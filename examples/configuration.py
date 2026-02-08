"""Application and device configuration examples for bac-py.

Demonstrates various DeviceConfig options, object creation,
and object database management for building BACnet devices.
"""

import asyncio

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject, BinaryValueObject
from bac_py.objects.device import DeviceObject
from bac_py.objects.multistate import (
    MultiStateInputObject,
    MultiStateOutputObject,
    MultiStateValueObject,
)
from bac_py.types.enums import (
    BinaryPV,
    EngineeringUnits,
    PropertyIdentifier,
)


def basic_configuration() -> DeviceConfig:
    """Create a minimal device configuration.

    Only the instance_number is required. All other fields have defaults.
    """
    return DeviceConfig(instance_number=1)


def full_configuration() -> DeviceConfig:
    """Create a fully-specified device configuration.

    All available configuration parameters are shown.
    """
    return DeviceConfig(
        # Device identity
        instance_number=100,
        name="HVAC-Controller-01",
        vendor_name="ACME Building Controls",
        vendor_id=555,
        model_name="AC-3000",
        firmware_revision="2.1.0",
        application_software_version="1.0.0",
        # Network binding
        interface="192.168.1.50",  # Bind to specific interface
        port=0xBAC0,  # Standard BACnet port (47808)
        # APDU settings
        apdu_timeout=6000,  # Request timeout in milliseconds
        apdu_segment_timeout=2000,  # Segment timeout in milliseconds
        apdu_retries=3,  # Number of retries before giving up
        max_apdu_length=1476,  # Maximum APDU size in bytes
        max_segments=None,  # None = unlimited segmentation
    )


def client_only_configuration() -> DeviceConfig:
    """Create a configuration suitable for a client-only application.

    Uses instance 4194303 (the maximum/wildcard instance) and binds
    to all interfaces. Suitable for tools that only read/write
    remote devices without serving their own objects.
    """
    return DeviceConfig(
        instance_number=4194303,
        name="bacnet-client-tool",
        interface="0.0.0.0",
    )


def configure_device_object() -> DeviceObject:
    """Create and configure a DeviceObject with initial properties.

    The DeviceObject is the required root object for any BACnet device.
    It provides identity, capability, and protocol information.
    """
    device = DeviceObject(
        instance_number=100,
        object_name="Main Controller",
        vendor_name="ACME Building Controls",
        vendor_identifier=555,
        model_name="AC-3000",
        firmware_revision="2.1.0",
        application_software_version="1.0.0",
        description="Primary HVAC controller for Building A",
    )

    # Read back properties to verify
    print("Device Object Configuration:")
    print(f"  Object ID:    {device.object_identifier}")
    print(f"  Object Name:  {device.read_property(PropertyIdentifier.OBJECT_NAME)}")
    print(f"  Vendor Name:  {device.read_property(PropertyIdentifier.VENDOR_NAME)}")
    print(f"  Vendor ID:    {device.read_property(PropertyIdentifier.VENDOR_IDENTIFIER)}")
    print(f"  Model Name:   {device.read_property(PropertyIdentifier.MODEL_NAME)}")
    print(f"  Firmware Rev: {device.read_property(PropertyIdentifier.FIRMWARE_REVISION)}")
    print(f"  Description:  {device.read_property(PropertyIdentifier.DESCRIPTION)}")

    return device


def configure_analog_objects() -> list:
    """Create and configure Analog Input, Output, and Value objects.

    Demonstrates the different analog object types and their properties.
    """
    objects = []

    # Analog Input - represents a sensor reading (read-only present value)
    temp_sensor = AnalogInputObject(
        instance_number=1,
        object_name="Outside Air Temperature",
        description="Outdoor temperature sensor on north wall",
        units=EngineeringUnits.DEGREES_CELSIUS,
        present_value=22.5,
        min_pres_value=-40.0,
        max_pres_value=60.0,
        cov_increment=0.5,  # Notify on 0.5 degree change
    )
    objects.append(temp_sensor)

    # Analog Output - represents an actuator (commandable with priority array)
    damper = AnalogOutputObject(
        instance_number=1,
        object_name="Supply Air Damper",
        description="Main supply air damper position",
        units=EngineeringUnits.PERCENT,
        present_value=50.0,
        min_pres_value=0.0,
        max_pres_value=100.0,
        relinquish_default=50.0,
    )
    objects.append(damper)

    # Analog Value - represents a configuration parameter
    setpoint = AnalogValueObject(
        instance_number=1,
        object_name="Zone Temperature Setpoint",
        description="Target zone temperature",
        units=EngineeringUnits.DEGREES_CELSIUS,
        present_value=22.0,
    )
    objects.append(setpoint)

    # Analog Value with commandable priority array
    commandable_setpoint = AnalogValueObject(
        instance_number=2,
        commandable=True,
        object_name="Override Setpoint",
        description="Setpoint with priority override capability",
        units=EngineeringUnits.DEGREES_CELSIUS,
        present_value=21.0,
    )
    objects.append(commandable_setpoint)

    print("\nAnalog Objects:")
    for obj in objects:
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        name = obj.read_property(PropertyIdentifier.OBJECT_NAME)
        print(f"  {obj.object_identifier}: {name} = {pv}")

    return objects


