# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.2] - 2026-02-16

### Fixed

- **Docker entrypoint `sys.path`** — Added project root to `sys.path` so
  `docker.lib` imports work when the entrypoint is run as a script.
- **SC PKI `generate_test_pki()`** — Clear directory contents instead of
  `shutil.rmtree()` on Docker volume mount points (which cannot be removed).
- **SC certificate SANs** — Use specific `IPv4Address` entries instead of
  `IPv4Network` for Docker bridge IPs in certificate Subject Alternative Names.
  `IPv4Network` does not work for SSL hostname verification.

### Added

- **Mixed-environment SC profiling** — `bench_sc.py` supports `--mode hub` and
  `--mode client` for split Docker/local benchmarks, enabling isolated
  pyinstrument profiling of hub-side or client-side TLS overhead.
  `--generate-certs DIR` creates shared TLS certificates with broad SANs
  (localhost, host.docker.internal, Docker bridge IPs).  New Docker Compose
  profiles `sc-bench-hub` and `sc-bench-client` and Makefile targets
  `bench-sc-profile-client` and `bench-sc-profile-hub` orchestrate the
  mixed-environment runs.
- **Docker scenario 14: Mixed BIP↔IPv6 routing** — A BACnet/IP client on
  network 1 communicates with a BACnet/IPv6 server on network 2 through a
  dual-stack `NetworkRouter`.  Tests read, write, RPM, WPM, and object-list
  operations through the cross-transport router (6 tests).
  `make docker-test-mixed-bip-ipv6`.
- **Docker scenario 15: Mixed BIP↔SC routing** — A BACnet/IP client sends
  NPDUs through a BIP↔SC `NetworkRouter` to SC echo nodes connected via an
  SC hub with mutual TLS 1.3 on network 2.  SC echo nodes parse incoming
  NPDUs and swap SNET/SADR→DNET/DADR headers for proper routed responses.
  TLS certificates are generated locally and bind-mounted into containers
  (4 tests).  `make docker-test-mixed-bip-sc`.
- **Entrypoint roles: `router-bip-sc`, `sc-npdu-echo`** — New Docker
  entrypoint roles for BIP↔SC gateway routing and NPDU-level SC echo with
  proper routing header manipulation.

### Changed

- **Docker images tagged with version** — All services share a version-tagged
  image (`bac-py:<version>`) for reproducible builds.
- **`docker-build` uses `docker build` directly** — Replaced `docker compose
  build` (which built nothing since all services have profiles) with a direct
  `docker build` command.  `docker-clean` now removes all `bac-py:*` images.

- **Performance: APDU dispatch optimization** — Replaced `match`/`case` on
  `PduType` enum with direct `isinstance` checks in `_on_apdu_received()`,
  eliminating a redundant `PduType` extraction from the raw byte after
  `decode_apdu()` already determines the type. BIP throughput improved ~4%,
  Router throughput improved ~36% (cumulative with loop caching).
- **Performance: Event loop caching** — Cache the running `asyncio` event loop
  in `BACnetApplication.start()` and use `loop.create_task()` instead of
  `asyncio.create_task()` in `_spawn_task()`, skipping the `get_running_loop()`
  lookup on every request dispatch.
- **Performance: SC WebSocket pending events deque** — Changed
  `SCWebSocket._pending_events` from `list` with O(n) `pop(0)` to
  `collections.deque` with O(1) `popleft()` and built-in `maxlen=64` cap.
- **Performance: SC hub payload skip** — Hub connections now decode BVLC-SC
  messages with `skip_payload=True`, avoiding a `bytes()` copy of the NPDU
  payload that the hub never inspects (it forwards raw bytes directly).

## [1.5.1] - 2026-02-15

### Added

- **SC TLS stress testing**: All BACnet/SC stress tests and benchmarks now use
  mutual TLS 1.3 with a mock CA (EC P-256) by default, matching production
  requirements (Annex AB.7.4). A shared `docker/lib/sc_pki.py` module generates
  the test PKI. Docker SC scenarios use init containers to generate certificates
  into shared volumes. The local `bench_sc.py` benchmark accepts `--no-tls` to
  fall back to plaintext for comparison.

- **`add_route()` API**: Added `add_route(network, router_address)` to `Client`,
  `BACnetApplication`, and `NetworkLayer` for pre-populating the router cache.
  Enables communication with devices on remote networks without broadcast-based
  router discovery — required in Docker bridge networks where ephemeral-port
  clients cannot receive broadcast responses on the standard BACnet port.

### Fixed

- **Router per-port broadcast address**: Added `broadcast_address` field to
  `RouterPortConfig` and pass it to `BIPTransport` in router mode. Previously,
  all router ports used the default global broadcast (`255.255.255.255`), which
  fails in Docker bridge networks where directed subnet broadcasts are required.
  Docker router services now use `BROADCAST_ADDRESS_1`/`BROADCAST_ADDRESS_2`
  environment variables for per-port configuration.
- **BIPTransport ephemeral port broadcast**: Fixed `BIPTransport.send_broadcast()`
  sending to port 0 when the transport was created with `port=0` (ephemeral).
  The bound port is now stored after socket binding so broadcasts and BBMD
  advertisements use the correct port.
- **Docker router stress test**: Fixed the pre-existing router stress test failure
  caused by three compounding issues: (1) per-port broadcast addresses not being
  passed to the router's BIPTransport, (2) ephemeral port clients unable to
  receive broadcast I-Am responses forwarded by the router, and (3) missing
  router cache pre-population. The test now uses `add_route()` and a direct
  server address (`SERVER_ADDRESS`) to bypass all broadcast-dependent discovery.

### Security

- **SC hub VMAC collision race fix**: Added `_pending_vmacs` reservation set to
  `SCHubFunction` to prevent a TOCTOU race between VMAC collision check and
  connection registration during the handshake window (Annex AB.6.2).
- **SC URI scheme validation**: `SCNodeSwitch.establish_direct()` now validates
  that hub-provided peer URIs use `ws://` or `wss://` schemes before
  connecting, preventing SSRF-like redirection to non-WebSocket endpoints.
- **SC header options count cap**: BVLC-SC header option decoding now limits
  lists to 32 options per message (defense-in-depth against malformed payloads).
- **SC pending resolution cache cap**: `SCNodeSwitch.resolve_address()` now
  rejects new resolution requests when the cache reaches `max_connections`,
  preventing unbounded memory growth from address resolution flooding.
- **BBMD max BDT entries**: Added `max_bdt_entries` parameter (default 128) to
  `BBMDManager`. Write-BDT requests exceeding the limit are NAKed, preventing
  oversized BDT payloads from consuming unbounded memory.
- **IPv6 VMAC cache size limit**: `VMACCache` now accepts a `max_entries`
  parameter (default 4096). When full, stale entries are evicted first; if still
  full, the oldest entry is dropped.
- **IPv6 pending resolution cap**: `BIP6Transport.send_unicast()` now limits
  the pending VMAC resolution cache to 1024 entries, preventing unbounded growth
  from resolution requests to many unknown VMACs.
- **H1: `decode_real`/`decode_double` buffer validation**: Added explicit length
  checks before `struct.unpack_from` in `encoding/primitives.py`, raising
  `ValueError` instead of the opaque `struct.error` on truncated input.
- **H2: ErrorPDU bounds check**: Added bounds checks after each `decode_tag()` in
  `_decode_error()` (`encoding/apdu.py`) to reject truncated error class/code
  fields before slicing.
- **H3: `extract_context_value` overflow check**: Added bounds validation in
  `encoding/tags.py` to reject primitive tags whose length extends past the
  buffer end, preventing silent reads of stale/adjacent memory.
- **H4: Ethernet 802.3 minimum length**: `_decode_frame()` in
  `transport/ethernet.py` now rejects frames with length field < LLC header
  size (3 bytes), preventing underflow in NPDU extraction.
- **C1: Service decoder list caps**: Added `_MAX_DECODED_ITEMS = 10,000` cap to
  all unbounded decode loops across 8 service files (19 loops total):
  `read_property_multiple`, `write_property_multiple`, `alarm_summary`, `cov`,
  `write_group`, `virtual_terminal`, `object_mgmt`, and `audit`.
- **C2: `ObjectType` vendor cache cap**: `ObjectType._missing_()` now clears the
  vendor cache at 4096 entries, matching the `PropertyIdentifier` pattern and
  preventing unbounded growth from vendor-proprietary object types.
- **C3: Segmentation reassembly size cap**: `SegmentReceiver` now tracks total
  reassembly bytes and returns `ABORT` when the cumulative size exceeds 1 MiB.
  Added `created_at` timestamp field for stale receiver detection.
