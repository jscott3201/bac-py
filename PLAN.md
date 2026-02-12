# Phase 5 -- BACnet Procedures and Conformance Implementation Plan

## Scope Analysis

Phase 5 has 6 sub-phases. After analysis, here's the implementation plan ordered by
dependency and impact:

### Step 1. Backup and Restore Procedures (Clause 19.1)

**Server-side (state machine in `handle_reinitialize_device`):**

Modify `src/bac_py/app/server.py` `handle_reinitialize_device()` to manage backup/restore
state transitions on the Device object:

- `START_BACKUP` → set `system_status = BACKUP_IN_PROGRESS`, set `backup_and_restore_state`
- `END_BACKUP` → restore `system_status = OPERATIONAL`
- `START_RESTORE` → set `system_status = DOWNLOAD_IN_PROGRESS`
- `END_RESTORE` → restore `system_status = OPERATIONAL`, record `last_restore_time`
- `ABORT_RESTORE` → restore `system_status = OPERATIONAL`

Add `BACKUP_AND_RESTORE_STATE`, `CONFIGURATION_FILES`, `LAST_RESTORE_TIME`,
`BACKUP_PREPARATION_TIME`, `RESTORE_PREPARATION_TIME`, `RESTORE_COMPLETION_TIME`
properties to `DeviceObject`.

**Client-side (orchestration in `app/client.py`):**

- `backup_device(address) -> BackupData`: Full backup sequence (reinit START_BACKUP →
   poll status → read config files → download via AtomicReadFile → reinit END_BACKUP)
- `restore_device(address, backup_data)`: Full restore sequence (reinit START_RESTORE →
   poll status → upload via AtomicWriteFile → reinit END_RESTORE → verify)

**New type**: `BackupData` dataclass with device info + file contents.

**Files**: `src/bac_py/app/client.py`, `src/bac_py/app/server.py`,
`src/bac_py/objects/device.py`

### Step 2. Value Source Mechanism (Clause 19.5 -- New in 2020)

**New type in `src/bac_py/types/constructed.py`:**

`BACnetValueSource` -- CHOICE { none [0] NULL, object [1] BACnetDeviceObjectReference,
address [2] BACnetAddress }. Encode/decode methods.

**New PropertyIdentifier values in `src/bac_py/types/enums.py`:**

- `VALUE_SOURCE = 433`
- `VALUE_SOURCE_ARRAY = 434`
- `LAST_COMMAND_TIME = 432`
- `COMMAND_TIME_ARRAY = 435`

**Extend `commandable_properties()` in `src/bac_py/objects/base.py`:**

Add `VALUE_SOURCE`, `VALUE_SOURCE_ARRAY`, `LAST_COMMAND_TIME`, `COMMAND_TIME_ARRAY`.

**Update `_write_with_priority()` in `src/bac_py/objects/base.py`:**

On write: set `value_source_array[priority]` with source info, update
`command_time_array[priority]`. On relinquish: clear slot. Resolve winning slot's
source into `value_source` and `last_command_time`.

**Files**: `src/bac_py/types/constructed.py`, `src/bac_py/types/enums.py`,
`src/bac_py/objects/base.py`

### Step 3. PICS Generation (Clause 22 / Annex A)

**New file `src/bac_py/conformance/pics.py`:**

`PICGenerator` class that introspects a `BACnetApplication` to generate a Protocol
Implementation Conformance Statement:

- General device info (vendor, model, firmware)
- Services supported (from `PROTOCOL_SERVICES_SUPPORTED` bitstring)
- Object types supported (from `PROTOCOL_OBJECT_TYPES_SUPPORTED` bitstring)
- Data link options
- Character set support

Output: structured dict (JSON-serializable).

**Files**: `src/bac_py/conformance/__init__.py`, `src/bac_py/conformance/pics.py`

### Step 4. BIBB Conformance Matrix (Annex K)

**New file `src/bac_py/conformance/bibb.py`:**

`BIBBMatrix` class that maps registered services and objects to BACnet Interoperability
Building Blocks. Auto-detects which BIBBs are supported:

- DS-RP-A/B (ReadProperty), DS-WP-A/B (WriteProperty)
- DS-RPM-A/B (ReadPropertyMultiple), DS-WPM-A/B (WritePropertyMultiple)
- AE-N-A/B (Event Notification), AE-ACK-A/B (Alarm Acknowledgment)
- DM-DDB-A/B (Dynamic Device Binding - Who-Is/I-Am)
- etc.

**Files**: `src/bac_py/conformance/bibb.py`

### Step 5. Unconfigured Device Discovery (Clause 19.7)

Who-Am-I/You-Are services already exist (Phase 2). This step adds the procedure
orchestration:

- **Supervisor mode**: `DeviceAssignmentTable` mapping (vendor_id, serial_number) →
  device identity. Callback-based handler in server for Who-Am-I that looks up
  assignment and sends You-Are.
- **Client helper**: `discover_unconfigured(timeout)` that broadcasts Who-Am-I
  and collects responses.

**Files**: `src/bac_py/app/client.py`, `src/bac_py/app/server.py`

### Step 6. Tests

**New test files:**
- `tests/app/test_backup_restore.py` -- backup/restore state machine + client orchestration
- `tests/types/test_value_source.py` -- BACnetValueSource encode/decode
- `tests/objects/test_commandable_value_source.py` -- value source tracking on writes
- `tests/conformance/test_pics.py` -- PICS generation
- `tests/conformance/test_bibb.py` -- BIBB matrix detection

## Verification

1. `pytest tests/ --ignore=tests/serialization/test_json.py` -- all pass
2. `.venv/bin/ruff check src/ tests/` -- clean on new files
3. `.venv/bin/mypy --ignore-missing-imports src/` -- clean
4. Backup/restore state transitions correct
5. Value source metadata populated on commandable writes
6. PICS output matches registered services/objects
7. BIBB matrix accurately reflects implementation
