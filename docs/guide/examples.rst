.. _examples-guide:

Example Scripts
===============

The ``examples/`` directory contains 17 runnable scripts demonstrating bac-py's
capabilities. Each script is self-contained and uses the high-level
:class:`~bac_py.client.Client` API with ``asyncio.run()``.

Run any example by replacing the address and object identifiers with values
from your network:

.. code-block:: bash

   uv run python examples/read_value.py

All examples follow the same structure:

.. code-block:: python

   import asyncio
   from bac_py import Client

   async def main():
       async with Client(instance_number=999) as client:
           # ... operations ...

   asyncio.run(main())


.. _examples-reading-writing:

Reading and Writing
-------------------

read_value.py
^^^^^^^^^^^^^

Read a single property from a BACnet device. Demonstrates short aliases
(``"ai,1"``, ``"pv"``), full names (``"analog-input,1"``, ``"object-name"``),
and array element access via the ``array_index`` parameter.

.. code-block:: python

   value = await client.read("192.168.1.100", "ai,1", "pv")
   name = await client.read("192.168.1.100", "analog-input,1", "object-name")
   slot = await client.read("192.168.1.100", "av,1", "priority-array", array_index=8)

See :ref:`string-aliases` for the full alias table.


write_value.py
^^^^^^^^^^^^^^

Write property values with automatic type encoding. Floats become Real, ints
are encoded based on the target object/property type, and ``None`` relinquishes
a command priority.

.. code-block:: python

   # Float to analog -> Real
   await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)

   # Int to binary -> Enumerated
   await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)

   # Relinquish a priority
   await client.write("192.168.1.100", "av,1", "pv", None, priority=8)

See the :ref:`encoding rules table <encoding-rules>` for details.


read_multiple.py
^^^^^^^^^^^^^^^^

Read multiple properties from multiple objects in a single
``ReadPropertyMultiple`` request:

.. code-block:: python

   results = await client.read_multiple("192.168.1.100", {
       "ai,1": ["pv", "object-name", "units"],
       "ai,2": ["pv", "object-name"],
       "av,1": ["pv", "priority-array"],
   })


write_multiple.py
^^^^^^^^^^^^^^^^^

Write multiple properties to multiple objects in a single
``WritePropertyMultiple`` request, then verify with a read-back:

.. code-block:: python

   await client.write_multiple("192.168.1.100", {
       "av,1": {"pv": 72.5, "object-name": "Zone Temp SP"},
       "av,2": {"pv": 55.0},
   })

   # Verify
   results = await client.read_multiple("192.168.1.100", {
       "av,1": ["pv", "object-name"],
       "av,2": ["pv"],
   })


.. _examples-discovery:

Discovery
---------

discover_devices.py
^^^^^^^^^^^^^^^^^^^

Discover all BACnet devices on the network via Who-Is broadcast. Returns
:class:`~bac_py.app.client.DiscoveredDevice` objects with address, instance,
vendor ID, max APDU length, and segmentation support. Supports instance range
filtering.

.. code-block:: python

   devices = await client.discover(timeout=3.0)
   for dev in devices:
       print(f"  {dev.instance}  {dev.address_str}  vendor={dev.vendor_id}")

   # Filter by instance range
   devices = await client.discover(low_limit=100, high_limit=200, timeout=3.0)


extended_discovery.py
^^^^^^^^^^^^^^^^^^^^^

Enriches standard Who-Is discovery with Annex X profile metadata
(``Profile_Name``, ``Profile_Location``, ``Tags``) via
``ReadPropertyMultiple``:

.. code-block:: python

   devices = await client.discover_extended(timeout=3.0, enrich_timeout=5.0)
   for dev in devices:
       print(f"  {dev.instance}: profile={dev.profile_name}")
       if dev.tags:
           print(f"    tags: {dev.tags}")


advanced_discovery.py
^^^^^^^^^^^^^^^^^^^^^

Demonstrates three advanced discovery techniques beyond basic Who-Is:

- **Who-Has** -- find devices containing a specific object by name or
  identifier:

  .. code-block:: python

     results = await client.who_has(object_name="Zone Temp", timeout=3.0)
     results = await client.who_has(object_identifier="ai,1", timeout=3.0)

- **Unconfigured device discovery** -- find new devices that have not yet been
  assigned an instance number (Clause 19.7 Who-Am-I):

  .. code-block:: python

     unconfigured = await client.discover_unconfigured(timeout=5.0)
     for dev in unconfigured:
         print(f"  Vendor: {dev.vendor_id}  Serial: {dev.serial_number}")

- **Hierarchy traversal** -- walk Structured View object trees to collect all
  object identifiers:

  .. code-block:: python

     objects = await client.traverse_hierarchy("192.168.1.100", "structured-view,1")


router_discovery.py
^^^^^^^^^^^^^^^^^^^

Discover BACnet routers and the remote networks they can reach, then discover
devices on those remote networks:

.. code-block:: python

   routers = await client.who_is_router_to_network(timeout=3.0)
   for router in routers:
       print(f"  Router at {router.address}: networks={router.networks}")

   # Discover devices on a remote network through a router
   devices = await client.discover(destination=f"{remote_net}:*", timeout=5.0)


foreign_device.py
^^^^^^^^^^^^^^^^^

Register as a foreign device with a BBMD to communicate across subnets.
Demonstrates discovery on the BBMD's network and reading BDT/FDT tables:

.. code-block:: python

   async with Client(
       instance_number=999,
       bbmd_address="192.168.1.1",
       bbmd_ttl=60,
   ) as client:
       print(f"Status: {client.foreign_device_status}")

       devices = await client.discover(timeout=5.0)

       bdt = await client.read_bdt("192.168.1.1")
       fdt = await client.read_fdt("192.168.1.1")


