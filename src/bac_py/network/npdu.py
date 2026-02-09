"""NPDU encoding and decoding per ASHRAE 135-2016 Clause 6."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.network.address import BACnetAddress
from bac_py.types.enums import NetworkPriority

BACNET_PROTOCOL_VERSION = 1


@dataclass(frozen=True, slots=True)
class NPDU:
    """Decoded Network Protocol Data Unit (Clause 6.2)."""

    version: int = BACNET_PROTOCOL_VERSION
    """BACnet protocol version (always 1)."""

    is_network_message: bool = False
    """``True`` for network-layer messages, ``False`` for application-layer APDUs."""

    expecting_reply: bool = False
    """``True`` when the sender expects a reply."""

    priority: NetworkPriority = NetworkPriority.NORMAL
    """Message priority (NORMAL, URGENT, etc.)."""

    destination: BACnetAddress | None = None
    """Remote destination address, or ``None`` for local."""

    source: BACnetAddress | None = None
    """Originating address (populated by routers)."""

    hop_count: int = 255
    """Remaining hop count for routed messages (0-255)."""

    message_type: int | None = None
    """Network message type code when *is_network_message* is ``True``."""

    vendor_id: int | None = None
    """Vendor identifier for proprietary network messages."""

    apdu: bytes = b""
    """Application-layer APDU payload bytes."""

    network_message_data: bytes = b""
    """Payload bytes for network-layer messages."""


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
        if npdu.destination.network is None:
            msg = "Destination network must be set when destination is present"
            raise ValueError(msg)
        dnet = npdu.destination.network
        buf.extend(dnet.to_bytes(2, "big"))
        dlen = len(npdu.destination.mac_address)
        buf.append(dlen)
        if dlen > 0:
            buf.extend(npdu.destination.mac_address)

    # Source (if present) - validate per Clause 6.2.2.1
    if npdu.source is not None:
        if npdu.source.network is None:
            msg = "Source network must be set when source is present (must be 1-65534)"
            raise ValueError(msg)
        snet = npdu.source.network
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
        if npdu.message_type is None:
            msg = "message_type must be set when is_network_message is True"
            raise ValueError(msg)
        buf.append(npdu.message_type)
        # Proprietary message types (0x80-0xFF) include a 2-byte vendor ID
        if npdu.message_type >= 0x80:
            vid = npdu.vendor_id or 0
            buf.extend(vid.to_bytes(2, "big"))
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

    Raises:
        ValueError: If the data is too short or the protocol version is not 1.
    """
    if len(data) < 2:
        msg = f"NPDU data too short: need at least 2 bytes, got {len(data)}"
        raise ValueError(msg)

    if isinstance(data, bytes):
        data = memoryview(data)

    offset = 0
    version = data[offset]
    offset += 1

    if version != BACNET_PROTOCOL_VERSION:
        msg = f"Unsupported BACnet protocol version: {version}"
        raise ValueError(msg)

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
        if snet == 0xFFFF:
            msg = "Source SNET cannot be 0xFFFF (global broadcast)"
            raise ValueError(msg)
        if snet == 0:
            msg = "Source SNET cannot be 0 (must be 1-65534)"
            raise ValueError(msg)
        slen = data[offset]
        offset += 1
        if slen == 0:
            msg = "Source SLEN cannot be 0 when source is present"
            raise ValueError(msg)
        sadr = bytes(data[offset : offset + slen])
        offset += slen
        source = BACnetAddress(network=snet, mac_address=sadr)

    if has_destination:
        hop_count = data[offset]
        offset += 1

    message_type = None
    vendor_id = None
    network_message_data = b""
    apdu = b""

    if is_network_message:
        message_type = data[offset]
        offset += 1
        # Proprietary message types (0x80-0xFF) include a 2-byte vendor ID
        if message_type >= 0x80:
            vendor_id = int.from_bytes(data[offset : offset + 2], "big")
            offset += 2
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
        vendor_id=vendor_id,
        apdu=apdu,
        network_message_data=network_message_data,
    )
