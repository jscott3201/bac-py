"""Tests for Ethernet transport integration with BACnetApplication and Client."""

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


def _make_mock_ethernet_transport():
    """Create a mock EthernetTransport with required attributes."""
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    transport.local_mac = b"\xaa\xbb\xcc\xdd\xee\xff"
    transport.max_npdu_length = 1497
    transport.on_receive = MagicMock()
    return transport


# -------------------------------------------------------------------
# DeviceConfig validation
# -------------------------------------------------------------------


class TestDeviceConfigEthernetValidation:
    def test_ethernet_and_ipv6_mutually_exclusive(self):
        with pytest.raises(ValueError, match="ethernet_interface and ipv6 are mutually exclusive"):
            DeviceConfig(
                instance_number=1,
                ethernet_interface="eth0",
                ipv6=True,
            )

    def test_ethernet_and_sc_mutually_exclusive(self):
        with pytest.raises(
            ValueError, match="ethernet_interface and sc_config are mutually exclusive"
        ):
            DeviceConfig(
                instance_number=1,
                ethernet_interface="eth0",
                sc_config=SCTransportConfig(primary_hub_uri="wss://hub:4443"),
            )

    def test_ethernet_interface_alone_ok(self):
        cfg = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        assert cfg.ethernet_interface == "eth0"
        assert cfg.ethernet_mac is None
        assert cfg.ipv6 is False
        assert cfg.sc_config is None

    def test_ethernet_interface_with_mac(self):
        mac = b"\x01\x02\x03\x04\x05\x06"
        cfg = DeviceConfig(instance_number=1, ethernet_interface="eth0", ethernet_mac=mac)
        assert cfg.ethernet_interface == "eth0"
        assert cfg.ethernet_mac == mac

    def test_ethernet_fields_none_by_default(self):
        cfg = DeviceConfig(instance_number=1)
        assert cfg.ethernet_interface is None
        assert cfg.ethernet_mac is None


# -------------------------------------------------------------------
# RouterPortConfig with ethernet
# -------------------------------------------------------------------


class TestRouterPortConfigEthernet:
    def test_ethernet_interface_field(self):
        rpc = RouterPortConfig(port_id=1, network_number=100, ethernet_interface="eth0")
        assert rpc.ethernet_interface == "eth0"
        assert rpc.ethernet_mac is None

    def test_ethernet_interface_with_mac(self):
        mac = b"\x01\x02\x03\x04\x05\x06"
        rpc = RouterPortConfig(
            port_id=1, network_number=100, ethernet_interface="eth0", ethernet_mac=mac
        )
        assert rpc.ethernet_interface == "eth0"
        assert rpc.ethernet_mac == mac

    def test_ethernet_fields_none_by_default(self):
        rpc = RouterPortConfig(port_id=1, network_number=100)
        assert rpc.ethernet_interface is None
        assert rpc.ethernet_mac is None


# -------------------------------------------------------------------
# _start_ethernet_mode (non-router)
# -------------------------------------------------------------------


class TestStartEthernetMode:
    async def test_start_ethernet_mode_wires_transport(self):
        """Ethernet transport is started and wired into the app."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            try:
                assert app._transport is mock_t
                assert app._network is not None
                assert app._client_tsm is not None
                assert app._server_tsm is not None
                assert app._running is True
                mock_t.start.assert_awaited_once()
            finally:
                await app.stop()

    async def test_start_ethernet_mode_with_mac(self):
        """Explicit MAC is passed through to EthernetTransport."""
        mac = b"\x01\x02\x03\x04\x05\x06"
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0", ethernet_mac=mac)
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t) as mock_cls:
            await app.start()
            try:
                mock_cls.assert_called_once_with("eth0", mac_address=mac)
            finally:
                await app.stop()

    async def test_stop_calls_ethernet_transport_stop(self):
        """stop() calls transport.stop() for Ethernet transport."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            await app.stop()
            mock_t.stop.assert_awaited_once()


# -------------------------------------------------------------------
# Router mode with Ethernet port
# -------------------------------------------------------------------


