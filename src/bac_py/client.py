"""Simplified BACnet client combining application and client layers.

Provides a single :class:`Client` async context manager for common
client-only use cases. For advanced features (server handlers, custom
service registration, router mode), use
:class:`~bac_py.app.application.BACnetApplication` and
:class:`~bac_py.app.client.BACnetClient` directly.

Typical usage::

    from bac_py import Client, DeviceConfig

    async with Client(DeviceConfig(instance_number=999)) as client:
        value = await client.read("192.168.1.100", "ai,1", "pv")
        await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from bac_py.app.application import BACnetApplication, DeviceConfig, ForeignDeviceStatus
from bac_py.app.client import (
    BACnetClient,
    BDTEntryInfo,
    DiscoveredDevice,
    FDTEntryInfo,
    RouterInfo,
    decode_cov_values,
)

if TYPE_CHECKING:
    from bac_py.network.address import BACnetAddress
    from bac_py.services.cov import COVNotificationRequest
    from bac_py.services.file_access import (
        AtomicReadFileACK,
        AtomicWriteFileACK,
        RecordReadAccess,
        RecordWriteAccess,
        StreamReadAccess,
        StreamWriteAccess,
    )
    from bac_py.services.private_transfer import ConfirmedPrivateTransferACK
    from bac_py.services.read_property import ReadPropertyACK
    from bac_py.services.read_property_multiple import (
        ReadAccessSpecification,
        ReadPropertyMultipleACK,
    )
    from bac_py.services.read_range import (
        RangeByPosition,
        RangeBySequenceNumber,
        RangeByTime,
        ReadRangeACK,
    )
    from bac_py.services.who_has import IHaveRequest
    from bac_py.services.who_is import IAmRequest
    from bac_py.services.write_property_multiple import WriteAccessSpecification
    from bac_py.types.enums import (
        EnableDisable,
        ObjectType,
        PropertyIdentifier,
        ReinitializedState,
    )
    from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier


class Client:
    """Simplified BACnet client for common use cases.

    Combines :class:`~bac_py.app.application.BACnetApplication` and
    :class:`~bac_py.app.client.BACnetClient` into a single async
    context manager. All ``BACnetClient`` methods are available
    directly on this class.

    For advanced use (server handlers, custom service registration,
    router mode), use ``BACnetApplication`` and ``BACnetClient``
    directly.

    Usage::

        async with Client(DeviceConfig(instance_number=999)) as client:
            value = await client.read("192.168.1.100", "ai,1", "pv")
    """

    def __init__(
        self,
        config: DeviceConfig | None = None,
        *,
        instance_number: int = 999,
        interface: str = "0.0.0.0",
        port: int = 0xBAC0,
        bbmd_address: str | None = None,
        bbmd_ttl: int = 60,
    ) -> None:
        """Create a BACnet client.

        Args:
            config: Full device configuration. If provided, other
                keyword arguments are ignored.
            instance_number: Device instance number (used if *config*
                is not provided).
            interface: IP address to bind to (used if *config*
                is not provided).
            port: UDP port (used if *config* is not provided).
            bbmd_address: Optional BBMD address for foreign device
                registration (e.g. ``"192.168.1.1"`` or
                ``"192.168.1.1:47808"``). When set, the client
                registers as a foreign device on startup.
            bbmd_ttl: Registration time-to-live in seconds
                (default 60). Only used when *bbmd_address* is set.
        """
        if config is None:
            config = DeviceConfig(
                instance_number=instance_number,
                interface=interface,
                port=port,
            )
        self._config = config
        self._bbmd_address = bbmd_address
        self._bbmd_ttl = bbmd_ttl
        self._app: BACnetApplication | None = None
        self._client: BACnetClient | None = None

    @property
    def app(self) -> BACnetApplication:
        """The underlying BACnetApplication.

        Raises:
            RuntimeError: If the client has not been started.
        """
        if self._app is None:
            msg = "Client not started; use 'async with Client(...) as c:'"
            raise RuntimeError(msg)
        return self._app

    async def __aenter__(self) -> Client:
        """Start the application and return the client."""
        self._app = BACnetApplication(self._config)
        await self._app.start()
        if self._bbmd_address is not None:
            await self._app.register_as_foreign_device(
                self._bbmd_address, self._bbmd_ttl
            )
            await self._app.wait_for_registration(timeout=10.0)
        self._client = BACnetClient(self._app)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop the application."""
        if self._app is not None:
            await self._app.stop()
            self._app = None
            self._client = None

    def _require_client(self) -> BACnetClient:
        if self._client is None:
            msg = "Client not started; use 'async with Client(...) as c:'"
            raise RuntimeError(msg)
        return self._client

    # --- Convenience API (Phase 4) ---

    async def read(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        property_identifier: str | int | PropertyIdentifier,
        array_index: int | None = None,
    ) -> object:
        """Read a property and return a decoded Python value.

        See :meth:`~bac_py.app.client.BACnetClient.read` for details.
        """
        return await self._require_client().read(
            address, object_identifier, property_identifier, array_index
        )

    async def write(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        property_identifier: str | int | PropertyIdentifier,
        value: object,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a Python value to a property.

        See :meth:`~bac_py.app.client.BACnetClient.write` for details.
        """
        await self._require_client().write(
            address, object_identifier, property_identifier, value, priority, array_index
        )

    async def read_multiple(
        self,
        address: str | BACnetAddress,
        specs: dict[
            str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
            list[str | int | PropertyIdentifier],
        ],
    ) -> dict[str, dict[str, object]]:
        """Read multiple properties from multiple objects.

        See :meth:`~bac_py.app.client.BACnetClient.read_multiple` for details.
        """
        return await self._require_client().read_multiple(address, specs)

    async def write_multiple(
        self,
        address: str | BACnetAddress,
        specs: dict[
            str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
            dict[str | int | PropertyIdentifier, object],
        ],
        timeout: float | None = None,
    ) -> None:
        """Write multiple properties to multiple objects.

        See :meth:`~bac_py.app.client.BACnetClient.write_multiple` for details.
        """
        await self._require_client().write_multiple(address, specs, timeout=timeout)

    async def get_object_list(
        self,
        address: str | BACnetAddress,
        device_instance: int,
        timeout: float | None = None,
    ) -> list[ObjectIdentifier]:
        """Read the complete object list from a device.

        See :meth:`~bac_py.app.client.BACnetClient.get_object_list` for details.
        """
        return await self._require_client().get_object_list(
            address, device_instance, timeout=timeout
        )

    async def subscribe_cov_ex(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
        callback: Callable[[COVNotificationRequest, BACnetAddress], object] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to COV notifications with string arguments.

        See :meth:`~bac_py.app.client.BACnetClient.subscribe_cov_ex` for details.
        """
        await self._require_client().subscribe_cov_ex(
            address, object_identifier, process_id, confirmed, lifetime,
            callback=callback, timeout=timeout,
        )

    async def unsubscribe_cov_ex(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        process_id: int,
        unregister_callback: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Cancel a COV subscription with string arguments.

        See :meth:`~bac_py.app.client.BACnetClient.unsubscribe_cov_ex` for details.
        """
        await self._require_client().unsubscribe_cov_ex(
            address, object_identifier, process_id,
            unregister_callback=unregister_callback, timeout=timeout,
        )

    # --- Protocol-level API ---

    async def read_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> ReadPropertyACK:
        """Read a single property from a remote device.

        See :meth:`~bac_py.app.client.BACnetClient.read_property`.
        """
        return await self._require_client().read_property(
            address, object_identifier, property_identifier, array_index, timeout=timeout
        )

    async def write_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        value: bytes,
        priority: int | None = None,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Write a property value to a remote device.

        See :meth:`~bac_py.app.client.BACnetClient.write_property`.
        """
        await self._require_client().write_property(
            address,
            object_identifier,
            property_identifier,
            value,
            priority,
            array_index,
            timeout=timeout,
        )

    async def read_property_multiple(
        self,
        address: BACnetAddress,
        read_access_specs: list[ReadAccessSpecification],
        timeout: float | None = None,
    ) -> ReadPropertyMultipleACK:
        """Read multiple properties from one or more objects.

        See :meth:`~bac_py.app.client.BACnetClient.read_property_multiple`.
        """
        return await self._require_client().read_property_multiple(
            address, read_access_specs, timeout=timeout
        )

    async def write_property_multiple(
        self,
        address: BACnetAddress,
        write_access_specs: list[WriteAccessSpecification],
        timeout: float | None = None,
    ) -> None:
        """Write multiple properties to one or more objects.

        See :meth:`~bac_py.app.client.BACnetClient.write_property_multiple`.
        """
        await self._require_client().write_property_multiple(
            address, write_access_specs, timeout=timeout
        )

    async def read_range(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
        range_qualifier: RangeByPosition | RangeBySequenceNumber | RangeByTime | None = None,
        timeout: float | None = None,
    ) -> ReadRangeACK:
        """Read a range of items from a list or array property.

        See :meth:`~bac_py.app.client.BACnetClient.read_range`.
        """
        return await self._require_client().read_range(
            address,
            object_identifier,
            property_identifier,
            array_index,
            range_qualifier,
            timeout=timeout,
        )

    async def who_is(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[IAmRequest]:
        """Discover devices via Who-Is broadcast.

        See :meth:`~bac_py.app.client.BACnetClient.who_is`.

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address. Accepts an IP string
                (e.g. ``"192.168.1.255"``), a :class:`BACnetAddress`,
                or ``None`` for global broadcast.
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                responses have been collected.
        """
        from bac_py.network.address import GLOBAL_BROADCAST, parse_address

        client = self._require_client()
        dest = (
            parse_address(destination)
            if isinstance(destination, str)
            else (destination if destination is not None else GLOBAL_BROADCAST)
        )
        return await client.who_is(
            low_limit=low_limit,
            high_limit=high_limit,
            destination=dest,
            timeout=timeout,
            expected_count=expected_count,
        )

    async def discover(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[DiscoveredDevice]:
        """Discover devices via Who-Is and return enriched results.

        See :meth:`~bac_py.app.client.BACnetClient.discover`.

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address. Accepts an IP string
                (e.g. ``"192.168.1.255"``), a :class:`BACnetAddress`,
                or ``None`` for global broadcast.
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                devices have been discovered.
        """
        from bac_py.network.address import GLOBAL_BROADCAST, parse_address

        client = self._require_client()
        dest = (
            parse_address(destination)
            if isinstance(destination, str)
            else (destination if destination is not None else GLOBAL_BROADCAST)
        )
        return await client.discover(
            low_limit=low_limit,
            high_limit=high_limit,
            destination=dest,
            timeout=timeout,
            expected_count=expected_count,
        )

    async def subscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to COV notifications.

        See :meth:`~bac_py.app.client.BACnetClient.subscribe_cov`.
        """
        await self._require_client().subscribe_cov(
            address, object_identifier, process_id, confirmed, lifetime, timeout=timeout
        )

    async def unsubscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
        timeout: float | None = None,
    ) -> None:
        """Cancel a COV subscription.

        See :meth:`~bac_py.app.client.BACnetClient.unsubscribe_cov`.
        """
        await self._require_client().unsubscribe_cov(
            address, object_identifier, process_id, timeout=timeout
        )

    async def device_communication_control(
        self,
        address: BACnetAddress,
        enable_disable: EnableDisable,
        time_duration: int | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send DeviceCommunicationControl-Request.

        See :meth:`~bac_py.app.client.BACnetClient.device_communication_control`.
        """
        await self._require_client().device_communication_control(
            address, enable_disable, time_duration, password, timeout=timeout
        )

    async def reinitialize_device(
        self,
        address: BACnetAddress,
        reinitialized_state: ReinitializedState,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send ReinitializeDevice-Request.

        See :meth:`~bac_py.app.client.BACnetClient.reinitialize_device`.
        """
        await self._require_client().reinitialize_device(
            address, reinitialized_state, password, timeout=timeout
        )

    def time_synchronization(
        self,
        destination: BACnetAddress,
        date: BACnetDate,
        time: BACnetTime,
    ) -> None:
        """Send TimeSynchronization-Request.

        See :meth:`~bac_py.app.client.BACnetClient.time_synchronization`.
        """
        self._require_client().time_synchronization(destination, date, time)

    def utc_time_synchronization(
        self,
        destination: BACnetAddress,
        date: BACnetDate,
        time: BACnetTime,
    ) -> None:
        """Send UTCTimeSynchronization-Request.

        See :meth:`~bac_py.app.client.BACnetClient.utc_time_synchronization`.
        """
        self._require_client().utc_time_synchronization(destination, date, time)

    async def atomic_read_file(
        self,
        address: BACnetAddress,
        file_identifier: ObjectIdentifier,
        access_method: StreamReadAccess | RecordReadAccess,
        timeout: float | None = None,
    ) -> AtomicReadFileACK:
        """Send AtomicReadFile-Request.

        See :meth:`~bac_py.app.client.BACnetClient.atomic_read_file`.
        """
        return await self._require_client().atomic_read_file(
            address, file_identifier, access_method, timeout=timeout
        )

    async def atomic_write_file(
        self,
        address: BACnetAddress,
        file_identifier: ObjectIdentifier,
        access_method: StreamWriteAccess | RecordWriteAccess,
        timeout: float | None = None,
    ) -> AtomicWriteFileACK:
        """Send AtomicWriteFile-Request.

        See :meth:`~bac_py.app.client.BACnetClient.atomic_write_file`.
        """
        return await self._require_client().atomic_write_file(
            address, file_identifier, access_method, timeout=timeout
        )

    async def create_object(
        self,
        address: BACnetAddress,
        object_type: ObjectType | None = None,
        object_identifier: ObjectIdentifier | None = None,
        timeout: float | None = None,
    ) -> ObjectIdentifier:
        """Send CreateObject-Request.

        See :meth:`~bac_py.app.client.BACnetClient.create_object`.
        """
        return await self._require_client().create_object(
            address, object_type, object_identifier, timeout=timeout
        )

    async def delete_object(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        timeout: float | None = None,
    ) -> None:
        """Send DeleteObject-Request.

        See :meth:`~bac_py.app.client.BACnetClient.delete_object`.
        """
        await self._require_client().delete_object(address, object_identifier, timeout=timeout)

    async def add_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send AddListElement-Request.

        See :meth:`~bac_py.app.client.BACnetClient.add_list_element`.
        """
        await self._require_client().add_list_element(
            address,
            object_identifier,
            property_identifier,
            list_of_elements,
            array_index,
            timeout=timeout,
        )

    async def remove_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send RemoveListElement-Request.

        See :meth:`~bac_py.app.client.BACnetClient.remove_list_element`.
        """
        await self._require_client().remove_list_element(
            address,
            object_identifier,
            property_identifier,
            list_of_elements,
            array_index,
            timeout=timeout,
        )

    async def who_has(
        self,
        object_identifier: ObjectIdentifier | None = None,
        object_name: str | None = None,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[IHaveRequest]:
        """Discover objects via Who-Has broadcast.

        See :meth:`~bac_py.app.client.BACnetClient.who_has`.

        Args:
            object_identifier: Object to search for by identifier.
            object_name: Object to search for by name.
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address. Accepts an IP string,
                a :class:`BACnetAddress`, or ``None`` for global broadcast.
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                responses have been collected.
        """
        from bac_py.network.address import GLOBAL_BROADCAST, parse_address

        client = self._require_client()
        dest = (
            parse_address(destination)
            if isinstance(destination, str)
            else (destination if destination is not None else GLOBAL_BROADCAST)
        )
        return await client.who_has(
            object_identifier=object_identifier,
            object_name=object_name,
            low_limit=low_limit,
            high_limit=high_limit,
            destination=dest,
            timeout=timeout,
            expected_count=expected_count,
        )

    async def confirmed_private_transfer(
        self,
        address: BACnetAddress,
        vendor_id: int,
        service_number: int,
        service_parameters: bytes | None = None,
        timeout: float | None = None,
    ) -> ConfirmedPrivateTransferACK:
        """Send ConfirmedPrivateTransfer-Request.

        See :meth:`~bac_py.app.client.BACnetClient.confirmed_private_transfer`.
        """
        return await self._require_client().confirmed_private_transfer(
            address, vendor_id, service_number, service_parameters, timeout=timeout
        )

    def unconfirmed_private_transfer(
        self,
        destination: BACnetAddress,
        vendor_id: int,
        service_number: int,
        service_parameters: bytes | None = None,
    ) -> None:
        """Send UnconfirmedPrivateTransfer-Request.

        See :meth:`~bac_py.app.client.BACnetClient.unconfirmed_private_transfer`.
        """
        self._require_client().unconfirmed_private_transfer(
            destination, vendor_id, service_number, service_parameters
        )

    # --- Foreign device API ---

    async def register_as_foreign_device(
        self,
        bbmd_address: str,
        ttl: int = 60,
    ) -> None:
        """Register as a foreign device with a BBMD.

        See :meth:`~bac_py.app.application.BACnetApplication.register_as_foreign_device`.
        """
        await self.app.register_as_foreign_device(bbmd_address, ttl)

    async def deregister_foreign_device(self) -> None:
        """Deregister from the BBMD and stop re-registration.

        See :meth:`~bac_py.app.application.BACnetApplication.deregister_foreign_device`.
        """
        await self.app.deregister_foreign_device()

    @property
    def is_foreign_device(self) -> bool:
        """Whether this device is currently registered as a foreign device."""
        return self.app.is_foreign_device

    @property
    def foreign_device_status(self) -> ForeignDeviceStatus | None:
        """Current foreign device registration status."""
        return self.app.foreign_device_status

    async def wait_for_registration(self, timeout: float = 10.0) -> bool:
        """Wait for foreign device registration to complete.

        See :meth:`~bac_py.app.application.BACnetApplication.wait_for_registration`.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            ``True`` if registered, ``False`` if timeout expired.
        """
        return await self.app.wait_for_registration(timeout)

    # --- BBMD table management ---

    async def read_bdt(
        self,
        bbmd_address: str,
        timeout: float = 5.0,
    ) -> list[BDTEntryInfo]:
        """Read the Broadcast Distribution Table from a remote BBMD.

        See :meth:`~bac_py.app.client.BACnetClient.read_bdt`.
        """
        return await self._require_client().read_bdt(bbmd_address, timeout=timeout)

    async def read_fdt(
        self,
        bbmd_address: str,
        timeout: float = 5.0,
    ) -> list[FDTEntryInfo]:
        """Read the Foreign Device Table from a remote BBMD.

        See :meth:`~bac_py.app.client.BACnetClient.read_fdt`.
        """
        return await self._require_client().read_fdt(bbmd_address, timeout=timeout)

    async def write_bdt(
        self,
        bbmd_address: str,
        entries: list[BDTEntryInfo],
        timeout: float = 5.0,
    ) -> None:
        """Write a Broadcast Distribution Table to a remote BBMD.

        See :meth:`~bac_py.app.client.BACnetClient.write_bdt`.
        """
        await self._require_client().write_bdt(bbmd_address, entries, timeout=timeout)

    async def delete_fdt_entry(
        self,
        bbmd_address: str,
        entry_address: str,
        timeout: float = 5.0,
    ) -> None:
        """Delete a Foreign Device Table entry on a remote BBMD.

        See :meth:`~bac_py.app.client.BACnetClient.delete_fdt_entry`.
        """
        await self._require_client().delete_fdt_entry(
            bbmd_address, entry_address, timeout=timeout
        )

    # --- Router discovery ---

    async def who_is_router_to_network(
        self,
        network: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
    ) -> list[RouterInfo]:
        """Discover routers and reachable networks.

        See :meth:`~bac_py.app.client.BACnetClient.who_is_router_to_network`.

        Args:
            network: Optional specific network to query. If ``None``,
                discovers all reachable networks.
            destination: Target for the query. Accepts an IP string,
                a :class:`BACnetAddress`, or ``None`` for local
                broadcast.
            timeout: Seconds to wait for responses.
        """
        return await self._require_client().who_is_router_to_network(
            network=network, destination=destination, timeout=timeout
        )
