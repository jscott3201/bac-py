# Serialization

## 1. Overview

BACnet data processed by bac-py often needs to leave the protocol boundary — exported to REST APIs, stored in databases, sent to message brokers, or consumed by dashboards and analytics systems. This document defines how bac-py converts its internal data structures to and from external interchange formats, with JSON (via orjson) as the primary target.

### 1.1 Goals

- **External system integration**: Expose BACnet object state, property values, and service results in formats that non-BACnet systems can consume directly.
- **Round-trip fidelity**: Deserializing a serialized value must produce an equivalent object — no information loss for standard BACnet types.
- **Performance**: Serialization must not become a bottleneck when exporting high-frequency data (COV notifications, trend logs, bulk reads). orjson is selected for this reason.
- **Extensibility**: The design must allow additional output formats (MessagePack, CBOR, CSV) without changing the core type definitions.

### 1.2 Non-Goals

- Replacing BACnet wire encoding. The `encoding/` module handles ASN.1 TLV for on-wire communication. Serialization is for external consumption only.
- Schema negotiation with external systems. bac-py defines a canonical JSON representation; adapters for specific external schemas are the user's responsibility.

## 2. Architecture

### 2.1 Module Structure

```
src/bac_py/
└── serialization/
    ├── __init__.py        # Public API: serialize(), deserialize(), register_format()
    └── json.py            # JsonSerializer using orjson
```

### 2.2 Separation of Concerns

Serialization is split into two layers:

1. **Dict conversion** — Each BACnet type defines `to_dict()` and `from_dict()` methods that produce/consume plain Python dicts with JSON-safe values. This layer lives on the types themselves and is format-agnostic.
2. **Format encoding** — A `Serializer` protocol converts dicts to the target wire format (JSON bytes, MessagePack bytes, etc.). The default implementation uses orjson.

```
BACnet Object ──to_dict()──▶ dict ──Serializer.encode()──▶ bytes (JSON)
bytes (JSON) ──Serializer.decode()──▶ dict ──from_dict()──▶ BACnet Object
```

This split means `to_dict()`/`from_dict()` have no dependency on orjson or any serialization library, while the format layer is pluggable.

### 2.3 Serializer Protocol

```python
from typing import Any, Protocol


class Serializer(Protocol):
    """Interface for format-specific serialization backends."""

    def encode(self, data: dict[str, Any]) -> bytes:
        """Encode a dict to the target format."""
        ...

    def decode(self, raw: bytes) -> dict[str, Any]:
        """Decode bytes in the target format to a dict."""
        ...

    @property
    def content_type(self) -> str:
        """MIME type for the output format (e.g. 'application/json')."""
        ...
```

## 3. JSON Serializer (orjson)

### 3.1 Why orjson

| Criterion   | orjson                         | stdlib json                 |
| ----------- | ------------------------------ | --------------------------- |
| Speed       | ~10x faster serialization      | Baseline                    |
| Output type | `bytes` (no extra `.encode()`) | `str` (needs `.encode()`)   |
| Dataclass   | Native support, 40-50x faster  | Requires `default` function |
| Enum        | Native (`IntEnum` → int)       | Requires `default` function |
| Options     | Composable `OPT_*` flags       | `sort_keys`, `indent` only  |
| `datetime`  | RFC 3339 natively              | Requires `default` function |
| `UUID`      | RFC 4122 natively              | Requires `default` function |

orjson is added as an optional dependency under the `serialization` extra so the core protocol library remains dependency-free.

### 3.2 Implementation

```python
import orjson

from bac_py.serialization import Serializer


class JsonSerializer:
    """JSON serializer backed by orjson."""

    def __init__(
        self,
        *,
        pretty: bool = False,
        sort_keys: bool = False,
        enum_names: bool = True,
    ):
        self._options = orjson.OPT_NON_STR_KEYS
        if pretty:
            self._options |= orjson.OPT_INDENT_2
        if sort_keys:
            self._options |= orjson.OPT_SORT_KEYS
        self._enum_names = enum_names

    def encode(self, data: dict[str, Any]) -> bytes:
        """Encode a dict to JSON bytes."""
        return orjson.dumps(data, default=self._default, option=self._options)

    def decode(self, raw: bytes) -> dict[str, Any]:
        """Decode JSON bytes to a dict."""
        return orjson.loads(raw)

    @property
    def content_type(self) -> str:
        return "application/json"

    def _default(self, obj: Any) -> Any:
        """Handle BACnet types that orjson cannot serialize natively."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, bytes):
            return obj.hex()
        if isinstance(obj, memoryview):
            return bytes(obj).hex()
        raise TypeError(f"Cannot serialize {type(obj).__name__}")
```

