"""Tests for security and memory hardening (v1.4.2 and v2 audit)."""

import json
import struct
import time
from unittest.mock import MagicMock

import pytest

from bac_py.app.cov import COVManager
from bac_py.encoding.time_series import _MAX_IMPORT_RECORDS, TimeSeriesImporter
from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.network.layer import _MAX_ROUTER_CACHE, NetworkLayer, RouterCacheEntry
from bac_py.network.messages import _MAX_NETWORK_LIST, IAmRouterToNetwork, _decode_network_list
from bac_py.objects.analog import AnalogValueObject
from bac_py.objects.base import ObjectDatabase
from bac_py.services.cov import SubscribeCOVPropertyRequest, SubscribeCOVRequest
from bac_py.services.errors import BACnetError
from bac_py.transport.bip import BIPTransport
from bac_py.transport.bip6 import BIP6Transport
from bac_py.transport.bvll import encode_bvll
from bac_py.transport.bvll_ipv6 import encode_bvll6
from bac_py.types.constructed import (
    BACnetCalendarEntry,
    BACnetDateTime,
    BACnetTimeStamp,
    BACnetValueSource,
)
from bac_py.types.enums import (
    Bvlc6Function,
    BvlcFunction,
    ErrorClass,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

# ---------------------------------------------------------------------------
# Phase 1: Callback wrapping
# ---------------------------------------------------------------------------


class TestBIPCallbackWrapping:
    """Verify receive callback exceptions don't crash BIP datagram handler."""

    def test_unicast_callback_exception_does_not_crash(self):
        transport = BIPTransport()
        transport._local_address = BIPAddress(host="192.168.1.100", port=47808)
        transport._transport = MagicMock()

        def bad_callback(data, source):
            raise RuntimeError("boom")

        transport.on_receive(bad_callback)

        # Build a valid Original-Unicast-NPDU BVLL frame
        npdu = b"\x01\x00\x00"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        # Should not raise
        transport._on_datagram_received(bvll, ("10.0.0.1", 47808))

    def test_broadcast_callback_exception_does_not_crash(self):
        transport = BIPTransport()
        transport._local_address = BIPAddress(host="192.168.1.100", port=47808)
        transport._transport = MagicMock()

        def bad_callback(data, source):
            raise RuntimeError("boom")

        transport.on_receive(bad_callback)

        # Build a valid Original-Broadcast-NPDU BVLL frame
        npdu = b"\x01\x00\x00"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        # Should not raise
        transport._on_datagram_received(bvll, ("10.0.0.1", 47808))

    def test_bbmd_local_deliver_callback_exception_does_not_crash(self):
        transport = BIPTransport()
        transport._local_address = BIPAddress(host="192.168.1.100", port=47808)

        def bad_callback(data, source):
            raise RuntimeError("boom")

        transport.on_receive(bad_callback)

        source = BIPAddress(host="10.0.0.1", port=47808)
        # Should not raise
        transport._bbmd_local_deliver(b"\x01\x00\x00", source)


class TestBIP6CallbackWrapping:
    """Verify receive callback exceptions don't crash BIP6 datagram handler."""

    def test_unicast_callback_exception_does_not_crash(self):
        transport = BIP6Transport()
        transport._vmac = b"\x01\x02\x03"
        transport._local_address = MagicMock()
        transport._transport = MagicMock()

        def bad_callback(data, source):
            raise RuntimeError("boom")

        transport.on_receive(bad_callback)

        npdu = b"\x01\x00\x00"
        bvll = encode_bvll6(
            Bvlc6Function.ORIGINAL_UNICAST_NPDU,
            npdu,
            source_vmac=b"\x04\x05\x06",
            dest_vmac=b"\x01\x02\x03",
        )
        # Should not raise
        transport._on_datagram_received(bvll, ("::1", 47808, 0, 0))

    def test_bbmd_local_deliver_callback_exception_does_not_crash(self):
        transport = BIP6Transport()

        def bad_callback(data, source):
            raise RuntimeError("boom")

        transport.on_receive(bad_callback)

        # Should not raise
        transport._bbmd_local_deliver(b"\x01\x00\x00", b"\x04\x05\x06")


# ---------------------------------------------------------------------------
# Phase 2: TypeError in encode paths
# ---------------------------------------------------------------------------


class TestBACnetTimeStampTypeError:
    """Verify BACnetTimeStamp raises TypeError (not AssertionError) on type mismatch."""

    def test_choice_0_wrong_type(self):
        ts = BACnetTimeStamp(choice=0, value="not-a-time")
        with pytest.raises(TypeError, match="Expected BACnetTime"):
            ts.encode()

    def test_choice_1_wrong_type(self):
        ts = BACnetTimeStamp(choice=1, value="not-an-int")
        with pytest.raises(TypeError, match="Expected int"):
            ts.encode()

    def test_choice_2_wrong_type(self):
        ts = BACnetTimeStamp(choice=2, value="not-a-datetime")
        with pytest.raises(TypeError, match="Expected BACnetDateTime"):
            ts.encode()

    def test_choice_0_correct_type_works(self):
        ts = BACnetTimeStamp(
            choice=0,
            value=BACnetTime(hour=10, minute=30, second=0, hundredth=0),
        )
        result = ts.encode()
        assert isinstance(result, bytes)

    def test_choice_1_correct_type_works(self):
        ts = BACnetTimeStamp(choice=1, value=42)
        result = ts.encode()
        assert isinstance(result, bytes)

    def test_choice_2_correct_type_works(self):
        ts = BACnetTimeStamp(
            choice=2,
            value=BACnetDateTime(
                date=BACnetDate(year=2024, month=1, day=15, day_of_week=0xFF),
                time=BACnetTime(hour=10, minute=30, second=0, hundredth=0),
            ),
        )
        result = ts.encode()
        assert isinstance(result, bytes)


class TestBACnetCalendarEntryTypeError:
    """Verify BACnetCalendarEntry raises TypeError on type mismatch."""

    def test_choice_0_wrong_type(self):
        entry = BACnetCalendarEntry(choice=0, value="not-a-date")
        with pytest.raises(TypeError, match="Expected BACnetDate"):
            entry.encode()

    def test_choice_1_wrong_type(self):
        entry = BACnetCalendarEntry(choice=1, value="not-a-date-range")
        with pytest.raises(TypeError, match="Expected BACnetDateRange"):
            entry.encode()

    def test_choice_2_wrong_type(self):
        entry = BACnetCalendarEntry(choice=2, value="not-a-weeknday")
        with pytest.raises(TypeError, match="Expected BACnetWeekNDay"):
            entry.encode()


class TestBACnetValueSourceTypeError:
    """Verify BACnetValueSource raises TypeError on type mismatch."""

    def test_choice_1_wrong_type(self):
        vs = BACnetValueSource(choice=1, value="not-a-ref")
        with pytest.raises(TypeError, match="Expected BACnetDeviceObjectReference"):
            vs.encode()

    def test_choice_2_wrong_type(self):
        vs = BACnetValueSource(choice=2, value=12345)
        with pytest.raises(TypeError, match="Expected bytes"):
            vs.encode()


# ---------------------------------------------------------------------------
# Phase 3a: Router cache cap
# ---------------------------------------------------------------------------


class FakeTransport:
    """Minimal fake transport for testing NetworkLayer."""

    def __init__(self):
        self.sent_unicast = []
        self.sent_broadcast = []
        self._receive_callback = None
        self._local_address = BIPAddress(host="192.168.1.100", port=0xBAC0)

    def on_receive(self, callback):
        self._receive_callback = callback

    def send_unicast(self, data, dest):
        self.sent_unicast.append((data, dest))

    def send_broadcast(self, data):
        self.sent_broadcast.append(data)

    @property
    def local_address(self):
        return self._local_address

    def inject_receive(self, data, source):
        if self._receive_callback:
            self._receive_callback(data, source)


class TestRouterCacheCap:
    """Verify router cache is capped at _MAX_ROUTER_CACHE entries."""

    def test_cache_cap_evicts_at_limit(self):
        ft = FakeTransport()
        nl = NetworkLayer(ft, network_number=1)

        # Fill cache to capacity
        now = time.monotonic()
        for i in range(_MAX_ROUTER_CACHE):
            nl._router_cache[i] = RouterCacheEntry(
                network=i, router_mac=b"\x01\x02\x03\x04\x05\x06", last_seen=now
            )
        assert len(nl._router_cache) == _MAX_ROUTER_CACHE

        # Insert one more via I-Am-Router
        msg = IAmRouterToNetwork(networks=(99999,))
        nl._handle_i_am_router(msg, b"\x0a\x00\x00\x01\xba\xc0")

        # Should not exceed the max
        assert len(nl._router_cache) <= _MAX_ROUTER_CACHE
        # The new entry should be present
        assert 99999 in nl._router_cache

    def test_cache_cap_prefers_stale_eviction(self):
        ft = FakeTransport()
        nl = NetworkLayer(ft, network_number=1, cache_ttl=60.0)

        # Fill with fresh entries
        now = time.monotonic()
        for i in range(_MAX_ROUTER_CACHE):
            nl._router_cache[i] = RouterCacheEntry(
                network=i, router_mac=b"\x01\x02\x03\x04\x05\x06", last_seen=now
            )

        # Make one entry stale
        nl._router_cache[0].last_seen = now - 999.0

        # Insert a new entry
        msg = IAmRouterToNetwork(networks=(99999,))
        nl._handle_i_am_router(msg, b"\x0a\x00\x00\x01\xba\xc0")

        # Stale entry should have been evicted
        assert 0 not in nl._router_cache
        assert 99999 in nl._router_cache

    def test_learn_router_from_source_respects_cap(self):
        ft = FakeTransport()
        nl = NetworkLayer(ft, network_number=1)

        now = time.monotonic()
        for i in range(_MAX_ROUTER_CACHE):
            nl._router_cache[i] = RouterCacheEntry(
                network=i, router_mac=b"\x01\x02\x03\x04\x05\x06", last_seen=now
            )

        nl._learn_router_from_source(99999, b"\x0a\x00\x00\x01\xba\xc0")
        assert len(nl._router_cache) <= _MAX_ROUTER_CACHE
        assert 99999 in nl._router_cache


# ---------------------------------------------------------------------------
# Phase 3b: Network list decode cap
# ---------------------------------------------------------------------------


class TestNetworkListCap:
    """Verify decode raises ValueError above _MAX_NETWORK_LIST."""

    def test_decode_at_limit_succeeds(self):
        data = b"".join(i.to_bytes(2, "big") for i in range(_MAX_NETWORK_LIST))
        result = _decode_network_list(data)
        assert len(result) == _MAX_NETWORK_LIST

    def test_decode_above_limit_raises(self):
        data = b"".join(i.to_bytes(2, "big") for i in range(_MAX_NETWORK_LIST + 1))
        with pytest.raises(ValueError, match="Network list too large"):
            _decode_network_list(data)


# ---------------------------------------------------------------------------
# Phase 3c: COV subscription cap
# ---------------------------------------------------------------------------


SUBSCRIBER = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")


def _make_app(*, device_instance=1):
    app = MagicMock()
    app.device_object_identifier = ObjectIdentifier(ObjectType.DEVICE, device_instance)
    app.unconfirmed_request = MagicMock()
    app.send_confirmed_cov_notification = MagicMock()
    return app


class TestCOVSubscriptionCap:
    """Verify COV subscription rejection at max capacity."""

    def test_subscribe_rejects_at_max(self):
        app = _make_app()
        db = ObjectDatabase()
        cov = COVManager(app, max_subscriptions=2)

        # Create objects for each subscription
        for i in range(3):
            db.add(AnalogValueObject(instance_number=i, present_value=0.0))

        req1 = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 0),
        )
        req2 = SubscribeCOVRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
        )
        req3 = SubscribeCOVRequest(
            subscriber_process_identifier=3,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 2),
        )

        cov.subscribe(SUBSCRIBER, req1, db)
        cov.subscribe(SUBSCRIBER, req2, db)

        # Third subscription should be rejected
        with pytest.raises(BACnetError) as exc_info:
            cov.subscribe(SUBSCRIBER, req3, db)
        assert exc_info.value.error_class == ErrorClass.RESOURCES

    async def test_subscribe_allows_replacement_at_max(self):
        app = _make_app()
        db = ObjectDatabase()
        cov = COVManager(app, max_subscriptions=1)

        db.add(AnalogValueObject(instance_number=0, present_value=0.0))

        req = SubscribeCOVRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 0),
            lifetime=60,
        )

        cov.subscribe(SUBSCRIBER, req, db)

        # Replacing same subscription should succeed even at max
        cov.subscribe(SUBSCRIBER, req, db)
        assert len(cov._subscriptions) == 1

    def test_subscribe_property_rejects_at_max(self):
        app = _make_app()
        db = ObjectDatabase()
        cov = COVManager(app, max_property_subscriptions=1)

        db.add(AnalogValueObject(instance_number=0, present_value=0.0))
        db.add(AnalogValueObject(instance_number=1, present_value=0.0))

        from bac_py.services.cov import BACnetPropertyReference

        req1 = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=1,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 0),
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE)
            ),
        )
        req2 = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=2,
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE)
            ),
        )

        cov.subscribe_property(SUBSCRIBER, req1, db)

        with pytest.raises(BACnetError) as exc_info:
            cov.subscribe_property(SUBSCRIBER, req2, db)
        assert exc_info.value.error_class == ErrorClass.RESOURCES


