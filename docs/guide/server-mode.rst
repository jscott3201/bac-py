.. _server-mode:

Server Mode
===========

bac-py can act as a full BACnet server, exposing local objects, responding to
client requests, and running engines for scheduling, trend logging, events, and
auditing. This guide covers everything from basic setup to advanced
customization.


.. _basic-server-setup:

Basic Server Setup
------------------

Host a BACnet server that exposes local objects to the network. Server mode
uses :class:`~bac_py.app.application.BACnetApplication` and
:class:`~bac_py.app.server.DefaultServerHandlers` directly:

.. code-block:: python

   import asyncio
   from bac_py import BACnetApplication, DefaultServerHandlers, DeviceConfig, DeviceObject
   from bac_py.objects.analog import AnalogInputObject
   from bac_py.types.enums import EngineeringUnits

   async def serve():
       config = DeviceConfig(
           instance_number=100,
           name="My-Device",
           vendor_name="ACME",
           vendor_id=999,
       )

       async with BACnetApplication(config) as app:
           device = DeviceObject(
               instance_number=100,
               object_name="My-Device",
               vendor_name="ACME",
               vendor_identifier=999,
           )
           app.object_db.add(device)

           app.object_db.add(AnalogInputObject(
               instance_number=1,
               object_name="Temperature",
               units=EngineeringUnits.DEGREES_CELSIUS,
               present_value=22.5,
           ))

           handlers = DefaultServerHandlers(app, app.object_db, device)
           handlers.register()

           # Server now responds to Who-Is, ReadProperty,
           # ReadPropertyMultiple, WriteProperty, COV subscriptions,
           # and other standard services.
           await app.run()

   asyncio.run(serve())

``DefaultServerHandlers.register()`` installs handlers for all standard
BACnet server services. The server will respond to Who-Is with I-Am,
ReadProperty and ReadPropertyMultiple with values from the object database,
and WriteProperty/WritePropertyMultiple to update writable objects. See
:ref:`object-model` for the full list of supported object types.


.. _server-device-config:

DeviceConfig Options
^^^^^^^^^^^^^^^^^^^^

:class:`~bac_py.app.application.DeviceConfig` controls device identity,
network parameters, and security:

.. code-block:: python

   from bac_py import DeviceConfig
   from bac_py.app.application import RouterConfig, RouterPortConfig

   config = DeviceConfig(
       instance_number=100,           # BACnet device instance (0-4194302)
       name="My-Device",              # Device name
       vendor_name="ACME",            # Vendor string
       vendor_id=999,                 # ASHRAE vendor ID
       model_name="Controller-1",     # Model name
       firmware_revision="2.0.0",     # Firmware version (default: bac-py version)
       application_software_version="1.0.0",  # Software version (default: bac-py version)
       interface="0.0.0.0",           # IP address to bind
       port=0xBAC0,                   # UDP port (47808)
       max_apdu_length=1476,          # Max APDU size (bytes)
       max_segments=None,             # Max segments (None = unlimited)
       apdu_timeout=6000,             # Request timeout (ms)
       apdu_segment_timeout=2000,     # Segment timeout (ms)
       apdu_retries=3,                # Retry count
       broadcast_address="255.255.255.255",  # Directed broadcast address
       password="secret123",          # Optional password for DCC/ReinitializeDevice
       router_config=None,            # Multi-network router (see below)
   )

The ``password`` field (1--20 characters) is used by the
DeviceCommunicationControl and ReinitializeDevice handlers. When set, incoming
requests must include a matching password or the server responds with a
``PASSWORD_FAILURE`` error. The comparison uses ``hmac.compare_digest()`` for
constant-time security.

The ``broadcast_address`` defaults to ``"255.255.255.255"`` (global broadcast).
Override it for subnet-directed broadcasts in Docker or segmented networks
(e.g. ``"192.168.1.255"``).

See :ref:`multi-network-routing` for ``router_config`` details.


.. _object-database:

Object Database
---------------

The :class:`~bac_py.objects.base.ObjectDatabase` is the runtime registry for
all BACnet objects hosted by the server.

