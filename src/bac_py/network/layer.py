"""Network layer manager wiring transport to application per Clause 6.

Provides :class:`NetworkLayer`, the non-router network layer manager that
bridges a single :class:`~bac_py.transport.bip.BIPTransport` with the
application layer by handling NPDU wrapping/unwrapping, router cache
management, and network-number learning.
"""

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
    """The remote DNET this entry provides a route to."""

    router_mac: bytes
    """6-byte MAC of the local router serving this DNET."""

    last_seen: float
    """``time.monotonic()`` timestamp of last I-Am-Router-To-Network update."""


# Default cache TTL: 5 minutes. Per Clause 6.6.3.3, stale routes
# should eventually be re-discovered via Who-Is-Router queries.
_DEFAULT_CACHE_TTL: float = 300.0


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
        cache_ttl: float = _DEFAULT_CACHE_TTL,
    ) -> None:
        """Initialise the network layer.

        :param transport: The BIP transport used for sending and receiving.
        :param network_number: Local network number, or ``None`` if unknown.
        :param network_number_configured: ``True`` if the network number was
            explicitly configured (prevents learning via
            Network-Number-Is messages).
        :param cache_ttl: Time-to-live in seconds for router cache entries.
        """
        self._transport = transport
        self._network_number = network_number
        self._network_number_configured = network_number_configured
        self._router_cache: dict[int, RouterCacheEntry] = {}
        self._cache_ttl = cache_ttl
        self._receive_callback: Callable[[bytes, BACnetAddress], None] | None = None
        self._network_message_listeners: dict[int, list[Callable[..., None]]] = {}
        transport.on_receive(self._on_npdu_received)

    @property
    def network_number(self) -> int | None:
        """The local network number, or ``None`` if unknown."""
        return self._network_number

    def on_receive(self, callback: Callable[[bytes, BACnetAddress], None]) -> None:
        """Register a callback for received application-layer APDUs.

        :param callback: Called with ``(apdu_bytes, source_address)`` for each
            received NPDU containing an application-layer APDU.
        """
        self._receive_callback = callback

    def register_network_message_handler(
        self,
        message_type: int,
        handler: Callable[..., None],
    ) -> None:
        """Register a handler for incoming network-layer messages.

        Multiple handlers may be registered for the same message type;
        they are invoked in registration order.

        :param message_type: Network message type code to listen for.
        :param handler: Called with ``(decoded_message, source_mac)`` when
            a matching network message is received.
        """
        self._network_message_listeners.setdefault(message_type, []).append(handler)

    def unregister_network_message_handler(
        self,
        message_type: int,
        handler: Callable[..., None],
    ) -> None:
        """Remove a previously registered network-layer message handler.

        :param message_type: Network message type code.
        :param handler: The handler to remove.
        """
        listeners = self._network_message_listeners.get(message_type, [])
        if handler in listeners:
            listeners.remove(handler)

    def send_network_message(
        self,
        message_type: int,
        data: bytes,
        destination: BACnetAddress | None = None,
    ) -> None:
        """Send a network-layer message (non-APDU).

        :param message_type: Network message type code.
        :param data: Encoded message payload.
        :param destination: Target address. If ``None``, broadcasts locally.
        """
        npdu = NPDU(
            is_network_message=True,
            message_type=message_type,
            network_message_data=data,
            destination=destination,
            hop_count=255 if destination is not None else 0,
        )
        npdu_bytes = encode_npdu(npdu)
        if destination is None or destination.is_broadcast or destination.is_global_broadcast:
            self._transport.send_broadcast(npdu_bytes)
        else:
            self._transport.send_unicast(npdu_bytes, destination.mac_address)

    def send(
        self,
        apdu: bytes,
        destination: BACnetAddress,
        *,
        expecting_reply: bool = True,
        priority: NetworkPriority = NetworkPriority.NORMAL,
    ) -> None:
        """Send an APDU to a destination address.

        Wraps the APDU in an :class:`~bac_py.network.npdu.NPDU` and sends
        via the transport layer.  For remote destinations (DNET set), uses
        the router cache to send via a known router, or broadcasts if no
        router is cached.

        :param apdu: Application-layer PDU bytes.
        :param destination: Target :class:`~bac_py.network.address.BACnetAddress`.
        :param expecting_reply: Whether a reply is expected (affects routing).
        :param priority: Network priority level.
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
            self._transport.send_unicast(npdu_bytes, destination.mac_address)
        else:
            # Remote destination (DNET is set, not global broadcast)
            self._send_remote(npdu_bytes, destination)

    @property
    def local_address(self) -> BIPAddress:
        """The local address of the underlying transport."""
        return self._transport.local_address

    def get_router_for_network(self, dnet: int) -> bytes | None:
        """Look up the cached router MAC for a remote network.

        Evicts the entry if it has exceeded the cache TTL.

        :param dnet: The destination network number to look up.
        :returns: The 6-byte router MAC if cached and fresh, or ``None``
            if unknown or stale.
        """
        entry = self._router_cache.get(dnet)
        if entry is None:
            return None
        if time.monotonic() - entry.last_seen > self._cache_ttl:
            del self._router_cache[dnet]
            return None
        return entry.router_mac

    # ------------------------------------------------------------------
    # Receive path
    # ------------------------------------------------------------------

    def _on_npdu_received(self, data: bytes, source_mac: bytes) -> None:
        """Process incoming NPDU from transport.

        Decodes the NPDU, delegates network-layer messages to
        :meth:`_handle_network_message`, and delivers application-
        layer APDUs to the registered receive callback.  The source
        address is reconstructed from the NPDU source field (if
        present, for routed messages) or from the raw transport MAC.

        :param data: Raw NPDU bytes received from the transport.
        :param source_mac: MAC address of the sender on the local network.
        """
        try:
            npdu = decode_npdu(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed NPDU")
            return

        if npdu.is_network_message:
            self._handle_network_message(npdu, source_mac)
            return

        # Convert source MAC to BACnetAddress, preserving source
        # network from the NPDU if present (for routed messages).
        if npdu.source is not None:
            src_addr = npdu.source
            # Learn that source_mac is a router for this remote network.
            # This enables efficient unicast routing for subsequent requests
            # to devices on that network (e.g. MS/TP devices behind a router).
            if src_addr.network is not None and src_addr.network != 0xFFFF:
                self._learn_router_from_source(src_addr.network, source_mac)
        else:
            src_addr = BACnetAddress(
                mac_address=source_mac,
            )

        if self._receive_callback:
            self._receive_callback(npdu.apdu, src_addr)

    # ------------------------------------------------------------------
    # Network message handling (non-router)
    # ------------------------------------------------------------------

    def _handle_network_message(self, npdu: NPDU, source_mac: bytes) -> None:
        """Process network layer messages relevant to non-router devices.

        Handles I-Am-Router-To-Network, What-Is-Network-Number, and
        Network-Number-Is internally, and dispatches all decoded
        messages to registered listeners.

        :param npdu: The decoded :class:`NPDU` containing the network message.
        :param source_mac: MAC address of the sender on the local network.
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
            self._handle_i_am_router(msg, source_mac)
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

        # Dispatch to registered listeners
        listeners = self._network_message_listeners.get(npdu.message_type, [])
        for listener in listeners:
            try:
                listener(msg, source_mac)
            except Exception:
                logger.debug("Error in network message listener", exc_info=True)

    def _handle_i_am_router(
        self,
        msg: IAmRouterToNetwork,
        source_mac: bytes,
    ) -> None:
        """Populate the router cache from an I-Am-Router-To-Network message.

        Creates or updates a :class:`RouterCacheEntry` for each advertised
        DNET, recording the source MAC and current timestamp.

        :param msg: The decoded :class:`IAmRouterToNetwork` message.
        :param source_mac: MAC address of the advertising router.
        """
        now = time.monotonic()
        for dnet in msg.networks:
            self._router_cache[dnet] = RouterCacheEntry(
                network=dnet,
                router_mac=source_mac,
                last_seen=now,
            )
        logger.debug(
            "Router cache updated: %s via %s",
            msg.networks,
            source_mac.hex(),
        )

    def _learn_router_from_source(self, snet: int, source_mac: bytes) -> None:
        """Learn a router path from a routed APDU's SNET/SADR fields.

        When an APDU arrives with SNET set, the transport-level sender
        (source_mac) is a router that can reach that remote network.
        Cache this path so subsequent requests to devices on that network
        can be sent as unicast to the router rather than broadcast.

        Only creates an entry if one doesn't already exist or the existing
        entry has expired, to avoid overwriting explicit I-Am-Router-To-Network
        entries.

        :param snet: The source network number from the NPDU.
        :param source_mac: Transport-level MAC of the router that forwarded
            the message.
        """
        existing = self._router_cache.get(snet)
        if existing is not None:
            now = time.monotonic()
            if now - existing.last_seen <= self._cache_ttl:
                # Fresh entry exists — just refresh the timestamp
                self._router_cache[snet] = RouterCacheEntry(
                    network=snet,
                    router_mac=existing.router_mac,
                    last_seen=now,
                )
                return
        # No entry or stale — learn from source
        self._router_cache[snet] = RouterCacheEntry(
            network=snet,
            router_mac=source_mac,
            last_seen=time.monotonic(),
        )
        logger.debug(
            "Learned router for network %d from routed APDU via %s",
            snet,
            source_mac.hex(),
        )

    def _handle_what_is_network_number(self, npdu: NPDU) -> None:
        """Respond to What-Is-Network-Number if configured.

        Per Clause 6.4.19, this message must not be routed
        (ignore if SNET/SADR or DNET/DADR present).

        :param npdu: The decoded :class:`NPDU` used to check routing fields.
        """
        if npdu.source is not None or npdu.destination is not None:
            return
        if self._network_number is not None and self._network_number_configured:
            self._send_network_number_is()

    def _handle_network_number_is(self, msg: NetworkNumberIs, npdu: NPDU) -> None:
        """Learn network number from a Network-Number-Is message.

        Per Clause 6.4.20, this message must not be routed
        (ignore if SNET/SADR or DNET/DADR present).
        Only learn if our number is not configured and the source
        is configured (authoritative).

        :param msg: The decoded :class:`NetworkNumberIs` message.
        :param npdu: The decoded :class:`NPDU` used to check routing fields.
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
        """Send an NPDU to a remote destination using the router cache.

        If a router is cached for the destination network, unicasts to it.
        Otherwise broadcasts the NPDU and issues a Who-Is-Router query to
        populate the cache for future sends.

        :param npdu_bytes: The encoded NPDU bytes to send.
        :param destination: Remote :class:`~bac_py.network.address.BACnetAddress`
            (must have a network number set).
        :raises ValueError: If *destination* has no network number.
        """
        if destination.network is None:
            msg = "Cannot send to remote destination without network number"
            raise ValueError(msg)
        router_mac = self.get_router_for_network(destination.network)
        if router_mac is not None:
            self._transport.send_unicast(npdu_bytes, router_mac)
        else:
            # Cache miss: broadcast NPDU (a router will pick it up)
            self._transport.send_broadcast(npdu_bytes)
            # Also issue Who-Is-Router-To-Network to populate cache
            self._send_who_is_router(destination.network)

    def _send_who_is_router(self, dnet: int) -> None:
        """Broadcast a Who-Is-Router-To-Network query.

        :param dnet: The remote network number to query for.
        """
        msg = WhoIsRouterToNetwork(network=dnet)
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
            network_message_data=encode_network_message(msg),
        )
        self._transport.send_broadcast(encode_npdu(npdu))

    def _send_network_number_is(self) -> None:
        """Broadcast a Network-Number-Is message."""
        if self._network_number is None:
            return
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
