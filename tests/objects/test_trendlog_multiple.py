"""Tests for the BACnet Trend Log Multiple object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestTrendLogMultipleObject:
    def test_instantiation(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject
        from bac_py.types.enums import LoggingType

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.OBJECT_TYPE == ObjectType.TREND_LOG_MULTIPLE
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False
        assert obj.read_property(PropertyIdentifier.LOGGING_TYPE) == LoggingType.POLLED
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []
