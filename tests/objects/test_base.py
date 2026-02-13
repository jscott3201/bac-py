"""Tests for BACnet object model base classes (PropertyDefinition, ObjectDatabase, factory)."""

import pytest

from bac_py.objects.base import (
    ObjectDatabase,
    PropertyAccess,
    PropertyDefinition,
    create_object,
)
from bac_py.objects.device import DeviceObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestPropertyDefinition:
    def test_attributes(self):
        pd = PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        )
        assert pd.identifier == PropertyIdentifier.PRESENT_VALUE
        assert pd.datatype is float
        assert pd.access == PropertyAccess.READ_WRITE
        assert pd.required is True
        assert pd.default == 0.0

    def test_frozen(self):
        pd = PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        )
        with pytest.raises(AttributeError):
            pd.required = True


class TestBACnetObjectArrayAccess:
    def test_read_array_index_zero_returns_length(self):
        dev = DeviceObject(1)
        obj_list = [ObjectIdentifier(8, 1), ObjectIdentifier(0, 1)]
        dev._properties[PropertyIdentifier.OBJECT_LIST] = obj_list
        length = dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=0)
        assert length == 2

    def test_read_array_index_valid(self):
        dev = DeviceObject(1)
        obj_list = [ObjectIdentifier(8, 1), ObjectIdentifier(0, 2)]
        dev._properties[PropertyIdentifier.OBJECT_LIST] = obj_list
        elem = dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=1)
        assert elem == ObjectIdentifier(8, 1)

    def test_read_array_index_out_of_range(self):
        dev = DeviceObject(1)
        dev._properties[PropertyIdentifier.OBJECT_LIST] = [ObjectIdentifier(8, 1)]
        with pytest.raises(BACnetError) as exc_info:
            dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=5)
        assert exc_info.value.error_code == ErrorCode.INVALID_ARRAY_INDEX

    def test_read_array_index_on_non_array(self):
        dev = DeviceObject(1, object_name="test")
        with pytest.raises(BACnetError) as exc_info:
            dev.read_property(PropertyIdentifier.OBJECT_NAME, array_index=1)
        assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_AN_ARRAY


class TestObjectDatabase:
    def test_add_and_get(self):
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        result = db.get(ObjectIdentifier(ObjectType.DEVICE, 1))
        assert result is dev

    def test_add_duplicate_raises(self):
        db = ObjectDatabase()
        dev1 = DeviceObject(1)
        db.add(dev1)
        dev2 = DeviceObject(1)
        with pytest.raises(BACnetError) as exc_info:
            db.add(dev2)
        assert exc_info.value.error_code == ErrorCode.OBJECT_IDENTIFIER_ALREADY_EXISTS

    def test_get_nonexistent_returns_none(self):
        db = ObjectDatabase()
        result = db.get(ObjectIdentifier(ObjectType.DEVICE, 999))
        assert result is None

    def test_remove_object(self):
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        # Cannot remove Device object
        with pytest.raises(BACnetError) as exc_info:
            db.remove(ObjectIdentifier(ObjectType.DEVICE, 1))
        assert exc_info.value.error_code == ErrorCode.OBJECT_DELETION_NOT_PERMITTED

    def test_remove_nonexistent_raises(self):
        db = ObjectDatabase()
        with pytest.raises(BACnetError) as exc_info:
            db.remove(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    def test_object_list(self):
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        olist = db.object_list
        assert ObjectIdentifier(ObjectType.DEVICE, 1) in olist

    def test_len(self):
        db = ObjectDatabase()
        assert len(db) == 0
        db.add(DeviceObject(1))
        assert len(db) == 1

    def test_get_objects_of_type(self):
        db = ObjectDatabase()
        db.add(DeviceObject(1))
        devices = db.get_objects_of_type(ObjectType.DEVICE)
        assert len(devices) == 1
        ais = db.get_objects_of_type(ObjectType.ANALOG_INPUT)
        assert len(ais) == 0


class TestObjectFactory:
    def test_create_device_via_factory(self):
        dev = create_object(ObjectType.DEVICE, 42)
        assert isinstance(dev, DeviceObject)
        assert dev.object_identifier.instance_number == 42

    def test_create_unsupported_type_raises(self):
        # NETWORK_SECURITY is deprecated and not registered
        with pytest.raises(BACnetError) as exc_info:
            create_object(ObjectType.NETWORK_SECURITY, 1)
        assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_OBJECT_TYPE


# ---------------------------------------------------------------------------
# Coverage: write callback, priority array, array element, __iter__/__contains__
# ---------------------------------------------------------------------------


class TestWriteCallbackInvocation:
    """Line 501, 507-508: write callback invocation on property write."""

    def test_write_callback_fires_on_value_change(self):
        """Line 507-508: _on_property_written called when value changes."""
        from unittest.mock import MagicMock

        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1)
        cb = MagicMock()
        av._on_property_written = cb

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        cb.assert_called_once()
        args = cb.call_args[0]
        assert args[0] == PropertyIdentifier.PRESENT_VALUE

    def test_write_callback_not_fired_when_value_unchanged(self):
        """Callback should not fire if old == new."""
        from unittest.mock import MagicMock

        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 0.0)
        cb = MagicMock()
        av._on_property_written = cb

        av.write_property(PropertyIdentifier.PRESENT_VALUE, 0.0)
        cb.assert_not_called()

    def test_write_array_element(self):
        """Line 500-501: write to array element via array_index."""
        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1, commandable=True)
        # Priority array is a list of 16 elements
        pa = av.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert len(pa) == 16

        # Write to array element using the description property (non-commandable array)
        av._properties[PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG] = ["a", "b", "c"]
        av.write_property(PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG, "X", array_index=2)
        assert av._properties[PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG][1] == "X"


class TestWriteArrayElementErrors:
    """Lines 712-717: _write_array_element out-of-bounds and non-array."""

    def test_write_array_element_not_an_array(self):
        """Line 713-714: write to non-array property with array_index."""
        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1)
        av.write_property(PropertyIdentifier.DESCRIPTION, "test")
        with pytest.raises(BACnetError) as exc_info:
            av.write_property(PropertyIdentifier.DESCRIPTION, "new", array_index=1)
        assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_AN_ARRAY

    def test_write_array_element_index_zero(self):
        """Line 715-716: array_index < 1 raises error."""
        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1)
        av._properties[PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG] = ["a", "b"]
        with pytest.raises(BACnetError) as exc_info:
            av.write_property(PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG, "X", array_index=0)
        assert exc_info.value.error_code == ErrorCode.INVALID_ARRAY_INDEX

    def test_write_array_element_index_too_large(self):
        """Line 715-716: array_index > len(current) raises error."""
        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1)
        av._properties[PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG] = ["a", "b"]
        with pytest.raises(BACnetError) as exc_info:
            av.write_property(PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG, "X", array_index=5)
        assert exc_info.value.error_code == ErrorCode.INVALID_ARRAY_INDEX


class TestPriorityArrayValueSourceInit:
    """Line 656: _write_with_priority creates priority array when None."""

    def test_write_with_priority_creates_array_if_none(self):
        """Line 655-656: if _priority_array is None, initialize it."""
        from bac_py.objects.analog import AnalogValueObject

        av = AnalogValueObject(1)
        # Ensure _priority_array is None (non-commandable)
        assert av._priority_array is None
        # Directly call _write_with_priority — this should create the array
        av._write_with_priority(PropertyIdentifier.PRESENT_VALUE, 42.0, 8)
        assert av._priority_array is not None
        assert av._priority_array[7] == 42.0


class TestObjectDatabaseDunderMethods:
    """Lines 902-906: __iter__, __contains__."""

    def test_iter(self):
        """Line 902-903: __iter__ yields ObjectIdentifiers."""
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        ids = list(db)
        assert ObjectIdentifier(ObjectType.DEVICE, 1) in ids

    def test_contains(self):
        """Line 905-906: __contains__ checks membership."""
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        assert ObjectIdentifier(ObjectType.DEVICE, 1) in db
        assert ObjectIdentifier(ObjectType.DEVICE, 999) not in db


class TestObjectDatabaseRemoveBranch:
    """Lines 771-775: remove empties type bucket branch."""

    def test_remove_clears_empty_type_bucket(self):
        """Lines 771-775: type_bucket is deleted when empty after remove."""
        from bac_py.objects.analog import AnalogInputObject

        db = ObjectDatabase()
        db.add(DeviceObject(1))
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        assert ObjectType.ANALOG_INPUT in db._type_index

        db.remove(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
        # Type bucket should be cleaned up
        assert ObjectType.ANALOG_INPUT not in db._type_index


class TestObjectDatabaseNameIndex:
    """Lines 802-804: _update_name_index when old_name is set."""

    def test_update_name_index_removes_old_name(self):
        """Line 802-804: old_name is removed from index on rename."""
        from bac_py.objects.analog import AnalogInputObject

        db = ObjectDatabase()
        db.add(DeviceObject(1))
        ai = AnalogInputObject(1, object_name="OldName")
        db.add(ai)

        assert "OldName" in db._names
        ai.write_property(PropertyIdentifier.OBJECT_NAME, "NewName")
        assert "OldName" not in db._names
        assert "NewName" in db._names


class TestRegisterUnregisterChangeCallback:
    """Lines 836->exit, 853->exit, 856->exit: callback registration branches."""

    def test_register_callback_wires_notifier(self):
        """Line 836: obj._on_property_written is set when callback registered."""
        from bac_py.objects.analog import AnalogValueObject

        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)

        def cb(pid, old, new):
            pass

        db.register_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb)
        assert av._on_property_written is not None

    def test_unregister_callback_nonexistent_key(self):
        """Line 853->exit: no-op when key not in _change_callbacks."""
        from bac_py.objects.analog import AnalogValueObject

        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)

        def cb(pid, old, new):
            pass

        # Should not raise
        db.unregister_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb)

    def test_unregister_callback_removes_entry(self):
        """Line 856->exit: empty callback list is cleaned up."""
        from bac_py.objects.analog import AnalogValueObject

        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)

        def cb(pid, old, new):
            pass

        db.register_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb)
        key = (av.object_identifier, PropertyIdentifier.PRESENT_VALUE)
        assert key in db._change_callbacks

        db.unregister_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb)
        # After removing the last callback, the key should be deleted
        assert key not in db._change_callbacks

    def test_unregister_callback_wrong_callback(self):
        """Line 854: suppress ValueError when callback not in list."""
        from bac_py.objects.analog import AnalogValueObject

        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)

        def cb1(pid, old, new):
            pass

        def cb2(pid, old, new):
            pass

        db.register_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb1)
        # Trying to unregister cb2 that was never registered - should not raise
        db.unregister_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb2)
        key = (av.object_identifier, PropertyIdentifier.PRESENT_VALUE)
        # cb1 should still be registered
        assert key in db._change_callbacks
        assert cb1 in db._change_callbacks[key]


# ---------------------------------------------------------------------------
# Coverage: ObjectDatabase.remove() when type_bucket is None (branch 771->775)
# ---------------------------------------------------------------------------


class TestRemoveObjectNoTypeBucket:
    """Branch 771->775: remove when _type_index has no entry for the object type."""

    def test_remove_when_type_index_cleared_externally(self):
        """When _type_index lacks the object's type, remove still succeeds."""
        from bac_py.objects.analog import AnalogInputObject

        db = ObjectDatabase()
        db.add(DeviceObject(1))
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)

        # Manually clear the type index to simulate missing entry
        db._type_index.pop(ObjectType.ANALOG_INPUT, None)

        # remove() should still work — the type_bucket is None branch
        db.remove(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
        assert db.get(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)) is None


# ---------------------------------------------------------------------------
# Coverage: _update_name_index when old_name maps to different object (branch 802->804)
# ---------------------------------------------------------------------------


class TestUpdateNameIndexOldNameDifferentObject:
    """Branch 802->804: old_name is not None but maps to a different object."""

    def test_old_name_maps_to_different_object_not_deleted(self):
        """When _names[old_name] != object_id, old_name entry is preserved."""
        from bac_py.objects.analog import AnalogInputObject

        db = ObjectDatabase()
        db.add(DeviceObject(1))
        ai1 = AnalogInputObject(1, object_name="Name1")
        ai2 = AnalogInputObject(2, object_name="Name2")
        db.add(ai1)
        db.add(ai2)

        # Manually point "Name1" to ai2's id in the index to simulate mismatch
        db._names["Name1"] = ai2.object_identifier

        # Call _update_name_index with old_name="Name1" for ai1 —
        # since _names["Name1"] != ai1.object_identifier, old entry is kept
        db._update_name_index(ai1.object_identifier, "Name1", "NewName")

        # "Name1" should NOT be deleted because it maps to ai2
        assert "Name1" in db._names
        assert db._names["Name1"] == ai2.object_identifier
        # "NewName" should be set for ai1
        assert db._names["NewName"] == ai1.object_identifier


# ---------------------------------------------------------------------------
# Coverage: register_change_callback when object not in database (branch 836->exit)
# ---------------------------------------------------------------------------


class TestRegisterCallbackObjectNotInDatabase:
    """Branch 836->exit: register_change_callback when obj is None (not found)."""

    def test_register_callback_nonexistent_object(self):
        """Callback is registered in dict but notifier is not wired (no object)."""
        db = ObjectDatabase()
        fake_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 999)

        def cb(pid, old, new):
            pass

        # Object 999 doesn't exist in the database
        db.register_change_callback(fake_id, PropertyIdentifier.PRESENT_VALUE, cb)

        # Callback should still be in the dict
        key = (fake_id, PropertyIdentifier.PRESENT_VALUE)
        assert key in db._change_callbacks
        assert cb in db._change_callbacks[key]

    def test_register_callback_already_has_notifier(self):
        """Branch 836->exit: obj._on_property_written is already set, skip wiring."""
        from bac_py.objects.analog import AnalogValueObject

        db = ObjectDatabase()
        av = AnalogValueObject(1)
        db.add(av)

        def cb1(pid, old, new):
            pass

        def cb2(pid, old, new):
            pass

        # First registration wires the notifier
        db.register_change_callback(av.object_identifier, PropertyIdentifier.PRESENT_VALUE, cb1)
        notifier = av._on_property_written
        assert notifier is not None

        # Second registration should NOT overwrite the notifier
        db.register_change_callback(av.object_identifier, PropertyIdentifier.DESCRIPTION, cb2)
        assert av._on_property_written is notifier  # same object, not replaced
