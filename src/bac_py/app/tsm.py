"""Transaction State Machines per ASHRAE 135-2016 Clause 5.4."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from bac_py.encoding.apdu import (
    AbortPDU,
    ComplexAckPDU,
    ConfirmedRequestPDU,
    SegmentAckPDU,
    encode_apdu,
)
from bac_py.segmentation.manager import (
    SegmentAction,
    SegmentationError,
    SegmentReceiver,
    SegmentSender,
    compute_max_segment_payload,
)
from bac_py.services.errors import (
    BACnetAbortError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)
from bac_py.types.enums import AbortReason

if TYPE_CHECKING:
    from bac_py.network import NetworkSender
    from bac_py.network.address import BACnetAddress
    from bac_py.types.enums import (
        ErrorClass,
        ErrorCode,
        RejectReason,
    )

logger = logging.getLogger(__name__)


# --- Client TSM ---


class ClientTransactionState(IntEnum):
    """Client TSM states per Clause 5.4.4."""

    IDLE = 0
    SEGMENTED_REQUEST = 1
    AWAIT_CONFIRMATION = 2
    SEGMENTED_CONFIRMATION = 3


@dataclass
class ClientTransaction:
    """Tracks an outstanding confirmed service request."""

    invoke_id: int
    destination: BACnetAddress
    service_choice: int
    request_data: bytes
    future: asyncio.Future[bytes]
    retry_count: int = 0
    timeout_handle: asyncio.TimerHandle | None = None
    state: ClientTransactionState = ClientTransactionState.IDLE
    segment_sender: SegmentSender | None = None
    segment_receiver: SegmentReceiver | None = None
    seg_retry_count: int = 0


class ClientTSM:
    """Client Transaction State Machine (Clause 5.4.4).

    Manages outstanding confirmed requests, correlating responses
    by (source_address, invoke_id).
    """

    def __init__(
        self,
        network: NetworkSender,
        *,
        apdu_timeout: float = 6.0,
        apdu_retries: int = 3,
        max_apdu_length: int = 1476,
        max_segments: int | None = None,
        segment_timeout: float = 2.0,
        proposed_window_size: int = 16,
    ) -> None:
        """Initialise the client TSM.

        :param network: Network sender used for transmitting APDUs.
        :param apdu_timeout: Seconds to wait for a response before retry.
        :param apdu_retries: Maximum number of transmission retries.
        :param max_apdu_length: Maximum APDU length accepted by this device
            (bytes).
        :param max_segments: Maximum segments this device can accept, or
            ``None`` for unlimited.
        :param segment_timeout: Seconds to wait between segments.
        :param proposed_window_size: Proposed segmentation window size (1-127).
        """
        self._network = network
        self._timeout = apdu_timeout
        self._retries = apdu_retries
        self._max_apdu_length = max_apdu_length
        self._max_segments = max_segments
        self._segment_timeout = segment_timeout
        self._proposed_window_size = proposed_window_size
        self._transactions: dict[tuple[BACnetAddress, int], ClientTransaction] = {}
        self._next_invoke_id = 0

    def _allocate_invoke_id(self, destination: BACnetAddress) -> int:
        """Allocate the next available invoke ID (0-255) for the given peer."""
        for _ in range(256):
            iid = self._next_invoke_id
            self._next_invoke_id = (self._next_invoke_id + 1) & 0xFF
            if (destination, iid) not in self._transactions:
                return iid
        msg = "No available invoke IDs for this peer"
        raise RuntimeError(msg)

    async def send_request(
        self,
        service_choice: int,
        request_data: bytes,
        destination: BACnetAddress,
    ) -> bytes:
        """Send a confirmed request and await the response.

        If the request data exceeds the max segment payload, the request
        is automatically segmented per Clause 5.2.

        :returns: The service-ack data from ComplexACK, or empty bytes
            for SimpleACK.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        loop = asyncio.get_running_loop()
        invoke_id = self._allocate_invoke_id(destination)
        future: asyncio.Future[bytes] = loop.create_future()

        txn = ClientTransaction(
            invoke_id=invoke_id,
            destination=destination,
            service_choice=service_choice,
            request_data=request_data,
            future=future,
        )
        key = (destination, invoke_id)
        self._transactions[key] = txn

        try:
            max_payload = compute_max_segment_payload(self._max_apdu_length, "confirmed_request")
            if len(request_data) > max_payload:
                self._send_segmented_request(txn)
            else:
                self._send_confirmed_request(txn)
            return await future
        finally:
            self._transactions.pop(key, None)
            if txn.timeout_handle:
                txn.timeout_handle.cancel()

    def handle_simple_ack(
        self,
        source: BACnetAddress,
        invoke_id: int,
        service_choice: int,
    ) -> None:
        """Handle a SimpleACK response."""
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            if txn.state != ClientTransactionState.AWAIT_CONFIRMATION:
                return
            self._cancel_timeout(txn)
            txn.future.set_result(b"")

    def handle_complex_ack(
        self,
        source: BACnetAddress,
        invoke_id: int,
        service_choice: int,
        data: bytes,
    ) -> None:
        """Handle a ComplexACK response (non-segmented)."""
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            if txn.state != ClientTransactionState.AWAIT_CONFIRMATION:
                return
            self._cancel_timeout(txn)
            txn.future.set_result(data)

    def handle_error(
        self,
        source: BACnetAddress,
        invoke_id: int,
        error_class: ErrorClass,
        error_code: ErrorCode,
        error_data: bytes = b"",
    ) -> None:
        """Handle an Error-PDU response."""
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            self._cancel_timeout(txn)
            txn.future.set_exception(BACnetError(error_class, error_code, error_data))

    def handle_reject(
        self,
        source: BACnetAddress,
        invoke_id: int,
        reason: RejectReason,
    ) -> None:
        """Handle a Reject-PDU response."""
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            self._cancel_timeout(txn)
            txn.future.set_exception(BACnetRejectError(reason))

    def handle_abort(
        self,
        source: BACnetAddress,
        invoke_id: int,
        reason: AbortReason,
    ) -> None:
        """Handle an Abort-PDU response."""
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            self._cancel_timeout(txn)
            txn.future.set_exception(BACnetAbortError(reason))

    def handle_segment_ack(
        self,
        source: BACnetAddress,
        pdu: SegmentAckPDU,
    ) -> None:
        """Handle SegmentACK during segmented request sending."""
        key = (source, pdu.invoke_id)
        txn = self._transactions.get(key)
        if not txn or txn.future.done():
            return

        if txn.state != ClientTransactionState.SEGMENTED_REQUEST:
            return

        sender = txn.segment_sender
        if sender is None:
            return

        if pdu.actual_window_size < 1 or pdu.actual_window_size > 127:
            self._abort_transaction(txn, AbortReason.WINDOW_SIZE_OUT_OF_RANGE)
            return

        complete = sender.handle_segment_ack(
            pdu.sequence_number, pdu.actual_window_size, pdu.negative_ack
        )
        txn.seg_retry_count = 0

        if complete:
            txn.state = ClientTransactionState.AWAIT_CONFIRMATION
            txn.segment_sender = None
            self._start_timeout(txn)
        else:
            self._fill_and_send_request_window(txn)

    def handle_segmented_complex_ack(
        self,
        source: BACnetAddress,
        pdu: ComplexAckPDU,
    ) -> None:
        """Handle a segmented ComplexACK response."""
        key = (source, pdu.invoke_id)
        txn = self._transactions.get(key)
        if not txn or txn.future.done():
            return

        if pdu.sequence_number == 0 and txn.state == ClientTransactionState.AWAIT_CONFIRMATION:
            # First segment of segmented response
            self._cancel_timeout(txn)
            receiver = SegmentReceiver.create(
                first_segment_data=pdu.service_ack,
                service_choice=pdu.service_choice,
                proposed_window_size=pdu.proposed_window_size or 1,
                more_follows=pdu.more_follows,
                our_window_size=self._proposed_window_size,
            )
            txn.segment_receiver = receiver
            txn.state = ClientTransactionState.SEGMENTED_CONFIRMATION

            if not pdu.more_follows:
                # Single-segment "segmented" response (edge case)
                txn.future.set_result(receiver.reassemble())
                return

            self._send_client_segment_ack(txn, seq=0, negative=False)
            self._start_segment_timeout(txn)
            return

        if txn.state != ClientTransactionState.SEGMENTED_CONFIRMATION:
            return

        seg_receiver = txn.segment_receiver
        if seg_receiver is None:
            return

        if pdu.sequence_number is None:
            return

        action, ack_seq = seg_receiver.receive_segment(
            pdu.sequence_number, pdu.service_ack, pdu.more_follows
        )

        match action:
            case SegmentAction.COMPLETE:
                self._cancel_timeout(txn)
                self._send_client_segment_ack(txn, seq=ack_seq, negative=False)
                txn.future.set_result(seg_receiver.reassemble())
            case SegmentAction.SEND_ACK:
                self._send_client_segment_ack(txn, seq=ack_seq, negative=False)
                self._start_segment_timeout(txn)
            case SegmentAction.CONTINUE:
                self._start_segment_timeout(txn)
            case SegmentAction.RESEND_LAST_ACK:
                self._send_client_segment_ack(txn, seq=ack_seq, negative=False)
                self._start_segment_timeout(txn)
            case SegmentAction.ABORT:
                self._abort_transaction(txn, AbortReason.INVALID_APDU_IN_THIS_STATE)

    def active_transactions(self) -> list[ClientTransaction]:
        """Return all active transactions (for shutdown)."""
        return list(self._transactions.values())

    def _cancel_timeout(self, txn: ClientTransaction) -> None:
        """Cancel the timeout timer for a transaction."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
            txn.timeout_handle = None

    def _send_confirmed_request(self, txn: ClientTransaction) -> None:
        """Encode and send a non-segmented confirmed request APDU."""
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=self._max_segments,
            max_apdu_length=self._max_apdu_length,
            invoke_id=txn.invoke_id,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=txn.service_choice,
            service_request=txn.request_data,
        )
        apdu_bytes = encode_apdu(pdu)
        self._network.send(apdu_bytes, txn.destination, expecting_reply=True)
        txn.state = ClientTransactionState.AWAIT_CONFIRMATION
        self._start_timeout(txn)

    def _send_segmented_request(self, txn: ClientTransaction) -> None:
        """Begin sending a segmented request."""
        try:
            sender = SegmentSender.create(
                payload=txn.request_data,
                invoke_id=txn.invoke_id,
                service_choice=txn.service_choice,
                max_apdu_length=self._max_apdu_length,
                pdu_type="confirmed_request",
                proposed_window_size=self._proposed_window_size,
            )
        except SegmentationError as e:
            txn.future.set_exception(BACnetAbortError(e.abort_reason))
            return

        txn.segment_sender = sender
        txn.state = ClientTransactionState.SEGMENTED_REQUEST
        self._fill_and_send_request_window(txn)

    def _fill_and_send_request_window(self, txn: ClientTransaction) -> None:
        """Send the current window of request segments."""
        sender = txn.segment_sender
        if sender is None:
            return
        segments = sender.fill_window()
        for seq_num, seg_data, more_follows in segments:
            pdu = ConfirmedRequestPDU(
                segmented=True,
                more_follows=more_follows,
                segmented_response_accepted=True,
                max_segments=self._max_segments,
                max_apdu_length=self._max_apdu_length,
                invoke_id=txn.invoke_id,
                sequence_number=seq_num,
                proposed_window_size=sender.proposed_window_size,
                service_choice=txn.service_choice,
                service_request=seg_data,
            )
            self._network.send(encode_apdu(pdu), txn.destination, expecting_reply=True)
        # Wait for SegmentACK: use T_wait_for_seg = 4 * T_seg
        self._start_segment_timeout(txn, wait_for_seg=True)

    def _send_client_segment_ack(
        self,
        txn: ClientTransaction,
        seq: int,
        negative: bool,
    ) -> None:
        """Send a SegmentACK PDU (as client)."""
        receiver = txn.segment_receiver
        if receiver is None:
            return
        ack = SegmentAckPDU(
            negative_ack=negative,
            sent_by_server=False,
            invoke_id=txn.invoke_id,
            sequence_number=seq,
            actual_window_size=receiver.actual_window_size,
        )
        self._network.send(encode_apdu(ack), txn.destination, expecting_reply=True)

    def _abort_transaction(self, txn: ClientTransaction, reason: AbortReason) -> None:
        """Abort a transaction by sending Abort PDU and failing the future."""
        abort = AbortPDU(
            sent_by_server=False,
            invoke_id=txn.invoke_id,
            abort_reason=reason,
        )
        self._network.send(encode_apdu(abort), txn.destination, expecting_reply=False)
        if not txn.future.done():
            self._cancel_timeout(txn)
            txn.future.set_exception(BACnetAbortError(reason))

    def _start_timeout(self, txn: ClientTransaction) -> None:
        """Start or restart the APDU timeout timer (T_arr)."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        loop = asyncio.get_running_loop()
        key = (txn.destination, txn.invoke_id)
        txn.timeout_handle = loop.call_later(self._timeout, self._on_timeout, key)

    def _start_segment_timeout(
        self, txn: ClientTransaction, *, wait_for_seg: bool = False
    ) -> None:
        """Start a segment timeout timer.

        :param txn: The transaction.
        :param wait_for_seg: If ``True``, use T_wait_for_seg (4 * T_seg)
            instead of T_seg. Used when waiting for a SegmentACK after
            sending.
        """
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        timeout = 4 * self._segment_timeout if wait_for_seg else self._segment_timeout
        loop = asyncio.get_running_loop()
        key = (txn.destination, txn.invoke_id)
        txn.timeout_handle = loop.call_later(timeout, self._on_segment_timeout, key)

    def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        """Handle APDU transaction timeout."""
        txn = self._transactions.get(key)
        if not txn or txn.future.done():
            return
        if txn.retry_count < self._retries:
            txn.retry_count += 1
            logger.debug(
                "Retrying invoke_id=%d (attempt %d/%d)",
                txn.invoke_id,
                txn.retry_count,
                self._retries,
            )
            # Retry using the same method as the original request.
            # If the request data exceeds the max segment payload it
            # must be re-sent as a segmented request.
            max_payload = compute_max_segment_payload(self._max_apdu_length, "confirmed_request")
            if len(txn.request_data) > max_payload:
                self._send_segmented_request(txn)
            else:
                self._send_confirmed_request(txn)
        else:
            txn.future.set_exception(
                BACnetTimeoutError(f"No response after {self._retries} retries")
            )

    def _on_segment_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        """Handle segment timeout during segmented transactions."""
        txn = self._transactions.get(key)
        if not txn or txn.future.done():
            return

        if txn.state == ClientTransactionState.SEGMENTED_REQUEST:
            # Waiting for SegmentACK from server
            if txn.seg_retry_count < self._retries:
                txn.seg_retry_count += 1
                logger.debug(
                    "Segment timeout, re-filling window invoke_id=%d (attempt %d/%d)",
                    txn.invoke_id,
                    txn.seg_retry_count,
                    self._retries,
                )
                self._fill_and_send_request_window(txn)
            else:
                self._abort_transaction(txn, AbortReason.TSM_TIMEOUT)

        elif txn.state == ClientTransactionState.SEGMENTED_CONFIRMATION:
            # Waiting for more segments from server
            if txn.seg_retry_count < self._retries:
                txn.seg_retry_count += 1
                # Send negative SegmentACK requesting retransmission
                receiver = txn.segment_receiver
                if receiver is not None:
                    self._send_client_segment_ack(txn, seq=receiver.last_ack_seq, negative=True)
                    self._start_segment_timeout(txn)
            else:
                self._abort_transaction(txn, AbortReason.TSM_TIMEOUT)


