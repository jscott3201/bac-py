.. _benchmarks:

Benchmarks
==========

bac-py includes Docker-based stress tests that measure sustained throughput and
latency under realistic BACnet workloads. Two benchmark scenarios exercise the
core protocol paths: BACnet/IP (UDP) and BACnet Secure Connect (WebSocket).

Both tests enforce a **< 0.5% error rate** threshold over a 60-second sustained
measurement window, preceded by a 15-second warmup phase.


.. _bip-stress-benchmark:

BACnet/IP Stress Test
---------------------

The BIP stress test exercises the full BACnet/IP stack over real UDP sockets
between Docker containers. A stress server hosts 40 BACnet objects across 11
object types, and a single client pool runs mixed workloads concurrently.

**Server object inventory (40 objects):**

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

**Worker mix (7 total, representing a single intensive BACnet client):**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Worker Type
     - Count
     - Description
   * - ReadProperty
     - 2
     - Read ``present-value`` from random AI/BI/MSI objects (18 targets)
   * - WriteProperty
     - 1
     - Write ``present-value`` to random AnalogValue objects (5 targets)
   * - ReadPropertyMultiple
     - 1
     - Rotate through 5 spec sets reading 2-5 properties from 2-3 objects
   * - WritePropertyMultiple
     - 1
     - Rotate through 3 spec sets writing to 2 AV objects per request
   * - Object-list
     - 1
     - Read device ``object-list`` (throttled: 2s between reads)
   * - COV subscription
     - 1
     - Subscribe to COV on AI objects, resubscribe every 15s

All workers yield to the event loop between requests (``asyncio.sleep(0)``)
and apply a 50ms backoff on errors to prevent cascade failures from UDP socket
contention.

**Reference results (Docker, Alpine Linux, single host):**

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Metric
     - Value
   * - Sustained throughput
     - ~16,500 req/s
   * - Error rate
     - < 0.5%
   * - Overall latency (p50 / p95 / p99)
     - 0.1ms / 0.2ms / 0.2ms
   * - Duration
     - 60s sustained + 15s warmup

.. note::

   Throughput and latency numbers depend on host hardware, Docker networking
   overhead, and container resource limits. These results were collected on a
   single host with both client and server containers on the same Docker bridge
   network.


.. _sc-stress-benchmark:

BACnet/SC Stress Test
---------------------

The SC stress test exercises the BACnet Secure Connect WebSocket transport.
A test client connects to an SC hub alongside two echo nodes, then sends
varied-size NPDUs via unicast and broadcast at sustained concurrency.

**Architecture:**

- **SC Hub** -- WebSocket server routing messages between connected nodes
- **Echo Node 1 & 2** -- receive NPDUs and echo them back with an ``ECHO:`` prefix
- **Test Client** -- connects to the hub, sends unicast/broadcast NPDUs, measures
  round-trip latency for unicast via Future-based echo correlation

**Worker mix (10 total):**

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Worker Type
     - Count
     - Description
   * - Unicast
     - 8
     - Send NPDUs to random echo nodes, await echo response via tagged correlation
   * - Broadcast
     - 2
     - Send broadcast NPDUs (throttled: 0.5s between sends)

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
     - ~900 msg/s
   * - Error rate
     - < 0.5%
   * - Unicast latency (p50 / p95 / p99)
     - 0.3ms / 0.3ms / 0.6ms
   * - Duration
     - 60s sustained + 15s warmup


.. _running-benchmarks:

Running Benchmarks
------------------

The stress tests run as Docker Compose profiles. A Makefile wraps the common
invocations:

.. code-block:: bash

   # BACnet/IP stress test (pytest, pass/fail)
   make docker-test-stress

   # BACnet/IP stress runner (standalone, JSON report to stdout)
   make docker-stress

   # BACnet/SC stress test (pytest, pass/fail)
   make docker-test-sc-stress

   # BACnet/SC stress runner (standalone, JSON report to stdout)
   make docker-sc-stress

   # Run all Docker integration tests including stress
   make docker-test

The pytest variants assert ``error_rate < 0.5%`` and exit non-zero on failure.
The standalone runners output a structured JSON report suitable for CI pipelines
or historical tracking.


.. _benchmark-tuning:

Tuning Parameters
-----------------

Both stress tests are configured via environment variables in
``docker-compose.yml``. Override them to adjust concurrency, duration, or
thresholds.

**BACnet/IP parameters:**

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
   * - ``ERROR_BACKOFF``
     - 0.05
     - Seconds to pause after an error (prevents cascade)
   * - ``WARMUP_SECONDS``
     - 15
     - Warmup phase duration
   * - ``SUSTAIN_SECONDS``
     - 60
     - Sustained measurement duration

**BACnet/SC parameters:**

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Variable
     - Default
     - Description
   * - ``UNICAST_WORKERS``
     - 8
     - Unicast NPDU workers
   * - ``BROADCAST_WORKERS``
     - 2
     - Broadcast NPDU workers
   * - ``WARMUP_SECONDS``
     - 15
     - Warmup phase duration
   * - ``SUSTAIN_SECONDS``
     - 60
     - Sustained measurement duration
   * - ``CONNECT_TIMEOUT``
     - 30
     - Hub connection timeout (seconds)

.. tip::

   When increasing concurrency, watch for UDP socket contention (BIP) or
   WebSocket frame queuing (SC). The error backoff parameter is critical for
   BIP stability -- without it, failed requests retry instantly and flood the
   socket, causing cascade failures.
