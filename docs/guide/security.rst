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
   boundary.

**Allocation caps**
   Tag lengths exceeding 1 MB (1,048,576 bytes) are rejected to prevent memory
   exhaustion from malformed length fields. This catches both corrupted packets
   and deliberate attempts to trigger large allocations.

**Context nesting depth**
   Nested context tags are limited to a depth of 32. Deeply nested or recursive
   structures that exceed this limit raise ``ValueError``, preventing stack
   exhaustion from crafted payloads.

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

**VMAC origin validation**
   The hub function validates the source VMAC address on every received BVLC-SC
   message against the connection's registered VMAC. This prevents a connected
   node from spoofing another node's address in hub-routed traffic.

**WebSocket frame size limits**
   SC WebSocket connections support a configurable ``max_frame_size`` parameter.
   Frames exceeding the limit are logged and discarded, preventing a peer from
   consuming unbounded memory with oversized messages.

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
