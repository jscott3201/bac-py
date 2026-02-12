"""Tests for the BACnet Alert Enrollment object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType


class TestAlertEnrollmentObject:
    def test_instantiation(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        assert obj.OBJECT_TYPE == ObjectType.ALERT_ENROLLMENT
