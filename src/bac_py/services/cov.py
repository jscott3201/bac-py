"""COV (Change of Value) services per ASHRAE 135-2016 Clause 13.1/13.14."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_boolean,
    decode_object_identifier,
    decode_real,
    decode_unsigned,
    encode_boolean,
    encode_context_object_id,
    encode_context_real,
    encode_context_tagged,
    encode_real,
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
from bac_py.services.common import BACnetPropertyValue
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier

# Re-export for backward compatibility
__all__ = [
    "BACnetPropertyReference",
    "BACnetPropertyValue",
    "COVNotificationMultipleRequest",
    "COVNotificationRequest",
    "COVObjectNotification",
    "COVPropertyValue",
    "COVReference",
    "COVSubscriptionSpecification",
    "SubscribeCOVPropertyMultipleRequest",
    "SubscribeCOVPropertyRequest",
    "SubscribeCOVRequest",
]


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
        """Check whether this request is a subscription cancellation.

        :returns: ``True`` when both optional fields are ``None`` (cancellation per spec).
        """
        return self.issue_confirmed_notifications is None and self.lifetime is None

    def encode(self) -> bytes:
        """Encode SubscribeCOV-Request service parameters.

        :returns: Encoded service request bytes.
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

        :param data: Raw service request bytes.
        :returns: Decoded :class:`SubscribeCOVRequest`.
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

        :returns: Encoded service request bytes.
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

        :param data: Raw service request bytes.
        :returns: Decoded :class:`COVNotificationRequest`.
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

        # [4] listOfValues -- opening tag 4
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


@dataclass(frozen=True, slots=True)
class BACnetPropertyReference:
    """BACnetPropertyReference -- property identifier with optional array index.

    ::

        BACnetPropertyReference ::= SEQUENCE {
            propertyIdentifier   [0] BACnetPropertyIdentifier,
            propertyArrayIndex   [1] Unsigned OPTIONAL
        }
    """

    property_identifier: int
    property_array_index: int | None = None

    def encode(self) -> bytes:
        """Encode BACnetPropertyReference as context-tagged fields.

        :returns: Encoded bytes for this property reference.
        """
        buf = bytearray()
        # [0] propertyIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.property_identifier)))
        # [1] propertyArrayIndex (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(1, encode_unsigned(self.property_array_index)))
        return bytes(buf)

    @classmethod
    def decode(
        cls, data: memoryview | bytes, offset: int = 0
    ) -> tuple[BACnetPropertyReference, int]:
        """Decode BACnetPropertyReference from data at a given offset.

        :param data: Raw bytes containing encoded property reference data.
        :param offset: Byte offset to start decoding from.
        :returns: Tuple of (decoded :class:`BACnetPropertyReference`, new offset).
        """
        data = as_memoryview(data)

        # [0] propertyIdentifier
        tag, offset = decode_tag(data, offset)
        property_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] propertyArrayIndex (optional)
        property_array_index: int | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if (
                tag.cls == TagClass.CONTEXT
                and tag.number == 1
                and not tag.is_opening
                and not tag.is_closing
            ):
                property_array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length

        return cls(
            property_identifier=property_identifier,
            property_array_index=property_array_index,
        ), offset


