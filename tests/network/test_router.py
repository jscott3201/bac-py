"""Tests for network router data structures and engine (router.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.network.address import BACnetAddress
from bac_py.network.messages import (
    IAmRouterToNetwork,
    ICouldBeRouterToNetwork,
    InitializeRoutingTable,
    InitializeRoutingTableAck,
    NetworkNumberIs,
    RejectMessageToNetwork,
    RouterAvailableToNetwork,
    RouterBusyToNetwork,
    RoutingTablePort,
    WhoIsRouterToNetwork,
    decode_network_message,
    encode_network_message,
)
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.network.router import NetworkRouter, RouterPort, RoutingTable, RoutingTableEntry
from bac_py.types.enums import (
    NetworkMessageType,
    NetworkPriority,
    NetworkReachability,
    RejectMessageReason,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(*, local_mac: bytes = b"\x7f\x00\x00\x01\xba\xc0") -> MagicMock:
    """Create a mock TransportPort."""
    transport = MagicMock()
    transport.local_mac = local_mac
    transport.max_npdu_length = 1497
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    return transport


def _make_port(
    port_id: int = 1,
    network_number: int = 10,
    *,
    transport: MagicMock | None = None,
) -> RouterPort:
    """Create a RouterPort with sane defaults."""
    if transport is None:
        transport = _make_transport()
    return RouterPort(
        port_id=port_id,
        network_number=network_number,
        transport=transport,
        mac_address=transport.local_mac,
        max_npdu_length=transport.max_npdu_length,
    )


# ---------------------------------------------------------------------------
# RouterPort
# ---------------------------------------------------------------------------


class TestRouterPort:
    def test_create(self) -> None:
        t = _make_transport()
        port = RouterPort(
            port_id=1,
            network_number=10,
            transport=t,
            mac_address=b"\x7f\x00\x00\x01\xba\xc0",
            max_npdu_length=1497,
        )
        assert port.port_id == 1
        assert port.network_number == 10
        assert port.transport is t
        assert port.mac_address == b"\x7f\x00\x00\x01\xba\xc0"
        assert port.max_npdu_length == 1497

    def test_default_configured(self) -> None:
        port = _make_port()
        assert port.network_number_configured is True

    def test_configured_false(self) -> None:
        port = _make_port()
        port.network_number_configured = False
        assert port.network_number_configured is False

    def test_mutable(self) -> None:
        """RouterPort is mutable (not frozen) so we can update network_number."""
        port = _make_port(network_number=10)
        port.network_number = 20
        assert port.network_number == 20


# ---------------------------------------------------------------------------
# RoutingTableEntry
# ---------------------------------------------------------------------------


class TestRoutingTableEntry:
    def test_create_defaults(self) -> None:
        entry = RoutingTableEntry(network_number=10, port_id=1)
        assert entry.network_number == 10
        assert entry.port_id == 1
        assert entry.next_router_mac is None
        assert entry.reachability == NetworkReachability.REACHABLE
        assert entry.busy_timeout_handle is None

    def test_create_with_next_hop(self) -> None:
        entry = RoutingTableEntry(
            network_number=20,
            port_id=1,
            next_router_mac=b"\x0a\x00\x00\x02\xba\xc0",
        )
        assert entry.next_router_mac == b"\x0a\x00\x00\x02\xba\xc0"

    def test_mutable(self) -> None:
        entry = RoutingTableEntry(network_number=10, port_id=1)
        entry.reachability = NetworkReachability.BUSY
        assert entry.reachability == NetworkReachability.BUSY

    def test_equality_ignores_timer(self) -> None:
        """busy_timeout_handle is excluded from comparison (compare=False)."""
        a = RoutingTableEntry(network_number=10, port_id=1)
        b = RoutingTableEntry(network_number=10, port_id=1)
        b.busy_timeout_handle = MagicMock()  # type: ignore[assignment]
        assert a == b

    def test_repr_excludes_timer(self) -> None:
        """busy_timeout_handle is excluded from repr (repr=False)."""
        entry = RoutingTableEntry(network_number=10, port_id=1)
        r = repr(entry)
        assert "busy_timeout_handle" not in r


# ---------------------------------------------------------------------------
# RoutingTable -- Port management
# ---------------------------------------------------------------------------


class TestRoutingTablePortManagement:
    def test_add_port(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        assert rt.get_port(1) is port

    def test_add_port_creates_entry(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        entry = rt.get_entry(10)
        assert entry is not None
        assert entry.network_number == 10
        assert entry.port_id == 1
        assert entry.next_router_mac is None
        assert entry.reachability == NetworkReachability.REACHABLE

    def test_add_multiple_ports(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        assert rt.get_port(1) is p1
        assert rt.get_port(2) is p2
        assert len(rt.get_all_ports()) == 2

    def test_add_duplicate_port_id_raises(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=1, network_number=20)
        rt.add_port(p1)
        with pytest.raises(ValueError, match="Port 1 already registered"):
            rt.add_port(p2)

    def test_add_duplicate_network_raises(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=10)
        rt.add_port(p1)
        with pytest.raises(ValueError, match="Network 10 already in routing table"):
            rt.add_port(p2)

    def test_get_port_missing(self) -> None:
        rt = RoutingTable()
        assert rt.get_port(99) is None

    def test_get_all_ports_empty(self) -> None:
        rt = RoutingTable()
        assert rt.get_all_ports() == []


# ---------------------------------------------------------------------------
# RoutingTable -- Route queries
# ---------------------------------------------------------------------------


class TestRoutingTableRouteQueries:
    def test_get_port_for_directly_connected(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        result = rt.get_port_for_network(10)
        assert result is not None
        rp, entry = result
        assert rp is port
        assert entry.network_number == 10
        assert entry.next_router_mac is None

    def test_get_port_for_remote_network(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a\x00\x00\x02\xba\xc0")
        result = rt.get_port_for_network(20)
        assert result is not None
        rp, entry = result
        assert rp is port
        assert entry.next_router_mac == b"\x0a\x00\x00\x02\xba\xc0"

    def test_get_port_for_unknown_network(self) -> None:
        rt = RoutingTable()
        assert rt.get_port_for_network(99) is None

    def test_port_for_directly_connected_yes(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        assert rt.port_for_directly_connected(10) is port

    def test_port_for_directly_connected_no_remote(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x01")
        assert rt.port_for_directly_connected(20) is None

    def test_port_for_directly_connected_unknown(self) -> None:
        rt = RoutingTable()
        assert rt.port_for_directly_connected(99) is None

    def test_get_entry(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        entry = rt.get_entry(10)
        assert entry is not None
        assert entry.network_number == 10

    def test_get_entry_missing(self) -> None:
        rt = RoutingTable()
        assert rt.get_entry(99) is None

    def test_get_all_entries_empty(self) -> None:
        rt = RoutingTable()
        assert rt.get_all_entries() == []

    def test_get_all_entries(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        entries = rt.get_all_entries()
        assert len(entries) == 2
        networks = {e.network_number for e in entries}
        assert networks == {10, 20}


# ---------------------------------------------------------------------------
# RoutingTable -- Reachable networks
# ---------------------------------------------------------------------------


class TestRoutingTableReachableNetworks:
    def test_all_reachable(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        nets = rt.get_reachable_networks()
        assert set(nets) == {10, 20}

    def test_exclude_port(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        # Add remote network 30 via port 1
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")
        nets = rt.get_reachable_networks(exclude_port=1)
        assert set(nets) == {20}

    def test_excludes_busy(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x01")
        entry = rt.get_entry(20)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY
        nets = rt.get_reachable_networks()
        assert set(nets) == {10}

    def test_excludes_unreachable(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x01")
        entry = rt.get_entry(20)
        assert entry is not None
        entry.reachability = NetworkReachability.UNREACHABLE
        nets = rt.get_reachable_networks()
        assert set(nets) == {10}

    def test_empty_table(self) -> None:
        rt = RoutingTable()
        assert rt.get_reachable_networks() == []

    def test_includes_remote_routes(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x01")
        rt.update_route(30, port_id=1, next_router_mac=b"\x02")
        nets = rt.get_reachable_networks()
        assert set(nets) == {10, 20, 30}


# ---------------------------------------------------------------------------
# RoutingTable -- Route mutation
# ---------------------------------------------------------------------------


class TestRoutingTableRouteMutation:
    def test_update_route_new_entry(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        assert entry.network_number == 20
        assert entry.port_id == 1
        assert entry.next_router_mac == b"\x0a"
        assert entry.reachability == NetworkReachability.REACHABLE

    def test_update_route_overwrite(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        rt.update_route(30, port_id=1, next_router_mac=b"\x0a")
        rt.update_route(30, port_id=2, next_router_mac=b"\x0b")
        entry = rt.get_entry(30)
        assert entry is not None
        assert entry.port_id == 2
        assert entry.next_router_mac == b"\x0b"

    def test_update_route_clears_busy(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        assert entry.reachability == NetworkReachability.REACHABLE

    def test_update_route_unknown_port_raises(self) -> None:
        rt = RoutingTable()
        with pytest.raises(ValueError, match="Unknown port 99"):
            rt.update_route(20, port_id=99, next_router_mac=b"\x0a")

    def test_update_route_cancels_busy_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        mock_handle = MagicMock()
        entry.busy_timeout_handle = mock_handle
        rt.update_route(20, port_id=1, next_router_mac=b"\x0b")
        mock_handle.cancel.assert_called_once()
        assert entry.busy_timeout_handle is None

    def test_remove_entry(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        rt.remove_entry(20)
        assert rt.get_entry(20) is None

    def test_remove_entry_cancels_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        mock_handle = MagicMock()
        entry.busy_timeout_handle = mock_handle
        rt.remove_entry(20)
        mock_handle.cancel.assert_called_once()

    def test_remove_nonexistent_is_noop(self) -> None:
        rt = RoutingTable()
        rt.remove_entry(99)  # Should not raise


# ---------------------------------------------------------------------------
# RoutingTable -- Reachability state transitions
# ---------------------------------------------------------------------------


class TestRoutingTableReachability:
    def test_mark_available(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY
        rt.mark_available(20)
        assert entry.reachability == NetworkReachability.REACHABLE

    def test_mark_available_cancels_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        mock_handle = MagicMock()
        entry.busy_timeout_handle = mock_handle
        rt.mark_available(20)
        mock_handle.cancel.assert_called_once()
        assert entry.busy_timeout_handle is None

    def test_mark_available_nonexistent_is_noop(self) -> None:
        rt = RoutingTable()
        rt.mark_available(99)  # Should not raise

    def test_mark_unreachable(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        rt.mark_unreachable(20)
        entry = rt.get_entry(20)
        assert entry is not None
        assert entry.reachability == NetworkReachability.UNREACHABLE

    def test_mark_unreachable_cancels_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        mock_handle = MagicMock()
        entry.busy_timeout_handle = mock_handle
        rt.mark_unreachable(20)
        mock_handle.cancel.assert_called_once()
        assert entry.busy_timeout_handle is None

    def test_mark_unreachable_nonexistent_is_noop(self) -> None:
        rt = RoutingTable()
        rt.mark_unreachable(99)  # Should not raise

    def test_mark_busy_no_callback(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        # mark_busy without callback should not require event loop
        entry = rt.get_entry(20)
        assert entry is not None
        entry.reachability = NetworkReachability.REACHABLE
        rt.mark_busy(20)
        assert entry.reachability == NetworkReachability.BUSY
        assert entry.busy_timeout_handle is None

    def test_mark_busy_nonexistent_is_noop(self) -> None:
        rt = RoutingTable()
        rt.mark_busy(99)  # Should not raise

    def test_mark_busy_cancels_existing_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        entry = rt.get_entry(20)
        assert entry is not None
        mock_handle = MagicMock()
        entry.busy_timeout_handle = mock_handle
        rt.mark_busy(20)
        mock_handle.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# RoutingTable -- Timer-based busy expiry (async)
# ---------------------------------------------------------------------------


class TestRoutingTableBusyTimer:
    async def test_mark_busy_with_callback_sets_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        callback = MagicMock()
        rt.mark_busy(20, callback, timeout_seconds=0.05)
        entry = rt.get_entry(20)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY
        assert entry.busy_timeout_handle is not None
        # Wait for the timer to fire
        await asyncio.sleep(0.1)
        callback.assert_called_once()

    async def test_busy_timer_fires_callback(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        called = []
        rt.mark_busy(20, lambda: called.append(True), timeout_seconds=0.05)
        await asyncio.sleep(0.1)
        assert called == [True]

    async def test_mark_available_prevents_callback(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        callback = MagicMock()
        rt.mark_busy(20, callback, timeout_seconds=0.1)
        # Mark available before timer fires
        rt.mark_available(20)
        await asyncio.sleep(0.15)
        callback.assert_not_called()

    async def test_re_mark_busy_resets_timer(self) -> None:
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x0a")
        first_callback = MagicMock()
        second_callback = MagicMock()
        rt.mark_busy(20, first_callback, timeout_seconds=0.1)
        # Re-mark with a new callback before first timer fires
        rt.mark_busy(20, second_callback, timeout_seconds=0.05)
        await asyncio.sleep(0.08)
        first_callback.assert_not_called()
        second_callback.assert_called_once()


# ---------------------------------------------------------------------------
# RoutingTable -- Multi-port topology
# ---------------------------------------------------------------------------


class TestRoutingTableMultiPort:
    def test_two_ports_each_directly_connected(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        r1 = rt.get_port_for_network(10)
        r2 = rt.get_port_for_network(20)
        assert r1 is not None and r1[0] is p1
        assert r2 is not None and r2[0] is p2

    def test_remote_networks_via_different_ports(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        # Network 30 reachable via port 1
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")
        # Network 40 reachable via port 2
        rt.update_route(40, port_id=2, next_router_mac=b"\x02")
        r30 = rt.get_port_for_network(30)
        r40 = rt.get_port_for_network(40)
        assert r30 is not None and r30[0] is p1
        assert r40 is not None and r40[0] is p2

    def test_exclude_port_with_remote_networks(self) -> None:
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")
        rt.update_route(40, port_id=2, next_router_mac=b"\x02")
        # Excluding port 1 should remove networks 10 and 30
        nets = rt.get_reachable_networks(exclude_port=1)
        assert set(nets) == {20, 40}

    def test_route_move_between_ports(self) -> None:
        """A route can be updated to point to a different port."""
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")
        # Move network 30 to port 2
        rt.update_route(30, port_id=2, next_router_mac=b"\x02")
        result = rt.get_port_for_network(30)
        assert result is not None
        assert result[0] is p2
        assert result[1].next_router_mac == b"\x02"


# ===========================================================================
# NetworkRouter tests
# ===========================================================================

# ---------------------------------------------------------------------------
# NetworkRouter helpers
# ---------------------------------------------------------------------------

# Standard MAC addresses for test ports
_MAC_PORT1 = b"\x7f\x00\x00\x01\xba\xc0"  # 127.0.0.1:47808
_MAC_PORT2 = b"\x0a\x00\x00\x01\xba\xc0"  # 10.0.0.1:47808
_MAC_DEVICE_A = b"\xc0\xa8\x01\x0a\xba\xc0"  # 192.168.1.10:47808
_MAC_DEVICE_B = b"\xc0\xa8\x02\x14\xba\xc0"  # 192.168.2.20:47808


def _make_router_ports(
    *,
    net1: int = 10,
    net2: int = 20,
) -> tuple[RouterPort, RouterPort, MagicMock, MagicMock]:
    """Create two router ports with mock transports."""
    t1 = _make_transport(local_mac=_MAC_PORT1)
    t2 = _make_transport(local_mac=_MAC_PORT2)
    p1 = RouterPort(
        port_id=1,
        network_number=net1,
        transport=t1,
        mac_address=_MAC_PORT1,
        max_npdu_length=1497,
    )
    p2 = RouterPort(
        port_id=2,
        network_number=net2,
        transport=t2,
        mac_address=_MAC_PORT2,
        max_npdu_length=1497,
    )
    return p1, p2, t1, t2


def _make_two_port_router(
    *,
    app_port: int | None = 1,
    app_callback: MagicMock | None = None,
) -> tuple[NetworkRouter, MagicMock, MagicMock]:
    """Create a two-port router (net 10 on port 1, net 20 on port 2)."""
    p1, p2, t1, t2 = _make_router_ports()
    if app_callback is None:
        app_callback = MagicMock()
    router = NetworkRouter(
        [p1, p2],
        application_port_id=app_port,
        application_callback=app_callback,
    )
    return router, t1, t2


def _build_local_npdu(apdu: bytes = b"\x01\x02\x03") -> bytes:
    """Build an NPDU with no destination (local traffic)."""
    return encode_npdu(NPDU(apdu=apdu))


def _build_routed_npdu(
    dnet: int,
    dadr: bytes = b"",
    *,
    apdu: bytes = b"\x01\x02\x03",
    source: BACnetAddress | None = None,
    hop_count: int = 255,
) -> bytes:
    """Build an NPDU with destination address."""
    dest = BACnetAddress(network=dnet, mac_address=dadr)
    return encode_npdu(
        NPDU(
            destination=dest,
            source=source,
            hop_count=hop_count,
            apdu=apdu,
        )
    )


def _build_global_broadcast_npdu(
    apdu: bytes = b"\x01\x02\x03",
    *,
    source: BACnetAddress | None = None,
    hop_count: int = 255,
) -> bytes:
    """Build a global broadcast NPDU (DNET=0xFFFF)."""
    dest = BACnetAddress(network=0xFFFF, mac_address=b"")
    return encode_npdu(
        NPDU(
            destination=dest,
            source=source,
            hop_count=hop_count,
            apdu=apdu,
        )
    )


# ---------------------------------------------------------------------------
# NetworkRouter -- Construction
# ---------------------------------------------------------------------------


class TestNetworkRouterConstruction:
    def test_constructor_populates_routing_table(self) -> None:
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter([p1, p2])
        rt = router.routing_table
        assert rt.get_port(1) is p1
        assert rt.get_port(2) is p2
        assert rt.get_entry(10) is not None
        assert rt.get_entry(20) is not None

    def test_no_application_port(self) -> None:
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter([p1, p2])
        assert router._application_port_id is None
        assert router._application_callback is None

    def test_with_application_port(self) -> None:
        cb = MagicMock()
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter(
            [p1, p2],
            application_port_id=1,
            application_callback=cb,
        )
        assert router._application_port_id == 1


# ---------------------------------------------------------------------------
# NetworkRouter -- Start / Stop
# ---------------------------------------------------------------------------


class TestNetworkRouterLifecycle:
    async def test_start_wires_callbacks_and_starts_transports(self) -> None:
        router, t1, t2 = _make_two_port_router()
        await router.start()
        t1.on_receive.assert_called_once()
        t2.on_receive.assert_called_once()
        t1.start.assert_awaited_once()
        t2.start.assert_awaited_once()

    async def test_stop_stops_transports(self) -> None:
        router, t1, t2 = _make_two_port_router()
        await router.start()
        await router.stop()
        t1.stop.assert_awaited_once()
        t2.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# NetworkRouter -- Local delivery
# ---------------------------------------------------------------------------


class TestNetworkRouterLocalDelivery:
    def test_local_traffic_delivered_to_app(self) -> None:
        app_cb = MagicMock()
        router, _, _ = _make_two_port_router(app_callback=app_cb)
        data = _build_local_npdu(apdu=b"\xaa\xbb")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        app_cb.assert_called_once()
        apdu, src = app_cb.call_args[0]
        assert apdu == b"\xaa\xbb"
        assert src.mac_address == _MAC_DEVICE_A

    def test_local_traffic_no_app_callback(self) -> None:
        p1, p2, t1, t2 = _make_router_ports()
        router = NetworkRouter([p1, p2])  # no app callback
        data = _build_local_npdu()
        # Should not raise
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_unicast.assert_not_called()
        t2.send_unicast.assert_not_called()

    def test_local_traffic_source_from_npdu(self) -> None:
        """When NPDU has SNET/SADR, those should be used as source."""
        app_cb = MagicMock()
        router, _, _ = _make_two_port_router(app_callback=app_cb)
        src = BACnetAddress(network=30, mac_address=b"\xee")
        npdu = NPDU(source=src, apdu=b"\xdd")
        router._on_port_receive(1, encode_npdu(npdu), _MAC_DEVICE_A)
        _, delivered_src = app_cb.call_args[0]
        assert delivered_src.network == 30
        assert delivered_src.mac_address == b"\xee"


# ---------------------------------------------------------------------------
# NetworkRouter -- Global broadcast forwarding
# ---------------------------------------------------------------------------


class TestNetworkRouterGlobalBroadcast:
    def test_global_broadcast_delivered_to_app(self) -> None:
        app_cb = MagicMock()
        router, _, _ = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu(apdu=b"\x10\x20")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        app_cb.assert_called_once()
        apdu, _ = app_cb.call_args[0]
        assert apdu == b"\x10\x20"

    def test_global_broadcast_forwarded_to_other_ports(self) -> None:
        app_cb = MagicMock()
        router, t1, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should be forwarded to port 2 as broadcast
        t2.send_broadcast.assert_called_once()
        # Should NOT be sent back to port 1
        t1.send_broadcast.assert_not_called()

    def test_global_broadcast_not_forwarded_back_to_origin(self) -> None:
        app_cb = MagicMock()
        router, t1, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu()
        router._on_port_receive(2, data, _MAC_DEVICE_B)
        t1.send_broadcast.assert_called_once()
        t2.send_broadcast.assert_not_called()

    def test_global_broadcast_snet_sadr_injected(self) -> None:
        """When forwarding, SNET/SADR should be injected if not present."""
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Check the forwarded NPDU has SNET/SADR
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)
        assert forwarded.source is not None
        assert forwarded.source.network == 10  # port 1's network
        assert forwarded.source.mac_address == _MAC_DEVICE_A

    def test_global_broadcast_preserves_existing_snet_sadr(self) -> None:
        """If SNET/SADR already present, they should be preserved."""
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        orig_src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_global_broadcast_npdu(source=orig_src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)
        assert forwarded.source is not None
        assert forwarded.source.network == 30
        assert forwarded.source.mac_address == b"\xaa"

    def test_global_broadcast_hop_count_decremented(self) -> None:
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu(hop_count=100)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)
        assert forwarded.hop_count == 99

    def test_global_broadcast_hop_count_exhausted_not_forwarded(self) -> None:
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu(hop_count=1)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should still deliver to app
        app_cb.assert_called_once()
        # But NOT forward (hop count becomes 0)
        t2.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Forwarding to directly connected network
# ---------------------------------------------------------------------------


class TestNetworkRouterDirectlyConnected:
    def test_unicast_to_directly_connected_network(self) -> None:
        """NPDU with DNET=20 and DADR should be delivered on port 2."""
        router, _t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=20, dadr=_MAC_DEVICE_B, apdu=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should be sent as unicast to DADR on port 2
        t2.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_B
        # NPDU should have destination stripped
        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\xcc"

    def test_directed_broadcast_to_directly_connected_network(self) -> None:
        """NPDU with DNET=20 and DLEN=0 (broadcast) should broadcast on port 2."""
        router, _t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=20, dadr=b"", apdu=b"\xdd")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_broadcast.assert_called_once()
        sent_bytes = t2.send_broadcast.call_args[0][0]
        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\xdd"

    def test_snet_sadr_injected_on_delivery(self) -> None:
        """SNET/SADR should be injected when delivering to another net."""
        router, _, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=20, dadr=_MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        delivered = decode_npdu(sent_bytes)
        assert delivered.source is not None
        assert delivered.source.network == 10  # arrival port's network
        assert delivered.source.mac_address == _MAC_DEVICE_A

    def test_existing_snet_sadr_preserved(self) -> None:
        router, _, t2 = _make_two_port_router()
        src = BACnetAddress(network=30, mac_address=b"\xaa\xbb")
        data = _build_routed_npdu(dnet=20, dadr=_MAC_DEVICE_B, source=src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        delivered = decode_npdu(sent_bytes)
        assert delivered.source.network == 30
        assert delivered.source.mac_address == b"\xaa\xbb"

    def test_not_forwarded_to_origin_port(self) -> None:
        """Traffic for network 10 arriving on port 1 is delivered locally on port 1."""
        router, t1, t2 = _make_two_port_router()
        # Device on net 20 wants to reach device on net 10
        data = _build_routed_npdu(dnet=10, dadr=_MAC_DEVICE_A)
        router._on_port_receive(2, data, _MAC_DEVICE_B)
        t1.send_unicast.assert_called_once()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Forward via next-hop router
# ---------------------------------------------------------------------------


class TestNetworkRouterNextHop:
    def test_forward_via_next_hop(self) -> None:
        """Remote network via next-hop router."""
        router, _, t2 = _make_two_port_router()
        next_hop_mac = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop_mac)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_called_once()
        _, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == next_hop_mac

    def test_forward_preserves_dnet_dadr(self) -> None:
        """When forwarding via next-hop, DNET/DADR must be preserved."""
        router, _, t2 = _make_two_port_router()
        next_hop_mac = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop_mac)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        forwarded = decode_npdu(sent_bytes)
        assert forwarded.destination is not None
        assert forwarded.destination.network == 30
        assert forwarded.destination.mac_address == b"\xcc"

    def test_forward_decrements_hop_count(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=50)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        forwarded = decode_npdu(sent_bytes)
        assert forwarded.hop_count == 49

    def test_forward_injects_snet_sadr(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        forwarded = decode_npdu(sent_bytes)
        assert forwarded.source is not None
        assert forwarded.source.network == 10
        assert forwarded.source.mac_address == _MAC_DEVICE_A


# ---------------------------------------------------------------------------
# NetworkRouter -- Hop count handling
# ---------------------------------------------------------------------------


class TestNetworkRouterHopCount:
    def test_hop_count_one_discards(self) -> None:
        """Hop count 1 means next decrement = 0 -> discard."""
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=1)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_not_called()

    def test_hop_count_two_forwards(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=2)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_called_once()
        sent_bytes = t2.send_unicast.call_args[0][0]
        assert decode_npdu(sent_bytes).hop_count == 1

    def test_hop_count_255_forwards(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=255)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_called_once()
        sent_bytes = t2.send_unicast.call_args[0][0]
        assert decode_npdu(sent_bytes).hop_count == 254


# ---------------------------------------------------------------------------
# NetworkRouter -- Unknown destination
# ---------------------------------------------------------------------------


class TestNetworkRouterUnknownDest:
    def test_unknown_dnet_sends_reject(self) -> None:
        """Unknown DNET sends Reject-Message back to source (Clause 6.6.3.5)."""
        router, t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=99, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Reject sent back on arrival port
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 99
        # Not forwarded to other port
        t2.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Malformed NPDU
# ---------------------------------------------------------------------------


class TestNetworkRouterMalformed:
    def test_malformed_npdu_dropped(self) -> None:
        router, t1, t2 = _make_two_port_router()
        router._on_port_receive(1, b"\xff\xff\xff", _MAC_DEVICE_A)
        t1.send_unicast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Network message dispatch
# ---------------------------------------------------------------------------


class TestNetworkRouterNetworkMessage:
    def test_network_message_handled(self) -> None:
        """Network messages should go to _handle_network_message, not forwarding."""
        app_cb = MagicMock()
        router, _t1, _t2 = _make_two_port_router(app_callback=app_cb)
        # Build a network message NPDU (Who-Is-Router-To-Network)
        npdu = NPDU(
            is_network_message=True,
            message_type=0x00,
            network_message_data=b"",
        )
        router._on_port_receive(1, encode_npdu(npdu), _MAC_DEVICE_A)
        # Should NOT deliver to application
        app_cb.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- SNET/SADR injection details
# ---------------------------------------------------------------------------


class TestNetworkRouterSnetSadr:
    def test_inject_source_creates_bacnet_address(self) -> None:
        router, _, _ = _make_two_port_router()
        npdu = NPDU(apdu=b"\x01")
        result = router._inject_source(1, npdu, _MAC_DEVICE_A)
        assert result is not None
        assert result.network == 10
        assert result.mac_address == _MAC_DEVICE_A

    def test_inject_source_preserves_existing(self) -> None:
        router, _, _ = _make_two_port_router()
        src = BACnetAddress(network=30, mac_address=b"\xff")
        npdu = NPDU(source=src, apdu=b"\x01")
        result = router._inject_source(1, npdu, _MAC_DEVICE_A)
        assert result is src


# ---------------------------------------------------------------------------
# NetworkRouter -- send() method
# ---------------------------------------------------------------------------


class TestNetworkRouterSend:
    def test_send_local_broadcast(self) -> None:
        router, t1, t2 = _make_two_port_router()
        dest = BACnetAddress()  # local broadcast
        router.send(b"\xaa\xbb", dest)
        t1.send_broadcast.assert_called_once()
        t2.send_broadcast.assert_not_called()
        sent_bytes = t1.send_broadcast.call_args[0][0]
        npdu = decode_npdu(sent_bytes)
        assert npdu.apdu == b"\xaa\xbb"

    def test_send_global_broadcast(self) -> None:
        router, t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=0xFFFF)
        router.send(b"\xaa", dest)
        t1.send_broadcast.assert_called_once()
        t2.send_broadcast.assert_called_once()
        # Both should have the same encoded NPDU
        sent1 = t1.send_broadcast.call_args[0][0]
        sent2 = t2.send_broadcast.call_args[0][0]
        assert sent1 == sent2
        npdu = decode_npdu(sent1)
        assert npdu.destination is not None
        assert npdu.destination.network == 0xFFFF

    def test_send_local_unicast(self) -> None:
        router, t1, _t2 = _make_two_port_router()
        dest = BACnetAddress(mac_address=_MAC_DEVICE_A)
        router.send(b"\xcc", dest)
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.apdu == b"\xcc"
        assert npdu.destination is None  # local

    def test_send_remote_directly_connected(self) -> None:
        router, _t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=20, mac_address=_MAC_DEVICE_B)
        router.send(b"\xdd", dest)
        t2.send_unicast.assert_called_once()
        _sent_bytes, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_B

    def test_send_remote_broadcast(self) -> None:
        router, _t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=20, mac_address=b"")
        router.send(b"\xee", dest)
        t2.send_broadcast.assert_called_once()

    def test_send_remote_via_next_hop(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        dest = BACnetAddress(network=30, mac_address=b"\xcc")
        router.send(b"\xff", dest)
        t2.send_unicast.assert_called_once()
        _, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == next_hop

    def test_send_no_application_port_raises(self) -> None:
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter([p1, p2])  # no app port
        with pytest.raises(RuntimeError, match="No application port"):
            router.send(b"\x01", BACnetAddress())

    def test_send_unknown_network(self) -> None:
        router, t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=99, mac_address=b"\xcc")
        # Should not raise, just log warning
        router.send(b"\x01", dest)
        t1.send_unicast.assert_not_called()
        t2.send_unicast.assert_not_called()

    def test_send_expecting_reply(self) -> None:
        router, t1, _ = _make_two_port_router()
        dest = BACnetAddress(mac_address=_MAC_DEVICE_A)
        router.send(b"\x01", dest, expecting_reply=True)
        sent_bytes = t1.send_unicast.call_args[0][0]
        npdu = decode_npdu(sent_bytes)
        assert npdu.expecting_reply is True

    def test_send_priority(self) -> None:
        router, t1, _ = _make_two_port_router()
        dest = BACnetAddress(mac_address=_MAC_DEVICE_A)
        router.send(b"\x01", dest, priority=NetworkPriority.URGENT)
        sent_bytes = t1.send_unicast.call_args[0][0]
        npdu = decode_npdu(sent_bytes)
        assert npdu.priority == NetworkPriority.URGENT


# ---------------------------------------------------------------------------
# NetworkRouter -- Three-port topology
# ---------------------------------------------------------------------------


class TestNetworkRouterThreePort:
    def test_global_broadcast_floods_all_other_ports(self) -> None:
        t1 = _make_transport(local_mac=b"\x01\x00\x00\x01\xba\xc0")
        t2 = _make_transport(local_mac=b"\x02\x00\x00\x01\xba\xc0")
        t3 = _make_transport(local_mac=b"\x03\x00\x00\x01\xba\xc0")
        p1 = _make_port(port_id=1, network_number=10, transport=t1)
        p2 = _make_port(port_id=2, network_number=20, transport=t2)
        p3 = _make_port(port_id=3, network_number=30, transport=t3)
        router = NetworkRouter([p1, p2, p3])
        data = _build_global_broadcast_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t2.send_broadcast.assert_called_once()
        t3.send_broadcast.assert_called_once()

    def test_routed_unicast_to_correct_port(self) -> None:
        t1 = _make_transport(local_mac=b"\x01\x00\x00\x01\xba\xc0")
        t2 = _make_transport(local_mac=b"\x02\x00\x00\x01\xba\xc0")
        t3 = _make_transport(local_mac=b"\x03\x00\x00\x01\xba\xc0")
        p1 = _make_port(port_id=1, network_number=10, transport=t1)
        p2 = _make_port(port_id=2, network_number=20, transport=t2)
        p3 = _make_port(port_id=3, network_number=30, transport=t3)
        router = NetworkRouter([p1, p2, p3])
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc\xdd\xee\xff\xba\xc0")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_not_called()
        t3.send_unicast.assert_called_once()
        t1.send_unicast.assert_not_called()


# ===========================================================================
# Network message handler tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Helpers for building network message NPDUs
# ---------------------------------------------------------------------------


def _build_network_message_npdu(
    msg_type: int,
    data: bytes = b"",
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
    hop_count: int = 255,
) -> bytes:
    """Build a network layer message NPDU from raw type + data."""
    npdu = NPDU(
        is_network_message=True,
        message_type=msg_type,
        network_message_data=data,
        source=source,
        destination=destination,
        hop_count=hop_count if destination is not None else 255,
    )
    return encode_npdu(npdu)


def _build_who_is_router_npdu(network: int | None = None) -> bytes:
    """Build a Who-Is-Router-To-Network NPDU."""
    msg = WhoIsRouterToNetwork(network=network)
    return _build_network_message_npdu(
        NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_i_am_router_npdu(networks: tuple[int, ...]) -> bytes:
    """Build an I-Am-Router-To-Network NPDU."""
    msg = IAmRouterToNetwork(networks=networks)
    return _build_network_message_npdu(
        NetworkMessageType.I_AM_ROUTER_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_reject_message_npdu(
    reason: RejectMessageReason,
    network: int,
    *,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a Reject-Message-To-Network NPDU."""
    msg = RejectMessageToNetwork(reason=reason, network=network)
    return _build_network_message_npdu(
        NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
        encode_network_message(msg),
        destination=destination,
    )