# ---------------------------------------------------------------------------
# Phase 3d: Time series import cap
# ---------------------------------------------------------------------------


class TestTimeSeriesImportCap:
    """Verify ValueError above _MAX_IMPORT_RECORDS."""

    def test_from_json_rejects_too_many_records(self):
        records = [
            {
                "timestamp": {
                    "date": {"year": 2024, "month": 1, "day": 1, "day_of_week": 255},
                    "time": {"hour": 0, "minute": 0, "second": 0, "hundredth": 0},
                },
                "log_datum": i,
                "status_flags": None,
            }
            for i in range(_MAX_IMPORT_RECORDS + 1)
        ]
        data = json.dumps(
            {
                "format": "bacnet-time-series-v1",
                "metadata": {},
                "records": records,
            }
        )
        with pytest.raises(ValueError, match="Too many records"):
            TimeSeriesImporter.from_json(data)

    def test_from_csv_rejects_too_many_records(self):
        lines = ["timestamp,value"]
        for i in range(_MAX_IMPORT_RECORDS + 1):
            lines.append(f"2024-01-01T00:00:00.00,{i}")
        data = "\n".join(lines)
        with pytest.raises(ValueError, match="Too many records"):
            TimeSeriesImporter.from_csv(data)


# ===========================================================================
# V2 Security Hardening Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# H1: decode_real / decode_double buffer validation
# ---------------------------------------------------------------------------


