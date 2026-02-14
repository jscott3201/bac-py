"""NPDU encoding and decoding per ASHRAE 135-2016 Clause 6."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bac_py.network.address import BACnetAddress
from bac_py.types.enums import NetworkPriority

logger = logging.getLogger(__name__)

BACNET_PROTOCOL_VERSION = 1


@dataclass(frozen=True, slots=True)
class NPDU:
    """Decoded Network Protocol Data Unit (Clause 6.2).

    Represents the complete contents of a BACnet NPDU including the
    control octet fields, optional source/destination addressing, and
    either an application-layer APDU or a network-layer message payload.
    """

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
    """Encode an :class:`NPDU` dataclass into on-the-wire bytes.

    Builds the version octet, control octet, optional destination/source
    address fields, hop count, and either the network-message type + data
    or the application-layer APDU payload.

    :param npdu: The :class:`NPDU` dataclass to encode.
    :returns: The fully encoded NPDU byte string.
    :raises ValueError: If source address fields are invalid per the
        BACnet specification (e.g. SNET is 0xFFFF or SLEN is 0).
    """
    # Pre-allocate with estimated capacity: 2 header + up to 18 addr + payload
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
        dadr = npdu.destination.mac_address
        logger.debug(f"encode_npdu: dnet={dnet} dadr={dadr.hex() if dadr else '(empty)'}")
        buf.extend(dnet.to_bytes(2, "big"))
        dlen = len(dadr)
        buf.append(dlen)
        if dlen > 0:
            buf.extend(dadr)

    # Source (if present) - validate per Clause 6.2.2.1
    if npdu.source is not None:
        if npdu.source.network is None:
            msg = "Source network must be set when source is present (must be 1-65534)"
            logger.warning(f"encode_npdu: {msg}")
            raise ValueError(msg)
        snet = npdu.source.network
        if snet == 0xFFFF:
            msg = "SNET cannot be 0xFFFF (global broadcast is not a valid source)"
            logger.warning(f"encode_npdu: {msg}")
            raise ValueError(msg)
        if snet == 0:
            msg = "SNET cannot be 0 (must be 1-65534)"
            logger.warning(f"encode_npdu: {msg}")
            raise ValueError(msg)
        slen = len(npdu.source.mac_address)
        if slen == 0:
            msg = "SLEN cannot be 0 when source is present"
            logger.warning(f"encode_npdu: {msg}")
            raise ValueError(msg)
        logger.debug(f"encode_npdu: snet={snet} sadr={npdu.source.mac_address.hex()}")
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
    """Decode raw bytes into an :class:`NPDU` dataclass.

    Parses the version octet, control octet, optional destination/source
    address fields, hop count, and the remaining payload (network message
    or application-layer APDU).

    :param data: Raw NPDU bytes (at least 2 bytes required).
    :returns: The decoded :class:`NPDU`.
    :raises ValueError: If the data is too short or the protocol version
        is not 1.
    """
    if len(data) < 2:
        msg = f"NPDU data too short: need at least 2 bytes, got {len(data)}"
        logger.warning(f"decode_npdu: {msg}")
        raise ValueError(msg)

    if isinstance(data, bytes):
        data = memoryview(data)

    offset = 0
    version = data[offset]
    offset += 1

    if version != BACNET_PROTOCOL_VERSION:
        msg = f"Unsupported BACnet protocol version: {version}"
        logger.warning(f"decode_npdu: {msg}")
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
        logger.debug(f"decode_npdu: dnet={dnet} dadr={dadr.hex() if dadr else '(empty)'}")

    if has_source:
        snet = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        if snet == 0xFFFF:
            msg = "Source SNET cannot be 0xFFFF (global broadcast)"
            logger.warning(f"decode_npdu: {msg}")
            raise ValueError(msg)
        if snet == 0:
            msg = "Source SNET cannot be 0 (must be 1-65534)"
            logger.warning(f"decode_npdu: {msg}")
            raise ValueError(msg)
        slen = data[offset]
        offset += 1
        if slen == 0:
            msg = "Source SLEN cannot be 0 when source is present"
            logger.warning(f"decode_npdu: {msg}")
            raise ValueError(msg)
        sadr = bytes(data[offset : offset + slen])
        offset += slen
        source = BACnetAddress(network=snet, mac_address=sadr)
        logger.debug(f"decode_npdu: snet={snet} sadr={sadr.hex()}")

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
