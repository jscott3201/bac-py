.. _discovery-networking:

Discovery and Networking
========================


.. _device-discovery:

Device Discovery
----------------

Discover all devices
^^^^^^^^^^^^^^^^^^^^

:meth:`~bac_py.client.Client.discover` sends a Who-Is broadcast and returns
:class:`~bac_py.app.client.DiscoveredDevice` objects with the responding
device's address, instance number, vendor ID, max APDU length, and
segmentation support:

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

:meth:`~bac_py.client.Client.get_object_list` reads the complete list of
objects from a remote device:

.. code-block:: python

   objects = await client.get_object_list("192.168.1.100", device_instance=100)
   for obj_id in objects:
       print(f"  {obj_id.object_type.name},{obj_id.instance_number}")


Extended discovery
^^^^^^^^^^^^^^^^^^

:meth:`~bac_py.client.Client.discover_extended` enriches standard discovery
with Annex X profile metadata (``Profile_Name``, ``Profile_Location``,
``Tags``):

.. code-block:: python

   devices = await client.discover_extended(timeout=3.0, enrich_timeout=5.0)
   for dev in devices:
       print(f"  Device {dev.instance}: profile={dev.profile_name}")
       if dev.tags:
           print(f"    tags: {dev.tags}")


Discover unconfigured devices
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~bac_py.client.Client.discover_unconfigured` listens for Who-Am-I
broadcasts from unconfigured devices (Clause 19.7). This is useful for
commissioning new devices that have not yet been assigned an instance number:

.. code-block:: python

   devices = await client.discover_unconfigured(timeout=5.0)
   for dev in devices:
       print(f"  Vendor: {dev.vendor_id}  Model: {dev.model_name}")
       print(f"  Serial: {dev.serial_number}  Address: {dev.address}")


Find objects by identifier or name
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~bac_py.client.Client.who_has` sends a Who-Has broadcast to find
devices that contain a specific object. Accepts string object identifiers:

.. code-block:: python

   results = await client.who_has(object_identifier="ai,1", timeout=3.0)
   for r in results:
       print(f"  Device {r.device_identifier} has {r.object_identifier}")

   # Or search by name
   results = await client.who_has(object_name="Zone Temp", timeout=3.0)


.. _foreign-device-registration:

Foreign Device Registration
----------------------------

To communicate across subnets, register as a foreign device with a BBMD
(BACnet Broadcast Management Device). See :ref:`bbmd-support` for background
on BBMD capabilities.

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
and re-registers before the TTL expires. You can also register manually at any
time:

.. code-block:: python

   await client.register_as_foreign_device("192.168.1.1", ttl=60)


.. _ipv6-transport:

IPv6 Transport (Annex U)
-------------------------

bac-py supports BACnet/IPv6 per ASHRAE 135-2020 Annex U. Set ``ipv6=True``
on the :class:`~bac_py.client.Client` or
:class:`~bac_py.app.application.DeviceConfig` to use IPv6 multicast
instead of IPv4 broadcast:

.. code-block:: python

   from bac_py import Client

   async with Client(ipv6=True) as client:
       devices = await client.discover(timeout=5.0)

The default multicast group is ``ff02::bac0`` and the default interface is
``::`` (all IPv6 interfaces). Both can be customized:

.. code-block:: python

   async with Client(
       ipv6=True,
       interface="fd00::1",
       multicast_address="ff05::bac0",  # site-local scope
   ) as client:
       ...

IPv6 foreign device registration works the same as IPv4, but uses
bracket notation for the BBMD address:

.. code-block:: python

   async with Client(
       ipv6=True,
       bbmd_address="[fd00::1]:47808",
       bbmd_ttl=60,
   ) as client:
       devices = await client.discover(timeout=5.0)

For router-mode configurations, individual ports can use IPv6:

.. code-block:: python

   from bac_py.app.application import DeviceConfig, RouterConfig, RouterPortConfig

   config = DeviceConfig(
       instance_number=999,
       router_config=RouterConfig(
           ports=[
               RouterPortConfig(port_id=0, network_number=1,
                                interface="192.168.1.10", port=47808),
               RouterPortConfig(port_id=1, network_number=2,
                                ipv6=True, port=47808),
           ],
           application_port_id=0,
       ),
   )


.. _router-discovery:

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

See :ref:`addressing` for the routed address format.


.. _multi-network-routing:

Multi-Network Routing
---------------------

Configure bac-py as a BACnet router between multiple IP networks. See
:ref:`network-routing` for more on routing capabilities.

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
