# Object Model Design

## 1. Overview

BACnet models every physical and logical element in a building automation system as an "object" with typed "properties" (Clause 12). This document defines how bac-py represents the BACnet object model for both server (hosting objects) and client (reading/writing remote objects) roles.

## 2. Object Type Inventory

The specification defines 60 standard object types. For initial implementation, we prioritize the commonly deployed types:

### Tier 1 - Core (Implement First)

| Object Type        | ID  | Primary Use                                                     |
| ------------------ | --- | --------------------------------------------------------------- |
| Device             | 8   | Represents the device itself. Required for every BACnet device. |
| Analog Input       | 0   | Sensor readings (temperature, pressure, etc.)                   |
| Analog Output      | 1   | Actuator setpoints (valve position, etc.)                       |
| Analog Value       | 2   | Configuration parameters, calculated values                     |
| Binary Input       | 3   | On/off sensor states (switch, occupancy)                        |
| Binary Output      | 4   | On/off actuator controls (relay, fan)                           |
| Binary Value       | 5   | On/off configuration/status values                              |
| Multi-State Input  | 13  | Enumerated sensor states (mode, status)                         |
| Multi-State Output | 14  | Enumerated actuator commands                                    |
| Multi-State Value  | 19  | Enumerated configuration values                                 |
| Network Port       | 56  | Network interface configuration                                 |

### Tier 2 - Extended Functionality

| Object Type        | ID  | Primary Use                         |
| ------------------ | --- | ----------------------------------- |
| Schedule           | 17  | Time-based scheduling               |
| Calendar           | 6   | Date-based exceptions for schedules |
| Trend Log          | 20  | Historical data logging             |
| Notification Class | 15  | Alarm/event notification routing    |
| Event Enrollment   | 9   | Alarm/event detection configuration |
| Loop               | 12  | PID control loops                   |
| File               | 10  | File transfer (firmware, config)    |
| Accumulator        | 23  | Pulse counting (energy meters)      |
| Program            | 16  | Application programs                |

### Tier 3 - Specialized

| Object Type                                             | ID    | Primary Use                    |
| ------------------------------------------------------- | ----- | ------------------------------ |
| Integer Value                                           | 45    | Integer configuration values   |
| Positive Integer Value                                  | 48    | Positive integer values        |
| CharacterString Value                                   | 40    | String values                  |
| Large Analog Value                                      | 46    | Double-precision analog values |
| DateTime Value                                          | 44    | Date/time values               |
| BitString Value                                         | 39    | Named bit collections          |
| OctetString Value                                       | 47    | Raw byte string values         |
| Structured View                                         | 29    | Organizational grouping        |
| Channel                                                 | 53    | High-speed group writes        |
| Lighting Output                                         | 54    | Lighting dimming control       |
| Timer                                                   | 31    | Timer/countdown objects        |
| Load Control                                            | 28    | Demand response                |
| Trend Log Multiple                                      | 27    | Multi-property trend logging   |
| Notification Forwarder                                  | 51    | Event notification forwarding  |
| Alert Enrollment                                        | 52    | Alert detection                |
| Access Door / Point / Zone / User / Rights / Credential | 30-36 | Access control                 |
| Elevator Group / Lift / Escalator                       | 57-59 | Vertical transportation        |

## 3. Base Object Architecture

### 3.1 Property Definition

Each property on a BACnet object has metadata:

```python
@dataclass(frozen=True, slots=True)
class PropertyDefinition:
    """Metadata for a single BACnet property."""
    identifier: PropertyIdentifier
    datatype: type                   # Expected Python type for the value
    access: PropertyAccess           # Read-only, read-write, or write-only
    required: bool                   # Required by the spec for this object type
    default: Any = None              # Default value if not explicitly set


class PropertyAccess(IntEnum):
    READ_ONLY = 0
    READ_WRITE = 1
    WRITE_ONLY = 2
```

### 3.2 Base Object Class

