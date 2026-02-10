"""Network router per ASHRAE 135-2024 Clause 6.

This module provides the routing table data structures and the
:class:`NetworkRouter` engine that interconnects multiple BACnet
networks, forwarding NPDUs, processing network layer messages, and
maintaining the routing table dynamically.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from bac_py.network.address import BACnetAddress
from bac_py.network.messages import (
    DisconnectConnectionToNetwork,
    EstablishConnectionToNetwork,
    IAmRouterToNetwork,
    ICouldBeRouterToNetwork,
    InitializeRoutingTable,
    InitializeRoutingTableAck,
    NetworkMessage,
    NetworkNumberIs,
    RejectMessageToNetwork,
    RouterAvailableToNetwork,
    RouterBusyToNetwork,
    RoutingTablePort,
    WhatIsNetworkNumber,
    WhoIsRouterToNetwork,
    decode_network_message,
    encode_network_message,
)
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.types.enums import (
    NetworkMessageType,
    NetworkPriority,
    NetworkReachability,
    RejectMessageReason,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.transport.port import TransportPort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RouterPort
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RouterPort:
    """A single router port connecting to a BACnet network.

    Each port represents one physical or logical attachment point of the
    router to a BACnet network.  The port owns a :class:`TransportPort`
    that handles the actual data-link send/receive.
    """

    port_id: int
    """Unique port identifier (1-255)."""

    network_number: int
    """DNET of the directly connected network (1-65534)."""

    transport: TransportPort
    """The data-link transport for this port."""

    mac_address: bytes
    """Local MAC address on this network."""

    max_npdu_length: int
    """Max NPDU size for this data link."""

    network_number_configured: bool = True
    """``True`` if manually configured, ``False`` if learned via Network-Number-Is."""


# ---------------------------------------------------------------------------
# RoutingTableEntry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RoutingTableEntry:
    """A single entry in the router's routing table (Clause 6.6.1)."""

    network_number: int
    """The reachable DNET (1-65534)."""

    port_id: int
    """Which port this network is reachable through."""

    next_router_mac: bytes | None = None
    """MAC of the next-hop router, or ``None`` if directly connected."""

    reachability: NetworkReachability = NetworkReachability.REACHABLE
    """Current reachability status."""

    busy_timeout_handle: asyncio.TimerHandle | None = field(
        default=None, repr=False, compare=False
    )
    """Handle for the 30-second congestion timer."""


# ---------------------------------------------------------------------------
# RoutingTable
# ---------------------------------------------------------------------------

# Default congestion timeout per BACnet specification (seconds).
_BUSY_TIMEOUT_SECONDS: float = 30.0


