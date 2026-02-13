"""Tests for Who-Has and I-Have services."""

from bac_py.services.who_has import IHaveRequest, WhoHasRequest
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestWhoHasRequest:
    def test_by_object_id_no_limits(self):
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        request = WhoHasRequest(object_identifier=obj_id)
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier == obj_id
        assert decoded.object_name is None
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_by_object_name_no_limits(self):
        request = WhoHasRequest(object_name="Temperature-Sensor")
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier is None
        assert decoded.object_name == "Temperature-Sensor"
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_by_object_id_with_limits(self):
        obj_id = ObjectIdentifier(ObjectType.BINARY_INPUT, 5)
        request = WhoHasRequest(
            object_identifier=obj_id,
            low_limit=100,
            high_limit=500,
        )
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier == obj_id
        assert decoded.low_limit == 100
        assert decoded.high_limit == 500

    def test_by_object_name_with_limits(self):
        request = WhoHasRequest(
            object_name="Room-Temp",
            low_limit=0,
            high_limit=4194303,
        )
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_name == "Room-Temp"
        assert decoded.low_limit == 0
        assert decoded.high_limit == 4194303


class TestIHaveRequest:
    def test_round_trip(self):
        request = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1234),
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
            object_name="Temperature",
        )
        encoded = request.encode()
        decoded = IHaveRequest.decode(encoded)
        assert decoded.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 1234)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        assert decoded.object_name == "Temperature"

    def test_different_object_types(self):
        request = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 99),
            object_name="Alarm-Input",
        )
        encoded = request.encode()
        decoded = IHaveRequest.decode(encoded)
        assert decoded.object_identifier.object_type == ObjectType.BINARY_INPUT
        assert decoded.object_identifier.instance_number == 99


# ---------------------------------------------------------------------------
# Coverage: who_has.py lines 54-55, 70->72, 95->101, 106->109
# ---------------------------------------------------------------------------


class TestWhoHasRequestValidation:
    """Lines 54-55: __post_init__ validation."""

    def test_both_set_raises(self):
        """Lines 53-55: both object_identifier and object_name raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Exactly one"):
            WhoHasRequest(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                object_name="Test",
            )

    def test_neither_set_raises(self):
        """Lines 53-55: neither object_identifier nor object_name raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Exactly one"):
            WhoHasRequest()


class TestWhoHasRequestDecodeBranches:
    """Lines 70->72, 95->101, 106->109: decode branches for limits and CHOICE."""

    def test_decode_object_name_with_limits(self):
        """Lines 95-98, 106-107: decode with limits + object_name (tag 3)."""
        request = WhoHasRequest(
            object_name="Sensor-1",
            low_limit=10,
            high_limit=500,
        )
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_name == "Sensor-1"
        assert decoded.low_limit == 10
        assert decoded.high_limit == 500
        assert decoded.object_identifier is None

    def test_decode_object_id_no_limits(self):
        """Lines 91-93, 101-105: decode with objectIdentifier (tag 2) and no limits."""
        request = WhoHasRequest(
            object_identifier=ObjectIdentifier(ObjectType.MULTI_STATE_INPUT, 42),
        )
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.MULTI_STATE_INPUT, 42)
        assert decoded.low_limit is None
        assert decoded.high_limit is None


# ---------------------------------------------------------------------------
# Coverage: who_has.py branch partials 70->72, 95->101, 106->109
# ---------------------------------------------------------------------------


class TestWhoHasRequestEncodeBranches:
    """Branch 70->72: CHOICE encoding in WhoHasRequest.encode.

    Tests the elif branch (line 70) where object_name is used instead of
    object_identifier for encoding.
    """

    def test_encode_object_name_choice(self):
        """Encode with object_name (elif branch at line 70)."""
        request = WhoHasRequest(object_name="MyObject")
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_name == "MyObject"
        assert decoded.object_identifier is None


class TestWhoHasRequestDecodeLimitsBranch:
    """Branch 95->101: high_limit tag check fallthrough in WhoHasRequest.decode.

    When low_limit (tag 0) is present but the next tag is NOT tag 1
    (high_limit), the code falls through directly to the CHOICE parsing.
    """

    def test_low_limit_only_then_object_id(self):
        """Low limit present but no high limit -- falls through to CHOICE.

        Manually construct: [0] low_limit, [2] objectIdentifier (no [1]).
        """
        from bac_py.encoding.primitives import (
            encode_context_object_id,
            encode_context_tagged,
            encode_unsigned,
        )

        buf = bytearray()
        # [0] low_limit = 100
        buf.extend(encode_context_tagged(0, encode_unsigned(100)))
        # [2] objectIdentifier (skipping [1] high_limit)
        buf.extend(encode_context_object_id(2, ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)))

        decoded = WhoHasRequest.decode(bytes(buf))
        # low_limit was read but high_limit was not, so both remain as decoded
        assert decoded.low_limit == 100
        # high_limit is None because tag 1 was never found
        assert decoded.high_limit is None
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)


class TestWhoHasRequestDecodeUnknownChoiceTag:
    """Branch 106->109: unknown CHOICE tag in WhoHasRequest.decode.

    When the CHOICE tag is neither [2] nor [3], both conditions fail and
    the code falls through to the return, triggering __post_init__ validation.
    """

    def test_unknown_choice_tag_raises(self):
        """CHOICE tag with unexpected number (neither 2 nor 3) raises ValueError."""
        import pytest

        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        buf = bytearray()
        # Context tag 5 (not 0, 1, 2, or 3)
        buf.extend(encode_context_tagged(5, encode_unsigned(42)))

        # Decoding with an unknown CHOICE tag results in neither field set,
        # which __post_init__ rejects.
        with pytest.raises(ValueError, match="Exactly one"):
            WhoHasRequest.decode(bytes(buf))
