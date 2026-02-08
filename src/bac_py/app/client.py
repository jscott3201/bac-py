"""High-level BACnet client API per ASHRAE 135-2016."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bac_py.network.address import GLOBAL_BROADCAST
from bac_py.services.cov import SubscribeCOVRequest
from bac_py.services.read_property import ReadPropertyACK, ReadPropertyRequest
from bac_py.services.read_property_multiple import (
    ReadAccessSpecification,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
)
from bac_py.services.read_range import (
    RangeByPosition,
    RangeBySequenceNumber,
    RangeByTime,
    ReadRangeACK,
    ReadRangeRequest,
)
from bac_py.services.who_is import IAmRequest, WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.services.write_property_multiple import (
    WriteAccessSpecification,
    WritePropertyMultipleRequest,
)
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    PropertyIdentifier,
    UnconfirmedServiceChoice,
)

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.network.address import BACnetAddress
    from bac_py.types.primitives import ObjectIdentifier

logger = logging.getLogger(__name__)


class BACnetClient:
    """High-level async BACnet client API.

    Wraps a BACnetApplication to provide typed methods for common
    BACnet services: ReadProperty, WriteProperty, ReadPropertyMultiple,
    WritePropertyMultiple, ReadRange, and Who-Is/I-Am.
    """

    def __init__(self, app: BACnetApplication) -> None:
        self._app = app

    async def read_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
    ) -> ReadPropertyACK:
        """Read a single property from a remote device.

        Args:
            address: Target device address.
            object_identifier: Object to read from.
            property_identifier: Property to read.
            array_index: Optional array index for array properties.

        Returns:
            Decoded ReadPropertyACK containing the property value.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = ReadPropertyRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=array_index,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.READ_PROPERTY,
            service_data=request.encode(),
        )
        return ReadPropertyACK.decode(response_data)

    async def write_property(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        value: bytes,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        """Write a property value to a remote device.

        Args:
            address: Target device address.
            object_identifier: Object to write to.
            property_identifier: Property to write.
            value: Application-tagged encoded property value bytes.
            priority: Optional write priority (1-16).
            array_index: Optional array index for array properties.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = WritePropertyRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_value=value,
            property_array_index=array_index,
            priority=priority,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.WRITE_PROPERTY,
            service_data=request.encode(),
        )

    async def read_property_multiple(
        self,
        address: BACnetAddress,
        read_access_specs: list[ReadAccessSpecification],
    ) -> ReadPropertyMultipleACK:
        """Read multiple properties from one or more objects.

        Args:
            address: Target device address.
            read_access_specs: List of read access specifications, each
                containing an object identifier and list of property
                references to read.

        Returns:
            Decoded ReadPropertyMultiple-ACK with per-property results.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=read_access_specs,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE,
            service_data=request.encode(),
        )
        return ReadPropertyMultipleACK.decode(response_data)

    async def write_property_multiple(
        self,
        address: BACnetAddress,
        write_access_specs: list[WriteAccessSpecification],
    ) -> None:
        """Write multiple properties to one or more objects.

        Args:
            address: Target device address.
            write_access_specs: List of write access specifications, each
                containing an object identifier and list of property
                values to write.

        Raises:
            BACnetError: On Error-PDU response (first failing property).
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=write_access_specs,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE,
            service_data=request.encode(),
        )

    async def read_range(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        property_identifier: PropertyIdentifier,
        array_index: int | None = None,
        range_qualifier: RangeByPosition | RangeBySequenceNumber | RangeByTime | None = None,
    ) -> ReadRangeACK:
        """Read a range of items from a list or array property.

        Args:
            address: Target device address.
            object_identifier: Object containing the list property.
            property_identifier: List or array property to read.
            array_index: Optional array index.
            range_qualifier: Optional range qualifier (by position,
                sequence number, or time). If None, returns all items.

        Returns:
            Decoded ReadRange-ACK with the requested items.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = ReadRangeRequest(
            object_identifier=object_identifier,
            property_identifier=property_identifier,
            property_array_index=array_index,
            range=range_qualifier,
        )
        response_data = await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.READ_RANGE,
            service_data=request.encode(),
        )
        return ReadRangeACK.decode(response_data)

    async def who_is(
        self,
        low_limit: int | None = None,
        high_limit: int | None = None,
        destination: BACnetAddress = GLOBAL_BROADCAST,
        timeout: float = 3.0,
    ) -> list[IAmRequest]:
        """Discover devices via Who-Is broadcast.

        Sends a Who-Is request and collects I-Am responses for the
        specified timeout duration.

        Args:
            low_limit: Optional lower bound of device instance range.
            high_limit: Optional upper bound of device instance range.
            destination: Broadcast address (default: global broadcast).
            timeout: Seconds to wait for responses.

        Returns:
            List of I-Am responses received within the timeout.
        """
        responses: list[IAmRequest] = []

        def on_i_am(service_data: bytes, source: BACnetAddress) -> None:
            try:
                iam = IAmRequest.decode(service_data)
                responses.append(iam)
            except (ValueError, IndexError):
                logger.debug("Dropped malformed I-Am from %s", source)

        # Register temporary listener for I-Am responses
        self._app.register_temporary_handler(UnconfirmedServiceChoice.I_AM, on_i_am)
        try:
            # Send Who-Is request
            request = WhoIsRequest(low_limit=low_limit, high_limit=high_limit)
            self._app.unconfirmed_request(
                destination=destination,
                service_choice=UnconfirmedServiceChoice.WHO_IS,
                service_data=request.encode(),
            )
            # Collect responses for the timeout duration
            await asyncio.sleep(timeout)
        finally:
            self._app.unregister_temporary_handler(UnconfirmedServiceChoice.I_AM, on_i_am)

        return responses

    async def subscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
        confirmed: bool = True,
        lifetime: int | None = None,
    ) -> None:
        """Subscribe to COV notifications from a remote device.

        Sends a SubscribeCOV-Request per Clause 13.14.1. The remote
        device will send confirmed or unconfirmed COV notifications
        when the monitored object's value changes.

        Args:
            address: Target device address.
            object_identifier: Object to monitor.
            process_id: Subscriber process identifier (caller-managed).
            confirmed: True for confirmed notifications, False for unconfirmed.
            lifetime: Subscription lifetime in seconds, or None for indefinite.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = SubscribeCOVRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
            issue_confirmed_notifications=confirmed,
            lifetime=lifetime,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.SUBSCRIBE_COV,
            service_data=request.encode(),
        )

    async def unsubscribe_cov(
        self,
        address: BACnetAddress,
        object_identifier: ObjectIdentifier,
        process_id: int,
    ) -> None:
        """Cancel a COV subscription on a remote device.

        Per Clause 13.14, omits ``issueConfirmedNotifications`` and
        ``lifetime`` to indicate cancellation.

        Args:
            address: Target device address.
            object_identifier: Object being monitored.
            process_id: Subscriber process identifier used during subscription.

        Raises:
            BACnetError: On Error-PDU response.
            BACnetRejectError: On Reject-PDU response.
            BACnetAbortError: On Abort-PDU response.
            BACnetTimeoutError: On timeout after all retries.
        """
        request = SubscribeCOVRequest(
            subscriber_process_identifier=process_id,
            monitored_object_identifier=object_identifier,
        )
        await self._app.confirmed_request(
            destination=address,
            service_choice=ConfirmedServiceChoice.SUBSCRIBE_COV,
            service_data=request.encode(),
        )
