import asyncio
import logging

from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
from bac_py.transport.sc.node_switch import SCNodeSwitchConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID


def _plaintext_tls() -> SCTLSConfig:
    return SCTLSConfig(allow_plaintext=True)


async def _start_hub(bind_port: int = 0) -> tuple[SCHubFunction, int]:
    """Start a hub on loopback, return (hub, port)."""
    hub = SCHubFunction(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCHubConfig(
            bind_address="127.0.0.1",
            bind_port=bind_port,
            tls_config=_plaintext_tls(),
        ),
    )
    await hub.start()
    port = hub._server.sockets[0].getsockname()[1]
    return hub, port


class TestSCTransportConfig:
    async def test_default_config(self):
        config = SCTransportConfig()
        assert config.primary_hub_uri == ""
        assert config.failover_hub_uri is None
        assert config.max_npdu_length == 1497
        assert config.max_bvlc_length == 1600

    async def test_auto_generated_vmac_and_uuid(self):
        transport = SCTransport(SCTransportConfig())
        assert len(transport.local_mac) == 6
        assert transport.max_npdu_length == 1497


class TestSCTransportLifecycle:
    async def test_start_stop_with_hub(self):
        hub, port = await _start_hub()
        try:
            transport = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            await transport.start()
            connected = await transport.hub_connector.wait_connected(timeout=5)
            assert connected
            await transport.stop()
        finally:
            await hub.stop()

    async def test_start_stop_no_hub_uri(self):
        """Transport with no hub URI just starts/stops without error."""
        transport = SCTransport(SCTransportConfig())
        await transport.start()
        await transport.stop()

    async def test_stop_when_not_started(self):
        transport = SCTransport(SCTransportConfig())
        await transport.stop()  # Should not raise


class TestSCTransportProperties:
    async def test_local_mac_is_vmac_bytes(self):
        vmac = SCVMAC.random()
        transport = SCTransport(SCTransportConfig(vmac=vmac))
        assert transport.local_mac == vmac.address

    async def test_hub_connector_property(self):
        transport = SCTransport(SCTransportConfig())
        assert transport.hub_connector is not None

    async def test_hub_function_none_by_default(self):
        transport = SCTransport(SCTransportConfig())
        assert transport.hub_function is None

    async def test_hub_function_created_when_configured(self):
        transport = SCTransport(
            SCTransportConfig(
                hub_function_config=SCHubConfig(
                    bind_address="127.0.0.1",
                    bind_port=0,
                    tls_config=_plaintext_tls(),
                ),
            )
        )
        assert transport.hub_function is not None

    async def test_node_switch_none_by_default(self):
        transport = SCTransport(SCTransportConfig())
        assert transport.node_switch is None

    async def test_node_switch_created_when_configured(self):
        transport = SCTransport(
            SCTransportConfig(
                node_switch_config=SCNodeSwitchConfig(
                    enable=True,
                    bind_address="127.0.0.1",
                    tls_config=_plaintext_tls(),
                ),
            )
        )
        assert transport.node_switch is not None


class TestSCTransportReceive:
    async def test_on_receive_callback(self):
        """NPDU received from hub triggers the registered callback."""
        hub, port = await _start_hub()
        try:
            received: list[tuple[bytes, bytes]] = []

            transport = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))
            await transport.start()
            await transport.hub_connector.wait_connected(timeout=5)

            # Simulate a message from the hub by sending to self via hub
            # We need a second connected client to send a message
            transport2 = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            await transport2.start()
            await transport2.hub_connector.wait_connected(timeout=5)

            # Send unicast from transport2 to transport1
            transport2.send_unicast(b"\x01\x02\x03", transport.local_mac)
            await asyncio.sleep(0.5)

            assert len(received) >= 1
            assert received[0][0] == b"\x01\x02\x03"

            await transport2.stop()
            await transport.stop()
        finally:
            await hub.stop()