```python
class BACnetObject:
    """Base class for all BACnet objects.

    Each subclass defines its property schema via class-level
    PROPERTY_DEFINITIONS. Properties are stored in a dict and
    accessed via typed read/write methods.
    """

    # Subclasses override this
    OBJECT_TYPE: ClassVar[ObjectType]
    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]]

    def __init__(self, instance_number: int, **initial_properties: Any):
        self._object_id = ObjectIdentifier(self.OBJECT_TYPE, instance_number)
        self._properties: dict[PropertyIdentifier, Any] = {}
        self._priority_array: list[Any | None] | None = None

        # Set defaults from property definitions
        for prop_id, prop_def in self.PROPERTY_DEFINITIONS.items():
            if prop_def.default is not None:
                self._properties[prop_id] = prop_def.default

        # Set object-identifier and object-type (always required)
        self._properties[PropertyIdentifier.OBJECT_IDENTIFIER] = self._object_id
        self._properties[PropertyIdentifier.OBJECT_TYPE] = self.OBJECT_TYPE

        # Apply initial property overrides
        for key, value in initial_properties.items():
            prop_id = PropertyIdentifier[key.upper()]
            self._properties[prop_id] = value

    @property
    def object_identifier(self) -> ObjectIdentifier:
        return self._object_id

    def read_property(self, prop_id: PropertyIdentifier,
                      array_index: int | None = None) -> Any:
        """Read a property value.

        Raises BACnetError(PROPERTY, UNKNOWN_PROPERTY) if not found.
        Raises BACnetError(PROPERTY, INVALID_ARRAY_INDEX) if index invalid.
        """
        if prop_id == PropertyIdentifier.PROPERTY_LIST:
            return self._get_property_list()

        if prop_id not in self.PROPERTY_DEFINITIONS:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        value = self._properties.get(prop_id)
        if value is None and self.PROPERTY_DEFINITIONS[prop_id].required:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)

        if array_index is not None:
            if isinstance(value, (list, tuple)):
                if array_index == 0:
                    return len(value)
                if 1 <= array_index <= len(value):
                    return value[array_index - 1]
                raise BACnetError(ErrorClass.PROPERTY,
                                 ErrorCode.INVALID_ARRAY_INDEX)
            raise BACnetError(ErrorClass.PROPERTY,
                             ErrorCode.PROPERTY_IS_NOT_AN_ARRAY)

        return value

    def write_property(self, prop_id: PropertyIdentifier, value: Any,
                       priority: int | None = None,
                       array_index: int | None = None) -> None:
        """Write a property value.

        Raises BACnetError(PROPERTY, WRITE_ACCESS_DENIED) if read-only.
        """
        prop_def = self.PROPERTY_DEFINITIONS.get(prop_id)
        if prop_def is None:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY)
        if prop_def.access == PropertyAccess.READ_ONLY:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        # Handle commandable properties with priority array
        if self._is_commandable(prop_id) and priority is not None:
            self._write_with_priority(prop_id, value, priority)
        else:
            self._properties[prop_id] = value

    def _get_property_list(self) -> list[PropertyIdentifier]:
        """Return list of all properties present on this object."""
        return [pid for pid in self.PROPERTY_DEFINITIONS
                if pid in self._properties or
                self.PROPERTY_DEFINITIONS[pid].required]

    def _is_commandable(self, prop_id: PropertyIdentifier) -> bool:
        """Check if a property supports command prioritization (Clause 19.2)."""
        return (prop_id == PropertyIdentifier.PRESENT_VALUE and
                self._priority_array is not None)

    def _write_with_priority(self, prop_id: PropertyIdentifier,
                            value: Any, priority: int) -> None:
        """Write to a commandable property using the priority array.

        BACnet priority 1 = highest, 16 = lowest.
        Priority array index is 0-based internally (priority - 1).
        Priority 6 is reserved for Minimum On/Off and cannot be
        written by external WriteProperty requests (Clause 19.2.3).
        """
        if priority < 1 or priority > 16:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.VALUE_OUT_OF_RANGE)
        if priority == 6:
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.WRITE_ACCESS_DENIED)

        if self._priority_array is None:
            self._priority_array = [None] * 16

        if value is None:
            # Relinquish this priority level
            self._priority_array[priority - 1] = None
        else:
            self._priority_array[priority - 1] = value

        # Present Value = highest priority non-None value, or relinquish default
        for pv in self._priority_array:
            if pv is not None:
                self._properties[prop_id] = pv
                return
        # All relinquished - use relinquish default
        self._properties[prop_id] = self._properties.get(
            PropertyIdentifier.RELINQUISH_DEFAULT
        )
```

