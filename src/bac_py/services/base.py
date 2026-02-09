"""Service handler registration and dispatch per ASHRAE 135-2016."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bac_py.services.errors import BACnetRejectError
from bac_py.types.enums import RejectReason

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bac_py.network.address import BACnetAddress

logger = logging.getLogger(__name__)

# Service handler type aliases
type ConfirmedHandler = Callable[
    [int, bytes, BACnetAddress],  # service_choice, request_data, source
    Awaitable[bytes | None],  # response_data (None = SimpleACK)
]

type UnconfirmedHandler = Callable[
    [int, bytes, BACnetAddress],  # service_choice, request_data, source
    Awaitable[None],
]


class ServiceRegistry:
    """Registry for BACnet service request handlers.

    Maps service choice numbers to handler coroutines for both
    confirmed and unconfirmed services.
    """

    def __init__(self) -> None:
        self._confirmed: dict[int, ConfirmedHandler] = {}
        self._unconfirmed: dict[int, UnconfirmedHandler] = {}

    def register_confirmed(
        self,
        service_choice: int,
        handler: ConfirmedHandler,
    ) -> None:
        """Register a handler for a confirmed service.

        Args:
            service_choice: Confirmed service choice number.
            handler: Async handler coroutine.
        """
        self._confirmed[service_choice] = handler

    def register_unconfirmed(
        self,
        service_choice: int,
        handler: UnconfirmedHandler,
    ) -> None:
        """Register a handler for an unconfirmed service.

        Args:
            service_choice: Unconfirmed service choice number.
            handler: Async handler coroutine.
        """
        self._unconfirmed[service_choice] = handler

    async def dispatch_confirmed(
        self,
        service_choice: int,
        request_data: bytes,
        source: BACnetAddress,
    ) -> bytes | None:
        """Dispatch an incoming confirmed request to its handler.

        Args:
            service_choice: Confirmed service choice number.
            request_data: Raw service request bytes.
            source: Source address of the request.

        Returns:
            Service ACK data for ComplexACK, or None for SimpleACK.

        Raises:
            BACnetRejectError: If no handler is registered for the service.
        """
        handler = self._confirmed.get(service_choice)
        if handler is None:
            raise BACnetRejectError(RejectReason.UNRECOGNIZED_SERVICE)
        return await handler(service_choice, request_data, source)

    async def dispatch_unconfirmed(
        self,
        service_choice: int,
        request_data: bytes,
        source: BACnetAddress,
    ) -> None:
        """Dispatch an incoming unconfirmed request to its handler.

        If no handler is registered for *service_choice*, the request
        is silently ignored (per Clause 5.4.2 — no reject/abort is
        sent for unconfirmed services).

        Args:
            service_choice: Unconfirmed service choice number.
            request_data: Raw service request bytes.
            source: Source address of the request.
        """
        handler = self._unconfirmed.get(service_choice)
        if handler is not None:
            await handler(service_choice, request_data, source)
