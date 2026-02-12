"""Tests for event notification service encoding/decoding (Step 2.2).

Per ASHRAE 135-2020 Clause 13.5, 13.8, 13.9, 13.13.
"""

from bac_py.services.event_notification import (
    AcknowledgeAlarmRequest,
    EventNotificationRequest,
    LifeSafetyOperationRequest,
)
from bac_py.types.constructed import BACnetDateTime, BACnetTimeStamp
from bac_py.types.enums import (
    EventState,
    EventType,
    LifeSafetyOperation,
    NotifyType,
    ObjectType,
)
from bac_py.types.notification_params import (
    NotificationParameters,
    OutOfRange,
)
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier


class TestEventNotificationRequest:
    """Tests for EventNotification-Request encode/decode."""

    def _make_request(
        self,
        *,
        notify_type: NotifyType = NotifyType.ALARM,
        message_text: str | None = None,
        ack_required: bool | None = True,
        from_state: EventState | None = EventState.NORMAL,
        event_values: NotificationParameters | None = None,
    ) -> EventNotificationRequest:
        return EventNotificationRequest(
            process_identifier=42,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=10),
            notification_class=5,
            priority=100,
            event_type=EventType.OUT_OF_RANGE,
            notify_type=notify_type,
            to_state=EventState.HIGH_LIMIT,
            message_text=message_text,
            ack_required=ack_required,
            from_state=from_state,
            event_values=event_values,
        )

    def test_round_trip_all_fields(self):
        """Full alarm notification with all fields present."""
        event_values = OutOfRange(exceeding_value=85.5, deadband=1.0)
        req = self._make_request(
            message_text="Temperature too high",
            event_values=event_values,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.process_identifier == 42
        assert decoded.initiating_device_identifier.object_type == ObjectType.DEVICE
        assert decoded.initiating_device_identifier.instance_number == 100
        assert decoded.event_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.event_object_identifier.instance_number == 1
        assert decoded.time_stamp.choice == 1
        assert decoded.time_stamp.value == 10
        assert decoded.notification_class == 5
        assert decoded.priority == 100
        assert decoded.event_type == EventType.OUT_OF_RANGE
        assert decoded.message_text == "Temperature too high"
        assert decoded.notify_type == NotifyType.ALARM
        assert decoded.ack_required is True
        assert decoded.from_state == EventState.NORMAL
        assert decoded.to_state == EventState.HIGH_LIMIT
        assert isinstance(decoded.event_values, OutOfRange)
        assert decoded.event_values.exceeding_value == 85.5
        assert decoded.event_values.deadband == 1.0

    def test_round_trip_without_message_text(self):
        """Alarm notification without optional message_text."""
        req = self._make_request()
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.message_text is None
        assert decoded.notify_type == NotifyType.ALARM
        assert decoded.ack_required is True
        assert decoded.from_state == EventState.NORMAL
        assert decoded.to_state == EventState.HIGH_LIMIT

    def test_round_trip_ack_notification(self):
        """ACK_NOTIFICATION: conditional fields absent (tags 9, 10, 12)."""
        req = self._make_request(
            notify_type=NotifyType.ACK_NOTIFICATION,
            ack_required=None,
            from_state=None,
            event_values=None,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.notify_type == NotifyType.ACK_NOTIFICATION
        assert decoded.ack_required is None
        assert decoded.from_state is None
        assert decoded.to_state == EventState.HIGH_LIMIT
        assert decoded.event_values is None

    def test_round_trip_event_notify_type(self):
        """EVENT notify_type with conditional fields present."""
        req = self._make_request(
            notify_type=NotifyType.EVENT,
            ack_required=False,
            from_state=EventState.OFFNORMAL,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.notify_type == NotifyType.EVENT
        assert decoded.ack_required is False
        assert decoded.from_state == EventState.OFFNORMAL

    def test_round_trip_priority_boundary_zero(self):
        """Priority at the low boundary (0)."""
        req = EventNotificationRequest(
            process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            notification_class=1,
            priority=0,
            event_type=EventType.CHANGE_OF_STATE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.OFFNORMAL,
            ack_required=True,
            from_state=EventState.NORMAL,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)
        assert decoded.priority == 0

    def test_round_trip_priority_boundary_255(self):
        """Priority at the high boundary (255)."""
        req = EventNotificationRequest(
            process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            notification_class=1,
            priority=255,
            event_type=EventType.CHANGE_OF_STATE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.OFFNORMAL,
            ack_required=True,
            from_state=EventState.NORMAL,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)
        assert decoded.priority == 255

    def test_round_trip_time_timestamp(self):
        """Event notification using a Time timestamp (choice=0)."""
        req = EventNotificationRequest(
            process_identifier=7,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 3),
            time_stamp=BACnetTimeStamp(choice=0, value=BACnetTime(14, 30, 0, 0)),
            notification_class=10,
            priority=50,
            event_type=EventType.CHANGE_OF_VALUE,
            notify_type=NotifyType.EVENT,
            to_state=EventState.OFFNORMAL,
            ack_required=False,
            from_state=EventState.NORMAL,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.time_stamp.choice == 0
        assert isinstance(decoded.time_stamp.value, BACnetTime)
        assert decoded.time_stamp.value.hour == 14
        assert decoded.time_stamp.value.minute == 30

    def test_round_trip_datetime_timestamp(self):
        """Event notification using a DateTime timestamp (choice=2)."""
        dt = BACnetDateTime(
            date=BACnetDate(2024, 6, 15, 6),
            time=BACnetTime(9, 30, 0, 0),
        )
        req = EventNotificationRequest(
            process_identifier=3,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 5),
            time_stamp=BACnetTimeStamp(choice=2, value=dt),
            notification_class=1,
            priority=128,
            event_type=EventType.OUT_OF_RANGE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.LOW_LIMIT,
            ack_required=True,
            from_state=EventState.NORMAL,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.time_stamp.choice == 2
        assert isinstance(decoded.time_stamp.value, BACnetDateTime)
        assert decoded.time_stamp.value.date.year == 2024

    def test_round_trip_empty_message_text(self):
        """Empty string message_text is different from absent message_text."""
        req = self._make_request(message_text="")
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.message_text == ""

    def test_round_trip_change_of_life_safety(self):
        """CHANGE_OF_LIFE_SAFETY event type."""
        req = EventNotificationRequest(
            process_identifier=99,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.LIFE_SAFETY_POINT, 10),
            time_stamp=BACnetTimeStamp(choice=1, value=500),
            notification_class=3,
            priority=1,
            event_type=EventType.CHANGE_OF_LIFE_SAFETY,
            notify_type=NotifyType.ALARM,
            to_state=EventState.LIFE_SAFETY_ALARM,
            ack_required=True,
            from_state=EventState.NORMAL,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert decoded.event_type == EventType.CHANGE_OF_LIFE_SAFETY
        assert decoded.to_state == EventState.LIFE_SAFETY_ALARM

    def test_round_trip_all_event_states(self):
        """Verify all EventState values encode/decode correctly."""
        for state in EventState:
            req = EventNotificationRequest(
                process_identifier=1,
                initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                time_stamp=BACnetTimeStamp(choice=1, value=0),
                notification_class=1,
                priority=128,
                event_type=EventType.OUT_OF_RANGE,
                notify_type=NotifyType.ALARM,
                to_state=state,
                ack_required=True,
                from_state=EventState.NORMAL,
            )
            encoded = req.encode()
            decoded = EventNotificationRequest.decode(encoded)
            assert decoded.to_state == state

    def test_round_trip_large_process_identifier(self):
        """Large process identifier (up to 2^32-1)."""
        req = self._make_request()
        req = EventNotificationRequest(
            process_identifier=0xFFFFFFFF,
            initiating_device_identifier=req.initiating_device_identifier,
            event_object_identifier=req.event_object_identifier,
            time_stamp=req.time_stamp,
            notification_class=req.notification_class,
            priority=req.priority,
            event_type=req.event_type,
            notify_type=req.notify_type,
            to_state=req.to_state,
            ack_required=req.ack_required,
            from_state=req.from_state,
        )
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)
        assert decoded.process_identifier == 0xFFFFFFFF


class TestAcknowledgeAlarmRequest:
    """Tests for AcknowledgeAlarm-Request encode/decode."""

    def test_round_trip_basic(self):
        """Standard alarm acknowledgment."""
        req = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=42,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state_acknowledged=EventState.HIGH_LIMIT,
            time_stamp=BACnetTimeStamp(choice=1, value=100),
            acknowledgment_source="Operator-1",
            time_of_acknowledgment=BACnetTimeStamp(choice=1, value=101),
        )
        encoded = req.encode()
        decoded = AcknowledgeAlarmRequest.decode(encoded)

        assert decoded.acknowledging_process_identifier == 42
        assert decoded.event_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.event_object_identifier.instance_number == 1
        assert decoded.event_state_acknowledged == EventState.HIGH_LIMIT
        assert decoded.time_stamp.choice == 1
        assert decoded.time_stamp.value == 100
        assert decoded.acknowledgment_source == "Operator-1"
        assert decoded.time_of_acknowledgment.choice == 1
        assert decoded.time_of_acknowledgment.value == 101

    def test_round_trip_with_time_timestamps(self):
        """Timestamps using Time-of-day CHOICE variant."""
        req = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=BACnetTimeStamp(choice=0, value=BACnetTime(10, 15, 30, 0)),
            acknowledgment_source="System",
            time_of_acknowledgment=BACnetTimeStamp(choice=0, value=BACnetTime(10, 20, 0, 0)),
        )
        encoded = req.encode()
        decoded = AcknowledgeAlarmRequest.decode(encoded)

        assert decoded.time_stamp.choice == 0
        assert isinstance(decoded.time_stamp.value, BACnetTime)
        assert decoded.time_stamp.value.hour == 10
        assert decoded.time_of_acknowledgment.choice == 0
        assert isinstance(decoded.time_of_acknowledgment.value, BACnetTime)
        assert decoded.time_of_acknowledgment.value.hour == 10

    def test_round_trip_with_datetime_timestamps(self):
        """Timestamps using BACnetDateTime CHOICE variant."""
        event_ts = BACnetTimeStamp(
            choice=2,
            value=BACnetDateTime(
                date=BACnetDate(2024, 3, 15, 5),
                time=BACnetTime(8, 0, 0, 0),
            ),
        )
        ack_ts = BACnetTimeStamp(
            choice=2,
            value=BACnetDateTime(
                date=BACnetDate(2024, 3, 15, 5),
                time=BACnetTime(8, 5, 0, 0),
            ),
        )
        req = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=10,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 99),
            event_state_acknowledged=EventState.LOW_LIMIT,
            time_stamp=event_ts,
            acknowledgment_source="BMS-Central",
            time_of_acknowledgment=ack_ts,
        )
        encoded = req.encode()
        decoded = AcknowledgeAlarmRequest.decode(encoded)

        assert decoded.time_stamp.choice == 2
        assert isinstance(decoded.time_stamp.value, BACnetDateTime)
        assert decoded.time_stamp.value.date.year == 2024
        assert decoded.time_of_acknowledgment.choice == 2

    def test_round_trip_all_event_states(self):
        """Verify all EventState values can be acknowledged."""
        for state in EventState:
            req = AcknowledgeAlarmRequest(
                acknowledging_process_identifier=1,
                event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                event_state_acknowledged=state,
                time_stamp=BACnetTimeStamp(choice=1, value=0),
                acknowledgment_source="test",
                time_of_acknowledgment=BACnetTimeStamp(choice=1, value=1),
            )
            encoded = req.encode()
            decoded = AcknowledgeAlarmRequest.decode(encoded)
            assert decoded.event_state_acknowledged == state

    def test_round_trip_unicode_source(self):
        """Acknowledgment source with Unicode characters."""
        req = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state_acknowledged=EventState.NORMAL,
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            acknowledgment_source="Operator-\u00e9",
            time_of_acknowledgment=BACnetTimeStamp(choice=1, value=1),
        )
        encoded = req.encode()
        decoded = AcknowledgeAlarmRequest.decode(encoded)
        assert decoded.acknowledgment_source == "Operator-\u00e9"


