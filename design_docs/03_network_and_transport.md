# Network and Transport Layer Design

## 1. Overview

This document covers the two lowest layers of the bac-py stack:

- **Transport Layer**: BACnet/IP via UDP (Annex J), including BVLL, BBMD, and Foreign Device support
- **Network Layer**: NPDU encoding/decoding and addressing (Clause 6)

## 2. BACnet/IP Transport (Annex J)

### 2.1 UDP Foundation

BACnet/IP operates over UDP on port 0xBAC0 (47808). Each BACnet/IP device has a 6-octet "B/IP address" consisting of:

- 4-octet IPv4 address
- 2-octet UDP port number

Both are transmitted most significant octet first.

### 2.2 BVLL Message Types

The BACnet Virtual Link Layer (BVLL) wraps every BACnet/IP datagram. Every BVLL message starts with:

| Field         | Size     | Value                |
| ------------- | -------- | -------------------- |
| BVLC Type     | 1 octet  | 0x81 (BACnet/IP)     |
| BVLC Function | 1 octet  | Function code        |
| BVLC Length   | 2 octets | Total message length |

BVLC Function codes:

| Code | Function                              | Direction                     |
| ---- | ------------------------------------- | ----------------------------- |
| 0x00 | BVLC-Result                           | Response                      |
| 0x01 | Write-Broadcast-Distribution-Table    | To BBMD                       |
| 0x02 | Read-Broadcast-Distribution-Table     | To BBMD                       |
| 0x03 | Read-Broadcast-Distribution-Table-Ack | From BBMD                     |
| 0x04 | Forwarded-NPDU                        | From BBMD                     |
| 0x05 | Register-Foreign-Device               | To BBMD                       |
| 0x06 | Read-Foreign-Device-Table             | To BBMD                       |
| 0x07 | Read-Foreign-Device-Table-Ack         | From BBMD                     |
| 0x08 | Delete-Foreign-Device-Table-Entry     | To BBMD                       |
| 0x09 | Distribute-Broadcast-To-Network       | To BBMD (from foreign device) |
| 0x0A | Original-Unicast-NPDU                 | Device to device              |
| 0x0B | Original-Broadcast-NPDU               | Local broadcast               |
| 0x0C | Secure-BVLL                           | Security wrapper              |

### 2.3 BVLL Data Structures

```python
class BvlcFunction(IntEnum):
    BVLC_RESULT = 0x00
    WRITE_BROADCAST_DISTRIBUTION_TABLE = 0x01
    READ_BROADCAST_DISTRIBUTION_TABLE = 0x02
    READ_BROADCAST_DISTRIBUTION_TABLE_ACK = 0x03
    FORWARDED_NPDU = 0x04
    REGISTER_FOREIGN_DEVICE = 0x05
    READ_FOREIGN_DEVICE_TABLE = 0x06
    READ_FOREIGN_DEVICE_TABLE_ACK = 0x07
    DELETE_FOREIGN_DEVICE_TABLE_ENTRY = 0x08
    DISTRIBUTE_BROADCAST_TO_NETWORK = 0x09
    ORIGINAL_UNICAST_NPDU = 0x0A
    ORIGINAL_BROADCAST_NPDU = 0x0B
    SECURE_BVLL = 0x0C

BVLC_TYPE_BACNET_IP = 0x81
BVLL_HEADER_LENGTH = 4  # Type(1) + Function(1) + Length(2)


class BvlcResultCode(IntEnum):
    """BVLC-Result codes (Annex J.2)."""
    SUCCESSFUL_COMPLETION = 0x0000
    WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK = 0x0010
    READ_BROADCAST_DISTRIBUTION_TABLE_NAK = 0x0020
    REGISTER_FOREIGN_DEVICE_NAK = 0x0030
    READ_FOREIGN_DEVICE_TABLE_NAK = 0x0040
    DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK = 0x0050
    DISTRIBUTE_BROADCAST_TO_NETWORK_NAK = 0x0060


@dataclass(frozen=True, slots=True)
class BvllMessage:
    function: BvlcFunction
    data: bytes                          # Payload after BVLL header
    originating_address: BIPAddress | None = None  # For Forwarded-NPDU only


@dataclass(frozen=True, slots=True)
class BIPAddress:
    """6-octet BACnet/IP address: 4 bytes IP + 2 bytes port."""
    host: str           # IPv4 dotted-decimal string
    port: int           # UDP port number

    def encode(self) -> bytes:
        parts = [int(x) for x in self.host.split('.')]
        return bytes(parts) + self.port.to_bytes(2, 'big')

    @classmethod
    def decode(cls, data: bytes | memoryview) -> BIPAddress:
        host = f"{data[0]}.{data[1]}.{data[2]}.{data[3]}"
        port = int.from_bytes(data[4:6], 'big')
        return cls(host=host, port=port)
```

