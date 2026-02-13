"""Tests for parse_object_identifier and parse_property_identifier."""

import pytest

from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.parsing import (
    OBJECT_TYPE_ALIASES,
    PROPERTY_ALIASES,
    parse_object_identifier,
    parse_property_identifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestParseObjectIdentifier:
    # --- String formats ---

    def test_hyphenated_comma(self):
        result = parse_object_identifier("analog-input,1")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_hyphenated_colon(self):
        result = parse_object_identifier("analog-input:1")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_underscore_comma(self):
        result = parse_object_identifier("analog_input,1")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_alias_ai(self):
        result = parse_object_identifier("ai,1")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_alias_ao(self):
        result = parse_object_identifier("ao,2")
        assert result == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2)

    def test_alias_av(self):
        result = parse_object_identifier("av,3")
        assert result == ObjectIdentifier(ObjectType.ANALOG_VALUE, 3)

    def test_alias_bi(self):
        result = parse_object_identifier("bi,1")
        assert result == ObjectIdentifier(ObjectType.BINARY_INPUT, 1)

    def test_alias_bo(self):
        result = parse_object_identifier("bo,1")
        assert result == ObjectIdentifier(ObjectType.BINARY_OUTPUT, 1)

    def test_alias_bv(self):
        result = parse_object_identifier("bv,1")
        assert result == ObjectIdentifier(ObjectType.BINARY_VALUE, 1)

    def test_alias_msi(self):
        result = parse_object_identifier("msi,1")
        assert result == ObjectIdentifier(ObjectType.MULTI_STATE_INPUT, 1)

    def test_alias_mso(self):
        result = parse_object_identifier("mso,1")
        assert result == ObjectIdentifier(ObjectType.MULTI_STATE_OUTPUT, 1)

    def test_alias_msv(self):
        result = parse_object_identifier("msv,1")
        assert result == ObjectIdentifier(ObjectType.MULTI_STATE_VALUE, 1)

    def test_alias_dev(self):
        result = parse_object_identifier("dev,100")
        assert result == ObjectIdentifier(ObjectType.DEVICE, 100)

    def test_case_insensitive(self):
        result = parse_object_identifier("ANALOG-INPUT,1")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_mixed_case(self):
        result = parse_object_identifier("Analog-Input,1")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_alias_case_insensitive(self):
        result = parse_object_identifier("AI,5")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 5)

    def test_whitespace_stripped(self):
        result = parse_object_identifier(" ai , 1 ")
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    # --- Tuple formats ---

    def test_tuple_string_int(self):
        result = parse_object_identifier(("analog-input", 1))
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_tuple_alias_int(self):
        result = parse_object_identifier(("ai", 1))
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_tuple_objecttype_int(self):
        result = parse_object_identifier((ObjectType.ANALOG_INPUT, 1))
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_tuple_int_int(self):
        result = parse_object_identifier((0, 1))
        assert result == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    # --- Pass-through ---

    def test_passthrough(self):
        obj_id = ObjectIdentifier(ObjectType.DEVICE, 100)
        result = parse_object_identifier(obj_id)
        assert result is obj_id

    # --- Error cases ---

    def test_no_separator_raises(self):
        with pytest.raises(ValueError, match="Cannot parse object identifier"):
            parse_object_identifier("analog-input")

    def test_invalid_instance_raises(self):
        with pytest.raises(ValueError, match="Invalid instance number"):
            parse_object_identifier("ai,abc")

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown object type"):
            parse_object_identifier("nonexistent,1")

    def test_wrong_tuple_length_raises(self):
        with pytest.raises(ValueError, match="must have 2 elements"):
            parse_object_identifier(("ai", 1, 2))

    # --- All aliases exist ---

    def test_all_aliases_resolve(self):
        for alias, expected_type in OBJECT_TYPE_ALIASES.items():
            result = parse_object_identifier(f"{alias},1")
            assert result.object_type == expected_type


class TestParsePropertyIdentifier:
    # --- String formats ---

    def test_hyphenated(self):
        result = parse_property_identifier("present-value")
        assert result == PropertyIdentifier.PRESENT_VALUE

    def test_underscore(self):
        result = parse_property_identifier("present_value")
        assert result == PropertyIdentifier.PRESENT_VALUE

    def test_alias_pv(self):
        result = parse_property_identifier("pv")
        assert result == PropertyIdentifier.PRESENT_VALUE

    def test_alias_name(self):
        result = parse_property_identifier("name")
        assert result == PropertyIdentifier.OBJECT_NAME

    def test_alias_desc(self):
        result = parse_property_identifier("desc")
        assert result == PropertyIdentifier.DESCRIPTION

    def test_alias_units(self):
        result = parse_property_identifier("units")
        assert result == PropertyIdentifier.UNITS

    def test_alias_status(self):
        result = parse_property_identifier("status")
        assert result == PropertyIdentifier.STATUS_FLAGS

    def test_alias_oos(self):
        result = parse_property_identifier("oos")
        assert result == PropertyIdentifier.OUT_OF_SERVICE

    def test_case_insensitive(self):
        result = parse_property_identifier("PRESENT-VALUE")
        assert result == PropertyIdentifier.PRESENT_VALUE

    def test_mixed_case(self):
        result = parse_property_identifier("Present-Value")
        assert result == PropertyIdentifier.PRESENT_VALUE

    # --- Integer ---

    def test_integer_value(self):
        result = parse_property_identifier(85)
        assert result == PropertyIdentifier.PRESENT_VALUE

    # --- Pass-through ---

    def test_passthrough(self):
        prop = PropertyIdentifier.PRESENT_VALUE
        result = parse_property_identifier(prop)
        assert result is prop

    # --- Error cases ---

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown property identifier"):
            parse_property_identifier("nonexistent-property")

    # --- All aliases exist ---

    def test_all_aliases_resolve(self):
        for alias, expected_prop in PROPERTY_ALIASES.items():
            result = parse_property_identifier(alias)
            assert result == expected_prop


# ---------------------------------------------------------------------------
# Coverage gap tests for error branches
# ---------------------------------------------------------------------------


class TestParseObjectIdentifierTypeErrors:
    def test_invalid_input_type_raises(self):
        """parse_object_identifier with invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse object identifier from"):
            parse_object_identifier(12345)  # type: ignore[arg-type]

    def test_tuple_with_invalid_type_part_raises(self):
        """parse_object_identifier tuple with non-str/int/ObjectType type_part raises."""
        with pytest.raises(ValueError, match="Cannot parse object type from"):
            parse_object_identifier((3.14, 1))  # type: ignore[arg-type]


class TestParsePropertyIdentifierTypeErrors:
    def test_invalid_input_type_raises(self):
        """parse_property_identifier with invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse property identifier from"):
            parse_property_identifier([1, 2, 3])  # type: ignore[arg-type]

    def test_none_input_raises(self):
        """parse_property_identifier with None raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse property identifier from"):
            parse_property_identifier(None)  # type: ignore[arg-type]
