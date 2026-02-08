"""Tests for COV service encoding/decoding per ASHRAE 135-2016 Clause 13."""

from bac_py.encoding.primitives import encode_application_bit_string, encode_application_real
from bac_py.services.cov import (
    BACnetPropertyValue,
    COVNotificationRequest,
    SubscribeCOVRequest,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BitString, ObjectIdentifier


class TestSubscribeCOVRequest:
    """Tests for SubscribeCOV-Request encode/decode."""

    def test_round_trip_basic(self):
        """Full subscription with all fields."""
        req = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            issue_confirmed_notifications=True,
            lifetime=300,
        )
        encoded = req.encode()
        decoded = SubscribeCOVRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 42
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.monitored_object_identifier.instance_number == 1
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 300
        assert decoded.is_cancellation is False

    def test_round_trip_cancellation(self):
        """Cancellation: both optional fields omitted."""
        req = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        encoded = req.encode()
        decoded = SubscribeCOVRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 42
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.issue_confirmed_notifications is None
        assert decoded.lifetime is None
        assert decoded.is_cancellation is True

    def test_round_trip_unconfirmed(self):
        """Unconfirmed subscription with lifetime."""
        req = SubscribeCOVRequest(
            subscriber_process_identifier=7,
            monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
            issue_confirmed_notifications=False,
            lifetime=600,
        )
        encoded = req.encode()
        decoded = SubscribeCOVRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 7
        assert decoded.monitored_object_identifier.object_type == ObjectType.BINARY_INPUT
        assert decoded.monitored_object_identifier.instance_number == 5
        assert decoded.issue_confirmed_notifications is False
        assert decoded.lifetime == 600

    def test_round_trip_no_lifetime(self):
        """Confirmed notification with no lifetime (indefinite)."""
        req = SubscribeCOVRequest(
            subscriber_process_identifier=10,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 3),
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        encoded = req.encode()
        decoded = SubscribeCOVRequest.decode(encoded)

        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime is None
        assert decoded.is_cancellation is False

    def test_is_cancellation_property(self):
        """Verify is_cancellation logic."""
        # Both None = cancellation
        assert (
            SubscribeCOVRequest(
                subscriber_process_identifier=1,
                monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 0),
            ).is_cancellation
            is True
        )

        # Only one None = not cancellation
        assert (
            SubscribeCOVRequest(
                subscriber_process_identifier=1,
                monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 0),
                issue_confirmed_notifications=True,
            ).is_cancellation
            is False
        )

        assert (
            SubscribeCOVRequest(
                subscriber_process_identifier=1,
                monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 0),
                lifetime=300,
            ).is_cancellation
            is False
        )

    def test_large_process_id(self):
        """Process identifier up to 2^32-1."""
        req = SubscribeCOVRequest(
            subscriber_process_identifier=0xFFFFFFFF,
            monitored_object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            issue_confirmed_notifications=True,
            lifetime=3600,
        )
        encoded = req.encode()
        decoded = SubscribeCOVRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 0xFFFFFFFF


