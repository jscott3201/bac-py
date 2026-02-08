"""Read property examples for bac-py.

Demonstrates reading single properties, array-indexed properties,
and multiple properties from remote BACnet devices.
"""

import asyncio
import struct

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient
from bac_py.network.address import BACnetAddress
from bac_py.services.errors import (
    BACnetAbortError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)
from bac_py.services.read_property_multiple import (
    PropertyReference,
    ReadAccessSpecification,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


def make_address(ip: str, port: int = 0xBAC0) -> BACnetAddress:
    """Build a BACnetAddress from an IP string and port."""
    parts = [int(p) for p in ip.split(".")]
    mac = bytes(parts) + port.to_bytes(2, "big")
    return BACnetAddress(mac_address=mac)


async def read_single_property() -> None:
    """Read a single property from a remote device.

    Reads the Present_Value of Analog Input 1 on the target device.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

        try:
            ack = await client.read_property(
                target,
                obj_id,
                PropertyIdentifier.PRESENT_VALUE,
            )
            # ack.property_value contains application-tagged encoded bytes.
            # For a REAL value, decode the 4-byte IEEE 754 float after the
            # application tag (tag byte = 0x44, length = 4).
            raw = ack.property_value
            print(f"Object: {ack.object_identifier}")
            print(f"Property: {ack.property_identifier}")
            print(f"Raw value bytes: {raw.hex()}")

            # Decode a REAL (float) value from application-tagged bytes.
            # Application tag for REAL: tag number 4, length 4 -> header byte 0x44
            # The float data starts at offset 1.
            if len(raw) >= 5 and raw[0] == 0x44:
                value = struct.unpack("!f", raw[1:5])[0]
                print(f"Decoded float value: {value}")

        except BACnetError as e:
            print(f"BACnet error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Request timed out - device may be unreachable")


async def read_object_name() -> None:
    """Read the object name of a device."""
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        # Read the device object's name (device instance 1)
        device_id = ObjectIdentifier(ObjectType.DEVICE, 1)

        try:
            ack = await client.read_property(
                target,
                device_id,
                PropertyIdentifier.OBJECT_NAME,
            )
            print(f"Device object name (raw): {ack.property_value.hex()}")
        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Request timed out")


async def read_with_array_index() -> None:
    """Read an array-indexed property.

    Reads individual elements from the device's Object_List property.
    Index 0 returns the array length; indices 1..N return individual elements.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        device_id = ObjectIdentifier(ObjectType.DEVICE, 1)

        try:
            # Read the array length (index 0)
            ack = await client.read_property(
                target,
                device_id,
                PropertyIdentifier.OBJECT_LIST,
                array_index=0,
            )
            print(f"Object list length (raw): {ack.property_value.hex()}")

            # Read the first element (index 1)
            ack = await client.read_property(
                target,
                device_id,
                PropertyIdentifier.OBJECT_LIST,
                array_index=1,
            )
            print(f"First object in list (raw): {ack.property_value.hex()}")

        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Request timed out")


async def read_property_multiple() -> None:
    """Read multiple properties from one or more objects in a single request.

    More efficient than individual ReadProperty calls when you need
    several properties at once.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        # Read multiple properties from Analog Input 1
        ai_spec = ReadAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_property_references=[
                PropertyReference(PropertyIdentifier.OBJECT_NAME),
                PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                PropertyReference(PropertyIdentifier.UNITS),
                PropertyReference(PropertyIdentifier.DESCRIPTION),
            ],
        )

        # Read properties from Binary Input 1 in the same request
        bi_spec = ReadAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 1),
            list_of_property_references=[
                PropertyReference(PropertyIdentifier.OBJECT_NAME),
                PropertyReference(PropertyIdentifier.PRESENT_VALUE),
            ],
        )

        try:
            ack = await client.read_property_multiple(target, [ai_spec, bi_spec])

            for result in ack.list_of_read_access_results:
                print(f"\nObject: {result.object_identifier}")
                for elem in result.list_of_results:
                    if elem.property_value is not None:
                        print(f"  {elem.property_identifier.name}: {elem.property_value.hex()}")
                    elif elem.property_access_error is not None:
                        err_class, err_code = elem.property_access_error
                        print(
                            f"  {elem.property_identifier.name}: "
                            f"ERROR {err_class.name}/{err_code.name}"
                        )

        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Request timed out")


async def read_with_error_handling() -> None:
    """Demonstrate comprehensive error handling for read operations."""
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

        try:
            ack = await client.read_property(target, obj_id, PropertyIdentifier.PRESENT_VALUE)
            print(f"Value: {ack.property_value.hex()}")

        except BACnetError as e:
            # Protocol-level error (e.g., unknown object, unknown property)
            print(f"BACnet Error: {e.error_class.name} / {e.error_code.name}")

        except BACnetRejectError as e:
            # Request was syntactically invalid
            print(f"Rejected: {e.reason.name}")

        except BACnetAbortError as e:
            # Transaction was aborted
            print(f"Aborted: {e.reason.name}")

        except BACnetTimeoutError:
            # No response after all retries
            print("Timed out after all retries")


if __name__ == "__main__":
    print("=== Read Single Property ===")
    asyncio.run(read_single_property())

    print("\n=== Read Object Name ===")
    asyncio.run(read_object_name())

    print("\n=== Read with Array Index ===")
    asyncio.run(read_with_array_index())

    print("\n=== Read Property Multiple ===")
    asyncio.run(read_property_multiple())

    print("\n=== Read with Error Handling ===")
    asyncio.run(read_with_error_handling())