Adding and removing objects
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject
   from bac_py.objects.binary import BinaryInputObject
   from bac_py.types.enums import EngineeringUnits, ObjectType
   from bac_py.types.primitives import ObjectIdentifier

   # Add objects
   ai = AnalogInputObject(
       instance_number=1,
       object_name="Zone-Temp",
       units=EngineeringUnits.DEGREES_CELSIUS,
       present_value=22.5,
   )
   app.object_db.add(ai)

   # Object names must be unique (Clause 12.1.5)
   # Duplicate names or IDs raise BACnetError

   # Remove an object
   app.object_db.remove(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
   # Note: Device objects cannot be removed

Querying objects
^^^^^^^^^^^^^^^^

.. code-block:: python

   # Look up by identifier
   obj = app.object_db.get(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))

   # All objects of a type
   all_ai = app.object_db.get_objects_of_type(ObjectType.ANALOG_INPUT)

   # Full object list (auto-computed)
   obj_list = app.object_db.object_list

   # Iterate all objects
   for obj in app.object_db:
       print(obj.object_identifier, obj.read_property(PropertyIdentifier.OBJECT_NAME))

   # Count and membership
   count = len(app.object_db)
   exists = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1) in app.object_db

The ``Object_List`` property on the Device object is automatically computed
from the database contents. Adding or removing objects increments the
``Database_Revision`` property.

Change callbacks
^^^^^^^^^^^^^^^^

Register callbacks to be notified when a property value is written:

.. code-block:: python

   from bac_py.types.enums import PropertyIdentifier

   def on_temp_change(prop_id, old_value, new_value):
       print(f"Temperature changed: {old_value} -> {new_value}")

   app.object_db.register_change_callback(
       ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
       PropertyIdentifier.PRESENT_VALUE,
       on_temp_change,
   )

   # Later, to stop receiving callbacks:
   app.object_db.unregister_change_callback(
       ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
       PropertyIdentifier.PRESENT_VALUE,
       on_temp_change,
   )

Change callbacks power both COV-based trend logging and the event engine's
intrinsic reporting.


.. _supported-object-types:

Supported Object Types
----------------------

bac-py includes 40+ object types covering the full BACnet standard:

**Sensing:** AnalogInput, BinaryInput, MultiStateInput

**Control (commandable):** AnalogOutput, BinaryOutput, MultiStateOutput

**Values:** AnalogValue, BinaryValue, MultiStateValue

**Extended values:** IntegerValue, PositiveIntegerValue, LargeAnalogValue,
CharacterStringValue, OctetStringValue, BitStringValue, DateValue, TimeValue,
DateTimeValue, DatePatternValue, TimePatternValue, DateTimePatternValue

**Infrastructure:** Device, File, NetworkPort, Channel

**Scheduling:** Schedule, Calendar

**Trending:** TrendLog, TrendLogMultiple

**Events:** EventEnrollment, NotificationClass, EventLog, AlertEnrollment,
NotificationForwarder

**Safety:** LifeSafetyPoint, LifeSafetyZone

**Auditing:** AuditReporter, AuditLog

**Access control:** AccessDoor, AccessPoint, AccessZone, AccessUser,
AccessRights, AccessCredential, CredentialDataInput

**Advanced control:** Command, Timer, Staging, LoadControl, Loop,
PulseConverter, Accumulator

**Lighting:** LightingOutput, BinaryLightingOutput

**Transportation:** ElevatorGroup, Lift, Escalator

**Other:** Program, Averaging, Group, GlobalGroup, StructuredView

All objects are created as frozen dataclasses with validated property
definitions and read/write access control.


.. _commandable-objects:

Commandable Objects and Priority Arrays
----------------------------------------

BACnet commandable objects support a 16-level command priority array
(Clause 19.2). When multiple sources write to the same object, the highest
priority (lowest number) wins.

Always-commandable objects
^^^^^^^^^^^^^^^^^^^^^^^^^^

AnalogOutput, BinaryOutput, and MultiStateOutput are always commandable:

