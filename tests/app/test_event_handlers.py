"""Tests for alarm/event client methods and server handlers (Step 8.4).

Tests cover:
- Server handlers for GetAlarmSummary, GetEnrollmentSummary, GetEventInformation,
  AcknowledgeAlarm, ConfirmedEventNotification, UnconfirmedEventNotification
- Client methods that build requests and decode responses
- Error cases: unknown object, filtering, pagination
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.app.server import DefaultServerHandlers
from bac_py.network.address import BACnetAddress
from bac_py.objects.analog import AnalogInputObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.device import DeviceObject
from bac_py.objects.event_enrollment import EventEnrollmentObject
from bac_py.services.alarm_summary import (
    AlarmSummary,
    GetAlarmSummaryACK,
    GetAlarmSummaryRequest,
    GetEnrollmentSummaryACK,
    GetEnrollmentSummaryRequest,
    GetEventInformationACK,
    GetEventInformationRequest,
)
from bac_py.services.event_notification import (
    AcknowledgeAlarmRequest,
    EventNotificationRequest,
)
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    AcknowledgmentFilter,
    ErrorCode,
    EventState,
    EventType,
    NotifyType,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BitString, ObjectIdentifier

SOURCE = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")


def _make_app_and_handlers(device_instance: int = 1):
    """Create a mock application, object database, and server handlers."""
    app = MagicMock()
    app.config = MagicMock()
    app.config.max_apdu_length = 1476
    app.config.vendor_id = 42
    app.config.password = None
    app.service_registry = MagicMock()
    app.unconfirmed_request = MagicMock()

    db = ObjectDatabase()
    device = DeviceObject(
        device_instance,
        object_name="test-device",
        vendor_name="test-vendor",
        vendor_identifier=42,
        model_name="test-model",
        firmware_revision="1.0",
        application_software_version="1.0",
    )
    db.add(device)

    handlers = DefaultServerHandlers(app, db, device)
    return app, db, device, handlers


# ---------------------------------------------------------------------------
# GetAlarmSummary handler tests
# ---------------------------------------------------------------------------


class TestGetAlarmSummary:
    @pytest.mark.asyncio
    async def test_no_alarms_returns_empty(self):
        """No objects in alarm state -> empty summary list."""
        _, _, _, handlers = _make_app_and_handlers()
        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 0

    @pytest.mark.asyncio
    async def test_object_in_alarm_returned(self):
        """An analog input in OFFNORMAL event state is included."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.OFFNORMAL
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        db.add(ai)

        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 1
        summary = ack.list_of_alarm_summaries[0]
        assert summary.object_identifier == ai.object_identifier
        assert summary.alarm_state == EventState.OFFNORMAL

    @pytest.mark.asyncio
    async def test_normal_objects_excluded(self):
        """Objects in NORMAL event state are not included."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.NORMAL
        db.add(ai)

        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 0

    @pytest.mark.asyncio
    async def test_multiple_alarms(self):
        """Multiple alarmed objects are all returned."""
        _, db, _, handlers = _make_app_and_handlers()
        for i in range(3):
            ai = AnalogInputObject(i + 1)
            ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT
            ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
            db.add(ai)

        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 3


# ---------------------------------------------------------------------------
# GetEnrollmentSummary handler tests
# ---------------------------------------------------------------------------


class TestGetEnrollmentSummary:
    def _make_enrollment(self, db, instance, *, event_type=EventType.CHANGE_OF_VALUE,
                         event_state=EventState.NORMAL, notification_class=0):
        """Create an EventEnrollmentObject with given properties."""
        obj_ref = MagicMock()
        obj_ref.object_identifier = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        obj_ref.property_identifier = PropertyIdentifier.PRESENT_VALUE
        ee = EventEnrollmentObject(
            instance,
            event_type=event_type,
            object_property_reference=obj_ref,
        )
        ee._properties[PropertyIdentifier.EVENT_STATE] = event_state
        ee._properties[PropertyIdentifier.NOTIFICATION_CLASS] = notification_class
        ee._properties[PropertyIdentifier.EVENT_TYPE] = event_type
        db.add(ee)
        return ee

    @pytest.mark.asyncio
    async def test_all_enrollments_returned(self):
        """With no extra filters, all enrollments match."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1)
        self._make_enrollment(db, 2)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 2

    @pytest.mark.asyncio
    async def test_event_state_filter(self):
        """Only enrollments matching the event state filter are returned."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1, event_state=EventState.NORMAL)
        self._make_enrollment(db, 2, event_state=EventState.OFFNORMAL)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            event_state_filter=EventState.OFFNORMAL,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 1
        assert ack.list_of_enrollment_summaries[0].event_state == EventState.OFFNORMAL

    @pytest.mark.asyncio
    async def test_event_type_filter(self):
        """Only enrollments matching the event type filter are returned."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1, event_type=EventType.CHANGE_OF_VALUE)
        self._make_enrollment(db, 2, event_type=EventType.OUT_OF_RANGE)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            event_type_filter=EventType.OUT_OF_RANGE,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 1
        assert ack.list_of_enrollment_summaries[0].event_type == EventType.OUT_OF_RANGE

    @pytest.mark.asyncio
    async def test_notification_class_filter(self):
        """Only enrollments matching the notification class filter are returned."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1, notification_class=5)
        self._make_enrollment(db, 2, notification_class=10)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            notification_class_filter=10,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 1
        assert ack.list_of_enrollment_summaries[0].notification_class == 10

    @pytest.mark.asyncio
    async def test_no_enrollments(self):
        """Empty database returns empty list."""
        _, _, _, handlers = _make_app_and_handlers()
        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 0


# ---------------------------------------------------------------------------
# GetEventInformation handler tests
# ---------------------------------------------------------------------------


class TestGetEventInformation:
    @pytest.mark.asyncio
    async def test_no_events(self):
        """No objects in alarm -> empty event info list."""
        _, _, _, handlers = _make_app_and_handlers()
        request = GetEventInformationRequest()
        result = await handlers.handle_get_event_information(0, request.encode(), SOURCE)
        ack = GetEventInformationACK.decode(result)
        assert len(ack.list_of_event_summaries) == 0
        assert ack.more_events is False

    @pytest.mark.asyncio
    async def test_alarmed_object_included(self):
        """An object in alarm state appears in event information."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT
        ai._properties[PropertyIdentifier.NOTIFY_TYPE] = NotifyType.ALARM
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, False]
        db.add(ai)

        request = GetEventInformationRequest()
        result = await handlers.handle_get_event_information(0, request.encode(), SOURCE)
        ack = GetEventInformationACK.decode(result)
        assert len(ack.list_of_event_summaries) == 1
        summary = ack.list_of_event_summaries[0]
        assert summary.object_identifier == ai.object_identifier
        assert summary.event_state == EventState.HIGH_LIMIT
        assert summary.notify_type == NotifyType.ALARM

    @pytest.mark.asyncio
    async def test_pagination_skip(self):
        """With last_received_object_identifier, skip until past that object."""
        _, db, _, handlers = _make_app_and_handlers()
        ai1 = AnalogInputObject(1)
        ai1._properties[PropertyIdentifier.EVENT_STATE] = EventState.OFFNORMAL
        ai1._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        db.add(ai1)

        ai2 = AnalogInputObject(2)
        ai2._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT
        ai2._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        db.add(ai2)

        # Request with last_received as ai1 -> should skip ai1, return ai2
        request = GetEventInformationRequest(
            last_received_object_identifier=ai1.object_identifier,
        )
        result = await handlers.handle_get_event_information(0, request.encode(), SOURCE)
        ack = GetEventInformationACK.decode(result)
        assert len(ack.list_of_event_summaries) == 1
        assert ack.list_of_event_summaries[0].object_identifier == ai2.object_identifier


