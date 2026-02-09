"""Tests for network layer message encoding and decoding."""

import pytest

from bac_py.network.messages import (
    DisconnectConnectionToNetwork,
    EstablishConnectionToNetwork,
    IAmRouterToNetwork,
    ICouldBeRouterToNetwork,
    InitializeRoutingTable,
    InitializeRoutingTableAck,
    NetworkNumberIs,
    RejectMessageToNetwork,
    RouterAvailableToNetwork,
    RouterBusyToNetwork,
    RoutingTablePort,
    WhatIsNetworkNumber,
    WhoIsRouterToNetwork,
    decode_network_message,
    encode_network_message,
)
from bac_py.types.enums import NetworkMessageType, RejectMessageReason

# ---------------------------------------------------------------------------
# Who-Is-Router-To-Network
# ---------------------------------------------------------------------------


class TestWhoIsRouterToNetwork:
    def test_encode_no_network(self) -> None:
        msg = WhoIsRouterToNetwork()
        assert encode_network_message(msg) == b""

    def test_encode_with_network(self) -> None:
        msg = WhoIsRouterToNetwork(network=5)
        assert encode_network_message(msg) == b"\x00\x05"

    def test_encode_high_network(self) -> None:
        msg = WhoIsRouterToNetwork(network=0xFFFE)
        assert encode_network_message(msg) == b"\xff\xfe"

    def test_decode_no_network(self) -> None:
        msg = decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, b"")
        assert isinstance(msg, WhoIsRouterToNetwork)
        assert msg.network is None

    def test_decode_with_network(self) -> None:
        msg = decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, b"\x00\x0a")
        assert isinstance(msg, WhoIsRouterToNetwork)
        assert msg.network == 10

    def test_roundtrip_no_network(self) -> None:
        original = WhoIsRouterToNetwork()
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, encoded)
        assert decoded == original

    def test_roundtrip_with_network(self) -> None:
        original = WhoIsRouterToNetwork(network=1000)
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, encoded)
        assert decoded == original

    def test_decode_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, b"\x00")


# ---------------------------------------------------------------------------
# I-Am-Router-To-Network
# ---------------------------------------------------------------------------


class TestIAmRouterToNetwork:
    def test_encode_single_network(self) -> None:
        msg = IAmRouterToNetwork(networks=(1,))
        assert encode_network_message(msg) == b"\x00\x01"

    def test_encode_multiple_networks(self) -> None:
        msg = IAmRouterToNetwork(networks=(1, 2, 3))
        assert encode_network_message(msg) == b"\x00\x01\x00\x02\x00\x03"

    def test_encode_empty_networks(self) -> None:
        msg = IAmRouterToNetwork(networks=())
        assert encode_network_message(msg) == b""

    def test_decode_single_network(self) -> None:
        msg = decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, b"\x00\x05")
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == (5,)

    def test_decode_multiple_networks(self) -> None:
        data = b"\x00\x01\x00\x02\x00\x03"
        msg = decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == (1, 2, 3)

    def test_decode_empty(self) -> None:
        msg = decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, b"")
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == ()

    def test_roundtrip(self) -> None:
        original = IAmRouterToNetwork(networks=(10, 20, 30, 40))
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, encoded)
        assert decoded == original

    def test_decode_odd_length_raises(self) -> None:
        with pytest.raises(ValueError, match="multiple of 2"):
            decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, b"\x00\x01\x00")


# ---------------------------------------------------------------------------
# I-Could-Be-Router-To-Network
# ---------------------------------------------------------------------------


