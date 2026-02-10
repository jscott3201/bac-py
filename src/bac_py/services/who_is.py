"""Who-Is and I-Am services per ASHRAE 135-2016 Clause 16.10."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_unsigned,
    encode_application_enumerated,
    encode_application_object_id,
    encode_application_unsigned,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import TagClass, as_memoryview, decode_tag
from bac_py.types.enums import ObjectType, Segmentation
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class WhoIsRequest:
    """Who-Is-Request service parameters (Clause 16.10.1).

    Both limits must be present or both absent.
    """

    low_limit: int | None = None
    high_limit: int | None = None

    def encode(self) -> bytes:
        """Encode Who-Is-Request service parameters.

        :returns: Encoded service request bytes (may be empty if no range is set).
        """
        if self.low_limit is None or self.high_limit is None:
            return b""
        buf = bytearray()
        # [0] device-instance-range-low-limit
        buf.extend(encode_context_tagged(0, encode_unsigned(self.low_limit)))
        # [1] device-instance-range-high-limit
        buf.extend(encode_context_tagged(1, encode_unsigned(self.high_limit)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> WhoIsRequest:
        """Decode Who-Is-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`WhoIsRequest`.
        """
        data = as_memoryview(data)

        if len(data) == 0:
            return cls()

        offset = 0
        low_limit = None
        high_limit = None

        # [0] device-instance-range-low-limit
        tag, offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 0:
            low_limit = decode_unsigned(data[offset : offset + tag.length])
            offset += tag.length

        # [1] device-instance-range-high-limit
        if offset < len(data):
            tag, offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 1:
                high_limit = decode_unsigned(data[offset : offset + tag.length])

        return cls(low_limit=low_limit, high_limit=high_limit)

    def __post_init__(self) -> None:
        """Validate that both limits are present or both absent.

        If only one limit is provided, both are reset to ``None``
        (per Clause 16.10.1.1.1, malformed ranges are treated as unbounded).
        """
        if (self.low_limit is None) != (self.high_limit is None):
            # Per Clause 16.10.1.1.1, treat malformed as unbounded
            object.__setattr__(self, "low_limit", None)
            object.__setattr__(self, "high_limit", None)


@dataclass(frozen=True, slots=True)
class IAmRequest:
    """I-Am-Request service parameters (Clause 16.10.2).

    All fields use APPLICATION tags (not context-specific).
    """

    object_identifier: ObjectIdentifier
    max_apdu_length: int
    segmentation_supported: Segmentation
    vendor_id: int

    def encode(self) -> bytes:
        """Encode I-Am-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # iAmDeviceIdentifier - application tagged object-id
        buf.extend(
            encode_application_object_id(
                self.object_identifier.object_type,
                self.object_identifier.instance_number,
            )
        )
        # maxAPDULengthAccepted - application tagged unsigned
        buf.extend(encode_application_unsigned(self.max_apdu_length))
        # segmentationSupported - application tagged enumerated
        buf.extend(encode_application_enumerated(self.segmentation_supported))
        # vendorID - application tagged unsigned
        buf.extend(encode_application_unsigned(self.vendor_id))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> IAmRequest:
        """Decode I-Am-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`IAmRequest`.
        """
        data = as_memoryview(data)

        offset = 0

        # iAmDeviceIdentifier - application tagged object-id (tag 12)
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # maxAPDULengthAccepted - application tagged unsigned (tag 2)
        tag, offset = decode_tag(data, offset)
        max_apdu_length = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # segmentationSupported - application tagged enumerated (tag 9)
        tag, offset = decode_tag(data, offset)
        segmentation_supported = Segmentation(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        # vendorID - application tagged unsigned (tag 2)
        tag, offset = decode_tag(data, offset)
        vendor_id = decode_unsigned(data[offset : offset + tag.length])

        return cls(
            object_identifier=object_identifier,
            max_apdu_length=max_apdu_length,
            segmentation_supported=segmentation_supported,
            vendor_id=vendor_id,
        )
