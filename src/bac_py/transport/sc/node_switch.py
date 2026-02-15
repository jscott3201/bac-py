"""BACnet/SC Node Switch (AB.4).

Manages direct peer-to-peer connections between SC nodes, bypassing
the hub for unicast traffic.  Listens for inbound direct connections
and initiates outbound connections via address resolution through
the hub.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bac_py.transport.sc.bvlc import AddressResolutionAckPayload, SCMessage
from bac_py.transport.sc.connection import (
    SCConnection,
    SCConnectionConfig,
    SCConnectionState,
)
from bac_py.transport.sc.tls import SCTLSConfig, build_client_ssl_context, build_server_ssl_context
from bac_py.transport.sc.types import (
    SC_DIRECT_SUBPROTOCOL,
    BvlcSCFunction,
)
from bac_py.transport.sc.websocket import SCWebSocket

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

logger = logging.getLogger(__name__)


@dataclass
class SCNodeSwitchConfig:
    """Configuration for an SC Node Switch."""

    enable: bool = False
    bind_address: str = "0.0.0.0"
    bind_port: int = 0
    tls_config: SCTLSConfig = field(default_factory=SCTLSConfig)
    connection_config: SCConnectionConfig = field(default_factory=SCConnectionConfig)
    address_resolution_timeout: float = 5.0
    max_connections: int = 100
    max_bvlc_length: int = 1600
    max_npdu_length: int = 1497


class SCNodeSwitch:
    """BACnet/SC Node Switch (AB.4).

    Manages direct connections between SC nodes.  Listens for inbound
    direct connections and initiates outbound connections via address
    resolution through the hub.
    """

    def __init__(
        self,
        local_vmac: SCVMAC,
        local_uuid: DeviceUUID,
        config: SCNodeSwitchConfig | None = None,
    ) -> None:
        self._config = config or SCNodeSwitchConfig()
        self._local_vmac = local_vmac
        self._local_uuid = local_uuid
        self._direct_connections: dict[SCVMAC, SCConnection] = {}
        self._server: asyncio.Server | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._pending_resolutions: dict[SCVMAC, asyncio.Future[list[str]]] = {}

        # Cache TLS contexts (immutable after init)
        self._client_ssl_ctx = build_client_ssl_context(self._config.tls_config)
        self._server_ssl_ctx = build_server_ssl_context(self._config.tls_config)

        # Callbacks
        self.on_message: Callable[[SCMessage, bytes | None], Awaitable[None] | None] | None = None

    @property
    def connections(self) -> dict[SCVMAC, SCConnection]:
        """Active direct connections indexed by peer VMAC."""
        return dict(self._direct_connections)

    @property
    def connection_count(self) -> int:
        """Number of active direct connections."""
        return len(self._direct_connections)

    @property
    def local_vmac(self) -> SCVMAC:
        """Local VMAC address."""
        return self._local_vmac

    @local_vmac.setter
    def local_vmac(self, value: SCVMAC) -> None:
        self._local_vmac = value

    async def start(self) -> None:
        """Start the node switch, listening for inbound direct connections."""
        if not self._config.enable:
            return
        if self._server_ssl_ctx is None:
            logger.warning(
                "SC Node Switch starting WITHOUT TLS on %s:%d — "
                "direct connections will be unencrypted and unauthenticated",
                self._config.bind_address,
                self._config.bind_port,
            )
        self._server = await asyncio.start_server(
            self._handle_inbound,
            self._config.bind_address,
            self._config.bind_port,
            ssl=self._server_ssl_ctx,
        )
        logger.info(
            "SC Node Switch listening on %s:%d",
            self._config.bind_address,
            self._config.bind_port,
        )

    async def stop(self) -> None:
        """Stop the node switch and close all direct connections."""
        logger.info("SC node switch stopping")
        # Cancel pending resolutions
        for fut in self._pending_resolutions.values():
            if not fut.done():
                fut.cancel()
        self._pending_resolutions.clear()

        # Close all direct connections (must happen BEFORE server.close()
        # because Python 3.13 wait_closed() blocks until handlers finish)
        for conn in list(self._direct_connections.values()):
            with contextlib.suppress(Exception):
                await conn._go_idle()
        self._direct_connections.clear()

        # Cancel pending tasks
        for task in self._client_tasks:
            if not task.done():
                task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
        self._client_tasks.clear()

        # Stop server (after connections are closed)
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("SC node switch stopped")

    def has_direct(self, dest: SCVMAC) -> bool:
        """Check if a direct connection exists to the given VMAC."""
        conn = self._direct_connections.get(dest)
        return conn is not None and conn.state == SCConnectionState.CONNECTED

    async def send_direct(self, dest: SCVMAC, msg: SCMessage) -> bool:
        """Send via direct connection if available.

        :returns: True if sent successfully, False if no direct connection.
        """
        conn = self._direct_connections.get(dest)
        if conn is None or conn.state != SCConnectionState.CONNECTED:
            return False
        try:
            await conn.send_message(msg)
            logger.debug("SC message sent via direct connection to %s", dest)
            return True
        except (ConnectionError, OSError):
            logger.debug("SC direct send failed to %s", dest)
            return False

    async def resolve_address(
        self,
        dest: SCVMAC,
        hub_send: Callable[[SCMessage], Awaitable[None]],
    ) -> list[str]:
        """Request WebSocket URIs for a peer via Address-Resolution through the hub.

        :param dest: Target VMAC to resolve.
        :param hub_send: Callback to send a message through the hub connection.
        :returns: List of WebSocket URIs for the target, empty if not resolved.
        """
        if dest in self._pending_resolutions:
            return await self._pending_resolutions[dest]

        if len(self._pending_resolutions) >= self._config.max_connections:
            logger.warning("SC address resolution cache full, dropping request")
            return []

        fut: asyncio.Future[list[str]] = asyncio.get_running_loop().create_future()
        self._pending_resolutions[dest] = fut

        msg = SCMessage(
            BvlcSCFunction.ADDRESS_RESOLUTION,
            message_id=0,
            originating=self._local_vmac,
            destination=dest,
        )
        try:
            await hub_send(msg)
            async with asyncio.timeout(self._config.address_resolution_timeout):
                return await fut
        except (TimeoutError, OSError, ConnectionError, asyncio.CancelledError):
            return []
        finally:
            self._pending_resolutions.pop(dest, None)

    def handle_address_resolution_ack(self, msg: SCMessage) -> None:
        """Handle an Address-Resolution-ACK received from the hub.

        Resolves the pending future for the originating VMAC.
        """
        if msg.originating and msg.originating in self._pending_resolutions:
            fut = self._pending_resolutions[msg.originating]
            if not fut.done():
                ack = AddressResolutionAckPayload.decode(msg.payload)
                fut.set_result(list(ack.websocket_uris))

    async def establish_direct(self, dest: SCVMAC, uris: list[str]) -> bool:
        """Try connecting to a peer using resolved URIs.

        :returns: True if connected successfully.
        """
        if len(self._direct_connections) >= self._config.max_connections:
            logger.debug("SC direct connection limit reached (%d)", self._config.max_connections)
            return False

        logger.debug("SC establishing direct connection to %s via %s", dest, uris)
        for uri in uris:
            if not uri.startswith(("ws://", "wss://")):
                logger.warning(
                    "SC ignoring non-WebSocket URI in address resolution: %s",
                    uri,
                )
                continue
            try:
                ws = await SCWebSocket.connect(
                    uri,
                    self._client_ssl_ctx,
                    SC_DIRECT_SUBPROTOCOL,
                    max_size=self._config.max_bvlc_length,
                )
            except (OSError, ConnectionError):
                continue

            conn = SCConnection(
                self._local_vmac,
                self._local_uuid,
                config=self._config.connection_config,
                max_bvlc_length=self._config.max_bvlc_length,
                max_npdu_length=self._config.max_npdu_length,
            )
            conn.on_message = self.on_message
            conn.on_disconnected = self._make_disconnect_cb(conn)

            await conn.initiate(ws)

            if conn.state == SCConnectionState.CONNECTED and conn.peer_vmac == dest:
                self._direct_connections[dest] = conn
                logger.info("Direct connection established to VMAC=%s via %s", dest, uri)
                return True

            # Wrong peer or failed — clean up
            with contextlib.suppress(Exception):
                await conn._go_idle()

        return False

    # ------------------------------------------------------------------
    # Inbound connection handling
    # ------------------------------------------------------------------

    async def _handle_inbound(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an inbound direct connection from a peer."""
        if len(self._direct_connections) >= self._config.max_connections:
            writer.close()
            return

        try:
            ws = await SCWebSocket.accept(
                reader, writer, SC_DIRECT_SUBPROTOCOL, max_size=self._config.max_bvlc_length
            )
        except Exception:
            logger.debug("Direct WebSocket accept failed", exc_info=True)
            writer.close()
            return

        conn = SCConnection(
            self._local_vmac,
            self._local_uuid,
            config=self._config.connection_config,
            max_bvlc_length=self._config.max_bvlc_length,
            max_npdu_length=self._config.max_npdu_length,
        )
        conn.on_message = self.on_message
        conn.on_connected = lambda: self._on_inbound_connected(conn)
        conn.on_disconnected = lambda: self._on_direct_disconnected(conn)

        task = asyncio.create_task(conn.accept(ws))
        self._client_tasks.add(task)
        task.add_done_callback(self._on_client_task_done)

    def _on_client_task_done(self, task: asyncio.Task[None]) -> None:
        """Clean up a finished client task and log unexpected errors."""
        self._client_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.debug("SC direct connection task failed: %s", task.exception())

    def _make_disconnect_cb(self, conn: SCConnection) -> Callable[[], None]:
        """Create a disconnect callback bound to a specific connection."""

        def cb() -> None:
            self._on_direct_disconnected(conn)

        return cb

    def _on_inbound_connected(self, conn: SCConnection) -> None:
        """Register an inbound direct connection after handshake."""
        if conn.peer_vmac is None:
            return
        self._direct_connections[conn.peer_vmac] = conn
        logger.info("Inbound direct connection from VMAC=%s", conn.peer_vmac)

    def _on_direct_disconnected(self, conn: SCConnection) -> None:
        """Remove a disconnected direct connection."""
        if (
            conn.peer_vmac
            and conn.peer_vmac in self._direct_connections
            and self._direct_connections[conn.peer_vmac] is conn
        ):
            del self._direct_connections[conn.peer_vmac]
        logger.info("Direct connection disconnected: VMAC=%s", conn.peer_vmac)
