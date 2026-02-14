"""Shared BIP stress test workers, stats, object pools, and helpers.

Both ``docker/scenarios/test_stress.py`` (pytest) and
``docker/lib/stress_runner.py`` (standalone JSON runner) import from
this module to avoid code duplication.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import statistics
import time
from typing import Any

# ---------------------------------------------------------------------------
# Object pools
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

    def __init__(self) -> None:
        self.read_latencies: list[float] = []
        self.write_latencies: list[float] = []
        self.rpm_latencies: list[float] = []
        self.wpm_latencies: list[float] = []
        self.objlist_latencies: list[float] = []
        self.cov_latencies: list[float] = []
        self.cov_notifications: int = 0
        self.errors: int = 0

    @property
    def total_ok(self) -> int:
        return (
            len(self.read_latencies)
            + len(self.write_latencies)
            + len(self.rpm_latencies)
            + len(self.wpm_latencies)
            + len(self.objlist_latencies)
            + len(self.cov_latencies)
        )

    def snapshot(self) -> tuple[int, int, int, int, int, int, int, int]:
        """Return (reads, writes, rpms, wpms, objlists, covs, cov_notifs, errors)."""
        return (
            len(self.read_latencies),
            len(self.write_latencies),
            len(self.rpm_latencies),
            len(self.wpm_latencies),
            len(self.objlist_latencies),
            len(self.cov_latencies),
            self.cov_notifications,
            self.errors,
        )

    def combined_latencies(self) -> list[float]:
        """Return all latencies combined.  Call once at report time."""
        return (
            self.read_latencies
            + self.write_latencies
            + self.rpm_latencies
            + self.wpm_latencies
            + self.objlist_latencies
            + self.cov_latencies
        )


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


async def read_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    """Read present-value from random readable objects."""
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


async def write_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    """Write present-value to random AnalogValue objects."""
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


async def rpm_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    """ReadPropertyMultiple with rotating spec sets."""
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


async def wpm_worker(
    client: Any, server: str, stats: Stats, stop: asyncio.Event, error_backoff: float = 0.05
) -> None:
    """WritePropertyMultiple with rotating spec sets."""
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


async def objlist_worker(
    client: Any, server: str, device_id: str, stats: Stats, stop: asyncio.Event
) -> None:
    """Read device object-list, throttled to avoid flooding."""
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


async def cov_worker(worker_id: int, server: str, stats: Stats, stop: asyncio.Event) -> None:
    """Subscribe to COV on AI objects, resubscribe periodically."""
    from bac_py import Client

    process_id = 9000 + worker_id
    ai_obj = f"ai,{(worker_id % 10) + 1}"

    def _on_notification(_notif: Any, _source: Any) -> None:
        stats.cov_notifications += 1

    async with Client(instance_number=900 + worker_id, port=0) as client:
        while not stop.is_set():
            t0 = time.monotonic()
            try:
                await client.subscribe_cov_ex(
                    server,
                    ai_obj,
                    process_id=process_id,
                    confirmed=False,
                    lifetime=120,
                    callback=_on_notification,
                )
                stats.cov_latencies.append((time.monotonic() - t0) * 1000.0)
            except Exception:
                stats.errors += 1

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=15.0)

            if not stop.is_set():
                with contextlib.suppress(Exception):
                    await client.unsubscribe_cov_ex(server, ai_obj, process_id=process_id)


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


def spawn_workers(
    pools: list[Any],
    objlist_client: Any,
    server: str,
    instance: int,
    stats: Stats,
    stop: asyncio.Event,
    *,
    readers_per_pool: int,
    writers_per_pool: int,
    rpm_per_pool: int,
    wpm_per_pool: int,
    objlist_workers: int,
    cov_subscribers: int,
    error_backoff: float = 0.05,
) -> list[asyncio.Task[None]]:
    """Create and return all worker tasks for a stress test phase."""
    tasks: list[asyncio.Task[None]] = []
    device_id = f"device,{instance}"

    for client in pools:
        for _ in range(readers_per_pool):
            tasks.append(
                asyncio.create_task(read_worker(client, server, stats, stop, error_backoff))
            )
        for _ in range(writers_per_pool):
            tasks.append(
                asyncio.create_task(write_worker(client, server, stats, stop, error_backoff))
            )
        for _ in range(rpm_per_pool):
            tasks.append(
                asyncio.create_task(rpm_worker(client, server, stats, stop, error_backoff))
            )
        for _ in range(wpm_per_pool):
            tasks.append(
                asyncio.create_task(wpm_worker(client, server, stats, stop, error_backoff))
            )

    for _ in range(objlist_workers):
        tasks.append(
            asyncio.create_task(objlist_worker(objlist_client, server, device_id, stats, stop))
        )
    for cov_id in range(cov_subscribers):
        tasks.append(asyncio.create_task(cov_worker(cov_id, server, stats, stop)))

    return tasks


async def stop_phase(
    stop: asyncio.Event,
    workers: list[asyncio.Task[None]],
    *,
    timeout: float = 10.0,
) -> None:
    """Signal stop and wait for workers to finish."""
    stop.set()
    _done, pending = await asyncio.wait(workers, timeout=timeout)
    for t in pending:
        t.cancel()


# ---------------------------------------------------------------------------
# Latency helpers
# ---------------------------------------------------------------------------


def percentile(sorted_list: list[float], pct: float) -> float:
    """Return the pct-th percentile from a pre-sorted list."""
    if not sorted_list:
        return 0.0
    idx = min(int(len(sorted_list) * pct), len(sorted_list) - 1)
    return sorted_list[idx]


def latency_summary(lats: list[float]) -> str:
    """Format latency stats as a human-readable string."""
    if not lats:
        return "n/a"
    s = sorted(lats)
    return (
        f"p50={percentile(s, 0.50):.1f}ms  "
        f"p95={percentile(s, 0.95):.1f}ms  "
        f"p99={percentile(s, 0.99):.1f}ms  "
        f"mean={statistics.mean(lats):.1f}ms"
    )


def latency_dict(lats: list[float]) -> dict[str, float]:
    """Return latency percentiles as a dict (for JSON serialization)."""
    if not lats:
        return {"mean": 0, "p50": 0, "p95": 0, "p99": 0}
    s = sorted(lats)
    return {
        "mean": round(statistics.mean(lats), 2),
        "p50": round(percentile(s, 0.50), 2),
        "p95": round(percentile(s, 0.95), 2),
        "p99": round(percentile(s, 0.99), 2),
    }
