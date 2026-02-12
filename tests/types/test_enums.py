"""Tests for BACnet enumeration types."""

from enum import IntEnum

import pytest

from bac_py.types.enums import (
    AbortReason,
    Action,
    BinaryPV,
    BvlcFunction,
    BvlcResultCode,
    ConfirmedServiceChoice,
    EnableDisable,
    EngineeringUnits,
    ErrorClass,
    ErrorCode,
    EventState,
    FileAccessMethod,
    NetworkMessageType,
    NetworkPriority,
    NetworkReachability,
    ObjectType,
    PduType,
    Polarity,
    ProgramChange,
    ProgramState,
    PropertyIdentifier,
    ReinitializedState,
    RejectMessageReason,
    RejectReason,
    Reliability,
    Segmentation,
    UnconfirmedServiceChoice,
)

ALL_ENUM_CLASSES = [
    ObjectType,
    PropertyIdentifier,
    ErrorClass,
    ErrorCode,
    Segmentation,
    AbortReason,
    RejectReason,
    PduType,
    ConfirmedServiceChoice,
    UnconfirmedServiceChoice,
    NetworkPriority,
    NetworkMessageType,
    BvlcFunction,
    BvlcResultCode,
    EventState,
    BinaryPV,
    Polarity,
    Reliability,
    EngineeringUnits,
    EnableDisable,
    ReinitializedState,
    FileAccessMethod,
    ProgramState,
    ProgramChange,
    Action,
    RejectMessageReason,
    NetworkReachability,
]


# ---------------------------------------------------------------------------
# All enum classes are IntEnum subclasses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_ENUM_CLASSES, ids=lambda c: c.__name__)
def test_all_enums_are_intenum_subclasses(cls: type) -> None:
    assert issubclass(cls, IntEnum)


@pytest.mark.parametrize("cls", ALL_ENUM_CLASSES, ids=lambda c: c.__name__)
def test_enum_members_usable_as_int(cls: type) -> None:
    member = next(iter(cls))
    assert isinstance(member, int)
    # Verify arithmetic works (IntEnum contract).
    assert member + 0 == int(member)


# ---------------------------------------------------------------------------
# ObjectType
# ---------------------------------------------------------------------------


class TestObjectType:
    def test_analog_input(self) -> None:
        assert ObjectType.ANALOG_INPUT == 0

    def test_analog_output(self) -> None:
        assert ObjectType.ANALOG_OUTPUT == 1

    def test_analog_value(self) -> None:
        assert ObjectType.ANALOG_VALUE == 2

    def test_binary_input(self) -> None:
        assert ObjectType.BINARY_INPUT == 3

    def test_binary_output(self) -> None:
        assert ObjectType.BINARY_OUTPUT == 4

    def test_binary_value(self) -> None:
        assert ObjectType.BINARY_VALUE == 5

    def test_device(self) -> None:
        assert ObjectType.DEVICE == 8

    def test_schedule(self) -> None:
        assert ObjectType.SCHEDULE == 17

    def test_multi_state_value(self) -> None:
        assert ObjectType.MULTI_STATE_VALUE == 19

    def test_trend_log(self) -> None:
        assert ObjectType.TREND_LOG == 20

    def test_network_port(self) -> None:
        assert ObjectType.NETWORK_PORT == 56

    def test_lift(self) -> None:
        assert ObjectType.LIFT == 59

    def test_member_count(self) -> None:
        assert len(ObjectType) == 63


# ---------------------------------------------------------------------------
# PropertyIdentifier
# ---------------------------------------------------------------------------


