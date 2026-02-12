.. _getting-started:

Getting Started
===============

.. _installation:

Installation
------------

Install bac-py from PyPI:

.. code-block:: bash

   pip install bac-py

To enable JSON serialization support (using ``orjson``):

.. code-block:: bash

   pip install bac-py[serialization]

Requirements
^^^^^^^^^^^^

- Python >= 3.13
- No runtime dependencies for the core library
- Optional: ``orjson`` (installed with the ``serialization`` extra)

Development Setup
^^^^^^^^^^^^^^^^^

.. code-block:: bash

   git clone https://github.com/jscott3201/bac-py.git
   cd bac-py
   uv sync --group dev


Your First Read
---------------

The simplest way to read a value from a BACnet device:

.. code-block:: python

   import asyncio
   from bac_py import Client

   async def main():
       async with Client(instance_number=999) as client:
           value = await client.read("192.168.1.100", "ai,1", "pv")
           print(f"Temperature: {value}")

   asyncio.run(main())

The :class:`~bac_py.client.Client` class is an async context manager that
handles starting and stopping the underlying BACnet application. It binds a
UDP socket, assigns your device a BACnet instance number, and is ready to
communicate.

See :ref:`reading-properties` for more read examples.


Your First Write
----------------

Writing a value is equally straightforward. bac-py automatically encodes Python
values to the correct BACnet application tag:

.. code-block:: python

   import asyncio
   from bac_py import Client

   async def main():
       async with Client(instance_number=999) as client:
           await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
           print("Write complete.")

   asyncio.run(main())

The ``priority`` parameter sets the BACnet command priority (1--16). Priority 8
is commonly used for manual operator commands.

See :ref:`writing-properties` for more write examples including the full
:ref:`encoding rules table <encoding-rules>`.


.. _string-aliases:

String Aliases
--------------

The convenience API accepts short aliases for common object types and property
identifiers so you don't need to type out full names.

Object type aliases:

.. list-table::
   :header-rows: 1
   :widths: 15 35

   * - Alias
     - Object Type
   * - ``ai``
     - analog-input
   * - ``ao``
     - analog-output
   * - ``av``
     - analog-value
   * - ``bi``
     - binary-input
   * - ``bo``
     - binary-output
   * - ``bv``
     - binary-value
   * - ``msi``
     - multi-state-input
   * - ``mso``
     - multi-state-output
   * - ``msv``
     - multi-state-value
   * - ``dev``
     - device

Property identifier aliases:

.. list-table::
   :header-rows: 1
   :widths: 15 35

   * - Alias
     - Property
   * - ``pv``
     - present-value
   * - ``name``
     - object-name
   * - ``desc``
     - description
   * - ``units``
     - units
   * - ``status``
     - status-flags
   * - ``oos``
     - out-of-service
   * - ``cov-inc``
     - cov-increment
   * - ``reliability``
     - reliability

Full hyphenated names (``"analog-input,1"``, ``"present-value"``) and enum
values (``ObjectType.ANALOG_INPUT``, ``PropertyIdentifier.PRESENT_VALUE``)
are always accepted as well.


.. _addressing:

Addressing
----------

The convenience API accepts device addresses as plain strings:

.. code-block:: python

   # IP only (default BACnet port 47808)
   await client.read("192.168.1.100", "ai,1", "pv")

   # IP with explicit port
   await client.read("192.168.1.100:47808", "ai,1", "pv")

   # Routed address (network:ip:port)
   await client.read("5:192.168.1.100:47808", "ai,1", "pv")

   # Ethernet MAC address (colon-separated hex)
   addr = parse_address("aa:bb:cc:dd:ee:ff")

   # Remote Ethernet address on network 5
   addr = parse_address("5:aa:bb:cc:dd:ee:ff")

   # Remote MS/TP or non-IP station (network:hex_mac)
   addr = parse_address("4352:01")       # 1-byte MS/TP address on network 4352
   addr = parse_address("100:0a0b")      # 2-byte address on network 100


.. _configuration:

Configuration
-------------

:class:`~bac_py.app.application.DeviceConfig` controls device identity and
network parameters:

.. code-block:: python

   from bac_py import DeviceConfig

   config = DeviceConfig(
       instance_number=999,          # Device instance (0-4194302)
       name="bac-py",                # Device name
       vendor_name="bac-py",         # Vendor name
       vendor_id=0,                  # ASHRAE vendor ID
       interface="0.0.0.0",          # IP address to bind
       port=0xBAC0,                  # UDP port (47808)
       max_apdu_length=1476,         # Max APDU size
       apdu_timeout=6000,            # Request timeout (ms)
       apdu_retries=3,               # Retry count
       max_segments=None,            # Max segments (None = unlimited)
   )

   async with Client(config) as client:
       value = await client.read("192.168.1.100", "ai,1", "pv")

For simple client use cases, you can skip ``DeviceConfig`` and pass common
options directly:

.. code-block:: python

   async with Client(instance_number=999, interface="192.168.1.50") as client:
       ...


.. _error-handling:

Error Handling
--------------

All client methods raise from a common exception hierarchy:

.. code-block:: python

   from bac_py.services.errors import (
       BACnetBaseError,       # Base for all BACnet errors
       BACnetError,           # Error-PDU (error_class, error_code)
       BACnetRejectError,     # Reject-PDU (reason)
       BACnetAbortError,      # Abort-PDU (reason)
       BACnetTimeoutError,    # No response after all retries
   )

Example:

.. code-block:: python

   from bac_py.services.errors import BACnetError, BACnetTimeoutError

   try:
       value = await client.read("192.168.1.100", "ai,1", "pv")
   except BACnetTimeoutError:
       print("Device did not respond")
   except BACnetError as e:
       print(f"BACnet error: class={e.error_class}, code={e.error_code}")


.. _two-api-levels:

Two API Levels
--------------

bac-py exposes two API levels. Use whichever fits your needs:

:class:`~bac_py.client.Client` -- simplified wrapper for common client tasks.
Accepts string addresses, string object/property identifiers, and Python
values. Ideal for scripts, integrations, and most client-side work.

:class:`~bac_py.app.application.BACnetApplication` +
:class:`~bac_py.app.client.BACnetClient` -- full protocol-level access. Use
this when you need server handlers, router mode, custom service registration,
raw encoded bytes, or direct access to the transport and network layers. See
:ref:`protocol-level-api` for examples.

The ``Client`` wrapper exposes both levels. All ``BACnetClient`` protocol-level
methods are available alongside the convenience methods, and the underlying
``BACnetApplication`` is accessible via ``client.app``.