### 3.3 Object Database

```python
class ObjectDatabase:
    """Container for all BACnet objects in a device."""

    def __init__(self):
        self._objects: dict[ObjectIdentifier, BACnetObject] = {}

    def add(self, obj: BACnetObject) -> None:
        if obj.object_identifier in self._objects:
            raise BACnetError(ErrorClass.OBJECT,
                            ErrorCode.OBJECT_IDENTIFIER_ALREADY_EXISTS)
        self._objects[obj.object_identifier] = obj

    def remove(self, object_id: ObjectIdentifier) -> None:
        if object_id not in self._objects:
            raise BACnetError(ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        if object_id.object_type == ObjectType.DEVICE:
            raise BACnetError(ErrorClass.OBJECT,
                            ErrorCode.OBJECT_DELETION_NOT_PERMITTED)
        del self._objects[object_id]

    def get(self, object_id: ObjectIdentifier) -> BACnetObject | None:
        return self._objects.get(object_id)

    def get_objects_of_type(self, obj_type: ObjectType) -> list[BACnetObject]:
        return [o for o in self._objects.values()
                if o.object_identifier.object_type == obj_type]

    @property
    def object_list(self) -> list[ObjectIdentifier]:
        return list(self._objects.keys())

    def __len__(self) -> int:
        return len(self._objects)
```

## 4. Concrete Object Type Definitions

### 4.1 Device Object (Clause 12.11)

```python
class DeviceObject(BACnetObject):
    OBJECT_TYPE = ObjectType.DEVICE

    PROPERTY_DEFINITIONS = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER, ObjectIdentifier,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.OBJECT_NAME: PropertyDefinition(
            PropertyIdentifier.OBJECT_NAME, str,
            PropertyAccess.READ_WRITE, required=True),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE, ObjectType,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.SYSTEM_STATUS: PropertyDefinition(
            PropertyIdentifier.SYSTEM_STATUS, int,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.VENDOR_NAME: PropertyDefinition(
            PropertyIdentifier.VENDOR_NAME, str,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.VENDOR_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.VENDOR_IDENTIFIER, int,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.MODEL_NAME: PropertyDefinition(
            PropertyIdentifier.MODEL_NAME, str,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.FIRMWARE_REVISION: PropertyDefinition(
            PropertyIdentifier.FIRMWARE_REVISION, str,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.APPLICATION_SOFTWARE_VERSION: PropertyDefinition(
            PropertyIdentifier.APPLICATION_SOFTWARE_VERSION, str,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.PROTOCOL_VERSION: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_VERSION, int,
            PropertyAccess.READ_ONLY, required=True, default=1),
        PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_SERVICES_SUPPORTED, BitString,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_OBJECT_TYPES_SUPPORTED, BitString,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.OBJECT_LIST: PropertyDefinition(
            PropertyIdentifier.OBJECT_LIST, list,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED: PropertyDefinition(
            PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED, int,
            PropertyAccess.READ_ONLY, required=True, default=1476),
        PropertyIdentifier.SEGMENTATION_SUPPORTED: PropertyDefinition(
            PropertyIdentifier.SEGMENTATION_SUPPORTED, Segmentation,
            PropertyAccess.READ_ONLY, required=True, default=Segmentation.BOTH),
        PropertyIdentifier.MAX_SEGMENTS_ACCEPTED: PropertyDefinition(
            PropertyIdentifier.MAX_SEGMENTS_ACCEPTED, int,
            PropertyAccess.READ_ONLY, required=True, default=64),
        PropertyIdentifier.APDU_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.APDU_TIMEOUT, int,
            PropertyAccess.READ_WRITE, required=True, default=6000),
        PropertyIdentifier.NUMBER_OF_APDU_RETRIES: PropertyDefinition(
            PropertyIdentifier.NUMBER_OF_APDU_RETRIES, int,
            PropertyAccess.READ_WRITE, required=True, default=3),
        PropertyIdentifier.APDU_SEGMENT_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.APDU_SEGMENT_TIMEOUT, int,
            PropertyAccess.READ_WRITE, required=True, default=2000),
        PropertyIdentifier.DEVICE_ADDRESS_BINDING: PropertyDefinition(
            PropertyIdentifier.DEVICE_ADDRESS_BINDING, list,
            PropertyAccess.READ_ONLY, required=True, default=[]),
        PropertyIdentifier.DATABASE_REVISION: PropertyDefinition(
            PropertyIdentifier.DATABASE_REVISION, int,
            PropertyAccess.READ_ONLY, required=True, default=0),
        PropertyIdentifier.PROTOCOL_REVISION: PropertyDefinition(
            PropertyIdentifier.PROTOCOL_REVISION, int,
            PropertyAccess.READ_ONLY, required=True, default=22),  # 135-2016
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST, list,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION, str,
            PropertyAccess.READ_WRITE, required=False),
        # ... additional optional properties
    }
```

