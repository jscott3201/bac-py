#!/usr/bin/env python3
"""Local router benchmark — router, server, and stress clients in one process.

Runs a complete BACnet router stress test without Docker by creating an
in-process router bridging two localhost networks, a stress server on
network 2, and client pools on network 1.  Client router caches are
pre-populated so broadcast discovery (which doesn't work on loopback)
is not required.

Usage::

    # Default: 1 pool (2R + 1W + 1RPM + 1WPM) + 1 OL + 1 route-check, 5s warmup, 30s sustained
    uv run python scripts/bench_router.py

    # Custom: 2 pools, 60s sustained
    uv run python scripts/bench_router.py --pools 2 --sustain 60

    # Quick smoke test
    uv run python scripts/bench_router.py --sustain 5 --warmup 2

    # JSON output for CI/dashboards
    uv run python scripts/bench_router.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import statistics
import sys
import time
from typing import Any


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local router benchmark")
    p.add_argument("--pools", type=int, default=1, help="Client pool count (default: 1)")
    p.add_argument("--readers", type=int, default=2, help="Read workers per pool (default: 2)")
    p.add_argument("--writers", type=int, default=1, help="Write workers per pool (default: 1)")
    p.add_argument("--rpm", type=int, default=1, help="RPM workers per pool (default: 1)")
    p.add_argument("--wpm", type=int, default=1, help="WPM workers per pool (default: 1)")
    p.add_argument("--objlist", type=int, default=1, help="Object-list workers (default: 1)")
    p.add_argument("--warmup", type=int, default=5, help="Warmup seconds (default: 5)")
    p.add_argument("--sustain", type=int, default=30, help="Sustained test seconds (default: 30)")
    p.add_argument("--json", action="store_true", help="Output JSON report to stdout")
    p.add_argument("--profile", action="store_true", help="Enable pyinstrument profiling")
    p.add_argument("--profile-html", metavar="PATH", help="Save interactive HTML profile to file")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Object pools (inlined from docker/lib/bip_stress.py)
# ---------------------------------------------------------------------------

READABLE_OBJECTS = (
    [f"ai,{i}" for i in range(1, 11)]
    + [f"bi,{i}" for i in range(1, 6)]
    + [f"msi,{i}" for i in range(1, 4)]
)

WRITABLE_OBJECTS = [f"av,{i}" for i in range(1, 6)]

RPM_SPECS: list[dict[str, list[str]]] = [
    {"ai,1": ["present-value", "object-name", "units"], "ai,2": ["present-value", "units"]},
    {"ai,3": ["present-value", "status-flags"], "bi,1": ["present-value", "object-name"]},
    {"av,1": ["present-value", "units", "object-name"], "av,2": ["present-value"]},
    {
        "msi,1": ["present-value", "number-of-states"],
        "msi,2": ["present-value", "object-name"],
        "msi,3": ["present-value"],
    },
    {"ao,1": ["present-value", "units"], "ao,2": ["present-value", "object-name", "units"]},
]

WPM_SPECS: list[dict[str, dict[str, float]]] = [
    {"av,1": {"present-value": 71.0}, "av,2": {"present-value": 72.0}},
    {"av,3": {"present-value": 73.0}, "av,4": {"present-value": 74.0}},
    {"av,1": {"present-value": 68.0}, "av,5": {"present-value": 75.0}},
]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class Stats:
    """Asyncio-safe stats collector (single-threaded event loop)."""

    __slots__ = (
        "errors",
        "objlist_latencies",
        "read_latencies",
        "route_check_latencies",
        "route_discoveries",
        "rpm_latencies",
        "wpm_latencies",
        "write_latencies",
    )

    def __init__(self) -> None:
        self.read_latencies: list[float] = []
        self.write_latencies: list[float] = []
        self.rpm_latencies: list[float] = []
        self.wpm_latencies: list[float] = []
        self.objlist_latencies: list[float] = []
        self.route_check_latencies: list[float] = []
        self.route_discoveries: int = 0
        self.errors: int = 0

    @property
    def total_ok(self) -> int:
        return (
            len(self.read_latencies)
            + len(self.write_latencies)
            + len(self.rpm_latencies)
            + len(self.wpm_latencies)
            + len(self.objlist_latencies)
            + len(self.route_check_latencies)
        )

    def snapshot(self) -> tuple[int, int, int, int, int, int, int, int]:
        """Return (reads, writes, rpms, wpms, objlists, route_checks, route_disc, errors)."""
        return (
            len(self.read_latencies),
            len(self.write_latencies),
            len(self.rpm_latencies),
            len(self.wpm_latencies),
            len(self.objlist_latencies),
            len(self.route_check_latencies),
            self.route_discoveries,
            self.errors,
        )

    def combined_latencies(self) -> list[float]:
        """Return all latencies combined."""
        return (
            self.read_latencies
            + self.write_latencies
            + self.rpm_latencies
            + self.wpm_latencies
            + self.objlist_latencies
            + self.route_check_latencies
        )


# ---------------------------------------------------------------------------
# Workers (inlined from docker/lib/bip_stress.py + router_stress.py)
# ---------------------------------------------------------------------------


async def _read_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    while not stop.is_set():
        await asyncio.sleep(0)
        obj = random.choice(READABLE_OBJECTS)
        t0 = time.monotonic()
        try:
            await client.read(server, obj, "present-value")
            stats.read_latencies.append((time.monotonic() - t0) * 1000.0)
        except Exception:
            stats.errors += 1
            await asyncio.sleep(error_backoff)


async def _write_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    toggle = False
    while not stop.is_set():
        await asyncio.sleep(0)
        obj = random.choice(WRITABLE_OBJECTS)
        toggle = not toggle
        value = 72.5 if toggle else 68.0
        t0 = time.monotonic()
        try:
            await client.write(server, obj, "present-value", value, priority=8)
            stats.write_latencies.append((time.monotonic() - t0) * 1000.0)
        except Exception:
            stats.errors += 1
            await asyncio.sleep(error_backoff)


async def _rpm_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    idx = 0
    while not stop.is_set():
        await asyncio.sleep(0)
        spec = RPM_SPECS[idx % len(RPM_SPECS)]
        idx += 1
        t0 = time.monotonic()
        try:
            await client.read_multiple(server, spec)
            stats.rpm_latencies.append((time.monotonic() - t0) * 1000.0)
        except Exception:
            stats.errors += 1
            await asyncio.sleep(error_backoff)


async def _wpm_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    idx = 0
    while not stop.is_set():
        await asyncio.sleep(0)
        spec = WPM_SPECS[idx % len(WPM_SPECS)]
        idx += 1
        t0 = time.monotonic()
        try:
            await client.write_multiple(server, spec)
            stats.wpm_latencies.append((time.monotonic() - t0) * 1000.0)
        except Exception:
            stats.errors += 1
            await asyncio.sleep(error_backoff)


async def _objlist_worker(
    client: Any, server: str, device_id: str, stats: Stats, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        await asyncio.sleep(0)
        t0 = time.monotonic()
        try:
            await client.read(server, device_id, "object-list")
            stats.objlist_latencies.append((time.monotonic() - t0) * 1000.0)
        except Exception:
            stats.errors += 1
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=2.0)


async def _route_check_worker(
    client: Any,
    remote_network: int,
    stats: Stats,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        t0 = time.monotonic()
        try:
            routers = await client.who_is_router_to_network(network=remote_network, timeout=5.0)
            if routers:
                stats.route_check_latencies.append((time.monotonic() - t0) * 1000.0)
                stats.route_discoveries += 1
        except Exception:
            stats.errors += 1

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=10.0)


# ---------------------------------------------------------------------------
# Latency helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_list: list[float], pct: float) -> float:
    if not sorted_list:
        return 0.0
    idx = min(int(len(sorted_list) * pct), len(sorted_list) - 1)
    return sorted_list[idx]


def _latency_summary(lats: list[float]) -> str:
    if not lats:
        return "n/a"
    s = sorted(lats)
    return (
        f"p50={_percentile(s, 0.50):.1f}ms  "
        f"p95={_percentile(s, 0.95):.1f}ms  "
        f"p99={_percentile(s, 0.99):.1f}ms  "
        f"mean={statistics.mean(lats):.1f}ms"
    )


def _latency_dict(lats: list[float]) -> dict[str, float]:
    if not lats:
        return {"mean": 0, "p50": 0, "p95": 0, "p99": 0}
    s = sorted(lats)
    return {
        "mean": round(statistics.mean(lats), 2),
        "p50": round(_percentile(s, 0.50), 2),
        "p95": round(_percentile(s, 0.95), 2),
        "p99": round(_percentile(s, 0.99), 2),
    }


# ---------------------------------------------------------------------------
# Server object creation
# ---------------------------------------------------------------------------


def _create_stress_objects(app: Any, device_name: str) -> None:
    """Create 40 stress-test objects (39 + device) on the application."""
    import bac_py
    from bac_py.app.server import DefaultServerHandlers
    from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
    from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject, BinaryValueObject
    from bac_py.objects.calendar import CalendarObject
    from bac_py.objects.device import DeviceObject
    from bac_py.objects.multistate import MultiStateInputObject, MultiStateValueObject
    from bac_py.objects.notification import NotificationClassObject
    from bac_py.objects.schedule import ScheduleObject
    from bac_py.types.enums import EngineeringUnits, PropertyIdentifier

    device = DeviceObject(
        app._config.instance_number,
        object_name=device_name,
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-bench",
        firmware_revision=bac_py.__version__,
        application_software_version=bac_py.__version__,
    )
    app.object_db.add(device)

    ai_units = [
        EngineeringUnits.DEGREES_FAHRENHEIT,
        EngineeringUnits.DEGREES_CELSIUS,
        EngineeringUnits.PERCENT_RELATIVE_HUMIDITY,
        EngineeringUnits.PASCALS,
        EngineeringUnits.LITERS_PER_SECOND,
        EngineeringUnits.WATTS,
        EngineeringUnits.KILOWATT_HOURS,
        EngineeringUnits.AMPERES,
        EngineeringUnits.VOLTS,
        EngineeringUnits.HERTZ,
    ]
    for i in range(1, 11):
        app.object_db.add(
            AnalogInputObject(
                i, object_name=f"AI-{i}", present_value=60.0 + i * 1.5, units=ai_units[i - 1]
            )
        )

    for i in range(1, 6):
        app.object_db.add(
            AnalogOutputObject(
                i,
                object_name=f"AO-{i}",
                present_value=50.0 + i,
                units=EngineeringUnits.DEGREES_FAHRENHEIT,
            )
        )

    for i in range(1, 6):
        app.object_db.add(
            AnalogValueObject(
                i,
                object_name=f"AV-{i}",
                present_value=70.0 + i,
                units=EngineeringUnits.DEGREES_FAHRENHEIT,
                commandable=True,
            )
        )

    for i in range(1, 6):
        app.object_db.add(BinaryInputObject(i, object_name=f"BI-{i}"))

    for i in range(1, 4):
        app.object_db.add(BinaryOutputObject(i, object_name=f"BO-{i}"))

    for i in range(1, 4):
        app.object_db.add(BinaryValueObject(i, object_name=f"BV-{i}", commandable=True))

    for i in range(1, 4):
        app.object_db.add(MultiStateInputObject(i, object_name=f"MSI-{i}", number_of_states=4))

    for i in range(1, 3):
        app.object_db.add(
            MultiStateValueObject(i, object_name=f"MSV-{i}", commandable=True, number_of_states=3)
        )

    app.object_db.add(ScheduleObject(1, object_name="Schedule-1"))
    app.object_db.add(CalendarObject(1, object_name="Calendar-1"))

    nc = NotificationClassObject(1, object_name="NC-1")
    nc._properties[PropertyIdentifier.PRIORITY] = [3, 3, 3]
    nc._properties[PropertyIdentifier.ACK_REQUIRED] = [True, False, False]
    app.object_db.add(nc)

    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()


# ---------------------------------------------------------------------------
# Router cache injection
# ---------------------------------------------------------------------------


def _inject_router_cache(client: Any, network: int, router_mac: bytes) -> None:
    """Pre-populate a client's network layer router cache.

    On localhost, broadcast-based router discovery doesn't work (macOS loopback).
    Instead, we inject the router MAC for the target network directly.
    """
    from bac_py.network.layer import RouterCacheEntry

    layer = client.app._network
    if layer is None:
        return
    layer._router_cache[network] = RouterCacheEntry(
        network=network,
        router_mac=router_mac,
        last_seen=time.monotonic(),
    )


# ---------------------------------------------------------------------------
# Worker spawning
# ---------------------------------------------------------------------------


def _spawn_workers(
    pools: list[Any],
    objlist_client: Any,
    route_check_client: Any,
    server: str,
    instance: int,
    remote_network: int,
    stats: Stats,
    stop: asyncio.Event,
    *,
    readers_per_pool: int,
    writers_per_pool: int,
    rpm_per_pool: int,
    wpm_per_pool: int,
    objlist_workers: int,
) -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = []
    device_id = f"device,{instance}"

    for client in pools:
        for _ in range(readers_per_pool):
            tasks.append(asyncio.create_task(_read_worker(client, server, stats, stop)))
        for _ in range(writers_per_pool):
            tasks.append(asyncio.create_task(_write_worker(client, server, stats, stop)))
        for _ in range(rpm_per_pool):
            tasks.append(asyncio.create_task(_rpm_worker(client, server, stats, stop)))
        for _ in range(wpm_per_pool):
            tasks.append(asyncio.create_task(_wpm_worker(client, server, stats, stop)))

    for _ in range(objlist_workers):
        tasks.append(
            asyncio.create_task(_objlist_worker(objlist_client, server, device_id, stats, stop))
        )

    tasks.append(
        asyncio.create_task(_route_check_worker(route_check_client, remote_network, stats, stop))
    )

    return tasks


async def _stop_phase(
    stop: asyncio.Event,
    workers: list[asyncio.Task[None]],
    *,
    timeout: float = 10.0,
) -> None:
    stop.set()
    _done, pending = await asyncio.wait(workers, timeout=timeout)
    for t in pending:
        t.cancel()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    from bac_py import Client
    from bac_py.app.application import (
        BACnetApplication,
        DeviceConfig,
        RouterConfig,
        RouterPortConfig,
    )

    log = sys.stderr.write

    net1 = 1
    net2 = 2
    router_instance = 500
    server_instance = 501

    # -- Start router bridging network 1 and network 2 --
    # The router forwards packets between nets but does NOT host the stress
    # server.  A separate BACnetApplication on network 2 acts as the server.
    # This avoids the BIPTransport self-echo filter which drops packets a
    # socket sends to itself (the old approach hosted the server on the
    # router's own application port, causing all forwarded traffic to be
    # silently dropped as self-echoes).
    router_config = RouterConfig(
        ports=[
            RouterPortConfig(port_id=1, network_number=net1, interface="127.0.0.1", port=0),
            RouterPortConfig(port_id=2, network_number=net2, interface="127.0.0.1", port=0),
        ],
        application_port_id=1,
    )
    router_app = BACnetApplication(
        DeviceConfig(
            instance_number=router_instance,
            name="Bench-Router",
            router_config=router_config,
        )
    )
    await router_app.start()

    port1_port = router_app._transports[0].local_address.port
    port2_port = router_app._transports[1].local_address.port
    router_port1_mac = router_app._transports[0].local_mac
    log(f"  Router started: net {net1} on :{port1_port}, net {net2} on :{port2_port}\n")

    # -- Start stress server as a separate application on network 2 --
    # The server has its own UDP port (distinct from router port 2) so the
    # self-echo filter does not interfere.  It automatically learns the
    # return route from the SNET/SADR of the first routed request.
    server_app = BACnetApplication(
        DeviceConfig(
            instance_number=server_instance,
            name=f"Bench-Server-{server_instance}",
            interface="127.0.0.1",
            port=0,
        )
    )
    await server_app.start()

    server_port = server_app._transport.local_address.port  # type: ignore[union-attr]
    server_mac = server_app._transport.local_mac  # type: ignore[union-attr]
    server_addr = f"{net2}:{server_mac.hex()}"

    _create_stress_objects(server_app, f"Bench-Server-{server_instance}")
    log(f"  Server on net {net2} at :{server_port}, {len(list(server_app.object_db))} objects\n")

    per_pool = args.readers + args.writers + args.rpm + args.wpm
    total_workers = args.pools * per_pool + args.objlist + 1  # +1 for route check

    if not args.json:
        log(
            f"\n{'=' * 70}\n"
            f"  Router Local Benchmark: {args.pools} pool(s) x "
            f"({args.readers}R + {args.writers}W + {args.rpm}RPM + {args.wpm}WPM) + "
            f"{args.objlist}OL + 1 route-check\n"
            f"  Total workers: {total_workers}  |  "
            f"Warmup: {args.warmup}s  |  Sustained: {args.sustain}s\n"
            f"  Route: net {net1} (:{port1_port}) -> net {net2} (:{port2_port})"
            f" -> server (:{server_port})\n"
            f"  Server: {server_addr}\n"
            f"{'=' * 70}\n"
        )

    try:
        async with contextlib.AsyncExitStack() as stack:
            pools: list[Any] = []
            for i in range(args.pools):
                client = await stack.enter_async_context(Client(instance_number=700 + i, port=0))
                # Pre-populate router cache so client knows to send to router port 1
                _inject_router_cache(client, net2, router_port1_mac)
                pools.append(client)

            objlist_client = await stack.enter_async_context(Client(instance_number=750, port=0))
            _inject_router_cache(objlist_client, net2, router_port1_mac)

            route_check_client = await stack.enter_async_context(
                Client(instance_number=751, port=0)
            )
            _inject_router_cache(route_check_client, net2, router_port1_mac)

            if not args.json:
                log("  Clients started with pre-populated router cache\n")

            # -- Warmup phase --
            warmup_stats = Stats()
            warmup_stop = asyncio.Event()
            warmup_workers = _spawn_workers(
                pools,
                objlist_client,
                route_check_client,
                server_addr,
                server_instance,
                net2,
                warmup_stats,
                warmup_stop,
                readers_per_pool=args.readers,
                writers_per_pool=args.writers,
                rpm_per_pool=args.rpm,
                wpm_per_pool=args.wpm,
                objlist_workers=args.objlist,
            )

            if not args.json:
                log(f"\n  Warmup: {len(warmup_workers)} workers for {args.warmup}s ...\n")
            await asyncio.sleep(args.warmup)
            await _stop_phase(warmup_stop, warmup_workers)

            warmup_rps = warmup_stats.total_ok / args.warmup if args.warmup else 0
            if not args.json:
                log(
                    f"  Warmup complete: {warmup_rps:.0f} req/s "
                    f"({warmup_stats.total_ok} ok, {warmup_stats.errors} errors)\n"
                )

            # -- Sustained measurement phase --
            stats = Stats()
            stop = asyncio.Event()

            # Re-inject route cache for sustained phase clients
            for client in pools:
                _inject_router_cache(client, net2, router_port1_mac)
            _inject_router_cache(objlist_client, net2, router_port1_mac)
            _inject_router_cache(route_check_client, net2, router_port1_mac)

            workers = _spawn_workers(
                pools,
                objlist_client,
                route_check_client,
                server_addr,
                server_instance,
                net2,
                stats,
                stop,
                readers_per_pool=args.readers,
                writers_per_pool=args.writers,
                rpm_per_pool=args.rpm,
                wpm_per_pool=args.wpm,
                objlist_workers=args.objlist,
            )

            wall_start = time.monotonic()
            if not args.json:
                log(
                    f"\n  Sustained: {len(workers)} workers for {args.sustain}s\n"
                    f"  {'Time':>6s}  {'Reads':>7s}  {'Writes':>7s}  "
                    f"{'RPM':>5s}  {'WPM':>5s}  {'OL':>4s}  "
                    f"{'RtChk':>5s}  {'Errors':>6s}  {'RPS':>8s}\n"
                    f"  {'-' * 6}  {'-' * 7}  {'-' * 7}  "
                    f"{'-' * 5}  {'-' * 5}  {'-' * 4}  "
                    f"{'-' * 5}  {'-' * 6}  {'-' * 8}\n"
                )

            prev_snap = stats.snapshot()
            interval = max(5, args.sustain // 10)
            for tick in range(interval, args.sustain + 1, interval):
                remaining = min(float(interval), args.sustain - (tick - interval))
                if remaining <= 0:
                    break
                await asyncio.sleep(remaining)

                snap = stats.snapshot()
                d = tuple(snap[i] - prev_snap[i] for i in range(8))
                interval_total = d[0] + d[1] + d[2] + d[3] + d[4] + d[5]
                interval_rps = interval_total / remaining
                prev_snap = snap

                if not args.json:
                    log(
                        f"  {tick:>4d}s  {d[0]:>7d}  {d[1]:>7d}  "
                        f"{d[2]:>5d}  {d[3]:>5d}  {d[4]:>4d}  "
                        f"{d[5]:>5d}  {d[7]:>6d}  "
                        f"{interval_rps:>7.0f}\n"
                    )

            # -- Shutdown --
            await _stop_phase(stop, workers)
            wall_elapsed = time.monotonic() - wall_start

        # -- Results --
        total = stats.total_ok + stats.errors
        error_rate = stats.errors / total if total else 0.0
        rps = stats.total_ok / wall_elapsed if wall_elapsed else 0
        all_lats = stats.combined_latencies()

        result: dict[str, Any] = {
            "mode": "local",
            "transport": "router",
            "config": {
                "remote_network": net2,
                "server_instance": server_instance,
                "server_address": server_addr,
                "num_pools": args.pools,
                "readers_per_pool": args.readers,
                "writers_per_pool": args.writers,
                "rpm_per_pool": args.rpm,
                "wpm_per_pool": args.wpm,
                "objlist_workers": args.objlist,
                "total_workers": total_workers,
                "warmup_seconds": args.warmup,
                "sustain_seconds": args.sustain,
            },
            "warmup": {
                "duration": args.warmup,
                "successful": warmup_stats.total_ok,
                "errors": warmup_stats.errors,
                "throughput_rps": round(warmup_rps, 1),
            },
            "sustained": {
                "duration": round(wall_elapsed, 1),
                "successful": stats.total_ok,
                "reads": len(stats.read_latencies),
                "writes": len(stats.write_latencies),
                "rpm_reads": len(stats.rpm_latencies),
                "wpm_writes": len(stats.wpm_latencies),
                "object_list_reads": len(stats.objlist_latencies),
                "route_checks": stats.route_discoveries,
                "errors": stats.errors,
                "error_rate": round(error_rate, 4),
                "throughput_rps": round(rps, 1),
                "latency_ms": _latency_dict(all_lats),
                "read_latency_ms": _latency_dict(stats.read_latencies),
                "write_latency_ms": _latency_dict(stats.write_latencies),
                "rpm_latency_ms": _latency_dict(stats.rpm_latencies),
                "wpm_latency_ms": _latency_dict(stats.wpm_latencies),
                "route_check_latency_ms": _latency_dict(stats.route_check_latencies),
            },
        }

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            log(
                f"\n{'=' * 70}\n"
                f"  RESULTS ({wall_elapsed:.1f}s sustained, routed)\n"
                f"{'=' * 70}\n"
                f"  Throughput:   {rps:,.0f} req/s\n"
                f"  Reads:        {len(stats.read_latencies):,}\n"
                f"  Writes:       {len(stats.write_latencies):,}\n"
                f"  RPMs:         {len(stats.rpm_latencies):,}\n"
                f"  WPMs:         {len(stats.wpm_latencies):,}\n"
                f"  Obj-lists:    {len(stats.objlist_latencies):,}\n"
                f"  Route checks: {stats.route_discoveries:,}\n"
                f"  Errors:       {stats.errors:,} ({error_rate:.2%})\n"
                f"  Latency:      {_latency_summary(all_lats)}\n"
                f"  Read lat:     {_latency_summary(stats.read_latencies)}\n"
                f"  Write lat:    {_latency_summary(stats.write_latencies)}\n"
                f"  RPM lat:      {_latency_summary(stats.rpm_latencies)}\n"
                f"  WPM lat:      {_latency_summary(stats.wpm_latencies)}\n"
                f"  Route lat:    {_latency_summary(stats.route_check_latencies)}\n"
                f"{'=' * 70}\n"
            )

        return result

    finally:
        await server_app.stop()
        await router_app.stop()


def main() -> None:
    args = _parse_args()

    import logging

    logging.basicConfig(level=logging.WARNING)

    profiler = None
    if args.profile or args.profile_html:
        from pyinstrument import Profiler

        profiler = Profiler(async_mode="enabled")

    if profiler:
        profiler.start()
    result = asyncio.run(_run(args))
    if profiler:
        profiler.stop()
        if args.profile:
            profiler.print(file=sys.stderr, unicode=True, color=True)
        if args.profile_html:
            profiler.write_html(args.profile_html)
            print(f"Profile saved to {args.profile_html}", file=sys.stderr)

    error_rate = result["sustained"]["error_rate"]
    # Routing on loopback has higher error rates than direct BIP due to
    # extra UDP hops and broadcast limitations on macOS.  Use 1% threshold.
    if error_rate >= 0.01:
        print(f"FAIL: Error rate {error_rate:.2%} exceeds 1%", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
