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


# ---------------------------------------------------------------------------
# Additional coverage tests -- state machine branches
# ---------------------------------------------------------------------------


class TestStateMachineBranches:
    """Cover uncovered branches in EventStateMachine.evaluate()."""

    def test_fault_transition_disabled_returns_none(self):
        """Fault detected but to-fault disabled returns None (line 127)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.NORMAL,
            event_enable=[True, False, True],  # to-fault disabled
        )
        result = sm.evaluate(None, Reliability.OVER_RANGE, 1.0)
        assert result is None
        assert sm.event_state == EventState.NORMAL

    def test_staying_in_fault_while_faulted(self):
        """Already in FAULT + still faulted => no transition (line 131)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.FAULT,
            event_enable=[True, True, True],
        )
        result = sm.evaluate(None, Reliability.OVER_RANGE, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_fault_clearing_to_offnormal(self):
        """FAULT clearing when event algo says offnormal => to-offnormal (lines 141-142)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.FAULT,
            event_enable=[True, True, True],
            time_delay=0,
        )
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is not None
        assert result.from_state == EventState.FAULT
        assert result.to_state == EventState.HIGH_LIMIT

    def test_fault_clearing_to_offnormal_disabled(self):
        """FAULT clearing with offnormal target but to-offnormal disabled (lines 143-147)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.FAULT,
            event_enable=[False, True, True],  # to-offnormal disabled
            time_delay=0,
        )
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_alarm_to_normal_disabled(self):
        """In alarm state, condition clears but to-normal disabled (lines 166-168)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            event_enable=[True, True, False],  # to-normal disabled
            time_delay=0,
        )
        result = sm.evaluate(None, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is None
        assert sm.event_state == EventState.HIGH_LIMIT

    def test_alarm_to_different_alarm(self):
        """In HIGH_LIMIT, algo says LOW_LIMIT => transition to LOW_LIMIT (line 172)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            event_enable=[True, True, True],
            time_delay=0,
        )
        result = sm.evaluate(EventState.LOW_LIMIT, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is not None
        assert result.from_state == EventState.HIGH_LIMIT
        assert result.to_state == EventState.LOW_LIMIT

    def test_staying_in_same_alarm_state(self):
        """In HIGH_LIMIT, algo still says HIGH_LIMIT => no transition (lines 174-177)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            event_enable=[True, True, True],
            time_delay=0,
        )
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is None
        assert sm.event_state == EventState.HIGH_LIMIT

    def test_apply_delay_elapsed(self):
        """Time delay elapses after pending condition persists (lines 198-201)."""
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.NORMAL,
            event_enable=[True, True, True],
            time_delay=5.0,
        )
        # First evaluation: starts the timer
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 0.0)
        assert result is None

        # Second evaluation: delay not yet elapsed
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 3.0)
        assert result is None

        # Third evaluation: delay elapsed
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 6.0)
        assert result is not None
        assert result.to_state == EventState.HIGH_LIMIT


# ---------------------------------------------------------------------------
# Pure evaluator function coverage
# ---------------------------------------------------------------------------


class TestPureEvaluatorFunctions:
    """Cover uncovered branches in pure evaluator functions."""

    def test_out_of_range_deadband_high(self):
        """Deadband keeps HIGH_LIMIT while value in deadband zone (line 255)."""
        from bac_py.app.event_engine import evaluate_out_of_range

        result = evaluate_out_of_range(
            value=78.0,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result == EventState.HIGH_LIMIT

    def test_out_of_range_deadband_low(self):
        """Deadband keeps LOW_LIMIT while value in deadband zone (line 257)."""
        from bac_py.app.event_engine import evaluate_out_of_range

        result = evaluate_out_of_range(
            value=12.0,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            current_state=EventState.LOW_LIMIT,
        )
        assert result == EventState.LOW_LIMIT

    def test_change_of_bitstring_match(self):
        """Masked bitstring matches alarm value => OFFNORMAL (line 399)."""
        from bac_py.app.event_engine import evaluate_change_of_bitstring

        result = evaluate_change_of_bitstring(
            value=(1, 0, 1, 0),
            bitmask=(1, 1, 1, 0),
            alarm_values=((1, 0, 1, 0),),
        )
        assert result == EventState.OFFNORMAL

    def test_change_of_bitstring_no_match(self):
        """Masked bitstring does not match => None."""
        from bac_py.app.event_engine import evaluate_change_of_bitstring

        result = evaluate_change_of_bitstring(
            value=(1, 0, 1, 0),
            bitmask=(1, 1, 1, 0),
            alarm_values=((0, 0, 1, 0),),
        )
        assert result is None

    def test_change_of_value_triggers(self):
        """Change exceeds increment => OFFNORMAL (line 477)."""
        from bac_py.app.event_engine import evaluate_change_of_value

        result = evaluate_change_of_value(10.0, 5.0, 3.0)
        assert result == EventState.OFFNORMAL

    def test_change_of_value_no_trigger(self):
        """Change below increment => None."""
        from bac_py.app.event_engine import evaluate_change_of_value

        result = evaluate_change_of_value(10.0, 9.0, 3.0)
        assert result is None

    def test_change_of_status_flags_trigger(self):
        """Selected flag changed => OFFNORMAL (line 499)."""
        from bac_py.app.event_engine import evaluate_change_of_status_flags

        result = evaluate_change_of_status_flags(
            current_flags=(True, False, False, False),
            previous_flags=(False, False, False, False),
            selected_flags=(True, True, True, True),
        )
        assert result == EventState.OFFNORMAL

    def test_change_of_reliability_faulted(self):
        """Reliability != NO_FAULT_DETECTED => OFFNORMAL (line 513)."""
        from bac_py.app.event_engine import evaluate_change_of_reliability

        result = evaluate_change_of_reliability(Reliability.OVER_RANGE)
        assert result == EventState.OFFNORMAL

    def test_command_failure_mismatch(self):
        """Feedback != command => OFFNORMAL (line 531)."""
        from bac_py.app.event_engine import evaluate_command_failure

        result = evaluate_command_failure(50, 100)
        assert result == EventState.OFFNORMAL

    def test_command_failure_match(self):
        """Feedback == command => None."""
        from bac_py.app.event_engine import evaluate_command_failure

        result = evaluate_command_failure(100, 100)
        assert result is None

    def test_change_of_discrete_value_changed(self):
        """Discrete value changed => OFFNORMAL (line 610)."""
        from bac_py.app.event_engine import evaluate_change_of_discrete_value

        result = evaluate_change_of_discrete_value(5, 3)
        assert result == EventState.OFFNORMAL

    def test_change_of_discrete_value_same(self):
        """Discrete value unchanged => None."""
        from bac_py.app.event_engine import evaluate_change_of_discrete_value

        result = evaluate_change_of_discrete_value(5, 5)
        assert result is None


# ---------------------------------------------------------------------------
# Enrollment dispatch -- additional event types
# ---------------------------------------------------------------------------


class TestEnrollmentDispatchExtraTypes:
    """Cover _run_event_algorithm branches not reached by existing tests."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_enrollment_change_of_bitstring(self):
        """CHANGE_OF_BITSTRING dispatch through enrollment (lines 960-968)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = (1, 0, 1, 0)

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_BITSTRING,
            event_parameters={
                "bitmask": [1, 1, 1, 0],
                "alarm_values": [
                    [1, 0, 1, 0],
                ],
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

    def test_enrollment_change_of_value(self):
        """CHANGE_OF_VALUE dispatch through enrollment (lines 971-973)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_VALUE,
            event_parameters={
                "previous_value": 10.0,
                "cov_increment": 5.0,
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

    def test_enrollment_command_failure(self):
        """COMMAND_FAILURE dispatch through enrollment (lines 976-977)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 50

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.COMMAND_FAILURE,
            event_parameters={
                "feedback_value": 99,
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

    def test_enrollment_change_of_discrete_value(self):
        """CHANGE_OF_DISCRETE_VALUE dispatch through enrollment (lines 1082-1084)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 10

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_DISCRETE_VALUE,
            event_parameters={
                "previous_value": 5,
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
# Recipient routing helper coverage
# ---------------------------------------------------------------------------


class TestRecipientRoutingHelpers:
    """Cover uncovered branches in _recipient_matches, _dest_issue_confirmed, _dest_address."""

    def test_recipient_matches_non_typed_entry(self):
        """Non-BACnetDestination always matches (line 1405)."""
        from bac_py.app.event_engine import _recipient_matches

        result = _recipient_matches("plain-string", 0)
        assert result is True

    def test_recipient_matches_day_filter_rejects(self):
        """Day-of-week filter that excludes current day (lines 1420-1421)."""
        from bac_py.app.event_engine import _recipient_matches
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        # Build a BitString with all days OFF (0 bits)
        all_days_off = BitString(b"\x00", unused_bits=1)  # 7 bits, all 0

        dest = BACnetDestination(
            valid_days=all_days_off,
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(
                address=BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
            ),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3_all_true(),
        )

        result = _recipient_matches(dest, 0)
        assert result is False

    def test_recipient_matches_time_window_rejects(self):
        """Time window outside current time (lines 1442-1443)."""
        from datetime import UTC
        from datetime import datetime as real_datetime
        from unittest.mock import patch

        from bac_py.app.event_engine import _recipient_matches
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        # Time window from 01:00 to 01:01 -- almost certainly not current time
        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(1, 0, 0, 0),
            to_time=BACnetTime(1, 1, 0, 0),
            recipient=BACnetRecipient(
                address=BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
            ),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3_all_true(),
        )

        # Mock datetime.now to return 12:00 UTC Monday, outside 01:00-01:01 window
        mock_now = real_datetime(2024, 2, 12, 12, 0, 0, tzinfo=UTC)  # Monday

        class _FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return mock_now

        with patch("datetime.datetime", _FakeDatetime):
            result = _recipient_matches(dest, 0)

        assert result is False

    def test_recipient_matches_transition_filter_index_error(self):
        """Malformed transitions BitString => no filter (lines 1412-1413)."""
        from bac_py.app.event_engine import _recipient_matches
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(
                address=BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
            ),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=None,  # type: ignore[arg-type]
        )

        # transitions is None, so IndexError/TypeError should be caught
        result = _recipient_matches(dest, 0)
        # Should pass through all filters (allow by default on malformed)
        assert result is True

    def test_dest_issue_confirmed_attribute_error(self):
        """Object without issue_confirmed_notifications => False (line 1455)."""
        from bac_py.app.event_engine import _dest_issue_confirmed

        result = _dest_issue_confirmed(object())
        assert result is False

    def test_dest_address_device_recipient(self):
        """Recipient with device (not address) => None (lines 1464-1467)."""
        from bac_py.app.event_engine import _dest_address
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(
                device=ObjectIdentifier(ObjectType.DEVICE, 1),
                address=None,
            ),
            process_identifier=0,
            issue_confirmed_notifications=True,
            transitions=_make_bitstring_3_all_true(),
        )

        result = _dest_address(dest)
        assert result is None

    def test_dest_address_attribute_error(self):
        """Object without recipient => None (lines 1468-1469)."""
        from bac_py.app.event_engine import _dest_address

        result = _dest_address(object())
        assert result is None


