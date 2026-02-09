"""Tests for property-aware smart encoding (_encode_for_write with type hints)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.app.client import BACnetClient
from bac_py.encoding.primitives import (
    decode_real,
    decode_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestPropertyTypeHints:
    """Test that _encode_for_write uses _PROPERTY_TYPE_HINTS for non-PV properties."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock(return_value=b"")
        return app

    def _get_encoded_value(self, app):
        """Extract the property_value bytes from the WritePropertyRequest."""
        from bac_py.services.write_property import WritePropertyRequest

        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        req = WritePropertyRequest.decode(service_data)
        return req.property_value

    def test_int_to_units_encodes_as_enumerated(self):
        """Units property expects Enumerated; writing int 62 should encode as Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "units", 62)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 9  # Enumerated
            assert tag.cls == TagClass.APPLICATION
            assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 62

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_reliability_encodes_as_enumerated(self):
        """Reliability expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "reliability", 0)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 9  # Enumerated

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_event_state_encodes_as_enumerated(self):
        """Event-state expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "event-state", 0)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 9  # Enumerated

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_cov_increment_encodes_as_real(self):
        """COV-increment expects Real; writing int 5 should encode as Real 5.0."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "cov-inc", 5)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real
            assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(5.0)

        asyncio.get_event_loop().run_until_complete(run())

    def test_float_to_cov_increment_encodes_as_real(self):
        """COV-increment expects Real; writing float 0.5 should encode as Real."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "cov-inc", 0.5)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real
            assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(0.5)

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_high_limit_encodes_as_real(self):
        """High-limit expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "high-limit", 100)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real
            assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(100.0)

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_low_limit_encodes_as_real(self):
        """Low-limit expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "low-limit", 0)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real
            assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(0.0)

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_deadband_encodes_as_real(self):
        """Deadband expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "deadband", 2)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_relinquish_default_encodes_as_real(self):
        """Relinquish-default expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "av,1", "relinquish-default", 72)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_number_of_states_encodes_as_unsigned(self):
        """Number-of-states expects Unsigned."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "msv,1", "number-of-states", 5)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 2  # Unsigned
            assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 5

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_notification_class_encodes_as_unsigned(self):
        """Notification-class expects Unsigned."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "notification-class", 10)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 2  # Unsigned
            assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 10

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_out_of_service_encodes_as_boolean(self):
        """Out-of-service expects Boolean; writing int 1 should encode as Boolean."""
        app = self._make_app()
        client = BACnetClient(app)

        # Test _encode_for_write directly since Boolean tag encoding
        # (value in tag bits, no content bytes) doesn't round-trip
        # through WritePropertyRequest.decode.
        encoded = client._encode_for_write(
            1,
            PropertyIdentifier.OUT_OF_SERVICE,
            ObjectType.ANALOG_INPUT,
        )
        tag, _ = decode_tag(encoded, 0)
        assert tag.number == 1  # Boolean

    def test_int_to_polarity_encodes_as_enumerated(self):
        """Polarity expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "bi,1", "polarity", 1)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 9  # Enumerated

        asyncio.get_event_loop().run_until_complete(run())

    def test_string_to_hinted_string_property_still_works(self):
        """String values should still pass through to encode_property_value for string props."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "desc", "Zone Temperature")
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 7  # Character String

        asyncio.get_event_loop().run_until_complete(run())

    def test_pv_encoding_takes_priority_over_hints(self):
        """PV encoding (object-type-aware) should take priority for present-value."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            # Writing int to binary PV should encode as Enumerated (not via hint map)
            await client.write("192.168.1.100", "bv,1", "pv", 1)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 9  # Enumerated (from PV logic, not hint map)

        asyncio.get_event_loop().run_until_complete(run())

    def test_unknown_property_falls_through(self):
        """Properties not in the hint map should fall through to encode_property_value."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            # protocol-version is not in the hints map
            await client.write("192.168.1.100", "dev,100", "protocol-version", 42)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            # Falls through to encode_property_value which encodes int as Unsigned
            assert tag.number == 2  # Unsigned
            assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 42

        asyncio.get_event_loop().run_until_complete(run())

    def test_float_to_hinted_real_property(self):
        """Float value to a Real-hinted property should encode as Real."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ai,1", "resolution", 0.1)
            value_bytes = self._get_encoded_value(app)
            tag, offset = decode_tag(value_bytes, 0)
            assert tag.number == 4  # Real
            assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(0.1)

        asyncio.get_event_loop().run_until_complete(run())

    def test_int_to_feedback_value_encodes_as_enumerated(self):
        """Feedback-value expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "bo,1", "feedback-value", 1)
            value_bytes = self._get_encoded_value(app)
            tag, _ = decode_tag(value_bytes, 0)
            assert tag.number == 9  # Enumerated

        asyncio.get_event_loop().run_until_complete(run())
