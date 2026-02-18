"""BACnet/SC Hub Connector (AB.5.2).

Maintains a persistent connection to a primary hub with automatic
reconnection and failover to a secondary hub when configured.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bac_py.transport.sc.connection import (
    SCConnection,
    SCConnectionConfig,
    SCConnectionState,
)
from bac_py.transport.sc.tls import SCTLSConfig, build_client_ssl_context
from bac_py.transport.sc.types import (
    SC_HUB_SUBPROTOCOL,
    SCHubConnectionStatus,
)
from bac_py.transport.sc.websocket import SCWebSocket

# Aliases for readable status references
_STATUS_NONE = SCHubConnectionStatus.NO_HUB_CONNECTION
_STATUS_PRIMARY = SCHubConnectionStatus.CONNECTED_TO_PRIMARY
_STATUS_FAILOVER = SCHubConnectionStatus.CONNECTED_TO_FAILOVER

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bac_py.transport.sc.bvlc import SCMessage
    from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

logger = logging.getLogger(__name__)


@dataclass
class SCHubConnectorConfig:
    """Configuration for an SC Hub Connector."""

    primary_hub_uri: str = ""
    failover_hub_uri: str | None = None
    tls_config: SCTLSConfig = field(default_factory=SCTLSConfig)
    connection_config: SCConnectionConfig = field(default_factory=SCConnectionConfig)
    min_reconnect_time: float = 10.0
    max_reconnect_time: float = 600.0
    max_bvlc_length: int = 1600
    max_npdu_length: int = 1497


class SCHubConnector:
    """BACnet/SC Hub Connector (AB.5.2).

    Maintains a persistent connection to the primary hub with automatic
    reconnection and failover to a secondary hub when configured.
    """

    def __init__(
        self,
        local_vmac: SCVMAC,
        local_uuid: DeviceUUID,
        config: SCHubConnectorConfig | None = None,
    ) -> None:
        self._config = config or SCHubConnectorConfig()
        self._local_vmac = local_vmac
        self._local_uuid = local_uuid
        self._connection: SCConnection | None = None
        self._connected_to: SCHubConnectionStatus = _STATUS_NONE
        self._reconnect_delay: float = self._config.min_reconnect_time
        self._running = False
        self._connect_task: asyncio.Task[None] | None = None
        self._connected_event = asyncio.Event()
        self._ssl_ctx = build_client_ssl_context(self._config.tls_config)

        # Callbacks
        self.on_message: Callable[[SCMessage, bytes | None], Awaitable[None] | None] | None = None
        self.on_status_change: Callable[[SCHubConnectionStatus], None] | None = None

    @property
    def is_connected(self) -> bool:
        """Whether the connector has an active hub connection."""
        return (
            self._connection is not None and self._connection.state == SCConnectionState.CONNECTED
        )

    @property
    def connection_status(self) -> SCHubConnectionStatus:
        """Current hub connection status."""
        return self._connected_to

    @property
    def local_vmac(self) -> SCVMAC:
        """Local VMAC address."""
        return self._local_vmac

    @local_vmac.setter
    def local_vmac(self, value: SCVMAC) -> None:
        self._local_vmac = value
        if self._connection:
            self._connection.local_vmac = value

    async def start(self) -> None:
        """Start the hub connector, begin connection attempts."""
        if self._ssl_ctx is None:
            logger.warning(
                "SC hub connector starting WITHOUT TLS — hub communication "
                "will be unencrypted and unauthenticated"
            )
        logger.info("SC hub connector starting")
        self._running = True
        self._connect_task = asyncio.create_task(self._connect_loop())

    async def stop(self) -> None:
        """Disconnect from hub and stop reconnection loop."""
        logger.info("SC hub connector stopping")
        self._running = False
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
            self._connect_task = None
        if self._connection:
            with contextlib.suppress(Exception):
                await self._connection._go_idle()
            self._connection = None
        self._set_status(_STATUS_NONE)

    async def send(self, msg: SCMessage) -> None:
        """Send a message to the hub.

        :raises ConnectionError: If not connected.
        """
        if not self.is_connected or self._connection is None:
            err = "Hub connector not connected"
            raise ConnectionError(err)
        await self._connection.send_message(msg)

    async def send_raw(self, data: bytes) -> None:
        """Send pre-encoded bytes to the hub.

        :raises ConnectionError: If not connected.
        """
        if not self.is_connected or self._connection is None:
            err = "Hub connector not connected"
            raise ConnectionError(err)
        await self._connection.send_raw(data)

    async def wait_connected(self, timeout: float | None = None) -> bool:
        """Wait until the connector is connected to a hub.

        :returns: True if connected, False if timeout expired.
        """
        try:
            if timeout is not None:
                async with asyncio.timeout(timeout):
                    await self._connected_event.wait()
            else:
                await self._connected_event.wait()
            return True
        except TimeoutError:
            return False

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _connect_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        try:
            while self._running:
                # Try primary hub
                if self._config.primary_hub_uri and await self._try_connect(
                    self._config.primary_hub_uri,
                    _STATUS_PRIMARY,
                ):
                    self._reset_backoff()
                    await self._run_until_disconnected()
                    if not self._running:
                        break
                    continue

                # Try failover hub
                if self._config.failover_hub_uri and await self._try_connect(
                    self._config.failover_hub_uri,
                    _STATUS_FAILOVER,
                ):
                    self._reset_backoff()
                    await self._run_until_disconnected()
                    if not self._running:
                        break
                    continue

                # Both failed — backoff and retry
                logger.warning(
                    "SC hub connection failed, retrying in %.1fs", self._reconnect_delay
                )
                await asyncio.sleep(self._reconnect_delay)
                self._increase_backoff()
        except asyncio.CancelledError:
            pass

    async def _try_connect(self, uri: str, status: SCHubConnectionStatus) -> bool:
        """Attempt to connect to a hub URI.

        :returns: True if connected successfully.
        """
        try:
            ws = await SCWebSocket.connect(
                uri, self._ssl_ctx, SC_HUB_SUBPROTOCOL, max_size=self._config.max_bvlc_length
            )
        except (OSError, ConnectionError, Exception) as exc:
            logger.debug("Failed to connect to %s: %s", uri, exc)
            return False

        conn = SCConnection(
            self._local_vmac,
            self._local_uuid,
            config=self._config.connection_config,
            max_bvlc_length=self._config.max_bvlc_length,
            max_npdu_length=self._config.max_npdu_length,
        )

        connected = asyncio.Event()
        vmac_collision = False

        def on_connected() -> None:
            connected.set()

        def on_vmac_collision() -> None:
            nonlocal vmac_collision
            vmac_collision = True

        conn.on_connected = on_connected
        conn.on_vmac_collision = on_vmac_collision
        conn.on_message = self.on_message

        await conn.initiate(ws)

        if vmac_collision:
            logger.warning("VMAC collision connecting to %s", uri)
            await conn._go_idle()  # Clean up connection resources
            return False

        if conn.state != SCConnectionState.CONNECTED:
            await conn._go_idle()  # Clean up connection resources
            return False

        conn.on_disconnected = self._on_disconnected
        self._connection = conn
        self._set_status(status)
        self._connected_event.set()
        if status == _STATUS_FAILOVER:
            logger.info("Failed over to hub: %s", uri)
        else:
            logger.info("Connected to hub: %s", uri)
        return True

    async def _run_until_disconnected(self) -> None:
        """Wait until the current connection drops."""
        disconnected = asyncio.Event()

        def on_disc() -> None:
            disconnected.set()

        if self._connection:
            self._connection.on_disconnected = on_disc

        await disconnected.wait()
        logger.info("Disconnected from hub")
        self._connected_event.clear()
        self._connection = None
        self._set_status(_STATUS_NONE)

    def _on_disconnected(self) -> None:
        """Handle unexpected disconnection."""
        self._connected_event.clear()

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    def _reset_backoff(self) -> None:
        self._reconnect_delay = self._config.min_reconnect_time

    def _increase_backoff(self) -> None:
        self._reconnect_delay = min(
            self._reconnect_delay * 2,
            self._config.max_reconnect_time,
        )

    def _set_status(self, status: SCHubConnectionStatus) -> None:
        self._connected_to = status
        if self.on_status_change:
            self.on_status_change(status)