- **C4: Audit nesting depth enforcement**: Added depth checks (max 32) to all
  manual tag-nesting loops in `services/audit.py` (4 loops), preventing stack
  exhaustion from deeply nested opening tags in audit decode paths.
- **S1: Hub pending VMAC TTL and cap**: Converted `_pending_vmacs` from `set` to
  `dict[SCVMAC, float]` with 30-second TTL purge and `max_connections` cap in
  `transport/sc/hub_function.py`, preventing unbounded growth from slow or
  abandoned handshakes.
- **S2: SC header option data size cap**: Added `_MAX_OPTION_DATA_SIZE = 512`
  limit to `SCHeaderOption.decode_list()` in `transport/sc/bvlc.py`, rejecting
  oversized option data (up to 65535 per option) early in the decode path.
- **S3: SC WebSocket oversized frame rate limit**: `SCWebSocket._process_frame()`
  now tracks consecutive oversized frames and raises `ConnectionClosedError`
  after 3 in a row, preventing log flooding from misbehaving peers.
- **S4: SC WebSocket pending events cap**: Capped `_pending_events` buffer at 64
  entries in `transport/sc/websocket.py`, silently dropping excess frames when a
  single TCP segment delivers many WebSocket frames.
- **S5: SC address resolution URI cap**: `AddressResolutionAckPayload.decode()`
  now truncates the URI list to 16 entries, preventing unbounded allocations
  from malformed address resolution responses.
- **B1: FDT TTL upper bound**: Foreign device registration TTL is now capped at
  3600 seconds (1 hour) in `transport/bbmd.py`, preventing unreasonably long
  registration durations.
- **A1: Change callback cap**: `ObjectDatabase.register_change_callback()` now
  raises `ValueError` when a single property exceeds 100 registered callbacks,
  preventing unbounded list growth.
- **COV nesting depth enforcement**: Added depth check (max 32) to the manual
  tag-nesting loop in `COVPropertyValue.decode()` (`services/cov.py`),
  preventing stack exhaustion from deeply nested opening tags in COV value
  decode paths.
- **`decode_boolean` buffer validation**: Added explicit length check before
  accessing `data[0]` in `decode_boolean()` (`encoding/primitives.py`),
  raising `ValueError` on empty input for consistency with `decode_real` and
  `decode_double`.

## [1.5.0] - 2026-02-15

### Added

- **CONTRIBUTING.md**: Contributing guidelines covering development setup, code
  standards, quality gates, and pull request process.
- **SECURITY.md**: Security policy with vulnerability reporting instructions,
  supported versions, and security considerations for BACnet deployments.
- **CODE_OF_CONDUCT.md**: Contributor Covenant 3.0 Code of Conduct.
- **GitHub issue templates**: Structured bug report and feature request forms
  (`.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`).
- **GitHub PR template**: Pull request template with quality gate checklist
  (`.github/PULL_REQUEST_TEMPLATE.md`).
- **README badges**: Added PyPI version, Python version, license, and CI status
  badges. Added Contributing section linking to CONTRIBUTING.md and SECURITY.md.
- **Changelog project URL**: Added `Changelog` link to `[project.urls]` in
  `pyproject.toml` for display on PyPI.

### Changed

- **Release workflow**: Restructured `.github/workflows/release.yml` into three
  separate jobs (release, build, publish) per the official Python packaging guide.
  The publish job uses a dedicated `pypi` GitHub Environment with `id-token: write`
  and `attestations: write` permissions for trusted publishing with PEP 740
  attestations. Build artifacts pass between jobs via `actions/upload-artifact`.
- **sdist exclusions**: Configured `[tool.hatch.build.targets.sdist]` to exclude
  `docker/`, `scripts/`, `docs/`, `.github/`, `Makefile`, `ruff.toml`, `uv.lock`,
  and `.python-version` from source distributions. Reduces sdist from 397 to 314
  files. Wheel contents unchanged (only `bac_py/` package).

### Fixed

- **README test count**: Reconciled inconsistent test counts ("6,380+" vs
  "6,300+") in the Testing section.

## [1.4.9] - 2026-02-14

### Added

- **Interactive CLI example**: New `examples/interactive_cli.py` providing a menu-driven
  interactive CLI for testing Client API features against a real BACnet device. Supports
  read/write (single and multiple), device discovery (Who-Is, Who-Has, object list), COV
  subscriptions with live notifications, and time synchronization. Uses non-blocking input
  to keep the event loop responsive for COV callbacks between actions.

## [1.4.8] - 2026-02-14

### Added

- **Expanded object type aliases**: Added 48 short aliases (up from 10) for common
  object types in `parse_object_identifier()`. New aliases include `file`, `nc`,
  `sched`, `tl`, `el`, `ch`, `lp`, `lo`, `sv`, `np`, `ee`, `tmr`, `iv`, `csv`,
  `acc`, `lc`, `avg`, `al`, `ar`, and more. Full hyphenated names (e.g.
  `"analog-input"`) continue to work without needing aliases.
- **Expanded property identifier aliases**: Added 45 short aliases (up from 8) for
  common property identifiers in `parse_property_identifier()`. New aliases include
  `type`, `list`, `priority`, `relinquish`, `min`, `max`, `polarity`,
  `event-state`, `high-limit`, `low-limit`, `deadband`, `notify-class`,
  `vendor-name`, `model-name`, `max-apdu`, `log-buffer`, `enable`, and more.

### Changed

- **`traverse_hierarchy()` string support**: Now accepts string addresses and
  object identifiers (e.g. `"sv,1"`) in addition to typed objects.
- **`who_has()` string support**: `object_identifier` parameter now accepts
  string formats (e.g. `"ai,1"`) in addition to `ObjectIdentifier`.
- **`read_multiple()` timeout parameter**: Added missing `timeout` parameter for
  consistency with `write_multiple()` and other convenience methods.

### Docs

- **Alias reference tables**: Updated the string aliases tables in
  ``getting-started.rst``, ``features.rst``, and ``README.md`` to reflect the
  expanded alias sets. Fixed incorrect ``sf`` alias reference in README
  (correct alias is ``status``).

## [1.4.7] - 2026-02-14

### Changed

- **Router local-delivery fast path**: Added `encode_npdu_local_delivery()` that
  combines NPDU construction and encoding into a single operation, eliminating
  intermediate `NPDU` and `BACnetAddress` object creation on every routed packet
  in `_deliver_to_directly_connected()`.
- **Router forwarding fast path**: Added `encode_npdu_with_source()` combined
  encode for source-injected NPDUs with destination preserved.
- **Debug log guards (BIP transport)**: Added `if __debug__ and
  logger.isEnabledFor()` guards to `send_unicast()` and `_on_datagram_received()`
  hot paths, preventing string formatting and enum `.name` attribute access on
  every UDP datagram when DEBUG logging is disabled.
- **Debug log guards (network layer)**: Guarded `logger.debug` in
  `_on_npdu_received()` (every APDU dispatch) and `_send_remote()` (every remote
  send, avoids `.hex()` call).
- **Debug log guards (router)**: Guarded `logger.debug` in `_forward_to_network()`
  hot path (every directly-connected and next-hop forwarding decision).

### Docs

- **Docstring cleanup**: Added `:param:` documentation to all server handler methods
  (`handle_read_property`, `handle_write_property`, `handle_subscribe_cov`, etc.),
  `AuditManager.record_operation()`, COV manager methods, and `BACnetApplication`
  request methods.
- **Removed spec page/table references**: Replaced all page number references
  (e.g. `pp. 821-822`), table references (e.g. `Table 19-4`, `Table 6-1`,
  `Table 20.2.9.1`), and figure references (e.g. `Figure 6-11`, `Figure 6-12`)
  with Clause references throughout the codebase. Clause references are retained.

## [1.4.6] - 2026-02-14

### Changed

- **SC BVLC decode performance**: Replaced `SCControlFlag` IntFlag bitwise operations
  with raw integer constants and `BvlcSCFunction` enum construction with pre-built
  tuple lookup in the decode hot path, eliminating ~9% CPU overhead per message.
- **SCVMAC fast construction**: Added `SCVMAC._from_trusted()` classmethod that
  bypasses length validation on internal decode paths where the caller guarantees
  6 bytes.
- **NPDU decode performance**: Added `_make_npdu()` fast constructor bypassing frozen
  dataclass `__init__` overhead, and `NetworkPriority` tuple lookup replacing enum
  construction.
- **BVLL decode performance**: Replaced `BvlcFunction` enum construction with
  pre-built tuple lookup indexed by byte value.
- **APDU decode performance**: Replaced `PduType` enum construction with pre-built
  tuple lookup, added `_make_confirmed_request()` fast constructor for
  `ConfirmedRequestPDU`, and replaced `dict.get()` in max-segments/max-APDU decoding
  with direct tuple indexing.
