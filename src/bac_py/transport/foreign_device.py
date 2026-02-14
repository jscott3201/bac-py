"""Foreign device registration manager per Annex J.5-J.6.

Provides ForeignDeviceManager for registering with a remote BBMD,
periodic re-registration, and broadcast distribution via the BBMD.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from bac_py.transport.bvll import encode_bvll
from bac_py.types.enums import BvlcFunction, BvlcResultCode

if TYPE_CHECKING:
    from collections.abc import Callable

    from bac_py.network.address import BIPAddress

logger = logging.getLogger(__name__)


class ForeignDeviceManager:
    """Manages registration with a remote BBMD per Annex J.5-J.6.

    A BACnet/IP device on a different subnet registers with a BBMD
    as a "foreign device" to receive broadcast traffic. This manager
    handles:

    - Initial registration with the BBMD
    - Periodic re-registration at TTL/2 intervals to prevent expiry
    - Tracking registration state (registered, failed)
    - Sending broadcasts via Distribute-Broadcast-To-Network

    Usage::

        fd_mgr = ForeignDeviceManager(
            bbmd_address=BIPAddress("192.168.1.1", 47808),
            ttl=60,
            send_callback=transport_send,
        )
        await fd_mgr.start()
        # ...later...
        await fd_mgr.stop()
    """

    def __init__(
        self,
        bbmd_address: BIPAddress,
        ttl: int,
        send_callback: Callable[[bytes, BIPAddress], None],
        local_address: BIPAddress | None = None,
    ) -> None:
        """Initialize foreign device manager.

        :param bbmd_address: B/IP address of the BBMD to register with.
        :param ttl: Time-to-Live in seconds for registration. The device
            will re-register at TTL/2 intervals.
        :param send_callback: Called with ``(raw_bytes, destination)`` to send
            a UDP datagram.
        :param local_address: This device's B/IP address. Required for
            sending deregistration on stop. If ``None``, no
            deregistration message is sent on stop.
        """
        self._bbmd_address = bbmd_address
        if ttl < 1:
            msg = f"TTL must be >= 1 second, got {ttl}"
            raise ValueError(msg)
        self._ttl = ttl
        self._send = send_callback
        self._local_address = local_address
        self._task: asyncio.Task[None] | None = None
        self._registered = asyncio.Event()
        self._last_result: BvlcResultCode | None = None
        # Pre-compute registration BVLL (payload is always the same)
        self._registration_bvll = encode_bvll(
            BvlcFunction.REGISTER_FOREIGN_DEVICE, self._ttl.to_bytes(2, "big")
        )

    @property
    def bbmd_address(self) -> BIPAddress:
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
    def last_result(self) -> BvlcResultCode | None:
        """The last BVLC-Result code received from the BBMD."""
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
        BBMD so it can immediately remove the FDT entry rather than
        waiting for TTL + grace period expiry.
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
        """Process a BVLC-Result received from the BBMD.

        Should be called when a BVLC-Result is received from the
        BBMD address after a registration attempt.

        :param data: 2-octet result code payload.
        """
        if len(data) < 2:
            return

        result_code = BvlcResultCode(int.from_bytes(data[0:2], "big"))
        self._last_result = result_code

        if result_code == BvlcResultCode.SUCCESSFUL_COMPLETION:
            if not self._registered.is_set():
                logger.info(
                    "Registered as foreign device with BBMD %s:%d (TTL=%ds)",
                    self._bbmd_address.host,
                    self._bbmd_address.port,
                    self._ttl,
                )
            self._registered.set()
        else:
            logger.warning(
                "Foreign device registration NAK from BBMD %s:%d: %s",
                self._bbmd_address.host,
                self._bbmd_address.port,
                result_code.name,
            )
            self._registered.clear()

    def send_distribute_broadcast(self, npdu: bytes) -> None:
        """Send a broadcast via the BBMD using Distribute-Broadcast-To-Network.

        This is used by foreign devices instead of local broadcast.
        The BBMD will distribute the NPDU to all BDT peers and other
        registered foreign devices.

        :param npdu: NPDU bytes to broadcast.
        :raises RuntimeError: If not registered with a BBMD.
        """
        if not self._registered.is_set():
            msg = "Not registered as a foreign device"
            raise RuntimeError(msg)
        bvll = encode_bvll(BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK, npdu)
        self._send(bvll, self._bbmd_address)

    def _send_registration(self) -> None:
        """Send a Register-Foreign-Device message to the BBMD."""
        self._send(self._registration_bvll, self._bbmd_address)
        logger.debug(
            "Sent Register-Foreign-Device to %s:%d (TTL=%ds)",
            self._bbmd_address.host,
            self._bbmd_address.port,
            self._ttl,
        )

    def _send_deregistration(self) -> None:
        """Send a Delete-Foreign-Device-Table-Entry for this device.

        Per the BACnet specification, sending a delete for the
        device's own address allows the BBMD to immediately remove
        the FDT entry rather than waiting for TTL + grace period.
        """
        if self._local_address is None:
            return
        payload = self._local_address.encode()
        bvll = encode_bvll(BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY, payload)
        self._send(bvll, self._bbmd_address)
        logger.info(
            "Sent Delete-Foreign-Device-Table-Entry to %s:%d",
            self._bbmd_address.host,
            self._bbmd_address.port,
        )

    async def _registration_loop(self) -> None:
        """Re-register at TTL/2 intervals per Annex J.5.2.3."""
        while True:
            try:
                self._send_registration()
            except OSError:
                logger.warning("Failed to send foreign device registration", exc_info=True)
            # Re-register at half the TTL to avoid expiry
            await asyncio.sleep(self._ttl / 2)
