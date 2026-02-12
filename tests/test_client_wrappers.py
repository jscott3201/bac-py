"""Tests for high-level Client wrapper methods (Phase 1).

Verifies that the convenience wrappers on Client correctly parse string
arguments and delegate to the underlying BACnetClient methods.
"""

from unittest.mock import AsyncMock, MagicMock

from bac_py.app.client import BackupData
from bac_py.client import Client
from bac_py.network.address import BACnetAddress, parse_address
from bac_py.services.alarm_summary import (
    GetAlarmSummaryACK,
    GetEnrollmentSummaryACK,
    GetEventInformationACK,
)
from bac_py.services.audit import AuditLogQueryACK
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    AcknowledgmentFilter,
    EventState,
    MessagePriority,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


def _make_client_with_mock():
    """Create a Client with mocked internals for testing delegation."""
    mock_app = MagicMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.confirmed_request = AsyncMock(return_value=b"")
    mock_app.unconfirmed_request = MagicMock()
    mock_app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, 999)

    mock_bclient = MagicMock()
    client = Client()
    client._app = mock_app
    client._client = mock_bclient
    return client, mock_bclient, mock_app


class TestDiscoverExtended:
    async def test_string_destination(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.discover_extended = AsyncMock(return_value=[])

        result = await client.discover_extended(destination="192.168.1.255", timeout=2.0)

        assert result == []
        mock_bclient.discover_extended.assert_called_once()
        call_kwargs = mock_bclient.discover_extended.call_args[1]
        assert isinstance(call_kwargs["destination"], BACnetAddress)
        assert call_kwargs["timeout"] == 2.0

    async def test_none_destination_uses_global_broadcast(self):
        from bac_py.network.address import GLOBAL_BROADCAST

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.discover_extended = AsyncMock(return_value=[])

        await client.discover_extended()

        call_kwargs = mock_bclient.discover_extended.call_args[1]
        assert call_kwargs["destination"] is GLOBAL_BROADCAST

    async def test_bacnet_address_passthrough(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.discover_extended = AsyncMock(return_value=[])
        addr = parse_address("10.0.0.1")

        await client.discover_extended(destination=addr)

        call_kwargs = mock_bclient.discover_extended.call_args[1]
        assert call_kwargs["destination"] is addr

    async def test_all_params_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.discover_extended = AsyncMock(return_value=[])

        await client.discover_extended(
            low_limit=100,
            high_limit=200,
            destination="10.0.0.255",
            timeout=5.0,
            expected_count=3,
            enrich_timeout=10.0,
        )

        call_kwargs = mock_bclient.discover_extended.call_args[1]
        assert call_kwargs["low_limit"] == 100
        assert call_kwargs["high_limit"] == 200
        assert call_kwargs["timeout"] == 5.0
        assert call_kwargs["expected_count"] == 3
        assert call_kwargs["enrich_timeout"] == 10.0


class TestGetAlarmSummary:
    async def test_string_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_ack = MagicMock(spec=GetAlarmSummaryACK)
        mock_bclient.get_alarm_summary = AsyncMock(return_value=mock_ack)

        result = await client.get_alarm_summary("192.168.1.100")

        assert result is mock_ack
        args = mock_bclient.get_alarm_summary.call_args
        assert isinstance(args[0][0], BACnetAddress)

    async def test_bacnet_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_ack = MagicMock(spec=GetAlarmSummaryACK)
        mock_bclient.get_alarm_summary = AsyncMock(return_value=mock_ack)
        addr = parse_address("192.168.1.100")

        result = await client.get_alarm_summary(addr)

        assert result is mock_ack
        args = mock_bclient.get_alarm_summary.call_args
        assert args[0][0] is addr

    async def test_timeout_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.get_alarm_summary = AsyncMock(return_value=MagicMock(spec=GetAlarmSummaryACK))

        await client.get_alarm_summary("10.0.0.1", timeout=15.0)

        call_kwargs = mock_bclient.get_alarm_summary.call_args[1]
        assert call_kwargs["timeout"] == 15.0


class TestGetEnrollmentSummary:
    async def test_string_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_ack = MagicMock(spec=GetEnrollmentSummaryACK)
        mock_bclient.get_enrollment_summary = AsyncMock(return_value=mock_ack)

        result = await client.get_enrollment_summary("192.168.1.100", AcknowledgmentFilter.ALL)

        assert result is mock_ack
        args = mock_bclient.get_enrollment_summary.call_args
        assert isinstance(args[0][0], BACnetAddress)
        assert args[0][1] is AcknowledgmentFilter.ALL

    async def test_optional_filters_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.get_enrollment_summary = AsyncMock(
            return_value=MagicMock(spec=GetEnrollmentSummaryACK)
        )

        await client.get_enrollment_summary(
            "10.0.0.1",
            AcknowledgmentFilter.ACKED,
            event_state_filter=EventState.OFFNORMAL,
            priority_min=10,
            priority_max=200,
            notification_class_filter=5,
        )

        call_kwargs = mock_bclient.get_enrollment_summary.call_args[1]
        assert call_kwargs["event_state_filter"] is EventState.OFFNORMAL
        assert call_kwargs["priority_min"] == 10
        assert call_kwargs["priority_max"] == 200
        assert call_kwargs["notification_class_filter"] == 5


class TestGetEventInformation:
    async def test_string_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_ack = MagicMock(spec=GetEventInformationACK)
        mock_bclient.get_event_information = AsyncMock(return_value=mock_ack)

        result = await client.get_event_information("192.168.1.100")

        assert result is mock_ack
        args = mock_bclient.get_event_information.call_args
        assert isinstance(args[0][0], BACnetAddress)

    async def test_string_object_identifier_for_pagination(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.get_event_information = AsyncMock(
            return_value=MagicMock(spec=GetEventInformationACK)
        )

        await client.get_event_information("10.0.0.1", last_received_object_identifier="ai,5")

        call_kwargs = mock_bclient.get_event_information.call_args[1]
        oid = call_kwargs["last_received_object_identifier"]
        assert isinstance(oid, ObjectIdentifier)
        assert oid.object_type == ObjectType.ANALOG_INPUT
        assert oid.instance_number == 5

    async def test_none_pagination(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.get_event_information = AsyncMock(
            return_value=MagicMock(spec=GetEventInformationACK)
        )

        await client.get_event_information("10.0.0.1")

        call_kwargs = mock_bclient.get_event_information.call_args[1]
        assert call_kwargs["last_received_object_identifier"] is None


class TestAcknowledgeAlarm:
    async def test_string_address_and_object(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.acknowledge_alarm = AsyncMock()
        ts = MagicMock(spec=BACnetTimeStamp)
        ts2 = MagicMock(spec=BACnetTimeStamp)

        await client.acknowledge_alarm(
            "192.168.1.100",
            acknowledging_process_identifier=1,
            event_object_identifier="ai,1",
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts2,
        )

        args = mock_bclient.acknowledge_alarm.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] == 1
        assert isinstance(args[2], ObjectIdentifier)
        assert args[2].object_type == ObjectType.ANALOG_INPUT
        assert args[2].instance_number == 1
        assert args[3] is EventState.OFFNORMAL
        assert args[4] is ts
        assert args[5] == "operator"
        assert args[6] is ts2

    async def test_typed_objects_passthrough(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.acknowledge_alarm = AsyncMock()
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.BINARY_INPUT, 3)
        ts = MagicMock(spec=BACnetTimeStamp)

        await client.acknowledge_alarm(
            addr,
            acknowledging_process_identifier=2,
            event_object_identifier=oid,
            event_state_acknowledged=EventState.NORMAL,
            time_stamp=ts,
            acknowledgment_source="auto",
            time_of_acknowledgment=ts,
        )

        args = mock_bclient.acknowledge_alarm.call_args[0]
        assert args[0] is addr


class TestSendTextMessage:
    async def test_confirmed_with_string_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.send_confirmed_text_message = AsyncMock()

        await client.send_text_message("192.168.1.100", "Hello BACnet")

        mock_bclient.send_confirmed_text_message.assert_called_once()
        args = mock_bclient.send_confirmed_text_message.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] == ObjectIdentifier(ObjectType.DEVICE, 999)
        assert args[2] == "Hello BACnet"
        kwargs = mock_bclient.send_confirmed_text_message.call_args[1]
        assert kwargs["message_priority"] is MessagePriority.NORMAL

    async def test_unconfirmed(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.send_unconfirmed_text_message = MagicMock()

        await client.send_text_message(
            "192.168.1.100",
            "Broadcast msg",
            confirmed=False,
        )

        mock_bclient.send_unconfirmed_text_message.assert_called_once()
        mock_bclient.send_confirmed_text_message = AsyncMock()
        # confirmed should NOT have been called
        mock_bclient.send_confirmed_text_message.assert_not_called()

    async def test_custom_priority(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.send_confirmed_text_message = AsyncMock()

        await client.send_text_message(
            "10.0.0.1",
            "Urgent!",
            message_priority=MessagePriority.URGENT,
        )

        kwargs = mock_bclient.send_confirmed_text_message.call_args[1]
        assert kwargs["message_priority"] is MessagePriority.URGENT

    async def test_message_class_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.send_confirmed_text_message = AsyncMock()

        await client.send_text_message(
            "10.0.0.1",
            "test",
            message_class_numeric=42,
            message_class_character="maintenance",
        )

        kwargs = mock_bclient.send_confirmed_text_message.call_args[1]
        assert kwargs["message_class_numeric"] == 42
        assert kwargs["message_class_character"] == "maintenance"


class TestBackup:
    async def test_string_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_data = BackupData(device_instance=100, configuration_files=[])
        mock_bclient.backup_device = AsyncMock(return_value=mock_data)

        result = await client.backup("192.168.1.100")

        assert result is mock_data
        args = mock_bclient.backup_device.call_args[0]
        assert isinstance(args[0], BACnetAddress)

    async def test_password_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.backup_device = AsyncMock(
            return_value=BackupData(device_instance=100, configuration_files=[])
        )

        await client.backup("10.0.0.1", password="secret", poll_interval=2.0, timeout=30.0)

        kwargs = mock_bclient.backup_device.call_args[1]
        assert kwargs["password"] == "secret"
        assert kwargs["poll_interval"] == 2.0
        assert kwargs["timeout"] == 30.0


class TestRestore:
    async def test_string_address(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.restore_device = AsyncMock()
        backup_data = BackupData(device_instance=100, configuration_files=[])

        await client.restore("192.168.1.100", backup_data)

        mock_bclient.restore_device.assert_called_once()
        args = mock_bclient.restore_device.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] is backup_data

    async def test_password_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.restore_device = AsyncMock()
        backup_data = BackupData(device_instance=100, configuration_files=[])

        await client.restore(
            "10.0.0.1", backup_data, password="secret", poll_interval=2.0, timeout=30.0
        )

        kwargs = mock_bclient.restore_device.call_args[1]
        assert kwargs["password"] == "secret"
        assert kwargs["poll_interval"] == 2.0
        assert kwargs["timeout"] == 30.0


class TestQueryAuditLog:
    async def test_string_address_and_object(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_ack = MagicMock(spec=AuditLogQueryACK)
        mock_bclient.query_audit_log = AsyncMock(return_value=mock_ack)
        mock_query = MagicMock()

        result = await client.query_audit_log("192.168.1.100", "audit-log,1", mock_query)

        assert result is mock_ack
        args = mock_bclient.query_audit_log.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert isinstance(args[1], ObjectIdentifier)
        assert args[2] is mock_query

    async def test_typed_objects_passthrough(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.query_audit_log = AsyncMock(return_value=MagicMock(spec=AuditLogQueryACK))
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.AUDIT_LOG, 1)
        mock_query = MagicMock()

        await client.query_audit_log(addr, oid, mock_query)

        args = mock_bclient.query_audit_log.call_args[0]
        assert args[0] is addr

    async def test_optional_params_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.query_audit_log = AsyncMock(return_value=MagicMock(spec=AuditLogQueryACK))

        await client.query_audit_log(
            "10.0.0.1",
            "audit-log,1",
            MagicMock(),
            start_at_sequence_number=50,
            requested_count=25,
            timeout=10.0,
        )

        kwargs = mock_bclient.query_audit_log.call_args[1]
        assert kwargs["start_at_sequence_number"] == 50
        assert kwargs["requested_count"] == 25
        assert kwargs["timeout"] == 10.0


class TestSubscribeCovProperty:
    async def test_string_args(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.subscribe_cov_property = AsyncMock()

        await client.subscribe_cov_property(
            "192.168.1.100",
            "ai,1",
            "pv",
            process_id=1,
        )

        mock_bclient.subscribe_cov_property.assert_called_once()
        args = mock_bclient.subscribe_cov_property.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert isinstance(args[1], ObjectIdentifier)
        assert args[1].object_type == ObjectType.ANALOG_INPUT
        assert args[1].instance_number == 1
        assert args[2] == PropertyIdentifier.PRESENT_VALUE
        assert args[3] == 1

    async def test_optional_params_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.subscribe_cov_property = AsyncMock()

        await client.subscribe_cov_property(
            "10.0.0.1",
            "av,5",
            "pv",
            process_id=2,
            confirmed=False,
            lifetime=300,
            property_array_index=0,
            cov_increment=0.5,
            timeout=10.0,
        )

        kwargs = mock_bclient.subscribe_cov_property.call_args[1]
        assert kwargs["confirmed"] is False
        assert kwargs["lifetime"] == 300
        assert kwargs["property_array_index"] == 0
        assert kwargs["cov_increment"] == 0.5
        assert kwargs["timeout"] == 10.0


class TestCreateObject:
    async def test_string_address_and_type(self):
        client, mock_bclient, _ = _make_client_with_mock()
        oid = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        mock_bclient.create_object = AsyncMock(return_value=oid)

        result = await client.create_object("192.168.1.100", object_type="av")

        assert result is oid
        args = mock_bclient.create_object.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] == ObjectType.ANALOG_VALUE
        assert args[2] is None

    async def test_string_object_identifier(self):
        client, mock_bclient, _ = _make_client_with_mock()
        oid = ObjectIdentifier(ObjectType.ANALOG_VALUE, 5)
        mock_bclient.create_object = AsyncMock(return_value=oid)

        await client.create_object("10.0.0.1", object_identifier="av,5")

        args = mock_bclient.create_object.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] is None
        assert isinstance(args[2], ObjectIdentifier)
        assert args[2].object_type == ObjectType.ANALOG_VALUE
        assert args[2].instance_number == 5

    async def test_enum_type_passthrough(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.create_object = AsyncMock(
            return_value=ObjectIdentifier(ObjectType.BINARY_INPUT, 1)
        )

        await client.create_object("10.0.0.1", object_type=ObjectType.BINARY_INPUT)

        args = mock_bclient.create_object.call_args[0]
        assert args[1] is ObjectType.BINARY_INPUT


class TestDeleteObject:
    async def test_string_address_and_identifier(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.delete_object = AsyncMock()

        await client.delete_object("192.168.1.100", "av,1")

        args = mock_bclient.delete_object.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert isinstance(args[1], ObjectIdentifier)
        assert args[1].object_type == ObjectType.ANALOG_VALUE
        assert args[1].instance_number == 1

    async def test_typed_passthrough(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.delete_object = AsyncMock()
        addr = parse_address("10.0.0.1")
        oid = ObjectIdentifier(ObjectType.BINARY_INPUT, 3)

        await client.delete_object(addr, oid)

        args = mock_bclient.delete_object.call_args[0]
        assert args[0] is addr


class TestDeviceCommunicationControl:
    async def test_string_address_and_state(self):
        from bac_py.types.enums import EnableDisable

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.device_communication_control = AsyncMock()

        await client.device_communication_control("192.168.1.100", "disable")

        args = mock_bclient.device_communication_control.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] is EnableDisable.DISABLE

    async def test_hyphenated_string(self):
        from bac_py.types.enums import EnableDisable

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.device_communication_control = AsyncMock()

        await client.device_communication_control("10.0.0.1", "disable-initiation")

        args = mock_bclient.device_communication_control.call_args[0]
        assert args[1] is EnableDisable.DISABLE_INITIATION

    async def test_enable_string(self):
        from bac_py.types.enums import EnableDisable

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.device_communication_control = AsyncMock()

        await client.device_communication_control("10.0.0.1", "enable")

        args = mock_bclient.device_communication_control.call_args[0]
        assert args[1] is EnableDisable.ENABLE

    async def test_enum_passthrough(self):
        from bac_py.types.enums import EnableDisable

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.device_communication_control = AsyncMock()

        await client.device_communication_control("10.0.0.1", EnableDisable.DISABLE)

        args = mock_bclient.device_communication_control.call_args[0]
        assert args[1] is EnableDisable.DISABLE

    async def test_optional_params_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.device_communication_control = AsyncMock()

        await client.device_communication_control(
            "10.0.0.1", "disable", time_duration=30, password="secret", timeout=5.0
        )

        args = mock_bclient.device_communication_control.call_args[0]
        assert args[2] == 30
        assert args[3] == "secret"
        kwargs = mock_bclient.device_communication_control.call_args[1]
        assert kwargs["timeout"] == 5.0


class TestReinitializeDevice:
    async def test_string_address_and_state(self):
        from bac_py.types.enums import ReinitializedState

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.reinitialize_device = AsyncMock()

        await client.reinitialize_device("192.168.1.100", "coldstart")

        args = mock_bclient.reinitialize_device.call_args[0]
        assert isinstance(args[0], BACnetAddress)
        assert args[1] is ReinitializedState.COLDSTART

    async def test_hyphenated_string(self):
        from bac_py.types.enums import ReinitializedState

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.reinitialize_device = AsyncMock()

        await client.reinitialize_device("10.0.0.1", "start-backup")

        args = mock_bclient.reinitialize_device.call_args[0]
        assert args[1] is ReinitializedState.START_BACKUP

    async def test_warmstart(self):
        from bac_py.types.enums import ReinitializedState

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.reinitialize_device = AsyncMock()

        await client.reinitialize_device("10.0.0.1", "warmstart")

        args = mock_bclient.reinitialize_device.call_args[0]
        assert args[1] is ReinitializedState.WARMSTART

    async def test_enum_passthrough(self):
        from bac_py.types.enums import ReinitializedState

        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.reinitialize_device = AsyncMock()

        await client.reinitialize_device("10.0.0.1", ReinitializedState.COLDSTART)

        args = mock_bclient.reinitialize_device.call_args[0]
        assert args[1] is ReinitializedState.COLDSTART

    async def test_password_forwarded(self):
        client, mock_bclient, _ = _make_client_with_mock()
        mock_bclient.reinitialize_device = AsyncMock()

        await client.reinitialize_device("10.0.0.1", "coldstart", password="admin", timeout=10.0)

        args = mock_bclient.reinitialize_device.call_args[0]
        assert args[2] == "admin"
        kwargs = mock_bclient.reinitialize_device.call_args[1]
        assert kwargs["timeout"] == 10.0


class TestExports:
    def test_backup_data_exported(self):
        from bac_py import BackupData as ExportedBackupData

        assert ExportedBackupData is BackupData

    def test_server_types_exported(self):
        from bac_py import (
            BACnetApplication,
            DefaultServerHandlers,
            DeviceObject,
            RouterConfig,
            RouterPortConfig,
        )

        assert BACnetApplication is not None
        assert DefaultServerHandlers is not None
        assert DeviceObject is not None
        assert RouterConfig is not None
        assert RouterPortConfig is not None