### 3.3 Convenience API

The `serialization/__init__.py` provides top-level functions for common operations:

```python
_DEFAULT_SERIALIZER: Serializer | None = None


def get_serializer(format: str = "json", **kwargs: Any) -> Serializer:
    """Get a serializer instance for the given format.

    Args:
        format: Output format. Currently supported: "json".
        **kwargs: Format-specific options passed to the serializer constructor.

    Returns:
        A Serializer instance.

    Raises:
        ValueError: If the format is not supported.
        ImportError: If the required dependency is not installed.
    """
    if format == "json":
        from bac_py.serialization.json import JsonSerializer
        return JsonSerializer(**kwargs)
    raise ValueError(f"Unsupported serialization format: {format}")


def serialize(obj: Any, format: str = "json", **kwargs: Any) -> bytes:
    """Serialize a BACnet object or dict to the specified format.

    Accepts any object with a to_dict() method, or a plain dict.
    """
    serializer = get_serializer(format, **kwargs)
    data = obj.to_dict() if hasattr(obj, "to_dict") else obj
    return serializer.encode(data)


def deserialize(raw: bytes, format: str = "json") -> dict[str, Any]:
    """Deserialize bytes to a dict in the specified format."""
    serializer = get_serializer(format)
    return serializer.decode(raw)
```

## 4. Type Mapping

Every BACnet type maps to a JSON-friendly representation. The `to_dict()` method on each type produces this representation, and `from_dict()` reconstructs the original.

### 4.1 Primitive Type Mapping

| BACnet Type       | Python Type        | JSON Representation                                                             | Example                                                                            |
| ----------------- | ------------------ | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Null              | `None`             | `null`                                                                          | `null`                                                                             |
| Boolean           | `bool`             | `true` / `false`                                                                | `true`                                                                             |
| Unsigned Integer  | `int`              | number                                                                          | `42`                                                                               |
| Signed Integer    | `int`              | number                                                                          | `-7`                                                                               |
| Real              | `float`            | number                                                                          | `72.5`                                                                             |
| Double            | `float`            | number                                                                          | `72.5`                                                                             |
| Octet String      | `bytes`            | hex string                                                                      | `"deadbeef"`                                                                       |
| Character String  | `str`              | string                                                                          | `"Room 101"`                                                                       |
| Enumerated        | `IntEnum`          | `{"value": int, "name": str}`                                                   | `{"value": 0, "name": "analog-input"}`                                             |
| Object Identifier | `ObjectIdentifier` | `{"object_type": str, "instance": int}`                                         | `{"object_type": "analog-input", "instance": 1}`                                   |
| Date              | `BACnetDate`       | `{"year": int, "month": int, "day": int, "day_of_week": int}`                   | `{"year": 2024, "month": 6, "day": 15, "day_of_week": 6}`                          |
| Time              | `BACnetTime`       | `{"hour": int, "minute": int, "second": int, "hundredth": int}`                 | `{"hour": 14, "minute": 30, "second": 0, "hundredth": 0}`                          |
| Bit String        | `BitString`        | `{"bits": [bool, ...], "unused_bits": int}`                                     | `{"bits": [false, false, false, true], "unused_bits": 4}`                          |
| Status Flags      | `StatusFlags`      | `{"in_alarm": bool, "fault": bool, "overridden": bool, "out_of_service": bool}` | `{"in_alarm": false, "fault": false, "overridden": false, "out_of_service": true}` |

### 4.2 Enumeration Representation

BACnet enumerations (`IntEnum` subclasses) serialize with both their numeric value and a human-readable name by default. The name uses lowercase-hyphenated form derived from the Python `UPPER_SNAKE` name:

```python
def _enum_name(member: IntEnum) -> str:
    """Convert UPPER_SNAKE enum name to lower-hyphen form."""
    return member.name.lower().replace("_", "-")
```

```json
{ "value": 0, "name": "analog-input" }
```

