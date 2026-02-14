"""Standalone sustained stress test with mixed workloads and JSON output.

Progress is printed to stderr; the JSON report goes to stdout.
Exit code 1 if error rate exceeds 0.5%.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from typing import Any

from docker.lib.bip_stress import Stats, latency_dict, spawn_workers, stop_phase


async def main() -> None:
    from bac_py import Client

    server = os.environ.get("SERVER_ADDRESS", "172.30.1.70")
    instance = int(os.environ.get("SERVER_INSTANCE", "400"))
    num_pools = int(os.environ.get("NUM_POOLS", "1"))
    readers_per_pool = int(os.environ.get("READERS_PER_POOL", "2"))
    writers_per_pool = int(os.environ.get("WRITERS_PER_POOL", "1"))
    rpm_per_pool = int(os.environ.get("RPM_PER_POOL", "1"))
    wpm_per_pool = int(os.environ.get("WPM_PER_POOL", "1"))
    objlist_workers = int(os.environ.get("OBJLIST_WORKERS", "1"))
    cov_subscribers = int(os.environ.get("COV_SUBSCRIBERS", "1"))
    error_backoff = float(os.environ.get("ERROR_BACKOFF", "0.05"))
    warmup_seconds = int(os.environ.get("WARMUP_SECONDS", "15"))
    sustain_seconds = int(os.environ.get("SUSTAIN_SECONDS", "60"))

    per_pool = readers_per_pool + writers_per_pool + rpm_per_pool + wpm_per_pool
    total_workers = num_pools * per_pool + objlist_workers + cov_subscribers

    print(
        f"Stress test: {num_pools} pools x "
        f"({readers_per_pool}R + {writers_per_pool}W + "
        f"{rpm_per_pool}RPM + {wpm_per_pool}WPM) + "
        f"{objlist_workers}OL + {cov_subscribers}COV = "
        f"{total_workers} workers against {server}",
        file=sys.stderr,
    )
    print(
        f"  Warmup: {warmup_seconds}s  |  Sustained: {sustain_seconds}s",
        file=sys.stderr,
    )

    # -- Create client pools --------------------------------------------------
    async with contextlib.AsyncExitStack() as stack:
        pools: list[Any] = []
        for i in range(num_pools):
            client = await stack.enter_async_context(Client(instance_number=800 + i, port=0))
            pools.append(client)

        objlist_client = await stack.enter_async_context(Client(instance_number=850, port=0))

        # -- Warmup phase -----------------------------------------------------
        warmup_stats = Stats()
        warmup_stop = asyncio.Event()
        warmup_tasks = spawn_workers(
            pools,
            objlist_client,
            server,
            instance,
            warmup_stats,
            warmup_stop,
            readers_per_pool=readers_per_pool,
            writers_per_pool=writers_per_pool,
            rpm_per_pool=rpm_per_pool,
            wpm_per_pool=wpm_per_pool,
            objlist_workers=objlist_workers,
            cov_subscribers=cov_subscribers,
            error_backoff=error_backoff,
        )

        print(
            f"  Warmup: {len(warmup_tasks)} workers for {warmup_seconds}s ...",
            file=sys.stderr,
        )
        await asyncio.sleep(warmup_seconds)
        await stop_phase(warmup_stop, warmup_tasks)

        warmup_rps = warmup_stats.total_ok / warmup_seconds
        print(
            f"  Warmup complete: {warmup_rps:.0f} req/s "
            f"({warmup_stats.total_ok} ok, {warmup_stats.errors} errors)",
            file=sys.stderr,
        )

        # -- Sustained measurement phase --------------------------------------
        stats = Stats()
        stop = asyncio.Event()
        workers = spawn_workers(
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
            cov_subscribers=cov_subscribers,
            error_backoff=error_backoff,
        )

        wall_start = time.monotonic()
        print(
            f"  Sustained: {len(workers)} workers for {sustain_seconds}s ...",
            file=sys.stderr,
        )

        # Progress every 10s
        prev_ok = 0
        for tick in range(10, sustain_seconds + 1, 10):
            remaining = min(10.0, sustain_seconds - (tick - 10))
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)
            current_ok = stats.total_ok
            interval_rps = (current_ok - prev_ok) / remaining
            prev_ok = current_ok
            print(
                f"  {tick:>4d}s: {interval_rps:.0f} req/s cumulative",
                file=sys.stderr,
            )

        # -- Shutdown ---------------------------------------------------------
        await stop_phase(stop, workers)
        wall_elapsed = time.monotonic() - wall_start
        total_reqs = stats.total_ok + stats.errors
        error_rate = stats.errors / total_reqs if total_reqs else 0.0
        throughput = stats.total_ok / wall_elapsed if wall_elapsed else 0

        # -- JSON report ------------------------------------------------------
        warmup_all = warmup_stats.combined_latencies()
        all_lats = stats.combined_latencies()
        all_lats_d = latency_dict(all_lats)

        report: dict[str, Any] = {
            "config": {
                "server_address": server,
                "num_pools": num_pools,
                "readers_per_pool": readers_per_pool,
                "writers_per_pool": writers_per_pool,
                "rpm_per_pool": rpm_per_pool,
                "wpm_per_pool": wpm_per_pool,
                "objlist_workers": objlist_workers,
                "cov_subscribers": cov_subscribers,
                "total_workers": total_workers,
                "warmup_seconds": warmup_seconds,
                "sustain_seconds": sustain_seconds,
            },
            "warmup": {
                "duration_s": warmup_seconds,
                "total_requests": warmup_stats.total_ok + warmup_stats.errors,
                "successful": warmup_stats.total_ok,
                "errors": warmup_stats.errors,
                "throughput_rps": round(warmup_rps, 1),
                "latency_ms": latency_dict(warmup_all),
            },
            "sustained": {
                "duration_s": round(wall_elapsed, 2),
                "total_requests": total_reqs,
                "successful": stats.total_ok,
                "reads": len(stats.read_latencies),
                "writes": len(stats.write_latencies),
                "rpm_reads": len(stats.rpm_latencies),
                "wpm_writes": len(stats.wpm_latencies),
                "object_list_reads": len(stats.objlist_latencies),
                "cov_subscriptions": len(stats.cov_latencies),
                "cov_notifications": stats.cov_notifications,
                "errors": stats.errors,
                "error_rate": round(error_rate, 4),
                "throughput_rps": round(throughput, 1),
                "latency_ms": all_lats_d,
                "read_latency_ms": latency_dict(stats.read_latencies),
                "write_latency_ms": latency_dict(stats.write_latencies),
                "rpm_latency_ms": latency_dict(stats.rpm_latencies),
                "wpm_latency_ms": latency_dict(stats.wpm_latencies),
                "objlist_latency_ms": latency_dict(stats.objlist_latencies),
            },
        }

        print(json.dumps(report, indent=2))

        if error_rate > 0.005:
            print(
                f"\nFAILED: error rate {error_rate:.2%} exceeds 0.5% threshold",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"\nPASSED: {throughput:.1f} req/s sustained, "
            f"p50={all_lats_d['p50']:.1f}ms, "
            f"p95={all_lats_d['p95']:.1f}ms, "
            f"p99={all_lats_d['p99']:.1f}ms",
            file=sys.stderr,
        )


if __name__ == "__main__":
    asyncio.run(main())
