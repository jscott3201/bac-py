"""Phase 6 validation tests: Missing object types.

Tests verify new object types are properly registered with correct
OBJECT_TYPE, default property values, and basic read/write behavior.
"""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.channel import ChannelObject
from bac_py.objects.life_safety import LifeSafetyPointObject, LifeSafetyZoneObject
from bac_py.objects.network_port import NetworkPortObject
from bac_py.objects.value_types import (
    DatePatternValueObject,
    DateTimePatternValueObject,
    DateValueObject,
    TimePatternValueObject,
    TimeValueObject,
)
from bac_py.types.enums import (
    IPMode,
    LifeSafetyMode,
    LifeSafetyState,
    NetworkNumberQuality,
    NetworkPortCommand,
    NetworkType,
    ObjectType,
    PropertyIdentifier,
    ProtocolLevel,
    SilencedState,
    WriteStatus,
)
from bac_py.types.primitives import BACnetDate, BACnetTime


# ---------------------------------------------------------------------------
# Date/Time value object variants
# ---------------------------------------------------------------------------
class TestDateValueObject:
    """DateValue object (Clause 12.38)."""

    def test_object_type(self):
        obj = DateValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.DATE_VALUE

    def test_registry_creation(self):
        obj = create_object(ObjectType.DATE_VALUE, 1)
        assert isinstance(obj, DateValueObject)

    def test_present_value_write(self):
        obj = DateValueObject(1)
        date = BACnetDate(2024, 6, 15, 6)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, date)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == date

    def test_commandable(self):
        obj = DateValueObject(1, commandable=True)
        date = BACnetDate(2024, 1, 1, 1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, date, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == date


class TestDatePatternValueObject:
    """DatePatternValue object (Clause 12.39)."""

    def test_object_type(self):
        obj = DatePatternValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.DATEPATTERN_VALUE

    def test_wildcard_date(self):
        obj = DatePatternValueObject(1)
        # Wildcard date pattern (any year, any month, day 1)
        pattern = BACnetDate(0xFF, 0xFF, 1, 0xFF)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, pattern)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == pattern


class TestTimeValueObject:
    """TimeValue object (Clause 12.46)."""

    def test_object_type(self):
        obj = TimeValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.TIME_VALUE

    def test_present_value_write(self):
        obj = TimeValueObject(1)
        time = BACnetTime(14, 30, 0, 0)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, time)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == time

    def test_commandable(self):
        obj = TimeValueObject(1, commandable=True)
        time = BACnetTime(8, 0, 0, 0)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, time, priority=16)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == time


class TestTimePatternValueObject:
    """TimePatternValue object (Clause 12.47)."""

    def test_object_type(self):
        obj = TimePatternValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.TIMEPATTERN_VALUE

    def test_wildcard_time(self):
        obj = TimePatternValueObject(1)
        pattern = BACnetTime(0xFF, 30, 0xFF, 0xFF)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, pattern)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == pattern


class TestDateTimePatternValueObject:
    """DateTimePatternValue object (Clause 12.41)."""

    def test_object_type(self):
        obj = DateTimePatternValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.DATETIMEPATTERN_VALUE

    def test_registry_creation(self):
        obj = create_object(ObjectType.DATETIMEPATTERN_VALUE, 1)
        assert isinstance(obj, DateTimePatternValueObject)


