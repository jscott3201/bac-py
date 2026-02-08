"""Device discovery example for bac-py.

Connects to predefined BACnet demo devices, discovers all objects
(points) on each device, reads their properties, and writes the
full results to a JSON file.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient
from bac_py.encoding.primitives import (
    decode_character_string,
    decode_double,
    decode_object_identifier,
    decode_real,
    decode_signed,
    decode_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
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
from bac_py.types.enums import EngineeringUnits, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

logger = logging.getLogger(__name__)

LOG_FILE = "examples/device_discovery.log"


def setup_logging() -> None:
    """Configure verbose logging to both console and a log file."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler - captures everything at DEBUG level
    fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler - INFO and above so the terminal stays readable
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)


DEMO_DEVICES = []

# Properties to read from the Device object
DEVICE_PROPERTIES = [
    PropertyIdentifier.OBJECT_NAME,
    PropertyIdentifier.VENDOR_NAME,
    PropertyIdentifier.VENDOR_IDENTIFIER,
    PropertyIdentifier.MODEL_NAME,
    PropertyIdentifier.DESCRIPTION,
    PropertyIdentifier.FIRMWARE_REVISION,
    PropertyIdentifier.APPLICATION_SOFTWARE_VERSION,
    PropertyIdentifier.LOCATION,
    PropertyIdentifier.PROTOCOL_VERSION,
]

# Properties to read from each discovered point
POINT_PROPERTIES = [
    PropertyIdentifier.OBJECT_NAME,
    PropertyIdentifier.PRESENT_VALUE,
    PropertyIdentifier.DESCRIPTION,
    PropertyIdentifier.UNITS,
    PropertyIdentifier.STATUS_FLAGS,
]


def make_address(ip: str, port: int = 0xBAC0) -> BACnetAddress:
    """Build a BACnetAddress from an IP string and port."""
    parts = [int(p) for p in ip.split(".")]
    mac = bytes(parts) + port.to_bytes(2, "big")
    return BACnetAddress(mac_address=mac)


def _object_type_name(obj_type: int) -> str:
    """Return the ObjectType enum name, or the raw int as a string."""
    try:
        return ObjectType(obj_type).name
    except ValueError:
        return str(obj_type)


def decode_application_value(raw: bytes) -> str | float | int | bool | None:
    """Decode a single application-tagged value to a Python type."""
    if not raw:
        return None

    tag, offset = decode_tag(raw, 0)
    if tag.cls != TagClass.APPLICATION:
        return raw.hex()

    data = raw[offset : offset + tag.length]

    match tag.number:
        case 0:  # Null
            return None
        case 1:  # Boolean
            return tag.length != 0
        case 2:  # Unsigned Integer
            return decode_unsigned(data)
        case 3:  # Signed Integer
            return decode_signed(data)
        case 4:  # Real
            return round(decode_real(data), 4)
        case 5:  # Double
            return round(decode_double(data), 6)
        case 6:  # Octet String
            return bytes(data).hex()
        case 7:  # Character String
            return decode_character_string(data)
        case 8:  # Bit String
            return bytes(data).hex()
        case 9:  # Enumerated
            return decode_unsigned(data)
        case 10:  # Date
            if len(data) >= 4:
                year = data[0] + 1900 if data[0] != 0xFF else 0
                return f"{year}-{data[1]:02d}-{data[2]:02d}"
            return bytes(data).hex()
        case 11:  # Time
            if len(data) >= 4:
                return f"{data[0]:02d}:{data[1]:02d}:{data[2]:02d}"
            return bytes(data).hex()
        case 12:  # Object Identifier
            obj_type, instance = decode_object_identifier(data)
            return f"{_object_type_name(obj_type)}:{instance}"
        case _:
            return bytes(data).hex()


def decode_object_list(raw: bytes) -> list[tuple[int, int]]:
    """Decode a sequence of application-tagged object identifiers."""
    results = []
    offset = 0
    mv = memoryview(raw)
    while offset < len(mv):
        tag, new_offset = decode_tag(mv, offset)
        if tag.cls == TagClass.APPLICATION and tag.number == 12:
            obj_type, instance = decode_object_identifier(mv[new_offset : new_offset + tag.length])
            results.append((obj_type, instance))
        offset = new_offset + tag.length
    return results


def format_property_value(
    prop: PropertyIdentifier,
    value: int | str | float | bool | None,
) -> str | float | int | bool | None:
    """Resolve known enumerated property values to readable names."""
    if not isinstance(value, int):
        return value
    if prop == PropertyIdentifier.UNITS:
        try:
            return EngineeringUnits(value).name
        except ValueError:
            return value
    if prop == PropertyIdentifier.OBJECT_TYPE:
        return _object_type_name(value)
    return value


async def read_device_info(
    client: BACnetClient,
    address: BACnetAddress,
    instance: int,
) -> dict:
    """Read device object properties, falling back to individual reads."""
    device_id = ObjectIdentifier(ObjectType.DEVICE, instance)
    spec = ReadAccessSpecification(
        object_identifier=device_id,
        list_of_property_references=[PropertyReference(p) for p in DEVICE_PROPERTIES],
    )

    info: dict = {}
    logger.debug(
        "ReadPropertyMultiple for DEVICE:%d – %d properties", instance, len(DEVICE_PROPERTIES)
    )
    try:
        ack = await client.read_property_multiple(address, [spec])
        for result in ack.list_of_read_access_results:
            for elem in result.list_of_results:
                prop = elem.property_identifier
                if elem.property_value is not None:
                    value = decode_application_value(elem.property_value)
                    info[prop.name] = format_property_value(prop, value)
                    logger.debug(
                        "  %s = %s (raw %s)", prop.name, info[prop.name], elem.property_value.hex()
                    )
                elif elem.property_access_error is not None:
                    err_class, err_code = elem.property_access_error
                    info[prop.name] = f"ERROR: {err_class.name}/{err_code.name}"
                    logger.debug(
                        "  %s -> access error %s/%s", prop.name, err_class.name, err_code.name
                    )
    except (BACnetError, BACnetRejectError, BACnetAbortError) as exc:
        logger.warning(
            "ReadPropertyMultiple not supported (DEVICE:%d): %s – falling back to individual reads",
            instance,
            exc,
        )
        for prop in DEVICE_PROPERTIES:
            try:
                ack = await client.read_property(address, device_id, prop)
                value = decode_application_value(ack.property_value)
                info[prop.name] = format_property_value(prop, value)
                logger.debug("  %s = %s", prop.name, info[prop.name])
            except (BACnetError, BACnetTimeoutError) as inner:
                info[prop.name] = "unavailable"
                logger.debug("  %s -> unavailable (%s)", prop.name, inner)
    except BACnetTimeoutError:
        info["error"] = "timeout"
        logger.warning("Timeout reading device info for DEVICE:%d", instance)

    return info


async def discover_object_list(
    client: BACnetClient,
    address: BACnetAddress,
    instance: int,
) -> list[tuple[int, int]]:
    """Discover the full object list from a device.

    Tries an unindexed read first (returns the entire list in one
    response).  If that fails (e.g. the response is too large),
    falls back to reading array index 0 for the count and then
    fetching each element individually.
    """
    device_id = ObjectIdentifier(ObjectType.DEVICE, instance)

    # Attempt 1 - full list in a single read
    logger.debug("Attempting unindexed OBJECT_LIST read for DEVICE:%d", instance)
    try:
        ack = await client.read_property(
            address,
            device_id,
            PropertyIdentifier.OBJECT_LIST,
        )
        result = decode_object_list(ack.property_value)
        logger.debug(
            "Unindexed read returned %d objects (%d bytes)", len(result), len(ack.property_value)
        )
        return result
    except (BACnetError, BACnetAbortError) as exc:
        logger.debug("Unindexed OBJECT_LIST read failed: %s – trying indexed reads", exc)

    # Attempt 2 - indexed reads
    objects: list[tuple[int, int]] = []
    try:
        logger.debug("Reading OBJECT_LIST array length (index 0)")
        ack = await client.read_property(
            address,
            device_id,
            PropertyIdentifier.OBJECT_LIST,
            array_index=0,
        )
        count = decode_application_value(ack.property_value)
        if not isinstance(count, int):
            logger.warning("OBJECT_LIST length is not an integer: %s", count)
            return objects
        logger.debug("OBJECT_LIST contains %d elements", count)

        for i in range(1, count + 1):
            try:
                ack = await client.read_property(
                    address,
                    device_id,
                    PropertyIdentifier.OBJECT_LIST,
                    array_index=i,
                )
                tag, tag_off = decode_tag(ack.property_value, 0)
                if tag.number == 12:
                    obj_type, inst = decode_object_identifier(
                        ack.property_value[tag_off : tag_off + tag.length]
                    )
                    objects.append((obj_type, inst))
                    logger.debug("  [%d] %s:%d", i, _object_type_name(obj_type), inst)
            except (BACnetError, BACnetTimeoutError) as exc:
                logger.debug("  [%d] failed: %s", i, exc)
                continue
    except (BACnetError, BACnetTimeoutError) as exc:
        logger.warning("Cannot read OBJECT_LIST for DEVICE:%d: %s", instance, exc)

    return objects


async def read_point_properties(
    client: BACnetClient,
    address: BACnetAddress,
    obj_type: int,
    instance: int,
) -> dict:
    """Read properties from a single point/object."""
    type_name = _object_type_name(obj_type)
    obj_id = ObjectIdentifier(ObjectType(obj_type), instance)

    # Choose which properties to request based on object type.
    # The Device object has no PRESENT_VALUE; non-analog objects have no UNITS.
    props = [PropertyIdentifier.OBJECT_NAME, PropertyIdentifier.DESCRIPTION]

    if obj_type != ObjectType.DEVICE:
        props.append(PropertyIdentifier.PRESENT_VALUE)
        props.append(PropertyIdentifier.STATUS_FLAGS)

    if obj_type in (
        ObjectType.ANALOG_INPUT,
        ObjectType.ANALOG_OUTPUT,
        ObjectType.ANALOG_VALUE,
    ):
        props.append(PropertyIdentifier.UNITS)

    point: dict = {"object_type": type_name, "instance": instance}

    logger.debug(
        "ReadPropertyMultiple %s:%d – properties %s", type_name, instance, [p.name for p in props]
    )
    try:
        spec = ReadAccessSpecification(
            object_identifier=obj_id,
            list_of_property_references=[PropertyReference(p) for p in props],
        )
        ack = await client.read_property_multiple(address, [spec])
        for result in ack.list_of_read_access_results:
            for elem in result.list_of_results:
                prop = elem.property_identifier
                if elem.property_value is not None:
                    value = decode_application_value(elem.property_value)
                    point[prop.name] = format_property_value(prop, value)
                    logger.debug(
                        "  %s = %s (raw %s)",
                        prop.name,
                        point[prop.name],
                        elem.property_value.hex(),
                    )
                elif elem.property_access_error is not None:
                    err_class, err_code = elem.property_access_error
                    point[prop.name] = f"ERROR: {err_class.name}/{err_code.name}"
                    logger.debug(
                        "  %s -> access error %s/%s", prop.name, err_class.name, err_code.name
                    )
    except (BACnetError, BACnetRejectError, BACnetAbortError) as exc:
        logger.warning(
            "RPM failed for %s:%d (%s) – falling back to individual reads",
            type_name,
            instance,
            exc,
        )
        for prop in props:
            try:
                ack = await client.read_property(address, obj_id, prop)
                value = decode_application_value(ack.property_value)
                point[prop.name] = format_property_value(prop, value)
                logger.debug("  %s = %s", prop.name, point[prop.name])
            except (BACnetError, BACnetTimeoutError) as inner:
                point[prop.name] = "unavailable"
                logger.debug("  %s -> unavailable (%s)", prop.name, inner)
    except BACnetTimeoutError:
        point["error"] = "timeout"
        logger.warning("Timeout reading %s:%d", type_name, instance)

    return point


async def discover_device(
    client: BACnetClient,
    ip: str,
    instance: int,
    port: int,
) -> dict:
    """Run full point discovery on a single device."""
    logger.info("=" * 60)
    logger.info("Device at %s:%d  (instance %d)", ip, port, instance)
    logger.info("=" * 60)
    address = make_address(ip, port)
    device: dict = {"ip": ip, "port": port, "instance": instance}

    # 1. Device info
    logger.info("  Reading device info...")
    device["device_info"] = await read_device_info(client, address, instance)
    dev_name = device["device_info"].get("OBJECT_NAME", "unknown")
    logger.info("  Device name: %s", dev_name)

    # 2. Discover object list
    logger.info("  Discovering object list...")
    object_list = await discover_object_list(client, address, instance)
    logger.info("  Discovered %d objects", len(object_list))

    # 3. Read every point
    device["points"] = []
    for idx, (obj_type, obj_instance) in enumerate(object_list, 1):
        label = f"{_object_type_name(obj_type)}:{obj_instance}"
        logger.info("  [%d/%d] %s", idx, len(object_list), label)
        point = await read_point_properties(client, address, obj_type, obj_instance)
        device["points"].append(point)

    return device


async def main() -> None:
    """Discover all points on the demo devices and write to JSON."""
    setup_logging()

    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    logger.info("Starting BACnet device discovery...")
    logger.debug(
        "Scanner config: instance=%d, interface=%s, port=%d",
        config.instance_number,
        config.interface,
        config.port,
    )
    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        results: dict = {
            "scan_timestamp": datetime.now(UTC).isoformat(),
            "scanner_instance": config.instance_number,
            "devices": [],
        }

        for entry in DEMO_DEVICES:
            device = await discover_device(
                client,
                entry["ip"],
                entry["instance"],
                entry["port"],
            )
            results["devices"].append(device)

    output_file = "examples/device_discovery_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    logger.info("=" * 60)
    logger.info("Discovery complete")
    logger.info("=" * 60)
    total_points = sum(len(d["points"]) for d in results["devices"])
    logger.info("  Devices scanned: %d", len(results["devices"]))
    logger.info("  Total points:    %d", total_points)
    logger.info("  Output file:     %s", output_file)
    logger.info("  Log file:        %s", LOG_FILE)


if __name__ == "__main__":
    asyncio.run(main())
