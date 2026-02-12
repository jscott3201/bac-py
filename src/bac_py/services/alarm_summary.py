"""Alarm and enrollment query services per ASHRAE 135-2020 Clause 13.6/13.7/13.12."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_bit_string,
    decode_boolean,
    decode_enumerated,
    decode_object_identifier,
    decode_unsigned,
    encode_application_bit_string,
    encode_application_enumerated,
    encode_application_object_id,
    encode_application_unsigned,
    encode_boolean,
    encode_context_enumerated,
    encode_context_object_id,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_optional_context,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
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
# GetAlarmSummary (Clause 13.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlarmSummary:
    """Single entry in a GetAlarmSummary-ACK (Clause 13.6.1.3).

    Encoded as three consecutive application-tagged values within the
    SEQUENCE OF.
    """

    object_identifier: ObjectIdentifier
    alarm_state: EventState
    acknowledged_transitions: BitString


@dataclass(frozen=True, slots=True)
class GetAlarmSummaryRequest:
    """GetAlarmSummary-Request (Clause 13.6.1.1).

    This service has no parameters.
    """

    def encode(self) -> bytes:
        """Encode GetAlarmSummary-Request (empty payload).

        :returns: Empty bytes.
        """
        return b""

    @classmethod
    def decode(cls, data: memoryview | bytes) -> GetAlarmSummaryRequest:
        """Decode GetAlarmSummary-Request.

        :param data: Raw service request bytes (expected empty).
        :returns: Decoded :class:`GetAlarmSummaryRequest`.
        """
        return cls()


@dataclass(frozen=True, slots=True)
class GetAlarmSummaryACK:
    """GetAlarmSummary-ACK (Clause 13.6.1.3).

    ::

        GetAlarmSummary-ACK ::= SEQUENCE OF SEQUENCE {
            objectIdentifier         BACnetObjectIdentifier,
            alarmState               BACnetEventState,
            acknowledgedTransitions  BACnetEventTransitionBits
        }

    Inner SEQUENCE uses application-tagged encoding (no context tags).
    """

    list_of_alarm_summaries: list[AlarmSummary]

    def encode(self) -> bytes:
        """Encode GetAlarmSummary-ACK.

        :returns: Encoded ACK bytes.
        """
        buf = bytearray()
        for s in self.list_of_alarm_summaries:
            buf.extend(
                encode_application_object_id(
                    int(s.object_identifier.object_type),
                    s.object_identifier.instance_number,
                )
            )
            buf.extend(encode_application_enumerated(int(s.alarm_state)))
            buf.extend(encode_application_bit_string(s.acknowledged_transitions))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> GetAlarmSummaryACK:
        """Decode GetAlarmSummary-ACK.

        :param data: Raw ACK bytes.
        :returns: Decoded :class:`GetAlarmSummaryACK`.
        """
        data = as_memoryview(data)
        offset = 0
        summaries: list[AlarmSummary] = []

        while offset < len(data):
            # ObjectIdentifier (app tag 12)
            tag, offset = decode_tag(data, offset)
            obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
            offset += tag.length

            # EventState (app tag 9 = enumerated)
            tag, offset = decode_tag(data, offset)
            alarm_state = EventState(decode_enumerated(data[offset : offset + tag.length]))
            offset += tag.length

            # EventTransitionBits (app tag 8 = bitstring)
            tag, offset = decode_tag(data, offset)
            acked = decode_bit_string(data[offset : offset + tag.length])
            offset += tag.length

            summaries.append(
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType(obj_type), instance),
                    alarm_state=alarm_state,
                    acknowledged_transitions=acked,
                )
            )

        return cls(list_of_alarm_summaries=summaries)


# ---------------------------------------------------------------------------
# GetEnrollmentSummary (Clause 13.7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnrollmentSummary:
    """Single entry in a GetEnrollmentSummary-ACK (Clause 13.7.1.3).

    Encoded as five consecutive application-tagged values.
    """

    object_identifier: ObjectIdentifier
    event_type: EventType
    event_state: EventState
    priority: int
    notification_class: int


@dataclass(frozen=True, slots=True)
class GetEnrollmentSummaryRequest:
    """GetEnrollmentSummary-Request (Clause 13.7.1.1).

    ::

        GetEnrollmentSummary-Request ::= SEQUENCE {
            acknowledgmentFilter      [0] ENUMERATED,
            enrollmentFilter          [1] BACnetRecipientProcess OPTIONAL,
            eventStateFilter          [2] ENUMERATED OPTIONAL,
            eventTypeFilter           [3] BACnetEventType OPTIONAL,
            priority                  [4] SEQUENCE {
                minPriority Unsigned(0..255),
                maxPriority Unsigned(0..255)
            } OPTIONAL,
            notificationClassFilter   [5] Unsigned OPTIONAL
        }

    The ``enrollment_filter`` field (tag 1) is not currently supported
    for encoding. Decoding will skip it if present.
    """

    acknowledgment_filter: AcknowledgmentFilter
    event_state_filter: EventState | None = None
    event_type_filter: EventType | None = None
    priority_min: int | None = None
    priority_max: int | None = None
    notification_class_filter: int | None = None

    def encode(self) -> bytes:
        """Encode GetEnrollmentSummary-Request.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] acknowledgmentFilter
        buf.extend(encode_context_enumerated(0, int(self.acknowledgment_filter)))
        # [1] enrollmentFilter -- not supported for encoding yet
        # [2] eventStateFilter (optional)
        if self.event_state_filter is not None:
            buf.extend(encode_context_enumerated(2, int(self.event_state_filter)))
        # [3] eventTypeFilter (optional)
        if self.event_type_filter is not None:
            buf.extend(encode_context_enumerated(3, int(self.event_type_filter)))
        # [4] priority range (optional, both must be set)
        if self.priority_min is not None and self.priority_max is not None:
            buf.extend(encode_opening_tag(4))
            buf.extend(encode_application_unsigned(self.priority_min))
            buf.extend(encode_application_unsigned(self.priority_max))
            buf.extend(encode_closing_tag(4))
        # [5] notificationClassFilter (optional)
        if self.notification_class_filter is not None:
            buf.extend(encode_context_tagged(5, encode_unsigned(self.notification_class_filter)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> GetEnrollmentSummaryRequest:
        """Decode GetEnrollmentSummary-Request.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`GetEnrollmentSummaryRequest`.
        """
        data = as_memoryview(data)
        offset = 0

        # [0] acknowledgmentFilter
        tag, offset = decode_tag(data, offset)
        acknowledgment_filter = AcknowledgmentFilter(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [1] enrollmentFilter (optional, skip if present)
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 1 and tag.is_opening:
                # Skip the constructed enrollmentFilter
                depth = 1
                offset = new_offset
                while depth > 0 and offset < len(data):
                    t, offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                    elif t.is_closing:
                        depth -= 1
                    elif not t.is_opening and not t.is_closing:
                        offset += t.length

        # [2] eventStateFilter (optional)
        event_state_raw, offset = decode_optional_context(
            data, offset, 2, lambda d: decode_unsigned(d)
        )
        event_state_filter = EventState(event_state_raw) if event_state_raw is not None else None

        # [3] eventTypeFilter (optional)
        event_type_raw, offset = decode_optional_context(
            data, offset, 3, lambda d: decode_unsigned(d)
        )
        event_type_filter = EventType(event_type_raw) if event_type_raw is not None else None

        # [4] priority range (optional, constructed)
        priority_min: int | None = None
        priority_max: int | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 4 and tag.is_opening:
                offset = new_offset
                # minPriority (application-tagged unsigned)
                tag, offset = decode_tag(data, offset)
                priority_min = decode_unsigned(data[offset : offset + tag.length])
                offset += tag.length
                # maxPriority (application-tagged unsigned)
                tag, offset = decode_tag(data, offset)
                priority_max = decode_unsigned(data[offset : offset + tag.length])
                offset += tag.length
                # closing tag 4
                closing, offset = decode_tag(data, offset)
                assert closing.is_closing and closing.number == 4

        # [5] notificationClassFilter (optional)
        notification_class_filter, offset = decode_optional_context(
            data, offset, 5, decode_unsigned
        )

        return cls(
            acknowledgment_filter=acknowledgment_filter,
            event_state_filter=event_state_filter,
            event_type_filter=event_type_filter,
            priority_min=priority_min,
            priority_max=priority_max,
            notification_class_filter=notification_class_filter,
        )


@dataclass(frozen=True, slots=True)
class GetEnrollmentSummaryACK:
    """GetEnrollmentSummary-ACK (Clause 13.7.1.3).

    ::

        GetEnrollmentSummary-ACK ::= SEQUENCE OF SEQUENCE {
            objectIdentifier   BACnetObjectIdentifier,
            eventType          BACnetEventType,
            eventState         BACnetEventState,
            priority           Unsigned(0..255),
            notificationClass  Unsigned
        }

    Inner SEQUENCE uses application-tagged encoding.
    """

    list_of_enrollment_summaries: list[EnrollmentSummary]

    def encode(self) -> bytes:
        """Encode GetEnrollmentSummary-ACK.

        :returns: Encoded ACK bytes.
        """
        buf = bytearray()
        for s in self.list_of_enrollment_summaries:
            buf.extend(
                encode_application_object_id(
                    int(s.object_identifier.object_type),
                    s.object_identifier.instance_number,
                )
            )
            buf.extend(encode_application_enumerated(int(s.event_type)))
            buf.extend(encode_application_enumerated(int(s.event_state)))
            buf.extend(encode_application_unsigned(s.priority))
            buf.extend(encode_application_unsigned(s.notification_class))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> GetEnrollmentSummaryACK:
        """Decode GetEnrollmentSummary-ACK.

        :param data: Raw ACK bytes.
        :returns: Decoded :class:`GetEnrollmentSummaryACK`.
        """
        data = as_memoryview(data)
        offset = 0
        summaries: list[EnrollmentSummary] = []

        while offset < len(data):
            # ObjectIdentifier
            tag, offset = decode_tag(data, offset)
            obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
            offset += tag.length

            # EventType (enumerated)
            tag, offset = decode_tag(data, offset)
            event_type = EventType(decode_enumerated(data[offset : offset + tag.length]))
            offset += tag.length

            # EventState (enumerated)
            tag, offset = decode_tag(data, offset)
            event_state = EventState(decode_enumerated(data[offset : offset + tag.length]))
            offset += tag.length

            # Priority (unsigned)
            tag, offset = decode_tag(data, offset)
            priority = decode_unsigned(data[offset : offset + tag.length])
            offset += tag.length

            # NotificationClass (unsigned)
            tag, offset = decode_tag(data, offset)
            notification_class = decode_unsigned(data[offset : offset + tag.length])
            offset += tag.length

            summaries.append(
                EnrollmentSummary(
                    object_identifier=ObjectIdentifier(ObjectType(obj_type), instance),
                    event_type=event_type,
                    event_state=event_state,
                    priority=priority,
                    notification_class=notification_class,
                )
            )

        return cls(list_of_enrollment_summaries=summaries)


# ---------------------------------------------------------------------------
# GetEventInformation (Clause 13.12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventSummary:
    """Single entry in a GetEventInformation-ACK (Clause 13.12.1.3).

    Uses context-tagged encoding within the outer SEQUENCE OF.
    """

    object_identifier: ObjectIdentifier
    event_state: EventState
    acknowledged_transitions: BitString
    event_time_stamps: tuple[BACnetTimeStamp, BACnetTimeStamp, BACnetTimeStamp]
    notify_type: NotifyType
    event_enable: BitString
    event_priorities: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class GetEventInformationRequest:
    """GetEventInformation-Request (Clause 13.12.1.1).

    ::

        GetEventInformation-Request ::= SEQUENCE {
            lastReceivedObjectIdentifier [0] BACnetObjectIdentifier OPTIONAL
        }
    """

    last_received_object_identifier: ObjectIdentifier | None = None

    def encode(self) -> bytes:
        """Encode GetEventInformation-Request.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        if self.last_received_object_identifier is not None:
            buf.extend(encode_context_object_id(0, self.last_received_object_identifier))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> GetEventInformationRequest:
        """Decode GetEventInformation-Request.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`GetEventInformationRequest`.
        """
        data = as_memoryview(data)
        if len(data) == 0:
            return cls()

        tag, offset = decode_tag(data, 0)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        return cls(
            last_received_object_identifier=ObjectIdentifier(ObjectType(obj_type), instance)
        )


@dataclass(frozen=True, slots=True)
class GetEventInformationACK:
    """GetEventInformation-ACK (Clause 13.12.1.3).

    ::

        GetEventInformation-ACK ::= SEQUENCE {
            listOfEventSummaries [0] SEQUENCE OF SEQUENCE {
                objectIdentifier        [0] BACnetObjectIdentifier,
                eventState              [1] BACnetEventState,
                acknowledgedTransitions [2] BACnetEventTransitionBits,
                eventTimeStamps         [3] SEQUENCE OF BACnetTimeStamp SIZE(3),
                notifyType              [4] BACnetNotifyType,
                eventEnable             [5] BACnetEventTransitionBits,
                eventPriorities         [6] SEQUENCE SIZE(3) OF Unsigned
            },
            moreEvents [1] BOOLEAN
        }
    """

    list_of_event_summaries: list[EventSummary]
    more_events: bool

    def encode(self) -> bytes:
        """Encode GetEventInformation-ACK.

        :returns: Encoded ACK bytes.
        """
        buf = bytearray()
        # [0] listOfEventSummaries
        buf.extend(encode_opening_tag(0))
        for s in self.list_of_event_summaries:
            self._encode_event_summary(buf, s)
        buf.extend(encode_closing_tag(0))
        # [1] moreEvents
        buf.extend(encode_context_tagged(1, encode_boolean(self.more_events)))
        return bytes(buf)

    @staticmethod
    def _encode_event_summary(buf: bytearray, s: EventSummary) -> None:
        """Encode a single EventSummary into *buf*."""
        # [0] objectIdentifier
        buf.extend(encode_context_object_id(0, s.object_identifier))
        # [1] eventState
        buf.extend(encode_context_enumerated(1, int(s.event_state)))
        # [2] acknowledgedTransitions
        from bac_py.encoding.primitives import encode_bit_string

        buf.extend(encode_context_tagged(2, encode_bit_string(s.acknowledged_transitions)))
        # [3] eventTimeStamps (SEQUENCE OF, 3 elements)
        buf.extend(encode_opening_tag(3))
        for ts in s.event_time_stamps:
            buf.extend(ts.encode())
        buf.extend(encode_closing_tag(3))
        # [4] notifyType
        buf.extend(encode_context_enumerated(4, int(s.notify_type)))
        # [5] eventEnable
        buf.extend(encode_context_tagged(5, encode_bit_string(s.event_enable)))
        # [6] eventPriorities (SEQUENCE OF, 3 unsigned)
        buf.extend(encode_opening_tag(6))
        for p in s.event_priorities:
            buf.extend(encode_application_unsigned(p))
        buf.extend(encode_closing_tag(6))

    @classmethod
    def decode(cls, data: memoryview | bytes) -> GetEventInformationACK:
        """Decode GetEventInformation-ACK.

        :param data: Raw ACK bytes.
        :returns: Decoded :class:`GetEventInformationACK`.
        """
        data = as_memoryview(data)
        offset = 0

        # [0] listOfEventSummaries -- opening tag 0
        tag, offset = decode_tag(data, offset)
        assert tag.is_opening and tag.number == 0

        summaries: list[EventSummary] = []
        while offset < len(data):
            # Check for closing tag 0
            tag, new_offset = decode_tag(data, offset)
            if tag.is_closing and tag.number == 0:
                offset = new_offset
                break
            # Decode one EventSummary
            summary, offset = cls._decode_event_summary(data, offset)
            summaries.append(summary)

        # [1] moreEvents
        tag, offset = decode_tag(data, offset)
        more_events = decode_boolean(data[offset : offset + tag.length])
        offset += tag.length

        return cls(
            list_of_event_summaries=summaries,
            more_events=more_events,
        )

    @staticmethod
    def _decode_event_summary(data: memoryview, offset: int) -> tuple[EventSummary, int]:
        """Decode a single EventSummary from *data* at *offset*."""
        from bac_py.encoding.primitives import decode_bit_string

        # [0] objectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] eventState
        tag, offset = decode_tag(data, offset)
        event_state = EventState(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [2] acknowledgedTransitions
        tag, offset = decode_tag(data, offset)
        acknowledged_transitions = decode_bit_string(data[offset : offset + tag.length])
        offset += tag.length

        # [3] eventTimeStamps -- opening tag 3
        tag, offset = decode_tag(data, offset)
        assert tag.is_opening and tag.number == 3
        timestamps: list[BACnetTimeStamp] = []
        for _ in range(3):
            ts, offset = BACnetTimeStamp.decode(data, offset)
            timestamps.append(ts)
        closing, offset = decode_tag(data, offset)
        assert closing.is_closing and closing.number == 3

        # [4] notifyType
        tag, offset = decode_tag(data, offset)
        notify_type = NotifyType(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [5] eventEnable
        tag, offset = decode_tag(data, offset)
        event_enable = decode_bit_string(data[offset : offset + tag.length])
        offset += tag.length

        # [6] eventPriorities -- opening tag 6
        tag, offset = decode_tag(data, offset)
        assert tag.is_opening and tag.number == 6
        priorities: list[int] = []
        for _ in range(3):
            tag, offset = decode_tag(data, offset)
            priorities.append(decode_unsigned(data[offset : offset + tag.length]))
            offset += tag.length
        closing, offset = decode_tag(data, offset)
        assert closing.is_closing and closing.number == 6

        return (
            EventSummary(
                object_identifier=object_identifier,
                event_state=event_state,
                acknowledged_transitions=acknowledged_transitions,
                event_time_stamps=(timestamps[0], timestamps[1], timestamps[2]),
                notify_type=notify_type,
                event_enable=event_enable,
                event_priorities=(priorities[0], priorities[1], priorities[2]),
            ),
            offset,
        )
