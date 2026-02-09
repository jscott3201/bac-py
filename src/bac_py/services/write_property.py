"""WriteProperty service per ASHRAE 135-2016 Clause 15.9."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_unsigned,
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
    extract_context_value,
)
from bac_py.services.errors import BACnetRejectError
from bac_py.types.enums import ObjectType, PropertyIdentifier, RejectReason
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class WritePropertyRequest:
    """WriteProperty-Request service parameters (Clause 15.9.1.1).

    ::

        WriteProperty-Request ::= SEQUENCE {
            objectIdentifier    [0] BACnetObjectIdentifier,
            propertyIdentifier  [1] BACnetPropertyIdentifier,
            propertyArrayIndex  [2] Unsigned OPTIONAL,
            propertyValue       [3] ABSTRACT-SYNTAX.&TYPE,
            priority            [4] Unsigned (1..16) OPTIONAL
        }

    The property_value field contains raw application-tagged encoded bytes.
    The application layer is responsible for encoding the value
    appropriately for the target property type.
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    property_value: bytes
    property_array_index: int | None = None
    priority: int | None = None

    def encode(self) -> bytes:
        """Encode WriteProperty-Request service parameters.

        Returns:
            Encoded service request bytes.
        """
        buf = bytearray()
        # [0] object-identifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
        # [1] property-identifier
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        # [2] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        # [3] property-value (opening tag 3, data, closing tag 3)
        buf.extend(encode_opening_tag(3))
        buf.extend(self.property_value)
        buf.extend(encode_closing_tag(3))
        # [4] priority (optional)
        if self.priority is not None:
            buf.extend(encode_context_tagged(4, encode_unsigned(self.priority)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> WritePropertyRequest:
        """Decode WriteProperty-Request from service request bytes.

        Args:
            data: Raw service request bytes.

        Returns:
            Decoded WritePropertyRequest.
        """
        data = as_memoryview(data)

        offset = 0

        # [0] object-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] property-identifier
        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [2] property-array-index (optional) or [3] opening tag
        property_array_index = None
        tag, offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 2 and not tag.is_opening:
            property_array_index = decode_unsigned(data[offset : offset + tag.length])
            offset += tag.length
            tag, offset = decode_tag(data, offset)

        # [3] property-value: opening tag 3 ... closing tag 3
        property_value, offset = extract_context_value(data, offset, 3)

        # [4] priority (optional, 1-16 per Clause 15.9.1.1.5)
        priority, offset = decode_optional_context(data, offset, 4, decode_unsigned)
        if priority is not None and not (1 <= priority <= 16):
            raise BACnetRejectError(RejectReason.PARAMETER_OUT_OF_RANGE)

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_value=property_value,
            property_array_index=property_array_index,
            priority=priority,
        )
