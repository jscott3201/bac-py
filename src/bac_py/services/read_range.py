"""ReadRange service per ASHRAE 135-2016 Clause 15.8."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_bit_string,
    decode_date,
    decode_object_identifier,
    decode_signed,
    decode_time,
    decode_unsigned,
    encode_application_date,
    encode_application_signed,
    encode_application_time,
    encode_application_unsigned,
    encode_bit_string,
    encode_context_object_id,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_optional_context,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    extract_context_value,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier


@dataclass(frozen=True, slots=True)
class RangeByPosition:
    """Range qualifier: by position (index + count).

    ::

        SEQUENCE {
            referenceIndex  Unsigned,
            count           INTEGER
        }
    """

    reference_index: int
    count: int


@dataclass(frozen=True, slots=True)
class RangeBySequenceNumber:
    """Range qualifier: by sequence number.

    ::

        SEQUENCE {
            referenceSequenceNumber  Unsigned,
            count                    INTEGER
        }
    """

    reference_sequence_number: int
    count: int


@dataclass(frozen=True, slots=True)
class RangeByTime:
    """Range qualifier: by time.

    ::

        SEQUENCE {
            referenceTime  BACnetDateTime,
            count          INTEGER
        }
    """

    reference_date: BACnetDate
    reference_time: BACnetTime
    count: int


@dataclass(frozen=True, slots=True)
class ResultFlags:
    """BACnetResultFlags — 3-bit BitString.

    Bit 0: FIRST_ITEM — result includes the first item in the list
    Bit 1: LAST_ITEM — result includes the last item in the list
    Bit 2: MORE_ITEMS — more items remain beyond what was returned
    """

    first_item: bool = False
    last_item: bool = False
    more_items: bool = False

    def to_bit_string(self) -> BitString:
        """Encode as BACnet BitString (3 significant bits)."""
        value = (self.first_item << 2) | (self.last_item << 1) | self.more_items
        return BitString(bytes([value << 5]), unused_bits=5)

    @classmethod
    def from_bit_string(cls, bs: BitString) -> ResultFlags:
        """Decode from a BACnet BitString."""
        return cls(
            first_item=bs[0] if len(bs) > 0 else False,
            last_item=bs[1] if len(bs) > 1 else False,
            more_items=bs[2] if len(bs) > 2 else False,
        )


@dataclass(frozen=True, slots=True)
class ReadRangeRequest:
    """ReadRange-Request service parameters (Clause 15.8.1.1).

    ::

        ReadRange-Request ::= SEQUENCE {
            objectIdentifier    [0] BACnetObjectIdentifier,
            propertyIdentifier  [1] BACnetPropertyIdentifier,
            propertyArrayIndex  [2] Unsigned OPTIONAL,
            range               CHOICE {
                byPosition        [3] SEQUENCE { referenceIndex Unsigned, count INTEGER },
                bySequenceNumber  [6] SEQUENCE { referenceSequenceNumber Unsigned,
                                                  count INTEGER },
                byTime            [7] SEQUENCE { referenceTime BACnetDateTime,
                                                  count INTEGER }
            } OPTIONAL
        }
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    property_array_index: int | None = None
    range: RangeByPosition | RangeBySequenceNumber | RangeByTime | None = None

    def encode(self) -> bytes:
        """Encode ReadRange-Request service parameters."""
        buf = bytearray()
        # [0] object-identifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
        # [1] property-identifier
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        # [2] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        # Range qualifier (optional) -- inner SEQUENCE elements use
        # application tags per BACnet encoding rules.
        if isinstance(self.range, RangeByPosition):
            buf.extend(encode_opening_tag(3))
            buf.extend(encode_application_unsigned(self.range.reference_index))
            buf.extend(encode_application_signed(self.range.count))
            buf.extend(encode_closing_tag(3))
        elif isinstance(self.range, RangeBySequenceNumber):
            buf.extend(encode_opening_tag(6))
            buf.extend(encode_application_unsigned(self.range.reference_sequence_number))
            buf.extend(encode_application_signed(self.range.count))
            buf.extend(encode_closing_tag(6))
        elif isinstance(self.range, RangeByTime):
            buf.extend(encode_opening_tag(7))
            buf.extend(encode_application_date(self.range.reference_date))
            buf.extend(encode_application_time(self.range.reference_time))
            buf.extend(encode_application_signed(self.range.count))
            buf.extend(encode_closing_tag(7))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReadRangeRequest:
        """Decode ReadRange-Request from service request bytes."""
        data = as_memoryview(data)

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
        range_val: RangeByPosition | RangeBySequenceNumber | RangeByTime | None = None

        if offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if (
                tag_peek.cls == TagClass.CONTEXT
                and tag_peek.number == 2
                and not tag_peek.is_opening
                and not tag_peek.is_closing
            ):
                property_array_index = decode_unsigned(
                    data[next_offset : next_offset + tag_peek.length]
                )
                offset = next_offset + tag_peek.length

        # Range qualifier (optional)
        if offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if tag_peek.is_opening:
                offset = next_offset
                if tag_peek.number == 3:
                    # byPosition
                    t, offset = decode_tag(data, offset)
                    ref_index = decode_unsigned(data[offset : offset + t.length])
                    offset += t.length
                    t, offset = decode_tag(data, offset)
                    count = decode_signed(data[offset : offset + t.length])
                    offset += t.length
                    # closing tag 3
                    _closing, offset = decode_tag(data, offset)
                    range_val = RangeByPosition(reference_index=ref_index, count=count)
                elif tag_peek.number == 6:
                    # bySequenceNumber
                    t, offset = decode_tag(data, offset)
                    ref_seq = decode_unsigned(data[offset : offset + t.length])
                    offset += t.length
                    t, offset = decode_tag(data, offset)
                    count = decode_signed(data[offset : offset + t.length])
                    offset += t.length
                    # closing tag 6
                    _closing, offset = decode_tag(data, offset)
                    range_val = RangeBySequenceNumber(
                        reference_sequence_number=ref_seq, count=count
                    )
                elif tag_peek.number == 7:
                    # byTime
                    t, offset = decode_tag(data, offset)
                    ref_date = decode_date(data[offset : offset + t.length])
                    offset += t.length
                    t, offset = decode_tag(data, offset)
                    ref_time = decode_time(data[offset : offset + t.length])
                    offset += t.length
                    t, offset = decode_tag(data, offset)
                    count = decode_signed(data[offset : offset + t.length])
                    offset += t.length
                    # closing tag 7
                    _closing, offset = decode_tag(data, offset)
                    range_val = RangeByTime(
                        reference_date=ref_date,
                        reference_time=ref_time,
                        count=count,
                    )

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=property_array_index,
            range=range_val,
        )


