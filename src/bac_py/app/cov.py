"""COV (Change of Value) subscription manager per ASHRAE 135-2016 Clause 13.1."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bac_py.app._object_type_sets import ANALOG_TYPES
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
    from bac_py.services.cov import (
        SubscribeCOVPropertyMultipleRequest,
        SubscribeCOVPropertyRequest,
        SubscribeCOVRequest,
    )
    from bac_py.types.primitives import ObjectIdentifier

logger = logging.getLogger(__name__)


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


@dataclass
class PropertySubscription:
    """Tracks a single property-level COV subscription (Clause 13.15/13.16)."""

    subscriber: BACnetAddress
    """BACnet address of the subscribing device."""

    process_id: int
    """Subscriber-assigned process identifier."""

    monitored_object: ObjectIdentifier
    """Object identifier being monitored."""

    monitored_property: int  # PropertyIdentifier value
    """Property identifier being monitored."""

    property_array_index: int | None
    """Optional array index within the monitored property."""

    confirmed: bool
    """``True`` for confirmed notifications, ``False`` for unconfirmed."""

    lifetime: float | None
    """Subscription duration in seconds, or ``None`` for indefinite."""

    cov_increment: float | None
    """Subscription-specific COV increment override, or ``None``."""

    created_at: float = field(default_factory=time.monotonic)
    """Monotonic timestamp when the subscription was created."""

    last_value: Any = None
    """Last notified value for the monitored property."""

    expiry_handle: asyncio.TimerHandle | None = None
    """Timer handle for subscription expiry, if any."""


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
        self._property_subscriptions: dict[
            tuple[Any, int, Any, int, int | None],
            # (subscriber, process_id, object_id, property_id, array_index)
            PropertySubscription,
        ] = {}
        # Secondary indices for O(k) lookup in check_and_notify (vs O(N) scan)
        self._subs_by_object: dict[Any, dict[tuple[Any, int, Any], COVSubscription]] = {}
        self._prop_subs_by_obj_prop: dict[
            tuple[Any, int],  # (object_id, property_id)
            dict[tuple[Any, int, Any, int, int | None], PropertySubscription],
        ] = {}

    def subscribe(
        self,
        subscriber: BACnetAddress,
        request: SubscribeCOVRequest,
        object_db: ObjectDatabase,
    ) -> None:
        """Add or update a COV subscription.

        :param subscriber: Address of the subscribing device.
        :param request: The decoded SubscribeCOV-Request.
        :param object_db: Object database to validate the object exists.
        :raises BACnetError: If the monitored object does not exist.
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
        self._subs_by_object.setdefault(obj_id, {})[key] = sub
        logger.info(f"COV subscription created: {obj_id} subscriber={subscriber}")

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
        if sub:
            if sub.expiry_handle:
                sub.expiry_handle.cancel()
            obj_bucket = self._subs_by_object.get(monitored_object)
            if obj_bucket is not None:
                obj_bucket.pop(key, None)
                if not obj_bucket:
                    del self._subs_by_object[monitored_object]
            logger.info(f"COV subscription removed: {monitored_object}")

    def check_and_notify(
        self,
        obj: BACnetObject,
        changed_property: PropertyIdentifier,
    ) -> None:
        """Check all subscriptions for this object and send notifications if needed.

        Called after a property write. Compares current values against
        last-reported values using COV increment logic per Clause 13.1.

        :param obj: The object whose property was changed.
        :param changed_property: The property that was written.
        """
        obj_id = obj.object_identifier
        obj_bucket = self._subs_by_object.get(obj_id)
        if obj_bucket:
            for _key, sub in list(obj_bucket.items()):
                if self._should_notify(sub, obj):
                    self._send_notification(sub, obj)
                    # Update last-reported values
                    sub.last_present_value = self._read_present_value(obj)
                    sub.last_status_flags = self._read_status_flags(obj)

        # Also check property-level subscriptions
        self.check_and_notify_property(obj, changed_property)

    def get_active_subscriptions(
        self,
        object_id: ObjectIdentifier | None = None,
    ) -> list[COVSubscription]:
        """Return active subscriptions, optionally filtered by object."""
        if object_id is None:
            return list(self._subscriptions.values())
        obj_bucket = self._subs_by_object.get(object_id)
        return list(obj_bucket.values()) if obj_bucket else []

    def shutdown(self) -> None:
        """Cancel all subscription timers."""
        for sub in self._subscriptions.values():
            if sub.expiry_handle:
                sub.expiry_handle.cancel()
        self._subscriptions.clear()
        self._subs_by_object.clear()

        for prop_sub in self._property_subscriptions.values():
            if prop_sub.expiry_handle:
                prop_sub.expiry_handle.cancel()
        self._property_subscriptions.clear()
        self._prop_subs_by_obj_prop.clear()

    def remove_object_subscriptions(self, object_id: ObjectIdentifier) -> None:
        """Remove all subscriptions for a deleted object.

        Called when an object is removed from the database to clean
        up any outstanding COV subscriptions per Clause 13.1.
        """
        # Use secondary index for O(k) cleanup of object-level subscriptions
        obj_bucket = self._subs_by_object.pop(object_id, None)
        if obj_bucket:
            for key, sub in obj_bucket.items():
                self._subscriptions.pop(key, None)
                if sub.expiry_handle:
                    sub.expiry_handle.cancel()

        # Remove property subscriptions for this object
        prop_idx_keys = [
            idx_key for idx_key in self._prop_subs_by_obj_prop if idx_key[0] == object_id
        ]
        for idx_key in prop_idx_keys:
            prop_bucket = self._prop_subs_by_obj_prop.pop(idx_key)
            for pkey, psub in prop_bucket.items():
                self._property_subscriptions.pop(pkey, None)
                if psub.expiry_handle:
                    psub.expiry_handle.cancel()

    def subscribe_property(
        self,
        subscriber: BACnetAddress,
        request: SubscribeCOVPropertyRequest,
        object_db: ObjectDatabase,
    ) -> None:
        """Add or update a property-level COV subscription (Clause 13.15).

        :param subscriber: Address of the subscribing device.
        :param request: The decoded SubscribeCOVProperty-Request.
        :param object_db: Object database to validate the object exists.
        :raises BACnetError: If the monitored object does not exist.
        """
        obj_id = request.monitored_object_identifier
        obj = object_db.get(obj_id)
        if obj is None:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

        prop_ref = request.monitored_property_identifier
        prop_id = prop_ref.property_identifier
        array_index = prop_ref.property_array_index

        key: tuple[Any, int, Any, int, int | None] = (
            subscriber,
            request.subscriber_process_identifier,
            obj_id,
            prop_id,
            array_index,
        )

        # Cancel existing subscription timer if replacing
        existing = self._property_subscriptions.get(key)
        if existing and existing.expiry_handle:
            existing.expiry_handle.cancel()

        # Capture initial value of the specific property
        initial_value = self._read_property_value(obj, prop_id, array_index)

        confirmed = request.issue_confirmed_notifications or False
        lifetime = request.lifetime

        sub = PropertySubscription(
            subscriber=subscriber,
            process_id=request.subscriber_process_identifier,
            monitored_object=obj_id,
            monitored_property=prop_id,
            property_array_index=array_index,
            confirmed=confirmed,
            lifetime=float(lifetime) if lifetime is not None else None,
            cov_increment=request.cov_increment,
            last_value=initial_value,
        )
        self._property_subscriptions[key] = sub
        self._prop_subs_by_obj_prop.setdefault((obj_id, prop_id), {})[key] = sub

        # Start lifetime timer if applicable
        if lifetime is not None and lifetime > 0:
            loop = asyncio.get_running_loop()
            sub.expiry_handle = loop.call_later(
                float(lifetime), self._on_property_subscription_expired, key
            )

        # Send initial notification with current values
        self._send_property_notification(sub, obj)

    def subscribe_property_multiple(
        self,
        subscriber: BACnetAddress,
        request: SubscribeCOVPropertyMultipleRequest,
        object_db: ObjectDatabase,
    ) -> None:
        """Add or update multiple property-level COV subscriptions (Clause 13.16).

        :param subscriber: Address of the subscribing device.
        :param request: The decoded SubscribeCOVPropertyMultiple-Request.
        :param object_db: Object database to validate objects exist.
        :raises BACnetError: If any monitored object does not exist.
        """
        confirmed = request.issue_confirmed_notifications or False
        lifetime = request.lifetime

        for spec in request.list_of_cov_subscription_specifications:
            obj_id = spec.monitored_object_identifier
            obj = object_db.get(obj_id)
            if obj is None:
                raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)

            for ref in spec.list_of_cov_references:
                prop_id = ref.monitored_property.property_identifier
                array_index = ref.monitored_property.property_array_index

                key: tuple[Any, int, Any, int, int | None] = (
                    subscriber,
                    request.subscriber_process_identifier,
                    obj_id,
                    prop_id,
                    array_index,
                )

                # Cancel existing subscription timer if replacing
                existing = self._property_subscriptions.get(key)
                if existing and existing.expiry_handle:
                    existing.expiry_handle.cancel()

                # Capture initial value of the specific property
                initial_value = self._read_property_value(obj, prop_id, array_index)

                sub = PropertySubscription(
                    subscriber=subscriber,
                    process_id=request.subscriber_process_identifier,
                    monitored_object=obj_id,
                    monitored_property=prop_id,
                    property_array_index=array_index,
                    confirmed=confirmed,
                    lifetime=float(lifetime) if lifetime is not None else None,
                    cov_increment=ref.cov_increment,
                    last_value=initial_value,
                )
                self._property_subscriptions[key] = sub
                self._prop_subs_by_obj_prop.setdefault((obj_id, prop_id), {})[key] = sub

                # Start lifetime timer if applicable
                if lifetime is not None and lifetime > 0:
                    loop = asyncio.get_running_loop()
                    sub.expiry_handle = loop.call_later(
                        float(lifetime), self._on_property_subscription_expired, key
                    )

                # Send initial notification with current values
                self._send_property_notification(sub, obj)

    def unsubscribe_property(
        self,
        subscriber: BACnetAddress,
        process_id: int,
        obj_id: ObjectIdentifier,
        property_id: int,
        array_index: int | None = None,
    ) -> None:
        """Remove a property-level subscription (cancellation).

        Silently ignores if no matching subscription exists.

        :param subscriber: Address of the subscribing device.
        :param process_id: Subscriber-assigned process identifier.
        :param obj_id: Object identifier being monitored.
        :param property_id: Property identifier value being monitored.
        :param array_index: Optional array index within the property.
        """
        key: tuple[Any, int, Any, int, int | None] = (
            subscriber,
            process_id,
            obj_id,
            property_id,
            array_index,
        )
        sub = self._property_subscriptions.pop(key, None)
        if sub:
            if sub.expiry_handle:
                sub.expiry_handle.cancel()
            idx_key = (obj_id, property_id)
            prop_bucket = self._prop_subs_by_obj_prop.get(idx_key)
            if prop_bucket is not None:
                prop_bucket.pop(key, None)
                if not prop_bucket:
                    del self._prop_subs_by_obj_prop[idx_key]

    def check_and_notify_property(
        self,
        obj: BACnetObject,
        changed_property: PropertyIdentifier,
    ) -> None:
        """Check property-level subscriptions and send notifications if needed.

        For all property subscriptions matching this object and the changed
        property, check if the value changed enough to trigger a notification.
        For analog types, a subscription-specific ``cov_increment`` overrides
        the object's COV_INCREMENT. For non-analog types, any change triggers
        a notification.

        :param obj: The object whose property was changed.
        :param changed_property: The property that was written.
        """
        obj_id = obj.object_identifier
        changed_prop_int = int(changed_property)

        prop_bucket = self._prop_subs_by_obj_prop.get((obj_id, changed_prop_int))
        if not prop_bucket:
            return
        for _key, sub in list(prop_bucket.items()):
            current_value = self._read_property_value(
                obj, sub.monitored_property, sub.property_array_index
            )

            if self._should_notify_property(sub, obj, current_value):
                self._send_property_notification(sub, obj)
                sub.last_value = current_value

    def _should_notify_property(
        self,
        sub: PropertySubscription,
        obj: BACnetObject,
        current_value: Any,
    ) -> bool:
        """Determine if a property-level notification should be sent.

        :param sub: The property subscription to evaluate.
        :param obj: The monitored object.
        :param current_value: The current value of the monitored property.
        :returns: ``True`` if a notification should be sent.
        """
        if current_value == sub.last_value:
            return False

        obj_type = obj.object_identifier.object_type
        if obj_type in ANALOG_TYPES:
            # Use subscription-specific cov_increment if available,
            # otherwise fall back to the object's COV_INCREMENT
            cov_increment = sub.cov_increment
            if cov_increment is None:
                cov_increment = self._read_cov_increment(obj)

            if cov_increment is not None and cov_increment > 0:
                if sub.last_value is None:
                    return True
                if isinstance(current_value, (int, float)) and isinstance(
                    sub.last_value, (int, float)
                ):
                    return abs(current_value - sub.last_value) >= cov_increment
            # No COV_INCREMENT or zero: any change triggers
            return True

        # Non-analog: any change triggers notification
        return True

    def _send_property_notification(
        self,
        sub: PropertySubscription,
        obj: BACnetObject,
    ) -> None:
        """Send a COV notification for a property-level subscription.

        Builds a standard COVNotificationRequest with the monitored property's
        value and Status_Flags in ``list_of_values``, then sends via the
        application layer.

        :param sub: The property subscription triggering the notification.
        :param obj: The monitored object.
        """
        prop_value = self._read_property_value(
            obj, sub.monitored_property, sub.property_array_index
        )
        status_flags = self._read_status_flags(obj)

        prop_bytes = self._encode_value(prop_value, obj.object_identifier.object_type)
        sf_bytes = self._encode_status_flags(status_flags)

        list_of_values = [
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier(sub.monitored_property),
                property_array_index=sub.property_array_index,
                value=prop_bytes,
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

    def _on_property_subscription_expired(
        self,
        key: tuple[Any, int, Any, int, int | None],
    ) -> None:
        """Remove an expired property subscription.

        :param key: The subscription key to remove.
        """
        sub = self._property_subscriptions.pop(key, None)
        if sub:
            idx_key = (sub.monitored_object, sub.monitored_property)
            prop_bucket = self._prop_subs_by_obj_prop.get(idx_key)
            if prop_bucket is not None:
                prop_bucket.pop(key, None)
                if not prop_bucket:
                    del self._prop_subs_by_obj_prop[idx_key]
            logger.debug(
                "Property COV subscription expired: process_id=%d, object=%s, property=%d",
                sub.process_id,
                sub.monitored_object,
                sub.monitored_property,
            )

    @staticmethod
    def _read_property_value(
        obj: BACnetObject,
        property_id: int,
        array_index: int | None = None,
    ) -> Any:
        """Read a specific property value, returning None if not available.

        :param obj: The object to read from.
        :param property_id: The property identifier value.
        :param array_index: Optional array index.
        :returns: The property value, or ``None`` if unavailable.
        """
        try:
            return obj.read_property(PropertyIdentifier(property_id), array_index=array_index)
        except (BACnetError, ValueError):
            return None

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
        if obj_type in ANALOG_TYPES:
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
        logger.debug(f"COV notification for {sub.monitored_object} to {sub.subscriber}")
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
            obj_bucket = self._subs_by_object.get(sub.monitored_object)
            if obj_bucket is not None:
                obj_bucket.pop(key, None)
                if not obj_bucket:
                    del self._subs_by_object[sub.monitored_object]
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
        except BACnetError:
            return None

    @staticmethod
    def _read_status_flags(obj: BACnetObject) -> Any:
        """Read Status_Flags, returning None if not available."""
        try:
            return obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        except BACnetError:
            return None

    @staticmethod
    def _read_cov_increment(obj: BACnetObject) -> float | None:
        """Read COV_INCREMENT, returning None if not set."""
        try:
            value = obj.read_property(PropertyIdentifier.COV_INCREMENT)
            if isinstance(value, (int, float)):
                return float(value)
        except BACnetError:
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
        return encode_property_value(value, int_as_real=obj_type in ANALOG_TYPES)

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