- **TSM event loop caching**: Cached `asyncio.get_running_loop()` result in both
  `ClientTSM` and `ServerTSM` to avoid repeated lookups on every timeout start.
- **Debug log guards**: Added `if __debug__ and logger.isEnabledFor()` guards around
  debug logging in SC BVLC encode/decode, APDU encode/decode, SC transport send/receive,
  and SC hub function routing hot paths to avoid string formatting and attribute access
  when DEBUG is disabled.
- **NPDU encode performance**: `encode_npdu()` now pre-calculates total buffer size and
  fills a single pre-sized `bytearray` with slice assignment and `struct.pack_into`,
  replacing repeated `append()`/`extend()` calls.
- **SCMessage fast construction**: Added `_make_sc_message()` fast constructor bypassing
  frozen-dataclass `__init__` overhead, used in `SCMessage.decode()`.
- **BvllMessage fast construction**: Added `_make_bvll_message()` fast constructor
  bypassing frozen-dataclass `__init__` overhead, used in `decode_bvll()`.
- **Router hot-path NPDU construction**: `_deliver_to_directly_connected()` and
  `_prepare_forwarded_npdu()` now use `_make_npdu()` fast constructor instead of
  `NPDU(...)`, avoiding frozen-dataclass overhead on every routed packet.

## [1.4.5] - 2026-02-14

### Added

- **Benchmark profiling**: All local benchmark scripts (`bench_bip`, `bench_router`,
  `bench_bbmd`, `bench_sc`) accept `--profile` and `--profile-html` flags for
  pyinstrument profiling of async hot paths.  `pyinstrument` added as a dev
  dependency.  Makefile targets: `make bench-{bip,router,bbmd,sc}-profile`.

### Changed

- **Docs dependency group**: Added `websockets`, `cryptography`, and `orjson` to
  the `docs` dependency group so Sphinx autodoc builds with real imports instead
  of mock stubs, fixing SC transport API documentation warnings.
- **Transport setup guide**: Removed redundant `.. contents::` TOC directive
  (Furo theme provides sidebar navigation).

## [1.4.4] - 2026-02-14

### Changed

- **TLS X.509 strict verification**: SSL contexts for BACnet/SC now enable
  `VERIFY_X509_STRICT` flag for stricter certificate validation per RFC 5280.
- **System CA store blocked**: BACnet/SC SSL contexts no longer fall back to the
  system certificate store.  Only explicitly configured CA certificates are
  trusted, preventing accidental trust of arbitrary CAs on the host.
- **Deprecated asyncio APIs replaced**: All `asyncio.ensure_future()` calls
  replaced with `asyncio.create_task()` and all `asyncio.get_event_loop()`
  calls replaced with `asyncio.get_running_loop()` across the entire codebase
  (source, tests, examples, docker).
- **Fire-and-forget task error logging**: Background tasks in
  `BACnetApplication._spawn_task()` and SC transport task schedulers now log
  exceptions via done callbacks instead of silently dropping them.
- **WebSocket client handshake timeout**: `SCWebSocket.connect()` now accepts a
  `handshake_timeout` parameter (default 10s), matching the server-side
  `accept()` pattern.  Prevents indefinite hangs on unresponsive peers.

### Added

- **Private key passphrase support**: `SCTLSConfig.key_password` parameter
  allows passphrase-protected PEM private keys (accepts `bytes` or `str`).
  Passphrase values are redacted in `repr()` alongside `private_key_path`.
- **Transport setup guide**: New comprehensive documentation page covering all
  five transport types (BACnet/IP, IPv6, BBMD, Router, Ethernet, SC) with
  setup examples for common deployment topologies.
- **Documentation restructure**: Moved changelog to its own sidebar section,
  added introductory text to all API reference pages, documented the IPv6
  example script, and fixed the example count.

## [1.4.3] - 2026-02-14

### Changed

- **WebSocket write buffer tuning**: SC WebSocket connections now set write
  buffer high/low water marks (32 KiB / 8 KiB) to trigger backpressure earlier
  for slow peers, and enable TCP_NODELAY for low-latency frame delivery.
- **WebSocket max_size enforcement**: `SCWebSocket.connect()` and `.accept()`
  now accept a `max_size` parameter forwarded to the websockets protocol layer
  for early oversized-frame rejection. All callers (hub connector, hub function,
  node switch) pass `max_bvlc_length` as the limit.
- **Hub broadcast batched writes**: `SCHubFunction._broadcast()` now buffers
  WebSocket frames to all connections synchronously, then drains them
  concurrently via `asyncio.gather()`, reducing broadcast latency.
- **WebSocket recv() event buffering**: Fixed a bug where multiple WebSocket
  frames arriving in a single TCP segment could cause lost frames. `recv()` now
  buffers unconsumed events from `events_received()` for subsequent calls.

### Added

- **Local SC benchmark**: `scripts/bench_sc.py` runs a complete hub, echo
  nodes, and stress workers in a single process for Docker-free benchmarking.
  Supports human-readable and `--json` output modes.  Makefile targets:
  `make bench-sc` and `make bench-sc-json`.
- **Local BIP benchmark**: `scripts/bench_bip.py` runs an in-process BACnet/IP
  server with 40 objects and configurable stress client pools on localhost.
  Mixed workloads: read, write, RPM, WPM, object-list, COV.  Makefile targets:
  `make bench-bip` and `make bench-bip-json`.
- **Local router benchmark**: `scripts/bench_router.py` creates a two-network
  router on localhost with a stress server on network 2 and client pools on
  network 1.  Measures cross-network routing overhead.  Makefile targets:
  `make bench-router` and `make bench-router-json`.
- **Local BBMD benchmark**: `scripts/bench_bbmd.py` runs a server with BBMD
  attached and foreign-device client pools.  Includes FDT/BDT read workers.
  Makefile targets: `make bench-bbmd` and `make bench-bbmd-json`.

### Documentation

- **Benchmarks guide overhaul** (`docs/guide/benchmarks.rst`): Restructured into
  Local Benchmarks and Docker Benchmarks sections with reference results for all
  four transport types.  Added results comparison table, key observations
  (local vs Docker performance characteristics), local CLI tuning parameters,
  and testing conditions.

## [1.4.2] - 2026-02-14

### Fixed

- **Receive callback crash protection**: Wrapped 13 `_receive_callback` and
  application callback call sites in `try/except` across `bip.py`, `bip6.py`,
  `sc/__init__.py`, `router.py`, and `layer.py`. An exception from the callback
  no longer crashes the transport's datagram handler or router receive loop.
  The ethernet transport already had this pattern; now all transports are
  consistent.
- **Assert → TypeError in encode paths**: Replaced 8 `assert isinstance()`
  calls in `BACnetTimeStamp.encode()`, `BACnetCalendarEntry.encode()`, and
  `BACnetValueSource.encode()` with explicit `TypeError` raises. These
  validations now work correctly under `python -O` (optimized builds).
- **Router cache cap**: `NetworkLayer._router_cache` is now capped at 1024
  entries. When full, stale entries are evicted first, then the oldest entry.
  Prevents unbounded memory growth from I-Am-Router-To-Network floods.
- **Network list decode cap**: `_decode_network_list()` now rejects messages
  containing more than 512 network numbers, preventing allocation of
  oversized tuples from malformed packets.
- **COV subscription cap**: `COVManager` now accepts `max_subscriptions` and
  `max_property_subscriptions` parameters (default 1000). New subscriptions
  beyond the limit are rejected with `BACnetError(RESOURCES)`.
- **Time series import cap**: `TimeSeriesImporter.from_json()` and
  `from_csv()` now reject imports exceeding 100,000 records with a
  `ValueError`, preventing memory exhaustion from oversized files.

## [1.4.1] - 2026-02-14

### Changed

- **Encoding hot-path optimization**: `encode_unsigned()` and `encode_unsigned64()`
  now use a pre-computed 256-element lookup table for values 0-255, eliminating
  `to_bytes()` allocation on the most common code path. `encode_boolean()` uses
  pre-allocated `b"\x01"` / `b"\x00"` constants.
- **Address encode caching**: `BIPAddress.encode()` and `BIP6Address.encode()`
  now cache their result on the frozen dataclass instance, avoiding repeated
  `inet_aton()`/`inet_pton()` + `struct.pack()` calls. `BIPAddress.decode()`
  uses an LRU-cached factory to deduplicate instances for the same remote device.
- **Transport receive-path optimization**: BIP and BIP6 transports now perform
  a fast self-echo check using raw tuple/VMAC comparison before allocating
  address objects, reducing per-packet overhead on broadcast-heavy networks.
