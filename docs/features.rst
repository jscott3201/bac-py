.. _features:

Features
========

.. _core-protocol:

Core Protocol
-------------

- **Full BACnet/IP support** per ASHRAE 135-2020 Annex J over UDP
- **Client and server** in a single library
- **Async-first** design using native ``asyncio`` -- no threads, no blocking
- **Zero dependencies** for the core library (optional ``orjson`` for JSON
  serialization)
- **Python 3.13+** with comprehensive type hints throughout


.. _convenience-api:

Convenience API
---------------

The :class:`~bac_py.client.Client` class provides a simplified interface for
common operations. See :doc:`getting-started` for a walkthrough and
:doc:`guide/client-guide` for the full capabilities reference.

- **String-based addressing** -- pass IP addresses as strings instead of
  constructing :class:`~bac_py.network.address.BACnetAddress` objects
  (see :ref:`addressing`)
- **String object/property identifiers** -- use ``"ai,1"`` and ``"pv"``
  instead of ``ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)`` and
  ``PropertyIdentifier.PRESENT_VALUE``
- **Short aliases** -- 48 object type aliases (``ai``, ``ao``, ``av``,
  ``bi``, ``bo``, ``bv``, ``dev``, ``sched``, ``tl``, ``nc``, etc.) and
  45 property aliases (``pv``, ``name``, ``type``, ``list``, ``priority``,
  ``min``, ``max``, ``status``, etc.)
  (see :ref:`string-aliases` for the full table)
- **Auto-decoding on read** -- raw BACnet tags are decoded to Python values
  automatically
- **Auto-encoding on write** -- Python types are encoded to the correct BACnet
  application tag based on the value type, target object type, and property
  (see :ref:`smart-encoding`)
- **Async context manager** -- ``async with Client(...) as client:`` handles
  startup and shutdown
- **Alarm management** -- ``get_alarm_summary()``, ``get_enrollment_summary()``,
  ``get_event_information()``, ``acknowledge_alarm()`` with string arguments
- **Extended discovery** -- ``discover_extended()`` enriches Who-Is results
  with Annex X profile metadata
- **Text messaging** -- ``send_text_message()`` with confirmed/unconfirmed mode
- **Backup/restore** -- ``backup()`` and ``restore()`` handle the full
  Clause 19.1 procedure
- **Object management** -- ``create_object()``, ``delete_object()``, and
  ``get_object_list()`` with string identifiers
- **Device control** -- ``device_communication_control()`` and
  ``reinitialize_device()`` accept string enum values (e.g. ``"disable"``,
  ``"warmstart"``); ``time_synchronization()`` and
  ``utc_time_synchronization()`` sync device clocks
- **Object search** -- ``who_has()`` finds objects by identifier or name
  across the network with string arguments
- **Audit log queries** -- ``query_audit_log()`` with string addressing
- **Property-level COV** -- ``subscribe_cov_property()`` for monitoring
  specific properties, ``subscribe_cov_property_multiple()`` for batching
  multiple subscriptions in a single request
- **Hierarchy traversal** -- ``traverse_hierarchy()`` walks Structured View
  objects to collect all object identifiers
- **WriteGroup** -- ``write_group()`` for unconfirmed channel writes
- **Unconfigured device discovery** -- ``discover_unconfigured()`` finds
  devices via Who-Am-I (Clause 19.7)
- **Consistent string support** -- all methods accept string addresses,
  object identifiers, property identifiers, and enum values wherever
  applicable
- **Top-level server exports** -- ``BACnetApplication``, ``DefaultServerHandlers``,
  ``DeviceObject``, ``RouterConfig``, ``RouterPortConfig`` importable
  directly from ``bac_py``


.. _smart-encoding:

Smart Encoding
--------------

When writing values, bac-py automatically selects the correct BACnet
application tag. See the :ref:`encoding rules table <encoding-rules>` in
the examples.

