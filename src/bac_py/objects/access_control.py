"""BACnet Access Control objects per ASHRAE 135-2020 Clauses 12.26, 12.31-12.37."""

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
    AccessCredentialDisable,
    AccessEvent,
    AccessPassbackMode,
    AccessUserType,
    AuthorizationMode,
    DoorAlarmState,
    DoorSecuredStatus,
    DoorStatus,
    EventType,
    LockStatus,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class AccessDoorObject(BACnetObject):
    """BACnet Access Door object (Clause 12.26).

    Represents a physical door with lock, alarm, and access control.
    Has a state machine (LOCKED -> UNLOCKED -> OPENED -> CLOSED -> LOCKED).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCESS_DOOR
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.ACCESS_EVENT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            DoorStatus,
            PropertyAccess.READ_WRITE,
            required=True,
            default=DoorStatus.CLOSED,
        ),
        **status_properties(),
        PropertyIdentifier.DOOR_STATUS: PropertyDefinition(
            PropertyIdentifier.DOOR_STATUS,
            DoorStatus,
            PropertyAccess.READ_ONLY,
            required=True,
            default=DoorStatus.CLOSED,
        ),
        PropertyIdentifier.LOCK_STATUS: PropertyDefinition(
            PropertyIdentifier.LOCK_STATUS,
            LockStatus,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LockStatus.LOCKED,
        ),
        PropertyIdentifier.SECURED_STATUS: PropertyDefinition(
            PropertyIdentifier.SECURED_STATUS,
            DoorSecuredStatus,
            PropertyAccess.READ_ONLY,
            required=True,
            default=DoorSecuredStatus.SECURED,
        ),
        PropertyIdentifier.DOOR_ALARM_STATE: PropertyDefinition(
            PropertyIdentifier.DOOR_ALARM_STATE,
            DoorAlarmState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=DoorAlarmState.NORMAL,
        ),
        PropertyIdentifier.DOOR_MEMBERS: PropertyDefinition(
            PropertyIdentifier.DOOR_MEMBERS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.DOOR_PULSE_TIME: PropertyDefinition(
            PropertyIdentifier.DOOR_PULSE_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=3,
        ),
        PropertyIdentifier.DOOR_EXTENDED_PULSE_TIME: PropertyDefinition(
            PropertyIdentifier.DOOR_EXTENDED_PULSE_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=10,
        ),
        PropertyIdentifier.DOOR_UNLOCK_DELAY_TIME: PropertyDefinition(
            PropertyIdentifier.DOOR_UNLOCK_DELAY_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.DOOR_OPEN_TOO_LONG_TIME: PropertyDefinition(
            PropertyIdentifier.DOOR_OPEN_TOO_LONG_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MASKED_ALARM_VALUES: PropertyDefinition(
            PropertyIdentifier.MASKED_ALARM_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MAINTENANCE_REQUIRED: PropertyDefinition(
            PropertyIdentifier.MAINTENANCE_REQUIRED,
            bool,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class AccessPointObject(BACnetObject):
    """BACnet Access Point object (Clause 12.31).

    Represents a logical access point controlling one or more doors.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCESS_POINT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.ACCESS_EVENT: PropertyDefinition(
            PropertyIdentifier.ACCESS_EVENT,
            AccessEvent,
            PropertyAccess.READ_ONLY,
            required=True,
            default=AccessEvent.NONE,
        ),
        PropertyIdentifier.ACCESS_EVENT_TIME: PropertyDefinition(
            PropertyIdentifier.ACCESS_EVENT_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.ACCESS_EVENT_CREDENTIAL: PropertyDefinition(
            PropertyIdentifier.ACCESS_EVENT_CREDENTIAL,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.ACCESS_DOORS: PropertyDefinition(
            PropertyIdentifier.ACCESS_DOORS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.AUTHORIZATION_MODE: PropertyDefinition(
            PropertyIdentifier.AUTHORIZATION_MODE,
            AuthorizationMode,
            PropertyAccess.READ_WRITE,
            required=True,
            default=AuthorizationMode.AUTHORIZE,
        ),
        PropertyIdentifier.AUTHENTICATION_POLICY_LIST: PropertyDefinition(
            PropertyIdentifier.AUTHENTICATION_POLICY_LIST,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.AUTHENTICATION_POLICY_NAMES: PropertyDefinition(
            PropertyIdentifier.AUTHENTICATION_POLICY_NAMES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_AUTHENTICATION_POLICY: PropertyDefinition(
            PropertyIdentifier.ACTIVE_AUTHENTICATION_POLICY,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.AUTHORIZATION_EXEMPTIONS: PropertyDefinition(
            PropertyIdentifier.AUTHORIZATION_EXEMPTIONS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.VERIFICATION_TIME: PropertyDefinition(
            PropertyIdentifier.VERIFICATION_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACCESS_EVENT_TAG: PropertyDefinition(
            PropertyIdentifier.ACCESS_EVENT_TAG,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.ACCESS_EVENT_AUTHENTICATION_FACTOR: PropertyDefinition(
            PropertyIdentifier.ACCESS_EVENT_AUTHENTICATION_FACTOR,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.ACCESS_TRANSACTION_EVENTS: PropertyDefinition(
            PropertyIdentifier.ACCESS_TRANSACTION_EVENTS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACCESS_ALARM_EVENTS: PropertyDefinition(
            PropertyIdentifier.ACCESS_ALARM_EVENTS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.TRANSACTION_NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.TRANSACTION_NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class AccessZoneObject(BACnetObject):
    """BACnet Access Zone object (Clause 12.32).

    Represents a physical zone entered through access points.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCESS_ZONE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.GLOBAL_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.GLOBAL_IDENTIFIER,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.OCCUPANCY_STATE: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_STATE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.OCCUPANCY_COUNT: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_COUNT,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.OCCUPANCY_COUNT_ENABLE: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_COUNT_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
        PropertyIdentifier.OCCUPANCY_COUNT_ADJUST: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_COUNT_ADJUST,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.OCCUPANCY_UPPER_LIMIT: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_UPPER_LIMIT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.OCCUPANCY_LOWER_LIMIT: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_LOWER_LIMIT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.OCCUPANCY_UPPER_LIMIT_ENFORCED: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_UPPER_LIMIT_ENFORCED,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.OCCUPANCY_LOWER_LIMIT_ENFORCED: PropertyDefinition(
            PropertyIdentifier.OCCUPANCY_LOWER_LIMIT_ENFORCED,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ENTRY_POINTS: PropertyDefinition(
            PropertyIdentifier.ENTRY_POINTS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.EXIT_POINTS: PropertyDefinition(
            PropertyIdentifier.EXIT_POINTS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.PASSBACK_MODE: PropertyDefinition(
            PropertyIdentifier.PASSBACK_MODE,
            AccessPassbackMode,
            PropertyAccess.READ_WRITE,
            required=False,
            default=AccessPassbackMode.PASSBACK_OFF,
        ),
        PropertyIdentifier.PASSBACK_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.PASSBACK_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CREDENTIALS_IN_ZONE: PropertyDefinition(
            PropertyIdentifier.CREDENTIALS_IN_ZONE,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_CREDENTIAL_ADDED: PropertyDefinition(
            PropertyIdentifier.LAST_CREDENTIAL_ADDED,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_CREDENTIAL_ADDED_TIME: PropertyDefinition(
            PropertyIdentifier.LAST_CREDENTIAL_ADDED_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_CREDENTIAL_REMOVED: PropertyDefinition(
            PropertyIdentifier.LAST_CREDENTIAL_REMOVED,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_CREDENTIAL_REMOVED_TIME: PropertyDefinition(
            PropertyIdentifier.LAST_CREDENTIAL_REMOVED_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class AccessUserObject(BACnetObject):
    """BACnet Access User object (Clause 12.35).

    Represents a person or asset with access credentials.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCESS_USER

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.GLOBAL_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.GLOBAL_IDENTIFIER,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.USER_TYPE: PropertyDefinition(
            PropertyIdentifier.USER_TYPE,
            AccessUserType,
            PropertyAccess.READ_WRITE,
            required=True,
            default=AccessUserType.PERSON,
        ),
        PropertyIdentifier.USER_NAME: PropertyDefinition(
            PropertyIdentifier.USER_NAME,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.USER_EXTERNAL_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.USER_EXTERNAL_IDENTIFIER,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.USER_INFORMATION_REFERENCE: PropertyDefinition(
            PropertyIdentifier.USER_INFORMATION_REFERENCE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CREDENTIALS: PropertyDefinition(
            PropertyIdentifier.CREDENTIALS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.MEMBERS: PropertyDefinition(
            PropertyIdentifier.MEMBERS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MEMBER_OF: PropertyDefinition(
            PropertyIdentifier.MEMBER_OF,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class AccessRightsObject(BACnetObject):
    """BACnet Access Rights object (Clause 12.34).

    Defines access rules mapping users/credentials to access points.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCESS_RIGHTS

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.GLOBAL_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.GLOBAL_IDENTIFIER,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.POSITIVE_ACCESS_RULES: PropertyDefinition(
            PropertyIdentifier.POSITIVE_ACCESS_RULES,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.NEGATIVE_ACCESS_RULES: PropertyDefinition(
            PropertyIdentifier.NEGATIVE_ACCESS_RULES,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.ACCOMPANIMENT: PropertyDefinition(
            PropertyIdentifier.ACCOMPANIMENT,
            object,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class AccessCredentialObject(BACnetObject):
    """BACnet Access Credential object (Clause 12.35).

    Represents a physical or logical credential (card, PIN, biometric).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCESS_CREDENTIAL

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.GLOBAL_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.GLOBAL_IDENTIFIER,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.CREDENTIAL_STATUS: PropertyDefinition(
            PropertyIdentifier.CREDENTIAL_STATUS,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.CREDENTIAL_DISABLE: PropertyDefinition(
            PropertyIdentifier.CREDENTIAL_DISABLE,
            AccessCredentialDisable,
            PropertyAccess.READ_WRITE,
            required=True,
            default=AccessCredentialDisable.NONE,
        ),
        PropertyIdentifier.AUTHENTICATION_FACTORS: PropertyDefinition(
            PropertyIdentifier.AUTHENTICATION_FACTORS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.ACTIVATION_TIME: PropertyDefinition(
            PropertyIdentifier.ACTIVATION_TIME,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.EXPIRATION_TIME: PropertyDefinition(
            PropertyIdentifier.EXPIRATION_TIME,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.ASSIGNED_ACCESS_RIGHTS: PropertyDefinition(
            PropertyIdentifier.ASSIGNED_ACCESS_RIGHTS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.DAYS_REMAINING: PropertyDefinition(
            PropertyIdentifier.DAYS_REMAINING,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.USES_REMAINING: PropertyDefinition(
            PropertyIdentifier.USES_REMAINING,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ABSENTEE_LIMIT: PropertyDefinition(
            PropertyIdentifier.ABSENTEE_LIMIT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BELONGS_TO: PropertyDefinition(
            PropertyIdentifier.BELONGS_TO,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_ACCESS_POINT: PropertyDefinition(
            PropertyIdentifier.LAST_ACCESS_POINT,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_ACCESS_EVENT: PropertyDefinition(
            PropertyIdentifier.LAST_ACCESS_EVENT,
            AccessEvent,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_USE_TIME: PropertyDefinition(
            PropertyIdentifier.LAST_USE_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class CredentialDataInputObject(BACnetObject):
    """BACnet Credential Data Input object (Clause 12.37).

    Represents a credential reader device (card reader, keypad, etc.).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.CREDENTIAL_DATA_INPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        **status_properties(),
        PropertyIdentifier.SUPPORTED_FORMATS: PropertyDefinition(
            PropertyIdentifier.SUPPORTED_FORMATS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.SUPPORTED_FORMAT_CLASSES: PropertyDefinition(
            PropertyIdentifier.SUPPORTED_FORMAT_CLASSES,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.UPDATE_TIME: PropertyDefinition(
            PropertyIdentifier.UPDATE_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
