"""Tests for alarm and enrollment query services (Step 4.2).

Per ASHRAE 135-2020 Clause 13.6, 13.7, 13.12.
"""

from bac_py.services.alarm_summary import (
    AlarmSummary,
    EnrollmentSummary,
    EventSummary,
    GetAlarmSummaryACK,
    GetAlarmSummaryRequest,
    GetEnrollmentSummaryACK,
    GetEnrollmentSummaryRequest,
    GetEventInformationACK,
    GetEventInformationRequest,
)
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    AcknowledgmentFilter,
    EventState,
    EventType,
    NotifyType,
    ObjectType,
)
from bac_py.types.primitives import BitString, ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transitions_bits(to_offnormal: bool, to_fault: bool, to_normal: bool) -> BitString:
    """Build a 3-bit BitString for EventTransitionBits."""
    val = (to_offnormal << 2) | (to_fault << 1) | to_normal
    return BitString(bytes([val << 5]), unused_bits=5)


# ---------------------------------------------------------------------------
# GetAlarmSummary
# ---------------------------------------------------------------------------


class TestGetAlarmSummaryRequest:
    def test_encode_empty(self):
        req = GetAlarmSummaryRequest()
        assert req.encode() == b""

    def test_decode_empty(self):
        req = GetAlarmSummaryRequest.decode(b"")
        assert isinstance(req, GetAlarmSummaryRequest)


class TestGetAlarmSummaryACK:
    def test_round_trip_single_alarm(self):
        ack = GetAlarmSummaryACK(
            list_of_alarm_summaries=[
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    alarm_state=EventState.HIGH_LIMIT,
                    acknowledged_transitions=_make_transitions_bits(True, True, True),
                ),
            ]
        )
        encoded = ack.encode()
        decoded = GetAlarmSummaryACK.decode(encoded)

        assert len(decoded.list_of_alarm_summaries) == 1
        s = decoded.list_of_alarm_summaries[0]
        assert s.object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert s.object_identifier.instance_number == 1
        assert s.alarm_state == EventState.HIGH_LIMIT

    def test_round_trip_multiple_alarms(self):
        ack = GetAlarmSummaryACK(
            list_of_alarm_summaries=[
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    alarm_state=EventState.HIGH_LIMIT,
                    acknowledged_transitions=_make_transitions_bits(True, False, False),
                ),
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
                    alarm_state=EventState.OFFNORMAL,
                    acknowledged_transitions=_make_transitions_bits(False, True, True),
                ),
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 100),
                    alarm_state=EventState.LOW_LIMIT,
                    acknowledged_transitions=_make_transitions_bits(True, True, True),
                ),
            ]
        )
        encoded = ack.encode()
        decoded = GetAlarmSummaryACK.decode(encoded)

        assert len(decoded.list_of_alarm_summaries) == 3
        assert decoded.list_of_alarm_summaries[0].alarm_state == EventState.HIGH_LIMIT
        assert decoded.list_of_alarm_summaries[1].alarm_state == EventState.OFFNORMAL
        assert decoded.list_of_alarm_summaries[2].alarm_state == EventState.LOW_LIMIT

    def test_round_trip_empty(self):
        ack = GetAlarmSummaryACK(list_of_alarm_summaries=[])
        encoded = ack.encode()
        assert encoded == b""
        decoded = GetAlarmSummaryACK.decode(encoded)
        assert len(decoded.list_of_alarm_summaries) == 0

    def test_round_trip_all_event_states(self):
        """Verify all alarm-capable EventState values round-trip."""
        alarm_states = [
            EventState.OFFNORMAL,
            EventState.HIGH_LIMIT,
            EventState.LOW_LIMIT,
            EventState.LIFE_SAFETY_ALARM,
            EventState.FAULT,
        ]
        summaries = [
            AlarmSummary(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
                alarm_state=state,
                acknowledged_transitions=_make_transitions_bits(True, True, True),
            )
            for i, state in enumerate(alarm_states)
        ]
        ack = GetAlarmSummaryACK(list_of_alarm_summaries=summaries)
        encoded = ack.encode()
        decoded = GetAlarmSummaryACK.decode(encoded)

        for i, state in enumerate(alarm_states):
            assert decoded.list_of_alarm_summaries[i].alarm_state == state


