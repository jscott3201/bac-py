"""Default BACnet server handlers per ASHRAE 135-2016.

Provides handlers for Who-Is, ReadProperty, WriteProperty,
ReadPropertyMultiple, WritePropertyMultiple, and ReadRange that
work with the local ObjectDatabase and DeviceObject.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bac_py.encoding.primitives import (
    encode_application_object_id,
    encode_property_value,
)
from bac_py.network.address import GLOBAL_BROADCAST
from bac_py.objects.base import create_object
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
from bac_py.types.primitives import ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.objects.base import BACnetObject, ObjectDatabase
    from bac_py.objects.device import DeviceObject

logger = logging.getLogger(__name__)


def _encode_property_value(value: Any) -> bytes:
    """Encode a property value to application-tagged bytes.

    Thin wrapper around ``encode_property_value`` that converts
    TypeError to BACnetError for the server error response path.
    """
    try:
        return encode_property_value(value)
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

        Args:
            app: The parent application (used for service registration
                and sending unconfirmed responses).
            object_db: Object database to serve property reads/writes from.
            device: The local device object (used for Who-Is matching
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

    async def handle_read_property(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle ReadProperty-Request per Clause 15.5.

        Decodes the request, looks up the object and property in the
        database, and returns the encoded ReadPropertyACK.

        Returns:
            Encoded ReadProperty-ACK service data.

        Raises:
            BACnetError: If the object or property is not found.
        """
        request = ReadPropertyRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)

        # Look up the object
        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        # Read the property value (may raise BACnetError)
        value = self._read_object_property(
            obj,
            request.property_identifier,
            request.property_array_index,
        )

        # Encode the value to application-tagged bytes
        encoded_value = _encode_property_value(value)

        # Build and encode the ACK
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
        and writes the property value. Returns None for SimpleACK.

        Returns:
            None (SimpleACK response).

        Raises:
            BACnetError: If the object or property is not found,
                or the write is not permitted.
        """
        request = WritePropertyRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)

        # Look up the object
        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        # Write the property value (may raise BACnetError)
        # The raw application-tagged bytes are stored directly;
        # decoding to native types is the responsibility of extended handlers.
        await obj.async_write_property(
            request.property_identifier,
            request.property_value,
            request.priority,
            request.property_array_index,
        )

        # Trigger COV notification checks after successful write
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

        Returns None (SimpleACK) on success.

        Raises:
            BACnetError: If the monitored object does not exist or
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
        """Read a property from an object, with OBJECT_LIST override.

        The device's OBJECT_LIST property should reflect all objects in
        the database, not just the static list stored on the object.
        This method intercepts OBJECT_LIST reads on the device and
        returns the database's live object list instead.
        """
        if (
            prop_id == PropertyIdentifier.OBJECT_LIST
            and obj.object_identifier == self._device.object_identifier
        ):
            full_list = self._db.object_list
            if array_index is not None:
                if array_index == 0:
                    return len(full_list)
                if 1 <= array_index <= len(full_list):
                    return full_list[array_index - 1]
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_ARRAY_INDEX)
            return full_list
        return obj.read_property(prop_id, array_index)

    def _resolve_object_id(self, obj_id: ObjectIdentifier) -> ObjectIdentifier:
        """Resolve wildcard device instance 4194303 to local device."""
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

        Returns:
            Encoded ReadPropertyMultiple-ACK service data.
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
                    encoded_value = _encode_property_value(value)
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

        Decodes the request and writes all properties in order.
        Stops at the first error and returns a BACnet error.

        Returns:
            None (SimpleACK response) on full success.

        Raises:
            BACnetError: On first write failure.
        """
        request = WritePropertyMultipleRequest.decode(data)

        for spec in request.list_of_write_access_specs:
            obj_id = self._resolve_object_id(spec.object_identifier)
            obj = self._db.get(obj_id)
            if obj is None:
                raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

            for pv in spec.list_of_properties:
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

        Returns:
            Encoded ReadRange-ACK service data.

        Raises:
            BACnetError: If the object or property is not found.
        """
        request = ReadRangeRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)
        obj = self._db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        # Read the full property value
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

        # Encode items
        buf = bytearray()
        for item in items:
            buf.extend(_encode_property_value(item))
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

    async def handle_device_communication_control(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle DeviceCommunicationControl-Request per Clause 16.1.

        Logs the communication control state change. Does not actually
        disable communication in this implementation.

        Returns:
            None (SimpleACK response).
        """
        request = DeviceCommunicationControlRequest.decode(data)
        logger.info(
            "DeviceCommunicationControl from %s: enable_disable=%s, duration=%s",
            source,
            request.enable_disable,
            request.time_duration,
        )
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

        Returns:
            None (SimpleACK response).
        """
        request = ReinitializeDeviceRequest.decode(data)
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

        Returns:
            Encoded AtomicReadFile-ACK service data.

        Raises:
            BACnetError: If the object is not found or is not a File object.
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

        Returns:
            Encoded AtomicWriteFile-ACK service data.

        Raises:
            BACnetError: If the object is not found or is not a File object.
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

        Returns:
            Encoded APPLICATION-tagged ObjectIdentifier.

        Raises:
            BACnetError: If the object type is unsupported or the
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

        # Build initial properties from the request
        kwargs: dict[str, Any] = {}
        if request.list_of_initial_values:
            for pv in request.list_of_initial_values:
                prop_name = pv.property_identifier.name.lower()
                kwargs[prop_name] = pv.value

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

        Returns:
            None (SimpleACK response).

        Raises:
            BACnetError: If the object doesn't exist or is a Device object.
        """
        request = DeleteObjectRequest.decode(data)
        obj_id = self._resolve_object_id(request.object_identifier)
        self._db.remove(obj_id)
        return None

    async def handle_add_list_element(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle AddListElement-Request per Clause 15.1.

        Raises:
            BACnetError: If the object or property is not found,
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

        Raises:
            BACnetError: If the object or property is not found,
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

        # Search for the object
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

        # Send I-Have response
        obj_name = found_obj.read_property(PropertyIdentifier.OBJECT_NAME)
        ihave = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, instance),
            object_identifier=found_obj.object_identifier,
            object_name=obj_name,
        )
        self._app.unconfirmed_request(
            destination=source,
            service_choice=UnconfirmedServiceChoice.I_HAVE,
            service_data=ihave.encode(),
        )
