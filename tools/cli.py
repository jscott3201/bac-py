"""Click CLI group and global options for the BACnet CLI."""

from __future__ import annotations

import logging
import sys

import click

from tools.commands.read import read
from tools.commands.rpm import rpm
from tools.commands.scan import scan
from tools.commands.whohas import whohas
from tools.commands.whois import whois
from tools.commands.write import write


@click.group()
@click.option(
    "--interface",
    default="0.0.0.0",
    show_default=True,
    help="Local bind address.",
)
@click.option(
    "--port",
    default=0xBAC0,
    type=int,
    show_default=True,
    help="Local BACnet/IP port.",
)
@click.option(
    "--instance",
    default=999,
    type=int,
    show_default=True,
    help="Local device instance number.",
)
@click.option(
    "--json",
    "use_json",
    is_flag=True,
    default=False,
    help="Output JSON instead of table.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    interface: str,
    port: int,
    instance: int,
    use_json: bool,
    verbose: bool,
) -> None:
    """BACnet/IP command-line tools powered by bac-py."""
    ctx.ensure_object(dict)
    ctx.obj["interface"] = interface
    ctx.obj["port"] = port
    ctx.obj["instance"] = instance
    ctx.obj["use_json"] = use_json

    # Configure logging
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )


# Register commands
cli.add_command(read)
cli.add_command(write)
cli.add_command(rpm)
cli.add_command(whois)
cli.add_command(whohas)
cli.add_command(scan)
