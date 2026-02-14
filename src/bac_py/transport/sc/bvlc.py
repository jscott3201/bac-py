"""BVLC-SC message encoding and decoding per Annex AB.2.

Wire format (minimum 4 bytes)::

    Function(1) | Control(1) | MessageID(2) | [OrigVMAC(6)] | [DestVMAC(6)]
    | [DestOptions(var)] | [DataOptions(var)] | [Payload(var)]

All multi-octet numeric values are big-endian (most significant octet first).
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

from bac_py.transport.sc.types import (
    SC_HEADER_MIN_LENGTH,
    VMAC_LENGTH,
    BvlcSCFunction,
    SCControlFlag,
    SCHeaderOptionType,
    SCHubConnectionStatus,
    SCResultCode,
)
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Header Options
# ---------------------------------------------------------------------------

# Header Marker bit masks (AB.2.3)
_MARKER_MORE_OPTIONS = 0x80
_MARKER_MUST_UNDERSTAND = 0x40
_MARKER_HAS_DATA = 0x20
_MARKER_TYPE_MASK = 0x1F


@dataclass(frozen=True, slots=True)
class SCHeaderOption:
    """A single BVLC-SC header option (AB.2.3).

    Header options appear in the Destination Options and Data Options
    fields of a BVLC-SC message.  Each option has a type, a must-understand
    flag, and optional data.
    """

    type: int
    must_understand: bool
    data: bytes = b""

    def encode(self, *, more: bool) -> bytes:
        """Encode this header option to wire bytes.

        :param more: True if more options follow in the list.
        """
        marker = self.type & _MARKER_TYPE_MASK
        if more:
            marker |= _MARKER_MORE_OPTIONS
        if self.must_understand:
            marker |= _MARKER_MUST_UNDERSTAND
        if self.data:
            marker |= _MARKER_HAS_DATA
            buf = bytearray(3 + len(self.data))
            buf[0] = marker
            struct.pack_into("!H", buf, 1, len(self.data))
            buf[3:] = self.data
            return bytes(buf)
        return bytes((marker,))

    @staticmethod
    def decode_list(data: memoryview) -> tuple[tuple[SCHeaderOption, ...], int]:
        """Decode a list of chained header options.

        :returns: Tuple of (options, bytes_consumed).
        """
        options: list[SCHeaderOption] = []
        offset = 0
        while offset < len(data):
            marker = data[offset]
            offset += 1

            opt_type = marker & _MARKER_TYPE_MASK
            must_understand = bool(marker & _MARKER_MUST_UNDERSTAND)
            has_data = bool(marker & _MARKER_HAS_DATA)
            has_more = bool(marker & _MARKER_MORE_OPTIONS)

            opt_data = b""
            if has_data:
                if offset + 2 > len(data):
                    msg = "Header option truncated: missing Header Length"
                    raise ValueError(msg)
                (data_len,) = struct.unpack_from("!H", data, offset)
                offset += 2
                if offset + data_len > len(data):
                    msg = (
                        f"Header option data truncated: need {data_len} bytes, "
                        f"have {len(data) - offset}"
                    )
                    raise ValueError(msg)
                opt_data = bytes(data[offset : offset + data_len])
                offset += data_len

            options.append(SCHeaderOption(opt_type, must_understand, opt_data))
            if not has_more:
                break

        return tuple(options), offset


# ---------------------------------------------------------------------------
# BVLC-SC Message
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SCMessage:
    """A decoded BVLC-SC message (AB.2.1).

    This is the generic envelope for all 13 BVLC-SC message types.
    The *payload* field contains the raw payload bytes; use the typed
    payload dataclasses (e.g. :class:`ConnectRequestPayload`) to decode
    specific message payloads.
    """

    function: BvlcSCFunction
    message_id: int
    originating: SCVMAC | None = None
    destination: SCVMAC | None = None
    dest_options: tuple[SCHeaderOption, ...] = ()
    data_options: tuple[SCHeaderOption, ...] = ()
    payload: bytes = b""

    def encode(self) -> bytes:
        """Encode this message to wire bytes."""
        logger.debug("BVLC-SC encode: %s", self.function.name)
        flags = SCControlFlag.NONE
        if self.originating is not None:
            flags |= SCControlFlag.ORIGINATING_VMAC
        if self.destination is not None:
            flags |= SCControlFlag.DESTINATION_VMAC
        if self.dest_options:
            flags |= SCControlFlag.DESTINATION_OPTIONS
        if self.data_options:
            flags |= SCControlFlag.DATA_OPTIONS

        buf = bytearray(4)
        buf[0] = self.function
        buf[1] = flags
        struct.pack_into("!H", buf, 2, self.message_id)

        if self.originating is not None:
            buf.extend(self.originating.address)
        if self.destination is not None:
            buf.extend(self.destination.address)
        if self.dest_options:
            buf.extend(_encode_options(self.dest_options))
        if self.data_options:
            buf.extend(_encode_options(self.data_options))
        if self.payload:
            buf.extend(self.payload)

        return bytes(buf)

    @staticmethod
    def decode(data: bytes | memoryview) -> SCMessage:
        """Decode a BVLC-SC message from wire bytes.

        :raises ValueError: If the message is malformed or truncated.
        """
        if isinstance(data, bytes):
            data = memoryview(data)
        if len(data) < SC_HEADER_MIN_LENGTH:
            msg = (
                f"BVLC-SC message too short: need at least "
                f"{SC_HEADER_MIN_LENGTH} bytes, got {len(data)}"
            )
            logger.warning("BVLC-SC malformed message: %s", msg)
            raise ValueError(msg)

        function = BvlcSCFunction(data[0])
        logger.debug("BVLC-SC decode: %s", function.name)
        flags = SCControlFlag(data[1] & 0x0F)
        (message_id,) = struct.unpack_from("!H", data, 2)
        offset = SC_HEADER_MIN_LENGTH

        originating: SCVMAC | None = None
        if flags & SCControlFlag.ORIGINATING_VMAC:
            if offset + VMAC_LENGTH > len(data):
                msg = "Truncated: missing Originating Virtual Address"
                logger.warning("BVLC-SC malformed message: %s", msg)
                raise ValueError(msg)
            originating = SCVMAC(bytes(data[offset : offset + VMAC_LENGTH]))
            offset += VMAC_LENGTH

        destination: SCVMAC | None = None
        if flags & SCControlFlag.DESTINATION_VMAC:
            if offset + VMAC_LENGTH > len(data):
                msg = "Truncated: missing Destination Virtual Address"
                logger.warning("BVLC-SC malformed message: %s", msg)
                raise ValueError(msg)
            destination = SCVMAC(bytes(data[offset : offset + VMAC_LENGTH]))
            offset += VMAC_LENGTH

        dest_options: tuple[SCHeaderOption, ...] = ()
        if flags & SCControlFlag.DESTINATION_OPTIONS:
            dest_options, consumed = SCHeaderOption.decode_list(data[offset:])
            offset += consumed

        data_options: tuple[SCHeaderOption, ...] = ()
        if flags & SCControlFlag.DATA_OPTIONS:
            data_options, consumed = SCHeaderOption.decode_list(data[offset:])
            offset += consumed

        payload = bytes(data[offset:])
        return SCMessage(
            function=function,
            message_id=message_id,
            originating=originating,
            destination=destination,
            dest_options=dest_options,
            data_options=data_options,
            payload=payload,
        )


def _encode_options(options: tuple[SCHeaderOption, ...]) -> bytes:
    """Encode a list of header options with proper More-Options chaining."""
    buf = bytearray()
    last = len(options) - 1
    for i, opt in enumerate(options):
        buf.extend(opt.encode(more=i < last))
    return bytes(buf)


# ---------------------------------------------------------------------------
# Typed Payloads
# ---------------------------------------------------------------------------

# Connect-Request / Connect-Accept payload: 26 bytes fixed
_CONNECT_PAYLOAD_LENGTH = VMAC_LENGTH + 16 + 2 + 2  # 26


@dataclass(frozen=True, slots=True)
class _ConnectPayload:
    """Shared payload structure for Connect-Request (AB.2.10) and Connect-Accept (AB.2.11)."""

    vmac: SCVMAC
    uuid: DeviceUUID
    max_bvlc_length: int
    max_npdu_length: int

    def encode(self) -> bytes:
        """Encode to 26 bytes."""
        return (
            self.vmac.address
            + self.uuid.value
            + struct.pack("!HH", self.max_bvlc_length, self.max_npdu_length)
        )

    @staticmethod
    def decode(data: bytes | memoryview) -> _ConnectPayload:
        """Decode from payload bytes."""
        if len(data) < _CONNECT_PAYLOAD_LENGTH:
            msg = (
                f"Connect payload too short: need {_CONNECT_PAYLOAD_LENGTH} bytes, got {len(data)}"
            )
            raise ValueError(msg)
        vmac = SCVMAC(bytes(data[:6]))
        device_uuid = DeviceUUID(bytes(data[6:22]))
        max_bvlc, max_npdu = struct.unpack_from("!HH", data, 22)
        return _ConnectPayload(vmac, device_uuid, max_bvlc, max_npdu)


# Public aliases — same structure, separate names for API clarity
ConnectRequestPayload = _ConnectPayload
ConnectAcceptPayload = _ConnectPayload


@dataclass(frozen=True, slots=True)
class BvlcResultPayload:
    """Payload for BVLC-Result messages (AB.2.4).

    For ACK: only *for_function* and *result_code* are meaningful.
    For NAK: *error_header_marker*, *error_class*, *error_code*, and
    optionally *error_details* describe the error.
    """

    for_function: BvlcSCFunction
    result_code: SCResultCode
    error_header_marker: int = 0
    error_class: int = 0
    error_code: int = 0
    error_details: str = ""

    def encode(self) -> bytes:
        """Encode BVLC-Result payload."""
        if self.result_code != SCResultCode.NAK:
            return bytes((self.for_function, self.result_code))
        buf = bytearray(7)
        buf[0] = self.for_function
        buf[1] = self.result_code
        buf[2] = self.error_header_marker
        struct.pack_into("!HH", buf, 3, self.error_class, self.error_code)
        if self.error_details:
            buf.extend(self.error_details.encode("utf-8"))
        return bytes(buf)

    @staticmethod
    def decode(data: bytes | memoryview) -> BvlcResultPayload:
        """Decode BVLC-Result payload."""
        if len(data) < 2:
            msg = f"BVLC-Result payload too short: need at least 2 bytes, got {len(data)}"
            raise ValueError(msg)
        for_function = BvlcSCFunction(data[0])
        result_code = SCResultCode(data[1])
        if result_code == SCResultCode.ACK:
            return BvlcResultPayload(for_function, result_code)
        # NAK: marker(1) + error_class(2) + error_code(2) = 5 more bytes minimum
        if len(data) < 7:
            msg = f"BVLC-Result NAK payload too short: need at least 7 bytes, got {len(data)}"
            raise ValueError(msg)
        error_header_marker = data[2]
        error_class, error_code_val = struct.unpack_from("!HH", data, 3)
        error_details = ""
        if len(data) > 7:
            error_details = bytes(data[7:]).decode("utf-8", errors="replace")
        return BvlcResultPayload(
            for_function,
            result_code,
            error_header_marker,
            error_class,
            error_code_val,
            error_details,
        )


@dataclass(frozen=True, slots=True)
class AdvertisementPayload:
    """Payload for Advertisement messages (AB.2.8)."""

    hub_connection_status: SCHubConnectionStatus
    accept_direct_connections: bool
    max_bvlc_length: int
    max_npdu_length: int

    def encode(self) -> bytes:
        """Encode to 6 bytes."""
        return struct.pack(
            "!BBHH",
            self.hub_connection_status,
            0x01 if self.accept_direct_connections else 0x00,
            self.max_bvlc_length,
            self.max_npdu_length,
        )

    @staticmethod
    def decode(data: bytes | memoryview) -> AdvertisementPayload:
        """Decode from payload bytes."""
        if len(data) < 6:
            msg = f"Advertisement payload too short: need 6 bytes, got {len(data)}"
            raise ValueError(msg)
        status, accept, max_bvlc, max_npdu = struct.unpack_from("!BBHH", data, 0)
        return AdvertisementPayload(
            hub_connection_status=SCHubConnectionStatus(status),
            accept_direct_connections=accept != 0,
            max_bvlc_length=max_bvlc,
            max_npdu_length=max_npdu,
        )


@dataclass(frozen=True, slots=True)
class AddressResolutionAckPayload:
    """Payload for Address-Resolution-ACK messages (AB.2.7).

    WebSocket URIs are space-separated in the wire format.
    """

    websocket_uris: tuple[str, ...]

    def encode(self) -> bytes:
        """Encode URI list to UTF-8 payload."""
        return " ".join(self.websocket_uris).encode("utf-8")

    @staticmethod
    def decode(data: bytes | memoryview) -> AddressResolutionAckPayload:
        """Decode URI list from payload bytes."""
        text = bytes(data).decode("utf-8")
        if not text:
            return AddressResolutionAckPayload(())
        return AddressResolutionAckPayload(tuple(text.split(" ")))


@dataclass(frozen=True, slots=True)
class ProprietaryMessagePayload:
    """Payload for Proprietary-Message (AB.2.16)."""

    vendor_id: int
    proprietary_function: int
    proprietary_data: bytes = b""

    def encode(self) -> bytes:
        """Encode proprietary payload."""
        return (
            struct.pack("!HB", self.vendor_id, self.proprietary_function) + self.proprietary_data
        )

    @staticmethod
    def decode(data: bytes | memoryview) -> ProprietaryMessagePayload:
        """Decode proprietary payload."""
        if len(data) < 3:
            msg = f"Proprietary payload too short: need at least 3 bytes, got {len(data)}"
            raise ValueError(msg)
        vendor_id, prop_func = struct.unpack_from("!HB", data, 0)
        prop_data = bytes(data[3:])
        return ProprietaryMessagePayload(vendor_id, prop_func, prop_data)


# ---------------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------------


def build_secure_path_option() -> SCHeaderOption:
    """Build a Secure Path data option (AB.2.3.1).

    The Secure Path header option has Must-Understand=1 and no data.
    """
    return SCHeaderOption(
        type=SCHeaderOptionType.SECURE_PATH,
        must_understand=True,
    )
