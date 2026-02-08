"""Tests for BACnet Notification Class object (Clause 12.21)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.notification import NotificationClassObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestNotificationClassObject:
    """Tests for NotificationClassObject (Clause 12.21)."""

    def test_create_basic(self):
        nc = NotificationClassObject(1)
        assert nc.object_identifier == ObjectIdentifier(ObjectType.NOTIFICATION_CLASS, 1)

    def test_object_type(self):
        nc = NotificationClassObject(1)
        assert nc.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.NOTIFICATION_CLASS

    def test_notification_class_defaults_to_instance(self):
        nc = NotificationClassObject(42)
        assert nc.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 42

    def test_notification_class_read_only(self):
        nc = NotificationClassObject(1)
        with pytest.raises(BACnetError) as exc_info:
            nc.write_property(PropertyIdentifier.NOTIFICATION_CLASS, 99)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_priority_default(self):
        nc = NotificationClassObject(1)
        priority = nc.read_property(PropertyIdentifier.PRIORITY)
        assert priority == [0, 0, 0]

    def test_priority_writable(self):
        nc = NotificationClassObject(1)
        nc.write_property(PropertyIdentifier.PRIORITY, [100, 200, 50])
        assert nc.read_property(PropertyIdentifier.PRIORITY) == [100, 200, 50]

    def test_ack_required_default(self):
        nc = NotificationClassObject(1)
        ack = nc.read_property(PropertyIdentifier.ACK_REQUIRED)
        assert ack == [False, False, False]

    def test_ack_required_writable(self):
        nc = NotificationClassObject(1)
        nc.write_property(PropertyIdentifier.ACK_REQUIRED, [True, False, True])
        assert nc.read_property(PropertyIdentifier.ACK_REQUIRED) == [True, False, True]

    def test_recipient_list_default_empty(self):
        nc = NotificationClassObject(1)
        assert nc.read_property(PropertyIdentifier.RECIPIENT_LIST) == []

    def test_recipient_list_writable(self):
        nc = NotificationClassObject(1)
        recipients = [{"address": "192.168.1.1"}]
        nc.write_property(PropertyIdentifier.RECIPIENT_LIST, recipients)
        assert nc.read_property(PropertyIdentifier.RECIPIENT_LIST) == recipients

    def test_description_optional(self):
        nc = NotificationClassObject(1)
        assert nc.read_property(PropertyIdentifier.DESCRIPTION) is None

    def test_not_commandable(self):
        nc = NotificationClassObject(1)
        assert nc._priority_array is None

    def test_no_status_flags(self):
        """NotificationClass has no Status_Flags per spec."""
        nc = NotificationClassObject(1)
        with pytest.raises(BACnetError) as exc_info:
            nc.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_property_list(self):
        nc = NotificationClassObject(1)
        plist = nc.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.NOTIFICATION_CLASS in plist
        assert PropertyIdentifier.PRIORITY in plist
        assert PropertyIdentifier.ACK_REQUIRED in plist
        assert PropertyIdentifier.RECIPIENT_LIST in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.NOTIFICATION_CLASS, 15)
        assert isinstance(obj, NotificationClassObject)

    def test_initial_properties(self):
        nc = NotificationClassObject(
            1,
            object_name="NC-1",
            priority=[10, 20, 30],
        )
        assert nc.read_property(PropertyIdentifier.OBJECT_NAME) == "NC-1"
        assert nc.read_property(PropertyIdentifier.PRIORITY) == [10, 20, 30]
