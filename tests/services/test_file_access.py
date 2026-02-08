"""Tests for atomic file access services."""

from bac_py.services.file_access import (
    AtomicReadFileACK,
    AtomicReadFileRequest,
    AtomicWriteFileACK,
    AtomicWriteFileRequest,
    RecordReadAccess,
    RecordReadACK,
    RecordWriteAccess,
    StreamReadAccess,
    StreamReadACK,
    StreamWriteAccess,
)
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestAtomicReadFileRequest:
    def test_stream_access_round_trip(self):
        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamReadAccess(file_start_position=0, requested_octet_count=100),
        )
        encoded = request.encode()
        decoded = AtomicReadFileRequest.decode(encoded)
        assert decoded.file_identifier == ObjectIdentifier(ObjectType.FILE, 1)
        assert isinstance(decoded.access_method, StreamReadAccess)
        assert decoded.access_method.file_start_position == 0
        assert decoded.access_method.requested_octet_count == 100

    def test_record_access_round_trip(self):
        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 2),
            access_method=RecordReadAccess(file_start_record=5, requested_record_count=10),
        )
        encoded = request.encode()
        decoded = AtomicReadFileRequest.decode(encoded)
        assert decoded.file_identifier == ObjectIdentifier(ObjectType.FILE, 2)
        assert isinstance(decoded.access_method, RecordReadAccess)
        assert decoded.access_method.file_start_record == 5
        assert decoded.access_method.requested_record_count == 10

    def test_negative_start_position(self):
        """Negative file position for append mode."""
        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamReadAccess(file_start_position=-1, requested_octet_count=50),
        )
        encoded = request.encode()
        decoded = AtomicReadFileRequest.decode(encoded)
        assert decoded.access_method.file_start_position == -1


class TestAtomicReadFileACK:
    def test_stream_ack_round_trip(self):
        ack = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(file_start_position=0, file_data=b"Hello BACnet"),
        )
        encoded = ack.encode()
        decoded = AtomicReadFileACK.decode(encoded)
        assert decoded.end_of_file is True
        assert isinstance(decoded.access_method, StreamReadACK)
        assert decoded.access_method.file_start_position == 0
        assert decoded.access_method.file_data == b"Hello BACnet"

    def test_record_ack_round_trip(self):
        records = [b"record1", b"record2", b"record3"]
        ack = AtomicReadFileACK(
            end_of_file=False,
            access_method=RecordReadACK(
                file_start_record=0,
                returned_record_count=3,
                file_record_data=records,
            ),
        )
        encoded = ack.encode()
        decoded = AtomicReadFileACK.decode(encoded)
        assert decoded.end_of_file is False
        assert isinstance(decoded.access_method, RecordReadACK)
        assert decoded.access_method.file_start_record == 0
        assert decoded.access_method.returned_record_count == 3
        assert decoded.access_method.file_record_data == records

    def test_stream_ack_empty_data(self):
        ack = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(file_start_position=0, file_data=b""),
        )
        encoded = ack.encode()
        decoded = AtomicReadFileACK.decode(encoded)
        assert decoded.access_method.file_data == b""

    def test_record_ack_no_records(self):
        ack = AtomicReadFileACK(
            end_of_file=True,
            access_method=RecordReadACK(
                file_start_record=0,
                returned_record_count=0,
                file_record_data=[],
            ),
        )
        encoded = ack.encode()
        decoded = AtomicReadFileACK.decode(encoded)
        assert decoded.access_method.returned_record_count == 0
        assert decoded.access_method.file_record_data == []


class TestAtomicWriteFileRequest:
    def test_stream_write_round_trip(self):
        request = AtomicWriteFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamWriteAccess(
                file_start_position=100,
                file_data=b"new data",
            ),
        )
        encoded = request.encode()
        decoded = AtomicWriteFileRequest.decode(encoded)
        assert decoded.file_identifier == ObjectIdentifier(ObjectType.FILE, 1)
        assert isinstance(decoded.access_method, StreamWriteAccess)
        assert decoded.access_method.file_start_position == 100
        assert decoded.access_method.file_data == b"new data"

    def test_record_write_round_trip(self):
        records = [b"rec1", b"rec2"]
        request = AtomicWriteFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 3),
            access_method=RecordWriteAccess(
                file_start_record=0,
                record_count=2,
                file_record_data=records,
            ),
        )
        encoded = request.encode()
        decoded = AtomicWriteFileRequest.decode(encoded)
        assert isinstance(decoded.access_method, RecordWriteAccess)
        assert decoded.access_method.file_start_record == 0
        assert decoded.access_method.record_count == 2
        assert decoded.access_method.file_record_data == records

    def test_negative_start_position_append(self):
        """Negative file start position for append."""
        request = AtomicWriteFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamWriteAccess(
                file_start_position=-1,
                file_data=b"append data",
            ),
        )
        encoded = request.encode()
        decoded = AtomicWriteFileRequest.decode(encoded)
        assert decoded.access_method.file_start_position == -1


class TestAtomicWriteFileACK:
    def test_stream_ack_round_trip(self):
        ack = AtomicWriteFileACK(is_stream=True, file_start=100)
        encoded = ack.encode()
        decoded = AtomicWriteFileACK.decode(encoded)
        assert decoded.is_stream is True
        assert decoded.file_start == 100

    def test_record_ack_round_trip(self):
        ack = AtomicWriteFileACK(is_stream=False, file_start=5)
        encoded = ack.encode()
        decoded = AtomicWriteFileACK.decode(encoded)
        assert decoded.is_stream is False
        assert decoded.file_start == 5

    def test_negative_start(self):
        ack = AtomicWriteFileACK(is_stream=True, file_start=-1)
        encoded = ack.encode()
        decoded = AtomicWriteFileACK.decode(encoded)
        assert decoded.file_start == -1
