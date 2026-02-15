.. _security:

Security and Memory Safety
==========================

bac-py implements defense-in-depth for protocol parsing, transport security,
memory management, and logging. This guide describes the safety measures built
into the library and recommendations for production deployments.


.. _protocol-safety:

Protocol Safety
---------------

BACnet uses ASN.1 Basic Encoding Rules (BER) with tag-length-value (TLV)
encoding. Malformed or malicious packets can attempt to cause buffer overreads,
excessive memory allocation, or deep recursion. bac-py validates all fields
before processing:

**Tag and length validation**
   Every ``decode_tag()`` call validates that the buffer contains enough bytes
   for the tag number, length field, and content before reading. Truncated
   packets raise ``ValueError`` immediately rather than reading past the buffer
   boundary. Context-tag extraction (``extract_context_value``) additionally
   validates that primitive tag lengths do not extend past the buffer end.

**Primitive type buffer checks**
   ``decode_real()`` and ``decode_double()`` validate the input buffer is at
   least 4 or 8 bytes before calling ``struct.unpack_from()``, raising a clear
   ``ValueError`` instead of an opaque ``struct.error`` on truncated data.
   ErrorPDU decoding performs bounds checks after each ``decode_tag()`` call to
   reject truncated error class and error code fields.

**Allocation caps**
   Tag lengths exceeding 1 MB (1,048,576 bytes) are rejected to prevent memory
   exhaustion from malformed length fields. This catches both corrupted packets
   and deliberate attempts to trigger large allocations.

**Service decoder list caps**
   All service decode loops (ReadPropertyMultiple, WritePropertyMultiple,
   alarm summary, COV, write group, virtual terminal, object management, and
   audit services) enforce a maximum of 10,000 decoded items per message.
   This prevents crafted payloads with thousands of repeated elements from
   consuming excessive memory during decoding.

**Context nesting depth**
   Nested context tags are limited to a depth of 32. Deeply nested or recursive
   structures that exceed this limit raise ``ValueError``, preventing stack
   exhaustion from crafted payloads. This is enforced in the core tag decoder,
   the audit service decode paths, COV property value decoding, and all
   service decoders with manual nesting loops.

**Segmentation reassembly cap**
   ``SegmentReceiver`` tracks cumulative reassembly size and aborts the
   transaction when the total exceeds 1 MiB (1,048,576 bytes), preventing a
   peer from consuming unbounded memory with many small segments.

**Ethernet frame validation**
   The Ethernet transport rejects 802.3 frames whose length field is below the
   minimum LLC header size (3 bytes), preventing underflow when extracting the
   NPDU payload.

**APDU size constraints**
   Maximum APDU sizes are enforced per Clause 20.1.2.5 (50--1476 bytes). When
   communicating with a remote device, the library constrains requests to the
   minimum of the local and remote device's ``max_apdu_length_accepted`` value,
   populated automatically from I-Am responses.


.. _transport-security:

Transport Security
------------------

**TLS 1.3 for BACnet/SC**
   BACnet Secure Connect (Annex AB) requires TLS 1.3 with mutual
   authentication. Both hub and node present X.509 certificates, and the
   server context sets ``ssl.CERT_REQUIRED`` to enforce client certificate
   verification. The minimum TLS version is pinned to TLS 1.3 --
   older protocol versions are not negotiated.

**Plaintext warnings**
   When ``allow_plaintext=True`` is set on a TLS configuration (intended only
   for development and testing), the library logs a ``WARNING`` on every
   affected path: TLS client context creation, TLS server context creation, and
   transport startup. These warnings make it immediately visible when
   encryption is disabled.

**Stress test TLS coverage**
   All BACnet/SC stress tests and benchmarks (both local and Docker) exercise
   mutual TLS 1.3 by default using a mock CA with EC P-256 certificates.  This
   ensures that TLS handshake overhead and encrypted data paths are included in
   performance measurements. The local benchmark accepts ``--no-tls`` to fall
   back to plaintext for comparison.

**VMAC origin validation**
   The hub function validates the source VMAC address on every received BVLC-SC
   message against the connection's registered VMAC. This prevents a connected
   node from spoofing another node's address in hub-routed traffic.

**WebSocket frame size limits**
   SC WebSocket connections support a configurable ``max_frame_size`` parameter.
   Frames exceeding the limit are logged and discarded.  After 3 consecutive
   oversized frames, the connection is closed to prevent log flooding from
   misbehaving peers.  The internal pending events buffer is capped at 64
   entries to bound memory when a single TCP segment delivers many WebSocket
   frames.

**VMAC collision atomicity**
   The hub function reserves a VMAC address in a ``_pending_vmacs`` dictionary
   when the collision check passes during the BACnet/SC handshake.  This
   prevents a time-of-check/time-of-use (TOCTOU) race where two connections
   with the same VMAC could both pass the check before either is registered.
   Reservations expire after 30 seconds and the pending set is capped at
   ``max_connections`` to prevent growth from abandoned handshakes.

**URI scheme validation**
   When a hub provides peer WebSocket URIs via Address-Resolution-ACK, the node
   switch validates that each URI uses a ``ws://`` or ``wss://`` scheme before
   connecting.  URIs with other schemes are logged and skipped, preventing a
   malicious hub from redirecting the node to non-WebSocket endpoints.

