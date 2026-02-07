# Async Patterns, Concurrency, and Lifecycle

## 1. Overview

bac-py is built entirely on Python 3.13+ `asyncio`. This document details the concurrency model, lifecycle management, structured concurrency patterns, and how the async architecture maps to BACnet protocol requirements.

## 2. Event Loop Architecture

### 2.1 Single-Loop Model

All protocol processing runs in a single asyncio event loop. This eliminates synchronization primitives (locks, semaphores) within the protocol stack. The event loop handles:

- UDP socket I/O via `DatagramProtocol` (callback-driven, not awaited)
- Timer-based retries and timeouts via `loop.call_later()`
- Service request/response correlation via `asyncio.Future`
- Background tasks (COV, foreign device registration) via `asyncio.Task`

```
┌──────────────────────────────────────────────────────────┐
│                    asyncio Event Loop                     │
│                                                          │
│  ┌──────────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ UDP Protocol │  │  Timers   │  │ Background Tasks │  │
│  │ (callbacks)  │  │ (retries, │  │ (COV, FDR,       │  │
│  │              │  │  timeouts)│  │  BBMD cleanup)   │  │
│  └──────┬───────┘  └─────┬─────┘  └────────┬─────────┘  │
│         │                │                  │            │
│         ▼                ▼                  ▼            │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Protocol Stack Processing            │    │
│  │  BVLL → NPDU → APDU → Service Dispatch           │    │
│  └──────────────────────────────────────────────────┘    │
│         │                                                │
│         ▼                                                │
│  ┌──────────────────────────────────────────────────┐    │
│  │           Futures (caller awaits result)           │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Callback vs. Coroutine Boundary

The `asyncio.DatagramProtocol.datagram_received()` callback is synchronous. All protocol parsing (BVLL, NPDU, APDU header) runs synchronously within this callback. Only when dispatching to a service handler does processing cross into coroutine territory:

```python
def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
    # Synchronous: parse BVLL, NPDU, APDU header
    bvll = decode_bvll(memoryview(data))
    npdu = decode_npdu(memoryview(bvll.data))
    pdu_type, header = decode_apdu_header(memoryview(npdu.apdu))

    match pdu_type:
        case PduType.CONFIRMED_REQUEST:
            # Schedule async handler — do NOT await in callback
            asyncio.create_task(
                self._dispatch_confirmed(header, npdu, addr)
            )
        case PduType.UNCONFIRMED_REQUEST:
            asyncio.create_task(
                self._dispatch_unconfirmed(header, npdu, addr)
            )
        case PduType.SIMPLE_ACK | PduType.COMPLEX_ACK:
            # Synchronous: resolve the waiting Future
            self._client_tsm.handle_ack(header)
        case PduType.ERROR | PduType.REJECT | PduType.ABORT:
            # Synchronous: set exception on the waiting Future
            self._client_tsm.handle_error_response(header)
```

This design keeps the callback fast (no await) for response-path messages (ACKs, errors) that just resolve Futures, while allowing request-handler logic to use async I/O if needed.

## 3. Structured Concurrency with TaskGroup

### 3.1 Application Lifecycle

The top-level application uses `asyncio.TaskGroup` (Python 3.11+) for structured concurrency. All background tasks are children of the group, ensuring clean shutdown:

```python
class BACnetApplication:
    """Core application lifecycle manager."""

    def __init__(self, config: DeviceConfig):
        self._config = config
        self._transport: BIPTransport | None = None
        self._network: NetworkLayer | None = None
        self._client_tsm: ClientTSM | None = None
        self._server_tsm: ServerTSM | None = None
        self._service_registry = ServiceRegistry()
        self._object_db = ObjectDatabase()
        self._running = False

    async def run(self) -> None:
        """Start the application and run until cancelled.

        Uses TaskGroup for structured concurrency — all background
        tasks are automatically cancelled on shutdown.
        """
        self._transport = BIPTransport(
            interface=self._config.interface,
            port=self._config.port,
        )
        self._network = NetworkLayer(self._transport)
        self._client_tsm = ClientTSM(
            self._network,
            apdu_timeout=self._config.apdu_timeout / 1000,
            apdu_retries=self._config.apdu_retries,
        )
        self._server_tsm = ServerTSM(self._network)

        # Wire up receive callback
        self._network.on_receive(self._on_apdu_received)

        await self._transport.start()
        self._running = True
        self._stop_event = asyncio.Event()

        try:
            async with asyncio.TaskGroup() as tg:
                # Foreign device registration (if configured)
                if self._config.bbmd_address:
                    tg.create_task(self._foreign_device_loop())

                # COV subscription lifetime management
                tg.create_task(self._cov_lifetime_monitor())

                # I-Am announcement on startup
                tg.create_task(self._startup_announce())

                # Keep alive until stop() is called
                tg.create_task(self._wait_for_stop())
        except* Exception as eg:
            # TaskGroup wraps child exceptions in ExceptionGroup.
            # Log them so they aren't silently swallowed.
            for exc in eg.exceptions:
                logger.error("Background task failed", exc_info=exc)
        finally:
            self._running = False
            await self._transport.stop()

    async def _wait_for_stop(self) -> None:
        """Block until stop() signals the event."""
        await self._stop_event.wait()
