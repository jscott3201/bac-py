"""BACnet constructed data types per ASHRAE 135-2020."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.types.enums import LightingOperation


@dataclass(frozen=True, slots=True)
class StatusFlags:
    """BACnet StatusFlags bit string (Clause 12.50, BACnetStatusFlags).

    Four Boolean flags indicating the health of an object. Maps to a
    4-bit BACnet BitString where bit 0 is IN_ALARM, bit 1 is FAULT,
    bit 2 is OVERRIDDEN, and bit 3 is OUT_OF_SERVICE.
    """

    in_alarm: bool = False
    """``True`` when the object is in an alarm state."""

    fault: bool = False
    """``True`` when the object has a fault condition."""

    overridden: bool = False
    """``True`` when the object value has been overridden."""

    out_of_service: bool = False
    """``True`` when the object is out of service."""

    def to_bit_string(self) -> BitString:
        """Encode as a BACnet BitString with 4 significant bits.

        :returns: A :class:`~bac_py.types.primitives.BitString` representing
            the four status flags.
        """
        value = (
            (self.in_alarm << 3) | (self.fault << 2) | (self.overridden << 1) | self.out_of_service
        )
        return BitString(bytes([value << 4]), unused_bits=4)

    @classmethod
    def from_bit_string(cls, bs: BitString) -> StatusFlags:
        """Decode from a BACnet BitString.

        :param bs: A BitString containing at least 4 significant bits.
        :returns: Decoded :class:`StatusFlags` instance.
        """
        return cls(
            in_alarm=bs[0] if len(bs) > 0 else False,
            fault=bs[1] if len(bs) > 1 else False,
            overridden=bs[2] if len(bs) > 2 else False,
            out_of_service=bs[3] if len(bs) > 3 else False,
        )

    def to_dict(self) -> dict[str, bool]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary mapping flag names to boolean values.
        """
        return {
            "in_alarm": self.in_alarm,
            "fault": self.fault,
            "overridden": self.overridden,
            "out_of_service": self.out_of_service,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusFlags:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with boolean values keyed by flag name.
        :returns: Decoded :class:`StatusFlags` instance.
        """
        return cls(
            in_alarm=data.get("in_alarm", False),
            fault=data.get("fault", False),
            overridden=data.get("overridden", False),
            out_of_service=data.get("out_of_service", False),
        )

    def __repr__(self) -> str:
        flags = []
        if self.in_alarm:
            flags.append("IN_ALARM")
        if self.fault:
            flags.append("FAULT")
        if self.overridden:
            flags.append("OVERRIDDEN")
        if self.out_of_service:
            flags.append("OUT_OF_SERVICE")
        return f"StatusFlags({', '.join(flags) if flags else 'NORMAL'})"


@dataclass(frozen=True, slots=True)
class BACnetDateTime:
    """BACnet DateTime -- ``SEQUENCE { date Date, time Time }`` (Clause 21).

    Used by Schedule (Effective_Period), File (Modification_Date),
    TrendLog (Start_Time, Stop_Time), and Event Enrollment (Event_Time_Stamps).
    """

    date: BACnetDate
    """The date component."""

    time: BACnetTime
    """The time component."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"date"`` and ``"time"`` keys.
        """
        return {
            "date": self.date.to_dict(),
            "time": self.time.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDateTime:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing ``"date"`` and ``"time"`` keys.
        :returns: Decoded :class:`BACnetDateTime` instance.
        """
        return cls(
            date=BACnetDate.from_dict(data["date"]),
            time=BACnetTime.from_dict(data["time"]),
        )


@dataclass(frozen=True, slots=True)
class BACnetTimeStamp:
    """BACnet TimeStamp -- ``CHOICE { time [0], sequenceNumber [1], dateTime [2] }`` (Clause 21).

    Used by event notifications (Clause 13.8), alarm acknowledgment
    (Clause 13.5), and COV services for timestamping events.
    """

    choice: int
    """Discriminator: 0 = time, 1 = sequenceNumber, 2 = dateTime."""

    value: BACnetTime | int | BACnetDateTime
    """The typed value corresponding to the choice discriminator."""

    def encode(self) -> bytes:
        """Encode to context-tagged BACnet wire format.

        :returns: Context-tagged encoded bytes.
        :raises ValueError: If *choice* is not 0, 1, or 2.
        """
        from bac_py.encoding.primitives import (
            encode_context_tagged,
            encode_unsigned,
        )
        from bac_py.encoding.tags import (
            encode_closing_tag,
            encode_opening_tag,
        )

        if self.choice == 0:
            # [0] Time -- 4 bytes: hour, minute, second, hundredth
            assert isinstance(self.value, BACnetTime)
            from bac_py.encoding.primitives import encode_time

            return encode_context_tagged(0, encode_time(self.value))

        if self.choice == 1:
            # [1] Unsigned sequence number
            assert isinstance(self.value, int)
            return encode_context_tagged(1, encode_unsigned(self.value))

        if self.choice == 2:
            # [2] BACnetDateTime -- constructed (opening/closing tags)
            assert isinstance(self.value, BACnetDateTime)
            from bac_py.encoding.primitives import encode_date, encode_time

            buf = encode_opening_tag(2)
            buf += encode_date(self.value.date)
            buf += encode_time(self.value.time)
            buf += encode_closing_tag(2)
            return buf

        msg = f"Invalid BACnetTimeStamp choice: {self.choice}"
        raise ValueError(msg)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int = 0) -> tuple[BACnetTimeStamp, int]:
        """Decode from context-tagged BACnet wire format.

        :param data: Buffer to decode from.
        :param offset: Starting byte offset.
        :returns: Tuple of (decoded :class:`BACnetTimeStamp`, new offset).
        :raises ValueError: If the context tag is not 0, 1, or 2.
        """
        from bac_py.encoding.primitives import decode_time, decode_unsigned
        from bac_py.encoding.tags import TagClass, decode_tag

        if isinstance(data, bytes):
            data = memoryview(data)

        tag, new_offset = decode_tag(data, offset)

        if tag.cls != TagClass.CONTEXT:
            msg = f"Expected context tag for BACnetTimeStamp, got application tag {tag.number}"
            raise ValueError(msg)

        if tag.number == 0:
            # [0] Time
            time_val = decode_time(data[new_offset : new_offset + tag.length])
            return cls(choice=0, value=time_val), new_offset + tag.length

        if tag.number == 1:
            # [1] Unsigned sequence number
            seq_num = decode_unsigned(data[new_offset : new_offset + tag.length])
            return cls(choice=1, value=seq_num), new_offset + tag.length

        if tag.number == 2:
            # [2] BACnetDateTime -- constructed with opening/closing tags
            assert tag.is_opening
            from bac_py.encoding.primitives import decode_date

            date_val = decode_date(data[new_offset : new_offset + 4])
            new_offset += 4
            time_val = decode_time(data[new_offset : new_offset + 4])
            new_offset += 4
            # Consume the closing tag
            closing_tag, new_offset = decode_tag(data, new_offset)
            assert closing_tag.is_closing and closing_tag.number == 2
            return cls(choice=2, value=BACnetDateTime(date=date_val, time=time_val)), new_offset

        msg = f"Invalid BACnetTimeStamp context tag: {tag.number}"
        raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"choice"`` and ``"value"`` keys.
        """
        if self.choice == 0:
            assert isinstance(self.value, BACnetTime)
            return {"choice": "time", "value": self.value.to_dict()}
        if self.choice == 1:
            return {"choice": "sequence_number", "value": self.value}
        assert isinstance(self.value, BACnetDateTime)
        return {"choice": "date_time", "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetTimeStamp:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing ``"choice"`` and ``"value"`` keys.
        :returns: Decoded :class:`BACnetTimeStamp` instance.
        :raises ValueError: If the choice value is not recognized.
        """
        choice_str = data["choice"]
        value_data = data["value"]
        if choice_str == "time":
            return cls(choice=0, value=BACnetTime.from_dict(value_data))
        if choice_str == "sequence_number":
            return cls(choice=1, value=value_data)
        if choice_str == "date_time":
            return cls(choice=2, value=BACnetDateTime.from_dict(value_data))
        msg = f"Invalid BACnetTimeStamp choice: {choice_str}"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class BACnetDateRange:
    """BACnet DateRange -- ``SEQUENCE { start_date Date, end_date Date }`` (Clause 21).

    Used by Schedule (Effective_Period) and Calendar (Date_List entries).
    """

    start_date: BACnetDate
    """Inclusive start of the date range."""

    end_date: BACnetDate
    """Inclusive end of the date range."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"start_date"`` and ``"end_date"`` keys.
        """
        return {
            "start_date": self.start_date.to_dict(),
            "end_date": self.end_date.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDateRange:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing ``"start_date"`` and ``"end_date"`` keys.
        :returns: Decoded :class:`BACnetDateRange` instance.
        """
        return cls(
            start_date=BACnetDate.from_dict(data["start_date"]),
            end_date=BACnetDate.from_dict(data["end_date"]),
        )


@dataclass(frozen=True, slots=True)
class BACnetWeekNDay:
    """BACnet WeekNDay -- ``OCTET STRING (SIZE 3)`` (Clause 21).

    Encodes a recurring date pattern by month, week-of-month, and day-of-week.
    Used by Calendar (Date_List entries for week-n-day patterns).
    """

    month: int
    """Month selector: 1--14 or ``0xFF`` (any month). 13 = odd months, 14 = even months."""

    week_of_month: int
    """Week selector: 1--5 (specific week), 6 = last week, ``0xFF`` = any week."""

    day_of_week: int
    """Day selector: 1--7 (Monday--Sunday), ``0xFF`` = any day."""

    def to_dict(self) -> dict[str, int | None]:
        """Convert to a JSON-serializable dictionary.

        Wildcard values (``0xFF``) are represented as ``None``.

        :returns: Dictionary mapping field names to integer values or ``None``.
        """
        return {
            "month": None if self.month == 0xFF else self.month,
            "week_of_month": None if self.week_of_month == 0xFF else self.week_of_month,
            "day_of_week": None if self.day_of_week == 0xFF else self.day_of_week,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetWeekNDay:
        """Reconstruct from a JSON-friendly dictionary.

        ``None`` values are converted back to ``0xFF`` wildcards.

        :param data: Dictionary with ``"month"``, ``"week_of_month"``, and
            ``"day_of_week"`` keys.
        :returns: Decoded :class:`BACnetWeekNDay` instance.
        """
        return cls(
            month=0xFF if data.get("month") is None else data["month"],
            week_of_month=0xFF if data.get("week_of_month") is None else data["week_of_month"],
            day_of_week=0xFF if data.get("day_of_week") is None else data["day_of_week"],
        )


@dataclass(frozen=True, slots=True)
class BACnetCalendarEntry:
    """BACnet CalendarEntry -- ``CHOICE { date [0], dateRange [1], weekNDay [2] }`` (Clause 21).

    Used by Calendar.Date_List and Schedule.Exception_Schedule.
    """

    choice: int
    """Discriminator: 0 = date, 1 = dateRange, 2 = weekNDay."""

    value: BACnetDate | BACnetDateRange | BACnetWeekNDay
    """The typed value corresponding to the choice discriminator."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"choice"`` and ``"value"`` keys.
        """
        return {
            "choice": self.choice,
            "value": self.value.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetCalendarEntry:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing ``"choice"`` and ``"value"`` keys.
        :returns: Decoded :class:`BACnetCalendarEntry` instance.
        :raises ValueError: If the choice value is not 0, 1, or 2.
        """
        choice = data["choice"]
        value_data = data["value"]
        if choice == 0:
            value: BACnetDate | BACnetDateRange | BACnetWeekNDay = BACnetDate.from_dict(value_data)
        elif choice == 1:
            value = BACnetDateRange.from_dict(value_data)
        elif choice == 2:
            value = BACnetWeekNDay.from_dict(value_data)
        else:
            msg = f"Invalid BACnetCalendarEntry choice: {choice}"
            raise ValueError(msg)
        return cls(choice=choice, value=value)


@dataclass(frozen=True, slots=True)
class BACnetTimeValue:
    """BACnet TimeValue -- ``SEQUENCE { time Time, value ABSTRACT-SYNTAX.&Type }`` (Clause 21).

    Used by Schedule.Weekly_Schedule as lists of time-value pairs defining
    the schedule for each day of the week.
    """

    time: BACnetTime
    """The time at which this value takes effect."""

    value: Any
    """The primitive application-tagged value (any type)."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"time"`` and ``"value"`` keys.
        """
        v = self.value
        if hasattr(v, "to_dict"):
            v = v.to_dict()
        return {
            "time": self.time.to_dict(),
            "value": v,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetTimeValue:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing ``"time"`` and ``"value"`` keys.
        :returns: Decoded :class:`BACnetTimeValue` instance.
        """
        return cls(
            time=BACnetTime.from_dict(data["time"]),
            value=data["value"],
        )


@dataclass(frozen=True, slots=True)
class BACnetSpecialEvent:
    """BACnet SpecialEvent -- ``SEQUENCE`` (Clause 21).

    Used by Schedule.Exception_Schedule to define exception periods
    that override the normal weekly schedule.
    """

    period: BACnetCalendarEntry | ObjectIdentifier
    """Calendar entry defining when this event applies, or an
    :class:`~bac_py.types.primitives.ObjectIdentifier` referencing a Calendar object."""

    list_of_time_values: tuple[BACnetTimeValue, ...]
    """Time-value pairs active during this event period."""

    event_priority: int
    """Priority level (1--16) for schedule resolution. Lower values
    take precedence."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"period"``, ``"period_type"``,
            ``"list_of_time_values"``, and ``"event_priority"`` keys.
        """
        return {
            "period": self.period.to_dict(),
            "period_type": (
                "calendar_entry"
                if isinstance(self.period, BACnetCalendarEntry)
                else "calendar_reference"
            ),
            "list_of_time_values": [tv.to_dict() for tv in self.list_of_time_values],
            "event_priority": self.event_priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetSpecialEvent:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing event fields.
        :returns: Decoded :class:`BACnetSpecialEvent` instance.
        """
        period_type = data.get("period_type", "calendar_entry")
        if period_type == "calendar_reference":
            period: BACnetCalendarEntry | ObjectIdentifier = ObjectIdentifier.from_dict(
                data["period"]
            )
        else:
            period = BACnetCalendarEntry.from_dict(data["period"])
        return cls(
            period=period,
            list_of_time_values=tuple(
                BACnetTimeValue.from_dict(tv) for tv in data["list_of_time_values"]
            ),
            event_priority=data["event_priority"],
        )


@dataclass(frozen=True, slots=True)
class BACnetDeviceObjectPropertyReference:
    """BACnet DeviceObjectPropertyReference -- ``SEQUENCE`` (Clause 21).

    A reference to a property on a specific object, optionally on a remote
    device. Used by TrendLog.Log_Device_Object_Property, Loop references,
    EventEnrollment.Object_Property_Reference, and Schedule references.
    """

    object_identifier: ObjectIdentifier
    """The referenced object."""

    property_identifier: int
    """The referenced property (as int, maps to
    :class:`~bac_py.types.enums.PropertyIdentifier`)."""

    property_array_index: int | None = None
    """Optional array index within the property."""

    device_identifier: ObjectIdentifier | None = None
    """Optional device containing the referenced object. ``None`` means
    the local device."""

    def encode(self) -> bytes:
        """Encode as context-tagged SEQUENCE per Clause 21.

        :returns: Encoded bytes.
        """
        from bac_py.encoding.primitives import (
            encode_context_enumerated,
            encode_context_object_id,
            encode_context_tagged,
            encode_unsigned,
        )

        buf = bytearray()
        # [0] objectIdentifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
        # [1] propertyIdentifier
        buf.extend(encode_context_enumerated(1, self.property_identifier))
        # [2] propertyArrayIndex OPTIONAL
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.property_array_index)))
        # [3] deviceIdentifier OPTIONAL
        if self.device_identifier is not None:
            buf.extend(encode_context_object_id(3, self.device_identifier))
        return bytes(buf)

    @classmethod
    def decode(
        cls,
        data: memoryview | bytes,
        offset: int = 0,
    ) -> tuple[BACnetDeviceObjectPropertyReference, int]:
        """Decode from wire bytes.

        :param data: Buffer to decode from.
        :param offset: Starting position in *data*.
        :returns: Tuple of decoded reference and new offset.
        """
        from bac_py.encoding.primitives import (
            decode_object_identifier,
            decode_unsigned,
        )
        from bac_py.encoding.tags import as_memoryview, decode_tag

        data = as_memoryview(data)

        # [0] objectIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        from bac_py.types.enums import ObjectType

        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] propertyIdentifier
        tag, offset = decode_tag(data, offset)
        property_identifier = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [2] propertyArrayIndex OPTIONAL
        property_array_index: int | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.number == 2 and not tag.is_opening and not tag.is_closing:
                property_array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length

        # [3] deviceIdentifier OPTIONAL
        device_identifier: ObjectIdentifier | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.number == 3 and not tag.is_opening and not tag.is_closing:
                obj_type, instance = decode_object_identifier(
                    data[new_offset : new_offset + tag.length]
                )
                device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
                offset = new_offset + tag.length

        return cls(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=property_array_index,
            device_identifier=device_identifier,
        ), offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        Optional fields are omitted from the output when ``None``.

        :returns: Dictionary with reference fields.
        """
        result: dict[str, Any] = {
            "object_identifier": self.object_identifier.to_dict(),
            "property_identifier": self.property_identifier,
        }
        if self.property_array_index is not None:
            result["property_array_index"] = self.property_array_index
        if self.device_identifier is not None:
            result["device_identifier"] = self.device_identifier.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDeviceObjectPropertyReference:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing reference fields.
        :returns: Decoded :class:`BACnetDeviceObjectPropertyReference` instance.
        """
        device_id = None
        if "device_identifier" in data:
            device_id = ObjectIdentifier.from_dict(data["device_identifier"])
        return cls(
            object_identifier=ObjectIdentifier.from_dict(data["object_identifier"]),
            property_identifier=data["property_identifier"],
            property_array_index=data.get("property_array_index"),
            device_identifier=device_id,
        )


