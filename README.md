# bac-py

Asynchronous BACnet/IP protocol library for Python 3.13+, implementing
ASHRAE Standard 135-2020.

bac-py provides client and server capabilities for BACnet/IP networks with a
clean, layered architecture. It is built on native `asyncio` with zero required
dependencies.

```python
from bac_py import Client

async with Client(instance_number=999) as client:
    value = await client.read("192.168.1.100", "ai,1", "pv")
```

## Features

- **Full BACnet/IP support** per Annex J over UDP
- **Client and server** in a single library
- **Simplified convenience API** with string-based addressing and auto-encoding
- **Async-first** design using native `asyncio`
- **Zero dependencies** for the core library (optional `orjson` for JSON serialization)
- **Complete object model** -- Device, Analog/Binary/MultiState I/O/Value, File, Schedule, TrendLog, and more
- **All standard services** -- property access, discovery, COV, event notification, device management, file access, object management, audit logging, private transfer
- **Segmentation** -- automatic segmented request/response handling (Clause 5.2)
- **Network routing** -- multi-port router with dynamic routing tables (Clause 6)
- **BBMD** -- broadcast management device and foreign device registration
- **Priority array** -- 16-level command prioritization for commandable objects
- **Event reporting** -- all 18 event algorithms, intrinsic reporting, NotificationClass routing
- **Audit logging** -- automatic audit records for write/create/delete operations (new in 2020)
- **Scheduling** -- weekly and exception schedules with calendar-aware evaluation
- **Trend logging** -- polled, COV, and triggered acquisition with circular buffer management
- **Device info caching** -- automatic caching of peer device capabilities from I-Am responses (Clause 19.4) for correct APDU size negotiation
- **BACnet Ethernet** -- raw IEEE 802.3 transport with 802.2 LLC headers for legacy Ethernet data links (Clause 7)
- **BACnet/IPv6** -- full Annex U transport with VMAC addressing and multicast
- **Smart encoding** -- property-aware type coercion for writes (int to Real for analog, Enumerated for binary, etc.)
- **JSON serialization** -- `to_dict()`/`from_dict()` on all data types, optional `orjson` backend
- **Type-safe** -- enums, frozen dataclasses, and comprehensive type hints throughout
- **Docker integration tests** -- real UDP communication between containers for client/server, BBMD, router, and stress scenarios

## Installation

```bash
pip install bac-py
```

With optional JSON serialization:

```bash
pip install bac-py[serialization]
```

### Development

```bash
git clone https://github.com/jscott3201/bac-py.git
cd bac-py
uv sync --group dev
```

## Quick Start

### Read a Property

```python
import asyncio
from bac_py import Client


async def main():
    async with Client(instance_number=999) as client:
        value = await client.read("192.168.1.100", "ai,1", "pv")
        print(f"Temperature: {value}")


asyncio.run(main())
```

The convenience API accepts short aliases (`ai`, `ao`, `av`, `bi`, `bo`, `bv`,
`msv`, `dev`, etc.) and common property abbreviations (`pv`, `name`, `desc`,
`units`, `sf`, etc.). Full names like `"analog-input,1"` and `"present-value"`
also work.

### Write a Value

```python
async with Client(instance_number=999) as client:
    # Float to analog -> encoded as Real
    await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)

    # Int to binary -> encoded as Enumerated
    await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)

    # None -> Null (relinquish a command priority)
    await client.write("192.168.1.100", "av,1", "pv", None, priority=8)

    # String property
    await client.write("192.168.1.100", "av,1", "object-name", "Zone Temp SP")
```

Values are automatically encoded to the correct BACnet application tag based on
the Python type, target object type, and property:

| Python type            | BACnet encoding            |
| ---------------------- | -------------------------- |
| `float`                | Real                       |
| `int` (analog PV)      | Real                       |
| `int` (binary PV)      | Enumerated                 |
| `int` (multi-state PV) | Unsigned                   |
| `str`                  | Character String           |
| `bool`                 | Enumerated (1/0)           |
| `None`                 | Null                       |
| `IntEnum`              | Enumerated                 |
| `bytes`                | Pass-through (pre-encoded) |

For non-present-value properties, a built-in type hint map ensures common
properties like `units`, `cov-increment`, `high-limit`, and `out-of-service`
are encoded correctly even when given a plain `int`.

### Read Multiple Properties

```python
async with Client(instance_number=999) as client:
    results = await client.read_multiple("192.168.1.100", {
        "ai,1": ["pv", "object-name", "units"],
        "ai,2": ["pv", "object-name"],
        "av,1": ["pv", "priority-array"],
    })

    for obj_id, props in results.items():
        print(f"{obj_id}:")
        for name, value in props.items():
            print(f"  {name}: {value}")
```

