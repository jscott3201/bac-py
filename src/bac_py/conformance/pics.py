"""PICS (Protocol Implementation Conformance Statement) generator.

Generates a structured PICS report by introspecting a BACnet application's
registered services, object types, and device properties per ASHRAE 135-2020
Clause 22 / Annex A.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bac_py.objects.base import _OBJECT_REGISTRY
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ObjectType,
    PropertyIdentifier,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import BitString

if TYPE_CHECKING:
    from bac_py.objects.base import ObjectDatabase
    from bac_py.objects.device import DeviceObject


# Mapping of ProtocolServicesSupported bit positions to service names
# per Clause 12.11.18 and Clause 21.
_CONFIRMED_SERVICE_BITS: dict[int, ConfirmedServiceChoice] = {
    0: ConfirmedServiceChoice.ACKNOWLEDGE_ALARM,
    1: ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION,
    2: ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION,
    3: ConfirmedServiceChoice.GET_ALARM_SUMMARY,
    4: ConfirmedServiceChoice.GET_ENROLLMENT_SUMMARY,
    5: ConfirmedServiceChoice.SUBSCRIBE_COV,
    6: ConfirmedServiceChoice.ATOMIC_READ_FILE,
    7: ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
    8: ConfirmedServiceChoice.ADD_LIST_ELEMENT,
    9: ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
    10: ConfirmedServiceChoice.CREATE_OBJECT,
    11: ConfirmedServiceChoice.DELETE_OBJECT,
    12: ConfirmedServiceChoice.READ_PROPERTY,
    14: ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE,
    15: ConfirmedServiceChoice.WRITE_PROPERTY,
    16: ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE,
    17: ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL,
    18: ConfirmedServiceChoice.CONFIRMED_PRIVATE_TRANSFER,
    19: ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
    20: ConfirmedServiceChoice.REINITIALIZE_DEVICE,
    21: ConfirmedServiceChoice.VT_OPEN,
    22: ConfirmedServiceChoice.VT_CLOSE,
    23: ConfirmedServiceChoice.VT_DATA,
    26: ConfirmedServiceChoice.READ_RANGE,
    27: ConfirmedServiceChoice.LIFE_SAFETY_OPERATION,
    28: ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY,
    29: ConfirmedServiceChoice.GET_EVENT_INFORMATION,
    30: ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY_MULTIPLE,
    31: ConfirmedServiceChoice.CONFIRMED_COV_NOTIFICATION_MULTIPLE,
    32: ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
    33: ConfirmedServiceChoice.AUDIT_LOG_QUERY,
}

_UNCONFIRMED_SERVICE_BITS: dict[int, UnconfirmedServiceChoice] = {
    0: UnconfirmedServiceChoice.I_AM,
    1: UnconfirmedServiceChoice.I_HAVE,
    2: UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION,
    3: UnconfirmedServiceChoice.UNCONFIRMED_EVENT_NOTIFICATION,
    4: UnconfirmedServiceChoice.UNCONFIRMED_PRIVATE_TRANSFER,
    5: UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE,
    6: UnconfirmedServiceChoice.TIME_SYNCHRONIZATION,
    7: UnconfirmedServiceChoice.WHO_HAS,
    8: UnconfirmedServiceChoice.WHO_IS,
    9: UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION,
    10: UnconfirmedServiceChoice.WRITE_GROUP,
    11: UnconfirmedServiceChoice.UNCONFIRMED_COV_NOTIFICATION_MULTIPLE,
    12: UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION,
    13: UnconfirmedServiceChoice.WHO_AM_I,
    14: UnconfirmedServiceChoice.YOU_ARE,
}


def _bitstring_bit_set(bs: BitString, bit: int) -> bool:
    """Check if a specific bit is set in a BitString."""
    if bit < 0 or bit >= len(bs):
        return False
    return bs[bit]


class PICSGenerator:
    """Generate a PICS report from a running BACnet application.

    Introspects the application's device object, service registry,
    and object database to produce a structured conformance statement.
    """

    def __init__(self, object_db: ObjectDatabase, device: DeviceObject) -> None:
        self._db = object_db
        self._device = device

    def generate(self) -> dict[str, Any]:
        """Generate the full PICS report as a JSON-serializable dict."""
        return {
            "general": self._general_info(),
            "services_supported": self._services_supported(),
            "object_types_supported": self._object_types_supported(),
            "data_link": self._data_link_info(),
            "character_sets": self._character_set_info(),
        }

    def _general_info(self) -> dict[str, Any]:
        """Extract general device information."""
        props = self._device._properties
        return {
            "vendor_name": props.get(PropertyIdentifier.VENDOR_NAME, ""),
            "vendor_identifier": props.get(PropertyIdentifier.VENDOR_IDENTIFIER, 0),
            "model_name": props.get(PropertyIdentifier.MODEL_NAME, ""),
            "firmware_revision": props.get(PropertyIdentifier.FIRMWARE_REVISION, ""),
            "application_software_version": props.get(
                PropertyIdentifier.APPLICATION_SOFTWARE_VERSION, ""
            ),
            "protocol_version": props.get(PropertyIdentifier.PROTOCOL_VERSION, 1),
            "protocol_revision": props.get(PropertyIdentifier.PROTOCOL_REVISION, 0),
            "max_apdu_length_accepted": props.get(
                PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED, 1476
            ),
            "segmentation_supported": str(
                props.get(PropertyIdentifier.SEGMENTATION_SUPPORTED, "")
            ),
        }

    def _services_supported(self) -> dict[str, list[str]]:
        """Extract supported services from Protocol_Services_Supported."""
        services_bs = self._device._properties.get(PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED)
        confirmed: list[str] = []
        unconfirmed: list[str] = []

        if isinstance(services_bs, BitString):
            for bit, svc in _CONFIRMED_SERVICE_BITS.items():
                if _bitstring_bit_set(services_bs, bit):
                    confirmed.append(svc.name)

            for bit, usvc in _UNCONFIRMED_SERVICE_BITS.items():
                # Unconfirmed services start at bit 40 in the bitstring
                actual_bit = 40 + bit
                if _bitstring_bit_set(services_bs, actual_bit):
                    unconfirmed.append(usvc.name)

        return {
            "confirmed": confirmed,
            "unconfirmed": unconfirmed,
        }

    def _object_types_supported(self) -> list[str]:
        """Extract supported object types from Protocol_Object_Types_Supported."""
        obj_types_bs = self._device._properties.get(
            PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED
        )
        supported: list[str] = []

        if isinstance(obj_types_bs, BitString):
            for obj_type in ObjectType:
                if _bitstring_bit_set(obj_types_bs, obj_type.value):
                    supported.append(obj_type.name)

        # Also check what's actually registered
        for obj_type in sorted(_OBJECT_REGISTRY.keys(), key=lambda x: x.value):
            if obj_type.name not in supported:
                supported.append(obj_type.name)

        return supported

    def _data_link_info(self) -> dict[str, Any]:
        """Extract data link layer information."""
        return {
            "data_link_layer": "BACnet/IP (Annex J)",
            "max_apdu_length": self._device._properties.get(
                PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED, 1476
            ),
        }

    def _character_set_info(self) -> dict[str, Any]:
        """Extract character set support."""
        return {
            "character_sets": ["UTF-8"],
        }
