"""APDU segmentation and reassembly logic per ASHRAE 135-2016 Clause 5.2/5.4.

This module contains pure segmentation logic with no I/O dependencies.
TSMs drive instances of SegmentSender/SegmentReceiver via method calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from bac_py.types.enums import AbortReason

logger = logging.getLogger(__name__)

# Segment header overhead for each PDU type (when segmented=True).
# ConfirmedRequest: byte0 + byte1(max-seg/max-apdu) + invoke_id + seq_num + window_size + service_choice
CONFIRMED_REQUEST_SEGMENT_OVERHEAD = 6
# ComplexACK: byte0 + invoke_id + seq_num + window_size + service_choice
COMPLEX_ACK_SEGMENT_OVERHEAD = 5

DEFAULT_PROPOSED_WINDOW_SIZE = 16


class SegmentationError(Exception):
    """Raised when segmentation fails (e.g., APDU too long for peer)."""

    def __init__(self, abort_reason: AbortReason, message: str = "") -> None:
        self.abort_reason = abort_reason
        super().__init__(message)


class SegmentAction(Enum):
    """Action the receiver should take after processing a segment."""

    SEND_ACK = "send_ack"
    RESEND_LAST_ACK = "resend"
    COMPLETE = "complete"
    ABORT = "abort"


# --- Pure functions per Clause 5.4 ---


def in_window(seq_a: int, seq_b: int, actual_window_size: int) -> bool:
    """Determine if segment seq_a is within the window starting at seq_b.

    Per Clause 5.4: ``(seqA - seqB) mod 256 < ActualWindowSize``.
    """
    return ((seq_a - seq_b) % 256) < actual_window_size


def duplicate_in_window(
    seq_a: int,
    seq_b: int,
    actual_window_size: int,
    proposed_window_size: int,
) -> bool:
    """Determine if segment seq_a is a duplicate the receiver has already seen.

    Per Clause 5.4: ``Wm < (seqA - seqB) mod 256 <= 255``
    where ``Wm = max(ActualWindowSize, ProposedWindowSize)``.
    """
    wm = max(actual_window_size, proposed_window_size)
    diff = (seq_a - seq_b) % 256
    return wm < diff <= 255


def compute_max_segment_payload(
    max_apdu_length: int,
    pdu_type: Literal["confirmed_request", "complex_ack"],
) -> int:
    """Return the maximum service data bytes that fit in one segment.

    Args:
        max_apdu_length: Max APDU size for the link (e.g. 480, 1476).
        pdu_type: Which PDU type determines the header overhead.

    Returns:
        Max payload bytes per segment.
    """
    overhead = (
        CONFIRMED_REQUEST_SEGMENT_OVERHEAD
        if pdu_type == "confirmed_request"
        else COMPLEX_ACK_SEGMENT_OVERHEAD
    )
    return max_apdu_length - overhead


def split_payload(payload: bytes, max_segment_size: int) -> list[bytes]:
    """Split a byte payload into segments of at most max_segment_size bytes.

    Args:
        payload: The raw service data to split.
        max_segment_size: Maximum bytes per segment.

    Returns:
        List of byte segments. At least one segment is always returned
        (which may be empty if the payload is empty).

    Raises:
        ValueError: If max_segment_size is not positive.
    """
    if max_segment_size <= 0:
        msg = f"max_segment_size must be positive, got {max_segment_size}"
        raise ValueError(msg)
    if len(payload) == 0:
        return [b""]
    segments: list[bytes] = []
    for i in range(0, len(payload), max_segment_size):
        segments.append(payload[i : i + max_segment_size])
    return segments


def check_segment_count(num_segments: int, max_segments: int | None) -> bool:
    """Check that the segment count does not exceed the peer's limit.

    Args:
        num_segments: Total number of segments.
        max_segments: Peer's max-segments-accepted (None = unlimited).

    Returns:
        True if within limits.
    """
    if max_segments is None:
        return True
    return num_segments <= max_segments


# --- SegmentSender ---


@dataclass
class SegmentSender:
    """Manages the send side of a segmented transaction.

    Tracks segments by absolute 0-based index and converts to 8-bit
    sequence numbers (``index & 0xFF``) for the wire protocol.
    """

    segments: list[bytes]
    invoke_id: int
    service_choice: int
    proposed_window_size: int
    actual_window_size: int
    _window_start_idx: int = 0

    @classmethod
    def create(
        cls,
        payload: bytes,
        invoke_id: int,
        service_choice: int,
        max_apdu_length: int,
        pdu_type: Literal["confirmed_request", "complex_ack"],
        proposed_window_size: int = DEFAULT_PROPOSED_WINDOW_SIZE,
        peer_max_segments: int | None = None,
    ) -> SegmentSender:
        """Create a SegmentSender by splitting the payload.

        Raises:
            SegmentationError: If the segment count exceeds peer_max_segments.
        """
        max_payload = compute_max_segment_payload(max_apdu_length, pdu_type)
        segments = split_payload(payload, max_payload)
        if not check_segment_count(len(segments), peer_max_segments):
            msg = (
                f"Payload requires {len(segments)} segments but peer accepts "
                f"at most {peer_max_segments}"
            )
            raise SegmentationError(AbortReason.APDU_TOO_LONG, msg)
        return cls(
            segments=segments,
            invoke_id=invoke_id,
            service_choice=service_choice,
            proposed_window_size=proposed_window_size,
            actual_window_size=proposed_window_size,
        )

    def fill_window(self) -> list[tuple[int, bytes, bool]]:
        """Return segments for the current window.

        Returns:
            List of ``(sequence_number, segment_data, more_follows)`` tuples.
        """
        result: list[tuple[int, bytes, bool]] = []
        end_idx = min(len(self.segments), self._window_start_idx + self.actual_window_size)
        last_idx = len(self.segments) - 1
        for idx in range(self._window_start_idx, end_idx):
            seq_num = idx & 0xFF
            more_follows = idx < last_idx
            result.append((seq_num, self.segments[idx], more_follows))
        return result

    def handle_segment_ack(
        self,
        ack_seq: int,
        actual_window_size: int,
        negative: bool,
    ) -> bool:
        """Process a SegmentACK.

        Args:
            ack_seq: The sequence number in the SegmentACK.
            actual_window_size: The receiver's advertised window size.
            negative: Whether this is a negative ACK (retransmit request).

        Returns:
            True if all segments have been acknowledged.
        """
        acked_idx = self._seq_to_idx(ack_seq)
        self.actual_window_size = actual_window_size

        if negative:
            # Re-send from the segment after the last successfully received
            self._window_start_idx = acked_idx + 1
        else:
            # Advance past all acknowledged segments
            self._window_start_idx = acked_idx + 1

        return self.is_complete

    @property
    def is_complete(self) -> bool:
        """True when all segments have been acknowledged."""
        return self._window_start_idx >= len(self.segments)

    @property
    def total_segments(self) -> int:
        """Total number of segments."""
        return len(self.segments)

    def _seq_to_idx(self, seq: int) -> int:
        """Map an 8-bit sequence number to the nearest absolute index.

        Finds the index at or above ``_window_start_idx - actual_window_size``
        (to handle the case where the ACK references the last segment in the
        previous window) where ``idx & 0xFF == seq``.
        """
        # Start searching from a reasonable lower bound
        search_start = max(0, self._window_start_idx - self.actual_window_size)
        for idx in range(search_start, len(self.segments)):
            if (idx & 0xFF) == seq:
                return idx
        # Fallback: indicates a protocol state mismatch
        logger.warning(
            "Could not map sequence number %d to segment index; falling back to window start %d",
            seq,
            self._window_start_idx,
        )
        return self._window_start_idx


# --- SegmentReceiver ---


@dataclass
class SegmentReceiver:
    """Manages reassembly of received segments.

    Tracks segments by absolute 0-based index.
    """

    _segments: dict[int, bytes] = field(default_factory=dict)
    _expected_idx: int = 0
    actual_window_size: int = DEFAULT_PROPOSED_WINDOW_SIZE
    proposed_window_size: int = 1
    service_choice: int = 0
    _final_idx: int | None = None
    _last_ack_seq: int = 0

    @classmethod
    def create(
        cls,
        first_segment_data: bytes,
        service_choice: int,
        proposed_window_size: int,
        more_follows: bool = True,
        our_window_size: int = DEFAULT_PROPOSED_WINDOW_SIZE,
    ) -> SegmentReceiver:
        """Create a receiver from the first segment (sequence number 0).

        Args:
            first_segment_data: Payload of the first segment.
            service_choice: Service choice from the PDU header.
            proposed_window_size: Window size proposed by the sender.
            more_follows: The more-follows flag from the first segment.
            our_window_size: Our preferred window size.

        Returns:
            New SegmentReceiver with the first segment stored.
        """
        actual = min(our_window_size, proposed_window_size)
        receiver = cls(
            _segments={0: first_segment_data},
            _expected_idx=1,
            actual_window_size=actual,
            proposed_window_size=proposed_window_size,
            service_choice=service_choice,
            _final_idx=0 if not more_follows else None,
            _last_ack_seq=0,
        )
        return receiver

    def receive_segment(
        self,
        seq_num: int,
        data: bytes,
        more_follows: bool,
    ) -> tuple[SegmentAction, int]:
        """Process a received segment.

        Args:
            seq_num: 8-bit sequence number from the PDU.
            data: Segment payload data.
            more_follows: The more-follows flag from the PDU.

        Returns:
            ``(action, ack_sequence_number)`` indicating what the caller
            should do next. For ABORT, ack_sequence_number is -1.
        """
        expected_seq = self._expected_idx & 0xFF

        if in_window(seq_num, expected_seq, self.actual_window_size):
            # Map sequence to absolute index
            abs_idx = self._seq_to_abs_idx(seq_num)
            self._segments[abs_idx] = data

            if not more_follows:
                self._final_idx = abs_idx

            # Advance expected past contiguously received segments
            while self._expected_idx in self._segments:
                self._expected_idx += 1

            self._last_ack_seq = seq_num

            if self.is_complete:
                return (SegmentAction.COMPLETE, seq_num)
            return (SegmentAction.SEND_ACK, seq_num)

        if duplicate_in_window(
            seq_num, expected_seq, self.actual_window_size, self.proposed_window_size
        ):
            return (SegmentAction.RESEND_LAST_ACK, self._last_ack_seq)

        return (SegmentAction.ABORT, -1)

    @property
    def last_ack_seq(self) -> int:
        """The sequence number of the last acknowledged segment."""
        return self._last_ack_seq

    @property
    def is_complete(self) -> bool:
        """True when all segments have been received."""
        if self._final_idx is None:
            return False
        return self._expected_idx > self._final_idx

    def reassemble(self) -> bytes:
        """Concatenate all segments in order.

        Raises:
            ValueError: If not all segments have been received.
        """
        if not self.is_complete:
            msg = "Cannot reassemble: not all segments received"
            raise ValueError(msg)
        assert self._final_idx is not None
        parts: list[bytes] = []
        for i in range(self._final_idx + 1):
            parts.append(self._segments[i])
        return b"".join(parts)

    def _seq_to_abs_idx(self, seq_num: int) -> int:
        """Map an 8-bit sequence number to an absolute index near _expected_idx."""
        # The sequence number corresponds to an index in the vicinity of _expected_idx.
        # Since sequence numbers wrap at 256, compute the offset from expected.
        expected_seq = self._expected_idx & 0xFF
        offset = (seq_num - expected_seq) % 256
        return self._expected_idx + offset
