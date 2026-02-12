"""Text message services per ASHRAE 135-2020 Clause 16.5-16.6.

ConfirmedTextMessage (Clause 16.5), UnconfirmedTextMessage (Clause 16.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_object_identifier,
    decode_unsigned,
    encode_character_string,
    encode_context_object_id,
    encode_context_tagged,
    encode_enumerated,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
)
from bac_py.types.enums import MessagePriority, ObjectType
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class ConfirmedTextMessageRequest:
    """ConfirmedTextMessage-Request (Clause 16.5.1).

    ::

        ConfirmedTextMessage-Request ::= SEQUENCE {
            textMessageSourceDevice  [0] BACnetObjectIdentifier,
            messageClass             [1] CHOICE {
                numeric    [0] Unsigned,
                character  [1] CharacterString
            } OPTIONAL,
            messagePriority          [2] ENUMERATED { normal(0), urgent(1) },
            message                  [3] CharacterString
        }
    """

    text_message_source_device: ObjectIdentifier
    message_priority: MessagePriority
    message: str
    message_class_numeric: int | None = None
    message_class_character: str | None = None

    def encode(self) -> bytes:
        """Encode ConfirmedTextMessage-Request service parameters."""
        buf = bytearray()
        # [0] textMessageSourceDevice
        buf.extend(encode_context_object_id(0, self.text_message_source_device))
        # [1] messageClass (optional, constructed)
        if self.message_class_numeric is not None:
            buf.extend(encode_opening_tag(1))
            buf.extend(encode_context_tagged(0, encode_unsigned(self.message_class_numeric)))
            buf.extend(encode_closing_tag(1))
        elif self.message_class_character is not None:
            buf.extend(encode_opening_tag(1))
            buf.extend(
                encode_context_tagged(1, encode_character_string(self.message_class_character))
            )
            buf.extend(encode_closing_tag(1))
        # [2] messagePriority
        buf.extend(encode_context_tagged(2, encode_enumerated(self.message_priority)))
        # [3] message
        buf.extend(encode_context_tagged(3, encode_character_string(self.message)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode ConfirmedTextMessage-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        # [0] textMessageSourceDevice
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        source_device = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] messageClass (optional, constructed)
        message_class_numeric = None
        message_class_character = None
        tag, new_offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 1 and tag.is_opening:
            # Read the CHOICE inside
            tag, new_offset = decode_tag(data, new_offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 0:
                message_class_numeric = decode_unsigned(data[new_offset : new_offset + tag.length])
            elif tag.cls == TagClass.CONTEXT and tag.number == 1:
                message_class_character = decode_character_string(
                    data[new_offset : new_offset + tag.length]
                )
            offset = new_offset + tag.length
            # Skip closing tag [1]
            _closing, offset = decode_tag(data, offset)
            tag, new_offset = decode_tag(data, offset)

        # [2] messagePriority
        message_priority = MessagePriority(
            decode_unsigned(data[new_offset : new_offset + tag.length])
        )
        offset = new_offset + tag.length

        # [3] message
        tag, offset = decode_tag(data, offset)
        message = decode_character_string(data[offset : offset + tag.length])

        return cls(
            text_message_source_device=source_device,
            message_priority=message_priority,
            message=message,
            message_class_numeric=message_class_numeric,
            message_class_character=message_class_character,
        )


@dataclass(frozen=True, slots=True)
class UnconfirmedTextMessageRequest(ConfirmedTextMessageRequest):
    """UnconfirmedTextMessage-Request (Clause 16.6.1).

    Same structure as ConfirmedTextMessage-Request.
    """
