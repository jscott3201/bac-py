"""Event state machine, algorithm evaluators, and async engine per ASHRAE 135-2020 Clause 13.

The :class:`EventStateMachine` implements the state transition logic of
Clause 13.2.  Each ``evaluate_*`` function implements one of the 18 event
algorithm evaluators defined in Clause 13.3.

The :class:`EventEngine` is the async integration layer that periodically
evaluates ``EventEnrollment`` objects and intrinsic-reporting objects,
drives the state machines, and dispatches ``EventNotificationRequest``
PDUs on state transitions.

The state machine and evaluators are **pure logic** -- no async, no I/O,
no side effects.  The ``EventEngine`` provides the async scheduling and
notification dispatch wrapper.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bac_py.types.enums import (
    EventState,
    EventType,
    NotifyType,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.app.application import BACnetApplication
    from bac_py.objects.base import BACnetObject
    from bac_py.types.enums import LifeSafetyState, TimerState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventTransition -- result of a state machine evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventTransition:
    """Result of a state-machine evaluation that triggered a transition.

    :param from_state: The state before the transition.
    :param to_state: The state after the transition.
    :param timestamp: Monotonic time when the transition fired.
    """

    from_state: EventState
    to_state: EventState
    timestamp: float


# ---------------------------------------------------------------------------
# EventStateMachine -- Clause 13.2
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EventStateMachine:
    """Per-enrollment event state machine (Clause 13.2).

    Tracks state, timestamps, acknowledgments, and time-delay logic.
    Call :meth:`evaluate` each scan cycle with the event algorithm result
    and the fault algorithm result.  Returns an :class:`EventTransition`
    when a state change fires, or ``None`` when no change occurs.

    :param event_state: Current event state.
    :param event_enable: Three-element list ``[to_offnormal, to_fault,
        to_normal]``.
    :param acked_transitions: Three-element list ``[to_offnormal, to_fault,
        to_normal]`` indicating which transitions have been acknowledged.
    :param time_delay: Seconds the event condition must persist before
        transitioning to an alarm state.
    :param time_delay_normal: Seconds the normal condition must persist
        before returning to ``NORMAL``.  Defaults to *time_delay* when
        ``None``.
    """

    event_state: EventState = EventState.NORMAL
    event_enable: list[bool] = field(default_factory=lambda: [True, True, True])
    acked_transitions: list[bool] = field(default_factory=lambda: [True, True, True])
    time_delay: float = 0.0
    time_delay_normal: float | None = None

    # Internal: monotonic time when the pending condition was first detected.
    _pending_state: EventState | None = field(default=None, repr=False)
    _pending_since: float | None = field(default=None, repr=False)

    @property
    def effective_time_delay_normal(self) -> float:
        """Return the effective time-delay-normal value."""
        return self.time_delay_normal if self.time_delay_normal is not None else self.time_delay

    def evaluate(
        self,
        event_result: EventState | None,
        fault_result: Reliability,
        current_time: float,
    ) -> EventTransition | None:
        """Evaluate one scan cycle and return a transition if one fires.

        :param event_result: Target :class:`EventState` from the event
            algorithm, or ``None`` if no alarm condition is detected.
        :param fault_result: :class:`Reliability` from the fault algorithm.
            Any value other than ``NO_FAULT_DETECTED`` indicates a fault.
        :param current_time: Monotonic clock value (seconds).
        :returns: An :class:`EventTransition` if a state change fires,
            ``None`` otherwise.
        """
        has_fault = fault_result != Reliability.NO_FAULT_DETECTED

        # --- FAULT transitions take priority (Clause 13.2.5) ---
        if has_fault and self.event_state != EventState.FAULT:
            if self.event_enable[1]:  # to-fault enabled
                return self._transition(EventState.FAULT, current_time)
            return None

        # --- Staying in FAULT while still faulted ---
        if has_fault and self.event_state == EventState.FAULT:
            return None

        # --- Clearing from FAULT ---
        if self.event_state == EventState.FAULT and not has_fault:
            # Determine return state
            target = event_result if event_result is not None else EventState.NORMAL
            if target == EventState.NORMAL:
                if self.event_enable[2]:  # to-normal enabled
                    return self._apply_delay(target, current_time, normal=True)
            else:
                if self.event_enable[0]:  # to-offnormal enabled
                    return self._apply_delay(target, current_time, normal=False)
            # If transition disabled, stay in FAULT
            if self._pending_state != target:
                self._pending_state = None
                self._pending_since = None
            return None

        # --- NORMAL -> alarm transitions ---
        if self.event_state == EventState.NORMAL:
            if (
                event_result is not None
                and event_result != EventState.NORMAL
                and self.event_enable[0]  # to-offnormal enabled
            ):
                return self._apply_delay(event_result, current_time, normal=False)
            # Condition cleared while pending
            self._pending_state = None
            self._pending_since = None
            return None

        # --- Alarm -> NORMAL transitions ---
        if event_result is None or event_result == EventState.NORMAL:
            if self.event_enable[2]:  # to-normal enabled
                return self._apply_delay(EventState.NORMAL, current_time, normal=True)
            self._pending_state = None
            self._pending_since = None
            return None

        # --- Alarm -> different alarm (e.g., HIGH_LIMIT -> LOW_LIMIT) ---
        if event_result != self.event_state and self.event_enable[0]:  # to-offnormal
            return self._apply_delay(event_result, current_time, normal=False)

        # Staying in same alarm state -- clear any pending
        self._pending_state = None
        self._pending_since = None
        return None

    def _apply_delay(
        self,
        target: EventState,
        current_time: float,
        *,
        normal: bool,
    ) -> EventTransition | None:
        """Apply time-delay logic and return a transition if the delay has elapsed."""
        delay = self.effective_time_delay_normal if normal else self.time_delay

        if self._pending_state != target:
            # New condition -- start timing
            self._pending_state = target
            self._pending_since = current_time
            if delay <= 0:
                return self._transition(target, current_time)
            return None

        # Same condition still active -- check if delay elapsed
        assert self._pending_since is not None
        if current_time - self._pending_since >= delay:
            return self._transition(target, current_time)
        return None

    def _transition(self, target: EventState, current_time: float) -> EventTransition:
        """Execute a state transition and update internal bookkeeping."""
        old = self.event_state
        self.event_state = target
        self._pending_state = None
        self._pending_since = None

        # Update acked_transitions: mark the relevant transition as unacknowledged
        if target == EventState.FAULT:
            self.acked_transitions[1] = False
        elif target == EventState.NORMAL:
            self.acked_transitions[2] = False
        else:
            self.acked_transitions[0] = False

        return EventTransition(from_state=old, to_state=target, timestamp=current_time)


# ---------------------------------------------------------------------------
# Event Algorithm Evaluators -- Clause 13.3
# ---------------------------------------------------------------------------
#
# Each evaluator is a pure function returning the target EventState if an
# alarm condition is detected, or None if the monitored value is normal.
#
# Group A -- Threshold-based
# ---------------------------------------------------------------------------


def evaluate_out_of_range(
    value: float,
    high_limit: float,
    low_limit: float,
    deadband: float,
    *,
    current_state: EventState = EventState.NORMAL,
) -> EventState | None:
    """Evaluate OUT_OF_RANGE (Clause 13.3.6).

    :param value: Current monitored real value.
    :param high_limit: High-limit threshold.
    :param low_limit: Low-limit threshold.
    :param deadband: Hysteresis value for returning to normal.
    :param current_state: The current event state (for deadband logic).
    :returns: Target :class:`EventState` or ``None``.
    """
    if value > high_limit:
        return EventState.HIGH_LIMIT
    if value < low_limit:
        return EventState.LOW_LIMIT
    # Deadband: must drop below (high_limit - deadband) to go normal from HIGH_LIMIT
    if current_state == EventState.HIGH_LIMIT and value >= high_limit - deadband:
        return EventState.HIGH_LIMIT
    if current_state == EventState.LOW_LIMIT and value <= low_limit + deadband:
        return EventState.LOW_LIMIT
    return None


def evaluate_double_out_of_range(
    value: float,
    high_limit: float,
    low_limit: float,
    deadband: float,
    *,
    current_state: EventState = EventState.NORMAL,
) -> EventState | None:
    """Evaluate DOUBLE_OUT_OF_RANGE (Clause 13.3.14).

    Same logic as OUT_OF_RANGE but for Double precision values.
    """
    return evaluate_out_of_range(
        value, high_limit, low_limit, deadband, current_state=current_state
    )


def evaluate_signed_out_of_range(
    value: int,
    high_limit: int,
    low_limit: int,
    deadband: int,
    *,
    current_state: EventState = EventState.NORMAL,
) -> EventState | None:
    """Evaluate SIGNED_OUT_OF_RANGE (Clause 13.3.15).

    Same logic as OUT_OF_RANGE but for Signed integer values.
    """
    return evaluate_out_of_range(
        value, high_limit, low_limit, deadband, current_state=current_state
    )


def evaluate_unsigned_out_of_range(
    value: int,
    high_limit: int,
    low_limit: int,
    deadband: int,
    *,
    current_state: EventState = EventState.NORMAL,
) -> EventState | None:
    """Evaluate UNSIGNED_OUT_OF_RANGE (Clause 13.3.16).

    Same logic as OUT_OF_RANGE but for Unsigned integer values.
    """
    return evaluate_out_of_range(
        value, high_limit, low_limit, deadband, current_state=current_state
    )


def evaluate_unsigned_range(
    value: int,
    high_limit: int,
    low_limit: int,
) -> EventState | None:
    """Evaluate UNSIGNED_RANGE (Clause 13.3.11).

    Simpler variant with no deadband.

    :param value: Current monitored unsigned value.
    :param high_limit: High-limit threshold.
    :param low_limit: Low-limit threshold.
    :returns: Target :class:`EventState` or ``None``.
    """
    if value > high_limit:
        return EventState.HIGH_LIMIT
    if value < low_limit:
        return EventState.LOW_LIMIT
    return None


def evaluate_floating_limit(
    value: float,
    setpoint: float,
    high_diff_limit: float,
    low_diff_limit: float,
    deadband: float,
    *,
    current_state: EventState = EventState.NORMAL,
) -> EventState | None:
    """Evaluate FLOATING_LIMIT (Clause 13.3.5).

    Limits are relative to *setpoint*: ``setpoint + high_diff_limit`` and
    ``setpoint - low_diff_limit``.

    :param value: Current monitored real value.
    :param setpoint: Reference setpoint.
    :param high_diff_limit: Positive offset above setpoint for high limit.
    :param low_diff_limit: Positive offset below setpoint for low limit.
    :param deadband: Hysteresis value.
    :param current_state: Current event state for deadband logic.
    :returns: Target :class:`EventState` or ``None``.
    """
    high_limit = setpoint + high_diff_limit
    low_limit = setpoint - low_diff_limit
    return evaluate_out_of_range(
        value, high_limit, low_limit, deadband, current_state=current_state
    )


# ---------------------------------------------------------------------------
# Group B -- Set membership
# ---------------------------------------------------------------------------


def evaluate_change_of_state(
    value: int,
    alarm_values: tuple[int, ...],
) -> EventState | None:
    """Evaluate CHANGE_OF_STATE (Clause 13.3.2).

    :param value: Current enumerated property value (as int).
    :param alarm_values: Tuple of enumerated values that trigger OFFNORMAL.
    :returns: ``OFFNORMAL`` if *value* is in *alarm_values*, else ``None``.
    """
    if value in alarm_values:
        return EventState.OFFNORMAL
    return None


def evaluate_change_of_bitstring(
    value: tuple[int, ...],
    bitmask: tuple[int, ...],
    alarm_values: tuple[tuple[int, ...], ...],
) -> EventState | None:
    """Evaluate CHANGE_OF_BITSTRING (Clause 13.3.1).

    Applies *bitmask* to *value* and checks if the masked result matches
    any entry in *alarm_values*.

    :param value: Current bitstring as tuple of bit values (0/1).
    :param bitmask: Bitmask to AND with *value*.
    :param alarm_values: Set of masked bitstring values that trigger OFFNORMAL.
    :returns: ``OFFNORMAL`` if masked value matches any alarm value, else ``None``.
    """
    masked = tuple(v & m for v, m in zip(value, bitmask, strict=False))
    if masked in alarm_values:
        return EventState.OFFNORMAL
    return None


def evaluate_change_of_life_safety(
    tracking_value: LifeSafetyState,
    mode: int,
    alarm_values: tuple[int, ...],
    life_safety_alarm_values: tuple[int, ...],
) -> EventState | None:
    """Evaluate CHANGE_OF_LIFE_SAFETY (Clause 13.3.8).

    :param tracking_value: Current life-safety state.
    :param mode: Current life-safety mode (as int).
    :param alarm_values: States triggering OFFNORMAL.
    :param life_safety_alarm_values: States triggering LIFE_SAFETY_ALARM.
    :returns: Target state or ``None``.
    """
    _ = mode  # Mode filtering is caller's responsibility
    val = int(tracking_value)
    if val in life_safety_alarm_values:
        return EventState.LIFE_SAFETY_ALARM
    if val in alarm_values:
        return EventState.OFFNORMAL
    return None


def evaluate_change_of_characterstring(
    value: str,
    alarm_values: tuple[str, ...],
) -> EventState | None:
    """Evaluate CHANGE_OF_CHARACTERSTRING (Clause 13.3.17).

    :param value: Current character string value.
    :param alarm_values: Strings that trigger OFFNORMAL.
    :returns: ``OFFNORMAL`` if *value* is in *alarm_values*, else ``None``.
    """
    if value in alarm_values:
        return EventState.OFFNORMAL
    return None


def evaluate_access_event(
    access_event: int,
    access_event_list: tuple[int, ...],
) -> EventState | None:
    """Evaluate ACCESS_EVENT (Clause 13.3.13).

    :param access_event: Current access event value (as int).
    :param access_event_list: Events that trigger OFFNORMAL.
    :returns: ``OFFNORMAL`` if *access_event* is in the list, else ``None``.
    """
    if access_event in access_event_list:
        return EventState.OFFNORMAL
    return None


# ---------------------------------------------------------------------------
# Group C -- Change detection
# ---------------------------------------------------------------------------


def evaluate_change_of_value(
    value: float,
    previous_value: float,
    cov_increment: float,
) -> EventState | None:
    """Evaluate CHANGE_OF_VALUE (Clause 13.3.3).

    Triggers OFFNORMAL when the absolute change since the last reported
    value exceeds *cov_increment*.

    :param value: Current monitored value.
    :param previous_value: Value at last notification.
    :param cov_increment: Minimum change to trigger.
    :returns: ``OFFNORMAL`` if change exceeds increment, else ``None``.
    """
    if abs(value - previous_value) >= cov_increment:
        return EventState.OFFNORMAL
    return None


def evaluate_change_of_status_flags(
    current_flags: tuple[bool, ...],
    previous_flags: tuple[bool, ...],
    selected_flags: tuple[bool, ...],
) -> EventState | None:
    """Evaluate CHANGE_OF_STATUS_FLAGS (Clause 13.3.18).

    Triggers OFFNORMAL when any selected flag has changed from its
    previous value.

    :param current_flags: Current status flags (in_alarm, fault, overridden, out_of_service).
    :param previous_flags: Previous status flags at last notification.
    :param selected_flags: Which flags to monitor (True = monitor).
    :returns: ``OFFNORMAL`` if any selected flag changed, else ``None``.
    """
    for cur, prev, sel in zip(current_flags, previous_flags, selected_flags, strict=False):
        if sel and cur != prev:
            return EventState.OFFNORMAL
    return None


def evaluate_change_of_reliability(
    reliability: Reliability,
) -> EventState | None:
    """Evaluate CHANGE_OF_RELIABILITY (Clause 13.3.19).

    :param reliability: Current reliability value.
    :returns: ``OFFNORMAL`` if reliability is not ``NO_FAULT_DETECTED``,
        else ``None``.
    """
    if reliability != Reliability.NO_FAULT_DETECTED:
        return EventState.OFFNORMAL
    return None


def evaluate_command_failure(
    feedback_value: Any,
    command_value: Any,
) -> EventState | None:
    """Evaluate COMMAND_FAILURE (Clause 13.3.4).

    Triggers OFFNORMAL when the feedback value does not match the
    commanded value (the time-delay enforcement is handled by the
    state machine, not this evaluator).

    :param feedback_value: Current feedback property value.
    :param command_value: Most recent commanded value.
    :returns: ``OFFNORMAL`` if feedback != command, else ``None``.
    """
    if feedback_value != command_value:
        return EventState.OFFNORMAL
    return None


# ---------------------------------------------------------------------------
# Group D -- Specialized
# ---------------------------------------------------------------------------


def evaluate_buffer_ready(
    current_count: int,
    previous_count: int,
    notification_threshold: int,
) -> EventState | None:
    """Evaluate BUFFER_READY (Clause 13.3.10).

    Triggers OFFNORMAL when the number of new records since the last
    notification meets or exceeds the threshold.

    :param current_count: Current record count.
    :param previous_count: Record count at last notification.
    :param notification_threshold: Minimum new records to trigger.
    :returns: ``OFFNORMAL`` if threshold met, else ``None``.
    """
    if current_count - previous_count >= notification_threshold:
        return EventState.OFFNORMAL
    return None


def evaluate_extended(
    monitored_value: Any,
    params: Any,
    *,
    vendor_callback: Callable[[Any, Any], EventState | None] | None = None,
) -> EventState | None:
    """Evaluate EXTENDED (Clause 13.3.9).

    Vendor-specific algorithm.  Delegates to *vendor_callback* if provided.

    :param monitored_value: Current property value.
    :param params: Vendor-specific parameters.
    :param vendor_callback: Optional callable implementing vendor logic.
    :returns: Target state from callback, or ``None``.
    """
    if vendor_callback is not None:
        return vendor_callback(monitored_value, params)
    return None


def evaluate_change_of_timer(
    timer_state: TimerState,
    alarm_values: tuple[int, ...],
) -> EventState | None:
    """Evaluate CHANGE_OF_TIMER (Clause 13.3.20, new in 2020).

    :param timer_state: Current timer state.
    :param alarm_values: Timer state values (as int) that trigger OFFNORMAL.
    :returns: ``OFFNORMAL`` if current state is in alarm values, else ``None``.
    """
    if int(timer_state) in alarm_values:
        return EventState.OFFNORMAL
    return None


# ---------------------------------------------------------------------------
# EventEngine -- Async integration layer (Clause 13)
# ---------------------------------------------------------------------------


class _EnrollmentContext:
    """Per-enrollment tracking state for the EventEngine."""

    __slots__ = ("last_reliability", "state_machine")

    def __init__(self) -> None:
        self.state_machine = EventStateMachine()
        self.last_reliability: Reliability = Reliability.NO_FAULT_DETECTED


class EventEngine:
    """Async event/alarm evaluation engine per Clause 13.

    Mirrors the ``COVManager`` lifecycle pattern:

    - Constructed with a reference to :class:`BACnetApplication`.
    - :meth:`start` launches the periodic evaluation loop.
    - :meth:`stop` cancels the loop and cleans up.

    Each evaluation cycle iterates ``EventEnrollment`` objects and
    intrinsic-reporting objects in the object database, runs fault
    algorithms (Clause 13.4) then event algorithms (Clause 13.3),
    feeds results to per-enrollment :class:`EventStateMachine` instances,
    and dispatches ``EventNotificationRequest`` PDUs on transitions.
    """

    def __init__(
        self,
        app: BACnetApplication,
        *,
        scan_interval: float = 1.0,
    ) -> None:
        self._app = app
        self._scan_interval = scan_interval
        self._task: asyncio.Task[None] | None = None
        # Keyed by (object_type, instance_number) for both enrollment and intrinsic
        self._contexts: dict[tuple[int, int], _EnrollmentContext] = {}

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the periodic evaluation loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the evaluation loop and clean up."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._contexts.clear()

    # --- Main loop ---

    async def _run_loop(self) -> None:
        """Periodically evaluate all enrollments and intrinsic objects."""
        try:
            while True:
                self._evaluate_cycle()
                await asyncio.sleep(self._scan_interval)
        except asyncio.CancelledError:
            return

    def _evaluate_cycle(self) -> None:
        """Run one evaluation cycle across all monitored objects."""
        now = time.monotonic()
        db = self._app.object_db

        # 1. Evaluate EventEnrollment objects
        for obj in db.get_objects_of_type(ObjectType.EVENT_ENROLLMENT):
            self._evaluate_enrollment(obj, now)

        # 2. Evaluate intrinsic-reporting objects
        for bac_obj in db.values():
            if bac_obj.INTRINSIC_EVENT_ALGORITHM is not None:
                self._evaluate_intrinsic(bac_obj, now)

    # --- Enrollment-based evaluation ---

    def _evaluate_enrollment(self, enrollment: BACnetObject, now: float) -> None:
        """Evaluate a single EventEnrollment object."""
        # Check event_detection_enable
        detection_enable = self._read_prop(enrollment, PropertyIdentifier.EVENT_DETECTION_ENABLE)
        if detection_enable is False:
            return

        # Get or create context
        key = (int(enrollment.object_identifier.object_type), enrollment.object_identifier.instance_number)
        ctx = self._contexts.get(key)
        if ctx is None:
            ctx = _EnrollmentContext()
            # Sync event_enable and time_delay from the enrollment object
            self._sync_state_machine(ctx.state_machine, enrollment)
            self._contexts[key] = ctx

        # Sync state machine settings each cycle in case they changed
        self._sync_state_machine(ctx.state_machine, enrollment)

        # Read monitored property
        monitored_value = self._read_monitored_property(enrollment)
        if monitored_value is _SENTINEL:
            return  # Cannot read; skip this cycle

        # Run fault evaluation
        fault_result = self._evaluate_enrollment_fault(enrollment, monitored_value)

        # Run event algorithm
        event_type = self._read_prop(enrollment, PropertyIdentifier.EVENT_TYPE)
        event_result = self._run_event_algorithm(
            event_type, monitored_value, enrollment, ctx.state_machine.event_state
        )

        # Check Event_Algorithm_Inhibit (Clause 13.2.2, p.638)
        algorithm_inhibit = self._read_prop(enrollment, PropertyIdentifier.EVENT_ALGORITHM_INHIBIT)
        if algorithm_inhibit is True:
            event_result = EventState.NORMAL

        # Feed to state machine
        transition = ctx.state_machine.evaluate(event_result, fault_result, now)
        if transition is not None:
            self._dispatch_notification(enrollment, transition, event_type, fault_result)

    def _read_monitored_property(self, enrollment: BACnetObject) -> Any:
        """Read the property referenced by an enrollment's Object_Property_Reference."""
        ref = self._read_prop(enrollment, PropertyIdentifier.OBJECT_PROPERTY_REFERENCE)
        if ref is None:
            return _SENTINEL

        db = self._app.object_db
        target_obj = db.get(ref.object_identifier)
        if target_obj is None:
            return _SENTINEL

        prop_id = ref.property_identifier
        try:
            return target_obj.read_property(prop_id, ref.property_array_index)
        except Exception:
            logger.debug(
                "Failed to read monitored property %s on %s",
                prop_id,
                ref.object_identifier,
                exc_info=True,
            )
            return _SENTINEL

    @staticmethod
    def _evaluate_enrollment_fault(
        enrollment: BACnetObject,
        monitored_value: Any,
    ) -> Reliability:
        """Run fault evaluation for an enrollment object."""
        # Check Reliability_Evaluation_Inhibit (Clause 13.2.2, p.638)
        inhibit = enrollment._properties.get(PropertyIdentifier.RELIABILITY_EVALUATION_INHIBIT)
        if inhibit is True:
            return Reliability.NO_FAULT_DETECTED

        # Check reliability of the enrollment object itself
        reliability = enrollment._properties.get(PropertyIdentifier.RELIABILITY)
        if isinstance(reliability, Reliability) and reliability != Reliability.NO_FAULT_DETECTED:
            return reliability
        return Reliability.NO_FAULT_DETECTED

    # --- Intrinsic reporting evaluation ---

    def _evaluate_intrinsic(self, obj: BACnetObject, now: float) -> None:
        """Evaluate an intrinsic-reporting object."""
        # Check event_detection_enable if present
        detection_enable = obj._properties.get(PropertyIdentifier.EVENT_DETECTION_ENABLE)
        if detection_enable is False:
            return

        key = (int(obj.object_identifier.object_type), obj.object_identifier.instance_number)
        ctx = self._contexts.get(key)
        if ctx is None:
            ctx = _EnrollmentContext()
            self._sync_intrinsic_state_machine(ctx.state_machine, obj)
            self._contexts[key] = ctx

        self._sync_intrinsic_state_machine(ctx.state_machine, obj)

        # Read present value
        try:
            present_value = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        except Exception:
            return

        # Fault: check reliability property
        reliability = obj._properties.get(
            PropertyIdentifier.RELIABILITY, Reliability.NO_FAULT_DETECTED
        )
        fault_result = (
            reliability if reliability != Reliability.NO_FAULT_DETECTED else Reliability.NO_FAULT_DETECTED
        )

        # Check Reliability_Evaluation_Inhibit (Clause 13.2.2, p.638)
        rel_inhibit = obj._properties.get(PropertyIdentifier.RELIABILITY_EVALUATION_INHIBIT)
        if rel_inhibit is True:
            fault_result = Reliability.NO_FAULT_DETECTED

        # Run intrinsic event algorithm
        event_type = obj.INTRINSIC_EVENT_ALGORITHM
        event_result = self._run_intrinsic_algorithm(event_type, present_value, obj, ctx)

        # Check Event_Algorithm_Inhibit (Clause 13.2.2, p.638)
        algorithm_inhibit = obj._properties.get(PropertyIdentifier.EVENT_ALGORITHM_INHIBIT)
        if algorithm_inhibit is True:
            event_result = EventState.NORMAL

        transition = ctx.state_machine.evaluate(event_result, fault_result, now)
        if transition is not None:
            self._dispatch_intrinsic_notification(obj, transition, event_type, fault_result)

    def _run_intrinsic_algorithm(
        self,
        event_type: EventType | None,
        present_value: Any,
        obj: BACnetObject,
        ctx: _EnrollmentContext,
    ) -> EventState | None:
        """Run the intrinsic event algorithm for an object."""
        if event_type == EventType.OUT_OF_RANGE:
            high_limit = obj._properties.get(PropertyIdentifier.HIGH_LIMIT)
            low_limit = obj._properties.get(PropertyIdentifier.LOW_LIMIT)
            deadband = obj._properties.get(PropertyIdentifier.DEADBAND, 0.0)
            if high_limit is None or low_limit is None:
                return None
            # Check limit_enable
            limit_enable = obj._properties.get(PropertyIdentifier.LIMIT_ENABLE)
            if limit_enable is not None:
                # limit_enable is a BitString or list: [high_limit_enable, low_limit_enable]
                bits = _limit_enable_bits(limit_enable)
                effective_high = high_limit if bits[0] else float("inf")
                effective_low = low_limit if bits[1] else float("-inf")
            else:
                effective_high = high_limit
                effective_low = low_limit
            return evaluate_out_of_range(
                float(present_value),
                effective_high,
                effective_low,
                float(deadband),
                current_state=ctx.state_machine.event_state,
            )

        if event_type == EventType.CHANGE_OF_STATE:
            alarm_values = obj._properties.get(PropertyIdentifier.ALARM_VALUES)
            if alarm_values is None:
                # Try ALARM_VALUE (singular) for binary objects
                alarm_value = obj._properties.get(PropertyIdentifier.ALARM_VALUE)
                if alarm_value is None:
                    return None
                alarm_values = (alarm_value,)
            if not isinstance(alarm_values, tuple):
                alarm_values = tuple(alarm_values)
            return evaluate_change_of_state(present_value, alarm_values)

        return None

    # --- Event algorithm dispatch ---

    def _run_event_algorithm(
        self,
        event_type: Any,
        monitored_value: Any,
        enrollment: BACnetObject,
        current_state: EventState,
    ) -> EventState | None:
        """Dispatch to the appropriate event algorithm evaluator."""
        params = self._read_prop(enrollment, PropertyIdentifier.EVENT_PARAMETERS)

        if event_type == EventType.OUT_OF_RANGE and isinstance(params, dict):
            return evaluate_out_of_range(
                float(monitored_value),
                params.get("high_limit", float("inf")),
                params.get("low_limit", float("-inf")),
                params.get("deadband", 0.0),
                current_state=current_state,
            )

        if event_type == EventType.CHANGE_OF_STATE and isinstance(params, dict):
            alarm_values = params.get("alarm_values", ())
            if not isinstance(alarm_values, tuple):
                alarm_values = tuple(alarm_values)
            return evaluate_change_of_state(monitored_value, alarm_values)

        if event_type == EventType.CHANGE_OF_BITSTRING and isinstance(params, dict):
            bitmask = params.get("bitmask", ())
            alarm_values = params.get("alarm_values", ())
            if not isinstance(bitmask, tuple):
                bitmask = tuple(bitmask)
            if not isinstance(alarm_values, tuple):
                alarm_values = tuple(tuple(v) if not isinstance(v, tuple) else v for v in alarm_values)
            return evaluate_change_of_bitstring(monitored_value, bitmask, alarm_values)

        if event_type == EventType.CHANGE_OF_VALUE and isinstance(params, dict):
            prev = params.get("previous_value", monitored_value)
            increment = params.get("cov_increment", 0.0)
            return evaluate_change_of_value(float(monitored_value), float(prev), float(increment))

        if event_type == EventType.COMMAND_FAILURE and isinstance(params, dict):
            feedback = params.get("feedback_value")
            return evaluate_command_failure(feedback, monitored_value)

        # Unsupported or no params -- no alarm
        return None

    # --- Notification dispatch ---

    def _dispatch_notification(
        self,
        enrollment: BACnetObject,
        transition: EventTransition,
        event_type: Any,
        fault_result: Reliability,
    ) -> None:
        """Build and send an EventNotificationRequest for an enrollment transition."""
        from bac_py.services.event_notification import EventNotificationRequest
        from bac_py.types.constructed import BACnetTimeStamp

        notify_type = self._read_prop(enrollment, PropertyIdentifier.NOTIFY_TYPE)
        if notify_type is None:
            notify_type = NotifyType.ALARM

        notification_class_num = self._read_prop(enrollment, PropertyIdentifier.NOTIFICATION_CLASS)
        if notification_class_num is None:
            notification_class_num = 0

        priority = self._get_priority(notification_class_num, transition.to_state)

        # Determine ack_required from notification class
        ack_required = self._get_ack_required(notification_class_num, transition.to_state)

        notification = EventNotificationRequest(
            process_identifier=0,
            initiating_device_identifier=self._app.device_object_identifier,
            event_object_identifier=enrollment.object_identifier,
            time_stamp=BACnetTimeStamp(choice=1, value=int(transition.timestamp)),
            notification_class=notification_class_num,
            priority=priority,
            event_type=event_type if isinstance(event_type, EventType) else EventType.CHANGE_OF_STATE,
            notify_type=notify_type,
            to_state=transition.to_state,
            ack_required=ack_required,
            from_state=transition.from_state,
        )

        self._send_notification(notification)

        # Update event_time_stamps on the enrollment
        self._update_event_timestamps(enrollment, transition)

    def _dispatch_intrinsic_notification(
        self,
        obj: BACnetObject,
        transition: EventTransition,
        event_type: EventType | None,
        fault_result: Reliability,
    ) -> None:
        """Build and send an EventNotificationRequest for an intrinsic object."""
        from bac_py.services.event_notification import EventNotificationRequest
        from bac_py.types.constructed import BACnetTimeStamp

        notify_type = obj._properties.get(PropertyIdentifier.NOTIFY_TYPE, NotifyType.ALARM)
        notification_class_num = obj._properties.get(PropertyIdentifier.NOTIFICATION_CLASS, 0)
        priority = self._get_priority(notification_class_num, transition.to_state)
        ack_required = self._get_ack_required(notification_class_num, transition.to_state)

        notification = EventNotificationRequest(
            process_identifier=0,
            initiating_device_identifier=self._app.device_object_identifier,
            event_object_identifier=obj.object_identifier,
            time_stamp=BACnetTimeStamp(choice=1, value=int(transition.timestamp)),
            notification_class=notification_class_num,
            priority=priority,
            event_type=event_type if event_type is not None else EventType.CHANGE_OF_STATE,
            notify_type=notify_type,
            to_state=transition.to_state,
            ack_required=ack_required,
            from_state=transition.from_state,
        )

        self._send_notification(notification)

        # Update event_state on the object itself
        obj._properties[PropertyIdentifier.EVENT_STATE] = transition.to_state

        # Update event_time_stamps if present
        self._update_event_timestamps(obj, transition)

    def _send_notification(self, notification: Any) -> None:
        """Encode and send an event notification via the application."""
        from bac_py.types.enums import UnconfirmedServiceChoice

        try:
            encoded = notification.encode()
        except Exception:
            logger.debug("Failed to encode event notification", exc_info=True)
            return

        try:
            from bac_py.network.address import GLOBAL_BROADCAST

            self._app.unconfirmed_request(
                destination=GLOBAL_BROADCAST,
                service_choice=UnconfirmedServiceChoice.UNCONFIRMED_EVENT_NOTIFICATION,
                service_data=encoded,
            )
        except Exception:
            logger.debug("Failed to send event notification", exc_info=True)

    # --- Helper methods ---

    def _get_priority(self, notification_class_num: int, to_state: EventState) -> int:
        """Look up the priority from the NotificationClass object."""
        from bac_py.types.primitives import ObjectIdentifier

        nc_oid = ObjectIdentifier(ObjectType.NOTIFICATION_CLASS, notification_class_num)
        nc_obj = self._app.object_db.get(nc_oid)
        if nc_obj is None:
            return 0
        priorities = nc_obj._properties.get(PropertyIdentifier.PRIORITY)
        if not isinstance(priorities, list) or len(priorities) < 3:
            return 0
        idx = _transition_index(to_state)
        return int(priorities[idx])

    def _get_ack_required(self, notification_class_num: int, to_state: EventState) -> bool:
        """Look up ack_required from the NotificationClass object."""
        from bac_py.types.primitives import ObjectIdentifier

        nc_oid = ObjectIdentifier(ObjectType.NOTIFICATION_CLASS, notification_class_num)
        nc_obj = self._app.object_db.get(nc_oid)
        if nc_obj is None:
            return False
        ack_req = nc_obj._properties.get(PropertyIdentifier.ACK_REQUIRED)
        if not isinstance(ack_req, list) or len(ack_req) < 3:
            return False
        idx = _transition_index(to_state)
        return bool(ack_req[idx])

    @staticmethod
    def _sync_state_machine(sm: EventStateMachine, enrollment: BACnetObject) -> None:
        """Synchronize state machine settings from an enrollment object."""
        event_enable = enrollment._properties.get(PropertyIdentifier.EVENT_ENABLE)
        if isinstance(event_enable, list) and len(event_enable) >= 3:
            sm.event_enable = list(event_enable[:3])

        time_delay = enrollment._properties.get(PropertyIdentifier.TIME_DELAY)
        if isinstance(time_delay, (int, float)):
            sm.time_delay = float(time_delay)

        time_delay_normal = enrollment._properties.get(PropertyIdentifier.TIME_DELAY_NORMAL)
        if isinstance(time_delay_normal, (int, float)):
            sm.time_delay_normal = float(time_delay_normal)

    @staticmethod
    def _sync_intrinsic_state_machine(sm: EventStateMachine, obj: BACnetObject) -> None:
        """Synchronize state machine settings from an intrinsic-reporting object."""
        event_enable = obj._properties.get(PropertyIdentifier.EVENT_ENABLE)
        if isinstance(event_enable, list) and len(event_enable) >= 3:
            sm.event_enable = list(event_enable[:3])

        time_delay = obj._properties.get(PropertyIdentifier.TIME_DELAY)
        if isinstance(time_delay, (int, float)):
            sm.time_delay = float(time_delay)

        time_delay_normal = obj._properties.get(PropertyIdentifier.TIME_DELAY_NORMAL)
        if isinstance(time_delay_normal, (int, float)):
            sm.time_delay_normal = float(time_delay_normal)

        # Sync event_state from object to state machine on first load
        event_state = obj._properties.get(PropertyIdentifier.EVENT_STATE)
        if isinstance(event_state, EventState) and sm.event_state == EventState.NORMAL:
            sm.event_state = event_state

    @staticmethod
    def _update_event_timestamps(
        obj: BACnetObject,
        transition: EventTransition,
    ) -> None:
        """Update the event_time_stamps property on a transition."""
        from bac_py.types.constructed import BACnetTimeStamp

        timestamps = obj._properties.get(PropertyIdentifier.EVENT_TIME_STAMPS)
        if not isinstance(timestamps, list) or len(timestamps) < 3:
            return
        idx = _transition_index(transition.to_state)
        timestamps[idx] = BACnetTimeStamp(choice=1, value=int(transition.timestamp))

    @staticmethod
    def _read_prop(obj: BACnetObject, prop_id: PropertyIdentifier) -> Any:
        """Read a property safely, returning None on error."""
        try:
            return obj.read_property(prop_id)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _transition_index(to_state: EventState) -> int:
    """Map a target EventState to its 3-element array index."""
    if to_state == EventState.FAULT:
        return 1
    if to_state == EventState.NORMAL:
        return 2
    return 0  # offnormal / high_limit / low_limit / life_safety_alarm


def _limit_enable_bits(limit_enable: Any) -> tuple[bool, bool]:
    """Extract (high_limit_enable, low_limit_enable) from a LimitEnable value."""
    if isinstance(limit_enable, (list, tuple)) and len(limit_enable) >= 2:
        return (bool(limit_enable[0]), bool(limit_enable[1]))
    return (True, True)
