"""Network layer manager wiring transport to application per Clause 6."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.network.messages import (
    IAmRouterToNetwork,
    NetworkNumberIs,
    WhoIsRouterToNetwork,
    decode_network_message,
    encode_network_message,
)
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.types.enums import NetworkMessageType, NetworkPriority

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.transport.bip import BIPTransport

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RouterCacheEntry:
    """Cached router address for a remote network.

    Non-router devices maintain a cache mapping remote DNETs to the
    local MAC address of a router that can reach that network.
    """

    network: int
    router_mac: bytes  # 6-byte MAC of local router serving this DNET
    last_seen: float  # time.monotonic() timestamp


class NetworkLayer:
    """Network layer manager (non-router mode).

    Bridges the transport layer (BIPTransport) and the application layer.
    Handles NPDU wrapping/unwrapping for application-layer APDUs.

    Supports optional network number assignment and maintains a router
    cache for addressing remote networks via known routers.
    """

    def __init__(
        self,
        transport: BIPTransport,
        network_number: int | None = None,
        *,
        network_number_configured: bool = False,
    ) -> None:
        self._transport = transport
        self._network_number = network_number
        self._network_number_configured = network_number_configured
        self._router_cache: dict[int, RouterCacheEntry] = {}
        self._receive_callback: Callable[[bytes, BACnetAddress], None] | None = None
        transport.on_receive(self._on_npdu_received)

    @property
    def network_number(self) -> int | None:
        """The local network number, or ``None`` if unknown."""
        return self._network_number

    def on_receive(self, callback: Callable[[bytes, BACnetAddress], None]) -> None:
        """Register callback for received APDU data.

        Args:
            callback: Called with (apdu_bytes, source_address) for each
                received NPDU containing an application-layer APDU.
        """
        self._receive_callback = callback

    def send(
        self,
        apdu: bytes,
        destination: BACnetAddress,
        *,
        expecting_reply: bool = True,
        priority: NetworkPriority = NetworkPriority.NORMAL,
    ) -> None:
        """Send an APDU to a destination address.

        Wraps the APDU in an NPDU and sends via the transport layer.
        For remote destinations (DNET set), uses the router cache to
        send via a known router, or broadcasts if no router is cached.

        Args:
            apdu: Application-layer PDU bytes.
            destination: Target BACnet address.
            expecting_reply: Whether a reply is expected (affects routing).
            priority: Network priority level.
        """
        npdu = NPDU(
            is_network_message=False,
            expecting_reply=expecting_reply,
            priority=priority,
            destination=destination if not destination.is_local else None,
            hop_count=255,
            apdu=apdu,
        )
        npdu_bytes = encode_npdu(npdu)

        if destination.is_global_broadcast:
            self._transport.send_broadcast(npdu_bytes)
        elif destination.is_local and destination.is_broadcast:
            # Local broadcast (no network, no MAC)
            self._transport.send_broadcast(npdu_bytes)
        elif destination.is_local:
            # Local unicast
            bip_dest = self._bacnet_to_bip(destination)
            self._transport.send_unicast(npdu_bytes, bip_dest)
        else:
            # Remote destination (DNET is set, not global broadcast)
            self._send_remote(npdu_bytes, destination)

    @property
    def local_address(self) -> BIPAddress:
        """The local address of the underlying transport."""
        return self._transport.local_address

    def get_router_for_network(self, dnet: int) -> bytes | None:
        """Look up the cached router MAC for a remote network.

        Returns:
            The 6-byte router MAC if cached, or ``None`` if unknown.
        """
        entry = self._router_cache.get(dnet)
        return entry.router_mac if entry is not None else None

    # ------------------------------------------------------------------
    # Receive path
    # ------------------------------------------------------------------

    def _on_npdu_received(self, data: bytes, source: BIPAddress) -> None:
        """Process incoming NPDU from transport."""
        try:
            npdu = decode_npdu(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed NPDU")
            return

        if npdu.is_network_message:
            self._handle_network_message(npdu, source)
            return

        # Convert source BIPAddress to BACnetAddress, preserving source
        # network from the NPDU if present (for routed messages).
        if npdu.source is not None:
            src_addr = npdu.source
        else:
            src_addr = BACnetAddress(
                mac_address=source.encode(),
            )

        if self._receive_callback:
            self._receive_callback(npdu.apdu, src_addr)

    # ------------------------------------------------------------------
    # Network message handling (non-router)
    # ------------------------------------------------------------------

    def _handle_network_message(self, npdu: NPDU, source: BIPAddress) -> None:
        """Process network layer messages relevant to non-router devices.

        Only three message types are handled:
        - I-Am-Router-To-Network: populate router cache
        - What-Is-Network-Number: respond if configured
        - Network-Number-Is: learn network number if not configured
        """
        try:
            if npdu.message_type is None:
                logger.warning("Dropped network message with no message type")
                return
            msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        except (ValueError, IndexError):
            logger.warning(
                "Dropped malformed network message type %s",
                npdu.message_type,
            )
            return

        if isinstance(msg, IAmRouterToNetwork):
            self._handle_i_am_router(msg, source)
        elif isinstance(msg, WhoIsRouterToNetwork):
            # Non-routers do not respond to Who-Is-Router per spec.
            logger.debug("Ignoring Who-Is-Router-To-Network (non-router)")
        elif isinstance(msg, NetworkNumberIs):
            self._handle_network_number_is(msg, npdu)
        elif npdu.message_type == NetworkMessageType.WHAT_IS_NETWORK_NUMBER:
            self._handle_what_is_network_number(npdu)
        else:
            logger.debug(
                "Ignoring network message type %s (non-router)",
                npdu.message_type,
            )

    def _handle_i_am_router(
        self,
        msg: IAmRouterToNetwork,
        source: BIPAddress,
    ) -> None:
        """Populate router cache from I-Am-Router-To-Network."""
        router_mac = source.encode()
        now = time.monotonic()
        for dnet in msg.networks:
            self._router_cache[dnet] = RouterCacheEntry(
                network=dnet,
                router_mac=router_mac,
                last_seen=now,
            )
        logger.debug(
            "Router cache updated: %s via %s",
            msg.networks,
            source,
        )

    def _handle_what_is_network_number(self, npdu: NPDU) -> None:
        """Respond to What-Is-Network-Number if configured.

        Per Clause 6.4.19, this message must not be routed
        (ignore if SNET/SADR or DNET/DADR present).
        """
        if npdu.source is not None or npdu.destination is not None:
            return
        if self._network_number is not None and self._network_number_configured:
            self._send_network_number_is()

    def _handle_network_number_is(self, msg: NetworkNumberIs, npdu: NPDU) -> None:
        """Learn network number from Network-Number-Is.

        Per Clause 6.4.20, this message must not be routed
        (ignore if SNET/SADR or DNET/DADR present).
        Only learn if our number is not configured and the source
        is configured (authoritative).
        """
        if npdu.source is not None or npdu.destination is not None:
            return
        if not msg.configured:
            return
        if self._network_number_configured:
            return
        self._network_number = msg.network
        logger.info("Learned network number %d from Network-Number-Is", msg.network)

    # ------------------------------------------------------------------
    # Remote send helpers
    # ------------------------------------------------------------------

    def _send_remote(self, npdu_bytes: bytes, destination: BACnetAddress) -> None:
        """Send NPDU to a remote destination using the router cache.

        If a router is cached for the destination network, unicast to it.
        Otherwise broadcast the NPDU and issue a Who-Is-Router query.
        """
        assert destination.network is not None
        router_mac = self.get_router_for_network(destination.network)
        if router_mac is not None:
            # Cache hit: send to known router via unicast
            bip_dest = BIPAddress.decode(router_mac)
            self._transport.send_unicast(npdu_bytes, bip_dest)
        else:
            # Cache miss: broadcast NPDU (a router will pick it up)
            self._transport.send_broadcast(npdu_bytes)
            # Also issue Who-Is-Router-To-Network to populate cache
            self._send_who_is_router(destination.network)

    def _send_who_is_router(self, dnet: int) -> None:
        """Broadcast a Who-Is-Router-To-Network query."""
        msg = WhoIsRouterToNetwork(network=dnet)
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
            network_message_data=encode_network_message(msg),
        )
        self._transport.send_broadcast(encode_npdu(npdu))

    def _send_network_number_is(self) -> None:
        """Broadcast a Network-Number-Is message."""
        assert self._network_number is not None
        msg = NetworkNumberIs(
            network=self._network_number,
            configured=self._network_number_configured,
        )
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.NETWORK_NUMBER_IS,
            network_message_data=encode_network_message(msg),
        )
        self._transport.send_broadcast(encode_npdu(npdu))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _bacnet_to_bip(address: BACnetAddress) -> BIPAddress:
        """Convert a local BACnetAddress with 6-byte MAC to BIPAddress."""
        if len(address.mac_address) == 6:
            return BIPAddress.decode(address.mac_address)
        msg = (
            f"Cannot convert BACnetAddress with {len(address.mac_address)}-byte MAC to BIPAddress"
        )
        raise ValueError(msg)
