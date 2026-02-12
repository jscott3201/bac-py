"""Tests for Phase 3 object types."""

from __future__ import annotations

from typing import ClassVar

import bac_py.objects  # noqa: F401 -- trigger registration
from bac_py.objects.base import _OBJECT_REGISTRY, create_object
from bac_py.types.enums import ObjectType, PropertyIdentifier

# ---------------------------------------------------------------------------
# Registration tests
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
# High-priority objects
# ---------------------------------------------------------------------------


class TestAveragingObject:
    def test_instantiation(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.OBJECT_TYPE == ObjectType.AVERAGING
        assert obj.read_property(PropertyIdentifier.AVERAGE_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.MINIMUM_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.MAXIMUM_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.WINDOW_INTERVAL) == 60
        assert obj.read_property(PropertyIdentifier.WINDOW_SAMPLES) == 10

    def test_required_properties_present(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.AVERAGE_VALUE in prop_list
        assert PropertyIdentifier.UNITS in prop_list


class TestCommandObject:
    def test_instantiation(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.OBJECT_TYPE == ObjectType.COMMAND
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0
        assert obj.read_property(PropertyIdentifier.IN_PROCESS) is False
        assert obj.read_property(PropertyIdentifier.ALL_WRITES_SUCCESSFUL) is True

    def test_write_present_value(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 1)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 1


class TestStructuredViewObject:
    def test_instantiation(self):
        from bac_py.objects.structured_view import StructuredViewObject
        from bac_py.types.enums import NodeType

        obj = StructuredViewObject(1, object_name="sv-1")
        assert obj.OBJECT_TYPE == ObjectType.STRUCTURED_VIEW
        assert obj.read_property(PropertyIdentifier.NODE_TYPE) == NodeType.UNKNOWN
        assert obj.read_property(PropertyIdentifier.SUBORDINATE_LIST) == []


class TestTrendLogMultipleObject:
    def test_instantiation(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject
        from bac_py.types.enums import LoggingType

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.OBJECT_TYPE == ObjectType.TREND_LOG_MULTIPLE
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False
        assert obj.read_property(PropertyIdentifier.LOGGING_TYPE) == LoggingType.POLLED
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []


class TestEventLogObject:
    def test_instantiation(self):
        from bac_py.objects.event_log import EventLogObject
        from bac_py.types.enums import LoggingType

        obj = EventLogObject(1, object_name="el-1")
        assert obj.OBJECT_TYPE == ObjectType.EVENT_LOG
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False
        assert obj.read_property(PropertyIdentifier.LOGGING_TYPE) == LoggingType.TRIGGERED
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []


class TestTimerObject:
    def test_instantiation(self):
        from bac_py.objects.timer import TimerObject
        from bac_py.types.enums import EventType, TimerState, TimerTransition

        obj = TimerObject(1, object_name="timer-1")
        assert obj.OBJECT_TYPE == ObjectType.TIMER
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0
        assert obj.read_property(PropertyIdentifier.TIMER_STATE) == TimerState.IDLE
        assert obj.read_property(PropertyIdentifier.TIMER_RUNNING) is False
        assert obj.read_property(PropertyIdentifier.LAST_STATE_CHANGE) == TimerTransition.NONE
        assert obj.INTRINSIC_EVENT_ALGORITHM == EventType.CHANGE_OF_TIMER


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
# Lighting objects
# ---------------------------------------------------------------------------


class TestLightingOutputObject:
    def test_instantiation(self):
        from bac_py.objects.lighting import LightingOutputObject
        from bac_py.types.enums import LightingInProgress

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.OBJECT_TYPE == ObjectType.LIGHTING_OUTPUT
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.TRACKING_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.IN_PROGRESS) == LightingInProgress.IDLE
        assert obj.read_property(PropertyIdentifier.DEFAULT_FADE_TIME) == 0

    def test_commandable(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 75.0, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 75.0


class TestBinaryLightingOutputObject:
    def test_instantiation(self):
        from bac_py.objects.lighting import BinaryLightingOutputObject
        from bac_py.types.enums import BinaryPV

        obj = BinaryLightingOutputObject(1, object_name="blo-1")
        assert obj.OBJECT_TYPE == ObjectType.BINARY_LIGHTING_OUTPUT
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_commandable(self):
        from bac_py.objects.lighting import BinaryLightingOutputObject
        from bac_py.types.enums import BinaryPV

        obj = BinaryLightingOutputObject(1, object_name="blo-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE


# ---------------------------------------------------------------------------
# Access control objects
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Transportation objects
# ---------------------------------------------------------------------------


class TestElevatorGroupObject:
    def test_instantiation(self):
        from bac_py.objects.transportation import ElevatorGroupObject
        from bac_py.types.enums import LiftGroupMode

        obj = ElevatorGroupObject(1, object_name="eg-1")
        assert obj.OBJECT_TYPE == ObjectType.ELEVATOR_GROUP
        assert obj.read_property(PropertyIdentifier.GROUP_MODE) == LiftGroupMode.UNKNOWN


class TestLiftObject:
    def test_instantiation(self):
        from bac_py.objects.transportation import LiftObject
        from bac_py.types.enums import LiftCarDirection

        obj = LiftObject(1, object_name="lift-1")
        assert obj.OBJECT_TYPE == ObjectType.LIFT
        assert obj.read_property(PropertyIdentifier.CAR_POSITION) == 0
        assert (
            obj.read_property(PropertyIdentifier.CAR_ASSIGNED_DIRECTION)
            == LiftCarDirection.UNKNOWN
        )


class TestEscalatorObject:
    def test_instantiation(self):
        from bac_py.objects.transportation import EscalatorObject
        from bac_py.types.enums import EscalatorMode

        obj = EscalatorObject(1, object_name="esc-1")
        assert obj.OBJECT_TYPE == ObjectType.ESCALATOR
        assert obj.read_property(PropertyIdentifier.ESCALATOR_MODE) == EscalatorMode.UNKNOWN


# ---------------------------------------------------------------------------
# Remaining objects
# ---------------------------------------------------------------------------


class TestPulseConverterObject:
    def test_instantiation(self):
        from bac_py.objects.pulse_converter import PulseConverterObject

        obj = PulseConverterObject(1, object_name="pc-1")
        assert obj.OBJECT_TYPE == ObjectType.PULSE_CONVERTER
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.SCALE_FACTOR) == 1.0
        assert obj.read_property(PropertyIdentifier.COUNT) == 0


class TestLoadControlObject:
    def test_instantiation(self):
        from bac_py.objects.load_control import LoadControlObject
        from bac_py.types.enums import ShedState

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.OBJECT_TYPE == ObjectType.LOAD_CONTROL
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == ShedState.SHED_INACTIVE
        assert obj.read_property(PropertyIdentifier.SHED_DURATION) == 0


class TestNotificationForwarderObject:
    def test_instantiation(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        assert obj.OBJECT_TYPE == ObjectType.NOTIFICATION_FORWARDER
        assert obj.read_property(PropertyIdentifier.LOCAL_FORWARDING_ONLY) is True
        assert obj.read_property(PropertyIdentifier.SUBSCRIBED_RECIPIENTS) == []


class TestAlertEnrollmentObject:
    def test_instantiation(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        assert obj.OBJECT_TYPE == ObjectType.ALERT_ENROLLMENT


# ---------------------------------------------------------------------------
# New 2020 objects
# ---------------------------------------------------------------------------


class TestStagingObject:
    def test_instantiation(self):
        from bac_py.objects.staging import StagingObject
        from bac_py.types.enums import StagingState

        obj = StagingObject(1, object_name="staging-1")
        assert obj.OBJECT_TYPE == ObjectType.STAGING
        assert obj.read_property(PropertyIdentifier.STAGING_STATE) == StagingState.NOT_STAGED


class TestAuditReporterObject:
    def test_instantiation(self):
        from bac_py.objects.audit_reporter import AuditReporterObject

        obj = AuditReporterObject(1, object_name="ar-1")
        assert obj.OBJECT_TYPE == ObjectType.AUDIT_REPORTER
        assert obj.read_property(PropertyIdentifier.AUDIT_LEVEL) == 3  # AuditLevel.DEFAULT
        assert obj.read_property(PropertyIdentifier.MONITORED_OBJECTS) == []


class TestAuditLogObject:
    def test_instantiation(self):
        from bac_py.objects.audit_log import AuditLogObject

        obj = AuditLogObject(1, object_name="al-1")
        assert obj.OBJECT_TYPE == ObjectType.AUDIT_LOG
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []
        assert obj.read_property(PropertyIdentifier.STOP_WHEN_FULL) is False


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
