"""rpm command -- read multiple properties from a BACnet device."""

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
from bac_py.services.read_property_multiple import (
    PropertyReference,
    ReadAccessSpecification,
)
from bac_py.types.primitives import ObjectIdentifier
from tools.connection import run_command
from tools.encoding import decode_application_value, format_property_value
from tools.formatting import print_error, print_json, print_table
from tools.parsers import parse_address, parse_object_id, parse_property


@click.command()
@click.argument("address")
@click.argument("object")
@click.argument("properties", nargs=-1, required=True)
@click.pass_context
def rpm(
    ctx: click.Context,
    address: str,
    object: str,
    properties: tuple[str, ...],
) -> None:
    """Read multiple properties from a single object.

    ADDRESS is the device IP (or IP:port).
    OBJECT is type:instance (e.g. ai:1, device:0).
    PROPERTIES are the property names (e.g. present-value object-name units).
    """
    use_json: bool = ctx.obj["use_json"]

    try:
        addr = parse_address(address)
        obj_type, instance = parse_object_id(object)
        props = [parse_property(p) for p in properties]
    except ValueError as e:
        print_error(str(e), use_json)
        sys.exit(1)

    obj_id = ObjectIdentifier(obj_type, instance)

    async def _run(client: BACnetClient) -> None:
        try:
            spec = ReadAccessSpecification(
                object_identifier=obj_id,
                list_of_property_references=[PropertyReference(p) for p in props],
            )
            ack = await client.read_property_multiple(addr, [spec])

            results: list[dict] = []
            rows: list[list] = []
            for result in ack.list_of_read_access_results:
                for elem in result.list_of_results:
                    prop = elem.property_identifier
                    if elem.property_value is not None:
                        value = decode_application_value(elem.property_value)
                        display = format_property_value(prop, value)
                        results.append(
                            {
                                "property": prop.name,
                                "value": display,
                                "raw": elem.property_value.hex(),
                            }
                        )
                        rows.append([prop.name, str(display)])
                    elif elem.property_access_error is not None:
                        err_class, err_code = elem.property_access_error
                        err_str = f"ERROR: {err_class.name}/{err_code.name}"
                        results.append(
                            {
                                "property": prop.name,
                                "error": err_str,
                            }
                        )
                        rows.append([prop.name, err_str])

            if use_json:
                print_json(
                    {
                        "object": f"{obj_type.name}:{instance}",
                        "results": results,
                    }
                )
            else:
                print(f"{obj_type.name}:{instance}")
                print()
                print_table(["Property", "Value"], rows)

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
