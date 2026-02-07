"""ReadProperty service per ASHRAE 135-2016 Clause 15.5."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_unsigned,
    encode_context_tagged,
    encode_object_identifier,
    encode_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag, encode_closing_tag, encode_opening_tag
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class ReadPropertyRequest:
    """ReadProperty-Request service parameters (Clause 15.5.1.1).

    ::

        ReadProperty-Request ::= SEQUENCE {
            objectIdentifier    [0] BACnetObjectIdentifier,
            propertyIdentifier  [1] BACnetPropertyIdentifier,
            propertyArrayIndex  [2] Unsigned OPTIONAL
        }
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    property_array_index: int | None = None

    def encode(self) -> bytes:
        """Encode ReadProperty-Request service parameters.

        Returns:
            Encoded service request bytes.
        """
        buf = bytearray()
        # [0] object-identifier
        buf.extend(
            encode_context_tagged(
                0,
                encode_object_identifier(
                    self.object_identifier.object_type,
                    self.object_identifier.instance_number,
                ),
            )
        )
        # [1] property-identifier
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        # [2] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReadPropertyRequest:
        """Decode ReadProperty-Request from service request bytes.

        Args:
            data: Raw service request bytes.

        Returns:
            Decoded ReadPropertyRequest.
        """
        if isinstance(data, bytes):
            data = memoryview(data)

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

        # [2] property-array-index (optional)
        property_array_index = None
        if offset < len(data):
            tag, offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 2:
                property_array_index = decode_unsigned(data[offset : offset + tag.length])

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=property_array_index,
        )


@dataclass(frozen=True, slots=True)
class ReadPropertyACK:
    """ReadProperty-ACK service parameters (Clause 15.5.1.2).

    ::

        ReadProperty-ACK ::= SEQUENCE {
            objectIdentifier    [0] BACnetObjectIdentifier,
            propertyIdentifier  [1] BACnetPropertyIdentifier,
            propertyArrayIndex  [2] Unsigned OPTIONAL,
            propertyValue       [3] ABSTRACT-SYNTAX.&TYPE
        }

    The property_value field contains raw encoded bytes wrapped
    in context tag 3 (opening/closing). The application layer is
    responsible for interpreting the value based on the property type.
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    property_array_index: int | None = None
    property_value: bytes = b""

    def encode(self) -> bytes:
        """Encode ReadProperty-ACK service parameters.

        Returns:
            Encoded service ACK bytes.
        """
        buf = bytearray()
        # [0] object-identifier
        buf.extend(
            encode_context_tagged(
                0,
                encode_object_identifier(
                    self.object_identifier.object_type,
                    self.object_identifier.instance_number,
                ),
            )
        )
        # [1] property-identifier
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        # [2] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        # [3] property-value (opening tag 3, data, closing tag 3)
        buf.extend(encode_opening_tag(3))
        buf.extend(self.property_value)
        buf.extend(encode_closing_tag(3))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReadPropertyACK:
        """Decode ReadProperty-ACK from service ACK bytes.

        Args:
            data: Raw service ACK bytes.

        Returns:
            Decoded ReadPropertyACK.
        """
        if isinstance(data, bytes):
            data = memoryview(data)

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
            # Now read opening tag 3
            tag, offset = decode_tag(data, offset)

        # At this point tag should be opening tag 3
        # Find matching closing tag 3 to extract property value
        value_start = offset
        depth = 1
        while depth > 0 and offset < len(data):
            t, offset = decode_tag(data, offset)
            if t.is_opening:
                depth += 1
            elif t.is_closing:
                depth -= 1
            else:
                offset += t.length

        # value_start to just before the closing tag
        # Re-parse to find exact end: closing tag is at offset - (1 or 2 bytes)
        # Simpler: the value is everything between opening and closing tag 3
        # Let's re-find the closing tag position
        value_end = offset
        # Step back over the closing tag (1 byte for tag num <=14, 2 for >14)
        closing_tag_len = 1 if tag.number <= 14 else 2
        value_end -= closing_tag_len

        property_value = bytes(data[value_start:value_end])

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=property_array_index,
            property_value=property_value,
        )