class RoutingTable:
    """Router's complete routing table (Clause 6.6.1).

    Manages reachability information for all known networks.  All
    mutating operations are synchronous and intended to be called from
    the asyncio event loop thread.
    """

    def __init__(self) -> None:
        self._ports: dict[int, RouterPort] = {}
        self._entries: dict[int, RoutingTableEntry] = {}

    # -- Port management ----------------------------------------------------

    def add_port(self, port: RouterPort) -> None:
        """Register a router port and create a directly-connected routing entry.

        The port's *network_number* is automatically added to the
        routing table as a directly-connected entry (no next-hop router).

        :param port: The :class:`RouterPort` to register.
        :raises ValueError: If a port with the same *port_id* or a route for
            the same *network_number* already exists.
        """
        if port.port_id in self._ports:
            msg = f"Port {port.port_id} already registered"
            raise ValueError(msg)
        if port.network_number in self._entries:
            msg = f"Network {port.network_number} already in routing table"
            raise ValueError(msg)
        self._ports[port.port_id] = port
        self._entries[port.network_number] = RoutingTableEntry(
            network_number=port.network_number,
            port_id=port.port_id,
            next_router_mac=None,
            reachability=NetworkReachability.REACHABLE,
        )

    def get_port(self, port_id: int) -> RouterPort | None:
        """Look up a :class:`RouterPort` by its identifier.

        :param port_id: The port identifier to look up.
        :returns: The :class:`RouterPort`, or ``None`` if not found.
        """
        return self._ports.get(port_id)

    def get_all_ports(self) -> list[RouterPort]:
        """Return all registered :class:`RouterPort` instances.

        :returns: A list of all ports managed by this routing table.
        """
        return list(self._ports.values())

    # -- Route queries ------------------------------------------------------

    def get_port_for_network(self, dnet: int) -> tuple[RouterPort, RoutingTableEntry] | None:
        """Find the port and routing entry that can reach *dnet*.

        :param dnet: The destination network number to look up.
        :returns: A ``(RouterPort, RoutingTableEntry)`` tuple, or ``None`` if
            no route to *dnet* is known.
        """
        entry = self._entries.get(dnet)
        if entry is None:
            return None
        port = self._ports.get(entry.port_id)
        if port is None:
            return None
        return port, entry

    def port_for_directly_connected(self, dnet: int) -> RouterPort | None:
        """Return the port if *dnet* is directly connected, else ``None``.

        :param dnet: The network number to check.
        :returns: The :class:`RouterPort` if the network is directly connected,
            or ``None`` if it is remote or unknown.
        """
        entry = self._entries.get(dnet)
        if entry is None or entry.next_router_mac is not None:
            return None
        return self._ports.get(entry.port_id)

    def get_reachable_networks(
        self,
        *,
        exclude_port: int | None = None,
        include_busy: bool = False,
    ) -> list[int]:
        """Return network numbers of reachable routing table entries.

        :param exclude_port: If given, exclude networks reachable through
            this port.  Used when responding to Who-Is-Router so we
            don't advertise networks back to the port that asked.
        :param include_busy: If ``True``, include networks marked BUSY
            (temporarily unreachable due to congestion).  Per
            Clause 6.6.3.2, Who-Is-Router responses must include
            temporarily unreachable networks.
        :returns: A list of reachable DNET numbers.
        """
        result: list[int] = []
        for entry in self._entries.values():
            if entry.reachability == NetworkReachability.UNREACHABLE:
                continue
            if entry.reachability == NetworkReachability.BUSY and not include_busy:
                continue
            if exclude_port is not None and entry.port_id == exclude_port:
                continue
            result.append(entry.network_number)
        return result

    def get_all_entries(self) -> list[RoutingTableEntry]:
        """Return all routing table entries.

        :returns: A list of all :class:`RoutingTableEntry` instances.
        """
        return list(self._entries.values())

    def get_entry(self, dnet: int) -> RoutingTableEntry | None:
        """Look up a routing table entry by network number.

        :param dnet: The destination network number to look up.
        :returns: The :class:`RoutingTableEntry`, or ``None`` if not found.
        """
        return self._entries.get(dnet)

    # -- Route mutation -----------------------------------------------------

    def update_route(
        self,
        dnet: int,
        port_id: int,
        next_router_mac: bytes | None,
    ) -> None:
        """Add or update a routing table entry.

        If the entry already exists, its port, next-hop, and
        reachability are updated.  If the entry is new, it is created
        as REACHABLE.

        :param dnet: Destination network number.
        :param port_id: The port through which *dnet* is reachable.
        :param next_router_mac: MAC of the next-hop router, or ``None``
            if directly connected.
        :raises ValueError: If *port_id* is not a registered port.
        """
        if port_id not in self._ports:
            msg = f"Unknown port {port_id}"
            raise ValueError(msg)
        existing = self._entries.get(dnet)
        if existing is not None:
            # Cancel any pending busy timer on the old entry.
            if existing.busy_timeout_handle is not None:
                existing.busy_timeout_handle.cancel()
                existing.busy_timeout_handle = None
            existing.port_id = port_id
            existing.next_router_mac = next_router_mac
            existing.reachability = NetworkReachability.REACHABLE
        else:
            self._entries[dnet] = RoutingTableEntry(
                network_number=dnet,
                port_id=port_id,
                next_router_mac=next_router_mac,
                reachability=NetworkReachability.REACHABLE,
            )

    def remove_entry(self, dnet: int) -> None:
        """Remove a routing table entry.

        Any pending busy timer is cancelled.  Silently does nothing if
        the entry does not exist.

        :param dnet: The network number to remove.
        """
        entry = self._entries.pop(dnet, None)
        if entry is not None and entry.busy_timeout_handle is not None:
            entry.busy_timeout_handle.cancel()

    def update_port_network_number(self, port_id: int, new_network: int) -> None:
        """Update a port's network number and re-key its routing table entry.

        Called when a Network-Number-Is message provides the actual
        network number for a port that was not statically configured.
        Updates both the port's ``network_number`` and the routing
        table entry key so they remain consistent.

        :param port_id: The port whose network number changed.
        :param new_network: The new network number.
        :raises ValueError: If a route for *new_network* already exists
            (other than the port's own entry).
        """
        port = self._ports.get(port_id)
        if port is None:
            return
        old_network = port.network_number
        if old_network == new_network:
            return
        if new_network in self._entries:
            msg = f"Network {new_network} already in routing table"
            raise ValueError(msg)
        # Remove old entry and re-create with new key
        old_entry = self._entries.pop(old_network, None)
        port.network_number = new_network
        if old_entry is not None:
            old_entry.network_number = new_network
            self._entries[new_network] = old_entry
        else:
            self._entries[new_network] = RoutingTableEntry(
                network_number=new_network,
                port_id=port_id,
                next_router_mac=None,
                reachability=NetworkReachability.REACHABLE,
            )

    # -- Reachability management --------------------------------------------

    def mark_busy(
        self,
        dnet: int,
        timeout_callback: Callable[[], None] | None = None,
        *,
        timeout_seconds: float = _BUSY_TIMEOUT_SECONDS,
    ) -> None:
        """Mark a network as BUSY (congestion control).

        Starts a timer that will call *timeout_callback* after
        *timeout_seconds* (default 30 s per the BACnet specification).
        The callback is typically used to automatically restore the
        entry to REACHABLE.

        Does nothing if the entry does not exist.

        :param dnet: Network number to mark as busy.
        :param timeout_callback: Called when the busy timer expires.
        :param timeout_seconds: Timer duration in seconds.
        """
        entry = self._entries.get(dnet)
        if entry is None:
            return
        if entry.busy_timeout_handle is not None:
            entry.busy_timeout_handle.cancel()
            entry.busy_timeout_handle = None
        entry.reachability = NetworkReachability.BUSY
        if timeout_callback is not None:
            loop = asyncio.get_running_loop()
            entry.busy_timeout_handle = loop.call_later(timeout_seconds, timeout_callback)

    def mark_available(self, dnet: int) -> None:
        """Mark a network as REACHABLE (congestion lifted).

        Cancels any pending busy timer.  Does nothing if the entry
        does not exist.

        :param dnet: Network number to mark as available.
        """
        entry = self._entries.get(dnet)
        if entry is None:
            return
        if entry.busy_timeout_handle is not None:
            entry.busy_timeout_handle.cancel()
            entry.busy_timeout_handle = None
        entry.reachability = NetworkReachability.REACHABLE

    def mark_unreachable(self, dnet: int) -> None:
        """Mark a network as UNREACHABLE (permanent failure).

        Cancels any pending busy timer.  Does nothing if the entry
        does not exist.

        :param dnet: Network number to mark as unreachable.
        """
        entry = self._entries.get(dnet)
        if entry is None:
            return
        if entry.busy_timeout_handle is not None:
            entry.busy_timeout_handle.cancel()
            entry.busy_timeout_handle = None
        entry.reachability = NetworkReachability.UNREACHABLE


