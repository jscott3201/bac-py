"""Interactive demo client for the BACnet Smart Thermostat.

When stdin is a TTY (e.g. ``docker compose run``), presents an interactive
menu.  Otherwise (e.g. ``docker compose up``) runs an automated walkthrough
of every feature.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time

SERVER_ADDRESS = os.environ.get("SERVER_ADDRESS", "172.30.1.90")
SERVER_INSTANCE = int(os.environ.get("SERVER_INSTANCE", "500"))

BANNER = """\
========================================================
    BACnet Smart Thermostat Demo Client
    Powered by bac-py
========================================================"""

MENU = """\
Actions:
   1) Read temperatures
   2) Read setpoints
   3) Write heating setpoint
   4) Write cooling setpoint
   5) Read all I/O (ReadPropertyMultiple)
   6) Watch simulation (30s live view)
   7) Subscribe to COV notifications (15s)
   8) Read trend log history
   9) Check alarm status
  10) Get full object list
  11) Toggle system enable
  12) Relinquish setpoint overrides
   a) Run full auto demo
   q) Quit
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _header(title: str) -> None:
    print(f"\n--- {title} ---")


def _fmt(val, suffix="") -> str:
    if isinstance(val, float):
        return f"{val:.1f}{suffix}"
    return f"{val}{suffix}"


# ---------------------------------------------------------------------------
# Individual demo actions
# ---------------------------------------------------------------------------


async def do_read_temperatures(client, addr):
    _header("Temperatures")
    zone = await client.read(addr, "ai,1", "present-value")
    outside = await client.read(addr, "ai,2", "present-value")
    print(f"  Zone Temperature:    {_fmt(zone, ' F')}")
    print(f"  Outside Temperature: {_fmt(outside, ' F')}")


async def do_read_setpoints(client, addr):
    _header("Setpoints")
    heat = await client.read(addr, "av,1", "present-value")
    cool = await client.read(addr, "av,2", "present-value")
    db = await client.read(addr, "av,3", "present-value")
    print(f"  Heating Setpoint: {_fmt(heat, ' F')}")
    print(f"  Cooling Setpoint: {_fmt(cool, ' F')}")
    print(f"  Deadband:         {_fmt(db, ' F')}")


async def do_write_heating_sp(client, addr, interactive=True):
    _header("Write Heating Setpoint")
    if interactive:
        try:
            raw = input("  Enter new heating setpoint (F): ")
            val = float(raw)
        except (ValueError, EOFError):
            print("  Invalid input.")
            return
    else:
        val = 75.0
    await client.write(addr, "av,1", "present-value", val, priority=8)
    print(f"  Heating setpoint set to {val:.1f} F at priority 8")


async def do_write_cooling_sp(client, addr, interactive=True):
    _header("Write Cooling Setpoint")
    if interactive:
        try:
            raw = input("  Enter new cooling setpoint (F): ")
            val = float(raw)
        except (ValueError, EOFError):
            print("  Invalid input.")
            return
    else:
        val = 74.0
    await client.write(addr, "av,2", "present-value", val, priority=8)
    print(f"  Cooling setpoint set to {val:.1f} F at priority 8")


async def do_read_multiple(client, addr):
    _header("ReadPropertyMultiple")
    result = await client.read_multiple(
        addr,
        {
            "ai,1": ["present-value", "object-name", "units"],
            "ai,2": ["present-value", "object-name"],
            "ao,1": ["present-value", "object-name"],
            "ao,2": ["present-value", "object-name"],
            "av,1": ["present-value", "object-name"],
            "av,2": ["present-value", "object-name"],
            "bv,1": ["present-value", "object-name"],
            "bv,2": ["present-value", "object-name"],
        },
    )
    for obj_key, props in result.items():
        name = props.get("object-name", obj_key)
        pv = props.get("present-value", "?")
        units = props.get("units", "")
        unit_str = f" (units={units})" if units else ""
        print(f"  {name}: {_fmt(pv)}{unit_str}")


