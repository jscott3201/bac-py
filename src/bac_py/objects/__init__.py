"""BACnet object types and property management.

Importing this package triggers ``@register_object_type`` decorators in
each object-type sub-module, populating the global object-type registry
used by :func:`bac_py.objects.base.create_object`.  No public names are
exported — all object classes and helpers should be imported from their
individual modules (e.g. ``bac_py.objects.analog``).
"""

# Import object modules to trigger @register_object_type decorators.
from bac_py.objects import accumulator as _accumulator  # noqa: F401
from bac_py.objects import analog as _analog  # noqa: F401
from bac_py.objects import binary as _binary  # noqa: F401
from bac_py.objects import calendar as _calendar  # noqa: F401
from bac_py.objects import device as _device  # noqa: F401
from bac_py.objects import event_enrollment as _event_enrollment  # noqa: F401
from bac_py.objects import file as _file  # noqa: F401
from bac_py.objects import loop as _loop  # noqa: F401
from bac_py.objects import multistate as _multistate  # noqa: F401
from bac_py.objects import notification as _notification  # noqa: F401
from bac_py.objects import program as _program  # noqa: F401
from bac_py.objects import schedule as _schedule  # noqa: F401
from bac_py.objects import trendlog as _trendlog  # noqa: F401
from bac_py.objects import value_types as _value_types  # noqa: F401

__all__: list[str] = []  # All imports are for registration side effects only.
