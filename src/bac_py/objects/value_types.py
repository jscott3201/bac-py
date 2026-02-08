"""BACnet Value object types per ASHRAE 135-2016 Clause 12.36-12.45."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    commandable_properties,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.enums import (
    EngineeringUnits,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class IntegerValueObject(BACnetObject):
    """BACnet Integer Value object (Clause 12.43).

    Represents a signed integer value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.INTEGER_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        **status_properties(),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(int, 0, required=False),
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
            self._init_commandable(0)
        self._init_status_flags()


@register_object_type
class PositiveIntegerValueObject(BACnetObject):
    """BACnet Positive Integer Value object (Clause 12.44).

    Represents an unsigned integer value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.POSITIVE_INTEGER_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        **status_properties(),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(int, 0, required=False),
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
            self._init_commandable(0)
        self._init_status_flags()


@register_object_type
class LargeAnalogValueObject(BACnetObject):
    """BACnet Large Analog Value object (Clause 12.42).

    Represents a double-precision floating-point value.  Optionally
    commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LARGE_ANALOG_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        **status_properties(),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(float, 0.0, required=False),
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
            self._init_commandable(0.0)
        self._init_status_flags()


@register_object_type
class CharacterStringValueObject(BACnetObject):
    """BACnet CharacterString Value object (Clause 12.37).

    Represents a character string value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.CHARACTERSTRING_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
            default="",
        ),
        **status_properties(),
        **commandable_properties(str, "", required=False),
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
            self._init_commandable("")
        self._init_status_flags()


@register_object_type
class DateTimeValueObject(BACnetObject):
    """BACnet DateTime Value object (Clause 12.40).

    Represents a date/time value as a tuple.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.DATETIME_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            tuple,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        **status_properties(),
        **commandable_properties(tuple, None, required=False),
        PropertyIdentifier.IS_UTC: PropertyDefinition(
            PropertyIdentifier.IS_UTC,
            bool,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
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
            self._init_commandable(None)
        self._init_status_flags()


@register_object_type
class BitStringValueObject(BACnetObject):
    """BACnet BitString Value object (Clause 12.36).

    Represents a bit string value as a list of booleans.  Optionally
    commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BITSTRING_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        **status_properties(),
        PropertyIdentifier.BIT_TEXT: PropertyDefinition(
            PropertyIdentifier.BIT_TEXT,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BIT_MASK: PropertyDefinition(
            PropertyIdentifier.BIT_MASK,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        **commandable_properties(list, None, required=False),
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
            self._init_commandable(None)
        self._init_status_flags()


@register_object_type
class OctetStringValueObject(BACnetObject):
    """BACnet OctetString Value object (Clause 12.45).

    Represents a raw byte string value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.OCTETSTRING_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            bytes,
            PropertyAccess.READ_WRITE,
            required=True,
            default=b"",
        ),
        **status_properties(),
        **commandable_properties(bytes, b"", required=False),
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
            self._init_commandable(b"")
        self._init_status_flags()
