"""BACnet Loop object per ASHRAE 135-2016 Clause 12.17."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.enums import (
    Action,
    EngineeringUnits,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class LoopObject(BACnetObject):
    """BACnet Loop object (Clause 12.17).

    Represents a PID control loop.  Present_Value is the manipulated
    variable output.  The control algorithm parameters (P, I, D
    constants) define the loop behavior.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LOOP

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
        PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE: PropertyDefinition(
            PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.CONTROLLED_VARIABLE_VALUE: PropertyDefinition(
            PropertyIdentifier.CONTROLLED_VARIABLE_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.CONTROLLED_VARIABLE_UNITS: PropertyDefinition(
            PropertyIdentifier.CONTROLLED_VARIABLE_UNITS,
            EngineeringUnits,
            PropertyAccess.READ_ONLY,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MANIPULATED_VARIABLE_REFERENCE: PropertyDefinition(
            PropertyIdentifier.MANIPULATED_VARIABLE_REFERENCE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.SETPOINT_REFERENCE: PropertyDefinition(
            PropertyIdentifier.SETPOINT_REFERENCE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.SETPOINT: PropertyDefinition(
            PropertyIdentifier.SETPOINT,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.ACTION: PropertyDefinition(
            PropertyIdentifier.ACTION,
            Action,
            PropertyAccess.READ_WRITE,
            required=True,
            default=Action.DIRECT,
        ),
        PropertyIdentifier.PROPORTIONAL_CONSTANT: PropertyDefinition(
            PropertyIdentifier.PROPORTIONAL_CONSTANT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0.0,
        ),
        PropertyIdentifier.PROPORTIONAL_CONSTANT_UNITS: PropertyDefinition(
            PropertyIdentifier.PROPORTIONAL_CONSTANT_UNITS,
            EngineeringUnits,
            PropertyAccess.READ_ONLY,
            required=False,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.INTEGRAL_CONSTANT: PropertyDefinition(
            PropertyIdentifier.INTEGRAL_CONSTANT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0.0,
        ),
        PropertyIdentifier.INTEGRAL_CONSTANT_UNITS: PropertyDefinition(
            PropertyIdentifier.INTEGRAL_CONSTANT_UNITS,
            EngineeringUnits,
            PropertyAccess.READ_ONLY,
            required=False,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.DERIVATIVE_CONSTANT: PropertyDefinition(
            PropertyIdentifier.DERIVATIVE_CONSTANT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0.0,
        ),
        PropertyIdentifier.DERIVATIVE_CONSTANT_UNITS: PropertyDefinition(
            PropertyIdentifier.DERIVATIVE_CONSTANT_UNITS,
            EngineeringUnits,
            PropertyAccess.READ_ONLY,
            required=False,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MAXIMUM_OUTPUT: PropertyDefinition(
            PropertyIdentifier.MAXIMUM_OUTPUT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=100.0,
        ),
        PropertyIdentifier.MINIMUM_OUTPUT: PropertyDefinition(
            PropertyIdentifier.MINIMUM_OUTPUT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0.0,
        ),
        PropertyIdentifier.PRIORITY_FOR_WRITING: PropertyDefinition(
            PropertyIdentifier.PRIORITY_FOR_WRITING,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=16,
        ),
        PropertyIdentifier.UPDATE_INTERVAL: PropertyDefinition(
            PropertyIdentifier.UPDATE_INTERVAL,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
            default=100,
        ),
        PropertyIdentifier.OUTPUT_UNITS: PropertyDefinition(
            PropertyIdentifier.OUTPUT_UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.BIAS: PropertyDefinition(
            PropertyIdentifier.BIAS,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
        # Object property references default to empty if not provided
        if PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE not in self._properties:
            self._properties[PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE] = None
        if PropertyIdentifier.MANIPULATED_VARIABLE_REFERENCE not in self._properties:
            self._properties[PropertyIdentifier.MANIPULATED_VARIABLE_REFERENCE] = None
        if PropertyIdentifier.SETPOINT_REFERENCE not in self._properties:
            self._properties[PropertyIdentifier.SETPOINT_REFERENCE] = None
