"""WritePropertyMultiple service per ASHRAE 135-2016 Clause 15.10."""

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
class PropertyValue:
    """BACnetPropertyValue (Clause 21).

    ::

        BACnetPropertyValue ::= SEQUENCE {
            propertyIdentifier  [0] BACnetPropertyIdentifier,
            propertyArrayIndex  [1] Unsigned OPTIONAL,
            propertyValue       [2] ABSTRACT-SYNTAX.&TYPE,
            priority            [3] Unsigned (1..16) OPTIONAL
        }
    """

    property_identifier: PropertyIdentifier
    property_value: bytes
    property_array_index: int | None = None
    priority: int | None = None

    def encode(self) -> bytes:
        """Encode property value."""
        buf = bytearray()
        # [0] property-identifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.property_identifier)))
        # [1] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(1, encode_unsigned(self.property_array_index)))
        # [2] property-value (opening/closing)
        buf.extend(encode_opening_tag(2))
        buf.extend(self.property_value)
        buf.extend(encode_closing_tag(2))
        # [3] priority (optional)
        if self.priority is not None:
            buf.extend(encode_context_tagged(3, encode_unsigned(self.priority)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int) -> tuple[PropertyValue, int]:
        """Decode property value from buffer at offset.

        Returns:
            Tuple of (PropertyValue, new offset).
        """
        if isinstance(data, bytes):
            data = memoryview(data)

        # [0] property-identifier
        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [1] property-array-index (optional)
        property_array_index = None
        tag_peek, next_offset = decode_tag(data, offset)
        if (
            tag_peek.cls == TagClass.CONTEXT
            and tag_peek.number == 1
            and not tag_peek.is_opening
            and not tag_peek.is_closing
        ):
            property_array_index = decode_unsigned(
                data[next_offset : next_offset + tag_peek.length]
            )
            offset = next_offset + tag_peek.length
            tag_peek, next_offset = decode_tag(data, offset)

        # [2] property-value (opening tag 2 ... closing tag 2)
        # tag_peek should be opening tag 2
        offset = next_offset
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
        closing_tag_len = 1 if tag_peek.number <= 14 else 2
        value_end = offset - closing_tag_len
        property_value = bytes(data[value_start:value_end])

        # [3] priority (optional)
        priority = None
        if offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if (
                tag_peek.cls == TagClass.CONTEXT
                and tag_peek.number == 3
                and not tag_peek.is_opening
                and not tag_peek.is_closing
            ):
                priority = decode_unsigned(data[next_offset : next_offset + tag_peek.length])
                offset = next_offset + tag_peek.length

        return cls(
            property_identifier=property_identifier,
            property_value=property_value,
            property_array_index=property_array_index,
            priority=priority,
        ), offset


@dataclass(frozen=True, slots=True)
class WriteAccessSpecification:
    """BACnetWriteAccessSpecification (Clause 21).

    ::

        WriteAccessSpecification ::= SEQUENCE {
            objectIdentifier  [0] BACnetObjectIdentifier,
            listOfProperties  [1] SEQUENCE OF BACnetPropertyValue
        }
    """

    object_identifier: ObjectIdentifier
    list_of_properties: list[PropertyValue]

    def encode(self) -> bytes:
        """Encode write access specification."""
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
        # [1] SEQUENCE OF BACnetPropertyValue
        buf.extend(encode_opening_tag(1))
        for pv in self.list_of_properties:
            buf.extend(pv.encode())
        buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int) -> tuple[WriteAccessSpecification, int]:
        """Decode write access specification from buffer at offset.

        Returns:
            Tuple of (WriteAccessSpecification, new offset).
        """
        if isinstance(data, bytes):
            data = memoryview(data)

        # [0] object-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] opening tag
        _opening, offset = decode_tag(data, offset)

        # Decode property values until closing tag 1
        props: list[PropertyValue] = []
        while offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if tag_peek.is_closing and tag_peek.number == 1:
                offset = next_offset
                break
            pv, offset = PropertyValue.decode(data, offset)
            props.append(pv)

        return cls(
            object_identifier=object_identifier,
            list_of_properties=props,
        ), offset


@dataclass(frozen=True, slots=True)
class WritePropertyMultipleRequest:
    """WritePropertyMultiple-Request service parameters (Clause 15.10.1.1).

    ::

        WritePropertyMultiple-Request ::= SEQUENCE {
            listOfWriteAccessSpecs  SEQUENCE OF WriteAccessSpecification
        }
    """

    list_of_write_access_specs: list[WriteAccessSpecification]

    def encode(self) -> bytes:
        """Encode WritePropertyMultiple-Request service parameters."""
        buf = bytearray()
        for spec in self.list_of_write_access_specs:
            buf.extend(spec.encode())
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> WritePropertyMultipleRequest:
        """Decode WritePropertyMultiple-Request from service request bytes."""
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0
        specs: list[WriteAccessSpecification] = []
        while offset < len(data):
            spec, offset = WriteAccessSpecification.decode(data, offset)
            specs.append(spec)

        return cls(list_of_write_access_specs=specs)
