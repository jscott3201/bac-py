"""Tests for BACnet object type registration in the factory."""

from __future__ import annotations

from typing import ClassVar

import pytest

import bac_py.objects  # noqa: F401 -- trigger registration
from bac_py.objects.base import _OBJECT_REGISTRY, create_object
from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestPhase6Registry:
    """Verify all Phase 6 types are registered in the factory."""

    @pytest.mark.parametrize(
        "obj_type",
        [
            ObjectType.DATE_VALUE,
            ObjectType.DATEPATTERN_VALUE,
            ObjectType.TIME_VALUE,
            ObjectType.TIMEPATTERN_VALUE,
            ObjectType.DATETIMEPATTERN_VALUE,
            ObjectType.NETWORK_PORT,
            ObjectType.CHANNEL,
            ObjectType.LIFE_SAFETY_POINT,
            ObjectType.LIFE_SAFETY_ZONE,
        ],
    )
    def test_type_registered(self, obj_type):
        obj = create_object(obj_type, 1)
        assert obj_type == obj.OBJECT_TYPE
        assert obj.object_identifier.object_type == obj_type
        assert obj.object_identifier.instance_number == 1


# ---------------------------------------------------------------------------
# Phase 3 registration tests
# ---------------------------------------------------------------------------


class TestObjectRegistration:
    """Verify all Phase 3 objects are registered in the factory."""

    PHASE3_TYPES: ClassVar[list[ObjectType]] = [
        ObjectType.AVERAGING,
        ObjectType.COMMAND,
        ObjectType.STRUCTURED_VIEW,
        ObjectType.TREND_LOG_MULTIPLE,
        ObjectType.EVENT_LOG,
        ObjectType.TIMER,
        ObjectType.GLOBAL_GROUP,
        ObjectType.GROUP,
        ObjectType.LIGHTING_OUTPUT,
        ObjectType.BINARY_LIGHTING_OUTPUT,
        ObjectType.ACCESS_DOOR,
        ObjectType.ACCESS_POINT,
        ObjectType.ACCESS_ZONE,
        ObjectType.ACCESS_USER,
        ObjectType.ACCESS_RIGHTS,
        ObjectType.ACCESS_CREDENTIAL,
        ObjectType.CREDENTIAL_DATA_INPUT,
        ObjectType.ELEVATOR_GROUP,
        ObjectType.ESCALATOR,
        ObjectType.LIFT,
        ObjectType.PULSE_CONVERTER,
        ObjectType.LOAD_CONTROL,
        ObjectType.NOTIFICATION_FORWARDER,
        ObjectType.ALERT_ENROLLMENT,
        ObjectType.STAGING,
        ObjectType.AUDIT_REPORTER,
        ObjectType.AUDIT_LOG,
    ]

    def test_all_registered(self):
        for ot in self.PHASE3_TYPES:
            assert ot in _OBJECT_REGISTRY, f"{ot.name} not registered"

    def test_total_registered_types(self):
        assert len(_OBJECT_REGISTRY) >= 62

    def test_factory_create(self):
        for ot in self.PHASE3_TYPES:
            obj = create_object(ot, 1, object_name=f"test-{ot.name}")
            assert ot == obj.OBJECT_TYPE
            assert obj.object_identifier.instance_number == 1


# ---------------------------------------------------------------------------
# Global Group and Group objects
# ---------------------------------------------------------------------------


class TestGlobalGroupObject:
    def test_instantiation(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        assert obj.OBJECT_TYPE == ObjectType.GLOBAL_GROUP
        assert obj.read_property(PropertyIdentifier.GROUP_MEMBERS) == []
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == []


class TestGroupObject:
    def test_instantiation(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="grp-1")
        assert obj.OBJECT_TYPE == ObjectType.GROUP
        assert obj.read_property(PropertyIdentifier.LIST_OF_GROUP_MEMBERS) == []
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == []


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestNewEnums:
    def test_object_type_new_2020(self):
        assert ObjectType.STAGING == 60
        assert ObjectType.AUDIT_REPORTER == 61
        assert ObjectType.AUDIT_LOG == 62

    def test_node_type(self):
        from bac_py.types.enums import NodeType

        assert NodeType.UNKNOWN == 0
        assert NodeType.ZONE == 21

    def test_shed_state(self):
        from bac_py.types.enums import ShedState

        assert ShedState.SHED_INACTIVE == 0
        assert ShedState.SHED_NON_COMPLIANT == 3

    def test_door_enums(self):
        from bac_py.types.enums import DoorAlarmState, DoorStatus, LockStatus

        assert DoorStatus.CLOSED == 0
        assert LockStatus.LOCKED == 0
        assert DoorAlarmState.NORMAL == 0

    def test_lighting_enums(self):
        from bac_py.types.enums import LightingInProgress, LightingOperation

        assert LightingOperation.FADE_TO == 1
        assert LightingInProgress.IDLE == 0

    def test_transportation_enums(self):
        from bac_py.types.enums import (
            EscalatorFault,
            EscalatorMode,
            LiftCarDirection,
            LiftCarDoorStatus,
            LiftGroupMode,
        )

        assert EscalatorMode.STOP == 1
        assert EscalatorFault.CONTROLLER_FAULT == 0
        assert LiftCarDirection.UP == 3
        assert LiftGroupMode.NORMAL == 1
        assert LiftCarDoorStatus.CLOSED == 3

    def test_access_enums(self):
        from bac_py.types.enums import (
            AccessCredentialDisable,
            AccessEvent,
            AccessPassbackMode,
            AccessUserType,
            AuthorizationMode,
        )

        assert AccessEvent.GRANTED == 1
        assert AccessCredentialDisable.NONE == 0
        assert AccessUserType.PERSON == 2
        assert AuthorizationMode.AUTHORIZE == 0
        assert AccessPassbackMode.PASSBACK_OFF == 0

    def test_staging_state(self):
        from bac_py.types.enums import StagingState

        assert StagingState.NOT_STAGED == 0
        assert StagingState.COMMITTED == 4


# ---------------------------------------------------------------------------
# Constructed type tests
# ---------------------------------------------------------------------------


class TestBACnetLightingCommand:
    def test_creation(self):
        from bac_py.types.constructed import BACnetLightingCommand
        from bac_py.types.enums import LightingOperation

        cmd = BACnetLightingCommand(
            operation=LightingOperation.FADE_TO,
            target_level=50.0,
            fade_time=1000,
        )
        assert cmd.operation == LightingOperation.FADE_TO
        assert cmd.target_level == 50.0
        assert cmd.fade_time == 1000
        assert cmd.ramp_rate is None

    def test_frozen(self):
        import pytest

        from bac_py.types.constructed import BACnetLightingCommand
        from bac_py.types.enums import LightingOperation

        cmd = BACnetLightingCommand(operation=LightingOperation.NONE)
        with pytest.raises(AttributeError):
            cmd.operation = LightingOperation.FADE_TO  # type: ignore[misc]


class TestBACnetShedLevel:
    def test_percent(self):
        from bac_py.types.constructed import BACnetShedLevel

        level = BACnetShedLevel(percent=50)
        assert level.percent == 50
        assert level.level is None
        assert level.amount is None

    def test_amount(self):
        from bac_py.types.constructed import BACnetShedLevel

        level = BACnetShedLevel(amount=1500.0)
        assert level.amount == 1500.0