This ensures external systems can consume values by either numeric code or readable name. The `from_dict()` path accepts either form:

```python
@classmethod
def enum_from_dict(cls, enum_cls: type[IntEnum],
                   data: int | str | dict) -> IntEnum:
    """Reconstruct an enum from its JSON representation.

    Accepts:
      - int: raw numeric value
      - str: hyphenated name (e.g. "analog-input")
      - dict: {"value": int, "name": str}
    """
    if isinstance(data, int):
        return enum_cls(data)
    if isinstance(data, str):
        name = data.upper().replace("-", "_")
        return enum_cls[name]
    if isinstance(data, dict):
        return enum_cls(data["value"])
    raise ValueError(f"Cannot convert {data!r} to {enum_cls.__name__}")
```

### 4.3 Wildcard Values

BACnet dates and times use `0xFF` to indicate "any" or "unspecified" fields. In JSON, these are represented as `null`:

```json
{
  "year": null,
  "month": 12,
  "day": 25,
  "day_of_week": null
}
```

The `to_dict()` method maps `0xFF` → `None`, and `from_dict()` maps `None` → `0xFF`.

### 4.4 Compound Type Mapping

| BACnet Type     | JSON Representation                                              |
| --------------- | ---------------------------------------------------------------- |
| BACnetDateTime  | `{"date": <Date>, "time": <Time>}`                               |
| BACnetTimeStamp | `{"type": "time" \| "sequence" \| "datetime", "value": <value>}` |
| Priority Array  | `[<value or null>, ...]` (16-element array, null = relinquished) |
| Property Value  | Polymorphic — uses the mapping for the property's declared type  |

## 5. Data Structure Serialization Methods

### 5.1 Primitive Types

Each frozen dataclass gains `to_dict()` and `from_dict()`:

```python
@dataclass(frozen=True, slots=True)
class ObjectIdentifier:
    object_type: ObjectType
    instance_number: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": _enum_name(self.object_type),
            "instance": self.instance_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectIdentifier:
        return cls(
            object_type=_enum_from_dict(ObjectType, data["object_type"]),
            instance_number=data["instance"],
        )


@dataclass(frozen=True, slots=True)
class BACnetDate:
    year: int
    month: int
    day: int
    day_of_week: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": None if self.year == 0xFF else self.year,
            "month": None if self.month == 0xFF else self.month,
            "day": None if self.day == 0xFF else self.day,
            "day_of_week": None if self.day_of_week == 0xFF else self.day_of_week,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetDate:
        return cls(
            year=0xFF if data["year"] is None else data["year"],
            month=0xFF if data["month"] is None else data["month"],
            day=0xFF if data["day"] is None else data["day"],
            day_of_week=0xFF if data["day_of_week"] is None else data["day_of_week"],
        )


@dataclass(frozen=True, slots=True)
class BACnetTime:
    hour: int
    minute: int
    second: int
    hundredth: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": None if self.hour == 0xFF else self.hour,
            "minute": None if self.minute == 0xFF else self.minute,
            "second": None if self.second == 0xFF else self.second,
            "hundredth": None if self.hundredth == 0xFF else self.hundredth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetTime:
        return cls(
            hour=0xFF if data["hour"] is None else data["hour"],
            minute=0xFF if data["minute"] is None else data["minute"],
            second=0xFF if data["second"] is None else data["second"],
            hundredth=0xFF if data["hundredth"] is None else data["hundredth"],
        )


class BitString:
    def to_dict(self) -> dict[str, Any]:
        total_bits = len(self._data) * 8 - self._unused_bits
        return {
            "bits": [self[i] for i in range(total_bits)],
            "unused_bits": self._unused_bits,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BitString:
        bits = data["bits"]
        unused = data.get("unused_bits", 0)
        byte_count = (len(bits) + 7) // 8
        result = bytearray(byte_count)
        for i, bit in enumerate(bits):
            if bit:
                result[i // 8] |= 1 << (7 - (i % 8))
        return cls(bytes(result), unused)
```

### 5.2 BACnet Object Serialization

`BACnetObject` exposes its full property state as a dict:

