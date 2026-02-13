from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.types.enums import Segmentation
from bac_py.types.primitives import ObjectIdentifier


class TestWhoIsRequest:
    def test_encode_no_range(self):
        req = WhoIsRequest()
        assert req.encode() == b""

    def test_encode_with_range(self):
        req = WhoIsRequest(low_limit=100, high_limit=200)
        encoded = req.encode()
        assert len(encoded) > 0
        # Should contain context tags 0 and 1
        decoded = WhoIsRequest.decode(encoded)
        assert decoded.low_limit == 100
        assert decoded.high_limit == 200

    def test_round_trip_no_range(self):
        req = WhoIsRequest()
        decoded = WhoIsRequest.decode(req.encode())
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_round_trip_with_range(self):
        req = WhoIsRequest(low_limit=0, high_limit=4194303)
        decoded = WhoIsRequest.decode(req.encode())
        assert decoded.low_limit == 0
        assert decoded.high_limit == 4194303

    def test_round_trip_single_device(self):
        req = WhoIsRequest(low_limit=42, high_limit=42)
        decoded = WhoIsRequest.decode(req.encode())
        assert decoded.low_limit == 42
        assert decoded.high_limit == 42

    def test_decode_empty_bytes(self):
        decoded = WhoIsRequest.decode(b"")
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_mismatched_limits_treated_as_unbounded(self):
        """Both limits must be present or both absent (Clause 16.10.1.1.1)."""
        req = WhoIsRequest(low_limit=100, high_limit=None)
        assert req.low_limit is None
        assert req.high_limit is None

    def test_mismatched_limits_high_only(self):
        req = WhoIsRequest(low_limit=None, high_limit=200)
        assert req.low_limit is None
        assert req.high_limit is None


class TestIAmRequest:
    def test_round_trip(self):
        req = IAmRequest(
            object_identifier=ObjectIdentifier(8, 1234),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=42,
        )
        encoded = req.encode()
        decoded = IAmRequest.decode(encoded)
        assert decoded.object_identifier.object_type == 8
        assert decoded.object_identifier.instance_number == 1234
        assert decoded.max_apdu_length == 1476
        assert decoded.segmentation_supported == Segmentation.BOTH
        assert decoded.vendor_id == 42

    def test_device_type(self):
        req = IAmRequest(
            object_identifier=ObjectIdentifier(8, 99999),
            max_apdu_length=480,
            segmentation_supported=Segmentation.NONE,
            vendor_id=0,
        )
        encoded = req.encode()
        decoded = IAmRequest.decode(encoded)
        assert decoded.object_identifier.instance_number == 99999
        assert decoded.max_apdu_length == 480
        assert decoded.segmentation_supported == Segmentation.NONE
        assert decoded.vendor_id == 0

    def test_encode_uses_application_tags(self):
        req = IAmRequest(
            object_identifier=ObjectIdentifier(8, 1),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        encoded = req.encode()
        # First byte should be application tag 12 (object-id) = 0xC4
        assert encoded[0] == 0xC4

    def test_large_instance_number(self):
        req = IAmRequest(
            object_identifier=ObjectIdentifier(8, 4194303),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=999,
        )
        decoded = IAmRequest.decode(req.encode())
        assert decoded.object_identifier.instance_number == 4194303
        assert decoded.vendor_id == 999


# ---------------------------------------------------------------------------
# Coverage: who_is.py branch partials 63->68, 68->73, 70->73
# ---------------------------------------------------------------------------


class TestWhoIsRequestDecodeBranches:
    """Branches 63->68, 68->73, 70->73: decode branch partials in WhoIsRequest.

    Tests for non-matching first tag (63->68), data ending after low_limit
    (68->73), and non-matching second tag (70->73).
    """

    def test_non_context_first_tag(self):
        """First tag is not context tag 0 -- low_limit stays None.

        Manually construct data with an application tag (not context).
        Branch 63->68: tag.number != 0 check fails.
        """
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        # Context tag with number 5 (not 0) -- not a valid low_limit
        buf = bytearray()
        buf.extend(encode_context_tagged(5, encode_unsigned(100)))

        decoded = WhoIsRequest.decode(bytes(buf))
        # low_limit should be None because tag number is not 0
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_only_low_limit_no_high_limit(self):
        """Only low_limit tag present, data ends before high_limit.

        Branch 68->73: offset < len(data) is False.
        """
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        buf = bytearray()
        # [0] low_limit = 42
        buf.extend(encode_context_tagged(0, encode_unsigned(42)))
        # No more data -- high_limit not present

        decoded = WhoIsRequest.decode(bytes(buf))
        # __post_init__ treats mismatched limits as unbounded
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_low_limit_followed_by_non_matching_tag(self):
        """Low limit present, but second tag is not context tag 1.

        Branch 70->73: tag.number != 1 check fails.
        """
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        buf = bytearray()
        # [0] low_limit = 100
        buf.extend(encode_context_tagged(0, encode_unsigned(100)))
        # Context tag 5 (not 1) -- not a valid high_limit
        buf.extend(encode_context_tagged(5, encode_unsigned(200)))

        decoded = WhoIsRequest.decode(bytes(buf))
        # __post_init__ treats mismatched limits as unbounded
        assert decoded.low_limit is None
        assert decoded.high_limit is None
