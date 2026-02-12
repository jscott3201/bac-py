"""Tests for BACnet/IP IPv4 multicast support (Annex J.8)."""

from unittest.mock import MagicMock

import pytest

from bac_py.transport.bip import BIPTransport


class TestMulticastConstruction:
    def test_multicast_disabled_by_default(self):
        transport = BIPTransport()
        assert transport._multicast_enabled is False

    def test_multicast_enabled(self):
        transport = BIPTransport(multicast_enabled=True)
        assert transport._multicast_enabled is True

    def test_default_multicast_address(self):
        transport = BIPTransport(multicast_enabled=True)
        assert transport._multicast_address == "239.255.186.192"

    def test_custom_multicast_address(self):
        transport = BIPTransport(
            multicast_enabled=True,
            multicast_address="239.255.186.193",
        )
        assert transport._multicast_address == "239.255.186.193"

    def test_default_multicast_ttl(self):
        transport = BIPTransport(multicast_enabled=True)
        assert transport._multicast_ttl == 32

    def test_custom_multicast_ttl(self):
        transport = BIPTransport(multicast_enabled=True, multicast_ttl=64)
        assert transport._multicast_ttl == 64


class TestMulticastBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_multicast_and_directed(self):
        transport = BIPTransport(
            interface="127.0.0.1",
            port=0,
            broadcast_address="255.255.255.255",
            multicast_enabled=True,
        )
        await transport.start()
        try:
            mock_transport = MagicMock()
            transport._transport = mock_transport

            npdu = b"\x01\x00\x10"
            transport.send_broadcast(npdu)

            # Should send to both multicast and directed broadcast
            assert mock_transport.sendto.call_count == 2

            calls = mock_transport.sendto.call_args_list
            addrs = [call[0][1] for call in calls]
            multicast_addr = ("239.255.186.192", transport._port)
            broadcast_addr = ("255.255.255.255", transport._port)
            assert multicast_addr in addrs
            assert broadcast_addr in addrs
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_broadcast_without_multicast_sends_only_directed(self):
        transport = BIPTransport(
            interface="127.0.0.1",
            port=0,
            broadcast_address="255.255.255.255",
        )
        await transport.start()
        try:
            mock_transport = MagicMock()
            transport._transport = mock_transport

            transport.send_broadcast(b"\x01\x00\x10")

            assert mock_transport.sendto.call_count == 1
            _, sent_addr = mock_transport.sendto.call_args[0]
            assert sent_addr == ("255.255.255.255", transport._port)
        finally:
            await transport.stop()


class TestMulticastStartStop:
    @pytest.mark.asyncio
    async def test_start_with_multicast(self):
        transport = BIPTransport(
            interface="127.0.0.1",
            port=0,
            multicast_enabled=True,
        )
        await transport.start()
        try:
            assert transport._transport is not None
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_stop_with_multicast(self):
        transport = BIPTransport(
            interface="127.0.0.1",
            port=0,
            multicast_enabled=True,
        )
        await transport.start()
        await transport.stop()
        assert transport._transport is None


class TestMulticastConfig:
    def test_multicast_params_stored(self):
        transport = BIPTransport(
            multicast_enabled=True,
            multicast_address="239.0.0.1",
            multicast_ttl=16,
        )
        assert transport._multicast_enabled is True
        assert transport._multicast_address == "239.0.0.1"
        assert transport._multicast_ttl == 16
