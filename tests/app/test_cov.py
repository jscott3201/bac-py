"""Integration tests for COV (Change of Value) per ASHRAE 135-2016 Clause 13.1."""

import asyncio
from unittest.mock import MagicMock

import pytest

from bac_py.app.cov import COVManager
from bac_py.network.address import BACnetAddress
from bac_py.objects.analog import AnalogValueObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.binary import BinaryValueObject
from bac_py.objects.multistate import MultiStateValueObject
from bac_py.services.cov import (
    BACnetPropertyReference,
    COVNotificationRequest,
    COVReference,
    COVSubscriptionSpecification,
    SubscribeCOVPropertyMultipleRequest,
    SubscribeCOVPropertyRequest,
    SubscribeCOVRequest,
)
from bac_py.services.errors import BACnetError, BACnetRejectError
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import ObjectIdentifier

SUBSCRIBER = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
SUBSCRIBER2 = BACnetAddress(mac_address=b"\xc0\xa8\x01\x02\xba\xc0")


def _make_app(*, device_instance: int = 1):
    """Create a mock BACnetApplication for COV testing."""
    app = MagicMock()
    app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, device_instance)
    app.unconfirmed_request = MagicMock()
    app.send_confirmed_cov_notification = MagicMock()
    return app


def _make_cov_manager(
    app=None,
) -> tuple[MagicMock, ObjectDatabase, COVManager]:
    """Create a COVManager with a mock app and object database."""
    if app is None:
        app = _make_app()
    db = ObjectDatabase()
    cov = COVManager(app)
    return app, db, cov


def _subscribe_and_reset(
    app: MagicMock,
    cov: COVManager,
    subscriber: BACnetAddress,
    request: SubscribeCOVRequest,
    db: ObjectDatabase,
) -> None:
    """Subscribe and reset mock call counters.

    Per Clause 13.14.2, subscribe sends an initial notification.
    Reset mocks so subsequent assertions only count change-triggered
    notifications.
    """
    cov.subscribe(subscriber, request, db)
    app.unconfirmed_request.reset_mock()
    app.send_confirmed_cov_notification.reset_mock()


class TestCOVSubscription:
    """Tests for subscription lifecycle management."""

    def test_subscribe_creates_subscription(self):
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request, db)

        subs = cov.get_active_subscriptions(obj_id)
        assert len(subs) == 1
        assert subs[0].process_id == 42
        assert subs[0].confirmed is True
        assert subs[0].lifetime is None

    def test_subscribe_sends_initial_notification(self):
        """Per Clause 13.14.2, an initial notification shall be sent on subscribe."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request, db)

        # Initial notification should have been sent
        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION
        )

    def test_subscribe_replaces_existing(self):
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        # First subscription
        request1 = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request1, db)

        # Replace with different settings
        request2 = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request2, db)

        subs = cov.get_active_subscriptions(obj_id)
        assert len(subs) == 1
        assert subs[0].confirmed is False
        assert subs[0].lifetime is None

    def test_unsubscribe_removes_subscription(self):
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request, db)
        assert len(cov.get_active_subscriptions(obj_id)) == 1

        cov.unsubscribe(SUBSCRIBER, 42, obj_id)
        assert len(cov.get_active_subscriptions(obj_id)) == 0

    def test_unsubscribe_nonexistent_is_silent(self):
        _app, _db, cov = _make_cov_manager()
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 99)
        # Should not raise
        cov.unsubscribe(SUBSCRIBER, 42, obj_id)

    def test_subscribe_unknown_object_raises_error(self):
        _app, db, cov = _make_cov_manager()
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 99)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        with pytest.raises(BACnetError) as exc_info:
            cov.subscribe(SUBSCRIBER, request, db)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    def test_get_all_subscriptions(self):
        _app, db, cov = _make_cov_manager()
        av1 = AnalogValueObject(1)
        av2 = AnalogValueObject(2)
        db.add(av1)
        db.add(av2)

        request1 = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=av1.object_identifier,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        request2 = SubscribeCOVRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=av2.object_identifier,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request1, db)
        cov.subscribe(SUBSCRIBER, request2, db)

        all_subs = cov.get_active_subscriptions()
        assert len(all_subs) == 2

        # Filter by object
        subs_av1 = cov.get_active_subscriptions(av1.object_identifier)
        assert len(subs_av1) == 1
        assert subs_av1[0].process_id == 1

    def test_shutdown_clears_subscriptions(self):
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request, db)
        assert len(cov.get_active_subscriptions()) == 1

        cov.shutdown()
        assert len(cov.get_active_subscriptions()) == 0


class TestCOVNotification:
    """Tests for COV change detection and notification dispatch."""

    def test_analog_change_triggers_notification(self):
        """Any change in analog Present_Value (no COV_INCREMENT) triggers notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change Present_Value
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        # Should have sent an unconfirmed notification
        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION
        )

    def test_analog_cov_increment_triggers_when_exceeded(self):
        """Analog value change >= COV_INCREMENT should trigger notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        # Set a COV_INCREMENT of 5.0
        av.write_property(PropertyIdentifier.COV_INCREMENT, 5.0)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change by exactly 5.0 (== increment)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 5.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_analog_within_increment_no_notification(self):
        """Analog value change < COV_INCREMENT should NOT trigger notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        # Present_Value starts at 0.0
        av.write_property(PropertyIdentifier.COV_INCREMENT, 5.0)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change by 4.9 (< increment of 5.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 4.9)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_not_called()

    def test_analog_no_increment_any_change_triggers(self):
        """Analog object with no COV_INCREMENT -- any change triggers notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        # No COV_INCREMENT set (or default 0)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Even a tiny change should trigger
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 0.001)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_binary_any_change_triggers(self):
        """Binary object -- any Present_Value change triggers notification."""
        app, db, cov = _make_cov_manager()
        from bac_py.types.enums import BinaryPV

        bv = BinaryValueObject(1)
        db.add(bv)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=bv.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change from INACTIVE to ACTIVE
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        cov.check_and_notify(bv, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_binary_value_encoded_as_enumerated(self):
        """Binary Present_Value should be encoded as enumerated, not unsigned."""
        from bac_py.encoding.primitives import decode_enumerated
        from bac_py.encoding.tags import decode_tag
        from bac_py.services.cov import COVNotificationRequest
        from bac_py.types.enums import BinaryPV

        app, db, cov = _make_cov_manager()
        bv = BinaryValueObject(1)
        db.add(bv)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=bv.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        cov.check_and_notify(bv, PropertyIdentifier.PRESENT_VALUE)

        call_kwargs = app.unconfirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        notification = COVNotificationRequest.decode(service_data)

        # Find Present_Value in list_of_values
        pv_entry = next(
            v
            for v in notification.list_of_values
            if v.property_identifier == PropertyIdentifier.PRESENT_VALUE
        )
        # Application tag 9 = enumerated (not tag 2 = unsigned)
        tag, _ = decode_tag(pv_entry.value, 0)
        assert tag.number == 9, "BinaryPV should be encoded as enumerated (tag 9)"
        value = decode_enumerated(pv_entry.value[1 : 1 + tag.length])
        assert value == 1  # ACTIVE

    def test_multistate_any_change_triggers(self):
        """Multistate object -- any Present_Value change triggers notification."""
        app, db, cov = _make_cov_manager()
        mv = MultiStateValueObject(1, number_of_states=5)
        db.add(mv)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=mv.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change from 1 to 3
        mv.write_property(PropertyIdentifier.PRESENT_VALUE, 3)
        cov.check_and_notify(mv, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_no_change_no_notification(self):
        """No change in value -- no notification sent."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Don't change anything, just trigger check
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_not_called()

    def test_status_flags_change_triggers_notification(self):
        """Change in Status_Flags triggers notification regardless of Present_Value."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change Out_Of_Service to True, which causes StatusFlags to change
        # (the out_of_service bit is computed from the Out_Of_Service property)
        av._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        cov.check_and_notify(av, PropertyIdentifier.OUT_OF_SERVICE)

        app.unconfirmed_request.assert_called_once()


class TestCOVConfirmedVsUnconfirmed:
    """Tests for confirmed vs unconfirmed notification dispatch."""

    def test_confirmed_notification_sent(self):
        """Confirmed subscription should use send_confirmed_cov_notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.send_confirmed_cov_notification.assert_called_once()
        call_args = app.send_confirmed_cov_notification.call_args
        assert call_args[0][2] == ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION
        app.unconfirmed_request.assert_not_called()

    def test_unconfirmed_notification_sent(self):
        """Unconfirmed subscription should use unconfirmed_request."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION
        )
        app.send_confirmed_cov_notification.assert_not_called()


class TestCOVMultipleSubscribers:
    """Tests for multiple subscribers to the same object."""

    def test_multiple_subscribers_all_notified(self):
        """All subscribers to the same object should receive notifications."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        # Subscriber 1 (unconfirmed)
        request1 = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        # Subscriber 2 (confirmed)
        request2 = SubscribeCOVRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request1, db)
        cov.subscribe(SUBSCRIBER2, request2, db)
        app.unconfirmed_request.reset_mock()
        app.send_confirmed_cov_notification.reset_mock()

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        # Both should be notified
        app.unconfirmed_request.assert_called_once()
        app.send_confirmed_cov_notification.assert_called_once()

    def test_different_objects_independent(self):
        """Subscribers to different objects are independent."""
        app, db, cov = _make_cov_manager()
        av1 = AnalogValueObject(1)
        av2 = AnalogValueObject(2)
        db.add(av1)
        db.add(av2)

        # Subscribe to av1
        request1 = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=av1.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request1, db)

        # Change av2 (no subscription)
        av2.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        cov.check_and_notify(av2, PropertyIdentifier.PRESENT_VALUE)

        # No notification should be sent
        app.unconfirmed_request.assert_not_called()


