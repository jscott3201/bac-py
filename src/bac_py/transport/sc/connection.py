"""BACnet/SC connection state machine (AB.6.2).

Implements both the initiating peer (Figure AB-11) and accepting peer
(Figure AB-12) state machines for BACnet/SC connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from bac_py.transport.sc.bvlc import (
    BvlcResultPayload,
    ConnectAcceptPayload,
    ConnectRequestPayload,
    SCMessage,
)
from bac_py.transport.sc.types import BvlcSCFunction, SCResultCode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID
    from bac_py.transport.sc.websocket import SCWebSocket

logger = logging.getLogger(__name__)

# BACnet error code for VMAC collision (Clause 21)
_ERROR_CLASS_COMMUNICATION = 7
_ERROR_CODE_NODE_DUPLICATE_VMAC = 0x0071


class SCConnectionState(IntEnum):
    """Connection state machine states."""

    IDLE = 0
    AWAITING_WEBSOCKET = 1
    AWAITING_ACCEPT = 2
    AWAITING_REQUEST = 3
    CONNECTED = 4
    DISCONNECTING = 5


class SCConnectionRole(IntEnum):
    """Whether this side initiated or accepted the connection."""

    INITIATING = 0
    ACCEPTING = 1


@dataclass
class SCConnectionConfig:
    """Timeouts and tuning for an SC connection."""

    connect_wait_timeout: float = 10.0
    disconnect_wait_timeout: float = 5.0
    heartbeat_timeout: float = 300.0


class SCConnection:
    """BACnet/SC connection state machine (AB.6.2).

    Manages the lifecycle of a single WebSocket connection to a hub or
    direct peer, including handshake, heartbeat, and graceful disconnect.
    """

    def __init__(
        self,
        local_vmac: SCVMAC,
        local_uuid: DeviceUUID,
        config: SCConnectionConfig | None = None,
        max_bvlc_length: int = 1600,
        max_npdu_length: int = 1497,
        *,
        hub_mode: bool = False,
    ) -> None:
        self._config = config or SCConnectionConfig()
        self._local_vmac = local_vmac
        self._local_uuid = local_uuid
        self._max_bvlc = max_bvlc_length
        self._max_npdu = max_npdu_length
        self._hub_mode = hub_mode

        self._state = SCConnectionState.IDLE
        self._role: SCConnectionRole | None = None
        self._ws: SCWebSocket | None = None
        self._msg_id_counter = 0

        # Peer info (populated after Connect-Request/Accept exchange)
        self.peer_vmac: SCVMAC | None = None
        self.peer_uuid: DeviceUUID | None = None
        self.peer_max_bvlc: int = 0
        self.peer_max_npdu: int = 0

        # Callbacks
        self.on_connected: Callable[[], None] | None = None
        self.on_disconnected: Callable[[], None] | None = None
        self.on_message: Callable[[SCMessage, bytes | None], Awaitable[None] | None] | None = None
        self.on_vmac_collision: Callable[[], None] | None = None

        # Internal tasks
        self._receive_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._last_recv_time: float = 0.0

    @property
    def state(self) -> SCConnectionState:
        """Current connection state."""
        return self._state

    @property
    def role(self) -> SCConnectionRole | None:
        """Connection role (initiating or accepting)."""
        return self._role

    @property
    def local_vmac(self) -> SCVMAC:
        """Local VMAC address."""
        return self._local_vmac

    @local_vmac.setter
    def local_vmac(self, value: SCVMAC) -> None:
        self._local_vmac = value

    def _next_msg_id(self) -> int:
        self._msg_id_counter = (self._msg_id_counter + 1) & 0xFFFF
        return self._msg_id_counter

    # ------------------------------------------------------------------
    # Initiating peer (Figure AB-11)
    # ------------------------------------------------------------------

    async def initiate(self, ws: SCWebSocket) -> None:
        """Run the initiating peer state machine on an established WebSocket.

        Transitions: IDLE → AWAITING_ACCEPT → CONNECTED (or IDLE on failure).
        """
        if self._state != SCConnectionState.IDLE:
            err = f"Cannot initiate: state is {self._state.name}, expected IDLE"
            raise RuntimeError(err)
        self._role = SCConnectionRole.INITIATING
        self._ws = ws
        ws._max_frame_size = self._max_bvlc
        old_state = self._state
        self._state = SCConnectionState.AWAITING_ACCEPT
        logger.debug(
            "SC connection %s: %s -> %s", self._local_vmac, old_state.name, self._state.name
        )

        # Send Connect-Request
        payload = ConnectRequestPayload(
            self._local_vmac,
            self._local_uuid,
            self._max_bvlc,
            self._max_npdu,
        ).encode()
        msg = SCMessage(
            BvlcSCFunction.CONNECT_REQUEST,
            message_id=self._next_msg_id(),
            payload=payload,
        )
        await self._ws.send(msg.encode())

        # Wait for Connect-Accept or NAK
        try:
            async with asyncio.timeout(self._config.connect_wait_timeout):
                raw = await self._ws.recv()
        except (TimeoutError, OSError, ConnectionError) as exc:
            logger.debug("Connect wait timeout or error: %s", exc)
            await self._go_idle()
            return

        try:
            response = SCMessage.decode(raw)
        except ValueError:
            await self._go_idle()
            return

        if response.function == BvlcSCFunction.CONNECT_ACCEPT:
            accept = ConnectAcceptPayload.decode(response.payload)
            self.peer_vmac = accept.vmac
            self.peer_uuid = accept.uuid
            self.peer_max_bvlc = accept.max_bvlc_length
            self.peer_max_npdu = accept.max_npdu_length
            self._state = SCConnectionState.CONNECTED
            logger.debug("SC connection %s: AWAITING_ACCEPT -> CONNECTED", self._local_vmac)
            logger.info("SC connection established to peer %s", self.peer_vmac)
            self._start_background_tasks()
            if self.on_connected:
                self.on_connected()
        elif response.function == BvlcSCFunction.BVLC_RESULT:
            result = BvlcResultPayload.decode(response.payload)
            if (
                result.result_code == SCResultCode.NAK
                and result.error_code == _ERROR_CODE_NODE_DUPLICATE_VMAC
                and self.on_vmac_collision
            ):
                self.on_vmac_collision()
            await self._go_idle()
        else:
            await self._go_idle()

    # ------------------------------------------------------------------
    # Accepting peer (Figure AB-12)
    # ------------------------------------------------------------------

    async def accept(
        self,
        ws: SCWebSocket,
        vmac_checker: Callable[[SCVMAC, DeviceUUID], bool] | None = None,
    ) -> None:
        """Run the accepting peer state machine on an established WebSocket.

        :param ws: The WebSocket connection (already upgraded).
        :param vmac_checker: Optional callback ``(vmac, uuid) -> ok``.
            Returns False if the VMAC collides with an existing connection.

        Transitions: IDLE → AWAITING_REQUEST → CONNECTED (or IDLE on failure).
        """
        if self._state != SCConnectionState.IDLE:
            err = f"Cannot accept: state is {self._state.name}, expected IDLE"
            raise RuntimeError(err)
        self._role = SCConnectionRole.ACCEPTING
        self._ws = ws
        ws._max_frame_size = self._max_bvlc
        old_state = self._state
        self._state = SCConnectionState.AWAITING_REQUEST
        logger.debug(
            "SC connection %s: %s -> %s", self._local_vmac, old_state.name, self._state.name
        )

        # Wait for Connect-Request
        try:
            async with asyncio.timeout(self._config.connect_wait_timeout):
                raw = await self._ws.recv()
        except (TimeoutError, OSError, ConnectionError) as exc:
            logger.debug("Accepting connect wait timeout or error: %s", exc)
            await self._go_idle()
            return

        try:
            request = SCMessage.decode(raw)
        except ValueError:
            await self._go_idle()
            return

        if request.function != BvlcSCFunction.CONNECT_REQUEST:
            await self._go_idle()
            return

        req_payload = ConnectRequestPayload.decode(request.payload)

        # Check for VMAC collision
        if vmac_checker and not vmac_checker(req_payload.vmac, req_payload.uuid):
            nak = BvlcResultPayload(
                for_function=BvlcSCFunction.CONNECT_REQUEST,
                result_code=SCResultCode.NAK,
                error_header_marker=0x00,
                error_class=_ERROR_CLASS_COMMUNICATION,
                error_code=_ERROR_CODE_NODE_DUPLICATE_VMAC,
            ).encode()
            nak_msg = SCMessage(
                BvlcSCFunction.BVLC_RESULT,
                message_id=request.message_id,
                payload=nak,
            )
            await self._ws.send(nak_msg.encode())
            await self._go_idle()
            return

        self.peer_vmac = req_payload.vmac
        self.peer_uuid = req_payload.uuid
        self.peer_max_bvlc = req_payload.max_bvlc_length
        self.peer_max_npdu = req_payload.max_npdu_length

        # Send Connect-Accept
        accept_payload = ConnectAcceptPayload(
            self._local_vmac,
            self._local_uuid,
            self._max_bvlc,
            self._max_npdu,
        ).encode()
        accept_msg = SCMessage(
            BvlcSCFunction.CONNECT_ACCEPT,
            message_id=request.message_id,
            payload=accept_payload,
        )
        await self._ws.send(accept_msg.encode())

        self._state = SCConnectionState.CONNECTED
        logger.debug("SC connection %s: AWAITING_REQUEST -> CONNECTED", self._local_vmac)
        logger.info("SC connection accepted from peer %s", self.peer_vmac)
        self._start_background_tasks()
        if self.on_connected:
            self.on_connected()

    # ------------------------------------------------------------------
    # Message send
    # ------------------------------------------------------------------

    async def send_message(self, msg: SCMessage) -> None:
        """Send a BVLC-SC message on this connection."""
        if self._state != SCConnectionState.CONNECTED or self._ws is None:
            msg_text = "Cannot send: connection not in CONNECTED state"
            raise ConnectionError(msg_text)
        await self._ws.send(msg.encode())

    async def send_raw(self, data: bytes) -> None:
        """Send pre-encoded BVLC-SC bytes, skipping encode().

        Used by the hub to forward messages without re-encoding.
        """
        if self._state != SCConnectionState.CONNECTED or self._ws is None:
            msg_text = "Cannot send: connection not in CONNECTED state"
            raise ConnectionError(msg_text)
        await self._ws.send_raw(data)

    def write_raw_no_drain(self, data: bytes) -> bool:
        """Buffer pre-encoded bytes without draining.

        Returns True if data was buffered.  Call :meth:`drain` afterwards.
        Used by hub broadcast to batch writes before draining concurrently.
        """
        if self._state != SCConnectionState.CONNECTED or self._ws is None:
            return False
        return self._ws.write_no_drain(data)

    async def drain(self) -> None:
        """Drain the write buffer.  Pair with :meth:`write_raw_no_drain`."""
        if self._ws is not None:
            await self._ws.drain()

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    async def disconnect(self) -> None:
        """Initiate graceful disconnect."""
        if self._state != SCConnectionState.CONNECTED or self._ws is None:
            await self._go_idle()
            return

        old_state = self._state
        self._state = SCConnectionState.DISCONNECTING
        logger.debug("SC connection %s: %s -> DISCONNECTING", self._local_vmac, old_state.name)

        # Cancel background tasks first to get exclusive WebSocket access
        await self._stop_background_tasks()

        if self._ws is None:
            self._state = SCConnectionState.IDLE
            return

        disconnect_msg = SCMessage(
            BvlcSCFunction.DISCONNECT_REQUEST,
            message_id=self._next_msg_id(),
        )
        try:
            await self._ws.send(disconnect_msg.encode())
        except (OSError, ConnectionError):
            await self._go_idle()
            return

        # Wait for Disconnect-ACK (we have exclusive WS access now)
        try:
            async with asyncio.timeout(self._config.disconnect_wait_timeout):
                raw = await self._ws.recv()
                response = SCMessage.decode(raw)
                if response.function in (
                    BvlcSCFunction.DISCONNECT_ACK,
                    BvlcSCFunction.BVLC_RESULT,
                ):
                    pass  # Expected, proceed to IDLE
        except (TimeoutError, OSError, ConnectionError, ValueError):
            pass

        await self._go_idle()

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    def _start_background_tasks(self) -> None:
        self._last_recv_time = time.monotonic()
        self._receive_task = asyncio.create_task(self._receive_loop())
        if self._role == SCConnectionRole.INITIATING:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_background_tasks(self) -> None:
        """Cancel and await background tasks for exclusive WebSocket access."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

    async def _receive_loop(self) -> None:
        """Read messages from WebSocket, dispatch to state machine."""
        try:
            while self._state == SCConnectionState.CONNECTED and self._ws is not None:
                raw = await self._ws.recv()
                self._last_recv_time = time.monotonic()
                try:
                    msg = SCMessage.decode(raw, skip_payload=self._hub_mode)
                except ValueError as exc:
                    # Send BVLC-Result NAK for malformed messages (AB.3.1.5)
                    logger.warning("SC connection %s malformed message: %s", self._local_vmac, exc)
                    await self._send_decode_error_nak(raw, str(exc))
                    continue
                await self._handle_message(msg, raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("SC connection %s receive error: %s", self._local_vmac, exc)
            if self._state == SCConnectionState.CONNECTED:
                await self._go_idle()

    async def _handle_message(self, msg: SCMessage, raw: bytes | None = None) -> None:
        """Process a received BVLC-SC message per current state."""
        if self._state == SCConnectionState.CONNECTED:
            if msg.function == BvlcSCFunction.DISCONNECT_REQUEST:
                # Respond with Disconnect-ACK, then go idle
                ack = SCMessage(
                    BvlcSCFunction.DISCONNECT_ACK,
                    message_id=msg.message_id,
                )
                if self._ws:
                    with contextlib.suppress(OSError, ConnectionError):
                        await self._ws.send(ack.encode())
                await self._go_idle()
                return

            if msg.function == BvlcSCFunction.HEARTBEAT_REQUEST:
                ack = SCMessage(
                    BvlcSCFunction.HEARTBEAT_ACK,
                    message_id=msg.message_id,
                )
                if self._ws:
                    with contextlib.suppress(OSError, ConnectionError):
                        await self._ws.send(ack.encode())
                return

            if msg.function == BvlcSCFunction.HEARTBEAT_ACK:
                logger.debug("SC heartbeat ack received: %s", self._local_vmac)
                return  # Heartbeat response, no action needed

            # Forward other messages (Encapsulated-NPDU, etc.) to callback.
            # Pass raw bytes so hub can forward without re-encoding.
            if self.on_message:
                try:
                    result = self.on_message(msg, raw)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.error("on_message callback error: %s", exc, exc_info=True)

    # Response message functions that SHALL NOT generate BVLC-Result (AB.3.1.4)
    _RESPONSE_FUNCTIONS = frozenset(
        {
            BvlcSCFunction.BVLC_RESULT,
            BvlcSCFunction.CONNECT_ACCEPT,
            BvlcSCFunction.DISCONNECT_ACK,
            BvlcSCFunction.HEARTBEAT_ACK,
            BvlcSCFunction.ADDRESS_RESOLUTION_ACK,
        }
    )

    async def _send_decode_error_nak(self, raw: bytes, error: str) -> None:
        """Send a BVLC-Result NAK for a malformed message (AB.3.1.5).

        Attempts to extract the BVLC function from the first byte.
        Skips NAK if the message appears to be a response type (AB.3.1.4).
        """
        if self._ws is None:
            return
        # Try to extract the BVLC function
        for_function = BvlcSCFunction.BVLC_RESULT
        if raw:
            with contextlib.suppress(ValueError):
                for_function = BvlcSCFunction(raw[0])
        # Response messages SHALL NOT generate BVLC-Result responses
        if for_function in self._RESPONSE_FUNCTIONS:
            return
        nak = BvlcResultPayload(
            for_function=for_function,
            result_code=SCResultCode.NAK,
            error_header_marker=0x00,
            error_class=_ERROR_CLASS_COMMUNICATION,
            error_code=0,
            error_details=error[:128],
        ).encode()
        nak_msg = SCMessage(BvlcSCFunction.BVLC_RESULT, message_id=0, payload=nak)
        with contextlib.suppress(OSError, ConnectionError):
            await self._ws.send(nak_msg.encode())

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat (initiating peer only, AB.6.3).

        Per the spec, a heartbeat is sent only if no BVLC message was
        received within the heartbeat timeout.  The timer is reset each
        time ``_receive_loop`` records a message arrival.
        """
        try:
            while self._state == SCConnectionState.CONNECTED and self._ws is not None:
                # Compute time until next heartbeat is needed
                elapsed = time.monotonic() - self._last_recv_time
                remaining = self._config.heartbeat_timeout - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
                if self._state != SCConnectionState.CONNECTED or self._ws is None:
                    break
                # Re-check: a message may have arrived during the sleep
                elapsed = time.monotonic() - self._last_recv_time
                if elapsed < self._config.heartbeat_timeout:
                    continue
                hb = SCMessage(
                    BvlcSCFunction.HEARTBEAT_REQUEST,
                    message_id=self._next_msg_id(),
                )
                logger.debug("SC heartbeat sent: %s", self._local_vmac)
                try:
                    await self._ws.send(hb.encode())
                except (OSError, ConnectionError):
                    break
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _go_idle(self) -> None:
        """Transition to IDLE state, clean up resources."""
        if self._state == SCConnectionState.IDLE:
            return  # Already idle, prevent re-entry

        was_connected = self._state in (
            SCConnectionState.CONNECTED,
            SCConnectionState.DISCONNECTING,
        )
        old_state = self._state
        self._state = SCConnectionState.IDLE
        logger.debug("SC connection %s: %s -> IDLE", self._local_vmac, old_state.name)
        if was_connected:
            logger.info("SC connection closed: peer=%s", self.peer_vmac)

        # Cancel tasks — don't await since we may be called from within a task.
        # The tasks check self._state and will exit on their next iteration.
        for task in (self._heartbeat_task, self._receive_task):
            if task and not task.done():
                task.cancel()
        self._heartbeat_task = None
        self._receive_task = None

        # Close transport immediately (no graceful WS close handshake — the
        # BACnet SC layer handles graceful disconnect via Disconnect-Request/ACK)
        if self._ws:
            self._ws._close_transport()
            self._ws = None

        if was_connected and self.on_disconnected:
            self.on_disconnected()

        # Clear callbacks to break reference cycles (lambdas capture
        # external objects like hub_function/node_switch and this connection)
        self.on_connected = None
        self.on_disconnected = None
        self.on_message = None
        self.on_vmac_collision = None
