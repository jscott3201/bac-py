"""Network layer message encoding and decoding per ASHRAE 135-2024 Clause 6.4.

This module handles the variable-length data payloads of router-related
network layer messages. The NPDU envelope (version, control, addresses,
hop count, message type) is handled by npdu.py; this module handles
only the data that follows the message type byte.
"""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.types.enums import NetworkMessageType, RejectMessageReason

# ---------------------------------------------------------------------------
# Message dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WhoIsRouterToNetwork:
    """Clause 6.4.1 -- request routing info for a specific or all networks.

    If network is None, the request is for all reachable networks.
    """

    network: int | None = None


@dataclass(frozen=True, slots=True)
class IAmRouterToNetwork:
    """Clause 6.4.2 -- list of reachable DNETs."""

    networks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ICouldBeRouterToNetwork:
    """Clause 6.4.3 -- half-router advertisement.

    Performance index: lower value = higher performance.
    """

    network: int
    performance_index: int


@dataclass(frozen=True, slots=True)
class RejectMessageToNetwork:
    """Clause 6.4.4 -- routing rejection with reason code."""

    reason: RejectMessageReason
    network: int


@dataclass(frozen=True, slots=True)
class RouterBusyToNetwork:
    """Clause 6.4.5 -- congestion control, impose.

    Empty networks list means all networks served by the router.
    """

    networks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RouterAvailableToNetwork:
    """Clause 6.4.6 -- congestion control, lift.

    Empty networks list means all previously curtailed networks.
    """

    networks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RoutingTablePort:
    """A single port entry within an Initialize-Routing-Table message (Figure 6-11)."""

    network: int
    port_id: int
    port_info: bytes = b""


@dataclass(frozen=True, slots=True)
class InitializeRoutingTable:
    """Clause 6.4.7 -- routing table initialization or query.

    Empty ports list (Number of Ports = 0) is a query requesting
    the complete routing table without modification.
    """

    ports: tuple[RoutingTablePort, ...]


@dataclass(frozen=True, slots=True)
class InitializeRoutingTableAck:
    """Clause 6.4.8 -- routing table initialization response.

    Contains routing table data when responding to a query.
    Empty ports list when acknowledging an update.
    """

    ports: tuple[RoutingTablePort, ...]


@dataclass(frozen=True, slots=True)
class EstablishConnectionToNetwork:
    """Clause 6.4.9 -- instruct half-router to establish PTP connection.

    Termination time of 0 means the connection is permanent.
    """

    network: int
    termination_time: int


@dataclass(frozen=True, slots=True)
class DisconnectConnectionToNetwork:
    """Clause 6.4.10 -- instruct half-router to disconnect PTP connection."""

    network: int


@dataclass(frozen=True, slots=True)
class WhatIsNetworkNumber:
    """Clause 6.4.19 -- request local network number. No payload."""

    pass


@dataclass(frozen=True, slots=True)
class NetworkNumberIs:
    """Clause 6.4.20 -- announce local network number.

    configured=True means the number was manually configured.
    configured=False means it was learned from another device.
    """

    network: int
    configured: bool


# Union type for all network messages handled by this module.
NetworkMessage = (
    WhoIsRouterToNetwork
    | IAmRouterToNetwork
    | ICouldBeRouterToNetwork
    | RejectMessageToNetwork
    | RouterBusyToNetwork
    | RouterAvailableToNetwork
    | InitializeRoutingTable
    | InitializeRoutingTableAck
    | EstablishConnectionToNetwork
    | DisconnectConnectionToNetwork
    | WhatIsNetworkNumber
    | NetworkNumberIs
)


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def encode_network_message(msg: NetworkMessage) -> bytes:
    """Encode the data payload of a network layer message.

    This encodes only the variable-length data that follows the message
    type byte in the NPDU. The caller is responsible for constructing
    the full NPDU with the correct message type.

    Some message types (e.g. ``WhatIsNetworkNumber``) have no payload,
    so this function returns ``b""``.

    See :func:`decode_network_message` for the inverse operation.

    :param msg: A network message dataclass instance.
    :returns: Encoded data bytes (may be empty for some message types).
    :raises TypeError: If the message type is not recognized.
    """
    if isinstance(msg, WhoIsRouterToNetwork):
        return _encode_who_is_router(msg)
    if isinstance(msg, IAmRouterToNetwork):
        return _encode_network_list(msg.networks)
    if isinstance(msg, ICouldBeRouterToNetwork):
        return _encode_i_could_be_router(msg)
    if isinstance(msg, RejectMessageToNetwork):
        return _encode_reject_message(msg)
    if isinstance(msg, RouterBusyToNetwork):
        return _encode_network_list(msg.networks)
    if isinstance(msg, RouterAvailableToNetwork):
        return _encode_network_list(msg.networks)
    if isinstance(msg, InitializeRoutingTable):
        return _encode_routing_table(msg.ports)
    if isinstance(msg, InitializeRoutingTableAck):
        return _encode_routing_table(msg.ports)
    if isinstance(msg, EstablishConnectionToNetwork):
        return _encode_establish_connection(msg)
    if isinstance(msg, DisconnectConnectionToNetwork):
        return msg.network.to_bytes(2, "big")
    if isinstance(msg, WhatIsNetworkNumber):
        return b""
    if isinstance(msg, NetworkNumberIs):
        return _encode_network_number_is(msg)
    msg_text = f"Unknown network message type: {type(msg).__name__}"
    raise TypeError(msg_text)


def _encode_who_is_router(msg: WhoIsRouterToNetwork) -> bytes:
    """Encode Who-Is-Router payload: 2-byte DNET or empty if querying all."""
    if msg.network is None:
        return b""
    return msg.network.to_bytes(2, "big")


def _encode_network_list(networks: tuple[int, ...]) -> bytes:
    """Encode a sequence of 2-byte big-endian network numbers."""
    buf = bytearray()
    for net in networks:
        buf.extend(net.to_bytes(2, "big"))
    return bytes(buf)


def _encode_i_could_be_router(msg: ICouldBeRouterToNetwork) -> bytes:
    """Encode I-Could-Be-Router payload: 2-byte DNET + 1-byte performance index."""
    buf = bytearray()
    buf.extend(msg.network.to_bytes(2, "big"))
    buf.append(msg.performance_index & 0xFF)
    return bytes(buf)


def _encode_reject_message(msg: RejectMessageToNetwork) -> bytes:
    """Encode Reject-Message payload: 1-byte reason + 2-byte DNET."""
    buf = bytearray()
    buf.append(int(msg.reason) & 0xFF)
    buf.extend(msg.network.to_bytes(2, "big"))
    return bytes(buf)


def _encode_routing_table(ports: tuple[RoutingTablePort, ...]) -> bytes:
    """Encode a routing table per Figure 6-11: count + repeated port entries."""
    buf = bytearray()
    buf.append(len(ports))
    for port in ports:
        buf.extend(port.network.to_bytes(2, "big"))
        buf.append(port.port_id & 0xFF)
        buf.append(len(port.port_info) & 0xFF)
        buf.extend(port.port_info)
    return bytes(buf)


def _encode_establish_connection(msg: EstablishConnectionToNetwork) -> bytes:
    """Encode Establish-Connection payload: 2-byte DNET + 1-byte termination time."""
    buf = bytearray()
    buf.extend(msg.network.to_bytes(2, "big"))
    buf.append(msg.termination_time & 0xFF)
    return bytes(buf)


def _encode_network_number_is(msg: NetworkNumberIs) -> bytes:
    """Encode Network-Number-Is payload: 2-byte network + 1-byte configured flag."""
    buf = bytearray()
    buf.extend(msg.network.to_bytes(2, "big"))
    buf.append(1 if msg.configured else 0)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def decode_network_message(message_type: int, data: bytes | memoryview) -> NetworkMessage:
    """Decode the data payload of a network layer message.

    See :func:`encode_network_message` for the inverse operation.

    :param message_type: The :class:`~bac_py.types.enums.NetworkMessageType`
        value from the NPDU.
    :param data: The raw data bytes following the message type byte
        (may be empty for message types with no payload).
    :returns: A decoded network message dataclass instance.
    :raises ValueError: If the message type is not supported or data is
        malformed.
    """
    if isinstance(data, memoryview):
        data = bytes(data)

    mt = message_type

    if mt == NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK:
        return _decode_who_is_router(data)
    if mt == NetworkMessageType.I_AM_ROUTER_TO_NETWORK:
        return IAmRouterToNetwork(networks=_decode_network_list(data))
    if mt == NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK:
        return _decode_i_could_be_router(data)
    if mt == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK:
        return _decode_reject_message(data)
    if mt == NetworkMessageType.ROUTER_BUSY_TO_NETWORK:
        return RouterBusyToNetwork(networks=_decode_network_list(data))
    if mt == NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK:
        return RouterAvailableToNetwork(networks=_decode_network_list(data))
    if mt == NetworkMessageType.INITIALIZE_ROUTING_TABLE:
        return InitializeRoutingTable(ports=_decode_routing_table(data))
    if mt == NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK:
        return InitializeRoutingTableAck(ports=_decode_routing_table(data))
    if mt == NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK:
        return _decode_establish_connection(data)
    if mt == NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK:
        return _decode_disconnect_connection(data)
    if mt == NetworkMessageType.WHAT_IS_NETWORK_NUMBER:
        return WhatIsNetworkNumber()
    if mt == NetworkMessageType.NETWORK_NUMBER_IS:
        return _decode_network_number_is(data)

    msg = f"Unsupported network message type: 0x{mt:02X}"
    raise ValueError(msg)


