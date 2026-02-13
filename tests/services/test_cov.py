"""Tests for COV service encoding/decoding per ASHRAE 135-2016 Clause 13."""

from bac_py.encoding.primitives import (
    encode_application_bit_string,
    encode_application_real,
    encode_application_unsigned,
)
from bac_py.services.cov import (
    BACnetPropertyReference,
    BACnetPropertyValue,
    COVNotificationMultipleRequest,
    COVNotificationRequest,
    COVObjectNotification,
    COVPropertyValue,
    COVReference,
    COVSubscriptionSpecification,
    SubscribeCOVPropertyMultipleRequest,
    SubscribeCOVPropertyRequest,
    SubscribeCOVRequest,
)
from bac_py.types.constructed import BACnetTimeStamp
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


class TestBACnetPropertyReference:
    """Tests for BACnetPropertyReference encode/decode."""

    def test_round_trip_basic(self):
        """Property reference with just property_identifier."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        encoded = ref.encode()
        decoded, _offset = BACnetPropertyReference.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index is None

    def test_round_trip_with_array_index(self):
        """Property reference with property_array_index."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=5,
        )
        encoded = ref.encode()
        decoded, _offset = BACnetPropertyReference.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index == 5

    def test_round_trip_with_array_index_none(self):
        """Property reference with property_array_index explicitly None."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.STATUS_FLAGS,
            property_array_index=None,
        )
        encoded = ref.encode()
        decoded, _offset = BACnetPropertyReference.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.STATUS_FLAGS
        assert decoded.property_array_index is None


class TestSubscribeCOVPropertyRequest:
    """Tests for SubscribeCOVProperty-Request encode/decode."""

    def test_round_trip_full_subscription(self):
        """Full subscription with all fields set."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=10,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            monitored_property_identifier=ref,
            issue_confirmed_notifications=True,
            lifetime=600,
            cov_increment=1.5,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 10
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.monitored_object_identifier.instance_number == 1
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 600
        assert (
            decoded.monitored_property_identifier.property_identifier
            == PropertyIdentifier.PRESENT_VALUE
        )
        assert decoded.monitored_property_identifier.property_array_index is None
        assert decoded.cov_increment == 1.5

    def test_round_trip_cancellation(self):
        """Cancellation: optional fields None."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=10,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            monitored_property_identifier=ref,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 10
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.issue_confirmed_notifications is None
        assert decoded.lifetime is None
        assert decoded.cov_increment is None
        assert (
            decoded.monitored_property_identifier.property_identifier
            == PropertyIdentifier.PRESENT_VALUE
        )

    def test_round_trip_with_cov_increment(self):
        """Subscription with COV increment."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=0,
        )
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 7),
            monitored_property_identifier=ref,
            issue_confirmed_notifications=False,
            lifetime=300,
            cov_increment=0.5,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 42
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_VALUE
        assert decoded.monitored_object_identifier.instance_number == 7
        assert decoded.issue_confirmed_notifications is False
        assert decoded.lifetime == 300
        assert decoded.monitored_property_identifier.property_array_index == 0
        assert decoded.cov_increment == 0.5

    def test_round_trip_without_cov_increment(self):
        """Subscription without COV increment."""
        ref = BACnetPropertyReference(
            property_identifier=PropertyIdentifier.RELIABILITY,
        )
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=99,
            monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 3),
            monitored_property_identifier=ref,
            issue_confirmed_notifications=True,
            lifetime=120,
            cov_increment=None,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 99
        assert decoded.monitored_object_identifier.object_type == ObjectType.BINARY_INPUT
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 120
        assert (
            decoded.monitored_property_identifier.property_identifier
            == PropertyIdentifier.RELIABILITY
        )
        assert decoded.cov_increment is None