class TestCOVLifecycle:
    """Tests for subscription lifecycle (expiry, indefinite)."""

    async def test_subscription_expires(self):
        """Subscription should be removed after lifetime expires."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=1,  # 1 second
        )
        cov.subscribe(SUBSCRIBER, request, db)
        assert len(cov.get_active_subscriptions(obj_id)) == 1

        # Wait for expiry
        await asyncio.sleep(1.1)

        assert len(cov.get_active_subscriptions(obj_id)) == 0

    def test_indefinite_subscription_persists(self):
        """Subscription with no lifetime should persist."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        cov.subscribe(SUBSCRIBER, request, db)

        subs = cov.get_active_subscriptions(obj_id)
        assert len(subs) == 1
        assert subs[0].lifetime is None
        assert subs[0].expiry_handle is None


class TestCOVNotificationContent:
    """Tests verifying the content of COV notifications."""

    def test_notification_contains_present_value_and_status_flags(self):
        """COV notification should contain Present_Value and Status_Flags."""
        from bac_py.services.cov import COVNotificationRequest

        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 25.5)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        # Decode the notification that was sent
        call_kwargs = app.unconfirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        notification = COVNotificationRequest.decode(service_data)

        # Verify structure
        assert notification.subscriber_process_identifier == 42
        assert notification.monitored_object_identifier == av.object_identifier
        assert notification.initiating_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)

        # Should have exactly 2 property values
        assert len(notification.list_of_values) == 2

        prop_ids = [pv.property_identifier for pv in notification.list_of_values]
        assert PropertyIdentifier.PRESENT_VALUE in prop_ids
        assert PropertyIdentifier.STATUS_FLAGS in prop_ids

    async def test_notification_time_remaining(self):
        """COV notification should include valid time_remaining."""
        from bac_py.services.cov import COVNotificationRequest

        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=600,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        call_kwargs = app.unconfirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        notification = COVNotificationRequest.decode(service_data)

        # time_remaining should be close to 600 (just started)
        assert 595 <= notification.time_remaining <= 600

    def test_notification_time_remaining_zero_for_indefinite(self):
        """Indefinite subscription should have time_remaining=0."""
        from bac_py.services.cov import COVNotificationRequest

        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        call_kwargs = app.unconfirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        notification = COVNotificationRequest.decode(service_data)

        assert notification.time_remaining == 0


