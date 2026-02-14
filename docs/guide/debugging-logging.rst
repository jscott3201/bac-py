.. _debugging-logging:

Debugging and Logging
=====================

bac-py uses Python's standard :mod:`logging` module throughout the stack. Every
module has its own logger under the ``bac_py`` namespace, giving you granular
control over what gets logged and at what level.

No extra dependencies are required -- logging is built into the Python standard
library.


Quick Start
-----------

Enable logging with a single call before creating a ``Client``:

.. code-block:: python

   import logging

   logging.basicConfig(
       level=logging.INFO,
       format="%(asctime)s %(name)s %(levelname)s %(message)s",
   )

To see detailed protocol-level traces, set ``DEBUG``:

.. code-block:: python

   logging.basicConfig(
       level=logging.DEBUG,
       format="%(asctime)s %(name)s %(levelname)s %(message)s",
   )

You can also target specific modules to avoid noise from the rest of the stack:

.. code-block:: python

   import logging

   # Only show client-level operations
   logging.getLogger("bac_py.app.client").setLevel(logging.DEBUG)

   # Only show network-layer routing
   logging.getLogger("bac_py.network").setLevel(logging.DEBUG)

   # Show everything at WARNING and above by default
   logging.basicConfig(level=logging.WARNING)


Logger Hierarchy
----------------

All loggers are children of the root ``bac_py`` logger. Configuring a parent
logger automatically applies to its children. The full hierarchy:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Logger Name
     - What It Covers
   * - ``bac_py.app.application``
     - Application lifecycle (start/stop), APDU dispatch, device info cache
   * - ``bac_py.app.client``
     - All client request/response methods (56+ log points)
   * - ``bac_py.app.server``
     - Server handler dispatch, registration, error paths
   * - ``bac_py.app.tsm``
     - Transaction state machine: create, complete, timeout, retry
   * - ``bac_py.app.event_engine``
     - Event algorithm evaluation, state transitions, notifications
   * - ``bac_py.app.cov``
     - COV subscription lifecycle: create, remove, notify
   * - ``bac_py.app.audit``
     - Audit record creation, manager lifecycle
   * - ``bac_py.app.schedule_engine``
     - Schedule evaluation, value resolution
   * - ``bac_py.app.trendlog_engine``
     - Trend sample acquisition, engine lifecycle
   * - ``bac_py.network.npdu``
     - NPDU encode/decode, routing field validation
   * - ``bac_py.network.layer``
     - APDU dispatch, network message handling, router cache
   * - ``bac_py.network.router``
     - Router port start/stop, route table updates, forwarding
   * - ``bac_py.network.address``
     - Address parsing (IP, Ethernet, IPv6, MS/TP formats)
   * - ``bac_py.transport.bip``
     - BACnet/IP unicast/broadcast send, datagram receive
   * - ``bac_py.transport.bbmd``
     - BBMD lifecycle, broadcast forwarding, BDT/FDT queries
   * - ``bac_py.transport.ethernet``
     - Ethernet 802.3 frame send/receive
   * - ``bac_py.transport.bip6``
     - BACnet/IPv6 VMAC resolution, send/receive
   * - ``bac_py.transport.sc.*``
     - SC connection state machines, hub routing, failover, TLS, BVLC codec
   * - ``bac_py.encoding.apdu``
     - APDU type identification during encode/decode
   * - ``bac_py.encoding.tags``
     - Tag validation warnings (invalid tag numbers, malformed data)
   * - ``bac_py.types.enums``
     - Vendor-proprietary PropertyIdentifier creation
   * - ``bac_py.types.constructed``
     - CHOICE decode warnings (unexpected tag types)
   * - ``bac_py.objects.base``
     - ObjectDatabase add/remove, property read/write
   * - ``bac_py.objects.device``
     - DeviceObject creation
   * - ``bac_py.segmentation.manager``
     - Segment send/receive progress, window management, transfer completion
   * - ``bac_py.serialization``
     - Serialize/deserialize operations, type errors


Log Levels
----------

bac-py follows standard Python logging levels with consistent semantics:

**DEBUG**
   Protocol detail and trace information. APDU encode/decode types, individual
   request/response operations, state machine transitions, segment progress,
   property reads/writes. High volume -- use targeted loggers in production.

