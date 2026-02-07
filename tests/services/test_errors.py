from bac_py.services.errors import (
    BACnetAbortError,
    BACnetBaseError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)
from bac_py.types.enums import AbortReason, ErrorClass, ErrorCode, RejectReason


class TestBACnetError:
    def test_attributes(self):
        err = BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        assert err.error_class == ErrorClass.OBJECT
        assert err.error_code == ErrorCode.UNKNOWN_OBJECT
        assert err.error_data == b""

    def test_with_error_data(self):
        err = BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY, b"\x01\x02")
        assert err.error_data == b"\x01\x02"

    def test_is_bacnet_exception(self):
        err = BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        assert isinstance(err, BACnetBaseError)

    def test_str_contains_info(self):
        err = BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        assert "OBJECT" in str(err)
        assert "UNKNOWN_OBJECT" in str(err)


class TestBACnetRejectError:
    def test_attributes(self):
        err = BACnetRejectError(RejectReason.UNRECOGNIZED_SERVICE)
        assert err.reason == RejectReason.UNRECOGNIZED_SERVICE

    def test_is_bacnet_exception(self):
        err = BACnetRejectError(RejectReason.BUFFER_OVERFLOW)
        assert isinstance(err, BACnetBaseError)

    def test_str_contains_reason(self):
        err = BACnetRejectError(RejectReason.UNRECOGNIZED_SERVICE)
        assert "UNRECOGNIZED_SERVICE" in str(err)


class TestBACnetAbortError:
    def test_attributes(self):
        err = BACnetAbortError(AbortReason.OTHER)
        assert err.reason == AbortReason.OTHER

    def test_is_bacnet_exception(self):
        err = BACnetAbortError(AbortReason.BUFFER_OVERFLOW)
        assert isinstance(err, BACnetBaseError)

    def test_str_contains_reason(self):
        err = BACnetAbortError(AbortReason.OTHER)
        assert "OTHER" in str(err)


class TestBACnetTimeoutError:
    def test_is_bacnet_exception(self):
        err = BACnetTimeoutError("timed out")
        assert isinstance(err, BACnetBaseError)

    def test_message(self):
        err = BACnetTimeoutError("custom message")
        assert str(err) == "custom message"