```python
class BACnetObject:

    def to_dict(self) -> dict[str, Any]:
        """Serialize all properties to a JSON-friendly dict.

        Returns a dict with:
          - "_object_type": object type name
          - "_object_id": object identifier dict
          - One key per property, keyed by lowercase-hyphenated property name
          - Values converted via to_dict() where applicable
        """
        result: dict[str, Any] = {
            "_type": _enum_name(self.OBJECT_TYPE),
            "_id": self._object_id.to_dict(),
        }
        for prop_id, value in self._properties.items():
            key = _enum_name(prop_id)
            result[key] = _serialize_value(value)
        if self._priority_array is not None:
            result["priority-array"] = [
                _serialize_value(v) for v in self._priority_array
            ]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetObject:
        """Reconstruct a BACnet object from a dict.

        The dict must contain "_type" and "_id" keys, plus
        property keys matching PropertyIdentifier names.
        """
        obj_type = _enum_from_dict(ObjectType, data["_type"])
        obj_id = ObjectIdentifier.from_dict(data["_id"])
        obj = create_object(obj_type, obj_id.instance_number)
        for key, value in data.items():
            if key.startswith("_"):
                continue
            prop_name = key.upper().replace("-", "_")
            prop_id = PropertyIdentifier[prop_name]
            obj._properties[prop_id] = _deserialize_value(prop_id, value)
        return obj
```

### 5.3 Object Database Serialization

The entire object database can be exported/imported for snapshots, backups, or external sync:

```python
class ObjectDatabase:

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire object database.

        Returns a dict with:
          - "objects": list of serialized objects
          - "count": number of objects
        """
        return {
            "objects": [obj.to_dict() for obj in self._objects.values()],
            "count": len(self._objects),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectDatabase:
        """Reconstruct an object database from a dict."""
        db = cls()
        for obj_data in data["objects"]:
            obj = BACnetObject.from_dict(obj_data)
            db.add(obj)
        return db
```

### 5.4 Service Result Serialization

Service request/response dataclasses follow the same pattern. Each service request and ACK dataclass implements `to_dict()` and `from_dict()`:

```python
@dataclass(frozen=True, slots=True)
class ReadPropertyACK:
    object_identifier: ObjectIdentifier
    property_identifier: PropertyIdentifier
    property_array_index: int | None = None
    property_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "object_identifier": self.object_identifier.to_dict(),
            "property_identifier": _enum_name(self.property_identifier),
            "value": _serialize_value(self.property_value),
        }
        if self.property_array_index is not None:
            result["array_index"] = self.property_array_index
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReadPropertyACK:
        return cls(
            object_identifier=ObjectIdentifier.from_dict(
                data["object_identifier"]
            ),
            property_identifier=_enum_from_dict(
                PropertyIdentifier, data["property_identifier"]
            ),
            property_array_index=data.get("array_index"),
            property_value=data.get("value"),
        )
```

## 6. Property Value Serialization

Property values require polymorphic serialization because the same JSON key (`"value"`) carries different types depending on the property. The serializer uses a dispatch table keyed by the property's declared type.

### 6.1 Value Serialization Helper

```python
def _serialize_value(value: Any) -> Any:
    """Convert a BACnet property value to a JSON-safe representation.

    Dispatches based on the Python type of the value.
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, IntEnum):
        return {"value": int(value), "name": _enum_name(value)}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return str(value)


def _deserialize_value(prop_id: PropertyIdentifier, value: Any) -> Any:
    """Convert a JSON value back to the appropriate BACnet type.

    Uses the property type registry to determine the expected type.
    """
    info = _PROPERTY_TYPE_REGISTRY.get(prop_id)
    if info is None:
        return value  # Unknown property, return raw

    if value is None:
        return None

    expected_type = info.datatype
    if expected_type is ObjectIdentifier and isinstance(value, dict):
        return ObjectIdentifier.from_dict(value)
    if expected_type is BACnetDate and isinstance(value, dict):
        return BACnetDate.from_dict(value)
    if expected_type is BACnetTime and isinstance(value, dict):
        return BACnetTime.from_dict(value)
    if expected_type is BitString and isinstance(value, dict):
        return BitString.from_dict(value)
    if issubclass(expected_type, IntEnum) and isinstance(value, (dict, str, int)):
        return _enum_from_dict(expected_type, value)
    return value
```

## 7. JSON Output Examples

### 7.1 Single Object

