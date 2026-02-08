"""Write property examples for bac-py.

Demonstrates writing single properties, writing with priority,
and writing multiple properties to remote BACnet devices.

Note: WriteProperty and WritePropertyMultiple expect raw
application-tagged encoded bytes for the property value. Use
the encoding helpers in bac_py.encoding.primitives to build
these byte sequences.
"""

import asyncio

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient
from bac_py.encoding.primitives import (
    encode_application_character_string,
    encode_application_enumerated,
    encode_application_real,
    encode_application_unsigned,
)
from bac_py.network.address import BACnetAddress
from bac_py.services.errors import BACnetError, BACnetTimeoutError
from bac_py.services.write_property_multiple import (
    PropertyValue,
    WriteAccessSpecification,
)
from bac_py.types.enums import BinaryPV, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


def make_address(ip: str, port: int = 0xBAC0) -> BACnetAddress:
    """Build a BACnetAddress from an IP string and port."""
    parts = [int(p) for p in ip.split(".")]
    mac = bytes(parts) + port.to_bytes(2, "big")
    return BACnetAddress(mac_address=mac)


async def write_analog_value() -> None:
    """Write a floating-point value to an Analog Value object.

    Encodes the value as an application-tagged REAL and sends
    a WriteProperty request.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

        # Encode a float as application-tagged REAL bytes
        value_bytes = encode_application_real(72.5)

        try:
            await client.write_property(
                target,
                obj_id,
                PropertyIdentifier.PRESENT_VALUE,
                value=value_bytes,
            )
            print("Successfully wrote 72.5 to Analog Value 1")

        except BACnetError as e:
            print(f"Write failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Write timed out")


async def write_with_priority() -> None:
    """Write a value with a specific priority level.

    BACnet commandable objects use a 16-level priority array.
    Priority 1 is highest (manual-life-safety), priority 16 is lowest.
    Common priorities:
      - 1: Manual-Life-Safety
      - 2: Automatic-Life-Safety
      - 8: Manual-Operator
      - 16: Available (default/lowest)
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1)

        # Write a setpoint at priority 8 (Manual-Operator)
        value_bytes = encode_application_real(55.0)

        try:
            await client.write_property(
                target,
                obj_id,
                PropertyIdentifier.PRESENT_VALUE,
                value=value_bytes,
                priority=8,
            )
            print("Wrote 55.0 to Analog Output 1 at priority 8")

        except BACnetError as e:
            print(f"Write failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Write timed out")


async def write_binary_output() -> None:
    """Write to a Binary Output object.

    Binary values use the BinaryPV enumeration (INACTIVE=0, ACTIVE=1),
    encoded as an application-tagged ENUMERATED.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.BINARY_OUTPUT, 1)

        # Encode ACTIVE as an application-tagged enumerated value
        value_bytes = encode_application_enumerated(BinaryPV.ACTIVE)

        try:
            await client.write_property(
                target,
                obj_id,
                PropertyIdentifier.PRESENT_VALUE,
                value=value_bytes,
                priority=8,
            )
            print("Set Binary Output 1 to ACTIVE at priority 8")

        except BACnetError as e:
            print(f"Write failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Write timed out")


async def write_object_name() -> None:
    """Write a string property (Object_Name) to a remote object."""
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

        # Encode a string as application-tagged CharacterString
        value_bytes = encode_application_character_string("Zone Temperature Setpoint")

        try:
            await client.write_property(
                target,
                obj_id,
                PropertyIdentifier.OBJECT_NAME,
                value=value_bytes,
            )
            print("Updated object name to 'Zone Temperature Setpoint'")

        except BACnetError as e:
            print(f"Write failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Write timed out")


async def write_property_multiple() -> None:
    """Write multiple properties across multiple objects in a single request.

    Each WriteAccessSpecification targets one object and includes
    a list of PropertyValue entries to write.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        # Write two properties to Analog Value 1
        av_spec = WriteAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
            list_of_properties=[
                PropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    property_value=encode_application_real(68.0),
                ),
                PropertyValue(
                    property_identifier=PropertyIdentifier.DESCRIPTION,
                    property_value=encode_application_character_string("Heating setpoint"),
                ),
            ],
        )

        # Write to Analog Value 2 with a priority
        av2_spec = WriteAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 2),
            list_of_properties=[
                PropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    property_value=encode_application_real(74.0),
                    priority=8,
                ),
            ],
        )

        try:
            await client.write_property_multiple(target, [av_spec, av2_spec])
            print("Successfully wrote multiple properties")

        except BACnetError as e:
            print(f"Write failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Write timed out")


async def write_multistate_value() -> None:
    """Write to a Multi-State Value object.

    Multi-state values are 1-based unsigned integers representing
    the active state (1..Number_Of_States).
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.MULTI_STATE_VALUE, 1)

        # Encode state 3 as an application-tagged unsigned integer
        value_bytes = encode_application_unsigned(3)

        try:
            await client.write_property(
                target,
                obj_id,
                PropertyIdentifier.PRESENT_VALUE,
                value=value_bytes,
            )
            print("Set Multi-State Value 1 to state 3")

        except BACnetError as e:
            print(f"Write failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Write timed out")


if __name__ == "__main__":
    print("=== Write Analog Value ===")
    asyncio.run(write_analog_value())

    print("\n=== Write with Priority ===")
    asyncio.run(write_with_priority())

    print("\n=== Write Binary Output ===")
    asyncio.run(write_binary_output())

    print("\n=== Write Object Name ===")
    asyncio.run(write_object_name())

    print("\n=== Write Property Multiple ===")
    asyncio.run(write_property_multiple())

    print("\n=== Write Multi-State Value ===")
    asyncio.run(write_multistate_value())
