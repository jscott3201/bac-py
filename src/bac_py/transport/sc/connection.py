"""BACnet/SC connection state machine (AB.6.2).

Implements both the initiating peer (Figure AB-11) and accepting peer
(Figure AB-12) state machines for BACnet/SC connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
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
    ) -> None:
        self._config = config or SCConnectionConfig()
        self._local_vmac = local_vmac
        self._local_uuid = local_uuid
        self._max_bvlc = max_bvlc_length
        self._max_npdu = max_npdu_length

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
        self.on_message: Callable[[SCMessage], Awaitable[None] | None] | None = None
        self.on_vmac_collision: Callable[[], None] | None = None

        # Internal tasks
        self._receive_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

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
        self._role = SCConnectionRole.INITIATING
        self._ws = ws
        self._state = SCConnectionState.AWAITING_ACCEPT

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
        except (TimeoutError, Exception) as exc:
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
        self._role = SCConnectionRole.ACCEPTING
        self._ws = ws
        self._state = SCConnectionState.AWAITING_REQUEST

        # Wait for Connect-Request
        try:
            async with asyncio.timeout(self._config.connect_wait_timeout):
                raw = await self._ws.recv()
        except (TimeoutError, Exception) as exc:
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

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    async def disconnect(self) -> None:
        """Initiate graceful disconnect."""
        if self._state != SCConnectionState.CONNECTED or self._ws is None:
            await self._go_idle()
            return

        self._state = SCConnectionState.DISCONNECTING

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
        except (TimeoutError, Exception):
            pass

        await self._go_idle()

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    def _start_background_tasks(self) -> None:
        self._receive_task = asyncio.ensure_future(self._receive_loop())
        if self._role == SCConnectionRole.INITIATING:
            self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

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
                msg = SCMessage.decode(raw)
                await self._handle_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._state == SCConnectionState.CONNECTED:
                await self._go_idle()

    async def _handle_message(self, msg: SCMessage) -> None:
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
                return  # Heartbeat response, no action needed

            # Forward other messages (Encapsulated-NPDU, etc.) to callback
            if self.on_message:
                result = self.on_message(msg)
                if asyncio.iscoroutine(result):
                    await result

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat (initiating peer only, AB.6.3)."""
        try:
            while self._state == SCConnectionState.CONNECTED and self._ws is not None:
                await asyncio.sleep(self._config.heartbeat_timeout)
                if self._state != SCConnectionState.CONNECTED:
                    break
                hb = SCMessage(
                    BvlcSCFunction.HEARTBEAT_REQUEST,
                    message_id=self._next_msg_id(),
                )
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
        was_connected = self._state in (
            SCConnectionState.CONNECTED,
            SCConnectionState.DISCONNECTING,
        )
        self._state = SCConnectionState.IDLE

        # Cancel tasks (don't await — may be called from within a task)
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            self._receive_task = None

        # Close transport immediately (no graceful WS close handshake — the
        # BACnet SC layer handles graceful disconnect via Disconnect-Request/ACK)
        if self._ws:
            self._ws._close_transport()
            self._ws = None

        if was_connected and self.on_disconnected:
            self.on_disconnected()
