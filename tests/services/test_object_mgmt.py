"""Tests for object management services."""

from bac_py.encoding.primitives import encode_application_real
from bac_py.services.common import BACnetPropertyValue
from bac_py.services.object_mgmt import CreateObjectRequest, DeleteObjectRequest
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestCreateObjectRequest:
    def test_create_with_type_only(self):
        request = CreateObjectRequest(object_type=ObjectType.ANALOG_VALUE)
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type == ObjectType.ANALOG_VALUE
        assert decoded.object_identifier is None
        assert decoded.list_of_initial_values is None

    def test_create_with_object_identifier(self):
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 42)
        request = CreateObjectRequest(object_identifier=obj_id)
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type is None
        assert decoded.object_identifier == obj_id

    def test_create_with_initial_values(self):
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_real(25.5),
        )
        request = CreateObjectRequest(
            object_type=ObjectType.ANALOG_VALUE,
            list_of_initial_values=[pv],
        )
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type == ObjectType.ANALOG_VALUE
        assert decoded.list_of_initial_values is not None
        assert len(decoded.list_of_initial_values) == 1
        assert decoded.list_of_initial_values[0].property_identifier == (
            PropertyIdentifier.PRESENT_VALUE
        )

    def test_create_with_multiple_initial_values(self):
        pvs = [
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                value=encode_application_real(10.0),
            ),
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier.OBJECT_NAME,
                value=b"\x75\x05\x00test",
            ),
        ]
        request = CreateObjectRequest(
            object_type=ObjectType.ANALOG_VALUE,
            list_of_initial_values=pvs,
        )
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert len(decoded.list_of_initial_values) == 2


class TestDeleteObjectRequest:
    def test_round_trip(self):
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        request = DeleteObjectRequest(object_identifier=obj_id)
        encoded = request.encode()
        decoded = DeleteObjectRequest.decode(encoded)
        assert decoded.object_identifier == obj_id

    def test_different_types(self):
        for obj_type in [ObjectType.BINARY_VALUE, ObjectType.MULTI_STATE_VALUE, ObjectType.FILE]:
            obj_id = ObjectIdentifier(obj_type, 99)
            request = DeleteObjectRequest(object_identifier=obj_id)
            encoded = request.encode()
            decoded = DeleteObjectRequest.decode(encoded)
            assert decoded.object_identifier == obj_id


# ---------------------------------------------------------------------------
# Coverage: lines 85-86, 104-105, 59->61 in CreateObjectRequest
# ---------------------------------------------------------------------------


class TestCreateObjectRequestDecode:
    def test_decode_with_object_type(self):
        """Lines 85-86, 93-95: decode objectSpecifier with objectType (tag 0)."""
        request = CreateObjectRequest(object_type=ObjectType.BINARY_INPUT)
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type == ObjectType.BINARY_INPUT
        assert decoded.object_identifier is None

    def test_decode_with_initial_values(self):
        """Lines 104-105, 114-123: decode with listOfInitialValues present."""
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.DESCRIPTION,
            value=b"\x75\x06\x00hello",
        )
        request = CreateObjectRequest(
            object_type=ObjectType.ANALOG_INPUT,
            list_of_initial_values=[pv],
        )
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type == ObjectType.ANALOG_INPUT
        assert decoded.list_of_initial_values is not None
        assert len(decoded.list_of_initial_values) == 1

    def test_decode_with_object_identifier_and_initial_values(self):
        """Lines 96-102: decode objectSpecifier with objectIdentifier (tag 1)."""
        obj_id = ObjectIdentifier(ObjectType.BINARY_VALUE, 10)
        pv1 = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=b"\x91\x01",
        )
        pv2 = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            value=b"\x75\x05\x00test",
        )
        request = CreateObjectRequest(
            object_identifier=obj_id,
            list_of_initial_values=[pv1, pv2],
        )
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_identifier == obj_id
        assert decoded.object_type is None
        assert len(decoded.list_of_initial_values) == 2

    def test_encode_with_no_specifier(self):
        """Line 59->61: encode with neither objectType nor objectIdentifier."""
        request = CreateObjectRequest()
        encoded = request.encode()
        # Should encode opening tag 0 and closing tag 0 with nothing inside
        assert len(encoded) > 0

    def test_decode_unexpected_tag_raises(self):
        """Lines 103-105: unexpected tag in objectSpecifier CHOICE raises ValueError."""
        import pytest

        # Build malformed data: opening tag 0, then context tag 5 (invalid), closing tag 0
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        buf.extend(encode_opening_tag(0))
        buf.extend(encode_context_tagged(5, encode_unsigned(1)))
        buf.extend(encode_closing_tag(0))
        with pytest.raises(ValueError, match="Unexpected tag"):
            CreateObjectRequest.decode(bytes(buf))

    def test_decode_wrong_opening_tag_number_raises(self):
        """Lines 85-86: opening tag with wrong number raises ValueError."""
        import pytest

        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # Use opening tag 1 instead of expected opening tag 0
        buf.extend(encode_opening_tag(1))
        buf.extend(encode_context_tagged(0, encode_unsigned(0)))
        buf.extend(encode_closing_tag(1))
        with pytest.raises(ValueError, match="Expected opening tag 0"):
            CreateObjectRequest.decode(bytes(buf))


# ---------------------------------------------------------------------------
# Coverage: object_mgmt.py branch partials 114->125, 117->125
# ---------------------------------------------------------------------------


class TestCreateObjectRequestNoInitialValues:
    """Branches 114->125 and 117->125: optional listOfInitialValues in CreateObject.

    Branch 114->125 covers tag not matching opening tag 1. Branch 117->125
    covers the inner while loop exiting at the closing tag.
    """

    def test_trailing_non_matching_tag_after_specifier(self):
        """Data has extra bytes after objectSpecifier closing tag but not tag 1.

        Exercises branch 114->125: tag.is_opening and tag.number == 1 is False.
        """
        from bac_py.encoding.primitives import (
            encode_context_tagged,
            encode_enumerated,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] objectSpecifier with objectType
        buf.extend(encode_opening_tag(0))
        buf.extend(encode_context_tagged(0, encode_enumerated(ObjectType.ANALOG_VALUE)))
        buf.extend(encode_closing_tag(0))
        # Append a context tag with number 5 (not opening tag 1)
        buf.extend(encode_context_tagged(5, encode_unsigned(42)))

        decoded = CreateObjectRequest.decode(bytes(buf))
        assert decoded.object_type == ObjectType.ANALOG_VALUE
        assert decoded.list_of_initial_values is None

    def test_create_with_empty_initial_values_list(self):
        """Empty listOfInitialValues: inner while loop immediately breaks.

        Exercises branch 117->125: while loop exits via break at closing tag.
        """
        from bac_py.encoding.primitives import encode_context_tagged, encode_enumerated
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] objectSpecifier with objectType
        buf.extend(encode_opening_tag(0))
        buf.extend(encode_context_tagged(0, encode_enumerated(ObjectType.BINARY_INPUT)))
        buf.extend(encode_closing_tag(0))
        # [1] empty listOfInitialValues
        buf.extend(encode_opening_tag(1))
        buf.extend(encode_closing_tag(1))

        decoded = CreateObjectRequest.decode(bytes(buf))
        assert decoded.object_type == ObjectType.BINARY_INPUT
        assert decoded.list_of_initial_values is not None
        assert len(decoded.list_of_initial_values) == 0
