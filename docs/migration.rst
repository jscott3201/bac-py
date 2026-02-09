Migration Guide
===============

This guide shows how to migrate from the protocol-level API
(``BACnetApplication`` + ``BACnetClient``) to the simplified
``Client`` convenience API.

Reading a Property
------------------

**Before** (protocol-level)::

    from bac_py.app.application import BACnetApplication, DeviceConfig
    from bac_py.app.client import BACnetClient
    from bac_py.encoding.primitives import decode_application_value
    from bac_py.encoding.tags import decode_tag
    from bac_py.network.address import BACnetAddress, BIPAddress
    from bac_py.types.enums import ObjectType, PropertyIdentifier
    from bac_py.types.primitives import ObjectIdentifier

    config = DeviceConfig(instance_number=999)
    app = BACnetApplication(config)
    await app.start()

    client = BACnetClient(app)

    mac = BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
    address = BACnetAddress(mac_address=mac)
    obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
    prop_id = PropertyIdentifier.PRESENT_VALUE

    ack = await client.read_property(address, obj_id, prop_id)
    tag, offset = decode_tag(ack.property_value, 0)
    value = decode_application_value(tag, ack.property_value[offset:offset + tag.length])

    await app.stop()

**After** (convenience API)::

    from bac_py import Client

    async with Client(instance_number=999) as client:
        value = await client.read("192.168.1.100", "ai,1", "pv")


Writing a Property
------------------

**Before**::

    from bac_py.encoding.primitives import encode_application_real

    encoded = encode_application_real(72.5)
    await client.write_property(address, obj_id, prop_id, encoded, priority=8)

**After**::

    await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)

The convenience ``write()`` method automatically encodes Python values
to the correct BACnet application tag based on the value type, object
type, and property type hints:

- ``float`` → Real
- ``int`` to analog PV → Real
- ``int`` to binary PV → Enumerated
- ``int`` to multi-state PV → Unsigned
- ``str`` → Character String
- ``bool`` → Enumerated (1/0)
- ``None`` → Null (relinquish a priority)
- ``IntEnum`` → Enumerated
- ``bytes`` → pass-through (already-encoded)

For non-present-value properties, a built-in type hint map ensures
common properties like ``units``, ``cov-increment``, and
``out-of-service`` are encoded with the correct application tag even
when an ``int`` is passed.


Reading Multiple Properties
---------------------------

**Before**::

    from bac_py.services.read_property_multiple import ReadAccessSpecification

    specs = [
        ReadAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_property_references=[
                PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                PropertyReference(PropertyIdentifier.OBJECT_NAME),
            ],
        ),
    ]
    ack = await client.read_property_multiple(address, specs)
    # ... manual decoding of each result ...

**After**::

    results = await client.read_multiple("192.168.1.100", {
        "ai,1": ["pv", "object-name", "units"],
        "ai,2": ["pv", "object-name"],
    })
    # results["analog-input,1"]["present-value"] -> 72.5


Discovering Devices
-------------------

**Before** (``who_is`` returns raw ``IAmRequest`` objects)::

    responses = await client.who_is(timeout=3.0)
    for iam in responses:
        instance = iam.object_identifier.instance_number
        vendor = iam.vendor_id
        # Source address not available

**After** (``discover`` returns ``DiscoveredDevice`` with address)::

    devices = await client.discover(timeout=3.0)
    for dev in devices:
        print(dev.instance, dev.address_str, dev.vendor_id)

The ``who_is()`` method still exists for cases where you need the
raw ``IAmRequest`` objects.


Addressing
----------

The convenience API accepts addresses as strings. All of these work::

    # IP only (default BACnet port 47808)
    await client.read("192.168.1.100", "ai,1", "pv")

    # IP with explicit port
    await client.read("192.168.1.100:47808", "ai,1", "pv")

    # Routed address (network:ip:port)
    await client.read("5:192.168.1.100:47808", "ai,1", "pv")


Object and Property Identifiers
--------------------------------

String identifiers support both full names and common abbreviations::

    # Full names
    await client.read(addr, "analog-input,1", "present-value")

    # Short aliases
    await client.read(addr, "ai,1", "pv")

    # Tuples also work
    await client.read(addr, ("analog-input", 1), "present-value")

    # Enum values still work
    from bac_py.types.enums import ObjectType, PropertyIdentifier
    from bac_py.types.primitives import ObjectIdentifier

    await client.read(addr, ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                      PropertyIdentifier.PRESENT_VALUE)


Progressive Disclosure
----------------------

The ``Client`` class provides the simplified API for common tasks.
For advanced use cases, the underlying layers are still available:

- ``client.app`` — access the ``BACnetApplication`` for handler
  registration, COV callbacks, and transport-level control.
- ``client.read_property()`` / ``client.write_property()`` — protocol-level
  methods with explicit types and raw bytes.
- ``BACnetApplication`` + ``BACnetClient`` — direct instantiation for
  server handlers, router mode, and custom service registration.
