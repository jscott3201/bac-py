"""Who-Has and I-Have services per ASHRAE 135-2016 Clause 16.9."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_object_identifier,
    decode_unsigned,
    encode_application_character_string,
    encode_application_object_id,
    encode_character_string,
    encode_context_object_id,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import TagClass, as_memoryview, decode_tag
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class WhoHasRequest:
    """Who-Has-Request service parameters (Clause 16.9.1).

    ::

        Who-Has-Request ::= SEQUENCE {
            limits   SEQUENCE {
                deviceInstanceRangeLowLimit   [0] Unsigned (0..4194303),
                deviceInstanceRangeHighLimit  [1] Unsigned (0..4194303)
            } OPTIONAL,
            object   CHOICE {
                objectIdentifier  [2] BACnetObjectIdentifier,
                objectName        [3] CharacterString
            }
        }
    """

    object_identifier: ObjectIdentifier | None = None
    object_name: str | None = None
    low_limit: int | None = None
    high_limit: int | None = None

    def __post_init__(self) -> None:
        both_set = self.object_identifier is not None and self.object_name is not None
        neither_set = self.object_identifier is None and self.object_name is None
        if both_set or neither_set:
            msg = "Exactly one of object_identifier or object_name must be set"
            raise ValueError(msg)

    def encode(self) -> bytes:
        """Encode WhoHasRequest to bytes."""
        buf = bytearray()
        # Optional limits
        if self.low_limit is not None and self.high_limit is not None:
            buf.extend(encode_context_tagged(0, encode_unsigned(self.low_limit)))
            buf.extend(encode_context_tagged(1, encode_unsigned(self.high_limit)))
        # CHOICE: objectIdentifier [2] or objectName [3]
        if self.object_identifier is not None:
            buf.extend(encode_context_object_id(2, self.object_identifier))
        elif self.object_name is not None:
            buf.extend(encode_context_tagged(3, encode_character_string(self.object_name)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> WhoHasRequest:
        """Decode WhoHasRequest from bytes."""
        data = as_memoryview(data)

        offset = 0
        low_limit = None
        high_limit = None
        object_identifier = None
        object_name = None

        # Check for optional limits [0] and [1]
        tag, new_offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 0:
            low_limit = decode_unsigned(data[new_offset : new_offset + tag.length])
            offset = new_offset + tag.length
            tag, new_offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 1:
                high_limit = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
                tag, new_offset = decode_tag(data, offset)

        # CHOICE: objectIdentifier [2] or objectName [3]
        if tag.cls == TagClass.CONTEXT and tag.number == 2:
            obj_type, instance = decode_object_identifier(
                data[new_offset : new_offset + tag.length]
            )
            object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
        elif tag.cls == TagClass.CONTEXT and tag.number == 3:
            object_name = decode_character_string(data[new_offset : new_offset + tag.length])

        return cls(
            object_identifier=object_identifier,
            object_name=object_name,
            low_limit=low_limit,
            high_limit=high_limit,
        )


@dataclass(frozen=True, slots=True)
class IHaveRequest:
    """I-Have-Request service parameters (Clause 16.9.2).

    All fields use APPLICATION tags (not context-specific).

    ::

        I-Have-Request ::= SEQUENCE {
            deviceIdentifier  BACnetObjectIdentifier,
            objectIdentifier  BACnetObjectIdentifier,
            objectName        CharacterString
        }
    """

    device_identifier: ObjectIdentifier
    object_identifier: ObjectIdentifier
    object_name: str

    def encode(self) -> bytes:
        """Encode IHaveRequest to bytes."""
        buf = bytearray()
        buf.extend(
            encode_application_object_id(
                self.device_identifier.object_type,
                self.device_identifier.instance_number,
            )
        )
        buf.extend(
            encode_application_object_id(
                self.object_identifier.object_type,
                self.object_identifier.instance_number,
            )
        )
        buf.extend(encode_application_character_string(self.object_name))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> IHaveRequest:
        """Decode IHaveRequest from bytes."""
        data = as_memoryview(data)

        offset = 0

        # deviceIdentifier (APPLICATION tag 12)
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # objectIdentifier (APPLICATION tag 12)
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # objectName (APPLICATION tag 7)
        tag, offset = decode_tag(data, offset)
        object_name = decode_character_string(data[offset : offset + tag.length])

        return cls(
            device_identifier=device_identifier,
            object_identifier=object_identifier,
            object_name=object_name,
        )