- ``float`` is encoded as Real
- ``int`` on an analog present-value is encoded as Real
- ``int`` on a binary present-value is encoded as Enumerated
- ``int`` on a multi-state present-value is encoded as Unsigned
- ``str`` is encoded as Character String
- ``bool`` is encoded as Enumerated (1/0)
- ``None`` is encoded as Null (relinquishes a command priority)
- ``IntEnum`` is encoded as Enumerated
- ``bytes`` are passed through as pre-encoded data

For non-present-value properties, a built-in type hint map ensures common
properties like ``units``, ``cov-increment``, ``high-limit``, and
``out-of-service`` are encoded with the correct application tag.


.. _supported-services:

Supported Services
------------------

Confirmed services (request/response, reliable delivery):

- ReadProperty
- WriteProperty
- ReadPropertyMultiple
- WritePropertyMultiple
- ReadRange
- CreateObject / DeleteObject
- AddListElement / RemoveListElement
- AtomicReadFile / AtomicWriteFile
- SubscribeCOV / SubscribeCOVProperty / SubscribeCOVPropertyMultiple
- ConfirmedCOVNotification / ConfirmedCOVNotificationMultiple
- ConfirmedEventNotification
- GetAlarmSummary / GetEnrollmentSummary / GetEventInformation
- AcknowledgeAlarm
- ConfirmedTextMessage
- ConfirmedAuditNotification *(new in 2020)*
- AuditLogQuery *(new in 2020)*
- VT-Open / VT-Close / VT-Data
- DeviceCommunicationControl
- ReinitializeDevice
- ConfirmedPrivateTransfer

Unconfirmed services (broadcast, fire-and-forget):

- Who-Is / I-Am
- Who-Has / I-Have
- TimeSynchronization / UTCTimeSynchronization
- UnconfirmedCOVNotification / UnconfirmedCOVNotificationMultiple
- UnconfirmedEventNotification
- UnconfirmedTextMessage
- UnconfirmedAuditNotification *(new in 2020)*
- Who-Am-I / You-Are *(new in 2020)*
- WriteGroup
- UnconfirmedPrivateTransfer

See :ref:`reading-properties`, :ref:`writing-properties`,
:ref:`device-discovery`, :ref:`cov-subscriptions`, and :ref:`client-guide`
for usage examples. File access, private transfer, WriteGroup, virtual
terminal, and list element operations are documented in :doc:`guide/client-guide`.


.. _object-model:

Object Model
-------------

bac-py provides a complete BACnet object model as frozen dataclasses with
property validation and read/write access control:

- **Sensing:** AnalogInput, BinaryInput, MultiStateInput
- **Control:** AnalogOutput, BinaryOutput, MultiStateOutput
- **Values:** AnalogValue, BinaryValue, MultiStateValue
- **Infrastructure:** Device, File, NetworkPort, Channel
- **Scheduling:** Schedule, Calendar
- **Trending:** TrendLog, TrendLogMultiple
- **Events:** EventEnrollment, NotificationClass, EventLog, AlertEnrollment,
  NotificationForwarder
- **Safety:** LifeSafetyPoint, LifeSafetyZone
- **Auditing:** AuditReporter, AuditLog *(new in 2020)*
- **Access Control:** AccessDoor, AccessPoint, AccessZone, AccessCredential,
  AccessRights, CredentialDataInput
- **Advanced Control:** Command, Timer, Staging, LoadControl
- **Lighting:** LightingOutput
- **Facility:** Elevator, EscalatorGroup, Lift (transportation objects)
- **Other:** Accumulator, Loop, Program, Averaging, PulseConverter, Group,
  GlobalGroup, StructuredView
- **Generic values:** IntegerValue, CharacterStringValue, DateValue,
  DateTimeValue, LargeAnalogValue, OctetStringValue, PositiveIntegerValue,
  TimeValue, BitStringValue, and pattern variants

