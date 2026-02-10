"""BACnet object base classes per ASHRAE 135-2016 Clause 12."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ErrorClass,
    ErrorCode,
    EventState,
    NotifyType,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import BACnetDouble, BitString, ObjectIdentifier


class PropertyAccess(IntEnum):
    """Property access mode."""

    READ_ONLY = 0
    READ_WRITE = 1


@dataclass(frozen=True, slots=True)
class PropertyDefinition:
    """Metadata for a single BACnet property."""

    identifier: PropertyIdentifier
    """The :class:`PropertyIdentifier` for this property."""
    datatype: type
    """Expected Python type for the property value."""
    access: PropertyAccess
    """Read-only or read-write access mode."""
    required: bool
    """Whether the property is required by the BACnet standard."""
    default: Any = None
    """Default value assigned on object creation, or ``None``."""


def standard_properties() -> dict[PropertyIdentifier, PropertyDefinition]:
    """Return properties common to all BACnet objects (Clause 12.1).

    Includes the required Object_Identifier/Object_Name/Object_Type
    triad, the optional Description, and the required Property_List.

    :returns: Mapping of :class:`PropertyIdentifier` to :class:`PropertyDefinition`.
    """
    return {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER,
            ObjectIdentifier,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_NAME: PropertyDefinition(
            PropertyIdentifier.OBJECT_NAME,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE,
            ObjectType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
    }


def status_properties(
    *,
    event_state_required: bool = True,
    reliability_required: bool = False,
    reliability_default: Reliability | None = None,
    include_out_of_service: bool = True,
) -> dict[PropertyIdentifier, PropertyDefinition]:
    """Return status monitoring properties shared by most objects (Clause 12).

    Includes Status_Flags, Event_State, Reliability, and optionally
    Out_Of_Service.  Keyword arguments allow per-object-type overrides.

    :param event_state_required: Whether Event_State is required.
    :param reliability_required: Whether Reliability is required.
    :param reliability_default: Default value for Reliability, or ``None``.
    :param include_out_of_service: Whether to include the Out_Of_Service property.
    :returns: Mapping of :class:`PropertyIdentifier` to :class:`PropertyDefinition`.
    """
    props: dict[PropertyIdentifier, PropertyDefinition] = {
        PropertyIdentifier.STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.STATUS_FLAGS,
            StatusFlags,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.EVENT_STATE: PropertyDefinition(
            PropertyIdentifier.EVENT_STATE,
            EventState,
            PropertyAccess.READ_ONLY,
            required=event_state_required,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=reliability_required,
            default=reliability_default,
        ),
    }
    if include_out_of_service:
        props[PropertyIdentifier.OUT_OF_SERVICE] = PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        )
    return props


def commandable_properties(
    value_type: type,
    default: Any,
    *,
    required: bool = True,
) -> dict[PropertyIdentifier, PropertyDefinition]:
    """Return properties for commandable objects (Clause 19).

    :param value_type: Type of the Relinquish_Default value.
    :param default: Default value for Relinquish_Default.
    :param required: Whether commandable properties are required
        (``True`` for Output objects, ``False`` for optionally commandable Values).
    :returns: Mapping of :class:`PropertyIdentifier` to :class:`PropertyDefinition`.
    """
    return {
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=required,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            value_type,
            PropertyAccess.READ_WRITE,
            required=required,
            default=default if required else None,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=required,
        ),
    }


def intrinsic_reporting_properties(
    *,
    include_limit: bool = False,
) -> dict[PropertyIdentifier, PropertyDefinition]:
    """Return optional intrinsic reporting properties (Clause 12, Clause 13).

    These properties enable alarm/event reporting without a separate
    EventEnrollment object.  All are optional -- objects opt in by
    merging this dict into their PROPERTY_DEFINITIONS.

    :param include_limit: If ``True``, include analog-specific limit detection
        properties (High_Limit, Low_Limit, Deadband, Limit_Enable).
    :returns: Mapping of :class:`PropertyIdentifier` to :class:`PropertyDefinition`.
    """
    props: dict[PropertyIdentifier, PropertyDefinition] = {
        PropertyIdentifier.TIME_DELAY: PropertyDefinition(
            PropertyIdentifier.TIME_DELAY,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EVENT_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_ENABLE,
            BitString,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACKED_TRANSITIONS: PropertyDefinition(
            PropertyIdentifier.ACKED_TRANSITIONS,
            BitString,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.NOTIFY_TYPE: PropertyDefinition(
            PropertyIdentifier.NOTIFY_TYPE,
            NotifyType,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EVENT_TIME_STAMPS: PropertyDefinition(
            PropertyIdentifier.EVENT_TIME_STAMPS,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.EVENT_DETECTION_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_DETECTION_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EVENT_MESSAGE_TEXTS: PropertyDefinition(
            PropertyIdentifier.EVENT_MESSAGE_TEXTS,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG: PropertyDefinition(
            PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }
    if include_limit:
        props[PropertyIdentifier.HIGH_LIMIT] = PropertyDefinition(
            PropertyIdentifier.HIGH_LIMIT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        )
        props[PropertyIdentifier.LOW_LIMIT] = PropertyDefinition(
            PropertyIdentifier.LOW_LIMIT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        )
        props[PropertyIdentifier.DEADBAND] = PropertyDefinition(
            PropertyIdentifier.DEADBAND,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        )
        props[PropertyIdentifier.LIMIT_ENABLE] = PropertyDefinition(
            PropertyIdentifier.LIMIT_ENABLE,
            BitString,
            PropertyAccess.READ_WRITE,
            required=False,
        )
    return props


class BACnetObject:
    """Base class for all BACnet objects.

    Each subclass defines its property schema via class-level
    PROPERTY_DEFINITIONS. Properties are stored in a dict and
    accessed via typed read/write methods.
    """

    OBJECT_TYPE: ClassVar[ObjectType]
    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]]

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        """Initialize a BACnet object with default and overridden properties.

        :param instance_number: The BACnet instance number for this object.
        :param initial_properties: Property values keyed by uppercase property
            name (e.g., ``object_name="MyObject"``).
        """
        self._object_id = ObjectIdentifier(self.OBJECT_TYPE, instance_number)
        self._properties: dict[PropertyIdentifier, Any] = {}
        self._priority_array: list[Any | None] | None = None
        self._write_lock = asyncio.Lock()
        self._object_db: ObjectDatabase | None = None
        self._on_property_written: Callable[[PropertyIdentifier, Any, Any], None] | None = None

        # Set defaults from property definitions.
        # Use copy.copy() to prevent mutable defaults (e.g. lists) from
        # being shared across instances of the same object type.
        for prop_id, prop_def in self.PROPERTY_DEFINITIONS.items():
            if prop_def.default is not None:
                self._properties[prop_id] = copy.copy(prop_def.default)

        self._properties[PropertyIdentifier.OBJECT_IDENTIFIER] = self._object_id
        self._properties[PropertyIdentifier.OBJECT_TYPE] = self.OBJECT_TYPE

        for key, value in initial_properties.items():
            prop_id = PropertyIdentifier[key.upper()]
            self._properties[prop_id] = value

    @property
    def object_identifier(self) -> ObjectIdentifier:
        """The :class:`ObjectIdentifier` for this object."""
        return self._object_id

    def _init_status_flags(self) -> None:
        """Initialize Status_Flags to a default :class:`StatusFlags` if not already set."""
        self._set_default(PropertyIdentifier.STATUS_FLAGS, StatusFlags())

    def _set_default(self, prop_id: PropertyIdentifier, value: Any) -> None:
        """Set a property value only if it hasn't been set yet.

        :param prop_id: The property to set.
        :param value: The default value to assign.
        """
        if prop_id not in self._properties:
            self._properties[prop_id] = value

    def _init_commandable(self, relinquish_default: Any) -> None:
        """Initialize the priority array for a commandable object.

        :param relinquish_default: The value used when all priority slots
            are relinquished.
        """
        self._priority_array = [None] * 16
        self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
        self._set_default(PropertyIdentifier.RELINQUISH_DEFAULT, relinquish_default)

    @staticmethod
    def _coerce_value(prop_def: PropertyDefinition, value: Any) -> Any:
        """Coerce a value to the property's declared datatype if possible.

        Handles two cases:

        - IntEnum properties: plain ``int`` from wire decoding is coerced
          to the declared IntEnum subclass (e.g. ``1`` -> ``BinaryPV.ACTIVE``).
        - :class:`BACnetDouble` properties: plain ``float`` is wrapped in
          :class:`BACnetDouble` so it encodes as Double (tag 5) instead of
          Real (tag 4).

        :param prop_def: The :class:`PropertyDefinition` describing the target type.
        :param value: The value to coerce.
        :returns: The coerced value, or *value* unchanged if coercion is not
            applicable or it is already the correct type.
        """
        if value is None:
            return value
        dtype = prop_def.datatype
        if (
            dtype is not None
            and isinstance(value, int)
            and not isinstance(value, IntEnum)
            and not isinstance(value, bool)
            and issubclass(dtype, IntEnum)
        ):
            try:
                return dtype(value)
            except ValueError:
                return value
        if (
            dtype is BACnetDouble
            and isinstance(value, float)
            and not isinstance(value, BACnetDouble)
        ):
            return BACnetDouble(value)
        return value

    def read_property(
        self,
        prop_id: PropertyIdentifier,
        array_index: int | None = None,
    ) -> Any:
        """Read a property value.

        :param prop_id: Property identifier to read.
        :param array_index: Optional array index for array properties.
        :returns: The property value.
        :raises BACnetError: If the property is unknown or *array_index* is invalid.
        """
        if prop_id == PropertyIdentifier.PROPERTY_LIST:
            return self._get_property_list()

        if prop_id == PropertyIdentifier.CURRENT_COMMAND_PRIORITY:
            return self._get_current_command_priority()

        if prop_id == PropertyIdentifier.STATUS_FLAGS:
            return self._get_status_flags()

        if prop_id not in self.PROPERTY_DEFINITIONS:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        value = self._properties.get(prop_id)
        if value is None and self.PROPERTY_DEFINITIONS[prop_id].required:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.VALUE_NOT_INITIALIZED)

        if array_index is not None:
            if isinstance(value, (list, tuple)):
                if array_index == 0:
                    return len(value)
                if 1 <= array_index <= len(value):
                    return value[array_index - 1]
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_ARRAY_INDEX)
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.PROPERTY_IS_NOT_AN_ARRAY)

        return value

    def write_property(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property value.

        :param prop_id: Property identifier to write.
        :param value: Value to write.
        :param priority: Optional priority for commandable properties (1-16).
        :param array_index: Optional array index for array properties.
        :raises BACnetError: If the property is unknown, read-only, or
            *priority* / *array_index* is invalid.
        """
        prop_def = self.PROPERTY_DEFINITIONS.get(prop_id)
        if prop_def is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        if prop_def.access == PropertyAccess.READ_ONLY and not (
            # Present_Value is writable when Out_Of_Service is TRUE (Clause 12)
            prop_id == PropertyIdentifier.PRESENT_VALUE
            and self._properties.get(PropertyIdentifier.OUT_OF_SERVICE) is True
        ):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        # Object_Name uniqueness enforcement (Clause 12.1.5)
        if prop_id == PropertyIdentifier.OBJECT_NAME and self._object_db is not None:
            self._object_db.validate_name_unique(value, exclude=self._object_id)
            old_name = self._properties.get(PropertyIdentifier.OBJECT_NAME)
            self._object_db._update_name_index(self._object_id, old_name, value)
            self._object_db._increment_database_revision()

        value = self._coerce_value(prop_def, value)

        old_value = self._properties.get(prop_id)

        if self._is_commandable(prop_id):
            effective_priority = priority if priority is not None else 16
            self._write_with_priority(prop_id, value, effective_priority)
        elif array_index is not None:
            self._write_array_element(prop_id, value, array_index)
        else:
            self._properties[prop_id] = value

        # Fire write-change callback if registered (Annex A2)
        new_value = self._properties.get(prop_id)
        if self._on_property_written is not None and old_value != new_value:
            self._on_property_written(prop_id, old_value, new_value)

    async def async_write_property(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property value with concurrency protection.

        Uses an :class:`asyncio.Lock` to serialize writes to this object.

        :param prop_id: Property identifier to write.
        :param value: Value to write.
        :param priority: Optional priority for commandable properties (1-16).
        :param array_index: Optional array index for array properties.
        """
        async with self._write_lock:
            self.write_property(prop_id, value, priority, array_index)

    # Properties excluded from Property_List per Clause 12 / 12.11.
    _PROPERTY_LIST_EXCLUSIONS: ClassVar[frozenset[PropertyIdentifier]] = frozenset(
        {
            PropertyIdentifier.OBJECT_IDENTIFIER,
            PropertyIdentifier.OBJECT_NAME,
            PropertyIdentifier.OBJECT_TYPE,
            PropertyIdentifier.PROPERTY_LIST,
        }
    )

    def _get_property_list(self) -> list[PropertyIdentifier]:
        """Return the list of all properties present on this object.

        Per the BACnet standard, Property_List shall not include
        Object_Identifier, Object_Name, Object_Type, or Property_List.

        :returns: List of :class:`PropertyIdentifier` values excluding the
            standard triad and Property_List itself.
        """
        result = [
            pid
            for pid in self.PROPERTY_DEFINITIONS
            if pid not in self._PROPERTY_LIST_EXCLUSIONS
            and (pid in self._properties or self.PROPERTY_DEFINITIONS[pid].required)
        ]
        # Current_Command_Priority is a computed property (not stored in
        # _properties) that must appear in Property_List when the object
        # is commandable.
        if (
            self._priority_array is not None
            and PropertyIdentifier.CURRENT_COMMAND_PRIORITY in self.PROPERTY_DEFINITIONS
            and PropertyIdentifier.CURRENT_COMMAND_PRIORITY not in result
        ):
            result.append(PropertyIdentifier.CURRENT_COMMAND_PRIORITY)
        return result

    def _get_current_command_priority(self) -> int | None:
        """Return the active command priority level (Clause 19.5).

        Scans the priority array from highest (1) to lowest (16) and returns
        the index of the first non-null slot, or ``None`` if all slots are
        relinquished.

        :returns: The active priority level (1-16), or ``None``.
        :raises BACnetError: If the object is not commandable.
        """
        if self._priority_array is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        for i, slot in enumerate(self._priority_array):
            if slot is not None:
                return i + 1
        return None

    def _get_status_flags(self) -> StatusFlags:
        """Return :class:`StatusFlags` computed from related properties (Clause 12).

        IN_ALARM is ``True`` when Event_State is not NORMAL.
        FAULT is ``True`` when Reliability is present and not NO_FAULT_DETECTED.
        OVERRIDDEN is preserved from the stored value (hardware override).
        OUT_OF_SERVICE is read from the stored property.

        :returns: Computed :class:`StatusFlags` instance.
        :raises BACnetError: If the object does not define Status_Flags.
        """
        if PropertyIdentifier.STATUS_FLAGS not in self.PROPERTY_DEFINITIONS:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        # IN_ALARM: Event_State != NORMAL
        event_state = self._properties.get(PropertyIdentifier.EVENT_STATE)
        in_alarm = event_state is not None and event_state != EventState.NORMAL

        # FAULT: Reliability present and not NO_FAULT_DETECTED
        reliability = self._properties.get(PropertyIdentifier.RELIABILITY)
        fault = reliability is not None and reliability != Reliability.NO_FAULT_DETECTED

        # OUT_OF_SERVICE: direct property read
        out_of_service = bool(self._properties.get(PropertyIdentifier.OUT_OF_SERVICE, False))

        # OVERRIDDEN: preserve stored value (hardware override, not computable)
        stored = self._properties.get(PropertyIdentifier.STATUS_FLAGS)
        overridden = stored.overridden if isinstance(stored, StatusFlags) else False

        return StatusFlags(
            in_alarm=in_alarm,
            fault=fault,
            overridden=overridden,
            out_of_service=out_of_service,
        )

    def _is_commandable(self, prop_id: PropertyIdentifier) -> bool:
        """Check if a property supports command prioritization (Clause 19.2).

        :param prop_id: The property to check.
        :returns: ``True`` if *prop_id* is Present_Value and the object has a
            priority array.
        """
        return prop_id == PropertyIdentifier.PRESENT_VALUE and self._priority_array is not None

    def _write_with_priority(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int,
    ) -> None:
        """Write to a commandable property using the priority array.

        BACnet priority 1 = highest, 16 = lowest.
        Priority 6 is reserved for Minimum On/Off time objects
        (Clause 19.2.3) -- writes at priority 6 are rejected when
        the object defines Minimum_On_Time or Minimum_Off_Time.

        :param prop_id: The commandable property identifier to write.
        :param value: The value to write, or ``None`` to relinquish.
        :param priority: Priority level (1-16).
        :raises BACnetError: If *priority* is out of range or reserved.
        """
        if priority < 1 or priority > 16:
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.PARAMETER_OUT_OF_RANGE)
        if priority == 6 and (
            PropertyIdentifier.MINIMUM_ON_TIME in self.PROPERTY_DEFINITIONS
            or PropertyIdentifier.MINIMUM_OFF_TIME in self.PROPERTY_DEFINITIONS
        ):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        if self._priority_array is None:
            self._priority_array = [None] * 16

        if value is None:
            self._priority_array[priority - 1] = None
        else:
            self._priority_array[priority - 1] = value

        # Present Value = highest priority non-None value, or relinquish default
        for pv in self._priority_array:
            if pv is not None:
                self._properties[prop_id] = pv
                return
        self._properties[prop_id] = self._properties.get(PropertyIdentifier.RELINQUISH_DEFAULT)

    def _write_array_element(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        array_index: int,
    ) -> None:
        """Write to a specific element of an array property.

        :param prop_id: The array property identifier.
        :param value: The value to write at the given index.
        :param array_index: 1-based index into the array.
        :raises BACnetError: If the property is not an array or *array_index*
            is out of range.
        """
        current = self._properties.get(prop_id)
        if not isinstance(current, list):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.PROPERTY_IS_NOT_AN_ARRAY)
        if array_index < 1 or array_index > len(current):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_ARRAY_INDEX)
        current[array_index - 1] = value


class ObjectDatabase:
    """Container for all BACnet objects in a device.

    Enforces Object_Name uniqueness per Clause 12.1.5.
    """

    def __init__(self) -> None:
        self._objects: dict[ObjectIdentifier, BACnetObject] = {}
        self._names: dict[str, ObjectIdentifier] = {}

    def add(self, obj: BACnetObject) -> None:
        """Add an object to the database.

        :param obj: The :class:`BACnetObject` to register.
        :raises BACnetError: If an object with the same identifier or name
            already exists.
        """
        if obj.object_identifier in self._objects:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.OBJECT_IDENTIFIER_ALREADY_EXISTS)
        name = obj._properties.get(PropertyIdentifier.OBJECT_NAME)
        if name is not None and name in self._names:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.DUPLICATE_NAME)
        self._objects[obj.object_identifier] = obj
        if name is not None:
            self._names[name] = obj.object_identifier
        obj._object_db = self
        self._increment_database_revision()

    def remove(self, object_id: ObjectIdentifier) -> None:
        """Remove an object from the database.

        :param object_id: Identifier of the object to remove.
        :raises BACnetError: If the object does not exist or is a Device object.
        """
        if object_id not in self._objects:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if object_id.object_type == ObjectType.DEVICE:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.OBJECT_DELETION_NOT_PERMITTED)
        obj = self._objects[object_id]
        name = obj._properties.get(PropertyIdentifier.OBJECT_NAME)
        if name is not None and self._names.get(name) == object_id:
            del self._names[name]
        obj._object_db = None
        del self._objects[object_id]
        self._increment_database_revision()

    def validate_name_unique(self, name: str, exclude: ObjectIdentifier | None = None) -> None:
        """Check that a name is unique within the database.

        :param name: The object name to check.
        :param exclude: Object identifier to exclude (for rename operations).
        :raises BACnetError: If *name* is already in use by another object.
        """
        existing = self._names.get(name)
        if existing is not None and existing != exclude:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.DUPLICATE_NAME)

    def _update_name_index(
        self,
        object_id: ObjectIdentifier,
        old_name: str | None,
        new_name: str,
    ) -> None:
        """Update the name-to-identifier index after a rename.

        :param object_id: The identifier of the renamed object.
        :param old_name: The previous name, or ``None`` if not yet set.
        :param new_name: The new name to register.
        """
        if old_name is not None and self._names.get(old_name) == object_id:
            del self._names[old_name]
        self._names[new_name] = object_id

    def _increment_database_revision(self) -> None:
        """Increment Database_Revision on the Device object (Clause 12.11.23).

        Called when configuration changes: object add/remove, name changes.
        """
        for obj in self._objects.values():
            if obj.object_identifier.object_type == ObjectType.DEVICE:
                current = obj._properties.get(PropertyIdentifier.DATABASE_REVISION, 0)
                obj._properties[PropertyIdentifier.DATABASE_REVISION] = current + 1
                break

    def get(self, object_id: ObjectIdentifier) -> BACnetObject | None:
        """Retrieve an object by its identifier.

        :param object_id: The :class:`ObjectIdentifier` to look up.
        :returns: The :class:`BACnetObject`, or ``None`` if not found.
        """
        return self._objects.get(object_id)

    def get_objects_of_type(self, obj_type: ObjectType) -> list[BACnetObject]:
        """Retrieve all objects matching a given type.

        :param obj_type: The :class:`ObjectType` to filter by.
        :returns: List of matching :class:`BACnetObject` instances.
        """
        return [o for o in self._objects.values() if o.object_identifier.object_type == obj_type]

    @property
    def object_list(self) -> list[ObjectIdentifier]:
        """List of all :class:`ObjectIdentifier` values in the database."""
        return list(self._objects.keys())

    def __len__(self) -> int:
        """Return the number of objects in the database."""
        return len(self._objects)

    def __iter__(self) -> Iterator[ObjectIdentifier]:
        return iter(self._objects)

    def __contains__(self, object_id: object) -> bool:
        return object_id in self._objects

    def values(self) -> Iterator[BACnetObject]:
        """Iterate over all :class:`BACnetObject` instances in the database."""
        return iter(self._objects.values())


# Object type registry for factory creation
_OBJECT_REGISTRY: dict[ObjectType, type[BACnetObject]] = {}


def register_object_type(cls: type[BACnetObject]) -> type[BACnetObject]:
    """Class decorator to register a :class:`BACnetObject` subclass in the factory.

    :param cls: The :class:`BACnetObject` subclass to register.
    :returns: The same class, unmodified.
    """
    _OBJECT_REGISTRY[cls.OBJECT_TYPE] = cls
    return cls


def create_object(
    object_type: ObjectType,
    instance_number: int,
    **properties: Any,
) -> BACnetObject:
    """Create a :class:`BACnetObject` by type using the registry.

    :param object_type: BACnet object type.
    :param instance_number: Instance number for the new object.
    :param properties: Initial property values.
    :returns: New :class:`BACnetObject` instance.
    :raises BACnetError: If the object type is not registered.
    """
    cls = _OBJECT_REGISTRY.get(object_type)
    if cls is None:
        raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNSUPPORTED_OBJECT_TYPE)
    return cls(instance_number, **properties)