class TestPropertyIdentifier:
    def test_acked_transitions(self) -> None:
        assert PropertyIdentifier.ACKED_TRANSITIONS == 0

    def test_description(self) -> None:
        assert PropertyIdentifier.DESCRIPTION == 28

    def test_object_identifier(self) -> None:
        assert PropertyIdentifier.OBJECT_IDENTIFIER == 75

    def test_object_list(self) -> None:
        assert PropertyIdentifier.OBJECT_LIST == 76

    def test_object_name(self) -> None:
        assert PropertyIdentifier.OBJECT_NAME == 77

    def test_object_type(self) -> None:
        assert PropertyIdentifier.OBJECT_TYPE == 79

    def test_present_value(self) -> None:
        assert PropertyIdentifier.PRESENT_VALUE == 85

    def test_status_flags(self) -> None:
        assert PropertyIdentifier.STATUS_FLAGS == 111

    def test_units(self) -> None:
        assert PropertyIdentifier.UNITS == 117

    def test_vendor_identifier(self) -> None:
        assert PropertyIdentifier.VENDOR_IDENTIFIER == 120

    def test_vendor_name(self) -> None:
        assert PropertyIdentifier.VENDOR_NAME == 121

    def test_protocol_revision(self) -> None:
        assert PropertyIdentifier.PROTOCOL_REVISION == 139

    def test_max_apdu_length_accepted(self) -> None:
        assert PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED == 62

    def test_segmentation_supported(self) -> None:
        assert PropertyIdentifier.SEGMENTATION_SUPPORTED == 107

    def test_property_list(self) -> None:
        assert PropertyIdentifier.PROPERTY_LIST == 371

    def test_egress_active(self) -> None:
        assert PropertyIdentifier.EGRESS_ACTIVE == 386

    def test_vendor_property_id_accepted(self) -> None:
        """Vendor-proprietary property IDs beyond defined range should create pseudo-members."""
        prop = PropertyIdentifier(600)
        assert prop == 600
        assert prop.name == "VENDOR_600"

    def test_vendor_property_id_large(self) -> None:
        """Max 22-bit property namespace value should be accepted."""
        prop = PropertyIdentifier(4194303)
        assert prop == 4194303
        assert prop.name == "VENDOR_4194303"

    def test_vendor_property_id_out_of_range(self) -> None:
        """Values above the 22-bit namespace should still raise."""
        with pytest.raises(ValueError):
            PropertyIdentifier(4194304)

    def test_known_property_still_resolves(self) -> None:
        """Standard property IDs should resolve to their named members."""
        assert PropertyIdentifier(85) is PropertyIdentifier.PRESENT_VALUE


# ---------------------------------------------------------------------------
# ErrorClass
# ---------------------------------------------------------------------------


class TestErrorClass:
    def test_device(self) -> None:
        assert ErrorClass.DEVICE == 0

    def test_object(self) -> None:
        assert ErrorClass.OBJECT == 1

    def test_property(self) -> None:
        assert ErrorClass.PROPERTY == 2

    def test_resources(self) -> None:
        assert ErrorClass.RESOURCES == 3

    def test_security(self) -> None:
        assert ErrorClass.SECURITY == 4

    def test_services(self) -> None:
        assert ErrorClass.SERVICES == 5

    def test_vt(self) -> None:
        assert ErrorClass.VT == 6

    def test_communication(self) -> None:
        assert ErrorClass.COMMUNICATION == 7

    def test_member_count(self) -> None:
        assert len(ErrorClass) == 8


# ---------------------------------------------------------------------------
# ErrorCode
# ---------------------------------------------------------------------------


class TestErrorCode:
    def test_other(self) -> None:
        assert ErrorCode.OTHER == 0

    def test_device_busy(self) -> None:
        assert ErrorCode.DEVICE_BUSY == 3

    def test_unknown_object(self) -> None:
        assert ErrorCode.UNKNOWN_OBJECT == 31

    def test_unknown_property(self) -> None:
        assert ErrorCode.UNKNOWN_PROPERTY == 32

    def test_value_out_of_range(self) -> None:
        assert ErrorCode.VALUE_OUT_OF_RANGE == 37

    def test_write_access_denied(self) -> None:
        assert ErrorCode.WRITE_ACCESS_DENIED == 40

    def test_read_access_denied(self) -> None:
        assert ErrorCode.READ_ACCESS_DENIED == 27

    def test_timeout(self) -> None:
        assert ErrorCode.TIMEOUT == 30

    def test_service_request_denied(self) -> None:
        assert ErrorCode.SERVICE_REQUEST_DENIED == 29

    def test_communication_disabled(self) -> None:
        assert ErrorCode.COMMUNICATION_DISABLED == 83

    def test_optional_functionality_not_supported(self) -> None:
        assert ErrorCode.OPTIONAL_FUNCTIONALITY_NOT_SUPPORTED == 45


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


class TestSegmentation:
    def test_both(self) -> None:
        assert Segmentation.BOTH == 0

    def test_transmit(self) -> None:
        assert Segmentation.TRANSMIT == 1

    def test_receive(self) -> None:
        assert Segmentation.RECEIVE == 2

    def test_none(self) -> None:
        assert Segmentation.NONE == 3

    def test_member_count(self) -> None:
        assert len(Segmentation) == 4


