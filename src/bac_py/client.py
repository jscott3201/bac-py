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

from typing import TYPE_CHECKING

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient, DiscoveredDevice

if TYPE_CHECKING:
    from bac_py.network.address import BACnetAddress
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
        """
        if config is None:
            config = DeviceConfig(
                instance_number=instance_number,
                interface=interface,
                port=port,
            )
        self._config = config
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

    # --- Protocol-level API ---

    async def read_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
    ) -> ReadPropertyACK:
        """Read a single property from a remote device.

        See :meth:`~bac_py.app.client.BACnetClient.read_property`.
        """
        return await self._require_client().read_property(
            address, object_identifier, property_identifier, array_index
        )

    async def write_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        value: bytes,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property value to a remote device.

        See :meth:`~bac_py.app.client.BACnetClient.write_property`.
        """
        await self._require_client().write_property(
            address, object_identifier, property_identifier, value, priority, array_index
        )

    async def read_property_multiple(
        self,
        address: BACnetAddress,
        read_access_specs: list[ReadAccessSpecification],
    ) -> ReadPropertyMultipleACK:
        """Read multiple properties from one or more objects.

        See :meth:`~bac_py.app.client.BACnetClient.read_property_multiple`.
        """
        return await self._require_client().read_property_multiple(address, read_access_specs)

    async def write_property_multiple(
        self,
        address: BACnetAddress,
        write_access_specs: list[WriteAccessSpecification],
    ) -> None:
        """Write multiple properties to one or more objects.

        See :meth:`~bac_py.app.client.BACnetClient.write_property_multiple`.
        """
        await self._require_client().write_property_multiple(address, write_access_specs)

    async def read_range(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
        range_qualifier: RangeByPosition | RangeBySequenceNumber | RangeByTime | None = None,
    ) -> ReadRangeACK:
        """Read a range of items from a list or array property.

        See :meth:`~bac_py.app.client.BACnetClient.read_range`.
        """
        return await self._require_client().read_range(
            address, object_identifier, property_identifier, array_index, range_qualifier
        )

    async def who_is(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress | None = None,
        timeout: float = 3.0,
    ) -> list[IAmRequest]:
        """Discover devices via Who-Is broadcast.

        See :meth:`~bac_py.app.client.BACnetClient.who_is`.
        """
        client = self._require_client()
        kwargs: dict[str, object] = {
            "low_limit": low_limit,
            "high_limit": high_limit,
            "timeout": timeout,
        }
        if destination is not None:
            kwargs["destination"] = destination
        return await client.who_is(**kwargs)  # type: ignore[arg-type]

    async def discover(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress | None = None,
        timeout: float = 3.0,
    ) -> list[DiscoveredDevice]:
        """Discover devices via Who-Is and return enriched results.

        See :meth:`~bac_py.app.client.BACnetClient.discover`.
        """
        client = self._require_client()
        kwargs: dict[str, object] = {
            "low_limit": low_limit,
            "high_limit": high_limit,
            "timeout": timeout,
        }
        if destination is not None:
            kwargs["destination"] = destination
        return await client.discover(**kwargs)  # type: ignore[arg-type]

    async def subscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
    ) -> None:
        """Subscribe to COV notifications.

        See :meth:`~bac_py.app.client.BACnetClient.subscribe_cov`.
        """
        await self._require_client().subscribe_cov(
            address, object_identifier, process_id, confirmed, lifetime
        )

    async def unsubscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
    ) -> None:
        """Cancel a COV subscription.

        See :meth:`~bac_py.app.client.BACnetClient.unsubscribe_cov`.
        """
        await self._require_client().unsubscribe_cov(address, object_identifier, process_id)

    async def device_communication_control(
        self,
        address: BACnetAddress,
        enable_disable: EnableDisable,
        time_duration: int | None = None,
        password: str | None = None,
    ) -> None:
        """Send DeviceCommunicationControl-Request.

        See :meth:`~bac_py.app.client.BACnetClient.device_communication_control`.
        """
        await self._require_client().device_communication_control(
            address, enable_disable, time_duration, password
        )

    async def reinitialize_device(
        self,
        address: BACnetAddress,
        reinitialized_state: ReinitializedState,
        password: str | None = None,
    ) -> None:
        """Send ReinitializeDevice-Request.

        See :meth:`~bac_py.app.client.BACnetClient.reinitialize_device`.
        """
        await self._require_client().reinitialize_device(address, reinitialized_state, password)

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
    ) -> AtomicReadFileACK:
        """Send AtomicReadFile-Request.

        See :meth:`~bac_py.app.client.BACnetClient.atomic_read_file`.
        """
        return await self._require_client().atomic_read_file(
            address, file_identifier, access_method
        )

    async def atomic_write_file(
        self,
        address: BACnetAddress,
        file_identifier: ObjectIdentifier,
        access_method: StreamWriteAccess | RecordWriteAccess,
    ) -> AtomicWriteFileACK:
        """Send AtomicWriteFile-Request.

        See :meth:`~bac_py.app.client.BACnetClient.atomic_write_file`.
        """
        return await self._require_client().atomic_write_file(
            address, file_identifier, access_method
        )

    async def create_object(
        self,
        address: BACnetAddress,
        object_type: ObjectType | None = None,
        object_identifier: ObjectIdentifier | None = None,
    ) -> ObjectIdentifier:
        """Send CreateObject-Request.

        See :meth:`~bac_py.app.client.BACnetClient.create_object`.
        """
        return await self._require_client().create_object(address, object_type, object_identifier)

    async def delete_object(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
    ) -> None:
        """Send DeleteObject-Request.

        See :meth:`~bac_py.app.client.BACnetClient.delete_object`.
        """
        await self._require_client().delete_object(address, object_identifier)

    async def add_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
    ) -> None:
        """Send AddListElement-Request.

        See :meth:`~bac_py.app.client.BACnetClient.add_list_element`.
        """
        await self._require_client().add_list_element(
            address, object_identifier, property_identifier, list_of_elements, array_index
        )

    async def remove_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
    ) -> None:
        """Send RemoveListElement-Request.

        See :meth:`~bac_py.app.client.BACnetClient.remove_list_element`.
        """
        await self._require_client().remove_list_element(
            address, object_identifier, property_identifier, list_of_elements, array_index
        )

    async def who_has(
        self,
        object_identifier: ObjectIdentifier | None = None,
        object_name: str | None = None,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress | None = None,
        timeout: float = 3.0,
    ) -> list[IHaveRequest]:
        """Discover objects via Who-Has broadcast.

        See :meth:`~bac_py.app.client.BACnetClient.who_has`.
        """
        client = self._require_client()
        kwargs: dict[str, object] = {
            "object_identifier": object_identifier,
            "object_name": object_name,
            "low_limit": low_limit,
            "high_limit": high_limit,
            "timeout": timeout,
        }
        if destination is not None:
            kwargs["destination"] = destination
        return await client.who_has(**kwargs)  # type: ignore[arg-type]

    async def confirmed_private_transfer(
        self,
        address: BACnetAddress,
        vendor_id: int,
        service_number: int,
        service_parameters: bytes | None = None,
    ) -> ConfirmedPrivateTransferACK:
        """Send ConfirmedPrivateTransfer-Request.

        See :meth:`~bac_py.app.client.BACnetClient.confirmed_private_transfer`.
        """
        return await self._require_client().confirmed_private_transfer(
            address, vendor_id, service_number, service_parameters
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