Uses ReadPropertyMultiple under the hood for efficiency.

### Discover Devices

```python
from bac_py import Client, DiscoveredDevice

async with Client(instance_number=999) as client:
    devices = await client.discover(timeout=3.0)

    for dev in devices:
        print(f"  {dev.instance}  {dev.address_str}  vendor={dev.vendor_id}")
```

`discover()` returns `DiscoveredDevice` objects with the responding device's
address, instance number, vendor ID, max APDU length, and segmentation support.
Use `low_limit` and `high_limit` to filter by instance range.

### Subscribe to COV Notifications

```python
from bac_py import Client, decode_cov_values

async with Client(instance_number=999) as client:
    def on_notification(notification, source):
        values = decode_cov_values(notification)
        for name, value in values.items():
            print(f"  {name}: {value}")

    await client.subscribe_cov_ex(
        "192.168.1.100", "ai,1",
        process_id=1,
        callback=on_notification,
        lifetime=3600,
    )
```

### Serve Objects on the Network

```python
from bac_py import BACnetApplication, DefaultServerHandlers, DeviceConfig, DeviceObject
from bac_py.objects.analog import AnalogInputObject
from bac_py.types.enums import EngineeringUnits


async def serve():
    config = DeviceConfig(
        instance_number=100,
        name="My-Device",
        vendor_name="ACME",
        vendor_id=999,
    )

    async with BACnetApplication(config) as app:
        device = DeviceObject(
            instance_number=100,
            object_name="My-Device",
            vendor_name="ACME",
            vendor_identifier=999,
        )
        app.object_db.add(device)

        app.object_db.add(AnalogInputObject(
            instance_number=1,
            object_name="Temperature",
            units=EngineeringUnits.DEGREES_CELSIUS,
            present_value=22.5,
        ))

        handlers = DefaultServerHandlers(app, app.object_db, device)
        handlers.register()

        await app.run()
```

The server handles ReadProperty, WriteProperty, ReadPropertyMultiple,
WritePropertyMultiple, ReadRange, Who-Is, COV subscriptions, device management,
file access, and object management requests automatically.

## Progressive Disclosure

bac-py has two API levels. Use whichever fits your needs:

**`Client`** -- simplified wrapper for common client tasks. Combines
`BACnetApplication` and `BACnetClient` into a single async context manager.
Accepts string addresses, string object/property identifiers, and Python
values. Ideal for scripts, integrations, and most client-side work.

**`BACnetApplication` + `BACnetClient`** -- full protocol-level access. Use
this when you need server handlers, router mode, custom service registration,
raw encoded bytes, or direct access to the transport and network layers.

The `Client` wrapper exposes both levels. All `BACnetClient` protocol-level
methods are available alongside the convenience methods, and the underlying
`BACnetApplication` is accessible via `client.app`.

## Configuration

`DeviceConfig` controls device identity and network parameters:

```python
from bac_py.app.application import DeviceConfig

config = DeviceConfig(
    instance_number=999,          # Device instance (0-4194302)
    name="bac-py",                # Device name
    vendor_name="bac-py",         # Vendor name
    vendor_id=0,                  # ASHRAE vendor ID
    interface="0.0.0.0",          # IP address to bind
    port=0xBAC0,                  # UDP port (47808)
    max_apdu_length=1476,         # Max APDU size
    apdu_timeout=6000,            # Request timeout (ms)
    apdu_retries=3,               # Retry count
    max_segments=None,            # Max segments (None = unlimited)
)
```

For multi-network routing, add a `RouterConfig`:

```python
from bac_py.app.application import DeviceConfig, RouterConfig, RouterPortConfig

config = DeviceConfig(
    instance_number=999,
    router_config=RouterConfig(
        ports=[
            RouterPortConfig(port_id=0, network_number=1,
                             interface="192.168.1.10", port=47808),
            RouterPortConfig(port_id=1, network_number=2,
                             interface="10.0.0.10", port=47808),
        ],
        application_port_id=0,
    ),
)
```

## Architecture