# ---------------------------------------------------------------------------
# Message-type mapping helper
# ---------------------------------------------------------------------------

_MSG_TYPE_MAP: dict[type[NetworkMessage], int] = {
    WhoIsRouterToNetwork: NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
    IAmRouterToNetwork: NetworkMessageType.I_AM_ROUTER_TO_NETWORK,
    ICouldBeRouterToNetwork: NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK,
    RejectMessageToNetwork: NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
    RouterBusyToNetwork: NetworkMessageType.ROUTER_BUSY_TO_NETWORK,
    RouterAvailableToNetwork: NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK,
    InitializeRoutingTable: NetworkMessageType.INITIALIZE_ROUTING_TABLE,
    InitializeRoutingTableAck: NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK,
    EstablishConnectionToNetwork: NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK,
    DisconnectConnectionToNetwork: NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK,
    WhatIsNetworkNumber: NetworkMessageType.WHAT_IS_NETWORK_NUMBER,
    NetworkNumberIs: NetworkMessageType.NETWORK_NUMBER_IS,
}


def _message_type_for(msg: NetworkMessage) -> int:
    """Return the :class:`NetworkMessageType` value for a message dataclass.

    :param msg: The :class:`NetworkMessage` instance to look up.
    :returns: The integer message type code.
    :raises TypeError: If no mapping exists for the message type.
    """
    mt = _MSG_TYPE_MAP.get(type(msg))
    if mt is None:
        raise TypeError(f"No message type mapping for {type(msg).__name__}")
    return mt


# ---------------------------------------------------------------------------
# NetworkRouter
# ---------------------------------------------------------------------------