def configure_binary_objects() -> list:
    """Create and configure Binary Input, Output, and Value objects."""
    objects = []

    # Binary Input - represents a digital sensor (read-only)
    fan_status = BinaryInputObject(
        instance_number=1,
        object_name="Supply Fan Status",
        description="Supply fan running status from VFD",
        present_value=BinaryPV.INACTIVE,
        active_text="Running",
        inactive_text="Stopped",
    )
    objects.append(fan_status)

    # Binary Output - represents a digital actuator (commandable)
    fan_cmd = BinaryOutputObject(
        instance_number=1,
        object_name="Supply Fan Command",
        description="Supply fan start/stop command",
        present_value=BinaryPV.INACTIVE,
        active_text="Start",
        inactive_text="Stop",
        relinquish_default=BinaryPV.INACTIVE,
    )
    objects.append(fan_cmd)

    # Binary Value - internal boolean state
    occ_mode = BinaryValueObject(
        instance_number=1,
        object_name="Occupied Mode",
        description="Building occupancy state",
        present_value=BinaryPV.ACTIVE,
        active_text="Occupied",
        inactive_text="Unoccupied",
    )
    objects.append(occ_mode)

    print("\nBinary Objects:")
    for obj in objects:
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        name = obj.read_property(PropertyIdentifier.OBJECT_NAME)
        print(f"  {obj.object_identifier}: {name} = {pv.name}")

    return objects


def configure_multistate_objects() -> list:
    """Create and configure Multi-State Input, Output, and Value objects."""
    objects = []

    # Multi-State Input - enumerated sensor with N states
    mode_input = MultiStateInputObject(
        instance_number=1,
        number_of_states=4,
        object_name="System Mode Feedback",
        description="Current operating mode from BMS",
        present_value=1,
        state_text=["Off", "Heating", "Cooling", "Auto"],
    )
    objects.append(mode_input)

    # Multi-State Output - enumerated command (commandable)
    mode_cmd = MultiStateOutputObject(
        instance_number=1,
        number_of_states=4,
        object_name="System Mode Command",
        description="Operating mode command",
        present_value=4,
        state_text=["Off", "Heat", "Cool", "Auto"],
        relinquish_default=4,
    )
    objects.append(mode_cmd)

    # Multi-State Value - enumerated configuration
    schedule_mode = MultiStateValueObject(
        instance_number=1,
        number_of_states=3,
        object_name="Schedule Mode",
        description="Active schedule selection",
        present_value=1,
        state_text=["Weekday", "Weekend", "Holiday"],
    )
    objects.append(schedule_mode)

    print("\nMulti-State Objects:")
    for obj in objects:
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        name = obj.read_property(PropertyIdentifier.OBJECT_NAME)
        print(f"  {obj.object_identifier}: {name} = state {pv}")

    return objects


async def build_complete_device() -> None:
    """Build a complete BACnet device with multiple object types.

    Demonstrates the full workflow of configuring a DeviceConfig,
    creating objects, adding them to the object database, and
    starting the application.
    """
    config = full_configuration()

    async with BACnetApplication(config) as app:
        # Create the device object
        device = DeviceObject(
            instance_number=config.instance_number,
            object_name=config.name,
            vendor_name=config.vendor_name,
            vendor_identifier=config.vendor_id,
            model_name=config.model_name,
            firmware_revision=config.firmware_revision,
            application_software_version=config.application_software_version,
        )
        app.object_db.add(device)

        # Add analog objects
        app.object_db.add(
            AnalogInputObject(
                instance_number=1,
                object_name="Zone Temperature",
                units=EngineeringUnits.DEGREES_CELSIUS,
                present_value=22.0,
            )
        )
        app.object_db.add(
            AnalogOutputObject(
                instance_number=1,
                object_name="Heating Valve",
                units=EngineeringUnits.PERCENT,
            )
        )
        app.object_db.add(
            AnalogValueObject(
                instance_number=1,
                object_name="Setpoint",
                units=EngineeringUnits.DEGREES_CELSIUS,
                present_value=22.0,
            )
        )

        # Add binary objects
        app.object_db.add(
            BinaryInputObject(
                instance_number=1,
                object_name="Fan Status",
                present_value=BinaryPV.INACTIVE,
            )
        )
        app.object_db.add(
            BinaryOutputObject(
                instance_number=1,
                object_name="Fan Command",
            )
        )

        # Add multi-state objects
        app.object_db.add(
            MultiStateInputObject(
                instance_number=1,
                number_of_states=3,
                object_name="Operating Mode",
            )
        )

        # Print the complete object list
        print("\nComplete Object Database:")
        for obj_id in app.object_db.object_list:
            obj = app.object_db.get(obj_id)
            if obj is not None:
                name = obj.read_property(PropertyIdentifier.OBJECT_NAME)
                print(f"  {obj_id}: {name}")

        print(f"\nTotal objects: {len(app.object_db.object_list)}")
        print("Device is ready to serve BACnet requests.")

        # In a real application, you would call app.run() or keep
        # the context manager open to serve requests indefinitely.


if __name__ == "__main__":
    print("=== Basic Configuration ===")
    cfg = basic_configuration()
    print(f"Instance: {cfg.instance_number}, Interface: {cfg.interface}:{cfg.port}")

    print("\n=== Full Configuration ===")
    cfg = full_configuration()
    print(f"Instance: {cfg.instance_number}, Name: {cfg.name}")
    print(f"Interface: {cfg.interface}:{cfg.port}")
    print(f"APDU: timeout={cfg.apdu_timeout}ms, retries={cfg.apdu_retries}")

    print("\n=== Client-Only Configuration ===")
    cfg = client_only_configuration()
    print(f"Instance: {cfg.instance_number}, Name: {cfg.name}")

    print("\n=== Device Object ===")
    configure_device_object()

    print("\n=== Analog Objects ===")
    configure_analog_objects()

    print("\n=== Binary Objects ===")
    configure_binary_objects()

    print("\n=== Multi-State Objects ===")
    configure_multistate_objects()

    print("\n=== Complete Device ===")
    asyncio.run(build_complete_device())
