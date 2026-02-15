Objects
=======

BACnet object model with 40+ object types as frozen dataclasses. Each object
defines its standard properties, default values, and read/write access control.
Objects are hosted in an :class:`~bac_py.objects.base.ObjectDatabase` registry
for server-side use.

- **Base and Device** -- :class:`~bac_py.objects.base.BACnetObject`,
  :class:`~bac_py.objects.base.ObjectDatabase`,
  :class:`~bac_py.objects.device.DeviceObject`
- **I/O** -- Analog, Binary, MultiState inputs/outputs/values
- **Scheduling** -- Calendar, Schedule, TrendLog, Timer, Command, and more
- **Monitoring** -- EventEnrollment, NotificationClass, AuditLog, Accumulator
- **Infrastructure** -- File, NetworkPort, Channel, access control, lighting,
  transportation

See :ref:`supported-object-types` for the full categorized list and
:ref:`server-mode` for server setup.

.. automodule:: bac_py.objects
   :no-members:

.. toctree::
   :maxdepth: 2

   base
   io
   scheduling
   monitoring
   infrastructure