class TestSCTransportSend:
    async def test_send_unicast_via_hub(self):
        hub, port = await _start_hub()
        try:
            received: list[tuple[bytes, bytes]] = []

            t1 = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            t2 = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            t2.on_receive(lambda npdu, mac: received.append((npdu, mac)))

            await t1.start()
            await t2.start()
            await t1.hub_connector.wait_connected(timeout=5)
            await t2.hub_connector.wait_connected(timeout=5)

            t1.send_unicast(b"\xaa\xbb\xcc", t2.local_mac)
            await asyncio.sleep(0.5)

            assert len(received) >= 1
            assert received[0][0] == b"\xaa\xbb\xcc"

            await t1.stop()
            await t2.stop()
        finally:
            await hub.stop()

    async def test_send_broadcast_via_hub(self):
        hub, port = await _start_hub()
        try:
            received: list[tuple[bytes, bytes]] = []

            t1 = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            t2 = SCTransport(
                SCTransportConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                )
            )
            t2.on_receive(lambda npdu, mac: received.append((npdu, mac)))

            await t1.start()
            await t2.start()
            await t1.hub_connector.wait_connected(timeout=5)
            await t2.hub_connector.wait_connected(timeout=5)

            t1.send_broadcast(b"\xdd\xee\xff")
            await asyncio.sleep(0.5)

            assert len(received) >= 1
            assert received[0][0] == b"\xdd\xee\xff"

            await t1.stop()
            await t2.stop()
        finally:
            await hub.stop()

    async def test_send_unicast_when_not_connected(self):
        """Unicast when not connected should not raise."""
        transport = SCTransport(SCTransportConfig())
        transport.send_unicast(b"\x01", SCVMAC.random().address)
        await asyncio.sleep(0.1)  # Let fire-and-forget complete


class TestSCTransportWithHubFunction:
    async def test_transport_as_hub_and_client(self):
        """A transport that is both a hub and connects to itself."""
        transport = SCTransport(
            SCTransportConfig(
                hub_function_config=SCHubConfig(
                    bind_address="127.0.0.1",
                    bind_port=0,
                    tls_config=_plaintext_tls(),
                ),
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
            )
        )
        await transport.start()
        assert transport.hub_function is not None
        assert transport.hub_function._server is not None

        assert transport.hub_function._server is not None
        await transport.stop()

        # Now create a transport that connects to this hub
        hub_transport = SCTransport(
            SCTransportConfig(
                hub_function_config=SCHubConfig(
                    bind_address="127.0.0.1",
                    bind_port=0,
                    tls_config=_plaintext_tls(),
                ),
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
            )
        )
        await hub_transport.start()
        hub_port = hub_transport.hub_function._server.sockets[0].getsockname()[1]

        client = SCTransport(
            SCTransportConfig(
                primary_hub_uri=f"ws://127.0.0.1:{hub_port}",
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
            )
        )
        await client.start()
        connected = await client.hub_connector.wait_connected(timeout=5)
        assert connected

        await client.stop()
        await hub_transport.stop()


class TestTransportPortProtocol:
    async def test_implements_transport_port(self):
        """SCTransport satisfies the TransportPort protocol."""
        from bac_py.transport.port import TransportPort

        transport = SCTransport(SCTransportConfig())
        assert isinstance(transport, TransportPort)


# ---------------------------------------------------------------------------
# Security: plaintext warnings on start
# ---------------------------------------------------------------------------


class TestSCTransportMemoryCleanup:
    """Verify SCTransport.stop() cleans up send tasks."""

    async def test_stop_clears_send_tasks(self):
        """stop() should cancel and clear all pending send tasks."""
        transport = SCTransport(SCTransportConfig())
        await transport.start()

        # Inject dummy send tasks
        dummy1 = asyncio.ensure_future(asyncio.sleep(999))
        dummy2 = asyncio.ensure_future(asyncio.sleep(999))
        transport._send_tasks.add(dummy1)
        transport._send_tasks.add(dummy2)
        assert len(transport._send_tasks) == 2

        await transport.stop()
        assert len(transport._send_tasks) == 0
        assert dummy1.cancelled()
        assert dummy2.cancelled()

    async def test_stop_handles_already_done_tasks(self):
        """stop() handles tasks that completed before stop."""
        transport = SCTransport(SCTransportConfig())
        await transport.start()

        # Create a task that finishes immediately
        done_task = asyncio.ensure_future(asyncio.sleep(0))
        await asyncio.sleep(0.05)  # Let it complete
        transport._send_tasks.add(done_task)

        await transport.stop()
        assert len(transport._send_tasks) == 0


class TestSCTransportPlaintextWarnings:
    async def test_start_plaintext_warns(self, caplog):
        """SCTransport.start() with allow_plaintext=True logs WARNING."""
        transport = SCTransport(SCTransportConfig(tls_config=SCTLSConfig(allow_plaintext=True)))
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc"):
            await transport.start()
            await transport.stop()
        assert any("WITHOUT TLS" in m for m in caplog.messages)

    async def test_hub_function_plaintext_warns(self, caplog):
        """Hub function start without TLS logs WARNING."""
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc"):
            await hub.start()
        assert any("WITHOUT TLS" in m for m in caplog.messages)
        await hub.stop()
