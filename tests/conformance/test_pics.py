"""Tests for PICS generator per Clause 22 / Annex A."""

from bac_py.conformance.pics import PICSGenerator
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.device import DeviceObject
from bac_py.types.enums import PropertyIdentifier
from bac_py.types.primitives import BitString


def _make_device(**overrides) -> tuple[ObjectDatabase, DeviceObject]:
    """Create a minimal DB + Device for PICS generation."""
    db = ObjectDatabase()
    device = DeviceObject(
        1,
        object_name="test-device",
        vendor_name="TestVendor",
        vendor_identifier=999,
        model_name="TestModel",
        firmware_revision="1.0.0",
        application_software_version="2.0.0",
        **overrides,
    )
    db.add(device)
    return db, device


class TestPICSGeneral:
    def test_generate_returns_dict(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert isinstance(pics, dict)
        assert "general" in pics
        assert "services_supported" in pics
        assert "object_types_supported" in pics
        assert "data_link" in pics
        assert "character_sets" in pics

    def test_general_info(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        general = pics["general"]
        assert general["vendor_name"] == "TestVendor"
        assert general["vendor_identifier"] == 999
        assert general["model_name"] == "TestModel"
        assert general["firmware_revision"] == "1.0.0"
        assert general["application_software_version"] == "2.0.0"
        assert general["protocol_version"] == 1

    def test_max_apdu_length(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert pics["general"]["max_apdu_length_accepted"] == 1476


class TestPICSServicesSupported:
    def test_empty_bitstring_no_services(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        # Default is all zeros
        assert pics["services_supported"]["confirmed"] == []
        assert pics["services_supported"]["unconfirmed"] == []

    def test_read_property_bit_set(self):
        db, device = _make_device()
        # Bit 12 = ReadProperty (confirmed)
        # Build a bitstring with bit 12 set
        buf = bytearray(6)  # 48 bits
        buf[1] |= 0x08  # bit 12 = byte 1, bit index 4 → but 7-4=3 → 0x08
        device._properties[PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED] = (
            BitString(bytes(buf), 0)
        )
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert "READ_PROPERTY" in pics["services_supported"]["confirmed"]


class TestPICSObjectTypesSupported:
    def test_registered_types_always_included(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        obj_types = pics["object_types_supported"]
        # Device is always registered
        assert "DEVICE" in obj_types

    def test_bitstring_types_included(self):
        db, device = _make_device()
        # Bit 0 = ANALOG_INPUT
        buf = bytearray(8)
        buf[0] |= 0x80  # bit 0
        device._properties[PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED] = (
            BitString(bytes(buf), 0)
        )
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert "ANALOG_INPUT" in pics["object_types_supported"]


class TestPICSDataLink:
    def test_data_link_info(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert pics["data_link"]["data_link_layer"] == "BACnet/IP (Annex J)"
        assert pics["data_link"]["max_apdu_length"] == 1476


class TestPICSCharacterSets:
    def test_character_set_info(self):
        db, device = _make_device()
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert "UTF-8" in pics["character_sets"]["character_sets"]
