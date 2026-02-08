"""read command -- read a single property from a BACnet device."""

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
from tools.encoding import decode_application_value, format_property_value
from tools.formatting import print_error, print_json, print_kv
from tools.parsers import parse_address, parse_object_id, parse_property


@click.command()
@click.argument("address")
@click.argument("object")
@click.argument("property")
@click.option("--index", "array_index", type=int, default=None, help="Array index.")
@click.pass_context
def read(
    ctx: click.Context,
    address: str,
    object: str,
    property: str,
    array_index: int | None,
) -> None:
    """Read a single property from a remote device.

    ADDRESS is the device IP (or IP:port).
    OBJECT is type:instance (e.g. ai:1, device:0).
    PROPERTY is the property name (e.g. present-value, object-name).
    """
    use_json: bool = ctx.obj["use_json"]

    try:
        addr = parse_address(address)
        obj_type, instance = parse_object_id(object)
        prop = parse_property(property)
    except ValueError as e:
        print_error(str(e), use_json)
        sys.exit(1)

    obj_id = ObjectIdentifier(obj_type, instance)

    async def _run(client: BACnetClient) -> None:
        try:
            ack = await client.read_property(addr, obj_id, prop, array_index=array_index)
            value = decode_application_value(ack.property_value)
            display = format_property_value(prop, value)

            if use_json:
                print_json(
                    {
                        "object": f"{obj_type.name}:{instance}",
                        "property": prop.name,
                        "value": display,
                        "raw": ack.property_value.hex(),
                    }
                )
            else:
                print_kv(
                    [
                        ("Object", f"{obj_type.name}:{instance}"),
                        ("Property", prop.name),
                        ("Value", display),
                    ]
                )

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