# ---------------------------------------------------------------------------
# NetworkPort object
# ---------------------------------------------------------------------------
class TestNetworkPortObject:
    """NetworkPort object (Clause 12.56)."""

    def test_object_type(self):
        obj = NetworkPortObject(1)
        assert obj.OBJECT_TYPE == ObjectType.NETWORK_PORT

    def test_registry_creation(self):
        obj = create_object(ObjectType.NETWORK_PORT, 1)
        assert isinstance(obj, NetworkPortObject)

    def test_default_network_type(self):
        obj = NetworkPortObject(1)
        assert obj.read_property(PropertyIdentifier.NETWORK_TYPE) == NetworkType.IPV4

    def test_custom_network_type(self):
        obj = NetworkPortObject(1, network_type=NetworkType.MSTP)
        assert obj.read_property(PropertyIdentifier.NETWORK_TYPE) == NetworkType.MSTP

    def test_default_protocol_level(self):
        obj = NetworkPortObject(1)
        level = obj.read_property(PropertyIdentifier.PROTOCOL_LEVEL)
        assert level == ProtocolLevel.BACNET_APPLICATION

    def test_default_network_number(self):
        obj = NetworkPortObject(1)
        assert obj.read_property(PropertyIdentifier.NETWORK_NUMBER) == 0

    def test_network_number_writable(self):
        obj = NetworkPortObject(1)
        obj.write_property(PropertyIdentifier.NETWORK_NUMBER, 100)
        assert obj.read_property(PropertyIdentifier.NETWORK_NUMBER) == 100

    def test_default_network_number_quality(self):
        obj = NetworkPortObject(1)
        quality = obj.read_property(PropertyIdentifier.NETWORK_NUMBER_QUALITY)
        assert quality == NetworkNumberQuality.UNKNOWN

    def test_default_changes_pending(self):
        obj = NetworkPortObject(1)
        assert obj.read_property(PropertyIdentifier.CHANGES_PENDING) is False

    def test_default_command(self):
        obj = NetworkPortObject(1)
        cmd = obj.read_property(PropertyIdentifier.COMMAND)
        assert cmd == NetworkPortCommand.IDLE

    def test_command_writable(self):
        obj = NetworkPortObject(1)
        obj.write_property(PropertyIdentifier.COMMAND, NetworkPortCommand.RESTART_PORT)
        assert obj.read_property(PropertyIdentifier.COMMAND) == NetworkPortCommand.RESTART_PORT

    def test_default_apdu_length(self):
        obj = NetworkPortObject(1)
        assert obj.read_property(PropertyIdentifier.APDU_LENGTH) == 1476

    def test_bacnet_ip_mode_writable(self):
        obj = NetworkPortObject(1)
        obj.write_property(PropertyIdentifier.BACNET_IP_MODE, IPMode.BBMD)
        assert obj.read_property(PropertyIdentifier.BACNET_IP_MODE) == IPMode.BBMD

    def test_ip_address_writable(self):
        obj = NetworkPortObject(1)
        addr = bytes([192, 168, 1, 100])
        obj.write_property(PropertyIdentifier.IP_ADDRESS, addr)
        assert obj.read_property(PropertyIdentifier.IP_ADDRESS) == addr

    def test_bacnet_ip_udp_port_writable(self):
        obj = NetworkPortObject(1)
        obj.write_property(PropertyIdentifier.BACNET_IP_UDP_PORT, 47808)
        assert obj.read_property(PropertyIdentifier.BACNET_IP_UDP_PORT) == 47808

    def test_enum_coercion_on_command(self):
        """Raw int from wire should be coerced to NetworkPortCommand."""
        obj = NetworkPortObject(1)
        obj.write_property(PropertyIdentifier.COMMAND, 7)  # raw int for RESTART_PORT
        cmd = obj.read_property(PropertyIdentifier.COMMAND)
        assert isinstance(cmd, NetworkPortCommand)
        assert cmd == NetworkPortCommand.RESTART_PORT


