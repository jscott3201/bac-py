"""ReadPropertyMultiple service per ASHRAE 135-2016 Clause 15.7."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_unsigned,
    encode_application_enumerated,
    encode_context_object_id,
    encode_context_tagged,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    extract_context_value,
)
from bac_py.types.enums import ErrorClass, ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class PropertyReference:
    """BACnetPropertyReference (Clause 21).

    ::

        BACnetPropertyReference ::= SEQUENCE {
            propertyIdentifier  [0] BACnetPropertyIdentifier,
            propertyArrayIndex  [1] Unsigned OPTIONAL
        }
    """

    property_identifier: PropertyIdentifier
    property_array_index: int | None = None

    def encode(self) -> bytes:
        """Encode this property reference as context-tagged bytes.

        :returns: Encoded property reference bytes.
        """
        buf = bytearray()
        buf.extend(encode_context_tagged(0, encode_unsigned(self.property_identifier)))
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(1, encode_unsigned(self.property_array_index)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int) -> tuple[PropertyReference, int]:
        """Decode a property reference from a buffer at the given offset.

        :param data: Raw bytes containing encoded property reference data.
        :param offset: Byte offset to start decoding from.
        :returns: Tuple of (:class:`PropertyReference`, new offset).
        """
        data = as_memoryview(data)

        # [0] property-identifier
        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [1] property-array-index (optional)
        property_array_index = None
        if offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if (
                tag_peek.cls == TagClass.CONTEXT
                and tag_peek.number == 1
                and not tag_peek.is_opening
                and not tag_peek.is_closing
            ):
                property_array_index = decode_unsigned(
                    data[next_offset : next_offset + tag_peek.length]
                )
                offset = next_offset + tag_peek.length

        return cls(
            property_identifier=property_identifier,
            property_array_index=property_array_index,
        ), offset


@dataclass(frozen=True, slots=True)
class ReadAccessSpecification:
    """BACnetReadAccessSpecification (Clause 21).

    ::

        ReadAccessSpecification ::= SEQUENCE {
            objectIdentifier         [0] BACnetObjectIdentifier,
            listOfPropertyReferences [1] SEQUENCE OF BACnetPropertyReference
        }
    """

    object_identifier: ObjectIdentifier
    list_of_property_references: list[PropertyReference]

    def encode(self) -> bytes:
        """Encode this read access specification as context-tagged bytes.

        :returns: Encoded read access specification bytes.
        """
        buf = bytearray()
        # [0] object-identifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
        # [1] SEQUENCE OF BACnetPropertyReference
        buf.extend(encode_opening_tag(1))
        for ref in self.list_of_property_references:
            buf.extend(ref.encode())
        buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int) -> tuple[ReadAccessSpecification, int]:
        """Decode a read access specification from a buffer at the given offset.

        :param data: Raw bytes containing encoded read access specification data.
        :param offset: Byte offset to start decoding from.
        :returns: Tuple of (:class:`ReadAccessSpecification`, new offset).
        """
        data = as_memoryview(data)

        # [0] object-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] opening tag
        tag, offset = decode_tag(data, offset)
        # Should be opening tag 1

        # Decode property references until closing tag 1
        refs: list[PropertyReference] = []
        while offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if tag_peek.is_closing and tag_peek.number == 1:
                offset = next_offset
                break
            ref, offset = PropertyReference.decode(data, offset)
            refs.append(ref)

        return cls(
            object_identifier=object_identifier,
            list_of_property_references=refs,
        ), offset


@dataclass(frozen=True, slots=True)
class ReadPropertyMultipleRequest:
    """ReadPropertyMultiple-Request service parameters (Clause 15.7.1.1).

    ::

        ReadPropertyMultiple-Request ::= SEQUENCE {
            listOfReadAccessSpecs  SEQUENCE OF ReadAccessSpecification
        }
    """

    list_of_read_access_specs: list[ReadAccessSpecification]

    def encode(self) -> bytes:
        """Encode ReadPropertyMultiple-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        for spec in self.list_of_read_access_specs:
            buf.extend(spec.encode())
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReadPropertyMultipleRequest:
        """Decode ReadPropertyMultiple-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`ReadPropertyMultipleRequest`.
        """
        data = as_memoryview(data)

        offset = 0
        specs: list[ReadAccessSpecification] = []
        while offset < len(data):
            spec, offset = ReadAccessSpecification.decode(data, offset)
            specs.append(spec)

        return cls(list_of_read_access_specs=specs)


