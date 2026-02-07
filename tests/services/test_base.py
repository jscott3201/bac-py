import pytest

from bac_py.network.address import BACnetAddress
from bac_py.services.base import ServiceRegistry
from bac_py.services.errors import BACnetRejectError
from bac_py.types.enums import RejectReason


class TestServiceRegistry:
    def test_register_and_dispatch_confirmed(self):
        registry = ServiceRegistry()
        called_with = {}

        async def handler(sc: int, data: bytes, source: BACnetAddress) -> bytes:
            called_with["sc"] = sc
            called_with["data"] = data
            return b"\x01\x02"

        registry.register_confirmed(12, handler)
        import asyncio

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        result = asyncio.get_event_loop().run_until_complete(
            registry.dispatch_confirmed(12, b"\xaa", source)
        )
        assert result == b"\x01\x02"
        assert called_with["sc"] == 12
        assert called_with["data"] == b"\xaa"

    def test_dispatch_confirmed_unknown_rejects(self):
        registry = ServiceRegistry()
        import asyncio

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        with pytest.raises(BACnetRejectError) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                registry.dispatch_confirmed(99, b"", source)
            )
        assert exc_info.value.reason == RejectReason.UNRECOGNIZED_SERVICE

    def test_register_and_dispatch_unconfirmed(self):
        registry = ServiceRegistry()
        called = []

        async def handler(sc: int, data: bytes, source: BACnetAddress) -> None:
            called.append((sc, data))

        registry.register_unconfirmed(8, handler)
        import asyncio

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        asyncio.get_event_loop().run_until_complete(
            registry.dispatch_unconfirmed(8, b"\xbb", source)
        )
        assert len(called) == 1
        assert called[0] == (8, b"\xbb")

    def test_dispatch_unconfirmed_unknown_is_silent(self):
        registry = ServiceRegistry()
        import asyncio

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        # Should not raise
        asyncio.get_event_loop().run_until_complete(registry.dispatch_unconfirmed(99, b"", source))

    def test_replace_confirmed_handler(self):
        registry = ServiceRegistry()

        async def handler1(sc: int, data: bytes, source: BACnetAddress) -> bytes:
            return b"\x01"

        async def handler2(sc: int, data: bytes, source: BACnetAddress) -> bytes:
            return b"\x02"

        registry.register_confirmed(12, handler1)
        registry.register_confirmed(12, handler2)

        import asyncio

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        result = asyncio.get_event_loop().run_until_complete(
            registry.dispatch_confirmed(12, b"", source)
        )
        assert result == b"\x02"

    def test_confirmed_handler_returns_none_for_simple_ack(self):
        registry = ServiceRegistry()

        async def handler(sc: int, data: bytes, source: BACnetAddress) -> None:
            return None

        registry.register_confirmed(15, handler)
        import asyncio

        source = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        result = asyncio.get_event_loop().run_until_complete(
            registry.dispatch_confirmed(15, b"", source)
        )
        assert result is None