# ---------------------------------------------------------------------------
# AbortReason
# ---------------------------------------------------------------------------


class TestAbortReason:
    def test_other(self) -> None:
        assert AbortReason.OTHER == 0

    def test_buffer_overflow(self) -> None:
        assert AbortReason.BUFFER_OVERFLOW == 1

    def test_invalid_apdu_in_this_state(self) -> None:
        assert AbortReason.INVALID_APDU_IN_THIS_STATE == 2

    def test_segmentation_not_supported(self) -> None:
        assert AbortReason.SEGMENTATION_NOT_SUPPORTED == 4

    def test_security_error(self) -> None:
        assert AbortReason.SECURITY_ERROR == 5

    def test_tsm_timeout(self) -> None:
        assert AbortReason.TSM_TIMEOUT == 10

    def test_apdu_too_long(self) -> None:
        assert AbortReason.APDU_TOO_LONG == 11

    def test_member_count(self) -> None:
        assert len(AbortReason) == 12


# ---------------------------------------------------------------------------
# RejectReason
# ---------------------------------------------------------------------------


class TestRejectReason:
    def test_other(self) -> None:
        assert RejectReason.OTHER == 0

    def test_buffer_overflow(self) -> None:
        assert RejectReason.BUFFER_OVERFLOW == 1

    def test_inconsistent_parameters(self) -> None:
        assert RejectReason.INCONSISTENT_PARAMETERS == 2

    def test_missing_required_parameter(self) -> None:
        assert RejectReason.MISSING_REQUIRED_PARAMETER == 5

    def test_too_many_arguments(self) -> None:
        assert RejectReason.TOO_MANY_ARGUMENTS == 7

    def test_unrecognized_service(self) -> None:
        assert RejectReason.UNRECOGNIZED_SERVICE == 9

    def test_member_count(self) -> None:
        assert len(RejectReason) == 10


# ---------------------------------------------------------------------------
# PduType
# ---------------------------------------------------------------------------


class TestPduType:
    def test_confirmed_request(self) -> None:
        assert PduType.CONFIRMED_REQUEST == 0

    def test_unconfirmed_request(self) -> None:
        assert PduType.UNCONFIRMED_REQUEST == 1

    def test_simple_ack(self) -> None:
        assert PduType.SIMPLE_ACK == 2

    def test_complex_ack(self) -> None:
        assert PduType.COMPLEX_ACK == 3

    def test_segment_ack(self) -> None:
        assert PduType.SEGMENT_ACK == 4

    def test_error(self) -> None:
        assert PduType.ERROR == 5

    def test_reject(self) -> None:
        assert PduType.REJECT == 6

    def test_abort(self) -> None:
        assert PduType.ABORT == 7

    def test_member_count(self) -> None:
        assert len(PduType) == 8


# ---------------------------------------------------------------------------
# ConfirmedServiceChoice
# ---------------------------------------------------------------------------


class TestConfirmedServiceChoice:
    def test_acknowledge_alarm(self) -> None:
        assert ConfirmedServiceChoice.ACKNOWLEDGE_ALARM == 0

    def test_subscribe_cov(self) -> None:
        assert ConfirmedServiceChoice.SUBSCRIBE_COV == 5

    def test_atomic_read_file(self) -> None:
        assert ConfirmedServiceChoice.ATOMIC_READ_FILE == 6

    def test_read_property(self) -> None:
        assert ConfirmedServiceChoice.READ_PROPERTY == 12

    def test_read_property_multiple(self) -> None:
        assert ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE == 14

    def test_write_property(self) -> None:
        assert ConfirmedServiceChoice.WRITE_PROPERTY == 15

    def test_write_property_multiple(self) -> None:
        assert ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE == 16

    def test_device_communication_control(self) -> None:
        assert ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL == 17

    def test_reinitialize_device(self) -> None:
        assert ConfirmedServiceChoice.REINITIALIZE_DEVICE == 20

    def test_confirmed_cov_notification_multiple(self) -> None:
        assert ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION_MULTIPLE == 31

    def test_confirmed_audit_notification(self) -> None:
        assert ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION == 32

    def test_audit_log_query(self) -> None:
        assert ConfirmedServiceChoice.AUDIT_LOG_QUERY == 33


