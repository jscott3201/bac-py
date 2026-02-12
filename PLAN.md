# High-Level API & Examples Improvement Plan

## Analysis Summary

### Current State

The `Client` class wraps `BACnetClient` with 2 tiers:
- **High-level (string-based):** `read`, `write`, `read_multiple`, `write_multiple`, `get_object_list`, `discover`, `who_is`, `who_has`, `subscribe_cov_ex`, `unsubscribe_cov_ex`
- **Low-level pass-through:** Everything else -- requires typed `BACnetAddress`, `ObjectIdentifier`, `PropertyIdentifier`, raw bytes

### Problems Identified

**1. Missing high-level wrappers for common user tasks**

These `BACnetClient` methods have no `Client` wrapper at all:

| Method | User Task | Difficulty for Beginners |
|--------|-----------|------------------------|
| `discover_extended()` | See device profiles/tags | Must use `BACnetClient` directly |
| `get_alarm_summary()` | Monitor active alarms | Must use `BACnetClient` directly |
| `get_event_information()` | Check event states | Must use `BACnetClient` directly |
| `acknowledge_alarm()` | Acknowledge an alarm | Must use `BACnetClient` directly |
| `backup_device()` | Back up a device | Must use `BACnetClient` directly |
| `restore_device()` | Restore a device | Must use `BACnetClient` directly |
| `send_confirmed_text_message()` | Send a text message | Must use `BACnetClient` directly |
| `send_unconfirmed_text_message()` | Send a text message (broadcast) | Must use `BACnetClient` directly |
| `subscribe_cov_property()` | COV on specific property | Must use `BACnetClient` directly |
| `query_audit_log()` | Query audit records | Must use `BACnetClient` directly |

**2. Existing Client methods that are low-level only**

These ARE on `Client` but still require typed objects, defeating the convenience pattern:

| Method | Requires |
|--------|----------|
| `create_object()` | `ObjectType` or `ObjectIdentifier` |
| `delete_object()` | `ObjectIdentifier` |
| `add_list_element()` | `ObjectIdentifier`, `PropertyIdentifier`, raw bytes |
| `remove_list_element()` | `ObjectIdentifier`, `PropertyIdentifier`, raw bytes |
| `device_communication_control()` | `BACnetAddress`, `EnableDisable` enum |
| `reinitialize_device()` | `BACnetAddress`, `ReinitializedState` enum |
| `atomic_read_file()` | `BACnetAddress`, `ObjectIdentifier`, access method |
| `atomic_write_file()` | `BACnetAddress`, `ObjectIdentifier`, access method |

**3. Example gaps**

No example scripts exist for:
- Alarm management (acknowledge, summary, event info)
- Backup/restore
- Text messaging
- ReadRange / trend log data retrieval
- Extended discovery (device profiles)
- Audit log queries
- WritePropertyMultiple (write_multiple)

**4. Inconsistencies**

- `who_is()` / `discover()` accept string destinations, but `device_communication_control()` / `reinitialize_device()` require `BACnetAddress`
- `subscribe_cov_ex()` accepts strings, but `subscribe_cov()` requires typed objects (both on Client)
- `create_object()` / `delete_object()` on Client require typed objects when they could easily accept strings like `"av,1"`

**5. Top-level exports missing common types**

Users frequently need these but must dig into submodules:
- `BACnetApplication`, `RouterConfig`, `RouterPortConfig` (for server use)
- `DefaultServerHandlers` (for server use)
- `DeviceObject` (for server use)
- Common object classes (`AnalogInputObject`, etc.) for server use

---

## Implementation Plan

### Phase 1: Add missing high-level wrappers to Client

Add string-based convenience wrappers to `Client` for common tasks that currently
require dropping to `BACnetClient`:

**1a. `Client.discover_extended(...)` → `list[DiscoveredDevice]`**
- Same pattern as `discover()` but with profile enrichment
- Already exists on `BACnetClient`, just needs `Client` wrapper with string destination support

**1b. `Client.get_alarm_summary(address)` → `GetAlarmSummaryACK`**
- Accepts string address
- Thin wrapper delegating to BACnetClient

**1c. `Client.get_event_information(address, ...)` → `GetEventInformationACK`**
- Accepts string address
- Thin wrapper delegating to BACnetClient

**1d. `Client.acknowledge_alarm(address, object_id, ...)` → `None`**
- Accepts string address and string object identifier (e.g. `"ai,1"`)

**1e. `Client.send_text_message(destination, source_device, message, ...)` → `None`**
- Accepts string destination
- Separate confirmed/unconfirmed via `confirmed=` kwarg

**1f. `Client.backup(address, ...)` → `BackupData`**
- Accepts string address

**1g. `Client.restore(address, backup_data, ...)` → `None`**
- Accepts string address

**1h. `Client.query_audit_log(address, ...)` → `AuditLogQueryACK`**
- Accepts string address

### Phase 2: Make existing Client methods accept strings

Upgrade existing low-level-only methods on `Client` to accept strings while
preserving backwards compatibility with typed objects:

**2a. `create_object(address, object_type_str)` → `ObjectIdentifier`**
- Accept `"av"` or `"analog-value"` in addition to `ObjectType` enum
- Accept string address in addition to `BACnetAddress`

**2b. `delete_object(address, object_id_str)` → `None`**
- Accept `"av,1"` in addition to `ObjectIdentifier`
- Accept string address

**2c. `device_communication_control(address, state, ...)` → `None`**
- Accept string address
- Accept string state: `"enable"`, `"disable"`, `"disable-initiation"`

**2d. `reinitialize_device(address, state, ...)` → `None`**
- Accept string address
- Accept string state: `"coldstart"`, `"warmstart"`, etc.

### Phase 3: Add missing example scripts

**3a. `examples/write_multiple.py`** -- `write_multiple()` dict API
**3b. `examples/alarm_management.py`** -- alarm summary, event info, acknowledge
**3c. `examples/backup_restore.py`** -- backup/restore workflow
**3d. `examples/text_message.py`** -- sending text messages
**3e. `examples/extended_discovery.py`** -- discover_extended with profiles

### Phase 4: Expand top-level exports

Add commonly needed server-side types to `bac_py.__init__`:
- `BACnetApplication`, `RouterConfig`, `RouterPortConfig`
- `DefaultServerHandlers`
- `DeviceObject`

### Phase 5: Update documentation

- Update docs/examples.rst with new example scripts
- Update docs/features.rst convenience API section
- Update README.md examples table