@dataclass(frozen=True, slots=True)
class SubscribeCOVPropertyRequest:
    """SubscribeCOVProperty-Request service parameters (Clause 13.15.1).

    ::

        SubscribeCOVProperty-Request ::= SEQUENCE {
            subscriberProcessIdentifier  [0] Unsigned32,
            monitoredObjectIdentifier    [1] BACnetObjectIdentifier,
            issueConfirmedNotifications  [2] BOOLEAN OPTIONAL,
            lifetime                     [3] Unsigned OPTIONAL,
            monitoredPropertyIdentifier  [4] BACnetPropertyReference,
            covIncrement                 [5] REAL OPTIONAL
        }
    """

    subscriber_process_identifier: int
    monitored_object_identifier: ObjectIdentifier
    monitored_property_identifier: BACnetPropertyReference
    issue_confirmed_notifications: bool | None = None
    lifetime: int | None = None
    cov_increment: float | None = None

    def encode(self) -> bytes:
        """Encode SubscribeCOVProperty-Request service parameters.

        :returns: Encoded service request bytes.
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
        # [4] monitoredPropertyIdentifier (constructed)
        buf.extend(encode_opening_tag(4))
        buf.extend(self.monitored_property_identifier.encode())
        buf.extend(encode_closing_tag(4))
        # [5] covIncrement (optional)
        if self.cov_increment is not None:
            buf.extend(encode_context_tagged(5, encode_real(self.cov_increment)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> SubscribeCOVPropertyRequest:
        """Decode SubscribeCOVProperty-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`SubscribeCOVPropertyRequest`.
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

        # [4] monitoredPropertyIdentifier (constructed -- opening/closing tag 4)
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 4
        monitored_property_identifier, offset = BACnetPropertyReference.decode(data, offset)
        # consume closing tag 4
        tag, offset = decode_tag(data, offset)

        # [5] covIncrement (optional)
        cov_increment, offset = decode_optional_context(data, offset, 5, decode_real)

        return cls(
            subscriber_process_identifier=subscriber_process_identifier,
            monitored_object_identifier=monitored_object_identifier,
            monitored_property_identifier=monitored_property_identifier,
            issue_confirmed_notifications=issue_confirmed_notifications,
            lifetime=lifetime,
            cov_increment=cov_increment,
        )


