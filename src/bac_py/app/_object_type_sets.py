"""Shared object type classification sets.

Centralises the frozensets used by client, server, and COV logic
to decide how to encode/decode property values based on
object type (e.g. Real for analog, Enumerated for binary).
"""

from __future__ import annotations

from bac_py.types.enums import ObjectType

# Object types where Present_Value is Real (IEEE-754 float)
ANALOG_TYPES: frozenset[ObjectType] = frozenset(
    {
        ObjectType.ANALOG_INPUT,
        ObjectType.ANALOG_OUTPUT,
        ObjectType.ANALOG_VALUE,
        ObjectType.LARGE_ANALOG_VALUE,
    }
)

# Object types where Present_Value is Enumerated (BinaryPV)
BINARY_TYPES: frozenset[ObjectType] = frozenset(
    {
        ObjectType.BINARY_INPUT,
        ObjectType.BINARY_OUTPUT,
        ObjectType.BINARY_VALUE,
    }
)

# Object types where Present_Value is Unsigned
MULTISTATE_TYPES: frozenset[ObjectType] = frozenset(
    {
        ObjectType.MULTI_STATE_INPUT,
        ObjectType.MULTI_STATE_OUTPUT,
        ObjectType.MULTI_STATE_VALUE,
    }
)