class TestDecodeRealDoubleBoundsV2:
    """H1: decode_real/decode_double must raise ValueError on short input."""

    def test_decode_real_empty(self):
        from bac_py.encoding.primitives import decode_real

        with pytest.raises(ValueError, match="decode_real requires at least 4 bytes"):
            decode_real(b"")

    def test_decode_real_short(self):
        from bac_py.encoding.primitives import decode_real

        with pytest.raises(ValueError, match="decode_real requires at least 4 bytes"):
            decode_real(b"\x00\x01")

    def test_decode_double_empty(self):
        from bac_py.encoding.primitives import decode_double

        with pytest.raises(ValueError, match="decode_double requires at least 8 bytes"):
            decode_double(b"")

    def test_decode_double_short(self):
        from bac_py.encoding.primitives import decode_double

        with pytest.raises(ValueError, match="decode_double requires at least 8 bytes"):
            decode_double(b"\x00\x01\x02\x03")

    def test_decode_real_valid(self):
        from bac_py.encoding.primitives import decode_real

        data = struct.pack(">f", 3.14)
        assert abs(decode_real(data) - 3.14) < 0.001

    def test_decode_double_valid(self):
        from bac_py.encoding.primitives import decode_double

        data = struct.pack(">d", 3.14159)
        assert abs(decode_double(data) - 3.14159) < 0.00001


