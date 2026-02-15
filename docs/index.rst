bac-py
======

Asynchronous BACnet/IP protocol library for Python 3.13+.

bac-py implements ASHRAE Standard 135-2020 (BACnet) with an async-first
architecture built on Python's native ``asyncio`` framework. It provides both
client and server capabilities across five transport types -- BACnet/IP (UDP),
IPv6, Ethernet 802.3, BBMD, and BACnet Secure Connect -- with zero required
dependencies.

.. code-block:: python

   import asyncio
   from bac_py import Client

   async def main():
       async with Client(instance_number=999) as client:
           value = await client.read("192.168.1.100", "ai,1", "pv")
           print(f"Temperature: {value}")

   asyncio.run(main())

Head to :doc:`getting-started` for installation and first steps, or browse
the :doc:`guide/reading-writing` to see what bac-py can do. For transport
configuration (BBMD, routers, IPv6, Secure Connect), see
:doc:`guide/transport-setup`.

.. toctree::
   :caption: Getting Started
   :maxdepth: 2

   getting-started
   features

.. toctree::
   :caption: User Guide
   :maxdepth: 2

   guide/client-guide
   guide/reading-writing
   guide/discovery-networking
   guide/transport-setup
   guide/server-mode
   guide/events-alarms
   guide/device-management
   guide/secure-connect
   guide/debugging-logging
   guide/security
   guide/benchmarks
   guide/examples

.. toctree::
   :caption: API Reference
   :maxdepth: 2

   api/app/index
   api/types
   api/services/index
   api/objects/index
   api/encoding
   api/network
   api/transport
   api/segmentation
   api/conformance
   api/serialization

.. toctree::
   :caption: Project
   :maxdepth: 1

   changelog


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
