"""Interactive CLI for testing bac-py Client API features against a real BACnet device.

Usage::

    python interactive_cli.py [target_address]

    # Examples:
    python interactive_cli.py 192.168.1.100
    python interactive_cli.py 192.168.1.100:47808
"""

import asyncio
import contextlib
import datetime
import sys
from typing import Any

from bac_py import Client, decode_cov_values
from bac_py.services.errors import (
    BACnetAbortError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)
from bac_py.types.primitives import BACnetDate, BACnetTime


class _CLIState:
    """Tracks target address and active COV subscriptions."""

    def __init__(self, address: str) -> None:
        self.address = address
        self.subscriptions: dict[int, str] = {}  # process_id -> object_id
        self._next_pid = 1

    def next_process_id(self) -> int:
        """Return the next available process identifier."""
        pid = self._next_pid
        self._next_pid += 1
        return pid


async def _ainput(prompt: str = "") -> str:
    """Non-blocking input via ``run_in_executor``."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt)


async def _prompt(label: str, default: str = "") -> str:
    """Prompt for input with an optional default value."""
    if default:
        raw = await _ainput(f"  {label} [{default}]: ")
        return raw.strip() or default
    raw = await _ainput(f"  {label}: ")
    return raw.strip()


def _parse_value(text: str) -> object:
    """Parse a user-entered value: int, float, ``null`` -> None, or string."""
    if text.lower() == "null":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _do_read(client: Client, state: _CLIState) -> None:
    obj = await _prompt("Object (e.g. ai,1)")
    prop = await _prompt("Property (e.g. pv)")
    idx_str = await _prompt("Array index (blank for none)")
    idx = int(idx_str) if idx_str else None
    value = await client.read(state.address, obj, prop, array_index=idx)
    print(f"\n  Result: {value}")


async def _do_write(client: Client, state: _CLIState) -> None:
    obj = await _prompt("Object (e.g. av,1)")
    prop = await _prompt("Property (e.g. pv)")
    raw = await _prompt("Value (number, string, or 'null' to relinquish)")
    value = _parse_value(raw)
    pri_str = await _prompt("Priority 1-16 (blank for none)")
    priority = int(pri_str) if pri_str else None
    await client.write(state.address, obj, prop, value, priority=priority)
    print("\n  Write successful.")


async def _do_read_multiple(client: Client, state: _CLIState) -> None:
    print("  Enter object: prop1, prop2, ... (blank line to finish)")
    read_specs: Any = {}
    while True:
        line = await _ainput("  > ")
        if not line.strip():
            break
        obj, _, props_str = line.partition(":")
        prop_list = [p.strip() for p in props_str.split(",") if p.strip()]
        if obj.strip() and prop_list:
            read_specs[obj.strip()] = prop_list
    if not read_specs:
        print("  No properties specified.")
        return
    results = await client.read_multiple(state.address, read_specs)
    for obj_id, obj_props in results.items():
        print(f"\n  {obj_id}:")
        for prop_name, value in obj_props.items():
            print(f"    {prop_name}: {value}")


async def _do_write_multiple(client: Client, state: _CLIState) -> None:
    print("  Enter object: prop=value, ... (blank line to finish)")
    write_specs: Any = {}
    while True:
        line = await _ainput("  > ")
        if not line.strip():
            break
        obj, _, assignments_str = line.partition(":")
        obj = obj.strip()
        if not obj or not assignments_str.strip():
            continue
        obj_props: dict[str, object] = {}
        for assignment in assignments_str.split(","):
            key, _, val = assignment.partition("=")
            if key.strip() and val.strip():
                obj_props[key.strip()] = _parse_value(val.strip())
        if obj_props:
            write_specs[obj] = obj_props
    if not write_specs:
        print("  No properties specified.")
        return
    await client.write_multiple(state.address, write_specs)
    print("\n  Write multiple successful.")


async def _do_discover(client: Client, state: _CLIState) -> None:
    timeout_str = await _prompt("Timeout seconds", "3")
    timeout = float(timeout_str)
    devices = await client.discover(timeout=timeout)
    if not devices:
        print("\n  No devices found.")
        return
    print(f"\n  Found {len(devices)} device(s):")
    for dev in devices:
        print(f"    {dev}")


async def _do_who_has(client: Client, state: _CLIState) -> None:
    name = await _prompt("Object name or identifier (e.g. 'Room Temp' or ai,1)")
    if "," in name:
        results = await client.who_has(object_identifier=name)
    else:
        results = await client.who_has(object_name=name)
    if not results:
        print("\n  No responses.")
        return
    print(f"\n  {len(results)} response(s):")
    for r in results:
        print(f"    {r}")


async def _do_object_list(client: Client, state: _CLIState) -> None:
    inst_str = await _prompt("Device instance number")
    instance = int(inst_str)
    objects = await client.get_object_list(state.address, instance)
    print(f"\n  {len(objects)} object(s):")
    for obj in objects:
        print(f"    {obj}")


async def _do_subscribe_cov(client: Client, state: _CLIState) -> None:
    obj = await _prompt("Object (e.g. ai,1)")
    lifetime_str = await _prompt("Lifetime seconds (0 for indefinite)", "3600")
    lifetime = int(lifetime_str) or None
    pid = state.next_process_id()

    def _on_notification(notification: Any, source: Any) -> None:
        values = decode_cov_values(notification)
        print(f"\n  [COV] {notification.monitored_object_identifier}:")
        for prop_name, value in values.items():
            print(f"    {prop_name}: {value}")

    await client.subscribe_cov_ex(
        state.address,
        obj,
        process_id=pid,
        callback=_on_notification,
        confirmed=True,
        lifetime=lifetime,
    )
    state.subscriptions[pid] = obj
    print(f"\n  Subscribed (process_id={pid}). Notifications will print as [COV].")


async def _do_unsubscribe_cov(client: Client, state: _CLIState) -> None:
    if not state.subscriptions:
        print("  No active subscriptions.")
        return
    print("  Active subscriptions:")
    for pid, obj in state.subscriptions.items():
        print(f"    {pid}: {obj}")
    pid_str = await _prompt("Process ID to unsubscribe")
    pid = int(pid_str)
    if pid not in state.subscriptions:
        print(f"  Process ID {pid} not found.")
        return
    obj = state.subscriptions[pid]
    await client.unsubscribe_cov_ex(state.address, obj, process_id=pid)
    del state.subscriptions[pid]
    print(f"\n  Unsubscribed process_id={pid}.")


async def _do_time_sync(client: Client, state: _CLIState) -> None:
    now = datetime.datetime.now()
    date = BACnetDate(now.year, now.month, now.day, now.weekday() + 1)
    time = BACnetTime(now.hour, now.minute, now.second, 0)
    client.time_synchronization(state.address, date, time)
    print(f"\n  Time sync sent: {now.strftime('%Y-%m-%d %H:%M:%S')}")


async def _do_change_target(client: Client, state: _CLIState) -> None:
    addr = await _prompt("New target address", state.address)
    state.address = addr
    print(f"\n  Target changed to {addr}")


# ---------------------------------------------------------------------------
# Dispatch table and menu
# ---------------------------------------------------------------------------

_ACTIONS: dict[str, tuple[str, Any]] = {
    "1": ("Read property", _do_read),
    "2": ("Write property", _do_write),
    "3": ("Read multiple properties", _do_read_multiple),
    "4": ("Write multiple properties", _do_write_multiple),
    "5": ("Discover devices (Who-Is)", _do_discover),
    "6": ("Find object (Who-Has)", _do_who_has),
    "7": ("List objects on device", _do_object_list),
    "8": ("Subscribe to COV", _do_subscribe_cov),
    "9": ("Unsubscribe from COV", _do_unsubscribe_cov),
    "10": ("Time synchronization", _do_time_sync),
    "0": ("Change target device", _do_change_target),
}


def _print_menu(state: _CLIState) -> None:
    print(
        f"""