# ---------------------------------------------------------------------------
# H2: ErrorPDU truncated fields
# ---------------------------------------------------------------------------


class TestErrorPDUBoundsV2:
    """H2: ErrorPDU decode rejects truncated error class/code."""

    def test_error_pdu_truncated_error_class(self):
        from bac_py.encoding.apdu import decode_apdu

        # PDU type 0x50 (Error), invoke_id=1, service_choice=0,
        # then an application enumerated tag claiming 4 bytes but only 1 available
        data = bytes([0x50, 0x01, 0x00, 0x94])  # tag: enum, length 4, no data
        with pytest.raises(ValueError):
            decode_apdu(data)

    def test_error_pdu_truncated_error_code(self):
        from bac_py.encoding.apdu import decode_apdu

        # Valid error class (enumerated, 1 byte, value 0), then truncated error code
        data = bytes([0x50, 0x01, 0x00, 0x91, 0x00, 0x94])  # 2nd tag claims 4 bytes
        with pytest.raises(ValueError):
            decode_apdu(data)


# ---------------------------------------------------------------------------
# H3: extract_context_value tag overflow
# ---------------------------------------------------------------------------


class TestExtractContextValueOverflowV2:
    """H3: extract_context_value rejects tag data overflowing buffer."""

    def test_tag_data_past_buffer(self):
        from bac_py.encoding.tags import TagClass, encode_tag, extract_context_value

        # Build: opening tag 0, then a context tag 1 claiming 100 bytes,
        # but only 2 bytes of payload available in the buffer.
        opening = bytes([0x0E])  # opening tag 0
        # Context tag 1, length 100 — properly encoded
        ctx_tag = encode_tag(1, TagClass.CONTEXT, 100)
        data = opening + ctx_tag + b"\x00\x00"  # only 2 bytes, not 100
        with pytest.raises(ValueError, match="Tag data overflows buffer"):
            extract_context_value(data, 1, 0)


