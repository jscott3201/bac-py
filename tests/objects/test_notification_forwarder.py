"""Tests for the BACnet Notification Forwarder object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestNotificationForwarderObject:
    def test_instantiation(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        assert obj.OBJECT_TYPE == ObjectType.NOTIFICATION_FORWARDER
        assert obj.read_property(PropertyIdentifier.LOCAL_FORWARDING_ONLY) is True
        assert obj.read_property(PropertyIdentifier.SUBSCRIBED_RECIPIENTS) == []
