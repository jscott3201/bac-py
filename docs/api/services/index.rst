Services
========

BACnet service request and response types as frozen dataclasses. Each service
has an ``encode()`` method that produces raw bytes and a ``decode()`` class
method that parses bytes back into a typed object.

- **Property Access** -- ReadProperty, WriteProperty, ReadPropertyMultiple,
  WritePropertyMultiple, ReadRange. See :doc:`/guide/reading-writing`.
- **Discovery and COV** -- Who-Is/I-Am, Who-Has/I-Have, COV subscriptions.
  See :doc:`/guide/discovery-networking`.
- **Events and Alarms** -- EventNotification, AlarmSummary, Audit services.
  See :doc:`/guide/events-alarms`.
- **Device Management** -- DeviceCommunicationControl, ReinitializeDevice,
  CreateObject, DeleteObject, file access, private transfer.
  See :doc:`/guide/device-management` and :doc:`/guide/client-guide`.

.. automodule:: bac_py.services
   :no-members:

.. toctree::
   :maxdepth: 2

   property
   discovery
   events
   management
