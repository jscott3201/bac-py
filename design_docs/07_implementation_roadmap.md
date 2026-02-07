# Implementation Roadmap

## 1. Overview

This document defines the phased implementation plan for bac-py. Each phase produces a usable, testable slice of functionality. Phases build on each other bottom-up through the protocol stack.

## 2. Phase 0: Project Scaffolding

**Goal**: Set up the project structure, tooling, and CI pipeline before writing any protocol code.

### 2.1 Deliverables

| Item                | What                                                                                                  |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| `pyproject.toml`    | Project metadata, Python 3.13+ requirement, dev dependencies (pytest, pytest-asyncio, mypy, ruff)     |
| `src/bac_py/`       | Package directory with `__init__.py` and empty subpackage stubs for types/, encoding/, network/, etc. |
| `tests/`            | Test directory mirroring source tree with `conftest.py`                                               |
| `.github/workflows` | CI pipeline: lint (ruff), type check (mypy), test (pytest) on Python 3.13                             |
| `ruff.toml`         | Linter/formatter configuration                                                                        |

### 2.2 Testing

- Verify `uv run pytest` runs successfully with zero tests
- Verify `uv run mypy src/` passes with no errors
- Verify `uv run ruff check src/` passes

---

## 3. Phase 1: Foundation — Encoding, Types, and Transport

**Goal**: Establish the wire-format codec and UDP transport. After this phase, we can send and receive raw BACnet/IP datagrams.

### 3.1 Deliverables

