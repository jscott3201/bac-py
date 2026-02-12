"""BACnet Device object per ASHRAE 135-2020 Clause 12.11."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
)
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    BackupAndRestoreState,
    DeviceStatus,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    Segmentation,
)
from bac_py.types.primitives import BitString


@register_object_type
class DeviceObject(BACnetObject):
    """BACnet Device object (Clause 12.11).

    Every BACnet device must have exactly one Device object.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.DEVICE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.SYSTEM_STATUS: PropertyDefinition(
            PropertyIdentifier.SYSTEM_STATUS,
            DeviceStatus,
            PropertyAccess.READ_ONLY,
            required=True,
            default=DeviceStatus.OPERATIONAL,
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
        PropertyIdentifier.ACTIVE_COV_SUBSCRIPTIONS: PropertyDefinition(
            PropertyIdentifier.ACTIVE_COV_SUBSCRIPTIONS,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.BACKUP_AND_RESTORE_STATE: PropertyDefinition(
            PropertyIdentifier.BACKUP_AND_RESTORE_STATE,
            BackupAndRestoreState,
            PropertyAccess.READ_ONLY,
            required=False,
            default=BackupAndRestoreState.IDLE,
        ),
        PropertyIdentifier.CONFIGURATION_FILES: PropertyDefinition(
            PropertyIdentifier.CONFIGURATION_FILES,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_RESTORE_TIME: PropertyDefinition(
            PropertyIdentifier.LAST_RESTORE_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.BACKUP_FAILURE_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.BACKUP_FAILURE_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
            default=300,
        ),
        PropertyIdentifier.BACKUP_PREPARATION_TIME: PropertyDefinition(
            PropertyIdentifier.BACKUP_PREPARATION_TIME,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESTORE_PREPARATION_TIME: PropertyDefinition(
            PropertyIdentifier.RESTORE_PREPARATION_TIME,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESTORE_COMPLETION_TIME: PropertyDefinition(
            PropertyIdentifier.RESTORE_COMPLETION_TIME,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROFILE_NAME: PropertyDefinition(
            PropertyIdentifier.PROFILE_NAME,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.PROFILE_LOCATION: PropertyDefinition(
            PropertyIdentifier.PROFILE_LOCATION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.TAGS: PropertyDefinition(
            PropertyIdentifier.TAGS,
            list,
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

    def read_property(
        self,
        prop_id: PropertyIdentifier,
        array_index: int | None = None,
    ) -> Any:
        """Read property with virtual Object_List from database (Clause 12.11.19)."""
        if prop_id == PropertyIdentifier.OBJECT_LIST and self._object_db is not None:
            all_ids = self._object_db.object_list
            if array_index is not None:
                if array_index == 0:
                    return len(all_ids)
                if 1 <= array_index <= len(all_ids):
                    return all_ids[array_index - 1]
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_ARRAY_INDEX)
            return all_ids
        return super().read_property(prop_id, array_index)