class TestBACnetPropertyValue:
    """Tests for BACnetPropertyValue encode/decode."""

    def test_round_trip_basic(self):
        """Property with value, no array index or priority."""
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_real(72.5),
        )
        encoded = pv.encode()
        decoded, _offset = BACnetPropertyValue.decode_from(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index is None
        assert decoded.value == encode_application_real(72.5)
        assert decoded.priority is None

    def test_round_trip_with_array_index(self):
        """Property with array index."""
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=3,
            value=encode_application_real(42.0),
        )
        encoded = pv.encode()
        decoded, _offset = BACnetPropertyValue.decode_from(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index == 3
        assert decoded.value == encode_application_real(42.0)

    def test_round_trip_with_priority(self):
        """Property with priority."""
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_real(50.0),
            priority=8,
        )
        encoded = pv.encode()
        decoded, _offset = BACnetPropertyValue.decode_from(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.priority == 8

    def test_round_trip_status_flags(self):
        """StatusFlags encoded as BitString."""
        # StatusFlags: in_alarm=False, fault=False, overridden=False, out_of_service=False
        status_flags = BitString(bytes([0x00]), unused_bits=4)
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.STATUS_FLAGS,
            value=encode_application_bit_string(status_flags),
        )
        encoded = pv.encode()
        decoded, _offset = BACnetPropertyValue.decode_from(encoded)

        assert decoded.property_identifier == PropertyIdentifier.STATUS_FLAGS
        assert decoded.value == encode_application_bit_string(status_flags)

    def test_round_trip_with_all_fields(self):
        """Property with all fields set."""
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=1,
            value=encode_application_real(99.9),
            priority=16,
        )
        encoded = pv.encode()
        decoded, _offset = BACnetPropertyValue.decode_from(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index == 1
        assert decoded.priority == 16

    def test_multiple_sequential_decode(self):
        """Decode multiple BACnetPropertyValues sequentially."""
        pv1 = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_real(72.5),
        )
        pv2 = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.STATUS_FLAGS,
            value=encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4)),
        )
        combined = pv1.encode() + pv2.encode()

        decoded1, offset = BACnetPropertyValue.decode_from(combined, 0)
        decoded2, _offset = BACnetPropertyValue.decode_from(combined, offset)

        assert decoded1.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded2.property_identifier == PropertyIdentifier.STATUS_FLAGS


class TestCOVNotificationRequest:
    """Tests for COVNotification-Request encode/decode."""

    def test_round_trip_basic(self):
        """Full notification with two property values."""
        present_value_bytes = encode_application_real(72.5)
        status_flags_bytes = encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4))

        notification = COVNotificationRequest(
            subscriber_process_identifier=42,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=present_value_bytes,
                ),
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.STATUS_FLAGS,
                    value=status_flags_bytes,
                ),
            ],
        )

        encoded = notification.encode()
        decoded = COVNotificationRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 42
        assert decoded.initiating_device_identifier.object_type == ObjectType.DEVICE
        assert decoded.initiating_device_identifier.instance_number == 100
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.monitored_object_identifier.instance_number == 1
        assert decoded.time_remaining == 300
        assert len(decoded.list_of_values) == 2
        assert decoded.list_of_values[0].property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.list_of_values[0].value == present_value_bytes
        assert decoded.list_of_values[1].property_identifier == PropertyIdentifier.STATUS_FLAGS
        assert decoded.list_of_values[1].value == status_flags_bytes

    def test_round_trip_single_value(self):
        """Notification with a single property value."""
        notification = COVNotificationRequest(
            subscriber_process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
            monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 3),
            time_remaining=0,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=b"\x91\x01",  # application-tagged enumerated 1 (active)
                ),
            ],
        )

        encoded = notification.encode()
        decoded = COVNotificationRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 1
        assert decoded.time_remaining == 0
        assert len(decoded.list_of_values) == 1
        assert decoded.list_of_values[0].value == b"\x91\x01"

    def test_round_trip_zero_time_remaining(self):
        """Notification with time_remaining=0 (indefinite subscription)."""
        notification = COVNotificationRequest(
            subscriber_process_identifier=99,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
            time_remaining=0,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=encode_application_real(0.0),
                ),
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.STATUS_FLAGS,
                    value=encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4)),
                ),
            ],
        )

        encoded = notification.encode()
        decoded = COVNotificationRequest.decode(encoded)

        assert decoded.time_remaining == 0
        assert len(decoded.list_of_values) == 2

    def test_round_trip_binary_object(self):
        """COV notification for a binary object."""
        notification = COVNotificationRequest(
            subscriber_process_identifier=5,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_OUTPUT, 7),
            time_remaining=120,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=b"\x91\x00",  # enumerated 0 (inactive)
                ),
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.STATUS_FLAGS,
                    value=encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4)),
                ),
            ],
        )

        encoded = notification.encode()
        decoded = COVNotificationRequest.decode(encoded)

        assert decoded.monitored_object_identifier.object_type == ObjectType.BINARY_OUTPUT
        assert len(decoded.list_of_values) == 2
        assert decoded.list_of_values[0].value == b"\x91\x00"
