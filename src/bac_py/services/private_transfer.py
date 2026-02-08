"""Private transfer services per ASHRAE 135-2016 Clause 16.2-16.3.

ConfirmedPrivateTransfer (Clause 16.2), UnconfirmedPrivateTransfer (Clause 16.3).
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
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    extract_context_value,
)


@dataclass(frozen=True, slots=True)
class ConfirmedPrivateTransferRequest:
    """ConfirmedPrivateTransfer-Request (Clause 16.2.1.1).

    ::

        ConfirmedPrivateTransfer-Request ::= SEQUENCE {
            vendorID          [0] Unsigned,
            serviceNumber     [1] Unsigned,
            serviceParameters [2] ABSTRACT-SYNTAX.&TYPE OPTIONAL
        }
    """

    vendor_id: int
    service_number: int
    service_parameters: bytes | None = None

    def encode(self) -> bytes:
        """Encode ConfirmedPrivateTransferRequest to bytes."""
        buf = bytearray()
        buf.extend(encode_context_tagged(0, encode_unsigned(self.vendor_id)))
        buf.extend(encode_context_tagged(1, encode_unsigned(self.service_number)))
        if self.service_parameters is not None:
            buf.extend(encode_opening_tag(2))
            buf.extend(self.service_parameters)
            buf.extend(encode_closing_tag(2))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode ConfirmedPrivateTransferRequest from bytes."""
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        # [0] vendorID
        tag, offset = decode_tag(data, offset)
        vendor_id = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] serviceNumber
        tag, offset = decode_tag(data, offset)
        service_number = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [2] serviceParameters (optional)
        service_parameters = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.is_opening and tag.number == 2:
                service_parameters, offset = extract_context_value(data, new_offset, 2)

        return cls(
            vendor_id=vendor_id,
            service_number=service_number,
            service_parameters=service_parameters,
        )


@dataclass(frozen=True, slots=True)
class ConfirmedPrivateTransferACK:
    """ConfirmedPrivateTransfer-ACK (Clause 16.2.1.2).

    Same structure as the request.
    """

    vendor_id: int
    service_number: int
    result_block: bytes | None = None

    def encode(self) -> bytes:
        """Encode ConfirmedPrivateTransferACK to bytes."""
        buf = bytearray()
        buf.extend(encode_context_tagged(0, encode_unsigned(self.vendor_id)))
        buf.extend(encode_context_tagged(1, encode_unsigned(self.service_number)))
        if self.result_block is not None:
            buf.extend(encode_opening_tag(2))
            buf.extend(self.result_block)
            buf.extend(encode_closing_tag(2))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ConfirmedPrivateTransferACK:
        """Decode ConfirmedPrivateTransferACK from bytes."""
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        tag, offset = decode_tag(data, offset)
        vendor_id = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        tag, offset = decode_tag(data, offset)
        service_number = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        result_block = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.is_opening and tag.number == 2:
                result_block, offset = extract_context_value(data, new_offset, 2)

        return cls(
            vendor_id=vendor_id,
            service_number=service_number,
            result_block=result_block,
        )


@dataclass(frozen=True, slots=True)
class UnconfirmedPrivateTransferRequest(ConfirmedPrivateTransferRequest):
    """UnconfirmedPrivateTransfer-Request (Clause 16.3.1.1).

    Same structure as ConfirmedPrivateTransfer-Request.
    """
