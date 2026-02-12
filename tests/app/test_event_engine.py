"""Integration tests for EventEngine per ASHRAE 135-2020 Clause 13."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.app.event_engine import EventEngine
from bac_py.objects.accumulator import AccumulatorObject
from bac_py.objects.analog import AnalogInputObject, AnalogValueObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.binary import BinaryValueObject
from bac_py.objects.event_enrollment import EventEnrollmentObject
from bac_py.objects.life_safety import LifeSafetyPointObject, LifeSafetyZoneObject
from bac_py.objects.loop import LoopObject
from bac_py.objects.multistate import MultiStateValueObject
from bac_py.objects.notification import NotificationClassObject
from bac_py.types.constructed import (
    BACnetDestination,
    BACnetDeviceObjectPropertyReference,
)
from bac_py.types.enums import (
    EventState,
    EventType,
    LifeSafetyState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import BitString, ObjectIdentifier


def _make_app(*, device_instance: int = 1) -> MagicMock:
    """Create a mock BACnetApplication for EventEngine testing."""
    app = MagicMock()
    app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, device_instance)
    app.object_db = ObjectDatabase()
    app.unconfirmed_request = MagicMock()
    return app


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestEventEngineLifecycle:
    """Verify start/stop lifecycle of EventEngine."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Engine starts and stops cleanly."""
        app = _make_app()
        engine = EventEngine(app, scan_interval=0.01)
        await engine.start()
        assert engine._task is not None
        await engine.stop()
        assert engine._task is None

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        """Stop on an unstarted engine is a no-op."""
        app = _make_app()
        engine = EventEngine(app, scan_interval=0.01)
        await engine.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_double_start(self):
        """Calling start twice does not create duplicate tasks."""
        app = _make_app()
        engine = EventEngine(app, scan_interval=0.01)
        await engine.start()
        task = engine._task
        await engine.start()
        assert engine._task is task
        await engine.stop()


# ---------------------------------------------------------------------------
# Intrinsic reporting tests
# ---------------------------------------------------------------------------


