"""BACnet object types and property management."""

# Import object modules to trigger @register_object_type decorators.
from bac_py.objects import analog as _analog  # noqa: F401
from bac_py.objects import binary as _binary  # noqa: F401
from bac_py.objects import device as _device  # noqa: F401
from bac_py.objects import multistate as _multistate  # noqa: F401
