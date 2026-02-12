"""BACnet Averaging object per ASHRAE 135-2020 Clause 12.5."""

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
from bac_py.types.constructed import BACnetDateTime, BACnetDeviceObjectPropertyReference
from bac_py.types.enums import (
    EngineeringUnits,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class AveragingObject(BACnetObject):
    """BACnet Averaging object (Clause 12.5).

    Periodically samples a referenced property and computes
    minimum, average, and maximum values over a window.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.AVERAGING

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.MINIMUM_VALUE: PropertyDefinition(
            PropertyIdentifier.MINIMUM_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.AVERAGE_VALUE: PropertyDefinition(
            PropertyIdentifier.AVERAGE_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.MAXIMUM_VALUE: PropertyDefinition(
            PropertyIdentifier.MAXIMUM_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.MINIMUM_VALUE_TIMESTAMP: PropertyDefinition(
            PropertyIdentifier.MINIMUM_VALUE_TIMESTAMP,
            BACnetDateTime,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAXIMUM_VALUE_TIMESTAMP: PropertyDefinition(
            PropertyIdentifier.MAXIMUM_VALUE_TIMESTAMP,
            BACnetDateTime,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.VARIANCE_VALUE: PropertyDefinition(
            PropertyIdentifier.VARIANCE_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.OBJECT_PROPERTY_REFERENCE: PropertyDefinition(
            PropertyIdentifier.OBJECT_PROPERTY_REFERENCE,
            BACnetDeviceObjectPropertyReference,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.WINDOW_INTERVAL: PropertyDefinition(
            PropertyIdentifier.WINDOW_INTERVAL,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=60,
        ),
        PropertyIdentifier.WINDOW_SAMPLES: PropertyDefinition(
            PropertyIdentifier.WINDOW_SAMPLES,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=10,
        ),
        PropertyIdentifier.ATTEMPTED_SAMPLES: PropertyDefinition(
            PropertyIdentifier.ATTEMPTED_SAMPLES,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.VALID_SAMPLES: PropertyDefinition(
            PropertyIdentifier.VALID_SAMPLES,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
