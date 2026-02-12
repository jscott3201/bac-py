"""Virtual terminal services per ASHRAE 135-2020 Clause 17.

VT-Open (Clause 17.1), VT-Close (Clause 17.2), VT-Data (Clause 17.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_octet_string,
    decode_unsigned,
    encode_application_boolean,
    encode_application_enumerated,
    encode_application_octet_string,
    encode_application_unsigned,
)
from bac_py.encoding.tags import as_memoryview, decode_tag
from bac_py.types.enums import VTClass


@dataclass(frozen=True, slots=True)
class VTOpenRequest:
    """VT-Open-Request (Clause 17.1.1).

    ::

        VT-Open-Request ::= SEQUENCE {
            vtClass                    BACnetVTClass,
            localVTSessionIdentifier   Unsigned8
        }
    """

    vt_class: VTClass
    local_vt_session_identifier: int

    def encode(self) -> bytes:
        """Encode VT-Open-Request service parameters."""
        buf = bytearray()
        buf.extend(encode_application_enumerated(self.vt_class))
        buf.extend(encode_application_unsigned(self.local_vt_session_identifier))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> VTOpenRequest:
        """Decode VT-Open-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        tag, offset = decode_tag(data, offset)
        vt_class = VTClass(decode_unsigned(data[offset : offset + tag.length]))
        offset += tag.length

        tag, offset = decode_tag(data, offset)
        local_id = decode_unsigned(data[offset : offset + tag.length])

        return cls(vt_class=vt_class, local_vt_session_identifier=local_id)


@dataclass(frozen=True, slots=True)
class VTOpenACK:
    """VT-Open-ACK (Clause 17.1.2).

    ::

        VT-Open-ACK ::= SEQUENCE {
            remoteVTSessionIdentifier  Unsigned8
        }
    """

    remote_vt_session_identifier: int

    def encode(self) -> bytes:
        """Encode VT-Open-ACK service parameters."""
        return bytes(encode_application_unsigned(self.remote_vt_session_identifier))

    @classmethod
    def decode(cls, data: memoryview | bytes) -> VTOpenACK:
        """Decode VT-Open-ACK from service request bytes."""
        data = as_memoryview(data)
        tag, offset = decode_tag(data, 0)
        remote_id = decode_unsigned(data[offset : offset + tag.length])
        return cls(remote_vt_session_identifier=remote_id)


@dataclass(frozen=True, slots=True)
class VTCloseRequest:
    """VT-Close-Request (Clause 17.2.1).

    ::

        VT-Close-Request ::= SEQUENCE {
            listOfRemoteVTSessionIdentifiers  SEQUENCE OF Unsigned8
        }
    """

    list_of_remote_vt_session_identifiers: list[int]

    def encode(self) -> bytes:
        """Encode VT-Close-Request service parameters."""
        buf = bytearray()
        for session_id in self.list_of_remote_vt_session_identifiers:
            buf.extend(encode_application_unsigned(session_id))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> VTCloseRequest:
        """Decode VT-Close-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0
        identifiers: list[int] = []
        while offset < len(data):
            tag, offset = decode_tag(data, offset)
            identifiers.append(decode_unsigned(data[offset : offset + tag.length]))
            offset += tag.length
        return cls(list_of_remote_vt_session_identifiers=identifiers)


@dataclass(frozen=True, slots=True)
class VTDataRequest:
    """VT-Data-Request (Clause 17.3.1).

    ::

        VT-Data-Request ::= SEQUENCE {
            vtSessionIdentifier  Unsigned8,
            vtNewData            OCTET STRING,
            vtDataFlag           BOOLEAN
        }
    """

    vt_session_identifier: int
    vt_new_data: bytes
    vt_data_flag: bool

    def encode(self) -> bytes:
        """Encode VT-Data-Request service parameters."""
        buf = bytearray()
        buf.extend(encode_application_unsigned(self.vt_session_identifier))
        buf.extend(encode_application_octet_string(self.vt_new_data))
        buf.extend(encode_application_boolean(self.vt_data_flag))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> VTDataRequest:
        """Decode VT-Data-Request from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        tag, offset = decode_tag(data, offset)
        session_id = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        tag, offset = decode_tag(data, offset)
        vt_new_data = decode_octet_string(data[offset : offset + tag.length])
        offset += tag.length

        # Application-tagged boolean: value is in the tag L/V/T field
        tag, offset = decode_tag(data, offset)
        vt_data_flag = tag.is_boolean_true

        return cls(
            vt_session_identifier=session_id,
            vt_new_data=vt_new_data,
            vt_data_flag=vt_data_flag,
        )


@dataclass(frozen=True, slots=True)
class VTDataACK:
    """VT-Data-ACK (Clause 17.3.2).

    ::

        VT-Data-ACK ::= SEQUENCE {
            allNewDataAccepted  BOOLEAN,
            acceptedOctetCount  Unsigned OPTIONAL
        }

    ``accepted_octet_count`` is present only when
    ``all_new_data_accepted`` is ``False``.
    """

    all_new_data_accepted: bool
    accepted_octet_count: int | None = None

    def encode(self) -> bytes:
        """Encode VT-Data-ACK service parameters."""
        buf = bytearray()
        buf.extend(encode_application_boolean(self.all_new_data_accepted))
        if not self.all_new_data_accepted and self.accepted_octet_count is not None:
            buf.extend(encode_application_unsigned(self.accepted_octet_count))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> VTDataACK:
        """Decode VT-Data-ACK from service request bytes."""
        data = as_memoryview(data)
        offset = 0

        # Application-tagged boolean: value is in the tag L/V/T field
        tag, offset = decode_tag(data, offset)
        all_accepted = tag.is_boolean_true

        accepted_count = None
        if offset < len(data):
            tag, offset = decode_tag(data, offset)
            accepted_count = decode_unsigned(data[offset : offset + tag.length])

        return cls(
            all_new_data_accepted=all_accepted,
            accepted_octet_count=accepted_count,
        )