class TestICouldBeRouterToNetwork:
    def test_encode(self) -> None:
        msg = ICouldBeRouterToNetwork(network=5, performance_index=10)
        assert encode_network_message(msg) == b"\x00\x05\x0a"

    def test_encode_max_performance(self) -> None:
        msg = ICouldBeRouterToNetwork(network=100, performance_index=255)
        encoded = encode_network_message(msg)
        assert encoded == b"\x00\x64\xff"

    def test_decode(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK, b"\x00\x05\x0a"
        )
        assert isinstance(msg, ICouldBeRouterToNetwork)
        assert msg.network == 5
        assert msg.performance_index == 10

    def test_roundtrip(self) -> None:
        original = ICouldBeRouterToNetwork(network=200, performance_index=50)
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK, encoded)
        assert decoded == original

    def test_decode_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK, b"\x00\x05")


# ---------------------------------------------------------------------------
# Reject-Message-To-Network
# ---------------------------------------------------------------------------


class TestRejectMessageToNetwork:
    def test_encode_not_directly_connected(self) -> None:
        msg = RejectMessageToNetwork(reason=RejectMessageReason.NOT_DIRECTLY_CONNECTED, network=10)
        assert encode_network_message(msg) == b"\x01\x00\x0a"

    def test_encode_router_busy(self) -> None:
        msg = RejectMessageToNetwork(reason=RejectMessageReason.ROUTER_BUSY, network=20)
        assert encode_network_message(msg) == b"\x02\x00\x14"

    def test_encode_message_too_long(self) -> None:
        msg = RejectMessageToNetwork(reason=RejectMessageReason.MESSAGE_TOO_LONG, network=5)
        assert encode_network_message(msg) == b"\x04\x00\x05"

    def test_decode(self) -> None:
        msg = decode_network_message(NetworkMessageType.REJECT_MESSAGE_TO_NETWORK, b"\x01\x00\x0a")
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 10

    def test_roundtrip_all_reasons(self) -> None:
        for reason in RejectMessageReason:
            original = RejectMessageToNetwork(reason=reason, network=100)
            encoded = encode_network_message(original)
            decoded = decode_network_message(NetworkMessageType.REJECT_MESSAGE_TO_NETWORK, encoded)
            assert decoded == original

    def test_decode_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.REJECT_MESSAGE_TO_NETWORK, b"\x01\x00")


# ---------------------------------------------------------------------------
# Router-Busy-To-Network
# ---------------------------------------------------------------------------


class TestRouterBusyToNetwork:
    def test_encode_specific_networks(self) -> None:
        msg = RouterBusyToNetwork(networks=(5, 10))
        assert encode_network_message(msg) == b"\x00\x05\x00\x0a"

    def test_encode_all_networks(self) -> None:
        msg = RouterBusyToNetwork(networks=())
        assert encode_network_message(msg) == b""

    def test_decode_specific_networks(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.ROUTER_BUSY_TO_NETWORK, b"\x00\x05\x00\x0a"
        )
        assert isinstance(msg, RouterBusyToNetwork)
        assert msg.networks == (5, 10)

    def test_decode_all_networks(self) -> None:
        msg = decode_network_message(NetworkMessageType.ROUTER_BUSY_TO_NETWORK, b"")
        assert isinstance(msg, RouterBusyToNetwork)
        assert msg.networks == ()

    def test_roundtrip(self) -> None:
        original = RouterBusyToNetwork(networks=(1, 2, 3))
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.ROUTER_BUSY_TO_NETWORK, encoded)
        assert decoded == original


# ---------------------------------------------------------------------------
# Router-Available-To-Network
# ---------------------------------------------------------------------------


class TestRouterAvailableToNetwork:
    def test_encode_specific_networks(self) -> None:
        msg = RouterAvailableToNetwork(networks=(5, 10))
        assert encode_network_message(msg) == b"\x00\x05\x00\x0a"

    def test_encode_all_networks(self) -> None:
        msg = RouterAvailableToNetwork(networks=())
        assert encode_network_message(msg) == b""

    def test_decode_specific_networks(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK, b"\x00\x05\x00\x0a"
        )
        assert isinstance(msg, RouterAvailableToNetwork)
        assert msg.networks == (5, 10)

    def test_decode_all_networks(self) -> None:
        msg = decode_network_message(NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK, b"")
        assert isinstance(msg, RouterAvailableToNetwork)
        assert msg.networks == ()

    def test_roundtrip(self) -> None:
        original = RouterAvailableToNetwork(networks=(100, 200))
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK, encoded)
        assert decoded == original


