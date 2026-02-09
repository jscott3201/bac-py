"""Property encoding completeness tests.

Validates that all default property values stored in every registered
BACnet object type can be encoded via encode_property_value without error.
This catches cases where a property stores a constructed type that the
encoder doesn't handle.
"""

import pytest

import bac_py.objects  # noqa: F401 (triggers @register_object_type)
from bac_py.encoding.primitives import encode_property_value
from bac_py.objects.base import _OBJECT_REGISTRY, create_object
from bac_py.types.enums import ObjectType, PropertyIdentifier


def _object_type_ids() -> list[tuple[ObjectType, str]]:
    """Return (ObjectType, name) pairs for all registered types."""
    return [(ot, ot.name) for ot in sorted(_OBJECT_REGISTRY.keys(), key=lambda x: x.value)]


@pytest.mark.parametrize(
    "obj_type",
    [ot for ot, _ in _object_type_ids()],
    ids=[name for _, name in _object_type_ids()],
)
class TestPropertyEncodingCompleteness:
    """Every property with a non-None value on a freshly created object
    must be encodable via encode_property_value.
    """

    def test_all_default_properties_encodable(self, obj_type: ObjectType):
        """Encode every non-None property on a default-constructed object."""
        # Some object types need constructor args
        kwargs = _constructor_kwargs(obj_type)
        obj = create_object(obj_type, 1, **kwargs)

        failed = []
        for prop_id in obj.PROPERTY_DEFINITIONS:
            value = obj._properties.get(prop_id)
            if value is None:
                continue
            try:
                encoded = encode_property_value(value)
                assert isinstance(encoded, bytes), (
                    f"{prop_id.name}: encode_property_value returned "
                    f"{type(encoded).__name__}, expected bytes"
                )
            except (TypeError, ValueError) as exc:
                failed.append(f"{prop_id.name}: {exc}")

        assert not failed, (
            f"{obj_type.name} has {len(failed)} unencodable default properties:\n"
            + "\n".join(f"  - {f}" for f in failed)
        )

    def test_property_list_encodable(self, obj_type: ObjectType):
        """The Property_List itself should be encodable."""
        kwargs = _constructor_kwargs(obj_type)
        obj = create_object(obj_type, 1, **kwargs)
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        encoded = encode_property_value(prop_list)
        assert isinstance(encoded, bytes)


def _constructor_kwargs(obj_type: ObjectType) -> dict:
    """Return any special constructor kwargs needed for certain object types."""
    if obj_type in (
        ObjectType.MULTI_STATE_INPUT,
        ObjectType.MULTI_STATE_OUTPUT,
        ObjectType.MULTI_STATE_VALUE,
    ):
        return {"number_of_states": 3}
    return {}
