"""BACnet NotificationParameters CHOICE type per ASHRAE 135-2020 Clause 13.3.

Each variant is a frozen dataclass identified by its context tag number
which corresponds to the ``BACnetEventType`` enumeration value.  A factory
function :func:`decode_notification_parameters` dispatches to the correct
variant based on the opening context tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from bac_py.encoding.primitives import (
    decode_bit_string,
    decode_character_string,
    decode_date,
    decode_double,
    decode_real,
    decode_signed,
    decode_time,
    decode_unsigned,
    encode_bit_string,
    encode_character_string,
    encode_context_enumerated,
    encode_context_tagged,
    encode_date,
    encode_double,
    encode_real,
    encode_signed,
    encode_time,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    extract_context_value,
)
from bac_py.types.constructed import BACnetDateTime, StatusFlags
from bac_py.types.enums import (
    LifeSafetyMode,
    LifeSafetyOperation,
    LifeSafetyState,
    Reliability,
    TimerState,
    TimerTransition,
)
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_sf(tag: int, sf: StatusFlags) -> bytes:
    """Encode *StatusFlags* as a context-tagged BitString."""
    return encode_context_tagged(tag, encode_bit_string(sf.to_bit_string()))


def _decode_sf(data: memoryview, offset: int) -> tuple[StatusFlags, int]:
    """Decode a context-tagged StatusFlags BitString."""
    tag, offset = decode_tag(data, offset)
    bs = decode_bit_string(data[offset : offset + tag.length])
    offset += tag.length
    return StatusFlags.from_bit_string(bs), offset


def _decode_ctx_unsigned(data: memoryview, offset: int) -> tuple[int, int]:
    """Decode a context-tagged unsigned integer."""
    tag, offset = decode_tag(data, offset)
    val = decode_unsigned(data[offset : offset + tag.length])
    offset += tag.length
    return val, offset


def _decode_ctx_signed(data: memoryview, offset: int) -> tuple[int, int]:
    """Decode a context-tagged signed integer."""
    tag, offset = decode_tag(data, offset)
    val = decode_signed(data[offset : offset + tag.length])
    offset += tag.length
    return val, offset


def _decode_ctx_real(data: memoryview, offset: int) -> tuple[float, int]:
    """Decode a context-tagged Real."""
    tag, offset = decode_tag(data, offset)
    val = decode_real(data[offset : offset + tag.length])
    offset += tag.length
    return val, offset


def _decode_ctx_double(data: memoryview, offset: int) -> tuple[float, int]:
    """Decode a context-tagged Double."""
    tag, offset = decode_tag(data, offset)
    val = decode_double(data[offset : offset + tag.length])
    offset += tag.length
    return val, offset


def _decode_ctx_enum(data: memoryview, offset: int) -> tuple[int, int]:
    """Decode a context-tagged Enumerated (same wire format as unsigned)."""
    return _decode_ctx_unsigned(data, offset)


def _decode_ctx_bitstring(data: memoryview, offset: int) -> tuple[BitString, int]:
    """Decode a context-tagged BitString."""
    tag, offset = decode_tag(data, offset)
    bs = decode_bit_string(data[offset : offset + tag.length])
    offset += tag.length
    return bs, offset


def _decode_ctx_charstring(data: memoryview, offset: int) -> tuple[str, int]:
    """Decode a context-tagged CharacterString."""
    tag, offset = decode_tag(data, offset)
    val = decode_character_string(data[offset : offset + tag.length])
    offset += tag.length
    return val, offset


def _encode_ctx_charstring(tag: int, value: str) -> bytes:
    """Encode a CharacterString with a context tag."""
    return encode_context_tagged(tag, encode_character_string(value))


def _sf_dict(sf: StatusFlags) -> dict[str, bool]:
    """Convert *StatusFlags* to a dict."""
    return sf.to_dict()


def _sf_from_dict(d: dict[str, Any]) -> StatusFlags:
    """Reconstruct *StatusFlags* from a dict."""
    return StatusFlags.from_dict(d)


def _peek_tag(data: memoryview, offset: int) -> tuple[int, bool, bool, int]:
    """Peek at the next tag without consuming content.

    Returns ``(tag_number, is_opening, is_closing, offset_after_tag)``.
    """
    tag, new_offset = decode_tag(data, offset)
    return tag.number, tag.is_opening, tag.is_closing, new_offset


# ---------------------------------------------------------------------------
# Variant: ChangeOfBitstring (tag 0) -- Clause 13.3.1
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfBitstring:
    """change-of-bitstring notification parameters (Clause 13.3.1).

    Fields:
      [0] referenced_bitstring  BIT STRING
      [1] status_flags          BACnetStatusFlags
    """

    TAG: ClassVar[int] = 0

    referenced_bitstring: BitString = field(default_factory=lambda: BitString(b"", 0))
    status_flags: StatusFlags = field(default_factory=StatusFlags)

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_bit_string(self.referenced_bitstring))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[ChangeOfBitstring, int]:
        """Decode inner fields from wire data."""
        bs, offset = _decode_ctx_bitstring(data, offset)
        sf, offset = _decode_sf(data, offset)
        return cls(referenced_bitstring=bs, status_flags=sf), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-bitstring",
            "referenced_bitstring": self.referenced_bitstring.to_dict(),
            "status_flags": _sf_dict(self.status_flags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfBitstring:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            referenced_bitstring=BitString.from_dict(d["referenced_bitstring"]),
            status_flags=_sf_from_dict(d["status_flags"]),
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfState (tag 1) -- Clause 13.3.2
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfState:
    """change-of-state notification parameters (Clause 13.3.2).

    ``new_state`` is carried as raw bytes because ``BACnetPropertyStates``
    is a large CHOICE type with 40+ variants.

    Fields:
      [0] new_state    BACnetPropertyStates (raw bytes)
      [1] status_flags BACnetStatusFlags
    """

    TAG: ClassVar[int] = 1

    new_state: bytes = b""
    status_flags: StatusFlags = field(default_factory=StatusFlags)

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.new_state
        buf += encode_closing_tag(0)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[ChangeOfState, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        raw, offset = extract_context_value(data, offset, 0)
        sf, offset = _decode_sf(data, offset)
        return cls(new_state=raw, status_flags=sf), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-state",
            "new_state": self.new_state.hex(),
            "status_flags": _sf_dict(self.status_flags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfState:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            new_state=bytes.fromhex(d["new_state"]),
            status_flags=_sf_from_dict(d["status_flags"]),
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfValue (tag 2) -- Clause 13.3.3
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfValue:
    """change-of-value notification parameters (Clause 13.3.3).

    The ``new_value`` CHOICE is discriminated by ``new_value_choice``:
      0 = changed-bits (BitString), 1 = changed-value (Real).

    Fields:
      [0] new_value    CHOICE { [0] changed-bits, [1] changed-value }
      [1] status_flags BACnetStatusFlags
    """

    TAG: ClassVar[int] = 2

    new_value_choice: int = 1
    new_value: BitString | float = 0.0
    status_flags: StatusFlags = field(default_factory=StatusFlags)

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        if self.new_value_choice == 0:
            assert isinstance(self.new_value, BitString)
            buf += encode_context_tagged(0, encode_bit_string(self.new_value))
        else:
            assert isinstance(self.new_value, (int, float))
            buf += encode_context_tagged(1, encode_real(float(self.new_value)))
        buf += encode_closing_tag(0)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[ChangeOfValue, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        inner_tag, inner_offset = decode_tag(data, offset)
        if inner_tag.number == 0:
            bs = decode_bit_string(data[inner_offset : inner_offset + inner_tag.length])
            offset = inner_offset + inner_tag.length
            new_value_choice = 0
            new_value: BitString | float = bs
        else:
            val = decode_real(data[inner_offset : inner_offset + inner_tag.length])
            offset = inner_offset + inner_tag.length
            new_value_choice = 1
            new_value = val
        _closing, offset = decode_tag(data, offset)  # closing 0
        sf, offset = _decode_sf(data, offset)
        return cls(
            new_value_choice=new_value_choice,
            new_value=new_value,
            status_flags=sf,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        d: dict[str, Any] = {
            "type": "change-of-value",
            "new_value_choice": "changed-bits" if self.new_value_choice == 0 else "changed-value",
            "status_flags": _sf_dict(self.status_flags),
        }
        if self.new_value_choice == 0:
            assert isinstance(self.new_value, BitString)
            d["new_value"] = self.new_value.to_dict()
        else:
            d["new_value"] = self.new_value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfValue:
        """Reconstruct from a JSON-friendly dict."""
        choice = 0 if d["new_value_choice"] == "changed-bits" else 1
        if choice == 0:
            nv: BitString | float = BitString.from_dict(d["new_value"])
        else:
            nv = float(d["new_value"])
        return cls(
            new_value_choice=choice,
            new_value=nv,
            status_flags=_sf_from_dict(d["status_flags"]),
        )


# ---------------------------------------------------------------------------
# Variant: CommandFailure (tag 3) -- Clause 13.3.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CommandFailure:
    """command-failure notification parameters (Clause 13.3.4).

    ``command_value`` and ``feedback_value`` are ``ABSTRACT-SYNTAX.&Type``
    and are carried as raw bytes.

    Fields:
      [0] command_value  (raw bytes)
      [1] status_flags   BACnetStatusFlags
      [2] feedback_value (raw bytes)
    """

    TAG: ClassVar[int] = 3

    command_value: bytes = b""
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    feedback_value: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.command_value
        buf += encode_closing_tag(0)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_opening_tag(2)
        buf += self.feedback_value
        buf += encode_closing_tag(2)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[CommandFailure, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        cmd, offset = extract_context_value(data, offset, 0)
        sf, offset = _decode_sf(data, offset)
        _tag, offset = decode_tag(data, offset)  # opening 2
        fb, offset = extract_context_value(data, offset, 2)
        return cls(command_value=cmd, status_flags=sf, feedback_value=fb), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "command-failure",
            "command_value": self.command_value.hex(),
            "status_flags": _sf_dict(self.status_flags),
            "feedback_value": self.feedback_value.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CommandFailure:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            command_value=bytes.fromhex(d["command_value"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            feedback_value=bytes.fromhex(d["feedback_value"]),
        )


# ---------------------------------------------------------------------------
# Variant: FloatingLimit (tag 4) -- Clause 13.3.5
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FloatingLimit:
    """floating-limit notification parameters (Clause 13.3.5).

    Fields:
      [0] reference_value REAL
      [1] status_flags    BACnetStatusFlags
      [2] setpoint_value  REAL
      [3] error_limit     REAL
    """

    TAG: ClassVar[int] = 4

    reference_value: float = 0.0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    setpoint_value: float = 0.0
    error_limit: float = 0.0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_real(self.reference_value))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_real(self.setpoint_value))
        buf += encode_context_tagged(3, encode_real(self.error_limit))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[FloatingLimit, int]:
        """Decode inner fields from wire data."""
        rv, offset = _decode_ctx_real(data, offset)
        sf, offset = _decode_sf(data, offset)
        sp, offset = _decode_ctx_real(data, offset)
        el, offset = _decode_ctx_real(data, offset)
        return cls(
            reference_value=rv,
            status_flags=sf,
            setpoint_value=sp,
            error_limit=el,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "floating-limit",
            "reference_value": self.reference_value,
            "status_flags": _sf_dict(self.status_flags),
            "setpoint_value": self.setpoint_value,
            "error_limit": self.error_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FloatingLimit:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            reference_value=float(d["reference_value"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            setpoint_value=float(d["setpoint_value"]),
            error_limit=float(d["error_limit"]),
        )


# ---------------------------------------------------------------------------
# Variant: OutOfRange (tag 5) -- Clause 13.3.6
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutOfRange:
    """out-of-range notification parameters (Clause 13.3.6).

    Fields:
      [0] exceeding_value REAL
      [1] status_flags    BACnetStatusFlags
      [2] deadband        REAL
      [3] exceeded_limit  REAL
    """

    TAG: ClassVar[int] = 5

    exceeding_value: float = 0.0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    deadband: float = 0.0
    exceeded_limit: float = 0.0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_real(self.exceeding_value))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_real(self.deadband))
        buf += encode_context_tagged(3, encode_real(self.exceeded_limit))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[OutOfRange, int]:
        """Decode inner fields from wire data."""
        ev, offset = _decode_ctx_real(data, offset)
        sf, offset = _decode_sf(data, offset)
        db, offset = _decode_ctx_real(data, offset)
        el, offset = _decode_ctx_real(data, offset)
        return cls(
            exceeding_value=ev,
            status_flags=sf,
            deadband=db,
            exceeded_limit=el,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "out-of-range",
            "exceeding_value": self.exceeding_value,
            "status_flags": _sf_dict(self.status_flags),
            "deadband": self.deadband,
            "exceeded_limit": self.exceeded_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutOfRange:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            exceeding_value=float(d["exceeding_value"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            deadband=float(d["deadband"]),
            exceeded_limit=float(d["exceeded_limit"]),
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfLifeSafety (tag 8) -- Clause 13.3.8
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfLifeSafety:
    """change-of-life-safety notification parameters (Clause 13.3.8).

    Fields:
      [0] new_state          BACnetLifeSafetyState
      [1] new_mode           BACnetLifeSafetyMode
      [2] status_flags       BACnetStatusFlags
      [3] operation_expected BACnetLifeSafetyOperation
    """

    TAG: ClassVar[int] = 8

    new_state: LifeSafetyState = LifeSafetyState.QUIET
    new_mode: LifeSafetyMode = LifeSafetyMode.OFF
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    operation_expected: LifeSafetyOperation = LifeSafetyOperation.NONE

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_enumerated(0, self.new_state)
        buf += encode_context_enumerated(1, self.new_mode)
        buf += _encode_sf(2, self.status_flags)
        buf += encode_context_enumerated(3, self.operation_expected)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls,
        data: memoryview,
        offset: int,
    ) -> tuple[ChangeOfLifeSafety, int]:
        """Decode inner fields from wire data."""
        ns, offset = _decode_ctx_enum(data, offset)
        nm, offset = _decode_ctx_enum(data, offset)
        sf, offset = _decode_sf(data, offset)
        oe, offset = _decode_ctx_enum(data, offset)
        return cls(
            new_state=LifeSafetyState(ns),
            new_mode=LifeSafetyMode(nm),
            status_flags=sf,
            operation_expected=LifeSafetyOperation(oe),
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-life-safety",
            "new_state": self.new_state.value,
            "new_mode": self.new_mode.value,
            "status_flags": _sf_dict(self.status_flags),
            "operation_expected": self.operation_expected.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfLifeSafety:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            new_state=LifeSafetyState(d["new_state"]),
            new_mode=LifeSafetyMode(d["new_mode"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            operation_expected=LifeSafetyOperation(d["operation_expected"]),
        )


# ---------------------------------------------------------------------------
# Variant: Extended (tag 9) -- Clause 13.3.9
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Extended:
    """extended notification parameters (Clause 13.3.9).

    ``parameters`` is carried as raw bytes (vendor-defined content).

    Fields:
      [0] vendor_id            Unsigned16
      [1] extended_event_type  Unsigned
      [2] parameters           SEQUENCE OF CHOICE (raw bytes)
    """

    TAG: ClassVar[int] = 9

    vendor_id: int = 0
    extended_event_type: int = 0
    parameters: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_unsigned(self.vendor_id))
        buf += encode_context_tagged(1, encode_unsigned(self.extended_event_type))
        buf += encode_opening_tag(2)
        buf += self.parameters
        buf += encode_closing_tag(2)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[Extended, int]:
        """Decode inner fields from wire data."""
        vid, offset = _decode_ctx_unsigned(data, offset)
        eet, offset = _decode_ctx_unsigned(data, offset)
        _tag, offset = decode_tag(data, offset)  # opening 2
        params, offset = extract_context_value(data, offset, 2)
        return cls(vendor_id=vid, extended_event_type=eet, parameters=params), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "extended",
            "vendor_id": self.vendor_id,
            "extended_event_type": self.extended_event_type,
            "parameters": self.parameters.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Extended:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            vendor_id=d["vendor_id"],
            extended_event_type=d["extended_event_type"],
            parameters=bytes.fromhex(d["parameters"]),
        )


# ---------------------------------------------------------------------------
# Variant: BufferReady (tag 10) -- Clause 13.3.10
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BufferReady:
    """buffer-ready notification parameters (Clause 13.3.10).

    ``buffer_property`` is carried as raw bytes representing the
    encoded ``BACnetDeviceObjectPropertyReference``.

    Fields:
      [0] buffer_property       BACnetDeviceObjectPropertyReference (raw)
      [1] previous_notification Unsigned32
      [2] current_notification  Unsigned32
    """

    TAG: ClassVar[int] = 10

    buffer_property: bytes = b""
    previous_notification: int = 0
    current_notification: int = 0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.buffer_property
        buf += encode_closing_tag(0)
        buf += encode_context_tagged(1, encode_unsigned(self.previous_notification))
        buf += encode_context_tagged(2, encode_unsigned(self.current_notification))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[BufferReady, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        bp, offset = extract_context_value(data, offset, 0)
        pn, offset = _decode_ctx_unsigned(data, offset)
        cn, offset = _decode_ctx_unsigned(data, offset)
        return cls(buffer_property=bp, previous_notification=pn, current_notification=cn), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "buffer-ready",
            "buffer_property": self.buffer_property.hex(),
            "previous_notification": self.previous_notification,
            "current_notification": self.current_notification,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BufferReady:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            buffer_property=bytes.fromhex(d["buffer_property"]),
            previous_notification=d["previous_notification"],
            current_notification=d["current_notification"],
        )


# ---------------------------------------------------------------------------
# Variant: UnsignedRange (tag 11) -- Clause 13.3.11
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnsignedRange:
    """unsigned-range notification parameters (Clause 13.3.11).

    Fields:
      [0] exceeding_value Unsigned
      [1] status_flags    BACnetStatusFlags
      [2] exceeded_limit  Unsigned
    """

    TAG: ClassVar[int] = 11

    exceeding_value: int = 0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    exceeded_limit: int = 0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_unsigned(self.exceeding_value))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_unsigned(self.exceeded_limit))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[UnsignedRange, int]:
        """Decode inner fields from wire data."""
        ev, offset = _decode_ctx_unsigned(data, offset)
        sf, offset = _decode_sf(data, offset)
        el, offset = _decode_ctx_unsigned(data, offset)
        return cls(exceeding_value=ev, status_flags=sf, exceeded_limit=el), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "unsigned-range",
            "exceeding_value": self.exceeding_value,
            "status_flags": _sf_dict(self.status_flags),
            "exceeded_limit": self.exceeded_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> UnsignedRange:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            exceeding_value=d["exceeding_value"],
            status_flags=_sf_from_dict(d["status_flags"]),
            exceeded_limit=d["exceeded_limit"],
        )


# ---------------------------------------------------------------------------
# Variant: AccessEvent (tag 13) -- Clause 13.3.13
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccessEvent:
    """access-event notification parameters (Clause 13.3.13).

    ``access_event_time``, ``access_credential``, and
    ``authentication_factor`` are carried as raw bytes due to complexity.

    Fields:
      [0] access_event          Enumerated
      [1] status_flags          BACnetStatusFlags
      [2] access_event_tag      Unsigned
      [3] access_event_time     BACnetTimeStamp (raw)
      [4] access_credential     BACnetDeviceObjectReference (raw)
      [5] authentication_factor BACnetAuthenticationFactor (raw, OPTIONAL)
    """

    TAG: ClassVar[int] = 13

    access_event: int = 0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    access_event_tag: int = 0
    access_event_time: bytes = b""
    access_credential: bytes = b""
    authentication_factor: bytes | None = None

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_enumerated(0, self.access_event)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_unsigned(self.access_event_tag))
        buf += encode_opening_tag(3)
        buf += self.access_event_time
        buf += encode_closing_tag(3)
        buf += encode_opening_tag(4)
        buf += self.access_credential
        buf += encode_closing_tag(4)
        if self.authentication_factor is not None:
            buf += encode_opening_tag(5)
            buf += self.authentication_factor
            buf += encode_closing_tag(5)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[AccessEvent, int]:
        """Decode inner fields from wire data."""
        ae, offset = _decode_ctx_enum(data, offset)
        sf, offset = _decode_sf(data, offset)
        aet, offset = _decode_ctx_unsigned(data, offset)
        _tag, offset = decode_tag(data, offset)  # opening 3
        aetime, offset = extract_context_value(data, offset, 3)
        _tag, offset = decode_tag(data, offset)  # opening 4
        ac, offset = extract_context_value(data, offset, 4)
        auth: bytes | None = None
        if offset < len(data):
            tag_num, is_open, _is_close, _ = _peek_tag(data, offset)
            if is_open and tag_num == 5:
                _tag, offset = decode_tag(data, offset)  # opening 5
                auth, offset = extract_context_value(data, offset, 5)
        return cls(
            access_event=ae,
            status_flags=sf,
            access_event_tag=aet,
            access_event_time=aetime,
            access_credential=ac,
            authentication_factor=auth,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        d: dict[str, Any] = {
            "type": "access-event",
            "access_event": self.access_event,
            "status_flags": _sf_dict(self.status_flags),
            "access_event_tag": self.access_event_tag,
            "access_event_time": self.access_event_time.hex(),
            "access_credential": self.access_credential.hex(),
        }
        if self.authentication_factor is not None:
            d["authentication_factor"] = self.authentication_factor.hex()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AccessEvent:
        """Reconstruct from a JSON-friendly dict."""
        auth = d.get("authentication_factor")
        return cls(
            access_event=d["access_event"],
            status_flags=_sf_from_dict(d["status_flags"]),
            access_event_tag=d["access_event_tag"],
            access_event_time=bytes.fromhex(d["access_event_time"]),
            access_credential=bytes.fromhex(d["access_credential"]),
            authentication_factor=bytes.fromhex(auth) if auth is not None else None,
        )


# ---------------------------------------------------------------------------
# Variant: DoubleOutOfRange (tag 14) -- Clause 13.3.14
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DoubleOutOfRange:
    """double-out-of-range notification parameters (Clause 13.3.14).

    Fields:
      [0] exceeding_value Double
      [1] status_flags    BACnetStatusFlags
      [2] deadband        Double
      [3] exceeded_limit  Double
    """

    TAG: ClassVar[int] = 14

    exceeding_value: float = 0.0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    deadband: float = 0.0
    exceeded_limit: float = 0.0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_double(self.exceeding_value))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_double(self.deadband))
        buf += encode_context_tagged(3, encode_double(self.exceeded_limit))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[DoubleOutOfRange, int]:
        """Decode inner fields from wire data."""
        ev, offset = _decode_ctx_double(data, offset)
        sf, offset = _decode_sf(data, offset)
        db, offset = _decode_ctx_double(data, offset)
        el, offset = _decode_ctx_double(data, offset)
        return cls(
            exceeding_value=ev,
            status_flags=sf,
            deadband=db,
            exceeded_limit=el,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "double-out-of-range",
            "exceeding_value": self.exceeding_value,
            "status_flags": _sf_dict(self.status_flags),
            "deadband": self.deadband,
            "exceeded_limit": self.exceeded_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DoubleOutOfRange:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            exceeding_value=float(d["exceeding_value"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            deadband=float(d["deadband"]),
            exceeded_limit=float(d["exceeded_limit"]),
        )


# ---------------------------------------------------------------------------
# Variant: SignedOutOfRange (tag 15) -- Clause 13.3.15
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignedOutOfRange:
    """signed-out-of-range notification parameters (Clause 13.3.15).

    Fields:
      [0] exceeding_value Signed
      [1] status_flags    BACnetStatusFlags
      [2] deadband        Unsigned
      [3] exceeded_limit  Signed
    """

    TAG: ClassVar[int] = 15

    exceeding_value: int = 0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    deadband: int = 0
    exceeded_limit: int = 0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_signed(self.exceeding_value))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_unsigned(self.deadband))
        buf += encode_context_tagged(3, encode_signed(self.exceeded_limit))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[SignedOutOfRange, int]:
        """Decode inner fields from wire data."""
        ev, offset = _decode_ctx_signed(data, offset)
        sf, offset = _decode_sf(data, offset)
        db, offset = _decode_ctx_unsigned(data, offset)
        el, offset = _decode_ctx_signed(data, offset)
        return cls(
            exceeding_value=ev,
            status_flags=sf,
            deadband=db,
            exceeded_limit=el,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "signed-out-of-range",
            "exceeding_value": self.exceeding_value,
            "status_flags": _sf_dict(self.status_flags),
            "deadband": self.deadband,
            "exceeded_limit": self.exceeded_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SignedOutOfRange:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            exceeding_value=d["exceeding_value"],
            status_flags=_sf_from_dict(d["status_flags"]),
            deadband=d["deadband"],
            exceeded_limit=d["exceeded_limit"],
        )


# ---------------------------------------------------------------------------
# Variant: UnsignedOutOfRange (tag 16) -- Clause 13.3.16
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnsignedOutOfRange:
    """unsigned-out-of-range notification parameters (Clause 13.3.16).

    Fields:
      [0] exceeding_value Unsigned
      [1] status_flags    BACnetStatusFlags
      [2] deadband        Unsigned
      [3] exceeded_limit  Unsigned
    """

    TAG: ClassVar[int] = 16

    exceeding_value: int = 0
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    deadband: int = 0
    exceeded_limit: int = 0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_unsigned(self.exceeding_value))
        buf += _encode_sf(1, self.status_flags)
        buf += encode_context_tagged(2, encode_unsigned(self.deadband))
        buf += encode_context_tagged(3, encode_unsigned(self.exceeded_limit))
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls,
        data: memoryview,
        offset: int,
    ) -> tuple[UnsignedOutOfRange, int]:
        """Decode inner fields from wire data."""
        ev, offset = _decode_ctx_unsigned(data, offset)
        sf, offset = _decode_sf(data, offset)
        db, offset = _decode_ctx_unsigned(data, offset)
        el, offset = _decode_ctx_unsigned(data, offset)
        return cls(
            exceeding_value=ev,
            status_flags=sf,
            deadband=db,
            exceeded_limit=el,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "unsigned-out-of-range",
            "exceeding_value": self.exceeding_value,
            "status_flags": _sf_dict(self.status_flags),
            "deadband": self.deadband,
            "exceeded_limit": self.exceeded_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> UnsignedOutOfRange:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            exceeding_value=d["exceeding_value"],
            status_flags=_sf_from_dict(d["status_flags"]),
            deadband=d["deadband"],
            exceeded_limit=d["exceeded_limit"],
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfCharacterstring (tag 17) -- Clause 13.3.17
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfCharacterstring:
    """change-of-characterstring notification parameters (Clause 13.3.17).

    Fields:
      [0] changed_value CharacterString
      [1] status_flags  BACnetStatusFlags
      [2] alarm_value   CharacterString
    """

    TAG: ClassVar[int] = 17

    changed_value: str = ""
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    alarm_value: str = ""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += _encode_ctx_charstring(0, self.changed_value)
        buf += _encode_sf(1, self.status_flags)
        buf += _encode_ctx_charstring(2, self.alarm_value)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls,
        data: memoryview,
        offset: int,
    ) -> tuple[ChangeOfCharacterstring, int]:
        """Decode inner fields from wire data."""
        cv, offset = _decode_ctx_charstring(data, offset)
        sf, offset = _decode_sf(data, offset)
        av, offset = _decode_ctx_charstring(data, offset)
        return cls(changed_value=cv, status_flags=sf, alarm_value=av), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-characterstring",
            "changed_value": self.changed_value,
            "status_flags": _sf_dict(self.status_flags),
            "alarm_value": self.alarm_value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfCharacterstring:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            changed_value=d["changed_value"],
            status_flags=_sf_from_dict(d["status_flags"]),
            alarm_value=d["alarm_value"],
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfStatusFlags (tag 18) -- Clause 13.3.18
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfStatusFlags:
    """change-of-status-flags notification parameters (Clause 13.3.18).

    ``present_value`` is ``ABSTRACT-SYNTAX.&Type`` (raw bytes).

    Fields:
      [0] present_value    (raw bytes)
      [1] referenced_flags BACnetStatusFlags
    """

    TAG: ClassVar[int] = 18

    present_value: bytes = b""
    referenced_flags: StatusFlags = field(default_factory=StatusFlags)

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.present_value
        buf += encode_closing_tag(0)
        buf += _encode_sf(1, self.referenced_flags)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls,
        data: memoryview,
        offset: int,
    ) -> tuple[ChangeOfStatusFlags, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        pv, offset = extract_context_value(data, offset, 0)
        sf, offset = _decode_sf(data, offset)
        return cls(present_value=pv, referenced_flags=sf), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-status-flags",
            "present_value": self.present_value.hex(),
            "referenced_flags": _sf_dict(self.referenced_flags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfStatusFlags:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            present_value=bytes.fromhex(d["present_value"]),
            referenced_flags=_sf_from_dict(d["referenced_flags"]),
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfReliability (tag 19) -- Clause 13.3.19
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfReliability:
    """change-of-reliability notification parameters (Clause 13.3.19).

    ``property_values`` is carried as raw bytes.

    Fields:
      [0] reliability      BACnetReliability
      [1] status_flags     BACnetStatusFlags
      [2] property_values  SEQUENCE OF BACnetPropertyValue (raw)
    """

    TAG: ClassVar[int] = 19

    reliability: Reliability = Reliability.NO_FAULT_DETECTED
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    property_values: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_enumerated(0, self.reliability)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_opening_tag(2)
        buf += self.property_values
        buf += encode_closing_tag(2)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls,
        data: memoryview,
        offset: int,
    ) -> tuple[ChangeOfReliability, int]:
        """Decode inner fields from wire data."""
        rel, offset = _decode_ctx_enum(data, offset)
        sf, offset = _decode_sf(data, offset)
        _tag, offset = decode_tag(data, offset)  # opening 2
        pv, offset = extract_context_value(data, offset, 2)
        return cls(
            reliability=Reliability(rel),
            status_flags=sf,
            property_values=pv,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-reliability",
            "reliability": self.reliability.value,
            "status_flags": _sf_dict(self.status_flags),
            "property_values": self.property_values.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfReliability:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            reliability=Reliability(d["reliability"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            property_values=bytes.fromhex(d["property_values"]),
        )


# ---------------------------------------------------------------------------
# Variant: NoneParams (tag 20) -- matches EventType.NONE = 20
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NoneParams:
    """Empty notification parameters for EventType.NONE (tag 20)."""

    TAG: ClassVar[int] = 20

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        return encode_opening_tag(self.TAG) + encode_closing_tag(self.TAG)

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[NoneParams, int]:
        """Decode inner fields from wire data (no fields)."""
        return cls(), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {"type": "none"}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NoneParams:
        """Reconstruct from a JSON-friendly dict."""
        return cls()


# ---------------------------------------------------------------------------
# Variant: ChangeOfDiscreteValue (tag 21) -- Clause 13.3.21
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChangeOfDiscreteValue:
    """change-of-discrete-value notification parameters (Clause 13.3.21).

    ``new_value`` is dependent on object type and carried as raw bytes.

    Fields:
      [0] new_value    CHOICE (raw bytes)
      [1] status_flags BACnetStatusFlags
    """

    TAG: ClassVar[int] = 21

    new_value: bytes = b""
    status_flags: StatusFlags = field(default_factory=StatusFlags)

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.new_value
        buf += encode_closing_tag(0)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls,
        data: memoryview,
        offset: int,
    ) -> tuple[ChangeOfDiscreteValue, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        nv, offset = extract_context_value(data, offset, 0)
        sf, offset = _decode_sf(data, offset)
        return cls(new_value=nv, status_flags=sf), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "change-of-discrete-value",
            "new_value": self.new_value.hex(),
            "status_flags": _sf_dict(self.status_flags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfDiscreteValue:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            new_value=bytes.fromhex(d["new_value"]),
            status_flags=_sf_from_dict(d["status_flags"]),
        )


# ---------------------------------------------------------------------------
# Variant: ChangeOfTimer (tag 22) -- Clause 13.3.22 (new in 2020)
# ---------------------------------------------------------------------------


def _default_unspecified_dt() -> BACnetDateTime:
    """Return a wildcard ``BACnetDateTime`` for default field values."""
    return BACnetDateTime(
        date=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF),
        time=BACnetTime(0xFF, 0xFF, 0xFF, 0xFF),
    )


@dataclass(frozen=True, slots=True)
class ChangeOfTimer:
    """change-of-timer notification parameters (Clause 13.3.22, new in 2020).

    Fields:
      [0] new_state         BACnetTimerState
      [1] status_flags      BACnetStatusFlags
      [2] update_time       BACnetDateTime
      [3] last_state_change BACnetTimerTransition
      [4] initial_timeout   Unsigned (OPTIONAL)
      [5] expiration_time   BACnetDateTime (OPTIONAL)
    """

    TAG: ClassVar[int] = 22

    new_state: TimerState = TimerState.IDLE
    status_flags: StatusFlags = field(default_factory=StatusFlags)
    update_time: BACnetDateTime = field(default_factory=_default_unspecified_dt)
    last_state_change: TimerTransition = TimerTransition.NONE
    initial_timeout: int | None = None
    expiration_time: BACnetDateTime | None = None

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_enumerated(0, self.new_state)
        buf += _encode_sf(1, self.status_flags)
        buf += encode_opening_tag(2)
        buf += encode_date(self.update_time.date)
        buf += encode_time(self.update_time.time)
        buf += encode_closing_tag(2)
        buf += encode_context_enumerated(3, self.last_state_change)
        if self.initial_timeout is not None:
            buf += encode_context_tagged(4, encode_unsigned(self.initial_timeout))
        if self.expiration_time is not None:
            buf += encode_opening_tag(5)
            buf += encode_date(self.expiration_time.date)
            buf += encode_time(self.expiration_time.time)
            buf += encode_closing_tag(5)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[ChangeOfTimer, int]:
        """Decode inner fields from wire data."""
        ns, offset = _decode_ctx_enum(data, offset)
        sf, offset = _decode_sf(data, offset)
        # [2] update_time -- opening tag 2, Date, Time, closing tag 2
        _tag, offset = decode_tag(data, offset)  # opening 2
        dt_date = decode_date(data[offset : offset + 4])
        offset += 4
        dt_time = decode_time(data[offset : offset + 4])
        offset += 4
        _tag, offset = decode_tag(data, offset)  # closing 2
        update_time = BACnetDateTime(date=dt_date, time=dt_time)
        lsc, offset = _decode_ctx_enum(data, offset)
        # [4] optional initial_timeout
        initial_timeout: int | None = None
        if offset < len(data):
            peek_tag, _, _, _ = _peek_tag(data, offset)
            if peek_tag == 4:
                initial_timeout, offset = _decode_ctx_unsigned(data, offset)
        # [5] optional expiration_time
        expiration_time: BACnetDateTime | None = None
        if offset < len(data):
            peek_tag, is_open, _, _ = _peek_tag(data, offset)
            if is_open and peek_tag == 5:
                _tag, offset = decode_tag(data, offset)  # opening 5
                exp_date = decode_date(data[offset : offset + 4])
                offset += 4
                exp_time = decode_time(data[offset : offset + 4])
                offset += 4
                _tag, offset = decode_tag(data, offset)  # closing 5
                expiration_time = BACnetDateTime(date=exp_date, time=exp_time)
        return cls(
            new_state=TimerState(ns),
            status_flags=sf,
            update_time=update_time,
            last_state_change=TimerTransition(lsc),
            initial_timeout=initial_timeout,
            expiration_time=expiration_time,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        d: dict[str, Any] = {
            "type": "change-of-timer",
            "new_state": self.new_state.value,
            "status_flags": _sf_dict(self.status_flags),
            "update_time": self.update_time.to_dict(),
            "last_state_change": self.last_state_change.value,
        }
        if self.initial_timeout is not None:
            d["initial_timeout"] = self.initial_timeout
        if self.expiration_time is not None:
            d["expiration_time"] = self.expiration_time.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeOfTimer:
        """Reconstruct from a JSON-friendly dict."""
        exp = d.get("expiration_time")
        return cls(
            new_state=TimerState(d["new_state"]),
            status_flags=_sf_from_dict(d["status_flags"]),
            update_time=BACnetDateTime.from_dict(d["update_time"]),
            last_state_change=TimerTransition(d["last_state_change"]),
            initial_timeout=d.get("initial_timeout"),
            expiration_time=BACnetDateTime.from_dict(exp) if exp is not None else None,
        )


# ---------------------------------------------------------------------------
# Fallback: RawNotificationParameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawNotificationParameters:
    """Fallback for unknown or reserved notification parameter variants.

    Carries the raw encoded bytes between the CHOICE opening/closing tags.
    Used for reserved tags (6, 7, 12) or vendor-extended tags.
    """

    tag_number: int
    raw_data: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        return (
            encode_opening_tag(self.tag_number)
            + self.raw_data
            + encode_closing_tag(self.tag_number)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "raw",
            "tag_number": self.tag_number,
            "raw_data": self.raw_data.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RawNotificationParameters:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            tag_number=d["tag_number"],
            raw_data=bytes.fromhex(d["raw_data"]),
        )


# ---------------------------------------------------------------------------
# Union type and factory
# ---------------------------------------------------------------------------

NotificationParameters = (
    ChangeOfBitstring
    | ChangeOfState
    | ChangeOfValue
    | CommandFailure
    | FloatingLimit
    | OutOfRange
    | ChangeOfLifeSafety
    | Extended
    | BufferReady
    | UnsignedRange
    | AccessEvent
    | DoubleOutOfRange
    | SignedOutOfRange
    | UnsignedOutOfRange
    | ChangeOfCharacterstring
    | ChangeOfStatusFlags
    | ChangeOfReliability
    | NoneParams
    | ChangeOfDiscreteValue
    | ChangeOfTimer
    | RawNotificationParameters
)

# Dispatch table: context tag number -> decode_inner classmethod
_DECODERS: dict[int, Any] = {
    0: ChangeOfBitstring.decode_inner,
    1: ChangeOfState.decode_inner,
    2: ChangeOfValue.decode_inner,
    3: CommandFailure.decode_inner,
    4: FloatingLimit.decode_inner,
    5: OutOfRange.decode_inner,
    8: ChangeOfLifeSafety.decode_inner,
    9: Extended.decode_inner,
    10: BufferReady.decode_inner,
    11: UnsignedRange.decode_inner,
    13: AccessEvent.decode_inner,
    14: DoubleOutOfRange.decode_inner,
    15: SignedOutOfRange.decode_inner,
    16: UnsignedOutOfRange.decode_inner,
    17: ChangeOfCharacterstring.decode_inner,
    18: ChangeOfStatusFlags.decode_inner,
    19: ChangeOfReliability.decode_inner,
    20: NoneParams.decode_inner,
    21: ChangeOfDiscreteValue.decode_inner,
    22: ChangeOfTimer.decode_inner,
}

# Dispatch table: dict type name -> from_dict classmethod
_FROM_DICT: dict[str, Any] = {
    "change-of-bitstring": ChangeOfBitstring.from_dict,
    "change-of-state": ChangeOfState.from_dict,
    "change-of-value": ChangeOfValue.from_dict,
    "command-failure": CommandFailure.from_dict,
    "floating-limit": FloatingLimit.from_dict,
    "out-of-range": OutOfRange.from_dict,
    "change-of-life-safety": ChangeOfLifeSafety.from_dict,
    "extended": Extended.from_dict,
    "buffer-ready": BufferReady.from_dict,
    "unsigned-range": UnsignedRange.from_dict,
    "access-event": AccessEvent.from_dict,
    "double-out-of-range": DoubleOutOfRange.from_dict,
    "signed-out-of-range": SignedOutOfRange.from_dict,
    "unsigned-out-of-range": UnsignedOutOfRange.from_dict,
    "change-of-characterstring": ChangeOfCharacterstring.from_dict,
    "change-of-status-flags": ChangeOfStatusFlags.from_dict,
    "change-of-reliability": ChangeOfReliability.from_dict,
    "none": NoneParams.from_dict,
    "change-of-discrete-value": ChangeOfDiscreteValue.from_dict,
    "change-of-timer": ChangeOfTimer.from_dict,
    "raw": RawNotificationParameters.from_dict,
}


def decode_notification_parameters(
    data: memoryview | bytes,
    offset: int = 0,
) -> tuple[NotificationParameters, int]:
    """Decode a ``BACnetNotificationParameters`` CHOICE from wire data.

    Reads the opening context tag to determine the variant, dispatches to
    the correct decoder, then consumes the closing context tag.

    :param data: Buffer containing the encoded CHOICE.
    :param offset: Starting position in the buffer.
    :returns: Tuple of (decoded variant, new offset past the closing tag).
    """
    data = as_memoryview(data)
    tag, offset = decode_tag(data, offset)
    if not tag.is_opening:
        msg = f"Expected opening tag for NotificationParameters, got tag {tag}"
        raise ValueError(msg)
    choice_tag = tag.number

    decoder = _DECODERS.get(choice_tag)
    if decoder is None:
        raw, offset = extract_context_value(data, offset, choice_tag)
        return RawNotificationParameters(tag_number=choice_tag, raw_data=raw), offset

    result, offset = decoder(data, offset)

    closing, offset = decode_tag(data, offset)
    if not closing.is_closing or closing.number != choice_tag:
        msg = (
            f"Expected closing tag {choice_tag} for NotificationParameters, "
            f"got tag {closing.number} (closing={closing.is_closing})"
        )
        raise ValueError(msg)
    return result, offset


def notification_parameters_from_dict(d: dict[str, Any]) -> NotificationParameters:
    """Reconstruct a ``NotificationParameters`` variant from a dictionary.

    :param d: Dictionary with a ``"type"`` field identifying the variant.
    :returns: The reconstructed variant instance.
    :raises ValueError: If the type is not recognised.
    """
    type_name = d.get("type", "")
    factory = _FROM_DICT.get(type_name)
    if factory is None:
        msg = f"Unknown NotificationParameters type: {type_name!r}"
        raise ValueError(msg)
    result: NotificationParameters = factory(d)
    return result