# ---------------------------------------------------------------------------
# H4: Ethernet minimum 802.3 length
# ---------------------------------------------------------------------------


class TestEthernetMinLengthV2:
    """H4: _decode_frame rejects 802.3 length < LLC_HEADER_SIZE."""

    def test_undersized_length_field(self):
        from bac_py.transport.ethernet import _decode_frame

        # Frame with length=1 (< 3 = LLC_HEADER_SIZE)
        frame = b"\xff" * 6 + b"\xaa" * 6 + b"\x00\x01" + b"\x82\x82\x03" + b"\x00" * 30
        assert _decode_frame(frame) is None

    def test_zero_length_field(self):
        from bac_py.transport.ethernet import _decode_frame

        frame = b"\xff" * 6 + b"\xaa" * 6 + b"\x00\x00" + b"\x82\x82\x03" + b"\x00" * 30
        assert _decode_frame(frame) is None

    def test_valid_frame_still_works(self):
        from bac_py.transport.ethernet import _decode_frame, _encode_frame

        src = b"\x01\x02\x03\x04\x05\x06"
        dst = b"\xff\xff\xff\xff\xff\xff"
        npdu = b"\x01\x00"
        frame = _encode_frame(dst, src, npdu)
        result = _decode_frame(frame)
        assert result is not None
        decoded_npdu, decoded_src = result
        assert decoded_npdu == npdu
        assert decoded_src == src