Each object type defines its standard properties, default values, and which
properties are writable. See :ref:`basic-server-setup` for creating and
hosting objects, :ref:`commandable-objects` for priority arrays, and
:ref:`supported-object-types` for the categorized list.


.. _device-info-caching:

Device Info Caching
-------------------

When bac-py discovers devices via Who-Is / I-Am, the I-Am response includes
``max_apdu_length_accepted`` and ``segmentation_supported`` values. These are
automatically cached in a per-application :class:`~bac_py.app.application.DeviceInfo`
store so that subsequent confirmed requests to that device use the correct
maximum APDU size (Clause 19.4).

This means segmented requests are automatically constrained to the remote
device's capabilities without any manual configuration. The cache is populated
transparently from I-Am responses and used in
:meth:`~bac_py.app.application.BACnetApplication.confirmed_request`. You can
also query the cache directly:

.. code-block:: python

   info = client.app.get_device_info(device_address)
   if info is not None:
       print(f"Max APDU: {info.max_apdu_length}")
       print(f"Segmentation: {info.segmentation_supported}")


.. _segmentation:

Segmentation
------------

bac-py automatically handles segmented requests and responses per Clause 5.2.
When a message exceeds the maximum APDU size, it is split into segments and
reassembled transparently. This works in both directions -- sending segmented
requests and receiving segmented responses.


.. _network-routing:

Network Routing
---------------

Multi-port BACnet router support per Clause 6. Configure bac-py to route
between multiple BACnet/IP networks with dynamic routing tables, including
mixed data link forwarding between BACnet/IP, MS/TP, and Ethernet networks.
The network layer automatically learns router paths from routed APDUs
(SNET/SADR fields), enabling efficient unicast routing to devices on remote
networks. See :ref:`multi-network-routing` for configuration and
:ref:`router-discovery` for discovering existing routers on the network.

.. code-block:: python

   from bac_py.app.application import DeviceConfig, RouterConfig, RouterPortConfig

   config = DeviceConfig(
       instance_number=999,
       router_config=RouterConfig(
           ports=[
               RouterPortConfig(port_id=0, network_number=1,
                                interface="192.168.1.10", port=47808),
               RouterPortConfig(port_id=1, network_number=2,
                                interface="10.0.0.10", port=47808),
           ],
           application_port_id=0,
       ),
   )


.. _extended-discovery:

Extended Discovery
------------------

Extended discovery *(Annex X)* enriches standard Who-Is / I-Am device
discovery with profile metadata. After discovering devices on the network,
:meth:`~bac_py.app.client.BACnetClient.discover_extended` reads each
device's ``Profile_Name``, ``Profile_Location``, and ``Tags`` properties
via ReadPropertyMultiple to populate the returned
:class:`~bac_py.app.client.DiscoveredDevice` with classification metadata.
Devices that do not support these optional properties gracefully return
``None`` for the missing fields.

.. code-block:: python

   devices = await client.discover_extended(timeout=3.0)
   for dev in devices:
       print(dev.instance, dev.profile_name, dev.tags)

Hierarchy traversal via
:meth:`~bac_py.client.Client.traverse_hierarchy` reads
``Subordinate_List`` from Structured View objects and recursively descends
to collect all object identifiers in a device's object hierarchy:

.. code-block:: python

   all_objects = await client.traverse_hierarchy(
       "192.168.1.100", "structured-view,1"
   )


.. _bacnet-ipv6:

BACnet/IPv6
-----------

Full BACnet/IPv6 transport per ASHRAE 135-2020 Annex U, fully integrated with
:class:`~bac_py.client.Client` and :class:`~bac_py.app.application.BACnetApplication`:

- **IPv6 BVLL** with all 13 function codes (type ``0x82``), source VMAC on every message
- **3-byte VMAC** virtual addressing with automatic address resolution
- **IPv6 multicast** broadcasts (``ff02::bac0`` link-local, ``ff05::bac0`` site-local)
- **Address resolution** protocol with TTL-based caching
- **IPv6 BBMD** (BBMD6Manager) with BDT/FDT forwarding and foreign device management
- **IPv6 foreign device** registration with TTL-based re-registration
- **Application-layer integration** --- use ``ipv6=True`` on ``Client`` or ``DeviceConfig``

.. code-block:: python

   from bac_py import Client

   # Simple IPv6 client
   async with Client(ipv6=True) as client:
       devices = await client.discover(timeout=5.0)

   # IPv6 foreign device
   async with Client(
       ipv6=True,
       bbmd_address="[fd00::1]:47808",
   ) as client:
       devices = await client.discover(timeout=5.0)

For advanced transport-level usage:

.. code-block:: python

   from bac_py.transport.bip6 import BIP6Transport

   transport = BIP6Transport(interface="::", port=0xBAC0)
   await transport.start()


.. _bacnet-ethernet:

BACnet Ethernet (ISO 8802-3)
----------------------------

Raw Ethernet transport per Clause 7 for legacy BACnet installations that use
IEEE 802.3 frames with 802.2 LLC headers instead of IP:

- **802.2 LLC** header (DSAP=0x82, SSAP=0x82, Control=0x03) per Clause 7
- **6-byte IEEE MAC** addressing
- **Max NPDU** of 1497 bytes (1500 Ethernet payload minus 3-byte LLC header)
- **Linux** support via ``AF_PACKET`` / ``SOCK_RAW`` (requires ``CAP_NET_RAW``)
- **macOS** support via BPF devices (``/dev/bpf*``)
- **Async I/O** using ``asyncio`` event loop reader integration

.. code-block:: python

   from bac_py.transport.ethernet import EthernetTransport

   transport = EthernetTransport(
       interface="eth0",
       mac_address=b"\x00\x11\x22\x33\x44\x55",  # optional on Linux
   )
   await transport.start()

Ethernet MAC addresses are supported in :func:`~bac_py.network.address.parse_address`
using colon-separated hex notation:

.. code-block:: python

   from bac_py.network.address import parse_address

   # Local Ethernet address
   addr = parse_address("aa:bb:cc:dd:ee:ff")

   # Remote Ethernet address on network 5
   addr = parse_address("5:aa:bb:cc:dd:ee:ff")

Remote MS/TP, ARCNET, and other non-IP stations behind routers are addressed
using ``network:hex_mac`` notation where the MAC is even-length hex:

.. code-block:: python

   # MS/TP device (1-byte MAC) on network 4352
   addr = parse_address("4352:01")

   # 2-byte MAC device on network 100
   addr = parse_address("100:0a0b")


.. _bacnet-sc:

BACnet Secure Connect (Annex AB)
---------------------------------

BACnet/SC provides a modern, IT-friendly transport for BACnet using TLS-secured
WebSocket connections per ASHRAE 135-2020 Annex AB. It replaces broadcast UDP
with a hub-and-spoke topology that traverses firewalls and NAT without special
network configuration.

- **WebSocket/TLS hub-and-spoke topology** -- all nodes connect to a central
  hub over TLS-secured WebSockets, eliminating the need for UDP broadcast
  routing and BBMD infrastructure
- **13 BVLC-SC message types** -- BVLC-Result, Encapsulated-NPDU,
  Address-Resolution, Address-Resolution-ACK, Advertisement,
  Advertisement-Solicitation, Connect-Request, Connect-Accept,
  Disconnect-Request, Disconnect-ACK, Heartbeat-Request, Heartbeat-ACK,
  and Proprietary-Message
- **Hub Function** (server) -- accepts WebSocket connections from hub
  connectors and broadcasts/unicasts encapsulated NPDUs to connected nodes
- **Hub Connector** (client with failover) -- connects to a primary hub with
  automatic failover to a secondary hub on connection loss