class TestCOVIncrementAccumulation:
    """Tests for COV increment accumulation behavior."""

    def test_increment_accumulates_from_last_notification(self):
        """COV increment is measured from last-reported value, not last write."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        av.write_property(PropertyIdentifier.COV_INCREMENT, 10.0)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Write 3.0 -- below increment, no notification
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 3.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        assert app.unconfirmed_request.call_count == 0

        # Write 7.0 -- still below 10.0 from last-reported (0.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 7.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        assert app.unconfirmed_request.call_count == 0

        # Write 10.0 -- exactly at increment from last-reported (0.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        assert app.unconfirmed_request.call_count == 1

        # Now last-reported becomes 10.0
        # Write 15.0 -- only 5.0 from last-reported (10.0), below increment
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 15.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        assert app.unconfirmed_request.call_count == 1

        # Write 20.0 -- exactly 10.0 from last-reported (10.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        assert app.unconfirmed_request.call_count == 2


class TestServerSubscribeCOVHandler:
    """Tests for the server-side SubscribeCOV handler."""

    def _make_server(self):
        """Create a DefaultServerHandlers instance for testing."""
        from bac_py.app.server import DefaultServerHandlers
        from bac_py.objects.device import DeviceObject

        app = MagicMock()
        app.config = MagicMock()
        app.config.max_apdu_length = 1476
        app.config.vendor_id = 42
        app.config.instance_number = 1
        app.service_registry = MagicMock()
        app.unconfirmed_request = MagicMock()
        app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, 1)
        app.send_confirmed_cov_notification = MagicMock()

        db = ObjectDatabase()
        device = DeviceObject(
            1,
            object_name="test-device",
            vendor_name="test-vendor",
            vendor_identifier=42,
            model_name="test-model",
            firmware_revision="1.0",
            application_software_version="1.0",
        )
        db.add(device)

        cov = COVManager(app)
        app.cov_manager = cov

        handlers = DefaultServerHandlers(app, db, device)
        return app, db, device, cov, handlers

    async def test_subscribe_returns_simple_ack(self):
        """SubscribeCOV should return None (SimpleACK) on success."""
        _app, db, _device, cov, handlers = self._make_server()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=True,
            lifetime=None,
        )

        result = await handlers.handle_subscribe_cov(5, request.encode(), SUBSCRIBER)
        assert result is None  # SimpleACK

        # Verify subscription was created
        subs = cov.get_active_subscriptions(av.object_identifier)
        assert len(subs) == 1

    async def test_subscribe_unknown_object_returns_error(self):
        """SubscribeCOV for unknown object should raise BACnetError."""
        _app, _db, _device, _cov, handlers = self._make_server()

        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 99)
        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_subscribe_cov(5, request.encode(), SUBSCRIBER)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_subscribe_lifetime_without_confirmed_rejects(self):
        """Per Clause 13.14.1.1.4, lifetime requires issue_confirmed_notifications."""
        _app, db, _device, _cov, handlers = self._make_server()
        av = AnalogValueObject(1)
        db.add(av)

        # Lifetime present but issue_confirmed_notifications absent
        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=None,
            lifetime=300,
        )

        with pytest.raises(BACnetRejectError):
            await handlers.handle_subscribe_cov(5, request.encode(), SUBSCRIBER)

    async def test_cancellation_returns_simple_ack(self):
        """Cancellation request should return SimpleACK and remove subscription."""
        _app, db, _device, cov, handlers = self._make_server()
        av = AnalogValueObject(1)
        db.add(av)

        # First subscribe
        sub_req = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=True,
            lifetime=None,
        )

        await handlers.handle_subscribe_cov(5, sub_req.encode(), SUBSCRIBER)
        assert len(cov.get_active_subscriptions(av.object_identifier)) == 1

        # Send cancellation (no confirmed/lifetime fields)
        cancel_req = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
        )
        result = await handlers.handle_subscribe_cov(5, cancel_req.encode(), SUBSCRIBER)
        assert result is None
        assert len(cov.get_active_subscriptions(av.object_identifier)) == 0

    async def test_write_triggers_cov_notification(self):
        """WriteProperty should trigger COV notification after successful write."""
        app, db, _device, _cov, handlers = self._make_server()
        av = AnalogValueObject(1)
        db.add(av)

        # Subscribe
        sub_req = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )

        await handlers.handle_subscribe_cov(5, sub_req.encode(), SUBSCRIBER)
        app.unconfirmed_request.reset_mock()

        # Write a property value
        from bac_py.encoding.primitives import encode_application_real
        from bac_py.services.write_property import WritePropertyRequest

        wp_request = WritePropertyRequest(
            object_identifier=av.object_identifier,
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(42.0),
        )
        await handlers.handle_write_property(15, wp_request.encode(), SUBSCRIBER)

        # COV notification should have been sent
        app.unconfirmed_request.assert_called_once()


# ---------------------------------------------------------------------------
# Property-level COV subscription tests
# ---------------------------------------------------------------------------


def _make_prop_request(
    obj_id,
    *,
    process_id=42,
    property_id=PropertyIdentifier.PRESENT_VALUE,
    array_index=None,
    confirmed=False,
    lifetime=None,
    cov_increment=None,
):
    """Build a SubscribeCOVPropertyRequest for testing."""
    return SubscribeCOVPropertyRequest(
        subscriber_process_identifier=process_id,
        monitored_object_identifier=obj_id,
        monitored_property_identifier=BACnetPropertyReference(
            property_identifier=int(property_id),
            property_array_index=array_index,
        ),
        issue_confirmed_notifications=confirmed,
        lifetime=lifetime,
        cov_increment=cov_increment,
    )


class TestSubscribeProperty:
    """Tests for subscribe_property (Clause 13.15)."""

    def test_subscribe_property_creates_subscription(self):
        """Create a PropertySubscription and send initial notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier)
        cov.subscribe_property(SUBSCRIBER, request, db)

        # Should have exactly one property subscription
        assert len(cov._property_subscriptions) == 1
        sub = next(iter(cov._property_subscriptions.values()))
        assert sub.monitored_property == int(PropertyIdentifier.PRESENT_VALUE)
        assert sub.confirmed is False
        assert sub.lifetime is None
        assert sub.cov_increment is None

        # Initial notification sent
        app.unconfirmed_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_property_with_lifetime(self):
        """subscribe_property with lifetime sets up an expiry timer."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier, lifetime=300)
        cov.subscribe_property(SUBSCRIBER, request, db)

        sub = next(iter(cov._property_subscriptions.values()))
        assert sub.lifetime == 300.0
        assert sub.expiry_handle is not None

        # Clean up timer
        sub.expiry_handle.cancel()

    @pytest.mark.asyncio
    async def test_subscribe_property_replaces_existing(self):
        """Subscribing twice with the same key cancels the first timer."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        # First subscription with lifetime
        request1 = _make_prop_request(av.object_identifier, lifetime=300)
        cov.subscribe_property(SUBSCRIBER, request1, db)

        sub1 = next(iter(cov._property_subscriptions.values()))
        handle1 = sub1.expiry_handle
        assert handle1 is not None

        # Replace with a new subscription
        request2 = _make_prop_request(av.object_identifier, lifetime=600)
        cov.subscribe_property(SUBSCRIBER, request2, db)

        # First timer should have been cancelled
        assert handle1.cancelled()

        # Only one subscription remains
        assert len(cov._property_subscriptions) == 1
        sub2 = next(iter(cov._property_subscriptions.values()))
        assert sub2.lifetime == 600.0

        # Clean up
        if sub2.expiry_handle:
            sub2.expiry_handle.cancel()

    def test_subscribe_property_unknown_object(self):
        """subscribe_property for a nonexistent object raises BACnetError."""
        _app, db, cov = _make_cov_manager()
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 99)

        request = _make_prop_request(obj_id)
        with pytest.raises(BACnetError) as exc_info:
            cov.subscribe_property(SUBSCRIBER, request, db)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


class TestSubscribePropertyMultiple:
    """Tests for subscribe_property_multiple (Clause 13.16)."""

    def test_subscribe_property_multiple_basic(self):
        """subscribe_property_multiple with one spec creates subscriptions."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=42,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=av.object_identifier,
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
                            ),
                            cov_increment=2.0,
                        ),
                    ],
                ),
            ],
            issue_confirmed_notifications=False,
        )
        cov.subscribe_property_multiple(SUBSCRIBER, request, db)

        assert len(cov._property_subscriptions) == 1
        sub = next(iter(cov._property_subscriptions.values()))
        assert sub.cov_increment == 2.0
        assert sub.monitored_property == int(PropertyIdentifier.PRESENT_VALUE)

        # Initial notification sent
        app.unconfirmed_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_property_multiple_with_lifetime(self):
        """subscribe_property_multiple with lifetime sets timers per subscription."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=42,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=av.object_identifier,
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
                            ),
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
            lifetime=300,
        )
        cov.subscribe_property_multiple(SUBSCRIBER, request, db)

        assert len(cov._property_subscriptions) == 2
        for sub in cov._property_subscriptions.values():
            assert sub.lifetime == 300.0
            assert sub.expiry_handle is not None

        # Clean up timers
        for sub in cov._property_subscriptions.values():
            if sub.expiry_handle:
                sub.expiry_handle.cancel()

    def test_subscribe_property_multiple_unknown_object(self):
        """subscribe_property_multiple for an unknown object raises BACnetError."""
        _app, db, cov = _make_cov_manager()

        request = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=42,
            list_of_cov_subscription_specifications=[
                COVSubscriptionSpecification(
                    monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 99),
                    list_of_cov_references=[
                        COVReference(
                            monitored_property=BACnetPropertyReference(
                                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
                            ),
                        ),
                    ],
                ),
            ],
            issue_confirmed_notifications=False,
        )
        with pytest.raises(BACnetError) as exc_info:
            cov.subscribe_property_multiple(SUBSCRIBER, request, db)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


