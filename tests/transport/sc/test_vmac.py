import pytest

from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID


class TestSCVMACConstruction:
    def test_valid_6_bytes(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        assert vmac.address == b"\x02\x00\x00\x00\x00\x01"

    def test_rejects_too_short(self):
        with pytest.raises(ValueError, match="must be 6 bytes"):
            SCVMAC(b"\x01\x02\x03")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="must be 6 bytes"):
            SCVMAC(b"\x01\x02\x03\x04\x05\x06\x07")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="must be 6 bytes"):
            SCVMAC(b"")

    def test_frozen(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        with pytest.raises(AttributeError):
            vmac.address = b"\x00" * 6  # type: ignore[misc]


class TestSCVMACRandom:
    def test_random_returns_6_bytes(self):
        vmac = SCVMAC.random()
        assert len(vmac.address) == 6

    def test_random_locally_administered_bit(self):
        vmac = SCVMAC.random()
        assert vmac.address[0] & 0x02 == 0x02  # bit 1 set

    def test_random_unicast_bit(self):
        vmac = SCVMAC.random()
        assert vmac.address[0] & 0x01 == 0x00  # bit 0 clear

    def test_random_uniqueness(self):
        vmacs = {SCVMAC.random().address for _ in range(100)}
        assert len(vmacs) > 90  # overwhelmingly likely


class TestSCVMACBroadcast:
    def test_broadcast_value(self):
        vmac = SCVMAC.broadcast()
        assert vmac.address == b"\xff\xff\xff\xff\xff\xff"

    def test_broadcast_is_broadcast(self):
        assert SCVMAC.broadcast().is_broadcast is True

    def test_non_broadcast(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        assert vmac.is_broadcast is False


class TestSCVMACFromHex:
    def test_no_separator(self):
        vmac = SCVMAC.from_hex("AABBCCDDEEFF")
        assert vmac.address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_colon_separator(self):
        vmac = SCVMAC.from_hex("AA:BB:CC:DD:EE:FF")
        assert vmac.address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_hyphen_separator(self):
        vmac = SCVMAC.from_hex("AA-BB-CC-DD-EE-FF")
        assert vmac.address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_lowercase(self):
        vmac = SCVMAC.from_hex("aabbccddeeff")
        assert vmac.address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="Invalid VMAC hex"):
            SCVMAC.from_hex("AABB")

    def test_invalid_chars(self):
        with pytest.raises(ValueError):
            SCVMAC.from_hex("GGHHIIJJKKLL")


class TestSCVMACUninitialized:
    def test_uninitialized(self):
        vmac = SCVMAC(b"\x00\x00\x00\x00\x00\x00")
        assert vmac.is_uninitialized is True

    def test_not_uninitialized(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        assert vmac.is_uninitialized is False


class TestSCVMACDisplay:
    def test_str(self):
        vmac = SCVMAC(b"\xaa\xbb\xcc\xdd\xee\xff")
        assert str(vmac) == "AA:BB:CC:DD:EE:FF"

    def test_repr(self):
        vmac = SCVMAC(b"\xaa\xbb\xcc\xdd\xee\xff")
        assert repr(vmac) == "SCVMAC('AA:BB:CC:DD:EE:FF')"


class TestSCVMACEquality:
    def test_equal(self):
        a = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        b = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        assert a == b

    def test_not_equal(self):
        a = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        b = SCVMAC(b"\x02\x00\x00\x00\x00\x02")
        assert a != b

    def test_hash_equal(self):
        a = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        b = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        assert hash(a) == hash(b)

    def test_usable_as_dict_key(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        d = {vmac: "test"}
        assert d[SCVMAC(b"\x02\x00\x00\x00\x00\x01")] == "test"


class TestDeviceUUIDConstruction:
    def test_valid_16_bytes(self):
        raw = bytes(range(16))
        u = DeviceUUID(raw)
        assert u.value == raw

    def test_rejects_too_short(self):
        with pytest.raises(ValueError, match="must be 16 bytes"):
            DeviceUUID(b"\x00" * 8)

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="must be 16 bytes"):
            DeviceUUID(b"\x00" * 17)

    def test_frozen(self):
        u = DeviceUUID(b"\x00" * 16)
        with pytest.raises(AttributeError):
            u.value = b"\x01" * 16  # type: ignore[misc]


class TestDeviceUUIDGenerate:
    def test_returns_16_bytes(self):
        u = DeviceUUID.generate()
        assert len(u.value) == 16

    def test_uniqueness(self):
        uuids = {DeviceUUID.generate().value for _ in range(100)}
        assert len(uuids) == 100


class TestDeviceUUIDFromHex:
    def test_plain_hex(self):
        u = DeviceUUID.from_hex("550e8400e29b41d4a716446655440000")
        assert u.value == bytes.fromhex("550e8400e29b41d4a716446655440000")

    def test_with_hyphens(self):
        u = DeviceUUID.from_hex("550e8400-e29b-41d4-a716-446655440000")
        assert u.value == bytes.fromhex("550e8400e29b41d4a716446655440000")

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="Invalid UUID hex"):
            DeviceUUID.from_hex("550e8400")


class TestDeviceUUIDDisplay:
    def test_str(self):
        u = DeviceUUID(bytes.fromhex("550e8400e29b41d4a716446655440000"))
        assert str(u) == "550e8400-e29b-41d4-a716-446655440000"

    def test_repr(self):
        u = DeviceUUID(bytes.fromhex("550e8400e29b41d4a716446655440000"))
        assert repr(u) == "DeviceUUID('550e8400-e29b-41d4-a716-446655440000')"


class TestDeviceUUIDEquality:
    def test_equal(self):
        raw = b"\x01" * 16
        assert DeviceUUID(raw) == DeviceUUID(raw)

    def test_not_equal(self):
        assert DeviceUUID(b"\x01" * 16) != DeviceUUID(b"\x02" * 16)

    def test_hash_equal(self):
        raw = b"\x01" * 16
        assert hash(DeviceUUID(raw)) == hash(DeviceUUID(raw))
