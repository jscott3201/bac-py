"""Tests for BACnet Accumulator object (Clause 12.1)."""

import pytest

from bac_py.objects.accumulator import AccumulatorObject
from bac_py.objects.base import create_object
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import BACnetScale, StatusFlags
from bac_py.types.enums import (
    EngineeringUnits,
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestAccumulatorObject:
    """Tests for AccumulatorObject (Clause 12.1)."""

    def test_create_basic(self):
        acc = AccumulatorObject(1)
        assert acc.object_identifier == ObjectIdentifier(ObjectType.ACCUMULATOR, 1)

    def test_object_type(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.ACCUMULATOR

    def test_present_value_default(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.PRESENT_VALUE) == 0

    def test_present_value_read_only(self):
        acc = AccumulatorObject(1)
        with pytest.raises(BACnetError) as exc_info:
            acc.write_property(PropertyIdentifier.PRESENT_VALUE, 100)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_present_value_writable_when_oos(self):
        acc = AccumulatorObject(1)
        acc.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        acc.write_property(PropertyIdentifier.PRESENT_VALUE, 500)
        assert acc.read_property(PropertyIdentifier.PRESENT_VALUE) == 500

    def test_status_flags_initialized(self):
        acc = AccumulatorObject(1)
        sf = acc.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_event_state_default(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_out_of_service_default(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_units_default(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_scale_default(self):
        acc = AccumulatorObject(1)
        scale = acc.read_property(PropertyIdentifier.SCALE)
        assert isinstance(scale, BACnetScale)
        assert scale.float_scale == 1.0

    def test_prescale_optional(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.PRESCALE) is None

    def test_max_pres_value_default(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.MAX_PRES_VALUE) == 0xFFFFFFFF

    def test_max_pres_value_writable(self):
        acc = AccumulatorObject(1)
        acc.write_property(PropertyIdentifier.MAX_PRES_VALUE, 999999)
        assert acc.read_property(PropertyIdentifier.MAX_PRES_VALUE) == 999999

    def test_description_optional(self):
        acc = AccumulatorObject(1)
        assert acc.read_property(PropertyIdentifier.DESCRIPTION) is None

    def test_not_commandable(self):
        acc = AccumulatorObject(1)
        assert acc._priority_array is None

    def test_property_list(self):
        acc = AccumulatorObject(1)
        plist = acc.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.UNITS in plist
        assert PropertyIdentifier.SCALE in plist
        assert PropertyIdentifier.MAX_PRES_VALUE in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.ACCUMULATOR, 5)
        assert isinstance(obj, AccumulatorObject)

    def test_initial_properties(self):
        acc = AccumulatorObject(1, object_name="ACC-1", description="Power meter")
        assert acc.read_property(PropertyIdentifier.OBJECT_NAME) == "ACC-1"
        assert acc.read_property(PropertyIdentifier.DESCRIPTION) == "Power meter"
