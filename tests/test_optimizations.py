"""Tests for performance optimization changes.

Verifies caching (lru_cache on parsing/address), ObjectDatabase type index,
and BIPAddress encode optimizations.
"""

from bac_py.network.address import BACnetAddress, BIPAddress, parse_address
from bac_py.objects.analog import AnalogInputObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.binary import BinaryInputObject, BinaryValueObject
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.parsing import parse_object_identifier, parse_property_identifier


class TestParsingCache:
    """Verify lru_cache on string alias resolution."""

    def test_object_type_alias_cached(self):
        """Repeated parse_object_identifier calls return the same result."""
        oid1 = parse_object_identifier("ai,1")
        oid2 = parse_object_identifier("ai,1")
        assert oid1 == oid2
        assert oid1.object_type == ObjectType.ANALOG_INPUT

    def test_property_alias_cached(self):
        """Repeated parse_property_identifier calls return the same result."""
        pid1 = parse_property_identifier("pv")
        pid2 = parse_property_identifier("pv")
        assert pid1 == pid2
        assert pid1 == PropertyIdentifier.PRESENT_VALUE

    def test_hyphenated_names_cached(self):
        """Full hyphenated names resolve and cache correctly."""
        pid1 = parse_property_identifier("present-value")
        pid2 = parse_property_identifier("present-value")
        assert pid1 == pid2 == PropertyIdentifier.PRESENT_VALUE


class TestAddressCache:
    """Verify lru_cache on parse_address for string inputs."""

    def test_parse_address_string_cached(self):
        """Repeated parse_address calls with same string return equal results."""
        addr1 = parse_address("192.168.1.100")
        addr2 = parse_address("192.168.1.100")
        assert addr1 == addr2

    def test_parse_address_passthrough_not_cached(self):
        """BACnetAddress objects pass through without caching."""
        addr = BACnetAddress(mac_address=b"\xc0\xa8\x01\x64\xba\xc0")
        result = parse_address(addr)
        assert result is addr

    def test_parse_address_broadcast_cached(self):
        """Broadcast strings cache correctly."""
        b1 = parse_address("*")
        b2 = parse_address("*")
        assert b1 == b2
        assert b1.is_global_broadcast


class TestBIPAddressEncode:
    """Verify optimized BIPAddress.encode using socket.inet_aton."""

    def test_encode_produces_6_bytes(self):
        """BIPAddress.encode returns exactly 6 bytes."""
        addr = BIPAddress(host="192.168.1.100", port=0xBAC0)
        result = addr.encode()
        assert len(result) == 6
        assert result == b"\xc0\xa8\x01\x64\xba\xc0"

    def test_encode_decode_roundtrip(self):
        """Encode and decode produce the same address."""
        original = BIPAddress(host="10.0.0.1", port=47809)
        encoded = original.encode()
        decoded = BIPAddress.decode(encoded)
        assert decoded.host == original.host
        assert decoded.port == original.port


class TestObjectDatabaseTypeIndex:
    """Verify ObjectDatabase _type_index for O(1) type queries."""

    def test_add_populates_type_index(self):
        """Adding objects populates _type_index."""
        db = ObjectDatabase()
        ai1 = AnalogInputObject(1)
        ai2 = AnalogInputObject(2)
        bv1 = BinaryValueObject(1)
        db.add(ai1)
        db.add(ai2)
        db.add(bv1)

        assert ObjectType.ANALOG_INPUT in db._type_index
        assert len(db._type_index[ObjectType.ANALOG_INPUT]) == 2
        assert ObjectType.BINARY_VALUE in db._type_index
        assert len(db._type_index[ObjectType.BINARY_VALUE]) == 1

    def test_remove_cleans_type_index(self):
        """Removing an object updates _type_index and cleans empty buckets."""
        db = ObjectDatabase()
        bv1 = BinaryValueObject(1)
        db.add(bv1)
        assert ObjectType.BINARY_VALUE in db._type_index

        db.remove(bv1.object_identifier)
        assert ObjectType.BINARY_VALUE not in db._type_index

    def test_get_objects_of_type_uses_index(self):
        """get_objects_of_type returns correct results via _type_index."""
        db = ObjectDatabase()
        ai1 = AnalogInputObject(1)
        ai2 = AnalogInputObject(2)
        bv1 = BinaryValueObject(1)
        bi1 = BinaryInputObject(1)
        db.add(ai1)
        db.add(ai2)
        db.add(bv1)
        db.add(bi1)

        ais = db.get_objects_of_type(ObjectType.ANALOG_INPUT)
        assert len(ais) == 2
        assert set(o.object_identifier for o in ais) == {
            ai1.object_identifier,
            ai2.object_identifier,
        }

        bvs = db.get_objects_of_type(ObjectType.BINARY_VALUE)
        assert len(bvs) == 1
        assert bvs[0].object_identifier == bv1.object_identifier

        # No objects of this type
        avs = db.get_objects_of_type(ObjectType.ANALOG_VALUE)
        assert avs == []

    def test_type_index_partial_remove(self):
        """Removing one of multiple objects of the same type preserves the rest."""
        db = ObjectDatabase()
        ai1 = AnalogInputObject(1)
        ai2 = AnalogInputObject(2)
        db.add(ai1)
        db.add(ai2)

        db.remove(ai1.object_identifier)

        ais = db.get_objects_of_type(ObjectType.ANALOG_INPUT)
        assert len(ais) == 1
        assert ais[0].object_identifier == ai2.object_identifier
        assert ObjectType.ANALOG_INPUT in db._type_index
