"""NPDU encoding/decoding, BACnet addressing, and network-layer management.

This package provides:

- :class:`NetworkSender` — protocol satisfied by both :class:`NetworkLayer`
  (non-router) and :class:`NetworkRouter` (router mode) for sending APDUs.
- ``NetworkLayer`` — bridges transport and application layers in non-router
  mode, handling NPDU wrapping/unwrapping.
- ``NetworkRouter`` — full BACnet router engine per Clause 6.6.
- ``BACnetAddress`` / ``NPDU`` — addressing and PDU dataclasses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

__all__ = ["NetworkSender"]

if TYPE_CHECKING:
    from bac_py.network.address import BACnetAddress
    from bac_py.types.enums import NetworkPriority


class NetworkSender(Protocol):
    """Protocol for objects that can send APDUs to the network.

    Both ``NetworkLayer`` (non-router) and ``NetworkRouter`` (router mode)
    satisfy this protocol.
    """

    def send(
        self,
        apdu: bytes,
        destination: BACnetAddress,
        *,
        expecting_reply: bool = ...,
        priority: NetworkPriority = ...,
    ) -> None:
        """Send an APDU to the given destination address."""
        ...