- **Direct peer-to-peer connections** via Node Switch -- establishes direct
  WebSocket connections between nodes for latency-sensitive traffic, bypassing
  the hub when both peers are reachable
- **TLS 1.3 with mutual authentication** -- both hub and node present X.509
  certificates; the operational certificate includes the BACnet device UUID
  for identity binding
- **6-byte VMAC addressing** -- Virtual MAC addresses uniquely identify SC
  nodes within the BACnet/SC network, analogous to Ethernet MAC addresses
- **Optional dependency** -- install with ``pip install bac-py[secure]``
  (requires ``websockets`` and ``cryptography``)

.. code-block:: python

   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   config = SCTransportConfig(
       primary_hub_uri="wss://hub.example.com:8443",
       failover_hub_uri="wss://hub2.example.com:8443",
       tls_config=SCTLSConfig(
           ca_certificates_path="/path/to/ca.pem",
           certificate_path="/path/to/device.pem",
           private_key_path="/path/to/device.key",
       ),
   )
   transport = SCTransport(config)
   await transport.start()

See :doc:`guide/secure-connect` for a full walkthrough of hub setup, direct
connections, failover configuration, and TLS certificate management.


.. _bbmd-support:

BBMD Support
------------

Broadcast Management Device (BBMD) support for cross-subnet communication.
See :ref:`foreign-device-registration` for a full example.

- Register as a foreign device with a remote BBMD
- Automatic re-registration before TTL expiry
- Read and write Broadcast Distribution Tables (BDT)
- Read Foreign Device Tables (FDT)
- Delete FDT entries
- **IPv4 multicast** (Annex J.8) as an alternative to directed broadcast using
  multicast group ``239.255.186.192`` -- enable with ``multicast_enabled=True``


.. _priority-arrays:

Priority Arrays
---------------

16-level command prioritization for commandable objects. Write to specific
priority levels and relinquish priorities by writing ``None``:

.. code-block:: python

   # Command at priority 8
   await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)

   # Relinquish priority 8
   await client.write("192.168.1.100", "av,1", "pv", None, priority=8)

   # Read the full priority array
   pa = await client.read("192.168.1.100", "av,1", "priority-array")


.. _cov-feature:

COV (Change of Value)
---------------------

Subscribe to real-time property change notifications from remote devices.
Supports both confirmed and unconfirmed notifications with configurable
lifetimes and per-subscription callbacks. See :ref:`cov-subscriptions` for
a full example.


.. _event-reporting:

Event Reporting
---------------

Intrinsic and algorithmic event detection per Clause 13. The
:class:`~bac_py.app.event_engine.EventEngine` evaluates all 18 standard event
algorithms (change-of-bitstring, change-of-state, change-of-value, out-of-range,
floating-limit, etc.) and generates event notifications routed through
:class:`~bac_py.objects.notification.NotificationClassObject` recipient lists
with day/time filtering and per-recipient confirmed/unconfirmed delivery.

- 18 event algorithms dispatched by the event engine
- Intrinsic reporting for Accumulator, Loop, and LifeSafety objects
- NotificationClass recipient list routing with calendar-aware filtering
- Alarm acknowledgment via AcknowledgeAlarm service
- GetAlarmSummary and GetEnrollmentSummary queries

See :ref:`event-notifications` for a usage example.


.. _scheduling:

Scheduling
----------

The :class:`~bac_py.app.schedule_engine.ScheduleEngine` evaluates
:class:`~bac_py.objects.schedule.ScheduleObject` instances, resolving
``Weekly_Schedule`` and ``Exception_Schedule`` entries with calendar-aware
priority to determine the effective present value at any point in time.

See :ref:`scheduling-example` for a usage example.


.. _trend-logging:

Trend Logging
-------------