- **BBMD forwarding optimization**: BDT unicast-mask lookup is now O(1) via a
  pre-computed dict. Peer list excludes self, eliminating per-forward self-skip
  checks. Foreign device registration messages are pre-computed once in
  `__init__` for both IPv4 and IPv6 managers.
- **ObjectType vendor member caching**: `ObjectType._missing_()` now caches
  vendor-proprietary pseudo-members (128-1023), matching the existing
  `PropertyIdentifier` pattern. Repeated lookups return the same object.
- **StatusFlags singleton**: A shared `_NORMAL_STATUS_FLAGS` instance is returned
  for the common all-normal case, avoiding per-read allocation.
- **`standard_properties()` caching**: The 5-entry base property dict is now
  computed once and reused across all 40+ object class definitions.

### Fixed

- **PropertyIdentifier vendor cache unbounded growth**: The
  `_PROPERTY_ID_VENDOR_CACHE` dict is now capped at 4096 entries. A misbehaving
  device sending millions of unique vendor property IDs can no longer cause
  unbounded memory growth.

## [1.4.0] - 2026-02-14

### Added

- **Full BACnet/IPv6 (Annex U) integration** — IPv6 transport is now fully
  wired into `Client` and `BACnetApplication`. Set `ipv6=True` to use IPv6
  multicast discovery and communication:
  - `Client(ipv6=True)` creates a `BIP6Transport` with `ff02::bac0` multicast
  - `DeviceConfig(ipv6=True)` and `RouterPortConfig(ipv6=True)` for app-level config
  - Mixed IPv4/IPv6 router ports in a single router configuration
  - IPv6 foreign device registration via `bbmd_address="[fd00::1]:47808"`
- **IPv6 BBMD manager** (`transport/bbmd6.py`): BDT/FDT management, broadcast
  forwarding to peers and foreign devices, FDT expiry cleanup.  Mirrors the
  IPv4 BBMD architecture adapted for Annex U (no broadcast mask, multicast
  callbacks, source VMAC on all messages).
- **IPv6 foreign device manager** (`transport/foreign_device6.py`): Registration,
  re-registration loop at TTL/2, deregistration on stop, distribute-broadcast.
- **BVLL6 spec compliance fix**: All 13 BVLL6 function codes now include
  `source_vmac` per Annex U (previously 4 codes were missing it).
- **NetworkLayer generalized** to accept any `TransportPort` (not just
  `BIPTransport`), enabling IPv6 and future transport types.
- **IPv6 example script** (`examples/ipv6_client_server.py`): Demonstrates
  IPv6 client with multicast discovery and property reads.
- **IPv6 Docker integration test** (Scenario 13, profile `ipv6`):
  `server-ipv6` and `test-ipv6` containers on a `fd00:bac:1::/64` network.
  New `make docker-test-ipv6` target.

## [1.3.11] - 2026-02-14

### Added

- **Router stress test scenario** (`docker/scenarios/test_router_stress.py`):
  Sustained cross-network routing throughput test.  Discovers a server on a
  remote BACnet network through a router and runs mixed-workload stress workers
  (read, write, RPM, WPM, object-list) with all traffic traversing the router.
  Includes periodic route health-check workers.  New
  `make docker-test-router-stress` and `make docker-router-stress` targets.
- **BBMD stress test scenario** (`docker/scenarios/test_bbmd_stress.py`):
  Sustained foreign-device management throughput test.  Registers test clients
  as foreign devices with a BBMD and runs mixed BACnet service workloads
  alongside BBMD-specific operations (FDT reads, BDT reads).  Measures BBMD
  overhead under concurrent foreign device activity.  New
  `make docker-test-bbmd-stress` and `make docker-bbmd-stress` targets.
- **Shared stress modules** (`docker/lib/router_stress.py`,
  `docker/lib/bbmd_stress.py`): Reusable worker libraries extending
  `bip_stress.Stats` with routing-specific (`RouterStats`) and BBMD-specific
  (`BBMDStats`) metrics.  Both modules reuse the core BIP stress workers for
  read/write/RPM/WPM operations.
- **Standalone stress runners** (`docker/lib/router_stress_runner.py`,
  `docker/lib/bbmd_stress_runner.py`): JSON-reporting standalone runners for
  router and BBMD stress tests, following the same warmup/sustain/report pattern
  as the existing BIP and SC stress runners.

### Changed

- **BACnet/SC WebSocket performance optimizations** (`transport/sc/`): Multiple
  improvements to the SC transport hot path, collectively improving sustained
  throughput by ~25% and reducing p99 latency from 0.6ms to 0.4ms:
  - **TCP_NODELAY on all SC connections** (`websocket.py`): Disables Nagle's
    algorithm on both client and server WebSocket connections.  Prevents 40-200ms
    stalls when sending small BACnet frames (100-1500 bytes) due to Nagle +
    delayed-ACK interaction.
  - **Raw bytes forwarding in hub** (`hub_function.py`, `connection.py`): The hub
    now forwards pre-encoded message bytes directly to destination connections,
    skipping the decode-then-re-encode cycle for routed messages.  The
    `on_message` callback chain passes raw wire bytes alongside the parsed
    `SCMessage` (optional `raw: bytes | None` parameter, backward-compatible).
  - **BVLC header caching** (`__init__.py`): `SCTransport.send_unicast()` and
    `send_broadcast()` use pre-computed BVLC-SC headers (per-destination for
    unicast, fixed for broadcast) concatenated with the NPDU payload, bypassing
    `SCMessage` object creation and `encode()` on every send.
  - **Direct chunk writes** (`websocket.py`): New `_write_pending()` helper writes
    protocol output chunks directly to the `StreamWriter` instead of collecting
    them with `b"".join()`, eliminating an allocation and copy per send.
  - **Concurrent hub broadcasts** (`hub_function.py`): Broadcast messages are
    forwarded to all connected nodes concurrently via `asyncio.gather()` instead
    of sequentially.
  - **Pre-sized encode buffer** (`bvlc.py`): `SCMessage.encode()` pre-calculates
    the total message size and allocates a single `bytearray`, eliminating
    incremental growth and reallocation.  Added `encode_encapsulated_npdu()`
    fast-path function for the common case.

- **Cross-transport encoding optimizations**: Applied the pre-sized bytearray
  pattern from BACnet/SC to all transport and encoding layers, reducing
  per-message memory allocations across the entire stack:
  - **BVLL encode** (`bvll.py`): `encode_bvll()` now uses a single pre-sized
    `bytearray` with `struct.pack_into()` instead of `bytes([...]) + content`
    concatenation.  Eliminates 2 intermediate allocations per send for BACnet/IP,
    BBMD forwarding, and foreign device registration.
  - **BVLL6 encode** (`bvll_ipv6.py`): `encode_bvll6()` rewritten to calculate
    total message size upfront and fill a single `bytearray`, replacing the
    `list.append()` + `b"".join()` + `header + content` pattern that created
    3+ intermediate allocations per send.
  - **BIP send_unicast** (`bip.py`): Inline MAC-to-host:port parsing avoids
    creating a `BIPAddress` object on every unicast send.
  - **Ethernet frame encoding** (`ethernet.py`): `_encode_frame()` uses a
    single pre-sized `bytearray` (zero-initialized for implicit padding) instead
    of concatenation + conditional padding allocation.  LLC header validation
    simplified to a single 3-byte slice comparison.  MAC address logging uses
    `.hex(':')` instead of generator + join.
  - **NPDU logging guards** (`npdu.py`): Debug log statements that call `.hex()`
    on MAC addresses are now guarded by `logger.isEnabledFor(DEBUG)`, avoiding
    string formatting overhead on every encode/decode when debug logging is
    disabled.
  - **Tag encoding lookup table** (`tags.py`): Pre-computed 150-entry lookup
    table for the most common single-byte tag encodings (tag 0-14, length 0-4,
    both APPLICATION and CONTEXT classes).  Eliminates `bytes([...])` list
    allocation on ~95% of `encode_tag()` calls.

- **Benchmarks guide** (`docs/guide/benchmarks.rst`): Added documentation for
  router stress and BBMD stress test configurations, architecture, and worker
  descriptions.

- **Docker infrastructure** (`docker-compose.yml`, `entrypoint.py`, `Makefile`):
  Added Scenario 11 (Router Stress) and Scenario 12 (BBMD Stress) with dedicated
  server, router/BBMD, test, and runner containers.  Added `router-stress` and
  `bbmd-stress` role dispatches in the entrypoint.  Added 4 new Makefile targets.

## [1.3.10] - 2026-02-14

### Fixed