@dataclass(frozen=True, slots=True)
class BACnetObjectPropertyReference:
    """BACnet ObjectPropertyReference -- ``SEQUENCE`` (Clause 21).

    Like :class:`BACnetDeviceObjectPropertyReference` but without a device
    identifier (always references the local device). Used by Loop references
    (Controlled_Variable, Manipulated_Variable, Setpoint_Reference).
    """

    object_identifier: ObjectIdentifier
    """The referenced object."""

    property_identifier: int
    """The referenced property (as int, maps to
    :class:`~bac_py.types.enums.PropertyIdentifier`)."""

    property_array_index: int | None = None
    """Optional array index within the property."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with reference fields.
        """
        result: dict[str, Any] = {
            "object_identifier": self.object_identifier.to_dict(),
            "property_identifier": self.property_identifier,
        }
        if self.property_array_index is not None:
            result["property_array_index"] = self.property_array_index
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetObjectPropertyReference:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing reference fields.
        :returns: Decoded :class:`BACnetObjectPropertyReference` instance.
        """
        return cls(
            object_identifier=ObjectIdentifier.from_dict(data["object_identifier"]),
            property_identifier=data["property_identifier"],
            property_array_index=data.get("property_array_index"),
        )


@dataclass(frozen=True, slots=True)
class BACnetAddress:
    """BACnet network address for recipient routing (Clause 21).

    Represents a network-layer address used in notification recipient
    and destination structures. Distinct from
    :class:`~bac_py.network.address.BACnetAddress` which is the transport-layer
    address used for packet routing.
    """

    network_number: int
    """DNET value: 0 = local network, ``0xFFFF`` = broadcast."""

    mac_address: bytes
    """MAC-layer address bytes."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"network_number"`` and ``"mac_address"`` keys.
        """
        return {
            "network_number": self.network_number,
            "mac_address": self.mac_address.hex(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetAddress:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"network_number"`` and ``"mac_address"`` keys.
        :returns: Decoded :class:`BACnetAddress` instance.
        """
        return cls(
            network_number=data["network_number"],
            mac_address=bytes.fromhex(data["mac_address"]),
        )


