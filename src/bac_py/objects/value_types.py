"""BACnet Value object types per ASHRAE 135-2016 Clause 12.36-12.45."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
)
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    EngineeringUnits,
    EventState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class IntegerValueObject(BACnetObject):
    """BACnet Integer Value object (Clause 12.43).

    Represents a signed integer value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.INTEGER_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
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
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = 0
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class PositiveIntegerValueObject(BACnetObject):
    """BACnet Positive Integer Value object (Clause 12.44).

    Represents an unsigned integer value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.POSITIVE_INTEGER_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
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
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = 0
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class LargeAnalogValueObject(BACnetObject):
    """BACnet Large Analog Value object (Clause 12.42).

    Represents a double-precision floating-point value.  Optionally
    commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LARGE_ANALOG_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
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
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = 0.0
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class CharacterStringValueObject(BACnetObject):
    """BACnet CharacterString Value object (Clause 12.37).

    Represents a character string value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.CHARACTERSTRING_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
            default="",
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = ""
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class DateTimeValueObject(BACnetObject):
    """BACnet DateTime Value object (Clause 12.40).

    Represents a date/time value as a tuple.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.DATETIME_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            tuple,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            tuple,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.IS_UTC: PropertyDefinition(
            PropertyIdentifier.IS_UTC,
            bool,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class BitStringValueObject(BACnetObject):
    """BACnet BitString Value object (Clause 12.36).

    Represents a bit string value as a list of booleans.  Optionally
    commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BITSTRING_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
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
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class OctetStringValueObject(BACnetObject):
    """BACnet OctetString Value object (Clause 12.45).

    Represents a raw byte string value.  Optionally commandable when
    constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.OCTETSTRING_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
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
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            bytes,
            PropertyAccess.READ_WRITE,
            required=True,
            default=b"",
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = b""
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()
