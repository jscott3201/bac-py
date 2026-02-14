"""Smart thermostat demo server with HVAC simulation loop.

Simulates a building zone thermostat with realistic BACnet objects
including temperature sensors, HVAC outputs, commandable setpoints,
occupancy scheduling, trend logging, and alarm monitoring.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import signal
import time
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("thermostat")

# Simulation constants
SIM_INTERVAL = 2.0  # seconds between simulation steps
OUTSIDE_TEMP_BASE = 55.0  # base outside temperature (degF)
OUTSIDE_TEMP_AMPLITUDE = 15.0  # swing +/-15 degF
OUTSIDE_TEMP_PERIOD = 600.0  # 10-minute sine cycle for demo speed
DRIFT_RATE = 0.002  # zone drift toward outside per step
HEAT_RATE = 0.05  # degF per % heating output per step
COOL_RATE = 0.05  # degF per % cooling output per step
RAMP_STEP = 10.0  # output ramp increment per step (%)

# Default setpoints
OCCUPIED_HEATING_SP = 72.0
OCCUPIED_COOLING_SP = 76.0


def _get_commandable_value(obj: Any, default: Any = 0.0) -> Any:
    """Resolve the effective present-value of a commandable object."""
    from bac_py.types.enums import PropertyIdentifier

    pa = obj._properties.get(PropertyIdentifier.PRIORITY_ARRAY)
    if pa:
        for v in pa:
            if v is not None:
                return v
    return obj._properties.get(PropertyIdentifier.RELINQUISH_DEFAULT, default)


def _write_healthy() -> None:
    with open("/tmp/healthy", "w") as f:
        f.write("ok")


async def run() -> None:
    """Start the thermostat server and run the simulation loop."""
    from bac_py.app.application import BACnetApplication, DeviceConfig
    from bac_py.app.schedule_engine import ScheduleEngine
    from bac_py.app.server import DefaultServerHandlers
    from bac_py.app.trendlog_engine import TrendLogEngine
    from bac_py.objects.analog import (
        AnalogInputObject,
        AnalogOutputObject,
        AnalogValueObject,
    )
    from bac_py.objects.binary import BinaryInputObject, BinaryValueObject
    from bac_py.objects.calendar import CalendarObject
    from bac_py.objects.device import DeviceObject
    from bac_py.objects.event_enrollment import EventEnrollmentObject
    from bac_py.objects.notification import NotificationClassObject
    from bac_py.objects.schedule import ScheduleObject
    from bac_py.objects.trendlog import TrendLogObject
    from bac_py.types.constructed import (
        BACnetCalendarEntry,
        BACnetDeviceObjectPropertyReference,
        BACnetTimeValue,
    )
    from bac_py.types.enums import (
        BinaryPV,
        EngineeringUnits,
        EventType,
        LoggingType,
        NotifyType,
        ObjectType,
        PropertyIdentifier,
    )
    from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

    instance = int(os.environ.get("DEVICE_INSTANCE", "500"))
    port = int(os.environ.get("BACNET_PORT", "47808"))

    broadcast_address = os.environ.get("BROADCAST_ADDRESS", "255.255.255.255")

    config = DeviceConfig(
        instance_number=instance,
        name=f"Smart-Thermostat-{instance}",
        port=port,
        broadcast_address=broadcast_address,
    )
    app = BACnetApplication(config)
    await app.start()

    # ---- Device ----
    device = DeviceObject(
        instance,
        object_name=f"Smart-Thermostat-{instance}",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-thermostat",
        firmware_revision="1.2.0",
        application_software_version="1.2.0",
    )
    app.object_db.add(device)

    # ---- Analog Inputs (sensors) ----
    zone_temp = AnalogInputObject(
        1,
        object_name="Zone-Temperature",
        present_value=72.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    outside_temp = AnalogInputObject(
        2,
        object_name="Outside-Temperature",
        present_value=OUTSIDE_TEMP_BASE,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )

    # ---- Analog Outputs (actuators) ----
    heating_out = AnalogOutputObject(
        1,
        object_name="Heating-Output",
        present_value=0.0,
        units=EngineeringUnits.PERCENT,
    )
    cooling_out = AnalogOutputObject(
        2,
        object_name="Cooling-Output",
        present_value=0.0,
        units=EngineeringUnits.PERCENT,
    )

    # ---- Analog Values (setpoints -- commandable) ----
    heating_sp = AnalogValueObject(
        1,
        object_name="Heating-Setpoint",
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
        commandable=True,
    )
    heating_sp._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = OCCUPIED_HEATING_SP
    heating_sp._properties[PropertyIdentifier.PRESENT_VALUE] = OCCUPIED_HEATING_SP
    cooling_sp = AnalogValueObject(
        2,
        object_name="Cooling-Setpoint",
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
        commandable=True,
    )
    cooling_sp._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = OCCUPIED_COOLING_SP
    cooling_sp._properties[PropertyIdentifier.PRESENT_VALUE] = OCCUPIED_COOLING_SP
    deadband_obj = AnalogValueObject(
        3,
        object_name="Deadband",
        present_value=2.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )

    # ---- Binary objects ----
    occupancy_sensor = BinaryInputObject(1, object_name="Occupancy-Sensor")
    system_enable = BinaryValueObject(
        1,
        object_name="System-Enable",
        commandable=True,
    )
    system_enable._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = BinaryPV.ACTIVE
    system_enable._properties[PropertyIdentifier.PRESENT_VALUE] = BinaryPV.ACTIVE
    fan_status = BinaryValueObject(2, object_name="Fan-Status")

    for obj in (
        zone_temp,
        outside_temp,
        heating_out,
        cooling_out,
        heating_sp,
        cooling_sp,
        deadband_obj,
        occupancy_sensor,
        system_enable,
        fan_status,
    ):
        app.object_db.add(obj)

    # ---- Schedule (weekday occupied 8am-6pm) ----
    schedule = ScheduleObject(1, object_name="Occupancy-Schedule")
    occupied_day = [
        BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=0),
        BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=1),
        BACnetTimeValue(time=BACnetTime(18, 0, 0, 0), value=0),
    ]
    unoccupied_day = [
        BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=0),
    ]
    schedule._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = [
        occupied_day,  # Monday
        occupied_day,  # Tuesday
        occupied_day,  # Wednesday
        occupied_day,  # Thursday
        occupied_day,  # Friday
        unoccupied_day,  # Saturday
        unoccupied_day,  # Sunday
    ]
    schedule._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 0
    app.object_db.add(schedule)

    # ---- Calendar ----
    calendar = CalendarObject(1, object_name="Holiday-Calendar")
    calendar._properties[PropertyIdentifier.DATE_LIST] = [
        BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 12, 25, 0xFF)),  # Christmas
        BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 1, 1, 0xFF)),  # New Year's
    ]
    app.object_db.add(calendar)

    # ---- Trend Logs ----
    tl_zone = TrendLogObject(1, object_name="Zone-Temp-Log")
    tl_zone._properties[PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY] = (
        BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
        )
    )
    tl_zone._properties[PropertyIdentifier.LOG_ENABLE] = True
    tl_zone._properties[PropertyIdentifier.LOG_INTERVAL] = 1000  # 10s in centiseconds
    tl_zone._properties[PropertyIdentifier.BUFFER_SIZE] = 100
    tl_zone._properties[PropertyIdentifier.STOP_WHEN_FULL] = False
    tl_zone._properties[PropertyIdentifier.LOGGING_TYPE] = LoggingType.POLLED
    app.object_db.add(tl_zone)

    tl_heating = TrendLogObject(2, object_name="Heating-Output-Log")
    tl_heating._properties[PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY] = (
        BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
        )
    )
    tl_heating._properties[PropertyIdentifier.LOG_ENABLE] = True
    tl_heating._properties[PropertyIdentifier.LOG_INTERVAL] = 1000
    tl_heating._properties[PropertyIdentifier.BUFFER_SIZE] = 100
    tl_heating._properties[PropertyIdentifier.STOP_WHEN_FULL] = False
    tl_heating._properties[PropertyIdentifier.LOGGING_TYPE] = LoggingType.POLLED
    app.object_db.add(tl_heating)

    # ---- Notification Class ----
    nc = NotificationClassObject(1, object_name="HVAC-Alarms")
    nc._properties[PropertyIdentifier.PRIORITY] = [3, 3, 3]
    nc._properties[PropertyIdentifier.ACK_REQUIRED] = [True, False, False]
    app.object_db.add(nc)

    # ---- Event Enrollments ----
    ee_high = EventEnrollmentObject(1, object_name="High-Temp-Alarm")
    ee_high._properties[PropertyIdentifier.EVENT_TYPE] = EventType.OUT_OF_RANGE
    ee_high._properties[PropertyIdentifier.OBJECT_PROPERTY_REFERENCE] = (
        BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
        )
    )
    ee_high._properties[PropertyIdentifier.EVENT_PARAMETERS] = {
        "time_delay": 5,
        "low_limit": -100.0,
        "high_limit": 85.0,
        "deadband": 1.0,
    }
    ee_high._properties[PropertyIdentifier.NOTIFICATION_CLASS] = 1
    ee_high._properties[PropertyIdentifier.NOTIFY_TYPE] = NotifyType.ALARM
    app.object_db.add(ee_high)

    ee_low = EventEnrollmentObject(2, object_name="Low-Temp-Alarm")
    ee_low._properties[PropertyIdentifier.EVENT_TYPE] = EventType.OUT_OF_RANGE
    ee_low._properties[PropertyIdentifier.OBJECT_PROPERTY_REFERENCE] = (
        BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
        )
    )
    ee_low._properties[PropertyIdentifier.EVENT_PARAMETERS] = {
        "time_delay": 5,
        "low_limit": 50.0,
        "high_limit": 200.0,
        "deadband": 1.0,
    }
    ee_low._properties[PropertyIdentifier.NOTIFICATION_CLASS] = 1
    ee_low._properties[PropertyIdentifier.NOTIFY_TYPE] = NotifyType.ALARM
    app.object_db.add(ee_low)

    # ---- Register handlers ----
    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()

    # ---- Start engines ----
    schedule_engine = ScheduleEngine(app, scan_interval=10.0)
    await schedule_engine.start()

    trendlog_engine = TrendLogEngine(app, scan_interval=1.0)
    await trendlog_engine.start()

    logger.info("Smart thermostat running: device %d on port %d", instance, port)
    _write_healthy()

    # ---- Simulation loop ----
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    sim_task = asyncio.create_task(
        _simulation_loop(
            stop,
            zone_temp=zone_temp,
            outside_temp=outside_temp,
            heating_out=heating_out,
            cooling_out=cooling_out,
            heating_sp=heating_sp,
            cooling_sp=cooling_sp,
            deadband_obj=deadband_obj,
            occupancy_sensor=occupancy_sensor,
            system_enable=system_enable,
            fan_status=fan_status,
            schedule=schedule,
        )
    )

    await stop.wait()
    sim_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sim_task

    logger.info("Shutting down thermostat...")
    await trendlog_engine.stop()
    await schedule_engine.stop()
    await app.stop()


async def _simulation_loop(
    stop: asyncio.Event,
    *,
    zone_temp: Any,
    outside_temp: Any,
    heating_out: Any,
    cooling_out: Any,
    heating_sp: Any,
    cooling_sp: Any,
    deadband_obj: Any,
    occupancy_sensor: Any,
    system_enable: Any,
    fan_status: Any,
    schedule: Any,
) -> None:
    from bac_py.types.enums import BinaryPV, PropertyIdentifier

    current_zone = 72.0
    current_heat_out = 0.0
    current_cool_out = 0.0
    start_time = time.monotonic()
    step = 0

    while not stop.is_set():
        await asyncio.sleep(SIM_INTERVAL)
        step += 1
        elapsed = time.monotonic() - start_time

        # --- Read inputs ---
        sys_on = _get_commandable_value(system_enable, BinaryPV.ACTIVE)
        heat_sp_val = _get_commandable_value(heating_sp, OCCUPIED_HEATING_SP)
        cool_sp_val = _get_commandable_value(cooling_sp, OCCUPIED_COOLING_SP)
        db = deadband_obj._properties.get(PropertyIdentifier.PRESENT_VALUE, 2.0)

        # --- Outside temperature (sine wave) ---
        outside_val = OUTSIDE_TEMP_BASE + OUTSIDE_TEMP_AMPLITUDE * math.sin(
            2 * math.pi * elapsed / OUTSIDE_TEMP_PERIOD
        )

        # --- Control logic ---
        if sys_on == BinaryPV.INACTIVE or sys_on == 0:
            current_heat_out = 0.0
            current_cool_out = 0.0
        else:
            if current_zone < heat_sp_val - db:
                current_heat_out = min(100.0, current_heat_out + RAMP_STEP)
            elif current_zone > heat_sp_val:
                current_heat_out = max(0.0, current_heat_out - RAMP_STEP)

            if current_zone > cool_sp_val + db:
                current_cool_out = min(100.0, current_cool_out + RAMP_STEP)
            elif current_zone < cool_sp_val:
                current_cool_out = max(0.0, current_cool_out - RAMP_STEP)

        # --- Temperature model ---
        current_zone += (outside_val - current_zone) * DRIFT_RATE
        current_zone += current_heat_out * HEAT_RATE / 100.0
        current_zone -= current_cool_out * COOL_RATE / 100.0

        # --- Update BACnet objects ---
        zone_temp._properties[PropertyIdentifier.PRESENT_VALUE] = round(current_zone, 1)
        outside_temp._properties[PropertyIdentifier.PRESENT_VALUE] = round(outside_val, 1)
        heating_out._properties[PropertyIdentifier.PRESENT_VALUE] = round(current_heat_out, 1)
        cooling_out._properties[PropertyIdentifier.PRESENT_VALUE] = round(current_cool_out, 1)

        fan_on = current_heat_out > 0 or current_cool_out > 0
        fan_status._properties[PropertyIdentifier.PRESENT_VALUE] = (
            BinaryPV.ACTIVE if fan_on else BinaryPV.INACTIVE
        )

        # Occupancy from schedule
        sched_val = schedule._properties.get(PropertyIdentifier.PRESENT_VALUE, 0)
        is_occupied = sched_val in (1, 1.0, True)
        occupancy_sensor._properties[PropertyIdentifier.PRESENT_VALUE] = (
            BinaryPV.ACTIVE if is_occupied else BinaryPV.INACTIVE
        )

        # Periodic log
        if step % 5 == 0:
            logger.info(
                "Zone=%.1f\u00b0F Outside=%.1f\u00b0F Heat=%.0f%% Cool=%.0f%% "
                "HSP=%.1f CSP=%.1f Fan=%s Occ=%s",
                current_zone,
                outside_val,
                current_heat_out,
                current_cool_out,
                heat_sp_val,
                cool_sp_val,
                "ON" if fan_on else "OFF",
                "Y" if is_occupied else "N",
            )
