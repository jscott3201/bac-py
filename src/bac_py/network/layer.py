"""Network layer manager wiring transport to application per Clause 6."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.types.enums import NetworkPriority

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.transport.bip import BIPTransport

logger = logging.getLogger(__name__)


class NetworkLayer:
    """Network layer manager.

    Bridges the transport layer (BIPTransport) and the application layer.
    Handles NPDU wrapping/unwrapping for application-layer APDUs.
    """

    def __init__(self, transport: BIPTransport) -> None:
        self._transport = transport
        self._receive_callback: Callable[[bytes, BACnetAddress], None] | None = None
        transport.on_receive(self._on_npdu_received)

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
            apdu=apdu,
        )
        npdu_bytes = encode_npdu(npdu)

        if destination.is_broadcast or destination.is_global_broadcast:
            self._transport.send_broadcast(npdu_bytes)
        else:
            # For local unicast, convert BACnetAddress to BIPAddress
            bip_dest = self._bacnet_to_bip(destination)
            self._transport.send_unicast(npdu_bytes, bip_dest)

    @property
    def local_address(self) -> BIPAddress:
        """The local address of the underlying transport."""
        return self._transport.local_address

    def _on_npdu_received(self, data: bytes, source: BIPAddress) -> None:
        """Process incoming NPDU from transport."""
        try:
            npdu = decode_npdu(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed NPDU")
            return

        if npdu.is_network_message:
            logger.debug("Ignoring network message type %s", npdu.message_type)
            return

        # Convert source BIPAddress to BACnetAddress
        src_addr = BACnetAddress(
            mac_address=source.encode(),
        )

        if self._receive_callback:
            self._receive_callback(npdu.apdu, src_addr)

    @staticmethod
    def _bacnet_to_bip(address: BACnetAddress) -> BIPAddress:
        """Convert a local BACnetAddress with 6-byte MAC to BIPAddress."""
        if len(address.mac_address) == 6:
            return BIPAddress.decode(address.mac_address)
        msg = (
            f"Cannot convert BACnetAddress with {len(address.mac_address)}-byte MAC to BIPAddress"
        )
        raise ValueError(msg)
