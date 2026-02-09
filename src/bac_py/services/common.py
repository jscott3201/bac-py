"""Shared BACnet service data types per ASHRAE 135-2016 Clause 21."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_unsigned,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    extract_context_value,
)
from bac_py.types.enums import PropertyIdentifier


@dataclass(frozen=True, slots=True)
class BACnetPropertyValue:
    """BACnetPropertyValue per Clause 21.

    ::

        BACnetPropertyValue ::= SEQUENCE {
            propertyIdentifier  [0] BACnetPropertyIdentifier,
            propertyArrayIndex  [1] Unsigned OPTIONAL,
            value               [2] ABSTRACT-SYNTAX.&Type,
            priority            [3] Unsigned (1..16) OPTIONAL
        }

    The ``value`` field contains raw application-tagged bytes.
    """

    property_identifier: PropertyIdentifier
    property_array_index: int | None = None
    value: bytes = b""
    priority: int | None = None

    def encode(self) -> bytes:
        """Encode BACnetPropertyValue.

        Returns:
            Encoded bytes.
        """
        buf = bytearray()
        # [0] propertyIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(self.property_identifier)))
        # [1] propertyArrayIndex (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(1, encode_unsigned(self.property_array_index)))
        # [2] value (opening/closing tag with raw application-tagged content)
        buf.extend(encode_opening_tag(2))
        buf.extend(self.value)
        buf.extend(encode_closing_tag(2))
        # [3] priority (optional)
        if self.priority is not None:
            buf.extend(encode_context_tagged(3, encode_unsigned(self.priority)))
        return bytes(buf)

    @classmethod
    def decode_from(
        cls, data: memoryview | bytes, offset: int = 0
    ) -> tuple[BACnetPropertyValue, int]:
        """Decode BACnetPropertyValue from data at given offset.

        Args:
            data: Raw bytes.
            offset: Start offset.

        Returns:
            Tuple of (decoded BACnetPropertyValue, new offset).
        """
        data = as_memoryview(data)

        # [0] propertyIdentifier
        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [1] propertyArrayIndex (optional)
        property_array_index = None
        tag, new_offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 1 and not tag.is_opening:
            property_array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
            offset = new_offset + tag.length
            tag, new_offset = decode_tag(data, offset)

        # [2] value — opening tag 2
        value, offset = extract_context_value(data, new_offset, 2)

        # [3] priority (optional)
        priority = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if (
                tag.cls == TagClass.CONTEXT
                and tag.number == 3
                and not tag.is_opening
                and not tag.is_closing
            ):
                priority = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length

        return (
            cls(
                property_identifier=property_identifier,
                property_array_index=property_array_index,
                value=value,
                priority=priority,
            ),
            offset,
        )
