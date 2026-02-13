# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-02-12

### Added

- **5 new example scripts** -- `device_control.py` (communication control,
  reinitialization, time synchronization), `object_management.py` (create,
  list, and delete objects), `advanced_discovery.py` (Who-Has, unconfigured
  device discovery, hierarchy traversal), `cov_property.py` (property-level
  COV subscriptions with increment), `audit_log.py` (audit log queries with
  pagination). Total example count is now 17.
- **`get_enrollment_summary()` example** in `alarm_management.py` --
  demonstrates querying enrollment summaries with acknowledgment filtering.

### Fixed

- **`extended_discovery.py`** -- changed `dev.address` to `dev.address_str`
  for consistency with all other example scripts.

### Changed

- Updated README examples table and documentation to reflect the 5 new
  example scripts.
- Added `get_enrollment_summary()` to the events-alarms guide and features
  convenience API list.

## [1.1.0] - 2026-02-12

### Added

- **4 new `Client` wrapper methods** -- `traverse_hierarchy()` walks Structured
  View object hierarchies with string addressing; `subscribe_cov_property_multiple()`
  batches property-level COV subscriptions in a single request;
  `write_group()` sends unconfirmed WriteGroup channel writes;
  `discover_unconfigured()` finds unconfigured devices via Who-Am-I (Clause 19.7).
- **`UnconfiguredDevice` top-level export** -- `UnconfiguredDevice` is now
  importable directly from `bac_py`.
- ~40 new `Client` unit tests covering string address parsing, `BACnetAddress`
  pass-through, broadcast destination defaults, enum string parsing, and new
  wrapper delegation.

### Changed

- **Consistent string support across all `Client` methods** -- 11 methods that
  previously required typed parameters now accept strings:
  `time_synchronization` and `utc_time_synchronization` (address),
  `atomic_read_file` and `atomic_write_file` (address, file identifier),
  `confirmed_private_transfer` and `unconfirmed_private_transfer` (address),
  `add_list_element` and `remove_list_element` (address, object identifier,
  property identifier), `subscribe_cov` and `unsubscribe_cov` (address, object
  identifier), `who_has` (object identifier). All parsing functions handle
  typed pass-through, so existing code using `BACnetAddress` / `ObjectIdentifier`
  / `PropertyIdentifier` continues to work unchanged.
- **Internal deduplication** -- Extracted `_resolve_broadcast_destination()` and
  `_parse_enum()` helpers to replace ~20 copy-pasted address parsing, broadcast
  resolution, and enum parsing blocks across the `Client` class. Moved
  `parse_address` to a top-level import.
- **Documentation updates** -- Added `discover_unconfigured()` and `who_has()`
  string usage to the Discovery and Networking guide. Added
  `subscribe_cov_property_multiple()` example to the COV section. Updated
  `traverse_hierarchy` example in Features to use string-friendly syntax.
  Expanded the Convenience API feature list with new methods and consistent
  string support note.

## [1.0.2] - 2026-02-12

### Fixed

- **MS/TP and non-IP address parsing** -- `parse_address()` now supports
  `"NETWORK:HEXMAC"` format (e.g. `"4352:01"` for MS/TP devices behind routers),
  enabling the high-level Client to communicate with devices on remote non-IP
  data links discovered via BBMD or router forwarding.
- **Router path learning from routed APDUs** -- The network layer now learns
  router paths from the SNET/SADR fields of incoming routed APDUs. When a
  response arrives from a remote network, the transport-level sender is cached
  as the router for that network, enabling efficient unicast routing for
  subsequent requests instead of broadcasting.
- **`BACnetAddress.__str__()` round-trip completeness** -- Address string output
  for non-IP MACs (1-byte MS/TP, 2-byte ARCNET, etc.) now round-trips correctly
  through `parse_address()`.

### Changed

