.. _server-mode:

Server Mode
===========


.. _serving-objects:

Serving Objects
---------------

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
