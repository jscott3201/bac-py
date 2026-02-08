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
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.types.enums import NetworkPriority, NetworkReachability

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

    Attributes:
        port_id: Unique port identifier (1-255).
        network_number: DNET of the directly connected network (1-65534).
        transport: The data-link transport for this port.
        mac_address: Local MAC address on this network.
        max_npdu_length: Max NPDU size for this data link.
        network_number_configured: ``True`` if the network number was
            manually configured, ``False`` if learned via
            Network-Number-Is.
    """

    port_id: int
    network_number: int
    transport: TransportPort
    mac_address: bytes
    max_npdu_length: int
    network_number_configured: bool = True


# ---------------------------------------------------------------------------
# RoutingTableEntry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RoutingTableEntry:
    """A single entry in the router's routing table (Clause 6.6.1).

    Attributes:
        network_number: The reachable DNET (1-65534).
        port_id: Which port this network is reachable through.
        next_router_mac: MAC of the next-hop router, or ``None`` if the
            network is directly connected to the port.
        reachability: Current reachability status.
        busy_timeout_handle: Handle for the 30-second congestion timer.
            Set when the entry is marked BUSY, cancelled when the entry
            returns to REACHABLE.
    """

    network_number: int
    port_id: int
    next_router_mac: bytes | None = None
    reachability: NetworkReachability = NetworkReachability.REACHABLE
    busy_timeout_handle: asyncio.TimerHandle | None = field(
        default=None, repr=False, compare=False
    )


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
        """Register a router port and create a directly-connected entry.

        The port's *network_number* is automatically added to the
        routing table as a directly-connected entry (no next-hop router).

        Raises:
            ValueError: If a port with the same *port_id* or a route for
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
        """Look up a port by its identifier."""
        return self._ports.get(port_id)

    def get_all_ports(self) -> list[RouterPort]:
        """Return all registered ports."""
        return list(self._ports.values())

    # -- Route queries ------------------------------------------------------

    def get_port_for_network(self, dnet: int) -> tuple[RouterPort, RoutingTableEntry] | None:
        """Find the port and entry that can reach *dnet*.

        Returns:
            A ``(RouterPort, RoutingTableEntry)`` tuple, or ``None`` if
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
        """Return the port if *dnet* is directly connected, else ``None``."""
        entry = self._entries.get(dnet)
        if entry is None or entry.next_router_mac is not None:
            return None
        return self._ports.get(entry.port_id)

    def get_reachable_networks(self, *, exclude_port: int | None = None) -> list[int]:
        """Return network numbers of all REACHABLE entries.

        Args:
            exclude_port: If given, exclude networks reachable through
                this port.  Used when responding to Who-Is-Router so we
                don't advertise networks back to the port that asked.
        """
        result: list[int] = []
        for entry in self._entries.values():
            if entry.reachability != NetworkReachability.REACHABLE:
                continue
            if exclude_port is not None and entry.port_id == exclude_port:
                continue
            result.append(entry.network_number)
        return result

    def get_all_entries(self) -> list[RoutingTableEntry]:
        """Return all routing table entries."""
        return list(self._entries.values())

    def get_entry(self, dnet: int) -> RoutingTableEntry | None:
        """Look up a routing table entry by network number."""
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

        Args:
            dnet: Destination network number.
            port_id: The port through which *dnet* is reachable.
            next_router_mac: MAC of the next-hop router, or ``None``
                if directly connected.

        Raises:
            ValueError: If *port_id* is not a registered port.
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
        """
        entry = self._entries.pop(dnet, None)
        if entry is not None and entry.busy_timeout_handle is not None:
            entry.busy_timeout_handle.cancel()

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
        *timeout_seconds* (default 30s per the BACnet specification).
        The callback is typically used to automatically restore the
        entry to REACHABLE.

        Does nothing if the entry does not exist.

        Args:
            dnet: Network number to mark as busy.
            timeout_callback: Called when the busy timer expires.
            timeout_seconds: Timer duration in seconds.
        """
        entry = self._entries.get(dnet)
        if entry is None:
            return
        # Cancel any existing timer.
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
        """
        entry = self._entries.get(dnet)
        if entry is None:
            return
        if entry.busy_timeout_handle is not None:
            entry.busy_timeout_handle.cancel()
            entry.busy_timeout_handle = None
        entry.reachability = NetworkReachability.UNREACHABLE


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
        """
        Args:
            ports: Router ports to manage.  Each port must have a
                unique *port_id* and *network_number*.
            application_port_id: If given, the port on which the
                router's own application entity resides.  Local
                traffic (and the local copy of global broadcasts)
                will be delivered to *application_callback* via this
                port.
            application_callback: Called with ``(apdu_bytes,
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
        """Start all port transports and wire receive callbacks."""
        for port in self._routing_table.get_all_ports():
            port.transport.on_receive(
                partial(self._on_port_receive, port.port_id)
            )
            await port.transport.start()

    async def stop(self) -> None:
        """Stop all port transports."""
        for port in self._routing_table.get_all_ports():
            await port.transport.stop()

    # -- Properties ---------------------------------------------------------

    @property
    def routing_table(self) -> RoutingTable:
        """The router's routing table."""
        return self._routing_table

    # -- Receive path -------------------------------------------------------

    def _on_port_receive(
        self, port_id: int, data: bytes, source_mac: bytes
    ) -> None:
        """Transport callback: raw NPDU received on a port."""
        try:
            npdu = decode_npdu(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed NPDU on port %d", port_id)
            return

        self._process_npdu(port_id, npdu, source_mac)

    def _process_npdu(
        self, port_id: int, npdu: NPDU, source_mac: bytes
    ) -> None:
        """Implement the forwarding flowchart (Figure 6-12).

        Steps:
        1. Network message? -> delegate to _handle_network_message
        2. No DNET? -> local delivery
        3. DNET == 0xFFFF? -> local delivery + flood all other ports
        4. DNET directly connected? -> deliver on that port
        5. DNET in routing table? -> forward to next-hop router
        6. Unknown DNET -> log (discovery deferred to Phase 5)
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

    def _deliver_to_application(
        self, port_id: int, npdu: NPDU, source_mac: bytes
    ) -> None:
        """Deliver an APDU to the local application entity (if present)."""
        if self._application_callback is None:
            return

        # Build source BACnetAddress
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
        """Forward a global broadcast to all ports except the arrival port."""
        forwarded_npdu = self._prepare_forwarded_npdu(
            arrival_port_id, npdu, source_mac
        )
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
        """Forward an NPDU toward *dnet*."""
        result = self._routing_table.get_port_for_network(dnet)
        if result is None:
            logger.debug(
                "No route to network %d, discarding", dnet
            )
            return

        dest_port, entry = result

        # Check if DNET is directly connected
        if entry.next_router_mac is None:
            self._deliver_to_directly_connected(
                arrival_port_id, npdu, source_mac, dest_port
            )
        else:
            self._forward_via_next_hop(
                arrival_port_id, npdu, source_mac, dest_port, entry
            )

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

        # Inject SNET/SADR if not present
        source = self._inject_source(arrival_port_id, npdu, source_mac)

        # Build new NPDU without destination (local delivery on target port)
        dadr = npdu.destination.mac_address

        if len(dadr) == 0:
            # Directed broadcast on the destination network
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
            dest_port.transport.send_broadcast(encode_npdu(local_npdu))
        else:
            # Unicast to specific station
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
            dest_port.transport.send_unicast(encode_npdu(local_npdu), dadr)

    def _forward_via_next_hop(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
        dest_port: RouterPort,
        entry: RoutingTableEntry,
    ) -> None:
        """Forward to a remote network via a next-hop router."""
        forwarded = self._prepare_forwarded_npdu(
            arrival_port_id, npdu, source_mac
        )
        if forwarded is None:
            return
        assert entry.next_router_mac is not None
        dest_port.transport.send_unicast(
            encode_npdu(forwarded), entry.next_router_mac
        )

    # -- NPDU manipulation helpers ------------------------------------------

    def _prepare_forwarded_npdu(
        self,
        arrival_port_id: int,
        npdu: NPDU,
        source_mac: bytes,
    ) -> NPDU | None:
        """Prepare an NPDU for forwarding: inject SNET/SADR, decrement hop count.

        Returns ``None`` if the hop count has reached zero.
        """
        # Hop count check
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

    # -- Network message handling (stub for Phase 5) ------------------------

    def _handle_network_message(
        self, port_id: int, npdu: NPDU, source_mac: bytes
    ) -> None:
        """Process a network layer message.

        Full handler implementations are added in Phase 5.
        """
        logger.debug(
            "Network message type 0x%02X on port %d (handlers pending)",
            npdu.message_type or 0,
            port_id,
        )

    # -- Application-layer send ---------------------------------------------

    def send(
        self,
        apdu: bytes,
        destination: BACnetAddress,
        *,
        expecting_reply: bool = True,
        priority: NetworkPriority = NetworkPriority.NORMAL,
    ) -> None:
        """Send an APDU to a destination address.

        This is called by the application layer to send outbound
        messages.  The router wraps the APDU in an NPDU and routes
        it to the appropriate port.

        Args:
            apdu: Application-layer PDU bytes.
            destination: Target BACnet address.
            expecting_reply: Whether a reply is expected.
            priority: Network priority level.
        """
        if self._application_port_id is None:
            msg = "No application port configured"
            raise RuntimeError(msg)

        app_port = self._routing_table.get_port(self._application_port_id)
        if app_port is None:
            msg = f"Application port {self._application_port_id} not found"
            raise RuntimeError(msg)

        # Local broadcast (no network specified, empty MAC)
        if destination.is_local and destination.is_broadcast:
            npdu = NPDU(
                is_network_message=False,
                expecting_reply=expecting_reply,
                priority=priority,
                apdu=apdu,
            )
            app_port.transport.send_broadcast(encode_npdu(npdu))
            return

        # Global broadcast
        if destination.is_global_broadcast:
            npdu = NPDU(
                is_network_message=False,
                expecting_reply=expecting_reply,
                priority=priority,
                destination=destination,
                apdu=apdu,
            )
            encoded = encode_npdu(npdu)
            for port in self._routing_table.get_all_ports():
                port.transport.send_broadcast(encoded)
            return

        # Local unicast (no network, has MAC)
        if destination.is_local and not destination.is_broadcast:
            npdu = NPDU(
                is_network_message=False,
                expecting_reply=expecting_reply,
                priority=priority,
                apdu=apdu,
            )
            app_port.transport.send_unicast(
                encode_npdu(npdu), destination.mac_address
            )
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

        # Build NPDU with destination
        npdu = NPDU(
            is_network_message=False,
            expecting_reply=expecting_reply,
            priority=priority,
            destination=destination,
            apdu=apdu,
        )
        encoded = encode_npdu(npdu)

        if dest_port.port_id == self._application_port_id:
            # Destination is on our own directly-connected network
            if entry.next_router_mac is None:
                # Directly connected: send to DADR or broadcast
                if len(destination.mac_address) == 0:
                    dest_port.transport.send_broadcast(encoded)
                else:
                    dest_port.transport.send_unicast(
                        encoded, destination.mac_address
                    )
            else:
                # Via next-hop router
                dest_port.transport.send_unicast(
                    encoded, entry.next_router_mac
                )
        else:
            # Different port from application: send toward destination
            if entry.next_router_mac is None:
                # Directly connected on the other port
                if len(destination.mac_address) == 0:
                    dest_port.transport.send_broadcast(encoded)
                else:
                    dest_port.transport.send_unicast(
                        encoded, destination.mac_address
                    )
            else:
                dest_port.transport.send_unicast(
                    encoded, entry.next_router_mac
                )
