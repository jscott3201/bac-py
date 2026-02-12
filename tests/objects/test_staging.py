"""Tests for the BACnet Staging object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestStagingObject:
    def test_instantiation(self):
        from bac_py.objects.staging import StagingObject
        from bac_py.types.enums import StagingState

        obj = StagingObject(1, object_name="staging-1")
        assert obj.OBJECT_TYPE == ObjectType.STAGING
        assert obj.read_property(PropertyIdentifier.STAGING_STATE) == StagingState.NOT_STAGED