@dataclass(frozen=True, slots=True)
class BACnetRecipient:
    """BACnet Recipient -- ``CHOICE { device [0], address [1] }`` (Clause 21).

    Used by :class:`BACnetDestination` in NotificationClass.Recipient_List.
    Exactly one of *device* or *address* should be set.
    """

    device: ObjectIdentifier | None = None
    """Target device object identifier, or ``None`` if using *address*."""

    address: BACnetAddress | None = None
    """Target network address, or ``None`` if using *device*."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with a ``"type"`` discriminator and the
            corresponding value.
        """
        if self.device is not None:
            return {"type": "device", "device": self.device.to_dict()}
        if self.address is not None:
            return {"type": "address", "address": self.address.to_dict()}
        return {"type": "device", "device": None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetRecipient:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"type"`` discriminator.
        :returns: Decoded :class:`BACnetRecipient` instance.
        """
        if data.get("type") == "address" and "address" in data:
            return cls(address=BACnetAddress.from_dict(data["address"]))
        if "device" in data and data["device"] is not None:
            return cls(device=ObjectIdentifier.from_dict(data["device"]))
        return cls()


@dataclass(frozen=True, slots=True)
class BACnetDestination:
    """BACnet Destination -- notification routing entry (Clause 21).

    Used by NotificationClass.Recipient_List to define where and when
    event notifications should be sent.
    """

    valid_days: BitString
    """7-bit BitString indicating valid days (Monday through Sunday)."""

    from_time: BACnetTime
    """Start of the valid time window."""

    to_time: BACnetTime
    """End of the valid time window."""

    recipient: BACnetRecipient
    """Target device or address for notifications."""

    process_identifier: int
    """Process identifier on the recipient to notify."""

    issue_confirmed_notifications: bool
    """``True`` for confirmed notifications, ``False`` for unconfirmed."""

    transitions: BitString
    """3-bit BitString for event transitions: to-offnormal, to-fault,
    to-normal."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with all destination fields.
        """
        return {
            "valid_days": self.valid_days.to_dict(),
            "from_time": self.from_time.to_dict(),
            "to_time": self.to_time.to_dict(),
            "recipient": self.recipient.to_dict(),
            "process_identifier": self.process_identifier,
            "issue_confirmed_notifications": self.issue_confirmed_notifications,
            "transitions": self.transitions.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDestination:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing all destination fields.
        :returns: Decoded :class:`BACnetDestination` instance.
        """
        return cls(
            valid_days=BitString.from_dict(data["valid_days"]),
            from_time=BACnetTime.from_dict(data["from_time"]),
            to_time=BACnetTime.from_dict(data["to_time"]),
            recipient=BACnetRecipient.from_dict(data["recipient"]),
            process_identifier=data["process_identifier"],
            issue_confirmed_notifications=data["issue_confirmed_notifications"],
            transitions=BitString.from_dict(data["transitions"]),
        )


@dataclass(frozen=True, slots=True)
class BACnetScale:
    """BACnet Scale -- ``CHOICE { float_scale [0], integer_scale [1] }`` (Clause 12.1).

    Used by Accumulator.Scale. Exactly one of *float_scale* or
    *integer_scale* should be set.
    """

    float_scale: float | None = None
    """Floating-point scale factor, or ``None`` if using *integer_scale*."""

    integer_scale: int | None = None
    """Integer scale factor, or ``None`` if using *float_scale*."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"type"`` and ``"value"`` keys.
        """
        if self.float_scale is not None:
            return {"type": "float", "value": self.float_scale}
        if self.integer_scale is not None:
            return {"type": "integer", "value": self.integer_scale}
        return {"type": "float", "value": None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetScale:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"type"`` and ``"value"`` keys.
        :returns: Decoded :class:`BACnetScale` instance.
        """
        if data.get("type") == "integer":
            return cls(integer_scale=data["value"])
        return cls(float_scale=data.get("value"))


@dataclass(frozen=True, slots=True)
class BACnetPrescale:
    """BACnet Prescale -- ``SEQUENCE { multiplier Unsigned, modulo_divide Unsigned }`` (Clause 12.1).

    Used by Accumulator.Prescale to define pulse prescaling parameters.
    """

    multiplier: int
    """Prescale multiplier value."""

    modulo_divide: int
    """Prescale modulo-divide value."""

    def to_dict(self) -> dict[str, int]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"multiplier"`` and ``"modulo_divide"`` keys.
        """
        return {
            "multiplier": self.multiplier,
            "modulo_divide": self.modulo_divide,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetPrescale:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"multiplier"`` and ``"modulo_divide"`` keys.
        :returns: Decoded :class:`BACnetPrescale` instance.
        """
        return cls(
            multiplier=data["multiplier"],
            modulo_divide=data["modulo_divide"],
        )


@dataclass(frozen=True, slots=True)
class BACnetLogRecord:
    """BACnet LogRecord for TrendLog.Log_Buffer (Clause 12.25).

    Represents a single timestamped entry in a trend log buffer.
    """

    timestamp: BACnetDateTime
    """When the value was logged."""

    log_datum: Any
    """The logged value. Type varies depending on the monitored property."""

    status_flags: StatusFlags | None = None
    """Optional status flags at the time of logging."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"timestamp"``, ``"log_datum"``, and
            optionally ``"status_flags"`` keys.
        """
        datum = self.log_datum
        if hasattr(datum, "to_dict"):
            datum = datum.to_dict()
        result: dict[str, Any] = {
            "timestamp": self.timestamp.to_dict(),
            "log_datum": datum,
        }
        if self.status_flags is not None:
            result["status_flags"] = self.status_flags.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetLogRecord:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing log record fields.
        :returns: Decoded :class:`BACnetLogRecord` instance.
        """
        sf = None
        if "status_flags" in data:
            sf = StatusFlags.from_dict(data["status_flags"])
        return cls(
            timestamp=BACnetDateTime.from_dict(data["timestamp"]),
            log_datum=data["log_datum"],
            status_flags=sf,
        )


@dataclass(frozen=True, slots=True)
class BACnetRecipientProcess:
    """BACnet RecipientProcess -- identifies a subscriber process (Clause 12.11.39).

    Pairs a :class:`BACnetRecipient` with a process identifier to uniquely
    identify a COV subscription endpoint.
    """

    recipient: BACnetRecipient
    """The subscribing device or address."""

    process_identifier: int
    """The subscriber's process ID."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"recipient"`` and ``"process_identifier"`` keys.
        """
        return {
            "recipient": self.recipient.to_dict(),
            "process_identifier": self.process_identifier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetRecipientProcess:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"recipient"`` and ``"process_identifier"`` keys.
        :returns: Decoded :class:`BACnetRecipientProcess` instance.
        """
        return cls(
            recipient=BACnetRecipient.from_dict(data["recipient"]),
            process_identifier=data["process_identifier"],
        )


@dataclass(frozen=True, slots=True)
class BACnetCOVSubscription:
    """BACnet COVSubscription -- read-only diagnostic entry (Clause 12.11.39).

    Used by Device.Active_COV_Subscriptions to expose active subscriptions
    as a read-only list.
    """

    recipient: BACnetRecipientProcess
    """The subscriber process."""

    monitored_object: ObjectIdentifier
    """The object being monitored for changes."""

    issue_confirmed_notifications: bool
    """``True`` for confirmed COV notifications."""

    time_remaining: int
    """Seconds until this subscription expires."""

    cov_increment: float | None = None
    """Optional COV increment threshold. ``None`` when not applicable."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with subscription fields.
        """
        result: dict[str, Any] = {
            "recipient": self.recipient.to_dict(),
            "monitored_object": self.monitored_object.to_dict(),
            "issue_confirmed_notifications": self.issue_confirmed_notifications,
            "time_remaining": self.time_remaining,
        }
        if self.cov_increment is not None:
            result["cov_increment"] = self.cov_increment
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetCOVSubscription:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary containing subscription fields.
        :returns: Decoded :class:`BACnetCOVSubscription` instance.
        """
        return cls(
            recipient=BACnetRecipientProcess.from_dict(data["recipient"]),
            monitored_object=ObjectIdentifier.from_dict(data["monitored_object"]),
            issue_confirmed_notifications=data["issue_confirmed_notifications"],
            time_remaining=data["time_remaining"],
            cov_increment=data.get("cov_increment"),
        )


@dataclass(frozen=True, slots=True)
class BACnetPriorityValue:
    """BACnet PriorityValue -- a single entry in a Priority_Array (Clause 19).

    Each slot holds either a commanded value or ``None`` (relinquished / Null).
    """

    value: Any = None
    """The commanded value, or ``None`` if relinquished."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with a ``"value"`` key.
        """
        v = self.value
        if hasattr(v, "to_dict"):
            v = v.to_dict()
        return {"value": v}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetPriorityValue:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with a ``"value"`` key.
        :returns: Decoded :class:`BACnetPriorityValue` instance.
        """
        return cls(value=data.get("value"))


@dataclass(frozen=True, slots=True)
class BACnetPriorityArray:
    """BACnet Priority_Array -- ``ARRAY[16] OF BACnetPriorityValue`` (Clause 19).

    Provides indexed access to the 16-level command priority array used
    by commandable objects (Analog Output, Binary Output, etc.).
    """

    slots: tuple[BACnetPriorityValue, ...] = field(
        default_factory=lambda: tuple(BACnetPriorityValue() for _ in range(16))
    )
    """Tuple of exactly 16 :class:`BACnetPriorityValue` entries."""

    def __post_init__(self) -> None:
        if len(self.slots) != 16:
            msg = f"Priority_Array must have exactly 16 entries, got {len(self.slots)}"
            raise ValueError(msg)

    def __getitem__(self, index: int) -> BACnetPriorityValue:
        return self.slots[index]

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with a ``"slots"`` key containing a list
            of 16 priority value dictionaries.
        """
        return {"slots": [s.to_dict() for s in self.slots]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetPriorityArray:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with a ``"slots"`` key containing exactly
            16 priority value entries.
        :returns: Decoded :class:`BACnetPriorityArray` instance.
        :raises ValueError: If the ``"slots"`` list does not contain exactly
            16 entries.
        """
        return cls(slots=tuple(BACnetPriorityValue.from_dict(s) for s in data["slots"]))


@dataclass(frozen=True, slots=True)
class BACnetLightingCommand:
    """BACnet lighting command (Clause 12.54).

    Used to control lighting output objects with fade/ramp/step operations.
    """

    operation: LightingOperation
    """The lighting operation to perform."""

    target_level: float | None = None
    """Target lighting level (0.0--100.0 percent)."""

    ramp_rate: float | None = None
    """Ramp rate in percent per second."""

    step_increment: float | None = None
    """Step increment in percent."""

    fade_time: int | None = None
    """Fade time in milliseconds."""

    priority: int | None = None
    """Priority for the lighting command (1--16)."""


@dataclass(frozen=True, slots=True)
class BACnetShedLevel:
    """BACnet shed level CHOICE type for Load Control (Clause 12.28).

    Exactly one of ``percent``, ``level``, or ``amount`` must be set.
    """

    percent: int | None = None
    """Shed as a percentage (0--100)."""

    level: int | None = None
    """Shed level enumeration index."""

    amount: float | None = None
    """Shed amount in engineering units."""


@dataclass(frozen=True, slots=True)
class BACnetDeviceObjectReference:
    """BACnet DeviceObjectReference (Clause 21).

    ``SEQUENCE { deviceIdentifier [0] OPTIONAL, objectIdentifier [1] }``
    """

    object_identifier: ObjectIdentifier
    """The referenced object."""

    device_identifier: ObjectIdentifier | None = None
    """Optional device hosting the object (None = local device)."""

    def encode(self) -> bytes:
        """Encode to context-tagged wire format."""
        from bac_py.encoding.primitives import encode_context_object_id

        buf = bytearray()
        if self.device_identifier is not None:
            buf.extend(encode_context_object_id(0, self.device_identifier))
        buf.extend(encode_context_object_id(1, self.object_identifier))
        return bytes(buf)

    @classmethod
    def decode(
        cls, data: memoryview | bytes, offset: int = 0
    ) -> tuple[BACnetDeviceObjectReference, int]:
        """Decode from context-tagged wire format."""
        from bac_py.encoding.primitives import decode_object_identifier
        from bac_py.encoding.tags import TagClass, decode_tag
        from bac_py.types.enums import ObjectType

        if isinstance(data, bytes):
            data = memoryview(data)

        device_identifier = None
        tag, new_offset = decode_tag(data, offset)

        if tag.cls == TagClass.CONTEXT and tag.number == 0:
            obj_type, instance = decode_object_identifier(
                data[new_offset : new_offset + tag.length]
            )
            device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
            new_offset += tag.length
            tag, new_offset = decode_tag(data, new_offset)

        # [1] objectIdentifier
        obj_type, instance = decode_object_identifier(data[new_offset : new_offset + tag.length])
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
        new_offset += tag.length

        return cls(
            object_identifier=object_identifier, device_identifier=device_identifier
        ), new_offset

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"object_identifier"`` and optionally
            ``"device_identifier"`` keys.
        """
        result: dict[str, Any] = {
            "object_identifier": self.object_identifier.to_dict(),
        }
        if self.device_identifier is not None:
            result["device_identifier"] = self.device_identifier.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDeviceObjectReference:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"object_identifier"`` and optionally
            ``"device_identifier"`` keys.
        :returns: Decoded :class:`BACnetDeviceObjectReference` instance.
        """
        device_id = None
        if "device_identifier" in data:
            device_id = ObjectIdentifier.from_dict(data["device_identifier"])
        return cls(
            object_identifier=ObjectIdentifier.from_dict(data["object_identifier"]),
            device_identifier=device_id,
        )


@dataclass(frozen=True, slots=True)
class BACnetValueSource:
    """BACnet ValueSource CHOICE type (Clause 19.5, new in 2020).

    ``CHOICE { none [0] NULL, object [1] BACnetDeviceObjectReference, address [2] BACnetAddress }``

    Tracks the source of the last write to a commandable property.
    """

    choice: int = 0
    """Discriminator: 0 = none, 1 = object, 2 = address."""

    value: None | BACnetDeviceObjectReference | bytes = None
    """The typed value: None for choice 0, DeviceObjectReference for 1, raw address bytes for 2."""

    @classmethod
    def none_source(cls) -> BACnetValueSource:
        """Create a ValueSource indicating no source."""
        return cls(choice=0, value=None)

    @classmethod
    def from_object(cls, ref: BACnetDeviceObjectReference) -> BACnetValueSource:
        """Create a ValueSource from a device/object reference."""
        return cls(choice=1, value=ref)

    @classmethod
    def from_address(cls, address: bytes) -> BACnetValueSource:
        """Create a ValueSource from a raw BACnet address."""
        return cls(choice=2, value=address)

    def encode(self) -> bytes:
        """Encode to context-tagged wire format."""
        from bac_py.encoding.primitives import encode_context_octet_string
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        if self.choice == 0:
            # [0] NULL -- context-tagged with length 0
            return encode_opening_tag(0) + encode_closing_tag(0)

        if self.choice == 1:
            # [1] BACnetDeviceObjectReference -- constructed
            assert isinstance(self.value, BACnetDeviceObjectReference)
            buf = encode_opening_tag(1)
            buf += self.value.encode()
            buf += encode_closing_tag(1)
            return buf

        if self.choice == 2:
            # [2] BACnetAddress -- as octet string
            assert isinstance(self.value, bytes)
            return encode_context_octet_string(2, self.value)

        msg = f"Invalid BACnetValueSource choice: {self.choice}"
        raise ValueError(msg)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int = 0) -> tuple[BACnetValueSource, int]:
        """Decode from context-tagged wire format."""
        from bac_py.encoding.tags import TagClass, decode_tag

        if isinstance(data, bytes):
            data = memoryview(data)

        tag, new_offset = decode_tag(data, offset)

        if tag.cls != TagClass.CONTEXT:
            msg = f"Expected context tag for BACnetValueSource, got {tag}"
            raise ValueError(msg)

        if tag.number == 0:
            # [0] NULL -- opening+closing
            if tag.is_opening:
                _closing, new_offset = decode_tag(data, new_offset)
            return cls.none_source(), new_offset

        if tag.number == 1:
            # [1] BACnetDeviceObjectReference -- constructed
            assert tag.is_opening
            ref, new_offset = BACnetDeviceObjectReference.decode(data, new_offset)
            _closing, new_offset = decode_tag(data, new_offset)
            return cls.from_object(ref), new_offset

        if tag.number == 2:
            # [2] BACnetAddress as octet string
            addr = bytes(data[new_offset : new_offset + tag.length])
            return cls.from_address(addr), new_offset + tag.length

        msg = f"Invalid BACnetValueSource choice tag: {tag.number}"
        raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"choice"`` (``"none"``, ``"object"``,
            or ``"address"``) and ``"value"`` keys.
        """
        if self.choice == 0:
            return {"choice": "none", "value": None}
        if self.choice == 1:
            assert isinstance(self.value, BACnetDeviceObjectReference)
            return {"choice": "object", "value": self.value.to_dict()}
        if self.choice == 2:
            assert isinstance(self.value, bytes)
            return {"choice": "address", "value": self.value.hex()}
        msg = f"Invalid BACnetValueSource choice: {self.choice}"
        raise ValueError(msg)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetValueSource:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"choice"`` and ``"value"`` keys.
        :returns: Decoded :class:`BACnetValueSource` instance.
        :raises ValueError: If the choice value is not recognized.
        """
        choice_str = data["choice"]
        if choice_str == "none":
            return cls.none_source()
        if choice_str == "object":
            return cls.from_object(BACnetDeviceObjectReference.from_dict(data["value"]))
        if choice_str == "address":
            return cls.from_address(bytes.fromhex(data["value"]))
        msg = f"Invalid BACnetValueSource choice: {choice_str}"
        raise ValueError(msg)