# --- Server TSM ---


class ServerTransactionState(IntEnum):
    """Server TSM states per Clause 5.4.5."""

    IDLE = 0
    SEGMENTED_REQUEST = 1
    AWAIT_RESPONSE = 2
    SEGMENTED_RESPONSE = 3


@dataclass
class ServerTransaction:
    """Tracks an incoming confirmed request being processed."""

    invoke_id: int
    source: BACnetAddress
    service_choice: int
    state: ServerTransactionState = ServerTransactionState.IDLE
    cached_response: bytes | None = None
    timeout_handle: asyncio.TimerHandle | None = None
    segment_receiver: SegmentReceiver | None = None
    segment_sender: SegmentSender | None = None
    seg_retry_count: int = 0
    client_max_apdu_length: int = 1476
    client_max_segments: int | None = None
    segmented_response_accepted: bool = False


class ServerTSM:
    """Server Transaction State Machine (Clause 5.4.5).

    Prevents duplicate processing and caches responses for
    retransmission detection.
    """

    def __init__(
        self,
        network: NetworkSender,
        *,
        request_timeout: float = 6.0,
        apdu_retries: int = 3,
        segment_timeout: float = 2.0,
        max_apdu_length: int = 1476,
        max_segments: int | None = None,
        proposed_window_size: int = 16,
    ) -> None:
        """Initialise the server TSM.

        :param network: Network sender used for transmitting responses.
        :param request_timeout: Seconds before a server transaction expires.
        :param apdu_retries: Maximum number of segment retries.
        :param segment_timeout: Seconds to wait between segments.
        :param max_apdu_length: Maximum APDU length this device can send
            (bytes).
        :param max_segments: Maximum segments this device can send, or
            ``None`` for unlimited.
        :param proposed_window_size: Proposed segmentation window size (1-127).
        """
        self._network = network
        self._timeout = request_timeout
        self._retries = apdu_retries
        self._segment_timeout = segment_timeout
        self._max_apdu_length = max_apdu_length
        self._max_segments = max_segments
        self._proposed_window_size = proposed_window_size
        self._transactions: dict[tuple[BACnetAddress, int], ServerTransaction] = {}

    def receive_confirmed_request(
        self,
        pdu: ConfirmedRequestPDU,
        source: BACnetAddress,
    ) -> tuple[ServerTransaction, bytes | None] | None:
        """Register an incoming confirmed request.

        Returns ``(txn, service_data)`` for new requests. ``service_data``
        is the complete request payload for non-segmented requests, or
        ``None`` for segmented requests that need more segments.

        Returns ``None`` for duplicates (cached response is resent).
        """
        key = (source, pdu.invoke_id)
        existing = self._transactions.get(key)

        if existing is not None:
            if existing.state == ServerTransactionState.SEGMENTED_REQUEST:
                # Subsequent segment of an in-progress segmented request
                return self.handle_request_segment(pdu, source)
            # Duplicate request - resend cached response if available
            if existing.cached_response is not None:
                self._network.send(
                    existing.cached_response,
                    source,
                    expecting_reply=False,
                )
            return None

        txn = ServerTransaction(
            invoke_id=pdu.invoke_id,
            source=source,
            service_choice=pdu.service_choice,
            state=ServerTransactionState.AWAIT_RESPONSE,
            client_max_apdu_length=pdu.max_apdu_length,
            client_max_segments=pdu.max_segments,
            segmented_response_accepted=pdu.segmented_response_accepted,
        )
        self._transactions[key] = txn
        self._start_timeout(txn)

        if pdu.segmented:
            # First segment of a segmented request
            txn.state = ServerTransactionState.SEGMENTED_REQUEST
            receiver = SegmentReceiver.create(
                first_segment_data=pdu.service_request,
                service_choice=pdu.service_choice,
                proposed_window_size=pdu.proposed_window_size or 1,
                more_follows=pdu.more_follows,
                our_window_size=self._proposed_window_size,
            )
            txn.segment_receiver = receiver

            if not pdu.more_follows:
                # Single-segment "segmented" request (unusual)
                txn.state = ServerTransactionState.AWAIT_RESPONSE
                self._send_server_segment_ack(txn, 0, negative=False)
                return (txn, receiver.reassemble())

            self._send_server_segment_ack(txn, 0, negative=False)
            self._start_segment_timeout(txn)
            return (txn, None)

        return (txn, pdu.service_request)

    def handle_request_segment(
        self,
        pdu: ConfirmedRequestPDU,
        source: BACnetAddress,
    ) -> tuple[ServerTransaction, bytes | None] | None:
        """Handle a subsequent segment of a segmented confirmed request.

        Returns ``(txn, complete_data)`` when all segments are received,
        ``(txn, None)`` when more segments expected,
        or ``None`` if no matching transaction.
        """
        key = (source, pdu.invoke_id)
        txn = self._transactions.get(key)
        if txn is None or txn.state != ServerTransactionState.SEGMENTED_REQUEST:
            return None

        receiver = txn.segment_receiver
        if receiver is None:
            return None

        if pdu.sequence_number is None:
            return None

        action, ack_seq = receiver.receive_segment(
            pdu.sequence_number, pdu.service_request, pdu.more_follows
        )

        match action:
            case SegmentAction.COMPLETE:
                self._cancel_timeout(txn)
                self._send_server_segment_ack(txn, ack_seq, negative=False)
                txn.state = ServerTransactionState.AWAIT_RESPONSE
                return (txn, receiver.reassemble())
            case SegmentAction.SEND_ACK:
                self._send_server_segment_ack(txn, ack_seq, negative=False)
                self._restart_segment_timeout(txn)
                return (txn, None)
            case SegmentAction.CONTINUE:
                self._restart_segment_timeout(txn)
                return (txn, None)
            case SegmentAction.RESEND_LAST_ACK:
                self._send_server_segment_ack(txn, ack_seq, negative=False)
                self._restart_segment_timeout(txn)
                return (txn, None)
            case SegmentAction.ABORT:
                self._abort_server_transaction(txn, AbortReason.INVALID_APDU_IN_THIS_STATE)
                return None

        return None  # pragma: no cover

    def start_segmented_response(
        self,
        txn: ServerTransaction,
        service_choice: int,
        response_data: bytes,
    ) -> None:
        """Begin sending a segmented ComplexACK response.

        :param txn: The server transaction.
        :param service_choice: Service choice for the response.
        :param response_data: The complete service-ack data to segment.
        """
        if not txn.segmented_response_accepted:
            self._abort_server_transaction(txn, AbortReason.SEGMENTATION_NOT_SUPPORTED)
            return

        try:
            sender = SegmentSender.create(
                payload=response_data,
                invoke_id=txn.invoke_id,
                service_choice=service_choice,
                max_apdu_length=txn.client_max_apdu_length,
                pdu_type="complex_ack",
                proposed_window_size=self._proposed_window_size,
                peer_max_segments=txn.client_max_segments,
            )
        except SegmentationError:
            self._abort_server_transaction(txn, AbortReason.APDU_TOO_LONG)
            return

        txn.segment_sender = sender
        txn.state = ServerTransactionState.SEGMENTED_RESPONSE
        # Cache the full non-segmented ComplexACK for retransmission detection.
        # If the client retransmits the request after all segments are sent,
        # the server resends this cached response.
        full_ack = ComplexAckPDU(
            segmented=False,
            more_follows=False,
            invoke_id=txn.invoke_id,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=service_choice,
            service_ack=response_data,
        )
        txn.cached_response = encode_apdu(full_ack)
        self._fill_and_send_response_window(txn)

    def handle_segment_ack_for_response(
        self,
        source: BACnetAddress,
        pdu: SegmentAckPDU,
    ) -> None:
        """Handle SegmentACK from client during segmented response sending."""
        key = (source, pdu.invoke_id)
        txn = self._transactions.get(key)
        if txn is None or txn.state != ServerTransactionState.SEGMENTED_RESPONSE:
            return

        sender = txn.segment_sender
        if sender is None:
            return

        if pdu.actual_window_size < 1 or pdu.actual_window_size > 127:
            self._abort_server_transaction(txn, AbortReason.WINDOW_SIZE_OUT_OF_RANGE)
            return

        complete = sender.handle_segment_ack(
            pdu.sequence_number, pdu.actual_window_size, pdu.negative_ack
        )
        txn.seg_retry_count = 0

        if complete:
            txn.state = ServerTransactionState.IDLE
            txn.segment_sender = None
            self._restart_timeout(txn)
        else:
            self._fill_and_send_response_window(txn)

    def complete_transaction(
        self,
        txn: ServerTransaction,
        response_apdu: bytes,
    ) -> None:
        """Cache the response and schedule cleanup."""
        txn.cached_response = response_apdu
        txn.state = ServerTransactionState.IDLE
        self._restart_timeout(txn)

    def _fill_and_send_response_window(self, txn: ServerTransaction) -> None:
        """Send the current window of response segments."""
        sender = txn.segment_sender
        if sender is None:
            return
        segments = sender.fill_window()
        for seq_num, seg_data, more_follows in segments:
            pdu = ComplexAckPDU(
                segmented=True,
                more_follows=more_follows,
                invoke_id=txn.invoke_id,
                sequence_number=seq_num,
                proposed_window_size=sender.proposed_window_size,
                service_choice=sender.service_choice,
                service_ack=seg_data,
            )
            self._network.send(encode_apdu(pdu), txn.source, expecting_reply=True)
        # Wait for SegmentACK: use T_wait_for_seg = 4 * T_seg
        self._start_server_segment_timeout(txn)

    def _send_server_segment_ack(
        self,
        txn: ServerTransaction,
        seq: int,
        negative: bool,
    ) -> None:
        """Send a SegmentACK PDU (as server)."""
        receiver = txn.segment_receiver
        actual_ws = receiver.actual_window_size if receiver else self._proposed_window_size
        ack = SegmentAckPDU(
            negative_ack=negative,
            sent_by_server=True,
            invoke_id=txn.invoke_id,
            sequence_number=seq,
            actual_window_size=actual_ws,
        )
        self._network.send(encode_apdu(ack), txn.source, expecting_reply=True)

    def _abort_server_transaction(self, txn: ServerTransaction, reason: AbortReason) -> None:
        """Abort a server transaction by sending Abort PDU."""
        abort = AbortPDU(
            sent_by_server=True,
            invoke_id=txn.invoke_id,
            abort_reason=reason,
        )
        self._network.send(encode_apdu(abort), txn.source, expecting_reply=False)
        key = (txn.source, txn.invoke_id)
        self._cancel_timeout(txn)
        self._transactions.pop(key, None)

    def _start_timeout(self, txn: ServerTransaction) -> None:
        """Start the cleanup timer for a transaction."""
        loop = asyncio.get_running_loop()
        key = (txn.source, txn.invoke_id)
        txn.timeout_handle = loop.call_later(self._timeout, self._on_timeout, key)

    def _restart_timeout(self, txn: ServerTransaction) -> None:
        """Restart the cleanup timer."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        self._start_timeout(txn)

    def _start_segment_timeout(self, txn: ServerTransaction) -> None:
        """Start a segment receive timeout (T_seg)."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        loop = asyncio.get_running_loop()
        key = (txn.source, txn.invoke_id)
        txn.timeout_handle = loop.call_later(
            self._segment_timeout, self._on_server_segment_timeout, key
        )

    def _restart_segment_timeout(self, txn: ServerTransaction) -> None:
        """Restart the segment receive timeout."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        self._start_segment_timeout(txn)

    def _start_server_segment_timeout(self, txn: ServerTransaction) -> None:
        """Start T_wait_for_seg timeout (4 * T_seg) for response sending."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        loop = asyncio.get_running_loop()
        key = (txn.source, txn.invoke_id)
        txn.timeout_handle = loop.call_later(
            4 * self._segment_timeout,
            self._on_server_segment_timeout,
            key,
        )

    def _cancel_timeout(self, txn: ServerTransaction) -> None:
        """Cancel the timeout timer for a transaction."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
            txn.timeout_handle = None

    def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        """Remove transaction on timeout."""
        self._transactions.pop(key, None)

    def _on_server_segment_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        """Handle segment timeout during segmented server transactions."""
        txn = self._transactions.get(key)
        if txn is None:
            return

        if txn.state == ServerTransactionState.SEGMENTED_REQUEST:
            # Waiting for more request segments from client
            if txn.seg_retry_count < self._retries:
                txn.seg_retry_count += 1
                receiver = txn.segment_receiver
                if receiver is not None:
                    self._send_server_segment_ack(txn, seq=receiver.last_ack_seq, negative=True)
                    self._start_segment_timeout(txn)
            else:
                self._abort_server_transaction(txn, AbortReason.TSM_TIMEOUT)

        elif txn.state == ServerTransactionState.SEGMENTED_RESPONSE:
            # Waiting for SegmentACK from client
            if txn.seg_retry_count < self._retries:
                txn.seg_retry_count += 1
                self._fill_and_send_response_window(txn)
            else:
                self._abort_server_transaction(txn, AbortReason.TSM_TIMEOUT)