### 2.4 BVLL Codec

```python
def encode_bvll(function: BvlcFunction, payload: bytes,
                originating_address: BIPAddress | None = None) -> bytes:
    """Encode a complete BVLL message."""
    if function == BvlcFunction.FORWARDED_NPDU:
        assert originating_address is not None
        content = originating_address.encode() + payload
    else:
        content = payload
    length = BVLL_HEADER_LENGTH + len(content)
    header = bytes([BVLC_TYPE_BACNET_IP, function, length >> 8, length & 0xFF])
    return header + content


def decode_bvll(data: memoryview) -> BvllMessage:
    """Decode a BVLL message from raw UDP datagram."""
    if data[0] != BVLC_TYPE_BACNET_IP:
        raise ValueError(f"Invalid BVLC type: {data[0]:#x}")
    function = BvlcFunction(data[1])
    length = (data[2] << 8) | data[3]
    if function == BvlcFunction.FORWARDED_NPDU:
        orig_addr = BIPAddress.decode(data[4:10])
        return BvllMessage(function=function, data=bytes(data[10:length]),
                          originating_address=orig_addr)
    return BvllMessage(function=function, data=bytes(data[4:length]))
```

## 3. BACnet/IP Transport Implementation

### 3.1 asyncio DatagramProtocol

```python
class BIPTransport:
    """BACnet/IP transport using asyncio UDP."""

    def __init__(self, interface: str = '0.0.0.0', port: int = 0xBAC0,
                 bbmd_address: BIPAddress | None = None,
                 bbmd_ttl: int = 60):
        self._interface = interface
        self._port = port
        self._bbmd_address = bbmd_address
        self._bbmd_ttl = bbmd_ttl
        self._protocol: _UDPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._receive_callback: Callable[[bytes, BIPAddress], None] | None = None
        self._local_address: BIPAddress | None = None

    async def start(self) -> None:
        """Bind UDP socket and start listening."""
        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._on_datagram_received),
            local_addr=(self._interface, self._port),
            allow_broadcast=True,
        )
        # Discover actual bound address
        sock = self._transport.get_extra_info('socket')
        addr = sock.getsockname()
        self._local_address = BIPAddress(host=addr[0], port=addr[1])

        # If configured as foreign device, start registration
        if self._bbmd_address:
            await self._register_foreign_device()

    async def stop(self) -> None:
        """Close UDP socket and cancel background tasks."""
        if self._transport:
            self._transport.close()

    def send_unicast(self, npdu: bytes, destination: BIPAddress) -> None:
        """Send a directed message (Original-Unicast-NPDU).

        Synchronous: transport.sendto() is non-blocking, no await needed.
        """
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        self._transport.sendto(bvll, (destination.host, destination.port))

    def send_broadcast(self, npdu: bytes) -> None:
        """Send a local broadcast (Original-Broadcast-NPDU).

        Synchronous: transport.sendto() is non-blocking, no await needed.
        """
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        broadcast_addr = self._get_broadcast_address()
        self._transport.sendto(bvll, (broadcast_addr, self._port))

    def send_distribute_broadcast(self, npdu: bytes) -> None:
        """Send via BBMD (Distribute-Broadcast-To-Network) for foreign devices.

        Synchronous: transport.sendto() is non-blocking, no await needed.
        """
        if not self._bbmd_address:
            raise RuntimeError("Not registered as a foreign device")
        bvll = encode_bvll(BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK, npdu)
        self._transport.sendto(bvll, (self._bbmd_address.host, self._bbmd_address.port))

    def _on_datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process incoming UDP datagram."""
        try:
            msg = decode_bvll(memoryview(data))
        except ValueError:
            return  # Silently drop malformed BVLL

        source = BIPAddress(host=addr[0], port=addr[1])

        match msg.function:
            case BvlcFunction.ORIGINAL_UNICAST_NPDU | BvlcFunction.ORIGINAL_BROADCAST_NPDU:
                if self._receive_callback:
                    self._receive_callback(msg.data, source)
            case BvlcFunction.FORWARDED_NPDU:
                # Use originating address as source
                if self._receive_callback and msg.originating_address:
                    self._receive_callback(msg.data, msg.originating_address)
            case BvlcFunction.BVLC_RESULT:
                self._handle_bvlc_result(msg.data)
            case _:
                pass  # BBMD management messages handled separately

    @property
    def local_address(self) -> BIPAddress:
        assert self._local_address is not None
        return self._local_address

    @property
    def max_npdu_length(self) -> int:
        return 1497  # Per Table 6-1


class _UDPProtocol(asyncio.DatagramProtocol):
    """Low-level asyncio DatagramProtocol wrapper."""

    def __init__(self, callback: Callable[[bytes, tuple[str, int]], None]):
        self._callback = callback

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        pass  # Log and continue
```

