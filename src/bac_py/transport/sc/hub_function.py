"""BACnet/SC Hub Function (AB.5.3).

The Hub Function accepts BACnet/SC connections as hub connections and
routes unicast/broadcast BVLC-SC messages between connected nodes.
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
from bac_py.transport.sc.tls import SCTLSConfig, build_server_ssl_context
from bac_py.transport.sc.types import SC_HUB_SUBPROTOCOL
from bac_py.transport.sc.websocket import SCWebSocket

if TYPE_CHECKING:
    from bac_py.transport.sc.bvlc import SCMessage
    from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

logger = logging.getLogger(__name__)


@dataclass
class SCHubConfig:
    """Configuration for an SC Hub Function."""

    bind_address: str = "0.0.0.0"
    bind_port: int = 4443
    tls_config: SCTLSConfig = field(default_factory=SCTLSConfig)
    connection_config: SCConnectionConfig = field(default_factory=SCConnectionConfig)
    max_connections: int = 1000
    max_bvlc_length: int = 1600
    max_npdu_length: int = 1497


class SCHubFunction:
    """BACnet/SC Hub Function (AB.5.3).

    WebSocket server that accepts hub connections from SC nodes.
    Routes unicast messages to destination VMAC, replicates broadcasts
    to all connected nodes except the source.
    """

    def __init__(
        self,
        hub_vmac: SCVMAC,
        hub_uuid: DeviceUUID,
        config: SCHubConfig | None = None,
    ) -> None:
        self._config = config or SCHubConfig()
        self._hub_vmac = hub_vmac
        self._hub_uuid = hub_uuid
        self._connections: dict[SCVMAC, SCConnection] = {}
        self._uuid_map: dict[DeviceUUID, SCVMAC] = {}
        self._server: asyncio.Server | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()

    @property
    def connections(self) -> dict[SCVMAC, SCConnection]:
        """Active connections indexed by peer VMAC."""
        return dict(self._connections)

    @property
    def connection_count(self) -> int:
        """Number of active hub connections."""
        return len(self._connections)

    async def start(self) -> None:
        """Start the hub function WebSocket server."""
        ssl_ctx = build_server_ssl_context(self._config.tls_config)
        self._server = await asyncio.start_server(
            self._handle_client,
            self._config.bind_address,
            self._config.bind_port,
            ssl=ssl_ctx,
        )
        logger.info(
            "SC Hub Function listening on %s:%d",
            self._config.bind_address,
            self._config.bind_port,
        )

    async def stop(self) -> None:
        """Stop the hub function, force-close all connections."""
        logger.info("SC hub function stopping")
        # Force-close all connections first (before closing the server,
        # since wait_closed() waits for active connection handlers)
        for conn in list(self._connections.values()):
            with contextlib.suppress(Exception):
                await conn._go_idle()

        # Cancel outstanding client tasks
        for task in self._client_tasks:
            if not task.done():
                task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
        self._client_tasks.clear()
        self._connections.clear()
        self._uuid_map.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("SC hub function stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an inbound WebSocket connection."""
        if len(self._connections) >= self._config.max_connections:
            writer.close()
            return

        try:
            ws = await SCWebSocket.accept(reader, writer, SC_HUB_SUBPROTOCOL)
        except Exception:
            logger.debug("WebSocket accept failed", exc_info=True)
            writer.close()
            return

        conn = SCConnection(
            self._hub_vmac,
            self._hub_uuid,
            config=self._config.connection_config,
            max_bvlc_length=self._config.max_bvlc_length,
            max_npdu_length=self._config.max_npdu_length,
        )

        conn.on_connected = lambda: self._on_node_connected(conn)
        conn.on_disconnected = lambda: self._on_node_disconnected(conn)
        conn.on_message = lambda msg: self._on_node_message(conn, msg)

        task = asyncio.ensure_future(conn.accept(ws, vmac_checker=self._check_vmac))
        self._client_tasks.add(task)
        task.add_done_callback(self._client_tasks.discard)

    def _check_vmac(self, vmac: SCVMAC, uuid: DeviceUUID) -> bool:
        """Check if VMAC/UUID pair is acceptable (no collision)."""
        if vmac in self._connections:
            existing = self._connections[vmac]
            if existing.peer_uuid != uuid:
                return False
        return True

    def _on_node_connected(self, conn: SCConnection) -> None:
        """Register a newly connected node."""
        if conn.peer_vmac is None or conn.peer_uuid is None:
            return

        # If this UUID was previously connected with a different VMAC, clean up
        if conn.peer_uuid in self._uuid_map:
            old_vmac = self._uuid_map[conn.peer_uuid]
            if old_vmac != conn.peer_vmac and old_vmac in self._connections:
                old_conn = self._connections.pop(old_vmac)
                task = asyncio.ensure_future(old_conn.disconnect())
                self._client_tasks.add(task)
                task.add_done_callback(self._client_tasks.discard)

        self._connections[conn.peer_vmac] = conn
        self._uuid_map[conn.peer_uuid] = conn.peer_vmac
        logger.info("SC node connected: VMAC=%s", conn.peer_vmac)

    def _on_node_disconnected(self, conn: SCConnection) -> None:
        """Remove a disconnected node from the connection table."""
        if (
            conn.peer_vmac
            and conn.peer_vmac in self._connections
            and self._connections[conn.peer_vmac] is conn
        ):
            del self._connections[conn.peer_vmac]
        if (
            conn.peer_uuid
            and conn.peer_uuid in self._uuid_map
            and self._uuid_map.get(conn.peer_uuid) == conn.peer_vmac
        ):
            del self._uuid_map[conn.peer_uuid]
        logger.info("SC node disconnected: VMAC=%s", conn.peer_vmac)

    async def _on_node_message(self, source: SCConnection, msg: SCMessage) -> None:
        """Route a message received from a connected node.

        - Unicast (destination set): forward to matching VMAC connection.
        - Broadcast (no destination): replicate to all except source.
        """
        if source.peer_vmac is None:
            return

        if msg.destination and not msg.destination.is_broadcast:
            logger.debug(f"SC hub routing unicast from {source.peer_vmac} to {msg.destination}")
            await self._unicast(msg, source.peer_vmac)
        else:
            logger.debug(f"SC hub routing broadcast from {source.peer_vmac}")
            await self._broadcast(msg, source.peer_vmac)

    async def _unicast(self, msg: SCMessage, exclude: SCVMAC) -> None:
        """Forward unicast message to destination VMAC."""
        if msg.destination is None:
            return
        dest_conn = self._connections.get(msg.destination)
        if dest_conn and dest_conn.state == SCConnectionState.CONNECTED:
            with contextlib.suppress(Exception):
                await dest_conn.send_message(msg)

    async def _broadcast(self, msg: SCMessage, exclude: SCVMAC) -> None:
        """Send message to all connected nodes except the source."""
        for vmac, conn in list(self._connections.items()):
            if vmac == exclude:
                continue
            if conn.state != SCConnectionState.CONNECTED:
                continue
            with contextlib.suppress(Exception):
                await conn.send_message(msg)