.. code-block:: python

   from bac_py.objects.analog import AnalogOutputObject
   from bac_py.types.enums import EngineeringUnits

   ao = AnalogOutputObject(
       instance_number=1,
       object_name="Damper-Position",
       units=EngineeringUnits.PERCENT,
       relinquish_default=0.0,
   )
   app.object_db.add(ao)

   # Write at priority 8 (manual operator)
   ao.write_property(PropertyIdentifier.PRESENT_VALUE, 75.0, priority=8)

   # The present value is now 75.0 (priority 8 is the highest active slot)

   # Write at priority 1 (life safety -- overrides priority 8)
   ao.write_property(PropertyIdentifier.PRESENT_VALUE, 100.0, priority=1)
   # Present value is now 100.0

   # Relinquish priority 1
   ao.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=1)
   # Present value falls back to 75.0 (priority 8)

   # Relinquish priority 8
   ao.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
   # All slots empty -- present value falls back to relinquish_default (0.0)

Optionally-commandable objects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

IntegerValue and PositiveIntegerValue support an optional ``commandable``
flag:

.. code-block:: python

   from bac_py.objects.value_types import IntegerValueObject

   iv = IntegerValueObject(
       instance_number=1,
       object_name="Setpoint-Mode",
       commandable=True,
       relinquish_default=0,
   )

When ``commandable=True``, the object gets a full 16-level priority array,
``Relinquish_Default``, ``Current_Command_Priority``, and value source tracking.
When ``commandable=False`` (the default), writes go directly to
``Present_Value`` without priority handling.


.. _cov-server-side:

COV Subscriptions (Server Side)
-------------------------------

The server's COV manager (:class:`~bac_py.app.cov.COVManager`) handles
incoming SubscribeCOV, SubscribeCOVProperty, and SubscribeCOVPropertyMultiple
requests automatically when ``DefaultServerHandlers`` is registered.

How it works
^^^^^^^^^^^^

1. A remote client sends a SubscribeCOV request for an object
2. The server registers the subscription with a lifetime timer
3. An initial notification is sent immediately (Clause 13.1.2)
4. On each property write, the server checks if the value change exceeds the
   COV threshold and sends notifications to all matching subscribers

**Notification thresholds:**

- **Analog objects:** Notify when ``|new - last| >= COV_Increment``, or on any
  change if no increment is set
- **Binary/multistate objects:** Notify on any change in ``Present_Value``
- **All objects:** Notify on any change in ``Status_Flags``

**Subscription types:**

- **Object-level** (SubscribeCOV): Monitors ``Present_Value`` and
  ``Status_Flags``
- **Property-level** (SubscribeCOVProperty): Monitors a specific property with
  optional per-subscription COV increment override
- **Property-multiple** (SubscribeCOVPropertyMultiple): Multiple property-level
  subscriptions in a single request

**Lifetime management:**

- Subscriptions with a ``lifetime`` (in seconds) expire automatically
- Subscriptions without a lifetime persist indefinitely
- Clients can cancel subscriptions or re-subscribe to refresh the lifetime

The COV manager is created automatically during application startup and
shut down during application stop. No additional configuration is needed
beyond registering ``DefaultServerHandlers``.

Inspecting active subscriptions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # List all active subscriptions
   subs = app.cov_manager.get_active_subscriptions()

   # Filter by object
   subs = app.cov_manager.get_active_subscriptions(
       ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
   )

   for sub in subs:
       print(f"Subscriber: {sub.subscriber}, Object: {sub.monitored_object}, "
             f"Confirmed: {sub.confirmed}, Lifetime: {sub.lifetime}")


.. _custom-service-handlers:

Custom Service Handlers
-----------------------

The :class:`~bac_py.services.registry.ServiceRegistry` dispatches incoming
requests to registered handler functions. ``DefaultServerHandlers`` registers
handlers for all standard services, but you can replace or extend them.

Handler signature
^^^^^^^^^^^^^^^^^

**Confirmed service handlers** receive the raw request bytes and return
response bytes (for ComplexACK) or ``None`` (for SimpleACK):

.. code-block:: python

   async def my_handler(
       service_choice: int,
       request_data: bytes,
       source: BACnetAddress,
   ) -> bytes | None:
       # Decode request_data, process, return response or None
       ...

**Unconfirmed service handlers** process the request without returning a
response:

.. code-block:: python

   async def my_unconfirmed_handler(
       service_choice: int,
       request_data: bytes,
       source: BACnetAddress,
   ) -> None:
       # Decode and process, no response needed
       ...

Registering custom handlers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from bac_py.types.enums import ConfirmedServiceChoice, UnconfirmedServiceChoice

   # Override a standard handler
   app.service_registry.register_confirmed(
       ConfirmedServiceChoice.CONFIRMED_PRIVATE_TRANSFER,
       my_private_transfer_handler,
   )

   # Register an unconfirmed handler
   app.service_registry.register_unconfirmed(
       UnconfirmedServiceChoice.UNCONFIRMED_PRIVATE_TRANSFER,
       my_unconfirmed_handler,
   )

Custom validation example
^^^^^^^^^^^^^^^^^^^^^^^^^^

Add a write-access filter that restricts writes to a whitelist of source
addresses:

.. code-block:: python

   from bac_py.services.errors import BACnetError
   from bac_py.services.property_access import WritePropertyRequest
   from bac_py.types.enums import ErrorClass, ErrorCode

   ALLOWED_WRITERS = {"192.168.1.10", "192.168.1.20"}

   async def restricted_write_handler(service_choice, data, source):
       if str(source) not in ALLOWED_WRITERS:
           raise BACnetError(ErrorClass.SECURITY, ErrorCode.WRITE_ACCESS_DENIED)
       # Fall through to default handling
       return await default_handlers.handle_write_property(service_choice, data, source)

   app.service_registry.register_confirmed(
       ConfirmedServiceChoice.WRITE_PROPERTY,
       restricted_write_handler,
   )

Error responses
^^^^^^^^^^^^^^^

Handlers signal errors by raising exceptions:

.. code-block:: python

   from bac_py.services.errors import (
       BACnetError,         # -> Error-PDU (error_class, error_code)
       BACnetRejectError,   # -> Reject-PDU (reason)
       BACnetAbortError,    # -> Abort-PDU (reason)
   )

   # Property not found
   raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

   # Malformed request
   raise BACnetRejectError(RejectReason.MISSING_REQUIRED_PARAMETER)

If no handler is registered for a confirmed service, the application
automatically sends a Reject-PDU with ``UNRECOGNIZED_SERVICE``. Unregistered
unconfirmed services are silently ignored per Clause 5.4.2.


.. _server-event-engine:

Event Engine
------------

The :class:`~bac_py.app.event_engine.EventEngine` evaluates all 18 standard
BACnet event algorithms and generates event notifications routed through
NotificationClass recipient lists.

Starting the event engine
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from bac_py.app.event_engine import EventEngine
   from bac_py.objects.analog import AnalogInputObject
   from bac_py.objects.notification import NotificationClassObject
   from bac_py.types.enums import EngineeringUnits, EventType, NotifyType

   async def serve_with_events():
       config = DeviceConfig(instance_number=100, name="My-Device",
                             vendor_name="ACME", vendor_id=999)

       async with BACnetApplication(config) as app:
           # ... add device object and register handlers ...

           # Notification class for routing alarm notifications
           app.object_db.add(NotificationClassObject(
               instance_number=1,
               object_name="Critical-Alarms",
               notification_class=1,
               priority=[3, 3, 3],  # [to_offnormal, to_fault, to_normal]
           ))

           # Analog input with intrinsic out-of-range reporting
           app.object_db.add(AnalogInputObject(
               instance_number=1,
               object_name="Zone-Temp",
               units=EngineeringUnits.DEGREES_CELSIUS,
               present_value=22.5,
               high_limit=30.0,
               low_limit=15.0,
               deadband=1.0,
               notification_class=1,
               event_enable=[True, True, True],
               notify_type=NotifyType.ALARM,
           ))

           engine = EventEngine(app, scan_interval=1.0)
           await engine.start()

           try:
               await app.run()
           finally:
               await engine.stop()

Supported algorithms
^^^^^^^^^^^^^^^^^^^^

The engine evaluates these event types automatically based on object
configuration:

- CHANGE_OF_BITSTRING
- CHANGE_OF_STATE
- CHANGE_OF_VALUE
- COMMAND_FAILURE
- FLOATING_LIMIT
- OUT_OF_RANGE
- CHANGE_OF_LIFE_SAFETY
- EXTENDED
- BUFFER_READY
- UNSIGNED_RANGE
- ACCESS_EVENT
- DOUBLE_OUT_OF_RANGE
- SIGNED_OUT_OF_RANGE
- UNSIGNED_OUT_OF_RANGE
- CHANGE_OF_CHARACTERSTRING
- CHANGE_OF_STATUS_FLAGS
- CHANGE_OF_RELIABILITY
- CHANGE_OF_DISCRETE_VALUE

Intrinsic reporting
^^^^^^^^^^^^^^^^^^^

Objects that define ``INTRINSIC_EVENT_ALGORITHM`` (AnalogInput, BinaryInput,
AnalogValue, etc.) automatically participate in event evaluation when their
``Event_Enable`` property has at least one transition enabled and a valid
``Notification_Class`` is assigned.

Algorithmic reporting
^^^^^^^^^^^^^^^^^^^^^

For custom event detection, create an
:class:`~bac_py.objects.event_enrollment.EventEnrollmentObject` that
references the monitored object and specifies the algorithm parameters:

.. code-block:: python

   from bac_py.objects.event_enrollment import EventEnrollmentObject
   from bac_py.types.enums import EventType, EventState

   app.object_db.add(EventEnrollmentObject(
       instance_number=1,
       object_name="Temp-Out-Of-Range",
       event_type=EventType.OUT_OF_RANGE,
       notify_type=NotifyType.ALARM,
       notification_class=1,
       event_enable=[True, True, True],
   ))

The engine routes notifications through
:class:`~bac_py.objects.notification.NotificationClassObject` recipient lists
with day/time filtering and per-recipient confirmed/unconfirmed delivery.
See :ref:`event-notifications` for client-side event handling.


.. _server-audit-logging:

Audit Logging (Server Side)
----------------------------

The :class:`~bac_py.app.audit.AuditManager` instruments server handlers to
automatically record write, create, and delete operations as audit log entries
(new in ASHRAE 135-2020).

Setting up audit logging
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from bac_py.app.audit import AuditManager
   from bac_py.objects.audit_reporter import AuditReporterObject
   from bac_py.objects.audit_log import AuditLogObject

   # Create an audit reporter that monitors all objects
   app.object_db.add(AuditReporterObject(
       instance_number=1,
       object_name="System-Auditor",
   ))

   # Create an audit log buffer
   app.object_db.add(AuditLogObject(
       instance_number=1,
       object_name="System-Audit-Log",
       buffer_size=1000,
   ))

   # The AuditManager is created in BACnetApplication and
   # is invoked automatically by DefaultServerHandlers
   # on write_property, create_object, and delete_object.

**Key AuditReporter properties:**

- ``monitored_objects``: List of ObjectIdentifiers to audit (empty = all)
- ``audit_level``: Filtering level (NONE, DEFAULT, AUDIT_CONFIG)
- ``auditable_operations``: BitString filter for operation types

**Key AuditLog properties:**

- ``buffer_size``: Maximum records before circular overwrite (default 100)
- ``stop_when_full``: If True, stop logging when buffer is full
- ``log_enable``: Enable/disable logging
- ``record_count``: Current records in buffer
- ``total_record_count``: Monotonically increasing sequence number

See :ref:`audit-logging-example` for client-side audit queries.


.. _server-error-handling:

Error Handling
--------------

Server handlers use a consistent error hierarchy:

.. code-block:: python

   from bac_py.services.errors import (
       BACnetError,        # Error-PDU (error_class, error_code)
       BACnetRejectError,  # Reject-PDU (reason)
       BACnetAbortError,   # Abort-PDU (reason)
   )

Common server-side error responses:

