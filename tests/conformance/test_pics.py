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
        device._properties[PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED] = BitString(
            bytes(buf), 0
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
        device._properties[PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED] = BitString(
            bytes(buf), 0
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


# --- Coverage gap tests: lines 145, 136->147, 159->165 ---


class TestPICSCoverageGaps:
    def test_unconfirmed_service_bits_set(self):
        """Line 145: Exercise the unconfirmed service bits loop with actual bits set.

        Unconfirmed services start at bit 40 in the bitstring, so I_AM (bit 0
        in the _UNCONFIRMED_SERVICE_BITS mapping) is at actual bit 40.
        """
        db, device = _make_device()
        # Build a BitString with bit 40 set (I_AM) and bit 48 set (WHO_IS)
        # Bit 40 = byte 5, bit index 0 within that byte => MSB-first: 7-0=7 => 0x80
        # Bit 48 = byte 6, bit index 0 => 0x80
        buf = bytearray(8)  # 64 bits total
        buf[5] |= 0x80  # bit 40 -> I_AM
        buf[6] |= 0x80  # bit 48 -> WHO_IS
        device._properties[PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED] = BitString(
            bytes(buf), 0
        )
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert "I_AM" in pics["services_supported"]["unconfirmed"]
        assert "WHO_IS" in pics["services_supported"]["unconfirmed"]

    def test_bitstring_boundary_bit_out_of_range(self):
        """_bitstring_bit_set returns False for bits beyond the BitString length."""
        from bac_py.conformance.pics import _bitstring_bit_set

        # Short bitstring with only 8 bits
        bs = BitString(b"\xff", 0)
        assert len(bs) == 8
        # Bit 8 is out of range
        assert _bitstring_bit_set(bs, 8) is False
        # Negative bit is out of range
        assert _bitstring_bit_set(bs, -1) is False

    def test_bitstring_bit_set_returns_true_for_set_bit(self):
        """_bitstring_bit_set returns True for a set bit."""
        from bac_py.conformance.pics import _bitstring_bit_set

        bs = BitString(b"\x80", 0)  # Bit 0 set
        assert _bitstring_bit_set(bs, 0) is True
        assert _bitstring_bit_set(bs, 1) is False

    def test_object_types_fallback_from_registry(self):
        """Branch 159->165: _OBJECT_REGISTRY types included when not in bitstring.

        Object types from the registry are appended even when they are not
        present in the Protocol_Object_Types_Supported bitstring.
        """
        db, device = _make_device()
        # Set a bitstring that only covers a few types (e.g., bit 0 = ANALOG_INPUT)
        # but the registry will also include other types like DEVICE
        buf = bytearray(8)
        buf[0] |= 0x80  # bit 0 = ANALOG_INPUT
        device._properties[PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED] = BitString(
            bytes(buf), 0
        )
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        obj_types = pics["object_types_supported"]
        # ANALOG_INPUT from bitstring
        assert "ANALOG_INPUT" in obj_types
        # DEVICE from _OBJECT_REGISTRY (it's always registered), but not in bitstring bit 8
        assert "DEVICE" in obj_types

    def test_empty_services_no_bitstring(self):
        """When Protocol_Services_Supported is not a BitString, no services are returned."""
        db, device = _make_device()
        # Set it to None or a non-BitString value
        device._properties[PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED] = None
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert pics["services_supported"]["confirmed"] == []
        assert pics["services_supported"]["unconfirmed"] == []

    def test_short_bitstring_unconfirmed_out_of_range(self):
        """When bitstring is too short to contain unconfirmed service bits, they are skipped."""
        db, device = _make_device()
        # Only 3 bytes = 24 bits. Unconfirmed bits start at 40, so all are out of range.
        buf = bytearray(3)
        buf[1] |= 0x08  # bit 12 = READ_PROPERTY (confirmed)
        device._properties[PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED] = BitString(
            bytes(buf), 0
        )
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        assert "READ_PROPERTY" in pics["services_supported"]["confirmed"]
        # No unconfirmed services because bitstring is too short
        assert pics["services_supported"]["unconfirmed"] == []

    def test_object_types_no_bitstring_uses_registry_only(self):
        """Branch 159->165: Non-BitString falls back to registry types only."""
        db, device = _make_device()
        # Override the default BitString with a non-BitString value
        device._properties[PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED] = None
        gen = PICSGenerator(db, device)
        pics = gen.generate()
        obj_types = pics["object_types_supported"]
        # Should still include types from the registry (DEVICE at minimum)
        assert "DEVICE" in obj_types
