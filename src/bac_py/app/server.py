"""Default BACnet server handlers per ASHRAE 135-2016.

Provides handlers for Who-Is, ReadProperty, WriteProperty,
ReadPropertyMultiple, WritePropertyMultiple, and ReadRange that
work with the local ObjectDatabase and DeviceObject.
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING, Any

from bac_py.encoding.primitives import (
    encode_application_bit_string,
    encode_application_character_string,
    encode_application_enumerated,
    encode_application_object_id,
    encode_application_unsigned,
)
from bac_py.services.errors import BACnetError
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
from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.services.write_property_multiple import WritePropertyMultipleRequest
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import BitString, ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.objects.base import BACnetObject, ObjectDatabase
    from bac_py.objects.device import DeviceObject

logger = logging.getLogger(__name__)


def _encode_property_value(value: Any) -> bytes:
    """Encode a property value to application-tagged bytes.

    Handles the common Python types stored in BACnet objects.
    Returns raw application-tagged encoded bytes suitable for
    inclusion in a ReadPropertyACK property-value field.
    """
    if isinstance(value, ObjectIdentifier):
        return encode_application_object_id(value.object_type, value.instance_number)
    if isinstance(value, BitString):
        return encode_application_bit_string(value)
    if isinstance(value, str):
        return encode_application_character_string(value)
    if isinstance(value, bool):
        # Must check bool before int since bool is a subclass of int
        return encode_application_enumerated(int(value))
    if isinstance(value, enum.IntEnum):
        # Must check IntEnum before int since IntEnum is a subclass of int
        return encode_application_enumerated(value)
    if isinstance(value, int):
        return encode_application_unsigned(value)
    if isinstance(value, list):
        # Encode list of ObjectIdentifiers (e.g., object-list)
        buf = bytearray()
        for item in value:
            buf.extend(_encode_property_value(item))
        return bytes(buf)
    raise BACnetError(ErrorClass.PROPERTY, ErrorCode.OTHER)


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
        registry.register_unconfirmed(
            UnconfirmedServiceChoice.WHO_IS,
            self.handle_who_is,
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

        # Wildcard device instance 4194303 resolves to local device (Clause 15.5.2)
        obj_id = request.object_identifier
        if obj_id.object_type == ObjectType.DEVICE and obj_id.instance_number == 0x3FFFFF:
            obj_id = self._device.object_identifier

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

        # Wildcard device instance 4194303 resolves to local device (Clause 15.9)
        obj_id = request.object_identifier
        if obj_id.object_type == ObjectType.DEVICE and obj_id.instance_number == 0x3FFFFF:
            obj_id = self._device.object_identifier

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

        return None

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

        # Send I-Am response
        config = self._app.config
        segmentation = self._device.read_property(PropertyIdentifier.SEGMENTATION_SUPPORTED)
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, instance),
            max_apdu_length=config.max_apdu_length,
            segmentation_supported=segmentation,
            vendor_id=config.vendor_id,
        )
        self._app.unconfirmed_request(
            destination=source,
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
                    pv.property_value,
                    pv.priority,
                    pv.property_array_index,
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
