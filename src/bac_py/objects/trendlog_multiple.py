"""BACnet Trend Log Multiple object per ASHRAE 135-2020 Clause 12.30."""

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
from bac_py.types.constructed import BACnetDateTime
from bac_py.types.enums import (
    LoggingType,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class TrendLogMultipleObject(BACnetObject):
    """BACnet Trend Log Multiple object (Clause 12.30).

    Logs multiple properties simultaneously per sampling interval.
    Each log record contains values for all monitored properties.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.TREND_LOG_MULTIPLE

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
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
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
