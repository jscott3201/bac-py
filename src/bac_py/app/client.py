"""High-level BACnet client API per ASHRAE 135-2020."""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from bac_py.encoding.primitives import (
    decode_all_application_values,
    decode_and_unwrap,
    decode_object_identifier,
    encode_application_boolean,
    encode_application_enumerated,
    encode_application_null,
    encode_application_real,
    encode_application_unsigned,
    encode_property_value,
)
from bac_py.encoding.tags import decode_tag
from bac_py.network.address import GLOBAL_BROADCAST, parse_address
from bac_py.services.alarm_summary import (
    GetAlarmSummaryACK,
    GetAlarmSummaryRequest,
    GetEnrollmentSummaryACK,
    GetEnrollmentSummaryRequest,
    GetEventInformationACK,
    GetEventInformationRequest,
)
from bac_py.services.audit import (
    AuditLogQueryACK,
    AuditLogQueryRequest,
    ConfirmedAuditNotificationRequest,
    UnconfirmedAuditNotificationRequest,
)
from bac_py.services.cov import (
    BACnetPropertyReference,
    COVNotificationRequest,
    COVSubscriptionSpecification,
    SubscribeCOVPropertyMultipleRequest,
    SubscribeCOVPropertyRequest,
    SubscribeCOVRequest,
)
from bac_py.services.device_discovery import WhoAmIRequest, YouAreRequest
from bac_py.services.device_mgmt import (
    DeviceCommunicationControlRequest,
    ReinitializeDeviceRequest,
    TimeSynchronizationRequest,
    UTCTimeSynchronizationRequest,
)
from bac_py.services.event_notification import (
    AcknowledgeAlarmRequest,
    EventNotificationRequest,
)
from bac_py.services.file_access import (
    AtomicReadFileACK,
    AtomicReadFileRequest,
    AtomicWriteFileACK,
    AtomicWriteFileRequest,
    RecordReadAccess,
    RecordWriteAccess,
    StreamReadAccess,
    StreamWriteAccess,
)
from bac_py.services.list_element import AddListElementRequest, RemoveListElementRequest
from bac_py.services.object_mgmt import CreateObjectRequest, DeleteObjectRequest
from bac_py.services.private_transfer import (
    ConfirmedPrivateTransferACK,
    ConfirmedPrivateTransferRequest,
    UnconfirmedPrivateTransferRequest,
)
from bac_py.services.read_property import ReadPropertyACK, ReadPropertyRequest
from bac_py.services.read_property_multiple import (
    ReadAccessSpecification,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
)
from bac_py.services.read_range import (
    RangeByPosition,
    RangeBySequenceNumber,
    RangeByTime,
    ReadRangeACK,
    ReadRangeRequest,
)
from bac_py.services.text_message import (
    ConfirmedTextMessageRequest,
    UnconfirmedTextMessageRequest,
)
from bac_py.services.virtual_terminal import (
    VTCloseRequest,
    VTDataACK,
    VTDataRequest,
    VTOpenACK,
    VTOpenRequest,
)
from bac_py.services.who_has import IHaveRequest, WhoHasRequest
from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.services.write_group import GroupChannelValue, WriteGroupRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.services.write_property_multiple import (
    WriteAccessSpecification,
    WritePropertyMultipleRequest,
)
from bac_py.types.enums import (
    AcknowledgmentFilter,
    BackupAndRestoreState,
    ConfirmedServiceChoice,
    EnableDisable,
    EventState,
    EventType,
    MessagePriority,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
    Segmentation,
    UnconfirmedServiceChoice,
    VTClass,
)
from bac_py.types.parsing import parse_object_identifier, parse_property_identifier
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.transport.bip import BIPTransport
    from bac_py.types.audit_types import (
        AuditQueryBySource,
        AuditQueryByTarget,
        BACnetAuditNotification,
    )
    from bac_py.types.constructed import BACnetTimeStamp

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """Device discovered via Who-Is / I-Am.

    Provides parsed convenience properties from the I-Am response
    along with the source address of the responding device.

    Returned by :meth:`BACnetClient.discover`::

        devices = await client.discover(timeout=3.0)
        for dev in devices:
            print(dev.instance, dev.address_str)
    """

    address: BACnetAddress
    """Network address the I-Am response was received from."""

    instance: int
    """Device instance number."""

    vendor_id: int
    """Vendor identifier."""

    max_apdu_length: int
    """Maximum APDU length accepted by the device."""

    segmentation_supported: Segmentation
    """Segmentation support level."""

    profile_name: str | None = None
    """Profile name from extended discovery (Annex X), or ``None``."""

    profile_location: str | None = None
    """Profile location from extended discovery (Annex X), or ``None``."""

    tags: list[dict[str, Any]] | None = None
    """Tags from extended discovery (Annex X), or ``None``."""

    @property
    def address_str(self) -> str:
        """Human-readable address string."""
        return str(self.address)

    def __repr__(self) -> str:
        return f"DiscoveredDevice(instance={self.instance}, address='{self.address_str}')"


@dataclass(frozen=True, slots=True)
class UnconfiguredDevice:
    """An unconfigured device discovered via Who-Am-I (Clause 19.7).

    Returned by :meth:`BACnetClient.discover_unconfigured`.
    """

    address: BACnetAddress
    """Network address the Who-Am-I was received from."""

    vendor_id: int
    """Vendor identifier."""

    model_name: str
    """Model name string."""

    serial_number: str
    """Serial number string."""


@dataclass(frozen=True, slots=True)
class DeviceAssignmentEntry:
    """A mapping from (vendor_id, serial_number) to a device identity.

    Used by :class:`DeviceAssignmentTable` for auto-responding to
    Who-Am-I with You-Are.
    """

    vendor_id: int
    serial_number: str
    device_identifier: ObjectIdentifier
    device_mac_address: bytes
    device_network_number: int | None = None


