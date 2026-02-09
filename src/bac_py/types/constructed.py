"""BACnet constructed data types per ASHRAE 135-2016."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier


@dataclass(frozen=True, slots=True)
class StatusFlags:
    """BACnet StatusFlags bit string (Clause 12.50, BACnetStatusFlags).

    Four Boolean flags indicating the "health" of an object:
      Bit 0: IN_ALARM
      Bit 1: FAULT
      Bit 2: OVERRIDDEN
      Bit 3: OUT_OF_SERVICE
    """

    in_alarm: bool = False
    fault: bool = False
    overridden: bool = False
    out_of_service: bool = False

    def to_bit_string(self) -> BitString:
        """Encode as a BACnet BitString (4 significant bits)."""
        value = (
            (self.in_alarm << 3) | (self.fault << 2) | (self.overridden << 1) | self.out_of_service
        )
        return BitString(bytes([value << 4]), unused_bits=4)

    @classmethod
    def from_bit_string(cls, bs: BitString) -> StatusFlags:
        """Decode from a BACnet BitString."""
        return cls(
            in_alarm=bs[0] if len(bs) > 0 else False,
            fault=bs[1] if len(bs) > 1 else False,
            overridden=bs[2] if len(bs) > 2 else False,
            out_of_service=bs[3] if len(bs) > 3 else False,
        )

    def to_dict(self) -> dict[str, bool]:
        """Convert to JSON-friendly dict."""
        return {
            "in_alarm": self.in_alarm,
            "fault": self.fault,
            "overridden": self.overridden,
            "out_of_service": self.out_of_service,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusFlags:
        """Reconstruct from a JSON-friendly dict."""
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


# --- C1: BACnetDateTime (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetDateTime:
    """BACnet DateTime - SEQUENCE { date Date, time Time }.

    Used by Schedule (Effective_Period), File (Modification_Date),
    TrendLog (Start_Time, Stop_Time), Event Enrollment (Event_Time_Stamps).
    """

    date: BACnetDate
    time: BACnetTime

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {
            "date": self.date.to_dict(),
            "time": self.time.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDateTime:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            date=BACnetDate.from_dict(data["date"]),
            time=BACnetTime.from_dict(data["time"]),
        )


# --- C2: BACnetDateRange (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetDateRange:
    """BACnet DateRange - SEQUENCE { start_date Date, end_date Date }.

    Used by Schedule (Effective_Period), Calendar (Date_List entries).
    """

    start_date: BACnetDate
    end_date: BACnetDate

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {
            "start_date": self.start_date.to_dict(),
            "end_date": self.end_date.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDateRange:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            start_date=BACnetDate.from_dict(data["start_date"]),
            end_date=BACnetDate.from_dict(data["end_date"]),
        )


# --- C3: BACnetWeekNDay (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetWeekNDay:
    """BACnet WeekNDay - OCTET STRING (SIZE 3).

    Encodes a recurring date pattern by month, week-of-month, and day-of-week.
    Used by Calendar (Date_List entries for week-n-day patterns).

    Attributes:
        month: 1-14 or 0xFF (any month). 13=odd months, 14=even months.
        week_of_month: 1-5 (specific week), 6=last, 0xFF (any week).
        day_of_week: 1-7 (Monday-Sunday), 0xFF (any day).
    """

    month: int
    week_of_month: int
    day_of_week: int

    def to_dict(self) -> dict[str, int | None]:
        """Convert to JSON-friendly dict."""
        return {
            "month": None if self.month == 0xFF else self.month,
            "week_of_month": None if self.week_of_month == 0xFF else self.week_of_month,
            "day_of_week": None if self.day_of_week == 0xFF else self.day_of_week,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetWeekNDay:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            month=0xFF if data.get("month") is None else data["month"],
            week_of_month=0xFF if data.get("week_of_month") is None else data["week_of_month"],
            day_of_week=0xFF if data.get("day_of_week") is None else data["day_of_week"],
        )


# --- C4: BACnetCalendarEntry (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetCalendarEntry:
    """BACnet CalendarEntry - CHOICE { date [0], dateRange [1], weekNDay [2] }.

    Used by Calendar.Date_List, Schedule.Exception_Schedule.

    Attributes:
        choice: 0=date, 1=dateRange, 2=weekNDay
        value: The typed value corresponding to the choice.
    """

    choice: int
    value: BACnetDate | BACnetDateRange | BACnetWeekNDay

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {
            "choice": self.choice,
            "value": self.value.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetCalendarEntry:
        """Reconstruct from a JSON-friendly dict."""
        choice = data["choice"]
        value_data = data["value"]
        if choice == 0:
            value: BACnetDate | BACnetDateRange | BACnetWeekNDay = BACnetDate.from_dict(
                value_data
            )
        elif choice == 1:
            value = BACnetDateRange.from_dict(value_data)
        elif choice == 2:
            value = BACnetWeekNDay.from_dict(value_data)
        else:
            msg = f"Invalid BACnetCalendarEntry choice: {choice}"
            raise ValueError(msg)
        return cls(choice=choice, value=value)


# --- C5: BACnetTimeValue (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetTimeValue:
    """BACnet TimeValue - SEQUENCE { time Time, value ABSTRACT-SYNTAX.&Type }.

    Used by Schedule.Weekly_Schedule (7 lists of time-value pairs).

    Attributes:
        time: The time at which this value takes effect.
        value: The primitive application-tagged value (any type).
    """

    time: BACnetTime
    value: Any

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        v = self.value
        if hasattr(v, "to_dict"):
            v = v.to_dict()
        return {
            "time": self.time.to_dict(),
            "value": v,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetTimeValue:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            time=BACnetTime.from_dict(data["time"]),
            value=data["value"],
        )


# --- C6: BACnetSpecialEvent (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetSpecialEvent:
    """BACnet SpecialEvent - SEQUENCE.

    Used by Schedule.Exception_Schedule.

    Attributes:
        period: Calendar entry or calendar object reference.
        list_of_time_values: Time-value pairs for this event.
        event_priority: 1-16 (priority for schedule resolution).
    """

    period: BACnetCalendarEntry | ObjectIdentifier
    list_of_time_values: tuple[BACnetTimeValue, ...]
    event_priority: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
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
        """Reconstruct from a JSON-friendly dict."""
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


# --- C7: BACnetDeviceObjectPropertyReference (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetDeviceObjectPropertyReference:
    """BACnet DeviceObjectPropertyReference - SEQUENCE.

    Used by TrendLog.Log_Device_Object_Property, Loop references,
    EventEnrollment.Object_Property_Reference, Schedule references.

    Attributes:
        object_identifier: The referenced object.
        property_identifier: The referenced property (as int, maps to PropertyIdentifier).
        property_array_index: Optional array index within the property.
        device_identifier: Optional device containing the referenced object.
    """

    object_identifier: ObjectIdentifier
    property_identifier: int
    property_array_index: int | None = None
    device_identifier: ObjectIdentifier | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
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
        """Reconstruct from a JSON-friendly dict."""
        device_id = None
        if "device_identifier" in data:
            device_id = ObjectIdentifier.from_dict(data["device_identifier"])
        return cls(
            object_identifier=ObjectIdentifier.from_dict(data["object_identifier"]),
            property_identifier=data["property_identifier"],
            property_array_index=data.get("property_array_index"),
            device_identifier=device_id,
        )


# --- C8: BACnetObjectPropertyReference (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetObjectPropertyReference:
    """BACnet ObjectPropertyReference - SEQUENCE (no device identifier).

    Used by Loop references (Controlled_Variable, Manipulated_Variable,
    Setpoint_Reference).

    Attributes:
        object_identifier: The referenced object.
        property_identifier: The referenced property (as int, maps to PropertyIdentifier).
        property_array_index: Optional array index within the property.
    """

    object_identifier: ObjectIdentifier
    property_identifier: int
    property_array_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        result: dict[str, Any] = {
            "object_identifier": self.object_identifier.to_dict(),
            "property_identifier": self.property_identifier,
        }
        if self.property_array_index is not None:
            result["property_array_index"] = self.property_array_index
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetObjectPropertyReference:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            object_identifier=ObjectIdentifier.from_dict(data["object_identifier"]),
            property_identifier=data["property_identifier"],
            property_array_index=data.get("property_array_index"),
        )


# --- C9: BACnetRecipient and BACnetDestination (Clause 21) ---


@dataclass(frozen=True, slots=True)
class BACnetAddress:
    """BACnet network address for recipient routing.

    Attributes:
        network_number: DNET (0 = local, 0xFFFF = broadcast).
        mac_address: MAC layer address bytes.
    """

    network_number: int
    mac_address: bytes

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {
            "network_number": self.network_number,
            "mac_address": self.mac_address.hex(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetAddress:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            network_number=data["network_number"],
            mac_address=bytes.fromhex(data["mac_address"]),
        )


@dataclass(frozen=True, slots=True)
class BACnetRecipient:
    """BACnet Recipient - CHOICE { device [0] ObjectIdentifier, address [1] BACnetAddress }.

    Used by BACnetDestination in NotificationClass.Recipient_List.
    Exactly one of device or address should be set.
    """

    device: ObjectIdentifier | None = None
    address: BACnetAddress | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        if self.device is not None:
            return {"type": "device", "device": self.device.to_dict()}
        if self.address is not None:
            return {"type": "address", "address": self.address.to_dict()}
        return {"type": "device", "device": None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetRecipient:
        """Reconstruct from a JSON-friendly dict."""
        if data.get("type") == "address" and "address" in data:
            return cls(address=BACnetAddress.from_dict(data["address"]))
        if "device" in data and data["device"] is not None:
            return cls(device=ObjectIdentifier.from_dict(data["device"]))
        return cls()


@dataclass(frozen=True, slots=True)
class BACnetDestination:
    """BACnet Destination - notification routing entry.

    Used by NotificationClass.Recipient_List.

    Attributes:
        valid_days: 7-bit BitString (Monday through Sunday).
        from_time: Start of valid time window.
        to_time: End of valid time window.
        recipient: Target device or address.
        process_identifier: Process to notify.
        issue_confirmed_notifications: True for confirmed, False for unconfirmed.
        transitions: 3-bit BitString (to-offnormal, to-fault, to-normal).
    """

    valid_days: BitString
    from_time: BACnetTime
    to_time: BACnetTime
    recipient: BACnetRecipient
    process_identifier: int
    issue_confirmed_notifications: bool
    transitions: BitString

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
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
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            valid_days=BitString.from_dict(data["valid_days"]),
            from_time=BACnetTime.from_dict(data["from_time"]),
            to_time=BACnetTime.from_dict(data["to_time"]),
            recipient=BACnetRecipient.from_dict(data["recipient"]),
            process_identifier=data["process_identifier"],
            issue_confirmed_notifications=data["issue_confirmed_notifications"],
            transitions=BitString.from_dict(data["transitions"]),
        )


# --- C10: BACnetScale and BACnetPrescale (Clause 12.1) ---


@dataclass(frozen=True, slots=True)
class BACnetScale:
    """BACnet Scale - CHOICE { float_scale [0] REAL, integer_scale [1] INTEGER }.

    Used by Accumulator.Scale.
    Exactly one of float_scale or integer_scale should be set.
    """

    float_scale: float | None = None
    integer_scale: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        if self.float_scale is not None:
            return {"type": "float", "value": self.float_scale}
        if self.integer_scale is not None:
            return {"type": "integer", "value": self.integer_scale}
        return {"type": "float", "value": None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetScale:
        """Reconstruct from a JSON-friendly dict."""
        if data.get("type") == "integer":
            return cls(integer_scale=data["value"])
        return cls(float_scale=data.get("value"))


@dataclass(frozen=True, slots=True)
class BACnetPrescale:
    """BACnet Prescale - SEQUENCE { multiplier Unsigned, modulo_divide Unsigned }.

    Used by Accumulator.Prescale.
    """

    multiplier: int
    modulo_divide: int

    def to_dict(self) -> dict[str, int]:
        """Convert to JSON-friendly dict."""
        return {
            "multiplier": self.multiplier,
            "modulo_divide": self.modulo_divide,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetPrescale:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            multiplier=data["multiplier"],
            modulo_divide=data["modulo_divide"],
        )


# --- C11: BACnetLogRecord (Clause 12.25) ---


@dataclass(frozen=True, slots=True)
class BACnetLogRecord:
    """BACnet LogRecord for TrendLog.Log_Buffer.

    Attributes:
        timestamp: When the value was logged.
        log_datum: The logged value (type varies).
        status_flags: Optional status at time of logging.
    """

    timestamp: BACnetDateTime
    log_datum: Any
    status_flags: StatusFlags | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
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
        """Reconstruct from a JSON-friendly dict."""
        sf = None
        if "status_flags" in data:
            sf = StatusFlags.from_dict(data["status_flags"])
        return cls(
            timestamp=BACnetDateTime.from_dict(data["timestamp"]),
            log_datum=data["log_datum"],
            status_flags=sf,
        )


# --- C12: BACnetCOVSubscription (Clause 12.11.39) ---


@dataclass(frozen=True, slots=True)
class BACnetRecipientProcess:
    """BACnet RecipientProcess - identifies a subscriber.

    Attributes:
        recipient: The subscribing device or address.
        process_identifier: The subscriber's process ID.
    """

    recipient: BACnetRecipient
    process_identifier: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {
            "recipient": self.recipient.to_dict(),
            "process_identifier": self.process_identifier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetRecipientProcess:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            recipient=BACnetRecipient.from_dict(data["recipient"]),
            process_identifier=data["process_identifier"],
        )


@dataclass(frozen=True, slots=True)
class BACnetCOVSubscription:
    """BACnet COVSubscription - read-only diagnostic entry.

    Used by Device.Active_COV_Subscriptions.

    Attributes:
        recipient: The subscriber process.
        monitored_object: The object being monitored.
        issue_confirmed_notifications: True for confirmed COV.
        time_remaining: Seconds until subscription expires.
        cov_increment: Optional COV increment threshold.
    """

    recipient: BACnetRecipientProcess
    monitored_object: ObjectIdentifier
    issue_confirmed_notifications: bool
    time_remaining: int
    cov_increment: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
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
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            recipient=BACnetRecipientProcess.from_dict(data["recipient"]),
            monitored_object=ObjectIdentifier.from_dict(data["monitored_object"]),
            issue_confirmed_notifications=data["issue_confirmed_notifications"],
            time_remaining=data["time_remaining"],
            cov_increment=data.get("cov_increment"),
        )


# --- C13: BACnetPriorityValue (Clause 19) ---


@dataclass(frozen=True, slots=True)
class BACnetPriorityValue:
    """BACnet PriorityValue - a single entry in a Priority_Array.

    Each slot is either a typed value or None (relinquished / Null).

    Attributes:
        value: The commanded value, or None if relinquished.
    """

    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        v = self.value
        if hasattr(v, "to_dict"):
            v = v.to_dict()
        return {"value": v}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetPriorityValue:
        """Reconstruct from a JSON-friendly dict."""
        return cls(value=data.get("value"))


@dataclass(frozen=True, slots=True)
class BACnetPriorityArray:
    """BACnet Priority_Array - ARRAY[16] of BACnetPriorityValue.

    Provides indexed access to the 16-level command priority array.
    """

    slots: tuple[BACnetPriorityValue, ...] = field(
        default_factory=lambda: tuple(BACnetPriorityValue() for _ in range(16))
    )

    def __post_init__(self) -> None:
        if len(self.slots) != 16:
            msg = f"Priority_Array must have exactly 16 entries, got {len(self.slots)}"
            raise ValueError(msg)

    def __getitem__(self, index: int) -> BACnetPriorityValue:
        return self.slots[index]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {"slots": [s.to_dict() for s in self.slots]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetPriorityArray:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            slots=tuple(BACnetPriorityValue.from_dict(s) for s in data["slots"])
        )
