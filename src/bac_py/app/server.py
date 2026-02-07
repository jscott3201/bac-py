"""Default BACnet server handlers per ASHRAE 135-2016.

Provides handlers for Who-Is, ReadProperty, and WriteProperty that
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
from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
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
    from bac_py.objects.base import ObjectDatabase
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

    Registers handlers for ReadProperty, WriteProperty, and Who-Is
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
        value = obj.read_property(
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
