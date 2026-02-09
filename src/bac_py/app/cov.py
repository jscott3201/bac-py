"""COV (Change of Value) subscription manager per ASHRAE 135-2016 Clause 13.1."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bac_py.encoding.primitives import (
    encode_application_bit_string,
    encode_property_value,
)
from bac_py.services.cov import BACnetPropertyValue, COVNotificationRequest
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import BitString

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.objects.base import BACnetObject, ObjectDatabase
    from bac_py.services.cov import SubscribeCOVRequest
    from bac_py.types.primitives import ObjectIdentifier

logger = logging.getLogger(__name__)

# Object types that use COV_INCREMENT for analog threshold checking
_ANALOG_TYPES = frozenset(
    {
        ObjectType.ANALOG_INPUT,
        ObjectType.ANALOG_OUTPUT,
        ObjectType.ANALOG_VALUE,
        ObjectType.LARGE_ANALOG_VALUE,
    }
)


@dataclass
class COVSubscription:
    """Tracks a single COV subscription."""

    subscriber: BACnetAddress
    """BACnet address of the subscribing device."""

    process_id: int
    """Subscriber-assigned process identifier."""

    monitored_object: ObjectIdentifier
    """Object identifier being monitored."""

    confirmed: bool
    """``True`` for confirmed notifications, ``False`` for unconfirmed."""

    lifetime: float | None  # None = indefinite; seconds
    """Subscription duration in seconds, or ``None`` for indefinite."""

    created_at: float = field(default_factory=time.monotonic)
    """Monotonic timestamp when the subscription was created."""

    expiry_handle: asyncio.TimerHandle | None = None
    """Timer handle for subscription expiry, if any."""

    last_present_value: Any = None
    """Last notified Present_Value, used for COV comparison."""

    last_status_flags: Any = None
    """Last notified Status_Flags, used for change detection."""


class COVManager:
    """Manages COV subscriptions and notification dispatch.

    Per Clause 13.1, COV notifications are sent when:
    - Analog objects: ``|new - last| >= COV_INCREMENT`` (any change if no increment set)
    - Binary/multistate objects: any change in Present_Value
    - Any object: change in Status_Flags
    """

    def __init__(self, app: BACnetApplication) -> None:
        self._app = app
        self._subscriptions: dict[
            tuple[Any, int, Any],  # (subscriber, process_id, object_id)
            COVSubscription,
        ] = {}

    def subscribe(
        self,
        subscriber: BACnetAddress,
        request: SubscribeCOVRequest,
        object_db: ObjectDatabase,
    ) -> None:
        """Add or update a COV subscription.

        Args:
            subscriber: Address of the subscribing device.
            request: The decoded SubscribeCOV-Request.
            object_db: Object database to validate the object exists.

        Raises:
            BACnetError: If the monitored object does not exist.
        """
        obj_id = request.monitored_object_identifier
        obj = object_db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        key = (subscriber, request.subscriber_process_identifier, obj_id)

        # Cancel existing subscription timer if replacing
        existing = self._subscriptions.get(key)
        if existing and existing.expiry_handle:
            existing.expiry_handle.cancel()

        # Capture initial values for COV comparison
        present_value = self._read_present_value(obj)
        status_flags = self._read_status_flags(obj)

        confirmed = request.issue_confirmed_notifications or False
        lifetime = request.lifetime

        sub = COVSubscription(
            subscriber=subscriber,
            process_id=request.subscriber_process_identifier,
            monitored_object=obj_id,
            confirmed=confirmed,
            lifetime=float(lifetime) if lifetime is not None else None,
            last_present_value=present_value,
            last_status_flags=status_flags,
        )
        self._subscriptions[key] = sub

        # Start lifetime timer if applicable
        if lifetime is not None and lifetime > 0:
            loop = asyncio.get_running_loop()
            sub.expiry_handle = loop.call_later(
                float(lifetime), self._on_subscription_expired, key
            )

        # Per Clause 13.1.2, send initial notification with current values
        self._send_notification(sub, obj)

    def unsubscribe(
        self,
        subscriber: BACnetAddress,
        process_id: int,
        monitored_object: ObjectIdentifier,
    ) -> None:
        """Remove a subscription (cancellation).

        Silently ignores if no matching subscription exists.
        """
        key = (subscriber, process_id, monitored_object)
        sub = self._subscriptions.pop(key, None)
        if sub and sub.expiry_handle:
            sub.expiry_handle.cancel()

    def check_and_notify(
        self,
        obj: BACnetObject,
        changed_property: PropertyIdentifier,
    ) -> None:
        """Check all subscriptions for this object and send notifications if needed.

        Called after a property write. Compares current values against
        last-reported values using COV increment logic per Clause 13.1.

        Args:
            obj: The object whose property was changed.
            changed_property: The property that was written.
        """
        obj_id = obj.object_identifier
        for _key, sub in list(self._subscriptions.items()):
            if sub.monitored_object != obj_id:
                continue
            if self._should_notify(sub, obj):
                self._send_notification(sub, obj)
                # Update last-reported values
                sub.last_present_value = self._read_present_value(obj)
                sub.last_status_flags = self._read_status_flags(obj)

    def get_active_subscriptions(
        self,
        object_id: ObjectIdentifier | None = None,
    ) -> list[COVSubscription]:
        """Return active subscriptions, optionally filtered by object."""
        if object_id is None:
            return list(self._subscriptions.values())
        return [sub for sub in self._subscriptions.values() if sub.monitored_object == object_id]

    def shutdown(self) -> None:
        """Cancel all subscription timers."""
        for sub in self._subscriptions.values():
            if sub.expiry_handle:
                sub.expiry_handle.cancel()
        self._subscriptions.clear()

    def remove_object_subscriptions(self, object_id: ObjectIdentifier) -> None:
        """Remove all subscriptions for a deleted object.

        Called when an object is removed from the database to clean
        up any outstanding COV subscriptions per Clause 13.1.
        """
        keys_to_remove = [
            key for key, sub in self._subscriptions.items() if sub.monitored_object == object_id
        ]
        for key in keys_to_remove:
            sub = self._subscriptions.pop(key)
            if sub.expiry_handle:
                sub.expiry_handle.cancel()

    def _should_notify(
        self,
        sub: COVSubscription,
        obj: BACnetObject,
    ) -> bool:
        """Determine if a notification should be sent based on COV rules.

        Per Clause 13.1:
        - Analog objects: ``|new_value - last_reported| >= COV_INCREMENT``
        - Binary/multistate: any change in Present_Value
        - Any: change in Status_Flags
        """
        current_pv = self._read_present_value(obj)
        current_sf = self._read_status_flags(obj)

        # Check Status_Flags change
        if current_sf != sub.last_status_flags:
            return True

        # Check Present_Value change
        if current_pv == sub.last_present_value:
            return False

        obj_type = obj.object_identifier.object_type
        if obj_type in _ANALOG_TYPES:
            # Analog: use COV_INCREMENT if available
            cov_increment = self._read_cov_increment(obj)
            if cov_increment is not None and cov_increment > 0:
                if sub.last_present_value is None:
                    return True
                if isinstance(current_pv, (int, float)) and isinstance(
                    sub.last_present_value, (int, float)
                ):
                    return abs(current_pv - sub.last_present_value) >= cov_increment
            # No COV_INCREMENT or zero: any change triggers
            return True

        # Binary/multistate: any change triggers
        return True

    def _send_notification(self, sub: COVSubscription, obj: BACnetObject) -> None:
        """Send a COV notification (confirmed or unconfirmed).

        Builds the notification with Present_Value and Status_Flags,
        then sends via the application layer.
        """
        # Build list_of_values with Present_Value and Status_Flags
        present_value = self._read_present_value(obj)
        status_flags = self._read_status_flags(obj)

        pv_bytes = self._encode_value(present_value, obj.object_identifier.object_type)
        sf_bytes = self._encode_status_flags(status_flags)

        list_of_values = [
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                value=pv_bytes,
            ),
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier.STATUS_FLAGS,
                value=sf_bytes,
            ),
        ]

        # Compute time_remaining
        time_remaining = 0
        if sub.lifetime is not None:
            elapsed = time.monotonic() - sub.created_at
            remaining = max(0, sub.lifetime - elapsed)
            time_remaining = int(remaining)

        # Build device identifier
        device_id = self._app.device_object_identifier

        notification = COVNotificationRequest(
            subscriber_process_identifier=sub.process_id,
            initiating_device_identifier=device_id,
            monitored_object_identifier=sub.monitored_object,
            time_remaining=time_remaining,
            list_of_values=list_of_values,
        )

        encoded = notification.encode()

        if sub.confirmed:
            self._app.send_confirmed_cov_notification(
                encoded, sub.subscriber, ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION
            )
        else:
            self._app.unconfirmed_request(
                destination=sub.subscriber,
                service_choice=UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION,
                service_data=encoded,
            )

    def _on_subscription_expired(self, key: tuple[Any, int, Any]) -> None:
        """Remove expired subscription."""
        sub = self._subscriptions.pop(key, None)
        if sub:
            logger.debug(
                "COV subscription expired: process_id=%d, object=%s",
                sub.process_id,
                sub.monitored_object,
            )

    @staticmethod
    def _read_present_value(obj: BACnetObject) -> Any:
        """Read Present_Value, returning None if not available."""
        try:
            return obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        except Exception:
            return None

    @staticmethod
    def _read_status_flags(obj: BACnetObject) -> Any:
        """Read Status_Flags, returning None if not available."""
        try:
            return obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        except Exception:
            return None

    @staticmethod
    def _read_cov_increment(obj: BACnetObject) -> float | None:
        """Read COV_INCREMENT, returning None if not set."""
        try:
            value = obj.read_property(PropertyIdentifier.COV_INCREMENT)
            if isinstance(value, (int, float)):
                return float(value)
        except Exception:
            pass
        return None

    @staticmethod
    def _encode_value(value: Any, obj_type: ObjectType) -> bytes:
        """Encode a property value to application-tagged bytes for COV notification.

        Delegates to :func:`encode_property_value`.  For analog object
        types, integers are encoded as REAL; otherwise the native type
        encoding is used.  Returns raw application-tagged bytes suitable
        for inclusion in a BACnetPropertyValue sequence.
        """
        return encode_property_value(value, int_as_real=obj_type in _ANALOG_TYPES)

    @staticmethod
    def _encode_status_flags(status_flags: Any) -> bytes:
        """Encode StatusFlags to application-tagged bytes.

        Accepts a :class:`StatusFlags` dataclass, a raw
        :class:`BitString`, or any other value (in which case
        all-clear flags are returned as a fallback).
        """
        if isinstance(status_flags, StatusFlags):
            return encode_application_bit_string(status_flags.to_bit_string())
        if isinstance(status_flags, BitString):
            return encode_application_bit_string(status_flags)
        # Default: all-clear flags
        return encode_application_bit_string(BitString(bytes([0x00]), unused_bits=4))
