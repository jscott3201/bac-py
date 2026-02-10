Examples
========

All examples below use the convenience ``Client`` API. For protocol-level
examples, see :ref:`protocol-level-api`.

Reading Properties
------------------

Read a single property
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import asyncio
   from bac_py import Client

   async def main():
       async with Client(instance_number=999) as client:
           # Read present-value using short aliases
           value = await client.read("192.168.1.100", "ai,1", "pv")
           print(f"Present value: {value}")

           # Full names work too
           name = await client.read("192.168.1.100", "analog-input,1", "object-name")
           print(f"Object name: {name}")

           # Read a specific array element (e.g. priority-array slot 8)
           priority = await client.read("192.168.1.100", "av,1", "priority-array", array_index=8)
           print(f"Priority 8: {priority}")

   asyncio.run(main())


Read multiple properties
^^^^^^^^^^^^^^^^^^^^^^^^

``read_multiple()`` uses ``ReadPropertyMultiple`` under the hood, sending a
single request for multiple objects and properties:

.. code-block:: python

   async with Client(instance_number=999) as client:
       results = await client.read_multiple("192.168.1.100", {
           "ai,1": ["pv", "object-name", "units", "status"],
           "ai,2": ["pv", "object-name"],
           "av,1": ["pv", "object-name"],
       })

       for obj_id, props in results.items():
           print(f"{obj_id}:")
           for prop_name, value in props.items():
               print(f"  {prop_name}: {value}")

The result is a nested dictionary keyed by canonical object identifier strings
(e.g. ``"analog-input,1"``) and property names (e.g. ``"present-value"``).


Writing Properties
------------------

Write with auto-encoding
^^^^^^^^^^^^^^^^^^^^^^^^^

The ``write()`` method automatically encodes Python values to the correct
BACnet application tag based on the value type, the target object type, and the
property:

.. code-block:: python

   async with Client(instance_number=999) as client:
       # Float to analog -> encoded as Real
       await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)

       # Int to binary -> encoded as Enumerated
       await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)

       # Int to multi-state -> encoded as Unsigned
       await client.write("192.168.1.100", "msv,1", "pv", 3, priority=8)

       # String property
       await client.write("192.168.1.100", "av,1", "object-name", "Zone Temp Setpoint")

       # Relinquish (release) a command priority by writing None
       await client.write("192.168.1.100", "av,1", "pv", None, priority=8)

The encoding rules:

.. list-table::
   :header-rows: 1
   :widths: 30 30

   * - Python type
     - BACnet encoding
   * - ``float``
     - Real
   * - ``int`` (analog present-value)
     - Real
   * - ``int`` (binary present-value)
     - Enumerated
   * - ``int`` (multi-state present-value)
     - Unsigned
   * - ``str``
     - Character String
   * - ``bool``
     - Enumerated (1/0)
   * - ``None``
     - Null (relinquish priority)
   * - ``IntEnum``
     - Enumerated
   * - ``bytes``
     - Pass-through (pre-encoded)

For non-present-value properties, a built-in type hint map ensures common
properties like ``units``, ``cov-increment``, ``high-limit``, and
``out-of-service`` are encoded correctly even when given a plain ``int``.


Write multiple properties
^^^^^^^^^^^^^^^^^^^^^^^^^

``write_multiple()`` writes several properties across multiple objects in a
single request:

.. code-block:: python

   async with Client(instance_number=999) as client:
       await client.write_multiple("192.168.1.100", {
           "av,1": {"pv": 72.5, "object-name": "Zone Temp SP"},
           "av,2": {"pv": 55.0},
       })


Device Discovery
----------------

Discover all devices
^^^^^^^^^^^^^^^^^^^^

``discover()`` sends a Who-Is broadcast and returns ``DiscoveredDevice``
objects with the responding device's address, instance number, vendor ID, max
APDU length, and segmentation support:

.. code-block:: python

   from bac_py import Client

   async with Client(instance_number=999) as client:
       devices = await client.discover(timeout=3.0)

       print(f"Found {len(devices)} device(s):")
       for dev in devices:
           print(f"  Instance: {dev.instance}")
           print(f"  Address:  {dev.address_str}")
           print(f"  Vendor:   {dev.vendor_id}")
           print(f"  Max APDU: {dev.max_apdu_length}")
           print(f"  Segmentation: {dev.segmentation_supported}")

Discover devices in a range
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use ``low_limit`` and ``high_limit`` to narrow the search to a specific
instance range:

.. code-block:: python

   devices = await client.discover(low_limit=100, high_limit=200, timeout=3.0)

Get a device's object list
^^^^^^^^^^^^^^^^^^^^^^^^^^

``get_object_list()`` reads the complete list of objects from a remote device:

.. code-block:: python

   from bac_py.types.primitives import ObjectIdentifier

   objects = await client.get_object_list("192.168.1.100", device_instance=100)
   for obj_id in objects:
       print(f"  {obj_id.object_type.name},{obj_id.instance_number}")


COV Subscriptions
-----------------

