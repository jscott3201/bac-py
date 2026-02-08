"""Tests for BACnet Event Enrollment object (Clause 12.12)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.event_enrollment import EventEnrollmentObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


class TestEventEnrollmentObject:
    """Tests for EventEnrollmentObject (Clause 12.12)."""

    def test_create_basic(self):
        ee = EventEnrollmentObject(1)
        assert ee.object_identifier == ObjectIdentifier(ObjectType.EVENT_ENROLLMENT, 1)

    def test_object_type(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.EVENT_ENROLLMENT

    def test_event_type_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.EVENT_TYPE) == 0

    def test_event_type_read_only(self):
        ee = EventEnrollmentObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ee.write_property(PropertyIdentifier.EVENT_TYPE, 5)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_event_state_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_event_enable_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.EVENT_ENABLE) == [True, True, True]

    def test_event_enable_writable(self):
        ee = EventEnrollmentObject(1)
        ee.write_property(PropertyIdentifier.EVENT_ENABLE, [True, False, True])
        assert ee.read_property(PropertyIdentifier.EVENT_ENABLE) == [True, False, True]

    def test_acked_transitions_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.ACKED_TRANSITIONS) == [
            True,
            True,
            True,
        ]

    def test_acked_transitions_read_only(self):
        ee = EventEnrollmentObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ee.write_property(PropertyIdentifier.ACKED_TRANSITIONS, [False, False, False])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_notify_type_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.NOTIFY_TYPE) == 0

    def test_notify_type_writable(self):
        ee = EventEnrollmentObject(1)
        ee.write_property(PropertyIdentifier.NOTIFY_TYPE, 1)
        assert ee.read_property(PropertyIdentifier.NOTIFY_TYPE) == 1

    def test_event_time_stamps_default(self):
        ee = EventEnrollmentObject(1)
        ts = ee.read_property(PropertyIdentifier.EVENT_TIME_STAMPS)
        assert ts == [None, None, None]

    def test_event_time_stamps_read_only(self):
        ee = EventEnrollmentObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ee.write_property(PropertyIdentifier.EVENT_TIME_STAMPS, [1, 2, 3])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_notification_class_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 0

    def test_notification_class_writable(self):
        ee = EventEnrollmentObject(1)
        ee.write_property(PropertyIdentifier.NOTIFICATION_CLASS, 42)
        assert ee.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 42

    def test_event_detection_enable_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.EVENT_DETECTION_ENABLE) is True

    def test_event_detection_enable_writable(self):
        ee = EventEnrollmentObject(1)
        ee.write_property(PropertyIdentifier.EVENT_DETECTION_ENABLE, False)
        assert ee.read_property(PropertyIdentifier.EVENT_DETECTION_ENABLE) is False

    def test_description_optional(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.DESCRIPTION) is None

    def test_status_flags_initialized(self):
        ee = EventEnrollmentObject(1)
        sf = ee.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_reliability_default(self):
        ee = EventEnrollmentObject(1)
        assert ee.read_property(PropertyIdentifier.RELIABILITY) == Reliability.NO_FAULT_DETECTED

    def test_not_commandable(self):
        ee = EventEnrollmentObject(1)
        assert ee._priority_array is None

    def test_property_list(self):
        ee = EventEnrollmentObject(1)
        plist = ee.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.EVENT_TYPE in plist
        assert PropertyIdentifier.EVENT_STATE in plist
        assert PropertyIdentifier.EVENT_ENABLE in plist
        assert PropertyIdentifier.ACKED_TRANSITIONS in plist
        assert PropertyIdentifier.NOTIFY_TYPE in plist
        assert PropertyIdentifier.EVENT_TIME_STAMPS in plist
        assert PropertyIdentifier.NOTIFICATION_CLASS in plist
        assert PropertyIdentifier.EVENT_DETECTION_ENABLE in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.RELIABILITY in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.EVENT_ENROLLMENT, 12)
        assert isinstance(obj, EventEnrollmentObject)

    def test_initial_properties(self):
        ee = EventEnrollmentObject(1, object_name="EE-1", notification_class=5)
        assert ee.read_property(PropertyIdentifier.OBJECT_NAME) == "EE-1"
        assert ee.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 5