async def do_watch_simulation(client, addr, duration=30):
    _header(f"Watching simulation for {duration}s")
    hdr = f"  {'Time':>5s}  {'Zone F':>7s}  {'Outside F':>10s}  {'Heat%':>6s}  {'Cool%':>6s}  {'Fan':>4s}"
    sep = f"  {'---':>5s}  {'---':>7s}  {'---':>10s}  {'---':>6s}  {'---':>6s}  {'---':>4s}"
    print(hdr)
    print(sep)
    start = time.monotonic()
    while time.monotonic() - start < duration:
        zone = await client.read(addr, "ai,1", "present-value")
        outside = await client.read(addr, "ai,2", "present-value")
        heat = await client.read(addr, "ao,1", "present-value")
        cool = await client.read(addr, "ao,2", "present-value")
        fan_val = await client.read(addr, "bv,2", "present-value")
        elapsed = int(time.monotonic() - start)
        fan_str = "ON" if fan_val else "OFF"
        print(
            f"  {elapsed:>4d}s  {zone:>7.1f}  {outside:>10.1f}"
            f"  {heat:>5.0f}%  {cool:>5.0f}%  {fan_str:>4s}"
        )
        await asyncio.sleep(5)


async def do_subscribe_cov(client, addr, duration=15):
    _header(f"COV Subscription on Zone Temperature ({duration}s)")
    notifications: list = []

    def on_cov(notification, source):
        notifications.append(notification)
        print(f"  COV #{len(notifications)}: {notification}")

    process_id = 42
    await client.subscribe_cov_ex(
        addr,
        "ai,1",
        process_id,
        confirmed=False,
        lifetime=duration + 10,
        callback=on_cov,
    )
    print(f"  Subscribed. Waiting {duration}s for notifications...")
    await asyncio.sleep(duration)
    with contextlib.suppress(Exception):
        await client.unsubscribe_cov_ex(addr, "ai,1", process_id)
    print(f"  Received {len(notifications)} COV notification(s)")


async def do_read_trend_log(client, addr):
    _header("Trend Log (Zone Temperature)")
    try:
        count = await client.read(addr, "trend-log,1", "record-count")
        print(f"  Records in buffer: {count}")
        buffer = await client.read(addr, "trend-log,1", "log-buffer")
        if isinstance(buffer, list) and buffer:
            show = buffer[-5:]
            print(f"  Latest {len(show)} entries:")
            for rec in show:
                print(f"    {rec}")
        elif not buffer:
            print("  (buffer empty -- try again after ~10s)")
    except Exception as e:
        print(f"  Could not read trend log: {e}")
        print("  (Trend data may take a few seconds to accumulate)")


async def do_check_alarms(client, addr):
    _header("Alarm Status")
    try:
        info = await client.get_event_information(addr)
        if hasattr(info, "list_of_event_summaries") and info.list_of_event_summaries:
            for ev in info.list_of_event_summaries:
                print(f"  {ev}")
        else:
            print("  No active alarms (zone temperature within normal range)")
    except Exception as e:
        print(f"  Could not get event info: {e}")


async def do_get_object_list(client, addr):
    _header("Object List")
    obj_list = await client.get_object_list(addr, SERVER_INSTANCE)
    print(f"  Found {len(obj_list)} objects:")
    for oid in obj_list:
        print(f"    {oid}")


async def do_toggle_system(client, addr):
    _header("Toggle System Enable")
    current = await client.read(addr, "bv,1", "present-value")
    is_on = bool(current)
    new_val = 0 if is_on else 1
    await client.write(addr, "bv,1", "present-value", new_val, priority=8)
    state = "OFF" if is_on else "ON"
    print(f"  System was {'ON' if is_on else 'OFF'}, now set to {state}")


async def do_relinquish(client, addr):
    _header("Relinquish Setpoint Overrides")
    await client.write(addr, "av,1", "present-value", None, priority=8)
    await client.write(addr, "av,2", "present-value", None, priority=8)
    await client.write(addr, "bv,1", "present-value", None, priority=8)
    print("  Released priority-8 overrides on heating/cooling setpoints and system enable")
    heat = await client.read(addr, "av,1", "present-value")
    cool = await client.read(addr, "av,2", "present-value")
    print(f"  Setpoints reverted to: Heating={_fmt(heat, ' F')}, Cooling={_fmt(cool, ' F')}")


