"""BACnet File object type per ASHRAE 135-2016 Clause 12.13."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
)
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    ErrorClass,
    ErrorCode,
    FileAccessMethod,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class FileObject(BACnetObject):
    """BACnet File object (Clause 12.13).

    Represents a file accessible via AtomicReadFile/AtomicWriteFile.
    Supports both stream and record access methods.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.FILE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.FILE_TYPE: PropertyDefinition(
            PropertyIdentifier.FILE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
            default="",
        ),
        PropertyIdentifier.FILE_SIZE: PropertyDefinition(
            PropertyIdentifier.FILE_SIZE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.MODIFICATION_DATE: PropertyDefinition(
            PropertyIdentifier.MODIFICATION_DATE,
            tuple,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.ARCHIVE: PropertyDefinition(
            PropertyIdentifier.ARCHIVE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
        PropertyIdentifier.READ_ONLY: PropertyDefinition(
            PropertyIdentifier.READ_ONLY,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.FILE_ACCESS_METHOD: PropertyDefinition(
            PropertyIdentifier.FILE_ACCESS_METHOD,
            FileAccessMethod,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
    }

    def __init__(
        self,
        instance_number: int,
        *,
        file_access_method: FileAccessMethod = FileAccessMethod.STREAM_ACCESS,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        self._properties[PropertyIdentifier.FILE_ACCESS_METHOD] = file_access_method

        # Internal storage
        self._file_data: bytes = b""
        self._record_data: list[bytes] = []

        self._update_file_size()

    def _update_file_size(self) -> None:
        """Update the FILE_SIZE property based on current data."""
        access_method = self._properties[PropertyIdentifier.FILE_ACCESS_METHOD]
        if access_method == FileAccessMethod.STREAM_ACCESS:
            self._properties[PropertyIdentifier.FILE_SIZE] = len(self._file_data)
        else:
            self._properties[PropertyIdentifier.FILE_SIZE] = len(self._record_data)

    def read_stream(self, start: int, count: int) -> tuple[bytes, bool]:
        """Read stream data from the file.

        Args:
            start: Starting byte position.
            count: Number of bytes to read.

        Returns:
            Tuple of (data, end_of_file).

        Raises:
            BACnetError: If access method is not stream.
        """
        if (
            self._properties[PropertyIdentifier.FILE_ACCESS_METHOD]
            != FileAccessMethod.STREAM_ACCESS
        ):
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.INVALID_FILE_ACCESS_METHOD)

        data = self._file_data[start : start + count]
        end_of_file = (start + count) >= len(self._file_data)
        return data, end_of_file

    def write_stream(self, start: int, data: bytes) -> int:
        """Write stream data to the file.

        Args:
            start: Starting byte position. Use -1 to append.
            data: Data to write.

        Returns:
            The actual file start position used.

        Raises:
            BACnetError: If access method is not stream or file is read-only.
        """
        if (
            self._properties[PropertyIdentifier.FILE_ACCESS_METHOD]
            != FileAccessMethod.STREAM_ACCESS
        ):
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.INVALID_FILE_ACCESS_METHOD)
        if self._properties.get(PropertyIdentifier.READ_ONLY):
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.FILE_ACCESS_DENIED)

        if start < 0:
            start = len(self._file_data)

        # Pad with zeros if start is beyond current data
        if start > len(self._file_data):
            self._file_data += b"\x00" * (start - len(self._file_data))

        # Overwrite from start position
        before = self._file_data[:start]
        after_end = start + len(data)
        after = self._file_data[after_end:] if after_end < len(self._file_data) else b""
        self._file_data = before + data + after
        self._update_file_size()
        return start

    def read_records(self, start: int, count: int) -> tuple[list[bytes], bool]:
        """Read records from the file.

        Args:
            start: Starting record index.
            count: Number of records to read.

        Returns:
            Tuple of (records, end_of_file).

        Raises:
            BACnetError: If access method is not record.
        """
        if (
            self._properties[PropertyIdentifier.FILE_ACCESS_METHOD]
            != FileAccessMethod.RECORD_ACCESS
        ):
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.INVALID_FILE_ACCESS_METHOD)

        records = self._record_data[start : start + count]
        end_of_file = (start + count) >= len(self._record_data)
        return records, end_of_file

    def write_records(self, start: int, records: list[bytes]) -> int:
        """Write records to the file.

        Args:
            start: Starting record index. Use -1 to append.
            records: Records to write.

        Returns:
            The actual file start record used.

        Raises:
            BACnetError: If access method is not record or file is read-only.
        """
        if (
            self._properties[PropertyIdentifier.FILE_ACCESS_METHOD]
            != FileAccessMethod.RECORD_ACCESS
        ):
            raise BACnetError(ErrorClass.SERVICES, ErrorCode.INVALID_FILE_ACCESS_METHOD)
        if self._properties.get(PropertyIdentifier.READ_ONLY):
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.FILE_ACCESS_DENIED)

        if start < 0:
            start = len(self._record_data)

        # Extend list if start is beyond current records
        while start > len(self._record_data):
            self._record_data.append(b"")

        # Overwrite/insert records
        for i, record in enumerate(records):
            idx = start + i
            if idx < len(self._record_data):
                self._record_data[idx] = record
            else:
                self._record_data.append(record)

        self._update_file_size()
        return start