class NetworkRouter:
    """BACnet router engine per Clause 6.6.

    Interconnects multiple BACnet networks via :class:`RouterPort`
    instances.  Forwards NPDUs between ports, processes network layer
    messages, and maintains the routing table dynamically.

    Optionally hosts a local application entity on one port, enabling
    the router device itself to participate in BACnet services.
    """

    def __init__(
        self,
        ports: list[RouterPort],
        *,
        application_port_id: int | None = None,
        application_callback: Callable[[bytes, BACnetAddress], None] | None = None,
    ) -> None:
        """Initialise the network router.

        :param ports: Router ports to manage.  Each port must have a
            unique *port_id* and *network_number*.
        :param application_port_id: If given, the port on which the
            router's own application entity resides.  Local
            traffic (and the local copy of global broadcasts)
            will be delivered to *application_callback* via this
            port.
        :param application_callback: Called with ``(apdu_bytes,
            source_address)`` when an APDU is delivered to the
            local application entity.
        """
        self._routing_table = RoutingTable()
        self._application_port_id = application_port_id
        self._application_callback = application_callback

        for port in ports:
            self._routing_table.add_port(port)

    # -- Lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Start all port transports, wire receive callbacks, and perform startup broadcasts.

        Per Clause 6.6.2, after starting transports, each port receives:

        1. A ``Network-Number-Is`` broadcast (if the port's network
           number is configured).
        2. An ``I-Am-Router-To-Network`` broadcast listing all networks
           reachable through *other* ports.
        """
        for port in self._routing_table.get_all_ports():
            port.transport.on_receive(partial(self._on_port_receive, port.port_id))
            await port.transport.start()

        # Startup broadcasts per Clause 6.6.2.
        for port in self._routing_table.get_all_ports():
            if port.network_number_configured:
                self._send_network_message_on_port(
                    port.port_id,
                    NetworkNumberIs(network=port.network_number, configured=True),
                    broadcast=True,
                )
            networks = self._routing_table.get_reachable_networks(exclude_port=port.port_id)
            if networks:
                self._send_network_message_on_port(
                    port.port_id,
                    IAmRouterToNetwork(networks=tuple(networks)),
                    broadcast=True,
                )

    async def stop(self) -> None:
        """Stop all port transports and cancel active routing table timers."""
        # Cancel any outstanding busy-timeout handles to prevent stale callbacks
        for entry in self._routing_table.get_all_entries():
            if entry.busy_timeout_handle is not None:
                entry.busy_timeout_handle.cancel()
                entry.busy_timeout_handle = None
        for port in self._routing_table.get_all_ports():
            await port.transport.stop()

    # -- Properties ---------------------------------------------------------

    @property
    def routing_table(self) -> RoutingTable:
        """The router's routing table."""
        return self._routing_table

    # -- Receive path -------------------------------------------------------

    def _on_port_receive(self, port_id: int, data: bytes, source_mac: bytes) -> None:
        """Handle a raw NPDU received on a port from the transport layer.

        Decodes the NPDU and delegates to :meth:`_process_npdu`.  Malformed
        NPDUs are logged and silently dropped.
        """
        try:
            npdu = decode_npdu(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed NPDU on port %d", port_id)
            return

        self._process_npdu(port_id, npdu, source_mac)

    def _process_npdu(self, port_id: int, npdu: NPDU, source_mac: bytes) -> None:
        """Route an NPDU per the forwarding flowchart (Figure 6-12).

        Decision sequence:

        1. Network message -- delegate to :meth:`_handle_network_message`.
        2. No DNET -- local delivery to the application entity.
        3. DNET == 0xFFFF -- local delivery + flood all other ports.
        4. DNET directly connected -- deliver on that port.
        5. DNET in routing table -- forward to next-hop router.
        6. Unknown DNET -- send Reject-Message-To-Network back.
        """
        if npdu.is_network_message:
            self._handle_network_message(port_id, npdu, source_mac)
            return

        dest = npdu.destination

        # Step 2: No destination (local traffic)
        if dest is None:
            self._deliver_to_application(port_id, npdu, source_mac)
            return

        dnet = dest.network if dest.network is not None else 0xFFFF

        # Step 3: Global broadcast
        if dnet == 0xFFFF:
            self._deliver_to_application(port_id, npdu, source_mac)
            self._forward_global_broadcast(port_id, npdu, source_mac)
            return

        # Step 4/5: Routed unicast or directed broadcast
        self._forward_to_network(port_id, npdu, source_mac, dnet)

    # -- Local application delivery -----------------------------------------

    def _deliver_to_application(self, port_id: int, npdu: NPDU, source_mac: bytes) -> None:
        """Deliver an APDU to the local application entity, if one is registered.

        Reconstructs the source :class:`~bac_py.network.address.BACnetAddress`
        from the NPDU's SNET/SADR (for routed messages) or from the arrival
        port's network number and the data-link source MAC.
        """
        if self._application_callback is None:
            return

        if npdu.source is not None:
            src_addr = npdu.source
        else:
            port = self._routing_table.get_port(port_id)
            network = port.network_number if port is not None else None
            src_addr = BACnetAddress(network=network, mac_address=source_mac)

        self._application_callback(npdu.apdu, src_addr)

    # -- Forwarding ---------------------------------------------------------

    def _forward_global_broadcast(
        self, arrival_port_id: int, npdu: NPDU, source_mac: bytes
    ) -> None:
        """Forward a global broadcast NPDU to all ports except the arrival port.

        Injects SNET/SADR and decrements the hop count before forwarding.
        """
        forwarded_npdu = self._prepare_forwarded_npdu(arrival_port_id, npdu, source_mac)
        if forwarded_npdu is None:
            return
        encoded = encode_npdu(forwarded_npdu)
        for port in self._routing_table.get_all_ports():
            if port.port_id == arrival_port_id:
                continue
            port.transport.send_broadcast(encoded)

    def _forward_to_network(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
        dnet: int,
    ) -> None:
        """Forward an NPDU toward *dnet*.

        Per Clause 6.6.3.5, sends a Reject-Message-To-Network back
        toward the source when the DNET is unknown, unreachable, or
        busy (congestion control per Clause 6.6.4).
        """
        result = self._routing_table.get_port_for_network(dnet)
        if result is None:
            logger.debug("No route to network %d, sending reject", dnet)
            self._send_reject_toward_source(
                arrival_port_id,
                npdu,
                source_mac,
                RejectMessageReason.NOT_DIRECTLY_CONNECTED,
                dnet,
            )
            return

        dest_port, entry = result

        # Reachability check (Clause 6.6.4)
        if entry.reachability == NetworkReachability.UNREACHABLE:
            logger.debug("Network %d unreachable, sending reject", dnet)
            self._send_reject_toward_source(
                arrival_port_id,
                npdu,
                source_mac,
                RejectMessageReason.NOT_DIRECTLY_CONNECTED,
                dnet,
            )
            return
        if entry.reachability == NetworkReachability.BUSY:
            logger.debug("Network %d busy, sending reject", dnet)
            self._send_reject_toward_source(
                arrival_port_id,
                npdu,
                source_mac,
                RejectMessageReason.ROUTER_BUSY,
                dnet,
            )
            return

        if entry.next_router_mac is None:
            self._deliver_to_directly_connected(arrival_port_id, npdu, source_mac, dest_port)
        else:
            self._forward_via_next_hop(arrival_port_id, npdu, source_mac, dest_port, entry)

    def _deliver_to_directly_connected(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
        dest_port: RouterPort,
    ) -> None:
        """Deliver to a directly-connected network.

        Strips DNET/DLEN/DADR and hop count from the NPCI.
        Injects SNET/SADR if not already present.
        """
        assert npdu.destination is not None

        source = self._inject_source(arrival_port_id, npdu, source_mac)

        # Build new NPDU without destination (local delivery on target port)
        dadr = npdu.destination.mac_address

        local_npdu = NPDU(
            is_network_message=npdu.is_network_message,
            expecting_reply=npdu.expecting_reply,
            priority=npdu.priority,
            destination=None,
            source=source,
            message_type=npdu.message_type,
            vendor_id=npdu.vendor_id,
            apdu=npdu.apdu,
            network_message_data=npdu.network_message_data,
        )
        encoded = encode_npdu(local_npdu)

        if len(dadr) == 0:
            # Directed broadcast on the destination network
            dest_port.transport.send_broadcast(encoded)
        else:
            # Unicast to specific station
            dest_port.transport.send_unicast(encoded, dadr)

    def _forward_via_next_hop(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
        dest_port: RouterPort,
        entry: RoutingTableEntry,
    ) -> None:
        """Forward an NPDU to a remote network via a next-hop router.

        Injects SNET/SADR, decrements hop count, and unicasts to
        the next-hop router's MAC address.
        """
        forwarded = self._prepare_forwarded_npdu(arrival_port_id, npdu, source_mac)
        if forwarded is None:
            return
        assert entry.next_router_mac is not None
        dest_port.transport.send_unicast(encode_npdu(forwarded), entry.next_router_mac)

    # -- NPDU manipulation helpers ------------------------------------------

    def _prepare_forwarded_npdu(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
    ) -> NPDU | None:
        """Prepare an NPDU for forwarding: inject SNET/SADR and decrement hop count.

        :returns: A new :class:`~bac_py.network.npdu.NPDU` ready for
            forwarding, or ``None`` if the hop count has been exhausted.
        """
        # Q2: Log if a routed NPDU (has SNET/SADR) still has the default
        # hop count of 255, which suggests no prior router decremented it.
        if npdu.source is not None and npdu.hop_count == 255:
            logger.debug(
                "Routed NPDU from SNET %s has default hop count 255",
                npdu.source.network,
            )

        new_hop_count = npdu.hop_count - 1
        if new_hop_count <= 0:
            logger.debug("Hop count exhausted, discarding NPDU")
            return None

        source = self._inject_source(arrival_port_id, npdu, source_mac)

        return NPDU(
            is_network_message=npdu.is_network_message,
            expecting_reply=npdu.expecting_reply,
            priority=npdu.priority,
            destination=npdu.destination,
            source=source,
            hop_count=new_hop_count,
            message_type=npdu.message_type,
            vendor_id=npdu.vendor_id,
            apdu=npdu.apdu,
            network_message_data=npdu.network_message_data,
        )

    def _inject_source(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
    ) -> BACnetAddress | None:
        """Inject SNET/SADR if not already present (Section 5.3).

        If the NPDU already has a source address, return it unchanged.
        Otherwise, build one from the arrival port's network number
        and the data-link source MAC.
        """
        if npdu.source is not None:
            return npdu.source
        port = self._routing_table.get_port(arrival_port_id)
        if port is None:
            return None
        return BACnetAddress(
            network=port.network_number,
            mac_address=source_mac,
        )

    # -- Network message send helpers ---------------------------------------

    def _send_network_message_on_port(
        self,
        port_id: int,
        msg: NetworkMessage,
        *,
        broadcast: bool = True,
        dest_mac: bytes | None = None,
    ) -> None:
        """Build and send a network-layer message on a specific port.

        :param port_id: The port to send on.
        :param msg: The network message dataclass to encode.
        :param broadcast: If ``True``, send as a local broadcast.
        :param dest_mac: If *broadcast* is ``False``, the destination
            MAC address for unicast delivery.
        """
        port = self._routing_table.get_port(port_id)
        if port is None:
            return
        msg_type = _message_type_for(msg)
        data = encode_network_message(msg)
        npdu = NPDU(
            is_network_message=True,
            message_type=msg_type,
            network_message_data=data,
        )
        encoded = encode_npdu(npdu)
        if broadcast:
            port.transport.send_broadcast(encoded)
        elif dest_mac is not None:
            port.transport.send_unicast(encoded, dest_mac)

    def _broadcast_network_message_all_except(
        self,
        exclude_port_id: int,
        msg: NetworkMessage,
    ) -> None:
        """Broadcast a network-layer message on all ports except the specified one.

        Used to re-broadcast messages received on one port to all other
        ports, as required by several Clause 6.6.3 message handlers.
        """
        for port in self._routing_table.get_all_ports():
            if port.port_id == exclude_port_id:
                continue
            self._send_network_message_on_port(port.port_id, msg, broadcast=True)

    # -- Network message handling -------------------------------------------

    def _handle_network_message(self, port_id: int, npdu: NPDU, source_mac: bytes) -> None:
        """Process a network layer message per Clauses 6.6.3.1-6.6.3.9.

        Decodes the message data and dispatches to the appropriate
        handler.  Unknown standard message types generate a
        Reject-Message-To-Network with reason UNKNOWN_MESSAGE_TYPE.
        """
        msg_type = npdu.message_type
        if msg_type is None:
            return

        try:
            msg = decode_network_message(msg_type, npdu.network_message_data)
        except ValueError:
            logger.warning(
                "Malformed network message type 0x%02X on port %d",
                msg_type,
                port_id,
            )
            return

        if isinstance(msg, WhoIsRouterToNetwork):
            self._handle_who_is_router(port_id, msg, npdu, source_mac)
        elif isinstance(msg, IAmRouterToNetwork):
            self._handle_i_am_router(port_id, msg, source_mac)
        elif isinstance(msg, RejectMessageToNetwork):
            self._handle_reject_message(port_id, msg, npdu, source_mac)
        elif isinstance(msg, RouterBusyToNetwork):
            self._handle_router_busy(port_id, msg, source_mac)
        elif isinstance(msg, RouterAvailableToNetwork):
            self._handle_router_available(port_id, msg, source_mac)
        elif isinstance(msg, InitializeRoutingTable):
            self._handle_init_routing_table(port_id, msg, source_mac)
        elif isinstance(msg, InitializeRoutingTableAck):
            self._handle_init_routing_table_ack(msg)
        elif isinstance(msg, WhatIsNetworkNumber):
            self._handle_what_is_network_number(port_id, npdu)
        elif isinstance(msg, NetworkNumberIs):
            self._handle_network_number_is(port_id, msg, npdu)
        elif isinstance(msg, ICouldBeRouterToNetwork):
            self._handle_i_could_be_router(port_id, msg, source_mac)
        elif isinstance(msg, EstablishConnectionToNetwork):
            self._handle_establish_connection(port_id, msg, source_mac)
        elif isinstance(msg, DisconnectConnectionToNetwork):
            self._handle_disconnect_connection(port_id, msg, source_mac)
        else:
            # Unknown or unsupported standard message type (Clause 6.4.4, reason 3).
            self._send_reject(port_id, source_mac, RejectMessageReason.UNKNOWN_MESSAGE_TYPE, 0)

    # -- Who-Is-Router-To-Network (Clause 6.6.3.2) -------------------------

    def _handle_who_is_router(
        self,
        port_id: int,
        msg: WhoIsRouterToNetwork,
        npdu: NPDU,
        source_mac: bytes,
    ) -> None:
        """Process a Who-Is-Router-To-Network message (Clause 6.6.3.2).

        If a specific DNET is requested and reachable through a different
        port, responds with I-Am-Router.  If the DNET is unknown, forwards
        the query to all other ports.  A wildcard query (no DNET) triggers
        an I-Am-Router listing all reachable networks (including BUSY).
        """
        if msg.network is not None:
            # Specific DNET requested.
            result = self._routing_table.get_port_for_network(msg.network)
            if result is not None:
                _, entry = result
                if entry.port_id != port_id:
                    # Reachable via a different port -- respond.
                    self._send_network_message_on_port(
                        port_id,
                        IAmRouterToNetwork(networks=(msg.network,)),
                        broadcast=True,
                    )
                # If reachable through the same port, don't reply.
            else:
                # Not found -- forward Who-Is out all other ports.
                # Inject SNET/SADR if the message came from a directly
                # connected device (no source in NPCI).
                forwarded = self._prepare_forwarded_npdu(port_id, npdu, source_mac)
                if forwarded is not None:
                    encoded = encode_npdu(forwarded)
                    for port in self._routing_table.get_all_ports():
                        if port.port_id == port_id:
                            continue
                        port.transport.send_broadcast(encoded)
        else:
            # Query all reachable networks.  Per Clause 6.6.3.2,
            # include temporarily unreachable (BUSY) networks.
            networks = self._routing_table.get_reachable_networks(
                exclude_port=port_id, include_busy=True
            )
            if networks:
                self._send_network_message_on_port(
                    port_id,
                    IAmRouterToNetwork(networks=tuple(networks)),
                    broadcast=True,
                )

    # -- I-Am-Router-To-Network (Clause 6.6.3.3) ---------------------------

    def _handle_i_am_router(
        self,
        port_id: int,
        msg: IAmRouterToNetwork,
        source_mac: bytes,
    ) -> None:
        """Process an I-Am-Router-To-Network message (Clause 6.6.3.3).

        Updates the routing table for each advertised network and
        re-broadcasts the message on all other ports.
        """
        for dnet in msg.networks:
            self._routing_table.update_route(dnet, port_id=port_id, next_router_mac=source_mac)
        # Re-broadcast on all other ports per Clause 6.6.3.3.
        self._broadcast_network_message_all_except(
            port_id, IAmRouterToNetwork(networks=msg.networks)
        )

    # -- Reject-Message-To-Network (Clause 6.6.3.5) ------------------------

    def _handle_reject_message(
        self,
        port_id: int,
        msg: RejectMessageToNetwork,
        npdu: NPDU,
        source_mac: bytes,
    ) -> None:
        """Process a Reject-Message-To-Network (Clause 6.6.3.5).

        Updates routing-table reachability based on the reject reason
        and relays the reject toward the original DADR destination.
        """
        if msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED:
            self._routing_table.mark_unreachable(msg.network)
        elif msg.reason == RejectMessageReason.ROUTER_BUSY:
            self._routing_table.mark_busy(
                msg.network,
                partial(self._routing_table.mark_available, msg.network),
            )

        # Relay toward the originator using normal routing (Clause 6.5).
        # The NPDU carries DNET/DADR addressing the original sender.
        if npdu.destination is not None:
            dest = npdu.destination
            dnet = dest.network if dest.network is not None else 0xFFFF
            if dnet == 0xFFFF:
                self._forward_global_broadcast(port_id, npdu, source_mac)
            else:
                self._forward_to_network(port_id, npdu, source_mac, dnet)

    # -- Router-Busy-To-Network (Clause 6.6.3.6) --------------------------

    def _handle_router_busy(
        self,
        port_id: int,
        msg: RouterBusyToNetwork,
        source_mac: bytes,
    ) -> None:
        """Process a Router-Busy-To-Network message (Clause 6.6.3.6).

        Marks the indicated networks as congested in the routing table
        and re-broadcasts the message on all other ports.
        """
        dnets = msg.networks
        if not dnets:
            # Empty list means all networks served by the sending router.
            dnets = tuple(
                e.network_number
                for e in self._routing_table.get_all_entries()
                if e.port_id == port_id and e.next_router_mac == source_mac
            )
        for dnet in dnets:
            self._routing_table.mark_busy(
                dnet,
                partial(self._routing_table.mark_available, dnet),
            )
        # Re-broadcast on all other ports (Clause 6.6.3.6).
        self._broadcast_network_message_all_except(
            port_id, RouterBusyToNetwork(networks=msg.networks)
        )

    # -- Router-Available-To-Network (Clause 6.6.3.7) ---------------------

    def _handle_router_available(
        self,
        port_id: int,
        msg: RouterAvailableToNetwork,
        source_mac: bytes,
    ) -> None:
        """Process a Router-Available-To-Network message (Clause 6.6.3.7).

        Clears the congestion flag for the indicated networks and
        re-broadcasts the availability on all other ports.
        """
        dnets = msg.networks
        if not dnets:
            # Empty list means all previously busy networks on this port.
            dnets = tuple(
                e.network_number
                for e in self._routing_table.get_all_entries()
                if e.reachability == NetworkReachability.BUSY and e.port_id == port_id
            )
        for dnet in dnets:
            self._routing_table.mark_available(dnet)
        # Re-broadcast on all other ports (Clause 6.6.3.7).
        self._broadcast_network_message_all_except(
            port_id, RouterAvailableToNetwork(networks=msg.networks)
        )

    # -- Initialize-Routing-Table (Clause 6.6.3.8) ------------------------

    def _handle_init_routing_table(
        self,
        port_id: int,
        msg: InitializeRoutingTable,
        source_mac: bytes,
    ) -> None:
        """Process an Initialize-Routing-Table message (Clause 6.6.3.8).

        An empty ports list is interpreted as a query: the complete routing
        table is returned in an Initialize-Routing-Table-Ack.  A non-empty
        ports list modifies the routing table (port_id 0 removes an entry)
        and the modification is acknowledged with an empty Ack.
        """
        if len(msg.ports) == 0:
            # Query: return full routing table.
            reply_ports: list[RoutingTablePort] = []
            for entry in self._routing_table.get_all_entries():
                reply_ports.append(
                    RoutingTablePort(
                        network=entry.network_number,
                        port_id=entry.port_id,
                        port_info=b"",
                    )
                )
            self._send_network_message_on_port(
                port_id,
                InitializeRoutingTableAck(ports=tuple(reply_ports)),
                broadcast=False,
                dest_mac=source_mac,
            )
        else:
            # Update: modify routing table per provided entries.
            for port_entry in msg.ports:
                if port_entry.port_id == 0:
                    self._routing_table.remove_entry(port_entry.network)
                else:
                    # Only update if the port_id is valid; silently
                    # skip unknown port IDs to avoid ValueError.
                    if self._routing_table.get_port(port_entry.port_id) is not None:
                        self._routing_table.update_route(
                            port_entry.network,
                            port_entry.port_id,
                            None,
                        )
            # Acknowledge without routing table data.
            self._send_network_message_on_port(
                port_id,
                InitializeRoutingTableAck(ports=()),
                broadcast=False,
                dest_mac=source_mac,
            )

    # -- Initialize-Routing-Table-Ack (Clause 6.6.3.9) --------------------

    def _handle_init_routing_table_ack(
        self,
        msg: InitializeRoutingTableAck,
    ) -> None:
        """Process an Initialize-Routing-Table-Ack (Clause 6.6.3.9).

        This is a response to a prior routing-table query.  Currently
        only logged for diagnostics; no routing-table updates are applied.
        """
        logger.debug(
            "Received Initialize-Routing-Table-Ack with %d port(s)",
            len(msg.ports),
        )

    # -- What-Is-Network-Number (Clause 6.4.19) ----------------------------

    def _handle_what_is_network_number(
        self,
        port_id: int,
        npdu: NPDU,
    ) -> None:
        """Respond to a What-Is-Network-Number request (Clause 6.4.19).

        Per spec, this message must not be routed -- it is silently
        ignored if SNET/SADR or DNET/DADR are present in the NPCI.
        Responds with Network-Number-Is only when the port's network
        number has been statically configured.
        """
        # Never routed -- ignore if SNET/SADR or DNET/DADR present.
        if npdu.source is not None or npdu.destination is not None:
            return
        port = self._routing_table.get_port(port_id)
        if port is not None and port.network_number_configured:
            self._send_network_message_on_port(
                port_id,
                NetworkNumberIs(network=port.network_number, configured=True),
                broadcast=True,
            )

    # -- Network-Number-Is (Clause 6.4.20) ---------------------------------

    def _handle_network_number_is(
        self,
        port_id: int,
        msg: NetworkNumberIs,
        npdu: NPDU,
    ) -> None:
        """Learn a network number from a Network-Number-Is message (Clause 6.4.20).

        Per spec, this message must not be routed -- it is silently
        ignored if SNET/SADR or DNET/DADR are present.  Only learns
        the number if the port's network number is not already statically
        configured and the source claims to be authoritative (configured=True).
        """
        # Never routed -- ignore if SNET/SADR or DNET/DADR present.
        if npdu.source is not None or npdu.destination is not None:
            return
        port = self._routing_table.get_port(port_id)
        if port is not None and not port.network_number_configured and msg.configured:
            self._routing_table.update_port_network_number(port_id, msg.network)

    # -- I-Could-Be-Router-To-Network (Clause 6.4.3) ----------------------

    def _handle_i_could_be_router(
        self,
        port_id: int,
        msg: ICouldBeRouterToNetwork,
        source_mac: bytes,
    ) -> None:
        """Process an I-Could-Be-Router-To-Network message (Clause 6.4.3).

        This is an informational message from a half-router indicating
        it could be configured to reach a network.  Logged for
        diagnostics; no routing table changes are applied.
        """
        logger.info(
            "I-Could-Be-Router-To-Network %d (perf=%d) from port %d MAC=%s",
            msg.network,
            msg.performance_index,
            port_id,
            source_mac.hex(),
        )

    # -- Establish-Connection-To-Network (Clause 6.4.9) ------------------

    def _handle_establish_connection(
        self,
        port_id: int,
        msg: EstablishConnectionToNetwork,
        source_mac: bytes,
    ) -> None:
        """Process an Establish-Connection-To-Network message (Clause 6.4.9).

        Demand-dial / PTP connections are not supported.  Responds with
        Reject-Message-To-Network with reason OTHER per Clause 6.4.4.
        """
        logger.debug(
            "Rejecting Establish-Connection-To-Network %d (not supported)",
            msg.network,
        )
        self._send_reject(port_id, source_mac, RejectMessageReason.OTHER, msg.network)

    # -- Disconnect-Connection-To-Network (Clause 6.4.10) ----------------

    def _handle_disconnect_connection(
        self,
        port_id: int,
        msg: DisconnectConnectionToNetwork,
        source_mac: bytes,
    ) -> None:
        """Process a Disconnect-Connection-To-Network message (Clause 6.4.10).

        Demand-dial / PTP connections are not supported.  Responds with
        Reject-Message-To-Network with reason OTHER per Clause 6.4.4.
        """
        logger.debug(
            "Rejecting Disconnect-Connection-To-Network %d (not supported)",
            msg.network,
        )
        self._send_reject(port_id, source_mac, RejectMessageReason.OTHER, msg.network)

    # -- Reject helper ------------------------------------------------------

    def _send_reject(
        self,
        port_id: int,
        dest_mac: bytes,
        reason: RejectMessageReason,
        dnet: int,
    ) -> None:
        """Send a Reject-Message-To-Network to a specific station.

        :param port_id: The port to send the reject on.
        :param dest_mac: Data-link MAC address of the recipient.
        :param reason: The :class:`RejectMessageReason` code.
        :param dnet: The network number being rejected.
        """
        self._send_network_message_on_port(
            port_id,
            RejectMessageToNetwork(reason=reason, network=dnet),
            broadcast=False,
            dest_mac=dest_mac,
        )

    def _send_reject_toward_source(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
        reason: RejectMessageReason,
        dnet: int,
    ) -> None:
        """Send a Reject-Message-To-Network back toward the originator.

        Per Clause 6.6.3.5, the Reject is sent toward the device that
        originated the request.  If the NPDU carries SNET/SADR (the
        originator is on a remote network), the Reject is routed using
        normal forwarding with DNET/DADR set to the originator.  If
        there is no SNET/SADR, the originator is directly connected on
        the arrival port so we unicast to its data-link MAC.
        """
        if npdu.source is not None:
            # Originator is remote -- build a routed Reject.
            msg = RejectMessageToNetwork(reason=reason, network=dnet)
            msg_type = _message_type_for(msg)
            data = encode_network_message(msg)
            reject_npdu = NPDU(
                is_network_message=True,
                message_type=msg_type,
                network_message_data=data,
                destination=npdu.source,
                hop_count=255,
            )
            encoded = encode_npdu(reject_npdu)
            # Route via the port that can reach SNET.
            assert npdu.source.network is not None  # guaranteed for routed NPDUs
            result = self._routing_table.get_port_for_network(npdu.source.network)
            if result is not None:
                out_port, entry = result
                if entry.next_router_mac is not None:
                    out_port.transport.send_unicast(encoded, entry.next_router_mac)
                elif len(npdu.source.mac_address) > 0:
                    out_port.transport.send_unicast(encoded, npdu.source.mac_address)
                else:
                    out_port.transport.send_broadcast(encoded)
            else:
                # Can't route back; fall back to arrival port
                self._send_reject(arrival_port_id, source_mac, reason, dnet)
        else:
            # Originator is directly connected on the arrival port.
            self._send_reject(arrival_port_id, source_mac, reason, dnet)

    # -- Application-layer send ---------------------------------------------

    def send(
        self,
        apdu: bytes,
        destination: BACnetAddress,
        *,
        expecting_reply: bool = True,
        priority: NetworkPriority = NetworkPriority.NORMAL,
    ) -> None:
        """Send an APDU from the router's local application entity.

        This is called by the application layer to send outbound
        messages.  The router wraps the APDU in an NPDU and routes
        it to the appropriate port based on the destination address.

        :param apdu: Application-layer PDU bytes.
        :param destination: Target :class:`~bac_py.network.address.BACnetAddress`.
        :param expecting_reply: Whether a reply is expected.
        :param priority: Network priority level.
        :raises RuntimeError: If no application port is configured or the
            configured application port is not found.
        """
        if self._application_port_id is None:
            msg = "No application port configured"
            raise RuntimeError(msg)

        app_port = self._routing_table.get_port(self._application_port_id)
        if app_port is None:
            msg = f"Application port {self._application_port_id} not found"
            raise RuntimeError(msg)

        # Local broadcast or unicast (no network specified)
        if destination.is_local:
            npdu = NPDU(
                is_network_message=False,
                expecting_reply=expecting_reply,
                priority=priority,
                apdu=apdu,
            )
            encoded = encode_npdu(npdu)
            if destination.is_broadcast:
                app_port.transport.send_broadcast(encoded)
            else:
                app_port.transport.send_unicast(encoded, destination.mac_address)
            return

        # Global broadcast
        if destination.is_global_broadcast:
            # Include SNET/SADR so remote devices can reply to us.
            app_source = BACnetAddress(
                network=app_port.network_number,
                mac_address=app_port.mac_address,
            )
            npdu = NPDU(
                is_network_message=False,
                expecting_reply=expecting_reply,
                priority=priority,
                destination=destination,
                source=app_source,
                hop_count=255,
                apdu=apdu,
            )
            encoded = encode_npdu(npdu)
            for port in self._routing_table.get_all_ports():
                port.transport.send_broadcast(encoded)
            return

        # Remote destination (has network number)
        dnet = destination.network
        if dnet is None:
            return

        result = self._routing_table.get_port_for_network(dnet)
        if result is None:
            logger.warning("No route to network %d for send", dnet)
            return

        dest_port, entry = result

        # Build NPDU with destination and SNET/SADR so the remote
        # device can route replies back to the router's application.
        app_source = BACnetAddress(
            network=app_port.network_number,
            mac_address=app_port.mac_address,
        )
        npdu = NPDU(
            is_network_message=False,
            expecting_reply=expecting_reply,
            priority=priority,
            destination=destination,
            source=app_source,
            hop_count=255,
            apdu=apdu,
        )
        encoded = encode_npdu(npdu)

        if entry.next_router_mac is not None:
            dest_port.transport.send_unicast(encoded, entry.next_router_mac)
        elif len(destination.mac_address) == 0:
            dest_port.transport.send_broadcast(encoded)
        else:
            dest_port.transport.send_unicast(encoded, destination.mac_address)
