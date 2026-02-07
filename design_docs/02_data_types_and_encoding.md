# Data Types and Encoding

## 1. Overview

BACnet defines a fixed encoding scheme based on ASN.1 tag-length-value (TLV) structures (Clause 20). This document specifies how bac-py represents BACnet data types in Python and implements the encoding/decoding rules.

## 2. Application Data Types (Clause 20.2.1.4)

BACnet defines 13 application-tagged primitive types. Each maps to a Python representation:

| Tag # | BACnet Type            | Python Type        | Notes                                                             |
| ----- | ---------------------- | ------------------ | ----------------------------------------------------------------- |
| 0     | Null                   | `None`             | No contents octets                                                |
| 1     | Boolean                | `bool`             | App-tagged: value in L/V/T bits; Context-tagged: 1 contents octet |
| 2     | Unsigned Integer       | `int`              | Variable-length, minimum octets, big-endian                       |
| 3     | Signed Integer         | `int`              | 2's complement, variable-length, big-endian                       |
| 4     | Real                   | `float`            | IEEE-754 single precision (4 bytes)                               |
| 5     | Double                 | `float`            | IEEE-754 double precision (8 bytes)                               |
| 6     | Octet String           | `bytes`            | Raw byte sequence                                                 |
| 7     | Character String       | `str`              | Leading charset byte (X'00' = UTF-8 default)                      |
| 8     | Bit String             | `BitString`        | Custom class: leading unused-bits count then data                 |
| 9     | Enumerated             | `int`              | Variable-length unsigned, maps to `IntEnum` subclasses            |
| 10    | Date                   | `BACnetDate`       | 4 bytes: year-1900, month, day, day-of-week (0xFF = unspecified)  |
| 11    | Time                   | `BACnetTime`       | 4 bytes: hours, minutes, seconds, hundredths (0xFF = unspecified) |
| 12    | BACnetObjectIdentifier | `ObjectIdentifier` | 4 bytes: 10-bit type + 22-bit instance                            |

## 3. Python Type Implementations

### 3.1 Primitive Wrapper Classes

```python
@dataclass(frozen=True, slots=True)
class ObjectIdentifier:
    """BACnet Object Identifier - 10-bit type, 22-bit instance."""
    object_type: ObjectType      # IntEnum
    instance_number: int         # 0 to 4194303

    def encode(self) -> bytes:
        value = (self.object_type << 22) | (self.instance_number & 0x3FFFFF)
        return value.to_bytes(4, 'big')

    @classmethod
    def decode(cls, data: bytes | memoryview) -> ObjectIdentifier:
        value = int.from_bytes(data[:4], 'big')
        return cls(
            object_type=ObjectType(value >> 22),
            instance_number=value & 0x3FFFFF,
        )
```

```python
@dataclass(frozen=True, slots=True)
class BACnetDate:
    """BACnet Date: year, month, day, day_of_week. 0xFF = unspecified."""
    year: int          # Actual year (added back from year-1900 on decode)
    month: int         # 1-14 (13 = odd months, 14 = even months, 0xFF = any)
    day: int           # 1-34 (32 = last day, 33 = odd days, 34 = even days, 0xFF = any)
    day_of_week: int   # 1 = Monday ... 7 = Sunday, 0xFF = any
```

```python
@dataclass(frozen=True, slots=True)
class BACnetTime:
    """BACnet Time: hour, minute, second, hundredth. 0xFF = unspecified."""
    hour: int          # 0-23, 0xFF = any
    minute: int        # 0-59, 0xFF = any
    second: int        # 0-59, 0xFF = any
    hundredth: int     # 0-99, 0xFF = any
```

```python
class BitString:
    """BACnet Bit String with named-bit support."""
    __slots__ = ('_data', '_unused_bits')

    def __init__(self, value: bytes, unused_bits: int = 0):
        self._data = value
        self._unused_bits = unused_bits

    def __getitem__(self, index: int) -> bool:
        byte_index = index // 8
        bit_index = 7 - (index % 8)
        return bool(self._data[byte_index] & (1 << bit_index))
```

### 3.2 Enumeration Types

BACnet enumerations are represented as `IntEnum` subclasses, generated from the spec's defined values:

```python
class ObjectType(IntEnum):
    ANALOG_INPUT = 0
    ANALOG_OUTPUT = 1
    ANALOG_VALUE = 2
    BINARY_INPUT = 3
    BINARY_OUTPUT = 4
    BINARY_VALUE = 5
    CALENDAR = 6
    COMMAND = 7
    DEVICE = 8
    EVENT_ENROLLMENT = 9
    FILE = 10
    GROUP = 11
    LOOP = 12
    MULTI_STATE_INPUT = 13
    MULTI_STATE_OUTPUT = 14
    NOTIFICATION_CLASS = 15
    PROGRAM = 16
    SCHEDULE = 17
    AVERAGING = 18
    MULTI_STATE_VALUE = 19
    TREND_LOG = 20
    LIFE_SAFETY_POINT = 21
    LIFE_SAFETY_ZONE = 22
    ACCUMULATOR = 23
    PULSE_CONVERTER = 24
    EVENT_LOG = 25
    GLOBAL_GROUP = 26
    TREND_LOG_MULTIPLE = 27
    LOAD_CONTROL = 28
    STRUCTURED_VIEW = 29
    ACCESS_DOOR = 30
    TIMER = 31
    ACCESS_CREDENTIAL = 32
    ACCESS_POINT = 33
    ACCESS_RIGHTS = 34
    ACCESS_USER = 35
    ACCESS_ZONE = 36
    CREDENTIAL_DATA_INPUT = 37
    NETWORK_SECURITY = 38
    BITSTRING_VALUE = 39
    CHARACTERSTRING_VALUE = 40
    DATEPATTERN_VALUE = 41
    DATE_VALUE = 42
    DATETIMEPATTERN_VALUE = 43
    DATETIME_VALUE = 44
    INTEGER_VALUE = 45
    LARGE_ANALOG_VALUE = 46
    OCTETSTRING_VALUE = 47
    POSITIVE_INTEGER_VALUE = 48
    TIMEPATTERN_VALUE = 49
    TIME_VALUE = 50
    NOTIFICATION_FORWARDER = 51
    ALERT_ENROLLMENT = 52
    CHANNEL = 53
    LIGHTING_OUTPUT = 54
    BINARY_LIGHTING_OUTPUT = 55
    NETWORK_PORT = 56
    ELEVATOR_GROUP = 57
    ESCALATOR = 58
    LIFT = 59
    # Vendor-specific: 128-1023


class PropertyIdentifier(IntEnum):
    ACKED_TRANSITIONS = 0
    ACK_REQUIRED = 1
    ACTION = 2
    ACTION_TEXT = 3
    ACTIVE_TEXT = 4
    ACTIVE_VT_SESSIONS = 5
    # ... (complete list from spec - ~500 defined properties)
    OBJECT_IDENTIFIER = 75
    OBJECT_LIST = 76
    OBJECT_NAME = 77
    OBJECT_TYPE = 79
    PRESENT_VALUE = 85
    PRIORITY_ARRAY = 87
    PROTOCOL_OBJECT_TYPES_SUPPORTED = 96
    PROTOCOL_SERVICES_SUPPORTED = 97
    PROTOCOL_VERSION = 98
    STATUS_FLAGS = 111
    SYSTEM_STATUS = 112
    UNITS = 117
    VENDOR_IDENTIFIER = 120
    VENDOR_NAME = 121
    MODEL_NAME = 70
    FIRMWARE_REVISION = 44
    APPLICATION_SOFTWARE_VERSION = 12
    # ... continued
    # Vendor-specific: 512+


class ErrorClass(IntEnum):
    DEVICE = 0
    OBJECT = 1
    PROPERTY = 2
    RESOURCES = 3
    SECURITY = 4
    SERVICES = 5
    VT = 6
    COMMUNICATION = 7


class ErrorCode(IntEnum):
    OTHER = 0
    CONFIGURATION_IN_PROGRESS = 2
    DEVICE_BUSY = 3
    DYNAMIC_CREATION_NOT_SUPPORTED = 4
    FILE_ACCESS_DENIED = 5
    OBJECT_DELETION_NOT_PERMITTED = 23
    OBJECT_IDENTIFIER_ALREADY_EXISTS = 24
    MISSING_REQUIRED_PARAMETER = 16
    NO_OBJECTS_OF_SPECIFIED_TYPE = 17
    PROPERTY_IS_NOT_A_LIST = 22
    READ_ACCESS_DENIED = 27
    SERVICE_REQUEST_DENIED = 29
    TIMEOUT = 30
    UNKNOWN_OBJECT = 31
    UNKNOWN_PROPERTY = 32
    VALUE_OUT_OF_RANGE = 37
    WRITE_ACCESS_DENIED = 40
    # ... continued


class Segmentation(IntEnum):
    BOTH = 0
    TRANSMIT = 1
    RECEIVE = 2
    NONE = 3


class AbortReason(IntEnum):
    OTHER = 0
    BUFFER_OVERFLOW = 1
    INVALID_APDU_IN_THIS_STATE = 2
    PREEMPTED_BY_HIGHER_PRIORITY_TASK = 3
    SEGMENTATION_NOT_SUPPORTED = 4
    SECURITY_ERROR = 5
    INSUFFICIENT_SECURITY = 6
    WINDOW_SIZE_OUT_OF_RANGE = 7
    APPLICATION_EXCEEDED_REPLY_TIME = 8
    OUT_OF_RESOURCES = 9
    TSM_TIMEOUT = 10
    APDU_TOO_LONG = 11


class RejectReason(IntEnum):
    OTHER = 0
    BUFFER_OVERFLOW = 1
    INCONSISTENT_PARAMETERS = 2
    INVALID_PARAMETER_DATA_TYPE = 3
    INVALID_TAG = 4
    MISSING_REQUIRED_PARAMETER = 5
    PARAMETER_OUT_OF_RANGE = 6
    TOO_MANY_ARGUMENTS = 7
    UNDEFINED_ENUMERATION = 8
    UNRECOGNIZED_SERVICE = 9
```