class TestLifeSafetyOperationRequest:
    """Tests for LifeSafetyOperation-Request encode/decode."""

    def test_round_trip_with_object_identifier(self):
        """Request targeting a specific object."""
        req = LifeSafetyOperationRequest(
            requesting_process_identifier=1,
            requesting_source="Fire Panel",
            request=LifeSafetyOperation.SILENCE,
            object_identifier=ObjectIdentifier(ObjectType.LIFE_SAFETY_POINT, 5),
        )
        encoded = req.encode()
        decoded = LifeSafetyOperationRequest.decode(encoded)

        assert decoded.requesting_process_identifier == 1
        assert decoded.requesting_source == "Fire Panel"
        assert decoded.request == LifeSafetyOperation.SILENCE
        assert decoded.object_identifier is not None
        assert decoded.object_identifier.object_type == ObjectType.LIFE_SAFETY_POINT
        assert decoded.object_identifier.instance_number == 5

    def test_round_trip_without_object_identifier(self):
        """Request without optional object identifier (applies to device)."""
        req = LifeSafetyOperationRequest(
            requesting_process_identifier=10,
            requesting_source="Central Station",
            request=LifeSafetyOperation.RESET,
        )
        encoded = req.encode()
        decoded = LifeSafetyOperationRequest.decode(encoded)

        assert decoded.requesting_process_identifier == 10
        assert decoded.requesting_source == "Central Station"
        assert decoded.request == LifeSafetyOperation.RESET
        assert decoded.object_identifier is None

    def test_round_trip_all_operations(self):
        """Verify all LifeSafetyOperation values encode/decode correctly."""
        for op in LifeSafetyOperation:
            req = LifeSafetyOperationRequest(
                requesting_process_identifier=1,
                requesting_source="test",
                request=op,
            )
            encoded = req.encode()
            decoded = LifeSafetyOperationRequest.decode(encoded)
            assert decoded.request == op

    def test_round_trip_zone_object(self):
        """Request targeting a life safety zone."""
        req = LifeSafetyOperationRequest(
            requesting_process_identifier=5,
            requesting_source="Panel-A",
            request=LifeSafetyOperation.SILENCE_ALL,
            object_identifier=ObjectIdentifier(ObjectType.LIFE_SAFETY_ZONE, 2),
        )
        encoded = req.encode()
        decoded = LifeSafetyOperationRequest.decode(encoded)

        assert decoded.object_identifier is not None
        assert decoded.object_identifier.object_type == ObjectType.LIFE_SAFETY_ZONE
        assert decoded.object_identifier.instance_number == 2

    def test_round_trip_large_process_id(self):
        """Large process identifier."""
        req = LifeSafetyOperationRequest(
            requesting_process_identifier=0xFFFFFFFF,
            requesting_source="BMS",
            request=LifeSafetyOperation.NONE,
        )
        encoded = req.encode()
        decoded = LifeSafetyOperationRequest.decode(encoded)
        assert decoded.requesting_process_identifier == 0xFFFFFFFF