| Module                   | File             | What                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types/enums.py`         | Enumerations     | `ObjectType`, `PropertyIdentifier`, `ErrorClass`, `ErrorCode`, `Segmentation`, `AbortReason`, `RejectReason`, confirmed/unconfirmed service choices                                                                                                                                                                                                                                                                                                |
| `types/primitives.py`    | Data types       | `ObjectIdentifier`, `BACnetDate`, `BACnetTime`, `BitString`                                                                                                                                                                                                                                                                                                                                                                                        |
| `encoding/tags.py`       | Tag codec        | `encode_tag`, `decode_tag`, `encode_opening_tag`, `encode_closing_tag`, `Tag`, `TagClass`                                                                                                                                                                                                                                                                                                                                                          |
| `encoding/primitives.py` | Primitive codecs | `encode_unsigned`, `decode_unsigned`, `encode_signed`, `decode_signed`, `encode_real`, `decode_real`, `encode_double`, `decode_double`, `encode_character_string`, `decode_character_string`, `encode_object_identifier`, `decode_object_identifier`, `encode_date`, `decode_date`, `encode_time`, `decode_time`, `encode_enumerated`, `decode_enumerated`, `encode_bit_string`, `decode_bit_string`, `encode_octet_string`, `decode_octet_string` |
| `encoding/apdu.py`       | APDU codec       | Encode/decode all 8 APDU PDU types. PDU dataclasses.                                                                                                                                                                                                                                                                                                                                                                                               |
| `network/address.py`     | Addressing       | `BACnetAddress`, `BIPAddress`, broadcast constants                                                                                                                                                                                                                                                                                                                                                                                                 |
| `network/npdu.py`        | NPDU codec       | `encode_npdu`, `decode_npdu`, `NPDU` dataclass                                                                                                                                                                                                                                                                                                                                                                                                     |
| `transport/bvll.py`      | BVLL codec       | `encode_bvll`, `decode_bvll`, `BvllMessage`, `BvlcFunction`                                                                                                                                                                                                                                                                                                                                                                                        |
| `transport/bip.py`       | UDP transport    | `BIPTransport` with `asyncio.DatagramProtocol`, send/receive                                                                                                                                                                                                                                                                                                                                                                                       |

### 3.2 Testing

- **Unit tests for every encoder/decoder**: Round-trip property (encode then decode equals original) for all primitive types
- **Tag edge cases**: Extended tag numbers (>14), extended lengths (5-253, 254-65535, >65535), opening/closing tags
- **NPDU round-trip**: With and without source/destination addresses, network messages, various priorities
- **BVLL round-trip**: All function codes, Forwarded-NPDU with originating address
- **APDU round-trip**: All 8 PDU types, segmented and non-segmented variants
- **Integration test**: Send/receive a raw UDP datagram on localhost, verify BVLL+NPDU framing

### 3.3 Spec References

- Clause 6 (Network Layer), Clause 20 (Encoding), Annex J (BACnet/IP)

---

## 4. Phase 2: Core Services — ReadProperty, WriteProperty, Who-Is/I-Am

**Goal**: Implement the minimum viable client and server. A client can discover devices and read/write single properties. A server can respond to Who-Is and ReadProperty.

### 4.1 Deliverables

| Module                       | File                      | What                                                                             |
| ---------------------------- | ------------------------- | -------------------------------------------------------------------------------- |
| `services/base.py`           | Service base              | Service request/response base patterns                                           |
| `services/who_is.py`         | Who-Is/I-Am               | `WhoIsRequest`, `IAmRequest`, encode/decode                                      |
| `services/read_property.py`  | ReadProperty              | `ReadPropertyRequest`, `ReadPropertyACK`, encode/decode                          |
| `services/write_property.py` | WriteProperty             | `WritePropertyRequest`, encode/decode                                            |
| `services/errors.py`         | Error types               | `BACnetError`, `BACnetReject`, `BACnetAbort`, `BACnetTimeout`, `BACnetException` |
| `network/layer.py`           | Network layer             | `NetworkLayer` manager wiring transport to application                           |
| `app/application.py`         | Application layer         | APDU dispatch, service registry, TSM orchestration                               |
| `app/tsm.py`                 | Transaction state machine | `ClientTSM` with invoke-id tracking, timeouts, retries                           |
| `app/client.py`              | Client API                | `BACnetClient.read_property()`, `.write_property()`, `.who_is()`                 |
| `objects/base.py`            | Object base               | `BACnetObject`, `PropertyDefinition`, `ObjectDatabase`                           |
| `objects/device.py`          | Device object             | `DeviceObject` with required properties                                          |
| `app/server.py`              | Server handlers           | Default handlers for Who-Is, ReadProperty                                        |

### 4.2 Testing

- **Service codec tests**: Encode/decode for each service request and response, matching spec examples from Annex F
- **TSM tests**: Invoke-id allocation, timeout/retry behavior, Future resolution on ACK, exception on Error/Reject/Abort
- **Mock transport tests**: Inject raw bytes into the stack, verify correct dispatch and response
- **Integration test**: Two `BACnetApplication` instances on localhost. Client sends Who-Is, receives I-Am. Client reads a property from the server's device object.
- **Object database tests**: Add/remove objects, read/write properties, unknown object/property errors

### 4.3 Spec References

- Clause 5.4 (TSM), Clause 12.11 (Device Object), Clause 15.5 (ReadProperty), Clause 15.9 (WriteProperty), Clause 16.10 (Who-Is/I-Am)

---

## 5. Phase 3: Object Model — Analog, Binary, Multi-State

**Goal**: Implement the core I/O object types. A server can host AnalogInput, AnalogOutput, BinaryInput, BinaryOutput, Multi-State objects with proper property schemas and commandable behavior.

### 5.1 Deliverables

| Module                  | File                 | What                                                                       |
| ----------------------- | -------------------- | -------------------------------------------------------------------------- |
| `objects/analog.py`     | Analog types         | `AnalogInputObject`, `AnalogOutputObject`, `AnalogValueObject`             |
| `objects/binary.py`     | Binary types         | `BinaryInputObject`, `BinaryOutputObject`, `BinaryValueObject`             |
| `objects/multistate.py` | Multi-State types    | `MultiStateInputObject`, `MultiStateOutputObject`, `MultiStateValueObject` |
| `objects/base.py`       | Commandable support  | Priority array, relinquish default, command prioritization                 |
| `types/constructed.py`  | Constructed encoding | Sequences, property value polymorphic encoding/decoding                    |

### 5.2 Testing

- **Property schema tests**: Verify required properties present, optional properties work, unknown property returns error
- **Command prioritization**: Write at various priorities, verify Present_Value follows highest-priority non-null value. Relinquish and verify fallback.
- **Status flags**: Out-of-service, fault, alarm, overridden states
- **Integration**: Server with multiple object types, client reads all properties via ReadPropertyMultiple

### 5.3 Spec References

- Clause 12 (Object Types), Clause 19.2 (Command Prioritization)

---

## 6. Phase 4: Bulk Services — ReadPropertyMultiple, WritePropertyMultiple, ReadRange

**Goal**: Implement efficient bulk operations. These are critical for real-world performance.

### 6.1 Deliverables

| Module                                | File                | What                                                                                             |
| ------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------ |
| `services/read_property_multiple.py`  | RPM                 | `ReadPropertyMultipleRequest`, `ReadPropertyMultipleACK`, encode/decode with nested access specs |
| `services/write_property_multiple.py` | WPM                 | `WritePropertyMultipleRequest`, encode/decode with per-property error reporting                  |
| `services/read_range.py`              | ReadRange           | `ReadRangeRequest`, `ReadRangeACK`, encode/decode for array/list slicing                         |
| `encoding/constructed.py`             | Constructed helpers | `ReadAccessSpecification`, `ReadAccessResult`, `WriteAccessSpecification`                        |
| `app/client.py`                       | Client extensions   | `BACnetClient.read_property_multiple()`, `.write_property_multiple()`, `.read_range()`           |
| `app/server.py`                       | Server handlers     | RPM, WPM, and ReadRange handlers with batch processing                                           |

### 6.2 Testing

- **RPM round-trip**: Request multiple properties from multiple objects, verify all values returned
- **RPM error handling**: Mix of valid and unknown properties — verify per-property errors in results
- **WPM round-trip**: Write multiple properties, verify all written
- **WPM partial failure**: Some writes succeed, some fail — verify correct error reporting
- **Performance benchmark**: Compare N individual ReadProperty calls vs. one RPM call

### 6.3 Spec References

- Clause 15.7 (ReadPropertyMultiple), Clause 15.8 (ReadRange), Clause 15.10 (WritePropertyMultiple)

---

## 7. Phase 5: Segmentation

**Goal**: Handle APDUs larger than the max APDU size. Required for ReadPropertyMultiple responses with many properties and for devices with small APDU buffers.

### 7.1 Deliverables

| Module                    | File                | What                                                          |
| ------------------------- | ------------------- | ------------------------------------------------------------- |
| `segmentation/manager.py` | Segmentation        | Segment-and-send, receive-and-reassemble, SegmentACK handling |
| `app/tsm.py`              | TSM updates         | Client and server TSM states for segmented transactions       |
| `app/application.py`      | Application updates | Wire segmentation into APDU send/receive path                 |

### 7.2 Testing

- **Client reassembly**: Server sends segmented ComplexACK, client reassembles correctly
- **Server reassembly**: Client sends segmented ConfirmedRequest, server reassembles
- **Window management**: Verify proposed window size negotiation and SegmentACK flow
- **Timeout recovery**: Segment timeout, retry, abort
- **Exceeds max segments**: Verify abort when segment count exceeds limit

### 7.3 Spec References

- Clause 5.2 (Segmentation), Clause 5.4 (TSM states for segmentation)

---

## 8. Phase 6: COV and Events

**Goal**: Implement Change of Value subscriptions and event notifications. This enables real-time monitoring.

### 8.1 Deliverables

| Module              | File              | What                                                                       |
| ------------------- | ----------------- | -------------------------------------------------------------------------- |
| `services/cov.py`   | COV services      | SubscribeCOV, ConfirmedCOVNotification, UnconfirmedCOVNotification         |
| `objects/base.py`   | COV mixin         | COV subscription tracking, increment checking, notification generation     |
| `services/event.py` | Event services    | ConfirmedEventNotification, UnconfirmedEventNotification, AcknowledgeAlarm |
| `app/client.py`     | Client extensions | `.subscribe_cov()`, COV callback registration                              |
| `app/server.py`     | Server extensions | COV subscription management, notification sending                          |

### 8.2 Testing

- **Subscribe and receive**: Client subscribes to COV, server value changes, client receives notification
- **COV increment**: Analog value changes within increment = no notification. Exceeds increment = notification.
- **Subscription lifetime**: Subscription expires, no more notifications
- **Confirmed vs. unconfirmed**: Test both notification modes
- **Multiple subscribers**: Multiple clients subscribe to the same object

### 8.3 Spec References

- Clause 13 (Alarm and Event Services), Clause 13.1 (COV)

---

## 9. Phase 7: Device Management and File Access

**Goal**: Implement remaining device management services and file transfer.

### 9.1 Deliverables

| Module                         | File              | What                                                                                        |
| ------------------------------ | ----------------- | ------------------------------------------------------------------------------------------- |
| `services/device_mgmt.py`      | Device management | DeviceCommunicationControl, ReinitializeDevice, TimeSynchronization, UTCTimeSynchronization |
| `services/file_access.py`      | File access       | AtomicReadFile, AtomicWriteFile (stream and record modes)                                   |
| `services/object_mgmt.py`      | Object management | CreateObject, DeleteObject                                                                  |
| `services/list_element.py`     | List operations   | AddListElement, RemoveListElement                                                           |
| `services/who_has.py`          | Who-Has/I-Have    | WhoHasRequest, IHaveRequest                                                                 |
| `services/private_transfer.py` | Private transfer  | ConfirmedPrivateTransfer, UnconfirmedPrivateTransfer                                        |
| `objects/file.py`              | File object       | FileObject with stream/record access                                                        |

### 9.2 Testing

- **DCC**: Enable/disable communication, verify rejected requests during disable
- **Reinitialize**: Warm start, cold start
- **Time Sync**: Send and receive time synchronization
- **File transfer**: Read and write file objects in both stream and record modes
- **Object creation/deletion**: Dynamic object management
- **Private transfer**: Vendor-specific service round-trip

### 9.3 Spec References

- Clause 14 (File Access), Clause 15.1-15.4 (List/Object Management), Clause 16 (Device Management)

---

## 10. Phase 8: BBMD and Foreign Device

**Goal**: Full BBMD and foreign device support for multi-subnet deployments.

### 10.1 Deliverables

| Module                        | File           | What                                                                      |
| ----------------------------- | -------------- | ------------------------------------------------------------------------- |
| `transport/bbmd.py`           | BBMD           | BBMDManager: BDT management, broadcast forwarding, FDT management         |
| `transport/foreign_device.py` | Foreign device | ForeignDeviceManager: Registration, re-registration, distribute-broadcast |

### 10.2 Testing

- **Foreign device registration**: Register, re-register, timeout
- **Broadcast forwarding**: BBMD forwards broadcasts to all BDT peers and foreign devices
- **Distribute-broadcast**: Foreign device sends broadcast via BBMD
- **Multi-BBMD**: Two BBMDs forward broadcasts between subnets

### 10.3 Spec References

- Annex J.4-J.7 (BBMD, Foreign Device Registration)

---

## 11. Phase 9: Extended Object Types

**Goal**: Implement Tier 2 and Tier 3 object types.

### 11.1 Deliverables

| Priority | Objects                                                                                                                                                               |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tier 2   | Schedule, Calendar, TrendLog, NotificationClass, EventEnrollment, Loop, Accumulator, Program                                                                          |
| Tier 3   | IntegerValue, PositiveIntegerValue, CharacterStringValue, LargeAnalogValue, DateTimeValue, BitStringValue, OctetStringValue, Channel, NetworkPort, Timer, LoadControl |

### 11.2 Testing

- Property schema validation per spec for each object type
- Schedule/Calendar: Effective period, weekly schedule, exception schedule
- TrendLog: Buffer management, log status
- Loop: PID algorithm basics

---

## 12. Testing Strategy

### 12.1 Test Framework

- **pytest** + **pytest-asyncio** for async test support
- Tests organized to mirror the source tree: `tests/encoding/`, `tests/transport/`, `tests/services/`, etc.

### 12.2 Test Categories

| Category    | Purpose                                                       | Run Time         |
| ----------- | ------------------------------------------------------------- | ---------------- |
| Unit        | Encode/decode round-trips, individual functions               | < 1 second each  |
| Integration | Two in-process applications communicating via localhost UDP   | < 5 seconds each |
| Conformance | Verify encoded bytes match spec Annex F examples exactly      | < 1 second each  |
| Interop     | Test against bacnet-stack C applications or BACnet test tools | Manual/CI        |

### 12.3 Conformance Test Vectors

The spec (Annex F) provides example encodings. We implement these as exact byte-comparison tests:

```python
def test_read_property_request_encoding():
    """Annex F.3.1 - ReadProperty example."""
    request = ReadPropertyRequest(
        object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        property_identifier=PropertyIdentifier.PRESENT_VALUE,
    )
    encoded = request.encode()
    # Expected bytes from Annex F
    assert encoded == bytes([
        0x0C, 0x00, 0x00, 0x00, 0x01,  # [0] object-identifier: AI:1
        0x19, 0x55,                      # [1] property-identifier: present-value
    ])
