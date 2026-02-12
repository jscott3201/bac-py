"""BACnetFaultParameter CHOICE type per ASHRAE 135-2020 Clause 13.4.

Each variant is a frozen dataclass identified by its context tag number.
A factory function :func:`decode_fault_parameter` dispatches to the correct
variant based on the opening context tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_double,
    decode_real,
    decode_signed,
    decode_unsigned,
    encode_application_character_string,
    encode_application_enumerated,
    encode_application_null,
    encode_context_tagged,
    encode_double,
    encode_real,
    encode_signed,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    extract_context_value,
)
from bac_py.types.constructed import BACnetDeviceObjectPropertyReference
from bac_py.types.enums import LifeSafetyMode, LifeSafetyState, ObjectType
from bac_py.types.primitives import ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_ctx_unsigned(data: memoryview, offset: int) -> tuple[int, int]:
    """Decode a context-tagged unsigned integer."""
    tag, offset = decode_tag(data, offset)
    val = decode_unsigned(data[offset : offset + tag.length])
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


def _decode_ctx_signed(data: memoryview, offset: int) -> tuple[int, int]:
    """Decode a context-tagged signed integer."""
    tag, offset = decode_tag(data, offset)
    val = decode_signed(data[offset : offset + tag.length])
    offset += tag.length
    return val, offset


def _peek_tag(data: memoryview, offset: int) -> tuple[int, bool, bool, int]:
    """Peek at the next tag without consuming content.

    Returns ``(tag_number, is_opening, is_closing, offset_after_tag)``.
    """
    tag, new_offset = decode_tag(data, offset)
    return tag.number, tag.is_opening, tag.is_closing, new_offset


# ---------------------------------------------------------------------------
# Variant: FaultNone (tag 0) -- Clause 13.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultNone:
    """fault-none parameter (Clause 13.4).

    Represents the ``none`` variant of BACnetFaultParameter.
    Carries no fields -- encoded as ``[0] NULL``.
    """

    TAG: ClassVar[int] = 0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_application_null()
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(cls, data: memoryview, offset: int) -> tuple[FaultNone, int]:
        """Decode inner fields from wire data."""
        # Consume the application-tagged NULL
        _tag, offset = decode_tag(data, offset)
        return cls(), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {"type": "fault-none"}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultNone:
        """Reconstruct from a JSON-friendly dict."""
        return cls()


# ---------------------------------------------------------------------------
# Variant: FaultCharacterString (tag 1) -- Clause 13.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultCharacterString:
    """fault-characterstring parameter (Clause 13.4).

    Fields:
      [0] list-of-fault-values  SEQUENCE OF CharacterString
    """

    TAG: ClassVar[int] = 1

    fault_values: tuple[str, ...] = ()

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        for s in self.fault_values:
            buf += encode_application_character_string(s)
        buf += encode_closing_tag(0)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultCharacterString, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        values: list[str] = []
        while offset < len(data):
            tag_num, _is_open, is_close, _ = _peek_tag(data, offset)
            if is_close and tag_num == 0:
                break
            tag, offset = decode_tag(data, offset)
            val = decode_character_string(data[offset : offset + tag.length])
            offset += tag.length
            values.append(val)
        _closing, offset = decode_tag(data, offset)  # closing 0
        return cls(fault_values=tuple(values)), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-characterstring",
            "fault_values": list(self.fault_values),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultCharacterString:
        """Reconstruct from a JSON-friendly dict."""
        return cls(fault_values=tuple(d["fault_values"]))


# ---------------------------------------------------------------------------
# Variant: FaultExtended (tag 2) -- Clause 13.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultExtended:
    """fault-extended parameter (Clause 13.4).

    Fields:
      [0] vendor-id           Unsigned16
      [1] extended-fault-type Unsigned
      [2] parameters          SEQUENCE OF ... (raw bytes)
    """

    TAG: ClassVar[int] = 2

    vendor_id: int = 0
    extended_fault_type: int = 0
    parameters: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_context_tagged(0, encode_unsigned(self.vendor_id))
        buf += encode_context_tagged(1, encode_unsigned(self.extended_fault_type))
        buf += encode_opening_tag(2)
        buf += self.parameters
        buf += encode_closing_tag(2)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultExtended, int]:
        """Decode inner fields from wire data."""
        vid, offset = _decode_ctx_unsigned(data, offset)
        eft, offset = _decode_ctx_unsigned(data, offset)
        _tag, offset = decode_tag(data, offset)  # opening 2
        params, offset = extract_context_value(data, offset, 2)
        return cls(
            vendor_id=vid, extended_fault_type=eft, parameters=params
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-extended",
            "vendor_id": self.vendor_id,
            "extended_fault_type": self.extended_fault_type,
            "parameters": self.parameters.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultExtended:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            vendor_id=d["vendor_id"],
            extended_fault_type=d["extended_fault_type"],
            parameters=bytes.fromhex(d["parameters"]),
        )


# ---------------------------------------------------------------------------
# Variant: FaultLifeSafety (tag 3) -- Clause 13.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultLifeSafety:
    """fault-life-safety parameter (Clause 13.4).

    Fields:
      [0] list-of-fault-values SEQUENCE OF BACnetLifeSafetyState
      [1] list-of-mode-values  SEQUENCE OF BACnetLifeSafetyMode
    """

    TAG: ClassVar[int] = 3

    fault_values: tuple[LifeSafetyState, ...] = ()
    mode_values: tuple[LifeSafetyMode, ...] = ()

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        for v in self.fault_values:
            buf += encode_application_enumerated(v)
        buf += encode_closing_tag(0)
        buf += encode_opening_tag(1)
        for m in self.mode_values:
            buf += encode_application_enumerated(m)
        buf += encode_closing_tag(1)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultLifeSafety, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        fault_vals: list[LifeSafetyState] = []
        while offset < len(data):
            tag_num, _is_open, is_close, _ = _peek_tag(data, offset)
            if is_close and tag_num == 0:
                break
            tag, offset = decode_tag(data, offset)
            val = decode_unsigned(data[offset : offset + tag.length])
            offset += tag.length
            fault_vals.append(LifeSafetyState(val))
        _closing, offset = decode_tag(data, offset)  # closing 0

        _tag, offset = decode_tag(data, offset)  # opening 1
        mode_vals: list[LifeSafetyMode] = []
        while offset < len(data):
            tag_num, _is_open, is_close, _ = _peek_tag(data, offset)
            if is_close and tag_num == 1:
                break
            tag, offset = decode_tag(data, offset)
            val = decode_unsigned(data[offset : offset + tag.length])
            offset += tag.length
            mode_vals.append(LifeSafetyMode(val))
        _closing, offset = decode_tag(data, offset)  # closing 1

        return cls(
            fault_values=tuple(fault_vals),
            mode_values=tuple(mode_vals),
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-life-safety",
            "fault_values": [v.value for v in self.fault_values],
            "mode_values": [m.value for m in self.mode_values],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultLifeSafety:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            fault_values=tuple(LifeSafetyState(v) for v in d["fault_values"]),
            mode_values=tuple(LifeSafetyMode(m) for m in d["mode_values"]),
        )


# ---------------------------------------------------------------------------
# Variant: FaultState (tag 4) -- Clause 13.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultState:
    """fault-state parameter (Clause 13.4).

    ``fault_values`` is carried as raw bytes because ``BACnetPropertyStates``
    is a large CHOICE type with 40+ variants.

    Fields:
      [0] list-of-fault-values SEQUENCE OF BACnetPropertyStates (raw bytes)
    """

    TAG: ClassVar[int] = 4

    fault_values: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.fault_values
        buf += encode_closing_tag(0)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultState, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        raw, offset = extract_context_value(data, offset, 0)
        return cls(fault_values=raw), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-state",
            "fault_values": self.fault_values.hex(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultState:
        """Reconstruct from a JSON-friendly dict."""
        return cls(fault_values=bytes.fromhex(d["fault_values"]))


# ---------------------------------------------------------------------------
# Variant: FaultStatusFlags (tag 5) -- Clause 13.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaultStatusFlags:
    """fault-status-flags parameter (Clause 13.4).

    Fields:
      [0] status-flags-reference BACnetDeviceObjectPropertyReference
    """

    TAG: ClassVar[int] = 5

    status_flags_ref: BACnetDeviceObjectPropertyReference = field(
        default_factory=lambda: BACnetDeviceObjectPropertyReference(
            object_identifier=_default_obj_id(),
            property_identifier=0,
        )
    )

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.status_flags_ref.encode()
        buf += encode_closing_tag(0)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultStatusFlags, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        ref, offset = BACnetDeviceObjectPropertyReference.decode(data, offset)
        _closing, offset = decode_tag(data, offset)  # closing 0
        return cls(status_flags_ref=ref), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-status-flags",
            "status_flags_ref": self.status_flags_ref.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultStatusFlags:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            status_flags_ref=BACnetDeviceObjectPropertyReference.from_dict(
                d["status_flags_ref"]
            ),
        )


# ---------------------------------------------------------------------------
# Variant: FaultOutOfRange (tag 6) -- Clause 13.4
# ---------------------------------------------------------------------------


_CHOICE_REAL = 0
_CHOICE_UNSIGNED = 1
_CHOICE_DOUBLE = 2
_CHOICE_INTEGER = 3

_CHOICE_NAMES: dict[int, str] = {
    _CHOICE_REAL: "real",
    _CHOICE_UNSIGNED: "unsigned",
    _CHOICE_DOUBLE: "double",
    _CHOICE_INTEGER: "integer",
}

_CHOICE_FROM_NAME: dict[str, int] = {v: k for k, v in _CHOICE_NAMES.items()}


def _encode_range_value(choice: int, value: float | int) -> bytes:
    """Encode a min/max normal value CHOICE element."""
    if choice == _CHOICE_REAL:
        return encode_context_tagged(0, encode_real(float(value)))
    if choice == _CHOICE_UNSIGNED:
        return encode_context_tagged(1, encode_unsigned(int(value)))
    if choice == _CHOICE_DOUBLE:
        return encode_context_tagged(2, encode_double(float(value)))
    # _CHOICE_INTEGER
    return encode_context_tagged(3, encode_signed(int(value)))


def _decode_range_value(
    data: memoryview, offset: int
) -> tuple[float | int, int, int]:
    """Decode a min/max normal value CHOICE element.

    Returns ``(value, choice, new_offset)``.
    """
    tag, new_offset = decode_tag(data, offset)
    if tag.number == _CHOICE_REAL:
        val: float | int = decode_real(data[new_offset : new_offset + tag.length])
        return val, _CHOICE_REAL, new_offset + tag.length
    if tag.number == _CHOICE_UNSIGNED:
        val = decode_unsigned(data[new_offset : new_offset + tag.length])
        return val, _CHOICE_UNSIGNED, new_offset + tag.length
    if tag.number == _CHOICE_DOUBLE:
        val = decode_double(data[new_offset : new_offset + tag.length])
        return val, _CHOICE_DOUBLE, new_offset + tag.length
    # _CHOICE_INTEGER
    val = decode_signed(data[new_offset : new_offset + tag.length])
    return val, _CHOICE_INTEGER, new_offset + tag.length


@dataclass(frozen=True, slots=True)
class FaultOutOfRange:
    """fault-out-of-range parameter (Clause 13.4).

    The min/max normal value each have an inner CHOICE:
      [0] real, [1] unsigned, [2] double, [3] integer.

    Fields:
      [0] min-normal-value  CHOICE { real [0], unsigned [1], double [2], integer [3] }
      [1] max-normal-value  CHOICE { real [0], unsigned [1], double [2], integer [3] }
    """

    TAG: ClassVar[int] = 6

    min_normal_value: float | int = 0.0
    max_normal_value: float | int = 0.0
    min_choice: int = 0
    max_choice: int = 0

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += _encode_range_value(self.min_choice, self.min_normal_value)
        buf += encode_closing_tag(0)
        buf += encode_opening_tag(1)
        buf += _encode_range_value(self.max_choice, self.max_normal_value)
        buf += encode_closing_tag(1)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultOutOfRange, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        min_val, min_ch, offset = _decode_range_value(data, offset)
        _closing, offset = decode_tag(data, offset)  # closing 0
        _tag, offset = decode_tag(data, offset)  # opening 1
        max_val, max_ch, offset = _decode_range_value(data, offset)
        _closing, offset = decode_tag(data, offset)  # closing 1
        return cls(
            min_normal_value=min_val,
            max_normal_value=max_val,
            min_choice=min_ch,
            max_choice=max_ch,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-out-of-range",
            "min_normal_value": self.min_normal_value,
            "max_normal_value": self.max_normal_value,
            "min_choice": _CHOICE_NAMES.get(self.min_choice, "real"),
            "max_choice": _CHOICE_NAMES.get(self.max_choice, "real"),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultOutOfRange:
        """Reconstruct from a JSON-friendly dict."""
        min_ch = _CHOICE_FROM_NAME.get(d.get("min_choice", "real"), _CHOICE_REAL)
        max_ch = _CHOICE_FROM_NAME.get(d.get("max_choice", "real"), _CHOICE_REAL)
        min_val: float | int = d["min_normal_value"]
        max_val: float | int = d["max_normal_value"]
        return cls(
            min_normal_value=min_val,
            max_normal_value=max_val,
            min_choice=min_ch,
            max_choice=max_ch,
        )


# ---------------------------------------------------------------------------
# Variant: FaultListed (tag 7) -- Clause 13.4
# ---------------------------------------------------------------------------


def _default_obj_id() -> ObjectIdentifier:
    """Return a default ObjectIdentifier for field defaults."""
    return ObjectIdentifier(ObjectType(0), 0)


@dataclass(frozen=True, slots=True)
class FaultListed:
    """fault-listed parameter (Clause 13.4).

    Fields:
      [0] fault-list-reference BACnetDeviceObjectPropertyReference
    """

    TAG: ClassVar[int] = 7

    fault_list_ref: BACnetDeviceObjectPropertyReference = field(
        default_factory=lambda: BACnetDeviceObjectPropertyReference(
            object_identifier=_default_obj_id(),
            property_identifier=0,
        )
    )

    def encode(self) -> bytes:
        """Encode to wire format with CHOICE opening/closing tags."""
        buf = encode_opening_tag(self.TAG)
        buf += encode_opening_tag(0)
        buf += self.fault_list_ref.encode()
        buf += encode_closing_tag(0)
        buf += encode_closing_tag(self.TAG)
        return buf

    @classmethod
    def decode_inner(
        cls, data: memoryview, offset: int
    ) -> tuple[FaultListed, int]:
        """Decode inner fields from wire data."""
        _tag, offset = decode_tag(data, offset)  # opening 0
        ref, offset = BACnetDeviceObjectPropertyReference.decode(data, offset)
        _closing, offset = decode_tag(data, offset)  # closing 0
        return cls(fault_list_ref=ref), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "type": "fault-listed",
            "fault_list_ref": self.fault_list_ref.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FaultListed:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            fault_list_ref=BACnetDeviceObjectPropertyReference.from_dict(
                d["fault_list_ref"]
            ),
        )


# ---------------------------------------------------------------------------
# Union type and factory
# ---------------------------------------------------------------------------

FaultParameter = (
    FaultNone
    | FaultCharacterString
    | FaultExtended
    | FaultLifeSafety
    | FaultState
    | FaultStatusFlags
    | FaultOutOfRange
    | FaultListed
)

# Dispatch table: context tag number -> decode_inner classmethod
_DECODERS: dict[int, Any] = {
    0: FaultNone.decode_inner,
    1: FaultCharacterString.decode_inner,
    2: FaultExtended.decode_inner,
    3: FaultLifeSafety.decode_inner,
    4: FaultState.decode_inner,
    5: FaultStatusFlags.decode_inner,
    6: FaultOutOfRange.decode_inner,
    7: FaultListed.decode_inner,
}

# Dispatch table: dict type name -> from_dict classmethod
_FROM_DICT: dict[str, Any] = {
    "fault-none": FaultNone.from_dict,
    "fault-characterstring": FaultCharacterString.from_dict,
    "fault-extended": FaultExtended.from_dict,
    "fault-life-safety": FaultLifeSafety.from_dict,
    "fault-state": FaultState.from_dict,
    "fault-status-flags": FaultStatusFlags.from_dict,
    "fault-out-of-range": FaultOutOfRange.from_dict,
    "fault-listed": FaultListed.from_dict,
}


def decode_fault_parameter(
    data: memoryview | bytes,
    offset: int = 0,
) -> tuple[FaultParameter, int]:
    """Decode a ``BACnetFaultParameter`` CHOICE from wire data.

    Reads the opening context tag to determine the variant, dispatches to
    the correct decoder, then consumes the closing context tag.

    :param data: Buffer containing the encoded CHOICE.
    :param offset: Starting position in the buffer.
    :returns: Tuple of (decoded variant, new offset past the closing tag).
    :raises ValueError: If the opening tag is missing or the tag number is
        not recognised.
    """
    data = as_memoryview(data)
    tag, offset = decode_tag(data, offset)
    if not tag.is_opening:
        msg = f"Expected opening tag for FaultParameter, got tag {tag}"
        raise ValueError(msg)
    choice_tag = tag.number

    decoder = _DECODERS.get(choice_tag)
    if decoder is None:
        msg = f"Unknown FaultParameter choice tag: {choice_tag}"
        raise ValueError(msg)

    result, offset = decoder(data, offset)

    closing, offset = decode_tag(data, offset)
    if not closing.is_closing or closing.number != choice_tag:
        msg = (
            f"Expected closing tag {choice_tag} for FaultParameter, "
            f"got tag {closing.number} (closing={closing.is_closing})"
        )
        raise ValueError(msg)
    return result, offset


def fault_parameter_from_dict(d: dict[str, Any]) -> FaultParameter:
    """Reconstruct a ``FaultParameter`` variant from a dictionary.

    :param d: Dictionary with a ``"type"`` field identifying the variant.
    :returns: The reconstructed variant instance.
    :raises ValueError: If the type is not recognised.
    """
    type_name = d.get("type", "")
    factory = _FROM_DICT.get(type_name)
    if factory is None:
        msg = f"Unknown FaultParameter type: {type_name!r}"
        raise ValueError(msg)
    result: FaultParameter = factory(d)
    return result
