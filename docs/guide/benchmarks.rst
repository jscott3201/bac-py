.. _benchmarks:

Benchmarks
==========

bac-py includes both **local** and **Docker-based** stress tests that measure
sustained throughput and latency under realistic BACnet workloads.  Four
benchmark scenarios exercise the core protocol paths: BACnet/IP (UDP),
BACnet Secure Connect (WebSocket), cross-network routing, and BBMD
foreign-device forwarding.

- **Local benchmarks** (``scripts/bench_*.py``) run server and clients in a
  single process on ``127.0.0.1`` using auto-assigned ports.  No Docker
  required.  Default: 5s warmup + 30s sustained.
- **Docker benchmarks** (``docker/scenarios/test_*_stress.py``) run server and
  clients in separate containers on Docker bridge networks.  Default: 15s
  warmup + 60s sustained.

Both enforce a **< 0.5% error rate** threshold (< 1% for router due to routing
overhead) over the sustained measurement window.


.. _stress-server-inventory:

Stress Server Object Inventory
------------------------------

All BIP, Router, and BBMD benchmarks (local and Docker) use the same 40-object
stress server across 11 object types:

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Object Type
     - Count
     - Notes
   * - AnalogInput
     - 10
     - Read-only, varied present_value and engineering units
   * - AnalogOutput
     - 5
     - Commandable (always per Clause 12.7)
   * - AnalogValue
     - 5
     - Commandable, used as write targets
   * - BinaryInput
     - 5
     - Read-only
   * - BinaryOutput
     - 3
     - Commandable (always)
   * - BinaryValue
     - 3
     - Commandable
   * - MultiStateInput
     - 3
     - 4 states each
   * - MultiStateValue
     - 2
     - Commandable, 3 states
   * - Schedule
     - 1
     - Weekly schedule
   * - Calendar
     - 1
     - Date list
   * - NotificationClass
     - 1
     - Priority and ack_required configured

All workers yield to the event loop between requests (``asyncio.sleep(0)``)
and apply a 50ms backoff on errors to prevent cascade failures from UDP socket
contention.


.. _local-benchmarks:

Local Benchmarks
----------------

Local benchmarks run entirely in a single Python process on localhost.  They
are fast to iterate on and require no Docker installation.  Because traffic
stays on the loopback interface, latency is lower than Docker but throughput
may also be lower due to single-process concurrency limits.


.. _local-bip-benchmark:

BACnet/IP (Local)
^^^^^^^^^^^^^^^^^

A ``BACnetApplication`` stress server with 40 objects and ``Client`` instances
all bound to ``127.0.0.1`` on auto-assigned UDP ports.

**Worker mix (7 total):** 2 readers, 1 writer, 1 RPM, 1 WPM, 1 object-list,
1 COV subscriber.

**Reference results (macOS, Apple M-series, single process):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~13,700 req/s
   * - Error rate
     - ~0.4%
   * - Overall latency (p50 / p95 / p99)
     - 0.1ms / 0.2ms / 0.2ms
   * - Duration
     - 30s sustained + 5s warmup


.. _local-sc-benchmark:

BACnet/SC (Local)
^^^^^^^^^^^^^^^^^

An in-process SC hub, two echo nodes, and a test client all connected via
``ws://127.0.0.1``.  Echo nodes receive NPDUs and echo them back with an
``ECHO:`` prefix for round-trip latency measurement.

**Worker mix (10 total):** 8 unicast, 2 broadcast.

**Reference results (macOS, Apple M-series, single process):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~10,200 msg/s
   * - Error rate
     - 0%
   * - Unicast latency (p50 / p95 / p99)
     - 0.7ms / 0.8ms / 0.9ms
   * - Duration
     - 30s sustained + 5s warmup

.. note::

   Local SC throughput is significantly higher than Docker (~1,100 msg/s)
   because WebSocket connections stay within a single event loop, avoiding
   inter-container TCP overhead and Docker network bridging.


.. _local-router-benchmark:

Router (Local)
^^^^^^^^^^^^^^

