"""Fault algorithm evaluators per ASHRAE 135-2020 Clause 13.4.

Each public function evaluates one fault algorithm variant.  They are
pure functions -- no I/O, no async, no side effects -- making them
straightforward to unit-test.

**Contract with the caller:**  The ``reliability_evaluation_inhibit``
property (PropertyIdentifier 357) is checked by the caller *before*
invoking any evaluator.  When that flag is ``True`` the caller must
skip evaluation and keep the current ``Reliability`` value unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bac_py.types.enums import Reliability

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from bac_py.types.constructed import StatusFlags
    from bac_py.types.enums import LifeSafetyState
    from bac_py.types.fault_params import (
        FaultCharacterString,
        FaultExtended,
        FaultLifeSafety,
        FaultListed,
        FaultOutOfRange,
        FaultState,
        FaultStatusFlags,
    )


def evaluate_fault_characterstring(
    current_value: str,
    params: FaultCharacterString,
) -> Reliability:
    """Evaluate FAULT_CHARACTERSTRING (Clause 13.4.1).

    If *current_value* matches any string in ``params.fault_values``,
    return ``MULTI_STATE_FAULT``; otherwise return ``NO_FAULT_DETECTED``.

    :param current_value: The current character-string property value.
    :param params: Fault parameter configuration carrying the list of
        fault-triggering strings.
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    if current_value in params.fault_values:
        return Reliability.MULTI_STATE_FAULT
    return Reliability.NO_FAULT_DETECTED


def evaluate_fault_extended(
    current_value: Any,
    params: FaultExtended,
    *,
    vendor_callback: Callable[[Any, FaultExtended], Reliability] | None = None,
) -> Reliability:
    """Evaluate FAULT_EXTENDED (Clause 13.4.2).

    Vendor-specific algorithm.  If *vendor_callback* is provided the
    evaluation is delegated to it; otherwise ``NO_FAULT_DETECTED`` is
    returned because the algorithm cannot be evaluated without
    vendor-supplied logic.

    :param current_value: The current property value (type varies by
        vendor).
    :param params: Fault parameter configuration with vendor-id,
        extended-fault-type, and raw parameter bytes.
    :param vendor_callback: Optional callable implementing the
        vendor-specific evaluation logic.
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    if vendor_callback is not None:
        return vendor_callback(current_value, params)
    return Reliability.NO_FAULT_DETECTED


def evaluate_fault_life_safety(
    current_value: LifeSafetyState,
    params: FaultLifeSafety,
) -> Reliability:
    """Evaluate FAULT_LIFE_SAFETY (Clause 13.4.3).

    If *current_value* appears in ``params.fault_values``, return
    ``MULTI_STATE_FAULT``.  Mode filtering (``params.mode_values``) is
    the responsibility of the caller -- it determines *whether* this
    evaluator should be invoked at all.

    :param current_value: The current life-safety state.
    :param params: Fault parameter configuration carrying fault values
        and mode values.
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    if current_value in params.fault_values:
        return Reliability.MULTI_STATE_FAULT
    return Reliability.NO_FAULT_DETECTED


def evaluate_fault_state(
    current_value: int,
    params: FaultState,
    *,
    fault_enum_values: tuple[int, ...] = (),
) -> Reliability:
    """Evaluate FAULT_STATE (Clause 13.4.4).

    Because ``BACnetPropertyStates`` is a large CHOICE type whose
    ``params.fault_values`` are stored as raw bytes, the caller
    pre-parses them into *fault_enum_values* -- a tuple of integer
    enumeration values to match against.

    :param current_value: The current enumerated property value
        (as an integer).
    :param params: Fault parameter configuration (used for reference;
        the actual match set is *fault_enum_values*).
    :param fault_enum_values: Pre-parsed integer enumeration values
        derived from ``params.fault_values``.
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    # params is kept in the signature for API consistency and to allow
    # future use; currently the pre-parsed values are authoritative.
    _ = params
    if current_value in fault_enum_values:
        return Reliability.MULTI_STATE_FAULT
    return Reliability.NO_FAULT_DETECTED


def evaluate_fault_status_flags(
    current_flags: StatusFlags,
    params: FaultStatusFlags,
) -> Reliability:
    """Evaluate FAULT_STATUS_FLAGS (Clause 13.4.5).

    If the *fault* bit in *current_flags* is set, return
    ``MEMBER_FAULT``.  The ``params.status_flags_ref`` tells the caller
    *where* to read the flags from; the actual flag values are supplied
    as *current_flags*.

    :param current_flags: The resolved status-flags value.
    :param params: Fault parameter configuration carrying the property
        reference (used by the caller, not by this evaluator).
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    _ = params
    if current_flags.fault:
        return Reliability.MEMBER_FAULT
    return Reliability.NO_FAULT_DETECTED


def evaluate_fault_out_of_range(
    current_value: float | int,
    params: FaultOutOfRange,
) -> Reliability:
    """Evaluate FAULT_OUT_OF_RANGE (Clause 13.4.6).

    Returns ``UNDER_RANGE`` when *current_value* is strictly less than
    ``params.min_normal_value``, ``OVER_RANGE`` when strictly greater
    than ``params.max_normal_value``, and ``NO_FAULT_DETECTED``
    otherwise.  Values exactly at the boundary are *not* faulted.

    :param current_value: The current analog property value.
    :param params: Fault parameter configuration with min/max normal
        value boundaries.
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    if current_value < params.min_normal_value:
        return Reliability.UNDER_RANGE
    if current_value > params.max_normal_value:
        return Reliability.OVER_RANGE
    return Reliability.NO_FAULT_DETECTED


def evaluate_fault_listed(
    current_value: Any,
    params: FaultListed,
    *,
    fault_list: tuple[tuple[Any, Callable[..., Reliability]], ...] = (),
) -> Reliability:
    """Evaluate FAULT_LISTED (Clause 13.4.7).

    Iterates over *fault_list* -- a sequence of
    ``(fault_params, evaluator_fn)`` pairs -- and returns the first
    non-``NO_FAULT_DETECTED`` result.  If every evaluator returns
    ``NO_FAULT_DETECTED`` (or the list is empty), ``NO_FAULT_DETECTED``
    is returned.

    ``params.fault_list_ref`` tells the caller *where* to read the
    fault list; the resolved list content is supplied as *fault_list*.

    :param current_value: The current property value forwarded to each
        sub-evaluator.
    :param params: Fault parameter configuration carrying the property
        reference (used by the caller, not directly by this evaluator).
    :param fault_list: Pre-resolved sequence of fault parameter /
        evaluator pairs.
    :returns: Computed :class:`~bac_py.types.enums.Reliability` value.
    """
    _ = params
    for sub_params, evaluator_fn in fault_list:
        result = evaluator_fn(current_value, sub_params)
        if result != Reliability.NO_FAULT_DETECTED:
            return result
    return Reliability.NO_FAULT_DETECTED
