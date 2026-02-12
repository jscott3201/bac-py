"""BACnet Staging object per ASHRAE 135-2020 Clause 12.62 (new in 2020)."""

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
    ObjectType,
    PropertyIdentifier,
    StagingState,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class StagingObject(BACnetObject):
    """BACnet Staging object (Clause 12.62, new in 2020).

    Two-phase write mechanism.  Writes to Present_Value are staged
    and can be committed or abandoned.  State machine transitions:
    NOT_STAGED -> STAGING -> STAGED -> COMMITTING -> COMMITTED
    or STAGED -> ABANDONING -> ABANDONED.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.STAGING

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        **status_properties(),
        PropertyIdentifier.STAGING_STATE: PropertyDefinition(
            PropertyIdentifier.STAGING_STATE,
            StagingState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=StagingState.NOT_STAGED,
        ),
        PropertyIdentifier.TARGET_OBJECT: PropertyDefinition(
            PropertyIdentifier.TARGET_OBJECT,
            ObjectIdentifier,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.TARGET_PROPERTY: PropertyDefinition(
            PropertyIdentifier.TARGET_PROPERTY,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.STAGING_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.STAGING_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
