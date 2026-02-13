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


# ---------------------------------------------------------------------------
# Coverage: device_mgmt.py lines 84, 95, 154
# ---------------------------------------------------------------------------


class TestDeviceCommunicationControlPassword:
    """Line 84: time_duration > 65535 raises BACnetRejectError."""

    def test_time_duration_overflow_raises(self):
        import pytest

        # Build request with time_duration > 65535 manually
        from bac_py.encoding.primitives import (
            encode_context_tagged,
            encode_enumerated,
            encode_unsigned,
        )
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        # [0] timeDuration = 70000 (> 65535)
        buf.extend(encode_context_tagged(0, encode_unsigned(70000)))
        # [1] enable-disable = DISABLE (1)
        buf.extend(encode_context_tagged(1, encode_enumerated(EnableDisable.DISABLE)))
        with pytest.raises(BACnetRejectError):
            DeviceCommunicationControlRequest.decode(bytes(buf))

    def test_password_out_of_range_raises(self):
        """Line 95: password length > 20 raises BACnetRejectError."""
        import pytest

        from bac_py.encoding.primitives import (
            encode_character_string,
            encode_context_tagged,
            encode_enumerated,
        )
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        # [1] enable-disable = ENABLE (0)
        buf.extend(encode_context_tagged(1, encode_enumerated(EnableDisable.ENABLE)))
        # [2] password = "a" * 25 (> 20 chars)
        buf.extend(encode_context_tagged(2, encode_character_string("a" * 25)))
        with pytest.raises(BACnetRejectError):
            DeviceCommunicationControlRequest.decode(bytes(buf))


class TestTimeSynchronizationFields:
    """Line 95 in TimeSynchronizationRequest: decode date/time fields."""

    def test_round_trip_midnight(self):
        """Verify midnight time round-trips correctly."""
        date = BACnetDate(2025, 12, 31, 3)
        time = BACnetTime(0, 0, 0, 0)
        request = TimeSynchronizationRequest(date=date, time=time)
        encoded = request.encode()
        decoded = TimeSynchronizationRequest.decode(encoded)
        assert decoded.date.year == 2025
        assert decoded.date.month == 12
        assert decoded.date.day == 31
        assert decoded.time.hour == 0
        assert decoded.time.minute == 0


class TestReinitializeDevicePasswordOutOfRange:
    """Line 154: password length > 20 raises BACnetRejectError."""

    def test_password_too_long_raises(self):
        import pytest

        from bac_py.encoding.primitives import (
            encode_character_string,
            encode_context_tagged,
            encode_enumerated,
        )
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        # [0] reinitializedStateOfDevice = COLDSTART (0)
        buf.extend(encode_context_tagged(0, encode_enumerated(ReinitializedState.COLDSTART)))
        # [1] password = "a" * 25 (> 20 chars)
        buf.extend(encode_context_tagged(1, encode_character_string("a" * 25)))
        with pytest.raises(BACnetRejectError):
            ReinitializeDeviceRequest.decode(bytes(buf))
