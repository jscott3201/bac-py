"""Transaction State Machines per ASHRAE 135-2016 Clause 5.4."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from bac_py.encoding.apdu import (
    ConfirmedRequestPDU,
    encode_apdu,
)
from bac_py.services.errors import (
    BACnetAbortError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)

if TYPE_CHECKING:
    from bac_py.network.address import BACnetAddress
    from bac_py.network.layer import NetworkLayer
    from bac_py.types.enums import (
        AbortReason,
        ErrorClass,
        ErrorCode,
        RejectReason,
    )

logger = logging.getLogger(__name__)


# --- Client TSM ---


class ClientTransactionState(IntEnum):
    """Client TSM states per Clause 5.4.4."""

    IDLE = 0
    AWAIT_CONFIRMATION = 2


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


class ClientTSM:
    """Client Transaction State Machine (Clause 5.4.4).

    Manages outstanding confirmed requests, correlating responses
    by (source_address, invoke_id).
    """

    def __init__(
        self,
        network: NetworkLayer,
        *,
        apdu_timeout: float = 6.0,
        apdu_retries: int = 3,
        max_apdu_length: int = 1476,
        max_segments: int | None = None,
    ) -> None:
        self._network = network
        self._timeout = apdu_timeout
        self._retries = apdu_retries
        self._max_apdu_length = max_apdu_length
        self._max_segments = max_segments
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

        Returns the service-ack data from ComplexACK,
        or empty bytes for SimpleACK.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
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
            self._cancel_timeout(txn)
            txn.future.set_result(data)

    def handle_error(
        self,
        source: BACnetAddress,
        invoke_id: int,
        error_class: ErrorClass,
        error_code: ErrorCode,
    ) -> None:
        """Handle an Error-PDU response."""
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            self._cancel_timeout(txn)
            txn.future.set_exception(BACnetError(error_class, error_code))

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

    def active_transactions(self) -> list[ClientTransaction]:
        """Return all active transactions (for shutdown)."""
        return list(self._transactions.values())

    def _cancel_timeout(self, txn: ClientTransaction) -> None:
        """Cancel the timeout timer for a transaction."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
            txn.timeout_handle = None

    def _send_confirmed_request(self, txn: ClientTransaction) -> None:
        """Encode and send a confirmed request APDU."""
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
        self._start_timeout(txn)

    def _start_timeout(self, txn: ClientTransaction) -> None:
        """Start or restart the timeout timer for a transaction."""
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        loop = asyncio.get_running_loop()
        key = (txn.destination, txn.invoke_id)
        txn.timeout_handle = loop.call_later(self._timeout, self._on_timeout, key)

    def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        """Handle transaction timeout."""
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
            self._send_confirmed_request(txn)
        else:
            txn.future.set_exception(
                BACnetTimeoutError(f"No response after {self._retries} retries")
            )


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


class ServerTSM:
    """Server Transaction State Machine (Clause 5.4.5).

    Prevents duplicate processing and caches responses for
    retransmission detection.
    """

    def __init__(
        self,
        network: NetworkLayer,
        *,
        request_timeout: float = 6.0,
    ) -> None:
        self._network = network
        self._timeout = request_timeout
        self._transactions: dict[tuple[BACnetAddress, int], ServerTransaction] = {}

    def receive_confirmed_request(
        self,
        invoke_id: int,
        source: BACnetAddress,
        service_choice: int,
    ) -> ServerTransaction | None:
        """Register an incoming confirmed request.

        Returns the transaction if this is a new request,
        or None if it is a duplicate (cached response is resent).
        """
        key = (source, invoke_id)
        existing = self._transactions.get(key)

        if existing is not None:
            # Duplicate request - resend cached response if available
            if existing.cached_response is not None:
                self._network.send(
                    existing.cached_response,
                    source,
                    expecting_reply=False,
                )
            return None

        txn = ServerTransaction(
            invoke_id=invoke_id,
            source=source,
            service_choice=service_choice,
            state=ServerTransactionState.AWAIT_RESPONSE,
        )
        self._transactions[key] = txn
        self._start_timeout(txn)
        return txn

    def complete_transaction(
        self,
        txn: ServerTransaction,
        response_apdu: bytes,
    ) -> None:
        """Cache the response and schedule cleanup."""
        txn.cached_response = response_apdu
        txn.state = ServerTransactionState.IDLE
        self._restart_timeout(txn)

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

    def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        """Remove transaction on timeout."""
        self._transactions.pop(key, None)
