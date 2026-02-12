"""Event notification services per ASHRAE 135-2020 Clause 13.5/13.8/13.9/13.13."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_boolean,
    decode_character_string,
    decode_object_identifier,
    decode_unsigned,
    encode_boolean,
    encode_character_string,
    encode_context_enumerated,
    encode_context_object_id,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    as_memoryview,
    decode_optional_context,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
)
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    EventState,
    EventType,
    LifeSafetyOperation,
    NotifyType,
    ObjectType,
)
from bac_py.types.notification_params import (
    NotificationParameters,
    decode_notification_parameters,
)
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class EventNotificationRequest:
    """Confirmed/Unconfirmed EventNotification-Request (Clause 13.8.1/13.9.1).

    ::

        EventNotification-Request ::= SEQUENCE {
            processIdentifier            [0] Unsigned32,
            initiatingDeviceIdentifier   [1] BACnetObjectIdentifier,
            eventObjectIdentifier        [2] BACnetObjectIdentifier,
            timeStamp                    [3] BACnetTimeStamp,
            notificationClass            [4] Unsigned,
            priority                     [5] Unsigned (0..255),
            eventType                    [6] BACnetEventType,
            messageText                  [7] CharacterString OPTIONAL,
            notifyType                   [8] BACnetNotifyType,
            ackRequired                  [9] BOOLEAN           -- conditional,
            fromState                    [10] BACnetEventState  -- conditional,
            toState                      [11] BACnetEventState,
            eventValues                  [12] BACnetNotificationParameters -- conditional
        }

    Conditional fields (tags 9, 10, 12) are present only when
    ``notify_type`` is ``ALARM`` or ``EVENT``.

    The ``event_values`` field is decoded as a typed
    :data:`~bac_py.types.notification_params.NotificationParameters` variant.
    """

    process_identifier: int
    initiating_device_identifier: ObjectIdentifier
    event_object_identifier: ObjectIdentifier
    time_stamp: BACnetTimeStamp
    notification_class: int
    priority: int
    event_type: EventType
    notify_type: NotifyType
    to_state: EventState
    message_text: str | None = None
    ack_required: bool | None = None
    from_state: EventState | None = None
    event_values: NotificationParameters | None = None

    def encode(self) -> bytes:
        """Encode EventNotification-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] processIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.process_identifier)))
        # [1] initiatingDeviceIdentifier
        buf.extend(encode_context_object_id(1, self.initiating_device_identifier))
        # [2] eventObjectIdentifier
        buf.extend(encode_context_object_id(2, self.event_object_identifier))
        # [3] timeStamp (constructed CHOICE)
        buf.extend(encode_opening_tag(3))
        buf.extend(self.time_stamp.encode())
        buf.extend(encode_closing_tag(3))
        # [4] notificationClass
        buf.extend(encode_context_tagged(4, encode_unsigned(self.notification_class)))
        # [5] priority
        buf.extend(encode_context_tagged(5, encode_unsigned(self.priority)))
        # [6] eventType
        buf.extend(encode_context_enumerated(6, int(self.event_type)))
        # [7] messageText (optional)
        if self.message_text is not None:
            buf.extend(encode_context_tagged(7, encode_character_string(self.message_text)))
        # [8] notifyType
        buf.extend(encode_context_enumerated(8, int(self.notify_type)))
        # [9] ackRequired (conditional: ALARM or EVENT)
        if self.ack_required is not None:
            buf.extend(encode_context_tagged(9, encode_boolean(self.ack_required)))
        # [10] fromState (conditional: ALARM or EVENT)
        if self.from_state is not None:
            buf.extend(encode_context_enumerated(10, int(self.from_state)))
        # [11] toState
        buf.extend(encode_context_enumerated(11, int(self.to_state)))
        # [12] eventValues (conditional: ALARM or EVENT)
        if self.event_values is not None:
            buf.extend(encode_opening_tag(12))
            buf.extend(self.event_values.encode())
            buf.extend(encode_closing_tag(12))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> EventNotificationRequest:
        """Decode EventNotification-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`EventNotificationRequest`.
        """
        data = as_memoryview(data)
        offset = 0

        # [0] processIdentifier
        tag, offset = decode_tag(data, offset)
        process_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] initiatingDeviceIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        initiating_device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [2] eventObjectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        event_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [3] timeStamp (constructed -- opening tag 3)
        tag, offset = decode_tag(data, offset)  # opening tag 3
        time_stamp, offset = BACnetTimeStamp.decode(data, offset)
        closing, offset = decode_tag(data, offset)  # closing tag 3
        assert closing.is_closing and closing.number == 3

        # [4] notificationClass
        tag, offset = decode_tag(data, offset)
        notification_class = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [5] priority
        tag, offset = decode_tag(data, offset)
        priority = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [6] eventType
        tag, offset = decode_tag(data, offset)
        event_type = EventType(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [7] messageText (optional)
        message_text, offset = decode_optional_context(data, offset, 7, decode_character_string)

        # [8] notifyType
        tag, offset = decode_tag(data, offset)
        notify_type = NotifyType(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [9] ackRequired (conditional)
        ack_required, offset = decode_optional_context(data, offset, 9, decode_boolean)

        # [10] fromState (conditional)
        from_state_raw, offset = decode_optional_context(
            data, offset, 10, lambda d: decode_unsigned(d)
        )
        from_state = EventState(from_state_raw) if from_state_raw is not None else None

        # [11] toState
        tag, offset = decode_tag(data, offset)
        to_state = EventState(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [12] eventValues (conditional, typed NotificationParameters)
        event_values: NotificationParameters | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.is_opening and tag.number == 12:
                offset = new_offset
                event_values, offset = decode_notification_parameters(data, offset)
                closing, offset = decode_tag(data, offset)
                assert closing.is_closing and closing.number == 12

        return cls(
            process_identifier=process_identifier,
            initiating_device_identifier=initiating_device_identifier,
            event_object_identifier=event_object_identifier,
            time_stamp=time_stamp,
            notification_class=notification_class,
            priority=priority,
            event_type=event_type,
            message_text=message_text,
            notify_type=notify_type,
            ack_required=ack_required,
            from_state=from_state,
            to_state=to_state,
            event_values=event_values,
        )


@dataclass(frozen=True, slots=True)
class AcknowledgeAlarmRequest:
    """AcknowledgeAlarm-Request per Clause 13.5.1.

    ::

        AcknowledgeAlarm-Request ::= SEQUENCE {
            acknowledgingProcessIdentifier [0] Unsigned32,
            eventObjectIdentifier          [1] BACnetObjectIdentifier,
            eventStateAcknowledged         [2] BACnetEventState,
            timeStamp                      [3] BACnetTimeStamp,
            acknowledgmentSource           [4] CharacterString,
            timeOfAcknowledgment           [5] BACnetTimeStamp
        }
    """

    acknowledging_process_identifier: int
    event_object_identifier: ObjectIdentifier
    event_state_acknowledged: EventState
    time_stamp: BACnetTimeStamp
    acknowledgment_source: str
    time_of_acknowledgment: BACnetTimeStamp

    def encode(self) -> bytes:
        """Encode AcknowledgeAlarm-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] acknowledgingProcessIdentifier
        buf.extend(
            encode_context_tagged(0, encode_unsigned(self.acknowledging_process_identifier))
        )
        # [1] eventObjectIdentifier
        buf.extend(encode_context_object_id(1, self.event_object_identifier))
        # [2] eventStateAcknowledged
        buf.extend(encode_context_enumerated(2, int(self.event_state_acknowledged)))
        # [3] timeStamp (constructed CHOICE)
        buf.extend(encode_opening_tag(3))
        buf.extend(self.time_stamp.encode())
        buf.extend(encode_closing_tag(3))
        # [4] acknowledgmentSource
        buf.extend(encode_context_tagged(4, encode_character_string(self.acknowledgment_source)))
        # [5] timeOfAcknowledgment (constructed CHOICE)
        buf.extend(encode_opening_tag(5))
        buf.extend(self.time_of_acknowledgment.encode())
        buf.extend(encode_closing_tag(5))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> AcknowledgeAlarmRequest:
        """Decode AcknowledgeAlarm-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`AcknowledgeAlarmRequest`.
        """
        data = as_memoryview(data)
        offset = 0

        # [0] acknowledgingProcessIdentifier
        tag, offset = decode_tag(data, offset)
        acknowledging_process_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] eventObjectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        event_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [2] eventStateAcknowledged
        tag, offset = decode_tag(data, offset)
        event_state_acknowledged = EventState(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [3] timeStamp (constructed)
        tag, offset = decode_tag(data, offset)  # opening tag 3
        time_stamp, offset = BACnetTimeStamp.decode(data, offset)
        closing, offset = decode_tag(data, offset)  # closing tag 3
        assert closing.is_closing and closing.number == 3

        # [4] acknowledgmentSource
        tag, offset = decode_tag(data, offset)
        acknowledgment_source = decode_character_string(data[offset : offset + tag.length])
        offset += tag.length

        # [5] timeOfAcknowledgment (constructed)
        tag, offset = decode_tag(data, offset)  # opening tag 5
        time_of_acknowledgment, offset = BACnetTimeStamp.decode(data, offset)
        closing, offset = decode_tag(data, offset)  # closing tag 5
        assert closing.is_closing and closing.number == 5

        return cls(
            acknowledging_process_identifier=acknowledging_process_identifier,
            event_object_identifier=event_object_identifier,
            event_state_acknowledged=event_state_acknowledged,
            time_stamp=time_stamp,
            acknowledgment_source=acknowledgment_source,
            time_of_acknowledgment=time_of_acknowledgment,
        )


@dataclass(frozen=True, slots=True)
class LifeSafetyOperationRequest:
    """LifeSafetyOperation-Request per Clause 13.13.1.

    ::

        LifeSafetyOperation-Request ::= SEQUENCE {
            requestingProcessIdentifier [0] Unsigned32,
            requestingSource            [1] CharacterString,
            request                     [2] BACnetLifeSafetyOperation,
            objectIdentifier            [3] BACnetObjectIdentifier OPTIONAL
        }
    """

    requesting_process_identifier: int
    requesting_source: str
    request: LifeSafetyOperation
    object_identifier: ObjectIdentifier | None = None

    def encode(self) -> bytes:
        """Encode LifeSafetyOperation-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] requestingProcessIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.requesting_process_identifier)))
        # [1] requestingSource
        buf.extend(encode_context_tagged(1, encode_character_string(self.requesting_source)))
        # [2] request
        buf.extend(encode_context_enumerated(2, int(self.request)))
        # [3] objectIdentifier (optional)
        if self.object_identifier is not None:
            buf.extend(encode_context_object_id(3, self.object_identifier))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> LifeSafetyOperationRequest:
        """Decode LifeSafetyOperation-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`LifeSafetyOperationRequest`.
        """
        data = as_memoryview(data)
        offset = 0

        # [0] requestingProcessIdentifier
        tag, offset = decode_tag(data, offset)
        requesting_process_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] requestingSource
        tag, offset = decode_tag(data, offset)
        requesting_source = decode_character_string(data[offset : offset + tag.length])
        offset += tag.length

        # [2] request
        tag, offset = decode_tag(data, offset)
        request = LifeSafetyOperation(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # [3] objectIdentifier (optional)
        object_identifier: ObjectIdentifier | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.number == 3:
                obj_type, instance = decode_object_identifier(
                    data[new_offset : new_offset + tag.length]
                )
                object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        return cls(
            requesting_process_identifier=requesting_process_identifier,
            requesting_source=requesting_source,
            request=request,
            object_identifier=object_identifier,
        )
