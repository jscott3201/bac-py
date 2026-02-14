"""BACnet tag encoding and decoding per ASHRAE 135-2016 Clause 20.2.1."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class TagClass(IntEnum):
    """Tag class indicating application or context-specific encoding.

    BACnet uses two tag classes per Clause 20.2.1.1:

    - ``APPLICATION`` tags identify the datatype (Null, Boolean, etc.).
    - ``CONTEXT`` tags identify a field within a constructed type.
    """

    APPLICATION = 0
    CONTEXT = 1


@dataclass(frozen=True, slots=True)
class Tag:
    """A decoded BACnet tag header per Clause 20.2.1.

    Represents the tag number, class, data length, and opening/closing
    status extracted from the tag octets.
    """

    number: int
    """Tag number: datatype for application tags, field index for context tags."""

    cls: TagClass
    """Tag class (application or context-specific)."""

    length: int
    """Content length in bytes, or the raw L/V/T value for application booleans."""

    is_opening: bool = False
    """Whether this is a context-specific opening tag (L/V/T = 6)."""

    is_closing: bool = False
    """Whether this is a context-specific closing tag (L/V/T = 7)."""

    @property
    def is_boolean_true(self) -> bool:
        """Check if this is an APPLICATION boolean tag with value True.

        Per Clause 20.2.3, APPLICATION-tagged booleans encode the
        value in the tag's L/V/T field with no contents octets.
        The ``length`` field here stores the raw L/V/T value, so
        a nonzero value means True.
        """
        return self.cls == TagClass.APPLICATION and self.number == 1 and self.length != 0


def encode_tag(tag_number: int, cls: TagClass, length: int) -> bytes:
    """Encode a tag header per Clause 20.2.1.

    For APPLICATION class tags, the tag number identifies the datatype
    (0=Null, 1=Boolean, ..., 12=ObjectIdentifier).  For CONTEXT class
    tags, the tag number is a context-specific field identifier (0-254).

    :param tag_number: Tag number (0-254).
    :param cls: Tag class (APPLICATION or CONTEXT).
    :param length: Data length in bytes.
    :returns: Encoded tag header bytes.
    :raises ValueError: If *tag_number* or *length* is out of range.
    """
    if tag_number < 0 or tag_number > 254:
        msg = f"Tag number must be 0-254, got {tag_number}"
        logger.warning(msg)
        raise ValueError(msg)
    if length < 0:
        msg = f"Tag length must be non-negative, got {length}"
        logger.warning(msg)
        raise ValueError(msg)

    # Fast path: tag_number <= 14 and length <= 4 → single byte (most common case)
    if tag_number <= 14 and length <= 4:
        return bytes([(tag_number << 4) | (cls << 3) | length])

    # General case
    initial = ((tag_number << 4) | (cls << 3)) if tag_number <= 14 else ((0x0F << 4) | (cls << 3))

    if length <= 4:
        # tag_number > 14, length <= 4: two bytes
        return bytes([initial | length, tag_number])

    # Extended length
    initial |= 5  # Extended length marker
    if tag_number <= 14:
        if length <= 253:
            return bytes([initial, length])
        if length <= 65535:
            return bytes([initial, 254]) + length.to_bytes(2, "big")
        return bytes([initial, 255]) + length.to_bytes(4, "big")

    # tag_number > 14 and length > 4
    if length <= 253:
        return bytes([initial, tag_number, length])
    if length <= 65535:
        return bytes([initial, tag_number, 254]) + length.to_bytes(2, "big")
    return bytes([initial, tag_number, 255]) + length.to_bytes(4, "big")


# Pre-computed opening/closing tags for tag numbers 0-14 (the common case).
# Avoids bytes([...]) allocation on every call.
_OPENING_TAGS: tuple[bytes, ...] = tuple(bytes([(i << 4) | 0x0E]) for i in range(15))
_CLOSING_TAGS: tuple[bytes, ...] = tuple(bytes([(i << 4) | 0x0F]) for i in range(15))


def encode_opening_tag(tag_number: int) -> bytes:
    """Encode a context-specific opening tag.

    :param tag_number: Context tag number.
    :returns: Encoded opening tag bytes.
    """
    if tag_number <= 14:
        return _OPENING_TAGS[tag_number]
    return bytes([0xFE, tag_number])


def encode_closing_tag(tag_number: int) -> bytes:
    """Encode a context-specific closing tag.

    :param tag_number: Context tag number.
    :returns: Encoded closing tag bytes.
    """
    if tag_number <= 14:
        return _CLOSING_TAGS[tag_number]
    return bytes([0xFF, tag_number])


def as_memoryview(data: bytes | memoryview) -> memoryview:
    """Ensure *data* is a :class:`memoryview` for efficient zero-copy slicing.

    :param data: Input bytes or memoryview.
    :returns: A :class:`memoryview` wrapping *data*.
    """
    return memoryview(data) if isinstance(data, bytes) else data


def decode_tag(buf: memoryview | bytes, offset: int) -> tuple[Tag, int]:
    """Decode a tag from *buf* starting at *offset*.

    Parses the initial tag octet, optional extended tag number, and
    optional extended length fields per Clause 20.2.1.

    :param buf: Buffer to decode from.
    :param offset: Starting byte offset in *buf*.
    :returns: Tuple of (decoded :class:`Tag`, new offset past the tag header).
    :raises ValueError: If *offset* is beyond the buffer length.
    """
    if isinstance(buf, bytes):
        buf = memoryview(buf)

    if offset >= len(buf):
        msg = f"Tag decode: offset {offset} beyond buffer length {len(buf)}"
        logger.warning(msg)
        raise ValueError(msg)

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

    Reads from *offset* (which should point just past the opening tag)
    through the matching closing tag, handling nested opening/closing tags.

    :param data: Buffer to read from.
    :param offset: Position immediately after the opening tag.
    :param tag_number: The context tag number of the enclosing pair.
    :returns: Tuple of (enclosed raw bytes, offset past the closing tag).
    :raises ValueError: If the matching closing tag is not found.
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
    logger.warning(msg)
    raise ValueError(msg)


def decode_optional_context[T](
    data: memoryview,
    offset: int,
    tag_number: int,
    decode_fn: Callable[[memoryview | bytes], T],
) -> tuple[T | None, int]:
    """Try to decode an optional context-tagged field.

    Peeks at the next tag; if it matches the expected context tag number,
    decodes the value using *decode_fn* and advances the offset.
    Otherwise returns ``(None, offset)`` unchanged.

    :param data: Buffer to decode from (must already be a :class:`memoryview`).
    :param offset: Current position in the buffer.
    :param tag_number: Expected context tag number.
    :param decode_fn: Callable to decode the tag's content bytes.
    :returns: Tuple of (decoded value or ``None``, new offset).
    """
    if offset >= len(data):
        return None, offset
    tag, new_offset = decode_tag(data, offset)
    if (
        tag.cls == TagClass.CONTEXT
        and tag.number == tag_number
        and not tag.is_opening
        and not tag.is_closing
    ):
        value = decode_fn(data[new_offset : new_offset + tag.length])
        return value, new_offset + tag.length
    return None, offset
