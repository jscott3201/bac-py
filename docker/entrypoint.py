"""Role-based container entrypoint for BACnet Docker testing."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("entrypoint")

# Subnet-directed broadcast for Docker bridge networks (global broadcast
# 255.255.255.255 is not routable on bridge networks).
BROADCAST_ADDRESS = os.environ.get("BROADCAST_ADDRESS", "255.255.255.255")


async def run_server() -> None:
    """Run a BACnet server with sample objects."""
    from bac_py.app.application import BACnetApplication, DeviceConfig
    from bac_py.app.server import DefaultServerHandlers
    from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
    from bac_py.objects.binary import BinaryInputObject, BinaryValueObject
    from bac_py.objects.device import DeviceObject
    from bac_py.types.enums import EngineeringUnits

    instance = int(os.environ.get("DEVICE_INSTANCE", "100"))
    port = int(os.environ.get("BACNET_PORT", "47808"))

    config = DeviceConfig(
        instance_number=instance,
        name=f"Docker-Device-{instance}",
        port=port,
        broadcast_address=BROADCAST_ADDRESS,
    )
    app = BACnetApplication(config)
    await app.start()

    # Create device object
    device = DeviceObject(
        instance,
        object_name=f"Docker-Device-{instance}",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-docker",
        firmware_revision="1.2.0",
        application_software_version="1.2.0",
    )
    app.object_db.add(device)

    # Sample objects
    ai = AnalogInputObject(
        1,
        object_name="Temperature",
        present_value=72.5,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    ao = AnalogOutputObject(
        1,
        object_name="Setpoint-Output",
        present_value=68.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    av = AnalogValueObject(
        1,
        object_name="Setpoint",
        present_value=70.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
        commandable=True,
    )
    bi = BinaryInputObject(1, object_name="Occupancy")
    bv = BinaryValueObject(1, object_name="Override", commandable=True)

    for obj in (ai, ao, av, bi, bv):
        app.object_db.add(obj)

    # Register default handlers
    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()

    logger.info("Server running: device %d on port %d", instance, port)

    # Write health marker
    _write_healthy()

    # Block until SIGTERM/SIGINT
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("Shutting down server...")
    await app.stop()


async def run_bbmd() -> None:
    """Run a BACnet server with BBMD enabled."""
    from bac_py.app.application import BACnetApplication, DeviceConfig
    from bac_py.app.server import DefaultServerHandlers
    from bac_py.objects.analog import AnalogInputObject
    from bac_py.objects.device import DeviceObject
    from bac_py.types.enums import EngineeringUnits

    instance = int(os.environ.get("DEVICE_INSTANCE", "200"))
    port = int(os.environ.get("BACNET_PORT", "47808"))

    config = DeviceConfig(
        instance_number=instance,
        name=f"Docker-BBMD-{instance}",
        port=port,
        broadcast_address=BROADCAST_ADDRESS,
    )
    app = BACnetApplication(config)
    await app.start()

    # Attach BBMD functionality (empty BDT = foreign-device-only mode)
    if app._transport is not None:
        await app._transport.attach_bbmd()
        logger.info("BBMD attached on port %d", port)

    device = DeviceObject(
        instance,
        object_name=f"Docker-BBMD-{instance}",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-docker-bbmd",
        firmware_revision="1.2.0",
        application_software_version="1.2.0",
    )
    app.object_db.add(device)

    ai = AnalogInputObject(
        1,
        object_name="BBMD-Temperature",
        present_value=65.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    app.object_db.add(ai)

    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()

    logger.info("BBMD server running: device %d on port %d", instance, port)
    _write_healthy()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("Shutting down BBMD...")
    await app.stop()


async def run_router() -> None:
    """Run a BACnet router bridging two networks."""
    from bac_py.app.application import (
        BACnetApplication,
        DeviceConfig,
        RouterConfig,
        RouterPortConfig,
    )
    from bac_py.app.server import DefaultServerHandlers
    from bac_py.objects.device import DeviceObject

    instance = int(os.environ.get("DEVICE_INSTANCE", "300"))
    net1 = int(os.environ.get("NETWORK_1", "1"))
    net2 = int(os.environ.get("NETWORK_2", "2"))
    iface1 = os.environ.get("INTERFACE_1", "0.0.0.0")
    iface2 = os.environ.get("INTERFACE_2", "0.0.0.0")
    port1 = int(os.environ.get("PORT_1", "47808"))
    port2 = int(os.environ.get("PORT_2", "47809"))

    router_config = RouterConfig(
        ports=[
            RouterPortConfig(port_id=1, network_number=net1, interface=iface1, port=port1),
            RouterPortConfig(port_id=2, network_number=net2, interface=iface2, port=port2),
        ],
        application_port_id=1,
    )

    config = DeviceConfig(
        instance_number=instance,
        name=f"Docker-Router-{instance}",
        router_config=router_config,
        broadcast_address=BROADCAST_ADDRESS,
    )
    app = BACnetApplication(config)
    await app.start()

    device = DeviceObject(
        instance,
        object_name=f"Docker-Router-{instance}",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-docker-router",
        firmware_revision="1.2.0",
        application_software_version="1.2.0",
    )
    app.object_db.add(device)

    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()

    logger.info(
        "Router running: device %d, net %d (port %d) <-> net %d (port %d)",
        instance,
        net1,
        port1,
        net2,
        port2,
    )
    _write_healthy()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("Shutting down router...")
    await app.stop()


async def run_server_extended() -> None:
    """Run a BACnet server with additional objects for advanced integration tests.

    Extends the basic server with: extra analog objects (for segmentation
    testing), notification class + event enrollment (for alarm/event testing),
    and audit reporter/log (for audit testing).
    """
    from bac_py.app.application import BACnetApplication, DeviceConfig
    from bac_py.app.audit import AuditManager
    from bac_py.app.server import DefaultServerHandlers
    from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
    from bac_py.objects.audit_log import AuditLogObject
    from bac_py.objects.audit_reporter import AuditReporterObject
    from bac_py.objects.binary import BinaryInputObject, BinaryValueObject
    from bac_py.objects.device import DeviceObject
    from bac_py.objects.event_enrollment import EventEnrollmentObject
    from bac_py.objects.notification import NotificationClassObject
    from bac_py.types.constructed import BACnetDeviceObjectPropertyReference
    from bac_py.types.enums import (
        AuditLevel,
        EngineeringUnits,
        EventType,
        ObjectType,
        PropertyIdentifier,
    )
    from bac_py.types.primitives import ObjectIdentifier

    instance = int(os.environ.get("DEVICE_INSTANCE", "600"))
    port = int(os.environ.get("BACNET_PORT", "47808"))

    config = DeviceConfig(
        instance_number=instance,
        name=f"Docker-Extended-{instance}",
        port=port,
        broadcast_address=BROADCAST_ADDRESS,
    )
    app = BACnetApplication(config)
    await app.start()

    device = DeviceObject(
        instance,
        object_name=f"Docker-Extended-{instance}",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-docker-extended",
        firmware_revision="1.2.0",
        application_software_version="1.2.0",
    )
    app.object_db.add(device)

    # --- Basic objects (same as standard server) ---
    ai1 = AnalogInputObject(
        1,
        object_name="Temperature",
        present_value=72.5,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    ao1 = AnalogOutputObject(
        1,
        object_name="Setpoint-Output",
        present_value=68.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    av1 = AnalogValueObject(
        1,
        object_name="Setpoint",
        present_value=70.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
        commandable=True,
    )
    bi1 = BinaryInputObject(1, object_name="Occupancy")
    bv1 = BinaryValueObject(1, object_name="Override", commandable=True)

    for obj in (ai1, ao1, av1, bi1, bv1):
        app.object_db.add(obj)

    # --- Extra analog objects (for segmentation / RPM testing) ---
    for i in range(2, 22):
        ai = AnalogInputObject(
            i,
            object_name=f"Sensor-{i}",
            present_value=60.0 + i * 0.5,
            units=EngineeringUnits.DEGREES_FAHRENHEIT,
        )
        app.object_db.add(ai)

    # --- Notification Class (for alarm/event testing) ---
    nc = NotificationClassObject(1, object_name="Alarms")
    nc._properties[PropertyIdentifier.PRIORITY] = [3, 3, 3]
    nc._properties[PropertyIdentifier.ACK_REQUIRED] = [True, False, False]
    app.object_db.add(nc)

    # --- Event Enrollment monitoring ai,1 (for alarm testing) ---
    ee = EventEnrollmentObject(
        1,
        object_name="TempHighAlarm",
        event_type=EventType.OUT_OF_RANGE,
    )
    ee._properties[PropertyIdentifier.OBJECT_PROPERTY_REFERENCE] = (
        BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
    )
    ee._properties[PropertyIdentifier.NOTIFICATION_CLASS] = 1
    ee._properties[PropertyIdentifier.EVENT_PARAMETERS] = {
        "low_limit": 50.0,
        "high_limit": 90.0,
        "deadband": 2.0,
        "time_delay": 0,
    }
    app.object_db.add(ee)

    # --- Audit Reporter + Audit Log (for audit testing) ---
    reporter = AuditReporterObject(1, object_name="AuditReporter-1")
    reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = AuditLevel.AUDIT_ALL
    app.object_db.add(reporter)

    audit_log = AuditLogObject(1, object_name="AuditLog-1")
    audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
    audit_log._properties[PropertyIdentifier.BUFFER_SIZE] = 1000
    audit_log._properties[PropertyIdentifier.STOP_WHEN_FULL] = False
    app.object_db.add(audit_log)

    # Wire up audit manager
    app._audit_manager = AuditManager(app.object_db)

    # Register default handlers
    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()

    logger.info(
        "Extended server running: device %d on port %d (%d objects)",
        instance,
        port,
        len(list(app.object_db)),
    )
    _write_healthy()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("Shutting down extended server...")
    await app.stop()


async def run_sc_hub() -> None:
    """Run a BACnet/SC hub function (WebSocket server)."""
    from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
    from bac_py.transport.sc.tls import SCTLSConfig
    from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

    bind_address = os.environ.get("BIND_ADDRESS", "0.0.0.0")
    bind_port = int(os.environ.get("BIND_PORT", "4443"))

    hub = SCHubFunction(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCHubConfig(
            bind_address=bind_address,
            bind_port=bind_port,
            tls_config=SCTLSConfig(allow_plaintext=True),
        ),
    )
    await hub.start()

    logger.info("SC Hub running on %s:%d", bind_address, bind_port)
    _write_healthy()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("Shutting down SC Hub...")
    await hub.stop()


async def run_sc_node() -> None:
    """Run a BACnet/SC node that connects to a hub and echoes NPDUs."""
    from bac_py.transport.sc import SCTransport, SCTransportConfig
    from bac_py.transport.sc.node_switch import SCNodeSwitchConfig
    from bac_py.transport.sc.tls import SCTLSConfig
    from bac_py.transport.sc.vmac import SCVMAC

    hub_uri = os.environ.get("HUB_URI", "ws://172.30.1.120:4443")
    vmac_hex = os.environ.get("VMAC", "")
    node_switch_port = int(os.environ.get("NODE_SWITCH_PORT", "0"))

    vmac = SCVMAC.from_hex(vmac_hex) if vmac_hex else None
    tls_config = SCTLSConfig(allow_plaintext=True)

    ns_config = None
    if node_switch_port:
        ns_config = SCNodeSwitchConfig(
            enable=True,
            bind_address="0.0.0.0",
            bind_port=node_switch_port,
            tls_config=tls_config,
        )

    transport = SCTransport(
        SCTransportConfig(
            primary_hub_uri=hub_uri,
            tls_config=tls_config,
            vmac=vmac,
            min_reconnect_time=0.5,
            max_reconnect_time=5.0,
            node_switch_config=ns_config,
        )
    )

    # Echo handler: on receive (npdu, source_mac) → send back b"ECHO:" + npdu
    def echo_handler(npdu: bytes, source_mac: bytes) -> None:
        logger.debug("Received %d bytes from %s, echoing", len(npdu), source_mac.hex())
        transport.send_unicast(b"ECHO:" + npdu, source_mac)

    transport.on_receive(echo_handler)
    await transport.start()

    connected = await transport.hub_connector.wait_connected(timeout=30)
    if connected:
        logger.info(
            "SC Node connected to hub %s (VMAC=%s)",
            hub_uri,
            ":".join(f"{b:02X}" for b in transport.local_mac),
        )
        _write_healthy()
    else:
        logger.error("SC Node failed to connect to hub %s", hub_uri)
        sys.exit(1)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    logger.info("Shutting down SC Node...")
    await transport.stop()


def run_test() -> None:
    """Run pytest on a specific scenario file."""
    test_file = os.environ.get("TEST_FILE", "")
    if not test_file:
        logger.error("TEST_FILE env var not set")
        sys.exit(1)

    test_path = f"docker/scenarios/{test_file}"
    logger.info("Running tests: %s", test_path)

    result = subprocess.run(
        ["uv", "run", "pytest", test_path, "-v", "-s", "--tb=short", "-x"],
        cwd="/app",
    )
    sys.exit(result.returncode)


def run_stress() -> None:
    """Run the stress test runner."""
    logger.info("Running stress tests...")
    result = subprocess.run(
        ["uv", "run", "python", "docker/lib/stress_runner.py"],
        cwd="/app",
    )
    sys.exit(result.returncode)


async def run_thermostat() -> None:
    """Run the smart thermostat demo server."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "thermostat", os.path.join(os.path.dirname(__file__), "demos", "thermostat.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    await mod.run()


