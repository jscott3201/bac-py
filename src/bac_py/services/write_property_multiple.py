"""WritePropertyMultiple service per ASHRAE 135-2016 Clause 15.10."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    encode_context_object_id,
)
from bac_py.encoding.tags import as_memoryview, decode_tag, encode_closing_tag, encode_opening_tag
from bac_py.services.common import BACnetPropertyValue
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


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
    list_of_properties: list[BACnetPropertyValue]

    def encode(self) -> bytes:
        """Encode write access specification."""
        buf = bytearray()
        # [0] object-identifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
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
        data = as_memoryview(data)

        # [0] object-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] opening tag
        _opening, offset = decode_tag(data, offset)

        # Decode property values until closing tag 1
        props: list[BACnetPropertyValue] = []
        while offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if tag_peek.is_closing and tag_peek.number == 1:
                offset = next_offset
                break
            pv, offset = BACnetPropertyValue.decode_from(data, offset)
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
        data = as_memoryview(data)

        offset = 0
        specs: list[WriteAccessSpecification] = []
        while offset < len(data):
            spec, offset = WriteAccessSpecification.decode(data, offset)
            specs.append(spec)

        return cls(list_of_write_access_specs=specs)
