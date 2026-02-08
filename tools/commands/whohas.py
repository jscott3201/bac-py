"""whohas command -- discover BACnet objects by name or identifier."""

from __future__ import annotations

import sys

import click

from bac_py.app.client import BACnetClient
from bac_py.types.primitives import ObjectIdentifier
from tools.connection import run_command
from tools.formatting import print_error, print_json, print_table
from tools.parsers import parse_object_id


@click.command()
@click.option("--object", "object_str", default=None, help="Object to find (e.g. ai:1).")
@click.option(
    "--name", "object_name", default=None, help="Object name to find (e.g. 'Room Temp')."
)
@click.option("--low", type=int, default=None, help="Low device instance limit.")
@click.option("--high", type=int, default=None, help="High device instance limit.")
@click.option(
    "--timeout", type=float, default=3.0, show_default=True, help="Seconds to wait for responses."
)
@click.pass_context
def whohas(
    ctx: click.Context,
    object_str: str | None,
    object_name: str | None,
    low: int | None,
    high: int | None,
    timeout: float,
) -> None:
    """Discover objects by name or identifier via Who-Has broadcast."""
    use_json: bool = ctx.obj["use_json"]

    if object_str is None and object_name is None:
        print_error("Provide either --object or --name", use_json)
        sys.exit(1)

    object_identifier = None
    if object_str:
        try:
            obj_type, instance = parse_object_id(object_str)
            object_identifier = ObjectIdentifier(obj_type, instance)
        except ValueError as e:
            print_error(str(e), use_json)
            sys.exit(1)

    async def _run(client: BACnetClient) -> None:
        responses = await client.who_has(
            object_identifier=object_identifier,
            object_name=object_name,
            low_limit=low,
            high_limit=high,
            timeout=timeout,
        )

        if not responses:
            if use_json:
                print_json({"results": []})
            else:
                print("No devices responded.")
            return

        results = []
        rows = []
        for ihave in responses:
            dev = ihave.device_identifier
            obj = ihave.object_identifier
            result = {
                "device": f"{dev.object_type.name}:{dev.instance_number}",
                "object": f"{obj.object_type.name}:{obj.instance_number}",
                "name": ihave.object_name,
            }
            results.append(result)
            rows.append(
                [
                    str(dev.instance_number),
                    f"{obj.object_type.name}:{obj.instance_number}",
                    ihave.object_name,
                ]
            )

        if use_json:
            print_json({"results": results})
        else:
            print(f"Found {len(responses)} result(s):\n")
            print_table(
                ["Device", "Object", "Name"],
                rows,
            )

    try:
        run_command(ctx.obj["interface"], ctx.obj["port"], ctx.obj["instance"], _run)
    except Exception as e:
        print_error(str(e), use_json)
        sys.exit(1)