### 3.2 Foreign Device Registration

```python
class ForeignDeviceManager:
    """Manages periodic re-registration with a BBMD."""

    def __init__(self, transport: BIPTransport, bbmd_address: BIPAddress,
                 ttl: int = 60):
        self._transport = transport
        self._bbmd_address = bbmd_address
        self._ttl = ttl
        self._task: asyncio.Task | None = None
        self._registered = asyncio.Event()

    async def start(self) -> None:
        """Register and start re-registration loop."""
        self._task = asyncio.create_task(self._registration_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _registration_loop(self) -> None:
        """Re-register at TTL/2 intervals."""
        while True:
            payload = self._ttl.to_bytes(2, 'big')
            bvll = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, payload)
            self._transport._transport.sendto(
                bvll, (self._bbmd_address.host, self._bbmd_address.port)
            )
            # Re-register at half the TTL to avoid expiry
            await asyncio.sleep(self._ttl / 2)
```

### 3.3 BBMD Support

For server applications that need to act as a BBMD:

```python
@dataclass(frozen=True, slots=True)
class BDTEntry:
    """Broadcast Distribution Table entry."""
    address: BIPAddress
    broadcast_mask: bytes  # 4 octets


@dataclass(frozen=True, slots=True)
class FDTEntry:
    """Foreign Device Table entry (Clause J.5.2.1)."""
    address: BIPAddress
    ttl: int               # Time-to-Live supplied at registration
    remaining: float       # Seconds remaining before purge

# Per Clause J.5.2.3, the BBMD adds a 30-second grace period to the TTL
FDT_GRACE_PERIOD_SECONDS = 30


class BBMDManager:
    """BACnet/IP Broadcast Management Device functionality."""

    def __init__(self, transport: BIPTransport):
        self._transport = transport
        self._bdt: list[BDTEntry] = []
        self._fdt: dict[BIPAddress, FDTEntry] = {}
        self._fdt_cleanup_task: asyncio.Task | None = None

    async def handle_original_broadcast(self, npdu: bytes,
                                        source: BIPAddress) -> None:
        """Forward broadcast to all BDT peers and foreign devices."""
        forwarded = encode_bvll(
            BvlcFunction.FORWARDED_NPDU, npdu,
            originating_address=source,
        )
        # Forward to each BDT peer (except self)
        for entry in self._bdt:
            if entry.address != self._transport.local_address:
                dest = self._compute_forward_address(entry)
                self._transport._transport.sendto(
                    forwarded, (dest.host, dest.port)
                )
        # Forward to each registered foreign device
        for fd in self._fdt.values():
            self._transport._transport.sendto(
                forwarded, (fd.address.host, fd.address.port)
            )

    def _compute_forward_address(self, entry: BDTEntry) -> BIPAddress:
        """Compute forwarding address from BDT entry and mask.

        If mask is all 1s = unicast to BBMD (two-hop).
        Otherwise = directed broadcast (one-hop).
        """
        ip_bytes = bytes(int(x) for x in entry.address.host.split('.'))
        mask = entry.broadcast_mask
        inv_mask = bytes(~b & 0xFF for b in mask)
        dest_ip = bytes(a | b for a, b in zip(ip_bytes, inv_mask))
        host = '.'.join(str(b) for b in dest_ip)
        return BIPAddress(host=host, port=entry.address.port)
```