class TestRouterModeWithEthernetPort:
    async def test_router_with_ethernet_port(self):
        """An Ethernet port can be configured alongside BIP ports in router mode."""
        router_config = RouterConfig(
            ports=[
                RouterPortConfig(port_id=1, network_number=100),
                RouterPortConfig(port_id=2, network_number=200, ethernet_interface="eth0"),
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

        mock_eth = _make_mock_ethernet_transport()

        with (
            patch("bac_py.app.application.BIPTransport", return_value=mock_bip),
            patch(
                "bac_py.transport.ethernet.EthernetTransport",
                return_value=mock_eth,
            ),
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
                mock_eth.start.assert_awaited_once()
                # Router created with 2 ports
                call_args = mock_router_cls.call_args
                ports_arg = call_args[0][0]
                assert len(ports_arg) == 2
                # Both transports tracked
                assert len(app._transports) == 2
            finally:
                await app.stop()

    async def test_router_ethernet_port_with_mac(self):
        """Router Ethernet port passes MAC to EthernetTransport."""
        mac = b"\x01\x02\x03\x04\x05\x06"
        router_config = RouterConfig(
            ports=[
                RouterPortConfig(
                    port_id=1,
                    network_number=100,
                    ethernet_interface="eth0",
                    ethernet_mac=mac,
                ),
            ],
            application_port_id=1,
        )
        config = DeviceConfig(instance_number=1, router_config=router_config)
        app = BACnetApplication(config)
        mock_eth = _make_mock_ethernet_transport()

        with (
            patch(
                "bac_py.transport.ethernet.EthernetTransport",
                return_value=mock_eth,
            ) as mock_cls,
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                mock_cls.assert_called_once_with("eth0", mac_address=mac)
            finally:
                await app.stop()

    async def test_router_ethernet_port_skips_bbmd(self):
        """BBMD config is ignored for Ethernet ports (no attach_bbmd)."""
        from bac_py.app.application import BBMDConfig

        router_config = RouterConfig(
            ports=[
                RouterPortConfig(
                    port_id=1,
                    network_number=100,
                    ethernet_interface="eth0",
                    bbmd_config=BBMDConfig(),
                ),
            ],
            application_port_id=1,
        )
        config = DeviceConfig(instance_number=1, router_config=router_config)
        app = BACnetApplication(config)
        mock_eth = _make_mock_ethernet_transport()
        # Ensure no attach_bbmd method
        del mock_eth.attach_bbmd

        with (
            patch(
                "bac_py.transport.ethernet.EthernetTransport",
                return_value=mock_eth,
            ),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                # Should not raise — hasattr guard skips BBMD for Ethernet
                mock_eth.start.assert_awaited_once()
            finally:
                await app.stop()


# -------------------------------------------------------------------
# Foreign device methods with Ethernet transport
# -------------------------------------------------------------------


class TestForeignDeviceWithEthernetTransport:
    async def test_register_foreign_device_raises_for_ethernet(self):
        """Foreign device registration raises for Ethernet transport."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            try:
                with pytest.raises(RuntimeError, match="only supported with BIP/BIP6"):
                    await app.register_as_foreign_device("192.168.1.1")
            finally:
                await app.stop()

    async def test_is_foreign_device_false_for_ethernet(self):
        """is_foreign_device returns False for Ethernet transport."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            try:
                assert app.is_foreign_device is False
            finally:
                await app.stop()

    async def test_foreign_device_status_none_for_ethernet(self):
        """foreign_device_status returns None for Ethernet transport."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            try:
                assert app.foreign_device_status is None
            finally:
                await app.stop()

    async def test_wait_for_registration_false_for_ethernet(self):
        """wait_for_registration returns False for Ethernet transport."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            try:
                result = await app.wait_for_registration()
                assert result is False
            finally:
                await app.stop()

    async def test_deregister_foreign_device_raises_for_ethernet(self):
        """deregister_foreign_device raises for Ethernet transport."""
        config = DeviceConfig(instance_number=1, ethernet_interface="eth0")
        app = BACnetApplication(config)
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            await app.start()
            try:
                with pytest.raises(RuntimeError, match="Not registered as a foreign device"):
                    await app.deregister_foreign_device()
            finally:
                await app.stop()


# -------------------------------------------------------------------
# Client wrapper with ethernet
# -------------------------------------------------------------------


class TestClientWithEthernet:
    def test_client_builds_config_with_ethernet(self):
        """Client builds DeviceConfig with ethernet_interface when provided."""
        client = Client(ethernet_interface="eth0")
        assert client._config.ethernet_interface == "eth0"
        assert client._config.ethernet_mac is None
        assert client._config.ipv6 is False
        assert client._config.sc_config is None

    def test_client_builds_config_with_ethernet_mac(self):
        """Client builds DeviceConfig with ethernet_mac when provided."""
        mac = b"\x01\x02\x03\x04\x05\x06"
        client = Client(ethernet_interface="eth0", ethernet_mac=mac)
        assert client._config.ethernet_interface == "eth0"
        assert client._config.ethernet_mac == mac

    def test_client_with_explicit_config(self):
        """Explicit DeviceConfig with ethernet_interface is passed through."""
        config = DeviceConfig(instance_number=100, ethernet_interface="eth0")
        client = Client(config)
        assert client._config is config
        assert client._config.ethernet_interface == "eth0"

    async def test_client_context_manager_with_ethernet(self):
        """Client context manager starts and stops with Ethernet transport."""
        mock_t = _make_mock_ethernet_transport()

        with patch("bac_py.transport.ethernet.EthernetTransport", return_value=mock_t):
            async with Client(ethernet_interface="eth0", instance_number=100) as client:
                assert client._app is not None
                assert client._app._transport is mock_t
            # After exit, app is stopped
            mock_t.stop.assert_awaited_once()

    def test_client_ethernet_and_ipv6_raises(self):
        """Client raises ValueError if both ethernet_interface and ipv6 are set."""
        with pytest.raises(ValueError, match="ethernet_interface and ipv6 are mutually exclusive"):
            Client(ethernet_interface="eth0", ipv6=True)

    def test_client_ethernet_and_sc_raises(self):
        """Client raises ValueError if both ethernet_interface and sc_config are set."""
        sc_cfg = SCTransportConfig(primary_hub_uri="wss://hub:4443")
        with pytest.raises(
            ValueError, match="ethernet_interface and sc_config are mutually exclusive"
        ):
            Client(ethernet_interface="eth0", sc_config=sc_cfg)