Subscribe to Change-of-Value (COV) notifications to be notified when a
property changes on a remote device:

.. code-block:: python

   from bac_py import Client, decode_cov_values

   async with Client(instance_number=999) as client:

       def on_notification(notification, source):
           values = decode_cov_values(notification)
           print(f"COV from {source}:")
           for name, value in values.items():
               print(f"  {name}: {value}")

       # Subscribe -- the device will send notifications for up to 1 hour
       await client.subscribe_cov_ex(
           "192.168.1.100", "ai,1",
           process_id=1,
           callback=on_notification,
           confirmed=True,
           lifetime=3600,
       )

       # Keep listening for 60 seconds
       await asyncio.sleep(60)

       # Clean up
       await client.unsubscribe_cov_ex("192.168.1.100", "ai,1", process_id=1)

``decode_cov_values()`` converts the raw notification into a dictionary of
property names to decoded Python values.


Foreign Device Registration
----------------------------

To communicate across subnets, register as a foreign device with a BBMD
(BACnet Broadcast Management Device):

.. code-block:: python

   from bac_py import Client

   async with Client(
       instance_number=999,
       bbmd_address="192.168.1.1",
       bbmd_ttl=60,
   ) as client:
       print(f"Status: {client.foreign_device_status}")

       # Discover devices on the BBMD's network
       devices = await client.discover(timeout=5.0)
       print(f"Discovered {len(devices)} device(s)")

       # Read BDT and FDT tables from the BBMD
       bdt = await client.read_bdt("192.168.1.1")
       for entry in bdt:
           print(f"  BDT: {entry.address} mask={entry.mask}")

       fdt = await client.read_fdt("192.168.1.1")
       for entry in fdt:
           print(f"  FDT: {entry.address} ttl={entry.ttl}s remaining={entry.remaining}s")

When ``bbmd_address`` is set, the client automatically registers on startup
and re-registers before the TTL expires.. You can also register manually at any
time:

.. code-block:: python

   await client.register_as_foreign_device("192.168.1.1", ttl=60)


Router Discovery
----------------

Discover routers and the remote networks they can reach:

.. code-block:: python

   async with Client(instance_number=999) as client:
       routers = await client.who_is_router_to_network(timeout=3.0)

       for router in routers:
           print(f"Router at {router.address}:")
           print(f"  Networks: {router.networks}")

       # Discover devices on a remote network through a router
       if routers:
           remote_net = routers[0].networks[0]
           devices = await client.discover(destination=f"{remote_net}:*", timeout=5.0)
           for dev in devices:
               print(f"  Device {dev.instance} at {dev.address_str}")


Serving Objects
---------------

Host a BACnet server that exposes local objects to the network:

.. code-block:: python

   import asyncio
   from bac_py.app.application import BACnetApplication, DeviceConfig
   from bac_py.app.server import DefaultServerHandlers
   from bac_py.objects.analog import AnalogInputObject
   from bac_py.objects.device import DeviceObject
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
and WriteProperty/WritePropertyMultiple to update writable objects.


Multi-Network Routing
---------------------

Configure bac-py as a BACnet router between multiple IP networks:

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


.. _protocol-level-api:

Protocol-Level API
------------------

For cases where the convenience API isn't sufficient, you can use the
protocol-level methods directly. These accept explicit ``BACnetAddress``,
``ObjectIdentifier``, and ``PropertyIdentifier`` types, and work with raw
application-tagged bytes:

.. code-block:: python

   from bac_py import Client
   from bac_py.encoding.primitives import encode_application_real
   from bac_py.network.address import parse_address
   from bac_py.types.enums import ObjectType, PropertyIdentifier
   from bac_py.types.primitives import ObjectIdentifier

   async with Client(instance_number=999) as client:
       address = parse_address("192.168.1.100")
       obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

       # Protocol-level write with explicit encoding
       await client.write_property(
           address, obj_id,
           PropertyIdentifier.PRESENT_VALUE,
           value=encode_application_real(72.5),
           priority=8,
       )

       # Protocol-level read returning raw ACK
       ack = await client.read_property(
           address, obj_id,
           PropertyIdentifier.PRESENT_VALUE,
       )
       print(ack.property_value.hex())

Encoding helpers for all BACnet application types are available in
``bac_py.encoding.primitives``:

.. code-block:: python

   from bac_py.encoding.primitives import (
       encode_application_real,              # float -> Real
       encode_application_unsigned,          # int -> Unsigned
       encode_application_signed,            # int -> Signed
       encode_application_enumerated,        # int -> Enumerated
       encode_application_character_string,  # str -> CharacterString
       encode_application_boolean,           # bool -> Boolean
       encode_application_octet_string,      # bytes -> OctetString
       encode_application_null,              # None -> Null
       encode_application_object_id,         # (type, instance) -> ObjectId
       encode_application_date,              # BACnetDate -> Date
       encode_application_time,              # BACnetTime -> Time
       encode_application_bit_string,        # BitString -> BitString
   )
