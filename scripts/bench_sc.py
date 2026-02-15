#!/usr/bin/env python3
"""Local BACnet/SC benchmark — hub, nodes, and stress workers in one process.

Runs a complete SC stress test without Docker by creating an in-process hub,
two echo nodes, and configurable unicast/broadcast workers.  All traffic
stays on localhost (127.0.0.1), eliminating network overhead so the benchmark
measures pure library throughput.

Usage::

    # Default: 8 unicast + 2 broadcast workers, 5s warmup, 30s sustained
    uv run python scripts/bench_sc.py

    # Custom: 16 unicast, 4 broadcast, 60s sustained
    uv run python scripts/bench_sc.py --unicast 16 --broadcast 4 --sustain 60

    # Quick smoke test
    uv run python scripts/bench_sc.py --sustain 5 --warmup 2

    # JSON output for CI/dashboards
    uv run python scripts/bench_sc.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import statistics
import struct
import sys
import time
from typing import Any


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local BACnet/SC benchmark")
    p.add_argument("--unicast", type=int, default=8, help="Unicast worker count (default: 8)")
    p.add_argument("--broadcast", type=int, default=2, help="Broadcast worker count (default: 2)")
    p.add_argument("--warmup", type=int, default=5, help="Warmup seconds (default: 5)")
    p.add_argument("--sustain", type=int, default=30, help="Sustained test seconds (default: 30)")
    p.add_argument("--port", type=int, default=0, help="Hub port (0=auto, default: 0)")
    p.add_argument("--json", action="store_true", help="Output JSON report to stdout")
    p.add_argument("--profile", action="store_true", help="Enable pyinstrument profiling")
    p.add_argument("--profile-html", metavar="PATH", help="Save interactive HTML profile to file")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Payload sizes matching real BACnet traffic patterns
# ---------------------------------------------------------------------------
PAYLOAD_SIZES = [25] * 30 + [200] * 30 + [800] * 25 + [1400] * 15


class Stats:
    """Thread-unsafe stats (fine — single event loop)."""

    __slots__ = (
        "broadcast_latencies",
        "bytes_received",
        "bytes_sent",
        "errors",
        "messages_received",
        "messages_sent",
        "unicast_latencies",
    )

    def __init__(self) -> None:
        self.unicast_latencies: list[float] = []
        self.broadcast_latencies: list[float] = []
        self.messages_sent: int = 0
        self.messages_received: int = 0
        self.bytes_sent: int = 0
        self.bytes_received: int = 0
        self.errors: int = 0

    @property
    def total_ok(self) -> int:
        return len(self.unicast_latencies) + len(self.broadcast_latencies)

    def snapshot(self) -> tuple[int, int, int, int, int, int, int]:
        return (
            len(self.unicast_latencies),
            len(self.broadcast_latencies),
            self.messages_sent,
            self.messages_received,
            self.bytes_sent,
            self.bytes_received,
            self.errors,
        )


# ---------------------------------------------------------------------------
# Workers (inlined to avoid docker.lib dependency)
# ---------------------------------------------------------------------------


def _make_payload(worker_id: int, seq: int) -> bytes:
    size = random.choice(PAYLOAD_SIZES)
    tag = struct.pack(">HI", worker_id, seq)
    pad_size = max(0, size - len(tag))
    padding = random.randbytes(pad_size) if pad_size > 0 else b""
    return tag + padding


async def _unicast_worker(
    worker_id: int,
    transport: Any,
    target_vmacs: list[bytes],
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
    stats: Stats,
    stop: asyncio.Event,
) -> None:
    seq = 0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        await asyncio.sleep(0)
        dest_vmac = random.choice(target_vmacs)
        payload = _make_payload(worker_id, seq)
        tag = payload[:6]
        seq += 1

        fut: asyncio.Future[tuple[bytes, bytes]] = loop.create_future()
        pending[tag] = fut

        t0 = time.monotonic()
        try:
            transport.send_unicast(payload, dest_vmac)
            stats.messages_sent += 1
            stats.bytes_sent += len(payload)

            echo_data, _source = await asyncio.wait_for(fut, timeout=10.0)
            elapsed = (time.monotonic() - t0) * 1000.0
            stats.unicast_latencies.append(elapsed)
            stats.messages_received += 1
            stats.bytes_received += len(echo_data)
        except Exception:
            stats.errors += 1
        finally:
            pending.pop(tag, None)


async def _broadcast_worker(
    worker_id: int,
    transport: Any,
    stats: Stats,
    stop: asyncio.Event,
) -> None:
    seq = 0
    while not stop.is_set():
        await asyncio.sleep(0)
        payload = _make_payload(worker_id + 1000, seq)
        seq += 1

        t0 = time.monotonic()
        try:
            transport.send_broadcast(payload)
            elapsed = (time.monotonic() - t0) * 1000.0
            stats.broadcast_latencies.append(elapsed)
            stats.messages_sent += 1
            stats.bytes_sent += len(payload)
        except Exception:
            stats.errors += 1

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=0.5)


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
# Orchestration
# ---------------------------------------------------------------------------


def _spawn_workers(
    transport: Any,
    target_vmacs: list[bytes],
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
    stats: Stats,
    stop: asyncio.Event,
    *,
    unicast_count: int,
    broadcast_count: int,
) -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = []
    for wid in range(unicast_count):
        tasks.append(
            asyncio.create_task(
                _unicast_worker(wid, transport, target_vmacs, pending, stats, stop)
            )
        )
    for wid in range(broadcast_count):
        tasks.append(asyncio.create_task(_broadcast_worker(wid, transport, stats, stop)))
    return tasks


async def _stop_phase(
    stop: asyncio.Event,
    workers: list[asyncio.Task[None]],
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
    *,
    timeout: float = 10.0,
) -> None:
    stop.set()
    _done, pend = await asyncio.wait(workers, timeout=timeout)
    for t in pend:
        t.cancel()
    for fut in pending.values():
        if not fut.done():
            fut.cancel()
    pending.clear()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    # Import SC modules (requires bac-py[secure])
    try:
        from bac_py.transport.sc import SCTransport, SCTransportConfig
        from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
        from bac_py.transport.sc.tls import SCTLSConfig
        from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID
    except ImportError:
        print(
            "ERROR: BACnet/SC requires the 'secure' extra.\n"
            "Install with: pip install bac-py[secure]",
            file=sys.stderr,
        )
        sys.exit(1)

    log = sys.stderr.write

    # -- Start hub --
    hub_vmac = SCVMAC.random()
    hub_uuid = DeviceUUID.generate()
    hub_port = args.port or 0

    hub = SCHubFunction(
        hub_vmac,
        hub_uuid,
        config=SCHubConfig(
            bind_address="127.0.0.1",
            bind_port=hub_port,
            tls_config=SCTLSConfig(allow_plaintext=True),
        ),
    )
    await hub.start()

    # Get the actual port (when 0 was requested)
    actual_port = hub._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    hub_uri = f"ws://127.0.0.1:{actual_port}"
    log(f"  Hub started on {hub_uri} (vmac={hub_vmac})\n")

    # -- Start echo nodes --
    node1_vmac = SCVMAC(b"\x02\xbb\x00\x00\x00\x01")
    node2_vmac = SCVMAC(b"\x02\xbb\x00\x00\x00\x02")
    nodes: list[SCTransport] = []

    for vmac in (node1_vmac, node2_vmac):
        node = SCTransport(
            SCTransportConfig(
                primary_hub_uri=hub_uri,
                tls_config=SCTLSConfig(allow_plaintext=True),
                vmac=vmac,
                min_reconnect_time=0.5,
                max_reconnect_time=5.0,
            )
        )

        def echo_handler(npdu: bytes, source_mac: bytes, _node: SCTransport = node) -> None:
            _node.send_unicast(b"ECHO:" + npdu, source_mac)

        node.on_receive(echo_handler)
        await node.start()
        nodes.append(node)

    # Wait for nodes to connect
    for node in nodes:
        connected = await node.hub_connector.wait_connected(timeout=10)
        if not connected:
            log("  ERROR: Echo node failed to connect to hub\n")
            sys.exit(1)
    log(f"  Echo nodes connected: {node1_vmac}, {node2_vmac}\n")

    # -- Start stress transport --
    stress_transport = SCTransport(
        SCTransportConfig(
            primary_hub_uri=hub_uri,
            tls_config=SCTLSConfig(allow_plaintext=True),
            min_reconnect_time=0.5,
            max_reconnect_time=5.0,
        )
    )

    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]] = {}

    def stress_echo_handler(npdu: bytes, source_mac: bytes) -> None:
        if npdu[:5] == b"ECHO:" and len(npdu) > 11:
            tag = npdu[5:11]
            fut = pending.get(tag)
            if fut and not fut.done():
                fut.set_result((npdu[5:], source_mac))

    stress_transport.on_receive(stress_echo_handler)
    await stress_transport.start()

    connected = await stress_transport.hub_connector.wait_connected(timeout=10)
    if not connected:
        log("  ERROR: Stress transport failed to connect to hub\n")
        sys.exit(1)
    log(f"  Stress client connected (vmac={stress_transport.local_mac.hex()})\n")

    target_vmacs = [node1_vmac.address, node2_vmac.address]
    total_workers = args.unicast + args.broadcast

    if not args.json:
        log(
            f"\n{'=' * 70}\n"
            f"  SC Local Benchmark: {args.unicast} unicast + "
            f"{args.broadcast} broadcast workers\n"
            f"  Total workers: {total_workers}  |  "
            f"Warmup: {args.warmup}s  |  Sustained: {args.sustain}s\n"
            f"  Hub: {hub_uri}  |  Nodes: 2 echo\n"
            f"{'=' * 70}\n"
        )

    try:
        # -- Warmup phase --
        warmup_stats = Stats()
        warmup_stop = asyncio.Event()
        warmup_workers = _spawn_workers(
            stress_transport,
            target_vmacs,
            pending,
            warmup_stats,
            warmup_stop,
            unicast_count=args.unicast,
            broadcast_count=args.broadcast,
        )

        if not args.json:
            log(f"\n  Warmup: {len(warmup_workers)} workers for {args.warmup}s ...\n")
        await asyncio.sleep(args.warmup)
        await _stop_phase(warmup_stop, warmup_workers, pending)

        warmup_mps = warmup_stats.total_ok / args.warmup if args.warmup else 0
        if not args.json:
            log(
                f"  Warmup complete: {warmup_mps:.0f} msg/s "
                f"({warmup_stats.total_ok} ok, {warmup_stats.errors} errors)\n"
            )

        # -- Sustained measurement phase --
        stats = Stats()
        stop = asyncio.Event()
        workers = _spawn_workers(
            stress_transport,
            target_vmacs,
            pending,
            stats,
            stop,
            unicast_count=args.unicast,
            broadcast_count=args.broadcast,
        )

        wall_start = time.monotonic()
        if not args.json:
            log(
                f"\n  Sustained: {len(workers)} workers for {args.sustain}s\n"
                f"  {'Time':>6s}  {'Unicast':>8s}  {'Bcast':>6s}  "
                f"{'Sent':>6s}  {'Recv':>6s}  {'Errors':>6s}  {'MPS':>8s}\n"
                f"  {'---' * 2}  {'---' * 3}  {'---' * 2}  "
                f"{'---' * 2}  {'---' * 2}  {'---' * 2}  {'---' * 3}\n"
            )

        prev_snap = stats.snapshot()
        interval = max(5, args.sustain // 10)
        for tick in range(interval, args.sustain + 1, interval):
            remaining = min(float(interval), args.sustain - (tick - interval))
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)

            snap = stats.snapshot()
            d = tuple(snap[i] - prev_snap[i] for i in range(7))
            interval_total = d[0] + d[1]
            interval_mps = interval_total / remaining
            prev_snap = snap

            if not args.json:
                log(
                    f"  {tick:>4d}s  {d[0]:>8d}  {d[1]:>6d}  "
                    f"{d[2]:>6d}  {d[3]:>6d}  {d[6]:>6d}  "
                    f"{interval_mps:>7.0f}\n"
                )

        # -- Shutdown --
        await _stop_phase(stop, workers, pending)
        wall_elapsed = time.monotonic() - wall_start

        # -- Results --
        total = stats.total_ok + stats.errors
        error_rate = stats.errors / total if total else 0.0
        mps = stats.total_ok / wall_elapsed if wall_elapsed else 0

        result = {
            "mode": "local",
            "config": {
                "hub_uri": hub_uri,
                "unicast_workers": args.unicast,
                "broadcast_workers": args.broadcast,
                "total_workers": total_workers,
                "warmup_seconds": args.warmup,
                "sustain_seconds": args.sustain,
            },
            "warmup": {
                "duration": args.warmup,
                "successful": warmup_stats.total_ok,
                "errors": warmup_stats.errors,
                "throughput_mps": round(warmup_mps, 1),
            },
            "sustained": {
                "duration": round(wall_elapsed, 1),
                "successful": stats.total_ok,
                "unicasts": len(stats.unicast_latencies),
                "broadcasts": len(stats.broadcast_latencies),
                "messages_sent": stats.messages_sent,
                "messages_received": stats.messages_received,
                "bytes_sent": stats.bytes_sent,
                "bytes_received": stats.bytes_received,
                "errors": stats.errors,
                "error_rate": round(error_rate, 4),
                "throughput_mps": round(mps, 1),
                "unicast_latency_ms": _latency_dict(stats.unicast_latencies),
                "broadcast_latency_ms": _latency_dict(stats.broadcast_latencies),
            },
        }

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            log(
                f"\n{'=' * 70}\n"
                f"  RESULTS ({wall_elapsed:.1f}s sustained)\n"
                f"{'=' * 70}\n"
                f"  Throughput:   {mps:,.0f} msg/s\n"
                f"  Unicasts:     {len(stats.unicast_latencies):,}\n"
                f"  Broadcasts:   {len(stats.broadcast_latencies):,}\n"
                f"  Msgs sent:    {stats.messages_sent:,}\n"
                f"  Msgs recv:    {stats.messages_received:,}\n"
                f"  Bytes sent:   {stats.bytes_sent:,}\n"
                f"  Bytes recv:   {stats.bytes_received:,}\n"
                f"  Errors:       {stats.errors:,} ({error_rate:.2%})\n"
                f"  Unicast lat:  {_latency_summary(stats.unicast_latencies)}\n"
                f"  Bcast lat:    {_latency_summary(stats.broadcast_latencies)}\n"
                f"{'=' * 70}\n"
            )

        return result

    finally:
        await stress_transport.stop()
        for node in nodes:
            await node.stop()
        await hub.stop()


def main() -> None:
    args = _parse_args()

    # Suppress noisy SC logging during benchmark
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
    if error_rate >= 0.005:
        print(f"FAIL: Error rate {error_rate:.2%} exceeds 0.5%", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
