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

To enable BACnet Secure Connect (BACnet/SC) support:

.. code-block:: bash

   pip install bac-py[secure]

Requirements
^^^^^^^^^^^^

- Python >= 3.13
- No runtime dependencies for the core library
- Optional: ``orjson`` (installed with the ``serialization`` extra)
- Optional: ``websockets`` and ``cryptography`` (installed with the ``secure``
  extra for BACnet/SC support)

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

See :ref:`reading-properties` for more read examples, or :doc:`guide/client-guide`
for the full client capabilities reference.


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
identifiers so you don't need to type out full names. Full hyphenated names
(``"analog-input,1"``, ``"present-value"``) and enum values
(``ObjectType.ANALOG_INPUT``, ``PropertyIdentifier.PRESENT_VALUE``) are always
accepted as well.

Object type aliases:

.. list-table::
   :header-rows: 1
   :widths: 15 35 15 35

   * - Alias
     - Object Type
     - Alias
     - Object Type
   * - ``ai``
     - analog-input
     - ``lo``
     - lighting-output
   * - ``ao``
     - analog-output
     - ``blo``
     - binary-lighting-output
   * - ``av``
     - analog-value
     - ``lc``
     - load-control
   * - ``lav``
     - large-analog-value
     - ``acc``
     - accumulator
   * - ``bi``
     - binary-input
     - ``pc``
     - pulse-converter
   * - ``bo``
     - binary-output
     - ``tmr``
     - timer
   * - ``bv``
     - binary-value
     - ``ee``
     - event-enrollment
   * - ``msi``
     - multi-state-input
     - ``ae``
     - alert-enrollment
   * - ``mso``
     - multi-state-output
     - ``nf``
     - notification-forwarder
   * - ``msv``
     - multi-state-value
     - ``avg``
     - averaging
   * - ``dev``
     - device
     - ``iv``
     - integer-value
   * - ``file``
     - file
     - ``piv``
     - positive-integer-value
   * - ``nc``
     - notification-class
     - ``csv``
     - characterstring-value
   * - ``np``
     - network-port
     - ``bsv``
     - bitstring-value
   * - ``cal``
     - calendar
     - ``osv``
     - octetstring-value
   * - ``cmd``
     - command
     - ``dv``
     - date-value
   * - ``ch``
     - channel
     - ``dtv``
     - datetime-value
   * - ``prog``
     - program
     - ``tv``
     - time-value
   * - ``sched``
     - schedule
     - ``sv``
     - structured-view
   * - ``tl``
     - trend-log
     - ``grp``
     - group
   * - ``tlm``
     - trend-log-multiple
     - ``gg``
     - global-group
   * - ``el``
     - event-log
     - ``lsp``
     - life-safety-point
   * - ``lp``
     - loop
     - ``lsz``
     - life-safety-zone
   * -
     -
     - ``ad``
     - access-door
   * -
     -
     - ``ap``
     - access-point
   * -
     -
     - ``ar``
     - audit-reporter
   * -
     -
     - ``al``
     - audit-log

Property identifier aliases:

.. list-table::
   :header-rows: 1
   :widths: 18 32 18 32

   * - Alias
     - Property
     - Alias
     - Property
   * - ``pv``
     - present-value
     - ``polarity``
     - polarity
   * - ``name``
     - object-name
     - ``active-text``
     - active-text
   * - ``type``
     - object-type
     - ``inactive-text``
     - inactive-text
   * - ``desc``
     - description
     - ``num-states``
     - number-of-states
   * - ``units``
     - units
     - ``state-text``
     - state-text
   * - ``status``
     - status-flags
     - ``event-enable``
     - event-enable
   * - ``oos``
     - out-of-service
     - ``acked-transitions``
     - acked-transitions
   * - ``reliability``
     - reliability
     - ``notify-type``
     - notify-type
   * - ``event-state``
     - event-state
     - ``time-delay``
     - time-delay
   * - ``list``
     - object-list
     - ``notify-class``
     - notification-class
   * - ``prop-list``
     - property-list
     - ``limit-enable``
     - limit-enable
   * - ``profile-name``
     - profile-name
     - ``log-buffer``
     - log-buffer
   * - ``priority``
     - priority-array
     - ``record-count``
     - record-count
   * - ``relinquish``
     - relinquish-default
     - ``enable``
     - log-enable
   * - ``min``
     - min-pres-value
     - ``weekly-schedule``
     - weekly-schedule
   * - ``max``
     - max-pres-value
     - ``exception-schedule``
     - exception-schedule
   * - ``res``
     - resolution
     - ``schedule-default``
     - schedule-default
   * - ``cov-inc``
     - cov-increment
     - ``system-status``
     - system-status
   * - ``deadband``
     - deadband
     - ``vendor-name``
     - vendor-name
   * - ``high-limit``
     - high-limit
     - ``vendor-id``
     - vendor-identifier
   * - ``low-limit``
     - low-limit
     - ``model-name``
     - model-name
   * -
     -
     - ``firmware-rev``
     - firmware-revision
   * -
     -
     - ``app-version``
     - application-software-version
   * -
     -
     - ``max-apdu``
     - max-apdu-length-accepted
   * -
     -
     - ``seg-supported``
     - segmentation-supported
   * -
     -
     - ``db-revision``
     - database-revision
   * -
     -
     - ``protocol-version``
     - protocol-version
   * -
     -
     - ``protocol-revision``
     - protocol-revision


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


.. _debugging-logging-quickstart:

Debugging and Logging
---------------------

bac-py includes structured logging throughout the stack using Python's standard
:mod:`logging` module. Enable it to see what's happening under the hood:

.. code-block:: python

   import logging

   # Show lifecycle events (start, stop, subscriptions, etc.)
   logging.basicConfig(
       level=logging.INFO,
       format="%(asctime)s %(name)s %(levelname)s %(message)s",
   )

   # Or for detailed protocol traces
   logging.basicConfig(level=logging.DEBUG)

You can target specific modules to reduce noise:

.. code-block:: python

   # Only debug client operations
   logging.getLogger("bac_py.app.client").setLevel(logging.DEBUG)

See :doc:`guide/debugging-logging` for the full logger hierarchy reference,
practical debugging recipes, and file logging configuration.


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
:ref:`server-mode` for server examples and :ref:`protocol-level-api` for
client-side protocol-level usage.

The ``Client`` wrapper exposes both levels. All ``BACnetClient`` protocol-level
methods are available alongside the convenience methods, and the underlying
``BACnetApplication`` is accessible via ``client.app``.
