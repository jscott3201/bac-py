"""BACnet application layer orchestrator per ASHRAE 135-2016."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bac_py.app.cov import COVManager
from bac_py.app.tsm import ClientTSM, ServerTSM
from bac_py.encoding.apdu import (
    AbortPDU,
    ComplexAckPDU,
    ConfirmedRequestPDU,
    ErrorPDU,
    RejectPDU,
    SegmentAckPDU,
    SimpleAckPDU,
    UnconfirmedRequestPDU,
    decode_apdu,
    encode_apdu,
)
from bac_py.network.layer import NetworkLayer
from bac_py.network.router import NetworkRouter, RouterPort
from bac_py.objects.base import ObjectDatabase
from bac_py.segmentation.manager import compute_max_segment_payload
from bac_py.services.base import ServiceRegistry
from bac_py.services.cov import COVNotificationRequest
from bac_py.services.errors import BACnetAbortError, BACnetError, BACnetRejectError
from bac_py.transport.bip import BIPTransport
from bac_py.types.enums import (
    AbortReason,
    ConfirmedServiceChoice,
    ObjectType,
    PduType,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import ObjectIdentifier

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.app.tsm import ServerTransaction
    from bac_py.network.address import BACnetAddress
    from bac_py.transport.bbmd import BDTEntry

logger = logging.getLogger(__name__)


@dataclass
class BBMDConfig:
    """Configuration for BBMD on a router port.

    Attributes:
        bdt_entries: Initial Broadcast Distribution Table entries
            (including self).  If empty, the BBMD starts with an
            empty BDT (foreign-device-only mode).
    """

    bdt_entries: list[BDTEntry] = field(default_factory=list)


@dataclass
class RouterPortConfig:
    """Configuration for a single router port."""

    port_id: int
    network_number: int
    interface: str = "0.0.0.0"
    port: int = 0xBAC0
    bbmd_config: BBMDConfig | None = None


@dataclass
class RouterConfig:
    """Configuration for a router device."""

    ports: list[RouterPortConfig] = field(default_factory=list)
    application_port_id: int = 1


@dataclass
class DeviceConfig:
    """Configuration for a BACnet device.

    Attributes:
        instance_number: BACnet device instance number (0-4194302).
        name: Device object name.
        vendor_name: Vendor name string.
        vendor_id: ASHRAE-assigned vendor identifier.
        model_name: Device model name string.
        firmware_revision: Firmware revision string.
        application_software_version: Application software version string.
        interface: Local IP address to bind to (``"0.0.0.0"`` for all).
        port: UDP port number (default ``0xBAC0`` / 47808).
        apdu_timeout: APDU timeout in milliseconds.
        apdu_segment_timeout: Segment timeout in milliseconds.
        apdu_retries: Maximum number of APDU retries.
        max_apdu_length: Maximum APDU length in bytes.
        max_segments: Maximum segments accepted, or ``None`` for unlimited.
        router_config: Optional router configuration for multi-network mode.
    """

    instance_number: int
    name: str = "bac-py"
    vendor_name: str = "bac-py"
    vendor_id: int = 0
    model_name: str = "bac-py"
    firmware_revision: str = "0.1.0"
    application_software_version: str = "0.1.0"
    interface: str = "0.0.0.0"
    port: int = 0xBAC0
    apdu_timeout: int = 6000  # milliseconds
    apdu_segment_timeout: int = 2000  # milliseconds
    apdu_retries: int = 3
    max_apdu_length: int = 1476
    max_segments: int | None = None
    router_config: RouterConfig | None = None


class BACnetApplication:
    """Central orchestrator connecting all protocol layers.

    Wires transport, network, TSMs, and service dispatch.
    """

    def __init__(self, config: DeviceConfig) -> None:
        """Initialise the application from a device configuration.

        Args:
            config: Device and network parameters for this BACnet device.
        """
        self._config = config
        self._transport: BIPTransport | None = None
        self._network: NetworkLayer | None = None
        self._router: NetworkRouter | None = None
        self._transports: list[BIPTransport] = []
        self._client_tsm: ClientTSM | None = None
        self._server_tsm: ServerTSM | None = None
        self._service_registry = ServiceRegistry()
        self._object_db = ObjectDatabase()
        self._running = False
        self._stopped = False
        self._stop_event: asyncio.Event | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._ready_event: asyncio.Event | None = None
        self._unconfirmed_listeners: dict[int, list[Callable[..., Any]]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._cov_manager: COVManager | None = None
        self._cov_callbacks: dict[int, Callable[..., Any]] = {}

    @property
    def object_db(self) -> ObjectDatabase:
        """The object database for this device."""
        return self._object_db

    @property
    def service_registry(self) -> ServiceRegistry:
        """The service handler registry."""
        return self._service_registry

    @property
    def config(self) -> DeviceConfig:
        """The device configuration."""
        return self._config

    @property
    def cov_manager(self) -> COVManager | None:
        """The COV subscription manager, or None if not started."""
        return self._cov_manager

    @property
    def device_object_identifier(self) -> Any:
        """The device object identifier for this application.

        Returns the ObjectIdentifier of the device object from the
        object database. Used by the COV manager to populate the
        initiating device identifier in notifications.
        """
        return ObjectIdentifier(ObjectType.DEVICE, self._config.instance_number)

    async def start(self) -> None:
        """Start the transport and initialize all layers."""
        self._stopped = False
        self._stop_event = asyncio.Event()

        if self._config.router_config:
            await self._start_router_mode()
        else:
            await self._start_non_router_mode()

        # Common: create TSMs with whichever network sender is active
        network = self._router or self._network
        if network is None:
            msg = "Neither router nor network layer initialized after start"
            raise RuntimeError(msg)
        segment_timeout = self._config.apdu_segment_timeout / 1000
        self._client_tsm = ClientTSM(
            network,
            apdu_timeout=self._config.apdu_timeout / 1000,
            apdu_retries=self._config.apdu_retries,
            max_apdu_length=self._config.max_apdu_length,
            max_segments=self._config.max_segments,
            segment_timeout=segment_timeout,
        )
        self._server_tsm = ServerTSM(
            network,
            segment_timeout=segment_timeout,
            max_apdu_length=self._config.max_apdu_length,
            max_segments=self._config.max_segments,
        )
        self._running = True

        # Initialize COV manager and register notification handlers
        self._cov_manager = COVManager(self)
        self._service_registry.register_confirmed(
            ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION,
            self._handle_confirmed_cov_notification,
        )
        self._service_registry.register_unconfirmed(
            UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION,
            self._handle_unconfirmed_cov_notification,
        )

    async def _start_non_router_mode(self) -> None:
        """Start in non-router (simple device) mode."""
        self._transport = BIPTransport(
            interface=self._config.interface,
            port=self._config.port,
        )
        self._network = NetworkLayer(self._transport)
        self._network.on_receive(self._on_apdu_received)
        await self._transport.start()

    async def _start_router_mode(self) -> None:
        """Start in router mode with multiple ports."""
        if self._config.router_config is None:
            msg = "Router config is required for router mode"
            raise RuntimeError(msg)
        ports: list[RouterPort] = []
        for pc in self._config.router_config.ports:
            transport = BIPTransport(interface=pc.interface, port=pc.port)
            await transport.start()
            self._transports.append(transport)

            # Attach BBMD if configured for this port
            if pc.bbmd_config is not None:
                await transport.attach_bbmd(pc.bbmd_config.bdt_entries or None)

            port = RouterPort(
                port_id=pc.port_id,
                network_number=pc.network_number,
                transport=transport,
                mac_address=transport.local_mac,
                max_npdu_length=transport.max_npdu_length,
            )
            ports.append(port)
        self._router = NetworkRouter(
            ports,
            application_port_id=self._config.router_config.application_port_id,
            application_callback=self._on_apdu_received,
        )
        await self._router.start()

    async def stop(self) -> None:
        """Stop the application and clean up resources.

        This method is idempotent -- calling it multiple times is safe.
        """
        if self._stopped:
            return
        self._stopped = True

        # Shutdown COV manager (cancel subscription timers)
        if self._cov_manager:
            self._cov_manager.shutdown()
            self._cov_manager = None

        # Cancel all pending client transactions
        if self._client_tsm:
            for txn in self._client_tsm.active_transactions():
                if not txn.future.done():
                    txn.future.cancel()

        if self._stop_event:
            self._stop_event.set()

        # Cancel all background tasks
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        if self._router:
            await self._router.stop()
        elif self._transport:
            await self._transport.stop()

        self._running = False

    async def run(self) -> None:
        """Start the application and block until stopped."""
        await self.start()
        try:
            if self._stop_event is not None:
                await self._stop_event.wait()
        finally:
            await self.stop()

    async def __aenter__(self) -> BACnetApplication:
        """Start the application as an async context manager."""
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop the application when exiting the context."""
        await self.stop()

    # --- Client API ---

    async def confirmed_request(
        self,
        destination: BACnetAddress,
        service_choice: int,
        service_data: bytes,
    ) -> bytes:
        """Send a confirmed request and await response.

        Returns ComplexACK service data, or empty bytes for SimpleACK.
        """
        if self._client_tsm is None:
            msg = "Application not started"
            raise RuntimeError(msg)
        return await self._client_tsm.send_request(service_choice, service_data, destination)

    def unconfirmed_request(
        self,
        destination: BACnetAddress,
        service_choice: int,
        service_data: bytes,
    ) -> None:
        """Send an unconfirmed request."""
        network = self._router or self._network
        if network is None:
            msg = "Application not started"
            raise RuntimeError(msg)
        pdu = UnconfirmedRequestPDU(
            service_choice=service_choice,
            service_request=service_data,
        )
        apdu_bytes = encode_apdu(pdu)
        network.send(apdu_bytes, destination, expecting_reply=False)

    def send_confirmed_cov_notification(
        self,
        service_data: bytes,
        destination: BACnetAddress,
        service_choice: int,
    ) -> None:
        """Send a confirmed COV notification (fire-and-forget).

        Unlike ``confirmed_request``, this does not await a response.
        COV notifications are best-effort; failures are logged but
        do not propagate.
        """
        self._spawn_task(self._send_confirmed_cov(service_data, destination, service_choice))

    async def _send_confirmed_cov(
        self,
        service_data: bytes,
        destination: BACnetAddress,
        service_choice: int,
    ) -> None:
        """Background task to send a confirmed COV notification."""
        try:
            await self.confirmed_request(
                destination=destination,
                service_choice=service_choice,
                service_data=service_data,
            )
        except Exception:
            logger.debug(
                "Confirmed COV notification to %s failed",
                destination,
                exc_info=True,
            )

    # --- COV callback management ---

    def register_cov_callback(
        self,
        process_id: int,
        callback: Callable[..., Any],
    ) -> None:
        """Register a callback for incoming COV notifications.

        Args:
            process_id: Subscriber process identifier to match.
            callback: Called with ``(notification, source)`` when a
                COV notification arrives for this process ID.
        """
        self._cov_callbacks[process_id] = callback

    def unregister_cov_callback(self, process_id: int) -> None:
        """Remove a COV notification callback."""
        self._cov_callbacks.pop(process_id, None)

    # --- Listener management ---

    def register_temporary_handler(
        self,
        service_choice: int,
        handler: Callable[..., Any],
    ) -> None:
        """Register a temporary listener for unconfirmed service responses."""
        self._unconfirmed_listeners.setdefault(service_choice, []).append(handler)

    def unregister_temporary_handler(
        self,
        service_choice: int,
        handler: Callable[..., Any],
    ) -> None:
        """Remove a temporary listener."""
        listeners = self._unconfirmed_listeners.get(service_choice, [])
        if handler in listeners:
            listeners.remove(handler)

    # --- Receive path ---

    def _spawn_task(self, coro: Any) -> None:
        """Create a background task and track it to prevent GC."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _on_apdu_received(self, data: bytes, source: BACnetAddress) -> None:
        """Dispatch received APDU based on PDU type.

        Routes confirmed requests to the server TSM, unconfirmed
        requests to the service registry, and responses (simple-ack,
        complex-ack, error, reject, abort, segment-ack) to the
        client TSM for correlation with outstanding transactions.
        """
        try:
            pdu = decode_apdu(data)
        except (ValueError, IndexError):
            logger.warning("Dropped malformed APDU from %s", source)
            return

        pdu_type = PduType((data[0] >> 4) & 0x0F)

        match pdu_type:
            case PduType.CONFIRMED_REQUEST:
                if not isinstance(pdu, ConfirmedRequestPDU):
                    return
                if pdu.segmented:
                    self._handle_segmented_request(pdu, source)
                else:
                    self._spawn_task(self._handle_confirmed_request(pdu, source))
            case PduType.UNCONFIRMED_REQUEST:
                self._spawn_task(self._handle_unconfirmed_request(pdu, source))
            case PduType.SIMPLE_ACK:
                if not isinstance(pdu, SimpleAckPDU):
                    return
                if self._client_tsm:
                    self._client_tsm.handle_simple_ack(source, pdu.invoke_id, pdu.service_choice)
            case PduType.COMPLEX_ACK:
                if not isinstance(pdu, ComplexAckPDU):
                    return
                if self._client_tsm and pdu.segmented:
                    self._client_tsm.handle_segmented_complex_ack(source, pdu)
                elif self._client_tsm:
                    self._client_tsm.handle_complex_ack(
                        source, pdu.invoke_id, pdu.service_choice, pdu.service_ack
                    )
            case PduType.ERROR:
                if not isinstance(pdu, ErrorPDU):
                    return
                if self._client_tsm:
                    self._client_tsm.handle_error(
                        source, pdu.invoke_id, pdu.error_class, pdu.error_code
                    )
            case PduType.REJECT:
                if not isinstance(pdu, RejectPDU):
                    return
                if self._client_tsm:
                    self._client_tsm.handle_reject(source, pdu.invoke_id, pdu.reject_reason)
            case PduType.ABORT:
                if not isinstance(pdu, AbortPDU):
                    return
                if self._client_tsm:
                    self._client_tsm.handle_abort(source, pdu.invoke_id, pdu.abort_reason)
            case PduType.SEGMENT_ACK:
                if not isinstance(pdu, SegmentAckPDU):
                    return
                if pdu.sent_by_server:
                    # Server sent ACK -> we are the client receiving it
                    if self._client_tsm:
                        self._client_tsm.handle_segment_ack(source, pdu)
                else:
                    # Client sent ACK -> we are the server receiving it
                    if self._server_tsm:
                        self._server_tsm.handle_segment_ack_for_response(source, pdu)

    def _handle_segmented_request(
        self,
        pdu: ConfirmedRequestPDU,
        source: BACnetAddress,
    ) -> None:
        """Handle a segmented confirmed request (first or subsequent segment)."""
        if self._server_tsm is None:
            return

        result = self._server_tsm.receive_confirmed_request(pdu, source)
        if result is None:
            return  # Duplicate or segment processed, waiting for more

        txn, service_data = result
        if service_data is not None:
            # All segments received, dispatch to service handler
            self._spawn_task(self._dispatch_request(txn, pdu.service_choice, service_data, source))

    async def _handle_confirmed_request(
        self,
        pdu: ConfirmedRequestPDU,
        source: BACnetAddress,
    ) -> None:
        """Process incoming non-segmented confirmed request through server TSM."""
        if self._server_tsm is None:
            return

        result = self._server_tsm.receive_confirmed_request(pdu, source)
        if result is None:
            return  # Duplicate, response already resent

        txn, service_data = result
        if service_data is None:
            return  # Should not happen for non-segmented requests

        await self._dispatch_request(txn, pdu.service_choice, service_data, source)

    async def _dispatch_request(
        self,
        txn: ServerTransaction,
        service_choice: int,
        service_data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Dispatch a confirmed request to the service handler and send the response."""
        if self._server_tsm is None:
            return

        network = self._router or self._network
        if network is None:
            return

        response_pdu: SimpleAckPDU | ComplexAckPDU | ErrorPDU | RejectPDU | AbortPDU
        try:
            result = await self._service_registry.dispatch_confirmed(
                service_choice, service_data, source
            )
            if result is None:
                response_pdu = SimpleAckPDU(
                    invoke_id=txn.invoke_id,
                    service_choice=service_choice,
                )
            else:
                # Check if response needs segmentation
                max_payload = compute_max_segment_payload(
                    txn.client_max_apdu_length, "complex_ack"
                )
                if len(result) > max_payload:
                    # Response is too large for a single APDU; segment it
                    self._server_tsm.start_segmented_response(txn, service_choice, result)
                    return

                response_pdu = ComplexAckPDU(
                    segmented=False,
                    more_follows=False,
                    invoke_id=txn.invoke_id,
                    sequence_number=None,
                    proposed_window_size=None,
                    service_choice=service_choice,
                    service_ack=result,
                )
        except BACnetError as e:
            response_pdu = ErrorPDU(
                invoke_id=txn.invoke_id,
                service_choice=service_choice,
                error_class=e.error_class,
                error_code=e.error_code,
            )
        except BACnetRejectError as e:
            response_pdu = RejectPDU(
                invoke_id=txn.invoke_id,
                reject_reason=e.reason,
            )
        except BACnetAbortError as e:
            response_pdu = AbortPDU(
                sent_by_server=True,
                invoke_id=txn.invoke_id,
                abort_reason=e.reason,
            )
        except Exception:
            logger.exception("Unhandled error in service handler")
            response_pdu = AbortPDU(
                sent_by_server=True,
                invoke_id=txn.invoke_id,
                abort_reason=AbortReason.OTHER,
            )

        response_bytes = encode_apdu(response_pdu)
        network.send(response_bytes, source, expecting_reply=False)
        self._server_tsm.complete_transaction(txn, response_bytes)

    async def _handle_unconfirmed_request(
        self,
        pdu: Any,
        source: BACnetAddress,
    ) -> None:
        """Dispatch unconfirmed request to handlers."""
        if not isinstance(pdu, UnconfirmedRequestPDU):
            return

        # Dispatch to permanent handlers
        await self._service_registry.dispatch_unconfirmed(
            pdu.service_choice, pdu.service_request, source
        )

        # Dispatch to temporary listeners
        listeners = self._unconfirmed_listeners.get(pdu.service_choice, [])
        for listener in listeners:
            try:
                listener(pdu.service_request, source)
            except Exception:
                logger.debug("Error in unconfirmed listener", exc_info=True)

    # --- COV notification handlers (client role) ---

    def _dispatch_cov_notification(self, data: bytes, source: BACnetAddress) -> None:
        """Decode a COV notification and dispatch to the registered callback."""
        notification = COVNotificationRequest.decode(data)
        callback = self._cov_callbacks.get(notification.subscriber_process_identifier)
        if callback:
            try:
                callback(notification, source)
            except Exception:
                logger.debug("Error in COV callback", exc_info=True)

    async def _handle_confirmed_cov_notification(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle incoming confirmed COV notification (client role).

        Dispatches to registered COV callbacks and returns SimpleACK.
        """
        self._dispatch_cov_notification(data, source)
        return None  # SimpleACK

    async def _handle_unconfirmed_cov_notification(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle incoming unconfirmed COV notification (client role).

        Dispatches to registered COV callbacks.
        """
        self._dispatch_cov_notification(data, source)
