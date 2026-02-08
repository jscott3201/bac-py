"""Tests for device management services."""

from bac_py.services.device_mgmt import (
    DeviceCommunicationControlRequest,
    ReinitializeDeviceRequest,
    TimeSynchronizationRequest,
    UTCTimeSynchronizationRequest,
)
from bac_py.types.enums import EnableDisable, ReinitializedState
from bac_py.types.primitives import BACnetDate, BACnetTime


class TestDeviceCommunicationControl:
    def test_round_trip_all_fields(self):
        request = DeviceCommunicationControlRequest(
            enable_disable=EnableDisable.DISABLE,
            time_duration=300,
            password="secret",
        )
        encoded = request.encode()
        decoded = DeviceCommunicationControlRequest.decode(encoded)
        assert decoded.enable_disable == EnableDisable.DISABLE
        assert decoded.time_duration == 300
        assert decoded.password == "secret"

    def test_round_trip_no_optional_fields(self):
        request = DeviceCommunicationControlRequest(
            enable_disable=EnableDisable.ENABLE,
        )
        encoded = request.encode()
        decoded = DeviceCommunicationControlRequest.decode(encoded)
        assert decoded.enable_disable == EnableDisable.ENABLE
        assert decoded.time_duration is None
        assert decoded.password is None

    def test_round_trip_time_duration_only(self):
        request = DeviceCommunicationControlRequest(
            enable_disable=EnableDisable.DISABLE_INITIATION,
            time_duration=60,
        )
        encoded = request.encode()
        decoded = DeviceCommunicationControlRequest.decode(encoded)
        assert decoded.enable_disable == EnableDisable.DISABLE_INITIATION
        assert decoded.time_duration == 60
        assert decoded.password is None

    def test_round_trip_password_only(self):
        request = DeviceCommunicationControlRequest(
            enable_disable=EnableDisable.DISABLE,
            password="mypassword",
        )
        encoded = request.encode()
        decoded = DeviceCommunicationControlRequest.decode(encoded)
        assert decoded.enable_disable == EnableDisable.DISABLE
        assert decoded.time_duration is None
        assert decoded.password == "mypassword"


class TestReinitializeDevice:
    def test_round_trip_coldstart(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.COLDSTART,
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.COLDSTART
        assert decoded.password is None

    def test_round_trip_warmstart_with_password(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.WARMSTART,
            password="admin123",
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.WARMSTART
        assert decoded.password == "admin123"

    def test_round_trip_all_states(self):
        for state in ReinitializedState:
            request = ReinitializeDeviceRequest(reinitialized_state=state)
            encoded = request.encode()
            decoded = ReinitializeDeviceRequest.decode(encoded)
            assert decoded.reinitialized_state == state


class TestTimeSynchronization:
    def test_round_trip(self):
        date = BACnetDate(2024, 6, 15, 6)
        time = BACnetTime(14, 30, 0, 0)
        request = TimeSynchronizationRequest(date=date, time=time)
        encoded = request.encode()
        decoded = TimeSynchronizationRequest.decode(encoded)
        assert decoded.date.year == 2024
        assert decoded.date.month == 6
        assert decoded.date.day == 15
        assert decoded.time.hour == 14
        assert decoded.time.minute == 30

    def test_wildcard_date(self):
        date = BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
        time = BACnetTime(0, 0, 0, 0)
        request = TimeSynchronizationRequest(date=date, time=time)
        encoded = request.encode()
        decoded = TimeSynchronizationRequest.decode(encoded)
        assert decoded.date.year == 0xFF


class TestUTCTimeSynchronization:
    def test_round_trip(self):
        date = BACnetDate(2024, 1, 1, 1)
        time = BACnetTime(12, 0, 0, 0)
        request = UTCTimeSynchronizationRequest(date=date, time=time)
        encoded = request.encode()
        decoded = UTCTimeSynchronizationRequest.decode(encoded)
        assert decoded.date.year == 2024
        assert decoded.date.month == 1
        assert decoded.time.hour == 12
