"""Tests for the BACnet Audit Reporter object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestAuditReporterObject:
    def test_instantiation(self):
        from bac_py.objects.audit_reporter import AuditReporterObject

        obj = AuditReporterObject(1, object_name="ar-1")
        assert obj.OBJECT_TYPE == ObjectType.AUDIT_REPORTER
        assert obj.read_property(PropertyIdentifier.AUDIT_LEVEL) == 3  # AuditLevel.DEFAULT
        assert obj.read_property(PropertyIdentifier.MONITORED_OBJECTS) == []