class TestUnsubscribeProperty:
    """Tests for unsubscribe_property."""

    @pytest.mark.asyncio
    async def test_unsubscribe_property_cancels_timer(self):
        """unsubscribe_property cancels the timer and removes the subscription."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        # Subscribe with lifetime so there is a timer to cancel
        request = _make_prop_request(obj_id, lifetime=300)
        cov.subscribe_property(SUBSCRIBER, request, db)
        assert len(cov._property_subscriptions) == 1

        sub = next(iter(cov._property_subscriptions.values()))
        handle = sub.expiry_handle
        assert handle is not None

        cov.unsubscribe_property(
            SUBSCRIBER,
            42,
            obj_id,
            int(PropertyIdentifier.PRESENT_VALUE),
        )

        assert len(cov._property_subscriptions) == 0
        assert handle.cancelled()

    def test_unsubscribe_property_nonexistent(self):
        """unsubscribe_property for a nonexistent subscription does not error."""
        _app, _db, cov = _make_cov_manager()
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 99)

        # Should not raise
        cov.unsubscribe_property(
            SUBSCRIBER,
            42,
            obj_id,
            int(PropertyIdentifier.PRESENT_VALUE),
        )


class TestCheckAndNotifyProperty:
    """Tests for check_and_notify_property and _should_notify_property."""

    def test_check_and_notify_property_triggers(self):
        """Writing a monitored property triggers a property notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier)
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Change the monitored property
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_check_and_notify_property_no_change(self):
        """No change in monitored property value means no notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier)
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Don't change the value, just trigger check
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_not_called()

    def test_should_notify_property_analog_with_increment(self):
        """Analog property with cov_increment: change >= increment triggers."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        # Subscribe with a cov_increment of 5.0
        request = _make_prop_request(av.object_identifier, cov_increment=5.0)
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Change by exactly 5.0 from initial (0.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 5.0)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_should_notify_property_analog_below_increment(self):
        """Analog property with cov_increment: change < increment does not trigger."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        # Subscribe with a cov_increment of 5.0
        request = _make_prop_request(av.object_identifier, cov_increment=5.0)
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Change by only 4.9 from initial (0.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 4.9)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_not_called()

    def test_should_notify_property_non_analog(self):
        """Non-analog (binary) property: any change triggers notification."""
        from bac_py.types.enums import BinaryPV

        app, db, cov = _make_cov_manager()
        bv = BinaryValueObject(1)
        db.add(bv)

        request = _make_prop_request(bv.object_identifier)
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        cov.check_and_notify_property(bv, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_should_notify_property_analog_none_last_value(self):
        """Analog property with last_value=None should trigger notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        # Subscribe with cov_increment; manually set last_value to None
        request = _make_prop_request(av.object_identifier, cov_increment=5.0)
        cov.subscribe_property(SUBSCRIBER, request, db)
        app.unconfirmed_request.reset_mock()

        # Force last_value to None to simulate the edge case
        sub = next(iter(cov._property_subscriptions.values()))
        sub.last_value = None

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 1.0)
        cov.check_and_notify_property(av, PropertyIdentifier.PRESENT_VALUE)

        # Should notify because last_value is None
        app.unconfirmed_request.assert_called_once()


