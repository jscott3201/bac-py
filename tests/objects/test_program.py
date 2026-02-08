"""Tests for BACnet Program object (Clause 12.22)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.program import ProgramObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ErrorCode,
    ObjectType,
    ProgramChange,
    ProgramState,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestProgramObject:
    """Tests for ProgramObject (Clause 12.22)."""

    def test_create_basic(self):
        prog = ProgramObject(1)
        assert prog.object_identifier == ObjectIdentifier(ObjectType.PROGRAM, 1)

    def test_object_type(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.PROGRAM

    def test_program_state_default(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.PROGRAM_STATE) == ProgramState.IDLE

    def test_program_state_read_only(self):
        prog = ProgramObject(1)
        with pytest.raises(BACnetError) as exc_info:
            prog.write_property(PropertyIdentifier.PROGRAM_STATE, ProgramState.RUNNING)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_program_change_default(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.PROGRAM_CHANGE) == ProgramChange.READY

    def test_program_change_writable(self):
        prog = ProgramObject(1)
        prog.write_property(PropertyIdentifier.PROGRAM_CHANGE, ProgramChange.RUN)
        assert prog.read_property(PropertyIdentifier.PROGRAM_CHANGE) == ProgramChange.RUN

    def test_status_flags_initialized(self):
        prog = ProgramObject(1)
        sf = prog.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_out_of_service_default(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_out_of_service_writable(self):
        prog = ProgramObject(1)
        prog.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        assert prog.read_property(PropertyIdentifier.OUT_OF_SERVICE) is True

    def test_reason_for_halt_optional(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.REASON_FOR_HALT) is None

    def test_description_of_halt_optional(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.DESCRIPTION_OF_HALT) is None

    def test_description_optional(self):
        prog = ProgramObject(1)
        assert prog.read_property(PropertyIdentifier.DESCRIPTION) is None

    def test_not_commandable(self):
        prog = ProgramObject(1)
        assert prog._priority_array is None

    def test_property_list(self):
        prog = ProgramObject(1)
        plist = prog.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PROGRAM_STATE in plist
        assert PropertyIdentifier.PROGRAM_CHANGE in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.OUT_OF_SERVICE in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.PROGRAM, 8)
        assert isinstance(obj, ProgramObject)

    def test_initial_properties(self):
        prog = ProgramObject(1, object_name="PROG-1", description="Main control")
        assert prog.read_property(PropertyIdentifier.OBJECT_NAME) == "PROG-1"
        assert prog.read_property(PropertyIdentifier.DESCRIPTION) == "Main control"

    def test_program_state_values(self):
        """Verify all ProgramState enum values."""
        assert ProgramState.IDLE == 0
        assert ProgramState.LOADING == 1
        assert ProgramState.RUNNING == 2
        assert ProgramState.WAITING == 3
        assert ProgramState.HALTED == 4
        assert ProgramState.UNLOADING == 5

    def test_program_change_values(self):
        """Verify all ProgramChange enum values."""
        assert ProgramChange.READY == 0
        assert ProgramChange.LOAD == 1
        assert ProgramChange.RUN == 2
        assert ProgramChange.HALT == 3
        assert ProgramChange.RESTART == 4
        assert ProgramChange.UNLOAD == 5