.. list-table::
   :header-rows: 1
   :widths: 35 35 30

   * - Situation
     - Exception
     - Clause
   * - Unknown object
     - ``BACnetError(OBJECT, UNKNOWN_OBJECT)``
     - 12.1
   * - Unknown property
     - ``BACnetError(PROPERTY, UNKNOWN_PROPERTY)``
     - 12.1
   * - Write to read-only property
     - ``BACnetError(PROPERTY, WRITE_ACCESS_DENIED)``
     - 15.9
   * - Wrong password
     - ``BACnetError(SECURITY, PASSWORD_FAILURE)``
     - 16.1
   * - DCC disabled
     - ``BACnetRejectError(OTHER)``
     - 16.1
   * - Missing parameter
     - ``BACnetRejectError(MISSING_REQUIRED_PARAMETER)``
     - 5.4
   * - Value out of range
     - ``BACnetError(PROPERTY, VALUE_OUT_OF_RANGE)``
     - 15.9

Password validation
^^^^^^^^^^^^^^^^^^^

When ``DeviceConfig.password`` is set, the DeviceCommunicationControl and
ReinitializeDevice handlers validate the password using constant-time
comparison (``hmac.compare_digest()``). Requests with a missing or incorrect
password receive a ``PASSWORD_FAILURE`` error.

DeviceCommunicationControl states
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The DCC handler supports three states:

- **ENABLE**: Normal operation (default)
- **DISABLE**: Only DeviceCommunicationControl and ReinitializeDevice requests
  are processed; all other confirmed services are rejected
- **DISABLE_INITIATION**: The server suppresses outbound unsolicited messages
  but still responds to incoming requests

An optional ``time_duration`` (minutes) automatically re-enables the device
after the specified period.


.. _application-lifecycle:

Application Lifecycle
---------------------

:class:`~bac_py.app.application.BACnetApplication` manages the full lifecycle
of transport, network layer, TSM, COV manager, and engines.

Async context manager (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   async with BACnetApplication(config) as app:
       # app.start() called automatically
       handlers = DefaultServerHandlers(app, app.object_db, device)
       handlers.register()
       await app.run()
       # app.stop() called automatically on exit

Manual lifecycle
^^^^^^^^^^^^^^^^

.. code-block:: python

   app = BACnetApplication(config)
   await app.start()  # Bind socket, start transport/network
   try:
       handlers = DefaultServerHandlers(app, app.object_db, device)
       handlers.register()
       await app.run()
   finally:
       await app.stop()  # Idempotent, safe to call multiple times

Combined client and server
^^^^^^^^^^^^^^^^^^^^^^^^^^

A single application can act as both client and server simultaneously:

.. code-block:: python

   from bac_py.app.client import BACnetClient

   async with BACnetApplication(config) as app:
       device = DeviceObject(instance_number=100, object_name="My-Device",
                             vendor_name="ACME", vendor_identifier=999)
       app.object_db.add(device)

       # Server side
       handlers = DefaultServerHandlers(app, app.object_db, device)
       handlers.register()

       # Client side
       bc = BACnetClient(app)
       value = await bc.read("192.168.1.200", "ai,1", "pv")

       await app.run()

Auto-computed properties
^^^^^^^^^^^^^^^^^^^^^^^^

When ``DefaultServerHandlers.register()`` is called, it automatically
computes and sets:

- ``Protocol_Services_Supported``: BitString reflecting all registered
  service handlers
- ``Protocol_Object_Types_Supported``: BitString for all object types
  supported by the library


.. _scheduling-example:

Scheduling
----------

Create a Schedule object with weekly time-value pairs and run the
:class:`~bac_py.app.schedule_engine.ScheduleEngine` to evaluate it:

.. code-block:: python

   import asyncio
   from bac_py.app.application import BACnetApplication, DeviceConfig
   from bac_py.app.schedule_engine import ScheduleEngine
   from bac_py.objects.schedule import ScheduleObject
   from bac_py.types.constructed import BACnetTimeValue
   from bac_py.types.primitives import BACnetTime

   async def serve_with_schedule():
       config = DeviceConfig(instance_number=100, name="My-Device",
                             vendor_name="ACME", vendor_id=999)

       async with BACnetApplication(config) as app:
           # ... add device and other objects ...

           # Occupied/unoccupied schedule (Mon-Fri 8am-6pm = 1, else = 0)
           weekday_entries = [
               BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=1),
               BACnetTimeValue(time=BACnetTime(18, 0, 0, 0), value=0),
           ]
           app.object_db.add(ScheduleObject(
               instance_number=1,
               object_name="Occupancy-Schedule",
               weekly_schedule=[
                   weekday_entries,  # Monday
                   weekday_entries,  # Tuesday
                   weekday_entries,  # Wednesday
                   weekday_entries,  # Thursday
                   weekday_entries,  # Friday
                   [],               # Saturday
                   [],               # Sunday
               ],
               schedule_default=0,
           ))

           # Start the schedule engine
           engine = ScheduleEngine(app, scan_interval=10.0)
           await engine.start()

           try:
               await app.run()
           finally:
               await engine.stop()

   asyncio.run(serve_with_schedule())


