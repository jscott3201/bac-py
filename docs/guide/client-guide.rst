.. _client-guide:

Client Guide
============

bac-py provides two API levels for client operations. This page is the
consolidated reference for all client capabilities, including features
documented elsewhere and those unique to this page.


.. _choosing-api-level:

Choosing an API Level
---------------------

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - :class:`~bac_py.client.Client`
     - :class:`~bac_py.app.client.BACnetClient`
   * - String addresses (``"1.2.3.4"``)
     - :class:`~bac_py.network.address.BACnetAddress` objects
   * - String identifiers (``"ai,1"``, ``"pv"``)
     - :class:`~bac_py.types.primitives.ObjectIdentifier`,
       :class:`~bac_py.types.enums.PropertyIdentifier` enums
   * - Auto-encodes Python values
     - Pre-encoded ``bytes`` for write values
   * - Async context manager
     - Requires a running
       :class:`~bac_py.app.application.BACnetApplication`
   * - Best for scripts, integrations
     - Best for servers, routers, custom protocol work

The ``Client`` wrapper exposes both levels. All ``BACnetClient`` methods are
available alongside the convenience methods, and the underlying application
is accessible via ``client.app``.

.. code-block:: python

   # Convenience API
   async with Client(instance_number=999) as client:
       value = await client.read("192.168.1.100", "ai,1", "pv")

   # Protocol-level API (same Client object)
   async with Client(instance_number=999) as client:
       from bac_py.network.address import parse_address
       from bac_py.types.enums import PropertyIdentifier, ObjectType
       from bac_py.types.primitives import ObjectIdentifier

       addr = parse_address("192.168.1.100")
       oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
       ack = await client.read_property(addr, oid, PropertyIdentifier.PRESENT_VALUE)


.. _client-transport-options:

Transport Options
------------------

``Client`` supports all bac-py transports via constructor parameters.
These are mutually exclusive -- at most one transport selector should be set:

.. code-block:: python

   # BACnet/IP (default)
   async with Client(instance_number=999) as client: ...

   # BACnet/IPv6 (Annex U)
   async with Client(instance_number=999, ipv6=True) as client: ...

   # BACnet/SC (Annex AB) -- requires bac-py[secure]
   from bac_py.transport.sc import SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   sc_config = SCTransportConfig(
       primary_hub_uri="wss://hub.example.com:8443",
       tls_config=SCTLSConfig(...),
   )
   async with Client(instance_number=999, sc_config=sc_config) as client: ...

   # BACnet Ethernet (Clause 7) -- requires root/CAP_NET_RAW
   async with Client(
       instance_number=999,
       ethernet_interface="eth0",
   ) as client: ...

See :doc:`transport-setup` for detailed transport configuration.


.. _capabilities-at-a-glance:

Capabilities at a Glance
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Capability
     - Method(s)
     - Guide
   * - Read properties
     - ``read()``, ``read_multiple()``
     - :ref:`reading-properties`
   * - Write properties
     - ``write()``, ``write_multiple()``
     - :ref:`writing-properties`
   * - Device discovery
     - ``who_is()``, ``discover()``, ``discover_extended()``
     - :ref:`device-discovery`
   * - Object search
     - ``who_has()``
     - :ref:`device-discovery`
   * - COV subscriptions
     - ``subscribe_cov()``, ``subscribe_cov_property()``
     - :ref:`cov-subscriptions`
   * - Alarm management
     - ``get_alarm_summary()``, ``acknowledge_alarm()``
     - :ref:`alarm-management`
   * - Event information
     - ``get_event_information()``, ``get_enrollment_summary()``
     - :ref:`event-notifications`
   * - Text messaging
     - ``send_text_message()``
     - :ref:`text-messaging`
   * - Object management
     - ``create_object()``, ``delete_object()``
     - :ref:`object-management-guide`
   * - Backup / restore
     - ``backup()``, ``restore()``
     - :ref:`backup-restore`
   * - Device control
     - ``device_communication_control()``, ``reinitialize_device()``
     - :ref:`device-control`
   * - Time sync
     - ``time_synchronization()``, ``utc_time_synchronization()``
     - :ref:`time-sync`
   * - Audit log queries
     - ``query_audit_log()``
     - :ref:`audit-logging-example`
   * - Foreign device
     - ``register_as_foreign_device()``
     - :ref:`foreign-device-registration`
   * - Router discovery
     - ``who_is_router_to_network()``
     - :ref:`router-discovery`
   * - File access
     - ``atomic_read_file()``, ``atomic_write_file()``
     - :ref:`file-access` *(below)*
   * - Private transfer
     - ``confirmed_private_transfer()``, ``unconfirmed_private_transfer()``
     - :ref:`private-transfer` *(below)*
   * - WriteGroup
     - ``write_group()``
     - :ref:`write-group` *(below)*
   * - Virtual terminal
     - ``vt_open()``, ``vt_data()``, ``vt_close()``
     - :ref:`virtual-terminal` *(below)*
   * - List elements
     - ``add_list_element()``, ``remove_list_element()``
     - :ref:`list-element-operations` *(below)*
   * - Hierarchy traversal
     - ``traverse_hierarchy()``
     - :ref:`hierarchy-traversal` *(below)*
   * - Unconfigured devices
     - ``discover_unconfigured()``
     - :ref:`device-discovery`


