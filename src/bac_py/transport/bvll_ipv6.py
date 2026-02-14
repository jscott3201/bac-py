"""BVLL (BACnet Virtual Link Layer) encoding and decoding for BACnet/IPv6 per Annex U."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from bac_py.network.address import BIP6Address
from bac_py.types.enums import Bvlc6Function

BVLC_TYPE_BACNET_IPV6 = 0x82
BVLL6_HEADER_LENGTH = 4  # Type(1) + Function(1) + Length(2)
VMAC_LENGTH = 3
BIP6_ADDRESS_LENGTH = 18  # 16-byte IPv6 + 2-byte port

# Which function codes include source VMAC, dest VMAC, and/or originating address.
_HAS_SOURCE_VMAC = frozenset(
    {
        Bvlc6Function.BVLC_RESULT,
        Bvlc6Function.ORIGINAL_UNICAST_NPDU,
        Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
        Bvlc6Function.FORWARDED_NPDU,
        Bvlc6Function.ADDRESS_RESOLUTION,
        Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION,
        Bvlc6Function.ADDRESS_RESOLUTION_ACK,
        Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION,
        Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK,
        Bvlc6Function.REGISTER_FOREIGN_DEVICE,
        Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
        Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU,
    }
)

_HAS_DEST_VMAC = frozenset(
    {
        Bvlc6Function.ORIGINAL_UNICAST_NPDU,
        Bvlc6Function.ADDRESS_RESOLUTION_ACK,
        Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK,
    }
)

_HAS_ORIGINATING_ADDRESS = frozenset(
    {
        Bvlc6Function.FORWARDED_NPDU,
        Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION,
    }
)


@dataclass(frozen=True, slots=True)
class Bvll6Message:
    """Decoded BACnet/IPv6 BVLL message."""

    function: Bvlc6Function
    data: bytes
    source_vmac: bytes | None = None
    dest_vmac: bytes | None = None
    originating_address: BIP6Address | None = None


def encode_bvll6(
    function: Bvlc6Function,
    payload: bytes,
    *,
    source_vmac: bytes | None = None,
    dest_vmac: bytes | None = None,
    originating_address: BIP6Address | None = None,
) -> bytes:
    """Encode a complete BACnet/IPv6 BVLL message.

    Uses a single pre-sized bytearray to avoid intermediate allocations.

    :param function: BVLC6 function code.
    :param payload: NPDU payload bytes (or result/registration data).
    :param source_vmac: 3-byte source VMAC (required for most functions).
    :param dest_vmac: 3-byte destination VMAC (required for unicast and ACKs).
    :param originating_address: 18-byte originating IPv6 address (Forwarded-NPDU).
    :returns: Complete BVLL message bytes ready for UDP transmission.
    """
    # Calculate total size upfront for single allocation
    size = BVLL6_HEADER_LENGTH + len(payload)
    has_src = function in _HAS_SOURCE_VMAC
    has_dst = function in _HAS_DEST_VMAC
    has_orig = function in _HAS_ORIGINATING_ADDRESS

    if has_src:
        if source_vmac is None or len(source_vmac) != VMAC_LENGTH:
            msg = f"{function.name} requires a 3-byte source VMAC"
            raise ValueError(msg)
        size += VMAC_LENGTH

    if has_dst:
        if dest_vmac is None or len(dest_vmac) != VMAC_LENGTH:
            msg = f"{function.name} requires a 3-byte destination VMAC"
            raise ValueError(msg)
        size += VMAC_LENGTH

    orig_bytes: bytes | None = None
    if has_orig:
        if originating_address is None:
            msg = f"{function.name} requires originating_address"
            raise ValueError(msg)
        orig_bytes = originating_address.encode()
        size += len(orig_bytes)

    buf = bytearray(size)
    buf[0] = BVLC_TYPE_BACNET_IPV6
    buf[1] = function
    struct.pack_into("!H", buf, 2, size)
    offset = BVLL6_HEADER_LENGTH

    if has_src:
        assert source_vmac is not None  # validated above
        buf[offset : offset + VMAC_LENGTH] = source_vmac
        offset += VMAC_LENGTH

    if has_dst:
        assert dest_vmac is not None  # validated above
        buf[offset : offset + VMAC_LENGTH] = dest_vmac
        offset += VMAC_LENGTH

    if orig_bytes is not None:
        buf[offset : offset + len(orig_bytes)] = orig_bytes
        offset += len(orig_bytes)

    buf[offset:] = payload
    return bytes(buf)


def decode_bvll6(data: memoryview | bytes) -> Bvll6Message:
    """Decode a BACnet/IPv6 BVLL message from raw UDP datagram.

    :param data: Raw UDP datagram bytes.
    :returns: Decoded :class:`Bvll6Message`.
    :raises ValueError: If data is too short, type byte is invalid, or payload is truncated.
    """
    if len(data) < BVLL6_HEADER_LENGTH:
        msg = f"BVLL6 data too short: need at least {BVLL6_HEADER_LENGTH} bytes, got {len(data)}"
        raise ValueError(msg)

    if isinstance(data, bytes):
        data = memoryview(data)

    if data[0] != BVLC_TYPE_BACNET_IPV6:
        msg = f"Invalid BVLC type: {data[0]:#x}, expected {BVLC_TYPE_BACNET_IPV6:#x}"
        raise ValueError(msg)

    function = Bvlc6Function(data[1])
    length = (data[2] << 8) | data[3]

    if length < BVLL6_HEADER_LENGTH or length > len(data):
        msg = f"Invalid BVLL6 length: declared {length}, actual {len(data)}"
        raise ValueError(msg)

    offset = BVLL6_HEADER_LENGTH
    source_vmac: bytes | None = None
    dest_vmac: bytes | None = None
    originating_address: BIP6Address | None = None

    if function in _HAS_SOURCE_VMAC:
        if offset + VMAC_LENGTH > length:
            msg = f"{function.name} truncated: missing source VMAC"
            raise ValueError(msg)
        source_vmac = bytes(data[offset : offset + VMAC_LENGTH])
        offset += VMAC_LENGTH

    if function in _HAS_DEST_VMAC:
        if offset + VMAC_LENGTH > length:
            msg = f"{function.name} truncated: missing destination VMAC"
            raise ValueError(msg)
        dest_vmac = bytes(data[offset : offset + VMAC_LENGTH])
        offset += VMAC_LENGTH

    if function in _HAS_ORIGINATING_ADDRESS:
        if offset + BIP6_ADDRESS_LENGTH > length:
            msg = f"{function.name} truncated: missing originating address"
            raise ValueError(msg)
        originating_address = BIP6Address.decode(data[offset : offset + BIP6_ADDRESS_LENGTH])
        offset += BIP6_ADDRESS_LENGTH

    return Bvll6Message(
        function=function,
        data=bytes(data[offset:length]),
        source_vmac=source_vmac,
        dest_vmac=dest_vmac,
        originating_address=originating_address,
    )
