"""Shared SC stress test workers, stats, payload generation, and helpers.

Both ``docker/scenarios/test_sc_stress.py`` (pytest) and
``docker/lib/sc_stress_runner.py`` (standalone JSON runner) import from
this module to avoid code duplication.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import statistics
import struct
import time
from typing import Any

# Payload sizes matching real BACnet traffic patterns
PAYLOAD_SIZES = [25] * 30 + [200] * 30 + [800] * 25 + [1400] * 15


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class SCStats:
    """Asyncio-safe stats for SC stress test."""

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
        """Return (unicasts, broadcasts, sent, received, bytes_s, bytes_r, errors)."""
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
# Payload
# ---------------------------------------------------------------------------


def make_payload(worker_id: int, seq: int) -> bytes:
    """Create a tagged payload with random size from the distribution.

    Uses ``random.randbytes()`` (C-level PRNG) for padding instead of
    a Python-level ``getrandbits`` loop — roughly 100x faster for large payloads.
    """
    size = random.choice(PAYLOAD_SIZES)
    tag = struct.pack(">HI", worker_id, seq)
    pad_size = max(0, size - len(tag))
    padding = random.randbytes(pad_size) if pad_size > 0 else b""
    return tag + padding


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


async def unicast_worker(
    worker_id: int,
    transport: Any,
    target_vmacs: list[bytes],
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
    stats: SCStats,
    stop: asyncio.Event,
) -> None:
    """Send unicast NPDUs to random echo nodes, wait for echo response."""
    seq = 0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        await asyncio.sleep(0)
        dest_vmac = random.choice(target_vmacs)
        payload = make_payload(worker_id, seq)
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


async def broadcast_worker(
    worker_id: int,
    transport: Any,
    stats: SCStats,
    stop: asyncio.Event,
) -> None:
    """Send broadcast NPDUs, throttled to avoid flooding."""
    seq = 0
    while not stop.is_set():
        await asyncio.sleep(0)
        payload = make_payload(worker_id + 1000, seq)
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
# Echo handler
# ---------------------------------------------------------------------------


def create_echo_handler(
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
) -> Any:
    """Create an echo response handler for SC stress tests.

    Echo nodes prefix responses with ``b"ECHO:"`` followed by the original
    payload.  The handler extracts the 6-byte tag and resolves the matching
    Future.
    """

    def handler(npdu: bytes, source_mac: bytes) -> None:
        if npdu[:5] == b"ECHO:" and len(npdu) > 11:
            tag = npdu[5:11]
            fut = pending.get(tag)
            if fut and not fut.done():
                fut.set_result((npdu[5:], source_mac))

    return handler


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


def spawn_workers(
    transport: Any,
    target_vmacs: list[bytes],
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
    stats: SCStats,
    stop: asyncio.Event,
    *,
    unicast_count: int,
    broadcast_count: int,
) -> list[asyncio.Task[None]]:
    """Create and return all SC worker tasks for a stress test phase."""
    tasks: list[asyncio.Task[None]] = []

    for wid in range(unicast_count):
        tasks.append(
            asyncio.create_task(unicast_worker(wid, transport, target_vmacs, pending, stats, stop))
        )
    for wid in range(broadcast_count):
        tasks.append(asyncio.create_task(broadcast_worker(wid, transport, stats, stop)))

    return tasks


async def stop_phase(
    stop: asyncio.Event,
    workers: list[asyncio.Task[None]],
    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]],
    *,
    timeout: float = 10.0,
) -> None:
    """Signal stop, wait for workers, and cancel pending futures."""
    stop.set()
    _done, pend = await asyncio.wait(workers, timeout=timeout)
    for t in pend:
        t.cancel()
    for fut in pending.values():
        if not fut.done():
            fut.cancel()
    pending.clear()


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
