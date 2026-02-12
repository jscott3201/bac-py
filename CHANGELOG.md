# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
