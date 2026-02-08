# bac-py Examples

Usage examples for the bac-py BACnet/IP library. Each file is a standalone
script demonstrating a specific area of the API.

## Examples

### `read_property.py` - Reading Properties

Read operations against remote BACnet devices:

- **Single property read** - Read one property from one object
- **Object name read** - Read string properties
- **Array-indexed read** - Read individual elements from array properties (e.g., Object_List)
- **ReadPropertyMultiple** - Batch-read multiple properties from multiple objects
- **Error handling** - Handling BACnetError, BACnetRejectError, BACnetAbortError, and BACnetTimeoutError

### `write_property.py` - Writing Properties

Write operations to remote BACnet devices:

- **Analog value write** - Write a float (REAL) to an Analog Value
- **Priority write** - Write with a specific priority level (1-16)
- **Binary output write** - Write ACTIVE/INACTIVE to a Binary Output
- **String write** - Write a CharacterString to Object_Name
- **WritePropertyMultiple** - Batch-write to multiple objects
- **Multi-state write** - Write a state index to a Multi-State Value

### `discovery.py` - Device and Object Discovery

Network discovery using Who-Is/I-Am and Who-Has/I-Have:

- **Discover all devices** - Global Who-Is broadcast
- **Discover device range** - Who-Is with instance number limits
- **Local network only** - Who-Is with LOCAL_BROADCAST
- **Find specific device** - Who-Is targeting a single instance
- **Find object by ID** - Who-Has with an ObjectIdentifier
- **Find object by name** - Who-Has with a name string
- **Discover then read** - Common workflow combining discovery and property reads

### `configuration.py` - Device Configuration

Setting up devices, objects, and the object database:

- **Basic config** - Minimal DeviceConfig with defaults
- **Full config** - All DeviceConfig parameters explained
- **Client-only config** - Configuration for read/write-only tools
- **Device object** - Creating and configuring the required DeviceObject
- **Analog objects** - AnalogInput, AnalogOutput, AnalogValue with units and limits
- **Binary objects** - BinaryInput, BinaryOutput, BinaryValue with active/inactive text
- **Multi-state objects** - MultiStateInput, MultiStateOutput, MultiStateValue with state text
- **Complete device** - Full device assembly with object database

### `client_operations.py` - Advanced Client Operations

Beyond basic reads and writes:

- **COV subscriptions** - Subscribe to value change notifications (confirmed and unconfirmed)
- **Device communication control** - Enable/disable remote device communication
- **Device reinitialization** - Request warm/cold start on remote devices
- **Time synchronization** - Broadcast local or UTC time to devices
- **File access** - Read/write files via AtomicReadFile/AtomicWriteFile
- **Object management** - Create and delete objects on remote devices
- **ReadRange** - Read portions of large list properties
- **Private transfer** - Vendor-specific confirmed and unconfirmed services

### `server_operations.py` - Server Device Operation

Running BACnet devices that serve objects to the network:

- **Basic server** - Minimal device with default service handlers
- **Simulated data** - Server with periodic sensor value updates and COV
- **Multiple devices** - Two independent devices on different ports

```bash
# Run a specific server example:
python examples/server_operations.py basic
python examples/server_operations.py simulated
python examples/server_operations.py multi
```

## Prerequisites

Install bac-py in your Python environment:

```bash
pip install -e .
```

## Network Notes

- The default BACnet/IP port is **47808** (0xBAC0)
- Examples use `0.0.0.0` to bind to all interfaces; change to a specific IP for multi-homed systems
- Device instance numbers must be unique on the network (0 - 4194302)
- Instance 4194303 is reserved as a wildcard

## Value Encoding

Write operations require application-tagged encoded bytes. Use the helpers
in `bac_py.encoding.primitives`:

```python
from bac_py.encoding.primitives import (
    encode_application_real,            # float -> REAL
    encode_application_unsigned,        # int -> Unsigned
    encode_application_signed,          # int -> Signed
    encode_application_enumerated,      # int/IntEnum -> Enumerated
    encode_application_character_string, # str -> CharacterString
    encode_application_boolean,         # bool -> Boolean
    encode_application_octet_string,    # bytes -> OctetString
    encode_application_null,            # -> Null
    encode_application_object_id,       # (type, instance) -> ObjectIdentifier
    encode_application_date,            # BACnetDate -> Date
    encode_application_time,            # BACnetTime -> Time
    encode_application_bit_string,      # BitString -> BitString
)
```