# ---------------------------------------------------------------------------
# Initialize-Routing-Table
# ---------------------------------------------------------------------------


class TestInitializeRoutingTable:
    def test_encode_query(self) -> None:
        """Number of Ports = 0 means query without modification."""
        msg = InitializeRoutingTable(ports=())
        assert encode_network_message(msg) == b"\x00"

    def test_encode_single_port(self) -> None:
        msg = InitializeRoutingTable(ports=(RoutingTablePort(network=5, port_id=1, port_info=b""),))
        # 01 (num ports) 00 05 (net) 01 (port_id) 00 (info_len)
        assert encode_network_message(msg) == b"\x01\x00\x05\x01\x00"

    def test_encode_port_with_info(self) -> None:
        msg = InitializeRoutingTable(
            ports=(RoutingTablePort(network=10, port_id=2, port_info=b"\xab\xcd"),)
        )
        # 01 (num) 00 0a (net) 02 (pid) 02 (info_len) ab cd (info)
        assert encode_network_message(msg) == b"\x01\x00\x0a\x02\x02\xab\xcd"

    def test_encode_multiple_ports(self) -> None:
        msg = InitializeRoutingTable(
            ports=(
                RoutingTablePort(network=1, port_id=1, port_info=b""),
                RoutingTablePort(network=2, port_id=2, port_info=b"\xff"),
            )
        )
        expected = b"\x02\x00\x01\x01\x00\x00\x02\x02\x01\xff"
        assert encode_network_message(msg) == expected

    def test_decode_query(self) -> None:
        msg = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, b"\x00")
        assert isinstance(msg, InitializeRoutingTable)
        assert msg.ports == ()

    def test_decode_single_port(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.INITIALIZE_ROUTING_TABLE, b"\x01\x00\x05\x01\x00"
        )
        assert isinstance(msg, InitializeRoutingTable)
        assert len(msg.ports) == 1
        assert msg.ports[0].network == 5
        assert msg.ports[0].port_id == 1
        assert msg.ports[0].port_info == b""

    def test_decode_port_with_info(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.INITIALIZE_ROUTING_TABLE, b"\x01\x00\x0a\x02\x02\xab\xcd"
        )
        assert isinstance(msg, InitializeRoutingTable)
        assert len(msg.ports) == 1
        assert msg.ports[0].network == 10
        assert msg.ports[0].port_id == 2
        assert msg.ports[0].port_info == b"\xab\xcd"

    def test_roundtrip_query(self) -> None:
        original = InitializeRoutingTable(ports=())
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, encoded)
        assert decoded == original

    def test_roundtrip_multiple_ports(self) -> None:
        original = InitializeRoutingTable(
            ports=(
                RoutingTablePort(network=5, port_id=1, port_info=b""),
                RoutingTablePort(network=10, port_id=2, port_info=b"\x01\x02\x03"),
                RoutingTablePort(network=20, port_id=3, port_info=b"\xff"),
            )
        )
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, encoded)
        assert decoded == original

    def test_decode_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, b"")

    def test_decode_truncated_port_raises(self) -> None:
        # Says 1 port but only has 2 bytes of network number
        with pytest.raises(ValueError, match="truncated"):
            decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, b"\x01\x00\x05")

    def test_decode_truncated_port_info_raises(self) -> None:
        # Says port_info_len is 3 but only has 1 byte
        with pytest.raises(ValueError, match="truncated"):
            decode_network_message(
                NetworkMessageType.INITIALIZE_ROUTING_TABLE, b"\x01\x00\x05\x01\x03\xab"
            )

    def test_port_id_zero_purge(self) -> None:
        """Port ID = 0 means purge entries for this DNET (Clause 6.4.7)."""
        msg = InitializeRoutingTable(ports=(RoutingTablePort(network=5, port_id=0, port_info=b""),))
        encoded = encode_network_message(msg)
        decoded = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, encoded)
        assert decoded.ports[0].port_id == 0


