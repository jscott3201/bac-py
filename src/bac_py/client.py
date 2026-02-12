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

from bac_py.app.application import BACnetApplication, DeviceConfig, ForeignDeviceStatus
from bac_py.app.client import (
    BackupData,
    BACnetClient,
    BDTEntryInfo,
    DiscoveredDevice,
    FDTEntryInfo,
    RouterInfo,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.network.address import BACnetAddress
    from bac_py.services.alarm_summary import (
        GetAlarmSummaryACK,
        GetEnrollmentSummaryACK,
        GetEventInformationACK,
    )
    from bac_py.services.audit import AuditLogQueryACK
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
    from bac_py.types.audit_types import AuditQueryBySource, AuditQueryByTarget
    from bac_py.types.constructed import BACnetTimeStamp
    from bac_py.types.enums import (
        AcknowledgmentFilter,
        EnableDisable,
        EventState,
        EventType,
        MessagePriority,
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

        :param config: Full device configuration. If provided, other
            keyword arguments are ignored.
        :param instance_number: Device instance number (used if *config*
            is not provided).
        :param interface: IP address to bind to (used if *config*
            is not provided).
        :param port: UDP port (used if *config* is not provided).
        :param bbmd_address: Optional BBMD address for foreign device
            registration (e.g. ``"192.168.1.1"`` or
            ``"192.168.1.1:47808"``). When set, the client
            registers as a foreign device on startup.
        :param bbmd_ttl: Registration time-to-live in seconds
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

        :raises RuntimeError: If the client has not been started.
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
            await self._app.register_as_foreign_device(self._bbmd_address, self._bbmd_ttl)
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
            address,
            object_identifier,
            process_id,
            confirmed,
            lifetime,
            callback=callback,
            timeout=timeout,
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
            address,
            object_identifier,
            process_id,
            unregister_callback=unregister_callback,
            timeout=timeout,
        )

    # --- Discovery ---

    async def discover_extended(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
        expected_count: int | None = None,
        enrich_timeout: float = 5.0,
    ) -> list[DiscoveredDevice]:
        """Discover devices and enrich with profile metadata (Annex X).

        Like :meth:`discover`, but also reads ``Profile_Name``,
        ``Profile_Location``, and ``Tags`` from each device.

        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address. Accepts an IP string
            (e.g. ``"192.168.1.255"``), a :class:`BACnetAddress`,
            or ``None`` for global broadcast.
        :param timeout: Seconds to wait for Who-Is responses.
        :param expected_count: Return early once this many devices respond.
        :param enrich_timeout: Per-device timeout for RPM enrichment.
        :returns: List of :class:`DiscoveredDevice` with profile metadata.
        """
        from bac_py.network.address import GLOBAL_BROADCAST, parse_address

        client = self._require_client()
        dest = (
            parse_address(destination)
            if isinstance(destination, str)
            else (destination if destination is not None else GLOBAL_BROADCAST)
        )
        return await client.discover_extended(
            low_limit=low_limit,
            high_limit=high_limit,
            destination=dest,
            timeout=timeout,
            expected_count=expected_count,
            enrich_timeout=enrich_timeout,
        )

    # --- Alarm management ---

    async def get_alarm_summary(
        self,
        address: str | BACnetAddress,
        timeout: float | None = None,
    ) -> GetAlarmSummaryACK:
        """Get a summary of active alarms from a device.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`GetAlarmSummaryACK` with alarm entries.
        """
        from bac_py.network.address import parse_address

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        return await client.get_alarm_summary(addr, timeout=timeout)

    async def get_enrollment_summary(
        self,
        address: str | BACnetAddress,
        acknowledgment_filter: AcknowledgmentFilter,
        event_state_filter: EventState | None = None,
        event_type_filter: EventType | None = None,
        priority_min: int | None = None,
        priority_max: int | None = None,
        notification_class_filter: int | None = None,
        timeout: float | None = None,
    ) -> GetEnrollmentSummaryACK:
        """Get a filtered summary of event enrollments from a device.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param acknowledgment_filter: Filter by acknowledgment state.
        :param event_state_filter: Optional filter by event state.
        :param event_type_filter: Optional filter by event type.
        :param priority_min: Optional minimum priority (0--255).
        :param priority_max: Optional maximum priority (0--255).
        :param notification_class_filter: Optional notification class filter.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`GetEnrollmentSummaryACK`.
        """
        from bac_py.network.address import parse_address

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        return await client.get_enrollment_summary(
            addr,
            acknowledgment_filter,
            event_state_filter=event_state_filter,
            event_type_filter=event_type_filter,
            priority_min=priority_min,
            priority_max=priority_max,
            notification_class_filter=notification_class_filter,
            timeout=timeout,
        )

    async def get_event_information(
        self,
        address: str | BACnetAddress,
        last_received_object_identifier: (
            str | tuple[str | ObjectType | int, int] | ObjectIdentifier | None
        ) = None,
        timeout: float | None = None,
    ) -> GetEventInformationACK:
        """Get event state information from a device.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param last_received_object_identifier: Optional object identifier
            for pagination (e.g. ``"ai,1"``). Pass the last object from a
            previous response when ``more_events`` is ``True``.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`GetEventInformationACK` with event summaries.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        last_oid = (
            parse_object_identifier(last_received_object_identifier)
            if last_received_object_identifier is not None
            else None
        )
        return await client.get_event_information(
            addr, last_received_object_identifier=last_oid, timeout=timeout
        )

    async def acknowledge_alarm(
        self,
        address: str | BACnetAddress,
        acknowledging_process_identifier: int,
        event_object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        event_state_acknowledged: EventState,
        time_stamp: BACnetTimeStamp,
        acknowledgment_source: str,
        time_of_acknowledgment: BACnetTimeStamp,
        timeout: float | None = None,
    ) -> None:
        """Acknowledge an alarm on a remote device.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param acknowledging_process_identifier: Process ID of the acknowledger.
        :param event_object_identifier: Object whose event is being
            acknowledged (e.g. ``"ai,1"``).
        :param event_state_acknowledged: Event state being acknowledged.
        :param time_stamp: Time stamp of the event being acknowledged.
        :param acknowledgment_source: Character string identifying the source.
        :param time_of_acknowledgment: Time stamp of the acknowledgment.
        :param timeout: Optional caller-level timeout in seconds.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        obj_id = parse_object_identifier(event_object_identifier)
        await client.acknowledge_alarm(
            addr,
            acknowledging_process_identifier,
            obj_id,
            event_state_acknowledged,
            time_stamp,
            acknowledgment_source,
            time_of_acknowledgment,
            timeout=timeout,
        )

    # --- Text messaging ---

    async def send_text_message(
        self,
        destination: str | BACnetAddress,
        message: str,
        *,
        confirmed: bool = True,
        message_priority: MessagePriority | None = None,
        message_class_numeric: int | None = None,
        message_class_character: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send a text message to a device or broadcast address.

        :param destination: Target address (IP string or
            :class:`BACnetAddress`).
        :param message: Text message content.
        :param confirmed: ``True`` for confirmed delivery (default),
            ``False`` for unconfirmed (fire-and-forget).
        :param message_priority: Message priority. Defaults to ``NORMAL``.
        :param message_class_numeric: Optional numeric message class.
        :param message_class_character: Optional character message class.
        :param timeout: Optional caller-level timeout (confirmed only).
        """
        from bac_py.network.address import parse_address
        from bac_py.types.enums import MessagePriority

        client = self._require_client()
        addr = parse_address(destination) if isinstance(destination, str) else destination
        priority = message_priority if message_priority is not None else MessagePriority.NORMAL
        source_device = self.app.device_object_identifier
        if confirmed:
            await client.send_confirmed_text_message(
                addr,
                source_device,
                message,
                message_priority=priority,
                message_class_numeric=message_class_numeric,
                message_class_character=message_class_character,
                timeout=timeout,
            )
        else:
            client.send_unconfirmed_text_message(
                addr,
                source_device,
                message,
                message_priority=priority,
                message_class_numeric=message_class_numeric,
                message_class_character=message_class_character,
            )

    # --- Backup and restore ---

    async def backup(
        self,
        address: str | BACnetAddress,
        password: str | None = None,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> BackupData:
        """Back up a remote BACnet device's configuration.

        Executes the full backup procedure (Clause 19.1):
        start backup, poll state, download config files, end backup.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param password: Optional password for ReinitializeDevice.
        :param poll_interval: Seconds between state polls.
        :param timeout: Optional overall timeout in seconds.
        :returns: :class:`BackupData` with downloaded configuration files.
        """
        from bac_py.network.address import parse_address

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        return await client.backup_device(
            addr, password=password, poll_interval=poll_interval, timeout=timeout
        )

    async def restore(
        self,
        address: str | BACnetAddress,
        backup_data: BackupData,
        password: str | None = None,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> None:
        """Restore a remote BACnet device from backup data.

        Executes the full restore procedure (Clause 19.1):
        start restore, poll state, upload config files, end restore.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param backup_data: :class:`BackupData` from a previous :meth:`backup`.
        :param password: Optional password for ReinitializeDevice.
        :param poll_interval: Seconds between state polls.
        :param timeout: Optional overall timeout in seconds.
        """
        from bac_py.network.address import parse_address

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        await client.restore_device(
            addr, backup_data, password=password, poll_interval=poll_interval, timeout=timeout
        )

    # --- Audit ---

    async def query_audit_log(
        self,
        address: str | BACnetAddress,
        audit_log: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        query_parameters: AuditQueryByTarget | AuditQueryBySource,
        start_at_sequence_number: int | None = None,
        requested_count: int = 100,
        timeout: float | None = None,
    ) -> AuditLogQueryACK:
        """Query audit log records from a device.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param audit_log: Audit Log object identifier (e.g.
            ``"audit-log,1"``).
        :param query_parameters: Query by target or source.
        :param start_at_sequence_number: Optional starting sequence number.
        :param requested_count: Maximum records to return (default 100).
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`AuditLogQueryACK`.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        log_oid = parse_object_identifier(audit_log)
        return await client.query_audit_log(
            addr,
            log_oid,
            query_parameters,
            start_at_sequence_number=start_at_sequence_number,
            requested_count=requested_count,
            timeout=timeout,
        )

    # --- COV property-level subscriptions ---

    async def subscribe_cov_property(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        property_identifier: str | int | PropertyIdentifier,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
        property_array_index: int | None = None,
        cov_increment: float | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to property-level COV notifications.

        Like :meth:`subscribe_cov_ex` but monitors a specific property
        rather than the default COV properties for the object type.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param object_identifier: Object to monitor (e.g. ``"ai,1"``).
        :param property_identifier: Property to monitor (e.g. ``"pv"``).
        :param process_id: Subscriber process identifier (caller-managed).
        :param confirmed: ``True`` for confirmed notifications.
        :param lifetime: Subscription lifetime in seconds, or ``None``.
        :param property_array_index: Optional array index within the property.
        :param cov_increment: Optional COV increment override.
        :param timeout: Optional caller-level timeout in seconds.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier, parse_property_identifier

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        obj_id = parse_object_identifier(object_identifier)
        prop_id = parse_property_identifier(property_identifier)
        await client.subscribe_cov_property(
            addr,
            obj_id,
            prop_id,
            process_id,
            confirmed=confirmed,
            lifetime=lifetime,
            property_array_index=property_array_index,
            cov_increment=cov_increment,
            timeout=timeout,
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

        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address. Accepts an IP string
            (e.g. ``"192.168.1.255"``), a :class:`BACnetAddress`,
            or ``None`` for global broadcast.
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
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

        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address. Accepts an IP string
            (e.g. ``"192.168.1.255"``), a :class:`BACnetAddress`,
            or ``None`` for global broadcast.
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
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
        address: str | BACnetAddress,
        enable_disable: str | EnableDisable,
        time_duration: int | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send DeviceCommunicationControl-Request.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param enable_disable: State to set. Accepts a string
            (``"enable"``, ``"disable"``, ``"disable-initiation"``)
            or :class:`EnableDisable` enum.
        :param time_duration: Optional duration in minutes.
        :param password: Optional password.
        :param timeout: Optional caller-level timeout in seconds.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.enums import EnableDisable

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        if isinstance(enable_disable, str):
            name = enable_disable.strip().upper().replace("-", "_")
            state = EnableDisable[name]
        else:
            state = enable_disable
        await client.device_communication_control(
            addr, state, time_duration, password, timeout=timeout
        )

    async def reinitialize_device(
        self,
        address: str | BACnetAddress,
        reinitialized_state: str | ReinitializedState,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send ReinitializeDevice-Request.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param reinitialized_state: State to set. Accepts a string
            (``"coldstart"``, ``"warmstart"``, ``"start-backup"``, etc.)
            or :class:`ReinitializedState` enum.
        :param password: Optional password.
        :param timeout: Optional caller-level timeout in seconds.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.enums import ReinitializedState

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        if isinstance(reinitialized_state, str):
            name = reinitialized_state.strip().upper().replace("-", "_")
            state = ReinitializedState[name]
        else:
            state = reinitialized_state
        await client.reinitialize_device(addr, state, password, timeout=timeout)

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
        address: str | BACnetAddress,
        object_type: str | ObjectType | None = None,
        object_identifier: str
        | tuple[str | ObjectType | int, int]
        | ObjectIdentifier
        | None = None,
        timeout: float | None = None,
    ) -> ObjectIdentifier:
        """Send CreateObject-Request.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param object_type: Object type to create. Accepts a string alias
            (e.g. ``"av"`` or ``"analog-value"``) or :class:`ObjectType`.
        :param object_identifier: Specific object identifier to create
            (e.g. ``"av,1"``). If provided, *object_type* is ignored.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: :class:`ObjectIdentifier` of the newly created object.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import _resolve_object_type, parse_object_identifier

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        resolved_type: ObjectType | None = None
        resolved_oid: ObjectIdentifier | None = None
        if object_identifier is not None:
            resolved_oid = parse_object_identifier(object_identifier)
        elif object_type is not None:
            resolved_type = (
                _resolve_object_type(object_type) if isinstance(object_type, str) else object_type
            )
        return await client.create_object(addr, resolved_type, resolved_oid, timeout=timeout)

    async def delete_object(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        timeout: float | None = None,
    ) -> None:
        """Send DeleteObject-Request.

        :param address: Target device address (IP string or
            :class:`BACnetAddress`).
        :param object_identifier: Object to delete (e.g. ``"av,1"``).
        :param timeout: Optional caller-level timeout in seconds.
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier

        client = self._require_client()
        addr = parse_address(address) if isinstance(address, str) else address
        obj_id = parse_object_identifier(object_identifier)
        await client.delete_object(addr, obj_id, timeout=timeout)

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

        :param object_identifier: Object to search for by identifier.
        :param object_name: Object to search for by name.
        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address. Accepts an IP string,
            a :class:`BACnetAddress`, or ``None`` for global broadcast.
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
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

        :param timeout: Maximum seconds to wait.
        :returns: ``True`` if registered, ``False`` if timeout expired.
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
        await self._require_client().delete_fdt_entry(bbmd_address, entry_address, timeout=timeout)

    # --- Router discovery ---

    async def who_is_router_to_network(
        self,
        network: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
    ) -> list[RouterInfo]:
        """Discover routers and reachable networks.

        See :meth:`~bac_py.app.client.BACnetClient.who_is_router_to_network`.

        :param network: Optional specific network to query. If ``None``,
            discovers all reachable networks.
        :param destination: Target for the query. Accepts an IP string,
            a :class:`BACnetAddress`, or ``None`` for local
            broadcast.
        :param timeout: Seconds to wait for responses.
        """
        return await self._require_client().who_is_router_to_network(
            network=network, destination=destination, timeout=timeout
        )