# ---------------------------------------------------------------------------
# Auto demo (non-interactive)
# ---------------------------------------------------------------------------


async def auto_demo(client, addr):
    """Run all demo steps automatically."""
    _header("AUTO DEMO: Running all demonstrations")

    # 1. Device identification via direct read
    _header("Step 1: Device Identification")
    name = await client.read(addr, f"device,{SERVER_INSTANCE}", "object-name")
    vendor = await client.read(addr, f"device,{SERVER_INSTANCE}", "vendor-name")
    model = await client.read(addr, f"device,{SERVER_INSTANCE}", "model-name")
    print(f"  Name:   {name}")
    print(f"  Vendor: {vendor}")
    print(f"  Model:  {model}")

    # 2. Object list
    await do_get_object_list(client, addr)

    # 3-4. Temperatures and setpoints
    await do_read_temperatures(client, addr)
    await do_read_setpoints(client, addr)

    # 5. Write heating setpoint
    _header("Step 5: Adjust Heating Setpoint")
    await client.write(addr, "av,1", "present-value", 75.0, priority=8)
    print("  Set heating setpoint to 75.0 F at priority 8")
    print("  Waiting 10s for simulation to respond...")
    await asyncio.sleep(10)
    zone = await client.read(addr, "ai,1", "present-value")
    print(f"  Zone temperature is now: {_fmt(zone, ' F')}")

    # 6. Read multiple
    await do_read_multiple(client, addr)

    # 7. Watch simulation
    await do_watch_simulation(client, addr, duration=30)

    # 8. COV subscription
    await do_subscribe_cov(client, addr, duration=15)

    # 9. Trend log
    await do_read_trend_log(client, addr)

    # 10. Alarms
    await do_check_alarms(client, addr)

    # 11. Relinquish
    await do_relinquish(client, addr)

    _header("AUTO DEMO COMPLETE")
    print("  All demonstrations completed successfully!")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> int:
    from bac_py.client import Client

    print(BANNER)
    print(f"Connecting to thermostat at {SERVER_ADDRESS} (device {SERVER_INSTANCE})...")

    async with Client(instance_number=900, port=0) as client:
        # Verify connectivity with a direct read (broadcast may not work in Docker)
        addr = SERVER_ADDRESS
        try:
            name = await client.read(addr, f"device,{SERVER_INSTANCE}", "object-name")
        except Exception as e:
            print(f"ERROR: Cannot reach thermostat at {addr}: {e}")
            return 1

        print(f"Connected to: {name} (instance {SERVER_INSTANCE})\n")

        interactive = sys.stdin.isatty()
        if not interactive:
            await auto_demo(client, addr)
            return 0

        # Interactive loop
        while True:
            print(MENU)
            try:
                choice = input("Choose> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break

            try:
                if choice == "q":
                    break
                elif choice == "1":
                    await do_read_temperatures(client, addr)
                elif choice == "2":
                    await do_read_setpoints(client, addr)
                elif choice == "3":
                    await do_write_heating_sp(client, addr, interactive=True)
                elif choice == "4":
                    await do_write_cooling_sp(client, addr, interactive=True)
                elif choice == "5":
                    await do_read_multiple(client, addr)
                elif choice == "6":
                    await do_watch_simulation(client, addr)
                elif choice == "7":
                    await do_subscribe_cov(client, addr)
                elif choice == "8":
                    await do_read_trend_log(client, addr)
                elif choice == "9":
                    await do_check_alarms(client, addr)
                elif choice == "10":
                    await do_get_object_list(client, addr)
                elif choice == "11":
                    await do_toggle_system(client, addr)
                elif choice == "12":
                    await do_relinquish(client, addr)
                elif choice == "a":
                    await auto_demo(client, addr)
                else:
                    print(f"  Unknown choice: {choice!r}")
            except Exception as e:
                print(f"  Error: {e}")

    print("\nGoodbye!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
