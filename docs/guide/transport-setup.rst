.. _transport-setup:

Transport Setup
===============

bac-py supports five BACnet transport types. This guide shows how to configure
each one for common deployment topologies: standalone clients, servers,
cross-subnet communication via BBMD, multi-network routing, raw Ethernet, and
BACnet Secure Connect.

All transports share the same application layer -- services, objects, and
encoding work identically regardless of the underlying transport. Switching
transports requires only configuration changes, not application code changes.


.. _transport-bip:

BACnet/IP (UDP)
---------------

The default transport. BACnet/IP (Annex J) uses UDP on port 47808 (``0xBAC0``)
with broadcast for discovery and unicast for point-to-point communication.

Client
^^^^^^

The simplest setup -- a client that reads from devices on the local subnet:

.. code-block:: python

   import asyncio
   from bac_py import Client

   async def main():
       async with Client(instance_number=999) as client:
           value = await client.read("192.168.1.100", "ai,1", "pv")
           print(f"Temperature: {value}")

   asyncio.run(main())

Bind to a specific interface when the host has multiple NICs:

.. code-block:: python

   async with Client(instance_number=999, interface="192.168.1.50") as client:
       ...

Server
^^^^^^

A BACnet/IP server that exposes objects to the network:

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
           interface="0.0.0.0",
           port=0xBAC0,
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
               object_name="Zone-Temp",
               units=EngineeringUnits.DEGREES_CELSIUS,
               present_value=22.5,
           ))

           handlers = DefaultServerHandlers(app, app.object_db, device)
           handlers.register()
           await app.run()

   asyncio.run(serve())

See :ref:`server-mode` for the full server guide including object database
management, custom handlers, event engine, scheduling, trend logging, and
audit logging.

Combined client and server
^^^^^^^^^^^^^^^^^^^^^^^^^^

A single application can act as both client and server:

.. code-block:: python

   from bac_py.app.client import BACnetClient

   async with BACnetApplication(config) as app:
       # Server side
       device = DeviceObject(instance_number=100, ...)
       app.object_db.add(device)
       handlers = DefaultServerHandlers(app, app.object_db, device)
       handlers.register()

       # Client side
       bc = BACnetClient(app)
       value = await bc.read("192.168.1.200", "ai,1", "pv")


.. _transport-bbmd:

BACnet/IP with BBMD
--------------------

BACnet Broadcast Management Devices (BBMDs) enable communication across IP
subnets. Without a BBMD, Who-Is broadcasts and other discovery messages stay
within the local subnet.

Foreign device client
^^^^^^^^^^^^^^^^^^^^^

Register as a foreign device to discover and communicate with devices on the
BBMD's subnet:

.. code-block:: python

   from bac_py import Client

   async with Client(
       instance_number=999,
       bbmd_address="192.168.1.1",
       bbmd_ttl=60,
   ) as client:
       # Discover devices on the BBMD's network
       devices = await client.discover(timeout=5.0)

       # Read from a device on the remote subnet
       value = await client.read("192.168.1.100", "ai,1", "pv")

       # Read BBMD tables
       bdt = await client.read_bdt("192.168.1.1")
       fdt = await client.read_fdt("192.168.1.1")

The client automatically re-registers before the TTL expires. You can also
register manually:

.. code-block:: python

   await client.register_as_foreign_device("192.168.1.1", ttl=60)

BBMD server
^^^^^^^^^^^^

Attach a BBMD to a server application to manage foreign devices and forward
broadcasts between subnets:

.. code-block:: python

   import asyncio
   from bac_py import BACnetApplication, DefaultServerHandlers, DeviceConfig, DeviceObject

   async def serve_with_bbmd():
       config = DeviceConfig(
           instance_number=100,
           name="BBMD-Device",
           vendor_name="ACME",
           vendor_id=999,
           interface="192.168.1.1",
           port=0xBAC0,
       )

       async with BACnetApplication(config) as app:
           device = DeviceObject(
               instance_number=100,
               object_name="BBMD-Device",
               vendor_name="ACME",
               vendor_identifier=999,
           )
           app.object_db.add(device)

           handlers = DefaultServerHandlers(app, app.object_db, device)
           handlers.register()

           # Attach BBMD functionality
           app._transport.attach_bbmd()

           await app.run()

   asyncio.run(serve_with_bbmd())

IPv4 multicast (Annex J.8)
^^^^^^^^^^^^^^^^^^^^^^^^^^

