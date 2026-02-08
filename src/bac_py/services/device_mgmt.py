"""Device management services per ASHRAE 135-2016 Clause 16.

DeviceCommunicationControl (Clause 16.1), ReinitializeDevice (Clause 16.4),
TimeSynchronization (Clause 16.7), and UTCTimeSynchronization (Clause 16.8).
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_date,
    decode_time,
    decode_unsigned,
    encode_application_date,
    encode_application_time,
    encode_character_string,
    encode_context_tagged,
    encode_enumerated,
    encode_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.types.enums import EnableDisable, ReinitializedState
from bac_py.types.primitives import BACnetDate, BACnetTime


@dataclass(frozen=True, slots=True)
class DeviceCommunicationControlRequest:
    """DeviceCommunicationControl-Request (Clause 16.1.1).

    ::

        DeviceCommunicationControl-Request ::= SEQUENCE {
            timeDuration  [0] Unsigned16 OPTIONAL,
            enable-disable [1] ENUMERATED,
            password      [2] CharacterString (1..20) OPTIONAL
        }
    """

    enable_disable: EnableDisable
    time_duration: int | None = None
    password: str | None = None

    def encode(self) -> bytes:
        buf = bytearray()
        # [0] timeDuration (optional)
        if self.time_duration is not None:
            buf.extend(encode_context_tagged(0, encode_unsigned(self.time_duration)))
        # [1] enable-disable
        buf.extend(encode_context_tagged(1, encode_enumerated(self.enable_disable)))
        # [2] password (optional)
        if self.password is not None:
            buf.extend(encode_context_tagged(2, encode_character_string(self.password)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> DeviceCommunicationControlRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0
        time_duration = None
        password = None

        # [0] timeDuration (optional)
        tag, new_offset = decode_tag(data, offset)
        if tag.cls == TagClass.CONTEXT and tag.number == 0:
            time_duration = decode_unsigned(data[new_offset : new_offset + tag.length])
            offset = new_offset + tag.length
            tag, new_offset = decode_tag(data, offset)

        # [1] enable-disable
        enable_disable = EnableDisable(decode_unsigned(data[new_offset : new_offset + tag.length]))
        offset = new_offset + tag.length

        # [2] password (optional)
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 2:
                password = decode_character_string(data[new_offset : new_offset + tag.length])
                offset = new_offset + tag.length

        return cls(
            enable_disable=enable_disable,
            time_duration=time_duration,
            password=password,
        )


@dataclass(frozen=True, slots=True)
class ReinitializeDeviceRequest:
    """ReinitializeDevice-Request (Clause 16.4.1).

    ::

        ReinitializeDevice-Request ::= SEQUENCE {
            reinitializedStateOfDevice  [0] ENUMERATED,
            password                    [1] CharacterString (1..20) OPTIONAL
        }
    """

    reinitialized_state: ReinitializedState
    password: str | None = None

    def encode(self) -> bytes:
        buf = bytearray()
        # [0] reinitializedStateOfDevice
        buf.extend(encode_context_tagged(0, encode_enumerated(self.reinitialized_state)))
        # [1] password (optional)
        if self.password is not None:
            buf.extend(encode_context_tagged(1, encode_character_string(self.password)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> ReinitializeDeviceRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        # [0] reinitializedStateOfDevice
        tag, offset = decode_tag(data, offset)
        reinitialized_state = ReinitializedState(
            decode_unsigned(data[offset : offset + tag.length])
        )
        offset += tag.length

        # [1] password (optional)
        password = None
        if offset < len(data):
            tag, new_offset = decode_tag(data, offset)
            if tag.cls == TagClass.CONTEXT and tag.number == 1:
                password = decode_character_string(data[new_offset : new_offset + tag.length])

        return cls(
            reinitialized_state=reinitialized_state,
            password=password,
        )


@dataclass(frozen=True, slots=True)
class TimeSynchronizationRequest:
    """TimeSynchronization-Request (Clause 16.7.1).

    ::

        TimeSynchronization-Request ::= SEQUENCE {
            date  Date,
            time  Time
        }

    Both fields are APPLICATION-tagged (not context).
    """

    date: BACnetDate
    time: BACnetTime

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(encode_application_date(self.date))
        buf.extend(encode_application_time(self.time))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> TimeSynchronizationRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        # Date (application tag 10)
        tag, offset = decode_tag(data, offset)
        date = decode_date(data[offset : offset + tag.length])
        offset += tag.length

        # Time (application tag 11)
        tag, offset = decode_tag(data, offset)
        time = decode_time(data[offset : offset + tag.length])

        return cls(date=date, time=time)


@dataclass(frozen=True, slots=True)
class UTCTimeSynchronizationRequest:
    """UTCTimeSynchronization-Request (Clause 16.8.1).

    Same structure as TimeSynchronizationRequest but uses
    UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION (9).
    """

    date: BACnetDate
    time: BACnetTime

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(encode_application_date(self.date))
        buf.extend(encode_application_time(self.time))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview | bytes) -> UTCTimeSynchronizationRequest:
        if isinstance(data, bytes):
            data = memoryview(data)

        offset = 0

        # Date (application tag 10)
        tag, offset = decode_tag(data, offset)
        date = decode_date(data[offset : offset + tag.length])
        offset += tag.length

        # Time (application tag 11)
        tag, offset = decode_tag(data, offset)
        time = decode_time(data[offset : offset + tag.length])

        return cls(date=date, time=time)
