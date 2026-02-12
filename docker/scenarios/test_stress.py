"""Scenario 4: Throughput and concurrency stress tests (pytest CI gate)."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from bac_py import Client

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.70")
SERVER_INSTANCE = int(os.environ.get("SERVER_INSTANCE", "400"))

pytestmark = pytest.mark.asyncio


async def test_concurrent_reads():
    """10 concurrent clients all reading successfully."""

    async def single_read(client_id: int) -> float:
        async with Client(instance_number=950 + client_id, port=0) as c:
            value = await c.read(SERVER, "ai,1", "present-value")
            assert isinstance(value, float)
            return value

    results = await asyncio.gather(*(single_read(i) for i in range(10)))
    assert len(results) == 10
    assert all(isinstance(v, float) for v in results)


async def test_rapid_sequential_reads():
    """100 sequential reads complete without error."""
    async with Client(instance_number=970, port=0) as client:
        start = time.monotonic()
        for _ in range(100):
            value = await client.read(SERVER, "ai,1", "present-value")
            assert isinstance(value, float)
        elapsed = time.monotonic() - start

        # Just log throughput -- no hard assertion on speed
        rps = 100 / elapsed if elapsed > 0 else float("inf")
        print(f"\n  Sequential reads: 100 in {elapsed:.2f}s ({rps:.1f} req/s)")
