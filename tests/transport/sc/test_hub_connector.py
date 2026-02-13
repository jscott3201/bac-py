import asyncio

import pytest

from bac_py.transport.sc.bvlc import SCMessage
from bac_py.transport.sc.hub_connector import SCHubConnector, SCHubConnectorConfig
from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.types import BvlcSCFunction, SCHubConnectionStatus
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


class TestHubConnectorConnect:
    async def test_connect_to_primary_hub(self):
        hub, port = await _start_hub()
        try:
            connector = SCHubConnector(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCHubConnectorConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                ),
            )
            await connector.start()
            connected = await connector.wait_connected(timeout=5)
            assert connected
            assert connector.is_connected
            assert connector.connection_status == SCHubConnectionStatus.CONNECTED_TO_PRIMARY
            await connector.stop()
        finally:
            await hub.stop()

    async def test_send_message_when_connected(self):
        hub, port = await _start_hub()
        try:
            connector = SCHubConnector(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCHubConnectorConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                ),
            )
            await connector.start()
            await connector.wait_connected(timeout=5)

            # Sending should not raise
            msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=1,
                payload=b"\x01\x02",
            )
            await connector.send(msg)

            await connector.stop()
        finally:
            await hub.stop()

    async def test_send_when_not_connected_raises(self):
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        msg = SCMessage(BvlcSCFunction.ENCAPSULATED_NPDU, message_id=1)
        with pytest.raises(ConnectionError, match="not connected"):
            await connector.send(msg)


class TestHubConnectorFailover:
    async def test_failover_when_primary_unavailable(self):
        # Don't start a primary hub — it's unreachable
        failover_hub, failover_port = await _start_hub()
        try:
            connector = SCHubConnector(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCHubConnectorConfig(
                    primary_hub_uri="ws://127.0.0.1:19999",  # Unreachable
                    failover_hub_uri=f"ws://127.0.0.1:{failover_port}",
                    tls_config=_plaintext_tls(),
                    min_reconnect_time=0.1,
                ),
            )
            await connector.start()
            connected = await connector.wait_connected(timeout=10)
            assert connected
            assert connector.connection_status == SCHubConnectionStatus.CONNECTED_TO_FAILOVER
            await connector.stop()
        finally:
            await failover_hub.stop()


class TestHubConnectorReconnect:
    async def test_reconnect_after_hub_stops(self):
        hub, port = await _start_hub()
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConnectorConfig(
                primary_hub_uri=f"ws://127.0.0.1:{port}",
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
            ),
        )
        await connector.start()
        connected = await connector.wait_connected(timeout=5)
        assert connected
        assert connector.connection_status == SCHubConnectionStatus.CONNECTED_TO_PRIMARY

        # Kill the hub — connector should detect disconnection
        await hub.stop()
        await asyncio.sleep(0.5)
        assert not connector.is_connected

        # Start a new hub on the same port
        hub2, _ = await _start_hub(bind_port=port)
        try:
            connected = await connector.wait_connected(timeout=10)
            assert connected
            assert connector.connection_status == SCHubConnectionStatus.CONNECTED_TO_PRIMARY
            await connector.stop()
        finally:
            await hub2.stop()

    async def test_backoff_increases(self):
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConnectorConfig(
                primary_hub_uri="ws://127.0.0.1:19999",  # Unreachable
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
                max_reconnect_time=1.0,
            ),
        )
        assert connector._reconnect_delay == 0.1
        connector._increase_backoff()
        assert connector._reconnect_delay == 0.2
        connector._increase_backoff()
        assert connector._reconnect_delay == 0.4
        connector._increase_backoff()
        assert connector._reconnect_delay == 0.8
        connector._increase_backoff()
        assert connector._reconnect_delay == 1.0  # Capped at max
        connector._reset_backoff()
        assert connector._reconnect_delay == 0.1


class TestHubConnectorLifecycle:
    async def test_stop_when_not_started(self):
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        await connector.stop()  # Should not raise

    async def test_stop_while_connecting(self):
        """Stop cancels the connect loop cleanly."""
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConnectorConfig(
                primary_hub_uri="ws://127.0.0.1:19999",  # Unreachable
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
            ),
        )
        await connector.start()
        await asyncio.sleep(0.3)
        await connector.stop()
        assert not connector.is_connected
        assert connector.connection_status == SCHubConnectionStatus.NO_HUB_CONNECTION

    async def test_status_change_callback(self):
        hub, port = await _start_hub()
        try:
            statuses: list[SCHubConnectionStatus] = []
            connector = SCHubConnector(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCHubConnectorConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                ),
            )
            connector.on_status_change = statuses.append
            await connector.start()
            await connector.wait_connected(timeout=5)

            assert SCHubConnectionStatus.CONNECTED_TO_PRIMARY in statuses

            await connector.stop()
            assert SCHubConnectionStatus.NO_HUB_CONNECTION in statuses
        finally:
            await hub.stop()

    async def test_local_vmac_setter(self):
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        new_vmac = SCVMAC.random()
        connector.local_vmac = new_vmac
        assert connector.local_vmac == new_vmac

    async def test_wait_connected_timeout(self):
        connector = SCHubConnector(
            SCVMAC.random(),
            DeviceUUID.generate(),
        )
        result = await connector.wait_connected(timeout=0.1)
        assert result is False

    async def test_message_callback(self):
        hub, port = await _start_hub()
        try:
            received: list[SCMessage] = []

            async def on_msg(msg: SCMessage) -> None:
                received.append(msg)

            connector = SCHubConnector(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCHubConnectorConfig(
                    primary_hub_uri=f"ws://127.0.0.1:{port}",
                    tls_config=_plaintext_tls(),
                ),
            )
            connector.on_message = on_msg
            await connector.start()
            await connector.wait_connected(timeout=5)
            assert connector.is_connected

            await connector.stop()
        finally:
            await hub.stop()