# ---------------------------------------------------------------------------
# UnconfirmedServiceChoice
# ---------------------------------------------------------------------------


class TestUnconfirmedServiceChoice:
    def test_i_am(self) -> None:
        assert UnconfirmedServiceChoice.I_AM == 0

    def test_i_have(self) -> None:
        assert UnconfirmedServiceChoice.I_HAVE == 1

    def test_unconfirmed_cov_notification(self) -> None:
        assert UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION == 2

    def test_time_synchronization(self) -> None:
        assert UnconfirmedServiceChoice.TIME_SYNCHRONIZATION == 6

    def test_who_has(self) -> None:
        assert UnconfirmedServiceChoice.WHO_HAS == 7

    def test_who_is(self) -> None:
        assert UnconfirmedServiceChoice.WHO_IS == 8

    def test_utc_time_synchronization(self) -> None:
        assert UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION == 9

    def test_write_group(self) -> None:
        assert UnconfirmedServiceChoice.WRITE_GROUP == 10

    def test_unconfirmed_cov_notification_multiple(self) -> None:
        assert UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION_MULTIPLE == 11

    def test_unconfirmed_audit_notification(self) -> None:
        assert UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION == 12

    def test_who_am_i(self) -> None:
        assert UnconfirmedServiceChoice.WHO_AM_I == 13

    def test_you_are(self) -> None:
        assert UnconfirmedServiceChoice.YOU_ARE == 14

    def test_member_count(self) -> None:
        assert len(UnconfirmedServiceChoice) == 15


# ---------------------------------------------------------------------------
# NetworkPriority
# ---------------------------------------------------------------------------


class TestNetworkPriority:
    def test_normal(self) -> None:
        assert NetworkPriority.NORMAL == 0

    def test_urgent(self) -> None:
        assert NetworkPriority.URGENT == 1

    def test_critical_equipment(self) -> None:
        assert NetworkPriority.CRITICAL_EQUIPMENT == 2

    def test_life_safety(self) -> None:
        assert NetworkPriority.LIFE_SAFETY == 3

    def test_member_count(self) -> None:
        assert len(NetworkPriority) == 4


# ---------------------------------------------------------------------------
# NetworkMessageType
# ---------------------------------------------------------------------------


class TestNetworkMessageType:
    def test_who_is_router_to_network(self) -> None:
        assert NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK == 0x00

    def test_i_am_router_to_network(self) -> None:
        assert NetworkMessageType.I_AM_ROUTER_TO_NETWORK == 0x01

    def test_reject_message_to_network(self) -> None:
        assert NetworkMessageType.REJECT_MESSAGE_TO_NETWORK == 0x03

    def test_initialize_routing_table(self) -> None:
        assert NetworkMessageType.INITIALIZE_ROUTING_TABLE == 0x06

    def test_initialize_routing_table_ack(self) -> None:
        assert NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK == 0x07

    def test_security_payload(self) -> None:
        assert NetworkMessageType.SECURITY_PAYLOAD == 0x0B

    def test_what_is_network_number(self) -> None:
        assert NetworkMessageType.WHAT_IS_NETWORK_NUMBER == 0x12

    def test_network_number_is(self) -> None:
        assert NetworkMessageType.NETWORK_NUMBER_IS == 0x13

    def test_member_count(self) -> None:
        assert len(NetworkMessageType) == 20


# ---------------------------------------------------------------------------
# BvlcFunction
# ---------------------------------------------------------------------------


class TestBvlcFunction:
    def test_bvlc_result(self) -> None:
        assert BvlcFunction.BVLC_RESULT == 0x00

    def test_forwarded_npdu(self) -> None:
        assert BvlcFunction.FORWARDED_NPDU == 0x04

    def test_register_foreign_device(self) -> None:
        assert BvlcFunction.REGISTER_FOREIGN_DEVICE == 0x05

    def test_distribute_broadcast_to_network(self) -> None:
        assert BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK == 0x09

    def test_original_unicast_npdu(self) -> None:
        assert BvlcFunction.ORIGINAL_UNICAST_NPDU == 0x0A

    def test_original_broadcast_npdu(self) -> None:
        assert BvlcFunction.ORIGINAL_BROADCAST_NPDU == 0x0B

    def test_secure_bvll(self) -> None:
        assert BvlcFunction.SECURE_BVLL == 0x0C

    def test_member_count(self) -> None:
        assert len(BvlcFunction) == 13


