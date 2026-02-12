"""Tests for unconfigured device discovery (Clause 19.7)."""

from bac_py.app.client import (
    DeviceAssignmentEntry,
    DeviceAssignmentTable,
    UnconfiguredDevice,
)
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestDeviceAssignmentTable:
    def test_add_and_lookup(self):
        table = DeviceAssignmentTable()
        entry = DeviceAssignmentEntry(
            vendor_id=999,
            serial_number="SN-001",
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            device_mac_address=b"\xc0\xa8\x01\x64\xba\xc0",
        )
        table.add(entry)

        result = table.lookup(999, "SN-001")
        assert result is not None
        assert result.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)

    def test_lookup_not_found(self):
        table = DeviceAssignmentTable()
        assert table.lookup(999, "UNKNOWN") is None

    def test_remove(self):
        table = DeviceAssignmentTable()
        entry = DeviceAssignmentEntry(
            vendor_id=999,
            serial_number="SN-001",
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            device_mac_address=b"\x01\x02\x03\x04",
        )
        table.add(entry)
        assert len(table) == 1

        table.remove(999, "SN-001")
        assert len(table) == 0
        assert table.lookup(999, "SN-001") is None

    def test_remove_nonexistent(self):
        table = DeviceAssignmentTable()
        table.remove(1, "nope")  # should not raise

    def test_update_existing(self):
        table = DeviceAssignmentTable()
        entry1 = DeviceAssignmentEntry(
            vendor_id=999,
            serial_number="SN-001",
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            device_mac_address=b"\x01\x02\x03\x04",
        )
        entry2 = DeviceAssignmentEntry(
            vendor_id=999,
            serial_number="SN-001",
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            device_mac_address=b"\x05\x06\x07\x08",
        )
        table.add(entry1)
        table.add(entry2)

        assert len(table) == 1
        result = table.lookup(999, "SN-001")
        assert result.device_identifier.instance_number == 200

    def test_multiple_entries(self):
        table = DeviceAssignmentTable()
        for i in range(5):
            table.add(
                DeviceAssignmentEntry(
                    vendor_id=999,
                    serial_number=f"SN-{i:03d}",
                    device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100 + i),
                    device_mac_address=b"\x01\x02\x03\x04",
                )
            )
        assert len(table) == 5

    def test_with_network_number(self):
        table = DeviceAssignmentTable()
        entry = DeviceAssignmentEntry(
            vendor_id=42,
            serial_number="ABC",
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
            device_mac_address=b"\xaa\xbb",
            device_network_number=5,
        )
        table.add(entry)
        result = table.lookup(42, "ABC")
        assert result.device_network_number == 5


class TestUnconfiguredDevice:
    def test_dataclass(self):
        from bac_py.network.address import BACnetAddress

        dev = UnconfiguredDevice(
            address=BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0"),
            vendor_id=999,
            model_name="TestModel",
            serial_number="SN-001",
        )
        assert dev.vendor_id == 999
        assert dev.model_name == "TestModel"
        assert dev.serial_number == "SN-001"
