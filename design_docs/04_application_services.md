# Application Services Design

## 1. Overview

BACnet application services (Clauses 13-17) define the operations that devices perform on each other's objects and properties. This document specifies how bac-py implements these services for both client (initiator) and server (responder) roles.

Services fall into two categories:

- **Confirmed services**: Request/response pattern. The client sends a request and awaits an ACK (SimpleACK or ComplexACK) or error. Uses client TSM for tracking.
- **Unconfirmed services**: Fire-and-forget. No acknowledgment expected. Typically broadcast.

## 2. Service Catalog

### 2.1 Object Access Services (Clause 15) - Priority 1

| Service               | Type        | Choice | Client                            | Server                               | Description             |
| --------------------- | ----------- | ------ | --------------------------------- | ------------------------------------ | ----------------------- |
| ReadProperty          | Confirmed   | 12     | Send request, decode ComplexACK   | Lookup object/property, return value | Core data read          |
| ReadPropertyMultiple  | Confirmed   | 14     | Send request, decode multi-result | Batch property lookup                | Efficient bulk read     |
| WriteProperty         | Confirmed   | 15     | Encode value + priority           | Validate and write                   | Core data write         |
| WritePropertyMultiple | Confirmed   | 16     | Encode multiple writes            | Batch write with error per property  | Efficient bulk write    |
| ReadRange             | Confirmed   | 26     | Specify range parameters          | Return array/list slice              | Trend log / list access |
| AddListElement        | Confirmed   | 8      | Encode elements to add            | Modify list property                 | List manipulation       |
| RemoveListElement     | Confirmed   | 9      | Encode elements to remove         | Modify list property                 | List manipulation       |
| CreateObject          | Confirmed   | 10     | Specify type + initial values     | Instantiate new object               | Dynamic object creation |
| DeleteObject          | Confirmed   | 11     | Specify object identifier         | Remove object from database          | Dynamic object deletion |
| WriteGroup            | Unconfirmed | 10     | Encode channel writes             | Apply to channel objects             | High-speed group writes |

### 2.2 Device Discovery Services (Clause 16.9-16.10) - Priority 1

| Service | Type        | Choice | Client                        | Server                        | Description         |
| ------- | ----------- | ------ | ----------------------------- | ----------------------------- | ------------------- |
| Who-Is  | Unconfirmed | 8      | Broadcast with optional range | Respond with I-Am if in range | Device discovery    |
| I-Am    | Unconfirmed | 0      | Emit on startup               | Process for device table      | Device announcement |
| Who-Has | Unconfirmed | 7      | Search by name or object ID   | Respond with I-Have if found  | Object discovery    |
| I-Have  | Unconfirmed | 1      | N/A                           | Process for object location   | Object announcement |

### 2.3 Alarm and Event Services (Clause 13) - Priority 2

| Service                            | Type        | Choice | Description                                   |
| ---------------------------------- | ----------- | ------ | --------------------------------------------- |
| SubscribeCOV                       | Confirmed   | 5      | Subscribe to change-of-value notifications    |
| SubscribeCOVProperty               | Confirmed   | 28     | Subscribe to COV on specific property         |
| ConfirmedCOVNotification           | Confirmed   | 1      | Send COV notification (confirmed)             |
| UnconfirmedCOVNotification         | Unconfirmed | 2      | Send COV notification (unconfirmed)           |
| ConfirmedEventNotification         | Confirmed   | 2      | Send event notification (confirmed)           |
| UnconfirmedEventNotification       | Unconfirmed | 3      | Send event notification (unconfirmed)         |
| AcknowledgeAlarm                   | Confirmed   | 0      | Acknowledge an alarm condition                |
| GetAlarmSummary                    | Confirmed   | 3      | List active alarms                            |
| GetEventInformation                | Confirmed   | 29     | List event states                             |
| GetEnrollmentSummary               | Confirmed   | 4      | List event enrollments                        |
| LifeSafetyOperation                | Confirmed   | 27     | Life safety commands                          |
| SubscribeCOVPropertyMultiple       | Confirmed   | 30     | Multi-property COV subscription               |
| ConfirmedCOVNotificationMultiple   | Confirmed   | 31     | Multi-property COV notification               |
| UnconfirmedCOVNotificationMultiple | Unconfirmed | 11     | Multi-property COV notification (unconfirmed) |

### 2.4 Remote Device Management Services (Clause 16) - Priority 2

| Service                    | Type        | Choice | Description                           |
| -------------------------- | ----------- | ------ | ------------------------------------- |
| DeviceCommunicationControl | Confirmed   | 17     | Enable/disable device communication   |
| ReinitializeDevice         | Confirmed   | 20     | Restart or reset device               |
| TimeSynchronization        | Unconfirmed | 6      | Sync device time                      |
| UTCTimeSynchronization     | Unconfirmed | 9      | Sync device UTC time                  |
| ConfirmedPrivateTransfer   | Confirmed   | 18     | Vendor-specific service               |
| UnconfirmedPrivateTransfer | Unconfirmed | 4      | Vendor-specific service (unconfirmed) |
| ConfirmedTextMessage       | Confirmed   | 19     | Send text message to device           |
| UnconfirmedTextMessage     | Unconfirmed | 5      | Send text message (unconfirmed)       |

