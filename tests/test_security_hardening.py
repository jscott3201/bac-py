"""Tests for v1.4.2 security and memory hardening."""

import json
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
