"""Tests for BIBB conformance matrix per Annex K."""

from bac_py.conformance.bibb import BIBBMatrix
from bac_py.services.base import ServiceRegistry
from bac_py.types.enums import ConfirmedServiceChoice, UnconfirmedServiceChoice


async def _noop_confirmed(service_choice, data, source):
    return None


async def _noop_unconfirmed(service_choice, data, source):
    return None


def _make_registry(*confirmed, unconfirmed=()) -> ServiceRegistry:
    """Create a registry with specified services registered."""
    reg = ServiceRegistry()
    for svc in confirmed:
        reg.register_confirmed(svc, _noop_confirmed)
    for svc in unconfirmed:
        reg.register_unconfirmed(svc, _noop_unconfirmed)
    return reg


class TestBIBBMatrixEmpty:
    def test_empty_registry_a_roles_supported(self):
        reg = _make_registry()
        matrix = BIBBMatrix(reg)
        bibbs = matrix.supported_bibb_names()
        # A-roles are always supported (client can always initiate)
        assert "DS-RP-A" in bibbs
        assert "DS-WP-A" in bibbs
        assert "DM-DDB-A" in bibbs

    def test_empty_registry_b_roles_not_supported(self):
        reg = _make_registry()
        matrix = BIBBMatrix(reg)
        bibbs = matrix.supported_bibb_names()
        # B-roles require handlers to be registered
        assert "DS-RP-B" not in bibbs
        assert "DS-WP-B" not in bibbs


class TestBIBBMatrixWithServices:
    def test_read_property_b_supported(self):
        reg = _make_registry(ConfirmedServiceChoice.READ_PROPERTY)
        matrix = BIBBMatrix(reg)
        bibbs = matrix.supported_bibb_names()
        assert "DS-RP-B" in bibbs

    def test_write_property_b_supported(self):
        reg = _make_registry(ConfirmedServiceChoice.WRITE_PROPERTY)
        matrix = BIBBMatrix(reg)
        bibbs = matrix.supported_bibb_names()
        assert "DS-WP-B" in bibbs

    def test_rpm_b_supported(self):
        reg = _make_registry(ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE)
        matrix = BIBBMatrix(reg)
        bibbs = matrix.supported_bibb_names()
        assert "DS-RPM-B" in bibbs

    def test_wpm_b_supported(self):
        reg = _make_registry(ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE)
        matrix = BIBBMatrix(reg)
        bibbs = matrix.supported_bibb_names()
        assert "DS-WPM-B" in bibbs

    def test_ddb_b_requires_both_who_is_and_i_am(self):
        # Only WHO_IS registered
        reg = _make_registry(
            unconfirmed=(UnconfirmedServiceChoice.WHO_IS,),
        )
        matrix = BIBBMatrix(reg)
        assert "DM-DDB-B" not in matrix.supported_bibb_names()

        # Both registered
        reg = _make_registry(
            unconfirmed=(
                UnconfirmedServiceChoice.WHO_IS,
                UnconfirmedServiceChoice.I_AM,
            ),
        )
        matrix = BIBBMatrix(reg)
        assert "DM-DDB-B" in matrix.supported_bibb_names()

    def test_cov_b_supported(self):
        reg = _make_registry(ConfirmedServiceChoice.SUBSCRIBE_COV)
        matrix = BIBBMatrix(reg)
        assert "DS-COV-B" in matrix.supported_bibb_names()

    def test_alarm_notification_b(self):
        reg = _make_registry(
            ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION,
            unconfirmed=(UnconfirmedServiceChoice.UNCONFIRMED_EVENT_NOTIFICATION,),
        )
        matrix = BIBBMatrix(reg)
        assert "AE-N-B" in matrix.supported_bibb_names()

    def test_alarm_ack_b(self):
        reg = _make_registry(ConfirmedServiceChoice.ACKNOWLEDGE_ALARM)
        matrix = BIBBMatrix(reg)
        assert "AE-ACK-B" in matrix.supported_bibb_names()


class TestBIBBMatrixGenerateMatrix:
    def test_generate_matrix_structure(self):
        reg = _make_registry(ConfirmedServiceChoice.READ_PROPERTY)
        matrix = BIBBMatrix(reg)
        result = matrix.generate_matrix()
        assert isinstance(result, dict)
        assert "DS-RP-B" in result
        assert result["DS-RP-B"]["supported"] is True
        assert result["DS-RP-B"]["role"] == "B"
        assert "description" in result["DS-RP-B"]

    def test_generate_matrix_unsupported_shown(self):
        reg = _make_registry()
        matrix = BIBBMatrix(reg)
        result = matrix.generate_matrix()
        assert "DS-RP-B" in result
        assert result["DS-RP-B"]["supported"] is False


class TestBIBBMatrixBackupRestore:
    def test_backup_restore_b_requires_all_services(self):
        # Missing ATOMIC_READ_FILE
        reg = _make_registry(
            ConfirmedServiceChoice.REINITIALIZE_DEVICE,
            ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
            ConfirmedServiceChoice.READ_PROPERTY,
        )
        matrix = BIBBMatrix(reg)
        assert "DM-BR-B" not in matrix.supported_bibb_names()

        # All four registered
        reg = _make_registry(
            ConfirmedServiceChoice.REINITIALIZE_DEVICE,
            ConfirmedServiceChoice.ATOMIC_READ_FILE,
            ConfirmedServiceChoice.ATOMIC_WRITE_FILE,
            ConfirmedServiceChoice.READ_PROPERTY,
        )
        matrix = BIBBMatrix(reg)
        assert "DM-BR-B" in matrix.supported_bibb_names()

    def test_object_creation_deletion_b(self):
        reg = _make_registry(
            ConfirmedServiceChoice.CREATE_OBJECT,
            ConfirmedServiceChoice.DELETE_OBJECT,
        )
        matrix = BIBBMatrix(reg)
        assert "DM-OCD-B" in matrix.supported_bibb_names()