```

### 3.2 Context Manager Interface

For convenience, the application also supports `async with`:

```python
class BACnetApplication:
    async def __aenter__(self) -> BACnetApplication:
        self._ready_event = asyncio.Event()
        self._run_task = asyncio.create_task(self._run_and_signal_ready())
        # Wait for transport to be ready without busy-spinning
        await self._ready_event.wait()
        return self

    async def _run_and_signal_ready(self) -> None:
        """Wrapper that signals readiness after transport starts."""
        # run() sets self._running = True after transport.start().
        # We need to signal the ready event at that point.
        # Override is kept simple: run() already sets _running,
        # and we poll once after yielding control.
        task = asyncio.ensure_future(self.run())
        while not self._running:
            await asyncio.sleep(0)
        self._ready_event.set()
        await task

    async def __aexit__(self, *exc_info) -> None:
        self._stop_event.set()
        with contextlib.suppress(asyncio.CancelledError):
            await self._run_task
```

Usage:

```python
async def main():
    config = DeviceConfig(instance_number=1234, name="My Device")
    app = BACnetApplication(config)

    async with app:
        client = BACnetClient(app)
        value = await client.read_property(
            target_addr,
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            PropertyIdentifier.PRESENT_VALUE,
        )
        print(f"Temperature: {value}")
```

## 4. Request/Response Correlation

### 4.1 Future-Based Request Tracking

Each confirmed service request creates a `Future` that the caller awaits. The client TSM resolves it when the matching response arrives:

```
Caller                    ClientTSM                Transport
  │                          │                        │
  │  send_request()          │                        │
  │─────────────────────────►│                        │
  │                          │  allocate invoke_id    │
  │                          │  create Future         │
  │                          │  encode APDU           │
  │                          │───────────────────────►│ UDP send
  │                          │                        │
  │  await future            │  start timeout timer   │
  │  ◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │                        │
  │  (suspended)             │                        │
  │                          │                        │
  │                          │  ◄────────────────────│ UDP recv (ACK)
  │                          │  decode response       │
  │                          │  future.set_result()   │
  │                          │                        │
  │  ◄───────────────────────│                        │
  │  (resumed with result)   │                        │
```

### 4.2 Timeout and Retry

Timeouts use `loop.call_later()` rather than `asyncio.wait_for()` to avoid task cancellation complexity:

```python
def _start_timeout(self, txn: ClientTransaction) -> None:
    loop = asyncio.get_running_loop()
    key = (txn.destination, txn.invoke_id)
    txn.timeout_handle = loop.call_later(
        self._timeout_seconds,
        self._on_timeout,
        key,
    )

def _on_timeout(self, key: tuple[BACnetAddress, int]) -> None:
    """Called by the event loop when a request times out."""
    txn = self._transactions.get(key)
    if txn is None or txn.future.done():
        return

    if txn.retry_count < self._max_retries:
        txn.retry_count += 1
        # Cancel old timer, re-send, start new timer
        asyncio.create_task(self._resend(txn))
    else:
        txn.future.set_exception(BACnetTimeout(
            f"No response after {self._max_retries} retries"
        ))
```

### 4.3 Concurrent Request Management

Multiple requests to different devices proceed concurrently. Requests to the _same_ device are independent (BACnet allows up to 256 concurrent invoke-ids per peer):

```python
# Concurrent reads to different devices
async with asyncio.TaskGroup() as tg:
    tasks = [
        tg.create_task(client.read_property(addr, obj_id, prop_id))
        for addr, obj_id, prop_id in targets
    ]

# Batch read from a single device (use ReadPropertyMultiple instead)
results = await client.read_property_multiple(addr, specs)
```

## 5. Background Task Patterns

### 5.1 Foreign Device Re-registration

```python
async def _foreign_device_loop(self) -> None:
    """Re-register with BBMD at TTL/2 intervals."""
    ttl = self._config.bbmd_ttl
    while True:
        await self._transport.register_foreign_device(
            self._config.bbmd_address, ttl
        )
        await asyncio.sleep(ttl / 2)
```

### 5.2 COV Subscription Lifetime

```python
async def _cov_lifetime_monitor(self) -> None:
    """Prune expired COV subscriptions."""
    while True:
        await asyncio.sleep(10)  # Check every 10 seconds
        now = asyncio.get_running_loop().time()
        expired = [
            sub for sub in self._cov_subscriptions
            if sub.lifetime is not None
            and (now - sub.created_at) > sub.lifetime
        ]
        for sub in expired:
            self._cov_subscriptions.remove(sub)
```

### 5.3 Who-Is Collection Pattern

Who-Is is broadcast-and-collect: send once, gather responses for a duration:

```python
async def who_is(self, low: int | None = None, high: int | None = None,
                 timeout: float = 3.0) -> list[IAmResponse]:
    """Broadcast Who-Is, collect I-Am responses for `timeout` seconds."""
    results: list[IAmResponse] = []
    collection_done = asyncio.Event()

    def on_i_am(iam: IAmResponse, source: BACnetAddress) -> None:
        results.append(iam)

    token = self._app.subscribe_unconfirmed(
        UnconfirmedServiceChoice.I_AM, on_i_am
    )
    try:
        await self._app.broadcast_unconfirmed(
            UnconfirmedServiceChoice.WHO_IS,
            encode_who_is(low, high),
        )
        await asyncio.sleep(timeout)
    finally:
        self._app.unsubscribe_unconfirmed(token)

    return results
```

## 6. Server-Side Concurrency

### 6.1 Request Processing

Incoming confirmed requests are dispatched as independent tasks. Each task processes the request, builds a response, and sends it back. No serialization is needed for read-only operations. Writes to the object database are serialized per-object:

```python
async def _dispatch_confirmed(self, header: ConfirmedRequestPDU,
                               source: BACnetAddress) -> None:
    """Handle an incoming confirmed request."""
    try:
        result = await self._service_registry.dispatch_confirmed(
            header.service_choice,
            header.service_request,
            source,
        )
        if result is None:
            await self._send_simple_ack(source, header.invoke_id,
                                        header.service_choice)
        else:
            await self._send_complex_ack(source, header.invoke_id,
                                         header.service_choice, result)
    except BACnetError as e:
        await self._send_error(source, header.invoke_id,
                               header.service_choice,
                               e.error_class, e.error_code)
    except BACnetReject as e:
        await self._send_reject(source, header.invoke_id, e.reason)
    except BACnetAbort as e:
        await self._send_abort(source, header.invoke_id, e.reason)
    except Exception:
        await self._send_abort(source, header.invoke_id,
                               AbortReason.OTHER)
```

### 6.2 Write Serialization

To prevent race conditions on object write operations, each object has an `asyncio.Lock` that serializes writes without blocking reads. The lock is needed because write operations may involve multiple steps (e.g., validating a value, updating the priority array, recalculating Present_Value, and triggering COV notifications). Without the lock, two concurrent writes could interleave mid-operation and corrupt the priority array state:

```python
class BACnetObject:
    def __init__(self, instance_number: int, **kwargs):
        ...
        self._write_lock = asyncio.Lock()

    async def async_write_property(self, prop_id: PropertyIdentifier,
                                    value: Any, priority: int | None = None,
                                    array_index: int | None = None) -> None:
        async with self._write_lock:
            self.write_property(prop_id, value, priority, array_index)
