"""Tests for the BACnet Structured View object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestStructuredViewObject:
    def test_instantiation(self):
        from bac_py.objects.structured_view import StructuredViewObject
        from bac_py.types.enums import NodeType

        obj = StructuredViewObject(1, object_name="sv-1")
        assert obj.OBJECT_TYPE == ObjectType.STRUCTURED_VIEW
        assert obj.read_property(PropertyIdentifier.NODE_TYPE) == NodeType.UNKNOWN
        assert obj.read_property(PropertyIdentifier.SUBORDINATE_LIST) == []