```json
{
  "_type": "analog-input",
  "_id": { "object_type": "analog-input", "instance": 1 },
  "object-identifier": { "object_type": "analog-input", "instance": 1 },
  "object-name": "Zone Temperature",
  "object-type": { "value": 0, "name": "analog-input" },
  "present-value": 72.5,
  "status-flags": {
    "in_alarm": false,
    "fault": false,
    "overridden": false,
    "out_of_service": false
  },
  "units": { "value": 62, "name": "degrees-fahrenheit" },
  "description": "Main zone temperature sensor",
  "cov-increment": 0.5
}
```

### 7.2 ReadProperty Result

```json
{
  "object_identifier": { "object_type": "analog-input", "instance": 1 },
  "property_identifier": "present-value",
  "value": 72.5
}
```

### 7.3 Object Database Export

```json
{
  "objects": [
    {
      "_type": "device",
      "_id": { "object_type": "device", "instance": 1234 },
      "object-name": "Building Controller",
      "vendor-name": "ACME Controls",
      "model-name": "BC-1000",
      "firmware-revision": "1.2.3"
    },
    {
      "_type": "analog-input",
      "_id": { "object_type": "analog-input", "instance": 1 },
      "object-name": "Zone Temperature",
      "present-value": 72.5,
      "units": { "value": 62, "name": "degrees-fahrenheit" }
    },
    {
      "_type": "binary-output",
      "_id": { "object_type": "binary-output", "instance": 1 },
      "object-name": "Fan Control",
      "present-value": 1,
      "priority-array": [
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        1,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null
      ]
    }
  ],
  "count": 3
}
```

### 7.4 Device Discovery (Who-Is/I-Am)

```json
{
  "device_identifier": { "object_type": "device", "instance": 1234 },
  "max_apdu_length": 1476,
  "segmentation_supported": { "value": 0, "name": "both" },
  "vendor_id": 42
}
```

## 8. Error Serialization

BACnet errors, rejects, and aborts serialize with their class, code, and human-readable descriptions:

```python
class BACnetError(BACnetException):

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "error",
            "error_class": _enum_name(self.error_class),
            "error_code": _enum_name(self.error_code),
            "message": str(self),
        }


class BACnetReject(BACnetException):

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "reject",
            "reason": _enum_name(self.reason),
            "message": str(self),
        }


class BACnetAbort(BACnetException):

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "abort",
            "reason": _enum_name(self.reason),
            "message": str(self),
        }
```

Example error JSON:

```json
{
  "type": "error",
  "error_class": "property",
  "error_code": "unknown-property",
  "message": "PROPERTY: UNKNOWN_PROPERTY"
}
```

## 9. Configuration and Options

### 9.1 Serializer Options

The `JsonSerializer` accepts options that control output format:

| Option       | Type   | Default | Description                                                       |
| ------------ | ------ | ------- | ----------------------------------------------------------------- |
| `pretty`     | `bool` | `False` | Indent output with 2 spaces (maps to `OPT_INDENT_2`)              |
| `sort_keys`  | `bool` | `False` | Sort dict keys alphabetically (maps to `OPT_SORT_KEYS`)           |
| `enum_names` | `bool` | `True`  | Include string names in enum output (False = numeric values only) |

### 9.2 Usage Examples

```python
from bac_py.serialization import serialize, get_serializer
from bac_py.serialization.json import JsonSerializer

# Quick one-shot serialization
json_bytes = serialize(analog_input_obj)

# Reusable serializer with options
serializer = JsonSerializer(pretty=True, sort_keys=True)
json_bytes = serializer.encode(analog_input_obj.to_dict())

# Deserialization
from bac_py.serialization import deserialize
data = deserialize(json_bytes)
obj = BACnetObject.from_dict(data)
```

## 10. Integration Patterns

### 10.1 REST API Export

```python
async def handle_read_property(request):
    """HTTP handler that proxies a BACnet ReadProperty to JSON."""
    value = await client.read_property(address, obj_id, prop_id)
    ack = ReadPropertyACK(
        object_identifier=obj_id,
        property_identifier=prop_id,
        property_value=value,
    )
    return Response(
        body=serialize(ack),
        content_type="application/json",
    )
```

### 10.2 COV Notification Streaming

