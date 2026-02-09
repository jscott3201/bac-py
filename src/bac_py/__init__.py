"""bac-py: Asynchronous BACnet/IP protocol library for Python 3.13+.

Typical usage::

    from bac_py import Client, DeviceConfig

    async with Client(DeviceConfig(instance_number=999)) as client:
        value = await client.read("192.168.1.100", "ai,1", "pv")
"""

__version__ = "0.1.0"

from bac_py.app.application import DeviceConfig
from bac_py.app.client import DiscoveredDevice
from bac_py.client import Client

__all__ = ["Client", "DeviceConfig", "DiscoveredDevice", "__version__"]