**INFO**
   Lifecycle events and significant operations. Application start/stop, transport
   start/stop, COV subscriptions created/removed, object database add/remove,
   event state transitions, segmented transfer completions.

**WARNING**
   Unusual but recoverable conditions. Unknown objects/properties in server
   requests, duplicate segments, write-access-denied, tag validation errors,
   CHOICE decode failures, address parse failures.

**ERROR**
   Failures that affect operation. Unhandled exceptions in service handlers
   (includes full traceback via ``exc_info=True``).


Practical Examples
------------------

Debugging a failed read
^^^^^^^^^^^^^^^^^^^^^^^

If reads are timing out or returning errors, enable client and TSM logging:

.. code-block:: python

   import logging

   logging.basicConfig(level=logging.WARNING)
   logging.getLogger("bac_py.app.client").setLevel(logging.DEBUG)
   logging.getLogger("bac_py.app.tsm").setLevel(logging.DEBUG)

This shows the outgoing request, transaction creation, retry attempts, and
final timeout or response.

Tracking device discovery
^^^^^^^^^^^^^^^^^^^^^^^^^

To see Who-Is/I-Am traffic and network routing during discovery:

.. code-block:: python

   logging.getLogger("bac_py.app.client").setLevel(logging.DEBUG)
   logging.getLogger("bac_py.network.layer").setLevel(logging.DEBUG)
   logging.getLogger("bac_py.transport.bip").setLevel(logging.DEBUG)

Monitoring server handlers
^^^^^^^^^^^^^^^^^^^^^^^^^^

When running a BACnet server, see which requests arrive and any errors:

.. code-block:: python

   logging.getLogger("bac_py.app.server").setLevel(logging.DEBUG)

Every incoming service request is logged with its parameters, and every error
path logs a WARNING before raising a BACnet error response.

Diagnosing segmentation issues
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For large transfers that fail mid-stream:

.. code-block:: python

   logging.getLogger("bac_py.segmentation.manager").setLevel(logging.DEBUG)

Shows individual segment send/receive, window fills, ACK handling, and
duplicate or out-of-window segment warnings.

Tracing SC connections
^^^^^^^^^^^^^^^^^^^^^^

For BACnet Secure Connect debugging:

.. code-block:: python

   logging.getLogger("bac_py.transport.sc").setLevel(logging.DEBUG)

Shows WebSocket connect/disconnect, TLS context creation, BVLC message
encode/decode, hub routing, failover events, and heartbeat cycles.


Writing Logs to a File
----------------------

.. code-block:: python

   import logging

   logging.basicConfig(
       level=logging.INFO,
       format="%(asctime)s %(name)s %(levelname)s %(message)s",
       filename="bacnet.log",
   )

Or use ``logging.config.dictConfig()`` for more advanced setups (multiple
handlers, rotation, structured output):

.. code-block:: python

   import logging.config

   logging.config.dictConfig({
       "version": 1,
       "handlers": {
           "console": {
               "class": "logging.StreamHandler",
               "level": "WARNING",
               "formatter": "brief",
           },
           "file": {
               "class": "logging.handlers.RotatingFileHandler",
               "filename": "bacnet.log",
               "maxBytes": 10_000_000,
               "backupCount": 3,
               "level": "DEBUG",
               "formatter": "detailed",
           },
       },
       "formatters": {
           "brief": {"format": "%(levelname)s %(message)s"},
           "detailed": {
               "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
           },
       },
       "loggers": {
           "bac_py": {"level": "DEBUG", "handlers": ["console", "file"]},
       },
   })


Performance Notes
-----------------

- **DEBUG logging on hot paths** (encoding, tags, APDU codec) adds overhead
  from string formatting on every packet. Use DEBUG only on targeted modules
  during troubleshooting, not globally in production.
- **INFO logging** is suitable for production monitoring. It covers lifecycle
  events and significant operations without per-packet overhead.
- The encoding and tag modules use WARNING-only logging (no DEBUG) specifically
  to avoid impacting APDU throughput.

See also: `Python asyncio debugging <https://docs.python.org/3/library/asyncio-dev.html>`_
for asyncio-specific debug techniques (slow callback detection, etc.).
