# bac-py

Asynchronous BACnet/IP protocol library for Python 3.13+, implementing ASHRAE Standard 135-2020. Zero required runtime dependencies, built on native `asyncio`.

```python
from bac_py import Client

async with Client(instance_number=999) as client:
    value = await client.read("192.168.1.100", "ai,1", "pv")
```

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Levels](#api-levels)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Examples](#examples)
- [Testing](#testing)
- [Requirements](#requirements)
- [License](#license)

## Features

| Category | Highlights |
|----------|-----------|
| **Transports** | BACnet/IP (Annex J), BACnet/IPv6 with BBMD and foreign device (Annex U), BACnet Ethernet (Clause 7), BACnet Secure Connect over WebSocket/TLS (Annex AB) |
| **Client & Server** | Full-duplex -- serve objects and issue requests from the same application |
| **Object Model** | 40+ object types with property definitions, priority arrays, and commandable outputs |
| **Services** | All confirmed and unconfirmed services including COV, alarms, file access, audit logging, and private transfer |
| **Event Reporting** | All 18 event algorithms, intrinsic reporting, NotificationClass routing with day/time filtering |
| **Engines** | Schedule evaluation, trend logging (polled/COV/triggered), and audit record generation |
| **Networking** | Multi-port routing, BBMD, foreign device registration, segmented transfers, device info caching |
| **Convenience API** | String-based addressing (`"ai,1"`, `"pv"`), smart type coercion, auto-discovery |
| **Serialization** | `to_dict()`/`from_dict()` on all data types; optional `orjson` backend |
| **Quality** | 6,100+ unit tests, Docker integration tests, type-safe enums and frozen dataclasses throughout |

## Installation

```bash
pip install bac-py
```

Optional extras:

```bash
pip install bac-py[serialization]          # orjson for JSON serialization
pip install bac-py[secure]                 # WebSocket + TLS for BACnet Secure Connect
pip install bac-py[serialization,secure]   # Both
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
    await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
    await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)
    await client.write("192.168.1.100", "av,1", "pv", None, priority=8)  # Relinquish
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

### Discover Devices

```python
from bac_py import Client

async with Client(instance_number=999) as client:
    devices = await client.discover(timeout=3.0)
    for dev in devices:
        print(f"  {dev.instance}  {dev.address_str}  vendor={dev.vendor_id}")
```

### Subscribe to COV

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

### Serve Objects

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

The server automatically handles ReadProperty, WriteProperty,
ReadPropertyMultiple, WritePropertyMultiple, ReadRange, Who-Is, COV
subscriptions, device management, file access, and object management.

## API Levels

bac-py offers two API levels:

**`Client`** -- simplified wrapper for common tasks. Accepts string addresses,
string object/property identifiers, and Python values. Ideal for scripts,
integrations, and most client-side work.

**`BACnetApplication` + `BACnetClient`** -- full protocol-level access for
server handlers, router mode, custom service registration, raw encoded bytes,
and direct transport/network layer access.

The `Client` wrapper exposes both levels. All `BACnetClient` protocol-level
methods are available alongside the convenience methods, and the underlying
`BACnetApplication` is accessible via `client.app`.

### Protocol-Level Example

```python
from bac_py.encoding.primitives import encode_application_real
from bac_py.network.address import parse_address
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

async with Client(instance_number=999) as client:
    address = parse_address("192.168.1.100")
    obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

    await client.write_property(
        address, obj_id,
        PropertyIdentifier.PRESENT_VALUE,
        value=encode_application_real(72.5),
        priority=8,
    )
```

## Configuration

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

```
src/bac_py/
  app/            Application orchestration, client API, server handlers,
                  event engine, schedule engine, trend log engine, audit manager
  encoding/       ASN.1/BER tag-length-value encoding and APDU codec
  network/        Addressing, NPDU network layer, multi-port router
  objects/        40+ BACnet object types with property definitions
  segmentation/   Segmented message assembly and transmission
  serialization/  JSON serialization (optional orjson backend)
  services/       Service request/response types and handler registry
  transport/      BACnet/IP, BACnet/IPv6, Ethernet 802.3, BACnet Secure Connect
  types/          Primitive types, enumerations, constructed types
  conformance/    BIBB declarations and PICS generation
```

### Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `Client` | `client` | Simplified async context manager for client use |
| `BACnetApplication` | `app.application` | Central orchestrator -- lifecycle, APDU dispatch, engines |
| `BACnetClient` | `app.client` | Full async API for all BACnet services |
| `DefaultServerHandlers` | `app.server` | Standard service handlers for a server device |
| `DeviceObject` | `objects.device` | Required device object (Clause 12.11) |
| `ObjectDatabase` | `objects.base` | Runtime registry of local BACnet objects |
| `BACnetAddress` | `network.address` | Network + MAC address for device targeting |
| `ObjectIdentifier` | `types.primitives` | Object type + instance number |

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

The [`examples/`](examples/) directory contains 21 runnable scripts. See the
[Examples Guide](https://jscott3201.github.io/bac-py/guide/examples.html) for
detailed walkthroughs.

| File | Description |
|------|-------------|
| `read_value.py` | Read properties with short aliases |
| `write_value.py` | Write values with auto-encoding and priority |
| `read_multiple.py` | Read multiple properties from multiple objects |
| `write_multiple.py` | Write multiple properties in a single request |
| `discover_devices.py` | Discover devices with Who-Is broadcast |
| `extended_discovery.py` | Extended discovery with profile metadata |
| `advanced_discovery.py` | Who-Has, unconfigured devices, hierarchy traversal |
| `monitor_cov.py` | Subscribe to COV and decode notifications |
| `cov_property.py` | Property-level COV subscriptions with increment |
| `alarm_management.py` | Alarm/enrollment summary, event info, acknowledgment |
| `text_message.py` | Send confirmed/unconfirmed text messages |
| `backup_restore.py` | Backup and restore device configuration |
| `object_management.py` | Create, list, and delete objects |
| `device_control.py` | Communication control, reinitialization, time sync |
| `audit_log.py` | Query audit log records with pagination |
| `router_discovery.py` | Discover routers and remote networks |
| `foreign_device.py` | Register as foreign device via BBMD |
| `secure_connect.py` | Connect to a BACnet/SC hub and exchange NPDUs |
| `secure_connect_hub.py` | Run a BACnet/SC hub with object serving |
| `ip_to_sc_router.py` | Bridge BACnet/IP and BACnet/SC networks |
| `sc_generate_certs.py` | Generate test PKI and demonstrate TLS-secured SC |

## Testing

```bash
make test          # 6,100+ unit tests
make lint          # ruff check + format verification
make typecheck     # mypy
make docs          # sphinx-build
make check         # all of the above
make coverage      # tests with coverage report
make fix           # auto-fix lint/format issues
```

### Docker Integration Tests

Real BACnet communication over UDP and WebSocket between containers:

```bash
make docker-build                # Build image (Alpine + uv + orjson)
make docker-test                 # All integration scenarios
make docker-test-client          # Client/server: read, write, discover, RPM, WPM
make docker-test-bbmd            # BBMD: foreign device registration + forwarding
make docker-test-router          # Router: cross-network discovery and reads
make docker-test-stress          # BIP stress: sustained throughput (60s)
make docker-test-sc              # Secure Connect: hub, node, NPDU relay
make docker-test-sc-stress       # SC stress: WebSocket throughput (60s)
make docker-test-router-stress   # Router stress: cross-network routing (60s)
make docker-test-bbmd-stress     # BBMD stress: foreign device throughput (60s)
make docker-test-device-mgmt     # Device management: DCC, time sync, text message
make docker-test-cov-advanced    # COV: concurrent subscriptions, property-level COV
make docker-test-events          # Events: alarm reporting, acknowledgment, queries
make docker-test-ipv6            # IPv6: BACnet/IPv6 client/server (Annex U)
make docker-stress               # BIP stress runner (JSON report to stdout)
make docker-sc-stress            # SC stress runner (JSON report to stdout)
make docker-router-stress        # Router stress runner (JSON report to stdout)
make docker-bbmd-stress          # BBMD stress runner (JSON report to stdout)
make docker-clean                # Cleanup
```

## Requirements

- Python >= 3.13
- No runtime dependencies for BACnet/IP, BACnet/IPv6, and BACnet Ethernet
- Optional: `orjson` for JSON serialization (`pip install bac-py[serialization]`)
- Optional: `websockets` + `cryptography` for BACnet Secure Connect (`pip install bac-py[secure]`)
- Docker and Docker Compose for integration tests

## License

MIT
