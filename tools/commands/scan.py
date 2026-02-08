"""scan command -- full device point discovery to JSON."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import click

from bac_py.app.client import BACnetClient
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
from tools.connection import run_command
from tools.encoding import (
    decode_application_value,
    decode_object_list,
    format_property_value,
)
from tools.formatting import print_error
from tools.parsers import parse_address

# Properties to read from the Device object
_DEVICE_PROPERTIES = [
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


def _object_type_name(obj_type: int) -> str:
    try:
        return ObjectType(obj_type).name
    except ValueError:
        return str(obj_type)


async def _read_device_info(
    client: BACnetClient,
    address: object,
    instance: int,
) -> dict:
    """Read device object properties with RPM fallback."""
    device_id = ObjectIdentifier(ObjectType.DEVICE, instance)
    info: dict = {}

    try:
        spec = ReadAccessSpecification(
            object_identifier=device_id,
            list_of_property_references=[PropertyReference(p) for p in _DEVICE_PROPERTIES],
        )
        ack = await client.read_property_multiple(address, [spec])
        for result in ack.list_of_read_access_results:
            for elem in result.list_of_results:
                prop = elem.property_identifier
                if elem.property_value is not None:
                    value = decode_application_value(elem.property_value)
                    info[prop.name] = format_property_value(prop, value)
                elif elem.property_access_error is not None:
                    err_class, err_code = elem.property_access_error
                    info[prop.name] = f"ERROR: {err_class.name}/{err_code.name}"
    except (BACnetError, BACnetRejectError, BACnetAbortError):
        for prop in _DEVICE_PROPERTIES:
            try:
                ack = await client.read_property(address, device_id, prop)
                value = decode_application_value(ack.property_value)
                info[prop.name] = format_property_value(prop, value)
            except (BACnetError, BACnetTimeoutError):
                info[prop.name] = "unavailable"
    except BACnetTimeoutError:
        info["error"] = "timeout"

    return info


async def _discover_object_list(
    client: BACnetClient,
    address: object,
    instance: int,
) -> list[tuple[int, int]]:
    """Discover the full object list from a device."""
    device_id = ObjectIdentifier(ObjectType.DEVICE, instance)

    # Try unindexed read first
    try:
        ack = await client.read_property(
            address,
            device_id,
            PropertyIdentifier.OBJECT_LIST,
        )
        return decode_object_list(ack.property_value)
    except (BACnetError, BACnetAbortError):
        pass

    # Fallback: indexed reads
    objects: list[tuple[int, int]] = []
    try:
        ack = await client.read_property(
            address,
            device_id,
            PropertyIdentifier.OBJECT_LIST,
            array_index=0,
        )
        count = decode_application_value(ack.property_value)
        if not isinstance(count, int):
            return objects

        from bac_py.encoding.primitives import decode_object_identifier
        from bac_py.encoding.tags import decode_tag

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
            except (BACnetError, BACnetTimeoutError):
                continue
    except (BACnetError, BACnetTimeoutError):
        pass

    return objects


async def _read_point_properties(
    client: BACnetClient,
    address: object,
    obj_type: int,
    instance: int,
) -> dict:
    """Read properties from a single point/object."""
    type_name = _object_type_name(obj_type)
    obj_id = ObjectIdentifier(ObjectType(obj_type), instance)

    props = [PropertyIdentifier.OBJECT_NAME, PropertyIdentifier.DESCRIPTION]
    if obj_type != ObjectType.DEVICE:
        props.append(PropertyIdentifier.PRESENT_VALUE)
        props.append(PropertyIdentifier.STATUS_FLAGS)
    if obj_type in (ObjectType.ANALOG_INPUT, ObjectType.ANALOG_OUTPUT, ObjectType.ANALOG_VALUE):
        props.append(PropertyIdentifier.UNITS)

    point: dict = {"object_type": type_name, "instance": instance}

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
                elif elem.property_access_error is not None:
                    err_class, err_code = elem.property_access_error
                    point[prop.name] = f"ERROR: {err_class.name}/{err_code.name}"
    except (BACnetError, BACnetRejectError, BACnetAbortError):
        for prop in props:
            try:
                ack = await client.read_property(address, obj_id, prop)
                value = decode_application_value(ack.property_value)
                point[prop.name] = format_property_value(prop, value)
            except (BACnetError, BACnetTimeoutError):
                point[prop.name] = "unavailable"
    except BACnetTimeoutError:
        point["error"] = "timeout"

    return point


@click.command()
@click.argument("address")
@click.argument("instance", type=int)
@click.option(
    "--output",
    "-o",
    "output_file",
    default=None,
    help="Output JSON file path (default: stdout).",
)
@click.pass_context
def scan(
    ctx: click.Context,
    address: str,
    instance: int,
    output_file: str | None,
) -> None:
    """Full device scan -- discovers all objects and reads their properties.

    ADDRESS is the device IP (or IP:port).
    INSTANCE is the device instance number.
    """
    use_json: bool = ctx.obj["use_json"]

    try:
        addr = parse_address(address)
    except ValueError as e:
        print_error(str(e), use_json)
        sys.exit(1)

    async def _run(client: BACnetClient) -> None:
        click.echo(f"Scanning device at {address} (instance {instance})...")

        # Read device info
        click.echo("  Reading device info...")
        device_info = await _read_device_info(client, addr, instance)
        dev_name = device_info.get("OBJECT_NAME", "unknown")
        click.echo(f"  Device name: {dev_name}")

        # Discover objects
        click.echo("  Discovering objects...")
        object_list = await _discover_object_list(client, addr, instance)
        click.echo(f"  Found {len(object_list)} objects")

        # Read all points
        points = []
        for idx, (obj_type, obj_instance) in enumerate(object_list, 1):
            label = f"{_object_type_name(obj_type)}:{obj_instance}"
            click.echo(f"  [{idx}/{len(object_list)}] {label}")
            point = await _read_point_properties(client, addr, obj_type, obj_instance)
            points.append(point)

        # Build results
        results = {
            "scan_timestamp": datetime.now(UTC).isoformat(),
            "device_address": address,
            "device_instance": instance,
            "device_info": device_info,
            "total_points": len(points),
            "points": points,
        }

        # Output
        if output_file:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2, default=str)
            click.echo(f"\nResults written to {output_file}")
        else:
            click.echo()
            click.echo(json.dumps(results, indent=2, default=str))

        # Summary
        click.echo(f"\nScan complete: {len(points)} points discovered")

    try:
        run_command(ctx.obj["interface"], ctx.obj["port"], ctx.obj["instance"], _run)
    except Exception as e:
        print_error(str(e), use_json)
        sys.exit(1)