@dataclass(frozen=True, slots=True)
class ReadRangeACK:
    """ReadRange-ACK service parameters (Clause 15.8.1.2).

    ::

        ReadRange-ACK ::= SEQUENCE {
            objectIdentifier    [0] BACnetObjectIdentifier,
            propertyIdentifier  [1] BACnetPropertyIdentifier,
            propertyArrayIndex  [2] Unsigned OPTIONAL,
            resultFlags         [3] BACnetResultFlags,
            itemCount           [4] Unsigned,
            itemData            [5] SEQUENCE OF ABSTRACT-SYNTAX.&TYPE,
            firstSequenceNumber [6] Unsigned32 OPTIONAL
        }

    The itemData field contains raw encoded bytes wrapped in context
    tag 5 (opening/closing).
    """

    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    result_flags: ResultFlags
    item_count: int
    item_data: bytes
    property_array_index: int | None = None
    first_sequence_number: int | None = None

    def encode(self) -> bytes:
        """Encode ReadRange-ACK service parameters."""
        buf = bytearray()
        # [0] object-identifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
        # [1] property-identifier
        buf.extend(encode_context_tagged(1, encode_unsigned(self.property_identifier)))
        # [2] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        # [3] result-flags (BitString)
        buf.extend(encode_context_tagged(3, encode_bit_string(self.result_flags.to_bit_string())))
        # [4] item-count
        buf.extend(encode_context_tagged(4, encode_unsigned(self.item_count)))
        # [5] item-data (opening/closing)
        buf.extend(encode_opening_tag(5))
        buf.extend(self.item_data)
        buf.extend(encode_closing_tag(5))
        # [6] first-sequence-number (optional)
        if self.first_sequence_number is not None:
            buf.extend(encode_context_tagged(6, encode_unsigned(self.first_sequence_number)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReadRangeACK:
        """Decode ReadRange-ACK from service ACK bytes."""
        data = as_memoryview(data)

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
        tag_peek, next_offset = decode_tag(data, offset)
        if (
            tag_peek.cls == TagClass.CONTEXT
            and tag_peek.number == 2
            and not tag_peek.is_opening
            and not tag_peek.is_closing
        ):
            property_array_index = decode_unsigned(
                data[next_offset : next_offset + tag_peek.length]
            )
            offset = next_offset + tag_peek.length
            tag_peek, next_offset = decode_tag(data, offset)

        # [3] result-flags
        # tag_peek should be context tag 3
        tag = tag_peek
        offset = next_offset
        bs = decode_bit_string(data[offset : offset + tag.length])
        result_flags = ResultFlags.from_bit_string(bs)
        offset += tag.length

        # [4] item-count
        tag, offset = decode_tag(data, offset)
        item_count = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [5] item-data (opening/closing)
        _opening, offset = decode_tag(data, offset)
        item_data, offset = extract_context_value(data, offset, 5)

        # [6] first-sequence-number (optional)
        first_sequence_number, _ = decode_optional_context(data, offset, 6, decode_unsigned)

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            result_flags=result_flags,
            item_count=item_count,
            item_data=item_data,
            property_array_index=property_array_index,
            first_sequence_number=first_sequence_number,
        )