A ``BACnetApplication`` router bridges network 1 and network 2, both on
``127.0.0.1`` with auto-assigned ports.  A separate ``BACnetApplication``
stress server listens on network 2.  Clients on network 1 discover the server
via the router using routed addresses (``NETWORK:HEXMAC`` format).

**Worker mix (6 total):** 2 readers, 1 writer, 1 RPM, 1 WPM, 1 object-list.

**Reference results (macOS, Apple M-series, single process):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~8,500 req/s
   * - Error rate
     - ~0.7%
   * - Overall latency (p50 / p95 / p99)
     - 0.2ms / 0.3ms / 0.3ms
   * - Duration
     - 30s sustained + 5s warmup

.. note::

   Router throughput is lower than direct BIP because every request traverses
   two UDP hops (client -> router port 1 -> router port 2 -> server) and the
   NPDU must be decoded, re-addressed, and re-encoded at each hop.


.. _local-bbmd-benchmark:

BBMD (Local)
^^^^^^^^^^^^

A ``BACnetApplication`` with BBMD attached hosts 40 stress objects.  Clients
register as foreign devices with the BBMD and perform standard workloads plus
FDT and BDT reads.

**Worker mix (8 total):** 2 readers, 1 writer, 1 RPM, 1 WPM, 1 object-list,
1 FDT reader, 1 BDT reader.

**Reference results (macOS, Apple M-series, single process):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~13,500 req/s
   * - Error rate
     - ~0.4%
   * - Overall latency (p50 / p95 / p99)
     - 0.1ms / 0.2ms / 0.2ms
   * - Duration
     - 30s sustained + 5s warmup


.. _docker-benchmarks:

Docker Benchmarks
-----------------

Docker benchmarks run server and clients in separate containers on Docker
bridge networks.  They exercise the full network stack including inter-container
UDP/TCP, Docker NAT, and separate Python processes.  Results may differ
significantly from local benchmarks due to Docker networking overhead.


.. _bip-stress-benchmark:

BACnet/IP (Docker)
^^^^^^^^^^^^^^^^^^

The BIP stress test exercises the full BACnet/IP stack over real UDP sockets
between Docker containers.

**Worker mix (7 total):** 2 readers, 1 writer, 1 RPM, 1 WPM, 1 object-list,
1 COV subscriber.  Same as the local BIP benchmark.

**Reference results (Docker, Alpine Linux, single host):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~17,600 req/s
   * - Error rate
     - ~0.3%
   * - Overall latency (p50 / p95 / p99)
     - 0.1ms / 0.2ms / 0.2ms
   * - Duration
     - 60s sustained + 15s warmup

.. note::

   Docker BIP throughput can exceed local single-process throughput because
   server and clients run as separate OS processes, allowing true parallel
   execution across CPU cores.


.. _sc-stress-benchmark:

BACnet/SC (Docker)
^^^^^^^^^^^^^^^^^^

The SC stress test exercises the BACnet Secure Connect WebSocket transport.
A test client connects to an SC hub alongside two echo nodes, then sends
varied-size NPDUs via unicast and broadcast at sustained concurrency.

**Architecture:**

- **SC Hub** -- WebSocket server routing messages between connected nodes
- **Echo Node 1 & 2** -- receive NPDUs and echo them back with an ``ECHO:`` prefix
- **Test Client** -- connects to the hub, sends unicast/broadcast NPDUs, measures
  round-trip latency for unicast via Future-based echo correlation

**Worker mix (10 total):** 8 unicast, 2 broadcast.

**Payload size distribution (matches real BACnet traffic):**

.. list-table::
   :header-rows: 1
   :widths: 15 20 65

   * - Proportion
     - Size
     - Representative traffic
   * - 30%
     - 25 bytes
     - Simple ReadProperty responses, Who-Is
   * - 30%
     - 200 bytes
     - RPM responses, COV notifications
   * - 25%
     - 800 bytes
     - Object-list responses, segmented data
   * - 15%
     - 1,400 bytes
     - Large RPM responses, trend data

Each message is tagged with a 6-byte identifier (``worker_id`` + ``sequence``)
for echo correlation. The test verifies that echoed payloads match.