@dataclass(frozen=True, slots=True)
class COVReference:
    """A single COV reference within a COV subscription specification.

    ::

        SEQUENCE {
            monitoredProperty  [0] BACnetPropertyReference,
            covIncrement       [1] REAL OPTIONAL
        }
    """

    monitored_property: BACnetPropertyReference
    cov_increment: float | None = None

    def encode(self) -> bytes:
        """Encode COVReference.

        :returns: Encoded bytes for this COV reference.
        """
        buf = bytearray()
        # [0] monitoredProperty (constructed)
        buf.extend(encode_opening_tag(0))
        buf.extend(self.monitored_property.encode())
        buf.extend(encode_closing_tag(0))
        # [1] covIncrement (optional)
        if self.cov_increment is not None:
            buf.extend(encode_context_real(1, self.cov_increment))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int = 0) -> tuple[COVReference, int]:
        """Decode COVReference from data at a given offset.

        :param data: Buffer to decode from.
        :param offset: Starting byte offset.
        :returns: Tuple of (decoded :class:`COVReference`, new offset).
        """
        data = as_memoryview(data)

        # [0] monitoredProperty -- opening tag 0
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 0
        monitored_property, offset = BACnetPropertyReference.decode(data, offset)
        # consume closing tag 0
        tag, offset = decode_tag(data, offset)

        # [1] covIncrement (optional)
        cov_increment: float | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if (
                tag.cls == TagClass.CONTEXT
                and tag.number == 1
                and not tag.is_opening
                and not tag.is_closing
            ):
                cov_increment = decode_real(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length

        return cls(
            monitored_property=monitored_property,
            cov_increment=cov_increment,
        ), offset


@dataclass(frozen=True, slots=True)
class COVSubscriptionSpecification:
    """A single subscription specification within SubscribeCOVPropertyMultiple.

    ::

        SEQUENCE {
            monitoredObjectIdentifier [0] BACnetObjectIdentifier,
            listOfCOVReferences       [1] SEQUENCE OF COVReference
        }
    """

    monitored_object_identifier: ObjectIdentifier
    list_of_cov_references: list[COVReference]

    def encode(self) -> bytes:
        """Encode COVSubscriptionSpecification.

        :returns: Encoded bytes for this subscription specification.
        """
        buf = bytearray()
        # [0] monitoredObjectIdentifier
        buf.extend(encode_context_object_id(0, self.monitored_object_identifier))
        # [1] listOfCOVReferences (constructed)
        buf.extend(encode_opening_tag(1))
        for ref in self.list_of_cov_references:
            buf.extend(ref.encode())
        buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(
        cls, data: memoryview | bytes, offset: int = 0
    ) -> tuple[COVSubscriptionSpecification, int]:
        """Decode COVSubscriptionSpecification from data at a given offset.

        :param data: Buffer to decode from.
        :param offset: Starting byte offset.
        :returns: Tuple of (decoded :class:`COVSubscriptionSpecification`, new offset).
        """
        data = as_memoryview(data)

        # [0] monitoredObjectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        monitored_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] listOfCOVReferences -- opening tag 1
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 1

        list_of_cov_references: list[COVReference] = []
        while offset < len(data):
            # Check for closing tag 1
            tag, new_offset = decode_tag(data, offset)
            if tag.is_closing and tag.number == 1:
                offset = new_offset
                break
            ref, offset = COVReference.decode(data, offset)
            list_of_cov_references.append(ref)

        return cls(
            monitored_object_identifier=monitored_object_identifier,
            list_of_cov_references=list_of_cov_references,
        ), offset


@dataclass(frozen=True, slots=True)
class SubscribeCOVPropertyMultipleRequest:
    """SubscribeCOVPropertyMultiple-Request service parameters (Clause 13.16.1).

    ::

        SubscribeCOVPropertyMultiple-Request ::= SEQUENCE {
            subscriberProcessIdentifier        [0] Unsigned32,
            issueConfirmedNotifications         [1] BOOLEAN OPTIONAL,
            lifetime                            [2] Unsigned OPTIONAL,
            maxNotificationDelay                [3] Unsigned OPTIONAL,
            listOfCOVSubscriptionSpecifications [4] SEQUENCE OF ...
        }
    """

    subscriber_process_identifier: int
    list_of_cov_subscription_specifications: list[COVSubscriptionSpecification]
    issue_confirmed_notifications: bool | None = None
    lifetime: int | None = None
    max_notification_delay: int | None = None

    def encode(self) -> bytes:
        """Encode SubscribeCOVPropertyMultiple-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] subscriberProcessIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.subscriber_process_identifier)))
        # [1] issueConfirmedNotifications (optional)
        if self.issue_confirmed_notifications is not None:
            buf.extend(
                encode_context_tagged(1, encode_boolean(self.issue_confirmed_notifications))
            )
        # [2] lifetime (optional)
        if self.lifetime is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.lifetime)))
        # [3] maxNotificationDelay (optional)
        if self.max_notification_delay is not None:
            buf.extend(encode_context_tagged(3, encode_unsigned(self.max_notification_delay)))
        # [4] listOfCOVSubscriptionSpecifications (constructed)
        buf.extend(encode_opening_tag(4))
        for spec in self.list_of_cov_subscription_specifications:
            buf.extend(spec.encode())
        buf.extend(encode_closing_tag(4))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> SubscribeCOVPropertyMultipleRequest:
        """Decode SubscribeCOVPropertyMultiple-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`SubscribeCOVPropertyMultipleRequest`.
        """
        data = as_memoryview(data)

        offset = 0

        # [0] subscriberProcessIdentifier
        tag, offset = decode_tag(data, offset)
        subscriber_process_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] issueConfirmedNotifications (optional)
        issue_confirmed_notifications, offset = decode_optional_context(
            data, offset, 1, decode_boolean
        )

        # [2] lifetime (optional)
        lifetime, offset = decode_optional_context(data, offset, 2, decode_unsigned)

        # [3] maxNotificationDelay (optional)
        max_notification_delay, offset = decode_optional_context(data, offset, 3, decode_unsigned)

        # [4] listOfCOVSubscriptionSpecifications -- opening tag 4
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 4

        specs: list[COVSubscriptionSpecification] = []
        while offset < len(data):
            # Check for closing tag 4
            tag, new_offset = decode_tag(data, offset)
            if tag.is_closing and tag.number == 4:
                offset = new_offset
                break
            spec, offset = COVSubscriptionSpecification.decode(data, offset)
            specs.append(spec)

        return cls(
            subscriber_process_identifier=subscriber_process_identifier,
            issue_confirmed_notifications=issue_confirmed_notifications,
            lifetime=lifetime,
            max_notification_delay=max_notification_delay,
            list_of_cov_subscription_specifications=specs,
        )


@dataclass(frozen=True, slots=True)
class COVPropertyValue:
    """A single property value within a COV notification.

    ::

        SEQUENCE {
            propertyIdentifier  [0] BACnetPropertyIdentifier,
            arrayIndex          [1] Unsigned OPTIONAL,
            value               [2] ABSTRACT-SYNTAX.&Type,
            timeOfChange        [3] BACnetTimeStamp OPTIONAL
        }
    """

    property_identifier: int
    value: bytes
    array_index: int | None = None
    time_of_change: BACnetTimeStamp | None = None

    def encode(self) -> bytes:
        """Encode COVPropertyValue.

        :returns: Encoded bytes for this property value.
        """
        buf = bytearray()
        # [0] propertyIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.property_identifier)))
        # [1] arrayIndex (optional)
        if self.array_index is not None:
            buf.extend(encode_context_tagged(1, encode_unsigned(self.array_index)))
        # [2] value (opening/closing tag with raw application-tagged content)
        buf.extend(encode_opening_tag(2))
        buf.extend(self.value)
        buf.extend(encode_closing_tag(2))
        # [3] timeOfChange (optional, constructed)
        if self.time_of_change is not None:
            buf.extend(encode_opening_tag(3))
            buf.extend(self.time_of_change.encode())
            buf.extend(encode_closing_tag(3))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int = 0) -> tuple[COVPropertyValue, int]:
        """Decode COVPropertyValue from data at a given offset.

        :param data: Buffer to decode from.
        :param offset: Starting byte offset.
        :returns: Tuple of (decoded :class:`COVPropertyValue`, new offset).
        """
        data = as_memoryview(data)

        # [0] propertyIdentifier
        tag, offset = decode_tag(data, offset)
        property_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] arrayIndex (optional)
        array_index: int | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if (
                tag.cls == TagClass.CONTEXT
                and tag.number == 1
                and not tag.is_opening
                and not tag.is_closing
            ):
                array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length

        # [2] value -- opening tag 2, collect raw bytes until closing tag 2
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 2
        value_start = offset
        depth = 1
        while depth > 0 and offset < len(data):
            inner_tag, inner_offset = decode_tag(data, offset)
            if inner_tag.is_opening:
                depth += 1
                offset = inner_offset
            elif inner_tag.is_closing:
                depth -= 1
                if depth == 0:
                    value_bytes = bytes(data[value_start:offset])
                    offset = inner_offset
                    break
                offset = inner_offset
            else:
                offset = inner_offset + inner_tag.length
        else:
            value_bytes = bytes(data[value_start:offset])

        # [3] timeOfChange (optional, constructed)
        time_of_change: BACnetTimeStamp | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.is_opening and tag.number == 3:
                time_of_change, offset = BACnetTimeStamp.decode(data, new_offset)
                # consume closing tag 3
                tag, offset = decode_tag(data, offset)

        return cls(
            property_identifier=property_identifier,
            value=value_bytes,
            array_index=array_index,
            time_of_change=time_of_change,
        ), offset


@dataclass(frozen=True, slots=True)
class COVObjectNotification:
    """A single object notification within COVNotificationMultiple.

    ::

        SEQUENCE {
            monitoredObjectIdentifier [0] BACnetObjectIdentifier,
            listOfValues              [1] SEQUENCE OF COVPropertyValue
        }
    """

    monitored_object_identifier: ObjectIdentifier
    list_of_values: list[COVPropertyValue]

    def encode(self) -> bytes:
        """Encode COVObjectNotification.

        :returns: Encoded bytes for this object notification.
        """
        buf = bytearray()
        # [0] monitoredObjectIdentifier
        buf.extend(encode_context_object_id(0, self.monitored_object_identifier))
        # [1] listOfValues (constructed)
        buf.extend(encode_opening_tag(1))
        for pv in self.list_of_values:
            buf.extend(pv.encode())
        buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(
        cls, data: memoryview | bytes, offset: int = 0
    ) -> tuple[COVObjectNotification, int]:
        """Decode COVObjectNotification from data at a given offset.

        :param data: Buffer to decode from.
        :param offset: Starting byte offset.
        :returns: Tuple of (decoded :class:`COVObjectNotification`, new offset).
        """
        data = as_memoryview(data)

        # [0] monitoredObjectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        monitored_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] listOfValues -- opening tag 1
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 1

        list_of_values: list[COVPropertyValue] = []
        while offset < len(data):
            # Check for closing tag 1
            tag, new_offset = decode_tag(data, offset)
            if tag.is_closing and tag.number == 1:
                offset = new_offset
                break
            pv, offset = COVPropertyValue.decode(data, offset)
            list_of_values.append(pv)

        return cls(
            monitored_object_identifier=monitored_object_identifier,
            list_of_values=list_of_values,
        ), offset


@dataclass(frozen=True, slots=True)
class COVNotificationMultipleRequest:
    """Confirmed/Unconfirmed COVNotification-Multiple-Request per Clause 13.17/13.18.

    ::

        COVNotification-Multiple-Request ::= SEQUENCE {
            subscriberProcessIdentifier  [0] Unsigned32,
            initiatingDeviceIdentifier   [1] BACnetObjectIdentifier,
            timeRemaining                [2] Unsigned,
            timestamp                    [3] BACnetTimeStamp,
            listOfCOVNotifications       [4] SEQUENCE OF COVObjectNotification
        }
    """

    subscriber_process_identifier: int
    initiating_device_identifier: ObjectIdentifier
    time_remaining: int
    timestamp: BACnetTimeStamp
    list_of_cov_notifications: list[COVObjectNotification]

    def encode(self) -> bytes:
        """Encode COVNotificationMultiple-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] subscriberProcessIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.subscriber_process_identifier)))
        # [1] initiatingDeviceIdentifier
        buf.extend(encode_context_object_id(1, self.initiating_device_identifier))
        # [2] timeRemaining
        buf.extend(encode_context_tagged(2, encode_unsigned(self.time_remaining)))
        # [3] timestamp (constructed)
        buf.extend(encode_opening_tag(3))
        buf.extend(self.timestamp.encode())
        buf.extend(encode_closing_tag(3))
        # [4] listOfCOVNotifications (constructed)
        buf.extend(encode_opening_tag(4))
        for notification in self.list_of_cov_notifications:
            buf.extend(notification.encode())
        buf.extend(encode_closing_tag(4))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> COVNotificationMultipleRequest:
        """Decode COVNotificationMultiple-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`COVNotificationMultipleRequest`.
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

        # [2] timeRemaining
        tag, offset = decode_tag(data, offset)
        time_remaining = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [3] timestamp (constructed -- opening/closing tag 3)
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 3
        timestamp, offset = BACnetTimeStamp.decode(data, offset)
        # consume closing tag 3
        tag, offset = decode_tag(data, offset)

        # [4] listOfCOVNotifications -- opening tag 4
        tag, offset = decode_tag(data, offset)
        # tag should be opening tag 4

        list_of_cov_notifications: list[COVObjectNotification] = []
        while offset < len(data):
            # Check for closing tag 4
            tag, new_offset = decode_tag(data, offset)
            if tag.is_closing and tag.number == 4:
                offset = new_offset
                break
            notification, offset = COVObjectNotification.decode(data, offset)
            list_of_cov_notifications.append(notification)

        return cls(
            subscriber_process_identifier=subscriber_process_identifier,
            initiating_device_identifier=initiating_device_identifier,
            time_remaining=time_remaining,
            timestamp=timestamp,
            list_of_cov_notifications=list_of_cov_notifications,
        )
