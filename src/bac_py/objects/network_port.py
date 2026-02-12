"""BACnet Network Port object type per ASHRAE 135-2020 Clause 12.56."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.enums import (
    IPMode,
    NetworkNumberQuality,
    NetworkPortCommand,
    NetworkType,
    ObjectType,
    PropertyIdentifier,
    ProtocolLevel,
    Reliability,
)


@register_object_type
class NetworkPortObject(BACnetObject):
    """BACnet Network Port object (Clause 12.56).

    Describes a network port's configuration and status.  Required for
    BACnet/IP devices.  Covers the essential properties for IP-based
    networking; additional properties (MS/TP, BACnet/SC) can be added
    as optional properties via initial_properties.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.NETWORK_PORT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(
            reliability_required=True,
            reliability_default=Reliability.NO_FAULT_DETECTED,
        ),
        # Required properties (Clause 12.56)
        PropertyIdentifier.NETWORK_TYPE: PropertyDefinition(
            PropertyIdentifier.NETWORK_TYPE,
            NetworkType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PROTOCOL_LEVEL: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_LEVEL,
            ProtocolLevel,
            PropertyAccess.READ_ONLY,
            required=True,
            default=ProtocolLevel.BACNET_APPLICATION,
        ),
        PropertyIdentifier.NETWORK_NUMBER: PropertyDefinition(
            PropertyIdentifier.NETWORK_NUMBER,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.NETWORK_NUMBER_QUALITY: PropertyDefinition(
            PropertyIdentifier.NETWORK_NUMBER_QUALITY,
            NetworkNumberQuality,
            PropertyAccess.READ_ONLY,
            required=True,
            default=NetworkNumberQuality.UNKNOWN,
        ),
        PropertyIdentifier.CHANGES_PENDING: PropertyDefinition(
            PropertyIdentifier.CHANGES_PENDING,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.COMMAND: PropertyDefinition(
            PropertyIdentifier.COMMAND,
            NetworkPortCommand,
            PropertyAccess.READ_WRITE,
            required=True,
            default=NetworkPortCommand.IDLE,
        ),
        PropertyIdentifier.MAC_ADDRESS: PropertyDefinition(
            PropertyIdentifier.MAC_ADDRESS,
            bytes,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.APDU_LENGTH: PropertyDefinition(
            PropertyIdentifier.APDU_LENGTH,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=1476,
        ),
        PropertyIdentifier.LINK_SPEED: PropertyDefinition(
            PropertyIdentifier.LINK_SPEED,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        # BACnet/IP properties (Clause 12.56)
        PropertyIdentifier.BACNET_IP_MODE: PropertyDefinition(
            PropertyIdentifier.BACNET_IP_MODE,
            IPMode,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IP_ADDRESS: PropertyDefinition(
            PropertyIdentifier.IP_ADDRESS,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BACNET_IP_UDP_PORT: PropertyDefinition(
            PropertyIdentifier.BACNET_IP_UDP_PORT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IP_SUBNET_MASK: PropertyDefinition(
            PropertyIdentifier.IP_SUBNET_MASK,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IP_DEFAULT_GATEWAY: PropertyDefinition(
            PropertyIdentifier.IP_DEFAULT_GATEWAY,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IP_DHCP_ENABLE: PropertyDefinition(
            PropertyIdentifier.IP_DHCP_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IP_DNS_SERVER: PropertyDefinition(
            PropertyIdentifier.IP_DNS_SERVER,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BBMD_ACCEPT_FD_REGISTRATIONS: PropertyDefinition(
            PropertyIdentifier.BBMD_ACCEPT_FD_REGISTRATIONS,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BBMD_BROADCAST_DISTRIBUTION_TABLE: PropertyDefinition(
            PropertyIdentifier.BBMD_BROADCAST_DISTRIBUTION_TABLE,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.FD_BBMD_ADDRESS: PropertyDefinition(
            PropertyIdentifier.FD_BBMD_ADDRESS,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BACNET_IP_NAT_TRAVERSAL: PropertyDefinition(
            PropertyIdentifier.BACNET_IP_NAT_TRAVERSAL,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BACNET_IP_GLOBAL_ADDRESS: PropertyDefinition(
            PropertyIdentifier.BACNET_IP_GLOBAL_ADDRESS,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        # BACnet/IPv6 properties (Clause 12.56, Annex U)
        PropertyIdentifier.BACNET_IPV6_MODE: PropertyDefinition(
            PropertyIdentifier.BACNET_IPV6_MODE,
            IPMode,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BACNET_IPV6_UDP_PORT: PropertyDefinition(
            PropertyIdentifier.BACNET_IPV6_UDP_PORT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BACNET_IPV6_MULTICAST_ADDRESS: PropertyDefinition(
            PropertyIdentifier.BACNET_IPV6_MULTICAST_ADDRESS,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IPV6_ADDRESS: PropertyDefinition(
            PropertyIdentifier.IPV6_ADDRESS,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IPV6_PREFIX_LENGTH: PropertyDefinition(
            PropertyIdentifier.IPV6_PREFIX_LENGTH,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IPV6_DEFAULT_GATEWAY: PropertyDefinition(
            PropertyIdentifier.IPV6_DEFAULT_GATEWAY,
            bytes,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IPV6_DNS_SERVER: PropertyDefinition(
            PropertyIdentifier.IPV6_DNS_SERVER,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.IPV6_AUTO_ADDRESSING_ENABLE: PropertyDefinition(
            PropertyIdentifier.IPV6_AUTO_ADDRESSING_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.VIRTUAL_MAC_ADDRESS_TABLE: PropertyDefinition(
            PropertyIdentifier.VIRTUAL_MAC_ADDRESS_TABLE,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        # MS/TP specific (optional)
        PropertyIdentifier.MAX_MASTER: PropertyDefinition(
            PropertyIdentifier.MAX_MASTER,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MAX_INFO_FRAMES: PropertyDefinition(
            PropertyIdentifier.MAX_INFO_FRAMES,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(
        self,
        instance_number: int,
        *,
        network_type: NetworkType = NetworkType.IPV4,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        self._set_default(PropertyIdentifier.NETWORK_TYPE, network_type)
        self._init_status_flags()