class DeviceAssignmentTable:
    """Supervisor-side table for automatic device identity assignment.

    When a Who-Am-I is received, the table looks up the device by
    (vendor_id, serial_number) and provides the You-Are response data.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[int, str], DeviceAssignmentEntry] = {}

    def add(self, entry: DeviceAssignmentEntry) -> None:
        """Add or update an assignment entry."""
        self._entries[(entry.vendor_id, entry.serial_number)] = entry

    def remove(self, vendor_id: int, serial_number: str) -> None:
        """Remove an assignment entry."""
        self._entries.pop((vendor_id, serial_number), None)

    def lookup(self, vendor_id: int, serial_number: str) -> DeviceAssignmentEntry | None:
        """Look up assignment for a device."""
        return self._entries.get((vendor_id, serial_number))

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True, slots=True)
class BackupData:
    """Data from a backup of a remote BACnet device (Clause 19.1).

    Contains the configuration files downloaded during a backup procedure.
    """

    device_instance: int
    """Device instance number of the backed-up device."""

    configuration_files: list[tuple[ObjectIdentifier, bytes]]
    """List of (file_object_id, file_data) tuples."""


def decode_cov_values(notification: COVNotificationRequest) -> dict[str, object]:
    """Decode COV notification property values to a Python dict.

    Extracts and decodes the ``list_of_values`` from a
    :class:`COVNotificationRequest` into a human-readable dictionary
    mapping property names to decoded Python values.

    :param notification: A decoded COV notification request.
    :returns: Dict mapping property name strings (hyphenated, lowercase) to
        decoded Python values.

    Example::

        def on_change(notification, source):
            values = decode_cov_values(notification)
            print(values)
            # {"present-value": 72.5, "status-flags": BitString(...)}
    """
    result: dict[str, object] = {}
    for prop_value in notification.list_of_values:
        prop_name = prop_value.property_identifier.name.lower().replace("_", "-")
        if prop_value.value:
            result[prop_name] = decode_and_unwrap(prop_value.value)
        else:
            result[prop_name] = None
    return result


@dataclass(frozen=True, slots=True)
class BDTEntryInfo:
    """Human-readable Broadcast Distribution Table entry.

    Returned by :meth:`BACnetClient.read_bdt`.
    """

    address: str
    """BBMD address string (e.g. ``"192.168.1.1:47808"``)."""

    mask: str
    """Broadcast distribution mask (e.g. ``"255.255.255.255"``)."""


@dataclass(frozen=True, slots=True)
class FDTEntryInfo:
    """Human-readable Foreign Device Table entry.

    Returned by :meth:`BACnetClient.read_fdt`.
    """

    address: str
    """Foreign device address string (e.g. ``"10.0.0.50:47808"``)."""

    ttl: int
    """Registration time-to-live in seconds."""

    remaining: int
    """Seconds remaining before this entry expires."""


@dataclass(frozen=True, slots=True)
class RouterInfo:
    """Router discovered via Who-Is-Router-To-Network.

    Returned by :meth:`BACnetClient.who_is_router_to_network`.
    """

    address: str
    """Router address string (MAC as hex)."""

    networks: list[int]
    """Network numbers reachable through this router."""


class BACnetClient:
    """High-level async BACnet client API.

    Wraps a BACnetApplication to provide typed methods for common
    BACnet services: ReadProperty, WriteProperty, ReadPropertyMultiple,
    WritePropertyMultiple, ReadRange, and Who-Is/I-Am.
    """

    def __init__(self, app: BACnetApplication) -> None:
        """Initialize the client.

        :param app: The :class:`BACnetApplication` instance to use for
            sending and receiving BACnet requests.
        """
        self._app = app

    async def read_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> ReadPropertyACK:
        """Read a single property from a remote device.

        :param address: Target device address.
        :param object_identifier: Object to read from.
        :param property_identifier: Property to read.
        :param array_index: Optional array index for array properties.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`ReadPropertyACK` containing the property value.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug(
            "read_property %s %s from %s", object_identifier, property_identifier, address
        )
        request = ReadPropertyRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=array_index,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.READ_PROPERTY,
            service_data=request.encode(),
            timeout=timeout,
        )
        return ReadPropertyACK.decode(response_data)

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

        :param address: Target device address.
        :param object_identifier: Object to write to.
        :param property_identifier: Property to write.
        :param value: Application-tagged encoded property value bytes.
        :param priority: Optional write priority (1--16).
        :param array_index: Optional array index for array properties.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("write_property %s %s to %s", object_identifier, property_identifier, address)
        request = WritePropertyRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_value=value,
            property_array_index=array_index,
            priority=priority,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.WRITE_PROPERTY,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def read_property_multiple(
        self,
        address: BACnetAddress,
        read_access_specs: list[ReadAccessSpecification],
        timeout: float | None = None,
    ) -> ReadPropertyMultipleACK:
        """Read multiple properties from one or more objects.

        :param address: Target device address.
        :param read_access_specs: List of read access specifications, each
            containing an object identifier and list of property
            references to read.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`ReadPropertyMultipleACK` with per-property results.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("read_property_multiple %s specs from %s", len(read_access_specs), address)
        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=read_access_specs,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE,
            service_data=request.encode(),
            timeout=timeout,
        )
        return ReadPropertyMultipleACK.decode(response_data)

    async def write_property_multiple(
        self,
        address: BACnetAddress,
        write_access_specs: list[WriteAccessSpecification],
        timeout: float | None = None,
    ) -> None:
        """Write multiple properties to one or more objects.

        :param address: Target device address.
        :param write_access_specs: List of write access specifications, each
            containing an object identifier and list of property
            values to write.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response (first failing property).
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("write_property_multiple %s specs to %s", len(write_access_specs), address)
        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=write_access_specs,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE,
            service_data=request.encode(),
            timeout=timeout,
        )

    # --- Convenience API ---

    def _encode_for_write(
        self,
        value: object,
        property_identifier: PropertyIdentifier,
        object_type: ObjectType,
    ) -> bytes:
        """Encode a Python value for writing to a specific property.

        Uses the object registry's ``PropertyDefinition.datatype`` to
        select the correct BACnet encoding.  Falls back to
        ``encode_property_value()`` for types or properties not found
        in the registry.

        Encoding priority:

        1. ``None`` always encodes as Null.
        2. Raw ``bytes`` pass through unchanged (pre-encoded).
        3. Registry-based: looks up the property's declared datatype
           from the object registry and encodes ``int``/``float``
           values accordingly (Real, Unsigned, Enumerated, Boolean).
        4. All other values fall back to ``encode_property_value()``.
        """
        # None -> Null (relinquish a command priority)
        if value is None:
            return encode_application_null()

        # Already-encoded bytes pass through
        if isinstance(value, bytes):
            return value

        # Registry-based encoding: look up the property's declared
        # datatype from the object registry and use it to select the
        # correct encoder for int/float/bool values.
        datatype = self._lookup_datatype(object_type, property_identifier)
        if datatype is not None:
            # Handle bool values: encode as Enumerated when the property
            # expects an IntEnum (e.g., BinaryPV), or as Boolean when
            # the property expects bool.
            if isinstance(value, bool):
                if issubclass(datatype, enum.IntEnum):
                    return encode_application_enumerated(int(value))
                if datatype is bool:
                    return encode_application_boolean(value)
            elif isinstance(value, (int, float)):
                if datatype is float or issubclass(datatype, float):
                    return encode_application_real(float(value))
                if issubclass(datatype, enum.IntEnum):
                    return encode_application_enumerated(int(value))
                if datatype is int:
                    return encode_application_unsigned(int(value))
                if datatype is bool:
                    return encode_application_boolean(bool(value))

        return encode_property_value(value)

    @staticmethod
    def _lookup_datatype(
        object_type: ObjectType,
        property_identifier: PropertyIdentifier,
    ) -> type | None:
        """Look up a property's declared datatype from the object registry.

        Returns the ``PropertyDefinition.datatype`` if the object type
        and property are found, otherwise ``None``.
        """
        from bac_py.objects.base import _OBJECT_REGISTRY

        obj_cls = _OBJECT_REGISTRY.get(object_type)
        if obj_cls is None:
            return None
        prop_def = obj_cls.PROPERTY_DEFINITIONS.get(property_identifier)
        if prop_def is None:
            return None
        return prop_def.datatype

    async def read(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        property_identifier: str | int | PropertyIdentifier,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> object:
        """Read a property and return a decoded Python value.

        Convenience wrapper around :meth:`read_property` that parses
        addresses and identifiers from strings and decodes the
        returned application-tagged bytes into native Python types.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param object_identifier: Object to read (e.g. ``"analog-input,1"``
            or ``"ai,1"``).
        :param property_identifier: Property to read (e.g. ``"present-value"``
            or ``"pv"``).
        :param array_index: Optional array index.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded Python value (``float``, ``int``, ``str``, ``bool``,
            etc.). Returns a ``list`` if the property contains multiple
            application-tagged values.

        Example::

            value = await client.read("192.168.1.100", "ai,1", "pv")
            name = await client.read("192.168.1.100", "ai,1", "object-name")
        """
        logger.debug("read %s %s from %s", object_identifier, property_identifier, address)
        addr = parse_address(address)
        obj_id = parse_object_identifier(object_identifier)
        prop_id = parse_property_identifier(property_identifier)

        ack = await self.read_property(addr, obj_id, prop_id, array_index, timeout=timeout)

        if not ack.property_value:
            return None

        return decode_and_unwrap(ack.property_value)

    async def write(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        property_identifier: str | int | PropertyIdentifier,
        value: object,
        priority: int | None = None,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Write a Python value to a property.

        Convenience wrapper around :meth:`write_property` that parses
        addresses and identifiers from strings and automatically
        encodes the value to the appropriate BACnet application-tagged
        format based on the Python type and target property.

        Type mapping:

        - ``float`` -> Real
        - ``int`` -> Unsigned (or Real for analog PV, Enumerated for
          binary PV, Unsigned for multi-state PV)
        - ``str`` -> Character String
        - ``bool`` -> Enumerated (1/0)
        - ``None`` -> Null (relinquish a command priority)
        - ``IntEnum`` -> Enumerated
        - ``bytes`` -> pass-through (already-encoded)

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param object_identifier: Object to write (e.g. ``"analog-value,1"``
            or ``"av,1"``).
        :param property_identifier: Property to write (e.g. ``"present-value"``
            or ``"pv"``).
        :param value: Python value to write (auto-encoded).
        :param priority: Optional write priority (1--16).
        :param array_index: Optional array index.
        :param timeout: Optional caller-level timeout in seconds.

        Example::

            await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
            await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)
            await client.write("192.168.1.100", "av,1", "pv", None, priority=8)
        """
        logger.debug("write %s %s to %s", object_identifier, property_identifier, address)
        addr = parse_address(address)
        obj_id = parse_object_identifier(object_identifier)
        prop_id = parse_property_identifier(property_identifier)

        encoded = self._encode_for_write(value, prop_id, obj_id.object_type)

        await self.write_property(
            addr, obj_id, prop_id, encoded, priority, array_index, timeout=timeout
        )

    async def read_multiple(
        self,
        address: str | BACnetAddress,
        specs: dict[
            str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
            list[str | int | PropertyIdentifier],
        ],
        timeout: float | None = None,
    ) -> dict[str, dict[str, object]]:
        """Read multiple properties from multiple objects.

        Convenience wrapper around :meth:`read_property_multiple` that
        accepts a simplified dict format and returns decoded Python values.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param specs: Mapping of object identifiers to lists of property
            identifiers. Example::

                {
                    "ai,1": ["pv", "name", "units"],
                    "ai,2": ["pv", "status"],
                }

        :param timeout: Optional caller-level timeout in seconds.
        :returns: Nested dict mapping object ID strings to property name/value
            dicts. Property values are decoded to native Python types.
            Properties that returned errors have ``None`` as their value.

            Result keys always use canonical hyphenated object type names
            (e.g. ``"analog-input,1"``) regardless of the input format
            used (e.g. ``"ai,1"``).

            Example::

                {
                    "analog-input,1": {
                        "present-value": 72.5,
                        "object-name": "Zone Temp",
                        "units": 62,
                    },
                }
        """
        logger.debug("read_multiple %s properties from %s", len(specs), address)
        from bac_py.services.read_property_multiple import PropertyReference

        addr = parse_address(address)

        access_specs: list[ReadAccessSpecification] = []
        for obj_key, prop_list in specs.items():
            obj_id = parse_object_identifier(obj_key)
            prop_refs = [PropertyReference(parse_property_identifier(p)) for p in prop_list]
            access_specs.append(
                ReadAccessSpecification(
                    object_identifier=obj_id,
                    list_of_property_references=prop_refs,
                )
            )

        ack = await self.read_property_multiple(addr, access_specs, timeout=timeout)

        result: dict[str, dict[str, object]] = {}
        for access_result in ack.list_of_read_access_results:
            obj_type = access_result.object_identifier.object_type
            instance = access_result.object_identifier.instance_number
            obj_key_str = f"{obj_type.name.lower().replace('_', '-')},{instance}"

            props: dict[str, object] = {}
            for elem in access_result.list_of_results:
                prop_name = elem.property_identifier.name.lower().replace("_", "-")
                if elem.property_access_error is not None:
                    props[prop_name] = None
                elif elem.property_value is not None and elem.property_value:
                    props[prop_name] = decode_and_unwrap(elem.property_value)
                else:
                    props[prop_name] = None
            result[obj_key_str] = props

        return result

    async def write_multiple(
        self,
        address: str | BACnetAddress,
        specs: dict[
            str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
            dict[str | int | PropertyIdentifier, object],
        ],
        priority: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Write multiple properties to multiple objects.

        Convenience wrapper around :meth:`write_property_multiple` that
        accepts a simplified dict format and automatically encodes
        Python values.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param specs: Mapping of object identifiers to property/value dicts.
            Example::

                {
                    "av,1": {"pv": 72.5, "object-name": "Zone Temp"},
                    "bo,1": {"pv": 1},
                }
        :param priority: Optional BACnet write priority (1--16).  Applied
            uniformly to every property in *specs*.  For per-property
            control use :meth:`write_property_multiple` directly.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response (first failing property).
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.

        Example::

            await client.write_multiple(
                "192.168.1.100",
                {
                    "av,1": {"pv": 72.5},
                    "bo,1": {"pv": 1},
                },
                priority=8,
            )
        """
        logger.debug("write_multiple %s values to %s", len(specs), address)
        from bac_py.services.common import BACnetPropertyValue

        addr = parse_address(address)

        write_specs: list[WriteAccessSpecification] = []
        for obj_key, prop_dict in specs.items():
            obj_id = parse_object_identifier(obj_key)
            prop_values: list[BACnetPropertyValue] = []
            for prop_key, value in prop_dict.items():
                prop_id = parse_property_identifier(prop_key)
                encoded = self._encode_for_write(value, prop_id, obj_id.object_type)
                prop_values.append(
                    BACnetPropertyValue(
                        property_identifier=prop_id,
                        value=encoded,
                        priority=priority,
                    )
                )
            write_specs.append(
                WriteAccessSpecification(
                    object_identifier=obj_id,
                    list_of_properties=prop_values,
                )
            )

        await self.write_property_multiple(addr, write_specs, timeout=timeout)

    async def get_object_list(
        self,
        address: str | BACnetAddress,
        device_instance: int,
        timeout: float | None = None,
    ) -> list[ObjectIdentifier]:
        """Read the complete object list from a device.

        Attempts to read the full ``object-list`` property first. If
        the response is too large (:class:`BACnetAbortError` with
        segmentation-not-supported), falls back to reading the array
        length then each element individually.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param device_instance: Device instance number of the target.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: List of :class:`ObjectIdentifier` for all objects in the device.

        Example::

            objects = await client.get_object_list("192.168.1.100", 1234)
            for obj in objects:
                print(obj.object_type, obj.instance_number)
        """
        logger.debug("get_object_list from %s", address)
        from bac_py.services.errors import BACnetAbortError
        from bac_py.types.enums import AbortReason

        addr = parse_address(address)
        device_obj = ObjectIdentifier(ObjectType.DEVICE, device_instance)
        try:
            ack = await self.read_property(
                addr,
                device_obj,
                PropertyIdentifier.OBJECT_LIST,
                timeout=timeout,
            )
            if ack.property_value:
                values = decode_all_application_values(ack.property_value)
                return [v for v in values if isinstance(v, ObjectIdentifier)]
            return []
        except BACnetAbortError as exc:
            if exc.reason != AbortReason.SEGMENTATION_NOT_SUPPORTED:
                raise

        # Fallback: read array length, then each element
        ack = await self.read_property(
            addr,
            device_obj,
            PropertyIdentifier.OBJECT_LIST,
            array_index=0,
            timeout=timeout,
        )
        count_val = decode_and_unwrap(ack.property_value)
        if not isinstance(count_val, int) or count_val == 0:
            return []

        result: list[ObjectIdentifier] = []
        for i in range(1, count_val + 1):
            ack = await self.read_property(
                addr,
                device_obj,
                PropertyIdentifier.OBJECT_LIST,
                array_index=i,
                timeout=timeout,
            )
            val = decode_and_unwrap(ack.property_value)
            if isinstance(val, ObjectIdentifier):
                result.append(val)

        return result

    # --- COV convenience ---

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

        Convenience wrapper around :meth:`subscribe_cov` that accepts
        flexible address and object identifier formats and optionally
        registers a notification callback.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param object_identifier: Object to monitor (e.g. ``"ai,1"``).
        :param process_id: Subscriber process identifier (caller-managed).
        :param confirmed: ``True`` for confirmed notifications, ``False`` for
            unconfirmed.
        :param lifetime: Subscription lifetime in seconds, or ``None`` for
            indefinite.
        :param callback: Optional callback for COV notifications. Receives
            ``(COVNotificationRequest, source_address)``. If provided,
            automatically registered via
            :meth:`~bac_py.app.application.BACnetApplication.register_cov_callback`.
        :param timeout: Optional caller-level timeout in seconds.

        Example::

            def on_change(notification, source):
                values = decode_cov_values(notification)
                print(f"COV from {source}: {values}")


            await client.subscribe_cov_ex(
                "192.168.1.100",
                "ai,1",
                process_id=1,
                callback=on_change,
                lifetime=3600,
            )
        """
        logger.info("subscribe_cov %s on %s lifetime=%s", object_identifier, address, lifetime)
        addr = parse_address(address)
        obj_id = parse_object_identifier(object_identifier)

        if callback is not None:
            self._app.register_cov_callback(process_id, callback)

        try:
            await self.subscribe_cov(
                addr, obj_id, process_id, confirmed, lifetime, timeout=timeout
            )
        except BaseException:
            # Undo callback registration on failure
            if callback is not None:
                self._app.unregister_cov_callback(process_id)
            raise

    async def unsubscribe_cov_ex(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        process_id: int,
        unregister_callback: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Cancel a COV subscription with string arguments.

        Convenience wrapper around :meth:`unsubscribe_cov` that accepts
        flexible address and object identifier formats and optionally
        unregisters the notification callback.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param object_identifier: Object being monitored (e.g. ``"ai,1"``).
        :param process_id: Subscriber process identifier used during subscription.
        :param unregister_callback: If ``True``, also unregister the COV callback.
        :param timeout: Optional caller-level timeout in seconds.
        """
        logger.info("unsubscribe_cov %s on %s", object_identifier, address)
        addr = parse_address(address)
        obj_id = parse_object_identifier(object_identifier)

        await self.unsubscribe_cov(addr, obj_id, process_id, timeout=timeout)

        if unregister_callback:
            self._app.unregister_cov_callback(process_id)

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

        :param address: Target device address.
        :param object_identifier: Object containing the list property.
        :param property_identifier: List or array property to read.
        :param array_index: Optional array index.
        :param range_qualifier: Optional range qualifier (by position,
            sequence number, or time). If ``None``, returns all items.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`ReadRangeACK` with the requested items.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("read_range %s %s from %s", object_identifier, property_identifier, address)
        request = ReadRangeRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=array_index,
            range=range_qualifier,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.READ_RANGE,
            service_data=request.encode(),
            timeout=timeout,
        )
        return ReadRangeACK.decode(response_data)

    # --- Unconfirmed response collection helper ---

    async def _collect_unconfirmed_responses(
        self,
        send_service: UnconfirmedServiceChoice,
        send_data: bytes,
        listen_service: UnconfirmedServiceChoice,
        decoder: Callable[[bytes, BACnetAddress], _T],
        destination: BACnetAddress,
        timeout: float,
        expected_count: int | None,
    ) -> list[_T]:
        """Send an unconfirmed request and collect decoded responses.

        Shared implementation for :meth:`who_is`, :meth:`discover`,
        and :meth:`who_has` which all follow the same broadcast-and-
        collect pattern.

        :param send_service: Service choice for the outgoing request.
        :param send_data: Encoded service data to send.
        :param listen_service: Service choice to listen for responses.
        :param decoder: Callable that decodes ``(service_data, source)``
            into a result object.  Return ``None`` to skip a
            malformed response.
        :param destination: Broadcast address for the request.
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
            responses have been collected.
        :returns: List of decoded response objects.
        """
        results: list[_T] = []
        done_event: asyncio.Event | None = asyncio.Event() if expected_count is not None else None

        def _on_response(service_data: bytes, source: BACnetAddress) -> None:
            try:
                item = decoder(service_data, source)
            except (ValueError, IndexError):
                logger.debug("Dropped malformed %s from %s", listen_service.name, source)
                return
            if item is not None:
                results.append(item)
                if (
                    done_event is not None
                    and expected_count is not None
                    and len(results) >= expected_count
                ):
                    done_event.set()

        self._app.register_temporary_handler(listen_service, _on_response)
        try:
            self._app.unconfirmed_request(
                destination=destination,
                service_choice=send_service,
                service_data=send_data,
            )
            if done_event is not None:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(done_event.wait(), timeout)
            else:
                await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(listen_service, _on_response)

        return results

    async def who_is(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[IAmRequest]:
        """Discover devices via Who-Is broadcast.

        Sends a Who-Is request and collects I-Am responses for the
        specified timeout duration.

        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address (default: global broadcast).
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
            responses have been collected instead of waiting for the
            full timeout.
        :returns: List of :class:`IAmRequest` responses received within the timeout.
        """
        logger.debug("who_is low=%s high=%s", low_limit, high_limit)
        # Auto-infer expected_count=1 for targeted unicast to a single instance
        if (
            expected_count is None
            and low_limit is not None
            and low_limit == high_limit
            and destination != GLOBAL_BROADCAST
            and not destination.is_broadcast
        ):
            expected_count = 1

        request = WhoIsRequest(low_limit=low_limit, high_limit=high_limit)
        return await self._collect_unconfirmed_responses(
            send_service=UnconfirmedServiceChoice.WHO_IS,
            send_data=request.encode(),
            listen_service=UnconfirmedServiceChoice.I_AM,
            decoder=lambda data, _src: IAmRequest.decode(data),
            destination=destination,
            timeout=timeout,
            expected_count=expected_count,
        )

    async def discover(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[DiscoveredDevice]:
        r"""Discover devices via Who-Is and return enriched results.

        Convenience wrapper around :meth:`who_is` that captures the
        source address of each I-Am response and returns
        :class:`DiscoveredDevice` objects with parsed fields.

        To discover devices on a remote network reachable through a
        router, pass a remote broadcast :class:`BACnetAddress`::

            from bac_py.network.address import BACnetAddress

            remote = BACnetAddress(network=2, mac_address=b"\\xff\\xff\\xff\\xff")
            devices = await client.discover(destination=remote, timeout=5.0)

        When using the :class:`~bac_py.client.Client` wrapper, you can
        pass a string like ``"192.168.1.255"`` for directed local
        broadcast.

        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address (default: global broadcast).
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
            devices have been discovered instead of waiting for the
            full timeout.
        :returns: List of :class:`DiscoveredDevice` with address and device info.

        Example::

            devices = await client.discover(timeout=3.0)
            for dev in devices:
                print(dev.instance, dev.address_str, dev.vendor_id)
        """
        logger.info("discover timeout=%s low=%s high=%s", timeout, low_limit, high_limit)
        # Auto-infer expected_count=1 for targeted unicast to a single instance
        if (
            expected_count is None
            and low_limit is not None
            and low_limit == high_limit
            and destination != GLOBAL_BROADCAST
            and not destination.is_broadcast
        ):
            expected_count = 1

        def _decode_device(service_data: bytes, source: BACnetAddress) -> DiscoveredDevice:
            iam = IAmRequest.decode(service_data)
            return DiscoveredDevice(
                address=source,
                instance=iam.object_identifier.instance_number,
                vendor_id=iam.vendor_id,
                max_apdu_length=iam.max_apdu_length,
                segmentation_supported=iam.segmentation_supported,
            )

        request = WhoIsRequest(low_limit=low_limit, high_limit=high_limit)
        return await self._collect_unconfirmed_responses(
            send_service=UnconfirmedServiceChoice.WHO_IS,
            send_data=request.encode(),
            listen_service=UnconfirmedServiceChoice.I_AM,
            decoder=_decode_device,
            destination=destination,
            timeout=timeout,
            expected_count=expected_count,
        )

    async def discover_extended(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
        expected_count: int | None = None,
        enrich_timeout: float = 5.0,
    ) -> list[DiscoveredDevice]:
        """Discover devices and enrich with profile metadata (Annex X).

        Calls :meth:`discover` to get the initial device list, then for
        each device reads ``PROFILE_NAME``, ``PROFILE_LOCATION``, and
        ``TAGS`` via ReadPropertyMultiple to populate extended fields.

        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address (default: global broadcast).
        :param timeout: Seconds to wait for Who-Is responses.
        :param expected_count: Return early once this many devices respond.
        :param enrich_timeout: Per-device timeout for RPM enrichment.
        :returns: List of :class:`DiscoveredDevice` with profile metadata.
        """
        logger.info("discover_extended timeout=%s low=%s high=%s", timeout, low_limit, high_limit)
        from bac_py.services.errors import BACnetError, BACnetTimeoutError
        from bac_py.services.read_property_multiple import PropertyReference

        devices = await self.discover(
            low_limit=low_limit,
            high_limit=high_limit,
            destination=destination,
            timeout=timeout,
            expected_count=expected_count,
        )

        async def _enrich_device(dev: DiscoveredDevice) -> DiscoveredDevice:
            profile_name: str | None = None
            profile_location: str | None = None
            tags: list[dict[str, Any]] | None = None

            try:
                spec = ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, dev.instance),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.PROFILE_NAME),
                        PropertyReference(PropertyIdentifier.PROFILE_LOCATION),
                        PropertyReference(PropertyIdentifier.TAGS),
                    ],
                )
                ack = await self.read_property_multiple(
                    dev.address, [spec], timeout=enrich_timeout
                )
                for result in ack.list_of_read_access_results:
                    for elem in result.list_of_results:
                        if elem.property_access_error is not None:
                            continue
                        pid = elem.property_identifier
                        val = (
                            decode_and_unwrap(elem.property_value) if elem.property_value else None
                        )
                        if pid == PropertyIdentifier.PROFILE_NAME:
                            profile_name = val if isinstance(val, str) else None
                        elif pid == PropertyIdentifier.PROFILE_LOCATION:
                            profile_location = val if isinstance(val, str) else None
                        elif pid == PropertyIdentifier.TAGS and isinstance(val, list):
                            tags = val
            except (BACnetError, BACnetTimeoutError, TimeoutError):
                pass

            return DiscoveredDevice(
                address=dev.address,
                instance=dev.instance,
                vendor_id=dev.vendor_id,
                max_apdu_length=dev.max_apdu_length,
                segmentation_supported=dev.segmentation_supported,
                profile_name=profile_name,
                profile_location=profile_location,
                tags=tags,
            )

        enriched = await asyncio.gather(
            *(_enrich_device(dev) for dev in devices),
        )
        return list(enriched)

    async def traverse_hierarchy(
        self,
        address: str | BACnetAddress,
        root: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        *,
        max_depth: int = 10,
        timeout: float | None = None,
    ) -> list[ObjectIdentifier]:
        """Traverse a Structured View hierarchy via subordinate lists.

        Reads ``SUBORDINATE_LIST`` from the *root* Structured View object,
        then recursively descends into any subordinate Structured View
        objects up to *max_depth* levels.

        :param address: Target device (e.g. ``"192.168.1.100"``).
        :param root: Root Structured View object (e.g. ``"sv,1"``
            or ``"structured-view,1"``).
        :param max_depth: Maximum recursion depth (prevents cycles).
        :param timeout: Optional per-request timeout in seconds.
        :returns: Flat list of all discovered :class:`ObjectIdentifier`
            values, including Structured View objects themselves.

        Example::

            objects = await client.traverse_hierarchy("192.168.1.100", "sv,1", max_depth=5)
        """
        logger.debug("traverse_hierarchy from %s", address)
        addr = parse_address(address)
        root_id = parse_object_identifier(root)
        result: list[ObjectIdentifier] = []
        await self._traverse_hierarchy_recursive(addr, root_id, max_depth, timeout, result, set())
        return result

    async def _traverse_hierarchy_recursive(
        self,
        address: BACnetAddress,
        node: ObjectIdentifier,
        depth: int,
        timeout: float | None,
        result: list[ObjectIdentifier],
        visited: set[tuple[int, int]],
    ) -> None:
        """Recursive helper for :meth:`traverse_hierarchy`."""
        from bac_py.services.errors import BACnetError, BACnetTimeoutError

        key = (node.object_type, node.instance_number)
        if key in visited or depth <= 0:
            return
        visited.add(key)

        try:
            ack = await self.read_property(
                address,
                node,
                PropertyIdentifier.SUBORDINATE_LIST,
                timeout=timeout,
            )
            raw_subordinates = decode_all_application_values(ack.property_value)
            if not isinstance(raw_subordinates, list):
                return
        except (BACnetError, BACnetTimeoutError, TimeoutError):
            return

        for sub in raw_subordinates:
            if isinstance(sub, ObjectIdentifier):
                result.append(sub)
                if sub.object_type == ObjectType.STRUCTURED_VIEW:
                    await self._traverse_hierarchy_recursive(
                        address, sub, depth - 1, timeout, result, visited
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
        """Subscribe to COV notifications from a remote device.

        Sends a SubscribeCOV-Request per Clause 13.14.1. The remote
        device will send confirmed or unconfirmed COV notifications
        when the monitored object's value changes.

        :param address: Target device address.
        :param object_identifier: Object to monitor.
        :param process_id: Subscriber process identifier (caller-managed).
        :param confirmed: ``True`` for confirmed notifications, ``False`` for
            unconfirmed.
        :param lifetime: Subscription lifetime in seconds, or ``None`` for
            indefinite.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("subscribe_cov %s on %s", object_identifier, address)
        request = SubscribeCOVRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
            issue_confirmed_notifications=confirmed,
            lifetime=lifetime,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.SUBSCRIBE_COV,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def unsubscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
        timeout: float | None = None,
    ) -> None:
        """Cancel a COV subscription on a remote device.

        Per Clause 13.14, omits ``issueConfirmedNotifications`` and
        ``lifetime`` to indicate cancellation.

        :param address: Target device address.
        :param object_identifier: Object being monitored.
        :param process_id: Subscriber process identifier used during subscription.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("unsubscribe_cov %s on %s", object_identifier, address)
        request = SubscribeCOVRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.SUBSCRIBE_COV,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def subscribe_cov_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: int,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
        property_array_index: int | None = None,
        cov_increment: float | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to property-level COV notifications per Clause 13.15.

        :param address: Target device address.
        :param object_identifier: Object to monitor.
        :param property_identifier: Specific property to monitor.
        :param process_id: Subscriber process identifier (caller-managed).
        :param confirmed: ``True`` for confirmed notifications, ``False`` for unconfirmed.
        :param lifetime: Subscription lifetime in seconds, or ``None`` for indefinite.
        :param property_array_index: Optional array index within the property.
        :param cov_increment: Optional COV increment override.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info(
            "subscribe_cov_property %s.%s on %s", object_identifier, property_identifier, address
        )
        request = SubscribeCOVPropertyRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
            monitored_property_identifier=BACnetPropertyReference(
                property_identifier=property_identifier,
                property_array_index=property_array_index,
            ),
            issue_confirmed_notifications=confirmed,
            lifetime=lifetime,
            cov_increment=cov_increment,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def subscribe_cov_property_multiple(
        self,
        address: BACnetAddress,
        process_id: int,
        specifications: list[COVSubscriptionSpecification],
        confirmed: bool = True,
        lifetime: int | None = None,
        max_notification_delay: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Subscribe to multiple property-level COV notifications per Clause 13.16.

        :param address: Target device address.
        :param process_id: Subscriber process identifier (caller-managed).
        :param specifications: List of subscription specifications, each containing
            a monitored object and its list of COV references.
        :param confirmed: ``True`` for confirmed notifications.
        :param lifetime: Subscription lifetime in seconds.
        :param max_notification_delay: Maximum notification delay in seconds.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("subscribe_cov_property_multiple on %s", address)
        request = SubscribeCOVPropertyMultipleRequest(
            subscriber_process_identifier=process_id,
            list_of_cov_subscription_specifications=specifications,
            issue_confirmed_notifications=confirmed,
            lifetime=lifetime,
            max_notification_delay=max_notification_delay,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY_MULTIPLE,
            service_data=request.encode(),
            timeout=timeout,
        )

    # --- Device management ---

    async def device_communication_control(
        self,
        address: BACnetAddress,
        enable_disable: EnableDisable,
        time_duration: int | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send DeviceCommunicationControl-Request per Clause 16.1.

        :param address: Target device address.
        :param enable_disable: Enable/disable communication state.
        :param time_duration: Optional duration in minutes.
        :param password: Optional password string (1--20 chars).
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("device_communication_control %s on %s", enable_disable, address)
        request = DeviceCommunicationControlRequest(
            enable_disable=enable_disable,
            time_duration=time_duration,
            password=password,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def reinitialize_device(
        self,
        address: BACnetAddress,
        reinitialized_state: ReinitializedState,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send ReinitializeDevice-Request per Clause 16.4.

        :param address: Target device address.
        :param reinitialized_state: Desired reinitialization state.
        :param password: Optional password string (1--20 chars).
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("reinitialize_device %s on %s", reinitialized_state, address)
        request = ReinitializeDeviceRequest(
            reinitialized_state=reinitialized_state,
            password=password,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.REINITIALIZE_DEVICE,
            service_data=request.encode(),
            timeout=timeout,
        )

    def time_synchronization(
        self,
        destination: BACnetAddress,
        date: BACnetDate,
        time: BACnetTime,
    ) -> None:
        """Send TimeSynchronization-Request per Clause 16.7.

        This is an unconfirmed service (fire-and-forget).

        :param destination: Target device or broadcast address.
        :param date: BACnet date to synchronize.
        :param time: BACnet time to synchronize.
        """
        logger.debug("time_synchronization to %s", destination)
        request = TimeSynchronizationRequest(date=date, time=time)
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.TIME_SYNCHRONIZATION,
            service_data=request.encode(),
        )

    def utc_time_synchronization(
        self,
        destination: BACnetAddress,
        date: BACnetDate,
        time: BACnetTime,
    ) -> None:
        """Send UTCTimeSynchronization-Request per Clause 16.8.

        This is an unconfirmed service (fire-and-forget).

        :param destination: Target device or broadcast address.
        :param date: BACnet UTC date to synchronize.
        :param time: BACnet UTC time to synchronize.
        """
        logger.debug("utc_time_synchronization to %s", destination)
        request = UTCTimeSynchronizationRequest(date=date, time=time)
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION,
            service_data=request.encode(),
        )

    # --- File access ---

    async def atomic_read_file(
        self,
        address: BACnetAddress,
        file_identifier: ObjectIdentifier,
        access_method: StreamReadAccess | RecordReadAccess,
        timeout: float | None = None,
    ) -> AtomicReadFileACK:
        """Send AtomicReadFile-Request per Clause 14.1.

        :param address: Target device address.
        :param file_identifier: :class:`ObjectIdentifier` of the File object.
        :param access_method: Stream or record read parameters.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`AtomicReadFileACK` with file data.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("atomic_read_file %s from %s", file_identifier, address)
        request = AtomicReadFileRequest(
            file_identifier=file_identifier,
            access_method=access_method,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.ATOMIC_READ_FILE,
            service_data=request.encode(),
            timeout=timeout,
        )
        return AtomicReadFileACK.decode(response_data)

    async def atomic_write_file(
        self,
        address: BACnetAddress,
        file_identifier: ObjectIdentifier,
        access_method: StreamWriteAccess | RecordWriteAccess,
        timeout: float | None = None,
    ) -> AtomicWriteFileACK:
        """Send AtomicWriteFile-Request per Clause 14.2.

        :param address: Target device address.
        :param file_identifier: :class:`ObjectIdentifier` of the File object.
        :param access_method: Stream or record write parameters.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`AtomicWriteFileACK` with actual start position.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("atomic_write_file %s to %s", file_identifier, address)
        request = AtomicWriteFileRequest(
            file_identifier=file_identifier,
            access_method=access_method,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
            service_data=request.encode(),
            timeout=timeout,
        )
        return AtomicWriteFileACK.decode(response_data)

    # --- Object management ---

    async def create_object(
        self,
        address: BACnetAddress,
        object_type: ObjectType | None = None,
        object_identifier: ObjectIdentifier | None = None,
        timeout: float | None = None,
    ) -> ObjectIdentifier:
        """Send CreateObject-Request per Clause 15.3.

        Supply either *object_type* (server auto-assigns instance)
        or *object_identifier* (explicit type and instance).

        :param address: Target device address.
        :param object_type: Object type for auto-assigned instance.
        :param object_identifier: Explicit object identifier.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: :class:`ObjectIdentifier` of the created object.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("create_object %s on %s", object_type, address)
        request = CreateObjectRequest(
            object_type=object_type,
            object_identifier=object_identifier,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.CREATE_OBJECT,
            service_data=request.encode(),
            timeout=timeout,
        )
        tag, offset = decode_tag(response_data, 0)
        obj_type_val, instance = decode_object_identifier(
            response_data[offset : offset + tag.length]
        )
        return ObjectIdentifier(ObjectType(obj_type_val), instance)

    async def delete_object(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        timeout: float | None = None,
    ) -> None:
        """Send DeleteObject-Request per Clause 15.4.

        :param address: Target device address.
        :param object_identifier: Object to delete.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("delete_object %s on %s", object_identifier, address)
        request = DeleteObjectRequest(object_identifier=object_identifier)
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.DELETE_OBJECT,
            service_data=request.encode(),
            timeout=timeout,
        )

    # --- List manipulation ---

    async def add_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send AddListElement-Request per Clause 15.1.

        :param address: Target device address.
        :param object_identifier: Object containing the list property.
        :param property_identifier: List property to modify.
        :param list_of_elements: Application-tagged encoded elements to add.
        :param array_index: Optional array index.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug(
            "add_list_element %s %s on %s", object_identifier, property_identifier, address
        )
        request = AddListElementRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            list_of_elements=list_of_elements,
            property_array_index=array_index,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.ADD_LIST_ELEMENT,
            service_data=request.encode(),
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
        """Send RemoveListElement-Request per Clause 15.2.

        :param address: Target device address.
        :param object_identifier: Object containing the list property.
        :param property_identifier: List property to modify.
        :param list_of_elements: Application-tagged encoded elements to remove.
        :param array_index: Optional array index.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug(
            "remove_list_element %s %s on %s", object_identifier, property_identifier, address
        )
        request = RemoveListElementRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            list_of_elements=list_of_elements,
            property_array_index=array_index,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
            service_data=request.encode(),
            timeout=timeout,
        )

    # --- Discovery ---

    async def who_has(
        self,
        object_identifier: (
            str | tuple[str | ObjectType | int, int] | ObjectIdentifier | None
        ) = None,
        object_name: str | None = None,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[IHaveRequest]:
        """Discover objects via Who-Has broadcast per Clause 16.9.

        Sends a Who-Has request and collects I-Have responses for the
        specified timeout duration. Supply either *object_identifier*
        or *object_name*.

        :param object_identifier: Object to search for by identifier
            (e.g. ``"ai,1"`` or ``ObjectIdentifier(...)``).
        :param object_name: Object to search for by name string.
        :param low_limit: Optional lower bound of device instance range.
        :param high_limit: Optional upper bound of device instance range.
        :param destination: Broadcast address (default: global broadcast).
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
            responses have been collected instead of waiting for the
            full timeout.
        :returns: List of :class:`IHaveRequest` responses received within the
            timeout.

        Example::

            # Search by object identifier
            results = await client.who_has(object_identifier="ai,1")

            # Search by object name
            results = await client.who_has(object_name="Zone Temp")
        """
        logger.debug("who_has object_name=%s object_identifier=%s", object_name, object_identifier)
        parsed_oid: ObjectIdentifier | None = None
        if object_identifier is not None:
            parsed_oid = parse_object_identifier(object_identifier)
        request = WhoHasRequest(
            object_identifier=parsed_oid,
            object_name=object_name,
            low_limit=low_limit,
            high_limit=high_limit,
        )
        return await self._collect_unconfirmed_responses(
            send_service=UnconfirmedServiceChoice.WHO_HAS,
            send_data=request.encode(),
            listen_service=UnconfirmedServiceChoice.I_HAVE,
            decoder=lambda data, _src: IHaveRequest.decode(data),
            destination=destination,
            timeout=timeout,
            expected_count=expected_count,
        )

    # --- Router discovery ---

    async def who_is_router_to_network(
        self,
        network: int | None = None,
        destination: str | BACnetAddress | None = None,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[RouterInfo]:
        """Discover routers and reachable networks.

        Sends a Who-Is-Router-To-Network message and collects
        I-Am-Router-To-Network responses.

        :param network: Optional specific network to query. If ``None``,
            discovers all reachable networks.
        :param destination: Target for the query. Accepts an IP string,
            a :class:`BACnetAddress`, or ``None`` for local
            broadcast.
        :param timeout: Seconds to wait for responses.
        :param expected_count: When set, return early once this many
            distinct routers have responded instead of waiting for the
            full timeout.
        :returns: List of router information with address and accessible
            networks. Multiple responses from the same router are
            merged.

        Example::

            routers = await client.who_is_router_to_network(timeout=3.0)
            for router in routers:
                print(f"Router at {router.address}: networks {router.networks}")
        """
        logger.debug("who_is_router_to_network network=%s", network)
        from bac_py.network.address import BIPAddress
        from bac_py.network.messages import (
            IAmRouterToNetwork,
            WhoIsRouterToNetwork,
            encode_network_message,
        )
        from bac_py.types.enums import NetworkMessageType

        # Collect responses keyed by router MAC
        router_map: dict[str, list[int]] = {}
        done_event: asyncio.Event | None = asyncio.Event() if expected_count is not None else None

        def on_i_am_router(msg: object, source_mac: bytes) -> None:
            if not isinstance(msg, IAmRouterToNetwork):
                return
            # Build human-readable address from 6-byte MAC
            addr = BIPAddress.decode(source_mac)
            addr_str = f"{addr.host}:{addr.port}"
            existing = router_map.get(addr_str, [])
            for net in msg.networks:
                if net not in existing:
                    existing.append(net)
            router_map[addr_str] = existing
            if (
                done_event is not None
                and expected_count is not None
                and len(router_map) >= expected_count
            ):
                done_event.set()

        self._app.register_network_message_handler(
            NetworkMessageType.I_AM_ROUTER_TO_NETWORK, on_i_am_router
        )
        try:
            # Send Who-Is-Router-To-Network
            who_msg = WhoIsRouterToNetwork(network=network)
            dest_addr: BACnetAddress | None = None
            if isinstance(destination, str):
                dest_addr = parse_address(destination)
            elif destination is not None:
                dest_addr = destination

            self._app.send_network_message(
                NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
                encode_network_message(who_msg),
                dest_addr,
            )
            if done_event is not None:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(done_event.wait(), timeout)
            else:
                await asyncio.sleep(timeout)
        finally:
            self._app.unregister_network_message_handler(
                NetworkMessageType.I_AM_ROUTER_TO_NETWORK, on_i_am_router
            )

        return [RouterInfo(address=addr, networks=nets) for addr, nets in router_map.items()]

    # --- Private transfer ---

    async def confirmed_private_transfer(
        self,
        address: BACnetAddress,
        vendor_id: int,
        service_number: int,
        service_parameters: bytes | None = None,
        timeout: float | None = None,
    ) -> ConfirmedPrivateTransferACK:
        """Send ConfirmedPrivateTransfer-Request per Clause 16.2.

        :param address: Target device address.
        :param vendor_id: Vendor identifier.
        :param service_number: Vendor-specific service number.
        :param service_parameters: Optional vendor-specific data.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded ConfirmedPrivateTransfer-ACK.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug(
            "confirmed_private_transfer vendor=%s service=%s to %s",
            vendor_id,
            service_number,
            address,
        )
        request = ConfirmedPrivateTransferRequest(
            vendor_id=vendor_id,
            service_number=service_number,
            service_parameters=service_parameters,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.CONFIRMED_PRIVATE_TRANSFER,
            service_data=request.encode(),
            timeout=timeout,
        )
        return ConfirmedPrivateTransferACK.decode(response_data)

    def unconfirmed_private_transfer(
        self,
        destination: BACnetAddress,
        vendor_id: int,
        service_number: int,
        service_parameters: bytes | None = None,
    ) -> None:
        """Send UnconfirmedPrivateTransfer-Request per Clause 16.3.

        This is an unconfirmed service (fire-and-forget).

        :param destination: Target device or broadcast address.
        :param vendor_id: Vendor identifier.
        :param service_number: Vendor-specific service number.
        :param service_parameters: Optional vendor-specific data.
        """
        logger.debug(
            "unconfirmed_private_transfer vendor=%s service=%s", vendor_id, service_number
        )
        request = UnconfirmedPrivateTransferRequest(
            vendor_id=vendor_id,
            service_number=service_number,
            service_parameters=service_parameters,
        )
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.UNCONFIRMED_PRIVATE_TRANSFER,
            service_data=request.encode(),
        )

    # --- BBMD table management ---

    def _require_transport(self) -> BIPTransport:
        """Return the primary BIPTransport or raise if unavailable."""
        transport = self._app._transport
        if transport is None:
            msg = "Transport not available (application not started or in router mode)"
            raise RuntimeError(msg)
        return transport  # type: ignore[return-value]

    async def read_bdt(
        self,
        bbmd_address: str | BACnetAddress,
        timeout: float = 5.0,
    ) -> list[BDTEntryInfo]:
        """Read the Broadcast Distribution Table from a remote BBMD.

        :param bbmd_address: Address of the BBMD to query (e.g.
            ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
        :param timeout: Seconds to wait for a response.
        :returns: List of BDT entries with address and mask information.
        :raises RuntimeError: If transport is not available or device
            rejects the request (not a BBMD).
        :raises TimeoutError: If no response within *timeout*.
        """
        logger.debug("read_bdt from %s", bbmd_address)
        from bac_py.transport.bip import BvlcNakError

        transport = self._require_transport()
        bip_addr = self._app._parse_bip_address(
            bbmd_address if isinstance(bbmd_address, str) else str(bbmd_address)
        )
        try:
            entries = await transport.read_bdt(bip_addr, timeout=timeout)
        except BvlcNakError as exc:
            msg = f"Device rejected Read-BDT: not a BBMD (NAK code {exc.result_code:#06x})"
            raise RuntimeError(msg) from exc
        return [
            BDTEntryInfo(
                address=f"{e.address.host}:{e.address.port}",
                mask=".".join(str(b) for b in e.broadcast_mask),
            )
            for e in entries
        ]

    async def read_fdt(
        self,
        bbmd_address: str | BACnetAddress,
        timeout: float = 5.0,
    ) -> list[FDTEntryInfo]:
        """Read the Foreign Device Table from a remote BBMD.

        :param bbmd_address: Address of the BBMD to query (e.g.
            ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
        :param timeout: Seconds to wait for a response.
        :returns: List of FDT entries with address, TTL, and remaining time.
        :raises RuntimeError: If transport is not available or device
            rejects the request (not a BBMD).
        :raises TimeoutError: If no response within *timeout*.
        """
        logger.debug("read_fdt from %s", bbmd_address)
        from bac_py.transport.bip import BvlcNakError

        transport = self._require_transport()
        bip_addr = self._app._parse_bip_address(
            bbmd_address if isinstance(bbmd_address, str) else str(bbmd_address)
        )
        try:
            entries = await transport.read_fdt(bip_addr, timeout=timeout)
        except BvlcNakError as exc:
            msg = f"Device rejected Read-FDT: not a BBMD (NAK code {exc.result_code:#06x})"
            raise RuntimeError(msg) from exc
        return [
            FDTEntryInfo(
                address=f"{e.address.host}:{e.address.port}",
                ttl=e.ttl,
                remaining=e.remaining,
            )
            for e in entries
        ]

    async def write_bdt(
        self,
        bbmd_address: str | BACnetAddress,
        entries: list[BDTEntryInfo],
        timeout: float = 5.0,
    ) -> None:
        """Write a Broadcast Distribution Table to a remote BBMD.

        :param bbmd_address: Address of the BBMD to configure (e.g.
            ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
        :param entries: BDT entries to write.
        :param timeout: Seconds to wait for a response.
        :raises RuntimeError: If transport is not available or BBMD
            rejects the write (NAK).
        :raises TimeoutError: If no response within *timeout*.
        """
        logger.debug("write_bdt %s entries to %s", len(entries), bbmd_address)
        from bac_py.transport.bbmd import BDTEntry
        from bac_py.types.enums import BvlcResultCode

        transport = self._require_transport()
        bip_addr = self._app._parse_bip_address(
            bbmd_address if isinstance(bbmd_address, str) else str(bbmd_address)
        )
        bdt_entries = []
        for info in entries:
            entry_addr = self._app._parse_bip_address(info.address)
            mask_parts = [int(x) for x in info.mask.split(".")]
            bdt_entries.append(BDTEntry(address=entry_addr, broadcast_mask=bytes(mask_parts)))
        result = await transport.write_bdt(bip_addr, bdt_entries, timeout=timeout)
        if result != BvlcResultCode.SUCCESSFUL_COMPLETION:
            msg = f"BBMD rejected Write-BDT: {result.name}"
            raise RuntimeError(msg)

    # --- Alarm and event services ---

    async def acknowledge_alarm(
        self,
        address: BACnetAddress,
        acknowledging_process_identifier: int,
        event_object_identifier: ObjectIdentifier,
        event_state_acknowledged: EventState,
        time_stamp: BACnetTimeStamp,
        acknowledgment_source: str,
        time_of_acknowledgment: BACnetTimeStamp,
        timeout: float | None = None,
    ) -> None:
        """Send AcknowledgeAlarm-Request per Clause 13.5.

        :param address: Target device address.
        :param acknowledging_process_identifier: Process ID of the acknowledger.
        :param event_object_identifier: Object whose event is being acknowledged.
        :param event_state_acknowledged: Event state being acknowledged.
        :param time_stamp: Time stamp of the event being acknowledged.
        :param acknowledgment_source: Character string identifying the source.
        :param time_of_acknowledgment: Time stamp of the acknowledgment.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.info("acknowledge_alarm %s on %s", event_object_identifier, address)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=acknowledging_process_identifier,
            event_object_identifier=event_object_identifier,
            event_state_acknowledged=event_state_acknowledged,
            time_stamp=time_stamp,
            acknowledgment_source=acknowledgment_source,
            time_of_acknowledgment=time_of_acknowledgment,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.ACKNOWLEDGE_ALARM,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def get_alarm_summary(
        self,
        address: BACnetAddress,
        timeout: float | None = None,
    ) -> GetAlarmSummaryACK:
        """Send GetAlarmSummary-Request per Clause 13.6.

        :param address: Target device address.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`GetAlarmSummaryACK` with alarm summary entries.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("get_alarm_summary from %s", address)
        request = GetAlarmSummaryRequest()
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.GET_ALARM_SUMMARY,
            service_data=request.encode(),
            timeout=timeout,
        )
        return GetAlarmSummaryACK.decode(response_data)

    async def get_enrollment_summary(
        self,
        address: BACnetAddress,
        acknowledgment_filter: AcknowledgmentFilter,
        event_state_filter: EventState | None = None,
        event_type_filter: EventType | None = None,
        priority_min: int | None = None,
        priority_max: int | None = None,
        notification_class_filter: int | None = None,
        timeout: float | None = None,
    ) -> GetEnrollmentSummaryACK:
        """Send GetEnrollmentSummary-Request per Clause 13.7.

        :param address: Target device address.
        :param acknowledgment_filter: Filter by acknowledgment state.
        :param event_state_filter: Optional filter by event state.
        :param event_type_filter: Optional filter by event type.
        :param priority_min: Optional minimum priority (0--255).
        :param priority_max: Optional maximum priority (0--255).
        :param notification_class_filter: Optional notification class filter.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`GetEnrollmentSummaryACK` with enrollment summaries.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("get_enrollment_summary from %s", address)
        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=acknowledgment_filter,
            event_state_filter=event_state_filter,
            event_type_filter=event_type_filter,
            priority_min=priority_min,
            priority_max=priority_max,
            notification_class_filter=notification_class_filter,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.GET_ENROLLMENT_SUMMARY,
            service_data=request.encode(),
            timeout=timeout,
        )
        return GetEnrollmentSummaryACK.decode(response_data)

    async def get_event_information(
        self,
        address: BACnetAddress,
        last_received_object_identifier: ObjectIdentifier | None = None,
        timeout: float | None = None,
    ) -> GetEventInformationACK:
        """Send GetEventInformation-Request per Clause 13.12.

        :param address: Target device address.
        :param last_received_object_identifier: Optional object identifier for
            pagination. Pass the last object identifier from a previous
            response to continue fetching when ``more_events`` is ``True``.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`GetEventInformationACK` with event summaries.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("get_event_information from %s", address)
        request = GetEventInformationRequest(
            last_received_object_identifier=last_received_object_identifier,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.GET_EVENT_INFORMATION,
            service_data=request.encode(),
            timeout=timeout,
        )
        return GetEventInformationACK.decode(response_data)

    async def confirmed_event_notification(
        self,
        address: BACnetAddress,
        notification: EventNotificationRequest,
        timeout: float | None = None,
    ) -> None:
        """Send ConfirmedEventNotification-Request per Clause 13.8.

        :param address: Target device address.
        :param notification: Pre-built :class:`EventNotificationRequest` with
            all event notification parameters.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetRejectError: On Reject-PDU response.
        :raises BACnetAbortError: On Abort-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("confirmed_event_notification to %s", address)
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION,
            service_data=notification.encode(),
            timeout=timeout,
        )

    async def delete_fdt_entry(
        self,
        bbmd_address: str | BACnetAddress,
        entry_address: str,
        timeout: float = 5.0,
    ) -> None:
        """Delete a Foreign Device Table entry on a remote BBMD.

        :param bbmd_address: Address of the BBMD (e.g.
            ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
        :param entry_address: Address of the FDT entry to delete
            (e.g. ``"10.0.0.50:47808"``).
        :param timeout: Seconds to wait for a response.
        :raises RuntimeError: If transport is not available or BBMD
            rejects the delete (NAK).
        :raises TimeoutError: If no response within *timeout*.
        """
        logger.info("delete_fdt_entry %s from %s", entry_address, bbmd_address)
        from bac_py.types.enums import BvlcResultCode

        transport = self._require_transport()
        bip_bbmd = self._app._parse_bip_address(
            bbmd_address if isinstance(bbmd_address, str) else str(bbmd_address)
        )
        bip_entry = self._app._parse_bip_address(entry_address)
        result = await transport.delete_fdt_entry(bip_bbmd, bip_entry, timeout=timeout)
        if result != BvlcResultCode.SUCCESSFUL_COMPLETION:
            msg = f"BBMD rejected Delete-FDT-Entry: {result.name}"
            raise RuntimeError(msg)

    # --- Text message ---

    async def send_confirmed_text_message(
        self,
        address: BACnetAddress,
        source_device: ObjectIdentifier,
        message: str,
        message_priority: MessagePriority = MessagePriority.NORMAL,
        message_class_numeric: int | None = None,
        message_class_character: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Send ConfirmedTextMessage-Request per Clause 16.5.

        :param address: Target device address.
        :param source_device: Object identifier of the sending device.
        :param message: Text message content.
        :param message_priority: Message priority (NORMAL or URGENT).
        :param message_class_numeric: Optional numeric message class.
        :param message_class_character: Optional character message class.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("send_confirmed_text_message to %s", address)
        request = ConfirmedTextMessageRequest(
            text_message_source_device=source_device,
            message_priority=message_priority,
            message=message,
            message_class_numeric=message_class_numeric,
            message_class_character=message_class_character,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
            service_data=request.encode(),
            timeout=timeout,
        )

    def send_unconfirmed_text_message(
        self,
        destination: BACnetAddress,
        source_device: ObjectIdentifier,
        message: str,
        message_priority: MessagePriority = MessagePriority.NORMAL,
        message_class_numeric: int | None = None,
        message_class_character: str | None = None,
    ) -> None:
        """Send UnconfirmedTextMessage-Request per Clause 16.6.

        This is an unconfirmed service (fire-and-forget).

        :param destination: Target device or broadcast address.
        :param source_device: Object identifier of the sending device.
        :param message: Text message content.
        :param message_priority: Message priority (NORMAL or URGENT).
        :param message_class_numeric: Optional numeric message class.
        :param message_class_character: Optional character message class.
        """
        logger.debug("send_unconfirmed_text_message")
        request = UnconfirmedTextMessageRequest(
            text_message_source_device=source_device,
            message_priority=message_priority,
            message=message,
            message_class_numeric=message_class_numeric,
            message_class_character=message_class_character,
        )
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE,
            service_data=request.encode(),
        )

    # --- WriteGroup ---

    def write_group(
        self,
        destination: BACnetAddress,
        group_number: int,
        write_priority: int,
        change_list: list[GroupChannelValue],
    ) -> None:
        """Send WriteGroup-Request per Clause 15.11.

        This is an unconfirmed service (fire-and-forget).

        :param destination: Target device or broadcast address.
        :param group_number: Channel group number (Unsigned32).
        :param write_priority: Write priority (1-16).
        :param change_list: List of channel values to write.
        """
        logger.debug("write_group group=%s", group_number)
        request = WriteGroupRequest(
            group_number=group_number,
            write_priority=write_priority,
            change_list=change_list,
        )
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.WRITE_GROUP,
            service_data=request.encode(),
        )

    # --- Device discovery (new in 2020) ---

    def who_am_i(
        self,
        destination: BACnetAddress,
        vendor_id: int,
        model_name: str,
        serial_number: str,
    ) -> None:
        """Send Who-Am-I-Request per Clause 16.11.

        This is an unconfirmed service (fire-and-forget).
        Sent by unconfigured devices to request identity assignment.

        :param destination: Target address (typically global broadcast).
        :param vendor_id: Device vendor identifier.
        :param model_name: Device model name.
        :param serial_number: Device serial number.
        """
        logger.debug("who_am_i")
        request = WhoAmIRequest(
            vendor_id=vendor_id,
            model_name=model_name,
            serial_number=serial_number,
        )
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.WHO_AM_I,
            service_data=request.encode(),
        )

    def you_are(
        self,
        destination: BACnetAddress,
        device_identifier: ObjectIdentifier,
        device_mac_address: bytes,
        device_network_number: int | None = None,
    ) -> None:
        """Send You-Are-Request per Clause 16.11.

        This is an unconfirmed service (fire-and-forget).
        Sent by a supervisor to assign identity to an unconfigured device.

        :param destination: Target device address.
        :param device_identifier: Assigned device object identifier.
        :param device_mac_address: MAC address of the target device.
        :param device_network_number: Optional network number.
        """
        logger.debug("you_are %s to %s", device_identifier, destination)
        request = YouAreRequest(
            device_identifier=device_identifier,
            device_mac_address=device_mac_address,
            device_network_number=device_network_number,
        )
        self._app.unconfirmed_request(
            destination=destination,
            service_choice=UnconfirmedServiceChoice.YOU_ARE,
            service_data=request.encode(),
        )

    # --- Unconfigured device discovery (Clause 19.7) ---

    async def discover_unconfigured(
        self,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 5.0,
    ) -> list[UnconfiguredDevice]:
        """Listen for unconfigured devices broadcasting Who-Am-I.

        Registers a temporary handler for Who-Am-I messages and collects
        responses for the specified duration.

        :param destination: Not used for listening, included for API consistency.
        :param timeout: Seconds to listen for Who-Am-I messages.
        :returns: List of :class:`UnconfiguredDevice` discovered.
        """
        logger.info("discover_unconfigured timeout=%s", timeout)
        results: list[UnconfiguredDevice] = []

        def _on_who_am_i(service_data: bytes, source: BACnetAddress) -> None:
            try:
                req = WhoAmIRequest.decode(service_data)
                results.append(
                    UnconfiguredDevice(
                        address=source,
                        vendor_id=req.vendor_id,
                        model_name=req.model_name,
                        serial_number=req.serial_number,
                    )
                )
            except (ValueError, IndexError):
                pass

        self._app.register_temporary_handler(
            UnconfirmedServiceChoice.WHO_AM_I,
            _on_who_am_i,
        )
        try:
            await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(
                UnconfirmedServiceChoice.WHO_AM_I,
                _on_who_am_i,
            )
        return results

    # --- Virtual terminal ---

    async def vt_open(
        self,
        address: BACnetAddress,
        vt_class: VTClass,
        local_vt_session_identifier: int,
        timeout: float | None = None,
    ) -> VTOpenACK:
        """Send VT-Open-Request per Clause 17.1.

        :param address: Target device address.
        :param vt_class: Virtual terminal class to open.
        :param local_vt_session_identifier: Local session ID (0-255).
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`VTOpenACK` with remote session ID.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("vt_open %s to %s", vt_class, address)
        request = VTOpenRequest(
            vt_class=vt_class,
            local_vt_session_identifier=local_vt_session_identifier,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.VT_OPEN,
            service_data=request.encode(),
            timeout=timeout,
        )
        return VTOpenACK.decode(response_data)

    async def vt_close(
        self,
        address: BACnetAddress,
        session_identifiers: list[int],
        timeout: float | None = None,
    ) -> None:
        """Send VT-Close-Request per Clause 17.2.

        :param address: Target device address.
        :param session_identifiers: List of remote VT session IDs to close.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("vt_close sessions=%s on %s", session_identifiers, address)
        request = VTCloseRequest(
            list_of_remote_vt_session_identifiers=session_identifiers,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.VT_CLOSE,
            service_data=request.encode(),
            timeout=timeout,
        )

    async def vt_data(
        self,
        address: BACnetAddress,
        vt_session_identifier: int,
        vt_new_data: bytes,
        vt_data_flag: bool = False,
        timeout: float | None = None,
    ) -> VTDataACK:
        """Send VT-Data-Request per Clause 17.3.

        :param address: Target device address.
        :param vt_session_identifier: Remote VT session ID.
        :param vt_new_data: Data to send to the virtual terminal.
        :param vt_data_flag: ``True`` if this is the last data segment.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`VTDataACK`.
        :raises BACnetError: On Error-PDU response.
        :raises BACnetTimeoutError: On timeout after all retries.
        """
        logger.debug("vt_data session=%s to %s", vt_session_identifier, address)
        request = VTDataRequest(
            vt_session_identifier=vt_session_identifier,
            vt_new_data=vt_new_data,
            vt_data_flag=vt_data_flag,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.VT_DATA,
            service_data=request.encode(),
            timeout=timeout,
        )
        return VTDataACK.decode(response_data)

    # --- Audit services (Clause 13.19-13.21) ---

    async def query_audit_log(
        self,
        address: BACnetAddress,
        audit_log: ObjectIdentifier,
        query_parameters: AuditQueryByTarget | AuditQueryBySource,
        start_at_sequence_number: int | None = None,
        requested_count: int = 100,
        timeout: float | None = None,
    ) -> AuditLogQueryACK:
        """Send AuditLogQuery-Request per Clause 13.19.

        :param address: Target device address.
        :param audit_log: Audit Log object identifier.
        :param query_parameters: Query by target or source.
        :param start_at_sequence_number: Optional starting sequence number.
        :param requested_count: Maximum number of records to return.
        :param timeout: Optional caller-level timeout in seconds.
        :returns: Decoded :class:`AuditLogQueryACK`.
        :raises BACnetError: On Error-PDU response.
        """
        logger.debug("query_audit_log from %s", address)
        request = AuditLogQueryRequest(
            audit_log=audit_log,
            query_parameters=query_parameters,
            start_at_sequence_number=start_at_sequence_number,
            requested_count=requested_count,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.AUDIT_LOG_QUERY,
            service_data=request.encode(),
            timeout=timeout,
        )
        return AuditLogQueryACK.decode(response_data)

    async def send_audit_notification(
        self,
        address: BACnetAddress,
        notifications: list[BACnetAuditNotification],
        confirmed: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Send audit notification(s) per Clause 13.20/13.21.

        :param address: Target device address.
        :param notifications: List of audit notifications to send.
        :param confirmed: ``True`` for confirmed, ``False`` for unconfirmed.
        :param timeout: Optional caller-level timeout in seconds.
        :raises BACnetError: On Error-PDU response (confirmed only).
        """
        logger.debug("send_audit_notification confirmed=%s", confirmed)
        if confirmed:
            request = ConfirmedAuditNotificationRequest(notifications=notifications)
            await self._app.confirmed_request(
                destination=address,
                service_choice=ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
                service_data=request.encode(),
                timeout=timeout,
            )
        else:
            request = UnconfirmedAuditNotificationRequest(notifications=notifications)
            self._app.unconfirmed_request(
                destination=address,
                service_choice=UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION,
                service_data=request.encode(),
            )

    # --- Backup and Restore (Clause 19.1) ---

    async def backup_device(
        self,
        address: BACnetAddress,
        password: str | None = None,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> BackupData:
        """Perform a full backup of a remote BACnet device (Clause 19.1).

        Executes the backup procedure:
        1. ReinitializeDevice START_BACKUP
        2. Poll BACKUP_AND_RESTORE_STATE until ready
        3. Read CONFIGURATION_FILES list
        4. Download each file via AtomicReadFile
        5. ReinitializeDevice END_BACKUP

        :param address: Target device address.
        :param password: Optional password for ReinitializeDevice.
        :param poll_interval: Seconds between state polls.
        :param timeout: Optional overall timeout in seconds.
        :returns: :class:`BackupData` with downloaded configuration files.
        :raises BACnetError: On Error-PDU or invalid state transition.
        :raises BACnetTimeoutError: On timeout.
        """
        logger.info("backup_device %s", address)
        # Step 1: Start backup
        await self.reinitialize_device(
            address,
            ReinitializedState.START_BACKUP,
            password=password,
            timeout=timeout,
        )

        # Step 2: Poll until preparing phase completes
        device_oid = await self._discover_device_oid(address, timeout=timeout)
        await self._poll_backup_restore_state(
            address,
            device_oid,
            target_states=(
                BackupAndRestoreState.PERFORMING_A_BACKUP,
                BackupAndRestoreState.PREPARING_FOR_BACKUP,
            ),
            poll_interval=poll_interval,
            timeout=timeout,
        )

        # Step 3: Read configuration files list
        ack = await self.read_property(
            address,
            device_oid,
            PropertyIdentifier.CONFIGURATION_FILES,
            timeout=timeout,
        )
        config_file_ids: list[ObjectIdentifier] = []
        decoded_files = decode_all_application_values(ack.property_value)
        if isinstance(decoded_files, list):
            for v in decoded_files:
                if isinstance(v, ObjectIdentifier):
                    config_file_ids.append(v)
        elif isinstance(decoded_files, ObjectIdentifier):
            config_file_ids.append(decoded_files)

        # Step 4: Download each file
        file_contents: list[tuple[ObjectIdentifier, bytes]] = []
        for file_oid in config_file_ids:
            data = await self._download_file(address, file_oid, timeout=timeout)
            file_contents.append((file_oid, data))

        # Step 5: End backup
        await self.reinitialize_device(
            address,
            ReinitializedState.END_BACKUP,
            password=password,
            timeout=timeout,
        )

        return BackupData(
            device_instance=device_oid.instance_number,
            configuration_files=file_contents,
        )

    async def restore_device(
        self,
        address: BACnetAddress,
        backup_data: BackupData,
        password: str | None = None,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> None:
        """Perform a full restore of a remote BACnet device (Clause 19.1).

        Executes the restore procedure:
        1. ReinitializeDevice START_RESTORE
        2. Poll BACKUP_AND_RESTORE_STATE until ready
        3. Upload each config file via AtomicWriteFile
        4. ReinitializeDevice END_RESTORE

        :param address: Target device address.
        :param backup_data: :class:`BackupData` from a previous backup.
        :param password: Optional password for ReinitializeDevice.
        :param poll_interval: Seconds between state polls.
        :param timeout: Optional overall timeout in seconds.
        :raises BACnetError: On Error-PDU or invalid state transition.
        :raises BACnetTimeoutError: On timeout.
        """
        logger.info("restore_device %s", address)
        # Step 1: Start restore
        await self.reinitialize_device(
            address,
            ReinitializedState.START_RESTORE,
            password=password,
            timeout=timeout,
        )

        # Step 2: Poll until ready for download
        device_oid = await self._discover_device_oid(address, timeout=timeout)
        await self._poll_backup_restore_state(
            address,
            device_oid,
            target_states=(
                BackupAndRestoreState.PERFORMING_A_RESTORE,
                BackupAndRestoreState.PREPARING_FOR_RESTORE,
            ),
            poll_interval=poll_interval,
            timeout=timeout,
        )

        # Step 3: Upload configuration files
        for file_oid, file_data in backup_data.configuration_files:
            await self.atomic_write_file(
                address,
                file_oid,
                StreamWriteAccess(0, file_data),
                timeout=timeout,
            )

        # Step 4: End restore
        await self.reinitialize_device(
            address,
            ReinitializedState.END_RESTORE,
            password=password,
            timeout=timeout,
        )

    async def _discover_device_oid(
        self,
        address: BACnetAddress,
        timeout: float | None = None,
    ) -> ObjectIdentifier:
        """Read the device's Object_Identifier to determine its instance."""
        ack = await self.read_property(
            address,
            ObjectIdentifier(ObjectType.DEVICE, 4194303),  # wildcard
            PropertyIdentifier.OBJECT_IDENTIFIER,
            timeout=timeout,
        )
        decoded = decode_and_unwrap(ack.property_value)
        if isinstance(decoded, ObjectIdentifier):
            return decoded
        return ObjectIdentifier(ObjectType.DEVICE, 4194303)

    async def _poll_backup_restore_state(
        self,
        address: BACnetAddress,
        device_oid: ObjectIdentifier,
        target_states: tuple[BackupAndRestoreState, ...],
        poll_interval: float = 1.0,
        timeout: float | None = None,
        overall_timeout: float = 300.0,
    ) -> BackupAndRestoreState:
        """Poll BACKUP_AND_RESTORE_STATE until it reaches a target state."""
        deadline = asyncio.get_event_loop().time() + overall_timeout
        while True:
            ack = await self.read_property(
                address,
                device_oid,
                PropertyIdentifier.BACKUP_AND_RESTORE_STATE,
                timeout=timeout,
            )
            decoded_state = decode_and_unwrap(ack.property_value)
            if isinstance(decoded_state, int):
                state = BackupAndRestoreState(decoded_state)
                if state in target_states:
                    return state
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                from bac_py.services.errors import BACnetTimeoutError

                raise BACnetTimeoutError("Timed out waiting for backup/restore state")
            await asyncio.sleep(min(poll_interval, remaining))

    async def _download_file(
        self,
        address: BACnetAddress,
        file_oid: ObjectIdentifier,
        chunk_size: int = 1024,
        timeout: float | None = None,
    ) -> bytes:
        """Download an entire file via AtomicReadFile stream access."""
        from bac_py.services.file_access import StreamReadACK

        buf = bytearray()
        file_offset = 0
        while True:
            ack = await self.atomic_read_file(
                address,
                file_oid,
                StreamReadAccess(file_offset, chunk_size),
                timeout=timeout,
            )
            access = ack.access_method
            assert isinstance(access, StreamReadACK)
            buf.extend(access.file_data)
            if ack.end_of_file:
                break
            file_offset += len(access.file_data)
        return bytes(buf)
