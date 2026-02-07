"""NPDU encoding and decoding per ASHRAE 135-2016 Clause 6."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.network.address import BACnetAddress
from bac_py.types.enums import NetworkMessageType, NetworkPriority

BACNET_PROTOCOL_VERSION = 1


@dataclass(frozen=True, slots=True)
class NPDU:
    """Decoded Network Protocol Data Unit."""

    version: int = BACNET_PROTOCOL_VERSION
    is_network_message: bool = False
    expecting_reply: bool = False
    priority: NetworkPriority = NetworkPriority.NORMAL
    destination: BACnetAddress | None = None
    source: BACnetAddress | None = None
    hop_count: int = 255
    message_type: NetworkMessageType | None = None
    apdu: bytes = b""
    network_message_data: bytes = b""


def encode_npdu(npdu: NPDU) -> bytes:
    """Encode an NPDU to bytes.

    Args:
        npdu: The NPDU dataclass to encode.

    Returns:
        Encoded NPDU bytes.

    Raises:
        ValueError: If source address fields are invalid per spec.
    """
    buf = bytearray()
    buf.append(BACNET_PROTOCOL_VERSION)

    # Build control octet (bits 6 and 4 are reserved, always zero)
    control = 0
    if npdu.is_network_message:
        control |= 0x80
    if npdu.destination is not None:
        control |= 0x20
    if npdu.source is not None:
        control |= 0x08
    if npdu.expecting_reply:
        control |= 0x04
    control |= npdu.priority & 0x03
    buf.append(control)

    # Destination (if present)
    if npdu.destination is not None:
        dnet = npdu.destination.network if npdu.destination.network is not None else 0xFFFF
        buf.extend(dnet.to_bytes(2, "big"))
        dlen = len(npdu.destination.mac_address)
        buf.append(dlen)
        if dlen > 0:
            buf.extend(npdu.destination.mac_address)

    # Source (if present) - validate per Clause 6.2.2.1
    if npdu.source is not None:
        snet = npdu.source.network or 0
        if snet == 0xFFFF:
            msg = "SNET cannot be 0xFFFF (global broadcast is not a valid source)"
            raise ValueError(msg)
        if snet == 0:
            msg = "SNET cannot be 0 (must be 1-65534)"
            raise ValueError(msg)
        slen = len(npdu.source.mac_address)
        if slen == 0:
            msg = "SLEN cannot be 0 when source is present"
            raise ValueError(msg)
        buf.extend(snet.to_bytes(2, "big"))
        buf.append(slen)
        buf.extend(npdu.source.mac_address)

    # Hop count (only if destination present)
    if npdu.destination is not None:
        buf.append(npdu.hop_count)

    # Message type or APDU
    if npdu.is_network_message:
        buf.append(npdu.message_type or 0)
        buf.extend(npdu.network_message_data)
    else:
        buf.extend(npdu.apdu)

    return bytes(buf)


def decode_npdu(data: memoryview | bytes) -> NPDU:
    """Decode an NPDU from bytes.

    Args:
        data: Raw NPDU bytes.

    Returns:
        Decoded NPDU dataclass.
    """
    if isinstance(data, bytes):
        data = memoryview(data)

    offset = 0
    version = data[offset]
    offset += 1
    control = data[offset]
    offset += 1

    is_network_message = bool(control & 0x80)
    has_destination = bool(control & 0x20)
    has_source = bool(control & 0x08)
    expecting_reply = bool(control & 0x04)
    priority = NetworkPriority(control & 0x03)

    destination = None
    source = None
    hop_count = 255

    if has_destination:
        dnet = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        dlen = data[offset]
        offset += 1
        dadr = bytes(data[offset : offset + dlen])
        offset += dlen
        destination = BACnetAddress(network=dnet, mac_address=dadr)

    if has_source:
        snet = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        slen = data[offset]
        offset += 1
        sadr = bytes(data[offset : offset + slen])
        offset += slen
        source = BACnetAddress(network=snet, mac_address=sadr)

    if has_destination:
        hop_count = data[offset]
        offset += 1

    message_type = None
    network_message_data = b""
    apdu = b""

    if is_network_message:
        message_type = NetworkMessageType(data[offset])
        offset += 1
        network_message_data = bytes(data[offset:])
    else:
        apdu = bytes(data[offset:])

    return NPDU(
        version=version,
        is_network_message=is_network_message,
        expecting_reply=expecting_reply,
        priority=priority,
        destination=destination,
        source=source,
        hop_count=hop_count,
        message_type=message_type,
        apdu=apdu,
        network_message_data=network_message_data,
    )
