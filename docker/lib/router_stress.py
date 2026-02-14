"""Shared router stress test workers, stats, and helpers.

Stresses cross-network routing performance by sending BACnet service
requests through a BACnet router.  Reuses the core workers from
:mod:`docker.lib.bip_stress` against a server on a remote network.

Both ``docker/scenarios/test_router_stress.py`` (pytest) and
``docker/lib/router_stress_runner.py`` (standalone JSON runner) import
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
    "RouterStats",
    "discover_remote_server",
    "latency_dict",
    "latency_summary",
    "percentile",
    "route_check_worker",
    "spawn_router_workers",
    "stop_phase",
]


class RouterStats(Stats):
    """Extended stats collector with routing-specific metrics."""

    def __init__(self) -> None:
        super().__init__()
        self.route_check_latencies: list[float] = []
        self.route_discoveries: int = 0


async def discover_remote_server(
    client: Any,
    remote_network: int,
    expected_instance: int,
    *,
    timeout: float = 30.0,
) -> str:
    """Discover the router, then find a server on a remote network.

    :param client: A started :class:`~bac_py.Client` instance.
    :param remote_network: Target BACnet network number (e.g. ``2``).
    :param expected_instance: Device instance to look for on the remote network.
    :param timeout: Total time budget for discovery.
    :returns: Address string usable for subsequent read/write operations.
    :raises RuntimeError: If the router or server cannot be found.
    """
    # Step 1: discover the router that knows about the remote network
    routers = await client.who_is_router_to_network(
        network=remote_network, timeout=min(10.0, timeout / 2)
    )
    if not routers:
        msg = f"No router found for network {remote_network}"
        raise RuntimeError(msg)

    all_nets = []
    for r in routers:
        all_nets.extend(r.networks)
    if remote_network not in all_nets:
        msg = f"Network {remote_network} not advertised by any router"
        raise RuntimeError(msg)

    # Step 2: discover the server on the remote network
    devices = await client.discover(
        low_limit=expected_instance,
        high_limit=expected_instance,
        destination=f"{remote_network}:*",
        timeout=min(15.0, timeout / 2),
        expected_count=1,
    )
    remote = next((d for d in devices if d.instance == expected_instance), None)
    if remote is None:
        msg = (
            f"Server instance {expected_instance} not found "
            f"on network {remote_network}"
        )
        raise RuntimeError(msg)

    result: str = remote.address_str
    return result


async def route_check_worker(
    client: Any,
    remote_network: int,
    stats: RouterStats,
    stop: asyncio.Event,
) -> None:
    """Periodically verify the route to the remote network is alive."""
    while not stop.is_set():
        t0 = time.monotonic()
        try:
            routers = await client.who_is_router_to_network(
                network=remote_network, timeout=5.0
            )
            if routers:
                stats.route_check_latencies.append(
                    (time.monotonic() - t0) * 1000.0
                )
                stats.route_discoveries += 1
        except Exception:
            stats.errors += 1

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=10.0)


def spawn_router_workers(
    pools: list[Any],
    objlist_client: Any,
    route_check_client: Any,
    server: str,
    instance: int,
    remote_network: int,
    stats: RouterStats,
    stop: asyncio.Event,
    *,
    readers_per_pool: int,
    writers_per_pool: int,
    rpm_per_pool: int,
    wpm_per_pool: int,
    objlist_workers: int,
    error_backoff: float = 0.05,
) -> list[asyncio.Task[None]]:
    """Create workers for router stress test.

    Spawns the standard BIP workers targeting the remote server address
    (which goes through the router), plus a route-check worker.
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
        cov_subscribers=0,  # No COV through router (requires separate client)
        error_backoff=error_backoff,
    )

    # Route health-check worker
    tasks.append(
        asyncio.create_task(
            route_check_worker(route_check_client, remote_network, stats, stop)
        )
    )

    return tasks
