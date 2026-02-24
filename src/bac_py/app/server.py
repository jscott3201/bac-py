"""Default BACnet server handlers per ASHRAE 135-2016.

Provides handlers for Who-Is, ReadProperty, WriteProperty,
ReadPropertyMultiple, WritePropertyMultiple, and ReadRange that
work with the local ObjectDatabase and DeviceObject.
"""

from __future__ import annotations

import contextlib
import hmac
import logging
from typing import TYPE_CHECKING, Any

from bac_py.app._object_type_sets import ANALOG_TYPES
from bac_py.app.audit import AuditManager
from bac_py.encoding.primitives import (
    decode_all_application_values,
    decode_and_unwrap,
    encode_application_object_id,
    encode_property_value,
)
from bac_py.network.address import GLOBAL_BROADCAST
from bac_py.objects.base import _OBJECT_REGISTRY, create_object
from bac_py.objects.file import FileObject
from bac_py.services.alarm_summary import (
    AlarmSummary,
    EnrollmentSummary,
    EventSummary,
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
    COVNotificationMultipleRequest,
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
from bac_py.services.errors import BACnetError, BACnetRejectError
from bac_py.services.event_notification import (
    AcknowledgeAlarmRequest,
    EventNotificationRequest,
)
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
from bac_py.services.write_group import WriteGroupRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.services.write_property_multiple import WritePropertyMultipleRequest
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    AcknowledgmentFilter,
    AuditOperation,
    BackupAndRestoreState,
    ConfirmedServiceChoice,
    DeviceStatus,
    ErrorClass,
    ErrorCode,
    EventState,
    EventType,
    NotifyType,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
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
        self._audit_manager = AuditManager(object_db)

    def register(self) -> None:
        """Register all default handlers with the application."""
        registry = self._app.service_registry
        logger.debug("registering default server handlers")
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
        registry.register_confirmed(
            ConfirmedServiceChoice.ACKNOWLEDGE_ALARM,
            self.handle_acknowledge_alarm,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION,
            self.handle_confirmed_event_notification,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.GET_ALARM_SUMMARY,
            self.handle_get_alarm_summary,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.GET_ENROLLMENT_SUMMARY,
            self.handle_get_enrollment_summary,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.GET_EVENT_INFORMATION,
            self.handle_get_event_information,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.UNCONFIRMED_EVENT_NOTIFICATION,
            self.handle_unconfirmed_event_notification,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY,
            self.handle_subscribe_cov_property,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY_MULTIPLE,
            self.handle_subscribe_cov_property_multiple,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION_MULTIPLE,
            self.handle_confirmed_cov_notification_multiple,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION_MULTIPLE,
            self.handle_unconfirmed_cov_notification_multiple,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
            self.handle_confirmed_text_message,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE,
            self.handle_unconfirmed_text_message,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.WRITE_GROUP,
            self.handle_write_group,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.WHO_AM_I,
            self.handle_who_am_i,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.YOU_ARE,
            self.handle_you_are,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.VT_OPEN,
            self.handle_vt_open,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.VT_CLOSE,
            self.handle_vt_close,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.VT_DATA,
            self.handle_vt_data,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.AUDIT_LOG_QUERY,
            self.handle_audit_log_query,
        )
        registry.register_confirmed(
            ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
            self.handle_confirmed_audit_notification,
        )
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION,
            self.handle_unconfirmed_audit_notification,
        )

        logger.debug(
            "registered %d confirmed and %d unconfirmed handlers",
            len(registry._confirmed),
            len(registry._unconfirmed),
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

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        :returns: Encoded ReadProperty-ACK service data.
        :raises BACnetError: If the object or property is not found.
        """
        request = ReadPropertyRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)
        logger.debug(
            "handling read_property %s %s from %s",
            obj_id,
            request.property_identifier.name,
            source,
        )

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("read_property: unknown object %s from %s", obj_id, source)
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
        and writes the property value.  Returns ``None`` for SimpleACK.

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the object or property is not found,
            or the write is not permitted.
        """
        request = WritePropertyRequest.decode(data)

        obj_id = self._resolve_object_id(request.object_identifier)
        logger.debug(
            "handling write_property %s %s from %s",
            obj_id,
            request.property_identifier.name,
            source,
        )

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("write_property: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        # Decode raw application-tagged bytes to native Python types
        # before storing -- mirrors the C reference library behavior
        # where incoming values are decoded before being applied.
        try:
            write_value = decode_and_unwrap(request.property_value)
        except (ValueError, IndexError):
            logger.warning(
                "write_property: invalid data type for %s %s from %s",
                obj_id,
                request.property_identifier.name,
                source,
            )
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

        self._audit_manager.record_operation(
            operation=AuditOperation.WRITE,
            target_object=obj_id,
            target_property=request.property_identifier,
            target_array_index=request.property_array_index,
            target_priority=request.priority,
            target_value=request.property_value,
        )

        return None

    async def handle_subscribe_cov(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle SubscribeCOV-Request per Clause 13.14.

        Returns ``None`` (SimpleACK) on success.

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        :raises BACnetError: If the monitored object does not exist or
            COV is not supported.
        """
        request = SubscribeCOVRequest.decode(data)
        obj_id = self._resolve_object_id(request.monitored_object_identifier)
        logger.debug("handling subscribe_cov %s from %s", obj_id, source)

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("subscribe_cov: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        cov_manager = self._app.cov_manager
        if cov_manager is None:
            logger.warning("subscribe_cov: COV not supported, denied request from %s", source)
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

    async def handle_subscribe_cov_property(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle SubscribeCOVProperty-Request per Clause 13.15.

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        """
        request = SubscribeCOVPropertyRequest.decode(data)
        obj_id = self._resolve_object_id(request.monitored_object_identifier)
        logger.debug("handling subscribe_cov_property %s from %s", obj_id, source)
        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("subscribe_cov_property: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        cov_manager = self._app.cov_manager
        if cov_manager is None:
            logger.warning(
                "subscribe_cov_property: COV not supported, denied request from %s",
                source,
            )
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.SERVICE_REQUEST_DENIED)
        cov_manager.subscribe_property(source, request, self._db)
        return None  # SimpleACK

    async def handle_subscribe_cov_property_multiple(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle SubscribeCOVPropertyMultiple-Request per Clause 13.16.

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        """
        request = SubscribeCOVPropertyMultipleRequest.decode(data)
        logger.debug("handling subscribe_cov_property_multiple from %s", source)
        cov_manager = self._app.cov_manager
        if cov_manager is None:
            logger.warning(
                "subscribe_cov_property_multiple: COV not supported, denied request from %s",
                source,
            )
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.SERVICE_REQUEST_DENIED)
        cov_manager.subscribe_property_multiple(source, request, self._db)
        return None  # SimpleACK

    async def handle_confirmed_cov_notification_multiple(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle ConfirmedCOVNotification-Multiple per Clause 13.17.

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        """
        request = COVNotificationMultipleRequest.decode(data)
        logger.debug(
            "ConfirmedCOVNotification-Multiple from %s: %d notifications",
            source,
            len(request.list_of_cov_notifications),
        )
        return None  # SimpleACK

    async def handle_unconfirmed_cov_notification_multiple(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle UnconfirmedCOVNotification-Multiple per Clause 13.18.

        :param service_choice: Unconfirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the sending device.
        """
        request = COVNotificationMultipleRequest.decode(data)
        logger.debug(
            "UnconfirmedCOVNotification-Multiple from %s: %d notifications",
            source,
            len(request.list_of_cov_notifications),
        )

    async def handle_who_is(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle Who-Is-Request per Clause 16.10.

        Checks if the local device instance is within the requested
        range and responds with an I-Am if so.

        :param service_choice: Unconfirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        """
        request = WhoIsRequest.decode(data)
        logger.debug(
            "handling who_is low=%s high=%s from %s",
            request.low_limit,
            request.high_limit,
            source,
        )
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
        if obj is self._device:
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
                if not any(
                    r.property_identifier == PropertyIdentifier.PROPERTY_LIST for r in result
                ):
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

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        :returns: Encoded ReadPropertyMultiple-ACK service data.
        """
        request = ReadPropertyMultipleRequest.decode(data)
        logger.debug(
            "handling read_property_multiple (%d specs) from %s",
            len(request.list_of_read_access_specs),
            source,
        )

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

        :param service_choice: Confirmed service choice code.
        :param data: Raw service request bytes.
        :param source: Address of the requesting device.
        :returns: ``None`` (SimpleACK response) on full success.
        :raises BACnetError: On first validation or write failure.
        """
        from bac_py.objects.base import PropertyAccess

        request = WritePropertyMultipleRequest.decode(data)
        logger.debug(
            "handling write_property_multiple (%d specs) from %s",
            len(request.list_of_write_access_specs),
            source,
        )

        # Pass 1: Validate all writes (object existence, property access)
        validated: list[tuple[BACnetObject, list[Any]]] = []
        for spec in request.list_of_write_access_specs:
            obj_id = self._resolve_object_id(spec.object_identifier)
            obj = self._db.get(obj_id)
            if obj is None:
                logger.warning(
                    "write_property_multiple: unknown object %s from %s", obj_id, source
                )
                raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
            for pv in spec.list_of_properties:
                prop_def = obj.PROPERTY_DEFINITIONS.get(pv.property_identifier)
                if prop_def is None:
                    logger.warning(
                        "write_property_multiple: unknown property %s on %s from %s",
                        pv.property_identifier.name,
                        obj_id,
                        source,
                    )
                    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
                if prop_def.access == PropertyAccess.READ_ONLY and not (
                    pv.property_identifier == PropertyIdentifier.PRESENT_VALUE
                    and obj._properties.get(PropertyIdentifier.OUT_OF_SERVICE) is True
                ):
                    logger.warning(
                        "write_property_multiple: write access denied for %s on %s from %s",
                        pv.property_identifier.name,
                        obj_id,
                        source,
                    )
                    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)
            validated.append((obj, spec.list_of_properties))

        # Pass 2: Apply all writes
        for obj, properties in validated:
            for pv in properties:
                try:
                    write_value = decode_and_unwrap(pv.value)
                except (ValueError, IndexError):
                    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.INVALID_DATA_TYPE) from None
                await obj.async_write_property(
                    pv.property_identifier,
                    write_value,
                    pv.priority,
                    pv.property_array_index,
                )
                # Trigger COV notification checks after each successful write
                cov_manager = self._app.cov_manager
                if cov_manager is not None:
                    cov_manager.check_and_notify(obj, pv.property_identifier)

                self._audit_manager.record_operation(
                    operation=AuditOperation.WRITE,
                    target_object=obj.object_identifier,
                    target_property=pv.property_identifier,
                    target_array_index=pv.property_array_index,
                    target_priority=pv.priority,
                )

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
        logger.debug(
            "handling read_range %s %s from %s",
            obj_id,
            request.property_identifier.name,
            source,
        )
        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("read_range: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        value = self._read_object_property(
            obj,
            request.property_identifier,
            request.property_array_index,
        )

        if not isinstance(value, list):
            logger.warning(
                "read_range: property %s on %s is not a list",
                request.property_identifier.name,
                obj_id,
            )
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

        Uses constant-time comparison (``hmac.compare_digest``) to prevent
        timing-based password extraction attacks.

        :raises BACnetError: If the password does not match or is unexpected.
        """
        config_password = self._app.config.password
        if config_password is not None:
            if request_password is None or not hmac.compare_digest(
                request_password.encode("utf-8"),
                config_password.encode("utf-8"),
            ):
                logger.warning("password validation failed: incorrect password")
                raise BACnetError(ErrorClass.SECURITY, ErrorCode.PASSWORD_FAILURE)
        elif request_password is not None:
            # Device has no password configured but request includes one
            logger.warning("password validation failed: unexpected password provided")
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
        """Handle ReinitializeDevice-Request per Clause 16.4 & 19.1.

        Manages backup/restore state transitions on the Device object
        per Clause 19.1:

        - ``START_BACKUP`` → ``system_status=BACKUP_IN_PROGRESS``
        - ``END_BACKUP`` → ``system_status=OPERATIONAL``
        - ``START_RESTORE`` → ``system_status=DOWNLOAD_IN_PROGRESS``
        - ``END_RESTORE`` → ``system_status=OPERATIONAL``
        - ``ABORT_RESTORE`` → ``system_status=OPERATIONAL``

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the password does not match or the
            state transition is invalid.
        """
        request = ReinitializeDeviceRequest.decode(data)

        self._validate_password(request.password)

        device = self._device
        state = request.reinitialized_state

        if state in (
            ReinitializedState.START_BACKUP,
            ReinitializedState.END_BACKUP,
            ReinitializedState.START_RESTORE,
            ReinitializedState.END_RESTORE,
            ReinitializedState.ABORT_RESTORE,
        ):
            br_state = device._properties.get(
                PropertyIdentifier.BACKUP_AND_RESTORE_STATE,
                BackupAndRestoreState.IDLE,
            )

            if state == ReinitializedState.START_BACKUP:
                if br_state != BackupAndRestoreState.IDLE:
                    raise BACnetError(ErrorClass.DEVICE, ErrorCode.OTHER)
                device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
                    DeviceStatus.BACKUP_IN_PROGRESS
                )
                device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
                    BackupAndRestoreState.PREPARING_FOR_BACKUP
                )

            elif state == ReinitializedState.END_BACKUP:
                if br_state not in (
                    BackupAndRestoreState.PREPARING_FOR_BACKUP,
                    BackupAndRestoreState.PERFORMING_A_BACKUP,
                ):
                    raise BACnetError(ErrorClass.DEVICE, ErrorCode.OTHER)
                device._properties[PropertyIdentifier.SYSTEM_STATUS] = DeviceStatus.OPERATIONAL
                device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
                    BackupAndRestoreState.IDLE
                )

            elif state == ReinitializedState.START_RESTORE:
                if br_state != BackupAndRestoreState.IDLE:
                    raise BACnetError(ErrorClass.DEVICE, ErrorCode.OTHER)
                device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
                    DeviceStatus.DOWNLOAD_IN_PROGRESS
                )
                device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
                    BackupAndRestoreState.PREPARING_FOR_RESTORE
                )

            elif state == ReinitializedState.END_RESTORE:
                if br_state not in (
                    BackupAndRestoreState.PREPARING_FOR_RESTORE,
                    BackupAndRestoreState.PERFORMING_A_RESTORE,
                ):
                    raise BACnetError(ErrorClass.DEVICE, ErrorCode.OTHER)
                device._properties[PropertyIdentifier.SYSTEM_STATUS] = DeviceStatus.OPERATIONAL
                device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
                    BackupAndRestoreState.IDLE
                )
                device._properties[PropertyIdentifier.LAST_RESTORE_TIME] = BACnetTimeStamp(
                    choice=1, value=0
                )

            elif state == ReinitializedState.ABORT_RESTORE:
                if br_state not in (
                    BackupAndRestoreState.PREPARING_FOR_RESTORE,
                    BackupAndRestoreState.PERFORMING_A_RESTORE,
                ):
                    raise BACnetError(ErrorClass.DEVICE, ErrorCode.OTHER)
                device._properties[PropertyIdentifier.SYSTEM_STATUS] = DeviceStatus.OPERATIONAL
                device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
                    BackupAndRestoreState.IDLE
                )

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
        logger.debug("handling atomic_read_file %s from %s", obj_id, source)

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("atomic_read_file: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if not isinstance(obj, FileObject):
            logger.warning(
                "atomic_read_file: object %s is not a FileObject from %s", obj_id, source
            )
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
        logger.debug("handling atomic_write_file %s from %s", obj_id, source)

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("atomic_write_file: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if not isinstance(obj, FileObject):
            logger.warning(
                "atomic_write_file: object %s is not a FileObject from %s", obj_id, source
            )
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
        logger.debug(
            "handling create_object type=%s id=%s from %s",
            request.object_type,
            request.object_identifier,
            source,
        )

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
            logger.warning("create_object: missing required parameter from %s", source)
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.MISSING_REQUIRED_PARAMETER)

        kwargs: dict[str, Any] = {}
        if request.list_of_initial_values:
            for pv in request.list_of_initial_values:
                prop_name = pv.property_identifier.name.lower()
                kwargs[prop_name] = decode_and_unwrap(pv.value)

        obj = create_object(obj_type, instance, **kwargs)
        self._db.add(obj)

        self._audit_manager.record_operation(
            operation=AuditOperation.CREATE,
            target_object=obj.object_identifier,
        )

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
        logger.debug("handling delete_object %s from %s", obj_id, source)
        self._db.remove(obj_id)

        cov_manager = self._app.cov_manager
        if cov_manager is not None:
            cov_manager.remove_object_subscriptions(obj_id)

        self._audit_manager.record_operation(
            operation=AuditOperation.DELETE,
            target_object=obj_id,
        )

        return None

    async def handle_add_list_element(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle AddListElement-Request per Clause 15.1.

        Decodes the elements from the request, validates that the target
        property is a list, checks write access, and extends the list.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the object or property is not found,
            or the property is not a list or is read-only.
        """
        from bac_py.objects.base import PropertyAccess

        request = AddListElementRequest.decode(data)
        obj_id = self._resolve_object_id(request.object_identifier)
        logger.debug(
            "handling add_list_element %s %s from %s",
            obj_id,
            request.property_identifier.name,
            source,
        )

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("add_list_element: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        prop_def = obj.PROPERTY_DEFINITIONS.get(request.property_identifier)
        if prop_def is None:
            logger.warning(
                "add_list_element: unknown property %s on %s from %s",
                request.property_identifier.name,
                obj_id,
                source,
            )
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        if prop_def.access == PropertyAccess.READ_ONLY:
            logger.warning(
                "add_list_element: write access denied for %s on %s from %s",
                request.property_identifier.name,
                obj_id,
                source,
            )
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        current = obj._properties.get(request.property_identifier)
        if not isinstance(current, list):
            if current is None and prop_def.datatype is list:
                current = []
                obj._properties[request.property_identifier] = current
            else:
                logger.warning(
                    "add_list_element: property %s on %s is not a list",
                    request.property_identifier.name,
                    obj_id,
                )
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.PROPERTY_IS_NOT_A_LIST)

        new_elements = decode_all_application_values(request.list_of_elements)
        current.extend(new_elements)
        return None

    async def handle_remove_list_element(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle RemoveListElement-Request per Clause 15.2.

        Decodes the elements from the request, validates that the target
        property is a list, checks write access, and removes matching entries.
        Non-matching elements are silently ignored per the standard.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the object or property is not found,
            or the property is not a list or is read-only.
        """
        from bac_py.objects.base import PropertyAccess

        request = RemoveListElementRequest.decode(data)
        obj_id = self._resolve_object_id(request.object_identifier)
        logger.debug(
            "handling remove_list_element %s %s from %s",
            obj_id,
            request.property_identifier.name,
            source,
        )

        obj = self._db.get(obj_id)
        if obj is None:
            logger.warning("remove_list_element: unknown object %s from %s", obj_id, source)
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        prop_def = obj.PROPERTY_DEFINITIONS.get(request.property_identifier)
        if prop_def is None:
            logger.warning(
                "remove_list_element: unknown property %s on %s from %s",
                request.property_identifier.name,
                obj_id,
                source,
            )
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        if prop_def.access == PropertyAccess.READ_ONLY:
            logger.warning(
                "remove_list_element: write access denied for %s on %s from %s",
                request.property_identifier.name,
                obj_id,
                source,
            )
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        current = obj._properties.get(request.property_identifier)
        if not isinstance(current, list):
            logger.warning(
                "remove_list_element: property %s on %s is not a list",
                request.property_identifier.name,
                obj_id,
            )
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.PROPERTY_IS_NOT_A_LIST)

        elements_to_remove = decode_all_application_values(request.list_of_elements)
        for elem in elements_to_remove:
            with contextlib.suppress(ValueError):
                current.remove(elem)
        return None

    # --- Alarm / event handlers ---

    async def handle_acknowledge_alarm(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle AcknowledgeAlarm-Request per Clause 13.5.

        Updates the acked_transitions property on the target object
        to mark the appropriate transition as acknowledged.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If the target object does not exist.
        """
        request = AcknowledgeAlarmRequest.decode(data)
        logger.debug(
            "handling acknowledge_alarm %s state=%s from %s",
            request.event_object_identifier,
            request.event_state_acknowledged.name,
            source,
        )

        obj = self._db.get(request.event_object_identifier)
        if obj is None:
            logger.warning(
                "acknowledge_alarm: unknown object %s from %s",
                request.event_object_identifier,
                source,
            )
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        acked_transitions = obj._properties.get(PropertyIdentifier.ACKED_TRANSITIONS)
        if isinstance(acked_transitions, list) and len(acked_transitions) >= 3:
            if request.event_state_acknowledged == EventState.FAULT:
                idx = 1
            elif request.event_state_acknowledged == EventState.NORMAL:
                idx = 2
            else:
                idx = 0
            acked_transitions[idx] = True

        return None

    async def handle_confirmed_event_notification(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle ConfirmedEventNotification-Request per Clause 13.8.

        Logs the notification at debug level.

        :returns: ``None`` (SimpleACK response).
        """
        request = EventNotificationRequest.decode(data)
        logger.debug(
            "ConfirmedEventNotification from %s: object=%s, toState=%s",
            source,
            request.event_object_identifier,
            request.to_state,
        )
        return None

    async def handle_unconfirmed_event_notification(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle UnconfirmedEventNotification-Request per Clause 13.9.

        Logs the notification at debug level.
        """
        request = EventNotificationRequest.decode(data)
        logger.debug(
            "UnconfirmedEventNotification from %s: object=%s, toState=%s",
            source,
            request.event_object_identifier,
            request.to_state,
        )

    async def handle_get_alarm_summary(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle GetAlarmSummary-Request per Clause 13.6.

        Scans all objects in the database for those in an alarm
        (non-NORMAL) event state and returns their summaries.

        :returns: Encoded GetAlarmSummary-ACK service data.
        """
        GetAlarmSummaryRequest.decode(data)
        logger.debug("handling get_alarm_summary from %s", source)

        summaries: list[AlarmSummary] = []
        for obj in self._db.values():
            event_state_val = obj._properties.get(PropertyIdentifier.EVENT_STATE)
            if event_state_val is None:
                continue
            if not isinstance(event_state_val, EventState):
                try:
                    event_state_val = EventState(event_state_val)
                except (ValueError, TypeError):
                    continue
            if event_state_val == EventState.NORMAL:
                continue

            acked_raw = obj._properties.get(PropertyIdentifier.ACKED_TRANSITIONS)
            if isinstance(acked_raw, list) and len(acked_raw) >= 3:
                b0 = bool(acked_raw[0])
                b1 = bool(acked_raw[1])
                b2 = bool(acked_raw[2])
                acked_bits = BitString(
                    bytes([(int(b0) << 7) | (int(b1) << 6) | (int(b2) << 5)]),
                    5,
                )
            elif isinstance(acked_raw, BitString):
                acked_bits = acked_raw
            else:
                acked_bits = BitString(b"\xe0", 5)

            summaries.append(
                AlarmSummary(
                    object_identifier=obj.object_identifier,
                    alarm_state=event_state_val,
                    acknowledged_transitions=acked_bits,
                )
            )

        return GetAlarmSummaryACK(list_of_alarm_summaries=summaries).encode()

    async def handle_get_enrollment_summary(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle GetEnrollmentSummary-Request per Clause 13.7.

        Iterates EventEnrollment objects, applies the request filters,
        and returns matching enrollment summaries.

        :returns: Encoded GetEnrollmentSummary-ACK service data.
        """
        request = GetEnrollmentSummaryRequest.decode(data)
        logger.debug("handling get_enrollment_summary from %s", source)

        summaries: list[EnrollmentSummary] = []
        for obj in self._db.get_objects_of_type(ObjectType.EVENT_ENROLLMENT):
            event_type_val = obj._properties.get(PropertyIdentifier.EVENT_TYPE)
            if event_type_val is not None and not isinstance(event_type_val, EventType):
                try:
                    event_type_val = EventType(event_type_val)
                except (ValueError, TypeError):
                    continue
            if event_type_val is None:
                event_type_val = EventType.CHANGE_OF_VALUE

            event_state_val = obj._properties.get(PropertyIdentifier.EVENT_STATE)
            if event_state_val is not None and not isinstance(event_state_val, EventState):
                try:
                    event_state_val = EventState(event_state_val)
                except (ValueError, TypeError):
                    continue
            if event_state_val is None:
                event_state_val = EventState.NORMAL

            notification_class: int = obj._properties.get(PropertyIdentifier.NOTIFICATION_CLASS, 0)

            # Apply request filters
            if (
                request.event_state_filter is not None
                and event_state_val != request.event_state_filter
            ):
                continue
            if (
                request.event_type_filter is not None
                and event_type_val != request.event_type_filter
            ):
                continue
            if (
                request.notification_class_filter is not None
                and notification_class != request.notification_class_filter
            ):
                continue

            # Acknowledgment filter
            if request.acknowledgment_filter == AcknowledgmentFilter.ACKED:
                acked_raw = obj._properties.get(PropertyIdentifier.ACKED_TRANSITIONS)
                if isinstance(acked_raw, list) and len(acked_raw) >= 3 and not all(acked_raw):
                    continue
            elif request.acknowledgment_filter == AcknowledgmentFilter.NOT_ACKED:
                acked_raw = obj._properties.get(PropertyIdentifier.ACKED_TRANSITIONS)
                if isinstance(acked_raw, list) and len(acked_raw) >= 3 and all(acked_raw):
                    continue

            summaries.append(
                EnrollmentSummary(
                    object_identifier=obj.object_identifier,
                    event_type=event_type_val,
                    event_state=event_state_val,
                    priority=0,
                    notification_class=notification_class,
                )
            )

        return GetEnrollmentSummaryACK(
            list_of_enrollment_summaries=summaries,
        ).encode()

    async def handle_get_event_information(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle GetEventInformation-Request per Clause 13.12.

        Iterates all objects in the database for those in an alarm
        (non-NORMAL) event state and returns event summaries with
        pagination support.

        :returns: Encoded GetEventInformation-ACK service data.
        """
        request = GetEventInformationRequest.decode(data)
        logger.debug("handling get_event_information from %s", source)

        default_timestamps = (
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
            BACnetTimeStamp(choice=1, value=0),
        )
        default_enable = BitString(b"\xe0", 5)
        default_acked = BitString(b"\xe0", 5)

        # If a last_received_object_identifier is specified, skip
        # objects until we pass it.
        skip = request.last_received_object_identifier is not None
        summaries: list[EventSummary] = []
        for obj in self._db.values():
            if skip:
                if obj.object_identifier == request.last_received_object_identifier:
                    skip = False
                continue

            event_state_val = obj._properties.get(PropertyIdentifier.EVENT_STATE)
            if event_state_val is None:
                continue
            if not isinstance(event_state_val, EventState):
                try:
                    event_state_val = EventState(event_state_val)
                except (ValueError, TypeError):
                    continue
            if event_state_val == EventState.NORMAL:
                continue

            # Event time stamps
            ts_raw = obj._properties.get(PropertyIdentifier.EVENT_TIME_STAMPS)
            if (
                isinstance(ts_raw, (list, tuple))
                and len(ts_raw) >= 3
                and all(isinstance(t, BACnetTimeStamp) for t in ts_raw[:3])
            ):
                event_time_stamps = (ts_raw[0], ts_raw[1], ts_raw[2])
            else:
                event_time_stamps = default_timestamps

            # Event enable
            event_enable_raw = obj._properties.get(PropertyIdentifier.EVENT_ENABLE)
            if isinstance(event_enable_raw, BitString):
                event_enable = event_enable_raw
            else:
                event_enable = default_enable

            # Notify type
            notify_type_raw = obj._properties.get(PropertyIdentifier.NOTIFY_TYPE)
            if isinstance(notify_type_raw, NotifyType):
                notify_type = notify_type_raw
            else:
                notify_type = NotifyType.ALARM

            # Acknowledged transitions
            acked_raw = obj._properties.get(PropertyIdentifier.ACKED_TRANSITIONS)
            if isinstance(acked_raw, BitString):
                acked_transitions = acked_raw
            elif isinstance(acked_raw, list) and len(acked_raw) >= 3:
                b0 = bool(acked_raw[0])
                b1 = bool(acked_raw[1])
                b2 = bool(acked_raw[2])
                acked_transitions = BitString(
                    bytes([(int(b0) << 7) | (int(b1) << 6) | (int(b2) << 5)]),
                    5,
                )
            else:
                acked_transitions = default_acked

            # Event priorities default to (0, 0, 0)
            event_priorities = (0, 0, 0)

            summaries.append(
                EventSummary(
                    object_identifier=obj.object_identifier,
                    event_state=event_state_val,
                    acknowledged_transitions=acked_transitions,
                    event_time_stamps=event_time_stamps,
                    notify_type=notify_type,
                    event_enable=event_enable,
                    event_priorities=event_priorities,
                )
            )

        return GetEventInformationACK(
            list_of_event_summaries=summaries,
            more_events=False,
        ).encode()

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
        logger.debug(
            "handling who_has id=%s name=%s from %s",
            request.object_identifier,
            request.object_name,
            source,
        )
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

    # --- Text message handlers ---

    async def handle_confirmed_text_message(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle ConfirmedTextMessage-Request per Clause 16.5.

        Logs the message and invokes the text message callback if set.

        :returns: ``None`` (SimpleACK response).
        """
        request = ConfirmedTextMessageRequest.decode(data)
        logger.info(
            "ConfirmedTextMessage from %s (device %s): priority=%s, message='%s'",
            source,
            request.text_message_source_device,
            request.message_priority.name,
            request.message,
        )
        callback = getattr(self._app, "_text_message_callback", None)
        if callback is not None:
            callback(request, source)
        return None

    async def handle_unconfirmed_text_message(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle UnconfirmedTextMessage-Request per Clause 16.6.

        Logs the message and invokes the text message callback if set.
        """
        request = UnconfirmedTextMessageRequest.decode(data)
        logger.info(
            "UnconfirmedTextMessage from %s (device %s): priority=%s, message='%s'",
            source,
            request.text_message_source_device,
            request.message_priority.name,
            request.message,
        )
        callback = getattr(self._app, "_text_message_callback", None)
        if callback is not None:
            callback(request, source)

    # --- WriteGroup handler ---

    async def handle_write_group(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle WriteGroup-Request per Clause 15.11.

        Looks up Channel objects by group number and writes values.
        """
        request = WriteGroupRequest.decode(data)
        logger.debug(
            "WriteGroup from %s: group=%d, priority=%d, %d channels",
            source,
            request.group_number,
            request.write_priority,
            len(request.change_list),
        )
        # Look up Channel objects whose Control_Groups includes this group number
        for obj in self._db.get_objects_of_type(ObjectType.CHANNEL):
            control_groups = obj._properties.get(PropertyIdentifier.CONTROL_GROUPS, [])
            if request.group_number not in control_groups:
                continue
            channel_number = obj._properties.get(PropertyIdentifier.CHANNEL_NUMBER)
            if channel_number is None:
                continue
            for gcv in request.change_list:
                if gcv.channel == channel_number:
                    try:
                        write_value = decode_and_unwrap(gcv.value)
                        priority = gcv.overriding_priority or request.write_priority
                        await obj.async_write_property(
                            PropertyIdentifier.PRESENT_VALUE,
                            write_value,
                            priority,
                        )
                    except (ValueError, BACnetError):
                        logger.debug("WriteGroup: failed to write channel %d", gcv.channel)

    # --- Device discovery handlers (new in 2020) ---

    async def handle_who_am_i(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle Who-Am-I-Request per Clause 16.11.

        Logs the request. A supervisor application should register a
        callback to handle device identity assignment.
        """
        request = WhoAmIRequest.decode(data)
        logger.info(
            "Who-Am-I from %s: vendor=%d, model='%s', serial='%s'",
            source,
            request.vendor_id,
            request.model_name,
            request.serial_number,
        )
        callback = getattr(self._app, "_who_am_i_callback", None)
        if callback is not None:
            callback(request, source)

    async def handle_you_are(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle You-Are-Request per Clause 16.11.

        Applies the assigned device identity if the device is unconfigured.
        """
        request = YouAreRequest.decode(data)
        logger.info(
            "You-Are from %s: device=%s, mac=%s, network=%s",
            source,
            request.device_identifier,
            request.device_mac_address.hex(),
            request.device_network_number,
        )
        callback = getattr(self._app, "_you_are_callback", None)
        if callback is not None:
            callback(request, source)

    # --- Virtual terminal handlers ---

    async def handle_vt_open(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle VT-Open-Request per Clause 17.1.

        :returns: Encoded VT-Open-ACK with remote session ID.
        :raises BACnetError: If no VT sessions are available or the
            VT class is not supported.
        """
        request = VTOpenRequest.decode(data)
        logger.info(
            "VT-Open from %s: class=%s, localSession=%d",
            source,
            request.vt_class.name,
            request.local_vt_session_identifier,
        )

        # Check VT class support
        vt_classes = self._device._properties.get(PropertyIdentifier.VT_CLASSES_SUPPORTED, [])
        if vt_classes and request.vt_class not in vt_classes:
            logger.warning("vt_open: unknown VT class %s from %s", request.vt_class.name, source)
            raise BACnetError(ErrorClass.VT, ErrorCode.UNKNOWN_VT_CLASS)

        # Allocate a session — use a simple counter on the app
        sessions: dict[int, dict[str, Any]] = getattr(self._app, "_vt_sessions", {})
        max_vt_sessions = 64
        if len(sessions) >= max_vt_sessions:
            logger.warning("vt_open: session limit (%d) reached from %s", max_vt_sessions, source)
            raise BACnetError(ErrorClass.RESOURCES, ErrorCode.NO_VT_SESSIONS_AVAILABLE)

        session_counter = getattr(self._app, "_vt_session_counter", 0) + 1
        self._app._vt_session_counter = session_counter  # type: ignore[attr-defined]

        # Store session mapping
        sessions[session_counter] = {
            "source": source,
            "vt_class": request.vt_class,
            "remote_session": request.local_vt_session_identifier,
        }
        self._app._vt_sessions = sessions  # type: ignore[attr-defined]

        ack = VTOpenACK(remote_vt_session_identifier=session_counter)
        return ack.encode()

    async def handle_vt_close(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle VT-Close-Request per Clause 17.2.

        :returns: ``None`` (SimpleACK response).
        :raises BACnetError: If a session ID is unknown.
        """
        request = VTCloseRequest.decode(data)
        sessions = getattr(self._app, "_vt_sessions", {})
        for session_id in request.list_of_remote_vt_session_identifiers:
            if session_id not in sessions:
                logger.warning("vt_close: unknown VT session %s from %s", session_id, source)
                raise BACnetError(ErrorClass.VT, ErrorCode.UNKNOWN_VT_SESSION)
            if sessions[session_id]["source"] != source:
                logger.warning("vt_close: session %s not owned by %s", session_id, source)
                raise BACnetError(ErrorClass.VT, ErrorCode.UNKNOWN_VT_SESSION)
            del sessions[session_id]
        logger.info(
            "VT-Close from %s: sessions=%s",
            source,
            request.list_of_remote_vt_session_identifiers,
        )
        return None

    async def handle_vt_data(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle VT-Data-Request per Clause 17.3.

        :returns: Encoded VT-Data-ACK.
        :raises BACnetError: If the session is unknown.
        """
        request = VTDataRequest.decode(data)
        sessions = getattr(self._app, "_vt_sessions", {})
        session = sessions.get(request.vt_session_identifier)
        if session is None:
            logger.warning(
                "vt_data: unknown VT session %d from %s",
                request.vt_session_identifier,
                source,
            )
            raise BACnetError(ErrorClass.VT, ErrorCode.UNKNOWN_VT_SESSION)
        if session["source"] != source:
            logger.warning(
                "vt_data: session %d not owned by %s",
                request.vt_session_identifier,
                source,
            )
            raise BACnetError(ErrorClass.VT, ErrorCode.UNKNOWN_VT_SESSION)
        logger.debug(
            "VT-Data from %s: session=%d, %d bytes, flag=%s",
            source,
            request.vt_session_identifier,
            len(request.vt_new_data),
            request.vt_data_flag,
        )
        ack = VTDataACK(all_new_data_accepted=True)
        return ack.encode()

    # --- Audit handlers (Clause 13.19-13.21) ---

    async def handle_audit_log_query(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes:
        """Handle AuditLogQuery-Request per Clause 13.19.

        Queries the specified Audit Log object's buffer.

        :returns: Encoded AuditLogQuery-ACK.
        :raises BACnetError: If the audit log object is not found.
        """
        from bac_py.objects.audit_log import AuditLogObject

        request = AuditLogQueryRequest.decode(data)
        logger.debug("handling audit_log_query %s from %s", request.audit_log, source)

        obj = self._db.get(request.audit_log)
        if obj is None or not isinstance(obj, AuditLogObject):
            logger.warning(
                "audit_log_query: unknown or invalid audit log %s from %s",
                request.audit_log,
                source,
            )
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        records, no_more = obj.query_records(
            start_at=request.start_at_sequence_number,
            count=request.requested_count,
        )

        ack = AuditLogQueryACK(
            audit_log=request.audit_log,
            records=records,
            no_more_items=no_more,
        )
        return ack.encode()

    async def handle_confirmed_audit_notification(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Handle ConfirmedAuditNotification-Request per Clause 13.20.

        Appends notifications to Audit Log objects.

        :returns: ``None`` (SimpleACK response).
        """
        from bac_py.objects.audit_log import AuditLogObject

        request = ConfirmedAuditNotificationRequest.decode(data)
        for notification in request.notifications:
            for obj in self._db.get_objects_of_type(ObjectType.AUDIT_LOG):
                if isinstance(obj, AuditLogObject):
                    obj.append_record(notification)
        logger.debug(
            "ConfirmedAuditNotification from %s: %d notifications",
            source,
            len(request.notifications),
        )
        return None

    async def handle_unconfirmed_audit_notification(
        self,
        service_choice: int,
        data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Handle UnconfirmedAuditNotification-Request per Clause 13.21.

        Appends notifications to Audit Log objects.
        """
        from bac_py.objects.audit_log import AuditLogObject

        request = UnconfirmedAuditNotificationRequest.decode(data)
        for notification in request.notifications:
            for obj in self._db.get_objects_of_type(ObjectType.AUDIT_LOG):
                if isinstance(obj, AuditLogObject):
                    obj.append_record(notification)
        logger.debug(
            "UnconfirmedAuditNotification from %s: %d notifications",
            source,
            len(request.notifications),
        )