```

### 12.4 Mock Transport for Testing

```python
class MockTransport:
    """In-memory transport for unit testing without UDP."""

    def __init__(self):
        self.sent: list[tuple[bytes, BIPAddress]] = []
        self.broadcasts: list[bytes] = []
        self._receive_callback = None

    async def send_unicast(self, data: bytes, dest: BIPAddress) -> None:
        self.sent.append((data, dest))

    async def send_broadcast(self, data: bytes) -> None:
        self.broadcasts.append(data)

    def inject(self, data: bytes, source: BIPAddress) -> None:
        """Simulate receiving a datagram."""
        if self._receive_callback:
            self._receive_callback(data, source)
```

## 13. Project Structure Summary

```
bac-py/
├── pyproject.toml
├── design_docs/              # This directory
├── src/
│   └── bac_py/
│       ├── __init__.py
│       ├── types/
│       │   ├── __init__.py
│       │   ├── enums.py
│       │   ├── primitives.py
│       │   └── constructed.py
│       ├── encoding/
│       │   ├── __init__.py
│       │   ├── tags.py
│       │   ├── primitives.py
│       │   └── apdu.py
│       ├── network/
│       │   ├── __init__.py
│       │   ├── address.py
│       │   ├── npdu.py
│       │   └── layer.py
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── bvll.py
│       │   ├── bip.py
│       │   ├── bbmd.py
│       │   └── foreign_device.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── who_is.py
│       │   ├── who_has.py
│       │   ├── read_property.py
│       │   ├── read_property_multiple.py
│       │   ├── write_property.py
│       │   ├── write_property_multiple.py
│       │   ├── read_range.py
│       │   ├── cov.py
│       │   ├── event.py
│       │   ├── device_mgmt.py
│       │   ├── file_access.py
│       │   ├── object_mgmt.py
│       │   ├── list_element.py
│       │   ├── private_transfer.py
│       │   └── errors.py
│       ├── objects/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── device.py
│       │   ├── analog.py
│       │   ├── binary.py
│       │   ├── multistate.py
│       │   ├── schedule.py
│       │   ├── trendlog.py
│       │   ├── notification.py
│       │   ├── file.py
│       │   ├── loop.py
│       │   ├── network_port.py
│       │   └── value_types.py
│       ├── app/
│       │   ├── __init__.py
│       │   ├── application.py
│       │   ├── tsm.py
│       │   ├── client.py
│       │   ├── server.py
│       │   └── device.py
│       └── segmentation/
│           ├── __init__.py
│           └── manager.py
└── tests/
    ├── conftest.py            # Shared fixtures, MockTransport
    ├── encoding/
    │   ├── test_tags.py
    │   ├── test_primitives.py
    │   └── test_apdu.py
    ├── network/
    │   ├── test_address.py
    │   └── test_npdu.py
    ├── transport/
    │   ├── test_bvll.py
    │   └── test_bip.py
    ├── services/
    │   ├── test_who_is.py
    │   ├── test_read_property.py
    │   ├── test_write_property.py
    │   └── test_cov.py
    ├── objects/
    │   ├── test_base.py
    │   ├── test_analog.py
    │   ├── test_binary.py
    │   └── test_device.py
    ├── app/
    │   ├── test_tsm.py
    │   ├── test_client.py
    │   └── test_server.py
    └── integration/
        ├── test_discovery.py
        ├── test_read_write.py
        └── test_cov.py
```

## 14. Dependency Decisions

| Dependency          | Type     | Phase  | Purpose                                    |
| ------------------- | -------- | ------ | ------------------------------------------ |
| Python 3.13+ stdlib | Required | 0      | asyncio, struct, enum, dataclasses, typing |
| pytest              | Dev      | 0      | Test framework                             |
| pytest-asyncio      | Dev      | 0      | Async test support                         |
| mypy                | Dev      | 0      | Static type checking                       |
| ruff                | Dev      | 0      | Linting and formatting                     |
| coverage            | Dev      | 0      | Test coverage reporting                    |
| cryptography        | Optional | Future | BACnet Secure Connect (Clause 24)          |