### 4.2 Analog Input Object (Clause 12.2)

```python
class AnalogInputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.ANALOG_INPUT

    PROPERTY_DEFINITIONS = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER, ObjectIdentifier,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.OBJECT_NAME: PropertyDefinition(
            PropertyIdentifier.OBJECT_NAME, str,
            PropertyAccess.READ_WRITE, required=True),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE, ObjectType,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE, float,
            PropertyAccess.READ_ONLY, required=True, default=0.0),
        PropertyIdentifier.STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.STATUS_FLAGS, BitString,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.EVENT_STATE: PropertyDefinition(
            PropertyIdentifier.EVENT_STATE, EventState,
            PropertyAccess.READ_ONLY, required=True, default=EventState.NORMAL),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE, bool,
            PropertyAccess.READ_WRITE, required=True, default=False),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS, int,
            PropertyAccess.READ_WRITE, required=True, default=95),  # no-units
        # Optional properties
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION, str,
            PropertyAccess.READ_WRITE, required=False),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY, int,
            PropertyAccess.READ_ONLY, required=False),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT, float,
            PropertyAccess.READ_WRITE, required=False),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE, float,
            PropertyAccess.READ_ONLY, required=False),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE, float,
            PropertyAccess.READ_ONLY, required=False),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST, list,
            PropertyAccess.READ_ONLY, required=True),
    }
```

### 4.3 Analog Output Object (Clause 12.3)

Analog Output is commandable - it has a priority array:

```python
class AnalogOutputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.ANALOG_OUTPUT

    def __init__(self, instance_number: int, commandable: bool = True,
                 **kwargs: Any):
        super().__init__(instance_number, **kwargs)
        # Initialize 16-level priority array for commandable property
        if commandable:
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = 0.0

    PROPERTY_DEFINITIONS = {
        # ... same required properties as AnalogInput plus:
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE, float,
            PropertyAccess.READ_WRITE, required=True, default=0.0),
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY, list,
            PropertyAccess.READ_ONLY, required=True),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT, float,
            PropertyAccess.READ_WRITE, required=True, default=0.0),
        # ... additional properties
    }
```

### 4.4 Pattern for Binary and Multi-State Types

Binary types follow the same structure but with `bool` or `int` present values and active/inactive text. Multi-state types use `int` present values with a `number_of_states` property:

```python
class BinaryInputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.BINARY_INPUT
    # Present_Value is BACnetBinaryPV enum (0=inactive, 1=active)
    # Has polarity, active_text, inactive_text properties

class BinaryOutputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.BINARY_OUTPUT
    # Commandable (has priority array)
    # Has minimum_on_time, minimum_off_time

class MultiStateInputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.MULTI_STATE_INPUT
    # Present_Value is 1-based unsigned integer
    # Has number_of_states, state_text properties

class MultiStateOutputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.MULTI_STATE_OUTPUT
    # Commandable (has priority array)
    # Has number_of_states, state_text properties
```

## 5. Command Prioritization (Clause 19.2)

Commandable properties (Present_Value on output and some value objects) use a 16-level priority array:

