"""COV (Change of Value) services per ASHRAE 135-2016 Clause 13.1/13.14."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_boolean,
    decode_object_identifier,
    decode_unsigned,
    encode_boolean,
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
from bac_py.services.common import BACnetPropertyValue
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier

# Re-export for backward compatibility
__all__ = ["BACnetPropertyValue", "COVNotificationRequest", "SubscribeCOVRequest"]


@dataclass(frozen=True, slots=True)
class SubscribeCOVRequest:
    """SubscribeCOV-Request service parameters (Clause 13.14.1).

    ::

        SubscribeCOV-Request ::= SEQUENCE {
            subscriberProcessIdentifier  [0] Unsigned32,
            monitoredObjectIdentifier    [1] BACnetObjectIdentifier,
            issueConfirmedNotifications  [2] BOOLEAN OPTIONAL,
            lifetime                     [3] Unsigned OPTIONAL
        }

    Per the spec, omitting both ``issueConfirmedNotifications`` and
    ``lifetime`` constitutes a subscription cancellation request.
    """

    subscriber_process_identifier: int
    monitored_object_identifier: ObjectIdentifier
    issue_confirmed_notifications: bool | None = None
    lifetime: int | None = None

    @property
    def is_cancellation(self) -> bool:
        """True when both optional fields are None (cancellation per spec)."""
        return self.issue_confirmed_notifications is None and self.lifetime is None

    def encode(self) -> bytes:
        """Encode SubscribeCOV-Request service parameters.

        Returns:
            Encoded service request bytes.
        """
        buf = bytearray()
        # [0] subscriberProcessIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.subscriber_process_identifier)))
        # [1] monitoredObjectIdentifier
        buf.extend(encode_context_object_id(1, self.monitored_object_identifier))
        # [2] issueConfirmedNotifications (optional)
        if self.issue_confirmed_notifications is not None:
            buf.extend(
                encode_context_tagged(2, encode_boolean(self.issue_confirmed_notifications))
            )
        # [3] lifetime (optional)
        if self.lifetime is not None:
            buf.extend(encode_context_tagged(3, encode_unsigned(self.lifetime)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> SubscribeCOVRequest:
        """Decode SubscribeCOV-Request from service request bytes.

        Args:
            data: Raw service request bytes.

        Returns:
            Decoded SubscribeCOVRequest.
        """
        data = as_memoryview(data)

        offset = 0

        # [0] subscriberProcessIdentifier
        tag, offset = decode_tag(data, offset)
        subscriber_process_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] monitoredObjectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        monitored_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [2] issueConfirmedNotifications (optional)
        issue_confirmed_notifications, offset = decode_optional_context(
            data, offset, 2, decode_boolean
        )

        # [3] lifetime (optional)
        lifetime, offset = decode_optional_context(data, offset, 3, decode_unsigned)

        return cls(
            subscriber_process_identifier=subscriber_process_identifier,
            monitored_object_identifier=monitored_object_identifier,
            issue_confirmed_notifications=issue_confirmed_notifications,
            lifetime=lifetime,
        )


@dataclass(frozen=True, slots=True)
class COVNotificationRequest:
    """Confirmed/Unconfirmed COVNotification-Request per Clause 13.14.7/13.14.8.

    ::

        COVNotification-Request ::= SEQUENCE {
            subscriberProcessIdentifier  [0] Unsigned32,
            initiatingDeviceIdentifier   [1] BACnetObjectIdentifier,
            monitoredObjectIdentifier    [2] BACnetObjectIdentifier,
            timeRemaining                [3] Unsigned,
            listOfValues                 [4] SEQUENCE OF BACnetPropertyValue
        }

    The same encoding is used for both ConfirmedCOVNotification-Request
    (service choice 1) and UnconfirmedCOVNotification-Request (service choice 2).
    """

    subscriber_process_identifier: int
    initiating_device_identifier: ObjectIdentifier
    monitored_object_identifier: ObjectIdentifier
    time_remaining: int
    list_of_values: list[BACnetPropertyValue]

    def encode(self) -> bytes:
        """Encode COVNotification-Request service parameters.

        Returns:
            Encoded service request bytes.
        """
        buf = bytearray()
        # [0] subscriberProcessIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.subscriber_process_identifier)))
        # [1] initiatingDeviceIdentifier
        buf.extend(encode_context_object_id(1, self.initiating_device_identifier))
        # [2] monitoredObjectIdentifier
        buf.extend(encode_context_object_id(2, self.monitored_object_identifier))
        # [3] timeRemaining
        buf.extend(encode_context_tagged(3, encode_unsigned(self.time_remaining)))
        # [4] listOfValues (SEQUENCE OF BACnetPropertyValue)
        buf.extend(encode_opening_tag(4))
        for pv in self.list_of_values:
            buf.extend(pv.encode())
        buf.extend(encode_closing_tag(4))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> COVNotificationRequest:
        """Decode COVNotification-Request from service request bytes.

        Args:
            data: Raw service request bytes.

        Returns:
            Decoded COVNotificationRequest.
        """
        data = as_memoryview(data)

        offset = 0

        # [0] subscriberProcessIdentifier
        tag, offset = decode_tag(data, offset)
        subscriber_process_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] initiatingDeviceIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        initiating_device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [2] monitoredObjectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        monitored_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [3] timeRemaining
        tag, offset = decode_tag(data, offset)
        time_remaining = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [4] listOfValues — opening tag 4
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 4

        list_of_values: list[BACnetPropertyValue] = []
        while offset < len(data):
            # Check for closing tag 4
            tag, new_offset = decode_tag(data, offset)
            if tag.is_closing and tag.number == 4:
                offset = new_offset
                break
            # Decode next BACnetPropertyValue
            pv, offset = BACnetPropertyValue.decode_from(data, offset)
            list_of_values.append(pv)

        return cls(
            subscriber_process_identifier=subscriber_process_identifier,
            initiating_device_identifier=initiating_device_identifier,
            monitored_object_identifier=monitored_object_identifier,
            time_remaining=time_remaining,
            list_of_values=list_of_values,
        )
