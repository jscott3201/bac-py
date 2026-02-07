# bac-py Architecture Overview

## 1. Introduction

bac-py is an asynchronous BACnet protocol library for Python 3.13+, implementing the ASHRAE Standard 135-2016 (BACnet). It provides both client and server capabilities for BACnet/IP networks, with an architecture designed for future extension to Ethernet and other transport media.

The library is built on Python's native `asyncio` framework, leveraging modern async patterns (structured concurrency via `TaskGroup`, typed protocols, and `asyncio.DatagramProtocol`) for high performance and correctness.

## 2. Protocol Architecture Mapping

BACnet uses a four-layer collapsed OSI architecture:

```
┌─────────────────────────────────────┐
│         Application Process         │  User code / BACnet objects
├─────────────────────────────────────┤
│         Application Layer           │  Services, APDU encoding, segmentation
├─────────────────────────────────────┤
│          Network Layer              │  NPDU, routing, addressing
├─────────────────────────────────────┤
│     Data Link / Physical Layer      │  BACnet/IP (BVLL over UDP), Ethernet
└─────────────────────────────────────┘
```

bac-py mirrors this with a corresponding Python module hierarchy:

```
bac_py/
├── __init__.py
├── types/                  # BACnet data types and enumerations
│   ├── __init__.py
│   ├── primitives.py       # Null, Bool, Unsigned, Signed, Real, Double, etc.
│   ├── constructed.py      # Sequences, choices, lists
│   ├── enums.py            # ObjectType, PropertyIdentifier, ErrorClass, etc.
│   └── object_id.py        # BACnetObjectIdentifier
│
├── encoding/               # ASN.1/BER-like tag-length-value encoding
│   ├── __init__.py
│   ├── tags.py             # Application & context-specific tag encode/decode
│   ├── primitives.py       # Encoding rules per data type (Clause 20.2)
│   └── apdu.py             # APDU fixed-part encoding (Clause 20.1)
│
├── network/                # Network layer (Clause 6)
│   ├── __init__.py
│   ├── npdu.py             # NPDU encode/decode, control octet parsing
│   └── address.py          # BACnet addresses (local, remote, broadcast)
│
├── transport/              # Data link layer implementations
│   ├── __init__.py
│   ├── base.py             # Abstract transport protocol
│   ├── bip.py              # BACnet/IP (Annex J) - UDP transport
│   ├── bvll.py             # BVLL message encode/decode
│   ├── bbmd.py             # BBMD broadcast management
│   └── foreign_device.py   # Foreign device registration
│
├── services/               # Application layer services
│   ├── __init__.py
│   ├── base.py             # Service request/response base classes
│   ├── who_is.py           # Who-Is / I-Am (Clause 16.10)
│   ├── who_has.py          # Who-Has / I-Have (Clause 16.9)
│   ├── read_property.py    # ReadProperty (Clause 15.5)
│   ├── read_property_multiple.py  # ReadPropertyMultiple (Clause 15.7)
│   ├── write_property.py   # WriteProperty (Clause 15.9)
│   ├── write_property_multiple.py # WritePropertyMultiple (Clause 15.10)
│   ├── read_range.py       # ReadRange (Clause 15.8)
│   ├── cov.py              # SubscribeCOV, COV notifications (Clause 13)
│   ├── event.py            # Event notifications (Clause 13)
│   ├── device_mgmt.py      # DCC, ReinitializeDevice, TimeSynchronization
│   ├── file_access.py      # AtomicReadFile, AtomicWriteFile (Clause 14)
│   ├── object_mgmt.py      # CreateObject, DeleteObject (Clause 15.3-15.4)
│   ├── list_element.py     # AddListElement, RemoveListElement (Clause 15.1-15.2)
│   ├── private_transfer.py # ConfirmedPrivateTransfer, UnconfirmedPrivateTransfer
│   └── errors.py           # BACnet-Error, Reject, Abort (Clause 18)
│
├── objects/                # BACnet object model (Clause 12)
│   ├── __init__.py
│   ├── base.py             # BACnetObject base class with property registry
│   ├── device.py           # Device object (Clause 12.11)
│   ├── analog.py           # AnalogInput, AnalogOutput, AnalogValue
│   ├── binary.py           # BinaryInput, BinaryOutput, BinaryValue
│   ├── multistate.py       # MultiStateInput, MultiStateOutput, MultiStateValue
│   ├── schedule.py         # Schedule, Calendar
│   ├── trendlog.py         # TrendLog, TrendLogMultiple
│   ├── notification.py     # NotificationClass, EventEnrollment
│   ├── file.py             # File object
│   ├── loop.py             # Loop (PID control)
│   ├── network_port.py     # NetworkPort object
│   └── value_types.py      # IntegerValue, PositiveIntegerValue, CharStringValue, etc.
│
├── app/                    # High-level application interface
│   ├── __init__.py
│   ├── client.py           # BACnet client application
│   ├── server.py           # BACnet server application
│   └── device.py           # Local device management
│
└── segmentation/           # Message segmentation (Clause 5.2)
    ├── __init__.py
    └── manager.py          # Segmentation state machine
```

