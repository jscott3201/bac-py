"""Server operations examples for bac-py.

Demonstrates how to create BACnet server devices that respond
to incoming requests from remote clients. Includes basic server
setup, custom service handlers, and COV notification serving.
"""

import asyncio
import logging

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.server import DefaultServerHandlers
from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject
from bac_py.objects.device import DeviceObject
from bac_py.objects.multistate import MultiStateInputObject
from bac_py.types.enums import (
    BinaryPV,
    EngineeringUnits,
    PropertyIdentifier,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def basic_server() -> None:
    """Run a minimal BACnet server device.

    Creates a device with a few objects and registers default
    service handlers so remote clients can read/write properties,
    discover the device, and subscribe to COV notifications.
    """
    config = DeviceConfig(
        instance_number=100,
        name="Simple-Device",
        vendor_name="Example Corp",
        vendor_id=999,
        interface="0.0.0.0",
        port=0xBAC0,
    )

    async with BACnetApplication(config) as app:
        # Create the required device object
        device = DeviceObject(
            instance_number=100,
            object_name="Simple-Device",
            vendor_name="Example Corp",
            vendor_identifier=999,
            model_name="Example-100",
            firmware_revision="1.0.0",
            application_software_version="1.0.0",
        )
        app.object_db.add(device)

        # Add some objects for clients to interact with
        app.object_db.add(
            AnalogInputObject(
                instance_number=1,
                object_name="Room Temperature",
                units=EngineeringUnits.DEGREES_CELSIUS,
                present_value=22.5,
                description="Main conference room temperature sensor",
            )
        )
        app.object_db.add(
            AnalogValueObject(
                instance_number=1,
                object_name="Temperature Setpoint",
                units=EngineeringUnits.DEGREES_CELSIUS,
                present_value=22.0,
                description="Desired room temperature",
            )
        )
        app.object_db.add(
            BinaryInputObject(
                instance_number=1,
                object_name="Occupancy Sensor",
                present_value=BinaryPV.ACTIVE,
                active_text="Occupied",
                inactive_text="Vacant",
            )
        )

        # Register the default service handlers. This enables:
        #   - ReadProperty / ReadPropertyMultiple
        #   - WriteProperty / WritePropertyMultiple
        #   - Who-Is / I-Am (device discovery)
        #   - Who-Has / I-Have (object discovery)
        #   - SubscribeCOV (change-of-value notifications)
        #   - ReadRange
        #   - DeviceCommunicationControl
        #   - ReinitializeDevice
        #   - AtomicReadFile / AtomicWriteFile
        #   - CreateObject / DeleteObject
        #   - TimeSynchronization / UTCTimeSynchronization
        handlers = DefaultServerHandlers(app, app.object_db, device)
        handlers.register()

        logger.info(
            "BACnet server started on %s:%d (device instance %d)",
            config.interface,
            config.port,
            config.instance_number,
        )
        logger.info("Objects served: %d", len(app.object_db.object_list))

        # Block until stopped (Ctrl+C or external signal)
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            logger.info("Server shutting down")


async def server_with_simulated_data() -> None:
    """Run a server that periodically updates its sensor values.

    Demonstrates how a real application would update object values
    based on hardware readings, calculations, or external data.
    Objects that have COV subscriptions will automatically notify
    subscribed clients when values change.
    """
    config = DeviceConfig(
        instance_number=200,
        name="Simulated-Controller",
        vendor_name="Example Corp",
        vendor_id=999,
        interface="0.0.0.0",
        port=0xBAC0,
    )

    async with BACnetApplication(config) as app:
        device = DeviceObject(
            instance_number=200,
            object_name="Simulated-Controller",
            vendor_name="Example Corp",
            vendor_identifier=999,
        )
        app.object_db.add(device)

        # Create sensor objects
        temp_sensor = AnalogInputObject(
            instance_number=1,
            object_name="Zone Temperature",
            units=EngineeringUnits.DEGREES_CELSIUS,
            present_value=20.0,
            cov_increment=0.5,
        )
        app.object_db.add(temp_sensor)

        humidity_sensor = AnalogInputObject(
            instance_number=2,
            object_name="Zone Humidity",
            units=EngineeringUnits.PERCENT_RELATIVE_HUMIDITY,
            present_value=45.0,
            cov_increment=2.0,
        )
        app.object_db.add(humidity_sensor)

        damper_output = AnalogOutputObject(
            instance_number=1,
            object_name="Damper Position",
            units=EngineeringUnits.PERCENT,
            present_value=50.0,
        )
        app.object_db.add(damper_output)

        fan_status = BinaryInputObject(
            instance_number=1,
            object_name="Fan Running",
            present_value=BinaryPV.INACTIVE,
        )
        app.object_db.add(fan_status)

        fan_command = BinaryOutputObject(
            instance_number=1,
            object_name="Fan Command",
        )
        app.object_db.add(fan_command)

        mode_input = MultiStateInputObject(
            instance_number=1,
            number_of_states=4,
            object_name="Operating Mode",
            state_text=["Off", "Heating", "Cooling", "Auto"],
            present_value=4,
        )
        app.object_db.add(mode_input)

        # Register handlers
        handlers = DefaultServerHandlers(app, app.object_db, device)
        handlers.register()

        logger.info("Simulated server started with %d objects", len(app.object_db.object_list))

        # Simulate changing sensor values
        import math

        base_temp = 20.0
        tick = 0

        try:
            while True:
                await asyncio.sleep(5)
                tick += 1

                # Simulate temperature oscillation (20-25 degrees)
                new_temp = base_temp + 2.5 * math.sin(tick * 0.1) + 2.5
                temp_sensor.write_property(PropertyIdentifier.PRESENT_VALUE, new_temp)

                # Simulate humidity changes (40-60%)
                new_humidity = 50.0 + 10.0 * math.cos(tick * 0.05)
                humidity_sensor.write_property(PropertyIdentifier.PRESENT_VALUE, new_humidity)

                # Toggle fan status every 20 ticks
                if tick % 20 == 0:
                    current = fan_status.read_property(PropertyIdentifier.PRESENT_VALUE)
                    new_status = (
                        BinaryPV.ACTIVE if current == BinaryPV.INACTIVE else BinaryPV.INACTIVE
                    )
                    fan_status.write_property(PropertyIdentifier.PRESENT_VALUE, new_status)
                    logger.info("Fan status changed to %s", new_status.name)

                if tick % 10 == 0:
                    logger.info(
                        "Sensor update: temp=%.1f C, humidity=%.1f %%",
                        new_temp,
                        new_humidity,
                    )

                # Check COV notifications for updated objects
                cov_mgr = app.cov_manager
                if cov_mgr is not None:
                    cov_mgr.check_and_notify(temp_sensor, PropertyIdentifier.PRESENT_VALUE)
                    cov_mgr.check_and_notify(humidity_sensor, PropertyIdentifier.PRESENT_VALUE)

        except asyncio.CancelledError:
            logger.info("Simulation stopped")


async def server_with_multiple_devices() -> None:
    """Run two independent BACnet devices on different ports.

    Each application instance acts as a separate BACnet device
    with its own instance number, objects, and service handlers.
    """
    config_a = DeviceConfig(
        instance_number=301,
        name="Device-A",
        vendor_name="Example Corp",
        vendor_id=999,
        interface="0.0.0.0",
        port=47808,
    )
    config_b = DeviceConfig(
        instance_number=302,
        name="Device-B",
        vendor_name="Example Corp",
        vendor_id=999,
        interface="0.0.0.0",
        port=47809,  # Different port for the second device
    )

    async with (
        BACnetApplication(config_a) as app_a,
        BACnetApplication(config_b) as app_b,
    ):
        # Set up Device A
        device_a = DeviceObject(
            instance_number=301,
            object_name="Device-A",
            vendor_name="Example Corp",
            vendor_identifier=999,
        )
        app_a.object_db.add(device_a)
        app_a.object_db.add(
            AnalogInputObject(
                instance_number=1,
                object_name="Sensor-A1",
                units=EngineeringUnits.DEGREES_CELSIUS,
                present_value=21.0,
            )
        )
        handlers_a = DefaultServerHandlers(app_a, app_a.object_db, device_a)
        handlers_a.register()

        # Set up Device B
        device_b = DeviceObject(
            instance_number=302,
            object_name="Device-B",
            vendor_name="Example Corp",
            vendor_identifier=999,
        )
        app_b.object_db.add(device_b)
        app_b.object_db.add(
            AnalogInputObject(
                instance_number=1,
                object_name="Sensor-B1",
                units=EngineeringUnits.DEGREES_CELSIUS,
                present_value=23.0,
            )
        )
        handlers_b = DefaultServerHandlers(app_b, app_b.object_db, device_b)
        handlers_b.register()

        logger.info("Device A (instance 301) running on port 47808")
        logger.info("Device B (instance 302) running on port 47809")

        # Both devices run concurrently
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            logger.info("Both devices shutting down")


if __name__ == "__main__":
    import sys

    examples = {
        "basic": basic_server,
        "simulated": server_with_simulated_data,
        "multi": server_with_multiple_devices,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in examples:
        print("Usage: python server_operations.py <example>")
        print()
        print("Available examples:")
        print("  basic      - Minimal BACnet server device")
        print("  simulated  - Server with simulated sensor data updates")
        print("  multi      - Two independent devices on different ports")
        sys.exit(1)

    example_name = sys.argv[1]
    print(f"Running '{example_name}' example (Ctrl+C to stop)...")

    try:
        asyncio.run(examples[example_name]())
    except KeyboardInterrupt:
        print("\nStopped.")
