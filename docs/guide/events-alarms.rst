.. _events-alarms:

Events and Alarms
=================


.. _alarm-management:

Alarm Management
-----------------

Get alarm summaries, query event information, and acknowledge alarms using
string-based addressing:

.. code-block:: python

   import datetime
   from bac_py import Client
   from bac_py.types.constructed import BACnetTimeStamp
   from bac_py.types.enums import EventState
   from bac_py.types.primitives import BACnetTime

   async with Client(instance_number=999) as client:
       addr = "192.168.1.100"

       # Get a summary of all active alarms
       alarm_summary = await client.get_alarm_summary(addr)
       for entry in alarm_summary.list_of_alarm_summaries:
           print(f"  {entry.object_identifier}: {entry.alarm_state}")

       # Get detailed event information (supports pagination)
       event_info = await client.get_event_information(addr)
       for summary in event_info.list_of_event_summaries:
           print(f"  {summary.object_identifier}: {summary.event_state}")

       # Acknowledge an alarm (string object identifier)
       now = datetime.datetime.now(tz=datetime.UTC)
       ts = BACnetTimeStamp(choice=0, value=BACnetTime(now.hour, now.minute, now.second, 0))
       await client.acknowledge_alarm(
           addr,
           acknowledging_process_identifier=1,
           event_object_identifier="ai,1",
           event_state_acknowledged=EventState.OFFNORMAL,
           time_stamp=ts,
           acknowledgment_source="operator",
           time_of_acknowledgment=ts,
       )


.. _text-messaging:

Text Messaging
--------------

Send confirmed (reliable) or unconfirmed (fire-and-forget) text messages:

.. code-block:: python

   from bac_py import Client
   from bac_py.types.enums import MessagePriority

   async with Client(instance_number=999) as client:
       # Confirmed text message (waits for acknowledgment)
       await client.send_text_message("192.168.1.100", "Maintenance at 2pm")

       # Urgent confirmed message
       await client.send_text_message(
           "192.168.1.100", "High temperature alarm!",
           message_priority=MessagePriority.URGENT,
       )

       # Unconfirmed broadcast message
       await client.send_text_message(
           "192.168.1.255", "System restart in 5 minutes",
           confirmed=False,
       )


.. _event-notifications:

Event Notifications
-------------------

Configure intrinsic event reporting on an AnalogInput with high/low limits
and a NotificationClass for routing notifications:

.. code-block:: python

   import asyncio
   from bac_py.app.application import BACnetApplication, DeviceConfig
   from bac_py.app.server import DefaultServerHandlers
   from bac_py.objects.analog import AnalogInputObject
   from bac_py.objects.device import DeviceObject
   from bac_py.objects.notification import NotificationClassObject
   from bac_py.types.enums import EngineeringUnits, EventState, EventType, NotifyType

   async def serve_with_events():
       config = DeviceConfig(instance_number=100, name="My-Device",
                             vendor_name="ACME", vendor_id=999)

       async with BACnetApplication(config) as app:
           device = DeviceObject(instance_number=100, object_name="My-Device",
                                 vendor_name="ACME", vendor_identifier=999)
           app.object_db.add(device)

           # NotificationClass routes events to recipients
           app.object_db.add(NotificationClassObject(
               instance_number=1,
               object_name="Critical-Alarms",
               notification_class=1,
               priority=[3, 3, 3],  # to-offnormal, to-fault, to-normal
           ))

           # AnalogInput with intrinsic out-of-range reporting
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

           handlers = DefaultServerHandlers(app, app.object_db, device)
           handlers.register()

           # The EventEngine starts automatically with the application
           # and evaluates intrinsic reporting objects each scan cycle.
           await app.run()

   asyncio.run(serve_with_events())


.. _audit-logging-example:

Audit Logging
-------------

Audit logging is built into ``DefaultServerHandlers``. When the server's
object database contains an :class:`~bac_py.objects.audit_reporter.AuditReporterObject`
and an :class:`~bac_py.objects.audit_log.AuditLogObject`, write/create/delete
operations are automatically recorded:

.. code-block:: python

   from bac_py.objects.audit_log import AuditLogObject
   from bac_py.objects.audit_reporter import AuditReporterObject
   from bac_py.types.enums import AuditLevel

   # Add audit objects to the server's object database
   app.object_db.add(AuditReporterObject(
       instance_number=1,
       object_name="Audit-Reporter",
       audit_level=AuditLevel.DEFAULT,
   ))

   app.object_db.add(AuditLogObject(
       instance_number=1,
       object_name="Audit-Log",
       buffer_size=1000,
   ))

   # Now any WriteProperty, CreateObject, or DeleteObject handled by
   # DefaultServerHandlers will automatically create audit records.
