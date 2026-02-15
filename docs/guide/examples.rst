.. _examples-guide:

Example Scripts
===============

The ``examples/`` directory contains 23 runnable scripts demonstrating bac-py's
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

.. tip::

   Most examples include a ``logging.basicConfig()`` call that you can
   uncomment or adjust to see protocol-level traces. Set ``level=logging.DEBUG``
   to see every request and response. See :doc:`debugging-logging` for the
   full logger hierarchy and filtering options.


.. _examples-interactive-cli:

Interactive CLI
---------------

interactive_cli.py
^^^^^^^^^^^^^^^^^^

A menu-driven interactive CLI for testing Client API features against a real
BACnet device. Provides a single tool to explore the full API interactively
instead of editing and re-running individual example scripts.

.. code-block:: bash

   # Start with a target address
   uv run python examples/interactive_cli.py 192.168.1.100

   # Or enter the address interactively
   uv run python examples/interactive_cli.py

The menu offers 10 actions covering the core Client API:

- **Read / Write** -- single property reads and writes with array index and
  priority support, plus batch operations via ReadPropertyMultiple and
  WritePropertyMultiple
- **Discovery** -- Who-Is device discovery, Who-Has object search, and object
  list enumeration
- **COV** -- subscribe and unsubscribe with live ``[COV]``-prefixed
  notifications printed between menu prompts
- **Device Management** -- time synchronization using the current system clock

Input uses ``asyncio.run_in_executor()`` so the event loop stays responsive for
COV callbacks while waiting for user input. Active COV subscriptions are
automatically cleaned up on exit.


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
       audit_log="audit-log,1",
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
           addr, audit_log="audit-log,1",
           query_parameters=query,
           start_at_sequence_number=last_seq + 1,
           requested_count=50,
       )


.. _examples-ipv6:

BACnet/IPv6
-----------

ipv6_client_server.py
^^^^^^^^^^^^^^^^^^^^^

Discover devices and read properties over BACnet/IPv6 (Annex U) with multicast
discovery using the ``ff02::bac0`` multicast group:

.. code-block:: python

   from bac_py import Client

   async with Client(ipv6=True) as client:
       devices = await client.discover(timeout=5.0)
       for dev in devices:
           print(f"  {dev.instance} at {dev.address_str}")

       if devices:
           value = await client.read(devices[0].address_str, "dev,*", "object-name")
           print(f"Device name: {value}")

See :ref:`transport-ipv6` for IPv6 transport configuration details.


.. _examples-secure-connect:

BACnet Secure Connect
---------------------

secure_connect.py
^^^^^^^^^^^^^^^^^

Connect to an SC hub over WebSocket/TLS and send a ReadProperty request to a
remote device addressed by its 6-byte VMAC. Demonstrates the lower-level
``SCTransport`` API with manual NPDU/APDU construction:

.. code-block:: python

   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig
   from bac_py.transport.sc.vmac import SCVMAC

   config = SCTransportConfig(
       primary_hub_uri="ws://192.168.1.200:4443",
       tls_config=SCTLSConfig(allow_plaintext=True),
   )
   transport = SCTransport(config)
   await transport.start()
   await transport.hub_connector.wait_connected(timeout=10.0)

   # Build and send NPDU to a remote VMAC
   transport.send_unicast(npdu_bytes, SCVMAC.from_hex("02:AA:BB:CC:DD:01").address)

Install the ``secure`` extra (``pip install bac-py[secure]``) to use SC
transport. See :doc:`secure-connect` for the full guide.


secure_connect_hub.py
^^^^^^^^^^^^^^^^^^^^^

Run a BACnet/SC hub that accepts WebSocket connections from SC nodes, routes
traffic between them, and optionally enables direct peer-to-peer connections
via the Node Switch:

.. code-block:: python

   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.hub_function import SCHubConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   config = SCTransportConfig(
       hub_function_config=SCHubConfig(
           bind_address="0.0.0.0",
           bind_port=4443,
           tls_config=SCTLSConfig(allow_plaintext=True),
       ),
       tls_config=SCTLSConfig(allow_plaintext=True),
   )
   transport = SCTransport(config)
   await transport.start()

   # Hub is now accepting SC node connections on port 4443
   print(f"Connected nodes: {transport.hub_function.connection_count}")


ip_to_sc_router.py
^^^^^^^^^^^^^^^^^^

Bridge a BACnet/IP network and a BACnet/SC network with a pure-forwarding
gateway router. Existing IP controllers communicate transparently with new
SC devices -- the router handles all NPDU forwarding in both directions:

.. code-block:: python

   from bac_py.network.router import NetworkRouter, RouterPort
   from bac_py.transport.bip import BIPTransport
   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   # Port 1: BACnet/IP
   bip_transport = BIPTransport(interface="0.0.0.0", port=0xBAC0)
   await bip_transport.start()
   bip_port = RouterPort(
       port_id=1, network_number=1, transport=bip_transport,
       mac_address=bip_transport.local_mac,
       max_npdu_length=bip_transport.max_npdu_length,
   )

   # Port 2: BACnet/SC
   sc_transport = SCTransport(SCTransportConfig(
       primary_hub_uri="ws://192.168.1.200:4443",
       tls_config=SCTLSConfig(allow_plaintext=True),
   ))
   sc_port = RouterPort(
       port_id=2, network_number=2, transport=sc_transport,
       mac_address=sc_transport.local_mac,
       max_npdu_length=sc_transport.max_npdu_length,
   )

   # Start the gateway (pure forwarding, no local application)
   router = NetworkRouter([bip_port, sc_port])
   await router.start()


sc_generate_certs.py
^^^^^^^^^^^^^^^^^^^^

Generate a self-signed test PKI (CA + three device certificates for a hub and
two nodes) and demonstrate TLS-secured SC communication with mutual
authentication.  Uses EC P-256 keys (the recommended curve for BACnet/SC) and
the ``cryptography`` library that ships with ``bac-py[secure]``.  The demo
starts a hub, connects two nodes via mutual TLS 1.3, and routes a test NPDU
from node 1 to node 2 through the hub:

.. code-block:: python

   from cryptography import x509
   from cryptography.hazmat.primitives import hashes, serialization
   from cryptography.hazmat.primitives.asymmetric import ec
   from cryptography.x509.oid import NameOID

   # Generate CA key + self-signed certificate
   ca_key = ec.generate_private_key(ec.SECP256R1())
   ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BACnet Test CA")])
   ca_cert = (
       x509.CertificateBuilder()
       .subject_name(ca_name)
       .issuer_name(ca_name)
       .public_key(ca_key.public_key())
       .serial_number(x509.random_serial_number())
       .not_valid_before(now)
       .not_valid_after(now + datetime.timedelta(days=365))
       .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
       .sign(ca_key, hashes.SHA256())
   )

   # Generate device certificate signed by the CA
   device_key = ec.generate_private_key(ec.SECP256R1())
   device_cert = (
       x509.CertificateBuilder()
       .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SC Hub")]))
       .issuer_name(ca_name)
       .public_key(device_key.public_key())
       .serial_number(x509.random_serial_number())
       .not_valid_before(now)
       .not_valid_after(now + datetime.timedelta(days=365))
       .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
       .sign(ca_key, hashes.SHA256())
   )

   # Wire into SCTLSConfig for mutual TLS
   hub_tls = SCTLSConfig(
       private_key_path="hub.key",
       certificate_path="hub.crt",
       ca_certificates_path="ca.crt",
   )
   node_tls = SCTLSConfig(
       private_key_path="node1.key",
       certificate_path="node1.crt",
       ca_certificates_path="ca.crt",
   )