**SC header options count and size limits**
   BVLC-SC header option decoding enforces a maximum of 32 options per list
   and a maximum of 512 bytes per individual option data field.  The BACnet/SC
   spec defines only two option types (Secure Path and Proprietary), so
   legitimate messages never approach these limits.  This prevents crafted
   payloads from causing excessive allocations via option count or oversized
   option data (up to 65,535 bytes per the wire format).

**SC address resolution URI cap**
   ``AddressResolutionAckPayload`` decoding truncates the URI list to 16
   entries, preventing unbounded allocations from malformed address resolution
   responses.

**Credential redaction**
   The ``SCTLSConfig.__repr__()`` method redacts ``private_key_path`` as
   ``'<REDACTED>'`` so private key paths never appear in logs, tracebacks, or
   debug output.

See :doc:`secure-connect` for TLS certificate setup, hub configuration, and
failover.


.. _logging-safety:

Logging Safety
--------------

**Lazy formatting**
   All log statements use ``%s``-style placeholder formatting
   (e.g., ``logger.debug("decode APDU type=%s", pdu_type)``), not f-strings.
   This ensures format arguments are only evaluated when the log level is
   active, avoiding unnecessary computation on suppressed messages and
   preventing format string injection.

**No sensitive data in output**
   Private keys, passwords, and certificate contents are never included in log
   messages, ``__repr__`` output, or error messages. Password comparisons use
   ``hmac.compare_digest()`` to prevent timing side-channels.

See :doc:`debugging-logging` for logger configuration and practical debugging
recipes.


.. _memory-safety:

Memory Safety
-------------

**Immutable protocol objects**
   Service request and response types, BVLC-SC messages, and other protocol
   structures are frozen dataclasses (``@dataclass(frozen=True, slots=True)``).
   Once created, their fields cannot be mutated, eliminating a class of state
   corruption bugs.

**Bounded buffers**
   Trend log and audit log objects use circular buffer management with
   configurable maximum sizes. When a buffer reaches capacity, the oldest
   entries are overwritten. This prevents unbounded memory growth from
   long-running data collection.

**Transport resource caps**
   All transport layers enforce size limits on network-facing data structures to
   prevent memory exhaustion from malicious or misbehaving peers:

   - **BBMD** -- Foreign device tables are capped by ``max_fdt_entries``
     (default 128) and broadcast distribution tables by ``max_bdt_entries``
     (default 128).  Requests exceeding either limit are NAKed.  Foreign device
     registration TTLs are capped at 3600 seconds (1 hour).
   - **BACnet/IPv6** -- The VMAC resolution cache enforces a ``max_entries``
     limit (default 4096) with automatic stale-entry eviction.  Pending address
     resolutions are capped at 1024 concurrent VMACs.
   - **BACnet/SC** -- The node switch caps pending address resolutions to
     ``max_connections``.  The hub function caps active connections via
     ``max_connections``.

**Enum vendor caches**
   The ``ObjectType._missing_()`` and ``PropertyIdentifier._missing_()``
   vendor-proprietary enum caches are both capped at 4,096 entries.  When the
   cap is reached the cache is cleared, preventing unbounded memory growth from
   protocol traffic containing many distinct vendor-proprietary type codes.

**Change callback cap**
   ``ObjectDatabase.register_change_callback()`` limits each property to 100
   registered callbacks, raising ``ValueError`` if the limit is exceeded.  This
   prevents accidental unbounded growth from repeated registrations.

**Constant-time secret comparison**
   Password verification in server handlers uses ``hmac.compare_digest()``
   rather than ``==``, preventing timing attacks that could reveal password
   length or content through response time variations.


.. _dependency-posture:

Dependency Posture
------------------

bac-py has **zero required runtime dependencies** for the core library. This
minimizes the attack surface from third-party code:

- **Core library** -- no external packages required; uses only the Python
  standard library (``asyncio``, ``ssl``, ``struct``, ``logging``, etc.)
- **BACnet/SC** -- optional ``websockets`` and ``cryptography`` packages,
  installed via ``pip install bac-py[secure]``
- **JSON serialization** -- optional ``orjson`` for performance, installed via
  ``pip install bac-py[serialization]``

All optional dependencies are well-maintained, widely-used packages with
active security response processes.


.. _production-checklist:

Production Checklist
--------------------

When deploying bac-py in production environments:

- **Enable TLS** -- never set ``allow_plaintext=True`` outside of development.
  BACnet/SC requires TLS 1.3 with mutual authentication for production use.
- **Set buffer limits** -- configure ``buffer_size`` on trend log and audit log
  objects to match available memory. The default circular buffer prevents
  unbounded growth, but sizing it appropriately avoids unnecessary memory use.
- **Enable INFO logging** -- ``INFO`` level covers lifecycle events and
  significant operations without per-packet overhead. Reserve ``DEBUG`` for
  targeted troubleshooting on specific modules.
- **Keep dependencies updated** -- regularly update optional dependencies
  (``websockets``, ``cryptography``, ``orjson``) to pick up security patches.
- **Bind to specific interfaces** -- when creating transports, specify the
  interface address rather than binding to ``0.0.0.0`` to limit exposure.
- **Use passwords for device control** -- set passwords on
  DeviceCommunicationControl and ReinitializeDevice handlers to prevent
  unauthorized device manipulation.
