"""NPDU and BACnet addressing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

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
    ) -> None: ...
