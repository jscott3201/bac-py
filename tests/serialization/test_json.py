"""Tests for JSON serialization module."""

from __future__ import annotations

import json

import pytest

from bac_py.serialization import Serializer, deserialize, get_serializer, serialize
from bac_py.serialization.json import JsonSerializer
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import (
    BACnetDate,
    BACnetTime,
    BitString,
    ObjectIdentifier,
)


class TestJsonSerializerRoundTrip:
    def test_encode_decode_plain_dict(self):
        s = JsonSerializer()
        data = {"name": "device-1", "value": 42, "active": True}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == data

    def test_encode_decode_nested_dict(self):
        s = JsonSerializer()
        data = {"outer": {"inner": [1, 2, 3]}, "flag": False}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == data


class TestJsonSerializerOptions:
    def test_pretty_produces_indented_output(self):
        s = JsonSerializer(pretty=True)
        data = {"a": 1}
        encoded = s.encode(data)
        text = encoded.decode("utf-8")
        assert "\n" in text
        assert "  " in text

    def test_sort_keys_produces_sorted_keys(self):
        s = JsonSerializer(sort_keys=True)
        data = {"z": 1, "a": 2, "m": 3}
        encoded = s.encode(data)
        text = encoded.decode("utf-8")
        keys = list(json.loads(text).keys())
        assert keys == sorted(keys)


class TestJsonSerializerDefault:
    def test_handles_object_with_to_dict(self):
        class Dummy:
            def to_dict(self):
                return {"key": "value"}

        s = JsonSerializer()
        data = {"obj": Dummy()}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == {"obj": {"key": "value"}}

    def test_handles_bytes_as_hex(self):
        s = JsonSerializer()
        data = {"raw": b"\xde\xad\xbe\xef"}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == {"raw": "deadbeef"}

    def test_default_raises_type_error_for_unknown_types(self):
        s = JsonSerializer()
        with pytest.raises(TypeError, match="Cannot serialize"):
            s._default(object())

    def test_encode_raises_type_error_for_unknown_types(self):
        s = JsonSerializer()
        data = {"bad": object()}
        with pytest.raises(TypeError):
            s.encode(data)


class TestConvenienceFunctions:
    def test_serialize_plain_dict(self):
        data = {"x": 10}
        raw = serialize(data)
        result = deserialize(raw)
        assert result == data

    def test_serialize_object_with_to_dict(self):
        oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        raw = serialize(oid)
        result = deserialize(raw)
        assert result == {"object_type": "device", "instance": 100}

    def test_serialize_passes_kwargs(self):
        data = {"z": 1, "a": 2}
        raw = serialize(data, sort_keys=True)
        text = raw.decode("utf-8")
        keys = list(json.loads(text).keys())
        assert keys == sorted(keys)


class TestGetSerializer:
    def test_json_returns_json_serializer(self):
        s = get_serializer("json")
        assert isinstance(s, JsonSerializer)

    def test_unknown_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported serialization format"):
            get_serializer("unknown")


class TestSerializerProtocol:
    def test_runtime_checkable(self):
        s = JsonSerializer()
        assert isinstance(s, Serializer)


class TestBACnetPrimitiveRoundTrips:
    def test_object_identifier_round_trip(self):
        original = ObjectIdentifier(ObjectType.ANALOG_INPUT, 7)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = ObjectIdentifier.from_dict(recovered_dict)
        assert restored == original

    def test_bacnet_date_with_wildcards(self):
        original = BACnetDate(year=0xFF, month=12, day=25, day_of_week=0xFF)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = BACnetDate.from_dict(recovered_dict)
        assert restored == original
        assert recovered_dict["year"] is None
        assert recovered_dict["day_of_week"] is None
        assert recovered_dict["month"] == 12

    def test_bacnet_time_round_trip(self):
        original = BACnetTime(hour=14, minute=30, second=0, hundredth=50)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = BACnetTime.from_dict(recovered_dict)
        assert restored == original

    def test_bitstring_round_trip(self):
        original = BitString(b"\xa4", unused_bits=2)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = BitString.from_dict(recovered_dict)
        assert restored == original


class TestContentType:
    def test_content_type_returns_application_json(self):
        s = JsonSerializer()
        assert s.content_type == "application/json"