## 3. Core Design Principles

### 3.1 Async-First

Every I/O operation is `async`. The transport layer uses `asyncio.DatagramProtocol` for UDP sockets. Service requests return `asyncio.Future` objects tracked by invoke-id. No threads are used for protocol processing.

### 3.2 Layered Separation

Each protocol layer has a clean interface:

- **Transport** emits/consumes raw BVLL-wrapped datagrams
- **Network** adds/strips NPDU headers, handles routing addresses
- **Application** manages APDU framing, invoke-id tracking, segmentation, and service dispatch

Layers communicate via typed callback protocols (Python `Protocol` classes), not inheritance.

### 3.3 Immutable Data Structures

BACnet PDUs and addresses are represented as frozen `dataclasses` or `NamedTuple` types. This eliminates mutation bugs in concurrent contexts and allows PDUs to be safely shared across tasks.

### 3.4 Zero-Copy Where Possible

Encoding/decoding operates on `memoryview` and `bytearray` buffers to avoid copies in the hot path. The tag parser reads directly from received datagram bytes.

### 3.5 Typed Throughout

All public APIs use type annotations. Enumerations use `IntEnum` subclasses corresponding to BACnet-defined values. Property values are typed with the appropriate Python representation.

## 4. Layered Data Flow

### 4.1 Client Sending a Request

```
User calls:  await client.read_property(device_addr, obj_id, prop_id)
                │
                ▼
        ┌─────────────────┐
        │ Application Layer│  Encodes service parameters, assigns invoke-id,
        │                  │  creates Confirmed-Request APDU, handles segmentation
        └────────┬────────┘
                 │ APDU bytes
                 ▼
        ┌─────────────────┐
        │  Network Layer   │  Wraps in NPDU with destination address,
        │                  │  sets control bits (data_expecting_reply, priority)
        └────────┬────────┘
                 │ NPDU bytes
                 ▼
        ┌─────────────────┐
        │  Transport Layer │  Wraps in BVLL (Original-Unicast-NPDU or
        │  (BACnet/IP)     │  Distribute-Broadcast-To-Network),
        │                  │  sends via UDP socket
        └─────────────────┘
```

### 4.2 Server Receiving a Request

```
        ┌─────────────────┐
        │  Transport Layer │  UDP datagram received,
        │  (BACnet/IP)     │  parses BVLL header, extracts NPDU
        └────────┬────────┘
                 │ NPDU bytes + source B/IP address
                 ▼
        ┌─────────────────┐
        │  Network Layer   │  Parses NPDU header, extracts source/dest addresses,
        │                  │  determines if message is for local device
        └────────┬────────┘
                 │ APDU bytes + BACnet address
                 ▼
        ┌─────────────────┐
        │ Application Layer│  Parses APDU type, dispatches to service handler,
        │                  │  service handler reads object properties,
        │                  │  builds response APDU, sends back down the stack
        └─────────────────┘
```

## 5. Key Component Interactions

### 5.1 Transaction State Machine (TSM)

The application layer maintains a Transaction State Machine per the spec (Clause 5.4):

- **Client TSM**: Tracks outstanding confirmed requests by invoke-id. Handles retries, timeouts, and segmented responses. Each active request holds a reference to an `asyncio.Future` that the caller awaits.
- **Server TSM**: Tracks incoming confirmed requests that require a response. Manages segmented request reassembly and response segmentation.

The TSM is implemented as a dict of `Transaction` objects keyed by `(remote_address, invoke_id)`.

### 5.2 Service Dispatch

Incoming APDUs are dispatched based on PDU type:

| APDU Type           | Dispatch Target                                  |
| ------------------- | ------------------------------------------------ |
| Confirmed-Request   | Registered service handler (server-side)         |
| Unconfirmed-Request | Registered service handler (broadcast/multicast) |
| SimpleACK           | Client TSM (completes Future)                    |
| ComplexACK          | Client TSM (completes Future with decoded data)  |
| SegmentACK          | Client/Server TSM (segmentation state machine)   |
| Error               | Client TSM (sets exception on Future)            |
| Reject              | Client TSM (sets exception on Future)            |
| Abort               | Client TSM (sets exception on Future)            |

### 5.3 Object Database

The server maintains an object database - a dictionary mapping `ObjectIdentifier` to `BACnetObject` instances. Each object type defines its required and optional properties. Property reads/writes are dispatched through the object's property accessors.

## 6. Transport Abstraction

```python
class TransportProtocol(Protocol):
    """Interface that all BACnet transports must implement."""

    async def send(self, data: bytes, address: BACnetAddress) -> None: ...
    async def broadcast(self, data: bytes) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    @property
    def local_address(self) -> BACnetAddress: ...
    @property
    def max_apdu_length(self) -> int: ...
```

