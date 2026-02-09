"""Tests for DiscoveredDevice and the discover() convenience method."""

import asyncio
from unittest.mock import MagicMock

import pytest

from bac_py.app.client import BACnetClient, DiscoveredDevice
from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.services.who_is import IAmRequest
from bac_py.types.enums import ObjectType, Segmentation, UnconfirmedServiceChoice
from bac_py.types.primitives import ObjectIdentifier

PEER_MAC = BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
PEER = BACnetAddress(mac_address=PEER_MAC)


class TestDiscoveredDevice:
    def test_basic_fields(self):
        dev = DiscoveredDevice(
            address=PEER,
            instance=100,
            vendor_id=42,
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
        )
        assert dev.instance == 100
        assert dev.vendor_id == 42
        assert dev.max_apdu_length == 1476
        assert dev.segmentation_supported == Segmentation.BOTH
        assert dev.address is PEER

    def test_address_str(self):
        dev = DiscoveredDevice(
            address=PEER,
            instance=100,
            vendor_id=42,
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
        )
        assert dev.address_str == "192.168.1.100:47808"

    def test_address_str_with_network(self):
        addr = BACnetAddress(network=5, mac_address=PEER_MAC)
        dev = DiscoveredDevice(
            address=addr,
            instance=200,
            vendor_id=1,
            max_apdu_length=480,
            segmentation_supported=Segmentation.NONE,
        )
        assert dev.address_str == "5:192.168.1.100:47808"

    def test_repr(self):
        dev = DiscoveredDevice(
            address=PEER,
            instance=100,
            vendor_id=42,
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
        )
        assert repr(dev) == "DiscoveredDevice(instance=100, address='192.168.1.100:47808')"

    def test_frozen(self):
        dev = DiscoveredDevice(
            address=PEER,
            instance=100,
            vendor_id=42,
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
        )
        with pytest.raises(AttributeError):
            dev.instance = 200  # type: ignore[misc]

    def test_equality(self):
        dev1 = DiscoveredDevice(
            address=PEER,
            instance=100,
            vendor_id=42,
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
        )
        dev2 = DiscoveredDevice(
            address=PEER,
            instance=100,
            vendor_id=42,
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
        )
        assert dev1 == dev2


class TestDiscover:
    def _make_app(self):
        app = MagicMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    def _make_iam(self, instance: int, vendor_id: int = 42) -> IAmRequest:
        return IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, instance),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=vendor_id,
        )

    def test_discover_returns_discovered_devices(self):
        app = self._make_app()
        client = BACnetClient(app)

        iam1 = self._make_iam(100)
        iam2 = self._make_iam(200, vendor_id=99)
        source1 = BACnetAddress(mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode())
        source2 = BACnetAddress(mac_address=BIPAddress(host="192.168.1.200", port=0xBAC0).encode())

        # Capture the handler so we can simulate I-Am responses
        def capture_handler(service_choice, handler):
            # Simulate two I-Am responses arriving
            handler(iam1.encode(), source1)
            handler(iam2.encode(), source2)

        app.register_temporary_handler.side_effect = capture_handler

        async def run():
            devices = await client.discover(timeout=0.01)
            assert len(devices) == 2

            assert isinstance(devices[0], DiscoveredDevice)
            assert devices[0].instance == 100
            assert devices[0].vendor_id == 42
            assert devices[0].max_apdu_length == 1476
            assert devices[0].segmentation_supported == Segmentation.BOTH
            assert devices[0].address == source1
            assert devices[0].address_str == "192.168.1.100:47808"

            assert devices[1].instance == 200
            assert devices[1].vendor_id == 99
            assert devices[1].address == source2

        asyncio.get_event_loop().run_until_complete(run())

    def test_discover_with_limits(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.discover(low_limit=100, high_limit=200, timeout=0.01)
            # Verify the Who-Is was sent
            app.unconfirmed_request.assert_called_once()
            call_kwargs = app.unconfirmed_request.call_args.kwargs
            assert call_kwargs["service_choice"] == UnconfirmedServiceChoice.WHO_IS
            # Verify service data includes the range limits
            from bac_py.services.who_is import WhoIsRequest

            req = WhoIsRequest.decode(call_kwargs["service_data"])
            assert req.low_limit == 100
            assert req.high_limit == 200

        asyncio.get_event_loop().run_until_complete(run())

    def test_discover_no_responses(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            devices = await client.discover(timeout=0.01)
            assert devices == []

        asyncio.get_event_loop().run_until_complete(run())

    def test_discover_handler_registered_and_unregistered(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.discover(timeout=0.01)
            app.register_temporary_handler.assert_called_once()
            reg_args = app.register_temporary_handler.call_args
            assert reg_args[0][0] == UnconfirmedServiceChoice.I_AM

            app.unregister_temporary_handler.assert_called_once()
            unreg_args = app.unregister_temporary_handler.call_args
            assert unreg_args[0][0] == UnconfirmedServiceChoice.I_AM

        asyncio.get_event_loop().run_until_complete(run())

    def test_discover_drops_malformed_iam(self):
        app = self._make_app()
        client = BACnetClient(app)

        def capture_handler(service_choice, handler):
            # One valid, one malformed
            valid_iam = self._make_iam(100)
            source = BACnetAddress(
                mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
            )
            handler(valid_iam.encode(), source)
            handler(b"\xff\xff", source)  # malformed

        app.register_temporary_handler.side_effect = capture_handler

        async def run():
            devices = await client.discover(timeout=0.01)
            assert len(devices) == 1
            assert devices[0].instance == 100

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_still_returns_iam_requests(self):
        """Verify the original who_is() method still works and returns IAmRequest."""
        app = self._make_app()
        client = BACnetClient(app)

        iam = self._make_iam(100)
        source = BACnetAddress(mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode())

        def capture_handler(service_choice, handler):
            handler(iam.encode(), source)

        app.register_temporary_handler.side_effect = capture_handler

        async def run():
            responses = await client.who_is(timeout=0.01)
            assert len(responses) == 1
            assert isinstance(responses[0], IAmRequest)
            assert responses[0].object_identifier.instance_number == 100

        asyncio.get_event_loop().run_until_complete(run())
