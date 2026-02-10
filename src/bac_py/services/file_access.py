"""Atomic file access services per ASHRAE 135-2016 Clause 14.

AtomicReadFile (Clause 14.1), AtomicWriteFile (Clause 14.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_octet_string,
    decode_signed,
    decode_unsigned,
    encode_application_boolean,
    encode_application_object_id,
    encode_application_octet_string,
    encode_application_signed,
    encode_application_unsigned,
    encode_context_tagged,
    encode_signed,
)
from bac_py.encoding.tags import as_memoryview, decode_tag, encode_closing_tag, encode_opening_tag
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier

# --- AtomicReadFile ---


@dataclass(frozen=True, slots=True)
class StreamReadAccess:
    """Stream access parameters for AtomicReadFile-Request."""

    file_start_position: int
    requested_octet_count: int


@dataclass(frozen=True, slots=True)
class RecordReadAccess:
    """Record access parameters for AtomicReadFile-Request."""

    file_start_record: int
    requested_record_count: int


@dataclass(frozen=True, slots=True)
class AtomicReadFileRequest:
    """AtomicReadFile-Request (Clause 14.1.1.1).

    ::

        AtomicReadFile-Request ::= SEQUENCE {
            fileIdentifier    BACnetObjectIdentifier,
            accessMethod      CHOICE {
                streamAccess  [0] SEQUENCE {
                    fileStartPosition      INTEGER,
                    requestedOctetCount    Unsigned
                },
                recordAccess  [1] SEQUENCE {
                    fileStartRecord        INTEGER,
                    requestedRecordCount   Unsigned
                }
            }
        }
    """

    file_identifier: ObjectIdentifier
    access_method: StreamReadAccess | RecordReadAccess

    def encode(self) -> bytes:
        """Encode AtomicReadFile-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        # fileIdentifier (APPLICATION-tagged)
        buf.extend(
            encode_application_object_id(
                self.file_identifier.object_type,
                self.file_identifier.instance_number,
            )
        )
        if isinstance(self.access_method, StreamReadAccess):
            buf.extend(encode_opening_tag(0))
            buf.extend(encode_application_signed(self.access_method.file_start_position))
            buf.extend(encode_application_unsigned(self.access_method.requested_octet_count))
            buf.extend(encode_closing_tag(0))
        else:
            buf.extend(encode_opening_tag(1))
            buf.extend(encode_application_signed(self.access_method.file_start_record))
            buf.extend(encode_application_unsigned(self.access_method.requested_record_count))
            buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> AtomicReadFileRequest:
        """Decode AtomicReadFile-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`AtomicReadFileRequest`.
        :raises ValueError: If the access method CHOICE tag is unrecognized.
        """
        data = as_memoryview(data)

        offset = 0

        # fileIdentifier (APPLICATION tag 12)
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        file_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # accessMethod CHOICE
        tag, offset = decode_tag(data, offset)
        access_method: StreamReadAccess | RecordReadAccess
        if tag.number == 0 and tag.is_opening:
            # streamAccess
            t, offset = decode_tag(data, offset)
            file_start_position = decode_signed(data[offset : offset + t.length])
            offset += t.length
            t, offset = decode_tag(data, offset)
            requested_octet_count = decode_unsigned(data[offset : offset + t.length])
            offset += t.length
            _closing, offset = decode_tag(data, offset)
            access_method = StreamReadAccess(file_start_position, requested_octet_count)
        elif tag.number == 1 and tag.is_opening:
            # recordAccess
            t, offset = decode_tag(data, offset)
            file_start_record = decode_signed(data[offset : offset + t.length])
            offset += t.length
            t, offset = decode_tag(data, offset)
            requested_record_count = decode_unsigned(data[offset : offset + t.length])
            offset += t.length
            _closing, offset = decode_tag(data, offset)
            access_method = RecordReadAccess(file_start_record, requested_record_count)
        else:
            msg = f"Unexpected tag {tag.number} in AtomicReadFile CHOICE"
            raise ValueError(msg)

        return cls(file_identifier=file_identifier, access_method=access_method)


@dataclass(frozen=True, slots=True)
class StreamReadACK:
    """Stream access result for AtomicReadFile-ACK."""

    file_start_position: int
    file_data: bytes


@dataclass(frozen=True, slots=True)
class RecordReadACK:
    """Record access result for AtomicReadFile-ACK."""

    file_start_record: int
    returned_record_count: int
    file_record_data: list[bytes]


