"""BACnet Secure Connect (BACnet/SC) transport per ASHRAE 135-2020 Annex AB.

Provides ``SCTransport`` which implements the ``TransportPort`` protocol,
wiring together the hub connector, optional hub function, and optional
direct-connection node switch.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bac_py.transport.sc.bvlc import SCMessage
from bac_py.transport.sc.connection import SCConnectionConfig
from bac_py.transport.sc.hub_connector import SCHubConnector, SCHubConnectorConfig
from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
from bac_py.transport.sc.node_switch import SCNodeSwitch, SCNodeSwitchConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.types import BvlcSCFunction
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class SCTransportConfig:
    """Configuration for a BACnet/SC transport."""

    primary_hub_uri: str = ""
    """WebSocket URI of the primary hub (e.g. ``wss://hub.example.com:4443``)."""

    failover_hub_uri: str | None = None
    """WebSocket URI of the failover hub, if configured."""

    hub_function_config: SCHubConfig | None = None
    """If this node IS a hub, provide hub function configuration."""

    node_switch_config: SCNodeSwitchConfig | None = None
    """Optional direct peer-to-peer connection configuration."""

    tls_config: SCTLSConfig = field(default_factory=SCTLSConfig)
    """TLS configuration for hub connections and direct connections."""

    connection_config: SCConnectionConfig = field(default_factory=SCConnectionConfig)
    """Timeouts and tuning for individual SC connections."""

    vmac: SCVMAC | None = None
    """Local VMAC address (auto-generated if ``None``)."""

    device_uuid: DeviceUUID | None = None
    """Device UUID (auto-generated if ``None``)."""

    max_bvlc_length: int = 1600
    """Maximum BVLC-SC message length."""

    max_npdu_length: int = 1497
    """Maximum NPDU length."""

    min_reconnect_time: float = 5.0
    """Minimum reconnect delay in seconds."""

    max_reconnect_time: float = 600.0
    """Maximum reconnect delay in seconds."""


class SCTransport:
    """BACnet/SC transport implementing the ``TransportPort`` protocol.

    Wraps the hub connector (client to primary/failover hub), optional
    hub function (if this node is a hub), and optional node switch
    (for direct peer-to-peer connections).
    """

    def __init__(self, config: SCTransportConfig | None = None) -> None:
        self._config = config or SCTransportConfig()
        self._vmac = self._config.vmac or SCVMAC.random()
        self._uuid = self._config.device_uuid or DeviceUUID.generate()
        self._receive_callback: Callable[[bytes, bytes], None] | None = None
        self._send_tasks: set[asyncio.Task[None]] = set()

        # Hub connector (client)
        self._hub_connector = SCHubConnector(
            self._vmac,
            self._uuid,
            config=SCHubConnectorConfig(
                primary_hub_uri=self._config.primary_hub_uri,
                failover_hub_uri=self._config.failover_hub_uri,
                tls_config=self._config.tls_config,
                connection_config=self._config.connection_config,
                min_reconnect_time=self._config.min_reconnect_time,
                max_reconnect_time=self._config.max_reconnect_time,
                max_bvlc_length=self._config.max_bvlc_length,
                max_npdu_length=self._config.max_npdu_length,
            ),
        )
        self._hub_connector.on_message = self._on_hub_message

        # Optional hub function (server)
        self._hub_function: SCHubFunction | None = None
        if self._config.hub_function_config:
            self._hub_function = SCHubFunction(
                self._vmac,
                self._uuid,
                config=self._config.hub_function_config,
            )

        # Optional node switch (direct connections)
        self._node_switch: SCNodeSwitch | None = None
        if self._config.node_switch_config:
            ns = SCNodeSwitch(
                self._vmac,
                self._uuid,
                config=self._config.node_switch_config,
            )
            ns.on_message = self._on_direct_message
            self._node_switch = ns

    @property
    def local_mac(self) -> bytes:
        """6-byte VMAC address as raw bytes."""
        return self._vmac.address

    @property
    def max_npdu_length(self) -> int:
        """Maximum NPDU length for SC transport."""
        return self._config.max_npdu_length

    @property
    def hub_connector(self) -> SCHubConnector:
        """The hub connector instance."""
        return self._hub_connector

    @property
    def hub_function(self) -> SCHubFunction | None:
        """The hub function instance (if this node is a hub)."""
        return self._hub_function

    @property
    def node_switch(self) -> SCNodeSwitch | None:
        """The node switch instance (if direct connections enabled)."""
        return self._node_switch

    def on_receive(self, callback: Callable[[bytes, bytes], None]) -> None:
        """Register a callback for incoming NPDUs.

        :param callback: Called with ``(npdu_bytes, source_mac)`` for each
            received NPDU.  *source_mac* is the 6-byte VMAC of the sender.
        """
        self._receive_callback = callback

    async def start(self) -> None:
        """Start the SC transport: hub function, hub connector, node switch."""
        tls = self._config.tls_config
        if tls.allow_plaintext and not tls.certificate_path:
            logger.warning(
                "SC transport starting WITHOUT TLS — all traffic will be unencrypted. "
                "Configure certificate_path, private_key_path, and ca_certificates_path "
                "for production use (ASHRAE 135-2020 Annex AB.7.4)."
            )
        logger.info("SC transport starting: vmac=%s", self._vmac)
        if self._hub_function:
            await self._hub_function.start()
        if self._config.primary_hub_uri:
            await self._hub_connector.start()
        if self._node_switch:
            await self._node_switch.start()
        logger.info("SC transport started")

    async def stop(self) -> None:
        """Stop the SC transport and release all resources."""
        logger.info("SC transport stopping")
        if self._node_switch:
            with contextlib.suppress(Exception):
                await self._node_switch.stop()
        with contextlib.suppress(Exception):
            await self._hub_connector.stop()
        if self._hub_function:
            with contextlib.suppress(Exception):
                await self._hub_function.stop()
        # Cancel and clean up pending send tasks
        for task in self._send_tasks:
            if not task.done():
                task.cancel()
        if self._send_tasks:
            await asyncio.gather(*self._send_tasks, return_exceptions=True)
        self._send_tasks.clear()
        logger.info("SC transport stopped")

    def send_unicast(self, npdu: bytes, mac_address: bytes) -> None:
        """Send an NPDU to a specific VMAC.

        Tries direct connection first (if available), then hub.
        """
        dest = SCVMAC(mac_address)
        logger.debug("SC send unicast: %d bytes to %s", len(npdu), dest)
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0,
            originating=self._vmac,
            destination=dest,
            payload=npdu,
        )

        # Try direct connection first
        if self._node_switch and self._node_switch.has_direct(dest):
            self._schedule_send(self._send_direct_or_hub(dest, msg))
        else:
            self._schedule_send(self._send_via_hub(msg))

    def send_broadcast(self, npdu: bytes) -> None:
        """Send an NPDU as a broadcast via the hub."""
        logger.debug("SC send broadcast: %d bytes", len(npdu))
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0,
            originating=self._vmac,
            payload=npdu,
        )
        self._schedule_send(self._send_via_hub(msg))

    def _schedule_send(self, coro: Awaitable[None]) -> None:
        """Schedule an async send and track the task."""
        task = asyncio.ensure_future(coro)
        self._send_tasks.add(task)
        task.add_done_callback(self._send_tasks.discard)

    # ------------------------------------------------------------------
    # Internal send helpers
    # ------------------------------------------------------------------

    async def _send_via_hub(self, msg: SCMessage) -> None:
        """Send a message through the hub connector."""
        try:
            await self._hub_connector.send(msg)
        except ConnectionError:
            logger.debug("Hub not connected, message dropped")

    async def _send_direct_or_hub(self, dest: SCVMAC, msg: SCMessage) -> None:
        """Try direct connection first, fall back to hub."""
        if self._node_switch:
            ok = await self._node_switch.send_direct(dest, msg)
            if ok:
                return
        await self._send_via_hub(msg)

    # ------------------------------------------------------------------
    # Message receive handlers
    # ------------------------------------------------------------------

    async def _on_hub_message(self, msg: SCMessage) -> None:
        """Handle a message received from the hub connection."""
        if msg.function == BvlcSCFunction.ENCAPSULATED_NPDU and msg.payload:
            source_mac = msg.originating.address if msg.originating else b"\x00" * 6
            logger.debug("SC recv from hub: %d bytes from %s", len(msg.payload), msg.originating)
            if self._receive_callback:
                self._receive_callback(msg.payload, source_mac)
        elif msg.function == BvlcSCFunction.ADDRESS_RESOLUTION_ACK and self._node_switch:
            self._node_switch.handle_address_resolution_ack(msg)

    async def _on_direct_message(self, msg: SCMessage) -> None:
        """Handle a message received from a direct connection."""
        if msg.function == BvlcSCFunction.ENCAPSULATED_NPDU and msg.payload:
            source_mac = msg.originating.address if msg.originating else b"\x00" * 6
            logger.debug(
                "SC recv from direct: %d bytes from %s", len(msg.payload), msg.originating
            )
            if self._receive_callback:
                self._receive_callback(msg.payload, source_mac)


__all__ = [
    "SCTransport",
    "SCTransportConfig",
]
