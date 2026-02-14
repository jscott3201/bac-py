"""Scenario 4: 2-minute sustained stress test with mixed operation types.

Ramps concurrent clients across four 30-second phases, progressively
introducing reads, writes, and COV subscriptions.  Reports per-phase
throughput and latency by operation type, then asserts the overall
error rate stays below 5%.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import statistics
import time

import pytest

from bac_py import Client

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.70")
SERVER_INSTANCE = int(os.environ.get("SERVER_INSTANCE", "400"))

pytestmark = pytest.mark.asyncio

# (duration_seconds, readers, writers, cov_subscribers)
RAMP_SCHEDULE = [
    (30, 2, 0, 0),
    (30, 3, 2, 0),
    (30, 4, 3, 3),
    (30, 8, 6, 6),
]


class Stats:
    """Thread-safe-ish stats collector (safe in single-threaded asyncio)."""

    def __init__(self) -> None:
        self.read_latencies: list[float] = []
        self.write_latencies: list[float] = []
        self.cov_latencies: list[float] = []  # subscribe round-trip
        self.cov_notifications: list[int] = [0]
        self.errors: list[int] = [0]

    @property
    def all_latencies(self) -> list[float]:
        return self.read_latencies + self.write_latencies + self.cov_latencies

    @property
    def total_ok(self) -> int:
        return len(self.read_latencies) + len(self.write_latencies) + len(self.cov_latencies)


async def _read_worker(
    worker_id: int,
    server: str,
    stats: Stats,
    stop: asyncio.Event,
) -> None:
    """Continuous sequential reads of ai,1 present-value."""
    async with Client(instance_number=800 + worker_id, port=0) as client:
        while not stop.is_set():
            t0 = time.monotonic()
            try:
                await client.read(server, "ai,1", "present-value")
                stats.read_latencies.append((time.monotonic() - t0) * 1000.0)
            except Exception:
                stats.errors[0] += 1


async def _write_worker(
    worker_id: int,
    server: str,
    stats: Stats,
    stop: asyncio.Event,
) -> None:
    """Continuous sequential writes to av,1 present-value, alternating values."""
    async with Client(instance_number=800 + worker_id, port=0) as client:
        toggle = False
        while not stop.is_set():
            value = 72.5 if toggle else 68.0
            toggle = not toggle
            t0 = time.monotonic()
            try:
                await client.write(server, "av,1", "present-value", value, priority=8)
                stats.write_latencies.append((time.monotonic() - t0) * 1000.0)
            except Exception:
                stats.errors[0] += 1


async def _cov_worker(
    worker_id: int,
    server: str,
    stats: Stats,
    stop: asyncio.Event,
) -> None:
    """Subscribe to COV on ai,1, count notifications, resubscribe periodically."""
    process_id = 9000 + worker_id

    def _on_notification(_notif: object, _source: object) -> None:
        stats.cov_notifications[0] += 1

    async with Client(instance_number=800 + worker_id, port=0) as client:
        while not stop.is_set():
            t0 = time.monotonic()
            try:
                await client.subscribe_cov_ex(
                    server,
                    "ai,1",
                    process_id=process_id,
                    confirmed=False,
                    lifetime=60,
                    callback=_on_notification,
                )
                stats.cov_latencies.append((time.monotonic() - t0) * 1000.0)
            except Exception:
                stats.errors[0] += 1

            # Hold subscription for 10s then resubscribe (exercises the path)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=10.0)

            if not stop.is_set():
                with contextlib.suppress(Exception):
                    await client.unsubscribe_cov_ex(server, "ai,1", process_id=process_id)


def _pct(sorted_list: list[float], pct: float) -> float:
    idx = min(int(len(sorted_list) * pct), len(sorted_list) - 1)
    return sorted_list[idx]


async def test_sustained_ramp() -> None:
    """2-minute ramp: reads -> reads+writes -> reads+writes+COV."""
    stats = Stats()
    stop = asyncio.Event()
    workers: list[asyncio.Task[None]] = []
    next_id = 0

    read_count = 0
    write_count = 0
    cov_count = 0

    wall_start = time.monotonic()
    header = (
        f"  {'Phase':>5s}  {'R':>3s}  {'W':>3s}  {'C':>3s}  "
        f"{'Reads':>7s}  {'Writes':>7s}  {'COVs':>5s}  {'Notifs':>6s}  "
        f"{'Errs':>5s}  {'RPS':>8s}  {'p50ms':>7s}  {'p95ms':>7s}"
    )
    print(f"\n{header}")
    print(
        f"  {'─' * 5}  {'─' * 3}  {'─' * 3}  {'─' * 3}  "
        f"{'─' * 7}  {'─' * 7}  {'─' * 5}  {'─' * 6}  "
        f"{'─' * 5}  {'─' * 8}  {'─' * 7}  {'─' * 7}"
    )

    for phase_idx, (duration, target_readers, target_writers, target_cov) in enumerate(
        RAMP_SCHEDULE
    ):
        snap_reads = len(stats.read_latencies)
        snap_writes = len(stats.write_latencies)
        snap_covs = len(stats.cov_latencies)
        snap_notifs = stats.cov_notifications[0]
        snap_errs = stats.errors[0]

        # Ramp up readers
        while read_count < target_readers:
            task = asyncio.create_task(_read_worker(next_id, SERVER, stats, stop))
            workers.append(task)
            next_id += 1
            read_count += 1

        # Ramp up writers
        while write_count < target_writers:
            task = asyncio.create_task(_write_worker(next_id, SERVER, stats, stop))
            workers.append(task)
            next_id += 1
            write_count += 1

        # Ramp up COV subscribers
        while cov_count < target_cov:
            task = asyncio.create_task(_cov_worker(next_id, SERVER, stats, stop))
            workers.append(task)
            next_id += 1
            cov_count += 1

        await asyncio.sleep(duration)

        # Phase deltas
        phase_reads = len(stats.read_latencies) - snap_reads
        phase_writes = len(stats.write_latencies) - snap_writes
        phase_covs = len(stats.cov_latencies) - snap_covs
        phase_notifs = stats.cov_notifications[0] - snap_notifs
        phase_errs = stats.errors[0] - snap_errs
        phase_total = phase_reads + phase_writes + phase_covs
        rps = phase_total / duration if duration else 0

        phase_all = sorted(
            stats.read_latencies[snap_reads:]
            + stats.write_latencies[snap_writes:]
            + stats.cov_latencies[snap_covs:]
        )
        if phase_all:
            p50 = _pct(phase_all, 0.50)
            p95 = _pct(phase_all, 0.95)
        else:
            p50 = p95 = 0.0

        print(
            f"  {phase_idx + 1:>5d}  {target_readers:>3d}  {target_writers:>3d}  {target_cov:>3d}  "
            f"{phase_reads:>7d}  {phase_writes:>7d}  {phase_covs:>5d}  {phase_notifs:>6d}  "
            f"{phase_errs:>5d}  {rps:>7.1f}  {p50:>7.1f}  {p95:>7.1f}"
        )

    # Shutdown
    stop.set()
    _done, pending = await asyncio.wait(workers, timeout=10.0)
    for t in pending:
        t.cancel()

    wall_elapsed = time.monotonic() - wall_start
    total = stats.total_ok + stats.errors[0]
    error_rate = stats.errors[0] / total if total else 0.0
    overall_rps = stats.total_ok / wall_elapsed if wall_elapsed else 0

    all_lats = stats.all_latencies
    if all_lats:
        s = sorted(all_lats)
        p50 = _pct(s, 0.50)
        p95 = _pct(s, 0.95)
        p99 = _pct(s, 0.99)
        mean = statistics.mean(all_lats)
    else:
        p50 = p95 = p99 = mean = 0.0

    print(
        f"\n  Total: {stats.total_ok} ok ({len(stats.read_latencies)} reads, "
        f"{len(stats.write_latencies)} writes, {len(stats.cov_latencies)} cov subs, "
        f"{stats.cov_notifications[0]} cov notifs), "
        f"{stats.errors[0]} errors ({error_rate:.1%}), "
        f"{wall_elapsed:.1f}s, {overall_rps:.1f} rps"
    )
    print(f"  Latency: mean={mean:.1f}ms  p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms")

    assert error_rate < 0.05, f"Error rate {error_rate:.1%} exceeds 5%"
    assert len(stats.read_latencies) > 0, "No successful reads"
    assert len(stats.write_latencies) > 0, "No successful writes"
    assert len(stats.cov_latencies) > 0, "No successful COV subscriptions"
