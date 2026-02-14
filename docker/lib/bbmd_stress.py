"""Shared BBMD stress test workers, stats, and helpers.

Stresses BBMD foreign-device management alongside standard BACnet
service traffic.  The test client registers as a foreign device with the
BBMD and performs concurrent reads, writes, RPM/WPM, plus
BBMD-specific operations (FDT reads, BDT reads).

Both ``docker/scenarios/test_bbmd_stress.py`` (pytest) and
``docker/lib/bbmd_stress_runner.py`` (standalone JSON runner) import
from this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from docker.lib.bip_stress import (
    Stats,
    latency_dict,
    latency_summary,
    percentile,
    spawn_workers,
    stop_phase,
)

__all__ = [
    "BBMDStats",
    "bdt_worker",
    "fdt_worker",
    "latency_dict",
    "latency_summary",
    "percentile",
    "spawn_bbmd_workers",
    "stop_phase",
]


class BBMDStats(Stats):
    """Extended stats collector with BBMD-specific metrics."""

    def __init__(self) -> None:
        super().__init__()
        self.fdt_latencies: list[float] = []
        self.bdt_latencies: list[float] = []
        self.fdt_reads: int = 0
        self.bdt_reads: int = 0

    def bbmd_snapshot(self) -> tuple[int, int]:
        """Return (fdt_reads, bdt_reads) for interval reporting."""
        return self.fdt_reads, self.bdt_reads


async def fdt_worker(
    client: Any,
    bbmd_address: str,
    stats: BBMDStats,
    stop: asyncio.Event,
) -> None:
    """Periodically read the Foreign Device Table from the BBMD."""
    while not stop.is_set():
        t0 = time.monotonic()
        try:
            await client.read_fdt(bbmd_address, timeout=5.0)
            stats.fdt_latencies.append((time.monotonic() - t0) * 1000.0)
            stats.fdt_reads += 1
        except Exception:
            stats.errors += 1

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=5.0)


async def bdt_worker(
    client: Any,
    bbmd_address: str,
    stats: BBMDStats,
    stop: asyncio.Event,
) -> None:
    """Periodically read the Broadcast Distribution Table from the BBMD."""
    while not stop.is_set():
        t0 = time.monotonic()
        try:
            await client.read_bdt(bbmd_address, timeout=5.0)
            stats.bdt_latencies.append((time.monotonic() - t0) * 1000.0)
            stats.bdt_reads += 1
        except Exception:
            stats.errors += 1

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=5.0)


def spawn_bbmd_workers(
    pools: list[Any],
    objlist_client: Any,
    bbmd_client: Any,
    server: str,
    instance: int,
    bbmd_address: str,
    stats: BBMDStats,
    stop: asyncio.Event,
    *,
    readers_per_pool: int,
    writers_per_pool: int,
    rpm_per_pool: int,
    wpm_per_pool: int,
    objlist_workers: int,
    fdt_workers: int,
    bdt_workers: int,
    error_backoff: float = 0.05,
) -> list[asyncio.Task[None]]:
    """Create workers for BBMD stress test.

    Spawns the standard BIP workers plus BBMD-specific FDT/BDT readers.
    All pool clients should already be registered as foreign devices.
    """
    tasks = spawn_workers(
        pools,
        objlist_client,
        server,
        instance,
        stats,
        stop,
        readers_per_pool=readers_per_pool,
        writers_per_pool=writers_per_pool,
        rpm_per_pool=rpm_per_pool,
        wpm_per_pool=wpm_per_pool,
        objlist_workers=objlist_workers,
        cov_subscribers=0,  # No COV through BBMD (requires separate client)
        error_backoff=error_backoff,
    )

    for _ in range(fdt_workers):
        tasks.append(
            asyncio.create_task(fdt_worker(bbmd_client, bbmd_address, stats, stop))
        )
    for _ in range(bdt_workers):
        tasks.append(
            asyncio.create_task(bdt_worker(bbmd_client, bbmd_address, stats, stop))
        )

    return tasks
