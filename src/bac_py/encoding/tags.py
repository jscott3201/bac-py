"""BACnet tag encoding and decoding per ASHRAE 135-2016 Clause 20.2.1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class TagClass(IntEnum):
    """Tag class: application or context-specific."""

    APPLICATION = 0
    CONTEXT = 1


@dataclass(frozen=True, slots=True)
class Tag:
    """Decoded BACnet tag."""

    number: int
    cls: TagClass
    length: int
    is_opening: bool = False
    is_closing: bool = False


def encode_tag(tag_number: int, cls: TagClass, length: int) -> bytes:
    """Encode a tag header.

    Args:
        tag_number: Tag number (0-254).
        cls: Tag class (APPLICATION or CONTEXT).
        length: Data length in bytes.

    Returns:
        Encoded tag header bytes.
    """
    buf = bytearray()

    # Initial tag octet
    initial = ((tag_number << 4) | (cls << 3)) if tag_number <= 14 else ((0x0F << 4) | (cls << 3))

    if length <= 4:
        initial |= length
        buf.append(initial)
    else:
        initial |= 5  # Extended length marker
        buf.append(initial)

    # Extended tag number
    if tag_number > 14:
        buf.append(tag_number)

    # Extended length
    if length > 4:
        if length <= 253:
            buf.append(length)
        elif length <= 65535:
            buf.append(254)
            buf.extend(length.to_bytes(2, "big"))
        else:
            buf.append(255)
            buf.extend(length.to_bytes(4, "big"))

    return bytes(buf)


def encode_opening_tag(tag_number: int) -> bytes:
    """Encode a context-specific opening tag.

    Args:
        tag_number: Context tag number.

    Returns:
        Encoded opening tag bytes.
    """
    if tag_number <= 14:
        return bytes([(tag_number << 4) | 0x0E])
    return bytes([0xFE, tag_number])


def encode_closing_tag(tag_number: int) -> bytes:
    """Encode a context-specific closing tag.

    Args:
        tag_number: Context tag number.

    Returns:
        Encoded closing tag bytes.
    """
    if tag_number <= 14:
        return bytes([(tag_number << 4) | 0x0F])
    return bytes([0xFF, tag_number])


def decode_tag(buf: memoryview | bytes, offset: int) -> tuple[Tag, int]:
    """Decode a tag from buffer, return (tag, new_offset).

    Args:
        buf: Buffer to decode from.
        offset: Starting offset in buffer.

    Returns:
        Tuple of (decoded Tag, new offset after tag header).
    """
    if isinstance(buf, bytes):
        buf = memoryview(buf)

    initial = buf[offset]
    offset += 1

    # Extract fields from initial octet
    tag_number = (initial >> 4) & 0x0F
    cls = TagClass((initial >> 3) & 0x01)
    lvt = initial & 0x07

    # Extended tag number
    if tag_number == 0x0F:
        tag_number = buf[offset]
        offset += 1

    # Check for opening/closing tags (context class only)
    if cls == TagClass.CONTEXT and lvt == 6:
        return Tag(number=tag_number, cls=cls, length=0, is_opening=True), offset
    if cls == TagClass.CONTEXT and lvt == 7:
        return Tag(number=tag_number, cls=cls, length=0, is_closing=True), offset

    # Data length
    if lvt < 5:
        length = lvt
    else:
        # Extended length
        ext = buf[offset]
        offset += 1
        if ext <= 253:
            length = ext
        elif ext == 254:
            length = int.from_bytes(buf[offset : offset + 2], "big")
            offset += 2
        else:  # ext == 255
            length = int.from_bytes(buf[offset : offset + 4], "big")
            offset += 4

    return Tag(number=tag_number, cls=cls, length=length), offset


def extract_context_value(
    data: memoryview | bytes,
    offset: int,
    tag_number: int,
) -> tuple[bytes, int]:
    """Extract raw bytes enclosed by a context opening/closing tag pair.

    Reads from ``offset`` (which should point just past the opening tag)
    through the matching closing tag, handling nested opening/closing tags.

    Args:
        data: Buffer to read from.
        offset: Position immediately after the opening tag.
        tag_number: The context tag number of the enclosing pair.

    Returns:
        Tuple of (enclosed raw bytes, offset past the closing tag).
    """
    if isinstance(data, bytes):
        data = memoryview(data)
    value_start = offset
    depth = 1
    while depth > 0 and offset < len(data):
        t, new_offset = decode_tag(data, offset)
        if t.is_opening:
            depth += 1
            offset = new_offset
        elif t.is_closing:
            depth -= 1
            if depth == 0:
                value_end = offset
                return bytes(data[value_start:value_end]), new_offset
            offset = new_offset
        else:
            offset = new_offset + t.length
    msg = f"Missing closing tag {tag_number}"
    raise ValueError(msg)