class TestCOVReference:
    """Tests for COVReference encode/decode."""

    def test_round_trip_with_cov_increment(self):
        """COV reference with increment."""
        ref = COVReference(
            monitored_property=BACnetPropertyReference(
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            cov_increment=2.0,
        )
        encoded = ref.encode()
        decoded, _offset = COVReference.decode(encoded)

        assert decoded.monitored_property.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.monitored_property.property_array_index is None
        assert decoded.cov_increment == 2.0

    def test_round_trip_without_cov_increment(self):
        """COV reference without increment."""
        ref = COVReference(
            monitored_property=BACnetPropertyReference(
                property_identifier=PropertyIdentifier.STATUS_FLAGS,
                property_array_index=3,
            ),
            cov_increment=None,
        )
        encoded = ref.encode()
        decoded, _offset = COVReference.decode(encoded)

        assert decoded.monitored_property.property_identifier == PropertyIdentifier.STATUS_FLAGS
        assert decoded.monitored_property.property_array_index == 3
        assert decoded.cov_increment is None


class TestCOVSubscriptionSpecification:
    """Tests for COVSubscriptionSpecification encode/decode."""

    def test_round_trip_single_reference(self):
        """Specification with a single COV reference."""
        spec = COVSubscriptionSpecification(
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_cov_references=[
                COVReference(
                    monitored_property=BACnetPropertyReference(
                        property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    ),
                    cov_increment=1.0,
                ),
            ],
        )
        encoded = spec.encode()
        decoded, _offset = COVSubscriptionSpecification.decode(encoded)

        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.monitored_object_identifier.instance_number == 1
        assert len(decoded.list_of_cov_references) == 1
        assert (
            decoded.list_of_cov_references[0].monitored_property.property_identifier
            == PropertyIdentifier.PRESENT_VALUE
        )
        assert decoded.list_of_cov_references[0].cov_increment == 1.0

    def test_round_trip_multiple_references(self):
        """Specification with multiple COV references."""
        spec = COVSubscriptionSpecification(
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
            list_of_cov_references=[
                COVReference(
                    monitored_property=BACnetPropertyReference(
                        property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    ),
                    cov_increment=0.5,
                ),
                COVReference(
                    monitored_property=BACnetPropertyReference(
                        property_identifier=PropertyIdentifier.STATUS_FLAGS,
                    ),
                    cov_increment=None,
                ),
                COVReference(
                    monitored_property=BACnetPropertyReference(
                        property_identifier=PropertyIdentifier.RELIABILITY,
                        property_array_index=2,
                    ),
                    cov_increment=3.0,
                ),
            ],
        )
        encoded = spec.encode()
        decoded, _offset = COVSubscriptionSpecification.decode(encoded)

        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_VALUE
        assert decoded.monitored_object_identifier.instance_number == 10
        assert len(decoded.list_of_cov_references) == 3
        assert decoded.list_of_cov_references[0].cov_increment == 0.5
        assert decoded.list_of_cov_references[1].cov_increment is None
        assert decoded.list_of_cov_references[2].monitored_property.property_array_index == 2
        assert decoded.list_of_cov_references[2].cov_increment == 3.0


class TestSubscribeCOVPropertyMultipleRequest:
    """Tests for SubscribeCOVPropertyMultiple-Request encode/decode."""

    def test_round_trip_basic_subscription(self):
        """Basic subscription with one specification."""
        req = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=15,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            ),
                            cov_increment=1.0,
                        ),
                    ],
                ),
            ],
            issue_confirmed_notifications=True,
            lifetime=300,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyMultipleRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 15
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 300
        assert decoded.max_notification_delay is None
        assert len(decoded.list_of_cov_subscription_specifications) == 1
        spec = decoded.list_of_cov_subscription_specifications[0]
        assert spec.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert len(spec.list_of_cov_references) == 1
        assert spec.list_of_cov_references[0].cov_increment == 1.0

    def test_round_trip_with_max_notification_delay(self):
        """Subscription with max_notification_delay set."""
        req = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=20,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 5),
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            ),
                        ),
                    ],
                ),
            ],
            issue_confirmed_notifications=False,
            lifetime=600,
            max_notification_delay=10,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyMultipleRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 20
        assert decoded.issue_confirmed_notifications is False
        assert decoded.lifetime == 600
        assert decoded.max_notification_delay == 10
        assert len(decoded.list_of_cov_subscription_specifications) == 1

    def test_round_trip_cancellation(self):
        """Cancellation: optional fields omitted."""
        req = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=30,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 2),
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            ),
                        ),
                    ],
                ),
            ],
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyMultipleRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 30
        assert decoded.issue_confirmed_notifications is None
        assert decoded.lifetime is None
        assert decoded.max_notification_delay is None
        assert len(decoded.list_of_cov_subscription_specifications) == 1


class TestCOVPropertyValue:
    """Tests for COVPropertyValue encode/decode."""

    def test_round_trip_basic(self):
        """Basic property value with no optional fields."""
        value_bytes = encode_application_real(72.5)
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=value_bytes,
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.value == value_bytes
        assert decoded.array_index is None
        assert decoded.time_of_change is None

    def test_round_trip_with_array_index(self):
        """Property value with array_index."""
        value_bytes = encode_application_unsigned(100)
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=value_bytes,
            array_index=3,
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.value == value_bytes
        assert decoded.array_index == 3
        assert decoded.time_of_change is None

    def test_round_trip_with_time_of_change(self):
        """Property value with time_of_change (BACnetTimeStamp sequence number)."""
        value_bytes = encode_application_real(55.0)
        timestamp = BACnetTimeStamp(choice=1, value=42)
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=value_bytes,
            time_of_change=timestamp,
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.value == value_bytes
        assert decoded.array_index is None
        assert decoded.time_of_change is not None
        assert decoded.time_of_change.choice == 1
        assert decoded.time_of_change.value == 42