# ---------------------------------------------------------------------------
# BvlcResultCode
# ---------------------------------------------------------------------------


class TestBvlcResultCode:
    def test_successful_completion(self) -> None:
        assert BvlcResultCode.SUCCESSFUL_COMPLETION == 0x0000

    def test_write_broadcast_distribution_table_nak(self) -> None:
        assert BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK == 0x0010

    def test_read_broadcast_distribution_table_nak(self) -> None:
        assert BvlcResultCode.READ_BROADCAST_DISTRIBUTION_TABLE_NAK == 0x0020

    def test_register_foreign_device_nak(self) -> None:
        assert BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK == 0x0030

    def test_read_foreign_device_table_nak(self) -> None:
        assert BvlcResultCode.READ_FOREIGN_DEVICE_TABLE_NAK == 0x0040

    def test_delete_foreign_device_table_entry_nak(self) -> None:
        assert BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK == 0x0050

    def test_distribute_broadcast_to_network_nak(self) -> None:
        assert BvlcResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK == 0x0060

    def test_member_count(self) -> None:
        assert len(BvlcResultCode) == 7


# ---------------------------------------------------------------------------
# EventState
# ---------------------------------------------------------------------------


class TestEventState:
    def test_normal(self) -> None:
        assert EventState.NORMAL == 0

    def test_fault(self) -> None:
        assert EventState.FAULT == 1

    def test_offnormal(self) -> None:
        assert EventState.OFFNORMAL == 2

    def test_high_limit(self) -> None:
        assert EventState.HIGH_LIMIT == 3

    def test_low_limit(self) -> None:
        assert EventState.LOW_LIMIT == 4

    def test_life_safety_alarm(self) -> None:
        assert EventState.LIFE_SAFETY_ALARM == 5

    def test_member_count(self) -> None:
        assert len(EventState) == 6


# ---------------------------------------------------------------------------
# BinaryPV
# ---------------------------------------------------------------------------


class TestBinaryPV:
    def test_inactive(self) -> None:
        assert BinaryPV.INACTIVE == 0

    def test_active(self) -> None:
        assert BinaryPV.ACTIVE == 1

    def test_member_count(self) -> None:
        assert len(BinaryPV) == 2


# ---------------------------------------------------------------------------
# Polarity
# ---------------------------------------------------------------------------


class TestPolarity:
    def test_normal(self) -> None:
        assert Polarity.NORMAL == 0

    def test_reverse(self) -> None:
        assert Polarity.REVERSE == 1

    def test_member_count(self) -> None:
        assert len(Polarity) == 2


# ---------------------------------------------------------------------------
# Reliability
# ---------------------------------------------------------------------------


class TestReliability:
    def test_no_fault_detected(self) -> None:
        assert Reliability.NO_FAULT_DETECTED == 0

    def test_no_sensor(self) -> None:
        assert Reliability.NO_SENSOR == 1

    def test_over_range(self) -> None:
        assert Reliability.OVER_RANGE == 2

    def test_communication_failure(self) -> None:
        assert Reliability.COMMUNICATION_FAILURE == 12

    def test_tripped(self) -> None:
        assert Reliability.TRIPPED == 15

    def test_faults_listed(self) -> None:
        assert Reliability.FAULTS_LISTED == 23

    def test_referenced_object_fault(self) -> None:
        assert Reliability.REFERENCED_OBJECT_FAULT == 24

    def test_member_count(self) -> None:
        assert len(Reliability) == 24


# ---------------------------------------------------------------------------
# EngineeringUnits
# ---------------------------------------------------------------------------


class TestEngineeringUnits:
    def test_degrees_celsius(self) -> None:
        assert EngineeringUnits.DEGREES_CELSIUS == 62

    def test_degrees_fahrenheit(self) -> None:
        assert EngineeringUnits.DEGREES_FAHRENHEIT == 64

    def test_watts(self) -> None:
        assert EngineeringUnits.WATTS == 48

    def test_kilowatt_hours(self) -> None:
        assert EngineeringUnits.KILOWATT_HOURS == 19

    def test_percent(self) -> None:
        assert EngineeringUnits.PERCENT == 98

    def test_no_units(self) -> None:
        assert EngineeringUnits.NO_UNITS == 95

    def test_square_meters(self) -> None:
        assert EngineeringUnits.SQUARE_METERS == 0

    def test_amperes(self) -> None:
        assert EngineeringUnits.AMPERES == 3

    def test_liters_per_second(self) -> None:
        assert EngineeringUnits.LITERS_PER_SECOND == 85

    def test_member_count(self) -> None:
        assert len(EngineeringUnits) == 62


