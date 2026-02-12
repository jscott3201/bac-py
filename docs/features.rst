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
common operations. See :doc:`getting-started` for a walkthrough.

- **String-based addressing** -- pass IP addresses as strings instead of
  constructing :class:`~bac_py.network.address.BACnetAddress` objects
  (see :ref:`addressing`)
- **String object/property identifiers** -- use ``"ai,1"`` and ``"pv"``
  instead of ``ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)`` and
  ``PropertyIdentifier.PRESENT_VALUE``
- **Short aliases** -- ``ai``, ``ao``, ``av``, ``bi``, ``bo``, ``bv``,
  ``msi``, ``mso``, ``msv``, ``dev`` for object types; ``pv``, ``name``,
  ``desc``, ``units``, ``status``, ``oos``, ``cov-inc``, ``reliability``
  for properties (see :ref:`string-aliases` for the full table)
- **Auto-decoding on read** -- raw BACnet tags are decoded to Python values
  automatically
- **Auto-encoding on write** -- Python types are encoded to the correct BACnet
  application tag based on the value type, target object type, and property
  (see :ref:`smart-encoding`)
- **Async context manager** -- ``async with Client(...) as client:`` handles
  startup and shutdown
- **Alarm management** -- ``get_alarm_summary()``, ``get_event_information()``,
  ``acknowledge_alarm()`` with string arguments
- **Extended discovery** -- ``discover_extended()`` enriches Who-Is results
  with Annex X profile metadata
- **Text messaging** -- ``send_text_message()`` with confirmed/unconfirmed mode
- **Backup/restore** -- ``backup()`` and ``restore()`` handle the full
  Clause 19.1 procedure
- **Audit log queries** -- ``query_audit_log()`` with string addressing
- **Property-level COV** -- ``subscribe_cov_property()`` for monitoring
  specific properties
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
- SubscribeCOV
- ConfirmedEventNotification
- GetAlarmSummary / GetEnrollmentSummary
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
- UnconfirmedCOVNotification
- UnconfirmedEventNotification
- UnconfirmedTextMessage
- UnconfirmedAuditNotification *(new in 2020)*
- Who-Am-I / You-Are *(new in 2020)*
- WriteGroup
- UnconfirmedPrivateTransfer

See :ref:`reading-properties`, :ref:`writing-properties`,
:ref:`device-discovery`, and :ref:`cov-subscriptions` for usage examples.


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
properties are writable. See :ref:`serving-objects` for an example of
creating and hosting objects.


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
between multiple BACnet/IP networks with dynamic routing tables. See
:ref:`multi-network-routing` for configuration and :ref:`router-discovery`
for discovering existing routers on the network.

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
:meth:`~bac_py.app.client.BACnetClient.traverse_hierarchy` reads
``Subordinate_List`` from Structured View objects and recursively descends
to collect all object identifiers in a device's object hierarchy:

.. code-block:: python

   from bac_py.types.primitives import ObjectIdentifier
   from bac_py.types.enums import ObjectType

   root = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
   all_objects = await client.traverse_hierarchy(device_addr, root)


.. _bacnet-ipv6:

BACnet/IPv6
-----------

Full BACnet/IPv6 transport per ASHRAE 135-2020 Annex U:

- **IPv6 BVLL** with all 13 function codes (type ``0x82``)
- **3-byte VMAC** virtual addressing with automatic address resolution
- **IPv6 multicast** broadcasts (``ff02::bac0`` link-local, ``ff05::bac0`` site-local)
- **Address resolution** protocol with TTL-based caching
- Foreign device registration over IPv6

.. code-block:: python

   from bac_py.transport.bip6 import BIP6Transport

   transport = BIP6Transport(interface="::", port=0xBAC0)
   await transport.start()


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

Four scenarios are provided:

- **Client/Server** -- ReadProperty, WriteProperty, ReadPropertyMultiple,
  WritePropertyMultiple, Who-Is discovery, and object list enumeration over
  real UDP between a server and client container.
- **BBMD** -- Foreign device registration, BDT/FDT table reads, and
  cross-subnet forwarding through a BBMD container.
- **Router** -- Who-Is-Router-To-Network discovery, cross-network device
  discovery, and cross-network property reads through a router container
  bridging two Docker networks.
- **Stress** -- Concurrent client reads (10 parallel clients) and rapid
  sequential reads (100 in a row) for throughput validation. A standalone
  stress runner produces structured JSON reports with latency percentiles.

Run with ``make docker-test`` (all scenarios) or individual targets like
``make docker-test-client``. See :ref:`docker-testing-example` for details.


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
     transport/      BACnet/IP (Annex J) UDP transport, BVLL, BBMD
     types/          Primitive types, enumerations, and string parsing

See the :doc:`api/index` for full API documentation of each module.
