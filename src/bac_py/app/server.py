"""Default BACnet server handlers per ASHRAE 135-2016.

Provides handlers for Who-Is, ReadProperty, WriteProperty,
ReadPropertyMultiple, WritePropertyMultiple, and ReadRange that
work with the local ObjectDatabase and DeviceObject.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bac_py.app._object_type_sets import ANALOG_TYPES
from bac_py.encoding.primitives import (
    decode_and_unwrap,
    encode_application_object_id,
    encode_property_value,
)
from bac_py.network.address import GLOBAL_BROADCAST
from bac_py.objects.base import _OBJECT_REGISTRY, create_object
from bac_py.objects.file import FileObject
from bac_py.services.cov import SubscribeCOVRequest
from bac_py.services.device_mgmt import (
    DeviceCommunicationControlRequest,
    ReinitializeDeviceRequest,
    TimeSynchronizationRequest,
    UTCTimeSynchronizationRequest,
)
from bac_py.services.errors import BACnetError, BACnetRejectError
from bac_py.services.file_access import (
    AtomicReadFileACK,
    AtomicReadFileRequest,
    AtomicWriteFileACK,
    AtomicWriteFileRequest,
    RecordReadACK,
    StreamReadAccess,
    StreamReadACK,
    StreamWriteAccess,
)
from bac_py.services.list_element import AddListElementRequest, RemoveListElementRequest
from bac_py.services.object_mgmt import CreateObjectRequest, DeleteObjectRequest
from bac_py.services.read_property import ReadPropertyACK, ReadPropertyRequest
from bac_py.services.read_property_multiple import (
    PropertyReference,
    ReadAccessResult,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
    ReadResultElement,
)
from bac_py.services.read_range import (
    RangeByPosition,
    ReadRangeACK,
    ReadRangeRequest,
    ResultFlags,
)
from bac_py.services.who_has import IHaveRequest, WhoHasRequest
from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.services.write_property_multiple import WritePropertyMultipleRequest
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    RejectReason,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import BitString, ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.objects.base import BACnetObject, ObjectDatabase
    from bac_py.objects.device import DeviceObject

logger = logging.getLogger(__name__)


def _bitstring_from_bits(bit_positions: set[int]) -> BitString:
    """Build a :class:`BitString` with specified bit positions set to ``1``.

    :param bit_positions: Set of bit indices (0-based, MSB-first) to set.
    :returns: :class:`BitString` with the specified bits set.
    """
    if not bit_positions:
        return BitString(b"\x00", 0)
    max_bit = max(bit_positions)
    byte_count = (max_bit // 8) + 1
    unused_bits = (byte_count * 8) - (max_bit + 1)
    buf = bytearray(byte_count)
    for bit in bit_positions:
        byte_index = bit // 8
        bit_index = 7 - (bit % 8)
        buf[byte_index] |= 1 << bit_index
    return BitString(bytes(buf), unused_bits)


def _encode_property_value(value: Any, obj_type: ObjectType | None = None) -> bytes:
    """Encode a property value to application-tagged bytes.

    Thin wrapper around ``encode_property_value`` that converts
    ``TypeError`` to :class:`BACnetError` for the server error response path.

    :param value: The value to encode.
    :param obj_type: Optional object type. When the object is an analog type,
        integers are encoded as Real instead of Unsigned.
    """
    try:
        return encode_property_value(
            value, int_as_real=obj_type in ANALOG_TYPES if obj_type is not None else False
        )
    except TypeError:
        raise BACnetError(ErrorClass.PROPERTY, ErrorCode.OTHER) from None


class DefaultServerHandlers:
    """Standard BACnet service handlers for a server device.

    Registers handlers for ReadProperty, WriteProperty, Who-Is,
    ReadPropertyMultiple, WritePropertyMultiple, and ReadRange
    with the application's service registry.
    """

    def __init__(
        self,
        app: BACnetApplication,
        object_db: ObjectDatabase,
        device: DeviceObject,
    ) -> None:
        """Initialise default server handlers.

        :param app: The parent application (used for service registration
            and sending unconfirmed responses).
        :param object_db: Object database to serve property reads/writes from.
        :param device: The local device object (used for Who-Is matching
            and wildcard resolution).
        """
        self._app = app
        self._db = object_db
        self._device = device

    def register(self) -> None:
        """Register all default handlers with the application."""
        registry = self._app.service_registry
        registry.register_confirmed(
            ConfirmedServiceChoice.READ_PROPERTY,
            self.handle_read_property,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.WRITE_PROPERTY,
            self.handle_write_property,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE,
            self.handle_read_property_multiple,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE,
            self.handle_write_property_multiple,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.READ_RANGE,
            self.handle_read_range,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.SUBSCRIBE_COV,
            self.handle_subscribe_cov,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
            self.handle_device_communication_control,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.REINITIALIZE_DEVICE,
            self.handle_reinitialize_device,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.ATOMIC_READ_FILE,
            self.handle_atomic_read_file,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
            self.handle_atomic_write_file,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.CREATE_OBJECT,
            self.handle_create_object,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.DELETE_OBJECT,
            self.handle_delete_object,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.ADD_LIST_ELEMENT,
            self.handle_add_list_element,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
            self.handle_remove_list_element,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.WHO_IS,
            self.handle_who_is,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.WHO_HAS,
            self.handle_who_has,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.TIME_SYNCHRONIZATION,
            self.handle_time_synchronization,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION,
            self.handle_utc_time_synchronization,
        )

        # Auto-compute Protocol_Services_Supported from registered handlers
        # Per Clause 12.11.44: confirmed services at bit positions matching
        # their ConfirmedServiceChoice value (0-31), unconfirmed services
        # at bit position 32 + UnconfirmedServiceChoice value.
        service_bits: set[int] = set()
        for sc in registry._confirmed:
            service_bits.add(sc)
        for sc in registry._unconfirmed:
            service_bits.add(32 + sc)
        self._device._properties[PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED] = (
            _bitstring_from_bits(service_bits)
        )

        # Auto-compute Protocol_Object_Types_Supported from registry
        # Per Clause 12.11.43: bit position = ObjectType value.
        obj_type_bits: set[int] = set()
        for obj_type in _OBJECT_REGISTRY:
            obj_type_bits.add(int(obj_type))
        self._device._properties[PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED] = (
            _bitstring_from_bits(obj_type_bits)
        )

    async def handle_read_property(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle ReadProperty-Request per Clause 15.5.

        Decodes the request, looks up the object and property in the
        database, and returns the encoded :class:`ReadPropertyACK`.

        :returns: Encoded ReadProperty-ACK service data.
        :raises BACnetError: If the object or property is not found.
        """
        request = ReadPropertyRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        # May raise BACnetError for unknown/unsupported properties
        value = self._read_object_property(
            obj,
            request.property_identifier,
            request.property_array_index,
        )

        encoded_value = _encode_property_value(value, obj_id.object_type)

        ack = ReadPropertyACK(
            object_identifier=obj_id,
            property_identifier=request.property_identifier,
            property_array_index=request.property_array_index,
            property_value=encoded_value,
        )
        return ack.encode()

    async def handle_write_property(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle WriteProperty-Request per Clause 15.9.

        Decodes the request, looks up the object in the database,
        and writes the property value. Returns ``None`` for SimpleACK.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the object or property is not found,
            or the write is not permitted.
        """
        request = WritePropertyRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        # Decode raw application-tagged bytes to native Python types
        # before storing -- mirrors the C reference library behavior
        # where incoming values are decoded before being applied.
        try:
            write_value = decode_and_unwrap(request.property_value)
        except (ValueError, IndexError):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_DATA_TYPE) from None

        await obj.async_write_property(
            request.property_identifier,
            write_value,
            request.priority,
            request.property_array_index,
        )

        cov_manager = self._app.cov_manager
        if cov_manager is not None:
            cov_manager.check_and_notify(obj, request.property_identifier)

        return None

    async def handle_subscribe_cov(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle SubscribeCOV-Request per Clause 13.14.

        Returns ``None`` (SimpleACK) on success.

        :raises BACnetError: If the monitored object does not exist or
            COV is not supported.
        """
        request = SubscribeCOVRequest.decode(data)
        obj_id = self._resolve_object_id(request.monitored_object_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        cov_manager = self._app.cov_manager
        if cov_manager is None:
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.SERVICE_REQUEST_DENIED)

        # Per Clause 13.14.1.1.4: if Lifetime is present then
        # Issue Confirmed Notifications shall be present.
        if request.lifetime is not None and request.issue_confirmed_notifications is None:
            raise BACnetRejectError(RejectReason.MISSING_REQUIRED_PARAMETER)

        if request.is_cancellation:
            cov_manager.unsubscribe(source, request.subscriber_process_identifier, obj_id)
        else:
            cov_manager.subscribe(source, request, self._db)

        return None  # SimpleACK

    async def handle_who_is(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle Who-Is-Request per Clause 16.10.

        Checks if the local device instance is within the requested
        range and responds with an I-Am if so.
        """
        request = WhoIsRequest.decode(data)
        instance = self._device.object_identifier.instance_number

        # Check if we are in range
        if (
            request.low_limit is not None
            and request.high_limit is not None
            and not (request.low_limit <= instance <= request.high_limit)
        ):
            return

        # Send I-Am response (per Clause 16.10.2, always send to global broadcast)
        config = self._app.config
        segmentation = self._device.read_property(PropertyIdentifier.SEGMENTATION_SUPPORTED)
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, instance),
            max_apdu_length=config.max_apdu_length,
            segmentation_supported=segmentation,
            vendor_id=config.vendor_id,
        )
        self._app.unconfirmed_request(
            destination=GLOBAL_BROADCAST,
            service_choice=UnconfirmedServiceChoice.I_AM,
            service_data=iam.encode(),
        )

    def _read_object_property(
        self,
        obj: BACnetObject,
        prop_id: PropertyIdentifier,
        array_index: int | None = None,
    ) -> Any:
        """Read a property from an object, with computed property overrides.

        Intercepts OBJECT_LIST reads on the device to return the live
        database object list, and ACTIVE_COV_SUBSCRIPTIONS to return
        the current COV subscriptions from the COV manager.

        :param obj: The BACnet object to read from.
        :param prop_id: Property identifier to read.
        :param array_index: Optional array index for array properties.
        :returns: The property value (type varies by property).
        :raises BACnetError: If the property is not found or the array
            index is out of range.
        """
        if obj.object_identifier == self._device.object_identifier:
            if prop_id == PropertyIdentifier.OBJECT_LIST:
                full_list = self._db.object_list
                if array_index is not None:
                    if array_index == 0:
                        return len(full_list)
                    if 1 <= array_index <= len(full_list):
                        return full_list[array_index - 1]
                    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_ARRAY_INDEX)
                return full_list
            if prop_id == PropertyIdentifier.ACTIVE_COV_SUBSCRIPTIONS:
                cov_manager = self._app.cov_manager
                if cov_manager is None:
                    return []
                return cov_manager.get_active_subscriptions()
        return obj.read_property(prop_id, array_index)

    def _resolve_object_id(self, obj_id: ObjectIdentifier) -> ObjectIdentifier:
        """Resolve wildcard device instance ``4194303`` to the local device.

        :param obj_id: Object identifier to resolve.
        :returns: The resolved :class:`ObjectIdentifier`, substituting the
            local device identifier when a wildcard is used.
        """
        if obj_id.object_type == ObjectType.DEVICE and obj_id.instance_number == 0x3FFFFF:
            return self._device.object_identifier
        return obj_id

    def _expand_property_references(
        self,
        obj: BACnetObject,
        refs: list[PropertyReference],
    ) -> list[PropertyReference]:
        """Expand ALL/REQUIRED/OPTIONAL into concrete property references.

        Per Clause 15.7.3.2, the special property identifiers ALL, REQUIRED,
        and OPTIONAL cause the server to expand the request to include
        all/required/optional properties of the object.

        :param obj: The BACnet object whose property definitions are used.
        :param refs: List of property references, possibly containing
            special identifiers.
        :returns: Expanded list of concrete :class:`PropertyReference` instances.
        """
        result: list[PropertyReference] = []
        for ref in refs:
            if ref.property_identifier == PropertyIdentifier.ALL:
                for pid, pdef in obj.PROPERTY_DEFINITIONS.items():
                    if pid in obj._properties or pdef.required:
                        result.append(PropertyReference(pid))
                # Property_List is computed, always present
                if PropertyIdentifier.PROPERTY_LIST not in {r.property_identifier for r in result}:
                    result.append(PropertyReference(PropertyIdentifier.PROPERTY_LIST))
            elif ref.property_identifier == PropertyIdentifier.REQUIRED:
                for pid, pdef in obj.PROPERTY_DEFINITIONS.items():
                    if pdef.required:
                        result.append(PropertyReference(pid))
            elif ref.property_identifier == PropertyIdentifier.OPTIONAL:
                for pid, pdef in obj.PROPERTY_DEFINITIONS.items():
                    if not pdef.required and pid in obj._properties:
                        result.append(PropertyReference(pid))
            else:
                result.append(ref)
        return result

    async def handle_read_property_multiple(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle ReadPropertyMultiple-Request per Clause 15.7.

        Decodes the request, reads all requested properties from the
        database, and returns the encoded ReadPropertyMultiple-ACK.
        Per-property errors are embedded in the ACK (no top-level error).
        Supports ALL, REQUIRED, and OPTIONAL special property identifiers
        per Clause 15.7.3.2.

        :returns: Encoded ReadPropertyMultiple-ACK service data.
        """
        request = ReadPropertyMultipleRequest.decode(data)

        results: list[ReadAccessResult] = []
        for spec in request.list_of_read_access_specs:
            obj_id = self._resolve_object_id(spec.object_identifier)
            obj = self._db.get(obj_id)

            elements: list[ReadResultElement] = []
            # Expand ALL/REQUIRED/OPTIONAL when the object exists
            refs = (
                self._expand_property_references(obj, spec.list_of_property_references)
                if obj is not None
                else spec.list_of_property_references
            )
            for ref in refs:
                if obj is None:
                    elements.append(
                        ReadResultElement(
                            property_identifier=ref.property_identifier,
                            property_array_index=ref.property_array_index,
                            property_access_error=(
                                ErrorClass.OBJECT,
                                ErrorCode.UNKNOWN_OBJECT,
                            ),
                        )
                    )
                    continue

                try:
                    value = self._read_object_property(
                        obj,
                        ref.property_identifier,
                        ref.property_array_index,
                    )
                    encoded_value = _encode_property_value(value, obj_id.object_type)
                    elements.append(
                        ReadResultElement(
                            property_identifier=ref.property_identifier,
                            property_array_index=ref.property_array_index,
                            property_value=encoded_value,
                        )
                    )
                except BACnetError as e:
                    elements.append(
                        ReadResultElement(
                            property_identifier=ref.property_identifier,
                            property_array_index=ref.property_array_index,
                            property_access_error=(e.error_class, e.error_code),
                        )
                    )

            results.append(
                ReadAccessResult(
                    object_identifier=obj_id,
                    list_of_results=elements,
                )
            )

        ack = ReadPropertyMultipleACK(list_of_read_access_results=results)
        return ack.encode()

    async def handle_write_property_multiple(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle WritePropertyMultiple-Request per Clause 15.10.

        Uses a two-pass approach for atomicity: validates all writes
        first, then applies them. Either all writes succeed or none
        are applied.

        :returns: ``None`` (SimpleACK response) on full success.
        :raises BACnetError: On first validation or write failure.
        """
        from bac_py.objects.base import PropertyAccess

        request = WritePropertyMultipleRequest.decode(data)

        # Pass 1: Validate all writes (object existence, property access)
        validated: list[tuple[BACnetObject, list[Any]]] = []
        for spec in request.list_of_write_access_specs:
            obj_id = self._resolve_object_id(spec.object_identifier)
            obj = self._db.get(obj_id)
            if obj is None:
                raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
            for pv in spec.list_of_properties:
                prop_def = obj.PROPERTY_DEFINITIONS.get(pv.property_identifier)
                if prop_def is None:
                    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
                if prop_def.access == PropertyAccess.READ_ONLY and not (
                    pv.property_identifier == PropertyIdentifier.PRESENT_VALUE
                    and obj._properties.get(PropertyIdentifier.OUT_OF_SERVICE) is True
                ):
                    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)
            validated.append((obj, spec.list_of_properties))

        # Pass 2: Apply all writes
        for obj, properties in validated:
            for pv in properties:
                await obj.async_write_property(
                    pv.property_identifier,
                    pv.value,
                    pv.priority,
                    pv.property_array_index,
                )
                # Trigger COV notification checks after each successful write
                cov_manager = self._app.cov_manager
                if cov_manager is not None:
                    cov_manager.check_and_notify(obj, pv.property_identifier)

        return None

    async def handle_read_range(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle ReadRange-Request per Clause 15.8.

        Decodes the request, reads the list/array property, applies
        the range qualifier, and returns the encoded ReadRange-ACK.

        :returns: Encoded ReadRange-ACK service data.
        :raises BACnetError: If the object or property is not found.
        """
        request = ReadRangeRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)
        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        value = self._read_object_property(
            obj,
            request.property_identifier,
            request.property_array_index,
        )

        if not isinstance(value, list):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.PROPERTY_IS_NOT_A_LIST)

        total = len(value)
        # Apply range qualifier
        if isinstance(request.range, RangeByPosition):
            ref_idx = request.range.reference_index
            count = request.range.count
            if count >= 0:
                start = max(0, ref_idx - 1)
                end = min(total, start + count)
            else:
                end = min(total, ref_idx)
                start = max(0, end + count)
            items = value[start:end]
            is_first = start == 0
            is_last = end >= total
        else:
            # No range or unsupported range type — return all items
            items = value
            start = 0
            is_first = True
            is_last = True

        buf = bytearray()
        for item in items:
            buf.extend(_encode_property_value(item, obj_id.object_type))
        item_data = bytes(buf)

        more_items = not is_last

        ack = ReadRangeACK(
            object_identifier=obj_id,
            property_identifier=request.property_identifier,
            result_flags=ResultFlags(
                first_item=is_first,
                last_item=is_last,
                more_items=more_items,
            ),
            item_count=len(items),
            item_data=item_data,
            property_array_index=request.property_array_index,
        )
        return ack.encode()

    # --- Device management handlers ---

    def _validate_password(self, request_password: str | None) -> None:
        """Validate a request password against the configured device password.

        :raises BACnetError: If the password does not match or is unexpected.
        """
        config_password = self._app.config.password
        if config_password is not None:
            if request_password != config_password:
                raise BACnetError(ErrorClass.SECURITY, ErrorCode.PASSWORD_FAILURE)
        elif request_password is not None:
            # Device has no password configured but request includes one
            raise BACnetError(ErrorClass.SECURITY, ErrorCode.PASSWORD_FAILURE)

    async def handle_device_communication_control(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle DeviceCommunicationControl-Request per Clause 16.1.

        Sets the application DCC state and optionally starts a timer
        to auto-re-enable after the specified duration.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the password does not match (Clause 16.1.3.1).
        """
        request = DeviceCommunicationControlRequest.decode(data)

        self._validate_password(request.password)

        logger.info(
            "DeviceCommunicationControl from %s: enable_disable=%s, duration=%s",
            source,
            request.enable_disable,
            request.time_duration,
        )
        self._app.set_dcc_state(request.enable_disable, request.time_duration)
        return None

    async def handle_reinitialize_device(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle ReinitializeDevice-Request per Clause 16.4.

        Logs the reinitialize request. Does not actually restart
        the device in this implementation.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the password does not match (Clause 16.4.3.4).
        """
        request = ReinitializeDeviceRequest.decode(data)

        self._validate_password(request.password)

        logger.info(
            "ReinitializeDevice from %s: state=%s",
            source,
            request.reinitialized_state,
        )
        return None

    async def handle_time_synchronization(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle TimeSynchronization-Request per Clause 16.7.

        Logs the received time. Does not update the local clock.
        """
        request = TimeSynchronizationRequest.decode(data)
        logger.info(
            "TimeSynchronization from %s: date=%s, time=%s",
            source,
            request.date,
            request.time,
        )

    async def handle_utc_time_synchronization(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle UTCTimeSynchronization-Request per Clause 16.8.

        Logs the received UTC time. Does not update the local clock.
        """
        request = UTCTimeSynchronizationRequest.decode(data)
        logger.info(
            "UTCTimeSynchronization from %s: date=%s, time=%s",
            source,
            request.date,
            request.time,
        )

    # --- File access handlers ---

    async def handle_atomic_read_file(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle AtomicReadFile-Request per Clause 14.1.

        :returns: Encoded AtomicReadFile-ACK service data.
        :raises BACnetError: If the object is not found or is not a
            :class:`FileObject`.
        """
        request = AtomicReadFileRequest.decode(data)
        obj_id = self._resolve_object_id(request.file_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if not isinstance(obj, FileObject):
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.INCONSISTENT_OBJECT_TYPE)

        if isinstance(request.access_method, StreamReadAccess):
            file_data, eof = obj.read_stream(
                request.access_method.file_start_position,
                request.access_method.requested_octet_count,
            )
            ack = AtomicReadFileACK(
                end_of_file=eof,
                access_method=StreamReadACK(
                    file_start_position=request.access_method.file_start_position,
                    file_data=file_data,
                ),
            )
        else:
            records, eof = obj.read_records(
                request.access_method.file_start_record,
                request.access_method.requested_record_count,
            )
            ack = AtomicReadFileACK(
                end_of_file=eof,
                access_method=RecordReadACK(
                    file_start_record=request.access_method.file_start_record,
                    returned_record_count=len(records),
                    file_record_data=records,
                ),
            )
        return ack.encode()

    async def handle_atomic_write_file(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle AtomicWriteFile-Request per Clause 14.2.

        :returns: Encoded AtomicWriteFile-ACK service data.
        :raises BACnetError: If the object is not found or is not a
            :class:`FileObject`.
        """
        request = AtomicWriteFileRequest.decode(data)
        obj_id = self._resolve_object_id(request.file_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if not isinstance(obj, FileObject):
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.INCONSISTENT_OBJECT_TYPE)

        if isinstance(request.access_method, StreamWriteAccess):
            actual_start = obj.write_stream(
                request.access_method.file_start_position,
                request.access_method.file_data,
            )
            ack = AtomicWriteFileACK(is_stream=True, file_start=actual_start)
        else:
            actual_start = obj.write_records(
                request.access_method.file_start_record,
                request.access_method.file_record_data,
            )
            ack = AtomicWriteFileACK(is_stream=False, file_start=actual_start)
        return ack.encode()

    # --- Object management handlers ---

    async def handle_create_object(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle CreateObject-Request per Clause 15.3.

        Creates a new object in the database and returns the
        encoded object identifier.

        :returns: Encoded APPLICATION-tagged :class:`ObjectIdentifier`.
        :raises BACnetError: If the object type is unsupported or the
            object identifier already exists.
        """
        request = CreateObjectRequest.decode(data)

        if request.object_identifier is not None:
            obj_type = request.object_identifier.object_type
            instance = request.object_identifier.instance_number
        elif request.object_type is not None:
            obj_type = request.object_type
            # Auto-assign instance number by finding max + 1
            existing = self._db.get_objects_of_type(obj_type)
            if existing:
                instance = max(o.object_identifier.instance_number for o in existing) + 1
            else:
                instance = 1
        else:
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.MISSING_REQUIRED_PARAMETER)

        kwargs: dict[str, Any] = {}
        if request.list_of_initial_values:
            for pv in request.list_of_initial_values:
                prop_name = pv.property_identifier.name.lower()
                kwargs[prop_name] = decode_and_unwrap(pv.value)

        obj = create_object(obj_type, instance, **kwargs)
        self._db.add(obj)

        return encode_application_object_id(obj_type, instance)

    async def handle_delete_object(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle DeleteObject-Request per Clause 15.4.

        Removes the object from the database.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the object does not exist or is a Device object.
        """
        request = DeleteObjectRequest.decode(data)
        obj_id = self._resolve_object_id(request.object_identifier)
        self._db.remove(obj_id)

        cov_manager = self._app.cov_manager
        if cov_manager is not None:
            cov_manager.remove_object_subscriptions(obj_id)

        return None

    async def handle_add_list_element(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle AddListElement-Request per Clause 15.1.

        :raises BACnetError: If the object or property is not found,
            or list manipulation is not supported.
        """
        request = AddListElementRequest.decode(data)
        obj_id = self._resolve_object_id(request.object_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        prop_def = obj.PROPERTY_DEFINITIONS.get(request.property_identifier)
        if prop_def is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        raise BACnetError(ErrorClass.SERVICES, ErrorCode.OPTIONAL_FUNCTIONALITY_NOT_SUPPORTED)

    async def handle_remove_list_element(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle RemoveListElement-Request per Clause 15.2.

        :raises BACnetError: If the object or property is not found,
            or list manipulation is not supported.
        """
        request = RemoveListElementRequest.decode(data)
        obj_id = self._resolve_object_id(request.object_identifier)

        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        prop_def = obj.PROPERTY_DEFINITIONS.get(request.property_identifier)
        if prop_def is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        raise BACnetError(ErrorClass.SERVICES, ErrorCode.OPTIONAL_FUNCTIONALITY_NOT_SUPPORTED)

    # --- Discovery handlers ---

    async def handle_who_has(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle Who-Has-Request per Clause 16.9.

        Searches the local object database for a matching object
        and responds with I-Have if found.
        """
        request = WhoHasRequest.decode(data)
        instance = self._device.object_identifier.instance_number

        # Check if we are in the requested device instance range
        if (
            request.low_limit is not None
            and request.high_limit is not None
            and not (request.low_limit <= instance <= request.high_limit)
        ):
            return

        found_obj = None
        if request.object_identifier is not None:
            found_obj = self._db.get(request.object_identifier)
        elif request.object_name is not None:
            for obj_id in self._db.object_list:
                obj = self._db.get(obj_id)
                if obj is not None:
                    try:
                        name = obj.read_property(PropertyIdentifier.OBJECT_NAME)
                        if name == request.object_name:
                            found_obj = obj
                            break
                    except BACnetError:
                        continue

        if found_obj is None:
            return

        # Send I-Have response (per Clause 16.9.2, always broadcast)
        obj_name = found_obj.read_property(PropertyIdentifier.OBJECT_NAME)
        ihave = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, instance),
            object_identifier=found_obj.object_identifier,
            object_name=obj_name,
        )
        self._app.unconfirmed_request(
            destination=GLOBAL_BROADCAST,
            service_choice=UnconfirmedServiceChoice.I_HAVE,
            service_data=ihave.encode(),
        )