@dataclass(frozen=True, slots=True)
class ReadResultElement:
    """Single result element within a ReadAccessResult.

    Contains either a property value (success) or an error (failure),
    but not both.

    ::

        ReadAccessResult.listOfResults-element ::= SEQUENCE {
            propertyIdentifier  [2] BACnetPropertyIdentifier,
            propertyArrayIndex  [3] Unsigned OPTIONAL,
            propertyValue       [4] ABSTRACT-SYNTAX.&TYPE,   -- on success
          | propertyAccessError [5] BACnetError               -- on failure
        }
    """

    property_identifier: PropertyIdentifier
    property_array_index: int | None = None
    property_value: bytes | None = None
    property_access_error: tuple[ErrorClass, ErrorCode] | None = None

    def encode(self) -> bytes:
        """Encode a single read result element.

        :returns: Encoded result element bytes containing either a property
            value (success) or a property access error (failure).
        """
        buf = bytearray()
        # [2] property-identifier
        buf.extend(encode_context_tagged(2, encode_unsigned(self.property_identifier)))
        # [3] property-array-index (optional)
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(3, encode_unsigned(self.property_array_index)))
        if self.property_value is not None:
            # [4] property-value (success)
            buf.extend(encode_opening_tag(4))
            buf.extend(self.property_value)
            buf.extend(encode_closing_tag(4))
        elif self.property_access_error is not None:
            # [5] property-access-error (failure)
            # BACnetError ::= SEQUENCE { error-class ENUMERATED, error-code ENUMERATED }
            error_class, error_code = self.property_access_error
            buf.extend(encode_opening_tag(5))
            buf.extend(encode_application_enumerated(error_class))
            buf.extend(encode_application_enumerated(error_code))
            buf.extend(encode_closing_tag(5))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int) -> tuple[ReadResultElement, int]:
        """Decode a single read result element from a buffer at the given offset.

        :param data: Raw bytes containing encoded result element data.
        :param offset: Byte offset to start decoding from.
        :returns: Tuple of (:class:`ReadResultElement`, new offset).
        """
        data = as_memoryview(data)

        # [2] property-identifier
        tag, offset = decode_tag(data, offset)
        property_identifier = PropertyIdentifier(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [3] property-array-index (optional)
        property_array_index = None
        tag_peek, next_offset = decode_tag(data, offset)
        if (
            tag_peek.cls == TagClass.CONTEXT
            and tag_peek.number == 3
            and not tag_peek.is_opening
            and not tag_peek.is_closing
        ):
            property_array_index = decode_unsigned(
                data[next_offset : next_offset + tag_peek.length]
            )
            offset = next_offset + tag_peek.length
            tag_peek, next_offset = decode_tag(data, offset)

        property_value = None
        property_access_error = None

        if tag_peek.is_opening and tag_peek.number == 4:
            # [4] property-value
            property_value, offset = extract_context_value(data, next_offset, 4)
        elif tag_peek.is_opening and tag_peek.number == 5:
            # [5] property-access-error
            offset = next_offset
            # error-class (application-tagged enumerated)
            tag_ec, offset = decode_tag(data, offset)
            error_class_val = decode_unsigned(data[offset : offset + tag_ec.length])
            offset += tag_ec.length
            # error-code (application-tagged enumerated)
            tag_ec2, offset = decode_tag(data, offset)
            error_code_val = decode_unsigned(data[offset : offset + tag_ec2.length])
            offset += tag_ec2.length
            # closing tag 5
            _closing, offset = decode_tag(data, offset)
            property_access_error = (ErrorClass(error_class_val), ErrorCode(error_code_val))

        return cls(
            property_identifier=property_identifier,
            property_array_index=property_array_index,
            property_value=property_value,
            property_access_error=property_access_error,
        ), offset


@dataclass(frozen=True, slots=True)
class ReadAccessResult:
    """BACnetReadAccessResult (Clause 21).

    ::

        ReadAccessResult ::= SEQUENCE {
            objectIdentifier  [0] BACnetObjectIdentifier,
            listOfResults     [1] SEQUENCE OF ReadAccessResult.listOfResults-element
        }
    """

    object_identifier: ObjectIdentifier
    list_of_results: list[ReadResultElement]

    def encode(self) -> bytes:
        """Encode this read access result as context-tagged bytes.

        :returns: Encoded read access result bytes.
        """
        buf = bytearray()
        # [0] object-identifier
        buf.extend(encode_context_object_id(0, self.object_identifier))
        # [1] SEQUENCE OF results
        buf.extend(encode_opening_tag(1))
        for elem in self.list_of_results:
            buf.extend(elem.encode())
        buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes, offset: int) -> tuple[ReadAccessResult, int]:
        """Decode a read access result from a buffer at the given offset.

        :param data: Raw bytes containing encoded read access result data.
        :param offset: Byte offset to start decoding from.
        :returns: Tuple of (:class:`ReadAccessResult`, new offset).
        """
        data = as_memoryview(data)

        # [0] object-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] opening tag
        _opening, offset = decode_tag(data, offset)

        # Decode result elements until closing tag 1
        results: list[ReadResultElement] = []
        while offset < len(data):
            tag_peek, next_offset = decode_tag(data, offset)
            if tag_peek.is_closing and tag_peek.number == 1:
                offset = next_offset
                break
            elem, offset = ReadResultElement.decode(data, offset)
            results.append(elem)

        return cls(
            object_identifier=object_identifier,
            list_of_results=results,
        ), offset


@dataclass(frozen=True, slots=True)
class ReadPropertyMultipleACK:
    """ReadPropertyMultiple-ACK service parameters (Clause 15.7.1.2).

    ::

        ReadPropertyMultiple-ACK ::= SEQUENCE {
            listOfReadAccessResults  SEQUENCE OF ReadAccessResult
        }
    """

    list_of_read_access_results: list[ReadAccessResult]

    def encode(self) -> bytes:
        """Encode ReadPropertyMultiple-ACK service parameters.

        :returns: Encoded service ACK bytes.
        """
        buf = bytearray()
        for result in self.list_of_read_access_results:
            buf.extend(result.encode())
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReadPropertyMultipleACK:
        """Decode ReadPropertyMultiple-ACK from service ACK bytes.

        :param data: Raw service ACK bytes.
        :returns: Decoded :class:`ReadPropertyMultipleACK`.
        """
        data = as_memoryview(data)

        offset = 0
        results: list[ReadAccessResult] = []
        while offset < len(data):
            result, offset = ReadAccessResult.decode(data, offset)
            results.append(result)

        return cls(list_of_read_access_results=results)
