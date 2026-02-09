"""BACnet protocol error types per ASHRAE 135-2016 Clause 18."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bac_py.types.enums import AbortReason, ErrorClass, ErrorCode, RejectReason


class BACnetBaseError(Exception):
    """Base exception for BACnet protocol errors."""


class BACnetError(BACnetBaseError):
    """BACnet Error-PDU received (Clause 18).

    Contains error class and code per the specification.
    """

    def __init__(
        self,
        error_class: ErrorClass,
        error_code: ErrorCode,
        error_data: bytes = b"",
    ) -> None:
        """Initialise a BACnet error.

        Args:
            error_class: The error class enumeration.
            error_code: The error code enumeration.
            error_data: Additional raw error data following the base
                error class/code pair.  Currently preserved but not
                decoded (extended error types are service-specific).
        """
        self.error_class = error_class
        self.error_code = error_code
        self.error_data = error_data
        super().__init__(f"{error_class.name}: {error_code.name}")


class BACnetRejectError(BACnetBaseError):
    """BACnet Reject-PDU received (Clause 18.9).

    Indicates a syntax or protocol error in the request.
    """

    def __init__(self, reason: RejectReason) -> None:
        self.reason = reason
        super().__init__(f"Reject: {reason.name}")


class BACnetAbortError(BACnetBaseError):
    """BACnet Abort-PDU received (Clause 18.10).

    Indicates the transaction was aborted.
    """

    def __init__(self, reason: AbortReason) -> None:
        self.reason = reason
        super().__init__(f"Abort: {reason.name}")


class BACnetTimeoutError(BACnetBaseError):
    """Request timed out after all retries exhausted."""