# ---------------------------------------------------------------------------
# Initialize-Routing-Table-Ack
# ---------------------------------------------------------------------------


class TestInitializeRoutingTableAck:
    def test_encode_empty_ack(self) -> None:
        """Acknowledging an update: no data."""
        msg = InitializeRoutingTableAck(ports=())
        assert encode_network_message(msg) == b"\x00"

    def test_encode_with_table_data(self) -> None:
        msg = InitializeRoutingTableAck(
            ports=(RoutingTablePort(network=5, port_id=1, port_info=b""),)
        )
        assert encode_network_message(msg) == b"\x01\x00\x05\x01\x00"

    def test_decode_empty_ack(self) -> None:
        msg = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK, b"\x00")
        assert isinstance(msg, InitializeRoutingTableAck)
        assert msg.ports == ()

    def test_roundtrip(self) -> None:
        original = InitializeRoutingTableAck(
            ports=(
                RoutingTablePort(network=1, port_id=1, port_info=b""),
                RoutingTablePort(network=2, port_id=2, port_info=b"\xaa\xbb"),
            )
        )
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK, encoded)
        assert decoded == original


# ---------------------------------------------------------------------------
# Establish-Connection-To-Network
# ---------------------------------------------------------------------------


class TestEstablishConnectionToNetwork:
    def test_encode(self) -> None:
        msg = EstablishConnectionToNetwork(network=5, termination_time=60)
        assert encode_network_message(msg) == b"\x00\x05\x3c"

    def test_encode_permanent(self) -> None:
        """Termination time 0 = permanent connection."""
        msg = EstablishConnectionToNetwork(network=10, termination_time=0)
        assert encode_network_message(msg) == b"\x00\x0a\x00"

    def test_decode(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK, b"\x00\x05\x3c"
        )
        assert isinstance(msg, EstablishConnectionToNetwork)
        assert msg.network == 5
        assert msg.termination_time == 60

    def test_roundtrip(self) -> None:
        original = EstablishConnectionToNetwork(network=100, termination_time=120)
        encoded = encode_network_message(original)
        decoded = decode_network_message(
            NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK, encoded
        )
        assert decoded == original

    def test_decode_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK, b"\x00\x05")


# ---------------------------------------------------------------------------
# Disconnect-Connection-To-Network
# ---------------------------------------------------------------------------


class TestDisconnectConnectionToNetwork:
    def test_encode(self) -> None:
        msg = DisconnectConnectionToNetwork(network=5)
        assert encode_network_message(msg) == b"\x00\x05"

    def test_decode(self) -> None:
        msg = decode_network_message(
            NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK, b"\x00\x0a"
        )
        assert isinstance(msg, DisconnectConnectionToNetwork)
        assert msg.network == 10

    def test_roundtrip(self) -> None:
        original = DisconnectConnectionToNetwork(network=500)
        encoded = encode_network_message(original)
        decoded = decode_network_message(
            NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK, encoded
        )
        assert decoded == original

    def test_decode_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK, b"\x00")


# ---------------------------------------------------------------------------
# What-Is-Network-Number
# ---------------------------------------------------------------------------


class TestWhatIsNetworkNumber:
    def test_encode(self) -> None:
        msg = WhatIsNetworkNumber()
        assert encode_network_message(msg) == b""

    def test_decode(self) -> None:
        msg = decode_network_message(NetworkMessageType.WHAT_IS_NETWORK_NUMBER, b"")
        assert isinstance(msg, WhatIsNetworkNumber)

    def test_roundtrip(self) -> None:
        original = WhatIsNetworkNumber()
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.WHAT_IS_NETWORK_NUMBER, encoded)
        assert decoded == original