```python
async def cov_to_json_stream(client, address, obj_id, ws):
    """Forward COV notifications as JSON over a WebSocket."""
    serializer = JsonSerializer()

    def on_cov(notification):
        data = notification.to_dict()
        ws.send_bytes(serializer.encode(data))

    await client.subscribe_cov(address, obj_id, callback=on_cov)
```

### 10.3 Database Snapshot

```python
# Export
snapshot = serialize(object_database, pretty=True)
Path("device_snapshot.json").write_bytes(snapshot)

# Import
raw = Path("device_snapshot.json").read_bytes()
data = deserialize(raw)
db = ObjectDatabase.from_dict(data)
```

## 11. Design Decisions

### 11.1 Why `to_dict()` / `from_dict()` Instead of Direct orjson Hooks?

orjson's `default` parameter can serialize custom types directly, but:

- `to_dict()` is format-agnostic — the same dict works for JSON, MessagePack, YAML, or database inserts.
- `from_dict()` enables deserialization, which `default` cannot.
- Explicit methods are discoverable and testable independently of the serializer.
- orjson's native dataclass serialization produces field-name keys, but BACnet types need custom representations (e.g., `ObjectIdentifier` as `{object_type, instance}` rather than `{object_type, instance_number}`).

The `default` function in `JsonSerializer` calls `to_dict()` as a fallback, so objects passed directly to `orjson.dumps()` still serialize correctly.

### 11.2 Why Enum Dicts Instead of Bare Names or Integers?

External systems may need the numeric wire value (for protocol-level tooling) or the human-readable name (for dashboards). The `{"value": int, "name": str}` format serves both. On deserialization, all three forms are accepted (int, string, or dict) for maximum interoperability.

### 11.3 Why Hex for Octet Strings?

BACnet Octet Strings are raw binary data. Base64 is more compact but hex is easier to inspect visually and matches common BACnet tooling conventions. JSON does not support raw binary, so a string encoding is required.

### 11.4 Why Optional Dependency?

The core bac-py library maintains zero mandatory external dependencies. orjson is only needed when serialization features are used. Users who only need the BACnet protocol stack (encode/decode/transport) should not be forced to install a compiled extension. The `serialization` extra makes the dependency explicit and opt-in.

## 12. Testing Strategy

### 12.1 Round-Trip Tests

Every type with `to_dict()` / `from_dict()` must pass a round-trip test:

```python
def test_object_identifier_round_trip():
    original = ObjectIdentifier(ObjectType.ANALOG_INPUT, 42)
    data = original.to_dict()
    json_bytes = orjson.dumps(data)
    restored_data = orjson.loads(json_bytes)
    restored = ObjectIdentifier.from_dict(restored_data)
    assert restored == original


def test_bacnet_object_round_trip():
    obj = AnalogInputObject(1, object_name="Temp Sensor")
    obj._properties[PropertyIdentifier.PRESENT_VALUE] = 72.5
    data = obj.to_dict()
    json_bytes = orjson.dumps(data)
    restored_data = orjson.loads(json_bytes)
    restored = BACnetObject.from_dict(restored_data)
    assert restored.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.5
    assert restored.read_property(PropertyIdentifier.OBJECT_NAME) == "Temp Sensor"
```

### 12.2 Enum Deserialization Flexibility

```python
@pytest.mark.parametrize("input_val", [
    0,                                          # int
    "analog-input",                             # hyphenated name
    {"value": 0, "name": "analog-input"},       # full dict
])
def test_enum_from_dict_accepts_all_forms(input_val):
    result = _enum_from_dict(ObjectType, input_val)
    assert result == ObjectType.ANALOG_INPUT
```

### 12.3 Wildcard Handling

```python
def test_date_wildcard_round_trip():
    date = BACnetDate(year=0xFF, month=12, day=25, day_of_week=0xFF)
    data = date.to_dict()
    assert data["year"] is None
    assert data["day_of_week"] is None
    restored = BACnetDate.from_dict(data)
    assert restored == date
```

### 12.4 Object Database Export/Import

```python
def test_object_database_round_trip():
    db = ObjectDatabase()
    db.add(DeviceObject(1234, object_name="Test Device"))
    db.add(AnalogInputObject(1, object_name="Temp"))
    data = db.to_dict()
    json_bytes = serialize(data)
    restored_data = deserialize(json_bytes)
    restored_db = ObjectDatabase.from_dict(restored_data)
    assert len(restored_db) == 2
```
