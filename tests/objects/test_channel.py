"""Tests for the BACnet Channel object."""

from bac_py.objects.base import create_object
from bac_py.objects.channel import ChannelObject
from bac_py.types.enums import (
    ObjectType,
    PropertyIdentifier,
    WriteStatus,
)


class TestChannelObject:
    """Channel object (Clause 12.53)."""

    def test_object_type(self):
        obj = ChannelObject(1)
        assert obj.OBJECT_TYPE == ObjectType.CHANNEL

    def test_registry_creation(self):
        obj = create_object(ObjectType.CHANNEL, 1)
        assert isinstance(obj, ChannelObject)

    def test_default_channel_number(self):
        obj = ChannelObject(1, channel_number=5)
        assert obj.read_property(PropertyIdentifier.CHANNEL_NUMBER) == 5

    def test_default_write_status(self):
        obj = ChannelObject(1)
        assert obj.read_property(PropertyIdentifier.WRITE_STATUS) == WriteStatus.IDLE

    def test_control_groups_default(self):
        obj = ChannelObject(1)
        assert obj.read_property(PropertyIdentifier.CONTROL_GROUPS) == []

    def test_present_value_writable(self):
        obj = ChannelObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 42