- **Documentation sidebar restructure** -- Split monolithic `examples.rst` (907
  lines) into 5 topical guide pages under `docs/guide/` (Reading and Writing
  Properties, Discovery and Networking, Events and Alarms, Server Mode, Device
  Management and Tools). Reorganized the Sphinx sidebar from 4 flat entries into
  3 captioned sections (Getting Started, User Guide, API Reference) with 17
  navigable entries. API modules are now listed directly in the top-level toctree
  instead of behind an intermediate landing page.
- **API reference sidebar overhaul** -- Split 3 monolithic API pages (Application,
  Services, Objects) into 12 focused sub-pages grouped by category. Application
  is now split into Client, Server, and Engines; Services into Property, Discovery,
  Events, and Management; Objects into Base, I/O, Scheduling, Monitoring, and
  Infrastructure. Removed `:undoc-members:` from all API documentation to reduce
  noise. Each sub-page now has a manageable right-hand table of contents instead
  of listing 20-30+ sections on a single page.
- **Hot-path performance optimizations** for typical building monitoring scenarios
  (100+ devices, 25-40 points each):
  - `parse_address()` string inputs now cached via `lru_cache` (O(1) repeated
    lookups in polling loops).
  - `_resolve_object_type()` and `_resolve_property_identifier()` alias
    resolution now cached via `lru_cache`.
  - `BIPAddress.encode()` uses `socket.inet_aton()` + `struct.pack()` instead
    of string splitting.
  - `encode_npdu()` pre-allocates bytearray to estimated packet size.
  - `COVManager.check_and_notify()` and `check_and_notify_property()` use
    secondary dict indices for O(k) dispatch (k = subscriptions on the changed
    object) instead of O(N) full scan of all subscriptions.
  - `ObjectDatabase.get_objects_of_type()` uses a type index for O(1) lookup
    instead of O(N) full scan.

### Added

- 137 new unit tests covering Ethernet/MS/TP support and performance optimizations:
  - NPDU variable MAC length encode/decode (1--8 byte SADR/DADR)
  - Mixed data link router forwarding (BIP↔MS/TP, 2-byte MAC, broadcasts)
  - Address `str()`↔`parse_address()` round-trips for all MAC formats
  - Network layer remote send with variable-length MACs and router cache learning
  - COV secondary index maintenance (subscribe/unsubscribe/expiry/shutdown)
  - ObjectDatabase type index (add/remove/query by type)

## [1.0.0] - 2026-02-12

### Added

- **Core protocol stack** -- Full BACnet/IP (Annex J) over UDP, ASN.1/BER
  encoding for all 13 primitive application tags, context-tagged constructed
  types, NPDU network layer with all 12 network messages, automatic segmented
  request/response handling (Clause 5.2), and Transaction State Machine with
  retry/timeout management.
- **All confirmed and unconfirmed services** -- ReadProperty, WriteProperty,
  ReadPropertyMultiple, WritePropertyMultiple, ReadRange, CreateObject,
  DeleteObject, AddListElement, RemoveListElement, AtomicReadFile,
  AtomicWriteFile, SubscribeCOV, SubscribeCOVProperty, EventNotification,
  AcknowledgeAlarm, GetAlarmSummary, GetEnrollmentSummary, GetEventInformation,
  ConfirmedTextMessage, DeviceCommunicationControl, ReinitializeDevice,
  ConfirmedPrivateTransfer, ConfirmedAuditNotification, AuditLogQuery,
  VT-Open/Close/Data, Who-Is/I-Am, Who-Has/I-Have, Who-Am-I/You-Are,
  TimeSynchronization, UnconfirmedCOVNotification, UnconfirmedEventNotification,
  UnconfirmedTextMessage, UnconfirmedAuditNotification, WriteGroup, and
  UnconfirmedPrivateTransfer.
