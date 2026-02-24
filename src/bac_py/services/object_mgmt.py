"""Object management services per ASHRAE 135-2016 Clause 15.3-15.4.

CreateObject (Clause 15.3), DeleteObject (Clause 15.4).
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_unsigned,
    encode_application_object_id,
    encode_context_object_id,
    encode_context_tagged,
    encode_enumerated,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
)
from bac_py.services.common import BACnetPropertyValue
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier

_MAX_DECODED_ITEMS = 10_000


@dataclass(frozen=True, slots=True)
class CreateObjectRequest:
    """CreateObject-Request (Clause 15.3.1.1).

    ::

        CreateObject-Request ::= SEQUENCE {
            objectSpecifier  [0] CHOICE {
                objectType        [0] BACnetObjectType,
                objectIdentifier  [1] BACnetObjectIdentifier
            },
            listOfInitialValues  [1] SEQUENCE OF BACnetPropertyValue OPTIONAL
        }
    """

    object_type: ObjectType | None = None
    object_identifier: ObjectIdentifier | None = None
    list_of_initial_values: list[BACnetPropertyValue] | None = None

    def encode(self) -> bytes:
        """Encode CreateObject-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # [0] objectSpecifier
        buf.extend(encode_opening_tag(0))
        if self.object_identifier is not None:
            buf.extend(encode_context_object_id(1, self.object_identifier))
        elif self.object_type is not None:
            buf.extend(encode_context_tagged(0, encode_enumerated(self.object_type)))
        buf.extend(encode_closing_tag(0))
        # [1] listOfInitialValues (optional)
        if self.list_of_initial_values:
            buf.extend(encode_opening_tag(1))
            for pv in self.list_of_initial_values:
                buf.extend(pv.encode())
            buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> CreateObjectRequest:
        """Decode CreateObject-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`CreateObjectRequest`.
        :raises ValueError: If the objectSpecifier CHOICE tag is unrecognized.
        """
        data = as_memoryview(data)

        offset = 0

        # [0] objectSpecifier (opening tag 0)
        opening, offset = decode_tag(data, offset)
        if not opening.is_opening or opening.number != 0:
            msg = f"Expected opening tag 0 for objectSpecifier, got tag {opening.number}"
            raise ValueError(msg)

        object_type: ObjectType | None = None
        object_identifier: ObjectIdentifier | None = None

        tag, new_offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 0:
            # objectType
            object_type = ObjectType(decode_unsigned(data[new_offset : new_offset + tag.length]))
            offset = new_offset + tag.length
        elif tag.cls == TagClass.CONTEXT and tag.number == 1:
            # objectIdentifier
            obj_type, instance = decode_object_identifier(
                data[new_offset : new_offset + tag.length]
            )
            object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
            offset = new_offset + tag.length
        else:
            msg = f"Unexpected tag {tag.number} in CreateObject objectSpecifier CHOICE"
            raise ValueError(msg)

        # closing tag 0
        _closing, offset = decode_tag(data, offset)

        # [1] listOfInitialValues (optional)
        list_of_initial_values: list[BACnetPropertyValue] | None = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.is_opening and tag.number == 1:
                offset = new_offset
                list_of_initial_values = []
                while offset < len(data):
                    tag, new_offset = decode_tag(data, offset)
                    if tag.is_closing and tag.number == 1:
                        offset = new_offset
                        break
                    pv, offset = BACnetPropertyValue.decode_from(data, offset)
                    list_of_initial_values.append(pv)
                    if len(list_of_initial_values) >= _MAX_DECODED_ITEMS:
                        msg = f"Decoded item count exceeds limit ({_MAX_DECODED_ITEMS})"
                        raise ValueError(msg)

        return cls(
            object_type=object_type,
            object_identifier=object_identifier,
            list_of_initial_values=list_of_initial_values,
        )


@dataclass(frozen=True, slots=True)
class DeleteObjectRequest:
    """DeleteObject-Request (Clause 15.4.1.1).

    ::

        DeleteObject-Request ::= SEQUENCE {
            objectIdentifier  BACnetObjectIdentifier
        }

    The objectIdentifier is APPLICATION-tagged.
    """

    object_identifier: ObjectIdentifier

    def encode(self) -> bytes:
        """Encode DeleteObject-Request service parameters.

        :returns: Encoded service request bytes.
        """
        return encode_application_object_id(
            self.object_identifier.object_type,
            self.object_identifier.instance_number,
        )

    @classmethod
    def decode(cls, data: memoryview | bytes) -> DeleteObjectRequest:
        """Decode DeleteObject-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`DeleteObjectRequest`.
        """
        data = as_memoryview(data)

        offset = 0
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])

        return cls(object_identifier=ObjectIdentifier(ObjectType(obj_type), instance))
