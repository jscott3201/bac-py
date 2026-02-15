import asyncio
import logging
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bac_py.app.application import (
    BACnetApplication,
    DeviceConfig,
    DeviceInfo,
    ForeignDeviceStatus,
    RouterConfig,
    RouterPortConfig,
)
from bac_py.encoding.apdu import (
    AbortPDU,
    ComplexAckPDU,
    ConfirmedRequestPDU,
    ErrorPDU,
    RejectPDU,
    SimpleAckPDU,
    UnconfirmedRequestPDU,
    encode_apdu,
)
from bac_py.network.address import BACnetAddress
from bac_py.services.errors import BACnetAbortError, BACnetError, BACnetRejectError
from bac_py.services.who_is import IAmRequest
from bac_py.types.enums import (
    AbortReason,
    ConfirmedServiceChoice,
    EnableDisable,
    ObjectType,
    RejectReason,
    Segmentation,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import ObjectIdentifier


def _make_mock_transport():
    """Create a mock BIPTransport with required attributes."""
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    transport.local_mac = b"\x7f\x00\x00\x01\xba\xc0"
    transport.max_npdu_length = 1497
    transport.on_receive = MagicMock()
    transport.foreign_device = None
    transport.attach_foreign_device = AsyncMock()
    return transport


def _make_started_app():
    """Create a BACnetApplication with mocked internal state (no real start)."""
    cfg = DeviceConfig(instance_number=1)
    app = BACnetApplication(cfg)
    # Set up mocked internals as if start() completed
    app._network = MagicMock()
    app._network.send = MagicMock()
    app._client_tsm = MagicMock()
    app._client_tsm.send_request = AsyncMock(return_value=b"\x00")
    app._client_tsm.active_transactions = MagicMock(return_value=[])
    app._server_tsm = MagicMock()
    app._server_tsm.receive_confirmed_request = MagicMock()
    app._server_tsm.complete_transaction = MagicMock()
    app._server_tsm.start_segmented_response = MagicMock()
    app._running = True
    return app


class TestRouterPortConfig:
    def test_required_fields(self):
        cfg = RouterPortConfig(port_id=1, network_number=100)
        assert cfg.port_id == 1
        assert cfg.network_number == 100

    def test_defaults(self):
        cfg = RouterPortConfig(port_id=1, network_number=100)
        assert cfg.interface == "0.0.0.0"
        assert cfg.port == 0xBAC0
        assert cfg.broadcast_address == "255.255.255.255"

    def test_custom_values(self):
        cfg = RouterPortConfig(port_id=2, network_number=200, interface="10.0.0.1", port=47809)
        assert cfg.port_id == 2
        assert cfg.network_number == 200
        assert cfg.interface == "10.0.0.1"
        assert cfg.port == 47809

    def test_custom_broadcast_address(self):
        cfg = RouterPortConfig(port_id=1, network_number=100, broadcast_address="192.168.1.255")
        assert cfg.broadcast_address == "192.168.1.255"


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


class TestDeviceInfoCache:
    """Test device info caching from I-Am responses (Clause 19.4)."""

    def test_cache_miss_returns_none(self):
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        assert app.get_device_info(dest) is None

    def test_cache_populated_from_i_am(self):
        """I-Am response should populate the device info cache."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            max_apdu_length=480,
            segmentation_supported=Segmentation.NONE,
            vendor_id=99,
        )
        app._device_info_cache[source] = DeviceInfo(
            max_apdu_length=iam.max_apdu_length,
            segmentation_supported=int(iam.segmentation_supported),
        )

        info = app.get_device_info(source)
        assert info is not None
        assert info.max_apdu_length == 480
        assert info.segmentation_supported == int(Segmentation.NONE)

    async def test_i_am_handler_populates_cache(self):
        """The _handle_i_am_for_cache handler should update the cache."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            max_apdu_length=1024,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=42,
        )
        await app._handle_i_am_for_cache(8, iam.encode(), source)

        info = app.get_device_info(source)
        assert info is not None
        assert info.max_apdu_length == 1024
        assert info.segmentation_supported == int(Segmentation.BOTH)

    async def test_subsequent_i_am_updates_cache(self):
        """A second I-Am from the same device should update the cache."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # First I-Am
        iam1 = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            max_apdu_length=480,
            segmentation_supported=Segmentation.NONE,
            vendor_id=42,
        )
        await app._handle_i_am_for_cache(8, iam1.encode(), source)
        assert app.get_device_info(source).max_apdu_length == 480  # type: ignore[union-attr]

        # Second I-Am with different capabilities
        iam2 = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=42,
        )
        await app._handle_i_am_for_cache(8, iam2.encode(), source)
        info = app.get_device_info(source)
        assert info is not None
        assert info.max_apdu_length == 1476
        assert info.segmentation_supported == int(Segmentation.BOTH)

    async def test_malformed_i_am_does_not_crash(self):
        """Malformed I-Am data should be silently ignored."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        await app._handle_i_am_for_cache(8, b"\x00", source)
        assert app.get_device_info(source) is None


# ==================== Section 1A: Property Getters & State Management ====================


class TestPropertyGettersAndState:
    """Test property accessors and DCC state management."""

    def test_cov_manager_none_before_start(self):
        """COV manager is None before start."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        assert app.cov_manager is None

    def test_event_engine_none_before_start(self):
        """Event engine is None before start."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        assert app.event_engine is None

    def test_dcc_state_default_enable(self):
        """DCC state defaults to ENABLE."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        assert app.dcc_state == EnableDisable.ENABLE

    def test_device_object_identifier(self):
        """Device object identifier uses config instance number."""
        app = BACnetApplication(DeviceConfig(instance_number=42))
        oid = app.device_object_identifier
        assert oid == ObjectIdentifier(ObjectType.DEVICE, 42)

    def test_set_dcc_state_no_duration(self):
        """Set DCC state without duration."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app.set_dcc_state(EnableDisable.DISABLE)
        assert app.dcc_state == EnableDisable.DISABLE
        assert app._dcc_timer is None

    async def test_set_dcc_state_with_duration(self):
        """Set DCC state with duration creates timer."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app.set_dcc_state(EnableDisable.DISABLE, duration=5)
        assert app.dcc_state == EnableDisable.DISABLE
        assert app._dcc_timer is not None
        # Clean up timer
        app._dcc_timer.cancel()

    async def test_set_dcc_state_enable_with_duration_no_timer(self):
        """Setting ENABLE with duration does not create timer."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app.set_dcc_state(EnableDisable.ENABLE, duration=5)
        assert app.dcc_state == EnableDisable.ENABLE
        assert app._dcc_timer is None

    async def test_set_dcc_state_cancels_previous_timer(self):
        """Setting DCC state cancels any existing timer."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        # Set initial timer
        app.set_dcc_state(EnableDisable.DISABLE, duration=10)
        first_timer = app._dcc_timer
        assert first_timer is not None

        # Set new state, should cancel previous timer
        app.set_dcc_state(EnableDisable.DISABLE_INITIATION, duration=5)
        assert first_timer.cancelled()
        assert app._dcc_timer is not first_timer
        # Clean up
        app._dcc_timer.cancel()

    def test_dcc_timer_expired(self):
        """DCC timer expiration re-enables communication."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._dcc_state = EnableDisable.DISABLE
        app._dcc_timer = MagicMock()
        app._dcc_timer_expired()
        assert app.dcc_state == EnableDisable.ENABLE
        assert app._dcc_timer is None

    def test_is_foreign_device_false_no_transport(self):
        """is_foreign_device is False when transport is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        assert app.is_foreign_device is False

    def test_is_foreign_device_false_no_fd(self):
        """is_foreign_device is False when foreign_device is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device = None
        assert app.is_foreign_device is False

    def test_is_foreign_device_false_not_registered(self):
        """is_foreign_device is False when FD exists but not registered."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device.is_registered = False
        assert app.is_foreign_device is False

    def test_is_foreign_device_true_when_registered(self):
        """is_foreign_device is True when FD is registered."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device.is_registered = True
        assert app.is_foreign_device is True

    def test_foreign_device_status_none_no_transport(self):
        """Foreign device status is None when transport is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        assert app.foreign_device_status is None

    def test_foreign_device_status_none_no_fd(self):
        """Foreign device status is None when no FD manager."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device = None
        assert app.foreign_device_status is None

    def test_foreign_device_status_constructs_status(self):
        """Foreign device status constructs ForeignDeviceStatus from FD manager."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        fd = MagicMock()
        fd.bbmd_address.host = "192.168.1.1"
        fd.bbmd_address.port = 47808
        fd.ttl = 60
        fd.is_registered = True
        fd.last_result.name = "SUCCESS"
        app._transport.foreign_device = fd

        status = app.foreign_device_status
        assert isinstance(status, ForeignDeviceStatus)
        assert status.bbmd_address == "192.168.1.1:47808"
        assert status.ttl == 60
        assert status.is_registered is True
        assert status.last_result == "SUCCESS"

    def test_foreign_device_status_last_result_none(self):
        """Foreign device status handles None last_result."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        fd = MagicMock()
        fd.bbmd_address.host = "10.0.0.1"
        fd.bbmd_address.port = 47808
        fd.ttl = 30
        fd.is_registered = False
        fd.last_result = None
        app._transport.foreign_device = fd

        status = app.foreign_device_status
        assert status is not None
        assert status.last_result is None