# ---------------------------------------------------------------------------
# GetEnrollmentSummary
# ---------------------------------------------------------------------------


class TestGetEnrollmentSummaryRequest:
    def test_round_trip_minimal(self):
        """Only required field (acknowledgment_filter)."""
        req = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        encoded = req.encode()
        decoded = GetEnrollmentSummaryRequest.decode(encoded)

        assert decoded.acknowledgment_filter == AcknowledgmentFilter.ALL
        assert decoded.event_state_filter is None
        assert decoded.event_type_filter is None
        assert decoded.priority_min is None
        assert decoded.priority_max is None
        assert decoded.notification_class_filter is None

    def test_round_trip_with_event_state_filter(self):
        req = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.NOT_ACKED,
            event_state_filter=EventState.OFFNORMAL,
        )
        encoded = req.encode()
        decoded = GetEnrollmentSummaryRequest.decode(encoded)

        assert decoded.acknowledgment_filter == AcknowledgmentFilter.NOT_ACKED
        assert decoded.event_state_filter == EventState.OFFNORMAL

    def test_round_trip_with_event_type_filter(self):
        req = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ACKED,
            event_type_filter=EventType.OUT_OF_RANGE,
        )
        encoded = req.encode()
        decoded = GetEnrollmentSummaryRequest.decode(encoded)

        assert decoded.event_type_filter == EventType.OUT_OF_RANGE

    def test_round_trip_with_priority_range(self):
        req = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            priority_min=0,
            priority_max=127,
        )
        encoded = req.encode()
        decoded = GetEnrollmentSummaryRequest.decode(encoded)

        assert decoded.priority_min == 0
        assert decoded.priority_max == 127

    def test_round_trip_with_notification_class_filter(self):
        req = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            notification_class_filter=5,
        )
        encoded = req.encode()
        decoded = GetEnrollmentSummaryRequest.decode(encoded)

        assert decoded.notification_class_filter == 5

    def test_round_trip_all_filters(self):
        """All optional filters set."""
        req = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.NOT_ACKED,
            event_state_filter=EventState.HIGH_LIMIT,
            event_type_filter=EventType.CHANGE_OF_VALUE,
            priority_min=10,
            priority_max=200,
            notification_class_filter=3,
        )
        encoded = req.encode()
        decoded = GetEnrollmentSummaryRequest.decode(encoded)

        assert decoded.acknowledgment_filter == AcknowledgmentFilter.NOT_ACKED
        assert decoded.event_state_filter == EventState.HIGH_LIMIT
        assert decoded.event_type_filter == EventType.CHANGE_OF_VALUE
        assert decoded.priority_min == 10
        assert decoded.priority_max == 200
        assert decoded.notification_class_filter == 3

    def test_round_trip_all_acknowledgment_filters(self):
        """Verify all AcknowledgmentFilter values."""
        for f in AcknowledgmentFilter:
            req = GetEnrollmentSummaryRequest(acknowledgment_filter=f)
            encoded = req.encode()
            decoded = GetEnrollmentSummaryRequest.decode(encoded)
            assert decoded.acknowledgment_filter == f


class TestGetEnrollmentSummaryACK:
    def test_round_trip_single(self):
        ack = GetEnrollmentSummaryACK(
            list_of_enrollment_summaries=[
                EnrollmentSummary(
                    object_identifier=ObjectIdentifier(ObjectType.EVENT_ENROLLMENT, 1),
                    event_type=EventType.OUT_OF_RANGE,
                    event_state=EventState.HIGH_LIMIT,
                    priority=100,
                    notification_class=5,
                ),
            ]
        )
        encoded = ack.encode()
        decoded = GetEnrollmentSummaryACK.decode(encoded)

        assert len(decoded.list_of_enrollment_summaries) == 1
        s = decoded.list_of_enrollment_summaries[0]
        assert s.object_identifier.object_type == ObjectType.EVENT_ENROLLMENT
        assert s.event_type == EventType.OUT_OF_RANGE
        assert s.event_state == EventState.HIGH_LIMIT
        assert s.priority == 100
        assert s.notification_class == 5

    def test_round_trip_multiple(self):
        ack = GetEnrollmentSummaryACK(
            list_of_enrollment_summaries=[
                EnrollmentSummary(
                    object_identifier=ObjectIdentifier(ObjectType.EVENT_ENROLLMENT, i),
                    event_type=EventType.CHANGE_OF_STATE,
                    event_state=EventState.OFFNORMAL,
                    priority=50 + i,
                    notification_class=i,
                )
                for i in range(5)
            ]
        )
        encoded = ack.encode()
        decoded = GetEnrollmentSummaryACK.decode(encoded)

        assert len(decoded.list_of_enrollment_summaries) == 5
        for i, s in enumerate(decoded.list_of_enrollment_summaries):
            assert s.object_identifier.instance_number == i
            assert s.priority == 50 + i
            assert s.notification_class == i

    def test_round_trip_empty(self):
        ack = GetEnrollmentSummaryACK(list_of_enrollment_summaries=[])
        encoded = ack.encode()
        decoded = GetEnrollmentSummaryACK.decode(encoded)
        assert len(decoded.list_of_enrollment_summaries) == 0


# ---------------------------------------------------------------------------
# GetEventInformation
# ---------------------------------------------------------------------------


class TestGetEventInformationRequest:
    def test_round_trip_no_pagination(self):
        """First request with no last_received_object_identifier."""
        req = GetEventInformationRequest()
        encoded = req.encode()
        assert encoded == b""
        decoded = GetEventInformationRequest.decode(encoded)
        assert decoded.last_received_object_identifier is None

    def test_round_trip_with_pagination(self):
        """Subsequent request for pagination."""
        req = GetEventInformationRequest(
            last_received_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 99)
        )
        encoded = req.encode()
        decoded = GetEventInformationRequest.decode(encoded)

        assert decoded.last_received_object_identifier is not None
        assert decoded.last_received_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.last_received_object_identifier.instance_number == 99