The :class:`~bac_py.app.trendlog_engine.TrendLogEngine` records property
values from :class:`~bac_py.objects.trendlog.TrendLogObject` instances via
polling, COV, or triggered acquisition modes. Configurable buffer sizes and
circular buffer management.

- **Polled** -- reads the monitored property at a fixed interval
- **COV** -- registers a change-of-value callback on the monitored local object
  and records a log entry whenever the value changes (Clause 12.25.13)
- **Triggered** -- records when triggered by an external event

COV-mode trend logging uses the :class:`~bac_py.objects.base.ObjectDatabase`
change-callback infrastructure to receive property-change notifications from
local objects without polling. When a monitored property is written, the engine
creates a :class:`~bac_py.types.constructed.BACnetLogRecord` and appends it to
the trend log buffer automatically.

See :ref:`trend-logging-example` for a usage example.


.. _time-series-exchange:

Time Series Data Exchange
-------------------------

Standardized export and import of trend log data *(Annex AA)* in JSON and
CSV formats via :class:`~bac_py.encoding.time_series.TimeSeriesExporter`
and :class:`~bac_py.encoding.time_series.TimeSeriesImporter`.

.. code-block:: python

   from bac_py.encoding.time_series import TimeSeriesExporter, TimeSeriesImporter

   # Export to JSON
   json_str = TimeSeriesExporter.to_json(
       log_records,
       metadata={"object_name": "Zone Temp Log"},
       pretty=True,
   )

   # Export to CSV
   csv_str = TimeSeriesExporter.to_csv(log_records)

   # Import from JSON
   records, metadata = TimeSeriesImporter.from_json(json_str)

   # Import from CSV
   records = TimeSeriesImporter.from_csv(csv_str)

The JSON format uses the ``bacnet-time-series-v1`` schema with optional
metadata. CSV uses ISO 8601 timestamps with BACnet wildcard support
(``*`` for unspecified fields).


.. _audit-logging:

Audit Logging
-------------

Audit logging support *(new in ASHRAE 135-2020)*. The
:class:`~bac_py.app.audit.AuditManager` instruments server handlers to
automatically record write, create, and delete operations as audit log entries.
Includes audit log query and notification services for distributing audit records.

- :class:`~bac_py.objects.audit_reporter.AuditReporterObject` for generating
  audit records
- :class:`~bac_py.objects.audit_log.AuditLogObject` for storing audit records
  with buffer management
- ConfirmedAuditNotification / UnconfirmedAuditNotification services
- AuditLogQuery service for retrieving stored records

See :ref:`audit-logging-example` for a usage example.


.. _type-safety:

Type Safety
-----------

bac-py uses enums, frozen dataclasses, and type hints throughout:

- All BACnet enumerations are Python ``IntEnum`` types
  (``ObjectType``, ``PropertyIdentifier``, ``EngineeringUnits``, etc.)
- Objects are frozen dataclasses with validated fields
- The full API is type-hinted for editor autocompletion and static analysis
- ``mypy`` strict mode is used in CI


.. _json-serialization:

JSON Serialization
------------------

Optional JSON serialization for BACnet values (install with
``pip install bac-py[serialization]``, see :ref:`installation`):

.. code-block:: python

   from bac_py import serialize, deserialize

   json_str = serialize(value)
   restored = deserialize(json_str)

Uses ``orjson`` for performance when available.


.. _docker-integration-testing:

Docker Integration Testing
--------------------------

Docker-based tests exercise real BACnet/IP communication over actual UDP
sockets between separate application instances running in containers. The
infrastructure lives under ``docker/`` and uses Docker Compose with isolated
bridge networks to simulate realistic BACnet/IP topologies.

Ten scenarios are provided:

- **Client/Server** -- ReadProperty, WriteProperty, ReadPropertyMultiple,
  WritePropertyMultiple, Who-Is discovery, and object list enumeration over
  real UDP between a server and client container.
- **BBMD** -- Foreign device registration, BDT/FDT table reads, and
  cross-subnet forwarding through a BBMD container.