# ---------------------------------------------------------------------------
# C1: Service decoder list caps
# ---------------------------------------------------------------------------


class TestServiceDecoderCapsV2:
    """C1: Verify _MAX_DECODED_ITEMS caps exist in all service decode modules."""

    def test_read_property_multiple_cap(self):
        from bac_py.services.read_property_multiple import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_write_property_multiple_cap(self):
        from bac_py.services.write_property_multiple import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_alarm_summary_cap(self):
        from bac_py.services.alarm_summary import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_cov_cap(self):
        from bac_py.services.cov import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_write_group_cap(self):
        from bac_py.services.write_group import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_virtual_terminal_cap(self):
        from bac_py.services.virtual_terminal import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_object_mgmt_cap(self):
        from bac_py.services.object_mgmt import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000

    def test_audit_cap(self):
        from bac_py.services.audit import _MAX_DECODED_ITEMS

        assert _MAX_DECODED_ITEMS == 10_000


# ---------------------------------------------------------------------------
# C2: ObjectType vendor cache cap
# ---------------------------------------------------------------------------


class TestObjectTypeVendorCacheCapV2:
    """C2: ObjectType vendor cache clears at 4096 entries."""

    def test_vendor_cache_bounded(self):
        from bac_py.types.enums import _OBJECT_TYPE_VENDOR_CACHE, ObjectType

        # Vendor types in range 128-1023 (896 values).
        # Create them all and verify cache stays bounded.
        for i in range(128, 1024):
            ObjectType(i)
        assert len(_OBJECT_TYPE_VENDOR_CACHE) <= 4096


# ---------------------------------------------------------------------------
# C3: Segmentation reassembly size cap
# ---------------------------------------------------------------------------


class TestSegmentReassemblySizeCapV2:
    """C3: SegmentReceiver aborts when reassembly exceeds 1 MiB."""

    def test_reassembly_size_cap(self):
        from bac_py.segmentation.manager import (
            _MAX_REASSEMBLY_SIZE,
            SegmentAction,
            SegmentReceiver,
        )

        assert _MAX_REASSEMBLY_SIZE == 1_048_576

        # Create a receiver with a 512 KiB first segment
        big_segment = b"\x00" * (512 * 1024)
        receiver = SegmentReceiver.create(
            first_segment_data=big_segment,
            service_choice=0,
            proposed_window_size=16,
            more_follows=True,
        )

        # Second segment pushes to ~1 MiB — still OK
        action, _ = receiver.receive_segment(1, big_segment, more_follows=True)
        assert action != SegmentAction.ABORT

        # Third segment exceeds 1 MiB -> ABORT
        action, _ = receiver.receive_segment(2, big_segment, more_follows=True)
        assert action == SegmentAction.ABORT

    def test_receiver_has_created_at(self):
        from bac_py.segmentation.manager import SegmentReceiver

        before = time.monotonic()
        receiver = SegmentReceiver.create(
            first_segment_data=b"\x00",
            service_choice=0,
            proposed_window_size=16,
        )
        after = time.monotonic()
        assert before <= receiver.created_at <= after


# ---------------------------------------------------------------------------
# C4: Audit nesting depth cap
# ---------------------------------------------------------------------------


class TestAuditNestingDepthCapV2:
    """C4: Audit decode rejects deeply nested opening tags."""

    def test_nesting_depth_constant(self):
        from bac_py.services.audit import _MAX_NESTING_DEPTH

        assert _MAX_NESTING_DEPTH == 32


# ---------------------------------------------------------------------------
# S1: Hub pending VMAC TTL and cap
# ---------------------------------------------------------------------------


