"""Sustained stress test: mixed-workload throughput for 60 seconds.

Default concurrency: 1 pool x (2R + 1W + 1RPM + 1WPM) + 1 OL + 1 COV = 7
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time

import pytest

from bac_py import Client
from docker.lib.bip_stress import Stats, latency_summary, spawn_workers, stop_phase

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.70")
SERVER_INSTANCE = int(os.environ.get("SERVER_INSTANCE", "400"))

NUM_POOLS = int(os.environ.get("NUM_POOLS", "1"))
READERS_PER_POOL = int(os.environ.get("READERS_PER_POOL", "2"))
WRITERS_PER_POOL = int(os.environ.get("WRITERS_PER_POOL", "1"))
RPM_PER_POOL = int(os.environ.get("RPM_PER_POOL", "1"))
WPM_PER_POOL = int(os.environ.get("WPM_PER_POOL", "1"))
OBJLIST_WORKERS = int(os.environ.get("OBJLIST_WORKERS", "1"))
COV_SUBSCRIBERS = int(os.environ.get("COV_SUBSCRIBERS", "1"))
ERROR_BACKOFF = float(os.environ.get("ERROR_BACKOFF", "0.05"))
WARMUP_SECONDS = int(os.environ.get("WARMUP_SECONDS", "15"))
SUSTAIN_SECONDS = int(os.environ.get("SUSTAIN_SECONDS", "60"))

pytestmark = pytest.mark.asyncio


async def test_sustained_max_throughput() -> None:
    """60-second sustained stress test with mixed BACnet workloads."""
    per_pool = READERS_PER_POOL + WRITERS_PER_POOL + RPM_PER_POOL + WPM_PER_POOL
    total_workers = NUM_POOLS * per_pool + OBJLIST_WORKERS + COV_SUBSCRIBERS
    print(
        f"\n{'=' * 70}"
        f"\n  Stress Test: {NUM_POOLS} pools x "
        f"({READERS_PER_POOL}R + {WRITERS_PER_POOL}W + "
        f"{RPM_PER_POOL}RPM + {WPM_PER_POOL}WPM) + "
        f"{OBJLIST_WORKERS}OL + {COV_SUBSCRIBERS}COV"
        f"\n  Total workers: {total_workers}  |  "
        f"Warmup: {WARMUP_SECONDS}s  |  Sustained: {SUSTAIN_SECONDS}s"
        f"\n  Server: {SERVER} (instance {SERVER_INSTANCE})"
        f"\n{'=' * 70}"
    )

    # -- Create client pools --------------------------------------------------
    async with contextlib.AsyncExitStack() as stack:
        pools: list[Client] = []
        for i in range(NUM_POOLS):
            client = await stack.enter_async_context(Client(instance_number=800 + i, port=0))
            pools.append(client)

        objlist_client = await stack.enter_async_context(Client(instance_number=850, port=0))

        # -- Warmup phase -----------------------------------------------------
        warmup_stats = Stats()
        warmup_stop = asyncio.Event()
        warmup_tasks = spawn_workers(
            pools,
            objlist_client,
            SERVER,
            SERVER_INSTANCE,
            warmup_stats,
            warmup_stop,
            readers_per_pool=READERS_PER_POOL,
            writers_per_pool=WRITERS_PER_POOL,
            rpm_per_pool=RPM_PER_POOL,
            wpm_per_pool=WPM_PER_POOL,
            objlist_workers=OBJLIST_WORKERS,
            cov_subscribers=COV_SUBSCRIBERS,
            error_backoff=ERROR_BACKOFF,
        )

        print(f"\n  Warmup: {len(warmup_tasks)} workers for {WARMUP_SECONDS}s ...")
        await asyncio.sleep(WARMUP_SECONDS)
        await stop_phase(warmup_stop, warmup_tasks)

        warmup_rps = warmup_stats.total_ok / WARMUP_SECONDS
        print(
            f"  Warmup complete: {warmup_rps:.0f} req/s "
            f"({warmup_stats.total_ok} ok, {warmup_stats.errors} errors)"
        )

        # -- Sustained measurement phase --------------------------------------
        stats = Stats()
        stop = asyncio.Event()
        workers = spawn_workers(
            pools,
            objlist_client,
            SERVER,
            SERVER_INSTANCE,
            stats,
            stop,
            readers_per_pool=READERS_PER_POOL,
            writers_per_pool=WRITERS_PER_POOL,
            rpm_per_pool=RPM_PER_POOL,
            wpm_per_pool=WPM_PER_POOL,
            objlist_workers=OBJLIST_WORKERS,
            cov_subscribers=COV_SUBSCRIBERS,
            error_backoff=ERROR_BACKOFF,
        )

        wall_start = time.monotonic()
        print(
            f"\n  Sustained: {len(workers)} workers for {SUSTAIN_SECONDS}s"
            f"\n  {'Time':>6s}  {'Reads':>8s}  {'Writes':>8s}  {'RPM':>6s}  "
            f"{'WPM':>6s}  {'ObjL':>5s}  {'COV':>5s}  "
            f"{'Errors':>6s}  {'RPS':>8s}"
            f"\n  {'─' * 6}  {'─' * 8}  {'─' * 8}  {'─' * 6}  "
            f"{'─' * 6}  {'─' * 5}  {'─' * 5}  "
            f"{'─' * 6}  {'─' * 8}"
        )

        prev_snap = stats.snapshot()
        for tick in range(10, SUSTAIN_SECONDS + 1, 10):
            remaining = min(10.0, SUSTAIN_SECONDS - (tick - 10))
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)

            snap = stats.snapshot()
            d = tuple(snap[i] - prev_snap[i] for i in range(8))
            interval_total = d[0] + d[1] + d[2] + d[3] + d[4] + d[5]
            interval_rps = interval_total / remaining
            prev_snap = snap

            print(
                f"  {tick:>4d}s  {d[0]:>8d}  {d[1]:>8d}  {d[2]:>6d}  "
                f"{d[3]:>6d}  {d[4]:>5d}  {d[5]:>5d}  "
                f"{d[7]:>6d}  {interval_rps:>7.0f}"
            )

        # -- Shutdown ---------------------------------------------------------
        await stop_phase(stop, workers)
        wall_elapsed = time.monotonic() - wall_start

        # -- Results ----------------------------------------------------------
        total = stats.total_ok + stats.errors
        error_rate = stats.errors / total if total else 0.0
        rps = stats.total_ok / wall_elapsed
        all_lats = stats.combined_latencies()

        print(
            f"\n{'=' * 70}"
            f"\n  RESULTS ({wall_elapsed:.1f}s sustained)"
            f"\n{'=' * 70}"
            f"\n  Throughput:    {rps:,.0f} req/s"
            f"\n  Reads:         {len(stats.read_latencies):,}"
            f"\n  Writes:        {len(stats.write_latencies):,}"
            f"\n  RPM reads:     {len(stats.rpm_latencies):,}"
            f"\n  WPM writes:    {len(stats.wpm_latencies):,}"
            f"\n  Object-list:   {len(stats.objlist_latencies):,}"
            f"\n  COV subs:      {len(stats.cov_latencies):,}"
            f"\n  COV notifs:    {stats.cov_notifications:,}"
            f"\n  Errors:        {stats.errors:,} ({error_rate:.2%})"
            f"\n  Overall lat:   {latency_summary(all_lats)}"
            f"\n  Read lat:      {latency_summary(stats.read_latencies)}"
            f"\n  Write lat:     {latency_summary(stats.write_latencies)}"
            f"\n  RPM lat:       {latency_summary(stats.rpm_latencies)}"
            f"\n  WPM lat:       {latency_summary(stats.wpm_latencies)}"
            f"\n  ObjList lat:   {latency_summary(stats.objlist_latencies)}"
            f"\n{'=' * 70}"
        )

        assert error_rate < 0.005, f"Error rate {error_rate:.2%} exceeds 0.5%"
        assert len(stats.read_latencies) > 0, "No successful reads"
        assert len(stats.write_latencies) > 0, "No successful writes"
        assert len(stats.rpm_latencies) > 0, "No successful RPM reads"
        assert len(stats.wpm_latencies) > 0, "No successful WPM writes"