class TestGetEventInformationACK:
    def _make_summary(
        self,
        instance: int = 1,
        event_state: EventState = EventState.HIGH_LIMIT,
    ) -> EventSummary:
        ts = BACnetTimeStamp(choice=1, value=0)
        return EventSummary(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, instance),
            event_state=event_state,
            acknowledged_transitions=_make_transitions_bits(True, True, True),
            event_time_stamps=(ts, ts, ts),
            notify_type=NotifyType.ALARM,
            event_enable=_make_transitions_bits(True, True, True),
            event_priorities=(1, 1, 1),
        )

    def test_round_trip_single_event(self):
        ack = GetEventInformationACK(
            list_of_event_summaries=[self._make_summary()],
            more_events=False,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)

        assert len(decoded.list_of_event_summaries) == 1
        s = decoded.list_of_event_summaries[0]
        assert s.object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert s.object_identifier.instance_number == 1
        assert s.event_state == EventState.HIGH_LIMIT
        assert s.notify_type == NotifyType.ALARM
        assert len(s.event_time_stamps) == 3
        assert len(s.event_priorities) == 3
        assert decoded.more_events is False

    def test_round_trip_more_events_true(self):
        ack = GetEventInformationACK(
            list_of_event_summaries=[self._make_summary()],
            more_events=True,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)
        assert decoded.more_events is True

    def test_round_trip_multiple_events(self):
        ack = GetEventInformationACK(
            list_of_event_summaries=[
                self._make_summary(instance=1, event_state=EventState.HIGH_LIMIT),
                self._make_summary(instance=2, event_state=EventState.LOW_LIMIT),
                self._make_summary(instance=3, event_state=EventState.OFFNORMAL),
            ],
            more_events=False,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)

        assert len(decoded.list_of_event_summaries) == 3
        assert decoded.list_of_event_summaries[0].event_state == EventState.HIGH_LIMIT
        assert decoded.list_of_event_summaries[1].event_state == EventState.LOW_LIMIT
        assert decoded.list_of_event_summaries[2].event_state == EventState.OFFNORMAL

    def test_round_trip_empty_list(self):
        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=False,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)

        assert len(decoded.list_of_event_summaries) == 0
        assert decoded.more_events is False

    def test_round_trip_enrollment_filter_skip(self):
        """Lines 251-260: decode skips enrollmentFilter [1] if present."""
        # Build a request with all optional filters so the decode path
        # that skips enrollmentFilter [1] is exercised.
        # We encode manually: [0] ack filter, [1] enrollment filter (constructed),
        # [2] event_state, [3] event_type, [4] priority, [5] notification_class
        from bac_py.encoding.primitives import (
            encode_application_unsigned,
            encode_context_enumerated,
            encode_context_tagged,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] acknowledgmentFilter = ALL (0)
        buf.extend(encode_context_enumerated(0, 0))
        # [1] enrollmentFilter (constructed, must be skipped by decoder)
        buf.extend(encode_opening_tag(1))
        # Put some dummy data inside the constructed block
        buf.extend(encode_application_unsigned(42))
        buf.extend(encode_closing_tag(1))
        # [2] eventStateFilter = OFFNORMAL (2)
        buf.extend(encode_context_enumerated(2, int(EventState.OFFNORMAL)))
        # [3] eventTypeFilter = CHANGE_OF_VALUE (2)
        buf.extend(encode_context_enumerated(3, 2))
        # [4] priority range
        buf.extend(encode_opening_tag(4))
        buf.extend(encode_application_unsigned(10))
        buf.extend(encode_application_unsigned(200))
        buf.extend(encode_closing_tag(4))
        # [5] notificationClassFilter
        buf.extend(encode_context_tagged(5, encode_unsigned(7)))

        decoded = GetEnrollmentSummaryRequest.decode(bytes(buf))
        assert decoded.acknowledgment_filter == AcknowledgmentFilter.ALL
        assert decoded.event_state_filter == EventState.OFFNORMAL
        assert decoded.event_type_filter == EventType.CHANGE_OF_VALUE
        assert decoded.priority_min == 10
        assert decoded.priority_max == 200
        assert decoded.notification_class_filter == 7

    def test_round_trip_with_time_timestamps(self):
        """EventSummary with Time-of-day timestamps."""
        from bac_py.types.primitives import BACnetTime

        ts0 = BACnetTimeStamp(choice=0, value=BACnetTime(8, 0, 0, 0))
        ts1 = BACnetTimeStamp(choice=0, value=BACnetTime(9, 0, 0, 0))
        ts2 = BACnetTimeStamp(choice=0, value=BACnetTime(10, 0, 0, 0))
        summary = EventSummary(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state=EventState.HIGH_LIMIT,
            acknowledged_transitions=_make_transitions_bits(True, False, True),
            event_time_stamps=(ts0, ts1, ts2),
            notify_type=NotifyType.EVENT,
            event_enable=_make_transitions_bits(True, True, False),
            event_priorities=(10, 20, 30),
        )
        ack = GetEventInformationACK(
            list_of_event_summaries=[summary],
            more_events=False,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)

        s = decoded.list_of_event_summaries[0]
        assert s.event_time_stamps[0].choice == 0
        assert isinstance(s.event_time_stamps[0].value, BACnetTime)
        assert s.event_time_stamps[0].value.hour == 8
        assert s.event_time_stamps[1].value.hour == 9
        assert s.event_time_stamps[2].value.hour == 10
        assert s.notify_type == NotifyType.EVENT
        assert s.event_priorities == (10, 20, 30)

    def test_enrollment_filter_with_nested_opening_tags(self):
        """Line 256: nested opening tag inside enrollmentFilter increments depth."""
        from bac_py.encoding.primitives import (
            encode_application_unsigned,
            encode_context_enumerated,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] acknowledgmentFilter = ALL (0)
        buf.extend(encode_context_enumerated(0, 0))
        # [1] enrollmentFilter (constructed, with nested opening/closing)
        buf.extend(encode_opening_tag(1))
        # Nested constructed element inside filter
        buf.extend(encode_opening_tag(0))
        buf.extend(encode_application_unsigned(99))
        buf.extend(encode_closing_tag(0))
        buf.extend(encode_closing_tag(1))
        # [2] eventStateFilter = OFFNORMAL (2)
        buf.extend(encode_context_enumerated(2, int(EventState.OFFNORMAL)))

        decoded = GetEnrollmentSummaryRequest.decode(bytes(buf))
        assert decoded.acknowledgment_filter == AcknowledgmentFilter.ALL
        assert decoded.event_state_filter == EventState.OFFNORMAL

    def test_round_trip_various_priorities(self):
        """EventSummary with different priorities per transition."""
        summary = EventSummary(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state=EventState.NORMAL,
            acknowledged_transitions=_make_transitions_bits(True, True, True),
            event_time_stamps=(
                BACnetTimeStamp(choice=1, value=100),
                BACnetTimeStamp(choice=1, value=200),
                BACnetTimeStamp(choice=1, value=300),
            ),
            notify_type=NotifyType.ALARM,
            event_enable=_make_transitions_bits(True, True, True),
            event_priorities=(0, 128, 255),
        )
        ack = GetEventInformationACK(
            list_of_event_summaries=[summary],
            more_events=False,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)

        s = decoded.list_of_event_summaries[0]
        assert s.event_priorities == (0, 128, 255)


