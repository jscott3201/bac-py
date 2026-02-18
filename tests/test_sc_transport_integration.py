"""Tests for SC transport integration with BACnetApplication and Client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bac_py.app.application import (
    BACnetApplication,
    DeviceConfig,
    RouterConfig,
    RouterPortConfig,
)
from bac_py.client import Client
from bac_py.transport.sc import SCTransportConfig


def _make_mock_sc_transport():
    """Create a mock SCTransport with required attributes."""
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    transport.local_mac = b"\x01\x02\x03\x04\x05\x06"
    transport.max_npdu_length = 1497
    transport.on_receive = MagicMock()
    transport.hub_connector = MagicMock()
    transport.hub_connector.wait_connected = AsyncMock(return_value=True)
    return transport


# -------------------------------------------------------------------
# DeviceConfig validation
# -------------------------------------------------------------------


class TestDeviceConfigSCValidation:
    def test_sc_config_and_ipv6_mutually_exclusive(self):
        with pytest.raises(ValueError, match="sc_config and ipv6 are mutually exclusive"):
            DeviceConfig(
                instance_number=1,
                sc_config=SCTransportConfig(primary_hub_uri="wss://hub:4443"),
                ipv6=True,
            )

    def test_sc_config_alone_ok(self):
        cfg = DeviceConfig(
            instance_number=1,
            sc_config=SCTransportConfig(primary_hub_uri="wss://hub:4443"),
        )
        assert cfg.sc_config is not None
        assert cfg.sc_config.primary_hub_uri == "wss://hub:4443"
        assert cfg.ipv6 is False

    def test_sc_config_none_by_default(self):
        cfg = DeviceConfig(instance_number=1)
        assert cfg.sc_config is None


# -------------------------------------------------------------------
# RouterPortConfig with sc_config
# -------------------------------------------------------------------


class TestRouterPortConfigSC:
    def test_sc_config_field(self):
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        rpc = RouterPortConfig(port_id=1, network_number=100, sc_config=sc_cfg)
        assert rpc.sc_config is sc_cfg

    def test_sc_config_none_by_default(self):
        rpc = RouterPortConfig(port_id=1, network_number=100)
        assert rpc.sc_config is None


# -------------------------------------------------------------------
# SCTransportConfig new fields
# -------------------------------------------------------------------


class TestSCTransportConfigFields:
    def test_network_number_default(self):
        cfg = SCTransportConfig()
        assert cfg.network_number is None

    def test_network_number_set(self):
        cfg = SCTransportConfig(network_number=5)
        assert cfg.network_number == 5

    def test_connect_timeout_default(self):
        cfg = SCTransportConfig()
        assert cfg.connect_timeout == 15.0

    def test_connect_timeout_custom(self):
        cfg = SCTransportConfig(connect_timeout=30.0)
        assert cfg.connect_timeout == 30.0


# -------------------------------------------------------------------
# _start_sc_mode (non-router)
# -------------------------------------------------------------------


class TestStartSCMode:
    async def test_start_sc_mode_wires_transport(self):
        """SC transport is started, connected, and wired into the app."""
        sc_cfg = SCTransportConfig(
            primary_hub_uri="wss://hub:4443",
            network_number=1,
        )
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                assert app._transport is mock_t
                assert app._network is not None
                assert app._client_tsm is not None
                assert app._server_tsm is not None
                assert app._running is True
                mock_t.start.assert_awaited_once()
                mock_t.hub_connector.wait_connected.assert_awaited_once_with(timeout=15.0)
            finally:
                await app.stop()

    async def test_start_sc_mode_no_hub_uri(self):
        """SC transport without hub URI skips connection wait."""
        sc_cfg = SCTransportConfig()  # no primary_hub_uri
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                assert app._transport is mock_t
                mock_t.start.assert_awaited_once()
                mock_t.hub_connector.wait_connected.assert_not_awaited()
            finally:
                await app.stop()

    async def test_start_sc_mode_connection_failure(self):
        """ConnectionError raised when hub connection times out."""
        sc_cfg = SCTransportConfig(
            primary_hub_uri="wss://hub:4443",
            connect_timeout=5.0,
        )
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()
        mock_t.hub_connector.wait_connected = AsyncMock(return_value=False)

        with (
            patch("bac_py.transport.sc.SCTransport", return_value=mock_t),
            pytest.raises(ConnectionError, match="Failed to connect to SC hub"),
        ):
            await app.start()

        mock_t.stop.assert_awaited_once()

    async def test_start_sc_mode_custom_timeout(self):
        """Custom connect_timeout is passed to wait_connected."""
        sc_cfg = SCTransportConfig(
            primary_hub_uri="wss://hub:4443",
            connect_timeout=30.0,
        )
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                mock_t.hub_connector.wait_connected.assert_awaited_once_with(timeout=30.0)
            finally:
                await app.stop()

    async def test_start_sc_mode_network_number(self):
        """Network number is passed to NetworkLayer."""
        sc_cfg = SCTransportConfig(
            primary_hub_uri="wss://hub:4443",
            network_number=42,
        )
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                assert app._network is not None
                assert app._network._network_number == 42
            finally:
                await app.stop()

    async def test_stop_calls_sc_transport_stop(self):
        """stop() calls transport.stop() for SC transport."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            await app.stop()
            mock_t.stop.assert_awaited_once()