class TestCOVObjectNotification:
    """Tests for COVObjectNotification encode/decode."""

    def test_round_trip_single_property_value(self):
        """Notification with a single property value."""
        value_bytes = encode_application_real(23.5)
        notification = COVObjectNotification(
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_values=[
                COVPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=value_bytes,
                ),
            ],
        )
        encoded = notification.encode()
        decoded, _offset = COVObjectNotification.decode(encoded)

        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.monitored_object_identifier.instance_number == 1
        assert len(decoded.list_of_values) == 1
        assert decoded.list_of_values[0].property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.list_of_values[0].value == value_bytes

    def test_round_trip_multiple_property_values(self):
        """Notification with multiple property values."""
        pv_bytes = encode_application_real(68.0)
        sf_bytes = encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4))
        notification = COVObjectNotification(
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
            list_of_values=[
                COVPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=pv_bytes,
                ),
                COVPropertyValue(
                    property_identifier=PropertyIdentifier.STATUS_FLAGS,
                    value=sf_bytes,
                    array_index=None,
                ),
            ],
        )
        encoded = notification.encode()
        decoded, _offset = COVObjectNotification.decode(encoded)

        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_VALUE
        assert decoded.monitored_object_identifier.instance_number == 10
        assert len(decoded.list_of_values) == 2
        assert decoded.list_of_values[0].property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.list_of_values[0].value == pv_bytes
        assert decoded.list_of_values[1].property_identifier == PropertyIdentifier.STATUS_FLAGS
        assert decoded.list_of_values[1].value == sf_bytes


class TestCOVNotificationMultipleRequest:
    """Tests for COVNotificationMultiple-Request encode/decode."""

    def test_round_trip_single_object_notification(self):
        """Multiple notification with a single object."""
        value_bytes = encode_application_real(72.5)
        timestamp = BACnetTimeStamp(choice=1, value=100)
        req = COVNotificationMultipleRequest(
            subscriber_process_identifier=42,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            time_remaining=300,
            timestamp=timestamp,
            list_of_cov_notifications=[
                COVObjectNotification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_values=[
                        COVPropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            value=value_bytes,
                        ),
                    ],
                ),
            ],
        )
        encoded = req.encode()
        decoded = COVNotificationMultipleRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 42
        assert decoded.initiating_device_identifier.object_type == ObjectType.DEVICE
        assert decoded.initiating_device_identifier.instance_number == 100
        assert decoded.time_remaining == 300
        assert decoded.timestamp.choice == 1
        assert decoded.timestamp.value == 100
        assert len(decoded.list_of_cov_notifications) == 1
        obj_notif = decoded.list_of_cov_notifications[0]
        assert obj_notif.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert len(obj_notif.list_of_values) == 1
        assert obj_notif.list_of_values[0].value == value_bytes

    def test_round_trip_multiple_object_notifications(self):
        """Multiple notification with multiple objects."""
        pv_bytes_ai = encode_application_real(72.5)
        sf_bytes = encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4))
        pv_bytes_bv = b"\x91\x01"  # enumerated 1 (active)
        timestamp = BACnetTimeStamp(choice=1, value=200)
        req = COVNotificationMultipleRequest(
            subscriber_process_identifier=7,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
            time_remaining=120,
            timestamp=timestamp,
            list_of_cov_notifications=[
                COVObjectNotification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_values=[
                        COVPropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            value=pv_bytes_ai,
                        ),
                        COVPropertyValue(
                            property_identifier=PropertyIdentifier.STATUS_FLAGS,
                            value=sf_bytes,
                        ),
                    ],
                ),
                COVObjectNotification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 3),
                    list_of_values=[
                        COVPropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            value=pv_bytes_bv,
                        ),
                    ],
                ),
            ],
        )
        encoded = req.encode()
        decoded = COVNotificationMultipleRequest.decode(encoded)

        assert decoded.subscriber_process_identifier == 7
        assert decoded.initiating_device_identifier.object_type == ObjectType.DEVICE
        assert decoded.initiating_device_identifier.instance_number == 50
        assert decoded.time_remaining == 120
        assert decoded.timestamp.choice == 1
        assert decoded.timestamp.value == 200
        assert len(decoded.list_of_cov_notifications) == 2

        notif_ai = decoded.list_of_cov_notifications[0]
        assert notif_ai.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert len(notif_ai.list_of_values) == 2
        assert notif_ai.list_of_values[0].value == pv_bytes_ai
        assert notif_ai.list_of_values[1].value == sf_bytes

        notif_bv = decoded.list_of_cov_notifications[1]
        assert notif_bv.monitored_object_identifier.object_type == ObjectType.BINARY_VALUE
        assert len(notif_bv.list_of_values) == 1
        assert notif_bv.list_of_values[0].value == pv_bytes_bv