## 4. Network Layer (Clause 6)

### 4.1 NPDU Structure

The Network Protocol Data Unit provides routing information between BACnet networks:

```
┌──────────┬─────────────┬──────┬──────┬──────┬──────┬──────┬──────┬───────────┬──────┬────────────┐
│ Version  │ Control     │ DNET │ DLEN │ DADR │ SNET │ SLEN │ SADR │ Hop Count │ Msg  │ APDU/      │
│ (1 byte) │ (1 byte)    │(2 b) │(1 b) │(var) │(2 b) │(1 b) │(var) │ (1 byte)  │ Type │ Msg Data   │
└──────────┴─────────────┴──────┴──────┴──────┴──────┴──────┴──────┴───────────┴──────┴────────────┘
```

Control octet bits (Clause 6.2.2):

- Bit 7: 1 = network layer message, 0 = APDU follows
- Bit 6: Reserved — shall be zero
- Bit 5: 1 = DNET/DLEN/Hop Count present
- Bit 4: Reserved — shall be zero
- Bit 3: 1 = SNET/SLEN/SADR present
- Bit 2: 1 = data expecting reply
- Bits 1,0: Network priority (0=Normal, 1=Urgent, 2=Critical, 3=Life Safety)

Network number constraints (Clause 6.2.2.1):
- DNET: 1-65535 (0xFFFF = global broadcast)
- SNET: 1-65534 (0xFFFF is NOT valid as a source)
- SLEN: must be > 0 when source is present (SLEN=0 is invalid per spec)

### 4.2 NPDU Data Structures

```python
class NetworkPriority(IntEnum):
    NORMAL = 0
    URGENT = 1
    CRITICAL_EQUIPMENT = 2
    LIFE_SAFETY = 3


class NetworkMessageType(IntEnum):
    WHO_IS_ROUTER_TO_NETWORK = 0x00
    I_AM_ROUTER_TO_NETWORK = 0x01
    I_COULD_BE_ROUTER_TO_NETWORK = 0x02
    REJECT_MESSAGE_TO_NETWORK = 0x03
    ROUTER_BUSY_TO_NETWORK = 0x04
    ROUTER_AVAILABLE_TO_NETWORK = 0x05
    INITIALIZE_ROUTING_TABLE = 0x06
    INITIALIZE_ROUTING_TABLE_ACK = 0x07
    ESTABLISH_CONNECTION_TO_NETWORK = 0x08
    DISCONNECT_CONNECTION_TO_NETWORK = 0x09
    CHALLENGE_REQUEST = 0x0A
    SECURITY_PAYLOAD = 0x0B
    SECURITY_RESPONSE = 0x0C
    REQUEST_KEY_UPDATE = 0x0D
    UPDATE_KEY_SET = 0x0E
    UPDATE_DISTRIBUTION_KEY = 0x0F
    REQUEST_MASTER_KEY = 0x10
    SET_MASTER_KEY = 0x11
    WHAT_IS_NETWORK_NUMBER = 0x12
    NETWORK_NUMBER_IS = 0x13


@dataclass(frozen=True, slots=True)
class BACnetAddress:
    """A full BACnet address: optional network number + MAC address."""
    network: int | None = None     # None = local network
    mac_address: bytes = b''       # MAC address (length depends on data link)

    @property
    def is_local(self) -> bool:
        return self.network is None

    @property
    def is_broadcast(self) -> bool:
        return self.network == 0xFFFF or len(self.mac_address) == 0

    @property
    def is_global_broadcast(self) -> bool:
        return self.network == 0xFFFF


# Convenience constructors
LOCAL_BROADCAST = BACnetAddress()
GLOBAL_BROADCAST = BACnetAddress(network=0xFFFF)

def remote_broadcast(network: int) -> BACnetAddress:
    return BACnetAddress(network=network, mac_address=b'')

def remote_station(network: int, mac: bytes) -> BACnetAddress:
    return BACnetAddress(network=network, mac_address=mac)


@dataclass(frozen=True, slots=True)
class NPDU:
    """Decoded Network Protocol Data Unit."""
    version: int = 1
    is_network_message: bool = False
    expecting_reply: bool = False
    priority: NetworkPriority = NetworkPriority.NORMAL
    destination: BACnetAddress | None = None   # None = local only
    source: BACnetAddress | None = None        # None = from local device
    hop_count: int = 255
    message_type: NetworkMessageType | None = None  # For network layer messages
    apdu: bytes = b''                          # For application layer messages
    network_message_data: bytes = b''          # For network layer messages
```