**Reference results (Docker, Alpine Linux, single host):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~1,100 msg/s
   * - Error rate
     - < 0.1%
   * - Unicast latency (p50 / p95 / p99)
     - 0.2ms / 0.3ms / 0.4ms
   * - Duration
     - 60s sustained + 15s warmup


.. _router-stress-benchmark:

Router (Docker)
^^^^^^^^^^^^^^^

The router stress test exercises cross-network routing performance by sending
standard BACnet service traffic through a BACnet router.  The test client is on
BACnet network 1 and the stress server (with 40 objects) is on BACnet network 2,
with all requests routed through the router.

**Architecture:**

- **Router** -- Bridges network 1 (172.30.1.0/24) and network 2 (172.30.2.0/24)
- **Stress Server** -- Standard stress server (40 objects) on network 2
- **Test Client** -- On network 1, discovers server via router, runs mixed workloads

**Worker mix (7 total):** 2 readers, 1 writer, 1 RPM, 1 WPM, 1 object-list,
plus a route health-check worker that periodically verifies the router is
advertising the remote network via Who-Is-Router-To-Network.

.. note::

   The Docker router stress test requires the router container to properly
   forward broadcast discovery messages between Docker bridge networks.
   Subnet-directed broadcast addresses must be configured correctly via the
   ``BROADCAST_ADDRESS`` environment variable for each network interface.


.. _bbmd-stress-benchmark:

BBMD (Docker)
^^^^^^^^^^^^^

The BBMD stress test exercises foreign-device management alongside standard
BACnet service traffic.  Test clients register as foreign devices with a BBMD
and perform concurrent reads, writes, RPM/WPM, plus BBMD-specific operations.

**Architecture:**

- **BBMD** -- Manages foreign device registrations and broadcast distribution
- **Stress Server** -- Standard stress server (40 objects) on the same network
- **Test Client** -- Registered as foreign device, runs mixed workloads + FDT/BDT reads

**Worker mix (8 total):** 2 readers, 1 writer, 1 RPM, 1 WPM, 1 object-list,
1 FDT reader, 1 BDT reader.

**Reference results (Docker, Alpine Linux, single host):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~17,800 req/s
   * - Error rate
     - ~0.3%
   * - Overall latency (p50 / p95 / p99)
     - 0.1ms / 0.2ms / 0.2ms
   * - Duration
     - 60s sustained + 15s warmup


.. _results-comparison:

Results Comparison
------------------

.. list-table::
   :header-rows: 1
   :widths: 20 20 15 20 15

   * - Transport
     - Local (req/s)
     - Errors
     - Docker (req/s)
     - Errors
   * - BACnet/IP
     - ~13,700
     - ~0.4%
     - ~17,600
     - ~0.3%
   * - BACnet/SC
     - ~10,200 msg/s
     - 0%
     - ~1,100 msg/s
     - < 0.1%
   * - Router
     - ~8,500
     - ~0.7%
     - --
     - --
   * - BBMD
     - ~13,500
     - ~0.4%
     - ~17,800
     - ~0.3%

**Key observations:**

- **BIP/BBMD Docker > Local:** Docker runs server and clients as separate OS
  processes, enabling true CPU parallelism.  The single-process local benchmark
  is limited by Python's GIL and event-loop scheduling.
- **SC Local >> Docker:** WebSocket connections within a single event loop avoid
  inter-container TCP overhead, Docker bridge NAT, and process context switching.
- **Router overhead:** Routing adds ~40% latency vs. direct BIP.  Each request
  traverses two UDP hops and requires NPDU decode/re-encode at each hop.

.. note::

   All reference results were collected on macOS with Apple M-series hardware
   (local) and Alpine Linux containers on the same host (Docker).  Throughput
   and latency depend on host hardware, OS, Docker version, and container
   resource limits.


.. _running-benchmarks:

Running Benchmarks
------------------

**Local benchmarks** (no Docker required):

.. code-block:: bash

   # BACnet/IP
   make bench-bip          # human-readable to stderr
   make bench-bip-json     # JSON report to stdout

   # BACnet/SC
   make bench-sc           # human-readable to stderr
   make bench-sc-json      # JSON report to stdout

   # Router
   make bench-router       # human-readable to stderr
   make bench-router-json  # JSON report to stdout

   # BBMD
   make bench-bbmd         # human-readable to stderr
   make bench-bbmd-json    # JSON report to stdout

