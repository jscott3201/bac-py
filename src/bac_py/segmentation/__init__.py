"""APDU segmentation and reassembly per ASHRAE 135-2016 Clause 5.2/5.4."""

from bac_py.segmentation.manager import (
    COMPLEX_ACK_SEGMENT_OVERHEAD,
    CONFIRMED_REQUEST_SEGMENT_OVERHEAD,
    DEFAULT_PROPOSED_WINDOW_SIZE,
    SegmentAction,
    SegmentationError,
    SegmentReceiver,
    SegmentSender,
    check_segment_count,
    compute_max_segment_payload,
    duplicate_in_window,
    in_window,
    split_payload,
)

__all__ = [
    "COMPLEX_ACK_SEGMENT_OVERHEAD",
    "CONFIRMED_REQUEST_SEGMENT_OVERHEAD",
    "DEFAULT_PROPOSED_WINDOW_SIZE",
    "SegmentAction",
    "SegmentReceiver",
    "SegmentSender",
    "SegmentationError",
    "check_segment_count",
    "compute_max_segment_payload",
    "duplicate_in_window",
    "in_window",
    "split_payload",
]