- **62 object types** -- Device, Analog/Binary/MultiState I/O/Value,
  Accumulator, Averaging, Calendar, Channel, Command, Event Enrollment,
  Event Log, File, Global Group, Group, Life Safety Point/Zone, Load Control,
  Loop, Network Port, Notification Class, Notification Forwarder, Program,
  Pulse Converter, Schedule, Staging, Structured View, Timer, Trend Log,
  Trend Log Multiple, Audit Reporter, Audit Log, Alert Enrollment,
  Access Door/Point/Zone/User/Rights/Credential, Credential Data Input,
  Elevator Group, Lift, Escalator, Lighting Output, Binary Lighting Output,
  and 12 generic value types.
- **Event engine** -- All 18 standard event algorithms (change-of-bitstring,
  change-of-state, change-of-value, out-of-range, floating-limit,
  change-of-life-safety, change-of-discrete-value, etc.), intrinsic reporting
  for 9 object types, NotificationClass recipient list routing with day/time
  filtering and per-recipient confirmed/unconfirmed delivery.
- **Schedule engine** -- Weekly and exception schedules with calendar-aware
  evaluation, wildcard dates, week-n-day patterns, and priority-based
  resolution writing to target object property references.
- **Trend log engine** -- Polled, COV-based (Clause 12.25.13), and triggered
  acquisition modes with configurable circular buffer management and
  property-change callbacks.
- **Audit logging** -- AuditManager with automatic audit records for
  write/create/delete operations, AuditReporter and AuditLog objects with
  buffer management, ConfirmedAuditNotification/UnconfirmedAuditNotification
  services, and AuditLogQuery for retrieval.
- **COV manager** -- Subscription lifecycle management, increment threshold
  enforcement, property-level and object-level subscriptions, confirmed and
  unconfirmed notification delivery.
- **High-level Client API** -- Simplified async context manager with
  string-based addressing, short aliases (ai, ao, av, bi, bo, bv, msv, pv,
  name, desc, etc.), auto-encoding/decoding, and convenience wrappers for
  discover, read, write, read_multiple, write_multiple, subscribe_cov,
  get_alarm_summary, get_event_information, acknowledge_alarm,
  send_text_message, backup, restore, query_audit_log, subscribe_cov_property,
  create_object, delete_object, device_communication_control, and
  reinitialize_device.
- **Server handlers** -- DefaultServerHandlers for ReadProperty, WriteProperty,
  ReadPropertyMultiple, WritePropertyMultiple, ReadRange, Who-Is, COV
  subscriptions, CreateObject, DeleteObject, device management, file access,
  and audit instrumentation.
- **Network routing** -- Multi-port BACnet router with dynamic routing tables
  (Clause 6), Who-Is-Router-To-Network discovery, and cross-network message
  forwarding.
- **BBMD** -- Broadcast Management Device with foreign device registration,
  BDT/FDT table management, cross-subnet forwarding, and IPv4 multicast
  (Annex J.8).
- **BACnet Ethernet** -- Raw IEEE 802.3 transport with 802.2 LLC headers
  (DSAP/SSAP=0x82) per Clause 7, Linux AF_PACKET and macOS BPF support.
- **BACnet/IPv6** -- Full Annex U transport with 3-byte VMAC addressing,
  IPv6 multicast, address resolution with TTL caching, and foreign device
  registration.
- **Device info caching** -- Automatic caching of peer device capabilities
  from I-Am responses (Clause 19.4) for correct APDU size negotiation.
- **JSON serialization** -- `to_dict()`/`from_dict()` on all data types with
  optional `orjson` backend, time series export/import (Annex AA) in JSON
  and CSV formats.
- **Conformance and PICS generation** -- PICSGenerator with full object
  introspection, BIBBMatrix with 40+ BIBB definitions and auto-detection.
- **Docker integration tests** -- 8 scenarios (Client/Server, BBMD, Router,
  Stress, Device Management, COV Advanced, Events, Demo) with real UDP
  communication between containers using Docker Compose with isolated bridge
  networks.
- **12 example scripts** -- read_value, write_value, read_multiple,
  write_multiple, discover_devices, extended_discovery, monitor_cov,
  alarm_management, text_message, backup_restore, router_discovery, and
  foreign_device.
