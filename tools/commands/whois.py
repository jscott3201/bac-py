"""whois command -- discover BACnet devices on the network."""

from __future__ import annotations

import sys

import click

from bac_py.app.client import BACnetClient
from tools.connection import run_command
from tools.formatting import print_error, print_json, print_table


@click.command()
@click.option("--low", type=int, default=None, help="Low device instance limit.")
@click.option("--high", type=int, default=None, help="High device instance limit.")
@click.option(
    "--timeout", type=float, default=3.0, show_default=True, help="Seconds to wait for responses."
)
@click.pass_context
def whois(
    ctx: click.Context,
    low: int | None,
    high: int | None,
    timeout: float,
) -> None:
    """Discover BACnet devices via Who-Is broadcast."""
    use_json: bool = ctx.obj["use_json"]

    async def _run(client: BACnetClient) -> None:
        responses = await client.who_is(
            low_limit=low,
            high_limit=high,
            timeout=timeout,
        )

        if not responses:
            if use_json:
                print_json({"devices": []})
            else:
                print("No devices responded.")
            return

        devices = []
        rows = []
        for iam in responses:
            oid = iam.object_identifier
            device = {
                "instance": oid.instance_number,
                "max_apdu": iam.max_apdu_length,
                "segmentation": iam.segmentation_supported.name,
                "vendor_id": iam.vendor_id,
            }
            devices.append(device)
            rows.append(
                [
                    str(oid.instance_number),
                    str(iam.max_apdu_length),
                    iam.segmentation_supported.name,
                    str(iam.vendor_id),
                ]
            )

        if use_json:
            print_json({"devices": devices})
        else:
            print(f"Found {len(responses)} device(s):\n")
            print_table(
                ["Instance", "Max APDU", "Segmentation", "Vendor ID"],
                rows,
            )

    try:
        run_command(ctx.obj["interface"], ctx.obj["port"], ctx.obj["instance"], _run)
    except Exception as e:
        print_error(str(e), use_json)
        sys.exit(1)
