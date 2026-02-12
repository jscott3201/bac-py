"""BIBB (BACnet Interoperability Building Block) conformance matrix.

Auto-detects which BIBBs are supported by introspecting registered
service handlers per ASHRAE 135-2020 Annex K.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bac_py.types.enums import ConfirmedServiceChoice, UnconfirmedServiceChoice

if TYPE_CHECKING:
    from bac_py.services.base import ServiceRegistry


@dataclass(frozen=True, slots=True)
class BIBBDefinition:
    """A BIBB definition with required services."""

    name: str
    """BIBB identifier (e.g. 'DS-RP-B')."""

    description: str
    """Human-readable description."""

    confirmed_services: frozenset[ConfirmedServiceChoice] = field(
        default_factory=frozenset
    )
    """Confirmed services required for this BIBB."""

    unconfirmed_services: frozenset[UnconfirmedServiceChoice] = field(
        default_factory=frozenset
    )
    """Unconfirmed services required for this BIBB."""

    role: str = "A"
    """'A' = client/initiator, 'B' = server/responder."""


# BIBB definitions per Annex K
_BIBB_DEFINITIONS: list[BIBBDefinition] = [
    # --- Data Sharing ---
    BIBBDefinition(
        name="DS-RP-A",
        description="Data Sharing - ReadProperty - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.READ_PROPERTY}),
        role="A",
    ),
    BIBBDefinition(
        name="DS-RP-B",
        description="Data Sharing - ReadProperty - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.READ_PROPERTY}),
        role="B",
    ),
    BIBBDefinition(
        name="DS-RPM-A",
        description="Data Sharing - ReadPropertyMultiple - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE}),
        role="A",
    ),
    BIBBDefinition(
        name="DS-RPM-B",
        description="Data Sharing - ReadPropertyMultiple - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE}),
        role="B",
    ),
    BIBBDefinition(
        name="DS-WP-A",
        description="Data Sharing - WriteProperty - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.WRITE_PROPERTY}),
        role="A",
    ),
    BIBBDefinition(
        name="DS-WP-B",
        description="Data Sharing - WriteProperty - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.WRITE_PROPERTY}),
        role="B",
    ),
    BIBBDefinition(
        name="DS-WPM-A",
        description="Data Sharing - WritePropertyMultiple - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE}),
        role="A",
    ),
    BIBBDefinition(
        name="DS-WPM-B",
        description="Data Sharing - WritePropertyMultiple - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE}),
        role="B",
    ),
    BIBBDefinition(
        name="DS-COV-A",
        description="Data Sharing - COV - A (Client/Subscriber)",
        confirmed_services=frozenset({ConfirmedServiceChoice.SUBSCRIBE_COV}),
        role="A",
    ),
    BIBBDefinition(
        name="DS-COV-B",
        description="Data Sharing - COV - B (Server/Notifier)",
        confirmed_services=frozenset({ConfirmedServiceChoice.SUBSCRIBE_COV}),
        role="B",
    ),
    # --- Alarm and Event ---
    BIBBDefinition(
        name="AE-N-A",
        description="Alarm & Event - Notification - A (Client/Notification Source)",
        confirmed_services=frozenset(
            {ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION}
        ),
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.UNCONFIRMED_EVENT_NOTIFICATION}
        ),
        role="A",
    ),
    BIBBDefinition(
        name="AE-N-B",
        description="Alarm & Event - Notification - B (Server/Notification Sink)",
        confirmed_services=frozenset(
            {ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION}
        ),
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.UNCONFIRMED_EVENT_NOTIFICATION}
        ),
        role="B",
    ),
    BIBBDefinition(
        name="AE-ACK-A",
        description="Alarm & Event - Acknowledgment - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.ACKNOWLEDGE_ALARM}),
        role="A",
    ),
    BIBBDefinition(
        name="AE-ACK-B",
        description="Alarm & Event - Acknowledgment - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.ACKNOWLEDGE_ALARM}),
        role="B",
    ),
    BIBBDefinition(
        name="AE-INFO-A",
        description="Alarm & Event - GetEventInformation - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.GET_EVENT_INFORMATION}),
        role="A",
    ),
    BIBBDefinition(
        name="AE-INFO-B",
        description="Alarm & Event - GetEventInformation - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.GET_EVENT_INFORMATION}),
        role="B",
    ),
    BIBBDefinition(
        name="AE-ASUM-A",
        description="Alarm & Event - GetAlarmSummary - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.GET_ALARM_SUMMARY}),
        role="A",
    ),
    BIBBDefinition(
        name="AE-ASUM-B",
        description="Alarm & Event - GetAlarmSummary - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.GET_ALARM_SUMMARY}),
        role="B",
    ),
    BIBBDefinition(
        name="AE-ESUM-A",
        description="Alarm & Event - GetEnrollmentSummary - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.GET_ENROLLMENT_SUMMARY}),
        role="A",
    ),
    BIBBDefinition(
        name="AE-ESUM-B",
        description="Alarm & Event - GetEnrollmentSummary - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.GET_ENROLLMENT_SUMMARY}),
        role="B",
    ),
    # --- Device Management ---
    BIBBDefinition(
        name="DM-DDB-A",
        description="Device Management - Dynamic Device Binding - A (Client)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.WHO_IS, UnconfirmedServiceChoice.I_AM}
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-DDB-B",
        description="Device Management - Dynamic Device Binding - B (Server)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.WHO_IS, UnconfirmedServiceChoice.I_AM}
        ),
        role="B",
    ),
    BIBBDefinition(
        name="DM-DOB-A",
        description="Device Management - Dynamic Object Binding - A (Client)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.WHO_HAS, UnconfirmedServiceChoice.I_HAVE}
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-DOB-B",
        description="Device Management - Dynamic Object Binding - B (Server)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.WHO_HAS, UnconfirmedServiceChoice.I_HAVE}
        ),
        role="B",
    ),
    BIBBDefinition(
        name="DM-DCC-A",
        description="Device Management - DeviceCommunicationControl - A (Client)",
        confirmed_services=frozenset(
            {ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL}
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-DCC-B",
        description="Device Management - DeviceCommunicationControl - B (Server)",
        confirmed_services=frozenset(
            {ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL}
        ),
        role="B",
    ),
    BIBBDefinition(
        name="DM-RD-A",
        description="Device Management - ReinitializeDevice - A (Client)",
        confirmed_services=frozenset({ConfirmedServiceChoice.REINITIALIZE_DEVICE}),
        role="A",
    ),
    BIBBDefinition(
        name="DM-RD-B",
        description="Device Management - ReinitializeDevice - B (Server)",
        confirmed_services=frozenset({ConfirmedServiceChoice.REINITIALIZE_DEVICE}),
        role="B",
    ),
    BIBBDefinition(
        name="DM-TS-A",
        description="Device Management - TimeSynchronization - A (Client)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.TIME_SYNCHRONIZATION}
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-TS-B",
        description="Device Management - TimeSynchronization - B (Server)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.TIME_SYNCHRONIZATION}
        ),
        role="B",
    ),
    BIBBDefinition(
        name="DM-UTC-A",
        description="Device Management - UTCTimeSynchronization - A (Client)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION}
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-UTC-B",
        description="Device Management - UTCTimeSynchronization - B (Server)",
        unconfirmed_services=frozenset(
            {UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION}
        ),
        role="B",
    ),
    # --- File Access ---
    BIBBDefinition(
        name="DM-BR-A",
        description="Device Management - Backup/Restore - A (Client)",
        confirmed_services=frozenset(
            {
                ConfirmedServiceChoice.REINITIALIZE_DEVICE,
                ConfirmedServiceChoice.ATOMIC_READ_FILE,
                ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
                ConfirmedServiceChoice.READ_PROPERTY,
            }
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-BR-B",
        description="Device Management - Backup/Restore - B (Server)",
        confirmed_services=frozenset(
            {
                ConfirmedServiceChoice.REINITIALIZE_DEVICE,
                ConfirmedServiceChoice.ATOMIC_READ_FILE,
                ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
                ConfirmedServiceChoice.READ_PROPERTY,
            }
        ),
        role="B",
    ),
    # --- Object Access ---
    BIBBDefinition(
        name="DM-OCD-A",
        description="Device Management - Object Creation/Deletion - A (Client)",
        confirmed_services=frozenset(
            {
                ConfirmedServiceChoice.CREATE_OBJECT,
                ConfirmedServiceChoice.DELETE_OBJECT,
            }
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-OCD-B",
        description="Device Management - Object Creation/Deletion - B (Server)",
        confirmed_services=frozenset(
            {
                ConfirmedServiceChoice.CREATE_OBJECT,
                ConfirmedServiceChoice.DELETE_OBJECT,
            }
        ),
        role="B",
    ),
    BIBBDefinition(
        name="DM-LM-A",
        description="Device Management - List Manipulation - A (Client)",
        confirmed_services=frozenset(
            {
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
            }
        ),
        role="A",
    ),
    BIBBDefinition(
        name="DM-LM-B",
        description="Device Management - List Manipulation - B (Server)",
        confirmed_services=frozenset(
            {
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
            }
        ),
        role="B",
    ),
]


class BIBBMatrix:
    """Determine which BIBBs are supported by a BACnet application.

    The matrix checks registered service handlers against the
    requirements for each BIBB definition.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry

    def supported_bibbs(self) -> list[BIBBDefinition]:
        """Return all BIBBs for which required services are registered."""
        result: list[BIBBDefinition] = []
        for bibb in _BIBB_DEFINITIONS:
            if self._is_supported(bibb):
                result.append(bibb)
        return result

    def supported_bibb_names(self) -> list[str]:
        """Return names of all supported BIBBs."""
        return [b.name for b in self.supported_bibbs()]

    def generate_matrix(self) -> dict[str, dict[str, str | bool]]:
        """Generate a matrix dict mapping BIBB name → info."""
        matrix: dict[str, dict[str, str | bool]] = {}
        for bibb in _BIBB_DEFINITIONS:
            matrix[bibb.name] = {
                "description": bibb.description,
                "role": bibb.role,
                "supported": self._is_supported(bibb),
            }
        return matrix

    def _is_supported(self, bibb: BIBBDefinition) -> bool:
        """Check if all services required by a BIBB are registered.

        For 'B' (server) role, checks that the service handler exists
        in the registry. For 'A' (client) role, we assume the client
        can initiate any service, so A-role BIBBs are always supported.
        """
        if bibb.role == "A":
            return True

        # B-role: check server handlers
        return all(
            svc.value in self._registry._confirmed for svc in bibb.confirmed_services
        ) and all(
            svc.value in self._registry._unconfirmed
            for svc in bibb.unconfirmed_services
        )
