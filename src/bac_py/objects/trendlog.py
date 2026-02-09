"""BACnet Trend Log object per ASHRAE 135-2016 Clause 12.25."""

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
    LoggingType,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class TrendLogObject(BACnetObject):
    """BACnet Trend Log object (Clause 12.25).

    Provides historical data logging with buffer management.
    Records are stored in an internal buffer and accessible via
    Log_Buffer.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.TREND_LOG

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.LOG_ENABLE: PropertyDefinition(
            PropertyIdentifier.LOG_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
        PropertyIdentifier.STOP_WHEN_FULL: PropertyDefinition(
            PropertyIdentifier.STOP_WHEN_FULL,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
        PropertyIdentifier.BUFFER_SIZE: PropertyDefinition(
            PropertyIdentifier.BUFFER_SIZE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.LOG_BUFFER: PropertyDefinition(
            PropertyIdentifier.LOG_BUFFER,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.RECORD_COUNT: PropertyDefinition(
            PropertyIdentifier.RECORD_COUNT,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.TOTAL_RECORD_COUNT: PropertyDefinition(
            PropertyIdentifier.TOTAL_RECORD_COUNT,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.LOGGING_TYPE: PropertyDefinition(
            PropertyIdentifier.LOGGING_TYPE,
            LoggingType,
            PropertyAccess.READ_WRITE,
            required=True,
            default=LoggingType.POLLED,
        ),
        PropertyIdentifier.LOG_INTERVAL: PropertyDefinition(
            PropertyIdentifier.LOG_INTERVAL,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.START_TIME: PropertyDefinition(
            PropertyIdentifier.START_TIME,
            BACnetDateTime,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.STOP_TIME: PropertyDefinition(
            PropertyIdentifier.STOP_TIME,
            BACnetDateTime,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY: PropertyDefinition(
            PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY,
            BACnetDeviceObjectPropertyReference,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ALIGN_INTERVALS: PropertyDefinition(
            PropertyIdentifier.ALIGN_INTERVALS,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.INTERVAL_OFFSET: PropertyDefinition(
            PropertyIdentifier.INTERVAL_OFFSET,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.TRIGGER: PropertyDefinition(
            PropertyIdentifier.TRIGGER,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
        self._set_default(PropertyIdentifier.LOG_BUFFER, [])
        self._set_default(PropertyIdentifier.LOGGING_TYPE, LoggingType.POLLED)