@dataclass(frozen=True, slots=True)
class AtomicReadFileACK:
    """AtomicReadFile-ACK (Clause 14.1.1.2).

    ::

        AtomicReadFile-ACK ::= SEQUENCE {
            endOfFile       BOOLEAN,
            accessMethod    CHOICE {
                streamAccess  [0] SEQUENCE {
                    fileStartPosition  INTEGER,
                    fileData           OCTET STRING
                },
                recordAccess  [1] SEQUENCE {
                    fileStartRecord      INTEGER,
                    returnedRecordCount  Unsigned,
                    fileRecordData       SEQUENCE OF OCTET STRING
                }
            }
        }
    """

    end_of_file: bool
    access_method: StreamReadACK | RecordReadACK

    def encode(self) -> bytes:
        """Encode AtomicReadFile-ACK service parameters.

        :returns: Encoded service ACK bytes.
        """
        buf = bytearray()
        # endOfFile (APPLICATION-tagged boolean)
        buf.extend(encode_application_boolean(self.end_of_file))
        if isinstance(self.access_method, StreamReadACK):
            buf.extend(encode_opening_tag(0))
            buf.extend(encode_application_signed(self.access_method.file_start_position))
            buf.extend(encode_application_octet_string(self.access_method.file_data))
            buf.extend(encode_closing_tag(0))
        else:
            buf.extend(encode_opening_tag(1))
            buf.extend(encode_application_signed(self.access_method.file_start_record))
            buf.extend(encode_application_unsigned(self.access_method.returned_record_count))
            for record in self.access_method.file_record_data:
                buf.extend(encode_application_octet_string(record))
            buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> AtomicReadFileACK:
        """Decode AtomicReadFile-ACK from service ACK bytes.

        :param data: Raw service ACK bytes.
        :returns: Decoded :class:`AtomicReadFileACK`.
        :raises ValueError: If the access method CHOICE tag is unrecognized.
        """
        data = as_memoryview(data)

        offset = 0

        # endOfFile (APPLICATION-tagged boolean, tag 1)
        # Per Clause 20.2.3, the boolean value is in the tag's L/V/T field.
        tag, offset = decode_tag(data, offset)
        end_of_file = tag.is_boolean_true

        # accessMethod CHOICE
        tag, offset = decode_tag(data, offset)
        access_method: StreamReadACK | RecordReadACK
        if tag.number == 0 and tag.is_opening:
            # streamAccess
            t, offset = decode_tag(data, offset)
            file_start_position = decode_signed(data[offset : offset + t.length])
            offset += t.length
            t, offset = decode_tag(data, offset)
            file_data = decode_octet_string(data[offset : offset + t.length])
            offset += t.length
            _closing, offset = decode_tag(data, offset)
            access_method = StreamReadACK(file_start_position, file_data)
        elif tag.number == 1 and tag.is_opening:
            # recordAccess
            t, offset = decode_tag(data, offset)
            file_start_record = decode_signed(data[offset : offset + t.length])
            offset += t.length
            t, offset = decode_tag(data, offset)
            returned_record_count = decode_unsigned(data[offset : offset + t.length])
            offset += t.length
            file_record_data: list[bytes] = []
            for _ in range(returned_record_count):
                t, offset = decode_tag(data, offset)
                file_record_data.append(decode_octet_string(data[offset : offset + t.length]))
                offset += t.length
            _closing, offset = decode_tag(data, offset)
            access_method = RecordReadACK(
                file_start_record, returned_record_count, file_record_data
            )
        else:
            msg = f"Unexpected tag {tag.number} in AtomicReadFileACK CHOICE"
            raise ValueError(msg)

        return cls(end_of_file=end_of_file, access_method=access_method)


# --- AtomicWriteFile ---


@dataclass(frozen=True, slots=True)
class StreamWriteAccess:
    """Stream access parameters for AtomicWriteFile-Request."""

    file_start_position: int
    file_data: bytes


@dataclass(frozen=True, slots=True)
class RecordWriteAccess:
    """Record access parameters for AtomicWriteFile-Request."""

    file_start_record: int
    record_count: int
    file_record_data: list[bytes]