## 4. Tag Encoding/Decoding (Clause 20.2.1)

### 4.1 Tag Structure

Every tagged data element starts with an initial tag octet:

```
Bits:  7  6  5  4  3  2  1  0
      [Tag Number ] [C] [L/V/T]
```

- **Tag Number** (bits 7-4): 0-14 inline, 15 = extended (next byte holds actual number)
- **Class** (bit 3): 0 = application tag, 1 = context-specific tag
- **L/V/T** (bits 2-0): Length, Value, or Type indicator
  - For primitive: data length (0-4 inline, 5 = extended length follows)
  - For Boolean app-tagged: value (0 = False, 1 = True)
  - For constructed: 6 = opening tag, 7 = closing tag

### 4.2 Codec Design

```python
@dataclass(frozen=True, slots=True)
class Tag:
    """Decoded BACnet tag."""
    number: int                    # Tag number
    cls: TagClass                  # APPLICATION or CONTEXT
    length: int                    # Data length in bytes (0 for opening/closing)
    is_opening: bool = False       # Opening constructed tag
    is_closing: bool = False       # Closing constructed tag

class TagClass(IntEnum):
    APPLICATION = 0
    CONTEXT = 1


def decode_tag(buf: memoryview, offset: int) -> tuple[Tag, int]:
    """Decode a tag from buffer, return (tag, new_offset).

    Operates on memoryview for zero-copy parsing.
    """
    ...

def encode_tag(tag_number: int, cls: TagClass, length: int) -> bytes:
    """Encode a tag header."""
    ...

def encode_opening_tag(tag_number: int) -> bytes:
    """Encode a context-specific opening tag."""
    ...

def encode_closing_tag(tag_number: int) -> bytes:
    """Encode a context-specific closing tag."""
    ...
```

### 4.3 Primitive Encoding Functions

Each BACnet data type has dedicated encode/decode functions:

```python
# Unsigned Integer - variable length, minimum octets, big-endian
def encode_unsigned(value: int) -> bytes: ...
def decode_unsigned(data: memoryview) -> int: ...

# Signed Integer - 2's complement, variable length
def encode_signed(value: int) -> bytes: ...
def decode_signed(data: memoryview) -> int: ...

# Real - IEEE-754 single precision
def encode_real(value: float) -> bytes:
    return struct.pack('>f', value)
def decode_real(data: memoryview) -> float:
    return struct.unpack('>f', data[:4])[0]

# Double - IEEE-754 double precision
def encode_double(value: float) -> bytes:
    return struct.pack('>d', value)
def decode_double(data: memoryview) -> float:
    return struct.unpack('>d', data[:8])[0]

# Character String - leading charset byte, default UTF-8
def encode_character_string(value: str, charset: int = 0) -> bytes:
    return bytes([charset]) + value.encode('utf-8')
def decode_character_string(data: memoryview) -> str:
    charset = data[0]
    if charset == 0:  # UTF-8
        return bytes(data[1:]).decode('utf-8')
    ...

# Object Identifier - 4 bytes: 10-bit type + 22-bit instance
def encode_object_identifier(obj_type: int, instance: int) -> bytes:
    return ((obj_type << 22) | (instance & 0x3FFFFF)).to_bytes(4, 'big')
def decode_object_identifier(data: memoryview) -> tuple[int, int]:
    value = int.from_bytes(data[:4], 'big')
    return (value >> 22, value & 0x3FFFFF)

# Date - 4 bytes: year-1900, month, day, day-of-week
def encode_date(date: BACnetDate) -> bytes:
    return bytes([date.year - 1900, date.month, date.day, date.day_of_week])
def decode_date(data: memoryview) -> BACnetDate:
    return BACnetDate(data[0] + 1900, data[1], data[2], data[3])

# Time - 4 bytes: hour, minute, second, hundredth
def encode_time(time: BACnetTime) -> bytes:
    return bytes([time.hour, time.minute, time.second, time.hundredth])
def decode_time(data: memoryview) -> BACnetTime:
    return BACnetTime(data[0], data[1], data[2], data[3])

# Enumerated - same encoding as unsigned
def encode_enumerated(value: int) -> bytes:
    return encode_unsigned(value)
def decode_enumerated(data: memoryview) -> int:
    return decode_unsigned(data)

# Bit String - leading unused-bits count byte
def encode_bit_string(value: BitString) -> bytes: ...
def decode_bit_string(data: memoryview) -> BitString: ...

# Octet String - raw bytes
def encode_octet_string(value: bytes) -> bytes:
    return value
def decode_octet_string(data: memoryview) -> bytes:
    return bytes(data)
```

### 4.4 Application-Tagged Encode/Decode

Convenience functions that combine tag + data encoding:

```python
def encode_application_tagged(tag_number: int, data: bytes) -> bytes:
    """Encode data with an application tag."""
    return encode_tag(tag_number, TagClass.APPLICATION, len(data)) + data

def encode_context_tagged(tag_number: int, data: bytes) -> bytes:
    """Encode data with a context-specific tag."""
    return encode_tag(tag_number, TagClass.CONTEXT, len(data)) + data

def encode_application_unsigned(value: int) -> bytes:
    data = encode_unsigned(value)
    return encode_application_tagged(2, data)

def encode_application_object_id(obj_type: int, instance: int) -> bytes:
    data = encode_object_identifier(obj_type, instance)
    return encode_application_tagged(12, data)

# ... similar functions for each application type
```

## 5. APDU Encoding (Clause 20.1)

### 5.1 PDU Type Identification

The first byte of every APDU encodes the PDU type in bits 7-4:

| Bits 7-4 | PDU Type                       |
| -------- | ------------------------------ |
| 0x0      | BACnet-Confirmed-Request-PDU   |
| 0x1      | BACnet-Unconfirmed-Request-PDU |
| 0x2      | BACnet-SimpleACK-PDU           |
| 0x3      | BACnet-ComplexACK-PDU          |
| 0x4      | BACnet-SegmentACK-PDU          |
| 0x5      | BACnet-Error-PDU               |
| 0x6      | BACnet-Reject-PDU              |
| 0x7      | BACnet-Abort-PDU               |

### 5.2 APDU Data Structures