.. _file-access:

File Access
-----------

Read and write BACnet File objects using the AtomicReadFile and
AtomicWriteFile services (Clause 14). Two access methods are supported:
**stream** (byte-oriented) and **record** (record-oriented).

Stream access
^^^^^^^^^^^^^

.. code-block:: python

   from bac_py.services.file_access import StreamReadAccess, StreamWriteAccess

   # Read 1024 bytes starting at position 0
   ack = await client.atomic_read_file(
       "192.168.1.100",
       "file,1",
       StreamReadAccess(file_start_position=0, requested_octet_count=1024),
   )
   data = ack.file_data          # bytes
   eof = ack.end_of_file         # True if no more data
   start = ack.file_start_position

   # Read the entire file in chunks
   position = 0
   contents = bytearray()
   while True:
       ack = await client.atomic_read_file(
           "192.168.1.100", "file,1",
           StreamReadAccess(file_start_position=position, requested_octet_count=4096),
       )
       contents.extend(ack.file_data)
       if ack.end_of_file:
           break
       position += len(ack.file_data)

   # Write data at position 0
   await client.atomic_write_file(
       "192.168.1.100",
       "file,1",
       StreamWriteAccess(file_start_position=0, file_data=b"Hello BACnet"),
   )

Record access
^^^^^^^^^^^^^

.. code-block:: python

   from bac_py.services.file_access import RecordReadAccess, RecordWriteAccess

   # Read 10 records starting at record 0
   ack = await client.atomic_read_file(
       "192.168.1.100",
       "file,1",
       RecordReadAccess(file_start_record=0, requested_record_count=10),
   )
   records = ack.record_data     # list[bytes]
   eof = ack.end_of_file

   # Write records starting at record 0
   await client.atomic_write_file(
       "192.168.1.100",
       "file,1",
       RecordWriteAccess(file_start_record=0, record_data=[b"rec1", b"rec2"]),
   )


.. _private-transfer:

Private Transfer
----------------

Vendor-specific services use ConfirmedPrivateTransfer (Clause 16.2) and
UnconfirmedPrivateTransfer (Clause 16.3) to exchange proprietary data.

.. code-block:: python

   # Confirmed (request/response)
   ack = await client.confirmed_private_transfer(
       "192.168.1.100",
       vendor_id=999,
       service_number=1,
       service_parameters=b"\x01\x02\x03",  # vendor-defined encoding
   )
   result = ack.result_block  # vendor-defined response bytes

   # Unconfirmed (fire-and-forget)
   client.unconfirmed_private_transfer(
       "192.168.1.100",
       vendor_id=999,
       service_number=2,
       service_parameters=b"\x04\x05",
   )

The ``service_parameters`` and response ``result_block`` are opaque bytes
whose encoding is defined by the vendor. Both the ``vendor_id`` (ASHRAE-
assigned) and ``service_number`` (vendor-defined) identify the specific
operation.


.. _write-group:

WriteGroup
----------

WriteGroup (Clause 15.11) is an unconfirmed service for writing values to
multiple Channel objects via group addressing. It is commonly used in
lighting and HVAC control for coordinated group commands.

.. code-block:: python

   from bac_py.services.write_group import GroupChannelValue
   from bac_py.encoding.primitives import encode_application_real

   # Write to channels 1 and 2 at priority 8
   client.write_group(
       "192.168.1.255",  # broadcast to subnet
       group_number=1,
       write_priority=8,
       change_list=[
           GroupChannelValue(
               channel=1,
               value=encode_application_real(75.0),
           ),
           GroupChannelValue(
               channel=2,
               value=encode_application_real(50.0),
               overriding_priority=1,  # optional per-channel priority override
           ),
       ],
   )

Each :class:`~bac_py.services.write_group.GroupChannelValue` targets a
channel number with application-tagged encoded value bytes. The
``overriding_priority`` optionally overrides the request-level
``write_priority`` for that specific channel.

WriteGroup is fire-and-forget (unconfirmed) and is typically broadcast.


.. _virtual-terminal:

Virtual Terminal Sessions
-------------------------

The Virtual Terminal (VT) services (Clause 17) provide a character-based
terminal interface to BACnet devices, useful for device diagnostics and
configuration.

.. code-block:: python

   from bac_py.types.enums import VTClass

   # Open a session
   ack = await client.vt_open(
       "192.168.1.100",
       vt_class=VTClass.DEFAULT_TERMINAL,
       local_vt_session_identifier=1,
   )
   remote_session_id = ack.remote_vt_session_identifier

   # Send data
   data_ack = await client.vt_data(
       "192.168.1.100",
       vt_session_identifier=remote_session_id,
       vt_new_data=b"show status\r\n",
   )
   # data_ack.all_new_data_accepted indicates if device accepted all bytes
   # data_ack.accepted_octet_count is the number of bytes accepted

   # Close the session
   await client.vt_close(
       "192.168.1.100",
       session_identifiers=[remote_session_id],
   )

Supported VT classes: ``DEFAULT_TERMINAL``, ``ANSI_X3_64``, ``DEC_VT52``,
``DEC_VT100``, ``DEC_VT220``, ``HP_700_94``, ``IBM_3130``.


.. _list-element-operations:

List Element Operations
-----------------------

AddListElement and RemoveListElement (Clause 15.1--15.2) modify list-type
properties without replacing the entire list. This is useful for managing
recipient lists, object references, and other collection properties.

.. code-block:: python

   from bac_py.encoding.primitives import encode_application_unsigned

   # Add elements to a list property
   await client.add_list_element(
       "192.168.1.100",
       "notification-class,1",
       "recipient-list",
       list_of_elements=encode_application_unsigned(5),  # application-tagged
   )

   # Remove elements from a list property
   await client.remove_list_element(
       "192.168.1.100",
       "notification-class,1",
       "recipient-list",
       list_of_elements=encode_application_unsigned(5),
   )

The ``list_of_elements`` parameter takes pre-encoded bytes with
application-tagged values. Use the encoding primitives from
:mod:`bac_py.encoding.primitives` to build them.

An optional ``array_index`` parameter targets a specific element within
an array-of-lists property.


.. _hierarchy-traversal:

Hierarchy Traversal
-------------------

:meth:`~bac_py.client.Client.traverse_hierarchy` walks a StructuredView
object tree by recursively reading ``Subordinate_List`` properties. It
returns a flat list of all object identifiers found in the hierarchy.

.. code-block:: python

   # Get all objects under a structured view
   all_objects = await client.traverse_hierarchy(
       "192.168.1.100",
       "structured-view,1",
       max_depth=10,
   )
   for oid in all_objects:
       print(oid)

The ``max_depth`` parameter (default 10) limits recursion to prevent
infinite loops in misconfigured hierarchies. StructuredView objects found
during traversal are descended into; other object types are collected as
leaf nodes.


.. _protocol-level-api:

Protocol-Level API
------------------

For full control, use the protocol-level methods that accept typed objects
instead of strings. These are available on both ``Client`` and
``BACnetClient``.

.. code-block:: python

   from bac_py.network.address import parse_address
   from bac_py.types.enums import ObjectType, PropertyIdentifier
   from bac_py.types.primitives import ObjectIdentifier
   from bac_py.encoding.primitives import encode_application_real
   from bac_py.services.property_access import ReadAccessSpecification

   addr = parse_address("192.168.1.100")
   oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

   # ReadProperty -- returns ReadPropertyACK with raw property_value bytes
   ack = await client.read_property(addr, oid, PropertyIdentifier.PRESENT_VALUE)

   # WriteProperty -- value must be application-tagged encoded bytes
   await client.write_property(
       addr, oid, PropertyIdentifier.PRESENT_VALUE,
       value=encode_application_real(25.0),
       priority=8,
   )

   # ReadPropertyMultiple -- full control over access specifications
   specs = [ReadAccessSpecification(
       object_identifier=oid,
       list_of_property_references=[
           PropertyIdentifier.PRESENT_VALUE,
           PropertyIdentifier.STATUS_FLAGS,
       ],
   )]
   rpm_ack = await client.read_property_multiple(addr, specs)

   # ReadRange -- read trend log buffer entries
   from bac_py.services.read_range import RangeByPosition
   rr_ack = await client.read_range(
       addr,
       ObjectIdentifier(ObjectType.TREND_LOG, 1),
       PropertyIdentifier.LOG_BUFFER,
       range_qualifier=RangeByPosition(reference_index=1, count=100),
   )

See :ref:`two-api-levels` for guidance on when to use each level, and
:ref:`server-mode` for building servers with ``BACnetApplication`` directly.