class TestPropertyNotificationSending:
    """Tests for _send_property_notification dispatch."""

    def test_send_property_notification_confirmed(self):
        """Confirmed property subscription sends via send_confirmed_cov_notification."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier, confirmed=True)
        cov.subscribe_property(SUBSCRIBER, request, db)

        # Initial notification sent as confirmed
        app.send_confirmed_cov_notification.assert_called_once()
        call_args = app.send_confirmed_cov_notification.call_args
        assert call_args[0][2] == ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION
        app.unconfirmed_request.assert_not_called()

    def test_send_property_notification_unconfirmed(self):
        """Unconfirmed property subscription sends via unconfirmed_request."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier, confirmed=False)
        cov.subscribe_property(SUBSCRIBER, request, db)

        # Initial notification sent as unconfirmed
        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION
        )
        app.send_confirmed_cov_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_property_notification_time_remaining(self):
        """Property subscription with lifetime includes correct time_remaining."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier, lifetime=600)
        cov.subscribe_property(SUBSCRIBER, request, db)

        # Decode the initial notification
        call_kwargs = app.unconfirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        notification = COVNotificationRequest.decode(service_data)

        # time_remaining should be close to 600 (just started)
        assert 595 <= notification.time_remaining <= 600

        # Clean up timer
        sub = next(iter(cov._property_subscriptions.values()))
        if sub.expiry_handle:
            sub.expiry_handle.cancel()

    def test_send_property_notification_content(self):
        """Property notification includes the monitored property and Status_Flags."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 25.5)

        request = _make_prop_request(av.object_identifier)
        cov.subscribe_property(SUBSCRIBER, request, db)

        call_kwargs = app.unconfirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        notification = COVNotificationRequest.decode(service_data)

        assert notification.subscriber_process_identifier == 42
        assert notification.monitored_object_identifier == av.object_identifier
        assert len(notification.list_of_values) == 2

        prop_ids = [pv.property_identifier for pv in notification.list_of_values]
        assert PropertyIdentifier.PRESENT_VALUE in prop_ids
        assert PropertyIdentifier.STATUS_FLAGS in prop_ids