- **Missing `docker/lib/` in repository** (`.gitignore`): The `lib/` gitignore
  pattern was excluding `docker/lib/`, which contains shared stress test worker
  modules (`bip_stress.py`, `sc_stress.py`, `stress_runner.py`,
  `sc_stress_runner.py`). Added `!docker/lib/` negation so the directory is
  tracked. This caused mypy CI failures since `docker.lib.*` imports could not
  resolve.

## [1.3.9] - 2026-02-14

### Added

- **SC stress test scenario** -- New Docker-based sustained WebSocket throughput
  test (`docker/scenarios/test_sc_stress.py`) with unicast and broadcast workers
  through an SC hub, measuring latency with echo correlation. New `make
  docker-test-sc-stress` and `make docker-sc-stress` targets.
- **Benchmarks guide** -- New `docs/guide/benchmarks.rst` documenting both BIP
  and SC stress test configurations, server object inventories, workload profiles,
  latency targets, and tuning guidance.

### Changed

- **DeviceConfig version defaults** (`application.py`): `firmware_revision` and
  `application_software_version` now default to `bac_py.__version__` instead of
  a hardcoded `"0.1.0"`. Docker entrypoint and thermostat demo updated to use
  `bac_py.__version__` instead of hardcoded version strings.
- **Docker build caching** (`Makefile`): `docker-build` target now uses
  `--no-cache` to ensure clean builds.
- **BIP stress test refactored** (`docker/scenarios/test_stress.py`,
  `docker/entrypoint.py`): Dedicated `stress-server` role with 40 diverse
  objects (analog, binary, multi-state, schedule, calendar, notification class).
  Configurable worker pools (readers, writers, RPM, WPM, object-list, COV) with
  environment variables. Warmup/sustain phase architecture replaces ramp schedule.
  Shared worker logic extracted to `docker/lib/` modules; `docker/__init__.py`
  added to enable package imports from test scenarios.
- **Docker Compose reorganized** (`docker/docker-compose.yml`): Added Scenario 10
  (SC Stress) with hub, two echo nodes, test container, and stress runner.
  Stress runner container moved next to its server. Header comment with scenario
  index and usage guide.

### Documentation

- **Server mode guide expansion** (`docs/guide/server-mode.rst`): Expanded from
  188 to 954 lines. Added sections for DeviceConfig options (password,
  broadcast_address, APDU settings), Object Database management (add/remove/query,
  change callbacks), supported object types (categorized list of 40+ types),
  commandable objects and priority arrays, COV subscriptions (server side),
  custom service handlers (signatures, registration, validation example, error
  responses), event engine (18 algorithms, intrinsic/algorithmic reporting),
  audit logging (server side), error handling (error table, password validation,
  DCC states), application lifecycle (context manager, manual, combined
  client+server), and registered services reference.
- **Client guide** (`docs/guide/client-guide.rst`): New consolidated client
  reference page covering API level comparison, capabilities-at-a-glance table
  with cross-references, and previously undocumented features: file access
  (AtomicReadFile/AtomicWriteFile with stream and record examples), private
  transfer (confirmed/unconfirmed vendor-specific), WriteGroup (channel group
  writes), virtual terminal sessions (VT-Open/Data/Close), list element
  operations (AddListElement/RemoveListElement), hierarchy traversal
  (StructuredView walking), and protocol-level API examples.
- Added `guide/client-guide` and `guide/benchmarks` to User Guide toctree in
  `docs/index.rst`.
- Updated `docs/getting-started.rst` with cross-references to client guide and
  protocol-level API section.
- Updated `docs/features.rst` with cross-references to client guide, commandable
  objects, supported object types, and new service documentation. Added SC Stress
  scenario, updated Docker scenario count from nine to ten, added benchmark
  cross-references.

## [1.3.8] - 2026-02-14

### Fixed

- **BIP future race condition (`bip.py`)**: Explicitly cancel pending BVLC request
  futures on timeout in `_bvlc_request()` to prevent late responses from setting
  results on garbage-collected futures. Also cancel all pending futures during
  `stop()` to prevent dangling references.
- **BIP6 memory leak (`bip6.py`)**: Capped pending address resolution queues at 16
  entries per VMAC to prevent unbounded growth when resolution never completes.
  Added 30-second TTL eviction to discard stale queued NPDUs in `_flush_pending()`.
- **BIP6 dangling futures (`bip6.py`)**: Cancel all pending BVLC futures and clear
  pending resolution queues during `stop()`.
- **Ethernet exception handler (`ethernet.py`)**: Broadened `_on_readable()` exception
  catch from `OSError` to `Exception` to prevent unexpected parsing errors or
  callback exceptions from crashing the event loop reader.
- **Router assertion safety (`router.py`)**: Replaced three `assert` statements in
  `_deliver_to_directly_connected()`, `_forward_via_next_hop()`, and
  `_send_reject_toward_source()` with explicit guard checks that degrade gracefully
  when Python runs with `-O` optimization flag.
- **NPDU decode bounds checking (`npdu.py`)**: Added explicit bounds checks before
  reading DNET/DLEN, SNET/SLEN, hop count, and message type fields in
  `decode_npdu()` to raise `ValueError` instead of `IndexError` on truncated data.
- **Tag decode bounds checking (`tags.py`)**: Added bounds validation before reading
  extended tag numbers, 1/2/4-byte extended length fields. Truncated packets now
  raise `ValueError` with descriptive messages instead of `IndexError`.
- **Tag length allocation cap (`tags.py`)**: Reject tag lengths exceeding 1 MB
  (1,048,576 bytes) to prevent memory exhaustion from malformed or malicious packets.
- **Context nesting depth limit (`tags.py`)**: Cap context tag nesting at 32 levels
  in `extract_context_value()` to prevent stack exhaustion from crafted payloads.
- **Application value content bounds check (`primitives.py`)**: Added bounds
  validation in `decode_application_value()` after decoding tag metadata but before
  reading content bytes.
- **Decoded value count cap (`primitives.py`)**: `decode_all_application_values()`
  now limits to 10,000 values to prevent memory exhaustion from crafted payloads.
- **Constant-time password comparison (`server.py`)**: `_validate_password()` now
  uses `hmac.compare_digest()` instead of `==` to prevent timing-based password
  extraction attacks.
- **SC VMAC origin validation (`hub_function.py`)**: Hub function now validates that
  the originating VMAC in received messages matches the authenticated peer's VMAC
  to prevent VMAC spoofing in hub-routed traffic (Annex AB.6.2).
- **SC TLS credential redaction (`tls.py`)**: `SCTLSConfig.__repr__()` now redacts
  `private_key_path` as `'<REDACTED>'` to prevent credential leaks in logs and
  tracebacks.
- **SC TLS configuration validation (`tls.py`)**: Added warnings for mismatched
  `certificate_path`/`private_key_path` configuration and missing CA certificates.
- **SC WebSocket frame size limit (`websocket.py`)**: Added `max_frame_size`
  parameter propagated from connection setup; oversized frames are logged at
  WARNING and dropped to prevent memory exhaustion.
- **SC plaintext warnings**: Upgraded plaintext-mode log messages from DEBUG to
  WARNING across `tls.py`, `__init__.py`, `hub_connector.py`, `hub_function.py`,
  `node_switch.py`, and `websocket.py` with references to ASHRAE 135-2020
  Annex AB.7.4.

### Changed

- **Lazy logging across entire codebase**: Converted all f-string
  `logger.debug()`/`logger.warning()`/`logger.info()` calls to lazy `%s`/`%d`
  formatting across the full stack: `app/` (client, server, application, tsm,
  event_engine, cov, audit, schedule_engine, trendlog_engine), `encoding/`
  (apdu), `objects/` (base, device), `segmentation/` (manager), `serialization/`,
  `types/` (enums), `transport/` (bip, bip6, bbmd, ethernet, npdu, layer, router,
  address), and `transport/sc/` (all modules). This avoids string interpolation
  overhead when the log level is disabled.
- **Device info cache eviction (`application.py`)**: Capped `_device_info_cache`
  at 1,000 entries with FIFO eviction (removes oldest 100 when limit reached) to
  prevent unbounded growth from I-Am responses.
- **Application stop cleanup (`application.py`)**: Clear unconfirmed listeners and
  device info cache during `stop()` to release references.
- **Event engine stop cleanup (`event_engine.py`)**: Cancel pending confirmed
  notification tasks during `stop()` to release memory.
- **Server TSM buffer release (`tsm.py`)**: Clear `cached_response` on server
  transaction abort and timeout to release large byte buffers promptly.
- **SC transport stop cleanup (`__init__.py`)**: Cancel and clean up pending send
  tasks during `stop()` to prevent dangling references.
- **SC connection callback cleanup (`connection.py`)**: Clear `on_connected`,
  `on_disconnected`, `on_message`, and `on_vmac_collision` callbacks in `_go_idle()`
  to break reference cycles between connection, hub function, and node switch objects.