class TestIntrinsicReporting:
    """Test intrinsic event detection on analog/binary/multistate objects."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_analog_high_limit_detection(self):
        """AnalogInputObject exceeding high_limit triggers HIGH_LIMIT."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        # Set present value above high limit
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Should have generated a notification
        assert app.unconfirmed_request.called

    def test_analog_low_limit_detection(self):
        """AnalogInputObject below low_limit triggers LOW_LIMIT."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 5.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_analog_normal_no_notification(self):
        """AnalogInputObject within limits generates no notification."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert not app.unconfirmed_request.called

    def test_binary_alarm_value_detection(self):
        """BinaryValueObject matching alarm_value triggers OFFNORMAL."""
        from bac_py.types.enums import BinaryPV

        app = _make_app()
        db = app.object_db

        bv = BinaryValueObject(
            1,
            alarm_value=BinaryPV.ACTIVE,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(bv)
        bv._properties[PropertyIdentifier.PRESENT_VALUE] = BinaryPV.ACTIVE

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_binary_no_alarm_value_no_notification(self):
        """BinaryValueObject with no alarm_value set produces no notification."""
        from bac_py.types.enums import BinaryPV

        app = _make_app()
        db = app.object_db

        bv = BinaryValueObject(1)
        db.add(bv)
        bv._properties[PropertyIdentifier.PRESENT_VALUE] = BinaryPV.ACTIVE

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert not app.unconfirmed_request.called

    def test_multistate_alarm_values_detection(self):
        """MultiStateValueObject matching alarm_values triggers OFFNORMAL."""
        app = _make_app()
        db = app.object_db

        mv = MultiStateValueObject(
            1,
            number_of_states=4,
            alarm_values=[2, 4],
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(mv)
        mv._properties[PropertyIdentifier.PRESENT_VALUE] = 2

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_event_detection_enable_false_suppresses(self):
        """Intrinsic reporting is suppressed when event_detection_enable is False."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            event_detection_enable=False,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert not app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Enrollment-based tests
# ---------------------------------------------------------------------------


class TestEnrollmentBasedDetection:
    """Test EventEnrollment-driven event detection."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_enrollment_out_of_range(self):
        """EventEnrollment for OUT_OF_RANGE detects high limit."""
        app = _make_app()
        db = app.object_db

        # Target object
        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 95.0

        # EventEnrollment pointing to av
        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_enrollment_detection_enable_false(self):
        """Enrollment with event_detection_enable=False is skipped."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 95.0

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            event_detection_enable=False,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert not app.unconfirmed_request.called

    def test_enrollment_change_of_state(self):
        """EventEnrollment for CHANGE_OF_STATE triggers on matching value."""
        app = _make_app()
        db = app.object_db

        mv = MultiStateValueObject(1, number_of_states=5)
        db.add(mv)
        mv._properties[PropertyIdentifier.PRESENT_VALUE] = 3

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_STATE,
            event_parameters={"alarm_values": [3, 5]},
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=mv.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Fault transition tests
# ---------------------------------------------------------------------------


class TestFaultTransitions:
    """Test fault detection and state transitions."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_fault_transition_generates_notification(self):
        """Object with faulted reliability transitions to FAULT."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_fault_clears_returns_to_normal(self):
        """Clearing a fault with normal present value returns to NORMAL."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE

        engine = self._make_engine(app)

        # First cycle: transition to FAULT
        engine._evaluate_cycle()
        app.unconfirmed_request.reset_mock()

        # Clear fault
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.NO_FAULT_DETECTED

        # Second cycle: transition from FAULT to NORMAL
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Notification class integration
# ---------------------------------------------------------------------------


class TestNotificationClassIntegration:
    """Test NotificationClass lookup for priority and ack_required."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_priority_from_notification_class(self):
        """Priority is read from the NotificationClass object."""
        app = _make_app()
        db = app.object_db

        nc = NotificationClassObject(
            5,
            priority=[100, 200, 50],
            ack_required=[True, False, True],
        )
        db.add(nc)

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            notification_class=5,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called
        # The notification was sent; verify priority would be 100 (to-offnormal)
        # by checking the engine's internal priority lookup
        assert engine._get_priority(5, EventState.HIGH_LIMIT) == 100
        assert engine._get_priority(5, EventState.FAULT) == 200
        assert engine._get_priority(5, EventState.NORMAL) == 50

    def test_ack_required_from_notification_class(self):
        """Ack_required is read from the NotificationClass object."""
        app = _make_app()
        db = app.object_db

        nc = NotificationClassObject(
            3,
            priority=[10, 20, 30],
            ack_required=[True, False, True],
        )
        db.add(nc)

        engine = self._make_engine(app)
        assert engine._get_ack_required(3, EventState.HIGH_LIMIT) is True
        assert engine._get_ack_required(3, EventState.FAULT) is False
        assert engine._get_ack_required(3, EventState.NORMAL) is True


# ---------------------------------------------------------------------------
# Time delay integration
# ---------------------------------------------------------------------------


class TestTimeDelayIntegration:
    """Test time-delay behavior in the evaluation cycle."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_time_delay_defers_notification(self):
        """With time_delay > 0, no notification on first cycle."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=10,  # 10 seconds
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Should NOT have notified yet -- time delay not elapsed
        assert not app.unconfirmed_request.called

    def test_zero_time_delay_immediate_notification(self):
        """With time_delay=0, notification fires immediately."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Multiple objects in single cycle
# ---------------------------------------------------------------------------


class TestMultipleObjects:
    """Test evaluation of multiple objects in a single cycle."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_multiple_intrinsic_objects(self):
        """Multiple intrinsic objects are evaluated in one cycle."""
        app = _make_app()
        db = app.object_db

        ai1 = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        ai2 = AnalogInputObject(
            2,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai1)
        db.add(ai2)

        # Both exceed high limit
        ai1._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0
        ai2._properties[PropertyIdentifier.PRESENT_VALUE] = 90.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Two notifications should have been generated
        assert app.unconfirmed_request.call_count == 2

    def test_mixed_enrollment_and_intrinsic(self):
        """Both enrollment-based and intrinsic objects are evaluated."""
        app = _make_app()
        db = app.object_db

        # Intrinsic object
        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        # Enrollment-monitored object
        av = AnalogValueObject(2)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 95.0

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # At least 2 notifications: one from intrinsic, one from enrollment
        assert app.unconfirmed_request.call_count >= 2


# ---------------------------------------------------------------------------
# Event state updates on intrinsic objects
# ---------------------------------------------------------------------------


class TestEventStateUpdates:
    """Verify that event_state is updated on intrinsic objects after transitions."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_event_state_set_on_transition(self):
        """Intrinsic object event_state is updated after a transition."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert ai._properties.get(PropertyIdentifier.EVENT_STATE) == EventState.HIGH_LIMIT

    def test_event_state_returns_to_normal(self):
        """Event state returns to NORMAL when alarm condition clears."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=0.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)

        engine = self._make_engine(app)

        # Trigger alarm
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0
        engine._evaluate_cycle()
        assert ai._properties.get(PropertyIdentifier.EVENT_STATE) == EventState.HIGH_LIMIT

        app.unconfirmed_request.reset_mock()

        # Clear alarm
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        engine._evaluate_cycle()
        assert ai._properties.get(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL


# ---------------------------------------------------------------------------
# Limit enable tests
# ---------------------------------------------------------------------------


class TestLimitEnable:
    """Test limit_enable filtering for analog intrinsic reporting."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_high_limit_disabled(self):
        """High limit disabled via limit_enable suppresses HIGH_LIMIT."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            limit_enable=[False, True],  # high disabled, low enabled
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # No notification since high limit is disabled
        assert not app.unconfirmed_request.called

    def test_low_limit_still_active(self):
        """Low limit still triggers when only high limit is disabled."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            limit_enable=[False, True],  # high disabled, low enabled
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 5.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Event_Algorithm_Inhibit tests (Clause 13.2.2, p.638-640)
# ---------------------------------------------------------------------------


class TestEventAlgorithmInhibit:
    """Test Event_Algorithm_Inhibit property behaviour per Clause 13.2.2."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_inhibit_blocks_normal_to_offnormal(self):
        """Inhibit=TRUE prevents transition from Normal to OffNormal."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0
        ai._properties[PropertyIdentifier.EVENT_ALGORITHM_INHIBIT] = True

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert not app.unconfirmed_request.called

    def test_inhibit_triggers_offnormal_to_normal(self):
        """Inhibit=TRUE while in OffNormal triggers return-to-normal."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=0.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        # First cycle: transition to HIGH_LIMIT
        engine._evaluate_cycle()
        assert ai._properties.get(PropertyIdentifier.EVENT_STATE) == EventState.HIGH_LIMIT
        app.unconfirmed_request.reset_mock()

        # Set inhibit while still in alarm condition
        ai._properties[PropertyIdentifier.EVENT_ALGORITHM_INHIBIT] = True
        engine._evaluate_cycle()

        # Should transition back to NORMAL
        assert app.unconfirmed_request.called
        assert ai._properties.get(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_inhibit_does_not_affect_fault_transitions(self):
        """Inhibit=TRUE does not prevent transitions to FAULT."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE
        ai._properties[PropertyIdentifier.EVENT_ALGORITHM_INHIBIT] = True

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Fault should still fire despite inhibit
        assert app.unconfirmed_request.called

    def test_inhibit_false_allows_normal_alarm(self):
        """Inhibit=FALSE allows normal alarm transitions."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0
        ai._properties[PropertyIdentifier.EVENT_ALGORITHM_INHIBIT] = False

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_inhibit_missing_treated_as_false(self):
        """Missing EVENT_ALGORITHM_INHIBIT allows alarm transitions."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0
        # No EVENT_ALGORITHM_INHIBIT set

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_inhibit_cleared_allows_alarm_again(self):
        """Toggling inhibit off re-enables alarm transitions."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0
        ai._properties[PropertyIdentifier.EVENT_ALGORITHM_INHIBIT] = True

        engine = self._make_engine(app)

        # Inhibited: no alarm
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

        # Clear inhibit
        ai._properties[PropertyIdentifier.EVENT_ALGORITHM_INHIBIT] = False
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Reliability_Evaluation_Inhibit tests (Clause 13.2.2, p.638)
# ---------------------------------------------------------------------------


class TestReliabilityEvaluationInhibit:
    """Test Reliability_Evaluation_Inhibit property behaviour per Clause 13.2.2."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_inhibit_blocks_fault_detection_enrollment(self):
        """Enrollment with inhibit=TRUE does not transition to FAULT."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        # Set fault on enrollment, but also inhibit reliability evaluation
        ee._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE
        ee._properties[PropertyIdentifier.RELIABILITY_EVALUATION_INHIBIT] = True

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # No fault notification since reliability evaluation is inhibited
        assert not app.unconfirmed_request.called

    def test_inhibit_blocks_fault_detection_intrinsic(self):
        """Intrinsic object with inhibit=TRUE does not transition to FAULT."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE
        ai._properties[PropertyIdentifier.RELIABILITY_EVALUATION_INHIBIT] = True

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # No notification since fault is inhibited and value is normal
        assert not app.unconfirmed_request.called

    def test_inhibit_false_allows_fault(self):
        """Inhibit=FALSE allows fault transitions."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE
        ai._properties[PropertyIdentifier.RELIABILITY_EVALUATION_INHIBIT] = False

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called

    def test_inhibit_missing_allows_fault(self):
        """Missing RELIABILITY_EVALUATION_INHIBIT allows fault transitions."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Time_Delay_Normal sync tests (Clause 13.2.2.1.4)
# ---------------------------------------------------------------------------


class TestTimeDelayNormalSync:
    """Test TIME_DELAY_NORMAL synchronization to state machines."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_sync_reads_time_delay_normal_enrollment(self):
        """Enrollment with TIME_DELAY_NORMAL sets sm.time_delay_normal."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=10,
            notification_class=0,
        )
        db.add(ee)
        ee._properties[PropertyIdentifier.TIME_DELAY_NORMAL] = 5

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        key = (int(ee.object_identifier.object_type), ee.object_identifier.instance_number)
        ctx = engine._contexts[key]
        assert ctx.state_machine.time_delay_normal == 5.0

    def test_sync_reads_time_delay_normal_intrinsic(self):
        """Intrinsic object with TIME_DELAY_NORMAL sets sm.time_delay_normal."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=10,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0
        ai._properties[PropertyIdentifier.TIME_DELAY_NORMAL] = 3

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        key = (int(ai.object_identifier.object_type), ai.object_identifier.instance_number)
        ctx = engine._contexts[key]
        assert ctx.state_machine.time_delay_normal == 3.0

    def test_missing_time_delay_normal_uses_default(self):
        """Without TIME_DELAY_NORMAL, sm.time_delay_normal stays None."""
        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=10,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        key = (int(ai.object_identifier.object_type), ai.object_identifier.instance_number)
        ctx = engine._contexts[key]
        assert ctx.state_machine.time_delay_normal is None


# ---------------------------------------------------------------------------
# Enrollment-based dispatch for all 13 new event types (Phase 1.1)
# ---------------------------------------------------------------------------


class TestEnrollmentAllEventTypes:
    """Test _run_event_algorithm() dispatch for all 18 event types."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_enrollment_floating_limit(self):
        """EventEnrollment for FLOATING_LIMIT detects high limit."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 90.0

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.FLOATING_LIMIT,
            event_parameters={
                "setpoint": 72.0,
                "high_diff_limit": 5.0,
                "low_diff_limit": 5.0,
                "deadband": 2.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_change_of_life_safety(self):
        """EventEnrollment for CHANGE_OF_LIFE_SAFETY detects alarm state."""
        app = _make_app()
        db = app.object_db

        lsp = LifeSafetyPointObject(1)
        db.add(lsp)
        lsp._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.ALARM

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_LIFE_SAFETY,
            event_parameters={
                "alarm_values": (int(LifeSafetyState.PRE_ALARM),),
                "life_safety_alarm_values": (int(LifeSafetyState.ALARM),),
                "mode": 0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=lsp.object_identifier,
                property_identifier=PropertyIdentifier.TRACKING_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_buffer_ready(self):
        """EventEnrollment for BUFFER_READY triggers on threshold."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 100  # current_count

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.BUFFER_READY,
            event_parameters={
                "previous_count": 90,
                "notification_threshold": 5,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_unsigned_range(self):
        """EventEnrollment for UNSIGNED_RANGE detects above high limit."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 101

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.UNSIGNED_RANGE,
            event_parameters={"high_limit": 100, "low_limit": 10},
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_access_event(self):
        """EventEnrollment for ACCESS_EVENT triggers on matching event."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 5

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.ACCESS_EVENT,
            event_parameters={"access_event_list": [5, 10]},
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_double_out_of_range(self):
        """EventEnrollment for DOUBLE_OUT_OF_RANGE detects high limit."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 100.1

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.DOUBLE_OUT_OF_RANGE,
            event_parameters={
                "high_limit": 100.0,
                "low_limit": 0.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_signed_out_of_range(self):
        """EventEnrollment for SIGNED_OUT_OF_RANGE detects low limit."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = -101

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.SIGNED_OUT_OF_RANGE,
            event_parameters={
                "high_limit": 100,
                "low_limit": -100,
                "deadband": 5,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_unsigned_out_of_range(self):
        """EventEnrollment for UNSIGNED_OUT_OF_RANGE detects high limit."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 101

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.UNSIGNED_OUT_OF_RANGE,
            event_parameters={
                "high_limit": 100,
                "low_limit": 10,
                "deadband": 5,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_change_of_characterstring(self):
        """EventEnrollment for CHANGE_OF_CHARACTERSTRING detects alarm string."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = "FAULT"

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_CHARACTERSTRING,
            event_parameters={"alarm_values": ["FAULT", "ERROR"]},
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_change_of_status_flags(self):
        """EventEnrollment for CHANGE_OF_STATUS_FLAGS detects flag change."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = (True, False, False, False)

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_STATUS_FLAGS,
            event_parameters={
                "previous_flags": (False, False, False, False),
                "selected_flags": (True, True, True, True),
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_change_of_reliability(self):
        """EventEnrollment for CHANGE_OF_RELIABILITY detects fault."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = Reliability.OVER_RANGE

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_RELIABILITY,
            event_parameters={},
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_change_of_timer(self):
        """EventEnrollment for CHANGE_OF_TIMER detects alarm state."""
        from bac_py.types.enums import TimerState

        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = TimerState.EXPIRED

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_TIMER,
            event_parameters={"alarm_values": [int(TimerState.EXPIRED)]},
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_extended_with_callback(self):
        """EventEnrollment for EXTENDED invokes vendor callback."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 42

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.EXTENDED,
            event_parameters={
                "vendor_callback": lambda v, p: EventState.OFFNORMAL if v > 10 else None,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Intrinsic reporting for new object types (Phase 1.2)
# ---------------------------------------------------------------------------


class TestIntrinsicNewObjectTypes:
    """Test intrinsic event detection on Accumulator, Loop, LifeSafety objects."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_accumulator_unsigned_range_high(self):
        """AccumulatorObject exceeding high_limit triggers HIGH_LIMIT."""
        app = _make_app()
        db = app.object_db

        acc = AccumulatorObject(
            1,
            high_limit=100,
            low_limit=10,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(acc)
        acc._properties[PropertyIdentifier.PRESENT_VALUE] = 101

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_accumulator_unsigned_range_low(self):
        """AccumulatorObject below low_limit triggers LOW_LIMIT."""
        app = _make_app()
        db = app.object_db

        acc = AccumulatorObject(
            1,
            high_limit=100,
            low_limit=10,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(acc)
        acc._properties[PropertyIdentifier.PRESENT_VALUE] = 5

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_accumulator_unsigned_range_normal(self):
        """AccumulatorObject within range generates no notification."""
        app = _make_app()
        db = app.object_db

        acc = AccumulatorObject(
            1,
            high_limit=100,
            low_limit=10,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(acc)
        acc._properties[PropertyIdentifier.PRESENT_VALUE] = 50

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

    def test_accumulator_missing_limits_no_alarm(self):
        """AccumulatorObject without limits does not alarm."""
        app = _make_app()
        db = app.object_db

        acc = AccumulatorObject(1, event_enable=[True, True, True], time_delay=0)
        db.add(acc)
        acc._properties[PropertyIdentifier.PRESENT_VALUE] = 999

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

    def test_loop_floating_limit_high(self):
        """LoopObject exceeding floating high limit triggers HIGH_LIMIT."""
        app = _make_app()
        db = app.object_db

        loop = LoopObject(
            1,
            setpoint=72.0,
            error_limit=5.0,
            deadband=2.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(loop)
        # effective high = 72 + 5 = 77, value > 77 triggers
        loop._properties[PropertyIdentifier.PRESENT_VALUE] = 78.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_loop_floating_limit_low(self):
        """LoopObject below floating low limit triggers LOW_LIMIT."""
        app = _make_app()
        db = app.object_db

        loop = LoopObject(
            1,
            setpoint=72.0,
            error_limit=5.0,
            deadband=2.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(loop)
        # effective low = 72 - 5 = 67, value < 67 triggers
        loop._properties[PropertyIdentifier.PRESENT_VALUE] = 66.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_loop_floating_limit_normal(self):
        """LoopObject within floating limits generates no notification."""
        app = _make_app()
        db = app.object_db

        loop = LoopObject(
            1,
            setpoint=72.0,
            error_limit=5.0,
            deadband=2.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(loop)
        loop._properties[PropertyIdentifier.PRESENT_VALUE] = 72.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

    def test_loop_missing_error_limit_no_alarm(self):
        """LoopObject without error_limit does not alarm."""
        app = _make_app()
        db = app.object_db

        loop = LoopObject(
            1,
            setpoint=72.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(loop)
        loop._properties[PropertyIdentifier.PRESENT_VALUE] = 999.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

    def test_life_safety_point_alarm(self):
        """LifeSafetyPointObject with alarm value triggers OFFNORMAL."""
        app = _make_app()
        db = app.object_db

        lsp = LifeSafetyPointObject(
            1,
            alarm_values=[int(LifeSafetyState.PRE_ALARM)],
            life_safety_alarm_values=[int(LifeSafetyState.ALARM)],
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(lsp)
        lsp._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.PRE_ALARM

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_life_safety_point_life_safety_alarm(self):
        """LifeSafetyPointObject with life_safety_alarm_values triggers LIFE_SAFETY_ALARM."""
        app = _make_app()
        db = app.object_db

        lsp = LifeSafetyPointObject(
            1,
            alarm_values=[int(LifeSafetyState.PRE_ALARM)],
            life_safety_alarm_values=[int(LifeSafetyState.ALARM)],
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(lsp)
        lsp._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.ALARM

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_life_safety_point_normal(self):
        """LifeSafetyPointObject in quiet state generates no notification."""
        app = _make_app()
        db = app.object_db

        lsp = LifeSafetyPointObject(
            1,
            alarm_values=[int(LifeSafetyState.PRE_ALARM)],
            life_safety_alarm_values=[int(LifeSafetyState.ALARM)],
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(lsp)
        lsp._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.QUIET

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

    def test_life_safety_zone_alarm(self):
        """LifeSafetyZoneObject with alarm value triggers OFFNORMAL."""
        app = _make_app()
        db = app.object_db

        lsz = LifeSafetyZoneObject(
            1,
            alarm_values=[int(LifeSafetyState.TAMPER)],
            life_safety_alarm_values=[int(LifeSafetyState.HOLDUP)],
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(lsz)
        lsz._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.TAMPER

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_life_safety_zone_no_alarm_values(self):
        """LifeSafetyZoneObject without alarm_values does not alarm."""
        app = _make_app()
        db = app.object_db

        lsz = LifeSafetyZoneObject(
            1,
            event_enable=[True, True, True],
            time_delay=0,
        )
        db.add(lsz)
        lsz._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.TAMPER

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        # No alarm values configured, tracking_value doesn't match empty lists
        assert not app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# NotificationClass recipient list routing (Phase 1.3)
# ---------------------------------------------------------------------------


def _make_bitstring_7_all_true() -> BitString:
    """Create a 7-bit BitString with all bits set (all days valid)."""
    # 7 bits all set: 0b1111_1110 with 1 unused bit
    return BitString(b"\xfe", unused_bits=1)


def _make_bitstring_3_all_true() -> BitString:
    """Create a 3-bit BitString with all bits set (all transitions)."""
    # 3 bits all set: 0b1110_0000 with 5 unused bits
    return BitString(b"\xe0", unused_bits=5)


def _make_bitstring_3(to_offnormal: bool, to_fault: bool, to_normal: bool) -> BitString:
    """Create a 3-bit transitions BitString."""
    val = (int(to_offnormal) << 7) | (int(to_fault) << 6) | (int(to_normal) << 5)
    return BitString(bytes([val]), unused_bits=5)


class TestRecipientListRouting:
    """Test NotificationClass recipient list routing (Clause 13.8)."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_no_recipient_list_broadcasts(self):
        """Without recipient_list, notification is sent as unconfirmed broadcast."""
        app = _make_app()
        db = app.object_db

        nc = NotificationClassObject(
            5,
            priority=[100, 200, 50],
            ack_required=[True, False, True],
            recipient_list=[],
        )
        db.add(nc)

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            notification_class=5,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Falls back to global broadcast
        assert app.unconfirmed_request.called

    def test_recipient_list_unconfirmed_to_address(self):
        """Recipient with address + unconfirmed sends to that address."""
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        target_addr = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(address=target_addr),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3_all_true(),
        )

        app = _make_app()
        db = app.object_db

        nc = NotificationClassObject(
            5,
            priority=[100, 200, 50],
            ack_required=[False, False, False],
            recipient_list=[dest],
        )
        db.add(nc)

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            notification_class=5,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        assert app.unconfirmed_request.called
        call_kwargs = app.unconfirmed_request.call_args
        # Verify the destination is our target address, not global broadcast
        assert call_kwargs[1]["destination"] == target_addr or call_kwargs[0][0] == target_addr

    def test_recipient_list_transition_filter(self):
        """Recipient filtered out by transitions BitString receives nothing."""
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        target_addr = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        # Only to-fault and to-normal, NOT to-offnormal
        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(address=target_addr),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3(False, True, True),
        )

        app = _make_app()
        db = app.object_db

        nc = NotificationClassObject(
            5,
            priority=[100, 200, 50],
            ack_required=[False, False, False],
            recipient_list=[dest],
        )
        db.add(nc)

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            notification_class=5,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Notification is to-offnormal (HIGH_LIMIT) but recipient filters it out.
        # No recipients match, so nothing should be sent.
        assert not app.unconfirmed_request.called

    def test_recipient_list_confirmed_sends_async(self):
        """Recipient with confirmed=True sends confirmed notification."""
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        target_addr = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(address=target_addr),
            process_identifier=0,
            issue_confirmed_notifications=True,
            transitions=_make_bitstring_3_all_true(),
        )

        app = _make_app()
        app.confirmed_request = AsyncMock()
        db = app.object_db

        nc = NotificationClassObject(
            5,
            priority=[100, 200, 50],
            ack_required=[True, False, True],
            recipient_list=[dest],
        )
        db.add(nc)

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            notification_class=5,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        # Confirmed sends schedule an asyncio task, but without a running loop
        # the _send_notification_confirmed logs a debug message and does not crash
        engine._evaluate_cycle()

        # No unconfirmed should be sent (it's confirmed-only)
        assert not app.unconfirmed_request.called

    def test_multiple_recipients_mixed(self):
        """Multiple recipients: some unconfirmed, some filtered out."""
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        addr1 = BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
        addr2 = BACnetAddress(mac_address=b"\x05\x06\x07\x08\xba\xc0")

        # Recipient 1: unconfirmed, all transitions
        dest1 = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(address=addr1),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3_all_true(),
        )

        # Recipient 2: unconfirmed, only to-normal (won't match to-offnormal)
        dest2 = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(address=addr2),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3(False, False, True),
        )

        app = _make_app()
        db = app.object_db

        nc = NotificationClassObject(
            5,
            priority=[100, 200, 50],
            ack_required=[False, False, False],
            recipient_list=[dest1, dest2],
        )
        db.add(nc)

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            notification_class=5,
            time_delay=0,
        )
        db.add(ai)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 85.0

        engine = self._make_engine(app)
        engine._evaluate_cycle()

        # Only 1 unconfirmed sent (to addr1; addr2 filtered by transitions)
        assert app.unconfirmed_request.call_count == 1
