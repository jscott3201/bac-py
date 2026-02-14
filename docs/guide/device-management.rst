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

