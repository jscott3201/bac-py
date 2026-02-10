"""Shared test utilities for bac-py tests."""

from __future__ import annotations

from bac_py.network.address import BACnetAddress


class FakeNetworkLayer:
    """Minimal fake network layer for TSM and segmentation tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, BACnetAddress, bool]] = []

    def send(
        self, apdu: bytes, destination: BACnetAddress, *, expecting_reply: bool = True
    ) -> None:
        self.sent.append((apdu, destination, expecting_reply))

    def clear(self) -> None:
        self.sent.clear()


PEER = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