```text
src/bac_py/
  app/            High-level application, client API, server handlers, TSM,
                  event engine, schedule engine, trendlog engine, audit manager
  conformance/    BIBB declarations and PICS generation
  encoding/       ASN.1/BER tag-length-value encoding and APDU codec
  network/        Addressing, NPDU network layer, multi-port router
  objects/        BACnet object model (Device, Analog, Binary, MultiState, ...)
  segmentation/   Segmented message assembly and transmission
  serialization/  JSON serialization (optional orjson backend)
  services/       Service request/response types and registry
  transport/      BACnet/IP (Annex J) UDP, BACnet/IPv6, Ethernet, BVLL, BBMD
  types/          Primitive types, enumerations, and string parsing
```

### Key Classes

| Class                   | Module             | Purpose                                                          |
| ----------------------- | ------------------ | ---------------------------------------------------------------- |
| `Client`                | `client`           | Simplified async context manager for client use cases            |
| `BACnetApplication`     | `app.application`  | Central orchestrator -- lifecycle, APDU dispatch, COV management |
| `DeviceConfig`          | `app.application`  | Device identity, network binding, and APDU parameters            |
| `BACnetClient`          | `app.client`       | Full async API for all BACnet services                           |
| `DiscoveredDevice`      | `app.client`       | Device info returned by `discover()`                             |
| `DefaultServerHandlers` | `app.server`       | Standard service handlers for a server device                    |
| `ObjectDatabase`        | `objects.base`     | Registry of local BACnet objects                                 |
| `BACnetObject`          | `objects.base`     | Base class for all object types                                  |
| `DeviceObject`          | `objects.device`   | Required device object (Clause 12.11)                            |
| `BACnetAddress`         | `network.address`  | Network + MAC address for device targeting                       |
| `ObjectIdentifier`      | `types.primitives` | Object type + instance number                                    |
| `ServiceRegistry`       | `services.base`    | Maps service choices to handler functions                        |

### Supported Object Types

Device, Analog Input/Output/Value, Binary Input/Output/Value, Multi-State
Input/Output/Value, Accumulator, Calendar, Channel, Command, Event Enrollment,
File, Life Safety Point/Zone, Loop, Network Port, Notification Class,
Notification Forwarder, Program, Schedule, Trend Log, Trend Log Multiple,
Audit Reporter, Audit Log, Access Door/Point/Zone/Credential/Rights,
Credential Data Input, Timer, Staging, Load Control, Lighting Output,
Elevator, Escalator Group, Lift, Alert Enrollment, Event Log, Averaging,
Pulse Converter, Group, Global Group, Structured View, and generic value types
(BitString, CharacterString, Date, DateTime, Integer, LargeAnalog, OctetString,
PositiveInteger, Time, and pattern variants).

### Supported Services

**Confirmed:** ReadProperty, WriteProperty, ReadPropertyMultiple,
WritePropertyMultiple, ReadRange, CreateObject, DeleteObject,
AddListElement, RemoveListElement, AtomicReadFile, AtomicWriteFile,
SubscribeCOV, ConfirmedEventNotification, AcknowledgeAlarm,
GetAlarmSummary, GetEnrollmentSummary, GetEventInformation,
ConfirmedTextMessage, ConfirmedAuditNotification *(2020)*,
AuditLogQuery *(2020)*, VT-Open, VT-Close, VT-Data,
DeviceCommunicationControl, ReinitializeDevice,
ConfirmedPrivateTransfer.

**Unconfirmed:** Who-Is/I-Am, Who-Has/I-Have,
TimeSynchronization/UTCTimeSynchronization, UnconfirmedCOVNotification,
UnconfirmedEventNotification, UnconfirmedTextMessage,
UnconfirmedAuditNotification *(2020)*, Who-Am-I/You-Are *(2020)*,
WriteGroup, UnconfirmedPrivateTransfer.

### Error Handling

All client methods raise from a common exception hierarchy:

```python
from bac_py.services.errors import (
    BACnetBaseError,       # Base for all BACnet errors
    BACnetError,           # Error-PDU (error_class, error_code)
    BACnetRejectError,     # Reject-PDU (reason)
    BACnetAbortError,      # Abort-PDU (reason)
    BACnetTimeoutError,    # Timeout after all retries
)
```

## Examples

The [`examples/`](examples/) directory contains runnable scripts:

| File                      | Description                                          |
| ------------------------- | ---------------------------------------------------- |
| `read_value.py`           | Read properties with short aliases                   |
| `write_value.py`          | Write values with auto-encoding and priority         |
| `read_multiple.py`        | Read multiple properties from multiple objects       |
| `write_multiple.py`       | Write multiple properties in a single request        |
| `discover_devices.py`     | Discover devices with Who-Is broadcast               |
| `extended_discovery.py`   | Extended discovery with profile metadata             |
| `advanced_discovery.py`   | Who-Has, unconfigured devices, hierarchy traversal   |
| `monitor_cov.py`          | Subscribe to COV and decode notifications            |
| `cov_property.py`         | Property-level COV subscriptions with increment      |
| `alarm_management.py`     | Alarm/enrollment summary, event info, acknowledgment |
| `text_message.py`         | Send confirmed/unconfirmed text messages             |
| `backup_restore.py`       | Backup and restore device configuration              |
| `object_management.py`    | Create, list, and delete objects                     |
| `device_control.py`       | Communication control, reinitialization, time sync   |
| `audit_log.py`            | Query audit log records with pagination              |
| `router_discovery.py`     | Discover routers and remote networks                 |
| `foreign_device.py`       | Register as foreign device via BBMD                  |

## Protocol-Level API

For cases where the convenience API isn't sufficient, you can use the
protocol-level methods directly. These accept explicit `BACnetAddress`,
`ObjectIdentifier`, and `PropertyIdentifier` types, and work with raw
application-tagged bytes.

```python
from bac_py.encoding.primitives import encode_application_real
from bac_py.network.address import parse_address
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

async with Client(instance_number=999) as client:
    address = parse_address("192.168.1.100")
    obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

    # Protocol-level write with explicit encoding
    await client.write_property(
        address, obj_id,
        PropertyIdentifier.PRESENT_VALUE,
        value=encode_application_real(72.5),
        priority=8,
    )

    # Protocol-level read returning raw ACK
    ack = await client.read_property(
        address, obj_id,
        PropertyIdentifier.PRESENT_VALUE,
    )
    print(ack.property_value.hex())
```

Encoding helpers for all BACnet application types are available in
`bac_py.encoding.primitives`:

```python
from bac_py.encoding.primitives import (
    encode_application_real,              # float -> Real
    encode_application_unsigned,          # int -> Unsigned
    encode_application_signed,            # int -> Signed
    encode_application_enumerated,        # int -> Enumerated
    encode_application_character_string,  # str -> CharacterString
    encode_application_boolean,           # bool -> Boolean
    encode_application_octet_string,      # bytes -> OctetString
    encode_application_null,              # None -> Null
    encode_application_object_id,         # (type, instance) -> ObjectId
    encode_application_date,              # BACnetDate -> Date
    encode_application_time,              # BACnetTime -> Time
    encode_application_bit_string,        # BitString -> BitString
)
```

## Testing

```bash
# Run the unit test suite (4,920+ tests)
make test

# With coverage
make coverage

# Linting and formatting
make lint

# Auto-fix lint issues
make fix

# Type checking
make typecheck

# Documentation build
make docs

# Run all checks (lint + typecheck + test + docs)
make check
```

### Docker Integration Tests

Docker-based tests exercise real BACnet/IP communication over actual UDP sockets
between separate application instances running in containers:

```bash
# Build the Docker image (Alpine + uv + orjson)
make docker-build

# Run all integration scenarios
make docker-test

# Individual scenarios
make docker-test-client       # Client/server: read, write, discover, RPM, WPM
make docker-test-bbmd         # BBMD: foreign device registration + forwarding
make docker-test-router       # Router: cross-network discovery and reads
make docker-test-stress       # Stress: concurrent and sequential throughput
make docker-test-device-mgmt  # Device management: DCC, time sync, text message
make docker-test-cov-advanced # COV: concurrent subscriptions, property-level COV
make docker-test-events       # Events: alarm reporting, acknowledgment, queries

# Full stress test with JSON throughput report
make docker-stress

# Cleanup
make docker-clean
```

The Docker infrastructure is under `docker/` and uses Docker Compose with
separate bridge networks to simulate realistic BACnet/IP topologies:

| Scenario          | What it tests                                            |
| ----------------- | -------------------------------------------------------- |
| Client/Server     | ReadProperty, WriteProperty, RPM, WPM, Who-Is, discover |
| BBMD              | Foreign device registration, BDT/FDT reads, forwarding  |
| Router            | Who-Is-Router, cross-network discovery and reads         |
| Stress            | 10 concurrent clients, 100 sequential reads, throughput  |
| Device Management | DCC, time synchronization, text messages, private transfer |
| COV Advanced      | Concurrent COV subscriptions, property-level COV, lifetimes |
| Events            | Alarm reporting, acknowledgment, event queries           |
| Demo              | Interactive demonstration of client/server capabilities  |

## Requirements

- Python >= 3.13
- No runtime dependencies (optional: `orjson` for JSON serialization)
- Docker and Docker Compose for integration tests (optional)

## License

MIT