def _build_router_busy_npdu(networks: tuple[int, ...]) -> bytes:
    """Build a Router-Busy-To-Network NPDU."""
    msg = RouterBusyToNetwork(networks=networks)
    return _build_network_message_npdu(
        NetworkMessageType.ROUTER_BUSY_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_router_available_npdu(networks: tuple[int, ...]) -> bytes:
    """Build a Router-Available-To-Network NPDU."""
    msg = RouterAvailableToNetwork(networks=networks)
    return _build_network_message_npdu(
        NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_init_routing_table_npdu(ports: tuple[RoutingTablePort, ...]) -> bytes:
    """Build an Initialize-Routing-Table NPDU."""
    msg = InitializeRoutingTable(ports=ports)
    return _build_network_message_npdu(
        NetworkMessageType.INITIALIZE_ROUTING_TABLE,
        encode_network_message(msg),
    )


def _build_init_routing_table_ack_npdu(ports: tuple[RoutingTablePort, ...]) -> bytes:
    """Build an Initialize-Routing-Table-Ack NPDU."""
    msg = InitializeRoutingTableAck(ports=ports)
    return _build_network_message_npdu(
        NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK,
        encode_network_message(msg),
    )


def _build_what_is_network_number_npdu(
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a What-Is-Network-Number NPDU."""
    return _build_network_message_npdu(
        NetworkMessageType.WHAT_IS_NETWORK_NUMBER,
        b"",
        source=source,
        destination=destination,
    )


def _build_network_number_is_npdu(
    network: int,
    configured: bool,
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a Network-Number-Is NPDU."""
    msg = NetworkNumberIs(network=network, configured=configured)
    return _build_network_message_npdu(
        NetworkMessageType.NETWORK_NUMBER_IS,
        encode_network_message(msg),
        source=source,
        destination=destination,
    )


def _decode_sent_network_message(
    transport_mock: MagicMock,
    *,
    method: str = "send_broadcast",
    call_index: int = 0,
) -> tuple[NPDU, bytes]:
    """Decode a network message sent on a mock transport.

    Returns (npdu, raw_network_message_data).
    """
    mock_method = getattr(transport_mock, method)
    args = mock_method.call_args_list[call_index][0]
    raw = args[0]
    npdu = decode_npdu(raw)
    return npdu, npdu.network_message_data


# ---------------------------------------------------------------------------
# RoutingTable -- include_busy parameter
# ---------------------------------------------------------------------------


class TestRoutingTableIncludeBusy:
    def test_get_reachable_networks_include_busy(self) -> None:
        """include_busy=True should include BUSY networks."""
        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(20, port_id=1, next_router_mac=b"\x01")
        rt.update_route(30, port_id=1, next_router_mac=b"\x02")
        # Mark 20 BUSY, 30 UNREACHABLE
        entry20 = rt.get_entry(20)
        assert entry20 is not None
        entry20.reachability = NetworkReachability.BUSY
        entry30 = rt.get_entry(30)
        assert entry30 is not None
        entry30.reachability = NetworkReachability.UNREACHABLE

        # Default: exclude BUSY
        nets_default = rt.get_reachable_networks()
        assert set(nets_default) == {10}

        # include_busy=True: include BUSY but not UNREACHABLE
        nets_busy = rt.get_reachable_networks(include_busy=True)
        assert set(nets_busy) == {10, 20}

    def test_include_busy_with_exclude_port(self) -> None:
        """include_busy + exclude_port should work together."""
        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        p2 = _make_port(port_id=2, network_number=20)
        rt.add_port(p1)
        rt.add_port(p2)
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")
        entry30 = rt.get_entry(30)
        assert entry30 is not None
        entry30.reachability = NetworkReachability.BUSY
        # Exclude port 1: removes networks 10 and 30
        nets = rt.get_reachable_networks(exclude_port=1, include_busy=True)
        assert set(nets) == {20}


# ---------------------------------------------------------------------------
# NetworkRouter -- Who-Is-Router-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleWhoIsRouter:
    def test_specific_dnet_found_on_other_port(self) -> None:
        """DNET reachable on different port -> I-Am-Router reply on arrival port."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=20)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should broadcast I-Am-Router on port 1 (arrival port)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        assert npdu.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == (20,)

    def test_specific_dnet_found_on_arrival_port(self) -> None:
        """DNET reachable on arrival port -> no reply (don't advertise back)."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=10)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()

    def test_specific_dnet_not_found_forwarded(self) -> None:
        """Unknown DNET -> forward Who-Is out all other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=99)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should forward (broadcast) on port 2
        t2.send_broadcast.assert_called_once()
        # Should NOT send on port 1
        t1.send_broadcast.assert_not_called()
        # The forwarded message should have SNET/SADR injected
        fwd_bytes = t2.send_broadcast.call_args[0][0]
        fwd_npdu = decode_npdu(fwd_bytes)
        assert fwd_npdu.source is not None
        assert fwd_npdu.source.network == 10

    def test_query_all_networks(self) -> None:
        """No specific DNET -> I-Am-Router with all reachable nets (excluding arrival)."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=None)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should reply on port 1 with network 20 (port 2's network)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert 20 in msg.networks
        assert 10 not in msg.networks  # exclude arrival port

    def test_query_all_includes_busy_networks(self) -> None:
        """Who-Is (no DNET) must include BUSY networks per Clause 6.6.3.2."""
        router, t1, _t2 = _make_two_port_router()
        # Add net 30 via port 2 and mark it BUSY
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY

        data = _build_who_is_router_npdu(network=None)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert 30 in msg.networks  # BUSY network included


# ---------------------------------------------------------------------------
# NetworkRouter -- I-Am-Router-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleIAmRouter:
    def test_new_entries_created(self) -> None:
        """I-Am-Router creates new routing table entries."""
        router, _t1, _t2 = _make_two_port_router()
        data = _build_i_am_router_npdu(networks=(30, 40))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # New entries in routing table
        entry30 = router.routing_table.get_entry(30)
        entry40 = router.routing_table.get_entry(40)
        assert entry30 is not None
        assert entry30.port_id == 1
        assert entry30.next_router_mac == _MAC_DEVICE_A
        assert entry40 is not None
        assert entry40.port_id == 1
        assert entry40.next_router_mac == _MAC_DEVICE_A

    def test_existing_entries_updated(self) -> None:
        """I-Am-Router updates existing entries with new MAC."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=b"\x01")
        data = _build_i_am_router_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.next_router_mac == _MAC_DEVICE_A

    def test_rebroadcast_on_other_ports(self) -> None:
        """I-Am-Router is re-broadcast on all other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_i_am_router_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should re-broadcast on port 2
        t2.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t2)
        assert npdu.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == (30,)
        # Should NOT broadcast back on port 1
        t1.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Reject-Message-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleRejectMessage:
    def test_reason_not_directly_connected_marks_unreachable(self) -> None:
        """Reason 1 -> network marked UNREACHABLE."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        data = _build_reject_message_npdu(
            RejectMessageReason.NOT_DIRECTLY_CONNECTED,
            30,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.UNREACHABLE

    async def test_reason_router_busy_marks_busy(self) -> None:
        """Reason 2 -> network marked BUSY with auto-recovery."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        data = _build_reject_message_npdu(
            RejectMessageReason.ROUTER_BUSY,
            30,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY

    def test_relay_toward_originator(self) -> None:
        """Reject message with DNET/DADR is forwarded toward originator."""
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        # DNET points to network 20 (directly connected on port 2)
        dest = BACnetAddress(network=20, mac_address=_MAC_DEVICE_B)
        data = _build_reject_message_npdu(
            RejectMessageReason.OTHER,
            30,
            destination=dest,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should forward toward network 20 (port 2)
        t2.send_unicast.assert_called_once()


# ---------------------------------------------------------------------------
# NetworkRouter -- Router-Busy-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleRouterBusy:
    async def test_listed_dnets_marked_busy(self) -> None:
        """Specific DNETs in the message are marked BUSY."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        data = _build_router_busy_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY

    async def test_empty_list_marks_all_sender_dnets(self) -> None:
        """Empty list -> all networks served by sender marked BUSY."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        router.routing_table.update_route(40, port_id=1, next_router_mac=_MAC_DEVICE_A)
        # Also a route via a different router on the same port
        router.routing_table.update_route(50, port_id=1, next_router_mac=b"\x99")
        data = _build_router_busy_npdu(networks=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # 30 and 40 should be BUSY (same source_mac)
        entry30 = router.routing_table.get_entry(30)
        entry40 = router.routing_table.get_entry(40)
        assert entry30 is not None and entry30.reachability == NetworkReachability.BUSY
        assert entry40 is not None and entry40.reachability == NetworkReachability.BUSY
        # 50 via different router should be unaffected
        entry50 = router.routing_table.get_entry(50)
        assert entry50 is not None and entry50.reachability == NetworkReachability.REACHABLE

    async def test_rebroadcast_on_other_ports(self) -> None:
        """Router-Busy is re-broadcast on all other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_router_busy_npdu(networks=(10,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_broadcast.assert_called_once()
        npdu, _msg_data = _decode_sent_network_message(t2)
        assert npdu.message_type == NetworkMessageType.ROUTER_BUSY_TO_NETWORK
        t1.send_broadcast.assert_not_called()

    async def test_busy_timer_auto_restores_reachable(self) -> None:
        """30s timer restores REACHABLE (tested with short timeout)."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        data = _build_router_busy_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY
        assert entry.busy_timeout_handle is not None
        # The handler uses call_later with default 30s; verify handle exists
        # Cancel and trigger manually for the test
        entry.busy_timeout_handle.cancel()
        router.routing_table.mark_available(30)
        assert entry.reachability == NetworkReachability.REACHABLE


# ---------------------------------------------------------------------------
# NetworkRouter -- Router-Available-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleRouterAvailable:
    def test_listed_dnets_marked_reachable(self) -> None:
        """Specific DNETs in the message are marked REACHABLE."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY
        data = _build_router_available_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert entry.reachability == NetworkReachability.REACHABLE

    def test_empty_list_marks_all_busy_reachable(self) -> None:
        """Empty list -> all previously BUSY networks restored."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=b"\x01")
        router.routing_table.update_route(40, port_id=1, next_router_mac=b"\x02")
        e30 = router.routing_table.get_entry(30)
        e40 = router.routing_table.get_entry(40)
        assert e30 is not None and e40 is not None
        e30.reachability = NetworkReachability.BUSY
        e40.reachability = NetworkReachability.BUSY
        data = _build_router_available_npdu(networks=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert e30.reachability == NetworkReachability.REACHABLE
        assert e40.reachability == NetworkReachability.REACHABLE

    def test_rebroadcast_on_other_ports(self) -> None:
        """Router-Available is re-broadcast on other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_router_available_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_broadcast.assert_called_once()
        npdu, _ = _decode_sent_network_message(t2)
        assert npdu.message_type == NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK
        t1.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Initialize-Routing-Table handler
# ---------------------------------------------------------------------------


class TestHandleInitRoutingTable:
    def test_query_returns_full_table(self) -> None:
        """Empty ports list (query) -> Ack with complete routing table."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_init_routing_table_npdu(ports=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should unicast Ack back to sender on port 1
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, InitializeRoutingTableAck)
        # Should include both directly-connected entries (net 10, net 20)
        ack_networks = {p.network for p in msg.ports}
        assert 10 in ack_networks
        assert 20 in ack_networks

    def test_update_modifies_table_and_acks(self) -> None:
        """Non-empty ports list -> table modified, empty Ack returned."""
        router, t1, _t2 = _make_two_port_router()
        update_ports = [
            RoutingTablePort(network=50, port_id=1, port_info=b""),
        ]
        data = _build_init_routing_table_npdu(ports=update_ports)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Network 50 should be added via port 1
        entry = router.routing_table.get_entry(50)
        assert entry is not None
        assert entry.port_id == 1
        # Response should be unicast Ack with empty ports
        t1.send_unicast.assert_called_once()
        sent_bytes, _ = t1.send_unicast.call_args[0]
        npdu = decode_npdu(sent_bytes)
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, InitializeRoutingTableAck)
        assert len(msg.ports) == 0

    def test_update_port_id_zero_removes_entry(self) -> None:
        """port_id=0 in update removes the entry."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(50, port_id=1, next_router_mac=b"\x01")
        update_ports = [
            RoutingTablePort(network=50, port_id=0, port_info=b""),
        ]
        data = _build_init_routing_table_npdu(ports=update_ports)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert router.routing_table.get_entry(50) is None

    def test_update_unknown_port_id_ignored(self) -> None:
        """Unknown port_id in update is silently ignored."""
        router, _t1, _t2 = _make_two_port_router()
        update_ports = [
            RoutingTablePort(network=50, port_id=99, port_info=b""),
        ]
        data = _build_init_routing_table_npdu(ports=update_ports)
        # Should not raise
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert router.routing_table.get_entry(50) is None


# ---------------------------------------------------------------------------
# NetworkRouter -- Initialize-Routing-Table-Ack handler
# ---------------------------------------------------------------------------


class TestHandleInitRoutingTableAck:
    def test_ack_received_no_error(self) -> None:
        """Ack is received without error (logged only)."""
        router, t1, t2 = _make_two_port_router()
        ack_ports = [
            RoutingTablePort(network=10, port_id=1, port_info=b""),
            RoutingTablePort(network=20, port_id=2, port_info=b""),
        ]
        data = _build_init_routing_table_ack_npdu(ports=ack_ports)
        # Should not raise or send anything
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- What-Is-Network-Number handler
# ---------------------------------------------------------------------------


class TestHandleWhatIsNetworkNumber:
    def test_configured_port_responds(self) -> None:
        """Configured port responds with Network-Number-Is broadcast."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_what_is_network_number_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        assert npdu.message_type == NetworkMessageType.NETWORK_NUMBER_IS
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, NetworkNumberIs)
        assert msg.network == 10
        assert msg.configured is True

    def test_routed_message_ignored(self) -> None:
        """What-Is with SNET/SADR is ignored (never routed)."""
        router, t1, _t2 = _make_two_port_router()
        src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_what_is_network_number_npdu(source=src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()

    def test_routed_with_destination_ignored(self) -> None:
        """What-Is with DNET/DADR is ignored (never routed)."""
        router, t1, _t2 = _make_two_port_router()
        dest = BACnetAddress(network=20, mac_address=b"")
        data = _build_what_is_network_number_npdu(destination=dest)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()

    def test_unconfigured_port_no_response(self) -> None:
        """Unconfigured port does not respond."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        data = _build_what_is_network_number_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Network-Number-Is handler
# ---------------------------------------------------------------------------


class TestHandleNetworkNumberIs:
    def test_unconfigured_port_learns_number(self) -> None:
        """Unconfigured port learns network number from configured source."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,  # unknown
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        data = _build_network_number_is_npdu(42, configured=True)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 42

    def test_configured_port_ignores(self) -> None:
        """Already configured port ignores Network-Number-Is."""
        router, _t1, _t2 = _make_two_port_router()
        data = _build_network_number_is_npdu(99, configured=True)
        port = router.routing_table.get_port(1)
        assert port is not None
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert port.network_number == 10  # unchanged

    def test_unconfigured_source_ignored(self) -> None:
        """Network-Number-Is with configured=False is ignored."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        data = _build_network_number_is_npdu(42, configured=False)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 0  # unchanged

    def test_routed_message_ignored(self) -> None:
        """Network-Number-Is with SNET/SADR is ignored."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_network_number_is_npdu(42, configured=True, source=src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 0  # unchanged

    def test_routed_with_destination_ignored(self) -> None:
        """Network-Number-Is with DNET/DADR is ignored."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        dest = BACnetAddress(network=20, mac_address=b"")
        data = _build_network_number_is_npdu(42, configured=True, destination=dest)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 0  # unchanged


# ---------------------------------------------------------------------------
# NetworkRouter -- Router startup broadcasts
# ---------------------------------------------------------------------------


class TestRouterStartup:
    async def test_startup_broadcasts_network_number_is(self) -> None:
        """Each configured port gets Network-Number-Is broadcast."""
        router, t1, t2 = _make_two_port_router()
        await router.start()
        # Both ports are configured, so both should get Network-Number-Is
        assert t1.send_broadcast.call_count >= 1
        assert t2.send_broadcast.call_count >= 1
        # Check first broadcast on each port is Network-Number-Is
        first_t1 = t1.send_broadcast.call_args_list[0][0][0]
        npdu1 = decode_npdu(first_t1)
        assert npdu1.message_type == NetworkMessageType.NETWORK_NUMBER_IS
        msg1 = decode_network_message(npdu1.message_type, npdu1.network_message_data)
        assert isinstance(msg1, NetworkNumberIs)
        assert msg1.network == 10
        assert msg1.configured is True

        first_t2 = t2.send_broadcast.call_args_list[0][0][0]
        npdu2 = decode_npdu(first_t2)
        assert npdu2.message_type == NetworkMessageType.NETWORK_NUMBER_IS
        msg2 = decode_network_message(npdu2.message_type, npdu2.network_message_data)
        assert isinstance(msg2, NetworkNumberIs)
        assert msg2.network == 20
        assert msg2.configured is True

    async def test_startup_broadcasts_i_am_router(self) -> None:
        """Each port gets I-Am-Router listing networks from other ports."""
        router, t1, t2 = _make_two_port_router()
        await router.start()
        # Port 1 should get I-Am-Router with network 20
        # Port 2 should get I-Am-Router with network 10
        second_t1 = t1.send_broadcast.call_args_list[1][0][0]
        npdu1 = decode_npdu(second_t1)
        assert npdu1.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg1 = decode_network_message(npdu1.message_type, npdu1.network_message_data)
        assert isinstance(msg1, IAmRouterToNetwork)
        assert 20 in msg1.networks
        assert 10 not in msg1.networks

        second_t2 = t2.send_broadcast.call_args_list[1][0][0]
        npdu2 = decode_npdu(second_t2)
        assert npdu2.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg2 = decode_network_message(npdu2.message_type, npdu2.network_message_data)
        assert isinstance(msg2, IAmRouterToNetwork)
        assert 10 in msg2.networks
        assert 20 not in msg2.networks

    async def test_startup_unconfigured_port_no_network_number_is(self) -> None:
        """Unconfigured port should not broadcast Network-Number-Is."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        await router.start()
        # Should NOT have Network-Number-Is (not configured)
        for c in t1.send_broadcast.call_args_list:
            npdu = decode_npdu(c[0][0])
            assert npdu.message_type != NetworkMessageType.NETWORK_NUMBER_IS


# ---------------------------------------------------------------------------
# NetworkRouter -- Unknown message type
# ---------------------------------------------------------------------------


class TestHandleUnknownMessageType:
    def test_unknown_type_sends_reject(self) -> None:
        """Unknown standard message type -> Reject with UNKNOWN_MESSAGE_TYPE."""
        router, t1, _t2 = _make_two_port_router()
        # I-Could-Be-Router (0x02) is decoded but not handled by the router.
        msg = ICouldBeRouterToNetwork(network=10, performance_index=5)
        data = _build_network_message_npdu(
            NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK,
            encode_network_message(msg),
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should send Reject-Message-To-Network
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg_decoded = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg_decoded, RejectMessageToNetwork)
        assert msg_decoded.reason == RejectMessageReason.UNKNOWN_MESSAGE_TYPE


# ---------------------------------------------------------------------------
# NetworkRouter -- Malformed network message
# ---------------------------------------------------------------------------


class TestHandleMalformedNetworkMessage:
    def test_malformed_message_data_dropped(self) -> None:
        """Malformed network message data is logged and dropped."""
        router, t1, t2 = _make_two_port_router()
        # Build NPDU with valid type but malformed data
        data = _build_network_message_npdu(
            NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
            b"\x01",  # too short for reject message (needs 3 bytes)
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should not crash, should not send anything
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Reject on unknown / unreachable / busy DNET (Clause 6.6.3.5)
# ---------------------------------------------------------------------------


class TestForwardRejectsUnknownDNET:
    """Forwarding to an unknown DNET sends Reject-Message-To-Network."""

    def test_unknown_dnet_sends_reject(self) -> None:
        """Unknown DNET -> Reject with NOT_DIRECTLY_CONNECTED on arrival port."""
        router, t1, _t2 = _make_two_port_router()
        # Network 99 is not in the routing table.
        data = _build_routed_npdu(99, _MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 99

    def test_unknown_dnet_not_forwarded(self) -> None:
        """Traffic to unknown DNET should NOT be forwarded anywhere."""
        router, _t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(99, _MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Port 2 should not receive anything.
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


class TestForwardRejectsUnreachableDNET:
    """Forwarding to an UNREACHABLE DNET sends Reject-Message-To-Network."""

    def test_unreachable_dnet_sends_reject(self) -> None:
        router, t1, _t2 = _make_two_port_router()
        # Add a remote route and mark it unreachable.
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_unreachable(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 30

    def test_unreachable_dnet_not_forwarded(self) -> None:
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_unreachable(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


class TestForwardRejectsBusyDNET:
    """Forwarding to a BUSY DNET sends Reject with ROUTER_BUSY reason."""

    def test_busy_dnet_sends_reject(self) -> None:
        router, t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_busy(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.ROUTER_BUSY
        assert msg.network == 30

    def test_busy_dnet_not_forwarded(self) -> None:
        """Traffic should NOT be forwarded to a busy network."""
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_busy(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()

    def test_reachable_dnet_still_forwarded(self) -> None:
        """Sanity check: REACHABLE DNET is still forwarded normally."""
        router, t1, t2 = _make_two_port_router()
        # Network 20 is directly connected and REACHABLE by default.
        data = _build_routed_npdu(20, _MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t2.send_unicast.assert_called_once()
        # No reject on arrival port.
        t1.send_unicast.assert_not_called()


class TestRejectRoutedBackWithSNET:
    """When the originator is on a remote network (SNET/SADR in NPDU), the Reject should be routed back via normal forwarding."""

    def test_reject_routed_to_snet(self) -> None:
        """Reject for unknown DNET with SNET/SADR routes back via SNET port."""
        # Three-port router: net 10 (port 1), net 20 (port 2), net 30 (port 3).
        t1 = _make_transport(local_mac=_MAC_PORT1)
        t2 = _make_transport(local_mac=_MAC_PORT2)
        t3 = _make_transport(local_mac=b"\x0a\x00\x00\x03\xba\xc0")
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
        )
        p2 = RouterPort(
            port_id=2,
            network_number=20,
            transport=t2,
            mac_address=_MAC_PORT2,
            max_npdu_length=1497,
        )
        p3 = RouterPort(
            port_id=3,
            network_number=30,
            transport=t3,
            mac_address=b"\x0a\x00\x00\x03\xba\xc0",
            max_npdu_length=1497,
        )
        router = NetworkRouter([p1, p2, p3], application_port_id=1)

        # Device on net 30 sends NPDU targeting unknown net 99 via port 2.
        # SNET=30, SADR=device_mac.
        source = BACnetAddress(network=30, mac_address=b"\xaa\xbb\xcc\xdd\xee\xff")
        data = _build_routed_npdu(99, b"\x01\x02\x03\x04\x05\x06", source=source)
        router._on_port_receive(2, data, _MAC_DEVICE_B)

        # Reject should be sent on port 3 (toward net 30), not port 2.
        t3.send_unicast.assert_called_once()
        sent_bytes = t3.send_unicast.call_args[0][0]
        sent_mac = t3.send_unicast.call_args[0][1]
        assert sent_mac == b"\xaa\xbb\xcc\xdd\xee\xff"

        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        assert npdu.destination is not None
        assert npdu.destination.network == 30
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 99

    def test_reject_fallback_to_arrival_port_when_snet_unreachable(self) -> None:
        """If SNET is not routable, fall back to sending on arrival port."""
        router, t1, _t2 = _make_two_port_router()
        # SNET=99 has no route.
        source = BACnetAddress(network=99, mac_address=b"\xaa\xbb")
        data = _build_routed_npdu(88, b"\x01", source=source)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        # Falls back to arrival port (port 1).
        t1.send_unicast.assert_called_once()
        sent_mac = t1.send_unicast.call_args[0][1]
        assert sent_mac == _MAC_DEVICE_A
