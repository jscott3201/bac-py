"""Tests for the BACnet NetworkPort object."""

from bac_py.objects.base import create_object
from bac_py.objects.network_port import NetworkPortObject
from bac_py.types.enums import (
    IPMode,
    NetworkNumberQuality,
    NetworkPortCommand,
    NetworkType,
    ObjectType,
    PropertyIdentifier,
    ProtocolLevel,
)


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
