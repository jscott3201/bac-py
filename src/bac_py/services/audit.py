"""Audit services per ASHRAE 135-2020 Clauses 13.19-13.21.

AuditLogQuery (Clause 13.19), ConfirmedAuditNotification (Clause 13.20),
UnconfirmedAuditNotification (Clause 13.21).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Self

from bac_py.encoding.primitives import (
    decode_object_identifier,
    decode_unsigned,
    decode_unsigned64,
    encode_context_boolean,
    encode_context_object_id,
    encode_context_tagged,
    encode_context_unsigned,
    encode_unsigned64,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
)
from bac_py.types.audit_types import (
    AuditQueryBySource,
    AuditQueryByTarget,
    BACnetAuditLogRecord,
    BACnetAuditNotification,
)
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier

_logger = logging.getLogger(__name__)
_MAX_DECODED_ITEMS = 10_000
_MAX_NESTING_DEPTH = 32


@dataclass(frozen=True, slots=True)
class AuditLogQueryRequest:
    """AuditLogQuery-Request per Clause 13.19.

    ::

        AuditLogQuery-Request ::= SEQUENCE {
            audit-log             [0] BACnetObjectIdentifier,
            query-parameters      CHOICE {
                by-target         [1] ...,
                by-source         [2] ...
            },
            start-at-seq-number   [3] Unsigned64 OPTIONAL,
            requested-count       [4] Unsigned16
        }
    """

    audit_log: ObjectIdentifier
    query_parameters: AuditQueryByTarget | AuditQueryBySource
    requested_count: int = 100
    start_at_sequence_number: int | None = None

    def encode(self) -> bytes:
        """Encode AuditLogQuery-Request."""
        buf = bytearray()
        # [0] audit-log
        buf.extend(encode_context_object_id(0, self.audit_log))
        # [1]/[2] query-parameters CHOICE
        if isinstance(self.query_parameters, AuditQueryByTarget):
            buf.extend(encode_opening_tag(1))
            buf.extend(self.query_parameters.encode())
            buf.extend(encode_closing_tag(1))
        else:
            buf.extend(encode_opening_tag(2))
            buf.extend(self.query_parameters.encode())
            buf.extend(encode_closing_tag(2))
        # [3] start-at-sequence-number OPTIONAL (Unsigned64)
        if self.start_at_sequence_number is not None:
            buf.extend(encode_context_tagged(3, encode_unsigned64(self.start_at_sequence_number)))
        # [4] requested-count
        buf.extend(encode_context_unsigned(4, self.requested_count))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode AuditLogQuery-Request."""
        data = as_memoryview(data)
        offset = 0

        # [0] audit-log
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        audit_log = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1]/[2] query-parameters CHOICE
        tag, new_offset = decode_tag(data, offset)
        if tag.number == 1 and tag.is_opening:
            # by-target
            inner_start = new_offset
            depth = 1
            scan = new_offset
            while depth > 0 and scan < len(data):
                t, t_offset = decode_tag(data, scan)
                if t.is_opening:
                    depth += 1
                    if depth > _MAX_NESTING_DEPTH:
                        msg = f"Nesting depth exceeds {_MAX_NESTING_DEPTH}"
                        raise ValueError(msg)
                    scan = t_offset
                elif t.is_closing:
                    depth -= 1
                    if depth == 0:
                        inner_end = scan
                        scan = t_offset
                    else:
                        scan = t_offset
                else:
                    scan = t_offset + t.length
            query_parameters: AuditQueryByTarget | AuditQueryBySource = AuditQueryByTarget.decode(
                data[inner_start:inner_end]
            )
            offset = scan
        else:
            # [2] by-source
            inner_start = new_offset
            depth = 1
            scan = new_offset
            while depth > 0 and scan < len(data):
                t, t_offset = decode_tag(data, scan)
                if t.is_opening:
                    depth += 1
                    if depth > _MAX_NESTING_DEPTH:
                        msg = f"Nesting depth exceeds {_MAX_NESTING_DEPTH}"
                        raise ValueError(msg)
                    scan = t_offset
                elif t.is_closing:
                    depth -= 1
                    if depth == 0:
                        inner_end = scan
                        scan = t_offset
                    else:
                        scan = t_offset
                else:
                    scan = t_offset + t.length
            query_parameters = AuditQueryBySource.decode(data[inner_start:inner_end])
            offset = scan

        # [3] start-at-sequence-number OPTIONAL
        start_at_sequence_number = None
        requested_count = 100

        while offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls != TagClass.CONTEXT:
                break
            if tag.number == 3:
                start_at_sequence_number = decode_unsigned64(
                    data[new_offset : new_offset + tag.length]
                )
                offset = new_offset + tag.length
            elif tag.number == 4:
                requested_count = decode_unsigned(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length
            else:
                break

        return cls(
            audit_log=audit_log,
            query_parameters=query_parameters,
            start_at_sequence_number=start_at_sequence_number,
            requested_count=requested_count,
        )


@dataclass(frozen=True, slots=True)
class AuditLogQueryACK:
    """AuditLogQuery-ACK per Clause 13.19.

    ::

        AuditLogQuery-ACK ::= SEQUENCE {
            audit-log         [0] BACnetObjectIdentifier,
            records           [1] SEQUENCE OF BACnetAuditLogRecord,
            no-more-items     [2] BOOLEAN
        }
    """

    audit_log: ObjectIdentifier
    records: list[BACnetAuditLogRecord]
    no_more_items: bool

    def encode(self) -> bytes:
        """Encode AuditLogQuery-ACK."""
        buf = bytearray()
        # [0] audit-log
        buf.extend(encode_context_object_id(0, self.audit_log))
        # [1] records (constructed SEQUENCE OF)
        buf.extend(encode_opening_tag(1))
        for record in self.records:
            buf.extend(record.encode())
        buf.extend(encode_closing_tag(1))
        # [2] no-more-items
        buf.extend(encode_context_boolean(2, self.no_more_items))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode AuditLogQuery-ACK."""
        data = as_memoryview(data)
        offset = 0

        # [0] audit-log
        tag, offset = decode_tag(data, offset)
        obj_type, instance = decode_object_identifier(data[offset : offset + tag.length])
        offset += tag.length
        audit_log = ObjectIdentifier(ObjectType(obj_type), instance)

        # [1] records (constructed)
        _opening, offset = decode_tag(data, offset)  # opening tag 1
        records: list[BACnetAuditLogRecord] = []
        while offset < len(data):
            peek_tag, peek_offset = decode_tag(data, offset)
            if peek_tag.is_closing and peek_tag.number == 1:
                offset = peek_offset
                break
            # Each record starts with [0] sequence-number
            rec_start = offset
            # Find the boundary of one record (next [0] tag or closing [1])
            # We decode one record at a time by finding the next [0] or closing
            depth = 0
            scan = offset
            # Advance past the record
            # Parse one [0] unsigned + [1] constructed notification
            rec_tag, rec_offset = decode_tag(data, scan)  # [0] seq number
            scan = rec_offset + rec_tag.length
            rec_tag, rec_offset = decode_tag(data, scan)  # [1] opening
            if rec_tag.is_opening:
                depth = 1
                scan = rec_offset
                while depth > 0 and scan < len(data):
                    t, t_offset = decode_tag(data, scan)
                    if t.is_opening:
                        depth += 1
                        if depth > _MAX_NESTING_DEPTH:
                            msg = f"Nesting depth exceeds {_MAX_NESTING_DEPTH}"
                            raise ValueError(msg)
                        scan = t_offset
                    elif t.is_closing:
                        depth -= 1
                        scan = t_offset
                    else:
                        scan = t_offset + t.length
            record = BACnetAuditLogRecord.decode(data[rec_start:scan])
            records.append(record)
            if len(records) >= _MAX_DECODED_ITEMS:
                msg = f"Decoded item count exceeds limit ({_MAX_DECODED_ITEMS})"
                raise ValueError(msg)
            offset = scan

        # [2] no-more-items
        tag, offset = decode_tag(data, offset)
        no_more_items = data[offset] != 0
        offset += tag.length

        return cls(
            audit_log=audit_log,
            records=records,
            no_more_items=no_more_items,
        )


@dataclass(frozen=True, slots=True)
class ConfirmedAuditNotificationRequest:
    """ConfirmedAuditNotification-Request per Clause 13.20.

    ::

        ConfirmedAuditNotification-Request ::= SEQUENCE {
            notifications [0] SEQUENCE OF BACnetAuditNotification
        }
    """

    notifications: list[BACnetAuditNotification]

    def encode(self) -> bytes:
        """Encode ConfirmedAuditNotification-Request."""
        buf = bytearray()
        # [0] notifications (constructed SEQUENCE OF)
        buf.extend(encode_opening_tag(0))
        for notification in self.notifications:
            buf.extend(notification.encode())
        buf.extend(encode_closing_tag(0))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> Self:
        """Decode ConfirmedAuditNotification-Request."""
        data = as_memoryview(data)
        offset = 0

        # [0] notifications (constructed)
        _opening, offset = decode_tag(data, offset)  # opening tag 0
        notifications: list[BACnetAuditNotification] = []

        while offset < len(data):
            peek_tag, peek_offset = decode_tag(data, offset)
            if peek_tag.is_closing and peek_tag.number == 0:
                offset = peek_offset
                break
            # Each notification: find the extent by scanning for the next
            # context tag [4] (operation) at depth 0 or closing tag [0].
            # Simpler: just find extent of one notification by tracking
            # context tags at depth 0. Since notifications are sequential,
            # we look for next [2]/[3]/[4] at depth 0 that would start
            # a new notification, or the closing [0].
            #
            # Best approach: consume one notification's worth of tags.
            # A notification starts with optional [0-3] tags and always
            # has [4] operation. Find each notification boundary.
            notif_start = offset
            # Scan to find the end of this notification:
            # We look for the start of the next notification (another tag
            # at context 0-4 after we've seen operation [4]) or closing.
            seen_operation = False
            scan = offset
            while scan < len(data):
                t, t_offset = decode_tag(data, scan)
                if t.is_closing and t.number == 0:
                    # End of SEQUENCE OF
                    break
                if t.is_opening:
                    # Skip constructed
                    depth = 1
                    scan = t_offset
                    while depth > 0 and scan < len(data):
                        inner, inner_off = decode_tag(data, scan)
                        if inner.is_opening:
                            depth += 1
                            if depth > _MAX_NESTING_DEPTH:
                                msg = f"Nesting depth exceeds {_MAX_NESTING_DEPTH}"
                                raise ValueError(msg)
                            scan = inner_off
                        elif inner.is_closing:
                            depth -= 1
                            scan = inner_off
                        else:
                            scan = inner_off + inner.length
                    continue
                if t.cls == TagClass.CONTEXT and t.number == 4:
                    if seen_operation:
                        # This is the start of the next notification
                        break
                    seen_operation = True
                scan = t_offset + t.length

            notification = BACnetAuditNotification.decode(data[notif_start:scan])
            notifications.append(notification)
            if len(notifications) >= _MAX_DECODED_ITEMS:
                msg = f"Decoded item count exceeds limit ({_MAX_DECODED_ITEMS})"
                raise ValueError(msg)
            offset = scan

        return cls(notifications=notifications)


@dataclass(frozen=True, slots=True)
class UnconfirmedAuditNotificationRequest(ConfirmedAuditNotificationRequest):
    """UnconfirmedAuditNotification-Request per Clause 13.21.

    Same structure as ConfirmedAuditNotification-Request.
    """
