"""BACnet primitive data types per ASHRAE 135-2016 Clause 20.2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bac_py.types.enums import ObjectType

if TYPE_CHECKING:
    from enum import IntEnum


def _enum_name(member: IntEnum) -> str:
    """Convert UPPER_SNAKE enum name to lower-hyphen form.

    :param member: An :class:`~enum.IntEnum` member.
    :returns: Lowercased, hyphen-separated name string.
    """
    return member.name.lower().replace("_", "-")


def _enum_from_dict(enum_cls: type[IntEnum], data: int | str | dict[str, Any]) -> IntEnum:
    """Reconstruct an enum member from its JSON representation.

    Accepts an integer (raw numeric value), a string (hyphenated name),
    or a dictionary with ``{"value": int, "name": str}``.

    :param enum_cls: The :class:`~enum.IntEnum` subclass to reconstruct.
    :param data: Serialized enum value in any of the accepted formats.
    :returns: The corresponding enum member.
    :raises ValueError: If *data* cannot be converted to a member of *enum_cls*.
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
    """BACnet Object Identifier -- 10-bit type, 22-bit instance (Clause 20.2.14).

    Uniquely identifies a BACnet object within a device by combining
    an :class:`~bac_py.types.enums.ObjectType` with an instance number.
    """

    object_type: ObjectType
    """The object type (10-bit, 0--1023)."""

    instance_number: int
    """The instance number (22-bit, 0--4194303)."""

    def __post_init__(self) -> None:
        if not 0 <= int(self.object_type) <= 1023:
            msg = f"Object type must be 0-1023 (10-bit), got {int(self.object_type)}"
            raise ValueError(msg)
        if not 0 <= self.instance_number <= 0x3FFFFF:
            msg = f"Instance number must be 0-4194303, got {self.instance_number}"
            raise ValueError(msg)

    def encode(self) -> bytes:
        """Encode to the 4-byte BACnet wire format.

        The 32-bit value is composed as ``(object_type << 22) | instance_number``,
        encoded big-endian.

        :returns: 4-byte encoded object identifier.
        """
        value = (int(self.object_type) << 22) | (self.instance_number & 0x3FFFFF)
        return value.to_bytes(4, "big")

    @classmethod
    def decode(cls, data: bytes | memoryview) -> ObjectIdentifier:
        """Decode from the 4-byte BACnet wire format.

        :param data: At least 4 bytes of wire data.
        :returns: Decoded :class:`ObjectIdentifier` instance.
        """
        value = int.from_bytes(data[:4], "big")
        return cls(
            object_type=ObjectType(value >> 22),
            instance_number=value & 0x3FFFFF,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"object_type"`` (hyphenated name) and
            ``"instance"`` keys.
        """
        return {
            "object_type": _enum_name(self.object_type),
            "instance": self.instance_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectIdentifier:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"object_type"`` and ``"instance"`` keys.
        :returns: Decoded :class:`ObjectIdentifier` instance.
        :raises TypeError: If the resolved type is not an
            :class:`~bac_py.types.enums.ObjectType`.
        """
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
    """BACnet Date -- year, month, day, day_of_week (Clause 20.2.12).

    ``0xFF`` indicates an unspecified (wildcard) field. Year is stored as
    the actual year (e.g. 2024), but encoded on the wire as ``year - 1900``.
    """

    year: int
    """Calendar year (e.g. 2024), or ``0xFF`` for unspecified."""

    month: int
    """Month (1--12), or ``0xFF`` for unspecified."""

    day: int
    """Day of month (1--31), or ``0xFF`` for unspecified."""

    day_of_week: int
    """Day of week (1 = Monday ... 7 = Sunday), or ``0xFF`` for unspecified."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        Wildcard values (``0xFF``) are represented as ``None``.

        :returns: Dictionary mapping field names to values or ``None``.
        """
        return {
            "year": None if self.year == 0xFF else self.year,
            "month": None if self.month == 0xFF else self.month,
            "day": None if self.day == 0xFF else self.day,
            "day_of_week": None if self.day_of_week == 0xFF else self.day_of_week,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDate:
        """Reconstruct from a JSON-friendly dictionary.

        ``None`` values are converted back to ``0xFF`` wildcards.

        :param data: Dictionary with ``"year"``, ``"month"``, ``"day"``, and
            ``"day_of_week"`` keys.
        :returns: Decoded :class:`BACnetDate` instance.
        """
        return cls(
            year=0xFF if data["year"] is None else data["year"],
            month=0xFF if data["month"] is None else data["month"],
            day=0xFF if data["day"] is None else data["day"],
            day_of_week=0xFF if data["day_of_week"] is None else data["day_of_week"],
        )


@dataclass(frozen=True, slots=True)
class BACnetTime:
    """BACnet Time -- hour, minute, second, hundredth (Clause 20.2.13).

    ``0xFF`` indicates an unspecified (wildcard) field.
    """

    hour: int
    """Hour (0--23), or ``0xFF`` for unspecified."""

    minute: int
    """Minute (0--59), or ``0xFF`` for unspecified."""

    second: int
    """Second (0--59), or ``0xFF`` for unspecified."""

    hundredth: int
    """Hundredths of a second (0--99), or ``0xFF`` for unspecified."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        Wildcard values (``0xFF``) are represented as ``None``.

        :returns: Dictionary mapping field names to values or ``None``.
        """
        return {
            "hour": None if self.hour == 0xFF else self.hour,
            "minute": None if self.minute == 0xFF else self.minute,
            "second": None if self.second == 0xFF else self.second,
            "hundredth": None if self.hundredth == 0xFF else self.hundredth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetTime:
        """Reconstruct from a JSON-friendly dictionary.

        ``None`` values are converted back to ``0xFF`` wildcards.

        :param data: Dictionary with ``"hour"``, ``"minute"``, ``"second"``, and
            ``"hundredth"`` keys.
        :returns: Decoded :class:`BACnetTime` instance.
        """
        return cls(
            hour=0xFF if data["hour"] is None else data["hour"],
            minute=0xFF if data["minute"] is None else data["minute"],
            second=0xFF if data["second"] is None else data["second"],
            hundredth=0xFF if data["hundredth"] is None else data["hundredth"],
        )


class BACnetDouble(float):
    """Sentinel type to distinguish Double (64-bit) from Real (32-bit) encoding.

    BACnet properties like LargeAnalogValue Present_Value are specified as
    Double (IEEE-754 64-bit, Application tag 5) per Clause 12.42. Since
    Python ``float`` is always 64-bit internally, this subclass serves as a
    marker so ``encode_property_value`` can emit the correct wire tag.
    """


class BitString:
    """BACnet Bit String with named-bit support (Clause 20.2.10).

    Stores raw bit data as bytes with an unused-bits count for the
    trailing byte. Provides indexed access to individual bits using
    MSB-first ordering within each byte.
    """

    __slots__ = ("_data", "_unused_bits")

    def __init__(self, value: bytes, unused_bits: int = 0) -> None:
        """Initialise a BitString.

        :param value: Raw bytes containing the bit data.
        :param unused_bits: Number of unused trailing bits in the last byte
            (0--7). Must be 0 when *value* is empty.
        :raises ValueError: If *unused_bits* is out of range or non-zero
            with empty *value*.
        """
        if not 0 <= unused_bits <= 7:
            msg = f"unused_bits must be 0-7, got {unused_bits}"
            raise ValueError(msg)
        if len(value) == 0 and unused_bits != 0:
            msg = "unused_bits must be 0 when data is empty"
            raise ValueError(msg)
        self._data = value
        self._unused_bits = unused_bits

    @property
    def data(self) -> bytes:
        """Raw byte data backing this bit string."""
        return self._data

    @property
    def unused_bits(self) -> int:
        """Number of unused trailing bits in the last byte (0--7)."""
        return self._unused_bits

    def __len__(self) -> int:
        """Return the total number of significant bits."""
        return len(self._data) * 8 - self._unused_bits

    def __getitem__(self, index: int) -> bool:
        """Get the bit value at *index* (MSB-first within each byte).

        :param index: Zero-based bit index.
        :returns: ``True`` if the bit is set, ``False`` otherwise.
        :raises IndexError: If *index* is out of range.
        """
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
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"bits"`` (list of booleans) and
            ``"unused_bits"`` keys.
        """
        total_bits = len(self)
        return {
            "bits": [self[i] for i in range(total_bits)],
            "unused_bits": self._unused_bits,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BitString:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"bits"`` (list of booleans) and
            optionally ``"unused_bits"`` keys.
        :returns: Decoded :class:`BitString` instance.
        """
        bits: list[bool] = data["bits"]
        unused = data.get("unused_bits", 0)
        byte_count = (len(bits) + 7) // 8
        result = bytearray(byte_count)
        for i, bit in enumerate(bits):
            if bit:
                result[i // 8] |= 1 << (7 - (i % 8))
        return cls(bytes(result), unused)