class TestPropertySubscriptionExpiry:
    """Tests for property subscription expiry and cleanup."""

    @pytest.mark.asyncio
    async def test_on_property_subscription_expired(self):
        """Expiry handler removes the property subscription."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = _make_prop_request(av.object_identifier, lifetime=1)
        cov.subscribe_property(SUBSCRIBER, request, db)
        assert len(cov._property_subscriptions) == 1

        # Wait for expiry
        await asyncio.sleep(1.1)

        assert len(cov._property_subscriptions) == 0

    @pytest.mark.asyncio
    async def test_remove_object_subscriptions_with_property_subs(self):
        """remove_object_subscriptions cleans up property subscriptions too."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        # Create both a regular and a property subscription
        regular_request = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=300,
        )
        cov.subscribe(SUBSCRIBER, regular_request, db)

        prop_request = _make_prop_request(av.object_identifier, process_id=2, lifetime=300)
        cov.subscribe_property(SUBSCRIBER, prop_request, db)

        assert len(cov._subscriptions) == 1
        assert len(cov._property_subscriptions) == 1

        # Capture the timer handles
        reg_handle = next(iter(cov._subscriptions.values())).expiry_handle
        prop_handle = next(iter(cov._property_subscriptions.values())).expiry_handle
        assert reg_handle is not None
        assert prop_handle is not None

        cov.remove_object_subscriptions(av.object_identifier)

        assert len(cov._subscriptions) == 0
        assert len(cov._property_subscriptions) == 0
        assert reg_handle.cancelled()
        assert prop_handle.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_cleans_property_subscriptions(self):
        """Shutdown cancels property subscription timers."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        prop_request = _make_prop_request(av.object_identifier, lifetime=300)
        cov.subscribe_property(SUBSCRIBER, prop_request, db)

        assert len(cov._property_subscriptions) == 1
        handle = next(iter(cov._property_subscriptions.values())).expiry_handle
        assert handle is not None

        cov.shutdown()

        assert len(cov._property_subscriptions) == 0
        assert handle.cancelled()


class TestCOVEdgeCases:
    """Tests for edge cases in COV logic."""

    def test_encode_status_flags_fallback(self):
        """_encode_status_flags with non-StatusFlags/non-BitString value returns all-clear."""
        from bac_py.encoding.primitives import decode_bit_string
        from bac_py.encoding.tags import decode_tag

        _app, _db, cov = _make_cov_manager()

        # Pass a plain integer (not StatusFlags or BitString)
        result = cov._encode_status_flags(42)
        assert isinstance(result, bytes)
        assert len(result) > 0

        # Decode and verify it is all-clear
        tag, offset = decode_tag(result, 0)
        bs = decode_bit_string(result[offset : offset + tag.length])
        assert bs.unused_bits == 4
        assert bs.data == bytes([0x00])

    def test_read_present_value_bacnet_error_returns_none(self):
        """_read_present_value returns None when object raises BACnetError."""
        _app, _db, cov = _make_cov_manager()

        obj = MagicMock()
        obj.read_property = MagicMock(
            side_effect=BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        )
        result = cov._read_present_value(obj)
        assert result is None

    def test_read_status_flags_bacnet_error_returns_none(self):
        """_read_status_flags returns None when object raises BACnetError."""
        _app, _db, cov = _make_cov_manager()

        obj = MagicMock()
        obj.read_property = MagicMock(
            side_effect=BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        )
        result = cov._read_status_flags(obj)
        assert result is None

    def test_read_cov_increment_bacnet_error_returns_none(self):
        """_read_cov_increment returns None when object raises BACnetError."""
        _app, _db, cov = _make_cov_manager()

        obj = MagicMock()
        obj.read_property = MagicMock(
            side_effect=BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        )
        result = cov._read_cov_increment(obj)
        assert result is None

    def test_read_property_value_exception_returns_none(self):
        """_read_property_value returns None on BACnetError or ValueError."""
        _app, _db, cov = _make_cov_manager()

        obj = MagicMock()
        obj.read_property = MagicMock(
            side_effect=BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        )
        result = cov._read_property_value(obj, int(PropertyIdentifier.PRESENT_VALUE))
        assert result is None

        # Also test ValueError
        obj.read_property = MagicMock(side_effect=ValueError("bad value"))
        result = cov._read_property_value(obj, int(PropertyIdentifier.PRESENT_VALUE))
        assert result is None

    def test_should_notify_analog_none_last_value(self):
        """_should_notify with analog subscription where last_present_value is None."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        av.write_property(PropertyIdentifier.COV_INCREMENT, 5.0)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Force last_present_value to None
        sub = next(iter(cov._subscriptions.values()))
        sub.last_present_value = None

        # Any non-None present value should trigger
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 1.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)

        app.unconfirmed_request.assert_called_once()

    def test_should_notify_analog_numeric_comparison(self):
        """_should_notify with analog subscription performs numeric |delta| >= increment."""
        app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        av.write_property(PropertyIdentifier.COV_INCREMENT, 10.0)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=None,
        )
        _subscribe_and_reset(app, cov, SUBSCRIBER, request, db)

        # Change by 9.9, below increment -- no notification
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 9.9)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        app.unconfirmed_request.assert_not_called()

        # Change to 10.0, exactly at increment from last reported (0.0)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        cov.check_and_notify(av, PropertyIdentifier.PRESENT_VALUE)
        app.unconfirmed_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_subscription_expired_logging(self):
        """_on_subscription_expired logs and removes the subscription."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=1,
        )
        cov.subscribe(SUBSCRIBER, request, db)
        assert len(cov.get_active_subscriptions(av.object_identifier)) == 1

        # Wait for expiry
        await asyncio.sleep(1.1)

        assert len(cov.get_active_subscriptions(av.object_identifier)) == 0

    @pytest.mark.asyncio
    async def test_subscribe_replaces_existing_cancels_timer(self):
        """subscribe() replacing an existing subscription cancels the old timer."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        # First subscription with lifetime
        request1 = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=300,
        )
        cov.subscribe(SUBSCRIBER, request1, db)

        sub1 = next(iter(cov._subscriptions.values()))
        handle1 = sub1.expiry_handle
        assert handle1 is not None

        # Replace
        request2 = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=600,
        )
        cov.subscribe(SUBSCRIBER, request2, db)

        # First timer should have been cancelled
        assert handle1.cancelled()
        assert len(cov.get_active_subscriptions(obj_id)) == 1

        sub2 = next(iter(cov._subscriptions.values()))
        assert sub2.lifetime == 600.0

        # Clean up
        if sub2.expiry_handle:
            sub2.expiry_handle.cancel()

    @pytest.mark.asyncio
    async def test_unsubscribe_cancels_timer(self):
        """unsubscribe() cancels the expiry timer."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)
        obj_id = av.object_identifier

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=False,
            lifetime=300,
        )
        cov.subscribe(SUBSCRIBER, request, db)

        sub = next(iter(cov._subscriptions.values()))
        handle = sub.expiry_handle
        assert handle is not None

        cov.unsubscribe(SUBSCRIBER, 42, obj_id)

        assert len(cov.get_active_subscriptions(obj_id)) == 0
        assert handle.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_regular_timers(self):
        """shutdown() cancels timers on regular subscriptions."""
        _app, db, cov = _make_cov_manager()
        av = AnalogValueObject(1)
        db.add(av)

        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=av.object_identifier,
            issue_confirmed_notifications=False,
            lifetime=300,
        )
        cov.subscribe(SUBSCRIBER, request, db)

        handle = next(iter(cov._subscriptions.values())).expiry_handle
        assert handle is not None

        cov.shutdown()

        assert len(cov.get_active_subscriptions()) == 0
        assert handle.cancelled()
