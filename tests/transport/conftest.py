"""Shared fixtures for transport tests."""

from __future__ import annotations

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bbmd import BBMDManager, BDTEntry
from bac_py.transport.bvll import decode_bvll
from bac_py.types.enums import BvlcFunction, BvlcResultCode

# --- Shared test addresses ---

BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)
PEER_ADDR = BIPAddress(host="192.168.2.1", port=47808)
PEER_ADDR2 = BIPAddress(host="192.168.3.1", port=47808)
FD_ADDR = BIPAddress(host="10.0.0.50", port=47808)
FD_ADDR2 = BIPAddress(host="10.0.0.51", port=47808)
CLIENT_ADDR = BIPAddress(host="192.168.1.100", port=47808)
ALL_ONES_MASK = b"\xff\xff\xff\xff"


class SentCollector:
    """Collects sent messages for test assertions."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, BIPAddress]] = []
        self.local_broadcasts: list[tuple[bytes, BIPAddress]] = []

    def send(self, data: bytes, dest: BIPAddress) -> None:
        self.sent.append((data, dest))

    def local_broadcast(self, npdu: bytes, source: BIPAddress) -> None:
        self.local_broadcasts.append((npdu, source))

    def clear(self) -> None:
        self.sent.clear()
        self.local_broadcasts.clear()

    def find_sent_to(self, dest: BIPAddress) -> list[bytes]:
        return [data for data, d in self.sent if d == dest]

    def find_bvlc_results(self, dest: BIPAddress) -> list[BvlcResultCode]:
        results = []
        for data, d in self.sent:
            if d == dest:
                msg = decode_bvll(data)
                if msg.function == BvlcFunction.BVLC_RESULT and len(msg.data) >= 2:
                    results.append(BvlcResultCode(int.from_bytes(msg.data[0:2], "big")))
        return results


@pytest.fixture
def collector() -> SentCollector:
    return SentCollector()


@pytest.fixture
def bbmd(collector: SentCollector) -> BBMDManager:
    return BBMDManager(
        local_address=BBMD_ADDR,
        send_callback=collector.send,
        local_broadcast_callback=collector.local_broadcast,
    )


@pytest.fixture
def bbmd_with_bdt(bbmd: BBMDManager) -> BBMDManager:
    """BBMD with a 2-entry BDT (self + one peer), all-ones mask."""
    bbmd.set_bdt(
        [
            BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
            BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
        ]
    )
    return bbmd
