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
from bac_py.services.cov import SubscribeCOVRequest
from bac_py.services.errors import BACnetError, BACnetRejectError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ConfirmedServiceChoice,
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

        # Change Status_Flags (set out_of_service) -- use internal _properties
        # since STATUS_FLAGS is read-only per the object model
        av._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags(out_of_service=True)
        cov.check_and_notify(av, PropertyIdentifier.STATUS_FLAGS)

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

    def test_subscription_expires(self):
        """Subscription should be removed after lifetime expires."""

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

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

    def test_notification_time_remaining(self):
        """COV notification should include valid time_remaining."""
        from bac_py.services.cov import COVNotificationRequest

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

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

    def test_subscribe_returns_simple_ack(self):
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

        async def run():
            result = await handlers.handle_subscribe_cov(5, request.encode(), SUBSCRIBER)
            assert result is None  # SimpleACK

        asyncio.get_event_loop().run_until_complete(run())

        # Verify subscription was created
        subs = cov.get_active_subscriptions(av.object_identifier)
        assert len(subs) == 1

    def test_subscribe_unknown_object_returns_error(self):
        """SubscribeCOV for unknown object should raise BACnetError."""
        _app, _db, _device, _cov, handlers = self._make_server()

        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 99)
        request = SubscribeCOVRequest(
            subscriber_process_identifier=42,
            monitored_object_identifier=obj_id,
            issue_confirmed_notifications=True,
            lifetime=None,
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_subscribe_cov(5, request.encode(), SUBSCRIBER)
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())

    def test_subscribe_lifetime_without_confirmed_rejects(self):
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

        async def run():
            with pytest.raises(BACnetRejectError):
                await handlers.handle_subscribe_cov(5, request.encode(), SUBSCRIBER)

        asyncio.get_event_loop().run_until_complete(run())

    def test_cancellation_returns_simple_ack(self):
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

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_triggers_cov_notification(self):
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

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())
