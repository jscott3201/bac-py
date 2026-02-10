"""bac-py: Asynchronous BACnet/IP protocol library for Python 3.13+.

Typical usage::

    from bac_py import Client, DeviceConfig

    async with Client(DeviceConfig(instance_number=999)) as client:
        value = await client.read("192.168.1.100", "ai,1", "pv")
"""

__version__ = "0.1.0"

from bac_py.app.application import DeviceConfig, ForeignDeviceStatus
from bac_py.app.client import (
    BDTEntryInfo,
    DiscoveredDevice,
    FDTEntryInfo,
    RouterInfo,
    decode_cov_values,
)
from bac_py.client import Client
from bac_py.serialization import deserialize, serialize

__all__ = [
    "BDTEntryInfo",
    "Client",
    "DeviceConfig",
    "DiscoveredDevice",
    "FDTEntryInfo",
    "ForeignDeviceStatus",
    "RouterInfo",
    "__version__",
    "decode_cov_values",
    "deserialize",
    "serialize",
]
