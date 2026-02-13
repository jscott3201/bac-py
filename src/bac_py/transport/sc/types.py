"""BACnet/SC enums and constants per Annex AB."""

from __future__ import annotations

from enum import IntEnum, IntFlag


class BvlcSCFunction(IntEnum):
    """BVLC-SC message function codes (Table AB-1)."""

    BVLC_RESULT = 0x00
    ENCAPSULATED_NPDU = 0x01
    ADDRESS_RESOLUTION = 0x02
    ADDRESS_RESOLUTION_ACK = 0x03
    ADVERTISEMENT = 0x04
    ADVERTISEMENT_SOLICITATION = 0x05
    CONNECT_REQUEST = 0x06
    CONNECT_ACCEPT = 0x07
    DISCONNECT_REQUEST = 0x08
    DISCONNECT_ACK = 0x09
    HEARTBEAT_REQUEST = 0x0A
    HEARTBEAT_ACK = 0x0B
    PROPRIETARY_MESSAGE = 0x0C


class SCControlFlag(IntFlag):
    """Control flags byte (AB.2.2)."""

    NONE = 0x00
    DATA_OPTIONS = 0x01
    DESTINATION_OPTIONS = 0x02
    DESTINATION_VMAC = 0x04
    ORIGINATING_VMAC = 0x08


class SCResultCode(IntEnum):
    """BVLC-Result result codes (AB.2.4)."""

    ACK = 0x00
    NAK = 0x01


class SCHeaderOptionType(IntEnum):
    """Header option types (Table AB-3)."""

    SECURE_PATH = 1
    PROPRIETARY = 31


class SCHubConnectionStatus(IntEnum):
    """Hub connection status values for Advertisement payload (AB.2.8)."""

    NO_HUB_CONNECTION = 0x00
    CONNECTED_TO_PRIMARY = 0x01
    CONNECTED_TO_FAILOVER = 0x02


# WebSocket subprotocol names (AB.7.1)
SC_HUB_SUBPROTOCOL = "hub.bsc.bacnet.org"
SC_DIRECT_SUBPROTOCOL = "dc.bsc.bacnet.org"

# VMAC constants (AB.1.5.2)
VMAC_LENGTH = 6
VMAC_BROADCAST = b"\xff\xff\xff\xff\xff\xff"
VMAC_UNINITIALIZED = b"\x00\x00\x00\x00\x00\x00"

# Device UUID length (AB.1.5.3)
UUID_LENGTH = 16

# Minimum BVLC-SC header: Function(1) + Control(1) + MessageID(2)
SC_HEADER_MIN_LENGTH = 4
