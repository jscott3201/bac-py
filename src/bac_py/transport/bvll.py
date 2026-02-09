"""BVLL (BACnet Virtual Link Layer) encoding and decoding per Annex J."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.network.address import BIPAddress
from bac_py.types.enums import BvlcFunction

BVLC_TYPE_BACNET_IP = 0x81
BVLL_HEADER_LENGTH = 4  # Type(1) + Function(1) + Length(2)


@dataclass(frozen=True, slots=True)
class BvllMessage:
    """Decoded BVLL message."""

    function: BvlcFunction
    data: bytes
    originating_address: BIPAddress | None = None


def encode_bvll(
    function: BvlcFunction,
    payload: bytes,
    originating_address: BIPAddress | None = None,
) -> bytes:
    """Encode a complete BVLL message.

    Args:
        function: BVLC function code.
        payload: NPDU payload bytes.
        originating_address: Required for Forwarded-NPDU.

    Returns:
        Complete BVLL message bytes ready for UDP transmission.
    """
    if function == BvlcFunction.FORWARDED_NPDU:
        if originating_address is None:
            msg = "Forwarded-NPDU requires originating_address"
            raise ValueError(msg)
        content = originating_address.encode() + payload
    else:
        content = payload

    length = BVLL_HEADER_LENGTH + len(content)
    header = bytes([BVLC_TYPE_BACNET_IP, function, length >> 8, length & 0xFF])
    return header + content


def decode_bvll(data: memoryview | bytes) -> BvllMessage:
    """Decode a BVLL message from raw UDP datagram.

    Args:
        data: Raw UDP datagram bytes.

    Returns:
        Decoded BvllMessage.

    Raises:
        ValueError: If data is too short, BVLC type byte is invalid,
            declared length is inconsistent, or a function-specific
            payload (e.g. Forwarded-NPDU originating address) is
            truncated.
    """
    if len(data) < BVLL_HEADER_LENGTH:
        msg = f"BVLL data too short: need at least {BVLL_HEADER_LENGTH} bytes, got {len(data)}"
        raise ValueError(msg)

    if isinstance(data, bytes):
        data = memoryview(data)

    if data[0] != BVLC_TYPE_BACNET_IP:
        msg = f"Invalid BVLC type: {data[0]:#x}"
        raise ValueError(msg)

    function = BvlcFunction(data[1])
    length = (data[2] << 8) | data[3]

    if length < BVLL_HEADER_LENGTH or length > len(data):
        msg = f"Invalid BVLL length: declared {length}, actual {len(data)}"
        raise ValueError(msg)

    if function == BvlcFunction.FORWARDED_NPDU:
        if length < BVLL_HEADER_LENGTH + 6:
            msg = f"Forwarded-NPDU too short: need at least {BVLL_HEADER_LENGTH + 6} bytes, got {length}"
            raise ValueError(msg)
        orig_addr = BIPAddress.decode(data[4:10])
        return BvllMessage(
            function=function,
            data=bytes(data[10:length]),
            originating_address=orig_addr,
        )

    return BvllMessage(function=function, data=bytes(data[4:length]))