As an alternative to directed broadcast, enable IPv4 multicast using group
``239.255.186.192``:

.. code-block:: python

   config = DeviceConfig(
       instance_number=999,
       multicast_enabled=True,
   )


.. _transport-router:

BACnet/IP Router
-----------------

A BACnet router bridges multiple BACnet networks, forwarding NPDUs between
them. Each router port connects to a different network number.

Basic two-network router
^^^^^^^^^^^^^^^^^^^^^^^^^

Bridge two IP subnets with a router:

.. code-block:: python

   from bac_py import BACnetApplication, DeviceConfig
   from bac_py.app.application import RouterConfig, RouterPortConfig

   config = DeviceConfig(
       instance_number=999,
       router_config=RouterConfig(
           ports=[
               RouterPortConfig(
                   port_id=0, network_number=1,
                   interface="192.168.1.10", port=47808,
               ),
               RouterPortConfig(
                   port_id=1, network_number=2,
                   interface="10.0.0.10", port=47808,
               ),
           ],
           application_port_id=0,
       ),
   )

   async with BACnetApplication(config) as app:
       # Router is now forwarding between network 1 and network 2
       await app.run()

The ``application_port_id`` specifies which port the local application listens
on for BACnet services. Set it to the port where you want the router's own
device object to be visible.

Client through a router
^^^^^^^^^^^^^^^^^^^^^^^^

Discover and communicate with devices on remote networks through a router:

.. code-block:: python

   from bac_py import Client

   async with Client(instance_number=998) as client:
       # Discover routers
       routers = await client.who_is_router_to_network(timeout=3.0)
       for r in routers:
           print(f"Router at {r.address}: networks={r.networks}")

       # Discover devices on a remote network
       devices = await client.discover(destination="2:*", timeout=5.0)
       for dev in devices:
           print(f"  Device {dev.instance} at {dev.address_str}")

       # Read from a device on the remote network using routed address
       value = await client.read("2:0A00000A:BAC0", "ai,1", "pv")

Routed addresses use the format ``network:hex_mac`` where the MAC is the
device's IP address and port encoded as hex. See :ref:`addressing` for details.

Mixed-transport router
^^^^^^^^^^^^^^^^^^^^^^^

Route between different transport types (e.g., BACnet/IP and BACnet/SC):

.. code-block:: python

   from bac_py.network.router import NetworkRouter, RouterPort
   from bac_py.transport.bip import BIPTransport
   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   # Port 1: BACnet/IP
   bip = BIPTransport(interface="0.0.0.0", port=0xBAC0)
   await bip.start()

   # Port 2: BACnet/SC
   sc = SCTransport(SCTransportConfig(
       primary_hub_uri="ws://192.168.1.200:4443",
       tls_config=SCTLSConfig(allow_plaintext=True),
   ))

   router = NetworkRouter([
       RouterPort(port_id=1, network_number=1, transport=bip,
                  mac_address=bip.local_mac,
                  max_npdu_length=bip.max_npdu_length),
       RouterPort(port_id=2, network_number=2, transport=sc,
                  mac_address=sc.local_mac,
                  max_npdu_length=sc.max_npdu_length),
   ])
   await router.start()

This enables BACnet/IP devices on network 1 to communicate transparently
with BACnet/SC devices on network 2. See :ref:`examples-secure-connect` for the
full ``ip_to_sc_router.py`` example.


.. _transport-ipv6:

BACnet/IPv6 (Annex U)
----------------------

BACnet/IPv6 provides native IPv6 transport with multicast discovery and
3-byte VMAC virtual addressing.

IPv6 client
^^^^^^^^^^^^

.. code-block:: python

   from bac_py import Client

   async with Client(ipv6=True) as client:
       devices = await client.discover(timeout=5.0)

The default multicast group is ``ff02::bac0`` (link-local). Use
``ff05::bac0`` for site-local scope:

.. code-block:: python

   async with Client(
       ipv6=True,
       interface="fd00::1",
       multicast_address="ff05::bac0",
   ) as client:
       ...

IPv6 foreign device
^^^^^^^^^^^^^^^^^^^^

Register with an IPv6 BBMD using bracket notation:

.. code-block:: python

   async with Client(
       ipv6=True,
       bbmd_address="[fd00::1]:47808",
       bbmd_ttl=60,
   ) as client:
       devices = await client.discover(timeout=5.0)

IPv6 router port
^^^^^^^^^^^^^^^^

Mix IPv4 and IPv6 on different router ports:

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


