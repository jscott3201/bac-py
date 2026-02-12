"""Tests for the BACnet Event Log object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestEventLogObject:
    def test_instantiation(self):
        from bac_py.objects.event_log import EventLogObject
        from bac_py.types.enums import LoggingType

        obj = EventLogObject(1, object_name="el-1")
        assert obj.OBJECT_TYPE == ObjectType.EVENT_LOG
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False
        assert obj.read_property(PropertyIdentifier.LOGGING_TYPE) == LoggingType.TRIGGERED
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []
