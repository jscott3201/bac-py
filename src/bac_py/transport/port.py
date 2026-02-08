"""Transport port abstraction for the network layer.

Defines the ``TransportPort`` protocol that all data-link transports
(BACnet/IP, MS/TP, etc.) must satisfy so the network router can operate
over heterogeneous data links without coupling to a specific technology.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable


@runtime_checkable
class TransportPort(Protocol):
    """Abstract interface for a data-link transport port.

    Each transport port represents a single attachment to one BACnet
    network.  The network layer (and network router) interact with
    ports exclusively through this interface, using raw MAC-address
    bytes so that the same forwarding logic works regardless of the
    underlying data-link technology.

    MAC encoding conventions (by data-link type):
        - BACnet/IP:  6 bytes  (4-byte IPv4 + 2-byte port, big-endian)
        - MS/TP:      1 byte   (station address 0-254)
    """

    async def start(self) -> None:
        """Bind the underlying transport and begin listening."""
        ...

    async def stop(self) -> None:
        """Release resources and stop listening."""
        ...

    def on_receive(self, callback: Callable[[bytes, bytes], None]) -> None:
        """Register a callback for incoming NPDUs.

        Args:
            callback: Called with ``(npdu_bytes, source_mac)`` for each
                received datagram.  *source_mac* is the raw MAC address
                of the sender in the encoding native to this data-link.
        """
        ...

    def send_unicast(self, npdu: bytes, mac_address: bytes) -> None:
        """Send an NPDU to a specific station.

        Args:
            npdu: Encoded NPDU bytes.
            mac_address: Destination MAC in this port's native encoding.
        """
        ...

    def send_broadcast(self, npdu: bytes) -> None:
        """Send an NPDU as a local broadcast.

        Args:
            npdu: Encoded NPDU bytes.
        """
        ...

    @property
    def local_mac(self) -> bytes:
        """The MAC address of this port in its native encoding."""
        ...

    @property
    def max_npdu_length(self) -> int:
        """Maximum NPDU length supported by this data-link (Table 6-1)."""
        ...
