"""Tests for the BACnet Command object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestCommandObject:
    def test_instantiation(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.OBJECT_TYPE == ObjectType.COMMAND
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0
        assert obj.read_property(PropertyIdentifier.IN_PROCESS) is False
        assert obj.read_property(PropertyIdentifier.ALL_WRITES_SUCCESSFUL) is True

    def test_write_present_value(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 1)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 1