# ==================== Section 1B: Error Validation Paths ====================


class TestErrorValidationPaths:
    """Test error paths and validation in BACnetApplication."""

    async def test_start_router_mode_raises_without_config(self):
        """_start_router_mode raises when router_config is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        with pytest.raises(RuntimeError, match="Router config is required"):
            await app._start_router_mode()

    async def test_register_foreign_device_no_transport(self):
        """register_as_foreign_device raises when not started."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        with pytest.raises(RuntimeError, match="not started"):
            await app.register_as_foreign_device("192.168.1.1")

    async def test_register_foreign_device_router_mode(self):
        """register_as_foreign_device raises in router mode."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._router = MagicMock()  # Simulate router mode
        with pytest.raises(RuntimeError, match="not supported in router mode"):
            await app.register_as_foreign_device("192.168.1.1")

    async def test_register_foreign_device_already_registered(self):
        """register_as_foreign_device raises when already registered."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device = MagicMock()  # Already has FD
        with pytest.raises(RuntimeError, match="Already registered"):
            await app.register_as_foreign_device("192.168.1.1")

    async def test_register_foreign_device_success(self):
        """register_as_foreign_device attaches FD manager."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device = None
        app._transport.attach_foreign_device = AsyncMock()

        await app.register_as_foreign_device("192.168.1.1", ttl=30)
        app._transport.attach_foreign_device.assert_called_once()
        call_args = app._transport.attach_foreign_device.call_args
        assert call_args[0][1] == 30  # ttl

    async def test_deregister_foreign_device_not_registered(self):
        """deregister_foreign_device raises when not registered."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        with pytest.raises(RuntimeError, match="Not registered"):
            await app.deregister_foreign_device()

    async def test_deregister_foreign_device_no_fd(self):
        """deregister_foreign_device raises when transport has no FD."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device = None
        with pytest.raises(RuntimeError, match="Not registered"):
            await app.deregister_foreign_device()

    async def test_deregister_foreign_device_success(self):
        """deregister_foreign_device stops FD and clears reference."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        fd = MagicMock()
        fd.stop = AsyncMock()
        app._transport.foreign_device = fd

        await app.deregister_foreign_device()
        fd.stop.assert_called_once()

    def test_send_network_message_no_network(self):
        """send_network_message raises when network is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        with pytest.raises(RuntimeError, match="not available"):
            app.send_network_message(0, b"\x00")

    def test_send_network_message_success(self):
        """send_network_message delegates to network layer."""
        app = _make_started_app()
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app.send_network_message(1, b"\x00", dest)
        app._network.send_network_message.assert_called_once_with(1, b"\x00", dest)

    def test_register_network_message_handler_no_network(self):
        """register_network_message_handler raises when network is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        with pytest.raises(RuntimeError, match="not available"):
            app.register_network_message_handler(0, lambda: None)

    def test_register_network_message_handler_success(self):
        """register_network_message_handler delegates to network layer."""
        app = _make_started_app()
        handler = MagicMock()
        app.register_network_message_handler(5, handler)
        app._network.register_network_message_handler.assert_called_once_with(5, handler)

    def test_unregister_network_message_handler_no_network(self):
        """unregister_network_message_handler is no-op when network is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        handler = MagicMock()
        # Should not raise
        app.unregister_network_message_handler(0, handler)

    def test_unregister_network_message_handler_success(self):
        """unregister_network_message_handler delegates to network layer."""
        app = _make_started_app()
        handler = MagicMock()
        app.unregister_network_message_handler(5, handler)
        app._network.unregister_network_message_handler.assert_called_once_with(5, handler)

    async def test_wait_for_registration_no_transport(self):
        """wait_for_registration returns False when transport is None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        assert await app.wait_for_registration() is False

    async def test_wait_for_registration_no_fd(self):
        """wait_for_registration returns False when no FD manager."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        app._transport.foreign_device = None
        assert await app.wait_for_registration() is False

    async def test_wait_for_registration_timeout(self):
        """wait_for_registration returns False on timeout."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        fd = MagicMock()
        fd._registered = asyncio.Event()  # Never set
        fd.is_registered = False
        app._transport.foreign_device = fd

        result = await app.wait_for_registration(timeout=0.01)
        assert result is False

    async def test_wait_for_registration_success(self):
        """wait_for_registration returns True when registered."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app._transport = MagicMock()
        fd = MagicMock()
        fd._registered = asyncio.Event()
        fd._registered.set()
        fd.is_registered = True
        app._transport.foreign_device = fd

        result = await app.wait_for_registration(timeout=1.0)
        assert result is True


# ==================== Section 1C: DCC Enforcement ====================


class TestDCCEnforcement:
    """Test DeviceCommunicationControl enforcement on requests."""

    def test_unconfirmed_request_suppressed_disable(self):
        """Unconfirmed request is suppressed when DCC is DISABLE."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app.unconfirmed_request(dest, 8, b"\x00")
        app._network.send.assert_not_called()

    def test_unconfirmed_request_suppressed_disable_initiation(self):
        """Unconfirmed request is suppressed when DCC is DISABLE_INITIATION."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE_INITIATION
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app.unconfirmed_request(dest, 8, b"\x00")
        app._network.send.assert_not_called()

    def test_unconfirmed_request_allowed_enable(self):
        """Unconfirmed request is sent when DCC is ENABLE."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.ENABLE
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app.unconfirmed_request(dest, 8, b"\x00")
        app._network.send.assert_called_once()

    async def test_dispatch_drops_non_dcc_in_disable(self):
        """Confirmed non-DCC request is dropped in DISABLE state."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        txn = MagicMock()
        txn.invoke_id = 1
        # ReadProperty (not in DCC allowed list)
        await app._dispatch_request(
            txn, ConfirmedServiceChoice.READ_PROPERTY, b"\x00", MagicMock()
        )
        # Service registry should NOT be called
        app._server_tsm.complete_transaction.assert_not_called()

    async def test_dispatch_allows_dcc_service_in_disable(self):
        """DCC service request is allowed in DISABLE state."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        txn = MagicMock()
        txn.invoke_id = 1
        txn.client_max_apdu_length = 1476

        app._service_registry.dispatch_confirmed = AsyncMock(return_value=None)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        await app._dispatch_request(
            txn,
            ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
            b"\x00",
            source,
        )
        app._service_registry.dispatch_confirmed.assert_called_once()

    async def test_dispatch_allows_reinitialize_in_disable(self):
        """ReinitializeDevice is allowed in DISABLE state."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        txn = MagicMock()
        txn.invoke_id = 1
        txn.client_max_apdu_length = 1476

        app._service_registry.dispatch_confirmed = AsyncMock(return_value=None)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        await app._dispatch_request(
            txn,
            ConfirmedServiceChoice.REINITIALIZE_DEVICE,
            b"\x00",
            source,
        )
        app._service_registry.dispatch_confirmed.assert_called_once()

    async def test_unconfirmed_handler_allows_who_is_disable_initiation(self):
        """WHO-IS is allowed when DCC is DISABLE_INITIATION."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE_INITIATION
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        pdu = UnconfirmedRequestPDU(
            service_choice=UnconfirmedServiceChoice.WHO_IS,
            service_request=b"\x00",
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_request(pdu, source)
        app._service_registry.dispatch_unconfirmed.assert_called_once()

    async def test_unconfirmed_handler_allows_who_has_disable_initiation(self):
        """WHO-HAS is allowed when DCC is DISABLE_INITIATION."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE_INITIATION
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        pdu = UnconfirmedRequestPDU(
            service_choice=UnconfirmedServiceChoice.WHO_HAS,
            service_request=b"\x00",
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_request(pdu, source)
        app._service_registry.dispatch_unconfirmed.assert_called_once()

    async def test_unconfirmed_handler_drops_others_disable(self):
        """Non-WHO-IS unconfirmed requests are dropped when DCC is DISABLE."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        pdu = UnconfirmedRequestPDU(
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_request=b"\x00",
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_request(pdu, source)
        app._service_registry.dispatch_unconfirmed.assert_not_called()

    async def test_unconfirmed_handler_drops_non_who_in_disable_initiation(self):
        """Non-WHO-IS/WHO-HAS dropped when DCC is DISABLE_INITIATION."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE_INITIATION
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        pdu = UnconfirmedRequestPDU(
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_request=b"\x00",
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_request(pdu, source)
        app._service_registry.dispatch_unconfirmed.assert_not_called()

    async def test_unconfirmed_handler_rejects_non_pdu(self):
        """_handle_unconfirmed_request returns early for non-PDU."""
        app = _make_started_app()
        app._service_registry.dispatch_unconfirmed = AsyncMock()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_request("not a pdu", source)
        app._service_registry.dispatch_unconfirmed.assert_not_called()


# ==================== Section 1D: APDU Handling & Dispatch ====================


class TestAPDUDispatch:
    """Test APDU receive path and dispatch logic."""

    def test_on_apdu_received_malformed_drops(self):
        """Malformed APDU bytes are dropped with warning."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Single byte is not a valid APDU
        app._on_apdu_received(b"\xff", source)
        # No crash, just logged

    def test_on_apdu_received_simple_ack(self):
        """SimpleAck is routed to client TSM."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = SimpleAckPDU(invoke_id=5, service_choice=15)
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._client_tsm.handle_simple_ack.assert_called_once_with(source, 5, 15)

    def test_on_apdu_received_complex_ack(self):
        """Non-segmented ComplexAck is routed to client TSM."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = ComplexAckPDU(
            segmented=False,
            more_follows=False,
            invoke_id=7,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_ack=b"\x01\x02",
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._client_tsm.handle_complex_ack.assert_called_once_with(source, 7, 12, b"\x01\x02")

    def test_on_apdu_received_error_pdu(self):
        """ErrorPDU is routed to client TSM."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = ErrorPDU(
            invoke_id=3,
            service_choice=12,
            error_class=2,
            error_code=31,
            error_data=None,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._client_tsm.handle_error.assert_called_once()

    def test_on_apdu_received_reject_pdu(self):
        """RejectPDU is routed to client TSM."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = RejectPDU(invoke_id=4, reject_reason=3)
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._client_tsm.handle_reject.assert_called_once_with(source, 4, 3)

    def test_on_apdu_received_abort_pdu(self):
        """AbortPDU is routed to client TSM."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = AbortPDU(sent_by_server=True, invoke_id=6, abort_reason=0)
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._client_tsm.handle_abort.assert_called_once_with(source, 6, 0)

    def test_on_apdu_received_no_client_tsm(self):
        """Response PDUs are ignored when client TSM is None."""
        app = _make_started_app()
        app._client_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = SimpleAckPDU(invoke_id=5, service_choice=15)
        apdu_bytes = encode_apdu(pdu)
        # Should not crash
        app._on_apdu_received(apdu_bytes, source)

    def test_handle_segmented_request_no_server_tsm(self):
        """Segmented request is ignored when server TSM is None."""
        app = _make_started_app()
        app._server_tsm = None
        pdu = MagicMock(spec=ConfirmedRequestPDU)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should not crash
        app._handle_segmented_request(pdu, source)

    def test_handle_segmented_request_returns_none(self):
        """Segmented request where assembly returns None (waiting for more)."""
        app = _make_started_app()
        app._server_tsm.receive_confirmed_request.return_value = None
        pdu = MagicMock(spec=ConfirmedRequestPDU)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app._handle_segmented_request(pdu, source)
        # No dispatch should happen

    async def test_handle_confirmed_request_no_server_tsm(self):
        """Confirmed request returns early when server TSM is None."""
        app = _make_started_app()
        app._server_tsm = None
        pdu = MagicMock(spec=ConfirmedRequestPDU)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_confirmed_request(pdu, source)

    async def test_handle_confirmed_request_duplicate(self):
        """Confirmed request returns early when TSM says duplicate."""
        app = _make_started_app()
        app._server_tsm.receive_confirmed_request.return_value = None
        pdu = MagicMock(spec=ConfirmedRequestPDU)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_confirmed_request(pdu, source)

    async def test_handle_confirmed_request_no_service_data(self):
        """Confirmed request returns early when service_data is None."""
        app = _make_started_app()
        txn = MagicMock()
        app._server_tsm.receive_confirmed_request.return_value = (txn, None)
        pdu = MagicMock(spec=ConfirmedRequestPDU)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_confirmed_request(pdu, source)

    async def test_dispatch_sends_simple_ack_for_none_result(self):
        """Dispatch sends SimpleAck when handler returns None."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(return_value=None)

        await app._dispatch_request(txn, 15, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        # Should be a SimpleAck (PDU type 0x20)
        assert (sent_bytes[0] >> 4) & 0x0F == 2  # PduType.SIMPLE_ACK

    async def test_dispatch_sends_complex_ack_for_result(self):
        """Dispatch sends ComplexAck when handler returns data."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(return_value=b"\x01\x02\x03")

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        # Should be a ComplexAck (PDU type 0x30)
        assert (sent_bytes[0] >> 4) & 0x0F == 3  # PduType.COMPLEX_ACK

    async def test_dispatch_handles_bacnet_error(self):
        """Dispatch sends ErrorPDU on BACnetError."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        from bac_py.types.enums import ErrorClass, ErrorCode

        app._service_registry.dispatch_confirmed = AsyncMock(
            side_effect=BACnetError(
                error_class=ErrorClass.PROPERTY, error_code=ErrorCode.UNKNOWN_PROPERTY
            )
        )

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        # Should be an Error PDU (PDU type 0x50)
        assert (sent_bytes[0] >> 4) & 0x0F == 5  # PduType.ERROR

    async def test_dispatch_handles_reject_error(self):
        """Dispatch sends RejectPDU on BACnetRejectError."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(
            side_effect=BACnetRejectError(reason=RejectReason.INVALID_PARAMETER_DATA_TYPE)
        )

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        # Should be a Reject PDU (PDU type 0x60)
        assert (sent_bytes[0] >> 4) & 0x0F == 6  # PduType.REJECT

    async def test_dispatch_handles_abort_error(self):
        """Dispatch sends AbortPDU on BACnetAbortError."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(
            side_effect=BACnetAbortError(reason=AbortReason.BUFFER_OVERFLOW)
        )

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        # Should be an Abort PDU (PDU type 0x70)
        assert (sent_bytes[0] >> 4) & 0x0F == 7  # PduType.ABORT

    async def test_dispatch_handles_value_error(self):
        """Dispatch sends RejectPDU on ValueError (malformed data)."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(side_effect=ValueError("bad data"))

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        assert (sent_bytes[0] >> 4) & 0x0F == 6  # PduType.REJECT

    async def test_dispatch_handles_struct_error(self):
        """Dispatch sends RejectPDU on struct.error (truncated data)."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(
            side_effect=struct.error("unpack failed")
        )

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        assert (sent_bytes[0] >> 4) & 0x0F == 6  # PduType.REJECT

    async def test_dispatch_handles_index_error(self):
        """Dispatch sends RejectPDU on IndexError."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(
            side_effect=IndexError("out of range")
        )

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        assert (sent_bytes[0] >> 4) & 0x0F == 6  # PduType.REJECT

    async def test_dispatch_handles_generic_exception(self):
        """Dispatch sends AbortPDU on unhandled Exception."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 1476
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._network.send.assert_called_once()
        sent_bytes = app._network.send.call_args[0][0]
        assert (sent_bytes[0] >> 4) & 0x0F == 7  # PduType.ABORT

    async def test_dispatch_no_server_tsm_returns(self):
        """Dispatch returns early when server TSM is None."""
        app = _make_started_app()
        app._server_tsm = None
        txn = MagicMock()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._dispatch_request(txn, 12, b"\x00", source)

    async def test_dispatch_no_network_returns(self):
        """Dispatch returns early when network is None."""
        app = _make_started_app()
        app._network = None
        app._router = None
        txn = MagicMock()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._dispatch_request(txn, 12, b"\x00", source)

    async def test_dispatch_segmented_response(self):
        """Dispatch starts segmented response for large results."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 10
        txn.client_max_apdu_length = 50  # Very small max APDU
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # Return data larger than max payload
        large_data = b"\x00" * 200
        app._service_registry.dispatch_confirmed = AsyncMock(return_value=large_data)

        await app._dispatch_request(txn, 12, b"\x00", source)

        app._server_tsm.start_segmented_response.assert_called_once_with(txn, 12, large_data)

    def test_broadcast_i_am_no_device_object(self):
        """_broadcast_i_am falls back to Segmentation.BOTH when no device object."""
        app = _make_started_app()
        # No device object in the DB
        app._network.send.reset_mock()
        app._broadcast_i_am()
        app._network.send.assert_called_once()

    def test_broadcast_i_am_with_device_object(self):
        """_broadcast_i_am reads segmentation from device object."""
        from bac_py.types.enums import PropertyIdentifier

        app = _make_started_app()
        device_obj = MagicMock()
        device_obj.read_property.return_value = Segmentation.NONE
        oid = ObjectIdentifier(ObjectType.DEVICE, 1)
        app._object_db._objects = {oid: device_obj}
        app._object_db.get = MagicMock(return_value=device_obj)

        app._network.send.reset_mock()
        app._broadcast_i_am()
        app._network.send.assert_called_once()
        device_obj.read_property.assert_called_once_with(PropertyIdentifier.SEGMENTATION_SUPPORTED)

    def test_broadcast_i_am_read_property_fails(self):
        """_broadcast_i_am falls back to Segmentation.BOTH on read failure."""
        app = _make_started_app()
        device_obj = MagicMock()
        device_obj.read_property.side_effect = Exception("read failed")
        app._object_db.get = MagicMock(return_value=device_obj)

        app._network.send.reset_mock()
        app._broadcast_i_am()
        app._network.send.assert_called_once()

    async def test_confirmed_request_uses_cached_max_apdu(self):
        """Confirmed request constrains max APDU using cache."""
        app = _make_started_app()
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Cache says peer only accepts 480 bytes
        app._device_info_cache[dest] = DeviceInfo(
            max_apdu_length=480,
            segmentation_supported=int(Segmentation.NONE),
        )

        await app.confirmed_request(dest, 12, b"\x00")
        call_kwargs = app._client_tsm.send_request.call_args[1]
        assert call_kwargs["max_apdu_override"] == 480

    async def test_confirmed_request_no_cache_no_override(self):
        """Confirmed request with no cache entry uses None override."""
        app = _make_started_app()
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        await app.confirmed_request(dest, 12, b"\x00")
        call_kwargs = app._client_tsm.send_request.call_args[1]
        assert call_kwargs["max_apdu_override"] is None

    async def test_confirmed_request_cache_min_of_local_and_remote(self):
        """Confirmed request uses min(local, remote) max APDU."""
        cfg = DeviceConfig(instance_number=1, max_apdu_length=1476)
        app = BACnetApplication(cfg)
        app._client_tsm = MagicMock()
        app._client_tsm.send_request = AsyncMock(return_value=b"\x00")

        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Remote accepts more than local
        app._device_info_cache[dest] = DeviceInfo(
            max_apdu_length=2000,
            segmentation_supported=int(Segmentation.BOTH),
        )

        await app.confirmed_request(dest, 12, b"\x00")
        call_kwargs = app._client_tsm.send_request.call_args[1]
        assert call_kwargs["max_apdu_override"] == 1476  # min(1476, 2000)

    async def test_confirmed_request_with_timeout(self):
        """Confirmed request passes timeout to asyncio.wait_for."""
        app = _make_started_app()
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        result = await app.confirmed_request(dest, 12, b"\x00", timeout=5.0)
        assert result == b"\x00"

    async def test_unconfirmed_handler_dispatches_to_listeners(self):
        """Unconfirmed handler dispatches to temporary listeners."""
        app = _make_started_app()
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        callback = MagicMock()
        app._unconfirmed_listeners[8] = [callback]

        pdu = UnconfirmedRequestPDU(service_choice=8, service_request=b"\x01\x02")
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_request(pdu, source)

        callback.assert_called_once_with(b"\x01\x02", source)

    async def test_unconfirmed_handler_listener_error_caught(self):
        """Errors in temporary listeners are caught."""
        app = _make_started_app()
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        callback = MagicMock(side_effect=RuntimeError("listener error"))
        app._unconfirmed_listeners[8] = [callback]

        pdu = UnconfirmedRequestPDU(service_choice=8, service_request=b"\x01")
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should not raise
        await app._handle_unconfirmed_request(pdu, source)

    def test_on_apdu_received_segment_ack_server(self):
        """SegmentAck from server routes to client TSM."""
        from bac_py.encoding.apdu import SegmentAckPDU

        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = SegmentAckPDU(
            sent_by_server=True,
            negative_ack=False,
            invoke_id=1,
            actual_window_size=4,
            sequence_number=0,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._client_tsm.handle_segment_ack.assert_called_once()

    def test_on_apdu_received_segment_ack_client(self):
        """SegmentAck from client routes to server TSM."""
        from bac_py.encoding.apdu import SegmentAckPDU

        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        pdu = SegmentAckPDU(
            sent_by_server=False,
            negative_ack=False,
            invoke_id=1,
            actual_window_size=4,
            sequence_number=0,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)
        app._server_tsm.handle_segment_ack_for_response.assert_called_once()


# ==================== Section 1E: Context Manager & Lifecycle ====================


class TestLifecycle:
    """Test context manager, run(), stop() lifecycle methods."""

    async def test_aenter_calls_start(self):
        """__aenter__ starts the application."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            result = await app.__aenter__()
            try:
                assert result is app
                assert app._running is True
            finally:
                await app.__aexit__(None, None, None)

    async def test_aexit_calls_stop(self):
        """__aexit__ stops the application."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.__aenter__()
            await app.__aexit__(None, None, None)
            assert app._running is False

    async def test_stop_idempotent(self):
        """stop() is idempotent -- multiple calls are safe."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            await app.stop()
            await app.stop()  # Should not raise

    async def test_stop_cancels_dcc_timer(self):
        """stop() cancels active DCC timer."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            app.set_dcc_state(EnableDisable.DISABLE, duration=10)
            assert app._dcc_timer is not None
            timer = app._dcc_timer
            await app.stop()
            assert timer.cancelled()
            assert app._dcc_timer is None

    async def test_stop_stops_event_engine(self):
        """stop() calls event_engine.stop()."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            assert app._event_engine is not None
            await app.stop()
            assert app._event_engine is None

    async def test_stop_shuts_down_cov_manager(self):
        """stop() calls cov_manager.shutdown()."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            assert app._cov_manager is not None
            await app.stop()
            assert app._cov_manager is None

    async def test_stop_cancels_client_transactions(self):
        """stop() cancels pending client transactions."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            # Add a fake pending transaction
            mock_future = asyncio.get_running_loop().create_future()
            mock_txn = MagicMock()
            mock_txn.future = mock_future
            app._client_tsm._transactions = {1: mock_txn}
            app._client_tsm.active_transactions = MagicMock(return_value=[mock_txn])

            await app.stop()
            assert mock_future.cancelled()

    async def test_stop_cancels_background_tasks(self):
        """stop() cancels all background tasks."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()

            # Create a long-running background task
            async def long_task():
                await asyncio.sleep(100)

            app._spawn_task(long_task())
            assert len(app._background_tasks) == 1

            await app.stop()
            assert len(app._background_tasks) == 0

    async def test_stop_transport_in_non_router(self):
        """stop() calls transport.stop() in non-router mode."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            await app.stop()
            mock_t.stop.assert_called_once()

    async def test_run_starts_and_waits(self):
        """run() starts the app and waits for stop event."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            # Run in background and stop it after a short delay
            async def stop_after_delay():
                await asyncio.sleep(0.05)
                await app.stop()

            task = asyncio.create_task(stop_after_delay())
            await app.run()
            await task
            assert app._running is False

    def test_parse_bip_address_host_only(self):
        """Parse BIP address with host only (default port)."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        addr = app._parse_bip_address("192.168.1.1")
        assert addr.host == "192.168.1.1"
        assert addr.port == 0xBAC0

    def test_parse_bip_address_host_and_port(self):
        """Parse BIP address with host:port."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        addr = app._parse_bip_address("192.168.1.1:47809")
        assert addr.host == "192.168.1.1"
        assert addr.port == 47809

    async def test_start_initializes_cov_manager(self):
        """start() creates a COVManager."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            try:
                assert app.cov_manager is not None
            finally:
                await app.stop()

    async def test_start_initializes_event_engine(self):
        """start() creates and starts an EventEngine."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            try:
                assert app.event_engine is not None
            finally:
                await app.stop()

    async def test_start_registers_cov_handlers(self):
        """start() registers COV notification handlers."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            await app.start()
            try:
                # Check that confirmed COV handler is registered
                confirmed_handler = app._service_registry._confirmed.get(
                    ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION
                )
                assert confirmed_handler is not None
            finally:
                await app.stop()

    async def test_start_broadcasts_i_am(self):
        """start() broadcasts I-Am on startup."""
        cfg = DeviceConfig(instance_number=1)
        app = BACnetApplication(cfg)
        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t):
            mock_network = MagicMock()
            with patch("bac_py.app.application.NetworkLayer", return_value=mock_network):
                await app.start()
                try:
                    # Network.send should be called at least once (I-Am broadcast)
                    mock_network.send.assert_called()
                finally:
                    await app.stop()


# ==================== Section 1F: COV & Task Management ====================


class TestCOVAndTaskManagement:
    """Test COV callback management and task spawning."""

    def test_register_cov_callback(self):
        """Register a COV callback."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        callback = MagicMock()
        app.register_cov_callback(42, callback)
        assert 42 in app._cov_callbacks
        assert app._cov_callbacks[42] is callback

    def test_unregister_cov_callback(self):
        """Unregister a COV callback."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        callback = MagicMock()
        app.register_cov_callback(42, callback)
        app.unregister_cov_callback(42)
        assert 42 not in app._cov_callbacks

    def test_unregister_cov_callback_missing(self):
        """Unregistering a missing callback is a no-op."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app.unregister_cov_callback(99)  # Should not raise

    async def test_spawn_task_creates_and_tracks(self):
        """_spawn_task creates an asyncio task and tracks it."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        completed = False

        async def simple_coro():
            nonlocal completed
            completed = True

        app._spawn_task(simple_coro())
        assert len(app._background_tasks) == 1

        # Let the task complete
        await asyncio.sleep(0.01)
        assert completed
        # Task should clean up via done callback
        assert len(app._background_tasks) == 0

    async def test_spawn_task_logs_exception(self, caplog):
        """_spawn_task logs errors from failed background tasks."""
        app = BACnetApplication(DeviceConfig(instance_number=1))

        async def failing_coro():
            msg = "test background failure"
            raise RuntimeError(msg)

        with caplog.at_level(logging.ERROR, logger="bac_py.app.application"):
            app._spawn_task(failing_coro())
            await asyncio.sleep(0.05)

        assert len(app._background_tasks) == 0
        assert any("Background task failed" in m for m in caplog.messages)

    async def test_dispatch_cov_notification_invokes_callback(self):
        """_dispatch_cov_notification calls registered callback."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        callback = MagicMock()
        app._cov_callbacks[10] = callback

        # Build a minimal COV notification
        from bac_py.services.cov import COVNotificationRequest

        notif = COVNotificationRequest(
            subscriber_process_identifier=10,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[],
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app._dispatch_cov_notification(notif.encode(), source)

        callback.assert_called_once()
        call_args = callback.call_args[0]
        assert call_args[0].subscriber_process_identifier == 10
        assert call_args[1] is source

    async def test_dispatch_cov_notification_no_callback(self):
        """_dispatch_cov_notification is silent when no callback registered."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        from bac_py.services.cov import COVNotificationRequest

        notif = COVNotificationRequest(
            subscriber_process_identifier=99,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[],
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should not raise
        app._dispatch_cov_notification(notif.encode(), source)

    async def test_dispatch_cov_notification_callback_error(self):
        """_dispatch_cov_notification catches callback errors."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        callback = MagicMock(side_effect=RuntimeError("callback error"))
        app._cov_callbacks[10] = callback

        from bac_py.services.cov import COVNotificationRequest

        notif = COVNotificationRequest(
            subscriber_process_identifier=10,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[],
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should not raise
        app._dispatch_cov_notification(notif.encode(), source)

    async def test_handle_confirmed_cov_notification(self):
        """Confirmed COV notification handler dispatches and returns None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        callback = MagicMock()
        app._cov_callbacks[10] = callback

        from bac_py.services.cov import COVNotificationRequest

        notif = COVNotificationRequest(
            subscriber_process_identifier=10,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[],
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        result = await app._handle_confirmed_cov_notification(1, notif.encode(), source)
        assert result is None
        callback.assert_called_once()

    async def test_handle_unconfirmed_cov_notification(self):
        """Unconfirmed COV notification handler dispatches."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        callback = MagicMock()
        app._cov_callbacks[10] = callback

        from bac_py.services.cov import COVNotificationRequest

        notif = COVNotificationRequest(
            subscriber_process_identifier=10,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[],
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        await app._handle_unconfirmed_cov_notification(2, notif.encode(), source)
        callback.assert_called_once()

    async def test_send_confirmed_cov_notification_spawns_task(self):
        """send_confirmed_cov_notification creates a background task."""
        app = _make_started_app()
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app.send_confirmed_cov_notification(b"\x00", dest, 1)
        assert len(app._background_tasks) == 1
        # Let the task complete
        await asyncio.sleep(0.01)

    async def test_send_confirmed_cov_failure_logged(self):
        """_send_confirmed_cov logs failure without propagating."""
        app = _make_started_app()
        app._client_tsm.send_request = AsyncMock(side_effect=RuntimeError("network error"))
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should not raise
        await app._send_confirmed_cov(b"\x00", dest, 1)


# ==================== Section 2: Coverage gap tests ====================


class TestDCCEnforcementPaths:
    """Test DCC (DeviceCommunicationControl) enforcement on request paths."""

    async def test_dcc_disable_blocks_confirmed_request(self):
        """DCC DISABLE drops confirmed requests (except DCC/Reinitialize)."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        # Create a mock transaction
        txn = MagicMock()
        txn.invoke_id = 1
        txn.client_max_apdu_length = 1476

        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # ReadProperty (service choice 12) should be blocked by DCC DISABLE
        await app._dispatch_request(txn, ConfirmedServiceChoice.READ_PROPERTY, b"\x00", source)
        # No response should be sent (request was dropped)
        app._network.send.assert_not_called()

    async def test_dcc_disable_allows_dcc_request(self):
        """DCC DISABLE still allows DeviceCommunicationControl requests."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        txn = MagicMock()
        txn.invoke_id = 1
        txn.client_max_apdu_length = 1476

        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # DCC service should be dispatched even when DISABLE
        app._service_registry.dispatch_confirmed = AsyncMock(return_value=None)
        await app._dispatch_request(
            txn,
            ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
            b"\x00",
            source,
        )
        # Response should be sent (not blocked)
        app._network.send.assert_called_once()

    async def test_dcc_disable_initiation_blocks_outbound_unconfirmed(self):
        """DCC DISABLE_INITIATION suppresses outbound unconfirmed requests."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE_INITIATION

        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should silently return without sending
        app.unconfirmed_request(
            destination=dest,
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_data=b"\x00",
        )
        app._network.send.assert_not_called()

    async def test_dcc_disable_blocks_outbound_unconfirmed(self):
        """DCC DISABLE suppresses outbound unconfirmed requests."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Should silently return without sending
        app.unconfirmed_request(
            destination=dest,
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_data=b"\x00",
        )
        app._network.send.assert_not_called()

    async def test_dcc_disable_drops_inbound_unconfirmed(self):
        """DCC DISABLE drops incoming unconfirmed requests."""
        from bac_py.encoding.apdu import UnconfirmedRequestPDU

        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE

        pdu = UnconfirmedRequestPDU(
            service_choice=UnconfirmedServiceChoice.WHO_IS,
            service_request=b"\x00",
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        await app._handle_unconfirmed_request(pdu, source)
        # Should NOT be dispatched
        app._service_registry.dispatch_unconfirmed.assert_not_called()

    async def test_dcc_disable_initiation_drops_non_whois_unconfirmed(self):
        """DCC DISABLE_INITIATION drops non-Who-Is unconfirmed requests."""
        from bac_py.encoding.apdu import UnconfirmedRequestPDU

        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE_INITIATION

        pdu = UnconfirmedRequestPDU(
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_request=b"\x00",
        )
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app._service_registry.dispatch_unconfirmed = AsyncMock()

        await app._handle_unconfirmed_request(pdu, source)
        # I-AM should be blocked under DISABLE_INITIATION
        app._service_registry.dispatch_unconfirmed.assert_not_called()


class TestDCCTimerExpiry:
    """Test DCC timer auto-re-enable functionality."""

    async def test_dcc_timer_expired_re_enables(self):
        """_dcc_timer_expired re-enables communication."""
        app = _make_started_app()
        app._dcc_state = EnableDisable.DISABLE
        app._dcc_timer = MagicMock()

        app._dcc_timer_expired()

        assert app._dcc_state == EnableDisable.ENABLE
        assert app._dcc_timer is None

    async def test_set_dcc_state_with_duration(self):
        """set_dcc_state with duration schedules auto-re-enable timer."""
        app = _make_started_app()

        app.set_dcc_state(EnableDisable.DISABLE, duration=1)
        assert app._dcc_state == EnableDisable.DISABLE
        assert app._dcc_timer is not None

        # Clean up the timer
        app._dcc_timer.cancel()
        app._dcc_timer = None

    async def test_set_dcc_state_cancels_previous_timer(self):
        """set_dcc_state cancels any existing timer before setting new state."""
        app = _make_started_app()
        old_timer = MagicMock()
        app._dcc_timer = old_timer

        app.set_dcc_state(EnableDisable.ENABLE)

        old_timer.cancel.assert_called_once()
        assert app._dcc_state == EnableDisable.ENABLE
        assert app._dcc_timer is None


class TestDeviceInfoCachePaths:
    """Test I-Am caching for max APDU size per Clause 19.4."""

    async def test_handle_i_am_for_cache_populates(self):
        """_handle_i_am_for_cache stores device info from I-Am."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            max_apdu_length=480,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        await app._handle_i_am_for_cache(UnconfirmedServiceChoice.I_AM, iam.encode(), source)

        info = app._device_info_cache.get(source)
        assert info is not None
        assert info.max_apdu_length == 480
        assert info.segmentation_supported == int(Segmentation.BOTH)

    async def test_handle_i_am_for_cache_decode_error(self):
        """_handle_i_am_for_cache handles decode errors gracefully."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # Malformed data should not raise
        await app._handle_i_am_for_cache(UnconfirmedServiceChoice.I_AM, b"\xff\xff", source)
        assert source not in app._device_info_cache

    async def test_confirmed_request_uses_cached_max_apdu(self):
        """confirmed_request constrains APDU size using cached device info."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # Populate cache with a device that has smaller max APDU
        app._device_info_cache[source] = DeviceInfo(
            max_apdu_length=480,
            segmentation_supported=int(Segmentation.BOTH),
        )

        await app.confirmed_request(
            destination=source,
            service_choice=ConfirmedServiceChoice.READ_PROPERTY,
            service_data=b"\x00",
        )

        # Verify send_request was called with max_apdu_override=480
        call_kwargs = app._client_tsm.send_request.call_args
        assert call_kwargs.kwargs.get("max_apdu_override") == 480

    def test_get_device_info_returns_cached(self):
        """get_device_info returns cached info or None."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        assert app.get_device_info(source) is None

        app._device_info_cache[source] = DeviceInfo(
            max_apdu_length=480,
            segmentation_supported=0,
        )
        info = app.get_device_info(source)
        assert info is not None
        assert info.max_apdu_length == 480


# ---------------------------------------------------------------------------
# Additional coverage tests for BACnetApplication
# ---------------------------------------------------------------------------


class TestApplicationStartError:
    """Test start() error when neither router nor network is available."""

    async def test_start_runtime_error_no_network(self):
        """start() raises RuntimeError when neither router nor network init (lines 302-303)."""
        app = BACnetApplication(DeviceConfig(instance_number=1))

        # Patch the start methods to not actually create network/router
        with patch.object(app, "_start_non_router_mode", new=AsyncMock()):
            # After _start_non_router_mode, _network is still None
            app._network = None
            app._router = None
            with pytest.raises(RuntimeError, match="Neither router nor network"):
                await app.start()


class TestApplicationStopBranches:
    """Test stop() cleanup branches (lines 396-432)."""

    async def test_stop_cleans_up_event_engine(self):
        """stop() shuts down event engine."""
        app = _make_started_app()
        mock_engine = MagicMock()
        mock_engine.stop = AsyncMock()
        app._event_engine = mock_engine
        app._cov_manager = None
        app._dcc_timer = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        await app.stop()
        mock_engine.stop.assert_called_once()
        assert app._event_engine is None

    async def test_stop_shuts_down_cov_manager(self):
        """stop() calls cov_manager.shutdown()."""
        app = _make_started_app()
        mock_cov = MagicMock()
        app._cov_manager = mock_cov
        app._event_engine = None
        app._dcc_timer = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        await app.stop()
        mock_cov.shutdown.assert_called_once()
        assert app._cov_manager is None

    async def test_stop_cancels_dcc_timer(self):
        """stop() cancels DCC timer."""
        app = _make_started_app()
        mock_timer = MagicMock()
        app._dcc_timer = mock_timer
        app._event_engine = None
        app._cov_manager = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        await app.stop()
        mock_timer.cancel.assert_called_once()
        assert app._dcc_timer is None

    async def test_stop_cancels_client_transactions(self):
        """stop() cancels pending client transactions."""
        app = _make_started_app()
        mock_future = MagicMock()
        mock_future.done.return_value = False
        mock_txn = MagicMock()
        mock_txn.future = mock_future
        app._client_tsm.active_transactions.return_value = [mock_txn]
        app._event_engine = None
        app._cov_manager = None
        app._dcc_timer = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        await app.stop()
        mock_future.cancel.assert_called_once()

    async def test_stop_router_mode(self):
        """stop() calls router.stop() in router mode."""
        app = _make_started_app()
        mock_router = MagicMock()
        mock_router.stop = AsyncMock()
        app._router = mock_router
        app._transport = None
        app._event_engine = None
        app._cov_manager = None
        app._dcc_timer = None

        await app.stop()
        mock_router.stop.assert_called_once()


class TestApplicationRunMethod:
    """Test run() method (lines 438-441)."""

    async def test_run_starts_and_stops(self):
        """run() starts the app and blocks until stop."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app.start = AsyncMock()
        app.stop = AsyncMock()
        app._stop_event = asyncio.Event()

        # Set the stop event after a short delay
        async def set_stop():
            await asyncio.sleep(0.01)
            app._stop_event.set()

        task = asyncio.create_task(app.run())
        stop_task = asyncio.create_task(set_stop())

        await task
        await stop_task
        app.start.assert_called_once()
        app.stop.assert_called_once()


class TestAPDUDispatchWithoutClientTSM:
    """Test _on_apdu_received dispatch paths when client_tsm is None."""

    def test_segmented_complex_ack_no_client_tsm(self):
        """Segmented ComplexACK without client_tsm is a no-op (lines 859-860)."""
        app = _make_started_app()
        app._client_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        pdu = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa",
        )
        apdu_bytes = encode_apdu(pdu)
        # Should not crash
        app._on_apdu_received(apdu_bytes, source)

    def test_error_pdu_no_client_tsm(self):
        """ErrorPDU without client_tsm is a no-op (lines 867-868)."""
        app = _make_started_app()
        app._client_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        from bac_py.types.enums import ErrorClass, ErrorCode

        pdu = ErrorPDU(
            invoke_id=1,
            service_choice=12,
            error_class=ErrorClass.OBJECT,
            error_code=ErrorCode.UNKNOWN_OBJECT,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)

    def test_reject_pdu_no_client_tsm(self):
        """RejectPDU without client_tsm is a no-op (lines 878-879)."""
        app = _make_started_app()
        app._client_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        pdu = RejectPDU(
            invoke_id=1,
            reject_reason=RejectReason.UNRECOGNIZED_SERVICE,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)

    def test_abort_pdu_no_client_tsm(self):
        """AbortPDU without client_tsm is a no-op (lines 883-884)."""
        app = _make_started_app()
        app._client_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        pdu = AbortPDU(
            sent_by_server=True,
            invoke_id=1,
            abort_reason=AbortReason.OTHER,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)

    def test_segment_ack_server_no_client_tsm(self):
        """SegmentACK (sent_by_server=True) without client_tsm is a no-op (lines 891-892)."""
        from bac_py.encoding.apdu import SegmentAckPDU

        app = _make_started_app()
        app._client_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        pdu = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=1,
            sequence_number=0,
            actual_window_size=2,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)

    def test_segment_ack_client_no_server_tsm(self):
        """SegmentACK (sent_by_server=False) without server_tsm is a no-op (lines 895-896)."""
        from bac_py.encoding.apdu import SegmentAckPDU

        app = _make_started_app()
        app._server_tsm = None
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        pdu = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=0,
            actual_window_size=2,
        )
        apdu_bytes = encode_apdu(pdu)
        app._on_apdu_received(apdu_bytes, source)


