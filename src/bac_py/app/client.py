"""High-level BACnet client API per ASHRAE 135-2016."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from bac_py.encoding.primitives import (
    decode_object_identifier,
)
from bac_py.encoding.tags import decode_tag
from bac_py.network.address import GLOBAL_BROADCAST
from bac_py.services.cov import SubscribeCOVRequest
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
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress

logger = logging.getLogger(__name__)


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
    ) -> ReadPropertyACK:
        """Read a single property from a remote device.

        Args:
            address: Target device address.
            object_identifier: Object to read from.
            property_identifier: Property to read.
            array_index: Optional array index for array properties.

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
    ) -> None:
        """Write a property value to a remote device.

        Args:
            address: Target device address.
            object_identifier: Object to write to.
            property_identifier: Property to write.
            value: Application-tagged encoded property value bytes.
            priority: Optional write priority (1-16).
            array_index: Optional array index for array properties.

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
        )

    async def read_property_multiple(
        self,
        address: BACnetAddress,
        read_access_specs: list[ReadAccessSpecification],
    ) -> ReadPropertyMultipleACK:
        """Read multiple properties from one or more objects.

        Args:
            address: Target device address.
            read_access_specs: List of read access specifications, each
                containing an object identifier and list of property
                references to read.

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
        )
        return ReadPropertyMultipleACK.decode(response_data)

    async def write_property_multiple(
        self,
        address: BACnetAddress,
        write_access_specs: list[WriteAccessSpecification],
    ) -> None:
        """Write multiple properties to one or more objects.

        Args:
            address: Target device address.
            write_access_specs: List of write access specifications, each
                containing an object identifier and list of property
                values to write.

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
        )

    # --- Convenience API ---

    # Object types where present-value is Real (IEEE-754 float)
    _ANALOG_TYPES = frozenset(
        {
            ObjectType.ANALOG_INPUT,
            ObjectType.ANALOG_OUTPUT,
            ObjectType.ANALOG_VALUE,
        }
    )
    # Object types where present-value is Enumerated
    _BINARY_TYPES = frozenset(
        {
            ObjectType.BINARY_INPUT,
            ObjectType.BINARY_OUTPUT,
            ObjectType.BINARY_VALUE,
        }
    )
    # Object types where present-value is Unsigned
    _MULTISTATE_TYPES = frozenset(
        {
            ObjectType.MULTI_STATE_INPUT,
            ObjectType.MULTI_STATE_OUTPUT,
            ObjectType.MULTI_STATE_VALUE,
        }
    )

    # Expected BACnet data type tag for well-known properties.
    # Used by _encode_for_write() to select the correct encoding
    # when a plain int is written to a property.
    #
    # Tag numbers: 1=Boolean, 2=Unsigned, 4=Real, 7=CharString, 9=Enumerated
    _PROPERTY_TYPE_HINTS: ClassVar[dict[PropertyIdentifier, int]] = {
        PropertyIdentifier.OBJECT_NAME: 7,
        PropertyIdentifier.DESCRIPTION: 7,
        PropertyIdentifier.UNITS: 9,
        PropertyIdentifier.OUT_OF_SERVICE: 1,
        PropertyIdentifier.POLARITY: 9,
        PropertyIdentifier.COV_INCREMENT: 4,
        PropertyIdentifier.HIGH_LIMIT: 4,
        PropertyIdentifier.LOW_LIMIT: 4,
        PropertyIdentifier.DEADBAND: 4,
        PropertyIdentifier.RELINQUISH_DEFAULT: 4,
        PropertyIdentifier.MIN_PRES_VALUE: 4,
        PropertyIdentifier.MAX_PRES_VALUE: 4,
        PropertyIdentifier.RESOLUTION: 4,
        PropertyIdentifier.RELIABILITY: 9,
        PropertyIdentifier.EVENT_STATE: 9,
        PropertyIdentifier.NUMBER_OF_STATES: 2,
        PropertyIdentifier.STATE_TEXT: 7,
        PropertyIdentifier.ACTIVE_TEXT: 7,
        PropertyIdentifier.INACTIVE_TEXT: 7,
        PropertyIdentifier.NOTIFICATION_CLASS: 2,
        PropertyIdentifier.UPDATE_INTERVAL: 2,
        PropertyIdentifier.ELAPSED_ACTIVE_TIME: 2,
        PropertyIdentifier.MINIMUM_OFF_TIME: 2,
        PropertyIdentifier.MINIMUM_ON_TIME: 2,
        PropertyIdentifier.CHANGE_OF_STATE_COUNT: 2,
        PropertyIdentifier.FEEDBACK_VALUE: 9,
    }

    async def read(
        self,
        address: str | BACnetAddress,
        object_identifier: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
        property_identifier: str | int | PropertyIdentifier,
        array_index: int | None = None,
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

        Returns:
            Decoded Python value (``float``, ``int``, ``str``, ``bool``,
            etc.). Returns a ``list`` if the property contains multiple
            application-tagged values.

        Example::

            value = await client.read("192.168.1.100", "ai,1", "pv")
            name = await client.read("192.168.1.100", "ai,1", "object-name")
        """
        from bac_py.encoding.primitives import decode_all_application_values
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier, parse_property_identifier

        addr = parse_address(address)
        obj_id = parse_object_identifier(object_identifier)
        prop_id = parse_property_identifier(property_identifier)

        ack = await self.read_property(addr, obj_id, prop_id, array_index)

        if not ack.property_value:
            return None

        values = decode_all_application_values(ack.property_value)
        if len(values) == 1:
            return values[0]
        return values

    def _encode_for_write(
        self,
        value: object,
        property_identifier: PropertyIdentifier,
        object_type: ObjectType,
    ) -> bytes:
        """Encode a Python value for writing to a specific property.

        Uses object type and property identifier to select the correct
        BACnet encoding. Falls back to ``encode_property_value()`` for
        types and properties not in the hint tables.

        Encoding priority:

        1. ``None`` always encodes as Null.
        2. For ``present-value``, object-type-aware encoding is used
           (Real for analog, Enumerated for binary, Unsigned for
           multi-state).
        3. For properties in ``_PROPERTY_TYPE_HINTS``, ``int`` and
           ``float`` values are encoded according to the expected
           BACnet data type.
        4. Raw ``bytes`` pass through unchanged.
        5. All other values fall back to ``encode_property_value()``.
        """
        import enum

        from bac_py.encoding.primitives import (
            encode_application_boolean,
            encode_application_enumerated,
            encode_application_null,
            encode_application_real,
            encode_application_unsigned,
            encode_property_value,
        )

        # None -> Null (relinquish a command priority)
        if value is None:
            return encode_application_null()

        # For present-value, use object-type-aware encoding
        if property_identifier == PropertyIdentifier.PRESENT_VALUE:
            if object_type in self._ANALOG_TYPES:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return encode_application_real(float(value))
            elif object_type in self._BINARY_TYPES:
                if isinstance(value, bool):
                    return encode_application_enumerated(1 if value else 0)
                if isinstance(value, int) and not isinstance(value, enum.IntEnum):
                    return encode_application_enumerated(value)
            elif (
                object_type in self._MULTISTATE_TYPES
                and isinstance(value, int)
                and not isinstance(value, enum.IntEnum)
            ):
                return encode_application_unsigned(int(value))

        # For well-known properties, use the type hint to encode int/float correctly
        hint = self._PROPERTY_TYPE_HINTS.get(property_identifier)
        if hint is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            if hint == 4:  # Real
                return encode_application_real(float(value))
            if hint == 9:  # Enumerated
                return encode_application_enumerated(int(value))
            if hint == 2:  # Unsigned
                return encode_application_unsigned(int(value))
            if hint == 1:  # Boolean
                return encode_application_boolean(bool(value))

        # Already-encoded bytes pass through
        if isinstance(value, bytes):
            return value

        return encode_property_value(value)

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

        Example::

            await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
            await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)
            await client.write("192.168.1.100", "av,1", "pv", None, priority=8)
        """
        from bac_py.network.address import parse_address
        from bac_py.types.parsing import parse_object_identifier, parse_property_identifier

        addr = parse_address(address)
        obj_id = parse_object_identifier(object_identifier)
        prop_id = parse_property_identifier(property_identifier)

        encoded = self._encode_for_write(value, prop_id, obj_id.object_type)

        await self.write_property(addr, obj_id, prop_id, encoded, priority, array_index)

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

            Example::

                {
                    "analog-input,1": {
                        "present-value": 72.5,
                        "object-name": "Zone Temp",
                        "units": 62,
                    },
                }
        """
        from bac_py.encoding.primitives import decode_all_application_values
        from bac_py.network.address import parse_address
        from bac_py.services.read_property_multiple import PropertyReference
        from bac_py.types.parsing import parse_object_identifier, parse_property_identifier

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
                    values = decode_all_application_values(elem.property_value)
                    props[prop_name] = values[0] if len(values) == 1 else values
                else:
                    props[prop_name] = None
            result[obj_key_str] = props

        return result

    async def read_range(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
        range_qualifier: RangeByPosition | RangeBySequenceNumber | RangeByTime | None = None,
    ) -> ReadRangeACK:
        """Read a range of items from a list or array property.

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List or array property to read.
            array_index: Optional array index.
            range_qualifier: Optional range qualifier (by position,
                sequence number, or time). If None, returns all items.

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
        )
        return ReadRangeACK.decode(response_data)

    async def who_is(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
    ) -> list[IAmRequest]:
        """Discover devices via Who-Is broadcast.

        Sends a Who-Is request and collects I-Am responses for the
        specified timeout duration.

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address (default: global broadcast).
            timeout: Seconds to wait for responses.

        Returns:
            List of I-Am responses received within the timeout.
        """
        responses: list[IAmRequest] = []

        def on_i_am(service_data: bytes, source: BACnetAddress) -> None:
            try:
                iam = IAmRequest.decode(service_data)
                responses.append(iam)
            except (ValueError, IndexError):
                logger.debug("Dropped malformed I-Am from %s", source)

        # Register temporary listener for I-Am responses
        self._app.register_temporary_handler(UnconfirmedServiceChoice.I_AM, on_i_am)
        try:
            # Send Who-Is request
            request = WhoIsRequest(low_limit=low_limit, high_limit=high_limit)
            self._app.unconfirmed_request(
                destination=destination,
                service_choice=UnconfirmedServiceChoice.WHO_IS,
                service_data=request.encode(),
            )
            # Collect responses for the timeout duration
            await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(UnconfirmedServiceChoice.I_AM, on_i_am)

        return responses

    async def discover(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
    ) -> list[DiscoveredDevice]:
        """Discover devices via Who-Is and return enriched results.

        Convenience wrapper around :meth:`who_is` that captures the
        source address of each I-Am response and returns
        :class:`DiscoveredDevice` objects with parsed fields.

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address (default: global broadcast).
            timeout: Seconds to wait for responses.

        Returns:
            List of discovered devices with address and device info.

        Example::

            devices = await client.discover(timeout=3.0)
            for dev in devices:
                print(dev.instance, dev.address_str, dev.vendor_id)
        """
        devices: list[DiscoveredDevice] = []

        def on_i_am(service_data: bytes, source: BACnetAddress) -> None:
            try:
                iam = IAmRequest.decode(service_data)
                devices.append(
                    DiscoveredDevice(
                        address=source,
                        instance=iam.object_identifier.instance_number,
                        vendor_id=iam.vendor_id,
                        max_apdu_length=iam.max_apdu_length,
                        segmentation_supported=iam.segmentation_supported,
                    )
                )
            except (ValueError, IndexError):
                logger.debug("Dropped malformed I-Am from %s", source)

        self._app.register_temporary_handler(UnconfirmedServiceChoice.I_AM, on_i_am)
        try:
            request = WhoIsRequest(low_limit=low_limit, high_limit=high_limit)
            self._app.unconfirmed_request(
                destination=destination,
                service_choice=UnconfirmedServiceChoice.WHO_IS,
                service_data=request.encode(),
            )
            await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(UnconfirmedServiceChoice.I_AM, on_i_am)

        return devices

    async def subscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
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
        )

    async def unsubscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
    ) -> None:
        """Cancel a COV subscription on a remote device.

        Per Clause 13.14, omits ``issueConfirmedNotifications`` and
        ``lifetime`` to indicate cancellation.

        Args:
            address: Target device address.
            object_identifier: Object being monitored.
            process_id: Subscriber process identifier used during subscription.

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
        )

    # --- Device management ---

    async def device_communication_control(
        self,
        address: BACnetAddress,
        enable_disable: EnableDisable,
        time_duration: int | None = None,
        password: str | None = None,
    ) -> None:
        """Send DeviceCommunicationControl-Request per Clause 16.1.

        Args:
            address: Target device address.
            enable_disable: Enable/disable communication state.
            time_duration: Optional duration in minutes.
            password: Optional password string (1-20 chars).

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
        )

    async def reinitialize_device(
        self,
        address: BACnetAddress,
        reinitialized_state: ReinitializedState,
        password: str | None = None,
    ) -> None:
        """Send ReinitializeDevice-Request per Clause 16.4.

        Args:
            address: Target device address.
            reinitialized_state: Desired reinitialization state.
            password: Optional password string (1-20 chars).

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
    ) -> AtomicReadFileACK:
        """Send AtomicReadFile-Request per Clause 14.1.

        Args:
            address: Target device address.
            file_identifier: ObjectIdentifier of the File object.
            access_method: Stream or record read parameters.

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
        )
        return AtomicReadFileACK.decode(response_data)

    async def atomic_write_file(
        self,
        address: BACnetAddress,
        file_identifier: ObjectIdentifier,
        access_method: StreamWriteAccess | RecordWriteAccess,
    ) -> AtomicWriteFileACK:
        """Send AtomicWriteFile-Request per Clause 14.2.

        Args:
            address: Target device address.
            file_identifier: ObjectIdentifier of the File object.
            access_method: Stream or record write parameters.

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
        )
        return AtomicWriteFileACK.decode(response_data)

    # --- Object management ---

    async def create_object(
        self,
        address: BACnetAddress,
        object_type: ObjectType | None = None,
        object_identifier: ObjectIdentifier | None = None,
    ) -> ObjectIdentifier:
        """Send CreateObject-Request per Clause 15.3.

        Supply either ``object_type`` (server auto-assigns instance)
        or ``object_identifier`` (explicit type and instance).

        Args:
            address: Target device address.
            object_type: Object type for auto-assigned instance.
            object_identifier: Explicit object identifier.

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
    ) -> None:
        """Send DeleteObject-Request per Clause 15.4.

        Args:
            address: Target device address.
            object_identifier: Object to delete.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = DeleteObjectRequest(object_identifier=object_identifier)
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.DELETE_OBJECT,
            service_data=request.encode(),
        )

    # --- List manipulation ---

    async def add_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
    ) -> None:
        """Send AddListElement-Request per Clause 15.1.

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List property to modify.
            list_of_elements: Application-tagged encoded elements to add.
            array_index: Optional array index.

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
        )

    async def remove_list_element(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        list_of_elements: bytes,
        array_index: int | None = None,
    ) -> None:
        """Send RemoveListElement-Request per Clause 15.2.

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List property to modify.
            list_of_elements: Application-tagged encoded elements to remove.
            array_index: Optional array index.

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

        Returns:
            List of I-Have responses received within the timeout.
        """
        responses: list[IHaveRequest] = []

        def on_i_have(service_data: bytes, source: BACnetAddress) -> None:
            try:
                ihave = IHaveRequest.decode(service_data)
                responses.append(ihave)
            except (ValueError, IndexError):
                logger.debug("Dropped malformed I-Have from %s", source)

        self._app.register_temporary_handler(UnconfirmedServiceChoice.I_HAVE, on_i_have)
        try:
            request = WhoHasRequest(
                object_identifier=object_identifier,
                object_name=object_name,
                low_limit=low_limit,
                high_limit=high_limit,
            )
            self._app.unconfirmed_request(
                destination=destination,
                service_choice=UnconfirmedServiceChoice.WHO_HAS,
                service_data=request.encode(),
            )
            await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(UnconfirmedServiceChoice.I_HAVE, on_i_have)

        return responses

    # --- Private transfer ---

    async def confirmed_private_transfer(
        self,
        address: BACnetAddress,
        vendor_id: int,
        service_number: int,
        service_parameters: bytes | None = None,
    ) -> ConfirmedPrivateTransferACK:
        """Send ConfirmedPrivateTransfer-Request per Clause 16.2.

        Args:
            address: Target device address.
            vendor_id: Vendor identifier.
            service_number: Vendor-specific service number.
            service_parameters: Optional vendor-specific data.

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