# ---------------------------------------------------------------------------
# Network-Number-Is
# ---------------------------------------------------------------------------


class TestNetworkNumberIs:
    def test_encode_configured(self) -> None:
        msg = NetworkNumberIs(network=5, configured=True)
        assert encode_network_message(msg) == b"\x00\x05\x01"

    def test_encode_learned(self) -> None:
        msg = NetworkNumberIs(network=10, configured=False)
        assert encode_network_message(msg) == b"\x00\x0a\x00"

    def test_decode_configured(self) -> None:
        msg = decode_network_message(NetworkMessageType.NETWORK_NUMBER_IS, b"\x00\x05\x01")
        assert isinstance(msg, NetworkNumberIs)
        assert msg.network == 5
        assert msg.configured is True

    def test_decode_learned(self) -> None:
        msg = decode_network_message(NetworkMessageType.NETWORK_NUMBER_IS, b"\x00\x0a\x00")
        assert isinstance(msg, NetworkNumberIs)
        assert msg.network == 10
        assert msg.configured is False

    def test_roundtrip_configured(self) -> None:
        original = NetworkNumberIs(network=1000, configured=True)
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.NETWORK_NUMBER_IS, encoded)
        assert decoded == original

    def test_roundtrip_learned(self) -> None:
        original = NetworkNumberIs(network=2000, configured=False)
        encoded = encode_network_message(original)
        decoded = decode_network_message(NetworkMessageType.NETWORK_NUMBER_IS, encoded)
        assert decoded == original

    def test_decode_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            decode_network_message(NetworkMessageType.NETWORK_NUMBER_IS, b"\x00\x05")


# ---------------------------------------------------------------------------
# Unsupported message type
# ---------------------------------------------------------------------------


class TestUnsupportedMessageType:
    def test_decode_security_payload_raises(self) -> None:
        """Security messages (0x0A-0x11) are not supported by this module."""
        with pytest.raises(ValueError, match="Unsupported"):
            decode_network_message(NetworkMessageType.SECURITY_PAYLOAD, b"")

    def test_decode_vendor_proprietary_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            decode_network_message(0x80, b"")

    def test_encode_unknown_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unknown"):
            encode_network_message("not a message")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Wire-format integration with NPDU
# ---------------------------------------------------------------------------