- **SC hub connector resource cleanup (`hub_connector.py`)**: Call `_go_idle()` on
  failed connections (VMAC collision or non-connected state) to clean up resources.
- **BBMD byte operations (`bbmd.py`)**: Replaced `bytearray` + `extend()` loops in
  `_handle_read_bdt()` and `_handle_read_fdt()` with `b"".join()` for fewer
  intermediate allocations.
- **Router cache optimization (`layer.py`)**: In `_learn_router_from_source()`,
  update `last_seen` timestamp in-place on fresh cache entries instead of creating
  a new `RouterCacheEntry` object.
- **Foreign device exception narrowing (`foreign_device.py`)**: Narrowed
  `_registration_loop()` exception catch from bare `Exception` to `OSError`.
- **Ethernet stop() cleanup (`ethernet.py`)**: Narrowed `contextlib.suppress(Exception)`
  to `contextlib.suppress(OSError, ValueError)` in `stop()`.
- Docker firmware/application version strings updated from `"1.2.0"` to `"1.3.8"`.

### Added

- **Security and memory safety documentation** -- New `docs/guide/security.rst`
  covering protocol safety (ASN.1/BER bounds checking, allocation caps, nesting
  depth limits), transport security (TLS 1.3, VMAC validation, frame size limits,
  credential redaction), logging safety (lazy formatting), memory safety (frozen
  dataclasses, bounded buffers, constant-time comparisons), dependency posture,
  and a production checklist.
- ~1,000 new test lines covering security hardening: tag decode bounds, allocation
  caps, nesting depth, application value truncation, decoded value count limit,
  constant-time password comparison, SC VMAC origin validation, SC frame size
  limits, SC TLS credential redaction, SC plaintext warnings, NPDU truncation,
  Ethernet exception handling, and device info cache eviction.

### Documentation

- Added `guide/security` to the User Guide toctree in `docs/index.rst`.
- Trimmed `docs/guide/device-management.rst` -- removed JSON Serialization, Docker
  Integration Testing, and Protocol-Level API sections that were duplicated in
  `features.rst` and `getting-started.rst`.
- Updated `docs/features.rst` Docker section: added SC scenario, updated count
  from eight to nine, added `docker-test-sc` target reference.
- Fixed cross-references after removing `protocol-level-api` label.

## [1.3.7] - 2026-02-14

### Fixed

- **SC connection state machine (`connection.py`)**: Added re-entry guards to
  `initiate()` and `accept()` to prevent use from non-IDLE states. Fixed
  `_go_idle()` double-cancellation race when called from both `disconnect()` and
  background tasks. Wrapped `on_message` callback dispatch in try/except to
  prevent callback exceptions from killing the receive loop.
- **SC exception handling**: Narrowed broad `(TimeoutError, Exception)` catches
  to specific `(TimeoutError, OSError, ConnectionError)` across connection.py,
  hub_connector.py, and node_switch.py to avoid catching `SystemExit`,
  `KeyboardInterrupt`, and other non-network exceptions.
- **SC node switch shutdown ordering**: Reordered `stop()` to close direct
  connections before `server.close()` + `wait_closed()`, preventing Python 3.13
  hang where `wait_closed()` blocks until active connection handlers finish.

### Changed

- **SC BVLC-SC message encoding (`bvlc.py`)**: Replaced list-of-bytes + join
  pattern with pre-sized `bytearray` + `struct.pack_into` across all encode
  methods (`SCMessage.encode()`, `SCHeaderOption.encode()`, `_encode_options()`,
  `BvlcResultPayload.encode()`). Reduces allocations on the hot path.
- **SC payload consolidation**: Merged identical `ConnectRequestPayload` and
  `ConnectAcceptPayload` into single `_ConnectPayload` with public aliases.
- **SC TLS context caching**: Cached SSL contexts in `SCHubConnector.__init__()`
  and `SCNodeSwitch.__init__()` instead of rebuilding per connection attempt.
- **SC WebSocket accept timeout**: Added `handshake_timeout` parameter (default
  10s) to `SCWebSocket.accept()` to prevent slow-client denial of service.
- Removed dead code (`decode_list` unreachable break) and moved lazy `_WSState`
  import to module level in websocket.py.

### Added

- **Example test suite (`tests/test_examples.py`)**: 110 tests covering all 21
  example scripts -- syntax validation, module-level docstring checks,
  `__main__` guard verification, `async def main()` presence, import validation
  (core and SC examples separately), and functional tests for
  `create_object_database()` and `generate_test_pki()` helpers.
- **Expanded CI quality gates**: mypy type checking now covers `src/`, `examples/`,
  and `docker/` (previously `src/` only). Ruff lint and format checks now cover
  `examples/`. Added full type annotations to all 21 example scripts, 8 docker
  test scenarios, 2 demo scripts, the docker entrypoint, and the stress runner.

### Fixed

- **`secure_connect_hub.py` example**: Fixed `AnalogInputObject` present-value
  writes that failed because present-value is read-only per the spec unless
  out-of-service is True. Now sets `OUT_OF_SERVICE = True` before writing values.

## [1.3.6] - 2026-02-14

### Added

- **Comprehensive structured logging across the entire stack** -- Every module now
  uses `logging.getLogger(__name__)` for hierarchical logger namespaces under
  `bac_py.*`. Users can enable granular debugging by configuring any logger in the
  hierarchy (e.g., `logging.getLogger("bac_py.app.client").setLevel(logging.DEBUG)`).
  - **app/client.py**: 56 log statements across all public methods (DEBUG for
    request/response, INFO for lifecycle/discovery operations)
  - **app/application.py**: Lifecycle (INFO start/stop), APDU dispatch (DEBUG),
    device info cache updates, handler errors (ERROR with exc_info)
  - **App engines** (tsm, event, cov, audit, schedule, trendlog): Transaction
    lifecycle, event state transitions, COV subscription management, audit record
    creation, schedule/trend evaluation cycles
  - **app/server.py**: Handler dispatch (DEBUG), registration events, all error
    paths now log WARNING before raising BACnetError
  - **Network layer** (npdu, layer, router, address): NPDU encode/decode routing
    info, APDU dispatch, router cache updates, address parsing
  - **Transports** (bip, bbmd, ethernet, bip6): Send/receive (DEBUG), BBMD
    lifecycle (INFO start/stop), broadcast forwarding
  - **Encoding/types** (apdu, tags, enums, constructed): APDU encode/decode type
    identification, tag validation warnings, vendor-proprietary PropertyIdentifier
    creation, CHOICE decode failures
  - **SC transport** (all 8 files): Connection state machines, hub routing,
    failover events, TLS context creation, BVLC message codec, WebSocket
    connect/accept/close
  - **Objects** (base, device): ObjectDatabase add/remove (INFO), property
    read/write (DEBUG), not-found warnings
  - **Segmentation**: Segment send/receive progress, window management, transfer
    completion (INFO), duplicate/out-of-window warnings
  - **Serialization**: Serialize/deserialize operations (DEBUG), type errors (WARNING)
- **Debugging and logging documentation** -- New `docs/guide/debugging-logging.rst`
  guide with logger hierarchy table, log level descriptions, practical debugging
  recipes (failed reads, discovery, server handlers, segmentation, SC connections),
  file logging configuration, and performance notes. Added "Structured Logging"
  section to `docs/features.rst` and "Debugging and Logging" subsection to
  `docs/getting-started.rst`.
- **Logging in example scripts** -- Added `logging.basicConfig()` to 5 core
  examples (`read_value.py`, `write_value.py`, `discover_devices.py`,
  `monitor_cov.py`, `object_management.py`), bringing the total to 9 of 21
  examples with logging setup.

## [1.3.5] - 2026-02-14

### Changed

- **ObjectDatabase Device object caching** -- `_increment_database_revision()` now
  uses a cached reference to the Device object instead of scanning all objects on
  every add/remove/rename operation (O(1) instead of O(n)).
- **`encode_property_value()` dispatch table** -- Replaced 20-deep `isinstance`
  cascade for constructed BACnet types with an O(1) type-keyed dispatch table.
  The table is built lazily on first call to avoid circular imports. Primitive type
  dispatch retains the `isinstance` chain due to subclass ordering requirements
  (bool < int, IntEnum < int, BACnetDouble < float).
- **`decode_real()` / `decode_double()` use `struct.unpack_from()`** -- Avoids a
  memoryview slice copy on every float decode by using `unpack_from` instead of
  `unpack` with a slice. This is a hot path in APDU decoding.
- **`client.py` top-level imports** -- Moved 14 repeated local imports
  (`parse_object_identifier`, `parse_property_identifier`, `_resolve_object_type`,
  `GLOBAL_BROADCAST`, `MessagePriority`, `EnableDisable`, `ReinitializedState`)
  to module-level to eliminate per-call import lookup overhead.