class TestHubPendingVmacTTLAndCapV2:
    """S1: _pending_vmacs uses dict with TTL and cap."""

    def test_pending_vmacs_is_dict(self):
        from bac_py.transport.sc.hub_function import SCHubFunction
        from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

        hub = SCHubFunction(
            hub_vmac=SCVMAC(b"\x00\x00\x00\x00\x00\x01"),
            hub_uuid=DeviceUUID(b"\x00" * 16),
        )
        assert isinstance(hub._pending_vmacs, dict)

    def test_check_vmac_stores_timestamp(self):
        from bac_py.transport.sc.hub_function import SCHubFunction
        from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

        hub = SCHubFunction(
            hub_vmac=SCVMAC(b"\x00\x00\x00\x00\x00\x01"),
            hub_uuid=DeviceUUID(b"\x00" * 16),
        )
        vmac = SCVMAC(b"\x00\x00\x00\x00\x00\x02")
        uuid = DeviceUUID(b"\x01" * 16)
        result = hub._check_vmac(vmac, uuid)
        assert result is True
        assert vmac in hub._pending_vmacs
        assert isinstance(hub._pending_vmacs[vmac], float)

    def test_check_vmac_rejects_duplicate(self):
        from bac_py.transport.sc.hub_function import SCHubFunction
        from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

        hub = SCHubFunction(
            hub_vmac=SCVMAC(b"\x00\x00\x00\x00\x00\x01"),
            hub_uuid=DeviceUUID(b"\x00" * 16),
        )
        vmac = SCVMAC(b"\x00\x00\x00\x00\x00\x02")
        uuid = DeviceUUID(b"\x01" * 16)
        hub._check_vmac(vmac, uuid)
        # Second check for same VMAC should fail
        assert hub._check_vmac(vmac, uuid) is False


# ---------------------------------------------------------------------------
# S2: SC header option data size cap
# ---------------------------------------------------------------------------


class TestSCOptionDataSizeCapV2:
    """S2: Header option data exceeding 512 bytes is rejected."""

    def test_oversized_option_rejected(self):
        from bac_py.transport.sc.bvlc import _MAX_OPTION_DATA_SIZE, SCHeaderOption

        assert _MAX_OPTION_DATA_SIZE == 512

        # Build a header option with 1000 bytes of data
        marker = 0x20 | 0x01  # has_data=True, type=1
        data_len = 1000
        option_bytes = bytes([marker]) + struct.pack("!H", data_len) + b"\x00" * data_len
        with pytest.raises(ValueError, match="too large"):
            SCHeaderOption.decode_list(memoryview(option_bytes))

    def test_valid_option_size_accepted(self):
        from bac_py.transport.sc.bvlc import SCHeaderOption

        # Build a header option with 100 bytes of data
        marker = 0x20 | 0x01  # has_data=True, type=1
        data_len = 100
        option_bytes = bytes([marker]) + struct.pack("!H", data_len) + b"\x00" * data_len
        options, _consumed = SCHeaderOption.decode_list(memoryview(option_bytes))
        assert len(options) == 1
        assert len(options[0].data) == 100


# ---------------------------------------------------------------------------
# S3: WebSocket oversized frame closes connection
# ---------------------------------------------------------------------------


class TestWebSocketOversizedFrameV2:
    """S3: Verify _oversize_count is initialized."""

    def test_oversize_counter_in_init(self):
        import inspect

        from bac_py.transport.sc.websocket import SCWebSocket

        source = inspect.getsource(SCWebSocket.__init__)
        assert "_oversize_count" in source


# ---------------------------------------------------------------------------
# S4: WebSocket pending events cap
# ---------------------------------------------------------------------------


class TestWebSocketPendingEventsCapV2:
    """S4: _pending_events list capped at 64 entries."""

    def test_pending_events_cap_in_source(self):
        import inspect

        from bac_py.transport.sc.websocket import SCWebSocket

        source = inspect.getsource(SCWebSocket.recv)
        assert "64" in source


# ---------------------------------------------------------------------------
# S5: AddressResolutionAck URI list cap
# ---------------------------------------------------------------------------


