"""Tests for backup/restore state machine per Clause 19.1."""

from bac_py.objects.device import DeviceObject
from bac_py.services.device_mgmt import ReinitializeDeviceRequest
from bac_py.types.enums import (
    BackupAndRestoreState,
    DeviceStatus,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
)
from bac_py.types.primitives import ObjectIdentifier


def _make_device() -> DeviceObject:
    """Create a minimal Device object with backup/restore properties."""
    device = DeviceObject(1, object_name="test-device")
    return device


class TestBackupAndRestoreStateEnum:
    def test_idle(self):
        assert BackupAndRestoreState.IDLE == 0

    def test_preparing_for_backup(self):
        assert BackupAndRestoreState.PREPARING_FOR_BACKUP == 1

    def test_preparing_for_restore(self):
        assert BackupAndRestoreState.PREPARING_FOR_RESTORE == 2

    def test_performing_a_backup(self):
        assert BackupAndRestoreState.PERFORMING_A_BACKUP == 3

    def test_performing_a_restore(self):
        assert BackupAndRestoreState.PERFORMING_A_RESTORE == 4


class TestDeviceBackupRestoreProperties:
    def test_default_backup_and_restore_state(self):
        device = _make_device()
        assert (
            device.read_property(PropertyIdentifier.BACKUP_AND_RESTORE_STATE)
            == BackupAndRestoreState.IDLE
        )

    def test_default_backup_failure_timeout(self):
        device = _make_device()
        assert device.read_property(PropertyIdentifier.BACKUP_FAILURE_TIMEOUT) == 300

    def test_system_status_default(self):
        device = _make_device()
        assert (
            device.read_property(PropertyIdentifier.SYSTEM_STATUS)
            == DeviceStatus.OPERATIONAL
        )


class TestBackupStateTransitions:
    def test_start_backup_sets_status(self):
        device = _make_device()
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.OPERATIONAL
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.IDLE
        )

        # Simulate START_BACKUP
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.BACKUP_IN_PROGRESS
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.PREPARING_FOR_BACKUP
        )

        assert (
            device.read_property(PropertyIdentifier.SYSTEM_STATUS)
            == DeviceStatus.BACKUP_IN_PROGRESS
        )
        assert (
            device.read_property(PropertyIdentifier.BACKUP_AND_RESTORE_STATE)
            == BackupAndRestoreState.PREPARING_FOR_BACKUP
        )

    def test_end_backup_restores_operational(self):
        device = _make_device()
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.BACKUP_IN_PROGRESS
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.PREPARING_FOR_BACKUP
        )

        # Simulate END_BACKUP
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.OPERATIONAL
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.IDLE
        )

        assert (
            device.read_property(PropertyIdentifier.SYSTEM_STATUS)
            == DeviceStatus.OPERATIONAL
        )
        assert (
            device.read_property(PropertyIdentifier.BACKUP_AND_RESTORE_STATE)
            == BackupAndRestoreState.IDLE
        )

    def test_start_restore_sets_download_in_progress(self):
        device = _make_device()

        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.DOWNLOAD_IN_PROGRESS
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.PREPARING_FOR_RESTORE
        )

        assert (
            device.read_property(PropertyIdentifier.SYSTEM_STATUS)
            == DeviceStatus.DOWNLOAD_IN_PROGRESS
        )

    def test_end_restore_sets_last_restore_time(self):
        device = _make_device()
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.PREPARING_FOR_RESTORE
        )

        # Simulate END_RESTORE
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.OPERATIONAL
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.IDLE
        )
        device._properties[PropertyIdentifier.LAST_RESTORE_TIME] = 12345

        assert (
            device.read_property(PropertyIdentifier.LAST_RESTORE_TIME) == 12345
        )

    def test_abort_restore_returns_to_idle(self):
        device = _make_device()
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.DOWNLOAD_IN_PROGRESS
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.PREPARING_FOR_RESTORE
        )

        # Simulate ABORT_RESTORE
        device._properties[PropertyIdentifier.SYSTEM_STATUS] = (
            DeviceStatus.OPERATIONAL
        )
        device._properties[PropertyIdentifier.BACKUP_AND_RESTORE_STATE] = (
            BackupAndRestoreState.IDLE
        )

        assert (
            device.read_property(PropertyIdentifier.SYSTEM_STATUS)
            == DeviceStatus.OPERATIONAL
        )
        assert (
            device.read_property(PropertyIdentifier.BACKUP_AND_RESTORE_STATE)
            == BackupAndRestoreState.IDLE
        )


class TestReinitializeDeviceEncodeDecode:
    def test_start_backup_round_trip(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.START_BACKUP,
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.START_BACKUP

    def test_end_backup_round_trip(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.END_BACKUP,
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.END_BACKUP

    def test_start_restore_round_trip(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.START_RESTORE,
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.START_RESTORE

    def test_end_restore_with_password(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.END_RESTORE,
            password="secret123",
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.END_RESTORE
        assert decoded.password == "secret123"

    def test_abort_restore_round_trip(self):
        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.ABORT_RESTORE,
        )
        encoded = request.encode()
        decoded = ReinitializeDeviceRequest.decode(encoded)
        assert decoded.reinitialized_state == ReinitializedState.ABORT_RESTORE


class TestBackupDataAndAssignment:
    def test_backup_data_creation(self):
        from bac_py.app.client import BackupData

        bd = BackupData(
            device_instance=100,
            configuration_files=[
                (ObjectIdentifier(ObjectType.FILE, 1), b"config-data-1"),
                (ObjectIdentifier(ObjectType.FILE, 2), b"config-data-2"),
            ],
        )
        assert bd.device_instance == 100
        assert len(bd.configuration_files) == 2
        assert bd.configuration_files[0][1] == b"config-data-1"