def run_demo_client() -> None:
    """Run the interactive thermostat demo client."""
    logger.info("Running demo client...")
    result = subprocess.run(
        ["uv", "run", "python", "docker/demos/demo_client.py"],
        cwd="/app",
    )
    sys.exit(result.returncode)


def _write_healthy() -> None:
    """Write health marker file for Docker healthcheck."""
    with open("/tmp/healthy", "w") as f:
        f.write("ok")


def main() -> None:
    """Dispatch based on ROLE env var."""
    role = os.environ.get("ROLE", "").lower()

    if role == "server":
        asyncio.run(run_server())
    elif role == "server-extended":
        asyncio.run(run_server_extended())
    elif role == "bbmd":
        asyncio.run(run_bbmd())
    elif role == "router":
        asyncio.run(run_router())
    elif role == "sc-hub":
        asyncio.run(run_sc_hub())
    elif role == "sc-node":
        asyncio.run(run_sc_node())
    elif role == "test":
        run_test()
    elif role == "stress":
        run_stress()
    elif role == "thermostat":
        asyncio.run(run_thermostat())
    elif role == "demo-client":
        run_demo_client()
    else:
        logger.error(
            "Unknown ROLE: %r (expected: server, server-extended, bbmd, router, "
            "sc-hub, sc-node, test, stress, thermostat, demo-client)",
            role,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
