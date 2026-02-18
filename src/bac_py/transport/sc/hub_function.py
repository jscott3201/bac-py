"""BACnet/SC Hub Function (AB.5.3).

The Hub Function accepts BACnet/SC connections as hub connections and
routes unicast/broadcast BVLC-SC messages between connected nodes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bac_py.transport.sc.connection import (
    SCConnection,
    SCConnectionConfig,
    SCConnectionState,
)
from bac_py.transport.sc.tls import SCTLSConfig, build_server_ssl_context
from bac_py.transport.sc.types import SC_HUB_SUBPROTOCOL, VMAC_BROADCAST
from bac_py.transport.sc.websocket import SCWebSocket

if TYPE_CHECKING:
    from bac_py.transport.sc.bvlc import SCMessage
    from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

logger = logging.getLogger(__name__)
_DEBUG = logging.DEBUG


@dataclass
class SCHubConfig:
    """Configuration for an SC Hub Function."""

    bind_address: str = "0.0.0.0"
    bind_port: int = 4443
    tls_config: SCTLSConfig = field(default_factory=SCTLSConfig)
    connection_config: SCConnectionConfig = field(default_factory=SCConnectionConfig)
    max_connections: int = 1000
    max_bvlc_length: int = 6000
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
        self._pending_vmacs: dict[SCVMAC, float] = {}
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
        if ssl_ctx is None:
            logger.warning(
                "SC Hub Function starting WITHOUT TLS on %s:%d — "
                "client connections will be unencrypted and unauthenticated",
                self._config.bind_address,
                self._config.bind_port,
            )
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
        # Stop accepting new connections first to prevent new clients
        # arriving during shutdown cleanup.
        if self._server:
            self._server.close()

        # Force-close all connections (before wait_closed(), since
        # wait_closed() blocks until active connection handlers finish)
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
        self._pending_vmacs.clear()

        if self._server:
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
            ws = await SCWebSocket.accept(
                reader, writer, SC_HUB_SUBPROTOCOL, max_size=self._config.max_bvlc_length
            )
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
            hub_mode=True,
        )

        conn.on_connected = lambda: self._on_node_connected(conn)
        conn.on_disconnected = lambda: self._on_node_disconnected(conn)

        async def _route(msg: SCMessage, raw: bytes | None = None) -> None:
            await self._on_node_message(conn, msg, raw)

        conn.on_message = _route

        task = asyncio.create_task(self._accept_with_cleanup(conn, ws))
        self._client_tasks.add(task)
        task.add_done_callback(self._on_client_task_done)

    async def _accept_with_cleanup(self, conn: SCConnection, ws: SCWebSocket) -> None:
        """Run the accept handshake, releasing any pending VMAC on failure."""
        try:
            await conn.accept(ws, vmac_checker=self._check_vmac)
        finally:
            # If the handshake failed before on_connected, the VMAC is still
            # in _pending_vmacs.  discard() is idempotent so this is safe
            # even when on_connected already cleaned it up.
            if conn.peer_vmac:
                self._pending_vmacs.pop(conn.peer_vmac, None)

    def _on_client_task_done(self, task: asyncio.Task[None]) -> None:
        """Clean up a finished client task and log unexpected errors."""
        self._client_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.debug("SC hub client task failed: %s", task.exception())

    def _check_vmac(self, vmac: SCVMAC, uuid: DeviceUUID) -> bool:
        """Check if VMAC/UUID pair is acceptable (no collision).

        Atomically reserves the VMAC in ``_pending_vmacs`` to prevent a
        TOCTOU race between the check and the registration in
        ``_on_node_connected``.  The reservation is released by
        ``_on_node_connected`` on success or ``_accept_with_cleanup``
        on failure.

        Stale pending entries (older than 30s) are purged on each call.
        The pending set is capped at ``max_connections``.
        """
        # Purge stale pending entries (30-second TTL)
        now = time.monotonic()
        stale = [k for k, ts in self._pending_vmacs.items() if now - ts > 30.0]
        for k in stale:
            self._pending_vmacs.pop(k, None)

        if vmac in self._connections:
            existing = self._connections[vmac]
            if existing.peer_uuid != uuid:
                return False
        if vmac in self._pending_vmacs:
            return False
        if len(self._pending_vmacs) >= self._config.max_connections:
            return False
        self._pending_vmacs[vmac] = now
        return True

    def _on_node_connected(self, conn: SCConnection) -> None:
        """Register a newly connected node."""
        if conn.peer_vmac is None or conn.peer_uuid is None:
            return
        self._pending_vmacs.pop(conn.peer_vmac, None)

        # If this UUID was previously connected with a different VMAC, clean up
        if conn.peer_uuid in self._uuid_map:
            old_vmac = self._uuid_map[conn.peer_uuid]
            if old_vmac != conn.peer_vmac and old_vmac in self._connections:
                old_conn = self._connections.pop(old_vmac)
                task = asyncio.create_task(old_conn.disconnect())
                self._client_tasks.add(task)
                task.add_done_callback(self._on_client_task_done)

        self._connections[conn.peer_vmac] = conn
        self._uuid_map[conn.peer_uuid] = conn.peer_vmac
        logger.info("SC node connected: VMAC=%s", conn.peer_vmac)

    def _on_node_disconnected(self, conn: SCConnection) -> None:
        """Remove a disconnected node from the connection table."""
        if conn.peer_vmac:
            self._pending_vmacs.pop(conn.peer_vmac, None)
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

    async def _on_node_message(
        self, source: SCConnection, msg: SCMessage, raw: bytes | None = None
    ) -> None:
        """Route a message received from a connected node.

        - Unicast (destination set): forward to matching VMAC connection.
        - Broadcast (no destination): replicate to all except source.

        Per AB.5.3, the hub rewrites VMAC headers before forwarding:

        - **Unicast (AB.5.3.2):** Sets Originating VMAC to the sender's VMAC
          and removes the Destination VMAC.
        - **Broadcast (AB.5.3.3):** Sets Originating VMAC to the sender's
          VMAC and keeps the Destination VMAC as the broadcast address.
        """
        if source.peer_vmac is None:
            return

        # Validate originating VMAC matches the authenticated peer identity
        # to prevent VMAC spoofing attacks (Annex AB.6.2).
        if msg.originating and msg.originating != source.peer_vmac:
            logger.warning(
                "SC hub dropping message: originating VMAC %s does not match "
                "authenticated peer %s",
                msg.originating,
                source.peer_vmac,
            )
            return

        # Rewrite raw bytes for hub forwarding (AB.5.3)
        source_mac = source.peer_vmac.address
        if msg.destination and not msg.destination.is_broadcast:
            if __debug__ and logger.isEnabledFor(_DEBUG):
                logger.debug(
                    "SC hub routing unicast from %s to %s", source.peer_vmac, msg.destination
                )
            forwarded = _rewrite_for_hub_unicast(raw, source_mac) if raw else None
            await self._unicast(msg, source.peer_vmac, forwarded)
        else:
            if __debug__ and logger.isEnabledFor(_DEBUG):
                logger.debug("SC hub routing broadcast from %s", source.peer_vmac)
            forwarded = _rewrite_for_hub_broadcast(raw, source_mac) if raw else None
            await self._broadcast(msg, source.peer_vmac, forwarded)

    async def _unicast(self, msg: SCMessage, exclude: SCVMAC, raw: bytes | None = None) -> None:
        """Forward unicast message to destination VMAC.

        Uses pre-encoded *raw* bytes when available to skip re-encoding.
        """
        if msg.destination is None:
            return
        dest_conn = self._connections.get(msg.destination)
        if dest_conn and dest_conn.state == SCConnectionState.CONNECTED:
            try:
                if raw is not None:
                    await dest_conn.send_raw(raw)
                else:
                    await dest_conn.send_message(msg)
            except Exception:
                logger.debug("Hub unicast to %s failed", msg.destination, exc_info=True)

    async def _broadcast(self, msg: SCMessage, exclude: SCVMAC, raw: bytes | None = None) -> None:
        """Send message to all connected nodes except the source.

        Uses pre-encoded *raw* bytes when available to skip re-encoding.
        Batches writes to all connections first (synchronous buffer),
        then drains them concurrently for lower latency.
        """
        encoded = raw if raw is not None else msg.encode()
        targets = [
            conn
            for vmac, conn in self._connections.items()
            if vmac != exclude and conn.state == SCConnectionState.CONNECTED
        ]
        if len(targets) == 1:
            try:
                await targets[0].send_raw(encoded)
            except Exception:
                logger.debug("Hub broadcast to single target failed", exc_info=True)
        elif targets:
            # Phase 1: buffer writes synchronously (no await)
            needs_drain = []
            for conn in targets:
                try:
                    if conn.write_raw_no_drain(encoded):
                        needs_drain.append(conn)
                except Exception:
                    logger.debug("Hub broadcast buffer write failed", exc_info=True)
            # Phase 2: drain all concurrently
            if needs_drain:
                await asyncio.gather(
                    *(conn.drain() for conn in needs_drain),
                    return_exceptions=True,
                )


# ---------------------------------------------------------------------------
# Hub forwarding byte rewriters (AB.5.3)
# ---------------------------------------------------------------------------

# Control flag bit positions (AB.2.2)
_ORIGINATING_VMAC = 0x08
_DESTINATION_VMAC = 0x04
_OPTIONS_MASK = 0x03  # bits 0-1: data_options, dest_options


def _rewrite_for_hub_unicast(raw: bytes | None, source_vmac: bytes) -> bytes | None:
    """Rewrite raw BVLC-SC bytes for hub unicast forwarding (AB.5.3.2).

    Sets Originating VMAC to the source peer's VMAC and removes the
    Destination VMAC.  Preserves message function, message ID, header
    options, and payload.
    """
    if raw is None or len(raw) < 4:
        return raw

    flags = raw[1] & 0x0F
    offset = 4  # skip function(1) + flags(1) + message_id(2)

    # Skip existing VMAC fields to find where options+payload start
    if flags & _ORIGINATING_VMAC:
        offset += 6
    if flags & _DESTINATION_VMAC:
        offset += 6

    # New flags: Originating VMAC only + preserve options flag bits
    new_flags = (flags & _OPTIONS_MASK) | _ORIGINATING_VMAC

    # Build: header(4) + originating_vmac(6) + rest
    rest_len = len(raw) - offset
    result = bytearray(10 + rest_len)
    result[0] = raw[0]
    result[1] = new_flags
    result[2] = raw[2]
    result[3] = raw[3]
    result[4:10] = source_vmac
    if rest_len:
        result[10:] = raw[offset:]
    return bytes(result)


def _rewrite_for_hub_broadcast(raw: bytes | None, source_vmac: bytes) -> bytes | None:
    """Rewrite raw BVLC-SC bytes for hub broadcast forwarding (AB.5.3.3).

    Sets Originating VMAC to the source peer's VMAC and sets the
    Destination VMAC to the broadcast address (``FF:FF:FF:FF:FF:FF``).
    Preserves message function, message ID, header options, and payload.
    """
    if raw is None or len(raw) < 4:
        return raw

    flags = raw[1] & 0x0F
    offset = 4

    if flags & _ORIGINATING_VMAC:
        offset += 6
    if flags & _DESTINATION_VMAC:
        offset += 6

    # New flags: Originating + Destination VMAC + preserve options flags
    new_flags = (flags & _OPTIONS_MASK) | _ORIGINATING_VMAC | _DESTINATION_VMAC

    # Build: header(4) + originating_vmac(6) + broadcast_vmac(6) + rest
    rest_len = len(raw) - offset
    result = bytearray(16 + rest_len)
    result[0] = raw[0]
    result[1] = new_flags
    result[2] = raw[2]
    result[3] = raw[3]
    result[4:10] = source_vmac
    result[10:16] = VMAC_BROADCAST
    if rest_len:
        result[16:] = raw[offset:]
    return bytes(result)
