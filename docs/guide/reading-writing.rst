.. _examples:

.. _reading-writing:

Reading and Writing Properties
==============================

All examples below use the convenience :class:`~bac_py.client.Client` API. For
protocol-level examples, see :ref:`protocol-level-api`.


.. _reading-properties:

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

See :ref:`string-aliases` for the full list of supported short names.


Read multiple properties
^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~bac_py.client.Client.read_multiple` uses ``ReadPropertyMultiple``
under the hood, sending a single request for multiple objects and properties:

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


.. _writing-properties:

Writing Properties
------------------

Write with auto-encoding
^^^^^^^^^^^^^^^^^^^^^^^^^

The :meth:`~bac_py.client.Client.write` method automatically encodes Python
values to the correct BACnet application tag based on the value type, the
target object type, and the property:

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

.. _encoding-rules:

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

:meth:`~bac_py.client.Client.write_multiple` writes several properties across
multiple objects in a single request:

.. code-block:: python

   async with Client(instance_number=999) as client:
       await client.write_multiple("192.168.1.100", {
           "av,1": {"pv": 72.5, "object-name": "Zone Temp SP"},
           "av,2": {"pv": 55.0},
       })


.. _cov-subscriptions:

COV Subscriptions
-----------------

Subscribe to Change-of-Value (COV) notifications to be notified when a
property changes on a remote device:

.. code-block:: python

   import asyncio
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

:func:`~bac_py.app.client.decode_cov_values` converts the raw notification
into a dictionary of property names to decoded Python values.

Property-level COV subscriptions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:meth:`~bac_py.client.Client.subscribe_cov_property` monitors a specific
property rather than the default COV properties for the object type:

.. code-block:: python

   await client.subscribe_cov_property(
       "192.168.1.100", "ai,1", "pv",
       process_id=2,
       cov_increment=0.5,  # notify when value changes by 0.5
       lifetime=3600,
   )
