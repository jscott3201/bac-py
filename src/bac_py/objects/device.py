"""BACnet Device object per ASHRAE 135-2016 Clause 12.11."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier, Segmentation
from bac_py.types.primitives import BitString, ObjectIdentifier


@register_object_type
class DeviceObject(BACnetObject):
    """BACnet Device object (Clause 12.11).

    Every BACnet device must have exactly one Device object.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.DEVICE

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
        PropertyIdentifier.SYSTEM_STATUS: PropertyDefinition(
            PropertyIdentifier.SYSTEM_STATUS,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,  # operational
        ),
        PropertyIdentifier.VENDOR_NAME: PropertyDefinition(
            PropertyIdentifier.VENDOR_NAME,
            str,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.VENDOR_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.VENDOR_IDENTIFIER,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.MODEL_NAME: PropertyDefinition(
            PropertyIdentifier.MODEL_NAME,
            str,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.FIRMWARE_REVISION: PropertyDefinition(
            PropertyIdentifier.FIRMWARE_REVISION,
            str,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.APPLICATION_SOFTWARE_VERSION: PropertyDefinition(
            PropertyIdentifier.APPLICATION_SOFTWARE_VERSION,
            str,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PROTOCOL_VERSION: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_VERSION,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=1,
        ),
        PropertyIdentifier.PROTOCOL_REVISION: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_REVISION,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=22,  # Revision 22 = ASHRAE 135-2016
        ),
        PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED,
            BitString,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED,
            BitString,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_LIST: PropertyDefinition(
            PropertyIdentifier.OBJECT_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED: PropertyDefinition(
            PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=1476,
        ),
        PropertyIdentifier.SEGMENTATION_SUPPORTED: PropertyDefinition(
            PropertyIdentifier.SEGMENTATION_SUPPORTED,
            Segmentation,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Segmentation.BOTH,
        ),
        PropertyIdentifier.MAX_SEGMENTS_ACCEPTED: PropertyDefinition(
            PropertyIdentifier.MAX_SEGMENTS_ACCEPTED,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=64,
        ),
        PropertyIdentifier.APDU_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.APDU_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=6000,
        ),
        PropertyIdentifier.NUMBER_OF_APDU_RETRIES: PropertyDefinition(
            PropertyIdentifier.NUMBER_OF_APDU_RETRIES,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=3,
        ),
        PropertyIdentifier.APDU_SEGMENT_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.APDU_SEGMENT_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=2000,
        ),
        PropertyIdentifier.DEVICE_ADDRESS_BINDING: PropertyDefinition(
            PropertyIdentifier.DEVICE_ADDRESS_BINDING,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.DATABASE_REVISION: PropertyDefinition(
            PropertyIdentifier.DATABASE_REVISION,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Initialize empty services/object-types supported if not provided
        self._set_default(
            PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED,
            BitString(b"\x00\x00\x00\x00\x00", 0),
        )
        self._set_default(
            PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED,
            BitString(b"\x00\x00\x00\x00\x00\x00\x00\x00", 0),
        )
        self._set_default(PropertyIdentifier.OBJECT_LIST, [])