@dataclass(frozen=True, slots=True)
class AtomicWriteFileRequest:
    """AtomicWriteFile-Request (Clause 14.2.1.1).

    ::

        AtomicWriteFile-Request ::= SEQUENCE {
            fileIdentifier    BACnetObjectIdentifier,
            accessMethod      CHOICE {
                streamAccess  [0] SEQUENCE {
                    fileStartPosition  INTEGER,
                    fileData           OCTET STRING
                },
                recordAccess  [1] SEQUENCE {
                    fileStartRecord    INTEGER,
                    recordCount        Unsigned,
                    fileRecordData     SEQUENCE OF OCTET STRING
                }
            }
        }
    """

    file_identifier: ObjectIdentifier
    access_method: StreamWriteAccess | RecordWriteAccess

    def encode(self) -> bytes:
        """Encode AtomicWriteFile-Request service parameters.

        :returns: Encoded service request bytes.
        """
        buf = bytearray()
        buf.extend(
            encode_application_object_id(
                self.file_identifier.object_type,
                self.file_identifier.instance_number,
            )
        )
        if isinstance(self.access_method, StreamWriteAccess):
            buf.extend(encode_opening_tag(0))
            buf.extend(encode_application_signed(self.access_method.file_start_position))
            buf.extend(encode_application_octet_string(self.access_method.file_data))
            buf.extend(encode_closing_tag(0))
        else:
            buf.extend(encode_opening_tag(1))
            buf.extend(encode_application_signed(self.access_method.file_start_record))
            buf.extend(encode_application_unsigned(self.access_method.record_count))
            for record in self.access_method.file_record_data:
                buf.extend(encode_application_octet_string(record))
            buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> AtomicWriteFileRequest:
        """Decode AtomicWriteFile-Request from service request bytes.

        :param data: Raw service request bytes.
        :returns: Decoded :class:`AtomicWriteFileRequest`.
        :raises ValueError: If the access method CHOICE tag is unrecognized.
        """
        data = as_memoryview(data)

        offset = 0

        # fileIdentifier (APPLICATION tag 12)
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        file_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        # accessMethod CHOICE
        tag, offset = decode_tag(data, offset)
        access_method: StreamWriteAccess | RecordWriteAccess
        if tag.number == 0 and tag.is_opening:
            # streamAccess
            t, offset = decode_tag(data, offset)
            file_start_position = decode_signed(data[offset : offset + t.length])
            offset += t.length
            t, offset = decode_tag(data, offset)
            file_data = decode_octet_string(data[offset : offset + t.length])
            offset += t.length
            _closing, offset = decode_tag(data, offset)
            access_method = StreamWriteAccess(file_start_position, file_data)
        elif tag.number == 1 and tag.is_opening:
            # recordAccess
            t, offset = decode_tag(data, offset)
            file_start_record = decode_signed(data[offset : offset + t.length])
            offset += t.length
            t, offset = decode_tag(data, offset)
            record_count = decode_unsigned(data[offset : offset + t.length])
            offset += t.length
            file_record_data: list[bytes] = []
            for _ in range(record_count):
                t, offset = decode_tag(data, offset)
                file_record_data.append(decode_octet_string(data[offset : offset + t.length]))
                offset += t.length
            _closing, offset = decode_tag(data, offset)
            access_method = RecordWriteAccess(file_start_record, record_count, file_record_data)
        else:
            msg = f"Unexpected tag {tag.number} in AtomicWriteFile CHOICE"
            raise ValueError(msg)

        return cls(file_identifier=file_identifier, access_method=access_method)


@dataclass(frozen=True, slots=True)
class AtomicWriteFileACK:
    """AtomicWriteFile-ACK (Clause 14.2.1.2).

    ::

        AtomicWriteFile-ACK ::= CHOICE {
            fileStartPosition  [0] INTEGER,
            fileStartRecord    [1] INTEGER
        }
    """

    is_stream: bool
    file_start: int

    def encode(self) -> bytes:
        """Encode AtomicWriteFile-ACK service parameters.

        :returns: Encoded service ACK bytes.
        """
        tag_number = 0 if self.is_stream else 1
        return encode_context_tagged(tag_number, encode_signed(self.file_start))

    @classmethod
    def decode(cls, data: memoryview | bytes) -> AtomicWriteFileACK:
        """Decode AtomicWriteFile-ACK from service ACK bytes.

        :param data: Raw service ACK bytes.
        :returns: Decoded :class:`AtomicWriteFileACK`.
        """
        data = as_memoryview(data)

        offset = 0
        tag, offset = decode_tag(data, offset)
        is_stream = tag.number == 0
        file_start = decode_signed(data[offset : offset + tag.length])

        return cls(is_stream=is_stream, file_start=file_start)