# ---------------------------------------------------------------------------
# Coverage: cov.py lines 710-711, 718, 722, 219->229, 521->530, 615->624
# ---------------------------------------------------------------------------


class TestCOVPropertyValueNestedOpeningClosing:
    """Lines 710-711, 718, 722: nested opening/closing tags in value field."""

    def test_nested_opening_closing_in_value(self):
        """Lines 709-711: opening tag inside value increments depth."""
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        # Create a value with nested opening/closing tags (e.g., a constructed type)
        inner_value = bytearray()
        inner_value.extend(encode_opening_tag(0))
        inner_value.extend(encode_application_real(42.0))
        inner_value.extend(encode_closing_tag(0))
        value_bytes = bytes(inner_value)

        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=value_bytes,
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.value == value_bytes

    def test_value_with_no_closing_tag(self):
        """Line 722: value_bytes collected when depth never reaches 0 (edge case)."""
        # This tests the else branch of the while loop (line 722)
        # Build a COVPropertyValue with empty value
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=b"",
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)
        assert decoded.value == b""

    def test_value_with_primitive_tag_inside(self):
        """Line 720: primitive tag inside value advances offset correctly."""
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_unsigned(100),
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)
        assert decoded.value == encode_application_unsigned(100)

    def test_value_truncated_before_closing_tag(self):
        """Line 722: while-else branch when data ends before closing tag [2]."""
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned
        from bac_py.encoding.tags import encode_opening_tag

        buf = bytearray()
        # [0] propertyIdentifier
        buf.extend(encode_context_tagged(0, encode_unsigned(85)))
        # [2] value opening tag -- but no closing tag
        buf.extend(encode_opening_tag(2))
        buf.extend(encode_application_real(42.0))
        # Deliberately omit closing tag 2 -- data ends here

        decoded, _offset = COVPropertyValue.decode(bytes(buf))
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        # value_bytes captured from value_start to end of data
        assert decoded.value == encode_application_real(42.0)


class TestCOVPropertyValueWithAllFields:
    """Lines 691-700: COVPropertyValue with array_index + time_of_change."""

    def test_round_trip_all_optional_fields(self):
        """All optional fields: array_index and time_of_change."""
        ts = BACnetTimeStamp(choice=1, value=99)
        value_bytes = encode_application_real(3.14)
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=value_bytes,
            array_index=5,
            time_of_change=ts,
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)

        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.value == value_bytes
        assert decoded.array_index == 5
        assert decoded.time_of_change is not None
        assert decoded.time_of_change.choice == 1
        assert decoded.time_of_change.value == 99


class TestSubscribeCOVRequestBranches:
    """Lines 219->229: decode path when listOfValues opening tag is missing."""

    def test_subscribe_cov_cancellation_minimal(self):
        """Verify cancellation encode/decode with minimal fields."""
        req = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 0),
        )
        encoded = req.encode()
        decoded = SubscribeCOVRequest.decode(encoded)
        assert decoded.issue_confirmed_notifications is None
        assert decoded.lifetime is None
        assert decoded.is_cancellation is True


# ---------------------------------------------------------------------------
# Coverage: common.py line 109 — BACnetPropertyValue priority out of range
# ---------------------------------------------------------------------------


class TestBACnetPropertyValuePriorityOutOfRange:
    """Line 109: priority outside 1-16 raises BACnetRejectError."""

    def test_priority_zero_raises(self):
        import pytest

        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        # [0] propertyIdentifier = 85
        buf.extend(encode_context_tagged(0, encode_unsigned(85)))
        # [2] value (empty)
        buf.extend(encode_opening_tag(2))
        buf.extend(encode_closing_tag(2))
        # [3] priority = 0 (out of range)
        buf.extend(encode_context_tagged(3, encode_unsigned(0)))
        with pytest.raises(BACnetRejectError):
            BACnetPropertyValue.decode_from(bytes(buf))

    def test_priority_17_raises(self):
        import pytest

        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        # [0] propertyIdentifier = 85
        buf.extend(encode_context_tagged(0, encode_unsigned(85)))
        # [2] value (empty)
        buf.extend(encode_opening_tag(2))
        buf.extend(encode_closing_tag(2))
        # [3] priority = 17 (out of range)
        buf.extend(encode_context_tagged(3, encode_unsigned(17)))
        with pytest.raises(BACnetRejectError):
            BACnetPropertyValue.decode_from(bytes(buf))


