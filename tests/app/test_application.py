from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bac_py.app.application import (
    BACnetApplication,
    DeviceConfig,
    RouterConfig,
    RouterPortConfig,
)
from bac_py.network.address import BACnetAddress


class TestRouterPortConfig:
    def test_required_fields(self):
        cfg = RouterPortConfig(port_id=1, network_number=100)
        assert cfg.port_id == 1
        assert cfg.network_number == 100

    def test_defaults(self):
        cfg = RouterPortConfig(port_id=1, network_number=100)
        assert cfg.interface == "0.0.0.0"
        assert cfg.port == 0xBAC0

    def test_custom_values(self):
        cfg = RouterPortConfig(port_id=2, network_number=200, interface="10.0.0.1", port=47809)
        assert cfg.port_id == 2
        assert cfg.network_number == 200
        assert cfg.interface == "10.0.0.1"
        assert cfg.port == 47809


class TestRouterConfig:
    def test_defaults(self):
        cfg = RouterConfig()
        assert cfg.ports == []
        assert cfg.application_port_id == 1

    def test_with_ports(self):
        ports = [
            RouterPortConfig(port_id=1, network_number=100),
            RouterPortConfig(port_id=2, network_number=200),
        ]
        cfg = RouterConfig(ports=ports, application_port_id=1)
        assert len(cfg.ports) == 2
        assert cfg.application_port_id == 1


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

    def test_no_router_config_by_default(self):
        cfg = DeviceConfig(instance_number=1)
        assert cfg.router_config is None

    def test_with_router_config(self):
        router_cfg = RouterConfig(
            ports=[
                RouterPortConfig(port_id=1, network_number=100),
                RouterPortConfig(port_id=2, network_number=200),
            ],
            application_port_id=1,
        )
        cfg = DeviceConfig(instance_number=1, router_config=router_cfg)
        assert cfg.router_config is router_cfg
        assert len(cfg.router_config.ports) == 2


class TestBACnetApplication:
    def test_init(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        assert app.config is cfg
        assert app.object_db is not None
        assert app.service_registry is not None

    def test_init_router_fields(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        assert app._router is None
        assert app._transports == []

    async def test_confirmed_request_before_start_raises(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with pytest.raises(RuntimeError, match="not started"):
            await app.confirmed_request(dest, 12, b"\x01")

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


class TestBACnetApplicationRouterMode:
    """Test router-mode startup/stop/send."""

    def _make_mock_transport(self):
        """Create a mock BIPTransport with required attributes."""
        transport = MagicMock()
        transport.start = AsyncMock()
        transport.stop = AsyncMock()
        transport.local_mac = b"\x7f\x00\x00\x01\xba\xc0"
        transport.max_npdu_length = 1497
        transport.on_receive = MagicMock()
        return transport

    @pytest.fixture
    def router_cfg(self):
        return DeviceConfig(
            instance_number=1,
            router_config=RouterConfig(
                ports=[
                    RouterPortConfig(port_id=1, network_number=100, port=0),
                    RouterPortConfig(port_id=2, network_number=200, port=0),
                ],
                application_port_id=1,
            ),
        )

    async def test_router_mode_start_creates_router(self, router_cfg):
        """After start(), app._router should be set in router mode."""
        app = BACnetApplication(router_cfg)

        mock_t1 = self._make_mock_transport()
        mock_t2 = self._make_mock_transport()
        transports = iter([mock_t1, mock_t2])

        with (
            patch(
                "bac_py.app.application.BIPTransport",
                side_effect=lambda **kwargs: next(transports),
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
                assert app._client_tsm is not None
                assert app._server_tsm is not None
                assert app._running is True
            finally:
                await app.stop()

    async def test_router_mode_creates_ports(self, router_cfg):
        """Router is created with correct port count."""
        app = BACnetApplication(router_cfg)

        mock_t1 = self._make_mock_transport()
        mock_t2 = self._make_mock_transport()
        transports = iter([mock_t1, mock_t2])

        with (
            patch(
                "bac_py.app.application.BIPTransport",
                side_effect=lambda **kwargs: next(transports),
            ),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                # NetworkRouter was called with a list of 2 ports
                call_args = mock_router_cls.call_args
                ports_arg = call_args[0][0]
                assert len(ports_arg) == 2
                assert call_args[1]["application_port_id"] == 1
                assert call_args[1]["application_callback"] is not None
            finally:
                await app.stop()

    async def test_router_mode_transports_started(self, router_cfg):
        """Each transport is started before creating the port."""
        app = BACnetApplication(router_cfg)

        mock_t1 = self._make_mock_transport()
        mock_t2 = self._make_mock_transport()
        transports = iter([mock_t1, mock_t2])

        with (
            patch(
                "bac_py.app.application.BIPTransport",
                side_effect=lambda **kwargs: next(transports),
            ),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                mock_t1.start.assert_called_once()
                mock_t2.start.assert_called_once()
                assert len(app._transports) == 2
            finally:
                await app.stop()

    async def test_router_mode_stop_calls_router_stop(self, router_cfg):
        """stop() calls router.stop() in router mode."""
        app = BACnetApplication(router_cfg)

        mock_t1 = self._make_mock_transport()
        mock_t2 = self._make_mock_transport()
        transports = iter([mock_t1, mock_t2])

        with (
            patch(
                "bac_py.app.application.BIPTransport",
                side_effect=lambda **kwargs: next(transports),
            ),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            await app.stop()

            mock_router_instance.stop.assert_called_once()

    async def test_unconfirmed_request_uses_router(self, router_cfg):
        """unconfirmed_request() should send via router in router mode."""
        app = BACnetApplication(router_cfg)

        mock_t1 = self._make_mock_transport()
        mock_t2 = self._make_mock_transport()
        transports = iter([mock_t1, mock_t2])

        with (
            patch(
                "bac_py.app.application.BIPTransport",
                side_effect=lambda **kwargs: next(transports),
            ),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_instance.send = MagicMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                # Reset mock to clear I-Am broadcast from start()
                mock_router_instance.send.reset_mock()
                dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
                app.unconfirmed_request(dest, 8, b"\x00")
                mock_router_instance.send.assert_called_once()
            finally:
                await app.stop()

    async def test_non_router_mode_no_router(self):
        """Non-router mode should not set _router."""
        cfg = DeviceConfig(instance_number=1, port=0)
        app = BACnetApplication(cfg)

        with patch(
            "bac_py.app.application.BIPTransport",
        ) as mock_bip_cls:
            mock_t = self._make_mock_transport()
            mock_bip_cls.return_value = mock_t

            await app.start()
            try:
                assert app._router is None
                assert app._network is not None
                assert app._client_tsm is not None
                assert app._server_tsm is not None
            finally:
                await app.stop()
