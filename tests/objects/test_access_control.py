"""Tests for the BACnet Access Control objects."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestAccessDoorObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import AccessDoorObject
        from bac_py.types.enums import DoorAlarmState, DoorStatus, LockStatus

        obj = AccessDoorObject(1, object_name="door-1")
        assert obj.OBJECT_TYPE == ObjectType.ACCESS_DOOR
        assert obj.read_property(PropertyIdentifier.DOOR_STATUS) == DoorStatus.CLOSED
        assert obj.read_property(PropertyIdentifier.LOCK_STATUS) == LockStatus.LOCKED
        assert obj.read_property(PropertyIdentifier.DOOR_ALARM_STATE) == DoorAlarmState.NORMAL


class TestAccessPointObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import AccessPointObject
        from bac_py.types.enums import AccessEvent, AuthorizationMode

        obj = AccessPointObject(1, object_name="ap-1")
        assert obj.OBJECT_TYPE == ObjectType.ACCESS_POINT
        assert obj.read_property(PropertyIdentifier.ACCESS_EVENT) == AccessEvent.NONE
        assert (
            obj.read_property(PropertyIdentifier.AUTHORIZATION_MODE) == AuthorizationMode.AUTHORIZE
        )


class TestAccessZoneObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import AccessZoneObject

        obj = AccessZoneObject(1, object_name="az-1")
        assert obj.OBJECT_TYPE == ObjectType.ACCESS_ZONE
        assert obj.read_property(PropertyIdentifier.OCCUPANCY_COUNT) == 0


class TestAccessUserObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import AccessUserObject
        from bac_py.types.enums import AccessUserType

        obj = AccessUserObject(1, object_name="au-1")
        assert obj.OBJECT_TYPE == ObjectType.ACCESS_USER
        assert obj.read_property(PropertyIdentifier.USER_TYPE) == AccessUserType.PERSON


class TestAccessRightsObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import AccessRightsObject

        obj = AccessRightsObject(1, object_name="ar-1")
        assert obj.OBJECT_TYPE == ObjectType.ACCESS_RIGHTS
        assert obj.read_property(PropertyIdentifier.POSITIVE_ACCESS_RULES) == []


class TestAccessCredentialObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import AccessCredentialObject
        from bac_py.types.enums import AccessCredentialDisable

        obj = AccessCredentialObject(1, object_name="ac-1")
        assert obj.OBJECT_TYPE == ObjectType.ACCESS_CREDENTIAL
        assert (
            obj.read_property(PropertyIdentifier.CREDENTIAL_DISABLE)
            == AccessCredentialDisable.NONE
        )


class TestCredentialDataInputObject:
    def test_instantiation(self):
        from bac_py.objects.access_control import CredentialDataInputObject

        obj = CredentialDataInputObject(1, object_name="cdi-1")
        assert obj.OBJECT_TYPE == ObjectType.CREDENTIAL_DATA_INPUT
        assert obj.read_property(PropertyIdentifier.SUPPORTED_FORMATS) == []
