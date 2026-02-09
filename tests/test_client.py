"""Tests for the unified Client class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bac_py.app.application import DeviceConfig
from bac_py.client import Client
from bac_py.encoding.primitives import (
    encode_application_character_string,
    encode_application_real,
)
from bac_py.services.read_property import ReadPropertyACK
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestClientLifecycle:
    def test_default_config(self):
        client = Client()
        assert client._config.instance_number == 999
        assert client._config.interface == "0.0.0.0"
        assert client._config.port == 0xBAC0

    def test_custom_kwargs(self):
        client = Client(instance_number=1234, interface="10.0.0.1", port=47809)
        assert client._config.instance_number == 1234
        assert client._config.interface == "10.0.0.1"
        assert client._config.port == 47809

    def test_config_overrides_kwargs(self):
        config = DeviceConfig(instance_number=5678, interface="192.168.1.1")
        client = Client(config, instance_number=1234)
        assert client._config.instance_number == 5678
        assert client._config.interface == "192.168.1.1"

    def test_app_property_before_start_raises(self):
        client = Client()
        with pytest.raises(RuntimeError, match="Client not started"):
            _ = client.app

    def test_method_before_start_raises(self):
        client = Client()
        with pytest.raises(RuntimeError, match="Client not started"):
            asyncio.get_event_loop().run_until_complete(client.read("192.168.1.100", "ai,1", "pv"))

    @patch("bac_py.client.BACnetApplication")
    def test_context_manager_lifecycle(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run():
            async with Client() as client:
                assert client._app is mock_app
                assert client._client is not None
                mock_app.start.assert_called_once()
            mock_app.stop.assert_called_once()
            assert client._app is None
            assert client._client is None

        asyncio.get_event_loop().run_until_complete(run())

    @patch("bac_py.client.BACnetApplication")
    def test_app_property_after_start(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run():
            async with Client() as client:
                assert client.app is mock_app

        asyncio.get_event_loop().run_until_complete(run())

    @patch("bac_py.client.BACnetApplication")
    def test_stop_on_exception(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        async def run():
            with pytest.raises(ValueError, match="boom"):
                async with Client():
                    raise ValueError("boom")
            mock_app.stop.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())


class TestClientDelegation:
    """Test that Client methods delegate to BACnetClient."""

    @patch("bac_py.client.BACnetApplication")
    def test_read_delegates(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        mock_app.confirmed_request = AsyncMock(return_value=ack.encode())

        async def run():
            async with Client() as client:
                result = await client.read("192.168.1.100", "ai,1", "pv")
                assert isinstance(result, float)
                assert result == pytest.approx(72.5)

        asyncio.get_event_loop().run_until_complete(run())

    @patch("bac_py.client.BACnetApplication")
    def test_write_delegates(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app.confirmed_request = AsyncMock(return_value=b"")
        mock_app_cls.return_value = mock_app

        async def run():
            async with Client() as client:
                await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
                mock_app.confirmed_request.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())

    @patch("bac_py.client.BACnetApplication")
    def test_read_multiple_delegates(self, mock_app_cls):
        from bac_py.services.read_property_multiple import (
            ReadAccessResult,
            ReadPropertyMultipleACK,
            ReadResultElement,
        )

        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(72.5),
                        ),
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.OBJECT_NAME,
                            property_value=encode_application_character_string("Zone Temp"),
                        ),
                    ],
                ),
            ]
        )
        mock_app.confirmed_request = AsyncMock(return_value=ack.encode())

        async def run():
            async with Client() as client:
                result = await client.read_multiple(
                    "192.168.1.100",
                    {"ai,1": ["pv", "name"]},
                )
                assert "analog-input,1" in result
                props = result["analog-input,1"]
                assert props["present-value"] == pytest.approx(72.5)
                assert props["object-name"] == "Zone Temp"

        asyncio.get_event_loop().run_until_complete(run())