```

Reads remain lock-free. The GIL and single event loop already ensure atomicity of individual dict operations.

## 7. Graceful Shutdown

### 7.1 Shutdown Sequence

1. Cancel the `TaskGroup` (or call `app.stop()`)
2. `TaskGroup.__aexit__` cancels all child tasks and waits for them
3. Foreign device registration loop exits
4. COV monitor exits
5. Outstanding client transactions have their Futures cancelled
6. Transport layer closes the UDP socket

```python
async def stop(self) -> None:
    """Initiate graceful shutdown."""
    # Cancel all pending transactions
    for txn in self._client_tsm.active_transactions():
        if not txn.future.done():
            txn.future.cancel()

    # Signal the run loop to exit (triggers TaskGroup cleanup)
    self._stop_event.set()
    if self._run_task and not self._run_task.done():
        with contextlib.suppress(asyncio.CancelledError):
            await self._run_task
```

### 7.2 Signal Handling

For standalone applications:

```python
async def main():
    app = BACnetApplication(config)
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(app.stop())
        )

    await app.run()
```

## 8. Thread Integration

### 8.1 Calling from Synchronous Code

When bac-py is embedded in a threaded application (e.g., a web framework), callers use `run_coroutine_threadsafe`:

```python
# From a non-asyncio thread:
future = asyncio.run_coroutine_threadsafe(
    client.read_property(addr, obj_id, prop_id),
    app.loop,
)
result = future.result(timeout=10)  # Blocks the calling thread
```

### 8.2 Running the Event Loop in a Background Thread

For integration with synchronous applications:

```python
import threading

class BACnetRunner:
    """Runs the BACnet application in a background thread."""

    def __init__(self, config: DeviceConfig):
        self._config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._app: BACnetApplication | None = None
        self._client: BACnetClient | None = None
        self._started = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait()

    def stop(self) -> None:
        if self._loop and self._app:
            asyncio.run_coroutine_threadsafe(
                self._app.stop(), self._loop
            ).result()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._app = BACnetApplication(self._config)
        self._client = BACnetClient(self._app)
        self._started.set()
        self._loop.run_until_complete(self._app.run())

    def read_property(self, addr, obj_id, prop_id, timeout=10):
        """Thread-safe synchronous read."""
        return asyncio.run_coroutine_threadsafe(
            self._client.read_property(addr, obj_id, prop_id),
            self._loop
        ).result(timeout=timeout)
```

## 9. Performance Characteristics

| Operation                | Model                                     | Blocking?              | Typical Latency                 |
| ------------------------ | ----------------------------------------- | ---------------------- | ------------------------------- |
| UDP send                 | `transport.sendto()` (sync, non-blocking) | No                     | Microseconds                    |
| UDP receive              | `datagram_received()` callback            | No                     | Microseconds                    |
| BVLL/NPDU/APDU parse     | Synchronous in callback                   | No                     | Microseconds                    |
| Service request (client) | `await future`                            | Suspends coroutine     | Network RTT + device processing |
| Service handler (server) | `create_task()`                           | No (runs concurrently) | Application-dependent           |
| Object property read     | Dict lookup (sync)                        | No                     | Microseconds                    |
| Object property write    | `asyncio.Lock` per object                 | Suspends if contended  | Microseconds                    |
| Who-Is scan              | `asyncio.sleep(timeout)`                  | Suspends coroutine     | User-specified timeout          |

## 10. Error Propagation

Errors in background tasks must not crash the application. The `TaskGroup` propagates `ExceptionGroup` on failure; individual task errors are caught:

```python
async def _cov_lifetime_monitor(self) -> None:
    while True:
        try:
            await asyncio.sleep(10)
            self._prune_expired_subscriptions()
        except asyncio.CancelledError:
            raise  # Always re-raise CancelledError
        except Exception:
            logger.exception("Error in COV lifetime monitor")
            # Continue running — don't crash the application
```

Client-side errors are delivered through the Future mechanism, converting wire-format errors to typed Python exceptions.