### 4.3 NPDU Codec

```python
BACNET_PROTOCOL_VERSION = 1

def encode_npdu(npdu: NPDU) -> bytes:
    """Encode an NPDU to bytes."""
    buf = bytearray()
    buf.append(BACNET_PROTOCOL_VERSION)

    # Build control octet (bits 6 and 4 are reserved, always zero)
    control = 0
    if npdu.is_network_message:
        control |= 0x80
    if npdu.destination is not None:
        control |= 0x20
    if npdu.source is not None:
        control |= 0x08
    if npdu.expecting_reply:
        control |= 0x04
    control |= npdu.priority & 0x03
    buf.append(control)

    # Destination (if present)
    if npdu.destination is not None:
        dnet = npdu.destination.network if npdu.destination.network is not None else 0xFFFF
        buf.extend(dnet.to_bytes(2, 'big'))
        dlen = len(npdu.destination.mac_address)
        buf.append(dlen)
        if dlen > 0:
            buf.extend(npdu.destination.mac_address)

    # Source (if present) — validate per Clause 6.2.2.1
    if npdu.source is not None:
        snet = npdu.source.network or 0
        if snet == 0xFFFF:
            raise ValueError("SNET cannot be 0xFFFF (global broadcast is not a valid source)")
        if snet == 0:
            raise ValueError("SNET cannot be 0 (must be 1-65534)")
        slen = len(npdu.source.mac_address)
        if slen == 0:
            raise ValueError("SLEN cannot be 0 when source is present")
        buf.extend(snet.to_bytes(2, 'big'))
        buf.append(slen)
        buf.extend(npdu.source.mac_address)

    # Hop count (only if destination present)
    if npdu.destination is not None:
        buf.append(npdu.hop_count)

    # Message type or APDU
    if npdu.is_network_message:
        buf.append(npdu.message_type or 0)
        buf.extend(npdu.network_message_data)
    else:
        buf.extend(npdu.apdu)

    return bytes(buf)


def decode_npdu(data: memoryview) -> NPDU:
    """Decode an NPDU from bytes."""
    offset = 0
    version = data[offset]; offset += 1
    control = data[offset]; offset += 1

    is_network_message = bool(control & 0x80)
    has_destination = bool(control & 0x20)
    has_source = bool(control & 0x08)
    expecting_reply = bool(control & 0x04)
    priority = NetworkPriority(control & 0x03)

    destination = None
    source = None
    hop_count = 255

    if has_destination:
        dnet = int.from_bytes(data[offset:offset+2], 'big'); offset += 2
        dlen = data[offset]; offset += 1
        dadr = bytes(data[offset:offset+dlen]); offset += dlen
        destination = BACnetAddress(network=dnet, mac_address=dadr)

    if has_source:
        snet = int.from_bytes(data[offset:offset+2], 'big'); offset += 2
        slen = data[offset]; offset += 1
        sadr = bytes(data[offset:offset+slen]); offset += slen
        source = BACnetAddress(network=snet, mac_address=sadr)

    if has_destination:
        hop_count = data[offset]; offset += 1

    message_type = None
    network_message_data = b''
    apdu = b''

    if is_network_message:
        message_type = NetworkMessageType(data[offset]); offset += 1
        network_message_data = bytes(data[offset:])
    else:
        apdu = bytes(data[offset:])

    return NPDU(
        version=version,
        is_network_message=is_network_message,
        expecting_reply=expecting_reply,
        priority=priority,
        destination=destination,
        source=source,
        hop_count=hop_count,
        message_type=message_type,
        apdu=apdu,
        network_message_data=network_message_data,
    )
```

### 4.4 Network Layer Manager