class TestNpduIntegration:
    """Test that network messages integrate properly with the NPDU codec."""

    def test_who_is_router_via_npdu(self) -> None:
        from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu

        msg = WhoIsRouterToNetwork(network=5)
        msg_data = encode_network_message(msg)
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
            network_message_data=msg_data,
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.is_network_message is True
        assert decoded.message_type == NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK
        result = decode_network_message(decoded.message_type, decoded.network_message_data)
        assert isinstance(result, WhoIsRouterToNetwork)
        assert result.network == 5

    def test_i_am_router_via_npdu(self) -> None:
        from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu

        msg = IAmRouterToNetwork(networks=(1, 2, 3))
        msg_data = encode_network_message(msg)
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.I_AM_ROUTER_TO_NETWORK,
            network_message_data=msg_data,
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        result = decode_network_message(decoded.message_type, decoded.network_message_data)
        assert isinstance(result, IAmRouterToNetwork)
        assert result.networks == (1, 2, 3)

    def test_reject_message_via_npdu(self) -> None:
        from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu

        msg = RejectMessageToNetwork(reason=RejectMessageReason.NOT_DIRECTLY_CONNECTED, network=10)
        msg_data = encode_network_message(msg)
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
            network_message_data=msg_data,
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        result = decode_network_message(decoded.message_type, decoded.network_message_data)
        assert isinstance(result, RejectMessageToNetwork)
        assert result.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert result.network == 10

    def test_init_routing_table_query_via_npdu(self) -> None:
        from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu

        msg = InitializeRoutingTable(ports=())
        msg_data = encode_network_message(msg)
        npdu = NPDU(
            is_network_message=True,
            expecting_reply=True,
            message_type=NetworkMessageType.INITIALIZE_ROUTING_TABLE,
            network_message_data=msg_data,
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.expecting_reply is True
        result = decode_network_message(decoded.message_type, decoded.network_message_data)
        assert isinstance(result, InitializeRoutingTable)
        assert result.ports == ()

    def test_network_number_is_via_npdu(self) -> None:
        from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu

        msg = NetworkNumberIs(network=42, configured=True)
        msg_data = encode_network_message(msg)
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.NETWORK_NUMBER_IS,
            network_message_data=msg_data,
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        result = decode_network_message(decoded.message_type, decoded.network_message_data)
        assert isinstance(result, NetworkNumberIs)
        assert result.network == 42
        assert result.configured is True


# ---------------------------------------------------------------------------
# Edge cases and boundary values
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_max_network_number(self) -> None:
        """Network number 0xFFFE is the maximum valid value for SNET."""
        msg = WhoIsRouterToNetwork(network=0xFFFE)
        encoded = encode_network_message(msg)
        decoded = decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, encoded)
        assert decoded.network == 0xFFFE

    def test_network_number_one(self) -> None:
        """Network number 1 is the minimum valid value."""
        msg = IAmRouterToNetwork(networks=(1,))
        encoded = encode_network_message(msg)
        decoded = decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, encoded)
        assert decoded.networks == (1,)

    def test_large_network_list(self) -> None:
        """Test with many networks in a single message."""
        networks = tuple(range(1, 101))
        msg = IAmRouterToNetwork(networks=networks)
        encoded = encode_network_message(msg)
        decoded = decode_network_message(NetworkMessageType.I_AM_ROUTER_TO_NETWORK, encoded)
        assert decoded.networks == networks
        assert len(encoded) == 200  # 100 networks * 2 bytes each

    def test_routing_table_max_port_info(self) -> None:
        """Port info can be up to 255 bytes."""
        port_info = bytes(range(255))
        msg = InitializeRoutingTable(
            ports=(RoutingTablePort(network=1, port_id=1, port_info=port_info),)
        )
        encoded = encode_network_message(msg)
        decoded = decode_network_message(NetworkMessageType.INITIALIZE_ROUTING_TABLE, encoded)
        assert decoded.ports[0].port_info == port_info

    def test_performance_index_zero(self) -> None:
        """Performance index 0 = best possible performance."""
        msg = ICouldBeRouterToNetwork(network=5, performance_index=0)
        encoded = encode_network_message(msg)
        decoded = decode_network_message(NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK, encoded)
        assert decoded.performance_index == 0

    def test_termination_time_max(self) -> None:
        """Termination time 255 is the maximum 1-byte value."""
        msg = EstablishConnectionToNetwork(network=1, termination_time=255)
        encoded = encode_network_message(msg)
        decoded = decode_network_message(
            NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK, encoded
        )
        assert decoded.termination_time == 255

    def test_decode_with_memoryview(self) -> None:
        """Ensure decoding works with memoryview inputs."""
        data = memoryview(b"\x00\x05")
        msg = decode_network_message(NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK, data)
        assert isinstance(msg, WhoIsRouterToNetwork)
        assert msg.network == 5

    def test_frozen_dataclass(self) -> None:
        """Network message dataclasses are frozen."""
        msg = WhoIsRouterToNetwork(network=5)
        with pytest.raises(AttributeError):
            msg.network = 10  # type: ignore[misc]

    def test_routing_table_port_frozen(self) -> None:
        """RoutingTablePort is frozen."""
        port = RoutingTablePort(network=1, port_id=1)
        with pytest.raises(AttributeError):
            port.network = 2  # type: ignore[misc]
