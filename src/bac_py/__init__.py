"""bac-py: Asynchronous BACnet/IP protocol library for Python 3.13+.

Typical usage::

    from bac_py import Client, DeviceConfig

    async with Client(DeviceConfig(instance_number=999)) as client:
        value = await client.read("192.168.1.100", "ai,1", "pv")
"""

__version__ = "1.5.0"

from bac_py.app.application import (
    BACnetApplication,
    DeviceConfig,
    ForeignDeviceStatus,
    RouterConfig,
    RouterPortConfig,
)
from bac_py.app.client import (
    BackupData,
    BDTEntryInfo,
    DiscoveredDevice,
    FDTEntryInfo,
    RouterInfo,
    UnconfiguredDevice,
    decode_cov_values,
)
from bac_py.app.server import DefaultServerHandlers
from bac_py.client import Client
from bac_py.objects.device import DeviceObject
from bac_py.serialization import deserialize, serialize

__all__ = [
    "BACnetApplication",
    "BDTEntryInfo",
    "BackupData",
    "Client",
    "DefaultServerHandlers",
    "DeviceConfig",
    "DeviceObject",
    "DiscoveredDevice",
    "FDTEntryInfo",
    "ForeignDeviceStatus",
    "RouterConfig",
    "RouterInfo",
    "RouterPortConfig",
    "SCTransport",
    "SCTransportConfig",
    "UnconfiguredDevice",
    "__version__",
    "decode_cov_values",
    "deserialize",
    "serialize",
]


def __getattr__(name: str) -> object:
    """Lazy-load optional SC transport (requires ``pip install bac-py[secure]``)."""
    if name in ("SCTransport", "SCTransportConfig"):
        from bac_py.transport.sc import SCTransport, SCTransportConfig

        globals()["SCTransport"] = SCTransport
        globals()["SCTransportConfig"] = SCTransportConfig
        return globals()[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
