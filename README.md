# bac-py

Asynchronous BACnet/IP protocol library for Python 3.13+, implementing
ASHRAE Standard 135-2016.

bac-py provides both client and server capabilities for BACnet/IP networks
with a clean, layered architecture. It is built on native `asyncio` with
zero required dependencies.

## Features

- **Full BACnet/IP support** per Annex J over UDP
- **Client and server** in a single library
- **Async-first** design using native `asyncio`
- **Zero dependencies** for the core library (optional `orjson` for JSON serialization)
- **Complete object model** -- Device, Analog/Binary/MultiState I/O/Value, File, Schedule, TrendLog, and more
- **Property access** -- ReadProperty, WriteProperty, ReadPropertyMultiple, WritePropertyMultiple, ReadRange
- **Discovery** -- Who-Is/I-Am, Who-Has/I-Have
- **Change of Value** -- SubscribeCOV with confirmed and unconfirmed notifications
- **Device management** -- DeviceCommunicationControl, ReinitializeDevice, TimeSynchronization
- **File access** -- AtomicReadFile, AtomicWriteFile (stream and record)
- **Object management** -- CreateObject, DeleteObject, AddListElement, RemoveListElement
- **Private transfer** -- Confirmed and unconfirmed vendor-specific services
- **Segmentation** -- Automatic segmented request/response handling (Clause 5.2)
- **Priority array** -- 16-level command prioritization for commandable objects
- **Type-safe** -- Enums, frozen dataclasses, and comprehensive type hints throughout

## Installation

```bash
pip install bac-py
```

Or with JSON serialization support:

```bash
pip install bac-py[serialization]
```

### Development

```bash
git clone <repo-url>
cd bac-py
uv sync --group dev
```

## Quick Start

### Client -- Read a Property

```python
import asyncio
from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient
from bac_py.network.address import BACnetAddress
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


async def main():
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        # Target device at 192.168.1.100 on the standard BACnet port
        target = BACnetAddress(
            mac_address=bytes([192, 168, 1, 100, 0xBA, 0xC0])
        )

        ack = await client.read_property(
            target,
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            PropertyIdentifier.PRESENT_VALUE,
        )
        print(f"Value: {ack.property_value.hex()}")


asyncio.run(main())
```

### Client -- Discover Devices

```python
async def discover():
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        devices = await client.who_is(timeout=3.0)
        for iam in devices:
            print(
                f"Device {iam.object_identifier.instance_number}  "
                f"vendor={iam.vendor_id}  max_apdu={iam.max_apdu_length}"
            )
```

### Client -- Write a Property

```python
from bac_py.encoding.primitives import encode_application_real

async def write():
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = BACnetAddress(
            mac_address=bytes([192, 168, 1, 100, 0xBA, 0xC0])
        )

        await client.write_property(
            target,
            ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
            PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_real(72.5),
            priority=8,
        )
```

### Server -- Serve Objects on the Network

```python
from bac_py.app.server import DefaultServerHandlers
from bac_py.objects.device import DeviceObject
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

        # Blocks until stopped
        await app.run()
```

## Architecture

```text
src/bac_py/
  app/            High-level application, client API, server handlers, TSM
  encoding/       ASN.1/BER tag-length-value encoding and APDU codec
  network/        Addressing and NPDU network layer
  objects/        BACnet object model (Device, Analog, Binary, MultiState, ...)
  segmentation/   Segmented message assembly and transmission
  serialization/  JSON serialization (optional orjson backend)
  services/       Service request/response types and registry
  transport/      BACnet/IP (Annex J) UDP transport, BVLL, BBMD
  types/          Primitive types, enumerations, and constructed types
```

### Key Classes

| Class                   | Module             | Purpose                                                          |
| ----------------------- | ------------------ | ---------------------------------------------------------------- |
| `BACnetApplication`     | `app.application`  | Central orchestrator -- lifecycle, APDU dispatch, COV management |
| `DeviceConfig`          | `app.application`  | Device identity, network binding, and APDU parameters            |
| `BACnetClient`          | `app.client`       | High-level async methods for all BACnet services                 |
| `DefaultServerHandlers` | `app.server`       | Standard service handlers for a server device                    |
| `ObjectDatabase`        | `objects.base`     | Registry of local BACnet objects                                 |
| `BACnetObject`          | `objects.base`     | Base class for all object types                                  |
| `DeviceObject`          | `objects.device`   | Required device object (Clause 12.11)                            |
| `BACnetAddress`         | `network.address`  | Network + MAC address for device targeting                       |
| `ObjectIdentifier`      | `types.primitives` | Object type + instance number                                    |
| `ServiceRegistry`       | `services.base`    | Maps service choices to handler functions                        |

## Examples

The [`examples/`](examples/) directory contains runnable scripts covering common
usage patterns:

| File                   | Topics                                                                                         |
| ---------------------- | ---------------------------------------------------------------------------------------------- |
| `read_property.py`     | Single reads, array indexing, ReadPropertyMultiple, error handling                             |
| `write_property.py`    | Float/enum/string writes, priority, WritePropertyMultiple                                      |
| `discovery.py`         | Who-Is/I-Am, Who-Has/I-Have, range filters, local vs global broadcast                          |
| `configuration.py`     | DeviceConfig, DeviceObject, Analog/Binary/MultiState object setup                              |
| `client_operations.py` | COV, device management, time sync, file access, object management, ReadRange, private transfer |
| `server_operations.py` | Basic server, simulated sensor data, multiple devices                                          |

## Value Encoding

Write operations require application-tagged encoded bytes. Use the helpers in
`bac_py.encoding.primitives`:

```python
from bac_py.encoding.primitives import (
    encode_application_real,              # float
    encode_application_unsigned,          # unsigned int
    encode_application_signed,            # signed int
    encode_application_enumerated,        # IntEnum / int
    encode_application_character_string,  # str
    encode_application_boolean,           # bool
    encode_application_octet_string,      # bytes
    encode_application_null,              # null
    encode_application_object_id,         # (type, instance)
    encode_application_date,              # BACnetDate
    encode_application_time,              # BACnetTime
    encode_application_bit_string,        # BitString
)
```

## Testing

```bash
# Run the test suite
uv run pytest

# With coverage
uv run coverage run -m pytest
uv run coverage report

# Linting and formatting
uv run ruff check src tests
uv run ruff format src tests

# Type checking
uv run mypy
```

## Project Status

**Version 0.1.0** -- foundation release.

Implemented:

- BACnet/IP transport (Annex J)
- Full APDU encoding/decoding
- Client and server transaction state machines
- All property access services (Read, Write, ReadMultiple, WriteMultiple, ReadRange)
- Discovery services (Who-Is/I-Am, Who-Has/I-Have)
- COV subscription and notification
- Device management services
- File access services
- Object management services
- Private transfer services
- Segmentation support
- 14+ object types with property definitions

Planned:

- BACnet/MSTP transport
- Alarm and event services
- Trend log data retrieval helpers
- Network router support
- BBMD foreign device registration workflows

## Requirements

- Python >= 3.13
- No runtime dependencies (optional: `orjson` for JSON serialization)
