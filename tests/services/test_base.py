import pytest

from bac_py.network.address import BACnetAddress
from bac_py.services.base import ServiceRegistry
from bac_py.services.errors import BACnetRejectError
from bac_py.types.enums import RejectReason


class TestServiceRegistry:
    async def test_register_and_dispatch_confirmed(self):
        registry = ServiceRegistry()
        called_with = {}

        async def handler(sc: int, data: bytes, source: BACnetAddress) -> bytes:
            called_with["sc"] = sc
            called_with["data"] = data
            return b"\x01\x02"

        registry.register_confirmed(12, handler)

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        result = await registry.dispatch_confirmed(12, b"\xaa", source)
        assert result == b"\x01\x02"
        assert called_with["sc"] == 12
        assert called_with["data"] == b"\xaa"

    async def test_dispatch_confirmed_unknown_rejects(self):
        registry = ServiceRegistry()

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        with pytest.raises(BACnetRejectError) as exc_info:
            await registry.dispatch_confirmed(99, b"", source)
        assert exc_info.value.reason == RejectReason.UNRECOGNIZED_SERVICE

    async def test_register_and_dispatch_unconfirmed(self):
        registry = ServiceRegistry()
        called = []

        async def handler(sc: int, data: bytes, source: BACnetAddress) -> None:
            called.append((sc, data))

        registry.register_unconfirmed(8, handler)

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        await registry.dispatch_unconfirmed(8, b"\xbb", source)
        assert len(called) == 1
        assert called[0] == (8, b"\xbb")

    async def test_dispatch_unconfirmed_unknown_is_silent(self):
        registry = ServiceRegistry()

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        # Should not raise
        await registry.dispatch_unconfirmed(99, b"", source)

    async def test_replace_confirmed_handler(self):
        registry = ServiceRegistry()

        async def handler1(sc: int, data: bytes, source: BACnetAddress) -> bytes:
            return b"\x01"

        async def handler2(sc: int, data: bytes, source: BACnetAddress) -> bytes:
            return b"\x02"

        registry.register_confirmed(12, handler1)
        registry.register_confirmed(12, handler2)

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        result = await registry.dispatch_confirmed(12, b"", source)
        assert result == b"\x02"

    async def test_confirmed_handler_returns_none_for_simple_ack(self):
        registry = ServiceRegistry()

        async def handler(sc: int, data: bytes, source: BACnetAddress) -> None:
            return None

        registry.register_confirmed(15, handler)

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        result = await registry.dispatch_confirmed(15, b"", source)
        assert result is None
