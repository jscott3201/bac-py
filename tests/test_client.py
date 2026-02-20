"""Tests for the unified Client class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bac_py.app.application import DeviceConfig
from bac_py.client import Client, _parse_enum, _resolve_broadcast_destination
from bac_py.encoding.primitives import (
    encode_application_character_string,
    encode_application_real,
)
from bac_py.network.address import GLOBAL_BROADCAST, BACnetAddress, parse_address
from bac_py.services.read_property import ReadPropertyACK
from bac_py.types.enums import (
    EnableDisable,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
)
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

    async def test_method_before_start_raises(self):
        client = Client()
        with pytest.raises(RuntimeError, match="Client not started"):
            await client.read("192.168.1.100", "ai,1", "pv")

    @patch("bac_py.client.BACnetApplication")
    async def test_context_manager_lifecycle(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        async with Client() as client:
            assert client._app is mock_app
            assert client._client is not None
            mock_app.start.assert_called_once()
        mock_app.stop.assert_called_once()
        assert client._app is None
        assert client._client is None

    @patch("bac_py.client.BACnetApplication")
    async def test_app_property_after_start(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        async with Client() as client:
            assert client.app is mock_app

    @patch("bac_py.client.BACnetApplication")
    async def test_stop_on_exception(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        with pytest.raises(ValueError, match="boom"):
            async with Client():
                raise ValueError("boom")
        mock_app.stop.assert_called_once()


class TestClientDelegation:
    """Test that Client methods delegate to BACnetClient."""

    @patch("bac_py.client.BACnetApplication")
    async def test_read_delegates(self, mock_app_cls):
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

        async with Client() as client:
            result = await client.read("192.168.1.100", "ai,1", "pv")
            assert isinstance(result, float)
            assert result == pytest.approx(72.5)

    @patch("bac_py.client.BACnetApplication")
    async def test_write_delegates(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app.confirmed_request = AsyncMock(return_value=b"")
        mock_app_cls.return_value = mock_app

        async with Client() as client:
            await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
            mock_app.confirmed_request.assert_called_once()

    @patch("bac_py.client.BACnetApplication")
    async def test_read_multiple_delegates(self, mock_app_cls):
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

        async with Client() as client:
            result = await client.read_multiple(
                "192.168.1.100",
                {"ai,1": ["pv", "name"]},
            )
            assert "analog-input,1" in result
            props = result["analog-input,1"]
            assert props["present-value"] == pytest.approx(72.5)
            assert props["object-name"] == "Zone Temp"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestResolveBroadcastDestination:
    """Tests for _resolve_broadcast_destination()."""

    def test_none_returns_global_broadcast(self):
        result = _resolve_broadcast_destination(None)
        assert result is GLOBAL_BROADCAST

    def test_string_parsed(self):
        result = _resolve_broadcast_destination("192.168.1.255")
        assert isinstance(result, BACnetAddress)
        assert result == parse_address("192.168.1.255")

    def test_bacnet_address_passthrough(self):
        addr = parse_address("10.0.0.1")
        result = _resolve_broadcast_destination(addr)
        assert result is addr


class TestParseEnum:
    """Tests for _parse_enum()."""

    def test_enum_passthrough(self):
        result = _parse_enum(EnableDisable.DISABLE, EnableDisable)
        assert result is EnableDisable.DISABLE

    def test_string_lowercase(self):
        result = _parse_enum("disable", EnableDisable)
        assert result is EnableDisable.DISABLE

    def test_string_uppercase(self):
        result = _parse_enum("DISABLE", EnableDisable)
        assert result is EnableDisable.DISABLE

    def test_string_with_hyphens(self):
        result = _parse_enum("disable-initiation", EnableDisable)
        assert result is EnableDisable.DISABLE_INITIATION

    def test_string_with_whitespace(self):
        result = _parse_enum("  coldstart  ", ReinitializedState)
        assert result is ReinitializedState.COLDSTART

    def test_string_start_backup(self):
        result = _parse_enum("start-backup", ReinitializedState)
        assert result is ReinitializedState.START_BACKUP

    def test_invalid_string_raises(self):
        with pytest.raises(KeyError):
            _parse_enum("nonexistent", EnableDisable)


# ---------------------------------------------------------------------------
# Refactored method tests — verify string parsing and delegation
# ---------------------------------------------------------------------------


def _make_mock_client():
    """Create a Client with a mock BACnetClient injected."""
    client = Client()
    mock_bacnet_client = MagicMock()
    # Make all methods return AsyncMock by default
    for attr in (
        "get_alarm_summary",
        "get_enrollment_summary",
        "get_event_information",
        "acknowledge_alarm",
        "send_confirmed_text_message",
        "send_unconfirmed_text_message",
        "backup_device",
        "restore_device",
        "query_audit_log",
        "subscribe_cov_property",
        "subscribe_cov",
        "unsubscribe_cov",
        "device_communication_control",
        "reinitialize_device",
        "time_synchronization",
        "utc_time_synchronization",
        "atomic_read_file",
        "atomic_write_file",
        "create_object",
        "delete_object",
        "add_list_element",
        "remove_list_element",
        "who_has",
        "who_is",
        "discover",
        "discover_extended",
        "confirmed_private_transfer",
        "unconfirmed_private_transfer",
        "traverse_hierarchy",
        "subscribe_cov_property_multiple",
        "write_group",
        "discover_unconfigured",
    ):
        setattr(mock_bacnet_client, attr, AsyncMock())
    # Sync methods
    for attr in (
        "time_synchronization",
        "utc_time_synchronization",
        "send_unconfirmed_text_message",
        "unconfirmed_private_transfer",
        "write_group",
    ):
        setattr(mock_bacnet_client, attr, MagicMock())

    mock_app = MagicMock()
    mock_app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, 999)
    client._client = mock_bacnet_client
    client._app = mock_app
    return client, mock_bacnet_client


class TestStringAddressParsing:
    """Verify methods accept string addresses and parse them."""

    async def test_get_alarm_summary_string_address(self):
        client, mock = _make_mock_client()
        await client.get_alarm_summary("192.168.1.100")
        addr_arg = mock.get_alarm_summary.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_get_enrollment_summary_string_address(self):
        from bac_py.types.enums import AcknowledgmentFilter

        client, mock = _make_mock_client()
        await client.get_enrollment_summary("10.0.0.1", AcknowledgmentFilter.ALL)
        addr_arg = mock.get_enrollment_summary.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_get_event_information_string_address(self):
        client, mock = _make_mock_client()
        await client.get_event_information("192.168.1.100")
        addr_arg = mock.get_event_information.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_acknowledge_alarm_string_address(self):
        from bac_py.types.constructed import BACnetTimeStamp
        from bac_py.types.enums import EventState
        from bac_py.types.primitives import BACnetTime

        ts = BACnetTimeStamp(choice=0, value=BACnetTime(12, 0, 0, 0))
        client, mock = _make_mock_client()
        await client.acknowledge_alarm(
            "192.168.1.100", 1, "ai,1", EventState.NORMAL, ts, "test", ts
        )
        addr_arg = mock.acknowledge_alarm.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_backup_string_address(self):
        client, mock = _make_mock_client()
        await client.backup("10.0.0.1")
        addr_arg = mock.backup_device.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_restore_string_address(self):
        from bac_py.app.client import BackupData

        client, mock = _make_mock_client()
        await client.restore("10.0.0.1", BackupData(device_instance=1, configuration_files=[]))
        addr_arg = mock.restore_device.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_query_audit_log_string_address(self):
        client, mock = _make_mock_client()
        query = MagicMock()
        await client.query_audit_log("10.0.0.1", "audit-log,1", query)
        addr_arg = mock.query_audit_log.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_subscribe_cov_property_string_address(self):
        client, mock = _make_mock_client()
        await client.subscribe_cov_property("10.0.0.1", "ai,1", "pv", 1)
        addr_arg = mock.subscribe_cov_property.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_device_communication_control_string_address(self):
        client, mock = _make_mock_client()
        await client.device_communication_control("10.0.0.1", "disable")
        addr_arg = mock.device_communication_control.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_reinitialize_device_string_address(self):
        client, mock = _make_mock_client()
        await client.reinitialize_device("10.0.0.1", "coldstart")
        addr_arg = mock.reinitialize_device.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_create_object_string_address(self):
        client, mock = _make_mock_client()
        await client.create_object("10.0.0.1", object_type="av")
        addr_arg = mock.create_object.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_delete_object_string_address(self):
        client, mock = _make_mock_client()
        await client.delete_object("10.0.0.1", "av,1")
        addr_arg = mock.delete_object.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)


class TestBACnetAddressPassthrough:
    """Verify methods accept BACnetAddress objects directly."""

    async def test_get_alarm_summary_bacnet_address(self):
        client, mock = _make_mock_client()
        addr = parse_address("192.168.1.100")
        await client.get_alarm_summary(addr)
        addr_arg = mock.get_alarm_summary.call_args[0][0]
        assert addr_arg == addr

    async def test_backup_bacnet_address(self):
        client, mock = _make_mock_client()
        addr = parse_address("192.168.1.100")
        await client.backup(addr)
        addr_arg = mock.backup_device.call_args[0][0]
        assert addr_arg == addr

    async def test_subscribe_cov_bacnet_address(self):
        client, mock = _make_mock_client()
        addr = parse_address("192.168.1.100")
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        await client.subscribe_cov(addr, oid, 1)
        addr_arg = mock.subscribe_cov.call_args[0][0]
        assert addr_arg == addr

    async def test_unsubscribe_cov_bacnet_address(self):
        client, mock = _make_mock_client()
        addr = parse_address("192.168.1.100")
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        await client.unsubscribe_cov(addr, oid, 1)
        addr_arg = mock.unsubscribe_cov.call_args[0][0]
        assert addr_arg == addr


class TestNewStringSupport:
    """Test newly widened string support on previously typed-only methods."""

    def test_time_synchronization_string_address(self):
        from bac_py.types.primitives import BACnetDate, BACnetTime

        client, mock = _make_mock_client()
        client.time_synchronization(
            "192.168.1.100", BACnetDate(2026, 2, 12, 4), BACnetTime(12, 0, 0, 0)
        )
        addr_arg = mock.time_synchronization.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    def test_utc_time_synchronization_string_address(self):
        from bac_py.types.primitives import BACnetDate, BACnetTime

        client, mock = _make_mock_client()
        client.utc_time_synchronization(
            "192.168.1.100", BACnetDate(2026, 2, 12, 4), BACnetTime(12, 0, 0, 0)
        )
        addr_arg = mock.utc_time_synchronization.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_atomic_read_file_string_address_and_oid(self):
        client, mock = _make_mock_client()
        access = MagicMock()
        await client.atomic_read_file("10.0.0.1", "file,1", access)
        addr_arg = mock.atomic_read_file.call_args[0][0]
        file_arg = mock.atomic_read_file.call_args[0][1]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(file_arg, ObjectIdentifier)
        assert file_arg.object_type == ObjectType.FILE

    async def test_atomic_write_file_string_address_and_oid(self):
        client, mock = _make_mock_client()
        access = MagicMock()
        await client.atomic_write_file("10.0.0.1", "file,2", access)
        addr_arg = mock.atomic_write_file.call_args[0][0]
        file_arg = mock.atomic_write_file.call_args[0][1]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(file_arg, ObjectIdentifier)
        assert file_arg.instance_number == 2

    async def test_confirmed_private_transfer_string_address(self):
        client, mock = _make_mock_client()
        await client.confirmed_private_transfer("10.0.0.1", 99, 1)
        addr_arg = mock.confirmed_private_transfer.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    def test_unconfirmed_private_transfer_string_address(self):
        client, mock = _make_mock_client()
        client.unconfirmed_private_transfer("10.0.0.1", 99, 1)
        addr_arg = mock.unconfirmed_private_transfer.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)

    async def test_add_list_element_string_params(self):
        client, mock = _make_mock_client()
        await client.add_list_element(
            "10.0.0.1", "notification-class,1", "recipient-list", b"\x00"
        )
        addr_arg = mock.add_list_element.call_args[0][0]
        oid_arg = mock.add_list_element.call_args[0][1]
        prop_arg = mock.add_list_element.call_args[0][2]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(oid_arg, ObjectIdentifier)
        assert isinstance(prop_arg, PropertyIdentifier)

    async def test_remove_list_element_string_params(self):
        client, mock = _make_mock_client()
        await client.remove_list_element(
            "10.0.0.1", "notification-class,1", "recipient-list", b"\x00"
        )
        addr_arg = mock.remove_list_element.call_args[0][0]
        oid_arg = mock.remove_list_element.call_args[0][1]
        prop_arg = mock.remove_list_element.call_args[0][2]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(oid_arg, ObjectIdentifier)
        assert isinstance(prop_arg, PropertyIdentifier)

    async def test_subscribe_cov_string_params(self):
        client, mock = _make_mock_client()
        await client.subscribe_cov("10.0.0.1", "ai,1", 1)
        addr_arg = mock.subscribe_cov.call_args[0][0]
        oid_arg = mock.subscribe_cov.call_args[0][1]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(oid_arg, ObjectIdentifier)

    async def test_unsubscribe_cov_string_params(self):
        client, mock = _make_mock_client()
        await client.unsubscribe_cov("10.0.0.1", "ai,1", 1)
        addr_arg = mock.unsubscribe_cov.call_args[0][0]
        oid_arg = mock.unsubscribe_cov.call_args[0][1]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(oid_arg, ObjectIdentifier)

    async def test_who_has_string_oid(self):
        mock_result = []
        client, mock = _make_mock_client()
        mock.who_has.return_value = mock_result
        await client.who_has(object_identifier="ai,1")
        oid_arg = mock.who_has.call_args[1]["object_identifier"]
        assert isinstance(oid_arg, ObjectIdentifier)
        assert oid_arg.object_type == ObjectType.ANALOG_INPUT


class TestBroadcastDestinationDefault:
    """Verify broadcast methods default to GLOBAL_BROADCAST."""

    async def test_who_is_default_broadcast(self):
        client, mock = _make_mock_client()
        mock.who_is.return_value = []
        await client.who_is()
        dest_arg = mock.who_is.call_args[1]["destination"]
        assert dest_arg is GLOBAL_BROADCAST

    async def test_discover_default_broadcast(self):
        client, mock = _make_mock_client()
        mock.discover.return_value = []
        await client.discover()
        dest_arg = mock.discover.call_args[1]["destination"]
        assert dest_arg is GLOBAL_BROADCAST

    async def test_discover_extended_default_broadcast(self):
        client, mock = _make_mock_client()
        mock.discover_extended.return_value = []
        await client.discover_extended()
        dest_arg = mock.discover_extended.call_args[1]["destination"]
        assert dest_arg is GLOBAL_BROADCAST

    async def test_who_has_default_broadcast(self):
        client, mock = _make_mock_client()
        mock.who_has.return_value = []
        await client.who_has(object_name="Test")
        dest_arg = mock.who_has.call_args[1]["destination"]
        assert dest_arg is GLOBAL_BROADCAST

    async def test_discover_unconfigured_default_broadcast(self):
        client, mock = _make_mock_client()
        mock.discover_unconfigured.return_value = []
        await client.discover_unconfigured()
        dest_arg = mock.discover_unconfigured.call_args[1]["destination"]
        assert dest_arg is GLOBAL_BROADCAST

    async def test_who_is_string_broadcast(self):
        client, mock = _make_mock_client()
        mock.who_is.return_value = []
        await client.who_is(destination="192.168.1.255")
        dest_arg = mock.who_is.call_args[1]["destination"]
        assert isinstance(dest_arg, BACnetAddress)


class TestEnumStringParsing:
    """Verify enum parsing in device_communication_control and reinitialize_device."""

    async def test_dcc_string_enable(self):
        client, mock = _make_mock_client()
        await client.device_communication_control("10.0.0.1", "enable")
        state_arg = mock.device_communication_control.call_args[0][1]
        assert state_arg is EnableDisable.ENABLE

    async def test_dcc_string_disable(self):
        client, mock = _make_mock_client()
        await client.device_communication_control("10.0.0.1", "disable")
        state_arg = mock.device_communication_control.call_args[0][1]
        assert state_arg is EnableDisable.DISABLE

    async def test_dcc_string_disable_initiation(self):
        client, mock = _make_mock_client()
        await client.device_communication_control("10.0.0.1", "disable-initiation")
        state_arg = mock.device_communication_control.call_args[0][1]
        assert state_arg is EnableDisable.DISABLE_INITIATION

    async def test_dcc_enum_passthrough(self):
        client, mock = _make_mock_client()
        await client.device_communication_control("10.0.0.1", EnableDisable.DISABLE)
        state_arg = mock.device_communication_control.call_args[0][1]
        assert state_arg is EnableDisable.DISABLE

    async def test_reinitialize_string_coldstart(self):
        client, mock = _make_mock_client()
        await client.reinitialize_device("10.0.0.1", "coldstart")
        state_arg = mock.reinitialize_device.call_args[0][1]
        assert state_arg is ReinitializedState.COLDSTART

    async def test_reinitialize_string_warmstart(self):
        client, mock = _make_mock_client()
        await client.reinitialize_device("10.0.0.1", "warmstart")
        state_arg = mock.reinitialize_device.call_args[0][1]
        assert state_arg is ReinitializedState.WARMSTART

    async def test_reinitialize_string_start_backup(self):
        client, mock = _make_mock_client()
        await client.reinitialize_device("10.0.0.1", "start-backup")
        state_arg = mock.reinitialize_device.call_args[0][1]
        assert state_arg is ReinitializedState.START_BACKUP

    async def test_reinitialize_enum_passthrough(self):
        client, mock = _make_mock_client()
        await client.reinitialize_device("10.0.0.1", ReinitializedState.COLDSTART)
        state_arg = mock.reinitialize_device.call_args[0][1]
        assert state_arg is ReinitializedState.COLDSTART


class TestNewWrapperDelegation:
    """Tests for the 4 new wrapper methods."""

    async def test_traverse_hierarchy_delegates(self):
        client, mock = _make_mock_client()
        mock.traverse_hierarchy.return_value = []
        await client.traverse_hierarchy("10.0.0.1", "structured-view,1", max_depth=5)
        addr_arg = mock.traverse_hierarchy.call_args[0][0]
        root_arg = mock.traverse_hierarchy.call_args[0][1]
        assert isinstance(addr_arg, BACnetAddress)
        assert isinstance(root_arg, ObjectIdentifier)
        assert root_arg.object_type == ObjectType.STRUCTURED_VIEW
        assert mock.traverse_hierarchy.call_args[1]["max_depth"] == 5

    async def test_subscribe_cov_property_multiple_delegates(self):
        client, mock = _make_mock_client()
        specs = []
        await client.subscribe_cov_property_multiple("10.0.0.1", 1, specs, lifetime=300)
        addr_arg = mock.subscribe_cov_property_multiple.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)
        assert mock.subscribe_cov_property_multiple.call_args[1]["lifetime"] == 300

    def test_write_group_delegates(self):
        client, mock = _make_mock_client()
        client.write_group("10.0.0.1", 1, 8, [])
        addr_arg = mock.write_group.call_args[0][0]
        assert isinstance(addr_arg, BACnetAddress)
        assert mock.write_group.call_args[0][1] == 1
        assert mock.write_group.call_args[0][2] == 8

    async def test_discover_unconfigured_delegates(self):
        client, mock = _make_mock_client()
        mock.discover_unconfigured.return_value = []
        result = await client.discover_unconfigured("192.168.1.255", timeout=3.0)
        assert result == []
        dest_arg = mock.discover_unconfigured.call_args[1]["destination"]
        assert isinstance(dest_arg, BACnetAddress)
        assert mock.discover_unconfigured.call_args[1]["timeout"] == 3.0

    async def test_traverse_hierarchy_bacnet_address(self):
        client, mock = _make_mock_client()
        mock.traverse_hierarchy.return_value = []
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        await client.traverse_hierarchy(addr, oid)
        addr_arg = mock.traverse_hierarchy.call_args[0][0]
        root_arg = mock.traverse_hierarchy.call_args[0][1]
        assert addr_arg == addr
        assert root_arg == oid


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestClientAppPropertyError:
    """Test Client.app property raises before start."""

    def test_app_property_raises_before_start(self):
        """Accessing .app before starting the context manager raises RuntimeError."""
        client = Client()
        with pytest.raises(RuntimeError, match="Client not started"):
            _ = client.app


class TestRequireClientEnforcement:
    """Test _require_client raises when not started."""

    def test_require_client_raises_when_none(self):
        """_require_client raises RuntimeError when _client is None."""
        client = Client()
        with pytest.raises(RuntimeError, match="Client not started"):
            client._require_client()

    async def test_write_before_start_raises(self):
        """Calling write before start raises RuntimeError."""
        client = Client()
        with pytest.raises(RuntimeError, match="Client not started"):
            await client.write("192.168.1.100", "av,1", "pv", 72.5)


class TestBBMDRegistration:
    """Test BBMD foreign device registration during context manager."""

    @patch("bac_py.client.BACnetApplication")
    async def test_bbmd_registration_on_start(self, mock_app_cls):
        """Context manager registers as foreign device when bbmd_address is set."""
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app.register_as_foreign_device = AsyncMock()
        mock_app.wait_for_registration = AsyncMock()
        mock_app_cls.return_value = mock_app

        async with Client(bbmd_address="192.168.1.1", bbmd_ttl=120):
            pass

        mock_app.register_as_foreign_device.assert_called_once_with("192.168.1.1", 120)
        mock_app.wait_for_registration.assert_called_once_with(timeout=10.0)
        mock_app.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Additional coverage tests for Client
# ---------------------------------------------------------------------------


def _make_protocol_mock_client():
    """Create a Client with a mock BACnetClient for protocol delegation tests."""
    client = Client.__new__(Client)
    client._config = DeviceConfig(instance_number=999)
    client._app = MagicMock()
    client._bbmd_address = None
    client._bbmd_ttl = 60
    mock = MagicMock()
    # Make async methods return coroutines
    mock.write_multiple = AsyncMock()
    mock.get_object_list = AsyncMock(return_value=[])
    mock.subscribe_cov_ex = AsyncMock()
    mock.unsubscribe_cov_ex = AsyncMock()
    mock.read_property = AsyncMock(return_value=MagicMock())
    mock.write_property = AsyncMock()
    mock.read_property_multiple = AsyncMock(return_value=MagicMock())
    mock.write_property_multiple = AsyncMock()
    mock.read_range = AsyncMock(return_value=MagicMock())
    mock.create_object = AsyncMock(return_value=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1))
    mock.read_bdt = AsyncMock(return_value=[])
    mock.read_fdt = AsyncMock(return_value=[])
    mock.write_bdt = AsyncMock()
    mock.delete_fdt_entry = AsyncMock()
    mock.who_is_router_to_network = AsyncMock(return_value=[])
    client._client = mock
    return client, mock


class TestClientAexit:
    """Test __aexit__ early return when app is None."""

    async def test_aexit_no_app(self):
        """__aexit__ with _app=None should be a no-op."""
        client = Client.__new__(Client)
        client._app = None
        client._client = None
        client._bbmd_address = None
        client._bbmd_ttl = 60
        # Should not raise
        await client.__aexit__(None, None, None)
        assert client._app is None


class TestClientProtocolDelegation:
    """Test Client protocol-level delegation methods."""

    async def test_write_multiple_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.write_multiple("10.0.0.1", {"av,1": {"pv": 42.0}})
        mock.write_multiple.assert_called_once()

    async def test_write_multiple_delegates_with_priority(self):
        client, mock = _make_protocol_mock_client()
        await client.write_multiple("10.0.0.1", {"av,1": {"pv": 42.0}}, priority=8)
        mock.write_multiple.assert_called_once()
        call_kwargs = mock.write_multiple.call_args
        assert call_kwargs.kwargs["priority"] == 8

    async def test_get_object_list_delegates(self):
        client, mock = _make_protocol_mock_client()
        result = await client.get_object_list("10.0.0.1", 1)
        mock.get_object_list.assert_called_once()
        assert result == []

    async def test_subscribe_cov_ex_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.subscribe_cov_ex("10.0.0.1", "av,1", 1)
        mock.subscribe_cov_ex.assert_called_once()

    async def test_unsubscribe_cov_ex_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.unsubscribe_cov_ex("10.0.0.1", "av,1", 1)
        mock.unsubscribe_cov_ex.assert_called_once()

    async def test_read_property_delegates(self):
        client, mock = _make_protocol_mock_client()
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        await client.read_property(addr, oid, PropertyIdentifier.PRESENT_VALUE)
        mock.read_property.assert_called_once()

    async def test_write_property_delegates(self):
        client, mock = _make_protocol_mock_client()
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        await client.write_property(
            addr, oid, PropertyIdentifier.PRESENT_VALUE, b"\x44\x42\x28\x00\x00"
        )
        mock.write_property.assert_called_once()

    async def test_read_property_multiple_delegates(self):
        client, mock = _make_protocol_mock_client()
        addr = parse_address("10.0.0.1")
        await client.read_property_multiple(addr, [])
        mock.read_property_multiple.assert_called_once()

    async def test_write_property_multiple_delegates(self):
        client, mock = _make_protocol_mock_client()
        addr = parse_address("10.0.0.1")
        await client.write_property_multiple(addr, [])
        mock.write_property_multiple.assert_called_once()

    async def test_read_range_delegates(self):
        client, mock = _make_protocol_mock_client()
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.TREND_LOG, 1)
        await client.read_range(addr, oid, PropertyIdentifier.LOG_BUFFER)
        mock.read_range.assert_called_once()


class TestClientCreateObjectStringType:
    """Test Client.create_object with string object_type resolution."""

    async def test_create_object_with_string_type(self):
        client, mock = _make_protocol_mock_client()
        result = await client.create_object("10.0.0.1", object_type="analog-value")
        mock.create_object.assert_called_once()
        assert result == ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

    async def test_create_object_with_object_identifier(self):
        client, mock = _make_protocol_mock_client()
        await client.create_object("10.0.0.1", object_identifier="av,1")
        mock.create_object.assert_called_once()

    async def test_create_object_with_object_type_enum(self):
        """create_object with ObjectType enum resolves correctly (branch 1035->1039)."""
        client, mock = _make_protocol_mock_client()
        result = await client.create_object("10.0.0.1", object_type=ObjectType.ANALOG_VALUE)
        mock.create_object.assert_called_once()
        call_args = mock.create_object.call_args
        # The resolved_type should be ObjectType.ANALOG_VALUE (not None)
        assert call_args[0][1] == ObjectType.ANALOG_VALUE
        assert result == ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)


class TestClientForeignDeviceAPI:
    """Test foreign device API delegations."""

    async def test_register_as_foreign_device(self):
        client, _mock = _make_protocol_mock_client()
        client._app.register_as_foreign_device = AsyncMock()
        await client.register_as_foreign_device("10.0.0.1", 120)
        client._app.register_as_foreign_device.assert_called_once_with("10.0.0.1", 120)

    async def test_deregister_foreign_device(self):
        client, _mock = _make_protocol_mock_client()
        client._app.deregister_foreign_device = AsyncMock()
        await client.deregister_foreign_device()
        client._app.deregister_foreign_device.assert_called_once()

    def test_is_foreign_device(self):
        client, _mock = _make_protocol_mock_client()
        client._app.is_foreign_device = True
        assert client.is_foreign_device is True

    def test_foreign_device_status(self):
        client, _mock = _make_protocol_mock_client()
        client._app.foreign_device_status = None
        assert client.foreign_device_status is None

    async def test_wait_for_registration(self):
        client, _mock = _make_protocol_mock_client()
        client._app.wait_for_registration = AsyncMock(return_value=True)
        result = await client.wait_for_registration(timeout=5.0)
        assert result is True

    async def test_read_bdt_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.read_bdt("10.0.0.1")
        mock.read_bdt.assert_called_once()

    async def test_read_fdt_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.read_fdt("10.0.0.1")
        mock.read_fdt.assert_called_once()

    async def test_write_bdt_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.write_bdt("10.0.0.1", [])
        mock.write_bdt.assert_called_once()

    async def test_delete_fdt_entry_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.delete_fdt_entry("10.0.0.1", "10.0.0.2")
        mock.delete_fdt_entry.assert_called_once()


class TestClientWhoIsRouterDelegation:
    """Test who_is_router_to_network delegation."""

    async def test_who_is_router_to_network_delegates(self):
        client, mock = _make_protocol_mock_client()
        await client.who_is_router_to_network(network=100)
        mock.who_is_router_to_network.assert_called_once()


class TestClientIPv6:
    """Test Client IPv6 convenience parameters."""

    def test_ipv6_flag_sets_config(self):
        client = Client(ipv6=True)
        assert client._config.ipv6 is True

    def test_ipv6_default_interface_becomes_all_ipv6(self):
        client = Client(ipv6=True)
        assert client._config.interface == "::"

    def test_ipv6_custom_interface_preserved(self):
        client = Client(ipv6=True, interface="fd00::1")
        assert client._config.interface == "fd00::1"

    def test_ipv6_multicast_address(self):
        client = Client(ipv6=True, multicast_address="ff02::1234")
        assert client._config.multicast_address == "ff02::1234"

    def test_ipv6_vmac(self):
        vmac = b"\x01\x02\x03"
        client = Client(ipv6=True, vmac=vmac)
        assert client._config.vmac == vmac

    def test_ipv6_false_keeps_ipv4_interface(self):
        client = Client(ipv6=False)
        assert client._config.interface == "0.0.0.0"
        assert client._config.ipv6 is False

    @patch("bac_py.client.BACnetApplication")
    async def test_ipv6_client_creates_app_with_ipv6_config(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_cls.return_value = mock_app

        async with Client(ipv6=True):
            # Verify the DeviceConfig passed to BACnetApplication
            cfg = mock_app_cls.call_args[0][0]
            assert cfg.ipv6 is True
            assert cfg.interface == "::"

    @patch("bac_py.client.BACnetApplication")
    async def test_ipv6_client_bbmd_registration(self, mock_app_cls):
        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app.register_as_foreign_device = AsyncMock()
        mock_app.deregister_foreign_device = AsyncMock()
        mock_app.wait_for_registration = AsyncMock()
        mock_app_cls.return_value = mock_app

        async with Client(ipv6=True, bbmd_address="[fd00::1]:47808", bbmd_ttl=120):
            mock_app.register_as_foreign_device.assert_called_once_with("[fd00::1]:47808", 120)