def _decode_who_is_router(data: bytes) -> WhoIsRouterToNetwork:
    """Decode Who-Is-Router payload: empty means all networks, otherwise 2-byte DNET."""
    if len(data) == 0:
        return WhoIsRouterToNetwork(network=None)
    if len(data) < 2:
        msg = "Who-Is-Router-To-Network data too short"
        raise ValueError(msg)
    network = int.from_bytes(data[:2], "big")
    return WhoIsRouterToNetwork(network=network)


def _decode_network_list(data: bytes) -> tuple[int, ...]:
    """Decode a sequence of 2-byte big-endian network numbers."""
    if len(data) % 2 != 0:
        msg = "Network list data length must be a multiple of 2"
        raise ValueError(msg)
    networks = []
    for i in range(0, len(data), 2):
        networks.append(int.from_bytes(data[i : i + 2], "big"))
    return tuple(networks)


def _decode_i_could_be_router(data: bytes) -> ICouldBeRouterToNetwork:
    """Decode I-Could-Be-Router payload: 2-byte DNET + 1-byte performance index."""
    if len(data) < 3:
        msg = "I-Could-Be-Router-To-Network data too short"
        raise ValueError(msg)
    network = int.from_bytes(data[:2], "big")
    performance_index = data[2]
    return ICouldBeRouterToNetwork(network=network, performance_index=performance_index)


def _decode_reject_message(data: bytes) -> RejectMessageToNetwork:
    """Decode Reject-Message payload: 1-byte reason + 2-byte DNET."""
    if len(data) < 3:
        msg = "Reject-Message-To-Network data too short"
        raise ValueError(msg)
    reason = RejectMessageReason(data[0])
    network = int.from_bytes(data[1:3], "big")
    return RejectMessageToNetwork(reason=reason, network=network)


def _decode_routing_table(data: bytes) -> tuple[RoutingTablePort, ...]:
    """Decode a routing table per Figure 6-11: count + repeated port entries."""
    if len(data) < 1:
        msg = "Routing table data too short"
        raise ValueError(msg)
    num_ports = data[0]
    offset = 1
    ports: list[RoutingTablePort] = []
    for _ in range(num_ports):
        if offset + 4 > len(data):
            msg = "Routing table data truncated"
            raise ValueError(msg)
        network = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        port_id = data[offset]
        offset += 1
        port_info_len = data[offset]
        offset += 1
        if offset + port_info_len > len(data):
            msg = "Routing table port info data truncated"
            raise ValueError(msg)
        port_info = data[offset : offset + port_info_len]
        offset += port_info_len
        ports.append(RoutingTablePort(network=network, port_id=port_id, port_info=port_info))
    return tuple(ports)


def _decode_establish_connection(data: bytes) -> EstablishConnectionToNetwork:
    """Decode Establish-Connection payload: 2-byte DNET + 1-byte termination time."""
    if len(data) < 3:
        msg = "Establish-Connection-To-Network data too short"
        raise ValueError(msg)
    network = int.from_bytes(data[:2], "big")
    termination_time = data[2]
    return EstablishConnectionToNetwork(network=network, termination_time=termination_time)


def _decode_disconnect_connection(data: bytes) -> DisconnectConnectionToNetwork:
    """Decode Disconnect-Connection payload: 2-byte DNET."""
    if len(data) < 2:
        msg = "Disconnect-Connection-To-Network data too short"
        raise ValueError(msg)
    network = int.from_bytes(data[:2], "big")
    return DisconnectConnectionToNetwork(network=network)


def _decode_network_number_is(data: bytes) -> NetworkNumberIs:
    """Decode Network-Number-Is payload: 2-byte network + 1-byte configured flag."""
    if len(data) < 3:
        msg = "Network-Number-Is data too short"
        raise ValueError(msg)
    network = int.from_bytes(data[:2], "big")
    configured = data[2] != 0
    return NetworkNumberIs(network=network, configured=configured)