### 2.5 File Access Services (Clause 14) - Priority 2

| Service         | Type      | Choice | Description                            |
| --------------- | --------- | ------ | -------------------------------------- |
| AtomicReadFile  | Confirmed | 6      | Read file contents (stream or record)  |
| AtomicWriteFile | Confirmed | 7      | Write file contents (stream or record) |

## 3. Service Architecture

### 3.1 Service Encoding/Decoding Pattern

Each service module follows a consistent structure (mirroring the bacnet-stack's `rp.c/h`, `wp.c/h`, etc. pattern):

```python
# services/read_property.py

@dataclass(frozen=True, slots=True)
class ReadPropertyRequest:
    """ReadProperty-Request service parameters (Clause 15.5.1)."""
    object_identifier: ObjectIdentifier       # [0] BACnetObjectIdentifier
    property_identifier: PropertyIdentifier   # [1] BACnetPropertyIdentifier
    property_array_index: int | None = None   # [2] Unsigned OPTIONAL

    def encode(self) -> bytes:
        """Encode service request parameters."""
        buf = bytearray()
        # [0] object-identifier - context tag 0
        buf.extend(encode_context_tagged(0,
            encode_object_identifier(
                self.object_identifier.object_type,
                self.object_identifier.instance_number)))
        # [1] property-identifier - context tag 1
        buf.extend(encode_context_tagged(1,
            encode_unsigned(self.property_identifier)))
        # [2] property-array-index - context tag 2, optional
        if self.property_array_index is not None:
            buf.extend(encode_context_tagged(2,
                encode_unsigned(self.property_array_index)))
        return bytes(buf)

    @classmethod
    def decode(cls, data: memoryview) -> ReadPropertyRequest:
        """Decode service request parameters from APDU."""
        ...


@dataclass(frozen=True, slots=True)
class ReadPropertyACK:
    """ReadProperty-ACK service parameters (Clause 15.5.1)."""
    object_identifier: ObjectIdentifier       # [0]
    property_identifier: PropertyIdentifier   # [1]
    property_array_index: int | None = None   # [2] OPTIONAL
    property_value: Any = None                # [3] ABSTRACT-SYNTAX.&TYPE

    def encode(self) -> bytes: ...

    @classmethod
    def decode(cls, data: memoryview) -> ReadPropertyACK: ...
```

### 3.2 Service Handler Registration

The server's application layer maintains a registry of service handlers:

```python
# Type aliases for service handlers
type ConfirmedHandler = Callable[
    [int, bytes, BACnetAddress],       # service_choice, request_data, source
    Awaitable[bytes | None]            # response_data (None = SimpleACK)
]

type UnconfirmedHandler = Callable[
    [int, bytes, BACnetAddress],       # service_choice, request_data, source
    Awaitable[None]
]


class ServiceRegistry:
    """Registry for service request handlers."""

    def __init__(self):
        self._confirmed: dict[int, ConfirmedHandler] = {}
        self._unconfirmed: dict[int, UnconfirmedHandler] = {}

    def register_confirmed(self, service_choice: int,
                          handler: ConfirmedHandler) -> None:
        self._confirmed[service_choice] = handler

    def register_unconfirmed(self, service_choice: int,
                            handler: UnconfirmedHandler) -> None:
        self._unconfirmed[service_choice] = handler

    async def dispatch_confirmed(self, service_choice: int,
                                request_data: bytes,
                                source: BACnetAddress) -> bytes | None:
        handler = self._confirmed.get(service_choice)
        if handler is None:
            raise BACnetReject(RejectReason.UNRECOGNIZED_SERVICE)
        return await handler(service_choice, request_data, source)

    async def dispatch_unconfirmed(self, service_choice: int,
                                  request_data: bytes,
                                  source: BACnetAddress) -> None:
        handler = self._unconfirmed.get(service_choice)
        if handler is not None:
            await handler(service_choice, request_data, source)
```

### 3.3 Default Server Handlers

The server application pre-registers handlers for standard services:

```python
class DefaultServiceHandlers:
    """Standard BACnet service handlers for a server device."""

    def __init__(self, object_db: ObjectDatabase, device: DeviceObject):
        self._db = object_db
        self._device = device

    async def handle_read_property(self, service_choice: int,
                                   data: bytes,
                                   source: BACnetAddress) -> bytes:
        """Handle ReadProperty-Request, return ComplexACK data."""
        request = ReadPropertyRequest.decode(memoryview(data))
        obj = self._db.get(request.object_identifier)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        value = obj.read_property(request.property_identifier,
                                  request.property_array_index)
        if value is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        ack = ReadPropertyACK(
            object_identifier=request.object_identifier,
            property_identifier=request.property_identifier,
            property_array_index=request.property_array_index,
            property_value=value,
        )
        return ack.encode()

    async def handle_write_property(self, service_choice: int,
                                    data: bytes,
                                    source: BACnetAddress) -> bytes | None:
        """Handle WriteProperty-Request, return SimpleACK (None)."""
        request = WritePropertyRequest.decode(memoryview(data))
        obj = self._db.get(request.object_identifier)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        obj.write_property(
            request.property_identifier,
            request.property_value,
            request.priority,
            request.property_array_index,
        )
        return None  # SimpleACK

    async def handle_who_is(self, service_choice: int,
                           data: bytes,
                           source: BACnetAddress) -> None:
        """Handle Who-Is broadcast, respond with I-Am if in range."""
        request = WhoIsRequest.decode(memoryview(data))
        instance = self._device.object_identifier.instance_number

        if request.low_limit is not None and request.high_limit is not None:
            if not (request.low_limit <= instance <= request.high_limit):
                return  # Not in range, don't respond

        # Send I-Am broadcast
        iam = IAmRequest(
            object_identifier=self._device.object_identifier,
            max_apdu_length=self._device.max_apdu_length_accepted,
            segmentation_supported=self._device.segmentation_supported,
            vendor_id=self._device.vendor_identifier,
        )
        await self._send_i_am(iam)
```

## 4. Transaction State Machine (Clause 5.4)

### 4.1 Client TSM

```python
@dataclass
class ClientTransaction:
    """Tracks an outstanding confirmed service request."""
    invoke_id: int
    destination: BACnetAddress
    service_choice: int
    request_data: bytes
    future: asyncio.Future[bytes]
    retry_count: int = 0
    timeout_handle: asyncio.TimerHandle | None = None
    # Segmentation state
    segments: dict[int, bytes] | None = None
    expected_segments: int | None = None


class ClientTransactionState(IntEnum):
    """Client TSM states per Clause 5.4.4."""
    IDLE = 0
    SEGMENTED_REQUEST = 1
    AWAIT_CONFIRMATION = 2
    SEGMENTED_CONF = 3


class ClientTSM:
    """Client Transaction State Machine (Clause 5.4.4).

    Manages outstanding confirmed requests, correlating responses
    by (source_address, invoke_id). Per Clause 5.4, a transaction
    is uniquely identified by the composite key (remote_address,
    invoke_id). Using invoke_id alone would cause collisions when
    communicating with multiple devices simultaneously.
    """

    def __init__(self, network: NetworkLayer,
                 apdu_timeout: float = 6.0,
                 apdu_retries: int = 3):
        self._network = network
        self._timeout = apdu_timeout
        self._retries = apdu_retries
        self._transactions: dict[
            tuple[BACnetAddress, int], ClientTransaction
        ] = {}
        self._next_invoke_id = 0

    def _allocate_invoke_id(self, destination: BACnetAddress) -> int:
        """Allocate the next available invoke ID (0-255) for the given peer."""
        for _ in range(256):
            iid = self._next_invoke_id
            self._next_invoke_id = (self._next_invoke_id + 1) & 0xFF
            if (destination, iid) not in self._transactions:
                return iid
        raise RuntimeError("No available invoke IDs for this peer")

    async def send_request(self, service_choice: int,
                          request_data: bytes,
                          destination: BACnetAddress,
                          expecting_reply: bool = True) -> bytes:
        """Send a confirmed request and await the response.

        Returns the service-ack data from ComplexACK,
        or empty bytes for SimpleACK.
        Raises BACnetError, BACnetReject, or BACnetAbort on failure.
        """
        loop = asyncio.get_running_loop()
        invoke_id = self._allocate_invoke_id(destination)
        future: asyncio.Future[bytes] = loop.create_future()

        txn = ClientTransaction(
            invoke_id=invoke_id,
            destination=destination,
            service_choice=service_choice,
            request_data=request_data,
            future=future,
        )
        key = (destination, invoke_id)
        self._transactions[key] = txn

        try:
            await self._send_confirmed_request(txn)
            return await future
        finally:
            self._transactions.pop(key, None)
            if txn.timeout_handle:
                txn.timeout_handle.cancel()

    def handle_simple_ack(self, source: BACnetAddress,
                          invoke_id: int, service_choice: int) -> None:
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            txn.future.set_result(b'')

    def handle_complex_ack(self, source: BACnetAddress,
                           invoke_id: int, service_choice: int,
                           data: bytes, segmented: bool,
                           more_follows: bool,
                           sequence_number: int | None) -> None:
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if not txn or txn.future.done():
            return

        if not segmented:
            txn.future.set_result(data)
        else:
            # Handle segmented response assembly
            self._handle_segment(txn, sequence_number, data, more_follows)

    def handle_error(self, source: BACnetAddress,
                    invoke_id: int, error_class: int,
                    error_code: int) -> None:
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            txn.future.set_exception(
                BACnetError(ErrorClass(error_class), ErrorCode(error_code))
            )

    def handle_reject(self, source: BACnetAddress,
                     invoke_id: int, reason: int) -> None:
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            txn.future.set_exception(BACnetReject(RejectReason(reason)))

    def handle_abort(self, source: BACnetAddress,
                    invoke_id: int, reason: int) -> None:
        key = (source, invoke_id)
        txn = self._transactions.get(key)
        if txn and not txn.future.done():
            txn.future.set_exception(BACnetAbort(AbortReason(reason)))

    async def _send_confirmed_request(self, txn: ClientTransaction) -> None:
        """Encode and send confirmed request APDU."""
        apdu = encode_confirmed_request(
            invoke_id=txn.invoke_id,
            service_choice=txn.service_choice,
            service_request=txn.request_data,
        )
        await self._network.send(
            apdu, txn.destination, expecting_reply=True
        )
        self._start_timeout(txn)

    def _start_timeout(self, txn: ClientTransaction) -> None:
        loop = asyncio.get_running_loop()
        key = (txn.destination, txn.invoke_id)
        txn.timeout_handle = loop.call_later(
            self._timeout, self._on_timeout, key
        )

    def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        txn = self._transactions.get(key)
        if not txn or txn.future.done():
            return
        if txn.retry_count < self._retries:
            txn.retry_count += 1
            asyncio.create_task(self._send_confirmed_request(txn))
        else:
            txn.future.set_exception(
                BACnetAbort(AbortReason.TSM_TIMEOUT)
            )
```

### 4.2 SegmentACK PDU and Wire Encoding Tables

```python
@dataclass(frozen=True, slots=True)
class SegmentAckPDU:
    """BACnet-SegmentACK-PDU (Clause 20.1.6)."""
    negative_ack: bool          # True = NAK (request retransmission)
    server: bool                # True = sent by server, False = sent by client
    invoke_id: int              # Original invoke ID
    sequence_number: int        # Sequence number being acknowledged
    actual_window_size: int     # 1-127, accepted window size


# Max-Segments-Accepted encoding (Clause 20.1.2.4)
# 3-bit field in ConfirmedRequestPDU header
MAX_SEGMENTS_ENCODING: dict[int, int | None] = {
    0: None,    # Unspecified
    1: 2,
    2: 4,
    3: 8,
    4: 16,
    5: 32,
    6: 64,
    7: None,    # Greater than 64
}

# Max-APDU-Length-Accepted encoding (Clause 20.1.2.5)
# 4-bit field in ConfirmedRequestPDU and I-Am
MAX_APDU_LENGTH_ENCODING: dict[int, int] = {
    0: 50,      # MinimumMessageSize
    1: 128,
    2: 206,     # Fits LonTalk frame
    3: 480,     # Fits ARCNET frame
    4: 1024,
    5: 1476,    # Fits Ethernet/BACnet-IP frame
    # 6-15: reserved by ASHRAE
}

def encode_max_apdu_length(length: int) -> int:
    """Convert a max APDU length to its 4-bit wire encoding."""
    for code, max_len in sorted(MAX_APDU_LENGTH_ENCODING.items(), reverse=True):
        if length >= max_len:
            return code
    return 0

def decode_max_apdu_length(code: int) -> int:
    """Convert a 4-bit wire encoding to max APDU length."""
    return MAX_APDU_LENGTH_ENCODING.get(code, 50)
```

### 4.3 Segmentation Manager

```python
class SegmentationManager:
    """Handles message segmentation for large APDUs (Clause 5.2).

    Splitting: When an APDU exceeds max_apdu_length, split into segments
    with sequence numbers. Send window at a time, await SegmentACK.

    Assembly: Collect incoming segments by sequence number, reassemble
    when all segments received (more_follows == False on last segment).
    """

    def __init__(self, max_apdu_length: int = 1476,
                 max_segments: int = 64,
                 proposed_window_size: int = 16):
        self._max_apdu = max_apdu_length
        self._max_segments = max_segments
        self._window_size = proposed_window_size

    def needs_segmentation(self, apdu_data: bytes) -> bool:
        return len(apdu_data) > self._max_apdu

    def segment(self, service_data: bytes) -> list[bytes]:
        """Split service data into segments."""
        # Account for APDU header overhead in each segment
        max_payload = self._max_apdu - 6  # Approximate header size
        segments = []
        offset = 0
        while offset < len(service_data):
            end = min(offset + max_payload, len(service_data))
            segments.append(service_data[offset:end])
            offset = end
        return segments

    def reassemble(self, segments: dict[int, bytes]) -> bytes:
        """Reassemble segments in sequence order."""
        return b''.join(
            segments[i] for i in sorted(segments.keys())
        )
```

## 5. High-Level Client API

```python
class BACnetClient:
    """High-level async BACnet client API.

    Provides typed, pythonic methods for common BACnet operations.
    """

    def __init__(self, app: BACnetApplication):
        self._app = app

    async def read_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
    ) -> Any:
        """Read a single property from a remote device."""
        request = ReadPropertyRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=array_index,
        )
        ack_data = await self._app.confirmed_request(
            address, ConfirmedServiceChoice.READ_PROPERTY, request.encode()
        )
        ack = ReadPropertyACK.decode(memoryview(ack_data))
        return ack.property_value

    async def read_property_multiple(
        self,
        address: BACnetAddress,
        read_access_specs: list[ReadAccessSpecification],
    ) -> list[ReadAccessResult]:
        """Read multiple properties from a remote device."""
        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=read_access_specs,
        )
        ack_data = await self._app.confirmed_request(
            address, ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE,
            request.encode()
        )
        ack = ReadPropertyMultipleACK.decode(memoryview(ack_data))
        return ack.list_of_read_access_results

    async def write_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        value: Any,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property value to a remote device."""
        request = WritePropertyRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_value=value,
            priority=priority,
            property_array_index=array_index,
        )
        await self._app.confirmed_request(
            address, ConfirmedServiceChoice.WRITE_PROPERTY, request.encode()
        )

    async def who_is(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
    ) -> list[IAmRequest]:
        """Discover devices via Who-Is broadcast.

        Sends a Who-Is request and collects I-Am responses for `timeout` seconds.
        """
        request = WhoIsRequest(low_limit=low_limit, high_limit=high_limit)
        results: list[IAmRequest] = []

        def on_i_am(data: bytes, source: BACnetAddress) -> None:
            iam = IAmRequest.decode(memoryview(data))
            results.append(iam)

        self._app.register_temporary_handler(
            UnconfirmedServiceChoice.I_AM, on_i_am
        )
        try:
            await self._app.unconfirmed_request(
                destination, UnconfirmedServiceChoice.WHO_IS, request.encode()
            )
            await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(
                UnconfirmedServiceChoice.I_AM, on_i_am
            )
        return results

    async def subscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        confirmed: bool = True,
        lifetime: int | None = None,
        callback: Callable[[CovNotification], None] | None = None,
    ) -> int:
        """Subscribe to Change of Value notifications.

        Returns the subscriber process identifier for managing the subscription.
        """
        process_id = self._app.allocate_process_id()
        request = SubscribeCOVRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
            issue_confirmed_notifications=confirmed,
            lifetime=lifetime,
        )
        await self._app.confirmed_request(
            address, ConfirmedServiceChoice.SUBSCRIBE_COV, request.encode()
        )
        if callback:
            self._app.register_cov_callback(process_id, callback)
        return process_id

    async def unsubscribe_cov(
        self,
        address: BACnetAddress,
        process_id: int,
        object_identifier: ObjectIdentifier,
    ) -> None:
        """Cancel a COV subscription.

        Per Clause 13.14, a cancellation request omits both
        issueConfirmedNotifications and lifetime fields.
        The server returns Result(+) even if no matching
        subscription context exists.
        """
        request = SubscribeCOVRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
            # Both None = cancellation per spec
            issue_confirmed_notifications=None,
            lifetime=None,
        )
        await self._app.confirmed_request(
            address, ConfirmedServiceChoice.SUBSCRIBE_COV, request.encode()
        )
        self._app.unregister_cov_callback(process_id)

    async def device_communication_control(
        self,
        address: BACnetAddress,
        enable_disable: int,
        duration: int | None = None,
        password: str | None = None,
    ) -> None:
        """Enable or disable communication on a remote device."""
        request = DeviceCommunicationControlRequest(
            enable_disable=enable_disable,
            duration=duration,
            password=password,
        )
        await self._app.confirmed_request(
            address, ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
            request.encode()
        )

    async def reinitialize_device(
        self,
        address: BACnetAddress,
        state: int,
        password: str | None = None,
    ) -> None:
        """Reinitialize a remote device."""
        request = ReinitializeDeviceRequest(
            reinitialized_state_of_device=state,
            password=password,
        )
        await self._app.confirmed_request(
            address, ConfirmedServiceChoice.REINITIALIZE_DEVICE,
            request.encode()
        )
```

## 6. Service Parameter Encoding Reference

### 6.1 ReadProperty-Request (Clause 15.5.1)

```
ReadProperty-Request ::= SEQUENCE {
    objectIdentifier    [0] BACnetObjectIdentifier,
    propertyIdentifier  [1] BACnetPropertyIdentifier,
    propertyArrayIndex  [2] Unsigned OPTIONAL
}
```

### 6.2 ReadPropertyMultiple-Request (Clause 15.7.1)

```
ReadPropertyMultiple-Request ::= SEQUENCE {
    listOfReadAccessSpecs  SEQUENCE OF ReadAccessSpecification
}

ReadAccessSpecification ::= SEQUENCE {
    objectIdentifier       [0] BACnetObjectIdentifier,
    listOfPropertyReferences  [1] SEQUENCE OF BACnetPropertyReference
}

BACnetPropertyReference ::= SEQUENCE {
    propertyIdentifier  [0] BACnetPropertyIdentifier,
    propertyArrayIndex  [1] Unsigned OPTIONAL
}
```

### 6.3 WriteProperty-Request (Clause 15.9.1)

```
WriteProperty-Request ::= SEQUENCE {
    objectIdentifier    [0] BACnetObjectIdentifier,
    propertyIdentifier  [1] BACnetPropertyIdentifier,
    propertyArrayIndex  [2] Unsigned OPTIONAL,
    propertyValue       [3] ABSTRACT-SYNTAX.&TYPE,
    priority            [4] Unsigned (1..16) OPTIONAL
}
```

### 6.4 Who-Is-Request (Clause 16.10)

```
Who-Is-Request ::= SEQUENCE {
    deviceInstanceRangeLowLimit  [0] Unsigned (0..4194303) OPTIONAL,
    deviceInstanceRangeHighLimit [1] Unsigned (0..4194303) OPTIONAL
}
-- Both must be present or both absent
```

### 6.5 I-Am-Request (Clause 16.10)

```
I-Am-Request ::= SEQUENCE {
    iAmDeviceIdentifier    BACnetObjectIdentifier,
    maxAPDULengthAccepted  Unsigned,
    segmentationSupported  BACnetSegmentation,
    vendorID               Unsigned
}
-- IMPORTANT: All fields use APPLICATION tags (not context-specific tags).
-- This is unlike most other service requests which use context tags.
-- The encoder must use encode_application_tagged() for all four fields.
```

### 6.6 SubscribeCOV-Request (Clause 13.14)

```
SubscribeCOV-Request ::= SEQUENCE {
    subscriberProcessIdentifier  [0] Unsigned32,
    monitoredObjectIdentifier    [1] BACnetObjectIdentifier,
    issueConfirmedNotifications  [2] BOOLEAN OPTIONAL,
    lifetime                     [3] Unsigned OPTIONAL
}
```

## 7. Error Handling Strategy

BACnet defines three negative response types. Each mapped to a distinct Python exception:

```python
class BACnetException(Exception):
    """Base exception for BACnet protocol errors."""
    pass

class BACnetError(BACnetException):
    """BACnet Error-PDU received. Contains error class and code per Clause 18.

    Note: In 135-2016, some services (e.g., WritePropertyMultiple,
    CreateObject) may include additional error data beyond the basic
    error-class + error-code pair. The error_data field captures this
    optional extended encoding.
    """
    def __init__(self, error_class: ErrorClass, error_code: ErrorCode,
                 error_data: bytes = b''):
        self.error_class = error_class
        self.error_code = error_code
        self.error_data = error_data
        super().__init__(f"{error_class.name}: {error_code.name}")

class BACnetReject(BACnetException):
    """BACnet Reject-PDU received. Syntax/protocol error per Clause 18.9."""
    def __init__(self, reason: RejectReason):
        self.reason = reason
        super().__init__(f"Reject: {reason.name}")

class BACnetAbort(BACnetException):
    """BACnet Abort-PDU received. Transaction aborted per Clause 18.10."""
    def __init__(self, reason: AbortReason):
        self.reason = reason
        super().__init__(f"Abort: {reason.name}")

class BACnetTimeout(BACnetException):
    """Request timed out after all retries exhausted."""
    pass
```

Server handlers raise `BACnetError` to send an Error-PDU back. The application layer catches this and encodes it automatically:

```python
# In application layer dispatch
try:
    result = await handler(service_choice, request_data, source)
    if result is None:
        send_simple_ack(invoke_id, service_choice)
    else:
        send_complex_ack(invoke_id, service_choice, result)
except BACnetError as e:
    send_error(invoke_id, service_choice, e.error_class, e.error_code)
except BACnetReject as e:
    send_reject(invoke_id, e.reason)
except BACnetAbort as e:
    send_abort(invoke_id, e.reason)
except Exception:
    send_abort(invoke_id, AbortReason.OTHER)
```

## 8. Server Transaction State Machine

The server TSM (Clause 5.4.3) tracks incoming confirmed requests that require a response. It ensures that duplicate requests receive the same response and manages segmented request reassembly.

### 8.1 Server TSM States

Per Clause 5.4.5, the server TSM has four states:

| State              | Description                                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------------------- |
| IDLE               | No active transaction for this invoke-id/source pair                                                     |
| SEGMENTED_REQUEST  | Receiving a segmented Confirmed-Request. Collecting segments, sending SegmentACKs.                       |
| AWAIT_RESPONSE     | Complete request received and dispatched; waiting for the service handler to complete                    |
| SEGMENTED_RESPONSE | Sending a segmented response; waiting for SegmentACK from client                                         |

### 8.2 Server TSM Implementation

```python
class ServerTransactionState(IntEnum):
    IDLE = 0
    SEGMENTED_REQUEST = 1
    AWAIT_RESPONSE = 2
    SEGMENTED_RESPONSE = 3


@dataclass
class ServerTransaction:
    """Tracks an incoming confirmed request being processed."""
    invoke_id: int
    source: BACnetAddress
    service_choice: int
    state: ServerTransactionState = ServerTransactionState.IDLE
    # Cached response for duplicate detection
    cached_response: bytes | None = None
    # Segmented response state
    segments: list[bytes] | None = None
    segment_index: int = 0
    window_size: int = 1
    timeout_handle: asyncio.TimerHandle | None = None


class ServerTSM:
    """Server Transaction State Machine.

    Prevents duplicate processing and manages response segmentation.
    Key: (source_address, invoke_id) -> ServerTransaction
    """

    def __init__(self, network: NetworkLayer,
                 request_timeout: float = 6.0):
        self._network = network
        self._timeout = request_timeout
        self._transactions: dict[tuple[BACnetAddress, int],
                                 ServerTransaction] = {}

    def receive_confirmed_request(
        self, invoke_id: int, source: BACnetAddress,
        service_choice: int, request_data: bytes
    ) -> ServerTransaction | None:
        """Register an incoming request. Returns None if duplicate."""
        key = (source, invoke_id)
        existing = self._transactions.get(key)

        if existing is not None:
            # Duplicate request — resend cached response if available
            if existing.cached_response is not None:
                asyncio.create_task(
                    self._network.send(existing.cached_response,
                                       source, expecting_reply=False)
                )
            return None  # Signal caller to skip processing

        txn = ServerTransaction(
            invoke_id=invoke_id,
            source=source,
            service_choice=service_choice,
            state=ServerTransactionState.AWAIT_RESPONSE,
        )
        self._transactions[key] = txn
        self._start_timeout(txn)
        return txn

    def complete_transaction(self, txn: ServerTransaction,
                            response_apdu: bytes) -> None:
        """Cache response and schedule cleanup."""
        txn.cached_response = response_apdu
        txn.state = ServerTransactionState.IDLE
        # Keep cached for a timeout period to handle retransmissions
        self._restart_timeout(txn)

    def _start_timeout(self, txn: ServerTransaction) -> None:
        loop = asyncio.get_running_loop()
        key = (txn.source, txn.invoke_id)
        txn.timeout_handle = loop.call_later(
            self._timeout, self._on_timeout, key
        )

    def _restart_timeout(self, txn: ServerTransaction) -> None:
        if txn.timeout_handle:
            txn.timeout_handle.cancel()
        self._start_timeout(txn)

    def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
        self._transactions.pop(key, None)
```

## 9. Application Layer Orchestrator

The `BACnetApplication` class ties all layers together. It owns the transport, network layer, both TSMs, and the service registry. It is the central coordination point.

### 9.1 Orchestrator Design

```python
class BACnetApplication:
    """Central orchestrator connecting all protocol layers.

    Owns: Transport -> Network -> Application dispatch
    Provides: confirmed_request() and unconfirmed_request() for client use,
              service handler registration for server use.
    """

    def __init__(self, config: DeviceConfig):
        self._config = config
        self._transport = BIPTransport(
            interface=config.interface,
            port=config.port,
        )
        self._network = NetworkLayer(self._transport)
        self._client_tsm = ClientTSM(
            self._network,
            apdu_timeout=config.apdu_timeout / 1000,
            apdu_retries=config.apdu_retries,
        )
        self._server_tsm = ServerTSM(self._network)
        self._service_registry = ServiceRegistry()
        self._object_db = ObjectDatabase()
        self._device: DeviceObject | None = None
        self._unconfirmed_listeners: dict[
            int, list[Callable]] = {}

        # Wire receive path
        self._network.on_receive(self._on_apdu_received)

    # ---- Client-side API ----

    async def confirmed_request(
        self, destination: BACnetAddress,
        service_choice: int,
        service_data: bytes,
    ) -> bytes:
        """Send a confirmed request and await the response.

        Returns ComplexACK service data, or empty bytes for SimpleACK.
        """
        return await self._client_tsm.send_request(
            service_choice, service_data, destination
        )

    async def unconfirmed_request(
        self, destination: BACnetAddress,
        service_choice: int,
        service_data: bytes,
    ) -> None:
        """Send an unconfirmed request (broadcast or directed)."""
        apdu = encode_unconfirmed_request(service_choice, service_data)
        await self._network.send(
            apdu, destination, expecting_reply=False
        )

    # ---- Receive path ----

    def _on_apdu_received(self, data: bytes,
                          source: BACnetAddress) -> None:
        """Dispatch received APDU based on PDU type."""
        pdu_type = (data[0] >> 4) & 0x0F

        match PduType(pdu_type):
            case PduType.CONFIRMED_REQUEST:
                header = decode_confirmed_request_header(memoryview(data))
                asyncio.create_task(
                    self._handle_confirmed_request(header, source)
                )
            case PduType.UNCONFIRMED_REQUEST:
                header = decode_unconfirmed_request_header(memoryview(data))
                asyncio.create_task(
                    self._handle_unconfirmed_request(header, source)
                )
            case PduType.SIMPLE_ACK:
                header = decode_simple_ack(memoryview(data))
                self._client_tsm.handle_simple_ack(
                    source, header.invoke_id, header.service_choice
                )
            case PduType.COMPLEX_ACK:
                header = decode_complex_ack(memoryview(data))
                self._client_tsm.handle_complex_ack(
                    source, header.invoke_id, header.service_choice,
                    header.service_ack,
                    header.segmented, header.more_follows,
                    header.sequence_number,
                )
            case PduType.ERROR:
                header = decode_error_pdu(memoryview(data))
                self._client_tsm.handle_error(
                    source, header.invoke_id,
                    header.error_class, header.error_code,
                )
            case PduType.REJECT:
                header = decode_reject_pdu(memoryview(data))
                self._client_tsm.handle_reject(
                    source, header.invoke_id, header.reject_reason,
                )
            case PduType.ABORT:
                header = decode_abort_pdu(memoryview(data))
                self._client_tsm.handle_abort(
                    source, header.invoke_id, header.abort_reason,
                )
            case PduType.SEGMENT_ACK:
                # Handled by whichever TSM owns the transaction
                pass

    async def _handle_confirmed_request(
        self, header: ConfirmedRequestPDU,
        source: BACnetAddress,
    ) -> None:
        """Process incoming confirmed request through server TSM."""
        txn = self._server_tsm.receive_confirmed_request(
            header.invoke_id, source,
            header.service_choice, header.service_request,
        )
        if txn is None:
            return  # Duplicate, response already resent

        try:
            result = await self._service_registry.dispatch_confirmed(
                header.service_choice,
                header.service_request,
                source,
            )
            if result is None:
                response = encode_simple_ack(
                    header.invoke_id, header.service_choice
                )
            else:
                response = encode_complex_ack(
                    header.invoke_id, header.service_choice, result
                )
        except BACnetError as e:
            response = encode_error_pdu(
                header.invoke_id, header.service_choice,
                e.error_class, e.error_code,
            )
        except BACnetReject as e:
            response = encode_reject_pdu(header.invoke_id, e.reason)
        except BACnetAbort as e:
            response = encode_abort_pdu(header.invoke_id, e.reason)
        except Exception:
            response = encode_abort_pdu(
                header.invoke_id, AbortReason.OTHER
            )

        await self._network.send(
            response, source, expecting_reply=False
        )
        self._server_tsm.complete_transaction(txn, response)

    async def _handle_unconfirmed_request(
        self, header: UnconfirmedRequestPDU,
        source: BACnetAddress,
    ) -> None:
        """Dispatch unconfirmed request to registered handlers."""
        # Dispatch to permanent handlers (service registry)
        await self._service_registry.dispatch_unconfirmed(
            header.service_choice, header.service_request, source
        )
        # Dispatch to temporary listeners (e.g., Who-Is collectors)
        listeners = self._unconfirmed_listeners.get(
            header.service_choice, []
        )
        for listener in listeners:
            try:
                listener(header.service_request, source)
            except Exception:
                pass  # Don't let listener errors affect dispatch

    # ---- Temporary listener management ----

    def register_temporary_handler(
        self, service_choice: int,
        handler: Callable,
    ) -> None:
        self._unconfirmed_listeners.setdefault(
            service_choice, []
        ).append(handler)

    def unregister_temporary_handler(
        self, service_choice: int,
        handler: Callable,
    ) -> None:
        listeners = self._unconfirmed_listeners.get(service_choice, [])
        if handler in listeners:
            listeners.remove(handler)
```

### 9.2 Layer Wiring Summary

```
User Code
    │
    ▼
BACnetClient / BACnetServer  (app/client.py, app/server.py)
    │
    ▼
BACnetApplication             (app/application.py)
    ├── ServiceRegistry        (services/base.py)
    ├── ClientTSM              (app/tsm.py)
    ├── ServerTSM              (app/tsm.py)
    │
    ▼
NetworkLayer                  (network/layer.py)
    │
    ▼
BIPTransport                  (transport/bip.py)
    ├── BVLL codec             (transport/bvll.py)
    ├── ForeignDeviceManager   (transport/foreign_device.py)
    └── BBMDManager            (transport/bbmd.py)
    │
    ▼
asyncio.DatagramProtocol      (UDP socket)
```