class TestHandleSegmentedRequestDispatch:
    """Test _handle_segmented_request with service_data dispatch (lines 911-914)."""

    async def test_segmented_request_dispatches_when_complete(self):
        """_handle_segmented_request dispatches when service_data is not None (line 914)."""
        app = _make_started_app()
        txn = MagicMock()
        app._server_tsm.receive_confirmed_request.return_value = (txn, b"\x01\x02")

        pdu = MagicMock(spec=ConfirmedRequestPDU)
        pdu.service_choice = 12
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # Mock _spawn_task to avoid asyncio.create_task needing a real loop
        app._spawn_task = MagicMock()
        app._handle_segmented_request(pdu, source)
        app._spawn_task.assert_called_once()

    async def test_segmented_request_no_dispatch_when_data_none(self):
        """_handle_segmented_request does NOT dispatch when service_data is None."""
        app = _make_started_app()
        txn = MagicMock()
        app._server_tsm.receive_confirmed_request.return_value = (txn, None)

        pdu = MagicMock(spec=ConfirmedRequestPDU)
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._spawn_task = MagicMock()
        app._handle_segmented_request(pdu, source)
        app._spawn_task.assert_not_called()


# ==================== Coverage gap tests: uncovered lines/branches ====================


class TestRouterBBMDConfig:
    """Test BBMD config attach during router setup (line 369)."""

    async def test_router_port_with_bbmd_config(self):
        """Router port with bbmd_config calls transport.attach_bbmd."""
        from bac_py.app.application import BBMDConfig

        bbmd_cfg = BBMDConfig(bdt_entries=[])
        router_cfg = DeviceConfig(
            instance_number=1,
            router_config=RouterConfig(
                ports=[
                    RouterPortConfig(port_id=1, network_number=100, port=0, bbmd_config=bbmd_cfg),
                ],
                application_port_id=1,
            ),
        )
        app = BACnetApplication(router_cfg)

        mock_t = _make_mock_transport()
        mock_t.attach_bbmd = AsyncMock()

        with (
            patch(
                "bac_py.app.application.BIPTransport",
                return_value=mock_t,
            ),
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                mock_t.attach_bbmd.assert_called_once_with(None)
            finally:
                await app.stop()


class TestAPDUIsInstanceGuards:
    """Test PDU type isinstance guards in _on_apdu_received (lines 843-888).

    These guards return early if decode_apdu returns a type that doesn't match
    the PDU type nibble. We mock decode_apdu to return mismatched types.
    """

    def _make_apdu_bytes(self, pdu_type_nibble: int) -> bytes:
        """Create minimal APDU bytes with the given PDU type nibble."""
        # Byte 0: PDU type nibble in upper 4 bits, flags in lower 4 bits
        # Add enough padding bytes to prevent decode errors before our mock kicks in
        return bytes([pdu_type_nibble << 4, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    def test_confirmed_request_isinstance_guard(self):
        """ConfirmedRequest type but decode returns wrong type (line 843-844)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            # PDU type 0 = CONFIRMED_REQUEST but decode returns non-ConfirmedRequestPDU
            app._on_apdu_received(self._make_apdu_bytes(0), source)
        # Should return early without crashing; no TSM calls
        app._server_tsm.receive_confirmed_request.assert_not_called()

    def test_simple_ack_isinstance_guard(self):
        """SimpleAck type but decode returns wrong type (line 852-853)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            app._on_apdu_received(self._make_apdu_bytes(2), source)
        app._client_tsm.handle_simple_ack.assert_not_called()

    def test_complex_ack_isinstance_guard(self):
        """ComplexAck type but decode returns wrong type (line 857-858)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            app._on_apdu_received(self._make_apdu_bytes(3), source)
        app._client_tsm.handle_complex_ack.assert_not_called()
        app._client_tsm.handle_segmented_complex_ack.assert_not_called()

    def test_error_isinstance_guard(self):
        """Error type but decode returns wrong type (line 866-867)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            app._on_apdu_received(self._make_apdu_bytes(5), source)
        app._client_tsm.handle_error.assert_not_called()

    def test_reject_isinstance_guard(self):
        """Reject type but decode returns wrong type (line 877-878)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            app._on_apdu_received(self._make_apdu_bytes(6), source)
        app._client_tsm.handle_reject.assert_not_called()

    def test_abort_isinstance_guard(self):
        """Abort type but decode returns wrong type (line 882-883)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            app._on_apdu_received(self._make_apdu_bytes(7), source)
        app._client_tsm.handle_abort.assert_not_called()

    def test_segment_ack_isinstance_guard(self):
        """SegmentAck type but decode returns wrong type (line 887-888)."""
        app = _make_started_app()
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        with patch("bac_py.app.application.decode_apdu", return_value=MagicMock()):
            app._on_apdu_received(self._make_apdu_bytes(4), source)
        app._client_tsm.handle_segment_ack.assert_not_called()
        app._server_tsm.handle_segment_ack_for_response.assert_not_called()


class TestStopBranchPartials:
    """Test shutdown branch partials: 411->416, 413->412, 429->432, 438->441."""

    async def test_stop_client_tsm_with_done_future(self):
        """stop() skips cancelling already-done futures (branch 413->412)."""
        app = _make_started_app()
        mock_future = MagicMock()
        mock_future.done.return_value = True  # Already done
        mock_txn = MagicMock()
        mock_txn.future = mock_future
        app._client_tsm.active_transactions.return_value = [mock_txn]
        app._event_engine = None
        app._cov_manager = None
        app._dcc_timer = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        await app.stop()
        mock_future.cancel.assert_not_called()

    async def test_stop_no_router_no_transport(self):
        """stop() with neither router nor transport (branch 429->432)."""
        app = _make_started_app()
        app._router = None
        app._transport = None
        app._event_engine = None
        app._cov_manager = None
        app._dcc_timer = None
        app._client_tsm = None

        # Should not crash
        await app.stop()
        assert app._running is False

    async def test_run_with_no_stop_event(self):
        """run() with _stop_event=None skips wait (branch 438->441)."""
        app = BACnetApplication(DeviceConfig(instance_number=1))
        app.start = AsyncMock()
        app.stop = AsyncMock()
        app._stop_event = None

        await app.run()
        app.start.assert_called_once()
        app.stop.assert_called_once()


class TestMemoryCleanupOnStop:
    """Verify stop() clears caches and listeners to prevent memory leaks."""

    async def test_stop_clears_unconfirmed_listeners(self):
        """stop() should clear _unconfirmed_listeners."""
        app = _make_started_app()
        app._event_engine = None
        app._cov_manager = None
        app._dcc_timer = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        # Register some listeners
        app._unconfirmed_listeners[8] = [lambda *a: None]
        app._unconfirmed_listeners[1] = [lambda *a: None, lambda *a: None]
        assert len(app._unconfirmed_listeners) == 2

        await app.stop()
        assert len(app._unconfirmed_listeners) == 0

    async def test_stop_clears_device_info_cache(self):
        """stop() should clear _device_info_cache."""
        app = _make_started_app()
        app._event_engine = None
        app._cov_manager = None
        app._dcc_timer = None
        app._transport = MagicMock()
        app._transport.stop = AsyncMock()

        # Populate cache
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        app._device_info_cache[source] = DeviceInfo(max_apdu_length=480, segmentation_supported=0)
        assert len(app._device_info_cache) == 1

        await app.stop()
        assert len(app._device_info_cache) == 0


class TestDeviceInfoCacheEviction:
    """Test FIFO eviction when device info cache exceeds 1000 entries."""

    async def test_cache_evicts_oldest_entries_at_limit(self):
        """When cache hits 1000 entries, oldest 100 are evicted."""
        app = _make_started_app()

        # Fill cache to exactly 1000 entries
        for i in range(1000):
            mac = i.to_bytes(4, "big") + b"\xba\xc0"
            source = BACnetAddress(mac_address=mac)
            app._device_info_cache[source] = DeviceInfo(
                max_apdu_length=480, segmentation_supported=0
            )
        assert len(app._device_info_cache) == 1000

        # Add one more via _handle_i_am_for_cache to trigger eviction
        new_source = BACnetAddress(mac_address=b"\xff\xff\xff\xff\xba\xc0")
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 9999),
            max_apdu_length=1024,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=42,
        )
        await app._handle_i_am_for_cache(UnconfirmedServiceChoice.I_AM, iam.encode(), new_source)

        # Should have evicted 100 oldest, then added 1 = 901
        assert len(app._device_info_cache) == 901
        # The new entry should be present
        assert app._device_info_cache.get(new_source) is not None
        # The first entry (oldest) should be evicted
        first_mac = (0).to_bytes(4, "big") + b"\xba\xc0"
        first_source = BACnetAddress(mac_address=first_mac)
        assert first_source not in app._device_info_cache

    async def test_cache_under_limit_no_eviction(self):
        """Under 1000 entries, no eviction occurs."""
        app = _make_started_app()

        for i in range(10):
            mac = i.to_bytes(4, "big") + b"\xba\xc0"
            source = BACnetAddress(mac_address=mac)
            app._device_info_cache[source] = DeviceInfo(
                max_apdu_length=480, segmentation_supported=0
            )

        new_source = BACnetAddress(mac_address=b"\xff\xff\xff\xff\xba\xc0")
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 9999),
            max_apdu_length=1024,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=42,
        )
        await app._handle_i_am_for_cache(UnconfirmedServiceChoice.I_AM, iam.encode(), new_source)

        # All 11 entries should be present (10 + 1 new)
        assert len(app._device_info_cache) == 11


