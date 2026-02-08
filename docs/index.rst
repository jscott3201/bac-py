bac-py
======

Asynchronous BACnet protocol library for Python 3.13+.

bac-py implements ASHRAE Standard 135-2016 (BACnet) with an async-first
architecture built on Python's native ``asyncio`` framework. It provides both
client and server capabilities for BACnet/IP networks.

Features
--------

- **Full BACnet/IP support** per Annex J over UDP
- **Client and server** in a single library
- **Async-first** design using native ``asyncio``
- **Zero dependencies** for the core library
- **Complete object model** -- Device, Analog, Binary, MultiState, File, Schedule, TrendLog, and more
- **All standard services** -- property access, discovery, COV, device management, file access, object management, private transfer
- **Segmentation support** -- automatic segmented request/response handling
- **Type-safe** -- enums, frozen dataclasses, and type hints throughout

Quick Start
-----------

Read a property from a remote device::

   import asyncio
   from bac_py.app.application import BACnetApplication, DeviceConfig
   from bac_py.app.client import BACnetClient
   from bac_py.network.address import BACnetAddress
   from bac_py.types.enums import ObjectType, PropertyIdentifier
   from bac_py.types.primitives import ObjectIdentifier

   async def main():
       config = DeviceConfig(instance_number=999, interface="0.0.0.0")

       async with BACnetApplication(config) as app:
           client = BACnetClient(app)
           target = BACnetAddress(
               mac_address=bytes([192, 168, 1, 100, 0xBA, 0xC0])
           )

           ack = await client.read_property(
               target,
               ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
               PropertyIdentifier.PRESENT_VALUE,
           )
           print(f"Value: {ack.property_value.hex()}")

   asyncio.run(main())

.. toctree::
   :maxdepth: 2
   :caption: Contents

   api/index


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
