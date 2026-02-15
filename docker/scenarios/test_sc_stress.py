"""Sustained SC stress test: WebSocket hub/node throughput for 60 seconds.

Thin wrapper around ``docker.lib.sc_stress`` shared module.  Connects
test nodes to an SC hub alongside two echo nodes, then sends varied-size
NPDUs via unicast and broadcast at sustained concurrency.

Structure:
  - 15 s warmup  (stabilize WebSocket connections)
  - 60 s sustained measurement at full concurrency
  - Graceful shutdown

Workers:
  - unicast_worker  (x8)  send varied-size NPDUs to echo nodes, await echo
  - broadcast_worker (x2)  send broadcast NPDUs (throttled 0.5s)
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from docker.lib.sc_stress import (
    SCStats,
    create_echo_handler,
    latency_summary,
    spawn_workers,
    stop_phase,
)

pytestmark = pytest.mark.asyncio

HUB_URI = os.environ.get("SC_STRESS_HUB_URI", "")
NODE1_VMAC = os.environ.get("SC_STRESS_NODE1_VMAC", "02BB00000001")
NODE2_VMAC = os.environ.get("SC_STRESS_NODE2_VMAC", "02BB00000002")

TLS_CERT_DIR = os.environ.get("TLS_CERT_DIR", "")
TLS_CERT_NAME = os.environ.get("TLS_CERT_NAME", "")

UNICAST_WORKERS = int(os.environ.get("UNICAST_WORKERS", "8"))
BROADCAST_WORKERS = int(os.environ.get("BROADCAST_WORKERS", "2"))
WARMUP_SECONDS = int(os.environ.get("WARMUP_SECONDS", "15"))
SUSTAIN_SECONDS = int(os.environ.get("SUSTAIN_SECONDS", "60"))
CONNECT_TIMEOUT = float(os.environ.get("CONNECT_TIMEOUT", "30"))


async def test_sc_sustained_throughput(
    sc_stress_hub_uri: str,
    sc_stress_node1_vmac: str,
    sc_stress_node2_vmac: str,
) -> None:
    """60-second sustained SC stress test with varied payload sizes."""
    from bac_py.transport.sc import SCTransport, SCTransportConfig
    from bac_py.transport.sc.tls import SCTLSConfig
    from bac_py.transport.sc.vmac import SCVMAC

    hub_uri = HUB_URI or sc_stress_hub_uri
    node1_vmac_hex = NODE1_VMAC or sc_stress_node1_vmac
    node2_vmac_hex = NODE2_VMAC or sc_stress_node2_vmac

    # Build TLS config from env vars
    if TLS_CERT_DIR and TLS_CERT_NAME:
        tls_config = SCTLSConfig(
            private_key_path=os.path.join(TLS_CERT_DIR, f"{TLS_CERT_NAME}.key"),
            certificate_path=os.path.join(TLS_CERT_DIR, f"{TLS_CERT_NAME}.crt"),
            ca_certificates_path=os.path.join(TLS_CERT_DIR, "ca.crt"),
        )
        tls_label = "TLS 1.3"
    else:
        tls_config = SCTLSConfig(allow_plaintext=True)
        tls_label = "plaintext"

    target_vmacs = [
        SCVMAC.from_hex(node1_vmac_hex).address,
        SCVMAC.from_hex(node2_vmac_hex).address,
    ]

    total_workers = UNICAST_WORKERS + BROADCAST_WORKERS
    print(
        f"\n{'=' * 70}"
        f"\n  SC Stress Test: {UNICAST_WORKERS} unicast + "
        f"{BROADCAST_WORKERS} broadcast workers"
        f"\n  Total workers: {total_workers}  |  "
        f"Warmup: {WARMUP_SECONDS}s  |  Sustained: {SUSTAIN_SECONDS}s"
        f"\n  Hub: {hub_uri}  |  {tls_label}"
        f"\n  Echo nodes: {node1_vmac_hex}, {node2_vmac_hex}"
        f"\n{'=' * 70}"
    )

    # -- Create test transport ------------------------------------------------
    transport = SCTransport(
        SCTransportConfig(
            primary_hub_uri=hub_uri,
            tls_config=tls_config,
            min_reconnect_time=0.5,
            max_reconnect_time=5.0,
        )
    )

    pending: dict[bytes, asyncio.Future[tuple[bytes, bytes]]] = {}
    handler = create_echo_handler(pending)
    transport.on_receive(handler)
    await transport.start()

    connected = await transport.hub_connector.wait_connected(timeout=CONNECT_TIMEOUT)
    assert connected, f"Failed to connect to SC hub at {hub_uri}"
    print(f"  Connected to hub (VMAC={transport.local_mac.hex()})")

    try:
        # -- Warmup phase ------------------------------------------------------
        warmup_stats = SCStats()
        warmup_stop = asyncio.Event()
        warmup_workers = spawn_workers(
            transport,
            target_vmacs,
            pending,
            warmup_stats,
            warmup_stop,
            unicast_count=UNICAST_WORKERS,
            broadcast_count=BROADCAST_WORKERS,
        )

        print(f"\n  Warmup: {len(warmup_workers)} workers for {WARMUP_SECONDS}s ...")
        await asyncio.sleep(WARMUP_SECONDS)
        await stop_phase(warmup_stop, warmup_workers, pending)

        warmup_mps = warmup_stats.total_ok / WARMUP_SECONDS if WARMUP_SECONDS else 0
        print(
            f"  Warmup complete: {warmup_mps:.0f} msg/s "
            f"({warmup_stats.total_ok} ok, {warmup_stats.errors} errors)"
        )

        # -- Sustained measurement phase ---------------------------------------
        stats = SCStats()
        stop = asyncio.Event()
        workers = spawn_workers(
            transport,
            target_vmacs,
            pending,
            stats,
            stop,
            unicast_count=UNICAST_WORKERS,
            broadcast_count=BROADCAST_WORKERS,
        )

        wall_start = time.monotonic()
        print(
            f"\n  Sustained: {len(workers)} workers for {SUSTAIN_SECONDS}s"
            f"\n  {'Time':>6s}  {'Unicast':>8s}  {'Bcast':>6s}  "
            f"{'Sent':>6s}  {'Recv':>6s}  {'Errors':>6s}  {'MPS':>8s}"
            f"\n  {'---' * 2}  {'---' * 3}  {'---' * 2}  "
            f"{'---' * 2}  {'---' * 2}  {'---' * 2}  {'---' * 3}"
        )

        prev_snap = stats.snapshot()
        for tick in range(10, SUSTAIN_SECONDS + 1, 10):
            remaining = min(10.0, SUSTAIN_SECONDS - (tick - 10))
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)

            snap = stats.snapshot()
            d = tuple(snap[i] - prev_snap[i] for i in range(7))
            interval_total = d[0] + d[1]
            interval_mps = interval_total / remaining
            prev_snap = snap

            print(
                f"  {tick:>4d}s  {d[0]:>8d}  {d[1]:>6d}  "
                f"{d[2]:>6d}  {d[3]:>6d}  {d[6]:>6d}  "
                f"{interval_mps:>7.0f}"
            )

        # -- Shutdown ----------------------------------------------------------
        await stop_phase(stop, workers, pending)
        wall_elapsed = time.monotonic() - wall_start

        # -- Results -----------------------------------------------------------
        total = stats.total_ok + stats.errors
        error_rate = stats.errors / total if total else 0.0
        mps = stats.total_ok / wall_elapsed if wall_elapsed else 0

        print(
            f"\n{'=' * 70}"
            f"\n  RESULTS ({wall_elapsed:.1f}s sustained)"
            f"\n{'=' * 70}"
            f"\n  Throughput:   {mps:,.0f} msg/s"
            f"\n  Unicasts:     {len(stats.unicast_latencies):,}"
            f"\n  Broadcasts:   {len(stats.broadcast_latencies):,}"
            f"\n  Msgs sent:    {stats.messages_sent:,}"
            f"\n  Msgs recv:    {stats.messages_received:,}"
            f"\n  Bytes sent:   {stats.bytes_sent:,}"
            f"\n  Bytes recv:   {stats.bytes_received:,}"
            f"\n  Errors:       {stats.errors:,} ({error_rate:.2%})"
            f"\n  Unicast lat:  "
            f"{latency_summary(stats.unicast_latencies)}"
            f"\n  Bcast lat:    "
            f"{latency_summary(stats.broadcast_latencies)}"
            f"\n{'=' * 70}"
        )

        assert error_rate < 0.005, f"Error rate {error_rate:.2%} exceeds 0.5%"
        assert len(stats.unicast_latencies) > 0, "No successful unicast messages"

    finally:
        await transport.stop()