class TestConfirmedRequestDispatchLine933:
    """Test _handle_confirmed_request dispatches to _dispatch_request (line 933)."""

    async def test_handle_confirmed_request_dispatches(self):
        """When TSM returns (txn, service_data), _dispatch_request is called."""
        app = _make_started_app()
        txn = MagicMock()
        txn.invoke_id = 1
        txn.client_max_apdu_length = 1476
        app._server_tsm.receive_confirmed_request.return_value = (txn, b"\x01\x02")

        pdu = MagicMock(spec=ConfirmedRequestPDU)
        pdu.service_choice = 12
        pdu.segmented = False
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        app._service_registry.dispatch_confirmed = AsyncMock(return_value=None)
        await app._handle_confirmed_request(pdu, source)
        # Should have sent a SimpleAck response
        app._network.send.assert_called_once()


# --- IPv6 transport selection tests ---


def _make_mock_bip6_transport():
    """Create a mock BIP6Transport with required attributes."""
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    transport.local_mac = b"\xaa\xbb\xcc"  # 3-byte VMAC
    transport.max_npdu_length = 1440
    transport.on_receive = MagicMock()
    transport.foreign_device = None
    transport.attach_foreign_device = AsyncMock()
    transport.bbmd = None
    return transport


class TestDeviceConfigIPv6:
    """Test DeviceConfig IPv6 fields."""

    def test_ipv6_defaults(self):
        cfg = DeviceConfig(instance_number=1)
        assert cfg.ipv6 is False
        assert cfg.multicast_address == ""
        assert cfg.vmac is None

    def test_ipv6_enabled(self):
        cfg = DeviceConfig(instance_number=1, ipv6=True)
        assert cfg.ipv6 is True

    def test_ipv6_custom_multicast(self):
        cfg = DeviceConfig(instance_number=1, ipv6=True, multicast_address="ff02::1234")
        assert cfg.multicast_address == "ff02::1234"

    def test_ipv6_custom_vmac(self):
        vmac = b"\x01\x02\x03"
        cfg = DeviceConfig(instance_number=1, ipv6=True, vmac=vmac)
        assert cfg.vmac == vmac