.. _transport-ethernet:

BACnet Ethernet (ISO 8802-3)
-----------------------------

Raw Ethernet transport for legacy BACnet installations using IEEE 802.3
frames with 802.2 LLC headers (Clause 7). This is a low-level transport that
bypasses IP entirely.

.. code-block:: python

   from bac_py.transport.ethernet import EthernetTransport

   transport = EthernetTransport(
       interface="eth0",
       mac_address=b"\x00\x11\x22\x33\x44\x55",  # optional on Linux
   )
   await transport.start()

Platform requirements:

- **Linux**: ``AF_PACKET`` / ``SOCK_RAW`` (requires ``CAP_NET_RAW``)
- **macOS**: BPF devices (``/dev/bpf*``)

Ethernet MAC addresses are supported in address strings:

.. code-block:: python

   from bac_py.network.address import parse_address

   addr = parse_address("aa:bb:cc:dd:ee:ff")           # Local Ethernet
   addr = parse_address("5:aa:bb:cc:dd:ee:ff")          # Remote on network 5
   addr = parse_address("4352:01")                       # MS/TP 1-byte MAC


.. _transport-sc:

BACnet Secure Connect (Annex AB)
---------------------------------

BACnet/SC replaces broadcast UDP with TLS-secured WebSocket connections in a
hub-and-spoke topology. It traverses firewalls and NAT without BBMD
infrastructure.

SC client (hub connector)
^^^^^^^^^^^^^^^^^^^^^^^^^^

Connect to an existing SC hub:

.. code-block:: python

   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   config = SCTransportConfig(
       primary_hub_uri="wss://hub.example.com:8443",
       tls_config=SCTLSConfig(
           ca_certificates_path="/path/to/ca.pem",
           certificate_path="/path/to/device.pem",
           private_key_path="/path/to/device.key",
       ),
   )
   transport = SCTransport(config)
   await transport.start()
   await transport.hub_connector.wait_connected(timeout=10.0)

SC hub server
^^^^^^^^^^^^^

Run a hub that accepts connections from SC nodes:

.. code-block:: python

   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.hub_function import SCHubConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   tls = SCTLSConfig(
       ca_certificates_path="/path/to/ca.pem",
       certificate_path="/path/to/hub.pem",
       private_key_path="/path/to/hub.key",
   )
   config = SCTransportConfig(
       hub_function_config=SCHubConfig(
           bind_address="0.0.0.0",
           bind_port=8443,
           tls_config=tls,
       ),
       tls_config=tls,
   )
   transport = SCTransport(config)
   await transport.start()

SC with failover
^^^^^^^^^^^^^^^^

Configure primary and failover hubs for continuous operation:

.. code-block:: python

   config = SCTransportConfig(
       primary_hub_uri="wss://hub1.example.com:8443",
       failover_hub_uri="wss://hub2.example.com:8443",
       tls_config=SCTLSConfig(...),
   )

SC with direct peer connections
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Enable the Node Switch for direct peer-to-peer WebSocket connections that
bypass the hub:

.. code-block:: python

   from bac_py.transport.sc.node_switch import SCNodeSwitchConfig

   config = SCTransportConfig(
       primary_hub_uri="wss://hub.example.com:8443",
       node_switch_config=SCNodeSwitchConfig(
           enable=True,
           bind_address="0.0.0.0",
           bind_port=8444,
       ),
       tls_config=SCTLSConfig(...),
   )

For a complete BACnet/SC guide including TLS certificate generation, VMAC
addressing, and address resolution, see :doc:`secure-connect`.


.. _transport-comparison:

Transport Comparison
---------------------

.. list-table::
   :header-rows: 1
   :widths: 15 15 15 15 20 20

   * - Transport
     - Protocol
     - Discovery
     - Encryption
     - Cross-subnet
     - Use case
   * - BACnet/IP
     - UDP
     - Broadcast
     - None
     - BBMD required
     - Standard BACnet networks
   * - BACnet/IPv6
     - UDP/IPv6
     - Multicast
     - None
     - BBMD6
     - IPv6-only networks
   * - Ethernet
     - 802.3 LLC
     - Broadcast
     - None
     - Router required
     - Legacy installations
   * - BACnet/SC
     - WebSocket/TLS
     - Via hub
     - TLS 1.3
     - NAT traversal
     - IT-managed, cloud-ready
   * - Router
     - Mixed
     - Forwarded
     - Per-port
     - Native
     - Multi-network bridging
