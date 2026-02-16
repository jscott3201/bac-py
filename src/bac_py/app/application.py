"""BACnet application layer orchestrator per ASHRAE 135-2016."""

from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bac_py.app.cov import COVManager
from bac_py.app.event_engine import EventEngine
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
from bac_py.transport.bip6 import BIP6Transport
from bac_py.types.enums import (
    AbortReason,
    ConfirmedServiceChoice,
    EnableDisable,
    ObjectType,
    RejectReason,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import ObjectIdentifier

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.app.tsm import ServerTransaction
    from bac_py.network.address import BACnetAddress, BIP6Address, BIPAddress
    from bac_py.transport.bbmd import BDTEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Cached peer device capabilities from I-Am responses (Clause 19.4)."""

    max_apdu_length: int
    """Maximum APDU length accepted by the peer device."""

    segmentation_supported: int
    """Segmentation support level (Segmentation enum value)."""


@dataclass
class BBMDConfig:
    """Configuration for BBMD on a router port."""

    bdt_entries: list[BDTEntry] = field(default_factory=list)
    """Initial Broadcast Distribution Table entries (including self).

    If empty, the BBMD starts with an empty BDT (foreign-device-only mode).
    """


@dataclass
class RouterPortConfig:
    """Configuration for a single router port."""

    port_id: int
    network_number: int
    interface: str = "0.0.0.0"
    port: int = 0xBAC0
    broadcast_address: str = "255.255.255.255"
    """Directed broadcast address for this port's subnet."""
    bbmd_config: BBMDConfig | None = None
    ipv6: bool = False
    """Use BACnet/IPv6 (Annex U) transport for this port."""
    multicast_address: str = ""
    """IPv6 multicast group address. Defaults to ``ff02::bac0``."""
    vmac: bytes | None = None
    """3-byte VMAC for IPv6. Auto-generated if ``None``."""


@dataclass
class RouterConfig:
    """Configuration for a router device."""

    ports: list[RouterPortConfig] = field(default_factory=list)
    application_port_id: int = 1


@dataclass
class DeviceConfig:
    """Configuration for a BACnet device."""

    instance_number: int
    """BACnet device instance number (0-4194302)."""

    name: str = "bac-py"
    """Device object name."""

    vendor_name: str = "bac-py"
    """Vendor name string."""

    vendor_id: int = 0
    """ASHRAE-assigned vendor identifier."""

    model_name: str = "bac-py"
    """Device model name string."""

    firmware_revision: str = ""
    """Firmware revision string. Defaults to the bac-py package version."""

    application_software_version: str = ""
    """Application software version string. Defaults to the bac-py package version."""

    interface: str = "0.0.0.0"
    """Local IP address to bind to (``"0.0.0.0"`` for all)."""

    port: int = 0xBAC0
    """UDP port number (default ``0xBAC0`` / 47808)."""

    apdu_timeout: int = 6000  # milliseconds
    """APDU timeout in milliseconds."""

    apdu_segment_timeout: int = 2000  # milliseconds
    """Segment timeout in milliseconds."""

    apdu_retries: int = 3
    """Maximum number of APDU retries."""

    max_apdu_length: int = 1476
    """Maximum APDU length in bytes."""

    max_segments: int | None = None
    """Maximum segments accepted, or ``None`` for unlimited."""

    router_config: RouterConfig | None = None
    """Optional router configuration for multi-network mode."""

    broadcast_address: str = "255.255.255.255"
    """Directed broadcast address for this subnet. Default global
    broadcast works on physical networks; set to the subnet broadcast
    (e.g. ``"192.168.1.255"``) when running in Docker bridge networks
    where global broadcast is not routable."""

    password: str | None = None
    """Optional password for DeviceCommunicationControl and ReinitializeDevice
    services (1-20 characters, per Clause 16.1.3.1 and 16.4.3.4).
    When set, incoming requests must include a matching password."""

    ipv6: bool = False
    """Use BACnet/IPv6 (Annex U) transport instead of BACnet/IP (Annex J)."""

    multicast_address: str = ""
    """IPv6 multicast group address. Defaults to ``ff02::bac0`` when *ipv6*
    is ``True``.  Ignored for IPv4 mode."""

    vmac: bytes | None = None
    """3-byte VMAC for IPv6 transport. Auto-generated if ``None``.
    Ignored for IPv4 mode."""

    def __post_init__(self) -> None:
        """Fill version defaults from the bac-py package version."""
        if not self.firmware_revision or not self.application_software_version:
            import bac_py  # lazy to avoid circular import

            if not self.firmware_revision:
                self.firmware_revision = bac_py.__version__
            if not self.application_software_version:
                self.application_software_version = bac_py.__version__


@dataclass(frozen=True, slots=True)
class ForeignDeviceStatus:
    """Foreign device registration status.

    Provides a snapshot of the current registration state when
    operating as a foreign device via a BBMD.
    """

    bbmd_address: str
    """BBMD address string (e.g. ``"192.168.1.1:47808"``)."""

    ttl: int
    """Registration time-to-live in seconds."""

    is_registered: bool
    """Whether registration is currently active."""

    last_result: str | None
    """Last BVLC result code name, or ``None`` if no response yet."""


class BACnetApplication:
    """Central orchestrator connecting all protocol layers.

    Wires transport, network, TSMs, and service dispatch.
    """

    def __init__(self, config: DeviceConfig) -> None:
        """Initialise the application from a device configuration.

        :param config: Device and network parameters for this BACnet device.
        """
        self._config = config
        self._transport: BIPTransport | BIP6Transport | None = None
        self._network: NetworkLayer | None = None
        self._router: NetworkRouter | None = None
        self._transports: list[BIPTransport | BIP6Transport] = []
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
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cov_manager: COVManager | None = None
        self._event_engine: EventEngine | None = None
        self._cov_callbacks: dict[int, Callable[..., Any]] = {}
        self._dcc_state: EnableDisable = EnableDisable.ENABLE
        self._dcc_timer: asyncio.TimerHandle | None = None
        self._device_info_cache: dict[BACnetAddress, DeviceInfo] = {}

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
    def event_engine(self) -> EventEngine | None:
        """The event/alarm evaluation engine, or None if not started."""
        return self._event_engine

    @property
    def dcc_state(self) -> EnableDisable:
        """The current DeviceCommunicationControl state."""
        return self._dcc_state

    def set_dcc_state(
        self,
        state: EnableDisable,
        duration: int | None = None,
    ) -> None:
        """Set the DeviceCommunicationControl state.

        :param state: New DCC state (ENABLE, DISABLE, or DISABLE_INITIATION).
        :param duration: Optional duration in minutes. When provided and state
            is not ENABLE, a timer is set to auto-re-enable after the
            specified number of minutes.
        """
        # Cancel any existing DCC timer
        if self._dcc_timer is not None:
            self._dcc_timer.cancel()
            self._dcc_timer = None

        self._dcc_state = state

        if duration is not None and state != EnableDisable.ENABLE:
            loop = asyncio.get_running_loop()
            self._dcc_timer = loop.call_later(
                duration * 60,
                self._dcc_timer_expired,
            )

    @property
    def device_object_identifier(self) -> Any:
        """The device object identifier for this application.

        Returns the ObjectIdentifier of the device object from the
        object database. Used by the COV manager to populate the
        initiating device identifier in notifications.
        """
        return ObjectIdentifier(ObjectType.DEVICE, self._config.instance_number)

    def get_device_info(self, address: BACnetAddress) -> DeviceInfo | None:
        """Look up cached peer device capabilities.

        Returns cached :class:`DeviceInfo` from I-Am responses, or
        ``None`` if no information is available for *address*.

        :param address: The peer device address.
        :returns: Cached device info, or ``None``.
        """
        return self._device_info_cache.get(address)

    async def start(self) -> None:
        """Start the transport and initialize all layers."""
        logger.info(
            "BACnetApplication starting on %s:%d (instance=%d)",
            self._config.interface,
            self._config.port,
            self._config.instance_number,
        )
        self._stopped = False
        self._stop_event = asyncio.Event()
        self._loop = asyncio.get_running_loop()

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

        # Initialize event engine and start evaluation loop
        self._event_engine = EventEngine(self)
        await self._event_engine.start()

        # Register I-Am listener for device info caching (Clause 19.4)
        self._service_registry.register_unconfirmed(
            UnconfirmedServiceChoice.I_AM,
            self._handle_i_am_for_cache,
        )

        # Broadcast I-Am on startup per Clause 12.11.13
        self._broadcast_i_am()

        logger.info("BACnetApplication started")

    async def _start_non_router_mode(self) -> None:
        """Start in non-router (simple device) mode."""
        if self._config.ipv6 or ":" in self._config.interface:
            iface = self._config.interface if self._config.interface != "0.0.0.0" else "::"
            mcast = self._config.multicast_address or "ff02::bac0"
            self._transport = BIP6Transport(
                interface=iface,
                port=self._config.port,
                multicast_address=mcast,
                vmac=self._config.vmac,
            )
        else:
            self._transport = BIPTransport(
                interface=self._config.interface,
                port=self._config.port,
                broadcast_address=self._config.broadcast_address,
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
            transport: BIPTransport | BIP6Transport
            if pc.ipv6 or ":" in pc.interface:
                iface = pc.interface if pc.interface != "0.0.0.0" else "::"
                mcast = pc.multicast_address or "ff02::bac0"
                transport = BIP6Transport(
                    interface=iface,
                    port=pc.port,
                    multicast_address=mcast,
                    vmac=pc.vmac,
                )
            else:
                transport = BIPTransport(
                    interface=pc.interface,
                    port=pc.port,
                    broadcast_address=pc.broadcast_address,
                )
            await transport.start()
            self._transports.append(transport)

            # Attach BBMD if configured for this port
            if pc.bbmd_config is not None:
                await transport.attach_bbmd(pc.bbmd_config.bdt_entries or None)  # type: ignore[arg-type]

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
        logger.info("BACnetApplication stopping")
        self._stopped = True

        # Shutdown event engine
        if self._event_engine:
            await self._event_engine.stop()
            self._event_engine = None

        # Shutdown COV manager (cancel subscription timers)
        if self._cov_manager:
            self._cov_manager.shutdown()
            self._cov_manager = None

        # Cancel DCC timer
        if self._dcc_timer is not None:
            self._dcc_timer.cancel()
            self._dcc_timer = None

        # Cancel all pending client transactions
        if self._client_tsm:
            for txn in self._client_tsm.active_transactions():
                if not txn.future.done():
                    txn.future.cancel()

        if self._stop_event:
            self._stop_event.set()

        # Cancel all background tasks (copy to avoid mutation during iteration)
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

        if self._router:
            await self._router.stop()
        elif self._transport:
            await self._transport.stop()

        # Clear caches and listener registrations to release references
        self._unconfirmed_listeners.clear()
        self._device_info_cache.clear()
        self._running = False
        logger.info("BACnetApplication stopped")

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

    def _broadcast_i_am(self) -> None:
        """Broadcast I-Am on startup per Clause 12.11.13.

        Sends an unsolicited I-Am to the global broadcast address
        using the device's configuration parameters.
        """
        from bac_py.network.address import GLOBAL_BROADCAST
        from bac_py.services.who_is import IAmRequest
        from bac_py.types.enums import PropertyIdentifier, Segmentation

        # Get segmentation supported from device object if available
        device_oid = self.device_object_identifier
        device_obj = self._object_db.get(device_oid)
        if device_obj is not None:
            try:
                segmentation = device_obj.read_property(PropertyIdentifier.SEGMENTATION_SUPPORTED)
            except Exception:
                segmentation = Segmentation.BOTH
        else:
            segmentation = Segmentation.BOTH

        iam = IAmRequest(
            object_identifier=device_oid,
            max_apdu_length=self._config.max_apdu_length,
            segmentation_supported=segmentation,
            vendor_id=self._config.vendor_id,
        )
        self.unconfirmed_request(
            destination=GLOBAL_BROADCAST,
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_data=iam.encode(),
        )

    # --- Foreign device API ---

    def _parse_bip_address(self, address: str) -> BIPAddress:
        """Parse a string to a BIPAddress.

        Accepts ``"host:port"`` or ``"host"`` (default port 47808).
        """
        from bac_py.network.address import BIPAddress as _BIPAddress

        if ":" in address:
            host, port_str = address.rsplit(":", 1)
            return _BIPAddress(host=host, port=int(port_str))
        return _BIPAddress(host=address, port=0xBAC0)

    def _parse_bip6_address(self, address: str) -> BIP6Address:
        """Parse a string to a BIP6Address.

        Accepts ``"[host]:port"`` or ``"host"`` (default port 47808).
        """
        from bac_py.network.address import BIP6Address as _BIP6Address

        if address.startswith("["):
            # "[host]:port" format
            bracket_end = address.index("]")
            host = address[1:bracket_end]
            rest = address[bracket_end + 1 :]
            if rest.startswith(":"):
                return _BIP6Address(host=host, port=int(rest[1:]))
            return _BIP6Address(host=host, port=0xBAC0)
        return _BIP6Address(host=address, port=0xBAC0)

    async def register_as_foreign_device(
        self,
        bbmd_address: str,
        ttl: int = 60,
    ) -> None:
        """Register as a foreign device with a BBMD.

        Attaches a foreign device manager to the primary transport and
        begins periodic re-registration at TTL/2 intervals.

        :param bbmd_address: Address of the BBMD. For IPv4 use
            ``"192.168.1.1"`` or ``"192.168.1.1:47808"``. For IPv6 use
            ``"[fd00::1]:47808"`` or ``"fd00::1"``.
        :param ttl: Registration time-to-live in seconds.
        :raises RuntimeError: If already registered, application not started,
            or running in router mode.
        """
        if self._transport is None:
            if self._router is not None:
                msg = "Foreign device registration is not supported in router mode"
                raise RuntimeError(msg)
            msg = "Application not started"
            raise RuntimeError(msg)
        if self._transport.foreign_device is not None:
            msg = "Already registered as a foreign device"
            raise RuntimeError(msg)

        if isinstance(self._transport, BIP6Transport):
            addr = self._parse_bip6_address(bbmd_address)
            await self._transport.attach_foreign_device(addr, ttl)
        else:
            bip_addr = self._parse_bip_address(bbmd_address)
            await self._transport.attach_foreign_device(bip_addr, ttl)

    async def deregister_foreign_device(self) -> None:
        """Deregister from the BBMD and stop re-registration.

        Sends a Delete-Foreign-Device-Table-Entry to the BBMD so the
        entry is removed immediately rather than waiting for TTL expiry.

        :raises RuntimeError: If not registered as a foreign device.
        """
        if self._transport is None or self._transport.foreign_device is None:
            msg = "Not registered as a foreign device"
            raise RuntimeError(msg)
        await self._transport.foreign_device.stop()
        self._transport._foreign_device = None

    @property
    def is_foreign_device(self) -> bool:
        """Whether this device is currently registered as a foreign device."""
        return (
            self._transport is not None
            and self._transport.foreign_device is not None
            and self._transport.foreign_device.is_registered
        )

    @property
    def foreign_device_status(self) -> ForeignDeviceStatus | None:
        """Current foreign device registration status.

        Returns ``None`` if foreign device mode is not active.
        """
        if self._transport is None or self._transport.foreign_device is None:
            return None
        fd = self._transport.foreign_device
        return ForeignDeviceStatus(
            bbmd_address=f"{fd.bbmd_address.host}:{fd.bbmd_address.port}",
            ttl=fd.ttl,
            is_registered=fd.is_registered,
            last_result=fd.last_result.name if fd.last_result is not None else None,
        )

    async def wait_for_registration(self, timeout: float = 10.0) -> bool:
        """Wait for foreign device registration to complete.

        Blocks until the BBMD confirms registration or the timeout
        elapses. Useful after :meth:`register_as_foreign_device` to
        ensure broadcasts will be distributed before performing
        discovery.

        :param timeout: Maximum seconds to wait.
        :returns: ``True`` if registered, ``False`` if timeout expired.
        """
        if self._transport is None or self._transport.foreign_device is None:
            return False
        fd = self._transport.foreign_device
        try:
            await asyncio.wait_for(fd._registered.wait(), timeout)
        except TimeoutError:
            return False
        return fd.is_registered

    # --- Network message API ---

    def send_network_message(
        self,
        message_type: int,
        data: bytes,
        destination: BACnetAddress | None = None,
    ) -> None:
        """Send a network-layer message (non-APDU).

        :param message_type: Network message type code.
        :param data: Encoded message payload.
        :param destination: Target address. If ``None``, broadcasts locally.
        :raises RuntimeError: If the application is not started or is
            running in router mode (which has its own message API).
        """
        if self._network is None:
            msg = "Network layer not available"
            raise RuntimeError(msg)
        self._network.send_network_message(message_type, data, destination)

    def add_route(self, network: int, router_address: str) -> None:
        """Pre-populate the router cache for a remote network.

        Allows sending to a remote network without broadcast-based
        router discovery.  Useful in Docker or test environments
        where broadcast delivery is unreliable.

        :param network: The remote network number.
        :param router_address: IP address of the router (e.g.
            ``"172.30.1.150"`` or ``"172.30.1.150:47808"``).
        :raises RuntimeError: If the application is not started.
        """
        if self._network is None:
            msg = "Network layer not available"
            raise RuntimeError(msg)
        from bac_py.network.address import parse_address

        addr = parse_address(router_address)
        self._network.add_route(network, addr.mac_address)

    def register_network_message_handler(
        self,
        message_type: int,
        handler: Callable[..., None],
    ) -> None:
        """Register a handler for incoming network-layer messages.

        :param message_type: Network message type code to listen for.
        :param handler: Called with ``(decoded_message, source_mac)`` when a
            matching network message is received.
        :raises RuntimeError: If the network layer is not available.
        """
        if self._network is None:
            msg = "Network layer not available"
            raise RuntimeError(msg)
        self._network.register_network_message_handler(message_type, handler)

    def unregister_network_message_handler(
        self,
        message_type: int,
        handler: Callable[..., None],
    ) -> None:
        """Remove a network-layer message handler.

        :param message_type: Network message type code.
        :param handler: The handler to remove.
        """
        if self._network is not None:
            self._network.unregister_network_message_handler(message_type, handler)

    async def _handle_i_am_for_cache(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Cache peer device info from incoming I-Am responses (Clause 19.4)."""
        try:
            from bac_py.services.who_is import IAmRequest

            iam = IAmRequest.decode(data)
            # Evict oldest entries if cache exceeds limit to prevent unbounded growth
            if len(self._device_info_cache) >= 1000:
                # Remove first 100 entries (FIFO order preserved in Python 3.7+ dicts)
                for evict_key in list(self._device_info_cache)[:100]:
                    del self._device_info_cache[evict_key]
            self._device_info_cache[source] = DeviceInfo(
                max_apdu_length=iam.max_apdu_length,
                segmentation_supported=int(iam.segmentation_supported),
            )
            logger.debug(
                f"cached device info: instance={iam.object_identifier} "
                f"max_apdu={iam.max_apdu_length} from {source}"
            )
        except Exception:
            logger.debug("Failed to decode I-Am for cache from %s", source, exc_info=True)

    async def confirmed_request(
        self,
        destination: BACnetAddress,
        service_choice: int,
        service_data: bytes,
        timeout: float | None = None,
    ) -> bytes:
        """Send a confirmed request and await response.

        :param destination: Target device address.
        :param service_choice: Confirmed service choice number.
        :param service_data: Encoded service request bytes.
        :param timeout: Optional caller-level timeout in seconds. When
            provided, the request is cancelled if no response is
            received within this duration (raises ``asyncio.TimeoutError``).
            When ``None``, the TSM's built-in retry/timeout logic is
            used exclusively.
        :returns: ComplexACK service data, or empty bytes for SimpleACK.
        """
        if self._client_tsm is None:
            msg = "Application not started"
            raise RuntimeError(msg)

        logger.debug("sending confirmed request service=%s to %s", service_choice, destination)

        # Constrain APDU size to peer capability if cached (Clause 19.4)
        max_apdu_override: int | None = None
        device_info = self._device_info_cache.get(destination)
        if device_info is not None:
            max_apdu_override = min(self._config.max_apdu_length, device_info.max_apdu_length)

        coro = self._client_tsm.send_request(
            service_choice,
            service_data,
            destination,
            max_apdu_override=max_apdu_override,
        )
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout)
        return await coro

    def unconfirmed_request(
        self,
        destination: BACnetAddress,
        service_choice: int,
        service_data: bytes,
    ) -> None:
        """Send an unconfirmed request.

        :param destination: Target device address.
        :param service_choice: Unconfirmed service choice number.
        :param service_data: Encoded service request bytes.
        """
        network = self._router or self._network
        if network is None:
            msg = "Application not started"
            raise RuntimeError(msg)

        # DCC enforcement: suppress outbound unsolicited when DISABLE_INITIATION
        if self._dcc_state == EnableDisable.DISABLE_INITIATION:
            logger.debug(
                "DCC DISABLE_INITIATION: suppressing outbound unconfirmed service %d",
                service_choice,
            )
            return
        if self._dcc_state == EnableDisable.DISABLE:
            logger.debug(
                "DCC DISABLE: suppressing outbound unconfirmed service %d",
                service_choice,
            )
            return
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

        :param service_data: Encoded service request bytes.
        :param destination: Target device address.
        :param service_choice: Confirmed service choice number.
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

        :param process_id: Subscriber process identifier to match.
        :param callback: Called with ``(notification, source)`` when a
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
        loop = self._loop or asyncio.get_running_loop()
        task = loop.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        """Clean up a finished background task and log unexpected errors."""
        self._background_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Background task failed: %s", task.exception(), exc_info=task.exception())

    def _dcc_timer_expired(self) -> None:
        """Re-enable communication after DCC timer expires."""
        self._dcc_state = EnableDisable.ENABLE
        self._dcc_timer = None
        logger.info("DCC timer expired, communication re-enabled")

    # Services allowed when DCC is DISABLE (per Clause 16.1)
    _DCC_ALLOWED_SERVICES: frozenset[int] = frozenset(
        {
            ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
            ConfirmedServiceChoice.REINITIALIZE_DEVICE,
        }
    )

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

        if isinstance(pdu, ConfirmedRequestPDU):
            if pdu.segmented:
                self._handle_segmented_request(pdu, source)
            else:
                self._spawn_task(self._handle_confirmed_request(pdu, source))
        elif isinstance(pdu, UnconfirmedRequestPDU):
            self._spawn_task(self._handle_unconfirmed_request(pdu, source))
        elif isinstance(pdu, SimpleAckPDU):
            if self._client_tsm:
                self._client_tsm.handle_simple_ack(source, pdu.invoke_id, pdu.service_choice)
        elif isinstance(pdu, ComplexAckPDU):
            if self._client_tsm and pdu.segmented:
                self._client_tsm.handle_segmented_complex_ack(source, pdu)
            elif self._client_tsm:
                self._client_tsm.handle_complex_ack(
                    source, pdu.invoke_id, pdu.service_choice, pdu.service_ack
                )
        elif isinstance(pdu, ErrorPDU):
            if self._client_tsm:
                self._client_tsm.handle_error(
                    source,
                    pdu.invoke_id,
                    pdu.error_class,
                    pdu.error_code,
                    pdu.error_data,
                )
        elif isinstance(pdu, RejectPDU):
            if self._client_tsm:
                self._client_tsm.handle_reject(source, pdu.invoke_id, pdu.reject_reason)
        elif isinstance(pdu, AbortPDU):
            if self._client_tsm:
                self._client_tsm.handle_abort(source, pdu.invoke_id, pdu.abort_reason)
        elif isinstance(pdu, SegmentAckPDU):
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

        logger.debug("dispatching confirmed service %s from %s", service_choice, source)

        # DCC enforcement: when DISABLE, only allow DCC and ReinitializeDevice
        if (
            self._dcc_state == EnableDisable.DISABLE
            and service_choice not in self._DCC_ALLOWED_SERVICES
        ):
            logger.debug(
                "DCC DISABLE: dropping confirmed service %d from %s",
                service_choice,
                source,
            )
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
                error_data=e.error_data,
            )
        except BACnetRejectError as e:
            if e.reason == RejectReason.UNRECOGNIZED_SERVICE:
                logger.warning("no handler for confirmed service %s", service_choice)
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
        except (ValueError, IndexError, struct.error):
            # Malformed service data (truncated, bad encoding, etc.)
            logger.debug(
                "Malformed service data for service %d from %s",
                service_choice,
                source,
                exc_info=True,
            )
            response_pdu = RejectPDU(
                invoke_id=txn.invoke_id,
                reject_reason=RejectReason.INVALID_PARAMETER_DATA_TYPE,
            )
        except Exception as exc:
            logger.error("handler error for service %s: %s", service_choice, exc, exc_info=True)
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

        # DCC enforcement for unconfirmed requests
        if self._dcc_state == EnableDisable.DISABLE:
            logger.debug(
                "DCC DISABLE: dropping unconfirmed service %d from %s",
                pdu.service_choice,
                source,
            )
            return
        if self._dcc_state == EnableDisable.DISABLE_INITIATION and pdu.service_choice not in {
            UnconfirmedServiceChoice.WHO_IS,
            UnconfirmedServiceChoice.WHO_HAS,
        }:
            logger.debug(
                "DCC DISABLE_INITIATION: dropping unconfirmed service %d from %s",
                pdu.service_choice,
                source,
            )
            return

        logger.debug("dispatching unconfirmed service %s from %s", pdu.service_choice, source)

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