The BACnet/IP transport implements this using `asyncio.DatagramProtocol` on UDP port 0xBAC0 (47808). Future Ethernet support would provide a separate implementation of the same protocol.

## 7. Configuration

The library is configured through a `DeviceConfig` dataclass:

```python
@dataclass(frozen=True)
class DeviceConfig:
    instance_number: int                    # Device instance number
    name: str                               # Device name
    vendor_id: int = 0                      # Vendor identifier
    max_apdu_length: int = 1476             # Max APDU length accepted
    segmentation_supported: Segmentation = Segmentation.BOTH
    apdu_timeout: int = 3000                # Milliseconds
    apdu_retries: int = 3                   # Number of retries
    database_revision: int = 0              # Object database revision
```

## 8. Error Model

BACnet defines three error response types, each mapped to a Python exception:

| BACnet PDU | Python Exception                       | Use Case              |
| ---------- | -------------------------------------- | --------------------- |
| Error-PDU  | `BACnetError(error_class, error_code)` | Service-level error   |
| Reject-PDU | `BACnetReject(reason)`                 | Protocol syntax error |
| Abort-PDU  | `BACnetAbort(reason)`                  | Transaction abort     |

All are subclasses of `BACnetException`, which is itself a subclass of `Exception`.

## 9. Thread Safety and Concurrency

- All protocol processing runs in a single asyncio event loop (no thread-safety concerns within the protocol stack).
- The public API (`BACnetClient`, `BACnetServer`) is designed to be called from coroutines within the same event loop.
- Background tasks (COV subscriptions, foreign device re-registration, BBMD timers) are managed via `asyncio.TaskGroup` for structured concurrency and clean shutdown.
- External integrations that need to call from threads can use `asyncio.run_coroutine_threadsafe()`.

## 10. Dependency Strategy

The library targets zero mandatory external dependencies beyond the Python 3.13+ standard library. `asyncio`, `struct`, `enum`, `dataclasses`, and `typing` provide everything needed for protocol implementation. Optional dependencies may include:

- `cryptography` - if/when BACnet network security (Clause 24) is implemented
- `pytest` + `pytest-asyncio` - for testing

## 11. Logging and Observability

### 11.1 Structured Logging

bac-py uses Python's standard `logging` module with a per-module logger hierarchy rooted at `bac_py`:

```
bac_py                     # Root logger
bac_py.transport           # BVLL/UDP level events
bac_py.network             # NPDU routing events
bac_py.app                 # APDU dispatch, TSM events
bac_py.services            # Service-level request/response
bac_py.objects             # Object property changes
```

Log levels follow standard semantics:

| Level | Usage |
|-------|-------|
| DEBUG | Full PDU hex dumps, tag-by-tag decoding, timer starts/cancels |
| INFO | Service requests/responses, device discovery, COV notifications |
| WARNING | Timeouts, retransmissions, unknown service choices, malformed packets silently dropped |
| ERROR | Transaction failures, unhandled exceptions in handlers |

No log messages are emitted at WARNING or above during normal operation. Users configure log levels and handlers through standard `logging.getLogger('bac_py')`.

### 11.2 Metrics Hooks

The application exposes optional callback hooks for metrics instrumentation without coupling to a specific framework:

```python
@dataclass
class MetricsHooks:
    on_request_sent: Callable[[str, BACnetAddress], None] | None = None
    on_response_received: Callable[[str, float], None] | None = None  # service, latency
    on_timeout: Callable[[str, BACnetAddress], None] | None = None
    on_error: Callable[[str, ErrorClass, ErrorCode], None] | None = None
```

## 12. Testing Strategy

### 12.1 Approach

Tests are organized to mirror the source tree. Each module has a corresponding test module. The test suite is designed around three categories:

- **Unit tests**: Isolated encode/decode round-trips, object property validation, TSM state transitions. Use `MockTransport` (no UDP). Run in milliseconds.
- **Integration tests**: Two `BACnetApplication` instances communicating via localhost UDP. Verifies full-stack behavior: client discovers server, reads/writes properties, receives COV notifications.
- **Conformance tests**: Byte-exact comparisons against ASHRAE 135-2016 Annex F examples. Ensures wire compatibility with other BACnet implementations.

### 12.2 Test Infrastructure

```python
# conftest.py — shared fixtures
@pytest.fixture
def mock_transport() -> MockTransport:
    """In-memory transport for unit testing."""
    return MockTransport()

@pytest.fixture
async def server_app() -> AsyncGenerator[BACnetApplication, None]:
    """Running BACnet server on an ephemeral port."""
    config = DeviceConfig(instance_number=1234, name="Test Server", port=0)
    app = BACnetApplication(config)
    async with app:
        yield app

@pytest.fixture
async def client_app() -> AsyncGenerator[BACnetApplication, None]:
    """Running BACnet client on an ephemeral port."""
    config = DeviceConfig(instance_number=5678, name="Test Client", port=0)
    app = BACnetApplication(config)
    async with app:
        yield app
```