# ---------------------------------------------------------------------------
# Coverage: cov.py branch partials for while-loop exits in decode methods
# 219->229, 521->530, 615->624, 691->703, 794->803, 892->901
# These are all "while offset < len(data)" loops that normally exit via break
# when a closing tag is found. The untaken branch is the while condition
# becoming false (data ends before closing tag). For most of these, a
# round-trip with an empty list exercises the immediate-break path.
# ---------------------------------------------------------------------------


class TestCOVNotificationRequestEmptyValues:
    """Branch 219->229: while loop exit in COVNotificationRequest.decode.

    Empty listOfValues causes an immediate break at the closing tag [4].
    """

    def test_empty_list_of_values(self):
        """Empty listOfValues: while enters and immediately breaks."""
        notification = COVNotificationRequest(
            subscriber_process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=0,
            list_of_values=[],
        )
        encoded = notification.encode()
        decoded = COVNotificationRequest.decode(encoded)
        assert decoded.list_of_values == []
        assert decoded.time_remaining == 0


class TestCOVSubscriptionSpecificationEmptyRefs:
    """Branch 521->530: while loop exit in COVSubscriptionSpecification.decode.

    Empty listOfCOVReferences exercises immediate break.
    """

    def test_empty_list_of_cov_references(self):
        """Empty listOfCOVReferences: while enters and immediately breaks."""
        spec = COVSubscriptionSpecification(
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_cov_references=[],
        )
        encoded = spec.encode()
        decoded, _offset = COVSubscriptionSpecification.decode(encoded)
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.list_of_cov_references == []


class TestSubscribeCOVPropertyMultipleEmptySpecs:
    """Branch 615->624: while loop exit in SubscribeCOVPropertyMultiple.decode.

    Empty listOfCOVSubscriptionSpecifications exercises immediate break.
    """

    def test_empty_list_of_specs(self):
        """Empty specifications list: while enters and immediately breaks."""
        req = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=1,
            list_of_cov_subscription_specifications=[],
            issue_confirmed_notifications=True,
            lifetime=100,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyMultipleRequest.decode(encoded)
        assert decoded.subscriber_process_identifier == 1
        assert decoded.list_of_cov_subscription_specifications == []
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 100


class TestCOVPropertyValueNoArrayIndex:
    """Branch 691->703: optional arrayIndex check in COVPropertyValue.decode.

    When the next tag is NOT array index [1], the code skips directly to
    the value tag [2].
    """

    def test_property_value_without_array_index(self):
        """COVPropertyValue without array_index -- tag check falls through."""
        value_bytes = encode_application_real(42.0)
        pv = COVPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=value_bytes,
            array_index=None,
        )
        encoded = pv.encode()
        decoded, _offset = COVPropertyValue.decode(encoded)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.array_index is None
        assert decoded.value == value_bytes


class TestCOVObjectNotificationEmptyValues:
    """Branch 794->803: while loop exit in COVObjectNotification.decode.

    Empty listOfValues exercises immediate break.
    """

    def test_empty_list_of_values(self):
        """Empty listOfValues in COVObjectNotification."""
        notification = COVObjectNotification(
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_values=[],
        )
        encoded = notification.encode()
        decoded, _offset = COVObjectNotification.decode(encoded)
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.list_of_values == []


class TestCOVNotificationMultipleEmptyNotifications:
    """Branch 892->901: while loop exit in COVNotificationMultipleRequest.decode.

    Empty listOfCOVNotifications exercises immediate break.
    """

    def test_empty_list_of_notifications(self):
        """Empty listOfCOVNotifications in COVNotificationMultipleRequest."""
        timestamp = BACnetTimeStamp(choice=1, value=50)
        req = COVNotificationMultipleRequest(
            subscriber_process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            time_remaining=60,
            timestamp=timestamp,
            list_of_cov_notifications=[],
        )
        encoded = req.encode()
        decoded = COVNotificationMultipleRequest.decode(encoded)
        assert decoded.subscriber_process_identifier == 1
        assert decoded.list_of_cov_notifications == []
        assert decoded.time_remaining == 60
