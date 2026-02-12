"""Tests for the BACnet Audit Log object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestAuditLogObject:
    def test_instantiation(self):
        from bac_py.objects.audit_log import AuditLogObject

        obj = AuditLogObject(1, object_name="al-1")
        assert obj.OBJECT_TYPE == ObjectType.AUDIT_LOG
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []
        assert obj.read_property(PropertyIdentifier.STOP_WHEN_FULL) is False