.. _trend-logging-example:

Trend Logging
-------------

Create a TrendLog object that records AnalogInput present-value readings
using the :class:`~bac_py.app.trendlog_engine.TrendLogEngine`:

.. code-block:: python

   import asyncio
   from bac_py.app.application import BACnetApplication, DeviceConfig
   from bac_py.app.trendlog_engine import TrendLogEngine
   from bac_py.objects.trendlog import TrendLogObject
   from bac_py.types.enums import LoggingType, ObjectType, PropertyIdentifier
   from bac_py.types.primitives import ObjectIdentifier

   async def serve_with_trendlog():
       config = DeviceConfig(instance_number=100, name="My-Device",
                             vendor_name="ACME", vendor_id=999)

       async with BACnetApplication(config) as app:
           # ... add device and AnalogInput objects ...

           # Log ai,1 present-value every 60 seconds (polled mode)
           app.object_db.add(TrendLogObject(
               instance_number=1,
               object_name="Zone-Temp-Log",
               log_device_object_property=ObjectIdentifier(
                   ObjectType.ANALOG_INPUT, 1),
               logging_type=LoggingType.POLLED,
               log_interval=60,  # seconds
               buffer_size=1000,
           ))

           engine = TrendLogEngine(app, scan_interval=1.0)
           await engine.start()

           try:
               await app.run()
           finally:
               await engine.stop()

   asyncio.run(serve_with_trendlog())


COV-based trend logging
^^^^^^^^^^^^^^^^^^^^^^^^

For change-of-value recording (Clause 12.25.13), set ``logging_type`` to
``LoggingType.COV``. The engine registers a change callback on the monitored
local object and records a log entry whenever the value is written:

.. code-block:: python

   # Log ai,1 present-value on every change (COV mode)
   app.object_db.add(TrendLogObject(
       instance_number=2,
       object_name="Zone-Temp-COV-Log",
       log_device_object_property=ObjectIdentifier(
           ObjectType.ANALOG_INPUT, 1),
       logging_type=LoggingType.COV,
       buffer_size=1000,
   ))

COV-mode trend logs do not poll. They only record when the monitored
property is actually written, which can be more efficient for slowly
changing values.


.. _registered-services:

Registered Services
-------------------

``DefaultServerHandlers.register()`` installs handlers for the following
services:

**Confirmed services:**

- ReadProperty, WriteProperty
- ReadPropertyMultiple, WritePropertyMultiple
- ReadRange
- SubscribeCOV, SubscribeCOVProperty, SubscribeCOVPropertyMultiple
- ConfirmedCOVNotificationMultiple
- DeviceCommunicationControl, ReinitializeDevice
- AtomicReadFile, AtomicWriteFile
- CreateObject, DeleteObject
- AddListElement, RemoveListElement
- AcknowledgeAlarm, ConfirmedEventNotification
- GetAlarmSummary, GetEnrollmentSummary, GetEventInformation
- ConfirmedTextMessage
- VT-Open, VT-Close, VT-Data
- AuditLogQuery, ConfirmedAuditNotification
- ConfirmedPrivateTransfer

**Unconfirmed services:**

- Who-Is, Who-Has
- TimeSynchronization, UTCTimeSynchronization
- UnconfirmedCOVNotificationMultiple
- UnconfirmedEventNotification
- UnconfirmedTextMessage
- WriteGroup
- Who-Am-I, You-Are
- UnconfirmedAuditNotification