.. _examples-cov:

COV Subscriptions
-----------------

monitor_cov.py
^^^^^^^^^^^^^^

Subscribe to object-level COV (Change of Value) notifications with a callback.
The device sends notifications whenever the object's default COV properties
change:

.. code-block:: python

   from bac_py import decode_cov_values

   def on_notification(notification, source):
       values = decode_cov_values(notification)
       for name, value in values.items():
           print(f"  {name}: {value}")

   await client.subscribe_cov_ex(
       "192.168.1.100", "ai,1",
       process_id=1,
       callback=on_notification,
       confirmed=True,
       lifetime=3600,
   )

   await asyncio.sleep(60)
   await client.unsubscribe_cov_ex("192.168.1.100", "ai,1", process_id=1)


cov_property.py
^^^^^^^^^^^^^^^

Subscribe to property-level COV on a specific property with a custom COV
increment (notification threshold). Contrast with ``monitor_cov.py`` which
uses object-level subscriptions:

.. code-block:: python

   # Register a process-ID callback for property-level COV
   client.app.register_cov_callback(42, on_notification)

   await client.subscribe_cov_property(
       "192.168.1.100", "ai,1", "pv",
       process_id=42,
       cov_increment=0.5,   # notify when value changes by >= 0.5
       lifetime=3600,
   )


.. _examples-events-alarms:

Events and Alarms
-----------------

alarm_management.py
^^^^^^^^^^^^^^^^^^^

Comprehensive alarm management: query active alarms, list event-generating
objects, check event state details with pagination, and acknowledge alarms:

.. code-block:: python

   # Active alarms
   summary = await client.get_alarm_summary(addr)

   # Enrollment summaries (all event-generating objects)
   enrollment = await client.get_enrollment_summary(
       addr, acknowledgment_filter=AcknowledgmentFilter.ALL,
   )

   # Event information with pagination
   event_info = await client.get_event_information(addr)
   while event_info.more_events:
       last = event_info.list_of_event_summaries[-1].object_identifier
       event_info = await client.get_event_information(
           addr, last_received_object_identifier=last,
       )

   # Acknowledge an alarm
   await client.acknowledge_alarm(
       addr,
       acknowledging_process_identifier=1,
       event_object_identifier="ai,1",
       event_state_acknowledged=EventState.OFFNORMAL,
       time_stamp=ts,
       acknowledgment_source="operator",
       time_of_acknowledgment=ts,
   )


text_message.py
^^^^^^^^^^^^^^^

Send confirmed (reliable) and unconfirmed (fire-and-forget) text messages:

.. code-block:: python

   # Confirmed message (waits for acknowledgment)
   await client.send_text_message("192.168.1.100", "Maintenance at 2pm")

   # Urgent confirmed message
   await client.send_text_message(
       "192.168.1.100", "High temperature alarm!",
       message_priority=MessagePriority.URGENT,
   )

   # Unconfirmed broadcast
   await client.send_text_message(
       "192.168.1.255", "System restart in 5 minutes",
       confirmed=False,
   )


.. _examples-device-management:

Device Management
-----------------

device_control.py
^^^^^^^^^^^^^^^^^

Device communication control, reinitialization, and time synchronization.
All methods accept string enum values (``"disable"``, ``"warmstart"``) in
addition to enum constants:

.. code-block:: python

   # Disable communications (with auto-re-enable after 60 seconds)
   await client.device_communication_control(
       addr, enable_disable="disable", time_duration=60,
   )

   # Re-enable
   await client.device_communication_control(addr, enable_disable="enable")

   # Warm restart
   await client.reinitialize_device(addr, reinitialized_state="warmstart")

   # Synchronize device clock
   now = datetime.datetime.now(tz=datetime.UTC)
   await client.time_synchronization(
       addr,
       BACnetDate(now.year, now.month, now.day, now.isoweekday() % 7),
       BACnetTime(now.hour, now.minute, now.second, 0),
   )


object_management.py
^^^^^^^^^^^^^^^^^^^^

Object lifecycle management using string-based identifiers -- list, create,
and delete objects on a remote device:

.. code-block:: python

   # List all objects
   objects = await client.get_object_list(addr, device_instance=100)

   # Create by type (server assigns instance number)
   await client.create_object(addr, object_type="av")

   # Create with specific instance
   await client.create_object(addr, object_identifier="av,100")

   # Delete
   await client.delete_object(addr, object_identifier="av,100")


backup_restore.py
^^^^^^^^^^^^^^^^^

Back up and restore a device's configuration files using the Clause 19.1
procedure:

.. code-block:: python

   # Download configuration
   backup_data = await client.backup(addr, password="admin")
   print(f"Downloaded {len(backup_data.configuration_files)} file(s)")

   # Upload configuration
   await client.restore(addr, backup_data, password="admin")


audit_log.py
^^^^^^^^^^^^

Query audit log records with target-based filtering and pagination:

.. code-block:: python

   from bac_py.services.audit import AuditQueryByTarget
   from bac_py.types.primitives import ObjectIdentifier

   result = await client.query_audit_log(
       addr,
       audit_log="al,1",
       query_parameters=AuditQueryByTarget(
           target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
       ),
       requested_count=50,
   )

   for record in result.records:
       print(f"  seq={record.sequence_number}")

   # Paginate if more records exist
   if not result.no_more_items:
       last_seq = result.records[-1].sequence_number
       next_page = await client.query_audit_log(
           addr, audit_log="al,1",
           query_parameters=query,
           start_at_sequence_number=last_seq + 1,
           requested_count=50,
       )
