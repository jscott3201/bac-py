"""List element services per ASHRAE 135-2016 Clause 15.1-15.2.

AddListElement (Clause 15.1), RemoveListElement (Clause 15.2).
"""

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
class AddListElementRequest:
    """AddListElement-Request (Clause 15.1.1.1).

    ::

        AddListElement-Request ::= SEQUENCE {
            objectIdentifier    [0] BACnetObjectIdentifier,
            propertyIdentifier  [1] BACnetPropertyIdentifier,
            propertyArrayIndex  [2] Unsigned OPTIONAL,
            listOfElements      [3] ABSTRACT-SYNTAX.&TYPE
        }

    The listOfElements field contains raw application-tagged bytes.
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    list_of_elements: bytes
    property_array_index: int | None = None

    def encode(self) -> bytes:
        buf = bytearray()
        # [0] objectIdentifier
        buf.extend(
            encode_context_tagged(
                0,
                encode_object_identifier(
                    self.object_identifier.object_type,
                    self.object_identifier.instance_number,
                ),
            )
        )
        # [1] propertyIdentifier
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        # [2] propertyArrayIndex (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        # [3] listOfElements (opening/closing)
        buf.extend(encode_opening_tag(3))
        buf.extend(self.list_of_elements)
        buf.extend(encode_closing_tag(3))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> AddListElementRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        # [0] objectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] propertyIdentifier
        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [2] propertyArrayIndex (optional)
        property_array_index = None
        tag, new_offset = decode_tag(data, offset)
        if (
            tag.cls == TagClass.CONTEXT
            and tag.number == 2
            and not tag.is_opening
            and not tag.is_closing
        ):
            property_array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
            offset = new_offset + tag.length
            tag, new_offset = decode_tag(data, offset)

        # [3] listOfElements (opening/closing tag 3)
        offset = new_offset
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
        closing_tag_len = 1 if 3 <= 14 else 2
        value_end = offset - closing_tag_len
        list_of_elements = bytes(data[value_start:value_end])

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            list_of_elements=list_of_elements,
            property_array_index=property_array_index,
        )


@dataclass(frozen=True, slots=True)
class RemoveListElementRequest:
    """RemoveListElement-Request (Clause 15.2.1.1).

    Same structure as AddListElement-Request.
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    list_of_elements: bytes
    property_array_index: int | None = None

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(
            encode_context_tagged(
                0,
                encode_object_identifier(
                    self.object_identifier.object_type,
                    self.object_identifier.instance_number,
                ),
            )
        )
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        buf.extend(encode_opening_tag(3))
        buf.extend(self.list_of_elements)
        buf.extend(encode_closing_tag(3))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> RemoveListElementRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        property_array_index = None
        tag, new_offset = decode_tag(data, offset)
        if (
            tag.cls == TagClass.CONTEXT
            and tag.number == 2
            and not tag.is_opening
            and not tag.is_closing
        ):
            property_array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
            offset = new_offset + tag.length
            tag, new_offset = decode_tag(data, offset)

        offset = new_offset
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
        closing_tag_len = 1 if 3 <= 14 else 2
        value_end = offset - closing_tag_len
        list_of_elements = bytes(data[value_start:value_end])

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            list_of_elements=list_of_elements,
            property_array_index=property_array_index,
        )