class TestRouterPortConfigIPv6:
    """Test RouterPortConfig IPv6 fields."""

    def test_ipv6_defaults(self):
        cfg = RouterPortConfig(port_id=1, network_number=100)
        assert cfg.ipv6 is False
        assert cfg.multicast_address == ""
        assert cfg.vmac is None

    def test_ipv6_enabled(self):
        cfg = RouterPortConfig(port_id=1, network_number=100, ipv6=True)
        assert cfg.ipv6 is True

    def test_ipv6_custom_values(self):
        cfg = RouterPortConfig(
            port_id=1,
            network_number=100,
            ipv6=True,
            multicast_address="ff02::bac1",
            vmac=b"\xaa\xbb\xcc",
        )
        assert cfg.multicast_address == "ff02::bac1"
        assert cfg.vmac == b"\xaa\xbb\xcc"


class TestIPv6TransportSelection:
    """Test that IPv6 config creates BIP6Transport."""

    async def test_non_router_ipv6_flag_creates_bip6(self):
        """DeviceConfig(ipv6=True) should create BIP6Transport."""
        cfg = DeviceConfig(instance_number=1, ipv6=True, port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_bip6_transport()

        with patch("bac_py.app.application.BIP6Transport", return_value=mock_t) as cls:
            await app.start()
            try:
                cls.assert_called_once()
                call_kwargs = cls.call_args[1]
                assert call_kwargs["interface"] == "::"
                assert call_kwargs["multicast_address"] == "ff02::bac0"
                assert app._transport is mock_t
            finally:
                await app.stop()

    async def test_non_router_ipv6_interface_auto_detects(self):
        """An IPv6 interface address (containing ':') selects BIP6Transport."""
        cfg = DeviceConfig(instance_number=1, interface="fd00::1", port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_bip6_transport()

        with patch("bac_py.app.application.BIP6Transport", return_value=mock_t) as cls:
            await app.start()
            try:
                cls.assert_called_once()
                call_kwargs = cls.call_args[1]
                assert call_kwargs["interface"] == "fd00::1"
            finally:
                await app.stop()

    async def test_non_router_ipv6_custom_multicast(self):
        """Custom multicast address is passed through."""
        cfg = DeviceConfig(instance_number=1, ipv6=True, multicast_address="ff02::1234", port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_bip6_transport()

        with patch("bac_py.app.application.BIP6Transport", return_value=mock_t) as cls:
            await app.start()
            try:
                call_kwargs = cls.call_args[1]
                assert call_kwargs["multicast_address"] == "ff02::1234"
            finally:
                await app.stop()

    async def test_non_router_ipv6_custom_vmac(self):
        """Custom VMAC is passed through."""
        vmac = b"\xdd\xee\xff"
        cfg = DeviceConfig(instance_number=1, ipv6=True, vmac=vmac, port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_bip6_transport()

        with patch("bac_py.app.application.BIP6Transport", return_value=mock_t) as cls:
            await app.start()
            try:
                call_kwargs = cls.call_args[1]
                assert call_kwargs["vmac"] == vmac
            finally:
                await app.stop()

    async def test_non_router_ipv4_still_creates_bip(self):
        """Default IPv4 config still creates BIPTransport."""
        cfg = DeviceConfig(instance_number=1, port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_transport()

        with patch("bac_py.app.application.BIPTransport", return_value=mock_t) as cls:
            await app.start()
            try:
                cls.assert_called_once()
                assert app._transport is mock_t
            finally:
                await app.stop()

    async def test_router_ipv6_port_creates_bip6(self):
        """Router port with ipv6=True creates BIP6Transport."""
        router_cfg = DeviceConfig(
            instance_number=1,
            router_config=RouterConfig(
                ports=[
                    RouterPortConfig(port_id=1, network_number=100, ipv6=True, port=0),
                ],
                application_port_id=1,
            ),
        )
        app = BACnetApplication(router_cfg)

        mock_t = _make_mock_bip6_transport()

        with (
            patch("bac_py.app.application.BIP6Transport", return_value=mock_t) as bip6_cls,
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                bip6_cls.assert_called_once()
                call_kwargs = bip6_cls.call_args[1]
                assert call_kwargs["interface"] == "::"
                assert call_kwargs["multicast_address"] == "ff02::bac0"
            finally:
                await app.stop()

    async def test_router_mixed_ipv4_ipv6_ports(self):
        """Router with one IPv4 and one IPv6 port creates correct transports."""
        router_cfg = DeviceConfig(
            instance_number=1,
            router_config=RouterConfig(
                ports=[
                    RouterPortConfig(port_id=1, network_number=100, port=0),
                    RouterPortConfig(port_id=2, network_number=200, ipv6=True, port=0),
                ],
                application_port_id=1,
            ),
        )
        app = BACnetApplication(router_cfg)

        mock_t_ipv4 = _make_mock_transport()
        mock_t_ipv6 = _make_mock_bip6_transport()

        with (
            patch("bac_py.app.application.BIPTransport", return_value=mock_t_ipv4) as bip_cls,
            patch("bac_py.app.application.BIP6Transport", return_value=mock_t_ipv6) as bip6_cls,
            patch("bac_py.app.application.NetworkRouter") as mock_router_cls,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.start = AsyncMock()
            mock_router_instance.stop = AsyncMock()
            mock_router_cls.return_value = mock_router_instance

            await app.start()
            try:
                bip_cls.assert_called_once()
                bip6_cls.assert_called_once()
                assert len(app._transports) == 2
            finally:
                await app.stop()


class TestParseBIP6Address:
    """Test _parse_bip6_address helper."""

    def test_bracketed_with_port(self):
        app = BACnetApplication(DeviceConfig(instance_number=1))
        addr = app._parse_bip6_address("[fd00::1]:47809")
        assert addr.host == "fd00::1"
        assert addr.port == 47809

    def test_bracketed_without_port(self):
        app = BACnetApplication(DeviceConfig(instance_number=1))
        addr = app._parse_bip6_address("[fd00::1]")
        assert addr.host == "fd00::1"
        assert addr.port == 0xBAC0

    def test_bare_address_default_port(self):
        app = BACnetApplication(DeviceConfig(instance_number=1))
        addr = app._parse_bip6_address("fd00::1")
        assert addr.host == "fd00::1"
        assert addr.port == 0xBAC0


class TestForeignDeviceIPv6:
    """Test foreign device registration with BIP6Transport."""

    async def test_register_with_bip6_transport(self):
        """register_as_foreign_device with BIP6Transport parses IPv6 address."""
        from bac_py.transport.bip6 import BIP6Transport

        cfg = DeviceConfig(instance_number=1, ipv6=True, port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_bip6_transport()
        mock_t.__class__ = BIP6Transport  # isinstance check

        app._transport = mock_t
        app._running = True

        await app.register_as_foreign_device("[fd00::1]:47808", ttl=120)
        mock_t.attach_foreign_device.assert_called_once()
        call_args = mock_t.attach_foreign_device.call_args
        addr = call_args[0][0]
        assert addr.host == "fd00::1"
        assert addr.port == 47808
        assert call_args[0][1] == 120

    async def test_register_not_started_raises(self):
        cfg = DeviceConfig(instance_number=1, ipv6=True)
        app = BACnetApplication(cfg)
        with pytest.raises(RuntimeError, match="not started"):
            await app.register_as_foreign_device("[fd00::1]:47808")

    async def test_register_already_registered_raises(self):
        from bac_py.transport.bip6 import BIP6Transport

        cfg = DeviceConfig(instance_number=1, ipv6=True, port=0)
        app = BACnetApplication(cfg)

        mock_t = _make_mock_bip6_transport()
        mock_t.__class__ = BIP6Transport
        mock_t.foreign_device = MagicMock()  # Already registered

        app._transport = mock_t
        app._running = True

        with pytest.raises(RuntimeError, match="Already registered"):
            await app.register_as_foreign_device("[fd00::1]:47808")