```python
class PduType(IntEnum):
    CONFIRMED_REQUEST = 0
    UNCONFIRMED_REQUEST = 1
    SIMPLE_ACK = 2
    COMPLEX_ACK = 3
    SEGMENT_ACK = 4
    ERROR = 5
    REJECT = 6
    ABORT = 7


@dataclass(frozen=True, slots=True)
class ConfirmedRequestPDU:
    segmented: bool
    more_follows: bool
    segmented_response_accepted: bool
    max_segments: int              # Encoded as 0-7 representing 0/2/4/8/16/32/64/unspecified
    max_apdu_length: int           # Encoded as 0-15 representing standard sizes
    invoke_id: int                 # 0-255
    sequence_number: int | None    # Present if segmented
    proposed_window_size: int | None  # Present if segmented
    service_choice: int            # ConfirmedServiceChoice
    service_request: bytes         # Encoded service parameters


@dataclass(frozen=True, slots=True)
class UnconfirmedRequestPDU:
    service_choice: int            # UnconfirmedServiceChoice
    service_request: bytes         # Encoded service parameters


@dataclass(frozen=True, slots=True)
class SimpleAckPDU:
    invoke_id: int
    service_choice: int


@dataclass(frozen=True, slots=True)
class ComplexAckPDU:
    segmented: bool
    more_follows: bool
    invoke_id: int
    sequence_number: int | None
    proposed_window_size: int | None
    service_choice: int
    service_ack: bytes


@dataclass(frozen=True, slots=True)
class ErrorPDU:
    invoke_id: int
    service_choice: int
    error_class: ErrorClass
    error_code: ErrorCode


@dataclass(frozen=True, slots=True)
class RejectPDU:
    invoke_id: int
    reject_reason: RejectReason


@dataclass(frozen=True, slots=True)
class AbortPDU:
    sent_by_server: bool
    invoke_id: int
    abort_reason: AbortReason
```

## 6. Confirmed Service Choice Values

```python
class ConfirmedServiceChoice(IntEnum):
    # Alarm and Event Services
    ACKNOWLEDGE_ALARM = 0
    CONFIRMED_COV_NOTIFICATION = 1
    CONFIRMED_EVENT_NOTIFICATION = 2
    GET_ALARM_SUMMARY = 3
    GET_ENROLLMENT_SUMMARY = 4
    SUBSCRIBE_COV = 5
    # File Access Services
    ATOMIC_READ_FILE = 6
    ATOMIC_WRITE_FILE = 7
    # Object Access Services
    ADD_LIST_ELEMENT = 8
    REMOVE_LIST_ELEMENT = 9
    CREATE_OBJECT = 10
    DELETE_OBJECT = 11
    READ_PROPERTY = 12
    READ_PROPERTY_MULTIPLE = 14
    READ_RANGE = 26
    WRITE_PROPERTY = 15
    WRITE_PROPERTY_MULTIPLE = 16
    # Remote Device Management Services
    DEVICE_COMMUNICATION_CONTROL = 17
    CONFIRMED_PRIVATE_TRANSFER = 18
    CONFIRMED_TEXT_MESSAGE = 19
    REINITIALIZE_DEVICE = 20
    # Virtual Terminal Services
    VT_OPEN = 21
    VT_CLOSE = 22
    VT_DATA = 23
    # Additional
    GET_EVENT_INFORMATION = 29
    SUBSCRIBE_COV_PROPERTY = 28
    LIFE_SAFETY_OPERATION = 27
    SUBSCRIBE_COV_PROPERTY_MULTIPLE = 30
    CONFIRMED_COV_NOTIFICATION_MULTIPLE = 31


class UnconfirmedServiceChoice(IntEnum):
    I_AM = 0
    I_HAVE = 1
    UNCONFIRMED_COV_NOTIFICATION = 2
    UNCONFIRMED_EVENT_NOTIFICATION = 3
    UNCONFIRMED_PRIVATE_TRANSFER = 4
    UNCONFIRMED_TEXT_MESSAGE = 5
    TIME_SYNCHRONIZATION = 6
    WHO_HAS = 7
    WHO_IS = 8
    UTC_TIME_SYNCHRONIZATION = 9
    WRITE_GROUP = 10
    UNCONFIRMED_COV_NOTIFICATION_MULTIPLE = 11
```

## 7. Constructed Type Encoding

BACnet service parameters use constructed encodings (Clause 20.2.1.3.2) to represent SEQUENCE, SEQUENCE OF, and CHOICE types. These are delimited by opening/closing context tags.

### 7.1 SEQUENCE Encoding

A SEQUENCE is encoded as a series of context-tagged elements between opening and closing tags:

```python
def encode_sequence(tag_number: int, elements: list[bytes]) -> bytes:
    """Encode a constructed SEQUENCE with opening/closing tags."""
    buf = bytearray()
    buf.extend(encode_opening_tag(tag_number))
    for element in elements:
        buf.extend(element)
    buf.extend(encode_closing_tag(tag_number))
    return bytes(buf)


def decode_sequence(data: memoryview, offset: int,
                    tag_number: int) -> tuple[memoryview, int]:
    """Decode a constructed SEQUENCE, returning inner data and new offset."""
    tag, offset = decode_tag(data, offset)
    assert tag.is_opening and tag.number == tag_number
    start = offset
    # Find matching closing tag (handling nested constructs)
    depth = 1
    while depth > 0:
        tag, offset = decode_tag(data, offset)
        if tag.is_opening and tag.number == tag_number:
            depth += 1
        elif tag.is_closing and tag.number == tag_number:
            depth -= 1
        else:
            offset += tag.length  # Skip over data
    end = offset - 1  # Before closing tag
    return data[start:end], offset
```

