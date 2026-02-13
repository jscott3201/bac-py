.. _device-management:

Device Management and Tools
============================


.. _device-control:

Device Communication Control
-----------------------------

Enable, disable, or restrict device communications using
:meth:`~bac_py.client.Client.device_communication_control`. All enum
parameters accept either typed values or plain strings:

.. code-block:: python

   from bac_py import Client

   async with Client(instance_number=999) as client:
       addr = "192.168.1.100"

       # Disable initiation (device stops sending, still responds)
       await client.device_communication_control(
           addr, enable_disable="disable-initiation",
       )

       # Fully disable (device stops responding to all requests)
       await client.device_communication_control(
           addr, enable_disable="disable", time_duration=60,
       )

       # Re-enable
       await client.device_communication_control(addr, enable_disable="enable")

The ``time_duration`` parameter (in minutes) causes the device to auto-
re-enable after the specified period. An optional ``password`` is sent to
devices that require authentication.


.. _reinitialization:

Reinitialization
----------------

Restart a remote device with
:meth:`~bac_py.client.Client.reinitialize_device`:

.. code-block:: python

   # Warm restart (preserve configuration)
   await client.reinitialize_device(addr, reinitialized_state="warmstart")

   # Cold restart (reset to factory defaults)
   await client.reinitialize_device(addr, reinitialized_state="coldstart",
                                    password="admin")


.. _time-sync:

Time Synchronization
--------------------

Synchronize a device's clock using either local time or UTC:

.. code-block:: python

   import datetime
   from bac_py.types.primitives import BACnetDate, BACnetTime

   now = datetime.datetime.now(tz=datetime.UTC)
   date = BACnetDate(now.year, now.month, now.day, now.isoweekday() % 7)
   time = BACnetTime(now.hour, now.minute, now.second, 0)

   # Local time sync (unconfirmed broadcast)
   await client.time_synchronization(addr, date, time)

   # UTC time sync
   await client.utc_time_synchronization(addr, date, time)


.. _object-management-guide:

Object Management
-----------------

Create, list, and delete objects on a remote device:

.. code-block:: python

   from bac_py import Client

   async with Client(instance_number=999) as client:
       addr = "192.168.1.100"

       # List all objects on the device
       objects = await client.get_object_list(addr, device_instance=100)
       for obj_id in objects:
           print(f"  {obj_id.object_type.name},{obj_id.instance_number}")

       # Create an object (server assigns instance number)
       await client.create_object(addr, object_type="av")

       # Create with a specific instance number
       await client.create_object(addr, object_identifier="av,100")

       # Delete an object
       await client.delete_object(addr, object_identifier="av,100")

String identifiers (``"av"``, ``"av,100"``) and typed
:class:`~bac_py.types.primitives.ObjectIdentifier` values are both accepted.


.. _backup-restore:

Backup and Restore
------------------

Back up and restore a remote device's configuration using the high-level API:

.. code-block:: python

   from bac_py import Client

   async with Client(instance_number=999) as client:
       # Backup: downloads all configuration files
       backup_data = await client.backup("192.168.1.100", password="admin")
       print(f"Downloaded {len(backup_data.configuration_files)} file(s)")

       # Restore: uploads configuration files back
       await client.restore("192.168.1.100", backup_data, password="admin")

The backup/restore procedure follows Clause 19.1: ReinitializeDevice to
enter backup/restore mode, poll state until ready, transfer files via
AtomicReadFile/AtomicWriteFile, and ReinitializeDevice to finish.


.. _json-serialization-example:

JSON Serialization
------------------

Serialize BACnet objects and data structures to JSON for REST APIs, webhooks,
or data export. Any object with a ``to_dict()`` method can be serialized:

.. code-block:: python

   from bac_py.serialization import serialize, deserialize

   # Serialize an object snapshot to JSON bytes
   ai = app.object_db.get(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
   json_bytes = serialize(ai)

   # Deserialize back to a dict
   data = deserialize(json_bytes)
   print(data["object_name"], data["present_value"])

   # Serialize notification parameters for a webhook
   from bac_py.types.notification_params import NotificationParameters
   json_bytes = serialize(notification_params)

   # Round-trip a plain dict
   snapshot = {"device": 100, "readings": [
       {"object": "ai,1", "value": 22.5},
       {"object": "ai,2", "value": 19.8},
   ]}
   json_bytes = serialize(snapshot)
   restored = deserialize(json_bytes)


.. _docker-testing-example:

Docker Integration Testing
--------------------------

Docker-based tests exercise real BACnet/IP communication over actual UDP
sockets between separate application instances. The test infrastructure is
under ``docker/`` and requires Docker and Docker Compose.

Build and run all scenarios:

.. code-block:: bash

   # Build the Alpine-based Docker image
   make docker-build

   # Run all eight integration scenarios
   make docker-test

Run individual scenarios:

.. code-block:: bash

   make docker-test-client       # Client/server: read, write, discover, RPM, WPM
   make docker-test-bbmd         # BBMD: foreign device registration + forwarding
   make docker-test-router       # Router: cross-network discovery and reads
   make docker-test-stress       # Stress: concurrent and sequential throughput
   make docker-test-device-mgmt  # Device management: DCC, time sync, text message
   make docker-test-cov-advanced # COV: concurrent subscriptions, property-level COV
   make docker-test-events       # Events: alarm reporting, acknowledgment, queries

Run the standalone stress test with JSON output:

.. code-block:: bash

   make docker-stress

   # Output:
   # {
   #   "config": {"num_clients": 10, "requests_per_client": 500},
   #   "results": {
   #     "throughput_rps": 1250.3,
   #     "latency_ms": {"p50": 3.2, "p95": 8.1, "p99": 15.4},
   #     "error_rate": 0.0
   #   }
   # }

The Docker Compose file defines three isolated bridge networks
(``bacnet-main``, ``bacnet-secondary``, ``bacnet-foreign``) and uses
profiles to run scenarios independently. Each server container exposes
sample objects (AnalogInput, AnalogOutput, AnalogValue, BinaryInput,
BinaryValue) and registers ``DefaultServerHandlers``.

.. list-table::
   :header-rows: 1
   :widths: 20 40

   * - Scenario
     - What it tests
   * - Client/Server
     - ReadProperty, WriteProperty, RPM, WPM, Who-Is, discover, object list
   * - BBMD
     - Foreign device registration, BDT/FDT reads, cross-subnet forwarding
   * - Router
     - Who-Is-Router, cross-network discovery, cross-network reads
   * - Stress
     - 10 concurrent clients, 100 sequential reads, throughput measurement
   * - Device Management
     - DCC disable/enable, time synchronization, text messages, private transfer
   * - COV Advanced
     - Concurrent COV subscriptions, property-level COV, lifetime expiration
   * - Events
     - Alarm reporting, acknowledgment, event queries, enrollment summaries
   * - Demo
     - Interactive client/server demonstration with reads, writes, and discovery

Clean up Docker resources:

.. code-block:: bash

   make docker-clean


.. _protocol-level-api:

Protocol-Level API
------------------

For cases where the convenience API isn't sufficient, you can use the
protocol-level methods directly. These accept explicit
:class:`~bac_py.network.address.BACnetAddress`,
:class:`~bac_py.types.primitives.ObjectIdentifier`, and
:class:`~bac_py.types.enums.PropertyIdentifier` types, and work with raw
application-tagged bytes. See :ref:`two-api-levels` for guidance on when to
use each level.

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
:mod:`bac_py.encoding.primitives`:

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
