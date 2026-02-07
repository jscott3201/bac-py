import asyncio

import pytest

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.network.address import BACnetAddress


class TestDeviceConfig:
    def test_defaults(self):
        cfg = DeviceConfig(instance_number=1)
        assert cfg.instance_number == 1
        assert cfg.name == "bac-py"
        assert cfg.port == 0xBAC0
        assert cfg.apdu_timeout == 6000
        assert cfg.apdu_retries == 3
        assert cfg.max_apdu_length == 1476
        assert cfg.max_segments is None

    def test_custom_values(self):
        cfg = DeviceConfig(
            instance_number=42,
            name="test-device",
            port=47809,
            apdu_timeout=3000,
        )
        assert cfg.instance_number == 42
        assert cfg.name == "test-device"
        assert cfg.port == 47809
        assert cfg.apdu_timeout == 3000


class TestBACnetApplication:
    def test_init(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        assert app.config is cfg
        assert app.object_db is not None
        assert app.service_registry is not None

    def test_confirmed_request_before_start_raises(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        async def run():
            with pytest.raises(RuntimeError, match="not started"):
                await app.confirmed_request(dest, 12, b"\x01")

        asyncio.get_event_loop().run_until_complete(run())

    def test_unconfirmed_request_before_start_raises(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        with pytest.raises(RuntimeError, match="not started"):
            app.unconfirmed_request(dest, 8, b"")

    def test_register_temporary_handler(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)

        def handler(data, source):
            return None

        app.register_temporary_handler(0, handler)
        # Should not raise when unregistering
        app.unregister_temporary_handler(0, handler)

    def test_unregister_nonexistent_handler(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)

        def handler(data, source):
            return None

        # Should not raise
        app.unregister_temporary_handler(0, handler)