| Priority | Typical Use                                            |
| -------- | ------------------------------------------------------ |
| 1        | Manual-Life Safety                                     |
| 2        | Automatic-Life Safety                                  |
| 3        | Available                                              |
| 4        | Available                                              |
| 5        | Critical Equipment Control                             |
| 6        | Minimum On/Off (reserved — written only by the device) |
| 7        | Available                                              |
| 8        | Manual Operator                                        |
| 9        | Available                                              |
| 10       | Available                                              |
| 11       | Available                                              |
| 12       | Available                                              |
| 13       | Available                                              |
| 14       | Available                                              |
| 15       | Available                                              |
| 16       | Available (lowest priority / default)                  |

Writing `None` (Null) to a priority level relinquishes it. The highest-priority (lowest number) non-None value becomes the Present_Value.

## 6. COV (Change of Value) Support

Objects that support COV reporting must track subscriptions and notify subscribers when values change:

```python
class EventState(IntEnum):
    """BACnet EventState enumeration (Clause 12.12.26)."""
    NORMAL = 0
    FAULT = 1
    OFFNORMAL = 2
    HIGH_LIMIT = 3
    LOW_LIMIT = 4
    LIFE_SAFETY_ALARM = 5


class COVMixin:
    """Mixin for objects that support COV (Change of Value) reporting."""

    def __init__(self):
        self._cov_subscriptions: list[COVSubscription] = []
        self._last_reported_value: Any = None

    def add_cov_subscription(self, subscription: COVSubscription) -> None:
        self._cov_subscriptions.append(subscription)

    def remove_cov_subscription(self, process_id: int,
                                subscriber: BACnetAddress) -> None:
        self._cov_subscriptions = [
            s for s in self._cov_subscriptions
            if not (s.process_id == process_id and
                    s.subscriber == subscriber)
        ]

    def check_cov(self, property_id: PropertyIdentifier,
                  new_value: Any) -> bool:
        """Check if value change exceeds COV increment for notification."""
        cov_increment = self._properties.get(PropertyIdentifier.COV_INCREMENT)
        if cov_increment is not None:
            if isinstance(new_value, (int, float)):
                if self._last_reported_value is None:
                    return True
                return abs(new_value - self._last_reported_value) >= cov_increment
        # Binary and multi-state: any change triggers COV
        return new_value != self._last_reported_value


@dataclass(frozen=True, slots=True)
class COVSubscription:
    subscriber: BACnetAddress
    process_id: int
    monitored_object: ObjectIdentifier
    confirmed: bool
    lifetime: float | None    # None = indefinite
    created_at: float         # monotonic time
```

## 7. Status Flags

Every I/O object has a StatusFlags bit string (4 bits):

```python
class StatusFlags:
    """BACnet StatusFlags bit string."""
    __slots__ = ('in_alarm', 'fault', 'overridden', 'out_of_service')

    def __init__(self, in_alarm: bool = False, fault: bool = False,
                 overridden: bool = False, out_of_service: bool = False):
        self.in_alarm = in_alarm
        self.fault = fault
        self.overridden = overridden
        self.out_of_service = out_of_service

    def to_bit_string(self) -> BitString:
        value = (self.in_alarm << 3) | (self.fault << 2) | \
                (self.overridden << 1) | self.out_of_service
        return BitString(bytes([value << 4]), unused_bits=4)
```

## 8. Object Factory

A registry-based factory for creating objects by type:

```python
_OBJECT_REGISTRY: dict[ObjectType, type[BACnetObject]] = {}

def register_object_type(cls: type[BACnetObject]) -> type[BACnetObject]:
    """Class decorator to register an object type."""
    _OBJECT_REGISTRY[cls.OBJECT_TYPE] = cls
    return cls

def create_object(object_type: ObjectType, instance_number: int,
                  **properties: Any) -> BACnetObject:
    """Create a BACnet object by type."""
    cls = _OBJECT_REGISTRY.get(object_type)
    if cls is None:
        raise BACnetError(ErrorClass.OBJECT,
                         ErrorCode.DYNAMIC_CREATION_NOT_SUPPORTED)
    return cls(instance_number, **properties)

# Registration
@register_object_type
class AnalogInputObject(BACnetObject):
    OBJECT_TYPE = ObjectType.ANALOG_INPUT
    ...
```
