"""Device discovery services per ASHRAE 135-2020 Clause 16.11.

Who-Am-I (new in 2020) and You-Are for device identity assignment.
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_object_identifier,
    decode_unsigned,
    encode_application_character_string,
    encode_application_unsigned,
    encode_context_object_id,
    encode_context_octet_string,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import TagClass, as_memoryview, decode_tag
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class WhoAmIRequest:
    """Who-Am-I-Request (Clause 16.11, new in 2020).

    Sent by an unconfigured device to request identity assignment.
    All fields use APPLICATION tags.

    ::

        Who-Am-I-Request ::= SEQUENCE {
            vendorID      Unsigned16,
            modelName     CharacterString,
            serialNumber  CharacterString
        }
    """

    vendor_id: int
    model_name: str
    serial_number: str

    def encode(self) -> bytes:
        """Encode Who-Am-I-Request service parameters."""
        buf = bytearray()
        buf.extend(encode_application_unsigned(self.vendor_id))
        buf.extend(encode_application_character_string(self.model_name))
        buf.extend(encode_application_character_string(self.serial_number))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> WhoAmIRequest:
        """Decode Who-Am-I-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        # vendorID (application tagged unsigned)
        tag, offset = decode_tag(data, offset)
        vendor_id = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # modelName (application tagged character string)
        tag, offset = decode_tag(data, offset)
        model_name = decode_character_string(data[offset : offset + tag.length])
        offset += tag.length

        # serialNumber (application tagged character string)
        tag, offset = decode_tag(data, offset)
        serial_number = decode_character_string(data[offset : offset + tag.length])

        return cls(
            vendor_id=vendor_id,
            model_name=model_name,
            serial_number=serial_number,
        )


@dataclass(frozen=True, slots=True)
class YouAreRequest:
    """You-Are-Request (Clause 16.11, new in 2020).

    Sent by a supervisor to assign identity to a device.

    ::

        You-Are-Request ::= SEQUENCE {
            deviceIdentifier     [0] BACnetObjectIdentifier,
            deviceMACAddress     [1] OCTET STRING,
            deviceNetworkNumber  [2] Unsigned16 OPTIONAL
        }
    """

    device_identifier: ObjectIdentifier
    device_mac_address: bytes
    device_network_number: int | None = None

    def encode(self) -> bytes:
        """Encode You-Are-Request service parameters."""
        buf = bytearray()
        # [0] deviceIdentifier
        buf.extend(encode_context_object_id(0, self.device_identifier))
        # [1] deviceMACAddress
        buf.extend(encode_context_octet_string(1, self.device_mac_address))
        # [2] deviceNetworkNumber (optional)
        if self.device_network_number is not None:
            buf.extend(encode_context_tagged(2, encode_unsigned(self.device_network_number)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> YouAreRequest:
        """Decode You-Are-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        # [0] deviceIdentifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] deviceMACAddress
        tag, offset = decode_tag(data, offset)
        device_mac_address = bytes(data[offset : offset + tag.length])
        offset += tag.length

        # [2] deviceNetworkNumber (optional)
        device_network_number = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 2:
                device_network_number = decode_unsigned(data[new_offset : new_offset + tag.length])

        return cls(
            device_identifier=device_identifier,
            device_mac_address=device_mac_address,
            device_network_number=device_network_number,
        )
