"""BACnet object base classes per ASHRAE 135-2016 Clause 12."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, ClassVar

from bac_py.services.errors import BACnetError
from bac_py.types.enums import ErrorClass, ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class PropertyAccess(IntEnum):
    """Property access mode."""

    READ_ONLY = 0
    READ_WRITE = 1
    WRITE_ONLY = 2


@dataclass(frozen=True, slots=True)
class PropertyDefinition:
    """Metadata for a single BACnet property."""

    identifier: PropertyIdentifier
    datatype: type
    access: PropertyAccess
    required: bool
    default: Any = None


class BACnetObject:
    """Base class for all BACnet objects.

    Each subclass defines its property schema via class-level
    PROPERTY_DEFINITIONS. Properties are stored in a dict and
    accessed via typed read/write methods.
    """

    OBJECT_TYPE: ClassVar[ObjectType]
    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]]

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        self._object_id = ObjectIdentifier(self.OBJECT_TYPE, instance_number)
        self._properties: dict[PropertyIdentifier, Any] = {}
        self._priority_array: list[Any | None] | None = None
        self._write_lock = asyncio.Lock()

        # Set defaults from property definitions
        for prop_id, prop_def in self.PROPERTY_DEFINITIONS.items():
            if prop_def.default is not None:
                self._properties[prop_id] = prop_def.default

        # Set object-identifier and object-type (always required)
        self._properties[PropertyIdentifier.OBJECT_IDENTIFIER] = self._object_id
        self._properties[PropertyIdentifier.OBJECT_TYPE] = self.OBJECT_TYPE

        # Apply initial property overrides
        for key, value in initial_properties.items():
            prop_id = PropertyIdentifier[key.upper()]
            self._properties[prop_id] = value

    @property
    def object_identifier(self) -> ObjectIdentifier:
        """The object identifier for this object."""
        return self._object_id

    def read_property(
        self,
        prop_id: PropertyIdentifier,
        array_index: int | None = None,
    ) -> Any:
        """Read a property value.

        Args:
            prop_id: Property identifier to read.
            array_index: Optional array index for array properties.

        Returns:
            The property value.

        Raises:
            BACnetError: If the property is unknown or array index is invalid.
        """
        if prop_id == PropertyIdentifier.PROPERTY_LIST:
            return self._get_property_list()

        if prop_id == PropertyIdentifier.CURRENT_COMMAND_PRIORITY:
            return self._get_current_command_priority()

        if prop_id not in self.PROPERTY_DEFINITIONS:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        value = self._properties.get(prop_id)
        if value is None and self.PROPERTY_DEFINITIONS[prop_id].required:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

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

        Args:
            prop_id: Property identifier to write.
            value: Value to write.
            priority: Optional priority for commandable properties (1-16).
            array_index: Optional array index for array properties.

        Raises:
            BACnetError: If the property is unknown, read-only, or
                priority/index is invalid.
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

        if self._is_commandable(prop_id):
            effective_priority = priority if priority is not None else 16
            self._write_with_priority(prop_id, value, effective_priority)
        elif array_index is not None:
            self._write_array_element(prop_id, value, array_index)
        else:
            self._properties[prop_id] = value

    async def async_write_property(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property value with concurrency protection.

        Uses an asyncio.Lock to serialize writes to this object.
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
        """Return list of all properties present on this object.

        Per the BACnet standard, Property_List shall not include
        Object_Identifier, Object_Name, Object_Type, or Property_List.
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

        Returns the priority (1-16) of the highest-priority non-null
        slot in the priority array, or None if all slots are relinquished.
        Raises UNKNOWN_PROPERTY if the object is not commandable.
        """
        if self._priority_array is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        for i, slot in enumerate(self._priority_array):
            if slot is not None:
                return i + 1
        return None

    def _is_commandable(self, prop_id: PropertyIdentifier) -> bool:
        """Check if a property supports command prioritization (Clause 19.2)."""
        return prop_id == PropertyIdentifier.PRESENT_VALUE and self._priority_array is not None

    def _write_with_priority(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int,
    ) -> None:
        """Write to a commandable property using the priority array.

        BACnet priority 1 = highest, 16 = lowest.
        Priority 6 is reserved for Minimum On/Off (Clause 19.2.3).
        """
        if priority < 1 or priority > 16:
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.PARAMETER_OUT_OF_RANGE)
        if priority == 6:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        if self._priority_array is None:
            self._priority_array = [None] * 16

        if value is None:
            # Relinquish this priority level
            self._priority_array[priority - 1] = None
        else:
            self._priority_array[priority - 1] = value

        # Present Value = highest priority non-None value, or relinquish default
        for pv in self._priority_array:
            if pv is not None:
                self._properties[prop_id] = pv
                return
        # All relinquished - use relinquish default
        self._properties[prop_id] = self._properties.get(PropertyIdentifier.RELINQUISH_DEFAULT)

    def _write_array_element(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        array_index: int,
    ) -> None:
        """Write to a specific array element."""
        current = self._properties.get(prop_id)
        if not isinstance(current, list):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.PROPERTY_IS_NOT_AN_ARRAY)
        if array_index < 1 or array_index > len(current):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_ARRAY_INDEX)
        current[array_index - 1] = value


class ObjectDatabase:
    """Container for all BACnet objects in a device."""

    def __init__(self) -> None:
        self._objects: dict[ObjectIdentifier, BACnetObject] = {}

    def add(self, obj: BACnetObject) -> None:
        """Add an object to the database.

        Raises:
            BACnetError: If an object with the same identifier already exists.
        """
        if obj.object_identifier in self._objects:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.OBJECT_IDENTIFIER_ALREADY_EXISTS)
        self._objects[obj.object_identifier] = obj

    def remove(self, object_id: ObjectIdentifier) -> None:
        """Remove an object from the database.

        Raises:
            BACnetError: If the object doesn't exist or is a Device object.
        """
        if object_id not in self._objects:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if object_id.object_type == ObjectType.DEVICE:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.OBJECT_DELETION_NOT_PERMITTED)
        del self._objects[object_id]

    def get(self, object_id: ObjectIdentifier) -> BACnetObject | None:
        """Get an object by identifier, or None if not found."""
        return self._objects.get(object_id)

    def get_objects_of_type(self, obj_type: ObjectType) -> list[BACnetObject]:
        """Get all objects of a given type."""
        return [o for o in self._objects.values() if o.object_identifier.object_type == obj_type]

    @property
    def object_list(self) -> list[ObjectIdentifier]:
        """List of all object identifiers in the database."""
        return list(self._objects.keys())

    def __len__(self) -> int:
        return len(self._objects)


# Object type registry for factory creation
_OBJECT_REGISTRY: dict[ObjectType, type[BACnetObject]] = {}


def register_object_type(cls: type[BACnetObject]) -> type[BACnetObject]:
    """Class decorator to register an object type in the factory."""
    _OBJECT_REGISTRY[cls.OBJECT_TYPE] = cls
    return cls


def create_object(
    object_type: ObjectType,
    instance_number: int,
    **properties: Any,
) -> BACnetObject:
    """Create a BACnet object by type using the registry.

    Args:
        object_type: BACnet object type.
        instance_number: Instance number for the new object.
        **properties: Initial property values.

    Returns:
        New BACnetObject instance.

    Raises:
        BACnetError: If the object type is not registered.
    """
    cls = _OBJECT_REGISTRY.get(object_type)
    if cls is None:
        raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNSUPPORTED_OBJECT_TYPE)
    return cls(instance_number, **properties)