```python
class NetworkLayer:
    """Manages NPDU encoding/decoding and address translation.

    Sits between the transport layer and the application layer.
    """

    def __init__(self, transport: BIPTransport,
                 network_number: int | None = None):
        self._transport = transport
        self._network_number = network_number
        self._receive_callback: Callable[[bytes, BACnetAddress], None] | None = None

    def on_receive(self, callback: Callable[[bytes, BACnetAddress], None]) -> None:
        """Register callback for received APDUs."""
        self._receive_callback = callback

    async def send(self, apdu: bytes, destination: BACnetAddress,
                   expecting_reply: bool = False,
                   priority: NetworkPriority = NetworkPriority.NORMAL) -> None:
        """Send an APDU to a destination address."""
        npdu = NPDU(
            expecting_reply=expecting_reply,
            priority=priority,
            destination=destination if not destination.is_local else None,
            apdu=apdu,
        )
        npdu_bytes = encode_npdu(npdu)

        if destination.is_global_broadcast or destination.is_broadcast:
            await self._transport.send_broadcast(npdu_bytes)
        else:
            bip_addr = self._resolve_address(destination)
            await self._transport.send_unicast(npdu_bytes, bip_addr)

    def _handle_received(self, data: bytes, source_bip: BIPAddress) -> None:
        """Handle received NPDU from transport layer."""
        npdu = decode_npdu(memoryview(data))

        if npdu.is_network_message:
            self._handle_network_message(npdu, source_bip)
            return

        # Build source BACnet address
        if npdu.source is not None:
            source_addr = npdu.source
        else:
            source_addr = BACnetAddress(
                network=self._network_number,
                mac_address=source_bip.encode(),
            )

        if self._receive_callback:
            self._receive_callback(npdu.apdu, source_addr)

    def _resolve_address(self, address: BACnetAddress) -> BIPAddress:
        """Resolve a BACnet address to a B/IP address for sending."""
        if address.is_local or address.network == self._network_number:
            # Local - MAC address IS the B/IP address
            return BIPAddress.decode(address.mac_address)
        # Remote - would need router table lookup
        # For now, raise an error for remote networks
        raise NotImplementedError("Routing to remote networks not yet supported")

    def _handle_network_message(self, npdu: NPDU, source: BIPAddress) -> None:
        """Handle network layer protocol messages (e.g., Who-Is-Router)."""
        # Initial implementation can log and ignore
        pass
```

## 5. Address Model Summary

| Context                | Address Type                   | Size     |
| ---------------------- | ------------------------------ | -------- |
| BACnet/IP MAC          | BIPAddress (IP:port)           | 6 octets |
| Ethernet MAC           | EthernetAddress                | 6 octets |
| MS/TP MAC              | int (station number)           | 1 octet  |
| BACnet Network Address | BACnetAddress (network + MAC)  | Variable |
| Global Broadcast       | BACnetAddress(network=0xFFFF)  | -        |
| Local Broadcast        | BACnetAddress(mac_address=b'') | -        |

## 6. Future: Ethernet Transport

The transport abstraction allows a future `EthernetTransport` implementing the same interface:

```python
class EthernetTransport:
    """BACnet over Ethernet (ISO 8802-3) using raw sockets."""

    async def send_unicast(self, npdu: bytes, destination: EthernetAddress) -> None: ...
    async def send_broadcast(self, npdu: bytes) -> None: ...
    # Uses LLC Type 1 with DSAP/SSAP = 0x82 and BACnet LSAP
```

This shares the same `NetworkLayer` since the NPDU format is transport-agnostic. The only difference is address encoding/decoding per Table 6-2 in the spec.

## 7. Performance Considerations

- **Zero-copy receives**: `datagram_received` passes raw bytes. BVLL and NPDU decoding work on `memoryview` slices to avoid copies.
- **No allocation on hot path**: Tag decoding and NPDU parsing return lightweight frozen dataclasses or named tuples.
- **Broadcast efficiency**: For servers on a single subnet (no BBMD), broadcasts go directly to the subnet broadcast address - no intermediary processing.
- **Socket options**: `SO_REUSEADDR` and `SO_BROADCAST` are set for proper BACnet/IP operation. On Linux, `SO_REUSEPORT` can be used for multiple processes sharing the BACnet port.
