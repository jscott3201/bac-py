"""High-level BACnet client API per ASHRAE 135-2016."""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

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
from bac_py.services.cov import COVNotificationRequest, SubscribeCOVRequest
from bac_py.services.device_mgmt import (
    DeviceCommunicationControlRequest,
    ReinitializeDeviceRequest,
    TimeSynchronizationRequest,
    UTCTimeSynchronizationRequest,
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
from bac_py.services.who_has import IHaveRequest, WhoHasRequest
from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.services.write_property_multiple import (
    WriteAccessSpecification,
    WritePropertyMultipleRequest,
)
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    EnableDisable,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
    Segmentation,
    UnconfirmedServiceChoice,
)
from bac_py.types.parsing import parse_object_identifier, parse_property_identifier
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.transport.bip import BIPTransport

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

    @property
    def address_str(self) -> str:
        """Human-readable address string."""
        return str(self.address)

    def __repr__(self) -> str:
        return f"DiscoveredDevice(instance={self.instance}, address='{self.address_str}')"


def decode_cov_values(notification: COVNotificationRequest) -> dict[str, object]:
    """Decode COV notification property values to a Python dict.

    Extracts and decodes the ``list_of_values`` from a COV notification
    into a human-readable dictionary mapping property names to decoded
    Python values.

    Args:
        notification: A decoded COV notification request.

    Returns:
        Dict mapping property name strings (hyphenated, lowercase) to
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

        Args:
            address: Target device address.
            object_identifier: Object to read from.
            property_identifier: Property to read.
            array_index: Optional array index for array properties.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded ReadPropertyACK containing the property value.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            object_identifier: Object to write to.
            property_identifier: Property to write.
            value: Application-tagged encoded property value bytes.
            priority: Optional write priority (1-16).
            array_index: Optional array index for array properties.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            read_access_specs: List of read access specifications, each
                containing an object identifier and list of property
                references to read.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded ReadPropertyMultiple-ACK with per-property results.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            write_access_specs: List of write access specifications, each
                containing an object identifier and list of property
                values to write.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response (first failing property).
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Convenience wrapper around ``read_property()`` that parses
        addresses and identifiers from strings and decodes the
        returned application-tagged bytes into native Python types.

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            object_identifier: Object to read (e.g. ``"analog-input,1"``
                or ``"ai,1"``).
            property_identifier: Property to read (e.g. ``"present-value"``
                or ``"pv"``).
            array_index: Optional array index.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded Python value (``float``, ``int``, ``str``, ``bool``,
            etc.). Returns a ``list`` if the property contains multiple
            application-tagged values.

        Example::

            value = await client.read("192.168.1.100", "ai,1", "pv")
            name = await client.read("192.168.1.100", "ai,1", "object-name")
        """
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

        Convenience wrapper around ``write_property()`` that parses
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

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            object_identifier: Object to write (e.g. ``"analog-value,1"``
                or ``"av,1"``).
            property_identifier: Property to write (e.g. ``"present-value"``
                or ``"pv"``).
            value: Python value to write (auto-encoded).
            priority: Optional write priority (1-16).
            array_index: Optional array index.
            timeout: Optional caller-level timeout in seconds.

        Example::

            await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
            await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)
            await client.write("192.168.1.100", "av,1", "pv", None, priority=8)
        """
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
    ) -> dict[str, dict[str, object]]:
        """Read multiple properties from multiple objects.

        Convenience wrapper around ``read_property_multiple()`` that
        accepts a simplified dict format and returns decoded Python values.

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            specs: Mapping of object identifiers to lists of property
                identifiers. Example::

                    {
                        "ai,1": ["pv", "name", "units"],
                        "ai,2": ["pv", "status"],
                    }

        Returns:
            Nested dict mapping object ID strings to property name/value
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

        ack = await self.read_property_multiple(addr, access_specs)

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
        timeout: float | None = None,
    ) -> None:
        """Write multiple properties to multiple objects.

        Convenience wrapper around ``write_property_multiple()`` that
        accepts a simplified dict format and automatically encodes
        Python values.

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            specs: Mapping of object identifiers to property/value dicts.
                Example::

                    {
                        "av,1": {"pv": 72.5, "object-name": "Zone Temp"},
                        "bo,1": {"pv": 1},
                    }
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response (first failing property).
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.

        Example::

            await client.write_multiple(
                "192.168.1.100",
                {
                    "av,1": {"pv": 72.5},
                    "bo,1": {"pv": 1},
                },
            )
        """
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
        the response is too large (``BACnetAbortError`` with
        segmentation-not-supported), falls back to reading the array
        length then each element individually.

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            device_instance: Device instance number of the target.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            List of ObjectIdentifier for all objects in the device.

        Example::

            objects = await client.get_object_list("192.168.1.100", 1234)
            for obj in objects:
                print(obj.object_type, obj.instance_number)
        """
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

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            object_identifier: Object to monitor (e.g. ``"ai,1"``).
            process_id: Subscriber process identifier (caller-managed).
            confirmed: True for confirmed notifications, False for unconfirmed.
            lifetime: Subscription lifetime in seconds, or None for indefinite.
            callback: Optional callback for COV notifications. Receives
                ``(COVNotificationRequest, source_address)``. If provided,
                automatically registered via
                :meth:`~bac_py.app.application.BACnetApplication.register_cov_callback`.
            timeout: Optional caller-level timeout in seconds.

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

        Args:
            address: Target device (e.g. ``"192.168.1.100"``).
            object_identifier: Object being monitored (e.g. ``"ai,1"``).
            process_id: Subscriber process identifier used during subscription.
            unregister_callback: If True, also unregister the COV callback.
            timeout: Optional caller-level timeout in seconds.
        """
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

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List or array property to read.
            array_index: Optional array index.
            range_qualifier: Optional range qualifier (by position,
                sequence number, or time). If None, returns all items.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded ReadRange-ACK with the requested items.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            send_service: Service choice for the outgoing request.
            send_data: Encoded service data to send.
            listen_service: Service choice to listen for responses.
            decoder: Callable that decodes ``(service_data, source)``
                into a result object.  Return ``None`` to skip a
                malformed response.
            destination: Broadcast address for the request.
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                responses have been collected.

        Returns:
            List of decoded response objects.
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

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address (default: global broadcast).
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                responses have been collected instead of waiting for the
                full timeout.

        Returns:
            List of I-Am responses received within the timeout.
        """
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
        router, pass a remote broadcast ``BACnetAddress``::

            from bac_py.network.address import BACnetAddress

            remote = BACnetAddress(network=2, mac_address=b"\\xff\\xff\\xff\\xff")
            devices = await client.discover(destination=remote, timeout=5.0)

        When using the :class:`~bac_py.client.Client` wrapper, you can
        pass a string like ``"192.168.1.255"`` for directed local
        broadcast.

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address (default: global broadcast).
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                devices have been discovered instead of waiting for the
                full timeout.

        Returns:
            List of discovered devices with address and device info.

        Example::

            devices = await client.discover(timeout=3.0)
            for dev in devices:
                print(dev.instance, dev.address_str, dev.vendor_id)
        """

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

        Args:
            address: Target device address.
            object_identifier: Object to monitor.
            process_id: Subscriber process identifier (caller-managed).
            confirmed: True for confirmed notifications, False for unconfirmed.
            lifetime: Subscription lifetime in seconds, or None for indefinite.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            object_identifier: Object being monitored.
            process_id: Subscriber process identifier used during subscription.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            enable_disable: Enable/disable communication state.
            time_duration: Optional duration in minutes.
            password: Optional password string (1-20 chars).
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            reinitialized_state: Desired reinitialization state.
            password: Optional password string (1-20 chars).
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            destination: Target device or broadcast address.
            date: BACnet date to synchronize.
            time: BACnet time to synchronize.
        """
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

        Args:
            destination: Target device or broadcast address.
            date: BACnet UTC date to synchronize.
            time: BACnet UTC time to synchronize.
        """
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

        Args:
            address: Target device address.
            file_identifier: ObjectIdentifier of the File object.
            access_method: Stream or record read parameters.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded AtomicReadFile-ACK with file data.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            file_identifier: ObjectIdentifier of the File object.
            access_method: Stream or record write parameters.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded AtomicWriteFile-ACK with actual start position.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Supply either ``object_type`` (server auto-assigns instance)
        or ``object_identifier`` (explicit type and instance).

        Args:
            address: Target device address.
            object_type: Object type for auto-assigned instance.
            object_identifier: Explicit object identifier.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            ObjectIdentifier of the created object.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            object_identifier: Object to delete.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List property to modify.
            list_of_elements: Application-tagged encoded elements to add.
            array_index: Optional array index.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List property to modify.
            list_of_elements: Application-tagged encoded elements to remove.
            array_index: Optional array index.
            timeout: Optional caller-level timeout in seconds.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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
        object_identifier: ObjectIdentifier | None = None,
        object_name: str | None = None,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
        expected_count: int | None = None,
    ) -> list[IHaveRequest]:
        """Discover objects via Who-Has broadcast per Clause 16.9.

        Sends a Who-Has request and collects I-Have responses for the
        specified timeout duration. Supply either ``object_identifier``
        or ``object_name``.

        Args:
            object_identifier: Object to search for by identifier.
            object_name: Object to search for by name.
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address (default: global broadcast).
            timeout: Seconds to wait for responses.
            expected_count: When set, return early once this many
                responses have been collected instead of waiting for the
                full timeout.

        Returns:
            List of I-Have responses received within the timeout.
        """
        request = WhoHasRequest(
            object_identifier=object_identifier,
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
    ) -> list[RouterInfo]:
        """Discover routers and reachable networks.

        Sends a Who-Is-Router-To-Network message and collects
        I-Am-Router-To-Network responses.

        Args:
            network: Optional specific network to query. If ``None``,
                discovers all reachable networks.
            destination: Target for the query. Accepts an IP string,
                a :class:`BACnetAddress`, or ``None`` for local
                broadcast.
            timeout: Seconds to wait for responses.

        Returns:
            List of router information with address and accessible
            networks. Multiple responses from the same router are
            merged.

        Example::

            routers = await client.who_is_router_to_network(timeout=3.0)
            for router in routers:
                print(f"Router at {router.address}: networks {router.networks}")
        """
        from bac_py.network.address import BIPAddress
        from bac_py.network.messages import (
            IAmRouterToNetwork,
            WhoIsRouterToNetwork,
            encode_network_message,
        )
        from bac_py.types.enums import NetworkMessageType

        # Collect responses keyed by router MAC
        router_map: dict[str, list[int]] = {}

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

        Args:
            address: Target device address.
            vendor_id: Vendor identifier.
            service_number: Vendor-specific service number.
            service_parameters: Optional vendor-specific data.
            timeout: Optional caller-level timeout in seconds.

        Returns:
            Decoded ConfirmedPrivateTransfer-ACK.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
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

        Args:
            destination: Target device or broadcast address.
            vendor_id: Vendor identifier.
            service_number: Vendor-specific service number.
            service_parameters: Optional vendor-specific data.
        """
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
        return transport

    async def read_bdt(
        self,
        bbmd_address: str | BACnetAddress,
        timeout: float = 5.0,
    ) -> list[BDTEntryInfo]:
        """Read the Broadcast Distribution Table from a remote BBMD.

        Args:
            bbmd_address: Address of the BBMD to query (e.g.
                ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
            timeout: Seconds to wait for a response.

        Returns:
            List of BDT entries with address and mask information.

        Raises:
            RuntimeError: If transport is not available.
            TimeoutError: If no response within *timeout*.
        """
        transport = self._require_transport()
        bip_addr = self._app._parse_bip_address(
            bbmd_address if isinstance(bbmd_address, str) else str(bbmd_address)
        )
        entries = await transport.read_bdt(bip_addr, timeout=timeout)
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

        Args:
            bbmd_address: Address of the BBMD to query (e.g.
                ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
            timeout: Seconds to wait for a response.

        Returns:
            List of FDT entries with address, TTL, and remaining time.

        Raises:
            RuntimeError: If transport is not available.
            TimeoutError: If no response within *timeout*.
        """
        transport = self._require_transport()
        bip_addr = self._app._parse_bip_address(
            bbmd_address if isinstance(bbmd_address, str) else str(bbmd_address)
        )
        entries = await transport.read_fdt(bip_addr, timeout=timeout)
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

        Args:
            bbmd_address: Address of the BBMD to configure (e.g.
                ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
            entries: BDT entries to write.
            timeout: Seconds to wait for a response.

        Raises:
            RuntimeError: If transport is not available or BBMD
                rejects the write (NAK).
            TimeoutError: If no response within *timeout*.
        """
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

    async def delete_fdt_entry(
        self,
        bbmd_address: str | BACnetAddress,
        entry_address: str,
        timeout: float = 5.0,
    ) -> None:
        """Delete a Foreign Device Table entry on a remote BBMD.

        Args:
            bbmd_address: Address of the BBMD (e.g.
                ``"192.168.1.1"`` or ``"192.168.1.1:47808"``).
            entry_address: Address of the FDT entry to delete
                (e.g. ``"10.0.0.50:47808"``).
            timeout: Seconds to wait for a response.

        Raises:
            RuntimeError: If transport is not available or BBMD
                rejects the delete (NAK).
            TimeoutError: If no response within *timeout*.
        """
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