=== bac-py Interactive CLI ===
Target: {state.address}

  Read / Write
    1. Read property
    2. Write property
    3. Read multiple properties
    4. Write multiple properties

  Discovery
    5. Discover devices (Who-Is)
    6. Find object (Who-Has)
    7. List objects on device

  COV (Change of Value)
    8. Subscribe to COV
    9. Unsubscribe from COV

  Device Management
   10. Time synchronization

   0. Change target device
   q. Quit
"""
    )


async def _command_loop(client: Client, state: _CLIState) -> None:
    """Run the interactive menu loop."""
    while True:
        _print_menu(state)
        choice = (await _ainput("Select> ")).strip().lower()
        if choice == "q":
            break
        action = _ACTIONS.get(choice)
        if action is None:
            print(f"  Unknown choice: {choice!r}")
            continue
        _label, handler = action
        try:
            await handler(client, state)
        except BACnetTimeoutError:
            print(f"\n  Timeout: no response from {state.address}")
        except BACnetRejectError as exc:
            print(f"\n  Rejected: {exc.reason}")
        except BACnetAbortError as exc:
            print(f"\n  Aborted: {exc.reason}")
        except BACnetError as exc:
            print(f"\n  BACnet error: {exc.error_class} / {exc.error_code}")
        except (ValueError, KeyError) as exc:
            print(f"\n  Input error: {exc}")


async def main() -> None:
    """Run the interactive CLI."""
    if len(sys.argv) > 1:
        address = sys.argv[1]
    else:
        address = input("Target device address [192.168.1.100]: ").strip() or "192.168.1.100"

    state = _CLIState(address)

    async with Client(instance_number=999) as client:
        try:
            await _command_loop(client, state)
        finally:
            for pid, obj in list(state.subscriptions.items()):
                with contextlib.suppress(Exception):
                    await client.unsubscribe_cov_ex(state.address, obj, process_id=pid)


if __name__ == "__main__":
    asyncio.run(main())
