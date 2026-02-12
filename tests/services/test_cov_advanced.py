"""Tests for advanced COV services (Step 9.4).

Covers:
- Round-trip encode/decode for all new service dataclasses
- Property-level subscription with custom cov_increment
- Property-level subscription: change detected only for subscribed property
- Multiple-property subscription
- Subscription cancellation for property-level subscriptions
- Coexistence: object-level and property-level subscriptions on same object
- Lifetime expiry removes property subscriptions
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bac_py.app.cov import COVManager, PropertySubscription
from bac_py.encoding.primitives import encode_application_real, encode_application_unsigned
from bac_py.network.address import BACnetAddress
from bac_py.objects.analog import AnalogInputObject, AnalogValueObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.binary import BinaryValueObject
from bac_py.services.cov import (
    BACnetPropertyReference,
    COVNotificationMultipleRequest,
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
from bac_py.types.primitives import ObjectIdentifier

SUBSCRIBER = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
SUBSCRIBER2 = BACnetAddress(mac_address=b"\xc0\xa8\x01\x02\xba\xc0")


def _make_app(*, device_instance: int = 1) -> MagicMock:
    app = MagicMock()
    app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, device_instance)
    app.unconfirmed_request = MagicMock()
    app.send_confirmed_cov_notification = MagicMock()
    return app


# ---------------------------------------------------------------------------
# Round-trip encode/decode tests for new service dataclasses
# ---------------------------------------------------------------------------


class TestBACnetPropertyReference:
    def test_round_trip_basic(self):
        ref = BACnetPropertyReference(property_identifier=85)
        encoded = ref.encode()
        decoded, _ = BACnetPropertyReference.decode(encoded)
        assert decoded.property_identifier == 85
        assert decoded.property_array_index is None

    def test_round_trip_with_array_index(self):
        ref = BACnetPropertyReference(property_identifier=85, property_array_index=3)
        encoded = ref.encode()
        decoded, _ = BACnetPropertyReference.decode(encoded)
        assert decoded.property_identifier == 85
        assert decoded.property_array_index == 3


class TestSubscribeCOVPropertyRequest:
    def test_round_trip_basic(self):
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=85,
            ),
            issue_confirmed_notifications=True,
            lifetime=300,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)
        assert decoded.subscriber_process_identifier == 42
        assert decoded.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.monitored_property_identifier.property_identifier == 85
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 300
        assert decoded.cov_increment is None

    def test_round_trip_with_cov_increment(self):
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=7,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 5),
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=85,
                property_array_index=2,
            ),
            issue_confirmed_notifications=False,
            lifetime=600,
            cov_increment=1.5,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)
        assert decoded.subscriber_process_identifier == 7
        assert decoded.monitored_property_identifier.property_array_index == 2
        assert decoded.cov_increment is not None
        assert abs(decoded.cov_increment - 1.5) < 0.01

    def test_round_trip_minimal(self):
        """Minimal request with no optional fields."""
        req = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 1),
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=85,
            ),
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyRequest.decode(encoded)
        assert decoded.issue_confirmed_notifications is None
        assert decoded.lifetime is None
        assert decoded.cov_increment is None


class TestSubscribeCOVPropertyMultipleRequest:
    def test_round_trip(self):
        req = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=10,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=85,
                            ),
                            cov_increment=2.0,
                        ),
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=111,
                            ),
                        ),
                    ],
                ),
            ],
            issue_confirmed_notifications=True,
            lifetime=120,
            max_notification_delay=5,
        )
        encoded = req.encode()
        decoded = SubscribeCOVPropertyMultipleRequest.decode(encoded)
        assert decoded.subscriber_process_identifier == 10
        assert decoded.issue_confirmed_notifications is True
        assert decoded.lifetime == 120
        assert decoded.max_notification_delay == 5
        assert len(decoded.list_of_cov_subscription_specifications) == 1
        spec = decoded.list_of_cov_subscription_specifications[0]
        assert spec.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert len(spec.list_of_cov_references) == 2
        assert spec.list_of_cov_references[0].cov_increment is not None
        assert abs(spec.list_of_cov_references[0].cov_increment - 2.0) < 0.01
        assert spec.list_of_cov_references[1].cov_increment is None


class TestCOVNotificationMultipleRequest:
    def test_round_trip(self):
        pv_value = encode_application_real(72.5)
        ts = BACnetTimeStamp(choice=1, value=0)
        req = COVNotificationMultipleRequest(
            subscriber_process_identifier=42,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            time_remaining=300,
            timestamp=ts,
            list_of_cov_notifications=[
                COVObjectNotification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_values=[
                        COVPropertyValue(
                            property_identifier=85,
                            value=pv_value,
                        ),
                    ],
                ),
            ],
        )
        encoded = req.encode()
        decoded = COVNotificationMultipleRequest.decode(encoded)
        assert decoded.subscriber_process_identifier == 42
        assert decoded.time_remaining == 300
        assert len(decoded.list_of_cov_notifications) == 1
        notif = decoded.list_of_cov_notifications[0]
        assert notif.monitored_object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert len(notif.list_of_values) == 1
        assert notif.list_of_values[0].property_identifier == 85

    def test_round_trip_with_time_of_change(self):
        """COVPropertyValue with optional timeOfChange field."""
        ts = BACnetTimeStamp(choice=1, value=100)
        pv_value = encode_application_unsigned(1)
        pv = COVPropertyValue(
            property_identifier=85,
            value=pv_value,
            time_of_change=ts,
        )
        encoded = pv.encode()
        decoded, _ = COVPropertyValue.decode(encoded)
        assert decoded.property_identifier == 85
        assert decoded.time_of_change is not None

    def test_round_trip_with_array_index(self):
        """COVPropertyValue with optional arrayIndex field."""
        pv_value = encode_application_unsigned(42)
        pv = COVPropertyValue(
            property_identifier=87,
            value=pv_value,
            array_index=3,
        )
        encoded = pv.encode()
        decoded, _ = COVPropertyValue.decode(encoded)
        assert decoded.property_identifier == 87
        assert decoded.array_index == 3


# ---------------------------------------------------------------------------
# COVManager property subscription tests
# ---------------------------------------------------------------------------


class TestPropertySubscription:
    """Test property-level COV subscription lifecycle."""

    def test_subscribe_property_creates_subscription(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        cov.subscribe_property(SUBSCRIBER, request, db)

        # Should have exactly one property subscription
        assert len(cov._property_subscriptions) == 1

    def test_subscribe_property_sends_initial_notification(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        cov.subscribe_property(SUBSCRIBER, request, db)

        # Should send initial unconfirmed notification
        app.unconfirmed_request.assert_called_once()

    def test_unsubscribe_property(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        prop_id = int(PropertyIdentifier.PRESENT_VALUE)
        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=prop_id,
            ),
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property(SUBSCRIBER, request, db)
        assert len(cov._property_subscriptions) == 1

        cov.unsubscribe_property(SUBSCRIBER, 42, av.object_identifier, prop_id)
        assert len(cov._property_subscriptions) == 0

    def test_property_change_triggers_notification(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Change the present value by more than default increment
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 100.0)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_property_no_change_no_notification(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Check without changing - no notification
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)
        app.unconfirmed_request.assert_not_called()

    def test_custom_cov_increment(self):
        """Property subscription uses subscription-specific cov_increment."""
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
            cov_increment=10.0,
        )
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Change by less than cov_increment - no notification
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 5.0)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)
        app.unconfirmed_request.assert_not_called()

        # Change by more than cov_increment - notification
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 15.0)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)
        app.unconfirmed_request.assert_called_once()


class TestPropertySubscriptionMultiple:
    """Test multi-property COV subscription."""

    def test_subscribe_multiple_creates_subscriptions(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        request = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=10,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=av.object_identifier,
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
                            ),
                            cov_increment=5.0,
                        ),
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=int(PropertyIdentifier.STATUS_FLAGS),
                            ),
                        ),
                    ],
                ),
            ],
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property_multiple(SUBSCRIBER, request, db)

        # Should have 2 property subscriptions
        assert len(cov._property_subscriptions) == 2


class TestCoexistence:
    """Test object-level and property-level subscriptions coexist."""

    def test_both_types_on_same_object(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        # Object-level subscription
        obj_request = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, obj_request, db)

        # Property-level subscription
        prop_request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property(SUBSCRIBER, prop_request, db)

        assert len(cov._subscriptions) == 1
        assert len(cov._property_subscriptions) == 1

    def test_shutdown_clears_both(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        obj_request = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
        )
        cov.subscribe(SUBSCRIBER, obj_request, db)

        prop_request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property(SUBSCRIBER, prop_request, db)

        cov.shutdown()
        assert len(cov._subscriptions) == 0
        assert len(cov._property_subscriptions) == 0

    def test_remove_object_clears_both(self):
        app = _make_app()
        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)
        cov = COVManager(app)

        obj_request = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
        )
        cov.subscribe(SUBSCRIBER, obj_request, db)

        prop_request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=av.object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property(SUBSCRIBER, prop_request, db)

        cov.remove_object_subscriptions(av.object_identifier)
        assert len(cov._subscriptions) == 0
        assert len(cov._property_subscriptions) == 0
