"""Sustained BBMD stress test: foreign device throughput for 60 seconds.

Registers test clients as foreign devices with a BBMD and runs
mixed-workload stress workers alongside BBMD-specific operations
(FDT reads, BDT reads).  Measures throughput and latency under
concurrent foreign device management.

Default concurrency: 1 pool x (2R + 1W + 1RPM + 1WPM) + 1 OL + 1 FDT + 1 BDT = 8
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time

import pytest

from bac_py import Client
from docker.lib.bbmd_stress import (
    BBMDStats,
    latency_summary,
    spawn_bbmd_workers,
)
from docker.lib.bip_stress import stop_phase

BBMD_ADDRESS = os.environ.get("BBMD_ADDRESS", "172.30.1.170")
SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.171")
SERVER_INSTANCE = int(os.environ.get("SERVER_INSTANCE", "551"))

NUM_POOLS = int(os.environ.get("NUM_POOLS", "1"))
READERS_PER_POOL = int(os.environ.get("READERS_PER_POOL", "2"))
WRITERS_PER_POOL = int(os.environ.get("WRITERS_PER_POOL", "1"))
RPM_PER_POOL = int(os.environ.get("RPM_PER_POOL", "1"))
WPM_PER_POOL = int(os.environ.get("WPM_PER_POOL", "1"))
OBJLIST_WORKERS = int(os.environ.get("OBJLIST_WORKERS", "1"))
FDT_WORKERS = int(os.environ.get("FDT_WORKERS", "1"))
BDT_WORKERS = int(os.environ.get("BDT_WORKERS", "1"))
ERROR_BACKOFF = float(os.environ.get("ERROR_BACKOFF", "0.05"))
WARMUP_SECONDS = int(os.environ.get("WARMUP_SECONDS", "15"))
SUSTAIN_SECONDS = int(os.environ.get("SUSTAIN_SECONDS", "60"))

pytestmark = pytest.mark.asyncio


async def test_bbmd_sustained_throughput() -> None:
    """60-second sustained stress test with foreign device management."""
    per_pool = READERS_PER_POOL + WRITERS_PER_POOL + RPM_PER_POOL + WPM_PER_POOL
    total_workers = NUM_POOLS * per_pool + OBJLIST_WORKERS + FDT_WORKERS + BDT_WORKERS
    print(
        f"\n{'=' * 70}"
        f"\n  BBMD Stress Test: {NUM_POOLS} pools x "
        f"({READERS_PER_POOL}R + {WRITERS_PER_POOL}W + "
        f"{RPM_PER_POOL}RPM + {WPM_PER_POOL}WPM) + "
        f"{OBJLIST_WORKERS}OL + {FDT_WORKERS}FDT + {BDT_WORKERS}BDT"
        f"\n  Total workers: {total_workers}  |  "
        f"Warmup: {WARMUP_SECONDS}s  |  Sustained: {SUSTAIN_SECONDS}s"
        f"\n  Server: {SERVER} (instance {SERVER_INSTANCE})"
        f"\n  BBMD: {BBMD_ADDRESS}"
        f"\n{'=' * 70}"
    )

    async with contextlib.AsyncExitStack() as stack:
        # Create client pools registered as foreign devices
        pools: list[Client] = []
        for i in range(NUM_POOLS):
            client = await stack.enter_async_context(
                Client(
                    instance_number=600 + i,
                    port=0,
                    bbmd_address=BBMD_ADDRESS,
                    bbmd_ttl=120,
                )
            )
            pools.append(client)

        objlist_client = await stack.enter_async_context(
            Client(
                instance_number=650,
                port=0,
                bbmd_address=BBMD_ADDRESS,
                bbmd_ttl=120,
            )
        )
        bbmd_client = await stack.enter_async_context(Client(instance_number=651, port=0))

        print("  All clients registered as foreign devices")

        # -- Warmup phase ------------------------------------------------------
        warmup_stats = BBMDStats()
        warmup_stop = asyncio.Event()
        warmup_tasks = spawn_bbmd_workers(
            pools,
            objlist_client,
            bbmd_client,
            SERVER,
            SERVER_INSTANCE,
            BBMD_ADDRESS,
            warmup_stats,
            warmup_stop,
            readers_per_pool=READERS_PER_POOL,
            writers_per_pool=WRITERS_PER_POOL,
            rpm_per_pool=RPM_PER_POOL,
            wpm_per_pool=WPM_PER_POOL,
            objlist_workers=OBJLIST_WORKERS,
            fdt_workers=FDT_WORKERS,
            bdt_workers=BDT_WORKERS,
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

        # -- Sustained measurement phase ---------------------------------------
        stats = BBMDStats()
        stop = asyncio.Event()
        workers = spawn_bbmd_workers(
            pools,
            objlist_client,
            bbmd_client,
            SERVER,
            SERVER_INSTANCE,
            BBMD_ADDRESS,
            stats,
            stop,
            readers_per_pool=READERS_PER_POOL,
            writers_per_pool=WRITERS_PER_POOL,
            rpm_per_pool=RPM_PER_POOL,
            wpm_per_pool=WPM_PER_POOL,
            objlist_workers=OBJLIST_WORKERS,
            fdt_workers=FDT_WORKERS,
            bdt_workers=BDT_WORKERS,
            error_backoff=ERROR_BACKOFF,
        )

        wall_start = time.monotonic()
        print(
            f"\n  Sustained: {len(workers)} workers for {SUSTAIN_SECONDS}s"
            f"\n  {'Time':>6s}  {'Reads':>8s}  {'Writes':>8s}  {'RPM':>6s}  "
            f"{'WPM':>6s}  {'ObjL':>5s}  {'FDT':>4s}  {'BDT':>4s}  "
            f"{'Errors':>6s}  {'RPS':>8s}"
            f"\n  {'─' * 6}  {'─' * 8}  {'─' * 8}  {'─' * 6}  "
            f"{'─' * 6}  {'─' * 5}  {'─' * 4}  {'─' * 4}  "
            f"{'─' * 6}  {'─' * 8}"
        )

        prev_snap = stats.snapshot()
        prev_bbmd = stats.bbmd_snapshot()
        for tick in range(10, SUSTAIN_SECONDS + 1, 10):
            remaining = min(10.0, SUSTAIN_SECONDS - (tick - 10))
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)

            snap = stats.snapshot()
            bbmd_snap = stats.bbmd_snapshot()
            d = tuple(snap[i] - prev_snap[i] for i in range(8))
            fdt_d = bbmd_snap[0] - prev_bbmd[0]
            bdt_d = bbmd_snap[1] - prev_bbmd[1]
            interval_total = d[0] + d[1] + d[2] + d[3] + d[4]
            interval_rps = interval_total / remaining
            prev_snap = snap
            prev_bbmd = bbmd_snap

            print(
                f"  {tick:>4d}s  {d[0]:>8d}  {d[1]:>8d}  {d[2]:>6d}  "
                f"{d[3]:>6d}  {d[4]:>5d}  {fdt_d:>4d}  {bdt_d:>4d}  "
                f"{d[7]:>6d}  {interval_rps:>7.0f}"
            )

        # -- Shutdown ----------------------------------------------------------
        await stop_phase(stop, workers)
        wall_elapsed = time.monotonic() - wall_start

        # -- Results -----------------------------------------------------------
        total = stats.total_ok + stats.errors
        error_rate = stats.errors / total if total else 0.0
        rps = stats.total_ok / wall_elapsed
        all_lats = stats.combined_latencies()

        print(
            f"\n{'=' * 70}"
            f"\n  RESULTS ({wall_elapsed:.1f}s sustained, via BBMD)"
            f"\n{'=' * 70}"
            f"\n  Throughput:    {rps:,.0f} req/s"
            f"\n  Reads:         {len(stats.read_latencies):,}"
            f"\n  Writes:        {len(stats.write_latencies):,}"
            f"\n  RPM reads:     {len(stats.rpm_latencies):,}"
            f"\n  WPM writes:    {len(stats.wpm_latencies):,}"
            f"\n  Object-list:   {len(stats.objlist_latencies):,}"
            f"\n  FDT reads:     {stats.fdt_reads:,}"
            f"\n  BDT reads:     {stats.bdt_reads:,}"
            f"\n  Errors:        {stats.errors:,} ({error_rate:.2%})"
            f"\n  Overall lat:   {latency_summary(all_lats)}"
            f"\n  Read lat:      {latency_summary(stats.read_latencies)}"
            f"\n  Write lat:     {latency_summary(stats.write_latencies)}"
            f"\n  RPM lat:       {latency_summary(stats.rpm_latencies)}"
            f"\n  WPM lat:       {latency_summary(stats.wpm_latencies)}"
            f"\n  FDT lat:       {latency_summary(stats.fdt_latencies)}"
            f"\n  BDT lat:       {latency_summary(stats.bdt_latencies)}"
            f"\n{'=' * 70}"
        )

        assert error_rate < 0.005, f"Error rate {error_rate:.2%} exceeds 0.5%"
        assert len(stats.read_latencies) > 0, "No successful reads"
        assert len(stats.write_latencies) > 0, "No successful writes"
