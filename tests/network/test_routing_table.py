"""Tests for RoutingTable and RoutingTableEntry data structures."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from bac_py.network.router import RoutingTable, RoutingTableEntry
from bac_py.types.enums import NetworkReachability
from tests.network.conftest import _make_port

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
