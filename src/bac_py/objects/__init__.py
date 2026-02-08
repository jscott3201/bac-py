"""BACnet object types and property management."""

# Import object modules to trigger @register_object_type decorators.
from bac_py.objects import analog as _analog  # noqa: F401
from bac_py.objects import binary as _binary  # noqa: F401
from bac_py.objects import device as _device  # noqa: F401
from bac_py.objects import file as _file  # noqa: F401
from bac_py.objects import multistate as _multistate  # noqa: F401
from bac_py.objects import value_types as _value_types  # noqa: F401
from bac_py.objects import calendar as _calendar  # noqa: F401
from bac_py.objects import accumulator as _accumulator  # noqa: F401
from bac_py.objects import schedule as _schedule  # noqa: F401
from bac_py.objects import trendlog as _trendlog  # noqa: F401
from bac_py.objects import notification as _notification  # noqa: F401
from bac_py.objects import loop as _loop  # noqa: F401
from bac_py.objects import event_enrollment as _event_enrollment  # noqa: F401
from bac_py.objects import program as _program  # noqa: F401
