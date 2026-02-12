"""BACnet Binary object types per ASHRAE 135-2020 Clause 12.6-12.8."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    commandable_properties,
    intrinsic_reporting_properties,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.enums import (
    BinaryPV,
    EventType,
    ObjectType,
    Polarity,
    PropertyIdentifier,
)


class _BinaryPolarityMixin:
    """Mixin providing polarity inversion for Present_Value reads.

    Per Clause 12.6.15 / 12.7.15, when Polarity is REVERSE the
    Present_Value returned to callers is inverted.
    """

    def read_property(
        self,
        prop_id: PropertyIdentifier,
        array_index: int | None = None,
    ) -> Any:
        value = super().read_property(prop_id, array_index)  # type: ignore[misc]
        if prop_id == PropertyIdentifier.PRESENT_VALUE:
            polarity = self._properties.get(PropertyIdentifier.POLARITY, Polarity.NORMAL)  # type: ignore[attr-defined]
            if polarity == Polarity.REVERSE:
                value = BinaryPV.ACTIVE if value == BinaryPV.INACTIVE else BinaryPV.INACTIVE
        return value


class _MinOnOffTimeMixin:
    """Mixin implementing Minimum On/Off Time enforcement (Clause 19.2).

    When ``minimum_on_time`` or ``minimum_off_time`` is configured, the
    present_value is held at the current state for at least that many
    seconds after a state transition.  Writes are accepted into the
    priority array, but the present_value output is locked until the
    timer expires.
    """

    _min_time_lock_until: float | None
    _min_time_locked_value: BinaryPV | None

    def _init_min_time(self) -> None:
        """Initialise minimum on/off time state."""
        self._min_time_lock_until = None
        self._min_time_locked_value = None

    def _write_with_priority(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int,
        value_source: Any = None,
    ) -> None:
        old_pv = self._properties.get(PropertyIdentifier.PRESENT_VALUE)  # type: ignore[attr-defined]

        # Always update the priority array via base class
        super()._write_with_priority(prop_id, value, priority, value_source)  # type: ignore[misc]

        now = time.monotonic()

        # If currently locked, restore locked value
        if self._min_time_lock_until is not None and now < self._min_time_lock_until:
            self._properties[prop_id] = self._min_time_locked_value  # type: ignore[attr-defined]
            return

        # Clear any expired lock
        if self._min_time_lock_until is not None:
            self._min_time_lock_until = None
            self._min_time_locked_value = None

        # Check if present_value changed; if so, start new lock
        new_pv = self._properties.get(PropertyIdentifier.PRESENT_VALUE)  # type: ignore[attr-defined]
        if new_pv != old_pv and old_pv is not None:
            self._start_lock_if_needed(new_pv, now)

    def _start_lock_if_needed(self, pv: BinaryPV, now: float) -> None:
        """Start a min-time lock if the relevant property is configured."""
        if pv == BinaryPV.ACTIVE:
            min_on = self._properties.get(PropertyIdentifier.MINIMUM_ON_TIME)  # type: ignore[attr-defined]
            if min_on and min_on > 0:
                self._min_time_lock_until = now + min_on
                self._min_time_locked_value = pv
        elif pv == BinaryPV.INACTIVE:
            min_off = self._properties.get(PropertyIdentifier.MINIMUM_OFF_TIME)  # type: ignore[attr-defined]
            if min_off and min_off > 0:
                self._min_time_lock_until = now + min_off
                self._min_time_locked_value = pv

    def check_min_time_expiry(self) -> bool:
        """Check if the lock has expired and re-evaluate present_value.

        Should be called periodically (e.g. by the ScheduleEngine or a
        dedicated timer).

        Returns:
            ``True`` if the lock expired and present_value was re-evaluated.
        """
        if self._min_time_lock_until is None:
            return False
        if time.monotonic() < self._min_time_lock_until:
            return False

        old_locked = self._min_time_locked_value
        self._min_time_lock_until = None
        self._min_time_locked_value = None

        # Re-resolve present_value from priority array
        pa = self._priority_array  # type: ignore[attr-defined]
        if pa is None:
            return True

        new_pv = None
        for slot in pa:
            if slot is not None:
                new_pv = slot
                break
        if new_pv is None:
            new_pv = self._properties.get(PropertyIdentifier.RELINQUISH_DEFAULT)  # type: ignore[attr-defined]

        self._properties[PropertyIdentifier.PRESENT_VALUE] = new_pv  # type: ignore[attr-defined]

        # If new value differs from what was locked, may need a new lock
        if new_pv != old_locked and new_pv is not None:
            self._start_lock_if_needed(new_pv, time.monotonic())

        return True


@register_object_type
class BinaryInputObject(_BinaryPolarityMixin, BACnetObject):
    """BACnet Binary Input object (Clause 12.6).

    Represents a binary sensor input (on/off, open/closed).
    Present_Value is read-only under normal operation and
    writable only when Out_Of_Service is TRUE.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_INPUT
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.CHANGE_OF_STATE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **status_properties(),
        PropertyIdentifier.POLARITY: PropertyDefinition(
            PropertyIdentifier.POLARITY,
            Polarity,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Polarity.NORMAL,
        ),
        PropertyIdentifier.INACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.INACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ALARM_VALUE: PropertyDefinition(
            PropertyIdentifier.ALARM_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **intrinsic_reporting_properties(),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class BinaryOutputObject(_MinOnOffTimeMixin, _BinaryPolarityMixin, BACnetObject):
    """BACnet Binary Output object (Clause 12.7).

    Represents a binary actuator output (relay, fan on/off).
    Always commandable with a 16-level priority array.
    Supports Minimum On/Off Time enforcement per Clause 19.2.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_OUTPUT
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.CHANGE_OF_STATE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **status_properties(),
        PropertyIdentifier.POLARITY: PropertyDefinition(
            PropertyIdentifier.POLARITY,
            Polarity,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Polarity.NORMAL,
        ),
        PropertyIdentifier.INACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.INACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_OFF_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_OFF_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_ON_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_ON_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(BinaryPV, BinaryPV.INACTIVE),
        PropertyIdentifier.FEEDBACK_VALUE: PropertyDefinition(
            PropertyIdentifier.FEEDBACK_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        **intrinsic_reporting_properties(),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Always commandable
        self._init_commandable(BinaryPV.INACTIVE)
        self._init_min_time()
        self._init_status_flags()


@register_object_type
class BinaryValueObject(_MinOnOffTimeMixin, BACnetObject):
    """BACnet Binary Value object (Clause 12.8).

    Represents an internal binary status or configuration value.
    Optionally commandable when constructed with ``commandable=True``.
    Supports Minimum On/Off Time enforcement per Clause 19.2.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_VALUE
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.CHANGE_OF_STATE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        **status_properties(),
        PropertyIdentifier.INACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.INACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_OFF_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_OFF_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_ON_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_ON_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(BinaryPV, BinaryPV.INACTIVE, required=False),
        PropertyIdentifier.ALARM_VALUE: PropertyDefinition(
            PropertyIdentifier.ALARM_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **intrinsic_reporting_properties(),
    }

    def __init__(
        self,
        instance_number: int,
        *,
        commandable: bool = False,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        if commandable:
            self._init_commandable(BinaryPV.INACTIVE)
        self._init_min_time()
        self._init_status_flags()