**Docker benchmarks** (requires Docker):

.. code-block:: bash

   # BACnet/IP stress test (pytest, pass/fail)
   make docker-test-stress

   # BACnet/IP stress runner (standalone, JSON report to stdout)
   make docker-stress

   # BACnet/SC stress test (pytest, pass/fail)
   make docker-test-sc-stress

   # BACnet/SC stress runner (standalone, JSON report to stdout)
   make docker-sc-stress

   # Router stress test (pytest, pass/fail)
   make docker-test-router-stress

   # Router stress runner (standalone, JSON report to stdout)
   make docker-router-stress

   # BBMD stress test (pytest, pass/fail)
   make docker-test-bbmd-stress

   # BBMD stress runner (standalone, JSON report to stdout)
   make docker-bbmd-stress

   # Run all Docker integration tests including stress
   make docker-test

The pytest variants assert ``error_rate < 0.5%`` and exit non-zero on failure.
The standalone runners output a structured JSON report suitable for CI pipelines
or historical tracking.


.. _benchmark-tuning:

Tuning Parameters
-----------------

**Local benchmark CLI options:**

All local benchmarks accept ``--warmup`` (default 5), ``--sustain`` (default 30),
and ``--json`` flags.  Transport-specific options:

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Option
     - Default
     - Description
   * - ``--pools``
     - 1
     - Client pool count (BIP, Router, BBMD)
   * - ``--readers``
     - 2
     - ReadProperty workers per pool
   * - ``--writers``
     - 1
     - WriteProperty workers per pool
   * - ``--rpm``
     - 1
     - ReadPropertyMultiple workers per pool
   * - ``--wpm``
     - 1
     - WritePropertyMultiple workers per pool
   * - ``--objlist``
     - 1
     - Object-list reader workers
   * - ``--cov``
     - 1
     - COV subscribers (BIP only)
   * - ``--fdt-workers``
     - 1
     - FDT read workers (BBMD only)
   * - ``--bdt-workers``
     - 1
     - BDT read workers (BBMD only)
   * - ``--unicast``
     - 8
     - Unicast NPDU workers (SC only)
   * - ``--broadcast``
     - 2
     - Broadcast NPDU workers (SC only)
   * - ``--port``
     - 0
     - Server/hub port (0 = auto-assign)

**Docker benchmark environment variables:**

Docker benchmarks are configured via environment variables in
``docker-compose.yml``.  Override them to adjust concurrency, duration, or
thresholds.

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Variable
     - Default
     - Description
   * - ``NUM_POOLS``
     - 1
     - Number of client pools (each shares one UDP socket)
   * - ``READERS_PER_POOL``
     - 2
     - ReadProperty workers per pool
   * - ``WRITERS_PER_POOL``
     - 1
     - WriteProperty workers per pool
   * - ``RPM_PER_POOL``
     - 1
     - ReadPropertyMultiple workers per pool
   * - ``WPM_PER_POOL``
     - 1
     - WritePropertyMultiple workers per pool
   * - ``OBJLIST_WORKERS``
     - 1
     - Object-list reader workers (global)
   * - ``COV_SUBSCRIBERS``
     - 1
     - COV subscription workers (global)
   * - ``UNICAST_WORKERS``
     - 8
     - Unicast NPDU workers (SC only)
   * - ``BROADCAST_WORKERS``
     - 2
     - Broadcast NPDU workers (SC only)
   * - ``ERROR_BACKOFF``
     - 0.05
     - Seconds to pause after an error (prevents cascade)
   * - ``WARMUP_SECONDS``
     - 15
     - Warmup phase duration
   * - ``SUSTAIN_SECONDS``
     - 60
     - Sustained measurement duration
   * - ``CONNECT_TIMEOUT``
     - 30
     - Hub connection timeout in seconds (SC only)

.. tip::

   When increasing concurrency, watch for UDP socket contention (BIP) or
   WebSocket frame queuing (SC). The error backoff parameter is critical for
   BIP stability -- without it, failed requests retry instantly and flood the
   socket, causing cascade failures.