- **Router** -- Who-Is-Router-To-Network discovery, cross-network device
  discovery, and cross-network property reads through a router container
  bridging two Docker networks.
- **Stress** -- Mixed-workload stress testing with ReadProperty, WriteProperty,
  ReadPropertyMultiple, WritePropertyMultiple, object-list queries, and COV
  subscriptions against a server hosting 40 diverse objects. A standalone
  stress runner produces structured JSON reports with latency percentiles.
  See :ref:`benchmarks` for details.
- **Device Management** -- DeviceCommunicationControl disable/enable cycles,
  time synchronization, confirmed text messages, and private transfer
  round-trips.
- **COV Advanced** -- Concurrent COV subscriptions from multiple clients,
  property-level COV subscriptions, lifetime expiration, and confirmed vs
  unconfirmed notification delivery.
- **Events** -- Alarm reporting triggered by out-of-range writes,
  GetAlarmSummary, GetEventInformation, AcknowledgeAlarm, and
  GetEnrollmentSummary queries.
- **Secure Connect** -- BACnet/SC hub function and hub connector with TLS,
  VMAC addressing, and BVLC-SC message exchange over WebSocket connections.
- **Demo** -- Interactive demonstration of client/server capabilities
  including reads, writes, discovery, and COV subscriptions.
- **SC Stress** -- Sustained WebSocket throughput testing with varied-size
  NPDU payloads through an SC hub, measuring unicast and broadcast latency
  with echo correlation. See :ref:`benchmarks` for details.

Run with ``make docker-test`` (all scenarios) or individual targets like
``make docker-test-client``, ``make docker-test-sc``, etc.


.. _structured-logging:

Structured Logging
------------------

Every module in the stack uses Python's standard :mod:`logging` module with a
hierarchical logger namespace under ``bac_py``. This gives you fine-grained
control over diagnostics without any extra dependencies:

.. code-block:: python

   import logging

   # Enable all bac-py logging at INFO level
   logging.basicConfig(level=logging.INFO)

   # Or target specific subsystems for DEBUG
   logging.getLogger("bac_py.app.client").setLevel(logging.DEBUG)
   logging.getLogger("bac_py.transport.sc").setLevel(logging.DEBUG)

Log levels follow consistent semantics:

- **DEBUG** -- protocol detail: request/response traces, APDU types, state
  transitions, segment progress, property reads/writes
- **INFO** -- lifecycle events: application start/stop, COV subscriptions,
  object database changes, event state transitions
- **WARNING** -- recoverable issues: unknown objects, write-access-denied,
  tag validation errors, address parse failures
- **ERROR** -- handler failures with full tracebacks

Coverage spans the full stack: client, server, application engines (TSM, COV,
events, scheduling, trend logging, audit), network layer, all transports
(BIP, BBMD, Ethernet, IPv6, Secure Connect), encoding, objects, segmentation,
and serialization.

See :doc:`guide/debugging-logging` for the complete logger reference and
practical debugging recipes.


.. _architecture:

Architecture
------------

.. code-block:: text

   src/bac_py/
     app/            High-level application, client API, server handlers, TSM,
                     event engine, schedule engine, trendlog engine, audit manager
     conformance/    BIBB declarations and PICS generation
     encoding/       ASN.1/BER tag-length-value encoding and APDU codec
     network/        Addressing, NPDU network layer, multi-port router
     objects/        BACnet object model (Device, Analog, Binary, MultiState, ...)
     segmentation/   Segmented message assembly and transmission
     serialization/  JSON serialization (optional orjson backend)
     services/       Service request/response types and registry
     transport/      BACnet/IP (Annex J), BACnet/IPv6, Ethernet, BACnet/SC (Annex AB)
     types/          Primitive types, enumerations, and string parsing

See the :doc:`api/app/index` for full API documentation of each module.