- **Dispatch table encoders use `b"".join()`** -- Converted multi-part constructed
  type encoders (`BACnetDestination`, `BACnetRecipientProcess`,
  `BACnetDeviceObjectPropertyReference`, `BACnetObjectPropertyReference`,
  `BACnetLogRecord`) from O(n²) `bytes +=` concatenation to O(n) `b"".join()`.
- **`encode_tag()` fast path** -- Added a single-byte fast path for the common case
  (tag_number <= 14 and length <= 4), avoiding bytearray allocation entirely.
  This function is called 100+ times per APDU encode.
- **`encode_npdu()` removed redundant `bytearray.clear()`** -- The buffer was
  pre-allocated with an estimated size and then immediately cleared, defeating
  the pre-allocation. Now starts with an empty bytearray.
- **EventEngine deduplicated `_sync_state_machine()` calls** -- New enrollment
  contexts were synced twice on first evaluation (once in creation, once in the
  per-cycle sync). Removed the redundant initial sync.
- **Server `_read_object_property()` uses identity check** -- Replaced
  `ObjectIdentifier.__eq__` comparison with `obj is self._device` identity check
  for the Device object special-case path.
- **Server `_expand_property_references()` uses short-circuit scan** -- Replaced
  set comprehension with `any()` generator for `PROPERTY_LIST` membership check,
  avoiding full set construction on every ReadPropertyMultiple ALL request.
- **Pre-computed opening/closing tag lookup tables** -- `encode_opening_tag()` and
  `encode_closing_tag()` now return pre-computed `bytes` objects for tag numbers
  0--14, eliminating a `bytes([...])` allocation on every call. These functions
  are called for every constructed type in every APDU.
- **Constructed type `encode()` methods use `b"".join()`** -- Converted all
  remaining `bytes +=` concatenation in `constructed.py` encode methods
  (`BACnetTimeStamp`, `BACnetCalendarEntry`, `BACnetSpecialEvent`,
  `BACnetObjectPropertyReference`, `BACnetRecipient`, `BACnetDestination`,
  `BACnetLogRecord`, `BACnetRecipientProcess`, `BACnetValueSource`) and
  primitives.py helper functions (`_encode_calendar_entry`,
  `_encode_special_event`, `_encode_recipient`, `_encode_cov_subscription`)
  from O(n²) concatenation to O(n) `b"".join()`.
- **`PropertyIdentifier._missing_()` vendor cache** -- Vendor-proprietary
  property IDs (512--4194303) are now cached so repeated lookups return the
  same pseudo-member instance instead of creating a new one each time.
- **`encode_bit_string()` / `encode_character_string()` pre-sized buffers** --
  Replaced `bytes([x]) + data` two-object concatenation with pre-sized
  `bytearray` writes. `decode_character_string()` avoids an unnecessary
  `bytes()` wrapper when input is already `bytes`.
- **README broadened to cover all transports** -- Updated description, installation,
  examples table, Docker scenarios, and requirements to reflect BACnet/IP, IPv6,
  Ethernet, and Secure Connect support.
- **`pyproject.toml` cleanup** -- Broadened description, added `bacnet-sc` keyword,
  removed unused `cli` optional dependency, removed stale duplicate `[tool.ruff]`
  section (authoritative config is in `ruff.toml`).

## [1.3.4] - 2026-02-14

### Added

- **Self-signed certificate generation example** (`examples/sc_generate_certs.py`) --
  Generates a test PKI (EC P-256 CA + hub and two node device certificates) and
  demonstrates TLS-secured BACnet/SC communication with mutual authentication by
  routing an NPDU between two nodes through a hub.  Provides the missing guidance
  for users who need to test SC transport with real TLS instead of
  `allow_plaintext=True`.
- **Certificate generation guide** -- New "Generating Test Certificates" section in
  the BACnet Secure Connect documentation (`docs/guide/secure-connect.rst`) with
  step-by-step instructions for creating a self-signed CA and device certificates
  using EC P-256 and the ``cryptography`` library, including SAN configuration
  notes for IP address vs DNS hostname verification.

## [1.3.3] - 2026-02-13

### Added

- **BACnet/IP-to-SC gateway router example** (`examples/ip_to_sc_router.py`) --
  Demonstrates bridging a BACnet/IP network and a BACnet Secure Connect network
  using `NetworkRouter` with dual transports (`BIPTransport` + `SCTransport`).
  Shows the real-world building modernisation pattern where existing IP
  controllers communicate transparently with new SC devices through a
  pure-forwarding gateway.

### Fixed

- **`audit_log.py` example used invalid alias `"al,1"`** -- The short alias
  `"al"` is not registered in `OBJECT_TYPE_ALIASES`. Changed to
  `"audit-log,1"` which resolves correctly via hyphen-to-underscore conversion.
  Also fixed the matching code snippet in `docs/guide/examples.rst`.

## [1.3.1] - 2026-02-13

### Added

- **Docker integration tests for BACnet Secure Connect** -- New Scenario 9
  (`secure-connect` profile) with real cross-container WebSocket communication
  between separate hub and node containers on Docker bridge networking. Three
  new container roles: `sc-hub` (SCHubFunction WebSocket server), `sc-node1`
  and `sc-node2` (SCTransport nodes with echo handlers). 9 test cases covering
  hub connection, unicast routing to each node, broadcast delivery to all nodes,
  bidirectional exchange, large NPDU transfer (~1400 bytes), rapid sequential
  messages (50 messages), and concurrent multi-node traffic.
- **`make docker-test-sc`** Makefile target for running the SC Docker scenario
  independently; also added to the `make docker-test` chain.
- 5 in-process SC integration tests moved from `docker/scenarios/` to
  `tests/transport/sc/test_sc_integration.py` where they belong alongside the
  224 existing SC unit tests. Total test count increased from 5,925 to 5,930.

### Changed

- **Docker image now includes SC dependencies** -- Added `--extra secure` to
  both `uv sync` commands in `docker/Dockerfile` so `websockets` and
  `cryptography` are available inside containers.

## [1.3.0] - 2026-02-13

### Added

- **BACnet Secure Connect (Annex AB)** -- Full implementation of BACnet/SC
  per ASHRAE 135-2020 Annex AB, providing encrypted, authenticated BACnet
  communication over WebSocket/TLS with a hub-and-spoke topology and optional
  direct peer-to-peer connections. This is the largest feature addition since
  the initial release.

  New transport layer in `src/bac_py/transport/sc/` (10 modules):
  - **BVLC-SC codec** (`bvlc.py`) -- Encode/decode for all 13 BVLC-SC message
    types (BVLC-Result, Encapsulated-NPDU, Address-Resolution,
    Address-Resolution-ACK, Advertisement, Advertisement-Solicitation,
    Connect-Request, Connect-Accept, Disconnect-Request, Disconnect-ACK,
    Heartbeat-Request, Heartbeat-ACK, Proprietary-Message) with typed payload
    dataclasses, header option chaining, and control flag handling.
  - **VMAC addressing** (`vmac.py`) -- 6-byte virtual MAC addresses with
    locally-administered unicast bit management and 16-byte RFC 4122 Device
    UUIDs for collision detection.
  - **WebSocket I/O layer** (`websocket.py`) -- Sans-I/O `websockets` library
    integration with asyncio TCP/TLS streams for both client and server
    connections, binary frame send/receive, and subprotocol negotiation
    (`hub.bsc.bacnet.org`, `dc.bsc.bacnet.org`).
  - **TLS context builder** (`tls.py`) -- TLS 1.3 client and server SSL context
    creation with mutual authentication, certificate chain loading, and
    plaintext mode for testing.
  - **Connection state machine** (`connection.py`) -- Initiating peer
    (Figure AB-11) and accepting peer (Figure AB-12) state machines with
    Connect-Request/Accept handshake, periodic heartbeat (AB.6.3), graceful
    Disconnect-Request/ACK exchange, VMAC collision detection, and configurable
    timeouts.
  - **Hub Function** (`hub_function.py`) -- WebSocket server (AB.5.3) that
    accepts hub connections from SC nodes, maintains a connection table indexed
    by VMAC, routes unicast messages to destination VMAC, replicates broadcasts
    to all connected nodes except the source, and detects VMAC/UUID collisions.
  - **Hub Connector** (`hub_connector.py`) -- WebSocket client (AB.5.2) with
    persistent connection to a primary hub, automatic reconnection with
    exponential backoff (configurable min/max delay), and failover to a
    secondary hub when the primary is unavailable.
  - **Node Switch** (`node_switch.py`) -- Direct peer-to-peer connection
    manager (AB.4) that listens for inbound direct connections, initiates
    outbound connections via address resolution through the hub, and maintains
    a connection pool with configurable limits.
  - **SC Transport** (`__init__.py`) -- `SCTransport` class implementing the
    `TransportPort` protocol, wiring together the hub connector, optional hub
    function, and optional node switch. Integrates with the existing
    `NetworkLayer` transparently -- the network layer sees standard 6-byte MAC
    addresses (VMACs) and uses the same `send_unicast`/`send_broadcast` API.
  - **Types and constants** (`types.py`) -- `BvlcSCFunction` (13 message types),
    `SCControlFlag`, `SCResultCode`, `SCHubConnectionStatus`, header option
    types, WebSocket subprotocol names, and VMAC constants.

  Install with optional dependencies: `pip install bac-py[secure]`
  (websockets>=14.0, cryptography>=42.0).

