"""Foreign device registration manager for BACnet/IPv6 per Annex U.

Provides ForeignDevice6Manager for registering with a remote IPv6 BBMD,
periodic re-registration, and broadcast distribution via the BBMD.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from bac_py.transport.bvll_ipv6 import encode_bvll6
from bac_py.types.enums import Bvlc6Function, Bvlc6ResultCode

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.network.address import BIP6Address

logger = logging.getLogger(__name__)


class ForeignDevice6Manager:
    r"""Manages registration with a remote IPv6 BBMD per Annex U.

    A BACnet/IPv6 device on a different subnet registers with a BBMD
    as a "foreign device" to receive broadcast traffic.  This manager
    handles:

    - Initial registration with the BBMD
    - Periodic re-registration at TTL/2 intervals to prevent expiry
    - Tracking registration state (registered, failed)
    - Sending broadcasts via Distribute-Broadcast-NPDU

    Usage::

        fd_mgr = ForeignDevice6Manager(
            bbmd_address=BIP6Address("fd00::1", 47808),
            ttl=60,
            send_callback=transport_send,
            local_vmac=b"\x01\x02\x03",
        )
        await fd_mgr.start()
        # ...later...
        await fd_mgr.stop()
    """

    def __init__(
        self,
        bbmd_address: BIP6Address,
        ttl: int,
        send_callback: Callable[[bytes, BIP6Address], None],
        local_vmac: bytes,
        local_address: BIP6Address | None = None,
    ) -> None:
        """Initialize IPv6 foreign device manager.

        :param bbmd_address: B/IPv6 address of the BBMD to register with.
        :param ttl: Time-to-Live in seconds for registration.
        :param send_callback: Called with ``(raw_bytes, destination)`` to send
            a UDP datagram.
        :param local_vmac: 3-byte VMAC for source_vmac in all BVLL6 messages.
        :param local_address: This device's B/IPv6 address.  Required for
            sending deregistration on stop.
        """
        self._bbmd_address = bbmd_address
        if ttl < 1:
            msg = f"TTL must be >= 1 second, got {ttl}"
            raise ValueError(msg)
        self._ttl = ttl
        self._send = send_callback
        self._local_vmac = local_vmac
        self._local_address = local_address
        self._task: asyncio.Task[None] | None = None
        self._registered = asyncio.Event()
        self._last_result: Bvlc6ResultCode | None = None
        # Pre-compute registration BVLL6 (payload is always the same)
        self._registration_bvll = encode_bvll6(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            self._ttl.to_bytes(2, "big"),
            source_vmac=self._local_vmac,
        )

    @property
    def bbmd_address(self) -> BIP6Address:
        """The BBMD address this device is registered with."""
        return self._bbmd_address

    @property
    def ttl(self) -> int:
        """The registration TTL in seconds."""
        return self._ttl

    @property
    def is_registered(self) -> bool:
        """Whether the device is currently registered with the BBMD."""
        return self._registered.is_set()

    @property
    def last_result(self) -> Bvlc6ResultCode | None:
        """The last BVLC6-Result code received from the BBMD."""
        return self._last_result

    async def start(self) -> None:
        """Start the registration loop.

        Sends an initial registration and begins periodic
        re-registration at TTL/2 intervals.
        """
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._registration_loop())

    async def stop(self) -> None:
        """Stop the registration loop and deregister from the BBMD.

        If the device is currently registered and a local address was
        provided, sends a Delete-Foreign-Device-Table-Entry to the
        BBMD so it can immediately remove the FDT entry.
        """
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._registered.is_set():
            self._send_deregistration()
            self._registered.clear()

    def handle_bvlc_result(self, data: bytes) -> None:
        """Process a BVLC6-Result received from the BBMD.

        :param data: 2-octet result code payload.
        """
        if len(data) < 2:
            return

        result_code = Bvlc6ResultCode(int.from_bytes(data[0:2], "big"))
        self._last_result = result_code

        if result_code == Bvlc6ResultCode.SUCCESSFUL_COMPLETION:
            if not self._registered.is_set():
                logger.info(
                    "Registered as IPv6 foreign device with BBMD [%s]:%d (TTL=%ds)",
                    self._bbmd_address.host,
                    self._bbmd_address.port,
                    self._ttl,
                )
            self._registered.set()
        else:
            logger.warning(
                "IPv6 foreign device registration NAK from BBMD [%s]:%d: %s",
                self._bbmd_address.host,
                self._bbmd_address.port,
                result_code.name,
            )
            self._registered.clear()

    def send_distribute_broadcast(self, npdu: bytes) -> None:
        """Send a broadcast via the BBMD using Distribute-Broadcast-NPDU.

        This is used by foreign devices instead of multicast broadcast.
        The BBMD will distribute the NPDU to all BDT peers and other
        registered foreign devices.

        :param npdu: NPDU bytes to broadcast.
        :raises RuntimeError: If not registered with a BBMD.
        """
        if not self._registered.is_set():
            msg = "Not registered as an IPv6 foreign device"
            raise RuntimeError(msg)
        bvll = encode_bvll6(
            Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU, npdu, source_vmac=self._local_vmac
        )
        self._send(bvll, self._bbmd_address)

    def _send_registration(self) -> None:
        """Send a Register-Foreign-Device message to the BBMD."""
        self._send(self._registration_bvll, self._bbmd_address)
        logger.debug(
            "Sent Register-Foreign-Device to [%s]:%d (TTL=%ds)",
            self._bbmd_address.host,
            self._bbmd_address.port,
            self._ttl,
        )

    def _send_deregistration(self) -> None:
        """Send a Delete-Foreign-Device-Table-Entry for this device."""
        if self._local_address is None:
            return
        payload = self._local_address.encode()
        bvll = encode_bvll6(
            Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            payload,
            source_vmac=self._local_vmac,
        )
        self._send(bvll, self._bbmd_address)
        logger.info(
            "Sent Delete-Foreign-Device-Table-Entry to [%s]:%d",
            self._bbmd_address.host,
            self._bbmd_address.port,
        )

    async def _registration_loop(self) -> None:
        """Re-register at TTL/2 intervals per Annex U."""
        while True:
            try:
                self._send_registration()
            except OSError:
                logger.warning("Failed to send IPv6 foreign device registration", exc_info=True)
            await asyncio.sleep(self._ttl / 2)
