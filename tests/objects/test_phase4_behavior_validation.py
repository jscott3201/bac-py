"""Phase 4 validation tests: Object behavior and validation (V1-V9).

Tests verify polarity inversion, range validation, COV_Increment validation,
Object_Name uniqueness, Database_Revision auto-increment, virtual Object_List,
and Number_Of_States guards.
"""

import pytest

from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject
from bac_py.objects.device import DeviceObject
from bac_py.objects.multistate import (
    MultiStateInputObject,
    MultiStateOutputObject,
    MultiStateValueObject,
)
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    BinaryPV,
    ErrorCode,
    Polarity,
    PropertyIdentifier,
)


# ---------------------------------------------------------------------------
# V1: Polarity inversion for binary objects
# ---------------------------------------------------------------------------
class TestV1PolarityInversion:
    """V1: Binary Input/Output apply polarity inversion on Present_Value reads."""

    def test_bi_normal_polarity_no_inversion(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.POLARITY) == Polarity.NORMAL
        assert bi.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_bi_reverse_polarity_inverts_inactive(self):
        bi = BinaryInputObject(1, polarity=Polarity.REVERSE)
        # Stored value is INACTIVE (default), but reverse polarity inverts it
        assert bi.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_bi_reverse_polarity_inverts_active(self):
        bi = BinaryInputObject(1, polarity=Polarity.REVERSE)
        bi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        bi.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        # Stored ACTIVE becomes INACTIVE with reverse polarity
        assert bi.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_bo_normal_polarity_no_inversion(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_bo_reverse_polarity_inverts(self):
        bo = BinaryOutputObject(1, polarity=Polarity.REVERSE)
        # Default INACTIVE stored, polarity REVERSE reads as ACTIVE
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_bo_reverse_polarity_after_write(self):
        bo = BinaryOutputObject(1, polarity=Polarity.REVERSE)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        # Stored ACTIVE becomes INACTIVE with reverse polarity
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_polarity_does_not_affect_other_properties(self):
        bi = BinaryInputObject(1, polarity=Polarity.REVERSE)
        # Other properties should not be affected
        assert bi.read_property(PropertyIdentifier.POLARITY) == Polarity.REVERSE
        assert bi.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False


# ---------------------------------------------------------------------------
# V2: Min/Max Present_Value range validation
# ---------------------------------------------------------------------------
class TestV2AnalogRangeValidation:
    """V2: Analog writes reject values outside Min/Max_Pres_Value."""

    def test_ao_write_within_range(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        ao._properties[PropertyIdentifier.MIN_PRES_VALUE] = 0.0
        ao._properties[PropertyIdentifier.MAX_PRES_VALUE] = 100.0
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0)
        assert ao.read_property(PropertyIdentifier.PRESENT_VALUE) == 50.0

    def test_ao_write_below_min_rejected(self):
        ao = AnalogOutputObject(1)
        ao._properties[PropertyIdentifier.MIN_PRES_VALUE] = 0.0
        ao._properties[PropertyIdentifier.MAX_PRES_VALUE] = 100.0
        with pytest.raises(BACnetError) as exc_info:
            ao.write_property(PropertyIdentifier.PRESENT_VALUE, -1.0, priority=16)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_ao_write_above_max_rejected(self):
        ao = AnalogOutputObject(1)
        ao._properties[PropertyIdentifier.MIN_PRES_VALUE] = 0.0
        ao._properties[PropertyIdentifier.MAX_PRES_VALUE] = 100.0
        with pytest.raises(BACnetError) as exc_info:
            ao.write_property(PropertyIdentifier.PRESENT_VALUE, 101.0, priority=16)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_ao_write_at_boundary_accepted(self):
        ao = AnalogOutputObject(1)
        ao._properties[PropertyIdentifier.MIN_PRES_VALUE] = 0.0
        ao._properties[PropertyIdentifier.MAX_PRES_VALUE] = 100.0
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 0.0, priority=16)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 100.0, priority=16)

    def test_av_range_validation(self):
        av = AnalogValueObject(1)
        av._properties[PropertyIdentifier.MIN_PRES_VALUE] = -10.0
        av._properties[PropertyIdentifier.MAX_PRES_VALUE] = 10.0
        with pytest.raises(BACnetError) as exc_info:
            av.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_ai_range_validation_when_oos(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        ai._properties[PropertyIdentifier.MIN_PRES_VALUE] = 0.0
        ai._properties[PropertyIdentifier.MAX_PRES_VALUE] = 50.0
        with pytest.raises(BACnetError) as exc_info:
            ai.write_property(PropertyIdentifier.PRESENT_VALUE, 60.0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_no_range_limits_allows_any_value(self):
        ao = AnalogOutputObject(1)
        # No min/max set, so any value should be accepted
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, -99999.0, priority=16)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 99999.0, priority=16)


# ---------------------------------------------------------------------------
# V3: COV_Increment non-negative validation
# ---------------------------------------------------------------------------
class TestV3COVIncrementValidation:
    """V3: COV_Increment must be >= 0."""

    def test_positive_cov_increment_accepted(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.COV_INCREMENT, 0.5)
        assert ai.read_property(PropertyIdentifier.COV_INCREMENT) == 0.5

    def test_zero_cov_increment_accepted(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.COV_INCREMENT, 0.0)
        assert ai.read_property(PropertyIdentifier.COV_INCREMENT) == 0.0

    def test_negative_cov_increment_rejected(self):
        ai = AnalogInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ai.write_property(PropertyIdentifier.COV_INCREMENT, -1.0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_negative_cov_increment_on_ao_rejected(self):
        ao = AnalogOutputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ao.write_property(PropertyIdentifier.COV_INCREMENT, -0.01)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_negative_cov_increment_on_av_rejected(self):
        av = AnalogValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            av.write_property(PropertyIdentifier.COV_INCREMENT, -5.0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE


# ---------------------------------------------------------------------------
# V4: Object_Name uniqueness enforcement
# ---------------------------------------------------------------------------
class TestV4ObjectNameUniqueness:
    """V4: Object_Name must be unique within ObjectDatabase."""

    def _make_device(self):
        return DeviceObject(
            1,
            object_name="Device-1",
            vendor_name="Test",
            vendor_identifier=999,
            model_name="Test",
            firmware_revision="1.0",
            application_software_version="1.0",
        )

    def test_add_objects_with_unique_names(self):
        db = ObjectDatabase()
        db.add(self._make_device())
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        assert len(db) == 2

    def test_add_object_with_duplicate_name_rejected(self):
        db = ObjectDatabase()
        db.add(self._make_device())
        ai1 = AnalogInputObject(1, object_name="Sensor-1")
        db.add(ai1)
        ai2 = AnalogInputObject(2, object_name="Sensor-1")
        with pytest.raises(BACnetError) as exc_info:
            db.add(ai2)
        assert exc_info.value.error_code == ErrorCode.DUPLICATE_NAME

    def test_rename_to_unique_name_accepted(self):
        db = ObjectDatabase()
        db.add(self._make_device())
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        ai.write_property(PropertyIdentifier.OBJECT_NAME, "AI-Renamed")
        assert ai.read_property(PropertyIdentifier.OBJECT_NAME) == "AI-Renamed"

    def test_rename_to_duplicate_name_rejected(self):
        db = ObjectDatabase()
        db.add(self._make_device())
        ai1 = AnalogInputObject(1, object_name="AI-1")
        ai2 = AnalogInputObject(2, object_name="AI-2")
        db.add(ai1)
        db.add(ai2)
        with pytest.raises(BACnetError) as exc_info:
            ai2.write_property(PropertyIdentifier.OBJECT_NAME, "AI-1")
        assert exc_info.value.error_code == ErrorCode.DUPLICATE_NAME

    def test_rename_to_own_name_accepted(self):
        db = ObjectDatabase()
        db.add(self._make_device())
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        # Writing the same name should not raise
        ai.write_property(PropertyIdentifier.OBJECT_NAME, "AI-1")

    def test_no_uniqueness_check_without_database(self):
        # Objects not in a database can have any name
        ai1 = AnalogInputObject(1, object_name="Same")
        ai2 = AnalogInputObject(2, object_name="Same")
        ai2.write_property(PropertyIdentifier.OBJECT_NAME, "Same")
        assert ai1.read_property(PropertyIdentifier.OBJECT_NAME) == "Same"

    def test_remove_frees_name(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        db.remove(ai.object_identifier)
        # Name should be available now
        ai2 = AnalogInputObject(2, object_name="AI-1")
        db.add(ai2)
        assert len(db) == 2


# ---------------------------------------------------------------------------
# V7: Database_Revision auto-increment
# ---------------------------------------------------------------------------
class TestV7DatabaseRevision:
    """V7: Database_Revision increments on add/remove/rename."""

    def _make_device(self):
        return DeviceObject(
            1,
            object_name="Device-1",
            vendor_name="Test",
            vendor_identifier=999,
            model_name="Test",
            firmware_revision="1.0",
            application_software_version="1.0",
        )

    def test_revision_increments_on_add(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        rev_after_dev = dev.read_property(PropertyIdentifier.DATABASE_REVISION)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        rev_after_ai = dev.read_property(PropertyIdentifier.DATABASE_REVISION)
        assert rev_after_ai == rev_after_dev + 1

    def test_revision_increments_on_remove(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        rev_before = dev.read_property(PropertyIdentifier.DATABASE_REVISION)
        db.remove(ai.object_identifier)
        rev_after = dev.read_property(PropertyIdentifier.DATABASE_REVISION)
        assert rev_after == rev_before + 1

    def test_revision_increments_on_rename(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        rev_before = dev.read_property(PropertyIdentifier.DATABASE_REVISION)
        ai.write_property(PropertyIdentifier.OBJECT_NAME, "AI-Renamed")
        rev_after = dev.read_property(PropertyIdentifier.DATABASE_REVISION)
        assert rev_after == rev_before + 1


# ---------------------------------------------------------------------------
# V8: Virtual Object_List on DeviceObject
# ---------------------------------------------------------------------------
class TestV8VirtualObjectList:
    """V8: Device.Object_List is computed from database."""

    def _make_device(self):
        return DeviceObject(
            1,
            object_name="Device-1",
            vendor_name="Test",
            vendor_identifier=999,
            model_name="Test",
            firmware_revision="1.0",
            application_software_version="1.0",
        )

    def test_object_list_reflects_database(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        obj_list = dev.read_property(PropertyIdentifier.OBJECT_LIST)
        assert dev.object_identifier in obj_list
        assert ai.object_identifier in obj_list
        assert len(obj_list) == 2

    def test_object_list_updates_after_remove(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        db.remove(ai.object_identifier)
        obj_list = dev.read_property(PropertyIdentifier.OBJECT_LIST)
        assert ai.object_identifier not in obj_list
        assert len(obj_list) == 1

    def test_object_list_array_index_0_returns_count(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        count = dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=0)
        assert count == 2

    def test_object_list_array_index_returns_element(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        obj_list = dev.read_property(PropertyIdentifier.OBJECT_LIST)
        first = dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=1)
        assert first == obj_list[0]

    def test_object_list_array_index_out_of_range(self):
        db = ObjectDatabase()
        dev = self._make_device()
        db.add(dev)
        with pytest.raises(BACnetError) as exc_info:
            dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=99)
        assert exc_info.value.error_code == ErrorCode.INVALID_ARRAY_INDEX

    def test_object_list_without_database_returns_empty(self):
        dev = self._make_device()
        # No database attached, falls back to stored property
        obj_list = dev.read_property(PropertyIdentifier.OBJECT_LIST)
        assert obj_list == []


# ---------------------------------------------------------------------------
# V9: Number_Of_States initialization guard
# ---------------------------------------------------------------------------
class TestV9NumberOfStatesGuard:
    """V9: Number_Of_States must be >= 1."""

    def test_msi_default_number_of_states(self):
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 2

    def test_msi_custom_number_of_states(self):
        msi = MultiStateInputObject(1, number_of_states=5)
        assert msi.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 5

    def test_mso_rejects_zero_states(self):
        mso = MultiStateOutputObject(1)
        mso.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        with pytest.raises(BACnetError) as exc_info:
            mso.write_property(PropertyIdentifier.NUMBER_OF_STATES, 0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_msv_rejects_negative_states(self):
        msv = MultiStateValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            msv.write_property(PropertyIdentifier.NUMBER_OF_STATES, -1)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_msi_present_value_validation_still_works(self):
        msi = MultiStateInputObject(1, number_of_states=3)
        msi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        msi.write_property(PropertyIdentifier.PRESENT_VALUE, 3)
        with pytest.raises(BACnetError) as exc_info:
            msi.write_property(PropertyIdentifier.PRESENT_VALUE, 4)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE

    def test_msi_present_value_zero_rejected(self):
        msi = MultiStateInputObject(1, number_of_states=3)
        msi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        with pytest.raises(BACnetError) as exc_info:
            msi.write_property(PropertyIdentifier.PRESENT_VALUE, 0)
        assert exc_info.value.error_code == ErrorCode.VALUE_OUT_OF_RANGE