# ---------------------------------------------------------------------------
# Channel object
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# LifeSafetyPoint object
# ---------------------------------------------------------------------------
class TestLifeSafetyPointObject:
    """LifeSafetyPoint object (Clause 12.15)."""

    def test_object_type(self):
        obj = LifeSafetyPointObject(1)
        assert obj.OBJECT_TYPE == ObjectType.LIFE_SAFETY_POINT

    def test_registry_creation(self):
        obj = create_object(ObjectType.LIFE_SAFETY_POINT, 1)
        assert isinstance(obj, LifeSafetyPointObject)

    def test_default_present_value(self):
        obj = LifeSafetyPointObject(1)
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == LifeSafetyState.QUIET
        assert isinstance(pv, LifeSafetyState)

    def test_default_tracking_value(self):
        obj = LifeSafetyPointObject(1)
        tv = obj.read_property(PropertyIdentifier.TRACKING_VALUE)
        assert tv == LifeSafetyState.QUIET

    def test_default_mode(self):
        obj = LifeSafetyPointObject(1)
        mode = obj.read_property(PropertyIdentifier.MODE)
        assert mode == LifeSafetyMode.ON

    def test_mode_writable(self):
        obj = LifeSafetyPointObject(1)
        obj.write_property(PropertyIdentifier.MODE, LifeSafetyMode.TEST)
        assert obj.read_property(PropertyIdentifier.MODE) == LifeSafetyMode.TEST

    def test_default_silenced(self):
        obj = LifeSafetyPointObject(1)
        assert obj.read_property(PropertyIdentifier.SILENCED) == SilencedState.UNSILENCED

    def test_present_value_writable_when_oos(self):
        obj = LifeSafetyPointObject(1)
        obj.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, LifeSafetyState.ALARM)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == LifeSafetyState.ALARM

    def test_enum_coercion_on_mode(self):
        """Raw int from wire should be coerced to LifeSafetyMode."""
        obj = LifeSafetyPointObject(1)
        obj.write_property(PropertyIdentifier.MODE, 2)  # raw int for TEST
        mode = obj.read_property(PropertyIdentifier.MODE)
        assert isinstance(mode, LifeSafetyMode)
        assert mode == LifeSafetyMode.TEST


# ---------------------------------------------------------------------------
# LifeSafetyZone object
# ---------------------------------------------------------------------------
class TestLifeSafetyZoneObject:
    """LifeSafetyZone object (Clause 12.16)."""

    def test_object_type(self):
        obj = LifeSafetyZoneObject(1)
        assert obj.OBJECT_TYPE == ObjectType.LIFE_SAFETY_ZONE

    def test_registry_creation(self):
        obj = create_object(ObjectType.LIFE_SAFETY_ZONE, 1)
        assert isinstance(obj, LifeSafetyZoneObject)

    def test_default_present_value(self):
        obj = LifeSafetyZoneObject(1)
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == LifeSafetyState.QUIET

    def test_zone_members_default(self):
        obj = LifeSafetyZoneObject(1)
        members = obj.read_property(PropertyIdentifier.ZONE_MEMBERS)
        assert members == []

    def test_mode_writable(self):
        obj = LifeSafetyZoneObject(1)
        obj.write_property(PropertyIdentifier.MODE, LifeSafetyMode.ARMED)
        assert obj.read_property(PropertyIdentifier.MODE) == LifeSafetyMode.ARMED


# ---------------------------------------------------------------------------
# All new types in registry
# ---------------------------------------------------------------------------
class TestPhase6Registry:
    """Verify all Phase 6 types are registered in the factory."""

    @pytest.mark.parametrize(
        "obj_type",
        [
            ObjectType.DATE_VALUE,
            ObjectType.DATEPATTERN_VALUE,
            ObjectType.TIME_VALUE,
            ObjectType.TIMEPATTERN_VALUE,
            ObjectType.DATETIMEPATTERN_VALUE,
            ObjectType.NETWORK_PORT,
            ObjectType.CHANNEL,
            ObjectType.LIFE_SAFETY_POINT,
            ObjectType.LIFE_SAFETY_ZONE,
        ],
    )
    def test_type_registered(self, obj_type):
        obj = create_object(obj_type, 1)
        assert obj_type == obj.OBJECT_TYPE
        assert obj.object_identifier.object_type == obj_type
        assert obj.object_identifier.instance_number == 1
