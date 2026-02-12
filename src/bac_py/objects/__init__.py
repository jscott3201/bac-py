"""BACnet object types and property management.

Importing this package triggers ``@register_object_type`` decorators in
each object-type sub-module, populating the global object-type registry
used by :func:`bac_py.objects.base.create_object`.  No public names are
exported — all object classes and helpers should be imported from their
individual modules (e.g. ``bac_py.objects.analog``).
"""

# Import object modules to trigger @register_object_type decorators.
from bac_py.objects import access_control as _access_control  # noqa: F401
from bac_py.objects import accumulator as _accumulator  # noqa: F401
from bac_py.objects import alert_enrollment as _alert_enrollment  # noqa: F401
from bac_py.objects import analog as _analog  # noqa: F401
from bac_py.objects import audit_log as _audit_log  # noqa: F401
from bac_py.objects import audit_reporter as _audit_reporter  # noqa: F401
from bac_py.objects import averaging as _averaging  # noqa: F401
from bac_py.objects import binary as _binary  # noqa: F401
from bac_py.objects import calendar as _calendar  # noqa: F401
from bac_py.objects import channel as _channel  # noqa: F401
from bac_py.objects import command as _command  # noqa: F401
from bac_py.objects import device as _device  # noqa: F401
from bac_py.objects import event_enrollment as _event_enrollment  # noqa: F401
from bac_py.objects import event_log as _event_log  # noqa: F401
from bac_py.objects import file as _file  # noqa: F401
from bac_py.objects import global_group as _global_group  # noqa: F401
from bac_py.objects import group as _group  # noqa: F401
from bac_py.objects import life_safety as _life_safety  # noqa: F401
from bac_py.objects import lighting as _lighting  # noqa: F401
from bac_py.objects import load_control as _load_control  # noqa: F401
from bac_py.objects import loop as _loop  # noqa: F401
from bac_py.objects import multistate as _multistate  # noqa: F401
from bac_py.objects import network_port as _network_port  # noqa: F401
from bac_py.objects import notification as _notification  # noqa: F401
from bac_py.objects import notification_forwarder as _notification_forwarder  # noqa: F401
from bac_py.objects import program as _program  # noqa: F401
from bac_py.objects import pulse_converter as _pulse_converter  # noqa: F401
from bac_py.objects import schedule as _schedule  # noqa: F401
from bac_py.objects import staging as _staging  # noqa: F401
from bac_py.objects import structured_view as _structured_view  # noqa: F401
from bac_py.objects import timer as _timer  # noqa: F401
from bac_py.objects import transportation as _transportation  # noqa: F401
from bac_py.objects import trendlog as _trendlog  # noqa: F401
from bac_py.objects import trendlog_multiple as _trendlog_multiple  # noqa: F401
from bac_py.objects import value_types as _value_types  # noqa: F401

__all__: list[str] = []  # All imports are for registration side effects only.
