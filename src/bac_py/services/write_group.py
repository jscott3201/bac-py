"""WriteGroup service per ASHRAE 135-2020 Clause 15.11.

WriteGroup is an unconfirmed service for writing channel values
via group addressing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

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


@dataclass(frozen=True, slots=True)
class GroupChannelValue:
    """A single channel value in a WriteGroup change list.

    ::

        GroupChannelValue ::= SEQUENCE {
            channel             [0] Unsigned16,
            overridingPriority  [1] Unsigned (1..16) OPTIONAL,
            value               ABSTRACT-SYNTAX.&TYPE
        }
    """

    channel: int
    value: bytes
    overriding_priority: int | None = None

    def encode(self) -> bytes:
        """Encode a single GroupChannelValue."""
        buf = bytearray()
        # [0] channel
        buf.extend(encode_context_tagged(0, encode_unsigned(self.channel)))
        # [1] overridingPriority (optional)
        if self.overriding_priority is not None:
            buf.extend(encode_context_tagged(1, encode_unsigned(self.overriding_priority)))
        # value (opening/closing tag 2)
        buf.extend(encode_opening_tag(2))
        buf.extend(self.value)
        buf.extend(encode_closing_tag(2))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview, offset: int) -> tuple[GroupChannelValue, int]:
        """Decode a single GroupChannelValue starting at offset.

        :returns: Tuple of (decoded value, new offset).
        """
        # [0] channel
        tag, offset = decode_tag(data, offset)
        channel = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] overridingPriority (optional)
        overriding_priority = None
        tag, new_offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 1 and not tag.is_opening:
            overriding_priority = decode_unsigned(data[new_offset : new_offset + tag.length])
            offset = new_offset + tag.length
            tag, new_offset = decode_tag(data, offset)

        # value (opening/closing tag 2)
        value, offset = extract_context_value(data, new_offset, 2)

        return cls(channel=channel, value=value, overriding_priority=overriding_priority), offset


@dataclass(frozen=True, slots=True)
class WriteGroupRequest:
    """WriteGroup-Request (Clause 15.11.1).

    ::

        WriteGroup-Request ::= SEQUENCE {
            groupNumber    [0] Unsigned32,
            writePriority  [1] Unsigned (1..16),
            changeList     [2] SEQUENCE OF GroupChannelValue
        }
    """

    group_number: int
    write_priority: int
    change_list: list[GroupChannelValue]

    def encode(self) -> bytes:
        """Encode WriteGroup-Request service parameters."""
        buf = bytearray()
        # [0] groupNumber
        buf.extend(encode_context_tagged(0, encode_unsigned(self.group_number)))
        # [1] writePriority
        buf.extend(encode_context_tagged(1, encode_unsigned(self.write_priority)))
        # [2] changeList (opening/closing)
        buf.extend(encode_opening_tag(2))
        for gcv in self.change_list:
            buf.extend(gcv.encode())
        buf.extend(encode_closing_tag(2))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode WriteGroup-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        # [0] groupNumber
        tag, offset = decode_tag(data, offset)
        group_number = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] writePriority
        tag, offset = decode_tag(data, offset)
        write_priority = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [2] changeList (opening/closing tag 2)
        tag, offset = decode_tag(data, offset)  # opening tag 2
        change_list: list[GroupChannelValue] = []
        while offset < len(data):
            tag, _ = decode_tag(data, offset)
            if tag.is_closing and tag.number == 2:
                break
            gcv, offset = GroupChannelValue.decode(data, offset)
            change_list.append(gcv)

        return cls(
            group_number=group_number,
            write_priority=write_priority,
            change_list=change_list,
        )
