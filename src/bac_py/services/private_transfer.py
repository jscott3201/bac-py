"""Private transfer services per ASHRAE 135-2016 Clause 16.2-16.3.

ConfirmedPrivateTransfer (Clause 16.2), UnconfirmedPrivateTransfer (Clause 16.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_unsigned,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import decode_tag, encode_closing_tag, encode_opening_tag


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
        buf = bytearray()
        buf.extend(encode_context_tagged(0, encode_unsigned(self.vendor_id)))
        buf.extend(encode_context_tagged(1, encode_unsigned(self.service_number)))
        if self.service_parameters is not None:
            buf.extend(encode_opening_tag(2))
            buf.extend(self.service_parameters)
            buf.extend(encode_closing_tag(2))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ConfirmedPrivateTransferRequest:
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
                offset = new_offset
                value_start = offset
                depth = 1
                while depth > 0 and offset < len(data):
                    t, offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                    elif t.is_closing:
                        depth -= 1
                    else:
                        offset += t.length
                closing_tag_len = 1 if 2 <= 14 else 2
                value_end = offset - closing_tag_len
                service_parameters = bytes(data[value_start:value_end])

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
                offset = new_offset
                value_start = offset
                depth = 1
                while depth > 0 and offset < len(data):
                    t, offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                    elif t.is_closing:
                        depth -= 1
                    else:
                        offset += t.length
                closing_tag_len = 1 if 2 <= 14 else 2
                value_end = offset - closing_tag_len
                result_block = bytes(data[value_start:value_end])

        return cls(
            vendor_id=vendor_id,
            service_number=service_number,
            result_block=result_block,
        )


@dataclass(frozen=True, slots=True)
class UnconfirmedPrivateTransferRequest:
    """UnconfirmedPrivateTransfer-Request (Clause 16.3.1.1).

    Same structure as ConfirmedPrivateTransfer-Request.
    """

    vendor_id: int
    service_number: int
    service_parameters: bytes | None = None

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(encode_context_tagged(0, encode_unsigned(self.vendor_id)))
        buf.extend(encode_context_tagged(1, encode_unsigned(self.service_number)))
        if self.service_parameters is not None:
            buf.extend(encode_opening_tag(2))
            buf.extend(self.service_parameters)
            buf.extend(encode_closing_tag(2))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> UnconfirmedPrivateTransferRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        tag, offset = decode_tag(data, offset)
        vendor_id = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        tag, offset = decode_tag(data, offset)
        service_number = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        service_parameters = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.is_opening and tag.number == 2:
                offset = new_offset
                value_start = offset
                depth = 1
                while depth > 0 and offset < len(data):
                    t, offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                    elif t.is_closing:
                        depth -= 1
                    else:
                        offset += t.length
                closing_tag_len = 1 if 2 <= 14 else 2
                value_end = offset - closing_tag_len
                service_parameters = bytes(data[value_start:value_end])

        return cls(
            vendor_id=vendor_id,
            service_number=service_number,
            service_parameters=service_parameters,
        )
