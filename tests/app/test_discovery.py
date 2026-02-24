"""Tests for device discovery: Who-Is, extended discovery, and unconfigured devices."""

from unittest.mock import MagicMock, patch

import pytest

from bac_py.app.client import (
    BACnetClient,
    DeviceAssignmentEntry,
    DeviceAssignmentTable,
    DiscoveredDevice,
    UnconfiguredDevice,
)
from bac_py.encoding.primitives import encode_application_character_string
from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.services.read_property import ReadPropertyACK
from bac_py.services.read_property_multiple import (
    ReadAccessResult,
    ReadPropertyMultipleACK,
    ReadResultElement,
)
from bac_py.services.who_is import IAmRequest
from bac_py.types.enums import (
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    Segmentation,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import ObjectIdentifier

PEER_MAC = BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
PEER = BACnetAddress(mac_address=PEER_MAC)


def _encode_oid_list(oids: list[ObjectIdentifier]) -> bytes:
    """Encode a list of ObjectIdentifiers as concatenated application-tagged bytes."""
    from bac_py.encoding.primitives import encode_application_object_id

    return b"".join(encode_application_object_id(o.object_type, o.instance_number) for o in oids)


def _base_device(instance: int = 100, address: BACnetAddress = PEER) -> DiscoveredDevice:
    return DiscoveredDevice(
        address=address,
        instance=instance,
        vendor_id=42,
        max_apdu_length=1476,
        segmentation_supported=Segmentation.BOTH,
    )


# ---------------------------------------------------------------------------
# DiscoveredDevice dataclass
# ---------------------------------------------------------------------------


class TestDiscoveredDevice:
    def test_basic_fields(self):
        dev = _base_device(100)
        assert dev.instance == 100
        assert dev.vendor_id == 42
        assert dev.max_apdu_length == 1476
        assert dev.segmentation_supported == Segmentation.BOTH
        assert dev.address is PEER

    def test_address_str(self):
        dev = _base_device(100)
        assert dev.address_str == "192.168.1.100:47808"

    def test_address_str_with_network(self):
        addr = BACnetAddress(network=5, mac_address=PEER_MAC)
        dev = DiscoveredDevice(
            address=addr,
            instance=200,
            vendor_id=1,
            max_apdu_length=480,
            segmentation_supported=Segmentation.NONE,
        )
        assert dev.address_str == "5:192.168.1.100:47808"

    def test_repr(self):
        dev = _base_device(100)
        assert repr(dev) == "DiscoveredDevice(instance=100, address='192.168.1.100:47808')"

    def test_frozen(self):
        dev = _base_device(100)
        with pytest.raises(AttributeError):
            dev.instance = 200  # type: ignore[misc]

    def test_equality(self):
        dev1 = _base_device(100)
        dev2 = _base_device(100)
        assert dev1 == dev2

    def test_default_extended_fields_none(self):
        """Extended discovery fields default to None."""
        dev = _base_device()
        assert dev.profile_name is None
        assert dev.profile_location is None
        assert dev.tags is None


# ---------------------------------------------------------------------------
# discover() — Who-Is / I-Am
# ---------------------------------------------------------------------------


class TestDiscover:
    def _make_app(self):
        app = MagicMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    def _make_iam(self, instance: int, vendor_id: int = 42) -> IAmRequest:
        return IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, instance),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=vendor_id,
        )

    async def test_discover_returns_discovered_devices(self):
        app = self._make_app()
        client = BACnetClient(app)

        iam1 = self._make_iam(100)
        iam2 = self._make_iam(200, vendor_id=99)
        source1 = BACnetAddress(mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode())
        source2 = BACnetAddress(mac_address=BIPAddress(host="192.168.1.200", port=0xBAC0).encode())

        def capture_handler(service_choice, handler):
            handler(iam1.encode(), source1)
            handler(iam2.encode(), source2)

        app.register_temporary_handler.side_effect = capture_handler

        devices = await client.discover(timeout=0.01)
        assert len(devices) == 2

        assert isinstance(devices[0], DiscoveredDevice)
        assert devices[0].instance == 100
        assert devices[0].vendor_id == 42
        assert devices[0].max_apdu_length == 1476
        assert devices[0].segmentation_supported == Segmentation.BOTH
        assert devices[0].address == source1
        assert devices[0].address_str == "192.168.1.100:47808"

        assert devices[1].instance == 200
        assert devices[1].vendor_id == 99
        assert devices[1].address == source2

    async def test_discover_with_limits(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.discover(low_limit=100, high_limit=200, timeout=0.01)
        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args.kwargs
        assert call_kwargs["service_choice"] == UnconfirmedServiceChoice.WHO_IS
        from bac_py.services.who_is import WhoIsRequest

        req = WhoIsRequest.decode(call_kwargs["service_data"])
        assert req.low_limit == 100
        assert req.high_limit == 200

    async def test_discover_no_responses(self):
        app = self._make_app()
        client = BACnetClient(app)

        devices = await client.discover(timeout=0.01)
        assert devices == []

    async def test_discover_handler_registered_and_unregistered(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.discover(timeout=0.01)
        app.register_temporary_handler.assert_called_once()
        reg_args = app.register_temporary_handler.call_args
        assert reg_args[0][0] == UnconfirmedServiceChoice.I_AM

        app.unregister_temporary_handler.assert_called_once()
        unreg_args = app.unregister_temporary_handler.call_args
        assert unreg_args[0][0] == UnconfirmedServiceChoice.I_AM

    async def test_discover_drops_malformed_iam(self):
        app = self._make_app()
        client = BACnetClient(app)

        def capture_handler(service_choice, handler):
            valid_iam = self._make_iam(100)
            source = BACnetAddress(
                mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
            )
            handler(valid_iam.encode(), source)
            handler(b"\xff\xff", source)  # malformed

        app.register_temporary_handler.side_effect = capture_handler

        devices = await client.discover(timeout=0.01)
        assert len(devices) == 1
        assert devices[0].instance == 100

    async def test_who_is_still_returns_iam_requests(self):
        """Verify the original who_is() method still works and returns IAmRequest."""
        app = self._make_app()
        client = BACnetClient(app)

        iam = self._make_iam(100)
        source = BACnetAddress(mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode())

        def capture_handler(service_choice, handler):
            handler(iam.encode(), source)

        app.register_temporary_handler.side_effect = capture_handler

        responses = await client.who_is(timeout=0.01)
        assert len(responses) == 1
        assert isinstance(responses[0], IAmRequest)
        assert responses[0].object_identifier.instance_number == 100


# ---------------------------------------------------------------------------
# discover_extended() — Profile enrichment (Annex X)
# ---------------------------------------------------------------------------


class TestDiscoverExtended:
    async def test_enriches_with_profile_metadata(self):
        """discover_extended() calls discover + RPM to populate profile fields."""
        app = MagicMock()
        client = BACnetClient(app)

        base_dev = _base_device(100)

        async def mock_discover(**kwargs):
            return [base_dev]

        async def mock_rpm(address, specs, timeout=None):
            return ReadPropertyMultipleACK(
                list_of_read_access_results=[
                    ReadAccessResult(
                        object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
                        list_of_results=[
                            ReadResultElement(
                                property_identifier=PropertyIdentifier.PROFILE_NAME,
                                property_value=encode_application_character_string("BACnet-HVAC"),
                            ),
                            ReadResultElement(
                                property_identifier=PropertyIdentifier.PROFILE_LOCATION,
                                property_value=encode_application_character_string(
                                    "https://example.com/profile"
                                ),
                            ),
                            ReadResultElement(
                                property_identifier=PropertyIdentifier.TAGS,
                                property_value=(
                                    encode_application_character_string("floor")
                                    + encode_application_character_string("3")
                                ),
                            ),
                        ],
                    )
                ]
            )

        with (
            patch.object(client, "discover", side_effect=mock_discover),
            patch.object(client, "read_property_multiple", side_effect=mock_rpm),
        ):
            devices = await client.discover_extended(timeout=0.01)

        assert len(devices) == 1
        dev = devices[0]
        assert dev.instance == 100
        assert dev.profile_name == "BACnet-HVAC"
        assert dev.profile_location == "https://example.com/profile"
        assert dev.tags == ["floor", "3"]

    async def test_gracefully_handles_unsupported_properties(self):
        """Devices without profile properties return None for those fields."""
        app = MagicMock()
        client = BACnetClient(app)

        base_dev = _base_device(200)

        async def mock_discover(**kwargs):
            return [base_dev]

        async def mock_rpm(address, specs, timeout=None):
            return ReadPropertyMultipleACK(
                list_of_read_access_results=[
                    ReadAccessResult(
                        object_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
                        list_of_results=[
                            ReadResultElement(
                                property_identifier=PropertyIdentifier.PROFILE_NAME,
                                property_access_error=(
                                    ErrorClass.PROPERTY,
                                    ErrorCode.UNKNOWN_PROPERTY,
                                ),
                            ),
                            ReadResultElement(
                                property_identifier=PropertyIdentifier.PROFILE_LOCATION,
                                property_access_error=(
                                    ErrorClass.PROPERTY,
                                    ErrorCode.UNKNOWN_PROPERTY,
                                ),
                            ),
                            ReadResultElement(
                                property_identifier=PropertyIdentifier.TAGS,
                                property_access_error=(
                                    ErrorClass.PROPERTY,
                                    ErrorCode.UNKNOWN_PROPERTY,
                                ),
                            ),
                        ],
                    )
                ]
            )

        with (
            patch.object(client, "discover", side_effect=mock_discover),
            patch.object(client, "read_property_multiple", side_effect=mock_rpm),
        ):
            devices = await client.discover_extended(timeout=0.01)

        assert len(devices) == 1
        dev = devices[0]
        assert dev.instance == 200
        assert dev.profile_name is None
        assert dev.profile_location is None
        assert dev.tags is None

    async def test_handles_rpm_timeout(self):
        """If RPM times out, profile fields are None but device is still returned."""
        app = MagicMock()
        client = BACnetClient(app)

        base_dev = _base_device(300)

        async def mock_discover(**kwargs):
            return [base_dev]

        async def mock_rpm(address, specs, timeout=None):
            raise TimeoutError("RPM timed out")

        with (
            patch.object(client, "discover", side_effect=mock_discover),
            patch.object(client, "read_property_multiple", side_effect=mock_rpm),
        ):
            devices = await client.discover_extended(timeout=0.01)

        assert len(devices) == 1
        assert devices[0].profile_name is None


# ---------------------------------------------------------------------------
# traverse_hierarchy() — Structured View traversal
# ---------------------------------------------------------------------------


class TestTraverseHierarchy:
    async def test_reads_subordinate_list(self):
        """traverse_hierarchy reads SUBORDINATE_LIST from root."""
        app = MagicMock()
        client = BACnetClient(app)

        ai1 = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        ai2 = ObjectIdentifier(ObjectType.ANALOG_INPUT, 2)

        async def mock_read_prop(address, obj_id, prop_id, timeout=None):
            return ReadPropertyACK(
                object_identifier=obj_id,
                property_identifier=prop_id,
                property_value=_encode_oid_list([ai1, ai2]),
            )

        root = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        with patch.object(client, "read_property", side_effect=mock_read_prop):
            result = await client.traverse_hierarchy(PEER, root)

        assert ai1 in result
        assert ai2 in result
        assert len(result) == 2

    async def test_recurses_through_nested_views(self):
        """traverse_hierarchy descends into nested Structured View objects."""
        app = MagicMock()
        client = BACnetClient(app)

        sv1 = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        sv2 = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 2)
        ai1 = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        bi1 = ObjectIdentifier(ObjectType.BINARY_INPUT, 1)

        async def mock_read_prop(address, obj_id, prop_id, timeout=None):
            if obj_id == sv1:
                return ReadPropertyACK(
                    object_identifier=obj_id,
                    property_identifier=prop_id,
                    property_value=_encode_oid_list([sv2, ai1]),
                )
            elif obj_id == sv2:
                return ReadPropertyACK(
                    object_identifier=obj_id,
                    property_identifier=prop_id,
                    property_value=_encode_oid_list([bi1]),
                )
            return ReadPropertyACK(
                object_identifier=obj_id,
                property_identifier=prop_id,
                property_value=b"",
            )

        with patch.object(client, "read_property", side_effect=mock_read_prop):
            result = await client.traverse_hierarchy(PEER, sv1)

        assert sv2 in result
        assert ai1 in result
        assert bi1 in result
        assert len(result) == 3

    async def test_respects_max_depth(self):
        """traverse_hierarchy stops at max_depth."""
        app = MagicMock()
        client = BACnetClient(app)

        sv1 = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        sv2 = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 2)

        async def mock_read_prop(address, obj_id, prop_id, timeout=None):
            if obj_id == sv1:
                return ReadPropertyACK(
                    object_identifier=obj_id,
                    property_identifier=prop_id,
                    property_value=_encode_oid_list([sv2]),
                )
            return ReadPropertyACK(
                object_identifier=obj_id,
                property_identifier=prop_id,
                property_value=_encode_oid_list([ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)]),
            )

        with patch.object(client, "read_property", side_effect=mock_read_prop):
            result = await client.traverse_hierarchy(PEER, sv1, max_depth=1)

        assert sv2 in result
        assert ObjectIdentifier(ObjectType.ANALOG_INPUT, 1) not in result

    async def test_handles_empty_subordinate_list(self):
        """traverse_hierarchy handles Structured View with no subordinates."""
        app = MagicMock()
        client = BACnetClient(app)

        async def mock_read_prop(address, obj_id, prop_id, timeout=None):
            return ReadPropertyACK(
                object_identifier=obj_id,
                property_identifier=prop_id,
                property_value=b"",
            )

        sv = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        with patch.object(client, "read_property", side_effect=mock_read_prop):
            result = await client.traverse_hierarchy(PEER, sv)

        assert result == []

    async def test_handles_read_error(self):
        """traverse_hierarchy gracefully handles read failures."""
        from bac_py.services.errors import BACnetError

        app = MagicMock()
        client = BACnetClient(app)

        async def mock_read_prop(address, obj_id, prop_id, timeout=None):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        sv = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        with patch.object(client, "read_property", side_effect=mock_read_prop):
            result = await client.traverse_hierarchy(PEER, sv)

        assert result == []

    async def test_prevents_cycles(self):
        """traverse_hierarchy doesn't loop on circular references."""
        app = MagicMock()
        client = BACnetClient(app)

        sv1 = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        sv2 = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 2)

        async def mock_read_prop(address, obj_id, prop_id, timeout=None):
            if obj_id == sv1:
                return ReadPropertyACK(
                    object_identifier=obj_id,
                    property_identifier=prop_id,
                    property_value=_encode_oid_list([sv2]),
                )
            else:
                return ReadPropertyACK(
                    object_identifier=obj_id,
                    property_identifier=prop_id,
                    property_value=_encode_oid_list([sv1]),
                )

        with patch.object(client, "read_property", side_effect=mock_read_prop):
            result = await client.traverse_hierarchy(PEER, sv1)

        assert sv2 in result
        assert sv1 in result


# ---------------------------------------------------------------------------
# Unconfigured device discovery (Clause 19.7)
# ---------------------------------------------------------------------------


class TestUnconfiguredDevice:
    def test_dataclass(self):
        dev = UnconfiguredDevice(
            address=BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0"),
            vendor_id=999,
            model_name="TestModel",
            serial_number="SN-001",
        )
        assert dev.vendor_id == 999
        assert dev.model_name == "TestModel"
        assert dev.serial_number == "SN-001"


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