### 7.2 SEQUENCE OF Encoding

A SEQUENCE OF is a list of uniformly-typed elements:

```python
def encode_sequence_of(tag_number: int,
                       encode_fn: Callable[[Any], bytes],
                       items: list[Any]) -> bytes:
    """Encode a SEQUENCE OF with opening/closing tags."""
    buf = bytearray()
    buf.extend(encode_opening_tag(tag_number))
    for item in items:
        buf.extend(encode_fn(item))
    buf.extend(encode_closing_tag(tag_number))
    return bytes(buf)
```

### 7.3 CHOICE Encoding

BACnet CHOICE types are represented as a union. The context tag disambiguates:

```python
@dataclass(frozen=True, slots=True)
class BACnetDateTime:
    """BACnet DateTime - combination of Date and Time."""
    date: BACnetDate
    time: BACnetTime

    def encode(self) -> bytes:
        return (encode_application_tagged(10, encode_date(self.date)) +
                encode_application_tagged(11, encode_time(self.time)))


@dataclass(frozen=True, slots=True)
class BACnetTimeStamp:
    """BACnet TimeStamp - CHOICE of time, sequence-number, or datetime."""
    time: BACnetTime | None = None
    sequence_number: int | None = None
    datetime: BACnetDateTime | None = None

    def encode(self) -> bytes:
        if self.time is not None:
            return encode_context_tagged(0, encode_time(self.time))
        elif self.sequence_number is not None:
            return encode_context_tagged(1,
                encode_unsigned(self.sequence_number))
        elif self.datetime is not None:
            return encode_sequence(2, [self.datetime.encode()])
        raise ValueError("TimeStamp must have exactly one value set")
```

## 8. Polymorphic Property Value Encoding/Decoding

Property values in ReadProperty-ACK and WriteProperty-Request carry `ABSTRACT-SYNTAX.&TYPE` — meaning the data type depends on which property is being read/written. The decoder must know the expected type to interpret the tagged data correctly.

### 8.1 Property Type Registry

A mapping from `(ObjectType, PropertyIdentifier)` to expected data type drives polymorphic decoding:

```python
class PropertyTypeInfo(NamedTuple):
    """Describes how to encode/decode a property's value."""
    app_tag: int | None      # Expected application tag (None for constructed)
    is_array: bool            # True if the property is a BACnetARRAY
    is_list: bool             # True if the property is a BACnetLIST
    decode_fn: Callable       # Function to decode the value
    encode_fn: Callable       # Function to encode the value


# Registry keyed by property identifier (most properties have the same type
# regardless of object type). Object-type-specific overrides via tuple key.
_PROPERTY_TYPE_REGISTRY: dict[
    PropertyIdentifier | tuple[ObjectType, PropertyIdentifier],
    PropertyTypeInfo
] = {
    PropertyIdentifier.PRESENT_VALUE: PropertyTypeInfo(
        app_tag=None, is_array=False, is_list=False,
        decode_fn=decode_present_value,  # Dispatches on object type
        encode_fn=encode_present_value,
    ),
    PropertyIdentifier.OBJECT_IDENTIFIER: PropertyTypeInfo(
        app_tag=12, is_array=False, is_list=False,
        decode_fn=decode_object_identifier,
        encode_fn=encode_object_identifier,
    ),
    PropertyIdentifier.OBJECT_NAME: PropertyTypeInfo(
        app_tag=7, is_array=False, is_list=False,
        decode_fn=decode_character_string,
        encode_fn=encode_character_string,
    ),
    PropertyIdentifier.OBJECT_TYPE: PropertyTypeInfo(
        app_tag=9, is_array=False, is_list=False,
        decode_fn=decode_enumerated,
        encode_fn=encode_enumerated,
    ),
    PropertyIdentifier.UNITS: PropertyTypeInfo(
        app_tag=9, is_array=False, is_list=False,
        decode_fn=decode_enumerated,
        encode_fn=encode_enumerated,
    ),
    PropertyIdentifier.STATUS_FLAGS: PropertyTypeInfo(
        app_tag=8, is_array=False, is_list=False,
        decode_fn=decode_bit_string,
        encode_fn=encode_bit_string,
    ),
    PropertyIdentifier.OBJECT_LIST: PropertyTypeInfo(
        app_tag=12, is_array=True, is_list=False,
        decode_fn=decode_object_identifier,
        encode_fn=encode_object_identifier,
    ),
    PropertyIdentifier.PRIORITY_ARRAY: PropertyTypeInfo(
        app_tag=None, is_array=True, is_list=False,
        decode_fn=decode_priority_value,
        encode_fn=encode_priority_value,
    ),
    # ... entries for all standard properties
}


def decode_property_value(object_type: ObjectType,
                          property_id: PropertyIdentifier,
                          data: memoryview) -> Any:
    """Decode a property value using the type registry."""
    # Check for object-type-specific override
    key = (object_type, property_id)
    info = _PROPERTY_TYPE_REGISTRY.get(key)
    if info is None:
        info = _PROPERTY_TYPE_REGISTRY.get(property_id)
    if info is None:
        # Unknown property — return raw tagged data
        return decode_any_tagged(data)

    if info.is_array:
        return decode_array(data, info.decode_fn)
    elif info.is_list:
        return decode_list(data, info.decode_fn)
    else:
        return info.decode_fn(data)


def encode_property_value(object_type: ObjectType,
                          property_id: PropertyIdentifier,
                          value: Any) -> bytes:
    """Encode a property value using the type registry."""
    key = (object_type, property_id)
    info = _PROPERTY_TYPE_REGISTRY.get(key)
    if info is None:
        info = _PROPERTY_TYPE_REGISTRY.get(property_id)
    if info is None:
        raise ValueError(f"Unknown property type: {property_id}")

    encoded = info.encode_fn(value)
    if info.app_tag is not None:
        return encode_application_tagged(info.app_tag, encoded)
    return encoded
```

### 8.2 Fallback Decoding

For unknown or vendor-specific properties, we decode the raw tagged value generically:

```python
def decode_any_tagged(data: memoryview) -> Any:
    """Decode tagged data without knowing the expected type.

    Returns the value based on the application tag found.
    """
    tag, offset = decode_tag(data, 0)
    content = data[offset:offset + tag.length]

    if tag.cls == TagClass.APPLICATION:
        match tag.number:
            case 0: return None
            case 1: return bool(tag.length)  # Boolean in L/V/T
            case 2: return decode_unsigned(content)
            case 3: return decode_signed(content)
            case 4: return decode_real(content)
            case 5: return decode_double(content)
            case 6: return decode_octet_string(content)
            case 7: return decode_character_string(content)
            case 8: return decode_bit_string(content)
            case 9: return decode_enumerated(content)
            case 10: return decode_date(content)
            case 11: return decode_time(content)
            case 12:
                type_id, inst = decode_object_identifier(content)
                return ObjectIdentifier(ObjectType(type_id), inst)
    # Context-tagged: return raw bytes
    return bytes(content)
```

## 9. Design Decisions

### 9.1 Why frozen dataclasses?

- PDUs flow through multiple layers; immutability prevents accidental mutation
- Enable use as dict keys (hashable) for TSM lookups
- Thread-safe by construction (irrelevant for single-loop async, but a correctness safety net)
- `slots=True` for memory efficiency with many concurrent transactions

### 9.2 Why memoryview for decoding?

- Received UDP datagrams need to be parsed through multiple layers (BVLL -> NPDU -> APDU -> service params)
- Each layer slices into the buffer without copying
- `struct.unpack_from()` works directly with memoryview
- Significant performance win on embedded/resource-constrained systems processing many packets

### 9.3 Why IntEnum for enumerations?

- Direct use in arithmetic and encoding (BACnet enumerations are unsigned integers)
- Type safety via mypy / static analysis
- String representation in error messages and debugging
- Extensible: vendor-specific values outside the defined range are valid wire values

### 9.4 Charset handling for CharacterString

BACnet supports multiple character sets. Our default and primary implementation targets UTF-8 (charset 0x00), which covers the vast majority of modern deployments. ISO 8859-1 (charset 0x05) support is straightforward. The less common IBM/DBCS and JIS encodings can be added as needed.