# ---------------------------------------------------------------------------
# EnableDisable
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_enable(self) -> None:
        assert EnableDisable.ENABLE == 0

    def test_disable(self) -> None:
        assert EnableDisable.DISABLE == 1

    def test_disable_initiation(self) -> None:
        assert EnableDisable.DISABLE_INITIATION == 2

    def test_member_count(self) -> None:
        assert len(EnableDisable) == 3


# ---------------------------------------------------------------------------
# ReinitializedState
# ---------------------------------------------------------------------------


class TestReinitializedState:
    def test_coldstart(self) -> None:
        assert ReinitializedState.COLDSTART == 0

    def test_warmstart(self) -> None:
        assert ReinitializedState.WARMSTART == 1

    def test_start_backup(self) -> None:
        assert ReinitializedState.START_BACKUP == 2

    def test_end_restore(self) -> None:
        assert ReinitializedState.END_RESTORE == 5

    def test_activate_changes(self) -> None:
        assert ReinitializedState.ACTIVATE_CHANGES == 7

    def test_member_count(self) -> None:
        assert len(ReinitializedState) == 8


# ---------------------------------------------------------------------------
# FileAccessMethod
# ---------------------------------------------------------------------------


class TestFileAccessMethod:
    def test_stream_access(self) -> None:
        assert FileAccessMethod.STREAM_ACCESS == 0

    def test_record_access(self) -> None:
        assert FileAccessMethod.RECORD_ACCESS == 1

    def test_member_count(self) -> None:
        assert len(FileAccessMethod) == 2


# ---------------------------------------------------------------------------
# ProgramState
# ---------------------------------------------------------------------------


class TestProgramState:
    def test_idle(self) -> None:
        assert ProgramState.IDLE == 0

    def test_loading(self) -> None:
        assert ProgramState.LOADING == 1

    def test_running(self) -> None:
        assert ProgramState.RUNNING == 2

    def test_waiting(self) -> None:
        assert ProgramState.WAITING == 3

    def test_halted(self) -> None:
        assert ProgramState.HALTED == 4

    def test_unloading(self) -> None:
        assert ProgramState.UNLOADING == 5

    def test_member_count(self) -> None:
        assert len(ProgramState) == 6


# ---------------------------------------------------------------------------
# ProgramChange
# ---------------------------------------------------------------------------


class TestProgramChange:
    def test_ready(self) -> None:
        assert ProgramChange.READY == 0

    def test_load(self) -> None:
        assert ProgramChange.LOAD == 1

    def test_run(self) -> None:
        assert ProgramChange.RUN == 2

    def test_halt(self) -> None:
        assert ProgramChange.HALT == 3

    def test_restart(self) -> None:
        assert ProgramChange.RESTART == 4

    def test_unload(self) -> None:
        assert ProgramChange.UNLOAD == 5

    def test_member_count(self) -> None:
        assert len(ProgramChange) == 6


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------


class TestAction:
    def test_direct(self) -> None:
        assert Action.DIRECT == 0

    def test_reverse(self) -> None:
        assert Action.REVERSE == 1

    def test_member_count(self) -> None:
        assert len(Action) == 2


# ---------------------------------------------------------------------------
# RejectMessageReason
# ---------------------------------------------------------------------------


class TestRejectMessageReason:
    def test_other(self) -> None:
        assert RejectMessageReason.OTHER == 0

    def test_not_directly_connected(self) -> None:
        assert RejectMessageReason.NOT_DIRECTLY_CONNECTED == 1

    def test_router_busy(self) -> None:
        assert RejectMessageReason.ROUTER_BUSY == 2

    def test_unknown_message_type(self) -> None:
        assert RejectMessageReason.UNKNOWN_MESSAGE_TYPE == 3

    def test_message_too_long(self) -> None:
        assert RejectMessageReason.MESSAGE_TOO_LONG == 4

    def test_security_error(self) -> None:
        assert RejectMessageReason.SECURITY_ERROR == 5

    def test_addressing_error(self) -> None:
        assert RejectMessageReason.ADDRESSING_ERROR == 6

    def test_member_count(self) -> None:
        assert len(RejectMessageReason) == 7


