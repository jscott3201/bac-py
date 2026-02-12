"""BACnet audit constructed types per ASHRAE 135-2020 Clause 19.6.

BACnetAuditNotification (Table 19-4), BACnetAuditLogRecord,
AuditQueryByTarget, AuditQueryBySource.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_object_identifier,
    decode_unsigned,
    encode_character_string,
    encode_context_enumerated,
    encode_context_object_id,
    encode_context_octet_string,
    encode_context_tagged,
    encode_context_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
)
from bac_py.types.enums import AuditOperation, ObjectType
from bac_py.types.primitives import ObjectIdentifier


@dataclass(frozen=True, slots=True)
class BACnetAuditNotification:
    """BACnetAuditNotification per Table 19-4 (pp. 821-822).

    ::

        BACnetAuditNotification ::= SEQUENCE {
            source-timestamp      [0] BACnetTimeStamp OPTIONAL,
            target-timestamp      [1] BACnetTimeStamp OPTIONAL,
            source-device         [2] BACnetRecipient OPTIONAL,
            source-object         [3] BACnetObjectIdentifier OPTIONAL,
            operation             [4] BACnetAuditOperation,
            source-comment        [5] CharacterString OPTIONAL,
            target-comment        [6] CharacterString OPTIONAL,
            invoke-id             [7] Unsigned8 OPTIONAL,
            source-user-id        [8] Unsigned16 OPTIONAL,
            source-user-role      [9] Unsigned8 OPTIONAL,
            target-device         [10] BACnetRecipient OPTIONAL,
            target-object         [11] BACnetObjectIdentifier OPTIONAL,
            target-property       [12] BACnetPropertyReference OPTIONAL,
            target-priority       [13] Unsigned (1..16) OPTIONAL,
            target-value          [14] ABSTRACT-SYNTAX.&Type OPTIONAL,
            current-value         [15] ABSTRACT-SYNTAX.&Type OPTIONAL,
            result                [16] Error OPTIONAL,
        }
    """

    operation: AuditOperation = AuditOperation.GENERAL
    source_device: ObjectIdentifier | None = None
    source_object: ObjectIdentifier | None = None
    source_comment: str | None = None
    target_comment: str | None = None
    invoke_id: int | None = None
    source_user_id: int | None = None
    source_user_role: int | None = None
    target_device: ObjectIdentifier | None = None
    target_object: ObjectIdentifier | None = None
    target_property: int | None = None
    target_array_index: int | None = None
    target_priority: int | None = None
    target_value: bytes | None = None
    current_value: bytes | None = None
    result_error_class: int | None = None
    result_error_code: int | None = None

    def encode(self) -> bytes:
        """Encode BACnetAuditNotification to ASN.1 bytes."""
        buf = bytearray()
        # [0] source-timestamp OPTIONAL -- omitted (simplified)
        # [1] target-timestamp OPTIONAL -- omitted (simplified)
        # [2] source-device OPTIONAL (simplified as ObjectIdentifier)
        if self.source_device is not None:
            buf.extend(encode_opening_tag(2))
            # BACnetRecipient CHOICE: [1] device
            buf.extend(encode_context_object_id(1, self.source_device))
            buf.extend(encode_closing_tag(2))
        # [3] source-object OPTIONAL
        if self.source_object is not None:
            buf.extend(encode_context_object_id(3, self.source_object))
        # [4] operation
        buf.extend(encode_context_enumerated(4, self.operation))
        # [5] source-comment OPTIONAL
        if self.source_comment is not None:
            buf.extend(encode_context_tagged(5, encode_character_string(self.source_comment)))
        # [6] target-comment OPTIONAL
        if self.target_comment is not None:
            buf.extend(encode_context_tagged(6, encode_character_string(self.target_comment)))
        # [7] invoke-id OPTIONAL
        if self.invoke_id is not None:
            buf.extend(encode_context_unsigned(7, self.invoke_id))
        # [8] source-user-id OPTIONAL
        if self.source_user_id is not None:
            buf.extend(encode_context_unsigned(8, self.source_user_id))
        # [9] source-user-role OPTIONAL
        if self.source_user_role is not None:
            buf.extend(encode_context_unsigned(9, self.source_user_role))
        # [10] target-device OPTIONAL (simplified as ObjectIdentifier)
        if self.target_device is not None:
            buf.extend(encode_opening_tag(10))
            buf.extend(encode_context_object_id(1, self.target_device))
            buf.extend(encode_closing_tag(10))
        # [11] target-object OPTIONAL
        if self.target_object is not None:
            buf.extend(encode_context_object_id(11, self.target_object))
        # [12] target-property OPTIONAL (BACnetPropertyReference)
        if self.target_property is not None:
            buf.extend(encode_opening_tag(12))
            buf.extend(encode_context_unsigned(0, self.target_property))
            if self.target_array_index is not None:
                buf.extend(encode_context_unsigned(1, self.target_array_index))
            buf.extend(encode_closing_tag(12))
        # [13] target-priority OPTIONAL
        if self.target_priority is not None:
            buf.extend(encode_context_unsigned(13, self.target_priority))
        # [14] target-value OPTIONAL (raw encoded)
        if self.target_value is not None:
            buf.extend(encode_opening_tag(14))
            buf.extend(self.target_value)
            buf.extend(encode_closing_tag(14))
        # [15] current-value OPTIONAL (raw encoded)
        if self.current_value is not None:
            buf.extend(encode_opening_tag(15))
            buf.extend(self.current_value)
            buf.extend(encode_closing_tag(15))
        # [16] result OPTIONAL (Error: error-class, error-code)
        if self.result_error_class is not None and self.result_error_code is not None:
            buf.extend(encode_opening_tag(16))
            buf.extend(encode_context_enumerated(0, self.result_error_class))
            buf.extend(encode_context_enumerated(1, self.result_error_code))
            buf.extend(encode_closing_tag(16))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode BACnetAuditNotification from ASN.1 bytes."""
        data = as_memoryview(data)
        offset = 0
        source_device = None
        source_object = None
        operation = AuditOperation.GENERAL
        source_comment = None
        target_comment = None
        invoke_id = None
        source_user_id = None
        source_user_role = None
        target_device = None
        target_object = None
        target_property = None
        target_array_index = None
        target_priority = None
        target_value = None
        current_value = None
        result_error_class = None
        result_error_code = None

        while offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls != TagClass.CONTEXT:
                offset = new_offset + tag.length
                continue

            if tag.number == 0 and tag.is_opening:
                # [0] source-timestamp -- skip constructed
                depth = 1
                offset = new_offset
                while depth > 0 and offset < len(data):
                    t, offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                    elif t.is_closing:
                        depth -= 1
                    elif not t.is_opening and not t.is_closing:
                        offset += t.length
            elif tag.number == 1 and tag.is_opening:
                # [1] target-timestamp -- skip constructed
                depth = 1
                offset = new_offset
                while depth > 0 and offset < len(data):
                    t, offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                    elif t.is_closing:
                        depth -= 1
                    elif not t.is_opening and not t.is_closing:
                        offset += t.length
            elif tag.number == 2 and tag.is_opening:
                # [2] source-device (BACnetRecipient CHOICE)
                offset = new_offset
                inner_tag, offset = decode_tag(data, offset)
                if inner_tag.number == 1:  # device OID
                    obj_type, instance = decode_object_identifier(
                        data[offset : offset + inner_tag.length]
                    )
                    source_device = ObjectIdentifier(ObjectType(obj_type), instance)
                    offset += inner_tag.length
                else:
                    offset += inner_tag.length
                # closing tag
                _closing, offset = decode_tag(data, offset)
            elif tag.number == 3 and not tag.is_opening:
                # [3] source-object
                obj_type, instance = decode_object_identifier(
                    data[new_offset : new_offset + tag.length]
                )
                source_object = ObjectIdentifier(ObjectType(obj_type), instance)
                offset = new_offset + tag.length
            elif tag.number == 4 and not tag.is_opening:
                # [4] operation
                operation = AuditOperation(
                    decode_unsigned(data[new_offset : new_offset + tag.length])
                )
                offset = new_offset + tag.length
            elif tag.number == 5 and not tag.is_opening:
                # [5] source-comment
                source_comment = decode_character_string(
                    data[new_offset : new_offset + tag.length]
                )
                offset = new_offset + tag.length
            elif tag.number == 6 and not tag.is_opening:
                # [6] target-comment
                target_comment = decode_character_string(
                    data[new_offset : new_offset + tag.length]
                )
                offset = new_offset + tag.length
            elif tag.number == 7 and not tag.is_opening:
                # [7] invoke-id
                invoke_id = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 8 and not tag.is_opening:
                # [8] source-user-id
                source_user_id = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 9 and not tag.is_opening:
                # [9] source-user-role
                source_user_role = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 10 and tag.is_opening:
                # [10] target-device (BACnetRecipient CHOICE)
                offset = new_offset
                inner_tag, offset = decode_tag(data, offset)
                if inner_tag.number == 1:  # device OID
                    obj_type, instance = decode_object_identifier(
                        data[offset : offset + inner_tag.length]
                    )
                    target_device = ObjectIdentifier(ObjectType(obj_type), instance)
                    offset += inner_tag.length
                else:
                    offset += inner_tag.length
                _closing, offset = decode_tag(data, offset)
            elif tag.number == 11 and not tag.is_opening:
                # [11] target-object
                obj_type, instance = decode_object_identifier(
                    data[new_offset : new_offset + tag.length]
                )
                target_object = ObjectIdentifier(ObjectType(obj_type), instance)
                offset = new_offset + tag.length
            elif tag.number == 12 and tag.is_opening:
                # [12] target-property (BACnetPropertyReference)
                offset = new_offset
                inner_tag, offset = decode_tag(data, offset)
                target_property = decode_unsigned(data[offset : offset + inner_tag.length])
                offset += inner_tag.length
                # optional array-index [1]
                if offset < len(data):
                    peek_tag, peek_offset = decode_tag(data, offset)
                    if (
                        peek_tag.cls == TagClass.CONTEXT
                        and peek_tag.number == 1
                        and not peek_tag.is_closing
                    ):
                        target_array_index = decode_unsigned(
                            data[peek_offset : peek_offset + peek_tag.length]
                        )
                        offset = peek_offset + peek_tag.length
                _closing, offset = decode_tag(data, offset)
            elif tag.number == 13 and not tag.is_opening:
                # [13] target-priority
                target_priority = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 14 and tag.is_opening:
                # [14] target-value (raw)
                offset = new_offset
                value_start = offset
                depth = 1
                while depth > 0 and offset < len(data):
                    t, t_offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                        offset = t_offset
                    elif t.is_closing:
                        depth -= 1
                        if depth == 0:
                            target_value = bytes(data[value_start:offset])
                            offset = t_offset
                        else:
                            offset = t_offset
                    else:
                        offset = t_offset + t.length
            elif tag.number == 15 and tag.is_opening:
                # [15] current-value (raw)
                offset = new_offset
                value_start = offset
                depth = 1
                while depth > 0 and offset < len(data):
                    t, t_offset = decode_tag(data, offset)
                    if t.is_opening:
                        depth += 1
                        offset = t_offset
                    elif t.is_closing:
                        depth -= 1
                        if depth == 0:
                            current_value = bytes(data[value_start:offset])
                            offset = t_offset
                        else:
                            offset = t_offset
                    else:
                        offset = t_offset + t.length
            elif tag.number == 16 and tag.is_opening:
                # [16] result (Error)
                offset = new_offset
                err_tag, offset = decode_tag(data, offset)
                result_error_class = decode_unsigned(data[offset : offset + err_tag.length])
                offset += err_tag.length
                err_tag, offset = decode_tag(data, offset)
                result_error_code = decode_unsigned(data[offset : offset + err_tag.length])
                offset += err_tag.length
                _closing, offset = decode_tag(data, offset)
            else:
                # Unknown tag -- skip
                if tag.is_opening:
                    depth = 1
                    offset = new_offset
                    while depth > 0 and offset < len(data):
                        t, offset = decode_tag(data, offset)
                        if t.is_opening:
                            depth += 1
                        elif t.is_closing:
                            depth -= 1
                        elif not t.is_opening and not t.is_closing:
                            offset += t.length
                else:
                    offset = new_offset + tag.length

        return cls(
            operation=operation,
            source_device=source_device,
            source_object=source_object,
            source_comment=source_comment,
            target_comment=target_comment,
            invoke_id=invoke_id,
            source_user_id=source_user_id,
            source_user_role=source_user_role,
            target_device=target_device,
            target_object=target_object,
            target_property=target_property,
            target_array_index=target_array_index,
            target_priority=target_priority,
            target_value=target_value,
            current_value=current_value,
            result_error_class=result_error_class,
            result_error_code=result_error_code,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        Optional fields are omitted when ``None``.

        :returns: Dictionary with audit notification fields.
        """
        result: dict[str, Any] = {
            "operation": int(self.operation),
        }
        if self.source_device is not None:
            result["source_device"] = self.source_device.to_dict()
        if self.source_object is not None:
            result["source_object"] = self.source_object.to_dict()
        if self.source_comment is not None:
            result["source_comment"] = self.source_comment
        if self.target_comment is not None:
            result["target_comment"] = self.target_comment
        if self.invoke_id is not None:
            result["invoke_id"] = self.invoke_id
        if self.source_user_id is not None:
            result["source_user_id"] = self.source_user_id
        if self.source_user_role is not None:
            result["source_user_role"] = self.source_user_role
        if self.target_device is not None:
            result["target_device"] = self.target_device.to_dict()
        if self.target_object is not None:
            result["target_object"] = self.target_object.to_dict()
        if self.target_property is not None:
            result["target_property"] = self.target_property
        if self.target_array_index is not None:
            result["target_array_index"] = self.target_array_index
        if self.target_priority is not None:
            result["target_priority"] = self.target_priority
        if self.target_value is not None:
            result["target_value"] = self.target_value.hex()
        if self.current_value is not None:
            result["current_value"] = self.current_value.hex()
        if self.result_error_class is not None:
            result["result_error_class"] = self.result_error_class
        if self.result_error_code is not None:
            result["result_error_code"] = self.result_error_code
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetAuditNotification:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with audit notification fields.
        :returns: Decoded :class:`BACnetAuditNotification` instance.
        """
        source_device = None
        if "source_device" in data:
            source_device = ObjectIdentifier.from_dict(data["source_device"])
        source_object = None
        if "source_object" in data:
            source_object = ObjectIdentifier.from_dict(data["source_object"])
        target_device = None
        if "target_device" in data:
            target_device = ObjectIdentifier.from_dict(data["target_device"])
        target_object = None
        if "target_object" in data:
            target_object = ObjectIdentifier.from_dict(data["target_object"])
        target_value = None
        if "target_value" in data:
            target_value = bytes.fromhex(data["target_value"])
        current_value = None
        if "current_value" in data:
            current_value = bytes.fromhex(data["current_value"])
        return cls(
            operation=AuditOperation(data["operation"]),
            source_device=source_device,
            source_object=source_object,
            source_comment=data.get("source_comment"),
            target_comment=data.get("target_comment"),
            invoke_id=data.get("invoke_id"),
            source_user_id=data.get("source_user_id"),
            source_user_role=data.get("source_user_role"),
            target_device=target_device,
            target_object=target_object,
            target_property=data.get("target_property"),
            target_array_index=data.get("target_array_index"),
            target_priority=data.get("target_priority"),
            target_value=target_value,
            current_value=current_value,
            result_error_class=data.get("result_error_class"),
            result_error_code=data.get("result_error_code"),
        )


@dataclass(frozen=True, slots=True)
class BACnetAuditLogRecord:
    """Wrapper combining a sequence number with an audit notification."""

    sequence_number: int
    notification: BACnetAuditNotification

    def encode(self) -> bytes:
        """Encode BACnetAuditLogRecord."""
        buf = bytearray()
        # [0] sequence-number (Unsigned64)
        buf.extend(encode_context_unsigned(0, self.sequence_number))
        # [1] notification (constructed)
        buf.extend(encode_opening_tag(1))
        buf.extend(self.notification.encode())
        buf.extend(encode_closing_tag(1))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode BACnetAuditLogRecord."""
        data = as_memoryview(data)
        offset = 0

        # [0] sequence-number
        tag, offset = decode_tag(data, offset)
        sequence_number = decode_unsigned(data[offset : offset + tag.length])
        offset += tag.length

        # [1] notification (constructed)
        _opening, offset = decode_tag(data, offset)  # opening tag 1
        # Collect inner bytes until closing tag 1
        inner_start = offset
        depth = 1
        while depth > 0 and offset < len(data):
            t, t_offset = decode_tag(data, offset)
            if t.is_opening:
                depth += 1
                offset = t_offset
            elif t.is_closing:
                depth -= 1
                if depth == 0:
                    inner_end = offset
                    offset = t_offset
                else:
                    offset = t_offset
            else:
                offset = t_offset + t.length

        notification = BACnetAuditNotification.decode(data[inner_start:inner_end])
        return cls(sequence_number=sequence_number, notification=notification)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary.

        :returns: Dictionary with ``"sequence_number"`` and ``"notification"`` keys.
        """
        return {
            "sequence_number": self.sequence_number,
            "notification": self.notification.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetAuditLogRecord:
        """Reconstruct from a JSON-friendly dictionary.

        :param data: Dictionary with ``"sequence_number"`` and ``"notification"`` keys.
        :returns: Decoded :class:`BACnetAuditLogRecord` instance.
        """
        return cls(
            sequence_number=data["sequence_number"],
            notification=BACnetAuditNotification.from_dict(data["notification"]),
        )


@dataclass(frozen=True, slots=True)
class AuditQueryByTarget:
    """Query parameters for AuditLogQuery by target (Clause 13.19)."""

    target_device_identifier: ObjectIdentifier
    target_device_address: bytes | None = None
    target_object_identifier: ObjectIdentifier | None = None
    target_property_identifier: int | None = None
    target_array_index: int | None = None
    target_priority: int | None = None
    operations: int | None = None
    result_filter: int = 0

    def encode(self) -> bytes:
        """Encode AuditQueryByTarget."""
        buf = bytearray()
        # [0] target-device-identifier
        buf.extend(encode_context_object_id(0, self.target_device_identifier))
        # [1] target-device-address OPTIONAL
        if self.target_device_address is not None:
            buf.extend(encode_context_octet_string(1, self.target_device_address))
        # [2] target-object-identifier OPTIONAL
        if self.target_object_identifier is not None:
            buf.extend(encode_context_object_id(2, self.target_object_identifier))
        # [3] target-property-identifier OPTIONAL
        if self.target_property_identifier is not None:
            buf.extend(encode_context_unsigned(3, self.target_property_identifier))
        # [4] target-array-index OPTIONAL
        if self.target_array_index is not None:
            buf.extend(encode_context_unsigned(4, self.target_array_index))
        # [5] target-priority OPTIONAL
        if self.target_priority is not None:
            buf.extend(encode_context_unsigned(5, self.target_priority))
        # [6] operations OPTIONAL (BACnetAuditOperationFlags bitstring as unsigned)
        if self.operations is not None:
            buf.extend(encode_context_unsigned(6, self.operations))
        # [7] result-filter
        buf.extend(encode_context_enumerated(7, self.result_filter))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode AuditQueryByTarget."""
        data = as_memoryview(data)
        offset = 0

        # [0] target-device-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        target_device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        target_device_address = None
        target_object_identifier = None
        target_property_identifier = None
        target_array_index = None
        target_priority = None
        operations = None
        result_filter = 0

        while offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls != TagClass.CONTEXT:
                break

            if tag.number == 1:
                target_device_address = bytes(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 2:
                obj_type, instance = decode_object_identifier(
                    data[new_offset : new_offset + tag.length]
                )
                target_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
                offset = new_offset + tag.length
            elif tag.number == 3:
                target_property_identifier = decode_unsigned(
                    data[new_offset : new_offset + tag.length]
                )
                offset = new_offset + tag.length
            elif tag.number == 4:
                target_array_index = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 5:
                target_priority = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 6:
                operations = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 7:
                result_filter = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            else:
                break

        return cls(
            target_device_identifier=target_device_identifier,
            target_device_address=target_device_address,
            target_object_identifier=target_object_identifier,
            target_property_identifier=target_property_identifier,
            target_array_index=target_array_index,
            target_priority=target_priority,
            operations=operations,
            result_filter=result_filter,
        )


@dataclass(frozen=True, slots=True)
class AuditQueryBySource:
    """Query parameters for AuditLogQuery by source (Clause 13.19)."""

    source_device_identifier: ObjectIdentifier
    source_device_address: bytes | None = None
    source_object_identifier: ObjectIdentifier | None = None
    operations: int | None = None
    result_filter: int = 0

    def encode(self) -> bytes:
        """Encode AuditQueryBySource."""
        buf = bytearray()
        # [0] source-device-identifier
        buf.extend(encode_context_object_id(0, self.source_device_identifier))
        # [1] source-device-address OPTIONAL
        if self.source_device_address is not None:
            buf.extend(encode_context_octet_string(1, self.source_device_address))
        # [2] source-object-identifier OPTIONAL
        if self.source_object_identifier is not None:
            buf.extend(encode_context_object_id(2, self.source_object_identifier))
        # [3] operations OPTIONAL
        if self.operations is not None:
            buf.extend(encode_context_unsigned(3, self.operations))
        # [4] result-filter
        buf.extend(encode_context_enumerated(4, self.result_filter))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode AuditQueryBySource."""
        data = as_memoryview(data)
        offset = 0

        # [0] source-device-identifier
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        source_device_identifier = ObjectIdentifier(ObjectType(obj_type), instance)

        source_device_address = None
        source_object_identifier = None
        operations = None
        result_filter = 0

        while offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls != TagClass.CONTEXT:
                break

            if tag.number == 1:
                source_device_address = bytes(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 2:
                obj_type, instance = decode_object_identifier(
                    data[new_offset : new_offset + tag.length]
                )
                source_object_identifier = ObjectIdentifier(ObjectType(obj_type), instance)
                offset = new_offset + tag.length
            elif tag.number == 3:
                operations = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            elif tag.number == 4:
                result_filter = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            else:
                break

        return cls(
            source_device_identifier=source_device_identifier,
            source_device_address=source_device_address,
            source_object_identifier=source_object_identifier,
            operations=operations,
            result_filter=result_filter,
        )