# ---------------------------------------------------------------------------
# Notification dispatch coverage
# ---------------------------------------------------------------------------


class TestNotificationDispatchCoverage:
    """Cover uncovered branches in notification encode/send."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_unconfirmed_encode_failure(self):
        """Notification encode() failure logs and returns (lines 1222-1224)."""
        app = _make_app()
        engine = self._make_engine(app)

        bad_notification = MagicMock()
        bad_notification.encode.side_effect = RuntimeError("encode fail")

        # Should not raise
        engine._send_notification_unconfirmed(bad_notification, destination=None)
        assert not app.unconfirmed_request.called

    def test_unconfirmed_send_failure(self):
        """unconfirmed_request raises => logs (lines 1235-1236)."""
        app = _make_app()
        app.unconfirmed_request.side_effect = RuntimeError("send fail")
        engine = self._make_engine(app)

        good_notification = MagicMock()
        good_notification.encode.return_value = b"\x00"

        # Should not raise
        engine._send_notification_unconfirmed(good_notification, destination=None)

    def test_confirmed_encode_failure(self):
        """Confirmed notification encode() failure logs (lines 1246-1248)."""
        app = _make_app()
        engine = self._make_engine(app)

        bad_notification = MagicMock()
        bad_notification.encode.side_effect = RuntimeError("encode fail")

        dest = MagicMock()
        # Should not raise
        engine._send_notification_confirmed(bad_notification, dest)

    def test_confirmed_no_address(self):
        """Confirmed notification with no resolvable address (lines 1252-1253)."""
        app = _make_app()
        engine = self._make_engine(app)

        notification = MagicMock()
        notification.encode.return_value = b"\x00"

        # A dest with no address and no device
        dest = MagicMock(spec=[])  # no attributes at all

        engine._send_notification_confirmed(notification, dest)

    async def test_confirmed_sends_task_in_event_loop(self):
        """Confirmed notification creates an asyncio task (lines 1257-1260)."""
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        app = _make_app()
        app.confirmed_request = AsyncMock()
        engine = self._make_engine(app)

        notification = MagicMock()
        notification.encode.return_value = b"\x00"

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

        engine._send_notification_confirmed(notification, dest)

        # Allow the task to complete
        import asyncio

        await asyncio.sleep(0.05)

        assert app.confirmed_request.called

    async def test_send_confirmed_async_failure(self):
        """_send_confirmed_async handles exception (lines 1274-1275)."""
        app = _make_app()
        app.confirmed_request = AsyncMock(side_effect=RuntimeError("net error"))
        engine = self._make_engine(app)

        # Should not raise
        await engine._send_confirmed_async(b"\x00", MagicMock())


# ---------------------------------------------------------------------------
# Event timestamps update coverage
# ---------------------------------------------------------------------------


class TestEventTimestampUpdates:
    """Cover _update_event_timestamps branches."""

    def test_update_event_timestamps_offnormal(self):
        """Event timestamps updated for offnormal transition."""
        from bac_py.app.event_engine import EventTransition
        from bac_py.types.constructed import BACnetTimeStamp

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
        # Set up event_time_stamps list
        ai._properties[PropertyIdentifier.EVENT_TIME_STAMPS] = [
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
        ]

        transition = EventTransition(
            from_state=EventState.NORMAL,
            to_state=EventState.HIGH_LIMIT,
            timestamp=12345.0,
        )
        EventEngine._update_event_timestamps(ai, transition)

        timestamps = ai._properties[PropertyIdentifier.EVENT_TIME_STAMPS]
        assert timestamps[0].value == 12345  # offnormal index

    def test_update_event_timestamps_fault(self):
        """Event timestamps updated for fault transition."""
        from bac_py.app.event_engine import EventTransition
        from bac_py.types.constructed import BACnetTimeStamp

        app = _make_app()
        db = app.object_db

        ai = AnalogInputObject(1, high_limit=80.0, low_limit=10.0)
        db.add(ai)
        ai._properties[PropertyIdentifier.EVENT_TIME_STAMPS] = [
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
        ]

        transition = EventTransition(
            from_state=EventState.NORMAL,
            to_state=EventState.FAULT,
            timestamp=99999.0,
        )
        EventEngine._update_event_timestamps(ai, transition)

        timestamps = ai._properties[PropertyIdentifier.EVENT_TIME_STAMPS]
        assert timestamps[1].value == 99999  # fault index

    def test_update_event_timestamps_normal(self):
        """Event timestamps updated for return-to-normal transition."""
        from bac_py.app.event_engine import EventTransition
        from bac_py.types.constructed import BACnetTimeStamp

        ai = AnalogInputObject(1, high_limit=80.0, low_limit=10.0)
        ai._properties[PropertyIdentifier.EVENT_TIME_STAMPS] = [
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
        ]

        transition = EventTransition(
            from_state=EventState.HIGH_LIMIT,
            to_state=EventState.NORMAL,
            timestamp=55555.0,
        )
        EventEngine._update_event_timestamps(ai, transition)

        timestamps = ai._properties[PropertyIdentifier.EVENT_TIME_STAMPS]
        assert timestamps[2].value == 55555  # normal index

    def test_update_event_timestamps_missing_property(self):
        """No event_time_stamps property => early return (line 1351)."""
        from bac_py.app.event_engine import EventTransition

        ai = AnalogInputObject(1, high_limit=80.0, low_limit=10.0)
        # No EVENT_TIME_STAMPS set

        transition = EventTransition(
            from_state=EventState.NORMAL,
            to_state=EventState.HIGH_LIMIT,
            timestamp=100.0,
        )
        # Should not raise
        EventEngine._update_event_timestamps(ai, transition)


# ---------------------------------------------------------------------------
# Enrollment-based: monitored property read failure
# ---------------------------------------------------------------------------


class TestEnrollmentMonitoredPropertyErrors:
    """Cover _read_monitored_property failure paths."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_monitored_property_read_exception(self):
        """read_property raises => returns _SENTINEL, enrollment skipped (lines 763-770)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        # Make read_property raise
        av.read_property = MagicMock(side_effect=RuntimeError("read error"))

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
        # No notification since monitored property read failed
        assert not app.unconfirmed_request.called

    def test_monitored_property_ref_is_none(self):
        """Object_Property_Reference is None => returns _SENTINEL (line 753)."""
        app = _make_app()
        db = app.object_db

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)
        # Remove the object_property_reference
        ee._properties.pop(PropertyIdentifier.OBJECT_PROPERTY_REFERENCE, None)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called

    def test_monitored_property_target_not_found(self):
        """Target object not in db => returns _SENTINEL (line 758)."""
        app = _make_app()
        db = app.object_db

        # Don't add the target object to db
        ee = EventEnrollmentObject(
            1,
            event_type=EventType.OUT_OF_RANGE,
            event_parameters={
                "high_limit": 80.0,
                "low_limit": 10.0,
                "deadband": 5.0,
            },
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 999),
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Enrollment fault: reliability on enrollment itself
# ---------------------------------------------------------------------------


class TestEnrollmentFaultOnEnrollment:
    """Cover _evaluate_enrollment_fault branches."""

    def test_enrollment_reliability_faulted(self):
        """Enrollment with Reliability != NO_FAULT triggers fault (line 786)."""
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
        ee._properties[PropertyIdentifier.RELIABILITY] = Reliability.OVER_RANGE

        engine = EventEngine(app, scan_interval=1.0)
        engine._evaluate_cycle()
        # Should detect fault from the enrollment object's own reliability
        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Enrollment algorithm_inhibit
# ---------------------------------------------------------------------------


class TestEnrollmentAlgorithmInhibit:
    """Cover Event_Algorithm_Inhibit on enrollment (line 742)."""

    def test_enrollment_algorithm_inhibit(self):
        """Enrollment with EVENT_ALGORITHM_INHIBIT=True suppresses alarm."""
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
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        # Patch read_property to return True for EVENT_ALGORITHM_INHIBIT
        original_read = ee.read_property

        def _patched_read(prop_id, array_index=None):
            if prop_id == PropertyIdentifier.EVENT_ALGORITHM_INHIBIT:
                return True
            return original_read(prop_id, array_index)

        ee.read_property = _patched_read  # type: ignore[method-assign]

        engine = EventEngine(app, scan_interval=1.0)
        engine._evaluate_cycle()
        # Algorithm inhibited => no alarm notification
        assert not app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Intrinsic present_value read failure
# ---------------------------------------------------------------------------


class TestIntrinsicPresentValueFailure:
    """Cover intrinsic reporting when present_value read fails (lines 810-811)."""

    def test_intrinsic_present_value_read_fails(self):
        """Intrinsic object where read_property(PRESENT_VALUE) raises => skipped."""
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
        # Remove present_value so read_property raises
        ai._properties.pop(PropertyIdentifier.PRESENT_VALUE, None)

        engine = EventEngine(app, scan_interval=1.0)
        engine._evaluate_cycle()
        assert not app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Additional pure evaluator "return None" paths
# ---------------------------------------------------------------------------


class TestPureEvaluatorNormalPaths:
    """Cover the 'return None' (normal) paths of pure evaluators."""

    def test_change_of_state_no_match(self):
        """Value not in alarm_values => None (line 379)."""
        from bac_py.app.event_engine import evaluate_change_of_state

        result = evaluate_change_of_state(1, (2, 3, 4))
        assert result is None

    def test_change_of_characterstring_no_match(self):
        """String not in alarm_values => None (line 438)."""
        from bac_py.app.event_engine import evaluate_change_of_characterstring

        result = evaluate_change_of_characterstring("OK", ("FAULT", "ERROR"))
        assert result is None

    def test_access_event_no_match(self):
        """Access event not in list => None (line 453)."""
        from bac_py.app.event_engine import evaluate_access_event

        result = evaluate_access_event(1, (5, 10))
        assert result is None

    def test_change_of_status_flags_no_change(self):
        """No selected flags changed => None (line 499)."""
        from bac_py.app.event_engine import evaluate_change_of_status_flags

        result = evaluate_change_of_status_flags(
            current_flags=(False, False, False, False),
            previous_flags=(False, False, False, False),
            selected_flags=(True, True, True, True),
        )
        assert result is None

    def test_change_of_reliability_normal(self):
        """Reliability is NO_FAULT_DETECTED => None (line 513)."""
        from bac_py.app.event_engine import evaluate_change_of_reliability

        result = evaluate_change_of_reliability(Reliability.NO_FAULT_DETECTED)
        assert result is None

    def test_buffer_ready_below_threshold(self):
        """Not enough new records => None (line 557)."""
        from bac_py.app.event_engine import evaluate_buffer_ready

        result = evaluate_buffer_ready(
            current_count=95, previous_count=90, notification_threshold=10
        )
        assert result is None

    def test_extended_no_callback(self):
        """No vendor callback => None (line 577)."""
        from bac_py.app.event_engine import evaluate_extended

        result = evaluate_extended("value", {"params": True})
        assert result is None

    def test_change_of_timer_no_match(self):
        """Timer state not in alarm values => None (line 592)."""
        from bac_py.app.event_engine import evaluate_change_of_timer
        from bac_py.types.enums import TimerState

        result = evaluate_change_of_timer(TimerState.IDLE, (int(TimerState.EXPIRED),))
        assert result is None


# ---------------------------------------------------------------------------
# EventEngine._run_loop coverage
# ---------------------------------------------------------------------------


class TestRunLoopCoverage:
    """Cover the _run_loop async method (lines 680-685)."""

    async def test_run_loop_evaluates_and_stops(self):
        """_run_loop runs at least one evaluation cycle (lines 680-685)."""
        import asyncio

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

        engine = EventEngine(app, scan_interval=0.01)
        await engine.start()
        await asyncio.sleep(0.05)
        await engine.stop()

        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Dispatch notification defaults
# ---------------------------------------------------------------------------


class TestDispatchNotificationDefaults:
    """Cover default branches in _dispatch_notification."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_dispatch_notification_default_notify_type_and_class(self):
        """When enrollment has no notify_type/notification_class, defaults used (lines 1104, 1108)."""
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
            time_delay=0,
        )
        db.add(ee)
        # Remove notify_type and notification_class to trigger defaults
        ee._properties.pop(PropertyIdentifier.NOTIFY_TYPE, None)
        ee._properties.pop(PropertyIdentifier.NOTIFICATION_CLASS, None)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        # Notification should still be sent with defaults
        assert app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# _get_priority / _get_ack_required edge cases
# ---------------------------------------------------------------------------


class TestPriorityAckEdgeCases:
    """Cover _get_priority and _get_ack_required when NC is malformed."""

    def test_get_priority_no_nc_object(self):
        """NotificationClass not in db => priority 0 (line 1289)."""
        app = _make_app()
        engine = EventEngine(app, scan_interval=1.0)
        assert engine._get_priority(999, EventState.HIGH_LIMIT) == 0

    def test_get_priority_malformed_priorities(self):
        """NC with short or wrong-type priorities => 0."""
        app = _make_app()
        db = app.object_db
        nc = NotificationClassObject(1, priority=[10], ack_required=[True, False, True])
        db.add(nc)
        engine = EventEngine(app, scan_interval=1.0)
        assert engine._get_priority(1, EventState.HIGH_LIMIT) == 0

    def test_get_ack_required_no_nc_object(self):
        """NotificationClass not in db => False (line 1303)."""
        app = _make_app()
        engine = EventEngine(app, scan_interval=1.0)
        assert engine._get_ack_required(999, EventState.HIGH_LIMIT) is False

    def test_get_ack_required_malformed(self):
        """NC with short ack_required list => False."""
        app = _make_app()
        db = app.object_db
        nc = NotificationClassObject(1, priority=[10, 20, 30], ack_required=[True])
        db.add(nc)
        engine = EventEngine(app, scan_interval=1.0)
        assert engine._get_ack_required(1, EventState.HIGH_LIMIT) is False


# ---------------------------------------------------------------------------
# _sync_state_machine edge cases
# ---------------------------------------------------------------------------


class TestSyncStateMachineEdgeCases:
    """Cover branches in _sync_state_machine/_sync_intrinsic_state_machine."""

    def test_sync_enrollment_with_non_list_event_enable(self):
        """event_enable that is not a list => not synced (line 1311->1314)."""
        from bac_py.app.event_engine import EventStateMachine

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

        # Set non-numeric time_delay to test branch
        ee._properties[PropertyIdentifier.TIME_DELAY] = "not-a-number"
        ee._properties[PropertyIdentifier.TIME_DELAY_NORMAL] = "not-a-number"

        sm = EventStateMachine()
        EventEngine._sync_state_machine(sm, ee)
        # time_delay should remain default since "not-a-number" fails isinstance check
        assert sm.time_delay == 0.0
        assert sm.time_delay_normal is None

    def test_sync_intrinsic_with_existing_event_state(self):
        """Intrinsic object with existing EVENT_STATE synced to state machine."""
        from bac_py.app.event_engine import EventStateMachine

        ai = AnalogInputObject(
            1,
            high_limit=80.0,
            low_limit=10.0,
            deadband=5.0,
            event_enable=[True, True, True],
            time_delay=0,
        )
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT

        sm = EventStateMachine()  # starts at NORMAL
        EventEngine._sync_intrinsic_state_machine(sm, ai)
        assert sm.event_state == EventState.HIGH_LIMIT


# ---------------------------------------------------------------------------
# _limit_enable_bits edge cases
# ---------------------------------------------------------------------------


class TestLimitEnableBits:
    """Cover _limit_enable_bits (line 1385)."""

    def test_limit_enable_bits_defaults(self):
        """Non-list/tuple or short value => (True, True) (line 1385)."""
        from bac_py.app.event_engine import _limit_enable_bits

        assert _limit_enable_bits(None) == (True, True)
        assert _limit_enable_bits(42) == (True, True)
        assert _limit_enable_bits([True]) == (True, True)

    def test_limit_enable_bits_normal(self):
        """Normal list with 2+ elements."""
        from bac_py.app.event_engine import _limit_enable_bits

        assert _limit_enable_bits([True, False]) == (True, False)
        assert _limit_enable_bits([False, True]) == (False, True)


# ---------------------------------------------------------------------------
# _recipient_matches additional edge cases
# ---------------------------------------------------------------------------


class TestRecipientMatchesEdgeCases:
    """Cover remaining branches in _recipient_matches."""

    def test_valid_days_index_error(self):
        """valid_days too short => IndexError caught, allows (lines 1422-1423)."""
        from bac_py.app.event_engine import _recipient_matches
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        # valid_days with only 1 bit -- will cause IndexError for most weekdays
        dest = BACnetDestination(
            valid_days=None,  # type: ignore[arg-type]  # None causes TypeError
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(
                address=BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
            ),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3_all_true(),
        )

        result = _recipient_matches(dest, 0)
        assert result is True  # TypeError caught, allowed

    def test_time_window_attribute_error(self):
        """from_time/to_time are None => AttributeError caught (lines 1444-1445)."""
        from bac_py.app.event_engine import _recipient_matches
        from bac_py.network.address import BACnetAddress
        from bac_py.types.constructed import BACnetRecipient

        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=None,  # type: ignore[arg-type]  # Will cause AttributeError
            to_time=None,  # type: ignore[arg-type]
            recipient=BACnetRecipient(
                address=BACnetAddress(mac_address=b"\x01\x02\x03\x04\xba\xc0")
            ),
            process_identifier=0,
            issue_confirmed_notifications=False,
            transitions=_make_bitstring_3_all_true(),
        )

        result = _recipient_matches(dest, 0)
        assert result is True  # AttributeError caught, allowed


# ---------------------------------------------------------------------------
# _dest_address final return None
# ---------------------------------------------------------------------------


class TestDestAddressFinalReturnNone:
    """Cover final return None in _dest_address (line 1470)."""

    def test_dest_address_recipient_no_address_no_device(self):
        """Recipient with both address and device as None (line 1470)."""
        from bac_py.app.event_engine import _dest_address
        from bac_py.types.constructed import BACnetRecipient
        from bac_py.types.primitives import BACnetTime

        dest = BACnetDestination(
            valid_days=_make_bitstring_7_all_true(),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(device=None, address=None),
            process_identifier=0,
            issue_confirmed_notifications=True,
            transitions=_make_bitstring_3_all_true(),
        )

        result = _dest_address(dest)
        assert result is None


# ---------------------------------------------------------------------------
# _run_event_algorithm: list-to-tuple conversion branches
# ---------------------------------------------------------------------------


class TestRunEventAlgorithmListConversions:
    """Cover branches where params contain lists instead of tuples."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_enrollment_change_of_life_safety_list_params(self):
        """CHANGE_OF_LIFE_SAFETY params with lists triggers conversion (lines 993, 995)."""
        app = _make_app()
        db = app.object_db

        lsp = LifeSafetyPointObject(1)
        db.add(lsp)
        lsp._properties[PropertyIdentifier.TRACKING_VALUE] = LifeSafetyState.ALARM

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_LIFE_SAFETY,
            event_parameters={
                "alarm_values": [int(LifeSafetyState.PRE_ALARM)],  # list, not tuple
                "life_safety_alarm_values": [int(LifeSafetyState.ALARM)],  # list, not tuple
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

    def test_enrollment_change_of_status_flags_list_params(self):
        """CHANGE_OF_STATUS_FLAGS params with lists triggers conversion (lines 1063, 1065, 1067)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = [True, False, False, False]  # list

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_STATUS_FLAGS,
            event_parameters={
                "previous_flags": [False, False, False, False],  # list, not tuple
                "selected_flags": [True, True, True, True],  # list, not tuple
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

    def test_enrollment_change_of_reliability_int_value(self):
        """CHANGE_OF_RELIABILITY with int value triggers Reliability conversion (line 1073)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        # Use int value instead of Reliability enum
        av._properties[PropertyIdentifier.PRESENT_VALUE] = int(Reliability.OVER_RANGE)

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

    def test_enrollment_change_of_timer_list_alarm_values(self):
        """CHANGE_OF_TIMER with list alarm_values triggers conversion (lines 1078-1080)."""
        from bac_py.types.enums import TimerState

        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = TimerState.EXPIRED

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_TIMER,
            event_parameters={"alarm_values": [int(TimerState.EXPIRED)]},  # list not tuple
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

    def test_enrollment_unsupported_event_type(self):
        """Unsupported event type returns None (line 1087)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0

        ee = EventEnrollmentObject(
            1,
            event_type=9999,  # non-existent event type
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
        # No alarm for unsupported type
        assert not app.unconfirmed_request.called

    def test_enrollment_access_event_tuple_param(self):
        """ACCESS_EVENT with tuple access_event_list skips conversion (line 1021->1023)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 5

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.ACCESS_EVENT,
            event_parameters={"access_event_list": (5, 10)},  # already a tuple
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

    def test_enrollment_characterstring_tuple_param(self):
        """CHANGE_OF_CHARACTERSTRING with tuple alarm_values (line 1054->1056)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = "FAULT"

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_CHARACTERSTRING,
            event_parameters={"alarm_values": ("FAULT", "ERROR")},  # already a tuple
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
# Intrinsic: _run_intrinsic_algorithm edge cases
# ---------------------------------------------------------------------------


class TestIntrinsicAlgorithmEdgeCases:
    """Cover remaining branches in _run_intrinsic_algorithm."""

    def _make_engine(self, app: MagicMock) -> EventEngine:
        return EventEngine(app, scan_interval=1.0)

    def test_intrinsic_life_safety_no_tracking_value(self):
        """LifeSafety without TRACKING_VALUE uses present_value (line 912)."""
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
        # Set present_value to an alarm state but remove TRACKING_VALUE
        lsp._properties[PropertyIdentifier.PRESENT_VALUE] = LifeSafetyState.ALARM
        lsp._properties.pop(PropertyIdentifier.TRACKING_VALUE, None)

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        # Should detect alarm using present_value as tracking_value
        assert app.unconfirmed_request.called

    def test_intrinsic_unsupported_event_algorithm(self):
        """Object with unknown INTRINSIC_EVENT_ALGORITHM returns None (line 930)."""
        app = _make_app()
        db = app.object_db

        # Create an object with a non-standard INTRINSIC_EVENT_ALGORITHM
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
        # Override the class attribute on the instance to simulate unsupported
        ai.INTRINSIC_EVENT_ALGORITHM = EventType.EXTENDED  # type: ignore[misc]

        engine = self._make_engine(app)
        engine._evaluate_cycle()
        # No alarm for unsupported intrinsic event algorithm
        assert not app.unconfirmed_request.called


# ---------------------------------------------------------------------------
# Remaining partial branch coverage
# ---------------------------------------------------------------------------


class TestRemainingBranches:
    """Cover remaining partial branch gaps."""

    def test_fault_clearing_to_normal_disabled(self):
        """FAULT clearing where target is NORMAL but to-normal disabled.

        Covers branch 138->144 (to-normal disabled, falls through to line 144).
        """
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.FAULT,
            event_enable=[True, True, False],  # to-normal disabled
            time_delay=0,
        )
        # Fault clears, event algo says normal (None), so target = NORMAL
        # But to-normal is disabled, so the `if self.event_enable[2]` is False
        result = sm.evaluate(None, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_fault_clearing_to_offnormal_disabled(self):
        """FAULT clearing where target is offnormal but to-offnormal disabled.

        Covers branch 144->147 (pending state cleanup on disabled transition).
        """
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.FAULT,
            event_enable=[False, True, False],  # both to-offnormal and to-normal disabled
            time_delay=0,
        )
        # Fault clears, event algo says HIGH_LIMIT but to-offnormal disabled
        result = sm.evaluate(EventState.HIGH_LIMIT, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_enrollment_change_of_state_tuple_param(self):
        """CHANGE_OF_STATE with alarm_values as tuple (covers 955->957 false branch)."""
        app = _make_app()
        db = app.object_db

        mv = MultiStateValueObject(1, number_of_states=5)
        db.add(mv)
        mv._properties[PropertyIdentifier.PRESENT_VALUE] = 3

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_STATE,
            event_parameters={"alarm_values": (3, 5)},  # already a tuple
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=mv.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = EventEngine(app, scan_interval=1.0)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_bitstring_tuple_params(self):
        """CHANGE_OF_BITSTRING with bitmask and alarm_values as tuples (covers 962->964, 964->968)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = (1, 0, 1, 0)

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_BITSTRING,
            event_parameters={
                "bitmask": (1, 1, 1, 0),  # already a tuple
                "alarm_values": ((1, 0, 1, 0),),  # already a tuple of tuples
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

        engine = EventEngine(app, scan_interval=1.0)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_enrollment_timer_tuple_alarm_values(self):
        """CHANGE_OF_TIMER with alarm_values already a tuple (covers 1078->1080)."""
        from bac_py.types.enums import TimerState

        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = TimerState.EXPIRED

        ee = EventEnrollmentObject(
            1,
            event_type=EventType.CHANGE_OF_TIMER,
            event_parameters={"alarm_values": (int(TimerState.EXPIRED),)},  # tuple
            object_property_reference=BACnetDeviceObjectPropertyReference(
                object_identifier=av.object_identifier,
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            event_enable=[True, True, True],
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        engine = EventEngine(app, scan_interval=1.0)
        engine._evaluate_cycle()
        assert app.unconfirmed_request.called

    def test_fault_clearing_disabled_pending_state_matches(self):
        """FAULT clearing disabled, pending state already matches target (branch 144->147).

        When clearing from FAULT with transition disabled, if _pending_state
        already equals the target, the cleanup on lines 144-146 is skipped.
        """
        from bac_py.app.event_engine import EventStateMachine

        sm = EventStateMachine(
            event_state=EventState.FAULT,
            event_enable=[True, True, False],  # to-normal disabled
            time_delay=5.0,
        )

        # First eval: fault clears, target=NORMAL, to-normal disabled
        # _apply_delay won't be called, but pending_state may be set
        sm._pending_state = EventState.NORMAL  # simulate already pending
        sm._pending_since = 0.0

        result = sm.evaluate(None, Reliability.NO_FAULT_DETECTED, 1.0)
        assert result is None
        # Pending state should NOT be cleared since it matches target
        assert sm._pending_state == EventState.NORMAL

    def test_enrollment_second_cycle_reuses_context(self):
        """Second evaluation cycle reuses existing context (branch 716->723)."""
        app = _make_app()
        db = app.object_db

        av = AnalogValueObject(1)
        db.add(av)
        av._properties[PropertyIdentifier.PRESENT_VALUE] = 50.0  # normal

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

        engine = EventEngine(app, scan_interval=1.0)
        # First cycle: creates context
        engine._evaluate_cycle()
        key = (int(ee.object_identifier.object_type), ee.object_identifier.instance_number)
        assert key in engine._contexts

        # Second cycle: reuses existing context (covers 716->723 branch)
        engine._evaluate_cycle()
        assert key in engine._contexts

    def test_sync_state_machine_non_list_event_enable(self):
        """Sync with event_enable that is not a list (covers 1311->1314)."""
        from bac_py.app.event_engine import EventStateMachine

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
            event_enable="not-a-list",  # type: ignore[arg-type]
            time_delay=0,
            notification_class=0,
        )
        db.add(ee)

        sm = EventStateMachine()
        EventEngine._sync_state_machine(sm, ee)
        # event_enable should remain default since "not-a-list" fails isinstance check
        assert sm.event_enable == [True, True, True]
