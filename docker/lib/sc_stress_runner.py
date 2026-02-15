"""Standalone SC stress test runner with JSON output.

Thin wrapper around ``docker.lib.sc_stress`` shared module.  Connects
to an SC hub alongside echo nodes and sends varied-size NPDUs via
unicast and broadcast at sustained concurrency.

Structure:
  - Warmup phase    (stabilize WebSocket connections)
  - Sustained phase (full concurrency, all metrics collected)
  - JSON report to stdout

Configuration via env vars:
    SC_STRESS_HUB_URI:       Hub WebSocket URI        (default: ws://172.30.1.130:4443)
    SC_STRESS_NODE1_VMAC:    Echo node 1 VMAC hex     (default: 02BB00000001)
    SC_STRESS_NODE2_VMAC:    Echo node 2 VMAC hex     (default: 02BB00000002)
    UNICAST_WORKERS:         Unicast worker count     (default: 8)
    BROADCAST_WORKERS:       Broadcast worker count   (default: 2)
    WARMUP_SECONDS:          Warmup duration           (default: 15)
    SUSTAIN_SECONDS:         Sustained measurement     (default: 60)
    CONNECT_TIMEOUT:         Hub connect timeout       (default: 30)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

from docker.lib.sc_stress import (
    SCStats,
    create_echo_handler,
    latency_dict,
    spawn_workers,
    stop_phase,
)


async def main() -> None:
    from bac_py.transport.sc import SCTransport, SCTransportConfig
    from bac_py.transport.sc.tls import SCTLSConfig
    from bac_py.transport.sc.vmac import SCVMAC

    hub_uri = os.environ.get("SC_STRESS_HUB_URI", "ws://172.30.1.130:4443")
    node1_vmac_hex = os.environ.get("SC_STRESS_NODE1_VMAC", "02BB00000001")
    node2_vmac_hex = os.environ.get("SC_STRESS_NODE2_VMAC", "02BB00000002")
    unicast_workers = int(os.environ.get("UNICAST_WORKERS", "8"))
    broadcast_workers = int(os.environ.get("BROADCAST_WORKERS", "2"))
    warmup_seconds = int(os.environ.get("WARMUP_SECONDS", "15"))
    sustain_seconds = int(os.environ.get("SUSTAIN_SECONDS", "60"))
    connect_timeout = float(os.environ.get("CONNECT_TIMEOUT", "30"))

    # Build TLS config from env vars
    cert_dir = os.environ.get("TLS_CERT_DIR", "")
    cert_name = os.environ.get("TLS_CERT_NAME", "")
    if cert_dir and cert_name:
        tls_config = SCTLSConfig(
            private_key_path=os.path.join(cert_dir, f"{cert_name}.key"),
            certificate_path=os.path.join(cert_dir, f"{cert_name}.crt"),
            ca_certificates_path=os.path.join(cert_dir, "ca.crt"),
        )
        tls_label = "TLS 1.3"
    else:
        tls_config = SCTLSConfig(allow_plaintext=True)
        tls_label = "plaintext"

    target_vmacs = [
        SCVMAC.from_hex(node1_vmac_hex).address,
        SCVMAC.from_hex(node2_vmac_hex).address,
    ]
    total_workers = unicast_workers + broadcast_workers

    print(
        f"SC Stress test: {unicast_workers} unicast + {broadcast_workers} "
        f"broadcast = {total_workers} workers against {hub_uri} ({tls_label})",
        file=sys.stderr,
    )
    print(
        f"  Echo nodes: {node1_vmac_hex}, {node2_vmac_hex}",
        file=sys.stderr,
    )
    print(
        f"  Warmup: {warmup_seconds}s  |  Sustained: {sustain_seconds}s",
        file=sys.stderr,
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

    connected = await transport.hub_connector.wait_connected(timeout=connect_timeout)
    if not connected:
        print(
            f"FAILED: could not connect to SC hub at {hub_uri}",
            file=sys.stderr,
        )
        await transport.stop()
        sys.exit(1)

    local_vmac = transport.local_mac.hex()
    print(f"  Connected to hub (VMAC={local_vmac})", file=sys.stderr)

    try:
        # -- Warmup phase ------------------------------------------------------
        warmup_stats = SCStats()
        warmup_stop = asyncio.Event()
        warmup_tasks = spawn_workers(
            transport,
            target_vmacs,
            pending,
            warmup_stats,
            warmup_stop,
            unicast_count=unicast_workers,
            broadcast_count=broadcast_workers,
        )

        print(
            f"  Warmup: {len(warmup_tasks)} workers for {warmup_seconds}s ...",
            file=sys.stderr,
        )
        await asyncio.sleep(warmup_seconds)
        await stop_phase(warmup_stop, warmup_tasks, pending)

        warmup_mps = warmup_stats.total_ok / warmup_seconds if warmup_seconds else 0
        print(
            f"  Warmup complete: {warmup_mps:.0f} msg/s "
            f"({warmup_stats.total_ok} ok, {warmup_stats.errors} errors)",
            file=sys.stderr,
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
            unicast_count=unicast_workers,
            broadcast_count=broadcast_workers,
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
            interval_mps = (current_ok - prev_ok) / remaining
            prev_ok = current_ok
            print(
                f"  {tick:>4d}s: {interval_mps:.0f} msg/s",
                file=sys.stderr,
            )

        # -- Shutdown ----------------------------------------------------------
        await stop_phase(stop, workers, pending)

        wall_elapsed = time.monotonic() - wall_start
        total_reqs = stats.total_ok + stats.errors
        error_rate = stats.errors / total_reqs if total_reqs else 0.0
        throughput = stats.total_ok / wall_elapsed if wall_elapsed else 0

        # -- JSON report -------------------------------------------------------
        report: dict[str, Any] = {
            "config": {
                "hub_uri": hub_uri,
                "local_vmac": local_vmac,
                "node1_vmac": node1_vmac_hex,
                "node2_vmac": node2_vmac_hex,
                "unicast_workers": unicast_workers,
                "broadcast_workers": broadcast_workers,
                "total_workers": total_workers,
                "warmup_seconds": warmup_seconds,
                "sustain_seconds": sustain_seconds,
            },
            "warmup": {
                "duration": warmup_seconds,
                "messages": warmup_stats.total_ok + warmup_stats.errors,
                "successful": warmup_stats.total_ok,
                "errors": warmup_stats.errors,
                "throughput_mps": round(warmup_mps, 1),
                "latency_ms": latency_dict(
                    warmup_stats.unicast_latencies + warmup_stats.broadcast_latencies
                ),
            },
            "sustained": {
                "duration": round(wall_elapsed, 2),
                "messages": total_reqs,
                "successful": stats.total_ok,
                "unicasts": len(stats.unicast_latencies),
                "broadcasts": len(stats.broadcast_latencies),
                "messages_sent": stats.messages_sent,
                "messages_received": stats.messages_received,
                "bytes_sent": stats.bytes_sent,
                "bytes_received": stats.bytes_received,
                "errors": stats.errors,
                "error_rate": round(error_rate, 4),
                "throughput_mps": round(throughput, 1),
                "unicast_latency_ms": latency_dict(stats.unicast_latencies),
                "broadcast_latency_ms": latency_dict(stats.broadcast_latencies),
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
            f"\nPASSED: {throughput:.1f} msg/s sustained, "
            f"unicast p50="
            f"{latency_dict(stats.unicast_latencies)['p50']:.1f}ms, "
            f"p95="
            f"{latency_dict(stats.unicast_latencies)['p95']:.1f}ms",
            file=sys.stderr,
        )

    finally:
        await transport.stop()


if __name__ == "__main__":
    asyncio.run(main())