# -------------------------------------------------------------------
# Router mode with SC port
# -------------------------------------------------------------------


class TestRouterModeWithSCPort:
    async def test_router_with_sc_port(self):
        """An SC port can be configured alongside BIP ports in router mode."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        router_config = RouterConfig(
            ports=[
                RouterPortConfig(port_id=1, network_number=100),
                RouterPortConfig(port_id=2, network_number=200, sc_config=sc_cfg),
            ],
            application_port_id=1,
        )
        config = DeviceConfig(instance_number=1, router_config=router_config)
        app = BACnetApplication(config)

        mock_bip = MagicMock()
        mock_bip.start = AsyncMock()
        mock_bip.stop = AsyncMock()
        mock_bip.local_mac = b"\x7f\x00\x00\x01\xba\xc0"
        mock_bip.max_npdu_length = 1497
        mock_bip.on_receive = MagicMock()
        mock_bip.foreign_device = None

        mock_sc = _make_mock_sc_transport()

        with (
            patch("bac_py.app.application.BIPTransport", return_value=mock_bip),
            patch("bac_py.transport.sc.SCTransport", return_value=mock_sc),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                assert app._router is mock_router_instance
                # Both transports started
                mock_bip.start.assert_awaited_once()
                mock_sc.start.assert_awaited_once()
                mock_sc.hub_connector.wait_connected.assert_awaited_once()
                # Router created with 2 ports
                call_args = mock_router_cls.call_args
                ports_arg = call_args[0][0]
                assert len(ports_arg) == 2
                # Both transports tracked
                assert len(app._transports) == 2
            finally:
                await app.stop()

    async def test_router_sc_port_connection_failure(self):
        """Router start fails if SC hub connection fails."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        router_config = RouterConfig(
            ports=[
                RouterPortConfig(port_id=1, network_number=100, sc_config=sc_cfg),
            ],
            application_port_id=1,
        )
        config = DeviceConfig(instance_number=1, router_config=router_config)
        app = BACnetApplication(config)

        mock_sc = _make_mock_sc_transport()
        mock_sc.hub_connector.wait_connected = AsyncMock(return_value=False)

        with (
            patch("bac_py.transport.sc.SCTransport", return_value=mock_sc),
            pytest.raises(ConnectionError, match="Failed to connect to SC hub"),
        ):
            await app.start()

        mock_sc.stop.assert_awaited_once()


# -------------------------------------------------------------------
# Foreign device methods with SC transport
# -------------------------------------------------------------------


class TestForeignDeviceWithSCTransport:
    async def test_register_foreign_device_raises_for_sc(self):
        """Foreign device registration raises for SC transport."""
        sc_cfg = SCTransportConfig()
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                with pytest.raises(RuntimeError, match="only supported with BIP/BIP6"):
                    await app.register_as_foreign_device("192.168.1.1")
            finally:
                await app.stop()

    async def test_is_foreign_device_false_for_sc(self):
        """is_foreign_device returns False for SC transport."""
        sc_cfg = SCTransportConfig()
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                assert app.is_foreign_device is False
            finally:
                await app.stop()

    async def test_foreign_device_status_none_for_sc(self):
        """foreign_device_status returns None for SC transport."""
        sc_cfg = SCTransportConfig()
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                assert app.foreign_device_status is None
            finally:
                await app.stop()

    async def test_wait_for_registration_false_for_sc(self):
        """wait_for_registration returns False for SC transport."""
        sc_cfg = SCTransportConfig()
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                result = await app.wait_for_registration()
                assert result is False
            finally:
                await app.stop()

    async def test_deregister_foreign_device_raises_for_sc(self):
        """deregister_foreign_device raises for SC transport."""
        sc_cfg = SCTransportConfig()
        config = DeviceConfig(instance_number=1, sc_config=sc_cfg)
        app = BACnetApplication(config)
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            await app.start()
            try:
                with pytest.raises(RuntimeError, match="Not registered as a foreign device"):
                    await app.deregister_foreign_device()
            finally:
                await app.stop()


# -------------------------------------------------------------------
# Client wrapper with sc_config
# -------------------------------------------------------------------


class TestClientWithSCConfig:
    def test_client_builds_config_with_sc(self):
        """Client builds DeviceConfig with sc_config when provided."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        client = Client(sc_config=sc_cfg)
        assert client._config.sc_config is sc_cfg
        assert client._config.ipv6 is False

    def test_client_with_explicit_config(self):
        """Explicit DeviceConfig with sc_config is passed through."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        config = DeviceConfig(instance_number=100, sc_config=sc_cfg)
        client = Client(config)
        assert client._config is config
        assert client._config.sc_config is sc_cfg

    async def test_client_context_manager_with_sc(self):
        """Client context manager starts and stops with SC transport."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        mock_t = _make_mock_sc_transport()

        with patch("bac_py.transport.sc.SCTransport", return_value=mock_t):
            async with Client(sc_config=sc_cfg, instance_number=100) as client:
                assert client._app is not None
                assert client._app._transport is mock_t
            # After exit, app is stopped
            mock_t.stop.assert_awaited_once()

    def test_client_sc_and_ipv6_raises(self):
        """Client raises ValueError if both sc_config and ipv6 are set."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        with pytest.raises(ValueError, match="sc_config and ipv6 are mutually exclusive"):
            Client(sc_config=sc_cfg, ipv6=True)
