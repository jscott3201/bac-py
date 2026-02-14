import asyncio

from bac_py.transport.sc.bvlc import AddressResolutionAckPayload, SCMessage
from bac_py.transport.sc.node_switch import SCNodeSwitch, SCNodeSwitchConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.types import BvlcSCFunction
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID


def _plaintext_tls() -> SCTLSConfig:
    return SCTLSConfig(allow_plaintext=True)


def _switch_config(
    enable: bool = True,
    bind_port: int = 0,
) -> SCNodeSwitchConfig:
    return SCNodeSwitchConfig(
        enable=enable,
        bind_address="127.0.0.1",
        bind_port=bind_port,
        tls_config=_plaintext_tls(),
    )


class TestNodeSwitchLifecycle:
    async def test_start_stop(self):
        ns = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await ns.start()
        assert ns._server is not None
        await ns.stop()
        assert ns._server is None

    async def test_start_disabled(self):
        ns = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(enable=False),
        )
        await ns.start()
        assert ns._server is None
        await ns.stop()

    async def test_stop_when_not_started(self):
        ns = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        await ns.stop()  # Should not raise

    async def test_connection_count_starts_at_zero(self):
        ns = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        assert ns.connection_count == 0
        assert ns.connections == {}

    async def test_local_vmac_property(self):
        vmac = SCVMAC.random()
        ns = SCNodeSwitch(vmac, DeviceUUID.generate())
        assert ns.local_vmac == vmac
        new_vmac = SCVMAC.random()
        ns.local_vmac = new_vmac
        assert ns.local_vmac == new_vmac