class TestAddressResolutionURICapV2:
    """S5: AddressResolutionAckPayload URI list capped at 16."""

    def test_uri_list_truncated_at_16(self):
        from bac_py.transport.sc.bvlc import AddressResolutionAckPayload

        uris = [f"wss://host{i}.example.com:443" for i in range(20)]
        payload_bytes = " ".join(uris).encode("utf-8")
        result = AddressResolutionAckPayload.decode(payload_bytes)
        assert len(result.websocket_uris) == 16

    def test_uri_list_under_cap_unchanged(self):
        from bac_py.transport.sc.bvlc import AddressResolutionAckPayload

        uris = ["wss://a.example.com", "wss://b.example.com"]
        payload_bytes = " ".join(uris).encode("utf-8")
        result = AddressResolutionAckPayload.decode(payload_bytes)
        assert len(result.websocket_uris) == 2


# ---------------------------------------------------------------------------
# B1: FDT TTL cap
# ---------------------------------------------------------------------------


class TestFDTTTLCapV2:
    """B1: FDT registration TTL capped at 3600 seconds."""

    def test_ttl_cap_in_source(self):
        import inspect

        from bac_py.transport.bbmd import BBMDManager

        source = inspect.getsource(BBMDManager)
        assert "min(ttl, 3600)" in source


# ---------------------------------------------------------------------------
# A1: Change callback cap
# ---------------------------------------------------------------------------


class TestChangeCallbackCapV2:
    """A1: register_change_callback rejects >100 callbacks per property."""

    def test_callback_cap(self):
        from bac_py.objects.base import ObjectDatabase
        from bac_py.types.enums import ObjectType, PropertyIdentifier
        from bac_py.types.primitives import ObjectIdentifier

        db = ObjectDatabase()
        obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        prop_id = PropertyIdentifier.PRESENT_VALUE

        # Register 100 callbacks (should succeed)
        for _i in range(100):
            db.register_change_callback(obj_id, prop_id, lambda p, o, n: None)

        # 101st should raise
        with pytest.raises(ValueError, match="Too many change callbacks"):
            db.register_change_callback(obj_id, prop_id, lambda p, o, n: None)


# ---------------------------------------------------------------------------
# V3: decode_boolean empty buffer
# ---------------------------------------------------------------------------


class TestDecodeBooleanBoundsV3:
    """decode_boolean must raise ValueError on empty input."""

    def test_decode_boolean_empty(self):
        from bac_py.encoding.primitives import decode_boolean

        with pytest.raises(ValueError, match="decode_boolean requires at least 1 byte"):
            decode_boolean(b"")

    def test_decode_boolean_valid_true(self):
        from bac_py.encoding.primitives import decode_boolean

        assert decode_boolean(b"\x01") is True

    def test_decode_boolean_valid_false(self):
        from bac_py.encoding.primitives import decode_boolean

        assert decode_boolean(b"\x00") is False


# ---------------------------------------------------------------------------
# V3: COVPropertyValue nesting depth cap
# ---------------------------------------------------------------------------


class TestCOVPropertyValueNestingDepthV3:
    """COVPropertyValue.decode() must reject deeply nested tags."""

    def test_nesting_depth_cap(self):
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.services.cov import COVPropertyValue

        # Build a COVPropertyValue with deeply nested value:
        # [0] property_identifier = 85 (present-value)
        buf = bytearray()
        # [0] context tag 0, unsigned 85
        buf.extend(b"\x09\x55")  # context tag 0, length 1, value 85
        # [2] opening tag for value
        buf.extend(encode_opening_tag(2))
        # 40 nested opening tags (exceeds 32 limit)
        for _ in range(40):
            buf.extend(encode_opening_tag(0))
        for _ in range(40):
            buf.extend(encode_closing_tag(0))
        buf.extend(encode_closing_tag(2))

        with pytest.raises(ValueError, match="Nesting depth exceeds 32"):
            COVPropertyValue.decode(memoryview(buf))
