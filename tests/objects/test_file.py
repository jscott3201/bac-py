"""Tests for BACnet File object."""

import pytest

from bac_py.objects.file import FileObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import FileAccessMethod, ObjectType, PropertyIdentifier


class TestFileObjectCreation:
    def test_stream_file_creation(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        assert f.object_identifier.object_type == ObjectType.FILE
        assert f.object_identifier.instance_number == 1
        assert (
            f.read_property(PropertyIdentifier.FILE_ACCESS_METHOD)
            == FileAccessMethod.STREAM_ACCESS
        )
        assert f.read_property(PropertyIdentifier.FILE_SIZE) == 0

    def test_record_file_creation(self):
        f = FileObject(2, file_access_method=FileAccessMethod.RECORD_ACCESS)
        assert (
            f.read_property(PropertyIdentifier.FILE_ACCESS_METHOD)
            == FileAccessMethod.RECORD_ACCESS
        )
        assert f.read_property(PropertyIdentifier.FILE_SIZE) == 0

    def test_default_properties(self):
        f = FileObject(1)
        assert f.read_property(PropertyIdentifier.FILE_TYPE) == ""
        assert f.read_property(PropertyIdentifier.ARCHIVE) is False
        assert f.read_property(PropertyIdentifier.READ_ONLY) is False

    def test_custom_name(self):
        f = FileObject(1, object_name="config.txt")
        assert f.read_property(PropertyIdentifier.OBJECT_NAME) == "config.txt"


class TestStreamAccess:
    def test_write_and_read(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"Hello BACnet")
        data, eof = f.read_stream(0, 100)
        assert data == b"Hello BACnet"
        assert eof is True
        assert f.read_property(PropertyIdentifier.FILE_SIZE) == 12

    def test_read_partial(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"Hello BACnet")
        data, eof = f.read_stream(0, 5)
        assert data == b"Hello"
        assert eof is False

    def test_write_overwrite(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"Hello BACnet")
        f.write_stream(6, b"World!")
        data, eof = f.read_stream(0, 100)
        assert data == b"Hello World!"

    def test_write_append(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"Hello ")
        start = f.write_stream(-1, b"BACnet")
        assert start == 6
        data, eof = f.read_stream(0, 100)
        assert data == b"Hello BACnet"

    def test_write_beyond_eof_pads_zeros(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"AB")
        f.write_stream(5, b"CD")
        data, eof = f.read_stream(0, 100)
        assert data == b"AB\x00\x00\x00CD"
        assert f.read_property(PropertyIdentifier.FILE_SIZE) == 7

    def test_read_empty_file(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        data, eof = f.read_stream(0, 100)
        assert data == b""
        assert eof is True

    def test_stream_on_record_file_raises(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        with pytest.raises(BACnetError):
            f.read_stream(0, 10)

    def test_write_stream_on_record_file_raises(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        with pytest.raises(BACnetError):
            f.write_stream(0, b"data")

    def test_write_read_only_raises(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS, read_only=True)
        with pytest.raises(BACnetError):
            f.write_stream(0, b"data")


class TestRecordAccess:
    def test_write_and_read(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        f.write_records(0, [b"rec1", b"rec2", b"rec3"])
        records, eof = f.read_records(0, 10)
        assert records == [b"rec1", b"rec2", b"rec3"]
        assert eof is True
        assert f.read_property(PropertyIdentifier.FILE_SIZE) == 3

    def test_read_partial_records(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        f.write_records(0, [b"rec1", b"rec2", b"rec3"])
        records, eof = f.read_records(0, 2)
        assert records == [b"rec1", b"rec2"]
        assert eof is False

    def test_append_records(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        f.write_records(0, [b"rec1", b"rec2"])
        start = f.write_records(-1, [b"rec3", b"rec4"])
        assert start == 2
        records, eof = f.read_records(0, 10)
        assert records == [b"rec1", b"rec2", b"rec3", b"rec4"]

    def test_overwrite_records(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        f.write_records(0, [b"rec1", b"rec2", b"rec3"])
        f.write_records(1, [b"new2"])
        records, eof = f.read_records(0, 10)
        assert records == [b"rec1", b"new2", b"rec3"]

    def test_read_empty_records(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        records, eof = f.read_records(0, 10)
        assert records == []
        assert eof is True

    def test_record_on_stream_file_raises(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        with pytest.raises(BACnetError):
            f.read_records(0, 10)

    def test_write_records_on_stream_file_raises(self):
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        with pytest.raises(BACnetError):
            f.write_records(0, [b"data"])

    def test_write_records_read_only_raises(self):
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS, read_only=True)
        with pytest.raises(BACnetError):
            f.write_records(0, [b"data"])
