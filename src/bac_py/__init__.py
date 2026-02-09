"""bac-py: Asynchronous BACnet/IP protocol library for Python 3.13+.

Typical usage::

    from bac_py.app import BACnetApplication, DeviceConfig

    config = DeviceConfig(instance_number=1234)
    app = BACnetApplication(config)
    await app.run()
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