- **Top-level lazy exports** -- `SCTransport` and `SCTransportConfig` are
  available from `bac_py` via `__getattr__` lazy loading, so importing the
  package incurs no cost when SC is not used.
- **Docker SC integration scenario** -- `docker/scenarios/test_secure_connect.py`
  with 5 tests: two-node unicast via hub, broadcast to all nodes, hub failover,
  direct P2P connection, and concurrent message stress test.
- 224 new unit tests across 10 test files covering BVLC-SC codec round-trips,
  VMAC generation and parsing, WebSocket client/server handshake, TLS context
  creation, connection state machine lifecycle, hub function routing, hub
  connector failover, node switch direct connections, address resolution, SC
  transport protocol compliance, and end-to-end NPDU exchange. Total test count
  increased from 5,701 to 5,925.

### Documentation

- **BACnet/SC user guide** -- New `docs/guide/secure-connect.rst` covering hub
  connection, hub function setup, direct connections via Node Switch, TLS
  certificate configuration, failover, and VMAC address resolution.
- **BACnet/SC features page** -- Added comprehensive SC section to
  `docs/features.rst` with feature bullet list and code example.
- **API reference** -- Added all 8 SC sub-modules to `docs/api/transport.rst`
  (BVLC codec, VMAC, Connection, Hub Function, Hub Connector, Node Switch,
  WebSocket, TLS, Types).
- **Getting started** -- Added `pip install bac-py[secure]` installation
  instructions and optional dependency note.
- **Example scripts** -- Added `examples/secure_connect.py` (SC client with
  manual NPDU/APDU construction) and `examples/secure_connect_hub.py` (SC hub
  server with ObjectDatabase, Node Switch, and signal-based shutdown).
- **Examples guide** -- Added BACnet Secure Connect section to
  `docs/guide/examples.rst` documenting both new example scripts.
- **README** -- Added SC feature bullet, `pip install bac-py[secure]`
  installation section, updated architecture and test count.

## [1.2.2] - 2026-02-13

### Added

- **Test coverage improvements** -- Added ~640 new unit tests covering encoding
  edge cases, network layer validation, event engine branches, application
  lifecycle, server handler error paths, object model operations, transport
  frame validation, conformance PICS generation, segmentation accounting,
  service decode branch partials, and type system optional-field paths.
  Coverage improved from 95% (472 uncovered lines) to 99% (15 uncovered lines).
  Total test count increased from 5,061 to 5,701.

### Fixed

- **Protocol stub coverage exclusions** -- Added `# pragma: no cover` to
  `TransportPort`, `Serializer`, and `NetworkSender` protocol class stubs
  (`transport/port.py`, `serialization/__init__.py`, `network/__init__.py`)
  since abstract method bodies (`...`) are untestable by design.

## [1.2.1] - 2026-02-12

### Fixed

- **`read_bdt()`/`read_fdt()` NAK handling** -- These client methods now convert
  the internal `BvlcNakError` to `RuntimeError` when the target device rejects
  the request (not a BBMD), matching the pattern already used by `write_bdt()`.
  Previously the internal exception type was not exported, making it impossible
  for callers to catch cleanly.

### Changed

- **Targeted unicast discovery early return** -- `who_is()` and `discover()`
  now auto-infer `expected_count=1` when `low_limit == high_limit` and the
  destination is a unicast address. This avoids waiting the full broadcast
  timeout (typically 3s) when only one response is expected, reducing targeted
  discovery from ~3s to RTT (~50ms).
- **`who_is_router_to_network()` early return** -- Added `expected_count`
  parameter to `who_is_router_to_network()` (both `BACnetClient` and `Client`
  wrapper). When set, the method returns as soon as the expected number of
  distinct routers have responded instead of waiting the full timeout.

## [1.2.0] - 2026-02-12

### Breaking Changes

- **PropertyIdentifier enum values corrected** -- ~40+ numerical values realigned
  to match ASHRAE 135-2020 Clause 21 pp. 933-942. Key changes:
  `TIME_DELAY_NORMAL` 204→356, `TIME_SYNCHRONIZATION_INTERVAL` 205→204,
  lift/escalator properties renumbered (`CAR_ASSIGNED_DIRECTION` 500→448, etc.),
  staging properties renumbered (`PRESENT_STAGE` at 493, etc.), audit properties
  renumbered (`AUDIT_LEVEL` 550→498, etc.). New properties added:
  `ISSUE_CONFIRMED_NOTIFICATIONS` (51), `INTERFACE_VALUE` (387),
  `LOW_DIFF_LIMIT` (390), `STRIKE_COUNT` (391), and others.
- **EngineeringUnits enum expanded from 62 to 269 members** -- Complete per
  ASHRAE 135-2020 Clause 21. Many existing values corrected: `WATTS` 48→47,
  `KILOWATTS` 49→48, `MEGAWATTS` 50→49, `LITERS_PER_SECOND` 85→87,
  `CUBIC_METERS` 46→80, `KILOGRAMS` 28→39, and others.
- **StagingObject property names corrected** -- Renamed to match Clause 12.62:
  `STAGING_STATE`→`PRESENT_STAGE`, `TARGET_OBJECT`→`STAGES`,
  `TARGET_PROPERTY`→`STAGE_NAMES`, `STAGING_TIMEOUT`→`TARGET_REFERENCES`.
- **AccessEvent enum corrected** -- Renamed
  `NO_ENTRY_AFTER_GRANT`→`NO_ENTRY_AFTER_GRANTED`,
  `DENIED_INCORRECT_AUTHENTICATION`→`DENIED_INCORRECT_AUTHENTICATION_FACTOR`,
  `DENIED_OTHER` 133→164, and 30+ new denied event members added.

### Added

- **5 new enums** -- `AccessCredentialDisableReason` (10 members),
  `LiftCarDoorCommand` (3), `LiftCarDriveStatus` (10), `LiftCarMode` (14),
  `LiftFault` (17) per ASHRAE 135-2020.
- **Bvlc6ResultCode fix** -- `VIRTUAL_ADDRESS_RESOLUTION_NAK` corrected from
  0x0060 to 0x0040 per Clause 7.
- **Examples guide** -- New `docs/guide/examples.rst` covering all 17 example
  scripts organized into 5 categories with code snippets and cross-references.
- **Device management guide sections** -- Added Device Communication Control,
  Reinitialization, Time Synchronization, and Object Management sections to
  `docs/guide/device-management.rst`.
- 120+ new enum tests covering `LiftFault`, `LiftCarMode`, `LiftCarDoorCommand`,
  `LiftCarDriveStatus`, `AccessCredentialDisableReason`, `AccessEvent`,
  `StagingState`, `EscalatorMode`, `EscalatorFault`, `LiftCarDirection`,
  `LiftGroupMode`, `LiftCarDoorStatus`, `AccessCredentialDisable`.

### Fixed

- **Docker infrastructure** -- Pinned uv from `latest` to `0.9` in Dockerfile
  for deterministic builds. Updated firmware/application version strings from
  `"0.1.0"` to `"1.2.0"` across all 4 server roles. Added `BROADCAST_ADDRESS`
  env var support to thermostat demo. Added `.dockerignore` exclusions
  (`.github/`, `.env*`, `tests/`, `*.md`).
- **Makefile CI alignment** -- Added `docker/` to `lint`, `fix`, and `format`
  targets to match CI. Added `--profile demo` and `--profile stress-runner`
  to `docker-clean` target.

### Changed

- **Documentation completeness** -- Added missing services
  (`SubscribeCOVProperty`, `SubscribeCOVPropertyMultiple`,
  `ConfirmedCOVNotification`, `ConfirmedCOVNotificationMultiple`,
  `GetEventInformation`, `UnconfirmedCOVNotificationMultiple`) to `features.rst`
  and `README.md`. Updated test count from 4,920+ to 5,050+. Fixed stale
  architecture link in `features.rst`.

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