class TestDirectConnectionOutbound:
    async def test_establish_direct_connection(self):
        """Initiate a direct connection to a peer node switch."""
        # Start a peer node switch listening for inbound connections
        peer_vmac = SCVMAC.random()
        peer_uuid = DeviceUUID.generate()
        peer = SCNodeSwitch(
            peer_vmac,
            peer_uuid,
            config=_switch_config(),
        )
        await peer.start()
        port = peer._server.sockets[0].getsockname()[1]

        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await local.start()

        try:
            ok = await local.establish_direct(
                peer_vmac,
                [f"ws://127.0.0.1:{port}"],
            )
            assert ok
            assert local.has_direct(peer_vmac)
            assert local.connection_count == 1
        finally:
            await local.stop()
            await peer.stop()

    async def test_establish_direct_fails_unreachable(self):
        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        ok = await local.establish_direct(
            SCVMAC.random(),
            ["ws://127.0.0.1:19999"],  # Unreachable
        )
        assert not ok

    async def test_establish_direct_tries_multiple_uris(self):
        """If the first URI fails, try the next one."""
        peer_vmac = SCVMAC.random()
        peer = SCNodeSwitch(
            peer_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await peer.start()
        port = peer._server.sockets[0].getsockname()[1]

        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        try:
            ok = await local.establish_direct(
                peer_vmac,
                [
                    "ws://127.0.0.1:19999",  # First URI unreachable
                    f"ws://127.0.0.1:{port}",  # Second URI works
                ],
            )
            assert ok
            assert local.has_direct(peer_vmac)
        finally:
            await local.stop()
            await peer.stop()


class TestDirectConnectionSend:
    async def test_send_direct(self):
        """Send a message via direct connection."""
        peer_vmac = SCVMAC.random()
        peer = SCNodeSwitch(
            peer_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        received: list[SCMessage] = []

        async def on_msg(msg: SCMessage, raw: bytes | None = None) -> None:
            received.append(msg)

        peer.on_message = on_msg
        await peer.start()
        port = peer._server.sockets[0].getsockname()[1]

        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        try:
            await local.establish_direct(peer_vmac, [f"ws://127.0.0.1:{port}"])
            msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=42,
                payload=b"\xde\xad\xbe\xef",
            )
            ok = await local.send_direct(peer_vmac, msg)
            assert ok
            await asyncio.sleep(0.3)
            assert len(received) >= 1
            assert received[0].payload == b"\xde\xad\xbe\xef"
        finally:
            await local.stop()
            await peer.stop()

    async def test_send_direct_no_connection(self):
        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        msg = SCMessage(BvlcSCFunction.ENCAPSULATED_NPDU, message_id=1)
        ok = await local.send_direct(SCVMAC.random(), msg)
        assert not ok

    async def test_has_direct_false_when_none(self):
        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        assert not local.has_direct(SCVMAC.random())


class TestDirectConnectionInbound:
    async def test_accept_inbound_connection(self):
        """A peer initiates a direct connection to our node switch."""
        local_vmac = SCVMAC.random()
        local = SCNodeSwitch(
            local_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await local.start()
        port = local._server.sockets[0].getsockname()[1]

        # Create a peer that connects to us
        peer_vmac = SCVMAC.random()
        peer = SCNodeSwitch(
            peer_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        try:
            ok = await peer.establish_direct(local_vmac, [f"ws://127.0.0.1:{port}"])
            assert ok
            await asyncio.sleep(0.3)
            # Local should now have the peer in its connection table
            assert local.connection_count == 1
            assert local.has_direct(peer_vmac)
        finally:
            await peer.stop()
            await local.stop()


class TestDirectConnectionDisconnect:
    async def test_disconnect_removes_from_table(self):
        peer_vmac = SCVMAC.random()
        peer = SCNodeSwitch(
            peer_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await peer.start()
        port = peer._server.sockets[0].getsockname()[1]

        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await local.start()
        try:
            await local.establish_direct(peer_vmac, [f"ws://127.0.0.1:{port}"])
            assert local.has_direct(peer_vmac)

            # Stop peer — connection should drop
            await peer.stop()
            await asyncio.sleep(0.5)
            assert not local.has_direct(peer_vmac)
        finally:
            await local.stop()

    async def test_stop_closes_all_direct(self):
        peer_vmac = SCVMAC.random()
        peer = SCNodeSwitch(
            peer_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await peer.start()
        port = peer._server.sockets[0].getsockname()[1]

        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await local.start()
        try:
            await local.establish_direct(peer_vmac, [f"ws://127.0.0.1:{port}"])
            assert local.connection_count == 1

            await local.stop()
            assert local.connection_count == 0
        finally:
            await peer.stop()


class TestAddressResolution:
    async def test_handle_address_resolution_ack(self):
        """Resolve pending address resolution with an ACK."""
        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        target_vmac = SCVMAC.random()

        async def fake_hub_send(msg: SCMessage) -> None:
            # Simulate the hub returning an Address-Resolution-ACK
            ack_payload = AddressResolutionAckPayload(
                ("wss://10.0.0.1:4444", "wss://10.0.0.2:4444")
            )
            ack_msg = SCMessage(
                BvlcSCFunction.ADDRESS_RESOLUTION_ACK,
                message_id=0,
                originating=target_vmac,
                payload=ack_payload.encode(),
            )
            # Deliver it asynchronously
            await asyncio.sleep(0.05)
            local.handle_address_resolution_ack(ack_msg)

        uris = await local.resolve_address(target_vmac, fake_hub_send)
        assert uris == ["wss://10.0.0.1:4444", "wss://10.0.0.2:4444"]

    async def test_resolve_timeout(self):
        """Address resolution times out when no ACK received."""
        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCNodeSwitchConfig(address_resolution_timeout=0.2),
        )

        async def fake_hub_send(msg: SCMessage) -> None:
            pass  # Never responds

        uris = await local.resolve_address(SCVMAC.random(), fake_hub_send)
        assert uris == []


class TestMaxConnections:
    async def test_max_connections_enforced_outbound(self):
        """Enforce max_connections limit."""
        local = SCNodeSwitch(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCNodeSwitchConfig(
                enable=True,
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=_plaintext_tls(),
                max_connections=1,
            ),
        )
        # Connect to first peer
        peer1_vmac = SCVMAC.random()
        peer1 = SCNodeSwitch(
            peer1_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await peer1.start()
        port1 = peer1._server.sockets[0].getsockname()[1]

        peer2_vmac = SCVMAC.random()
        peer2 = SCNodeSwitch(
            peer2_vmac,
            DeviceUUID.generate(),
            config=_switch_config(),
        )
        await peer2.start()
        port2 = peer2._server.sockets[0].getsockname()[1]

        try:
            ok1 = await local.establish_direct(peer1_vmac, [f"ws://127.0.0.1:{port1}"])
            assert ok1
            assert local.connection_count == 1

            # Second connection should be rejected
            ok2 = await local.establish_direct(peer2_vmac, [f"ws://127.0.0.1:{port2}"])
            assert not ok2
            assert local.connection_count == 1
        finally:
            await local.stop()
            await peer1.stop()
            await peer2.stop()