# ---------------------------------------------------------------------------
# Coverage: alarm_summary.py branch partials 259->253, 537->548
# ---------------------------------------------------------------------------


class TestGetEnrollmentSummaryRequestEnrollmentFilterPrimitiveTags:
    """Branch 259->253: the while loop in enrollmentFilter skip logic.

    When the enrollment filter contains primitive (non-opening, non-closing)
    tags, the code advances offset by t.length (line 260). The branch
    259->253 is the loop-back from line 259 to 253 -- specifically the case
    where a primitive tag inside the enrollment filter causes offset += t.length.
    This is already exercised by existing tests with dummy data inside the filter.
    The untaken direction is the while-loop exiting via the condition
    (depth > 0 and offset < len(data)) becoming false -- i.e., data ends
    before the enrollment filter closing tag is found.
    """

    def test_enrollment_filter_with_only_primitive_tags(self):
        """Enrollment filter containing only primitive tags (no nesting).

        Exercises the 'elif not t.is_opening and not t.is_closing' branch
        (line 259) followed by loop-back to 253.
        """
        from bac_py.encoding.primitives import (
            encode_application_unsigned,
            encode_context_enumerated,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] acknowledgmentFilter = ALL (0)
        buf.extend(encode_context_enumerated(0, 0))
        # [1] enrollmentFilter with multiple primitive tags inside
        buf.extend(encode_opening_tag(1))
        buf.extend(encode_application_unsigned(1))
        buf.extend(encode_application_unsigned(2))
        buf.extend(encode_application_unsigned(3))
        buf.extend(encode_closing_tag(1))

        decoded = GetEnrollmentSummaryRequest.decode(bytes(buf))
        assert decoded.acknowledgment_filter == AcknowledgmentFilter.ALL
        assert decoded.event_state_filter is None


class TestGetEventInformationACKEmptySummariesWhileExit:
    """Branch 537->548: while loop exit in GetEventInformationACK.decode.

    While loop in GetEventInformationACK.decode exits because the first tag
    read is the closing tag [0], causing a break which jumps to line 548
    (moreEvents).
    """

    def test_empty_event_summaries_list(self):
        """Empty listOfEventSummaries: while loop enters and immediately breaks."""
        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=True,
        )
        encoded = ack.encode()
        decoded = GetEventInformationACK.decode(encoded)
        assert len(decoded.list_of_event_summaries) == 0
        assert decoded.more_events is True