# ---------------------------------------------------------------------------
# NetworkReachability
# ---------------------------------------------------------------------------


class TestNetworkReachability:
    def test_reachable(self) -> None:
        assert NetworkReachability.REACHABLE == 0

    def test_busy(self) -> None:
        assert NetworkReachability.BUSY == 1

    def test_unreachable(self) -> None:
        assert NetworkReachability.UNREACHABLE == 2

    def test_member_count(self) -> None:
        assert len(NetworkReachability) == 3


# ---------------------------------------------------------------------------
# IntEnum integer interoperability
# ---------------------------------------------------------------------------


class TestIntEnumInterop:
    def test_object_type_int_comparison(self) -> None:
        assert ObjectType.DEVICE == 8
        assert ObjectType.DEVICE == 8

    def test_object_type_arithmetic(self) -> None:
        result = ObjectType.ANALOG_INPUT + 8
        assert result == 8

    def test_property_id_used_as_dict_key(self) -> None:
        mapping = {PropertyIdentifier.PRESENT_VALUE: "temperature"}
        assert mapping[85] == "temperature"
        assert mapping[PropertyIdentifier.PRESENT_VALUE] == "temperature"

    def test_enum_int_cast(self) -> None:
        assert int(ObjectType.DEVICE) == 8
        assert int(PropertyIdentifier.PRESENT_VALUE) == 85

    def test_enum_in_range(self) -> None:
        assert ObjectType.DEVICE in range(0, 60)

    def test_enum_hash_matches_int(self) -> None:
        assert hash(ObjectType.DEVICE) == hash(8)

    def test_bvlc_function_hex_values(self) -> None:
        assert BvlcFunction.ORIGINAL_UNICAST_NPDU == 10
        assert BvlcFunction.ORIGINAL_BROADCAST_NPDU == 11

    def test_bvlc_result_code_hex_values(self) -> None:
        assert BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK == 48
        assert BvlcResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK == 96


# ---------------------------------------------------------------------------
# Enum lookup by value
# ---------------------------------------------------------------------------


class TestEnumLookup:
    def test_object_type_from_value(self) -> None:
        assert ObjectType(0) is ObjectType.ANALOG_INPUT
        assert ObjectType(8) is ObjectType.DEVICE
        assert ObjectType(56) is ObjectType.NETWORK_PORT

    def test_property_identifier_from_value(self) -> None:
        assert PropertyIdentifier(85) is PropertyIdentifier.PRESENT_VALUE
        assert PropertyIdentifier(77) is PropertyIdentifier.OBJECT_NAME
        assert PropertyIdentifier(79) is PropertyIdentifier.OBJECT_TYPE

    def test_confirmed_service_choice_from_value(self) -> None:
        assert ConfirmedServiceChoice(12) is ConfirmedServiceChoice.READ_PROPERTY
        assert ConfirmedServiceChoice(15) is ConfirmedServiceChoice.WRITE_PROPERTY

    def test_unconfirmed_service_choice_from_value(self) -> None:
        assert UnconfirmedServiceChoice(0) is UnconfirmedServiceChoice.I_AM
        assert UnconfirmedServiceChoice(8) is UnconfirmedServiceChoice.WHO_IS

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            ObjectType(9999)

    def test_error_class_from_value(self) -> None:
        assert ErrorClass(2) is ErrorClass.PROPERTY

    def test_pdu_type_from_value(self) -> None:
        assert PduType(0) is PduType.CONFIRMED_REQUEST
        assert PduType(7) is PduType.ABORT


# ---------------------------------------------------------------------------
# Enum lookup by name
# ---------------------------------------------------------------------------


class TestEnumNameLookup:
    def test_object_type_by_name(self) -> None:
        assert ObjectType["DEVICE"] is ObjectType.DEVICE

    def test_property_identifier_by_name(self) -> None:
        assert PropertyIdentifier["PRESENT_VALUE"] is PropertyIdentifier.PRESENT_VALUE

    def test_error_class_by_name(self) -> None:
        assert ErrorClass["SERVICES"] is ErrorClass.SERVICES

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(KeyError):
            ObjectType["DOES_NOT_EXIST"]
