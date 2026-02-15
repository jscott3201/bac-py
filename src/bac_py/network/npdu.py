"""NPDU encoding and decoding per ASHRAE 135-2016 Clause 6."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

from bac_py.network.address import BACnetAddress
from bac_py.types.enums import NetworkPriority

logger = logging.getLogger(__name__)
_DEBUG = logging.DEBUG

BACNET_PROTOCOL_VERSION = 1

# Pre-built NetworkPriority lookup tuple (values 0-3)
_PRIORITIES: tuple[NetworkPriority, ...] = (
    NetworkPriority.NORMAL,
    NetworkPriority.URGENT,
    NetworkPriority.CRITICAL_EQUIPMENT,
    NetworkPriority.LIFE_SAFETY,
)


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

    Pre-calculates the total buffer size upfront and fills with slice
    assignment / ``struct.pack_into`` to avoid repeated ``append``/``extend``.

    :param npdu: The :class:`NPDU` dataclass to encode.
    :returns: The fully encoded NPDU byte string.
    :raises ValueError: If source address fields are invalid per the
        BACnet specification (e.g. SNET is 0xFFFF or SLEN is 0).
    """
    # -- Validate and gather fields ------------------------------------------
    dest = npdu.destination
    src = npdu.source
    dadr: bytes = b""
    dnet: int = 0
    sadr: bytes = b""
    snet: int = 0
    slen: int = 0

    if dest is not None:
        if dest.network is None:
            msg = "Destination network must be set when destination is present"
            raise ValueError(msg)
        dnet = dest.network
        dadr = dest.mac_address
        if logger.isEnabledFor(_DEBUG):
            logger.debug("encode_npdu: dnet=%d dadr=%s", dnet, dadr.hex() if dadr else "(empty)")

    if src is not None:
        if src.network is None:
            msg = "Source network must be set when source is present (must be 1-65534)"
            logger.warning("encode_npdu: %s", msg)
            raise ValueError(msg)
        snet = src.network
        if snet == 0xFFFF:
            msg = "SNET cannot be 0xFFFF (global broadcast is not a valid source)"
            logger.warning("encode_npdu: %s", msg)
            raise ValueError(msg)
        if snet == 0:
            msg = "SNET cannot be 0 (must be 1-65534)"
            logger.warning("encode_npdu: %s", msg)
            raise ValueError(msg)
        sadr = src.mac_address
        slen = len(sadr)
        if slen == 0:
            msg = "SLEN cannot be 0 when source is present"
            logger.warning("encode_npdu: %s", msg)
            raise ValueError(msg)
        if logger.isEnabledFor(_DEBUG):
            logger.debug("encode_npdu: snet=%d sadr=%s", snet, sadr.hex())

    # -- Calculate total buffer size -----------------------------------------
    total = 2  # version + control
    if dest is not None:
        total += 3 + len(dadr)  # DNET(2) + DLEN(1) + DADR
    if src is not None:
        total += 3 + slen  # SNET(2) + SLEN(1) + SADR
    if dest is not None:
        total += 1  # hop count

    if npdu.is_network_message:
        if npdu.message_type is None:
            msg = "message_type must be set when is_network_message is True"
            raise ValueError(msg)
        total += 1  # message_type
        if npdu.message_type >= 0x80:
            total += 2  # vendor_id
        total += len(npdu.network_message_data)
    else:
        total += len(npdu.apdu)

    # -- Fill pre-sized buffer -----------------------------------------------
    buf = bytearray(total)

    # Build control octet (bits 6 and 4 are reserved, always zero)
    control = npdu.priority & 0x03
    if npdu.is_network_message:
        control |= 0x80
    if dest is not None:
        control |= 0x20
    if src is not None:
        control |= 0x08
    if npdu.expecting_reply:
        control |= 0x04

    buf[0] = BACNET_PROTOCOL_VERSION
    buf[1] = control
    offset = 2

    # Destination (if present)
    if dest is not None:
        struct.pack_into("!HB", buf, offset, dnet, len(dadr))
        offset += 3
        dlen = len(dadr)
        if dlen > 0:
            buf[offset : offset + dlen] = dadr
            offset += dlen

    # Source (if present)
    if src is not None:
        struct.pack_into("!HB", buf, offset, snet, slen)
        offset += 3
        buf[offset : offset + slen] = sadr
        offset += slen

    # Hop count (only if destination present)
    if dest is not None:
        buf[offset] = npdu.hop_count
        offset += 1

    # Message type or APDU
    if npdu.is_network_message:
        buf[offset] = npdu.message_type  # type: ignore[assignment]  # validated above
        offset += 1
        if npdu.message_type >= 0x80:  # type: ignore[operator]
            vid = npdu.vendor_id or 0
            struct.pack_into("!H", buf, offset, vid)
            offset += 2
        nmd = npdu.network_message_data
        buf[offset : offset + len(nmd)] = nmd
    else:
        apdu = npdu.apdu
        buf[offset : offset + len(apdu)] = apdu

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
        logger.warning("decode_npdu: %s", msg)
        raise ValueError(msg)

    if isinstance(data, bytes):
        data = memoryview(data)

    offset = 0
    version = data[offset]
    offset += 1

    if version != BACNET_PROTOCOL_VERSION:
        msg = f"Unsupported BACnet protocol version: {version}"
        logger.warning("decode_npdu: %s", msg)
        raise ValueError(msg)

    control = data[offset]
    offset += 1

    is_network_message = bool(control & 0x80)
    has_destination = bool(control & 0x20)
    has_source = bool(control & 0x08)
    expecting_reply = bool(control & 0x04)
    priority = _PRIORITIES[control & 0x03]

    destination = None
    source = None
    hop_count = 255

    if has_destination:
        if offset + 3 > len(data):
            msg = f"NPDU too short for destination: need {offset + 3} bytes, got {len(data)}"
            raise ValueError(msg)
        dnet = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        dlen = data[offset]
        offset += 1
        if dlen > 0 and offset + dlen > len(data):
            msg = (
                f"NPDU destination address truncated: DLEN={dlen} but only "
                f"{len(data) - offset} bytes remain"
            )
            logger.warning("decode_npdu: %s", msg)
            raise ValueError(msg)
        dadr = bytes(data[offset : offset + dlen])
        offset += dlen
        destination = BACnetAddress(network=dnet, mac_address=dadr)
        if logger.isEnabledFor(_DEBUG):
            logger.debug("decode_npdu: dnet=%d dadr=%s", dnet, dadr.hex() if dadr else "(empty)")

    if has_source:
        if offset + 3 > len(data):
            msg = f"NPDU too short for source: need {offset + 3} bytes, got {len(data)}"
            raise ValueError(msg)
        snet = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        if snet == 0xFFFF:
            msg = "Source SNET cannot be 0xFFFF (global broadcast)"
            logger.warning("decode_npdu: %s", msg)
            raise ValueError(msg)
        if snet == 0:
            msg = "Source SNET cannot be 0 (must be 1-65534)"
            logger.warning("decode_npdu: %s", msg)
            raise ValueError(msg)
        slen = data[offset]
        offset += 1
        if slen == 0:
            msg = "Source SLEN cannot be 0 when source is present"
            logger.warning("decode_npdu: %s", msg)
            raise ValueError(msg)
        if offset + slen > len(data):
            msg = (
                f"NPDU source address truncated: SLEN={slen} but only "
                f"{len(data) - offset} bytes remain"
            )
            logger.warning("decode_npdu: %s", msg)
            raise ValueError(msg)
        sadr = bytes(data[offset : offset + slen])
        offset += slen
        source = BACnetAddress(network=snet, mac_address=sadr)
        if logger.isEnabledFor(_DEBUG):
            logger.debug("decode_npdu: snet=%d sadr=%s", snet, sadr.hex())

    if has_destination:
        if offset >= len(data):
            msg = "NPDU too short for hop count"
            raise ValueError(msg)
        hop_count = data[offset]
        offset += 1

    message_type = None
    vendor_id = None
    network_message_data = b""
    apdu = b""

    if is_network_message:
        if offset >= len(data):
            msg = "NPDU too short for network message type"
            raise ValueError(msg)
        message_type = data[offset]
        offset += 1
        # Proprietary message types (0x80-0xFF) include a 2-byte vendor ID
        if message_type >= 0x80:
            if offset + 2 > len(data):
                msg = "NPDU too short for proprietary vendor ID: need 2 bytes"
                logger.warning("decode_npdu: %s", msg)
                raise ValueError(msg)
            vendor_id = int.from_bytes(data[offset : offset + 2], "big")
            offset += 2
        network_message_data = bytes(data[offset:])
    else:
        apdu = bytes(data[offset:])

    return _make_npdu(
        version,
        is_network_message,
        expecting_reply,
        priority,
        destination,
        source,
        hop_count,
        message_type,
        vendor_id,
        apdu,
        network_message_data,
    )


def _make_npdu(
    version: int,
    is_network_message: bool,
    expecting_reply: bool,
    priority: NetworkPriority,
    destination: BACnetAddress | None,
    source: BACnetAddress | None,
    hop_count: int,
    message_type: int | None,
    vendor_id: int | None,
    apdu: bytes,
    network_message_data: bytes,
) -> NPDU:
    """Fast NPDU construction bypassing frozen-dataclass ``__init__``."""
    obj = object.__new__(NPDU)
    object.__setattr__(obj, "version", version)
    object.__setattr__(obj, "is_network_message", is_network_message)
    object.__setattr__(obj, "expecting_reply", expecting_reply)
    object.__setattr__(obj, "priority", priority)
    object.__setattr__(obj, "destination", destination)
    object.__setattr__(obj, "source", source)
    object.__setattr__(obj, "hop_count", hop_count)
    object.__setattr__(obj, "message_type", message_type)
    object.__setattr__(obj, "vendor_id", vendor_id)
    object.__setattr__(obj, "apdu", apdu)
    object.__setattr__(obj, "network_message_data", network_message_data)
    return obj
