"""BACnet primitive data types per ASHRAE 135-2016 Clause 20.2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bac_py.types.enums import ObjectType

if TYPE_CHECKING:
    from enum import IntEnum


def _enum_name(member: IntEnum) -> str:
    """Convert UPPER_SNAKE enum name to lower-hyphen form."""
    return member.name.lower().replace("_", "-")


def _enum_from_dict(enum_cls: type[IntEnum], data: int | str | dict[str, Any]) -> IntEnum:
    """Reconstruct an enum from its JSON representation.

    Accepts:
        data: int (raw numeric value), str (hyphenated name), or
            dict with ``{"value": int, "name": str}``.

    Returns:
        The corresponding enum member.
    """
    if isinstance(data, int):
        return enum_cls(data)
    if isinstance(data, str):
        name = data.upper().replace("-", "_")
        return enum_cls[name]
    if isinstance(data, dict):
        return enum_cls(data["value"])
    msg = f"Cannot convert {data!r} to {enum_cls.__name__}"
    raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ObjectIdentifier:
    """BACnet Object Identifier - 10-bit type, 22-bit instance."""

    object_type: ObjectType
    instance_number: int

    def __post_init__(self) -> None:
        if not 0 <= self.instance_number <= 0x3FFFFF:
            msg = f"Instance number must be 0-4194303, got {self.instance_number}"
            raise ValueError(msg)

    def encode(self) -> bytes:
        """Encode to 4-byte wire format."""
        value = (int(self.object_type) << 22) | (self.instance_number & 0x3FFFFF)
        return value.to_bytes(4, "big")

    @classmethod
    def decode(cls, data: bytes | memoryview) -> ObjectIdentifier:
        """Decode from 4-byte wire format."""
        value = int.from_bytes(data[:4], "big")
        return cls(
            object_type=ObjectType(value >> 22),
            instance_number=value & 0x3FFFFF,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {
            "object_type": _enum_name(self.object_type),
            "instance": self.instance_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectIdentifier:
        """Reconstruct from a JSON-friendly dict."""
        obj_type = _enum_from_dict(ObjectType, data["object_type"])
        if not isinstance(obj_type, ObjectType):
            msg = f"Expected ObjectType, got {type(obj_type).__name__}"
            raise TypeError(msg)
        return cls(
            object_type=obj_type,
            instance_number=data["instance"],
        )


@dataclass(frozen=True, slots=True)
class BACnetDate:
    """BACnet Date: year, month, day, day_of_week.

    ``0xFF`` indicates an unspecified (wildcard) field.
    Year is stored as the actual year (e.g. 2024), but encoded on the
    wire as year - 1900.
    """

    year: int
    month: int
    day: int
    day_of_week: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict with wildcards as None."""
        return {
            "year": None if self.year == 0xFF else self.year,
            "month": None if self.month == 0xFF else self.month,
            "day": None if self.day == 0xFF else self.day,
            "day_of_week": None if self.day_of_week == 0xFF else self.day_of_week,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDate:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            year=0xFF if data["year"] is None else data["year"],
            month=0xFF if data["month"] is None else data["month"],
            day=0xFF if data["day"] is None else data["day"],
            day_of_week=0xFF if data["day_of_week"] is None else data["day_of_week"],
        )


@dataclass(frozen=True, slots=True)
class BACnetTime:
    """BACnet Time: hour, minute, second, hundredth.

    ``0xFF`` indicates an unspecified (wildcard) field.
    """

    hour: int
    minute: int
    second: int
    hundredth: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict with wildcards as None."""
        return {
            "hour": None if self.hour == 0xFF else self.hour,
            "minute": None if self.minute == 0xFF else self.minute,
            "second": None if self.second == 0xFF else self.second,
            "hundredth": None if self.hundredth == 0xFF else self.hundredth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetTime:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            hour=0xFF if data["hour"] is None else data["hour"],
            minute=0xFF if data["minute"] is None else data["minute"],
            second=0xFF if data["second"] is None else data["second"],
            hundredth=0xFF if data["hundredth"] is None else data["hundredth"],
        )


class BACnetDouble(float):
    """Sentinel type to distinguish Double (64-bit) from Real (32-bit) encoding.

    BACnet properties like LargeAnalogValue Present_Value are specified as
    Double (IEEE-754 64-bit, Application tag 5) per Clause 12.42.  Since
    Python ``float`` is always 64-bit internally, we use this subclass as a
    marker so ``encode_property_value`` can emit the correct wire tag.
    """


class BitString:
    """BACnet Bit String with named-bit support.

    Stores raw bit data with an unused-bits count for the trailing byte.
    """

    __slots__ = ("_data", "_unused_bits")

    def __init__(self, value: bytes, unused_bits: int = 0) -> None:
        """Initialise a BitString.

        Args:
            value: Raw bytes containing the bit data.
            unused_bits: Number of unused trailing bits in the last byte
                (0-7).  Must be 0 when *value* is empty.
        """
        self._data = value
        self._unused_bits = unused_bits

    @property
    def data(self) -> bytes:
        """Raw byte data."""
        return self._data

    @property
    def unused_bits(self) -> int:
        """Number of unused bits in the last byte."""
        return self._unused_bits

    def __len__(self) -> int:
        """Total number of significant bits."""
        return len(self._data) * 8 - self._unused_bits

    def __getitem__(self, index: int) -> bool:
        """Get the bit at the given index (MSB-first within each byte)."""
        if index < 0 or index >= len(self):
            msg = f"Bit index {index} out of range for BitString of length {len(self)}"
            raise IndexError(msg)
        byte_index = index // 8
        bit_index = 7 - (index % 8)
        return bool(self._data[byte_index] & (1 << bit_index))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BitString):
            return NotImplemented
        return self._data == other._data and self._unused_bits == other._unused_bits

    def __hash__(self) -> int:
        return hash((self._data, self._unused_bits))

    def __repr__(self) -> str:
        bits = "".join("1" if self[i] else "0" for i in range(len(self)))
        return f"BitString({bits!r})"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        total_bits = len(self)
        return {
            "bits": [self[i] for i in range(total_bits)],
            "unused_bits": self._unused_bits,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BitString:
        """Reconstruct from a JSON-friendly dict."""
        bits: list[bool] = data["bits"]
        unused = data.get("unused_bits", 0)
        byte_count = (len(bits) + 7) // 8
        result = bytearray(byte_count)
        for i, bit in enumerate(bits):
            if bit:
                result[i // 8] |= 1 << (7 - (i % 8))
        return cls(bytes(result), unused)