# ---------------------------------------------------------------------------
# AcknowledgeAlarm handler tests
# ---------------------------------------------------------------------------


class TestAcknowledgeAlarm:
    @pytest.mark.asyncio
    async def test_acknowledge_offnormal(self):
        """Acknowledging an OFFNORMAL transition sets acked_transitions[0]."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.OFFNORMAL
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [False, True, True]
        db.add(ai)

        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ai.object_identifier,
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        result = await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert result is None  # SimpleACK
        assert ai._properties[PropertyIdentifier.ACKED_TRANSITIONS][0] is True

    @pytest.mark.asyncio
    async def test_acknowledge_fault(self):
        """Acknowledging a FAULT transition sets acked_transitions[1]."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.FAULT
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, False, True]
        db.add(ai)

        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ai.object_identifier,
            event_state_acknowledged=EventState.FAULT,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        result = await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert result is None
        assert ai._properties[PropertyIdentifier.ACKED_TRANSITIONS][1] is True

    @pytest.mark.asyncio
    async def test_acknowledge_normal(self):
        """Acknowledging a NORMAL transition sets acked_transitions[2]."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.NORMAL
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, False]
        db.add(ai)

        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ai.object_identifier,
            event_state_acknowledged=EventState.NORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        result = await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert result is None
        assert ai._properties[PropertyIdentifier.ACKED_TRANSITIONS][2] is True

    @pytest.mark.asyncio
    async def test_unknown_object_raises_error(self):
        """Acknowledging a non-existent object raises BACnetError."""
        _, _, _, handlers = _make_app_and_handlers()
        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


# ---------------------------------------------------------------------------
# Event notification handler tests
# ---------------------------------------------------------------------------


class TestEventNotificationHandlers:
    def _make_notification(self) -> EventNotificationRequest:
        return EventNotificationRequest(
            process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            notification_class=1,
            priority=100,
            event_type=EventType.OUT_OF_RANGE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.HIGH_LIMIT,
            ack_required=True,
            from_state=EventState.NORMAL,
        )

    @pytest.mark.asyncio
    async def test_confirmed_event_notification_returns_simple_ack(self):
        """Confirmed event notification handler returns None (SimpleACK)."""
        _, _, _, handlers = _make_app_and_handlers()
        notification = self._make_notification()
        result = await handlers.handle_confirmed_event_notification(
            0, notification.encode(), SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_unconfirmed_event_notification_returns_none(self):
        """Unconfirmed event notification handler returns None."""
        _, _, _, handlers = _make_app_and_handlers()
        notification = self._make_notification()
        result = await handlers.handle_unconfirmed_event_notification(
            0, notification.encode(), SOURCE,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Client method tests
# ---------------------------------------------------------------------------


class TestClientAlarmMethods:
    """Test client methods build correct requests and decode responses."""

    def _make_client(self):
        """Create a BACnetClient with mocked application."""
        from bac_py.app.client import BACnetClient

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        client = BACnetClient.__new__(BACnetClient)
        client._app = app
        client._default_timeout = 10.0
        return client, app

    @pytest.mark.asyncio
    async def test_acknowledge_alarm_sends_request(self):
        """acknowledge_alarm sends an AcknowledgeAlarm confirmed request."""
        client, app = self._make_client()
        app.confirmed_request.return_value = b""

        ts = BACnetTimeStamp(choice=1, value=0)
        await client.acknowledge_alarm(
            address=SOURCE,
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="test",
            time_of_acknowledgment=ts,
        )
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        from bac_py.types.enums import ConfirmedServiceChoice
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ACKNOWLEDGE_ALARM

    @pytest.mark.asyncio
    async def test_get_alarm_summary_decodes_ack(self):
        """get_alarm_summary sends request and decodes response."""
        client, app = self._make_client()
        # Build a valid ACK response
        ack = GetAlarmSummaryACK(list_of_alarm_summaries=[
            AlarmSummary(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                alarm_state=EventState.HIGH_LIMIT,
                acknowledged_transitions=BitString(b"\xe0", 5),
            ),
        ])
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_alarm_summary(address=SOURCE)
        assert len(result.list_of_alarm_summaries) == 1
        assert result.list_of_alarm_summaries[0].alarm_state == EventState.HIGH_LIMIT

    @pytest.mark.asyncio
    async def test_get_enrollment_summary_decodes_ack(self):
        """get_enrollment_summary sends request and decodes response."""
        client, app = self._make_client()
        from bac_py.services.alarm_summary import EnrollmentSummary
        ack = GetEnrollmentSummaryACK(list_of_enrollment_summaries=[
            EnrollmentSummary(
                object_identifier=ObjectIdentifier(ObjectType.EVENT_ENROLLMENT, 1),
                event_type=EventType.CHANGE_OF_VALUE,
                event_state=EventState.NORMAL,
                priority=0,
                notification_class=1,
            ),
        ])
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_enrollment_summary(
            address=SOURCE,
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        assert len(result.list_of_enrollment_summaries) == 1

    @pytest.mark.asyncio
    async def test_get_event_information_decodes_ack(self):
        """get_event_information sends request and decodes response."""
        client, app = self._make_client()
        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=False,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_event_information(address=SOURCE)
        assert len(result.list_of_event_summaries) == 0
        assert result.more_events is False

    @pytest.mark.asyncio
    async def test_confirmed_event_notification_sends_request(self):
        """confirmed_event_notification sends the notification as confirmed request."""
        client, app = self._make_client()
        app.confirmed_request.return_value = b""

        notification = EventNotificationRequest(
            process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            notification_class=1,
            priority=100,
            event_type=EventType.OUT_OF_RANGE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.HIGH_LIMIT,
            ack_required=True,
            from_state=EventState.NORMAL,
        )
        await client.confirmed_event_notification(
            address=SOURCE,
            notification=notification,
        )
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        from bac_py.types.enums import ConfirmedServiceChoice
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION
