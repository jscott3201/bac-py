"""write command -- write a property value to a BACnet device."""

from __future__ import annotations

import sys

import click

from bac_py.app.client import BACnetClient
from bac_py.services.errors import (
    BACnetAbortError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)
from bac_py.types.primitives import ObjectIdentifier
from tools.connection import run_command
from tools.encoding import encode_value
from tools.formatting import print_error, print_json
from tools.parsers import parse_address, parse_object_id, parse_property


@click.command()
@click.argument("address")
@click.argument("object")
@click.argument("property")
@click.argument("value")
@click.option(
    "--priority", type=click.IntRange(1, 16), default=None, help="Write priority (1-16)."
)
@click.option("--index", "array_index", type=int, default=None, help="Array index.")
@click.option(
    "--type",
    "type_override",
    default=None,
    help="Force value type (real, unsigned, signed, bool, enum, string, null).",
)
@click.pass_context
def write(
    ctx: click.Context,
    address: str,
    object: str,
    property: str,
    value: str,
    priority: int | None,
    array_index: int | None,
    type_override: str | None,
) -> None:
    """Write a property value to a remote device.

    ADDRESS is the device IP (or IP:port).
    OBJECT is type:instance (e.g. av:1, bo:3).
    PROPERTY is the property name (e.g. present-value).
    VALUE is the value to write (e.g. 72.5, active, null).
    """
    use_json: bool = ctx.obj["use_json"]

    try:
        addr = parse_address(address)
        obj_type, instance = parse_object_id(object)
        prop = parse_property(property)
    except ValueError as e:
        print_error(str(e), use_json)
        sys.exit(1)

    try:
        encoded = encode_value(value, obj_type, prop, type_override)
    except (ValueError, OverflowError) as e:
        print_error(f"Cannot encode value: {e}", use_json)
        sys.exit(1)

    obj_id = ObjectIdentifier(obj_type, instance)

    async def _run(client: BACnetClient) -> None:
        try:
            await client.write_property(
                addr,
                obj_id,
                prop,
                encoded,
                priority=priority,
                array_index=array_index,
            )
            if use_json:
                print_json(
                    {
                        "status": "ok",
                        "object": f"{obj_type.name}:{instance}",
                        "property": prop.name,
                        "value": value,
                        "encoded": encoded.hex(),
                    }
                )
            else:
                print(f"OK: wrote {value} to {obj_type.name}:{instance} {prop.name}")

        except BACnetError as e:
            print_error(f"BACnet error: {e.error_class.name}/{e.error_code.name}", use_json)
            sys.exit(1)
        except BACnetRejectError as e:
            print_error(f"Request rejected: {e.reason.name}", use_json)
            sys.exit(1)
        except BACnetAbortError as e:
            print_error(f"Transaction aborted: {e.reason.name}", use_json)
            sys.exit(1)
        except BACnetTimeoutError:
            print_error("Device did not respond (timeout)", use_json)
            sys.exit(1)

    try:
        run_command(ctx.obj["interface"], ctx.obj["port"], ctx.obj["instance"], _run)
    except Exception as e:
        print_error(str(e), use_json)
        sys.exit(1)
