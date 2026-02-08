"""Tests for BACnet Trend Log object (Clause 12.25)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.trendlog import TrendLogObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestTrendLogObject:
    """Tests for TrendLogObject (Clause 12.25)."""

    def test_create_basic(self):
        tl = TrendLogObject(1)
        assert tl.object_identifier == ObjectIdentifier(ObjectType.TREND_LOG, 1)

    def test_object_type(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.TREND_LOG

    def test_status_flags_initialized(self):
        tl = TrendLogObject(1)
        sf = tl.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_event_state_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_log_enable_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.LOG_ENABLE) is False

    def test_log_enable_writable(self):
        tl = TrendLogObject(1)
        tl.write_property(PropertyIdentifier.LOG_ENABLE, True)
        assert tl.read_property(PropertyIdentifier.LOG_ENABLE) is True

    def test_stop_when_full_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.STOP_WHEN_FULL) is False

    def test_stop_when_full_writable(self):
        tl = TrendLogObject(1)
        tl.write_property(PropertyIdentifier.STOP_WHEN_FULL, True)
        assert tl.read_property(PropertyIdentifier.STOP_WHEN_FULL) is True

    def test_buffer_size_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.BUFFER_SIZE) == 0

    def test_buffer_size_writable(self):
        tl = TrendLogObject(1)
        tl.write_property(PropertyIdentifier.BUFFER_SIZE, 1000)
        assert tl.read_property(PropertyIdentifier.BUFFER_SIZE) == 1000

    def test_log_buffer_default_empty(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.LOG_BUFFER) == []

    def test_log_buffer_read_only(self):
        tl = TrendLogObject(1)
        with pytest.raises(BACnetError) as exc_info:
            tl.write_property(PropertyIdentifier.LOG_BUFFER, [1, 2, 3])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_record_count_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.RECORD_COUNT) == 0

    def test_total_record_count_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.TOTAL_RECORD_COUNT) == 0

    def test_total_record_count_read_only(self):
        tl = TrendLogObject(1)
        with pytest.raises(BACnetError) as exc_info:
            tl.write_property(PropertyIdentifier.TOTAL_RECORD_COUNT, 50)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_log_interval_optional(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.LOG_INTERVAL) is None

    def test_logging_type_default(self):
        tl = TrendLogObject(1)
        assert tl.read_property(PropertyIdentifier.LOGGING_TYPE) == 0

    def test_not_commandable(self):
        tl = TrendLogObject(1)
        assert tl._priority_array is None

    def test_property_list(self):
        tl = TrendLogObject(1)
        plist = tl.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.LOG_ENABLE in plist
        assert PropertyIdentifier.STOP_WHEN_FULL in plist
        assert PropertyIdentifier.BUFFER_SIZE in plist
        assert PropertyIdentifier.LOG_BUFFER in plist
        assert PropertyIdentifier.RECORD_COUNT in plist
        assert PropertyIdentifier.TOTAL_RECORD_COUNT in plist
        assert PropertyIdentifier.LOGGING_TYPE in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.TREND_LOG, 7)
        assert isinstance(obj, TrendLogObject)

    def test_initial_properties(self):
        tl = TrendLogObject(1, object_name="TL-1", buffer_size=500)
        assert tl.read_property(PropertyIdentifier.OBJECT_NAME) == "TL-1"
        assert tl.read_property(PropertyIdentifier.BUFFER_SIZE) == 500
