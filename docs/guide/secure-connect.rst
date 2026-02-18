.. _secure-connect:

BACnet Secure Connect
=====================

BACnet Secure Connect (BACnet/SC) is a modern transport defined in ASHRAE
135-2020 Annex AB. It replaces traditional BACnet/IP broadcast UDP with
TLS-secured WebSocket connections arranged in a hub-and-spoke topology. This
makes BACnet traffic IT-friendly -- it traverses firewalls, NAT, and routed
IP networks without requiring BBMD infrastructure or special UDP broadcast
forwarding rules.

BACnet/SC is a transport-layer replacement. The BACnet application layer
(services, objects, encoding) remains identical -- existing application code
works unchanged once the transport is swapped from BACnet/IP to BACnet/SC.


Why BACnet/SC?
--------------

- **IT-friendly** -- uses standard HTTPS ports and TLS, compatible with
  corporate firewalls and network policies
- **Encrypted** -- all traffic is protected by TLS 1.3 with mutual
  authentication via X.509 certificates
- **No broadcast** -- eliminates the need for BBMDs and directed broadcast
  configuration
- **NAT traversal** -- nodes connect outbound to the hub, so devices behind
  NAT work without port forwarding
- **Cloud-ready** -- hubs can run in the cloud, enabling remote access to
  building networks


Installation
------------

BACnet/SC requires the ``websockets`` and ``cryptography`` libraries. Install
them with the ``secure`` extra:

.. code-block:: bash

   pip install bac-py[secure]


Architecture
------------

BACnet/SC uses a hub-and-spoke topology. All nodes connect to a central hub
via WebSocket over TLS. The hub relays messages between connected nodes.
Optionally, nodes can establish direct peer-to-peer WebSocket connections to
bypass the hub for latency-sensitive traffic.

.. code-block:: text

                         +------------------+
                         |   SC Hub (TLS)   |
                         |  wss://hub:8443  |
                         +--------+---------+
                                  |
                   +--------------+--------------+
                   |              |              |
              +----+----+   +----+----+   +----+----+
              | Node A  |   | Node B  |   | Node C  |
              | (Hub    |   | (Hub    |   | (Hub    |
              | Connect)|   | Connect)|   | Connect)|
              +---------+   +----+----+   +---------+
                                 |
                    Direct Connect (optional)
                                 |
                            +----+----+
                            | Node D  |
                            |(Node SW)|
                            +---------+

Each node is identified by a :class:`~bac_py.transport.sc.types.DeviceUUID`
(a 128-bit UUID bound to the device's operational certificate) and a 6-byte
:class:`~bac_py.transport.sc.vmac.SCVMAC` virtual MAC address that is unique
within the SC network.


High-Level Integration
-----------------------

BACnet/SC is fully integrated into :class:`~bac_py.app.application.BACnetApplication`
and :class:`~bac_py.client.Client`.  Pass an ``SCTransportConfig`` to
``DeviceConfig(sc_config=...)`` or ``Client(sc_config=...)`` and the SC
transport replaces BACnet/IP transparently -- all services, objects, and
encoding work identically.

**SC server** -- run a hub with full APDU dispatch (ReadProperty, WriteProperty,
Who-Is, etc.):

.. code-block:: python

   from bac_py import BACnetApplication, DeviceConfig
   from bac_py.transport.sc import SCTransportConfig
   from bac_py.transport.sc.hub_function import SCHubConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   tls = SCTLSConfig(ca_certificates_path="ca.pem",
                      certificate_path="hub.pem",
                      private_key_path="hub.key")

   config = DeviceConfig(
       instance_number=100,
       sc_config=SCTransportConfig(
           hub_function_config=SCHubConfig(bind_address="0.0.0.0", bind_port=8443,
                                           tls_config=tls),
           tls_config=tls,
       ),
   )
   app = BACnetApplication(config)
   await app.start()

See ``examples/sc_server.py`` for a complete server example.

**SC client** -- connect to an existing hub and use the convenience API:

.. code-block:: python

   from bac_py import Client
   from bac_py.transport.sc import SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   sc_config = SCTransportConfig(
       primary_hub_uri="wss://hub.example.com:8443",
       tls_config=SCTLSConfig(ca_certificates_path="ca.pem",
                               certificate_path="device.pem",
                               private_key_path="device.key"),
   )
   async with Client(instance_number=999, sc_config=sc_config) as client:
       devices = await client.discover(timeout=5.0)

The rest of this guide covers the lower-level ``SCTransport`` API for advanced
use cases (manual NPDU/APDU construction, custom callbacks, etc.).


Quick Start: Connecting to a Hub (Low-Level)
---------------------------------------------

The low-level approach connects directly to a hub via ``SCTransport``:

.. code-block:: python

   import asyncio
   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   async def main():
       config = SCTransportConfig(
           primary_hub_uri="wss://hub.example.com:8443",
           tls_config=SCTLSConfig(
               ca_certificates_path="/path/to/ca.pem",
               certificate_path="/path/to/device.pem",
               private_key_path="/path/to/device.key",
           ),
       )

       transport = SCTransport(config)
       await transport.start()

       connected = await transport.hub_connector.wait_connected(timeout=10.0)
       if connected:
           print(f"Connected! Local VMAC: {transport.local_mac.hex()}")
           # Send/receive NPDUs via transport.send_unicast() / transport.on_receive()

       await transport.stop()

   asyncio.run(main())

The :class:`~bac_py.transport.sc.SCTransport` handles the WebSocket
connection, TLS handshake, VMAC assignment, and BVLC-SC message framing
transparently.


Hub Function: Running Your Own Hub (Low-Level)
------------------------------------------------

To run a BACnet/SC hub using the low-level transport API (without APDU
dispatch -- see `High-Level Integration`_ above for the recommended
approach), use the
:class:`~bac_py.transport.sc.SCTransport` with a
:class:`~bac_py.transport.sc.hub_function.SCHubConfig`:

.. code-block:: python

   import asyncio
   from bac_py.transport.sc import SCTransport, SCTransportConfig
   from bac_py.transport.sc.hub_function import SCHubConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   async def main():
       tls = SCTLSConfig(
           ca_certificates_path="/path/to/ca.pem",
           certificate_path="/path/to/hub.pem",
           private_key_path="/path/to/hub.key",
       )

       config = SCTransportConfig(
           hub_function_config=SCHubConfig(
               bind_address="0.0.0.0",
               bind_port=8443,
               tls_config=tls,
           ),
           tls_config=tls,
       )
       transport = SCTransport(config)
       await transport.start()
       print("Hub listening on 0.0.0.0:8443")

       # Keep running until interrupted
       try:
           await asyncio.Event().wait()
       finally:
           await transport.stop()

   asyncio.run(main())

The :class:`~bac_py.transport.sc.hub_function.SCHubFunction` accepts incoming
WebSocket connections, authenticates clients via mutual TLS, and relays
BVLC-SC messages between connected nodes. Broadcast messages are forwarded to
all connected nodes; unicast messages are delivered to the specific destination
VMAC.


Direct Connections: Peer-to-Peer via Node Switch
--------------------------------------------------

For latency-sensitive communication, two nodes can establish a direct
WebSocket connection that bypasses the hub. Enable the
:class:`~bac_py.transport.sc.node_switch.SCNodeSwitch` via
``node_switch_config``:

.. code-block:: python

   from bac_py.transport.sc import SCTransportConfig
   from bac_py.transport.sc.node_switch import SCNodeSwitchConfig
   from bac_py.transport.sc.tls import SCTLSConfig

   config = SCTransportConfig(
       primary_hub_uri="wss://hub.example.com:8443",
       node_switch_config=SCNodeSwitchConfig(
           enable=True,
           bind_address="0.0.0.0",
           bind_port=8444,
       ),
       tls_config=SCTLSConfig(
           ca_certificates_path="/path/to/ca.pem",
           certificate_path="/path/to/device.pem",
           private_key_path="/path/to/device.key",
       ),
   )

When the Node Switch is enabled, the transport uses the BVLC-SC
Address-Resolution and Advertisement messages to discover the direct
connection URIs of other nodes. If a peer advertises a direct connection
endpoint, traffic to that peer is sent over the direct WebSocket link
instead of being relayed through the hub.


TLS Configuration
-----------------

BACnet/SC requires TLS 1.3 with mutual authentication. Both the hub and
connecting nodes must present valid X.509 certificates.

The :class:`~bac_py.transport.sc.tls.SCTLSConfig` dataclass holds the TLS
parameters:

.. code-block:: python

   from bac_py.transport.sc.tls import SCTLSConfig

   tls = SCTLSConfig(
       ca_certificates_path="/path/to/ca.pem",       # CA certificate (or bundle)
       certificate_path="/path/to/device.pem",        # Device operational certificate
       private_key_path="/path/to/device.key",        # Device private key
   )

Certificate requirements:

- The **CA certificate** (``ca_certificates_path``) is used to verify the
  peer's certificate chain. This can be a single CA or a bundle of trusted CAs.
- The **device certificate** (``certificate_path``) is the operational
  certificate presented during the TLS handshake. Per Annex AB, this
  certificate should contain the device's BACnet Device UUID in a Subject
  Alternative Name extension.
- The **private key** (``private_key_path``) corresponds to the device
  certificate.

The :func:`~bac_py.transport.sc.tls.build_client_ssl_context` and
:func:`~bac_py.transport.sc.tls.build_server_ssl_context` functions build
a Python ``ssl.SSLContext`` from the
:class:`~bac_py.transport.sc.tls.SCTLSConfig` with the correct protocol
version and verification settings.


Generating Test Certificates
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Production deployments use certificates issued by a site-specific BACnet CA
(often managed by the building's IT department).  For development and testing,
you can generate a self-signed CA and device certificates using the
``cryptography`` library that ships with ``bac-py[secure]``.

The test PKI consists of three layers:

1. **CA certificate** -- a self-signed Certificate Authority that signs all
   device certificates.  Every device loads this CA to verify its peers.
2. **Hub certificate** -- signed by the CA, presented by the hub during the
   TLS handshake.
3. **Node certificate(s)** -- signed by the same CA, presented by each
   connecting node.  Because TLS is *mutual*, both sides verify each other.

BACnet/SC recommends EC P-256 (``SECP256R1``) keys: they are compact, fast,
and natively supported by TLS 1.3.

.. code-block:: python

   import datetime, ipaddress
   from cryptography import x509
   from cryptography.hazmat.primitives import hashes, serialization
   from cryptography.hazmat.primitives.asymmetric import ec
   from cryptography.x509.oid import NameOID

   now = datetime.datetime.now(tz=datetime.UTC)
   validity = datetime.timedelta(days=365)

   # 1. CA key + self-signed certificate
   ca_key = ec.generate_private_key(ec.SECP256R1())
   ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BACnet Test CA")])
   ca_cert = (
       x509.CertificateBuilder()
       .subject_name(ca_name)
       .issuer_name(ca_name)
       .public_key(ca_key.public_key())
       .serial_number(x509.random_serial_number())
       .not_valid_before(now)
       .not_valid_after(now + validity)
       .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
       .add_extension(
           x509.KeyUsage(
               digital_signature=True, key_cert_sign=True, crl_sign=True,
               content_commitment=False, key_encipherment=False,
               data_encipherment=False, key_agreement=False,
               encipher_only=False, decipher_only=False,
           ),
           critical=True,
       )
       .sign(ca_key, hashes.SHA256())
   )

   # 2. Device key + certificate signed by the CA
   device_key = ec.generate_private_key(ec.SECP256R1())
   device_cert = (
       x509.CertificateBuilder()
       .subject_name(x509.Name(
           [x509.NameAttribute(NameOID.COMMON_NAME, "BACnet SC Hub")]
       ))
       .issuer_name(ca_name)
       .public_key(device_key.public_key())
       .serial_number(x509.random_serial_number())
       .not_valid_before(now)
       .not_valid_after(now + validity)
       .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
       .add_extension(
           x509.SubjectAlternativeName([
               x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
           ]),
           critical=False,
       )
       .sign(ca_key, hashes.SHA256())
   )

   # 3. Write PEM files
   Path("hub.key").write_bytes(device_key.private_bytes(
       serialization.Encoding.PEM,
       serialization.PrivateFormat.PKCS8,
       serialization.NoEncryption(),
   ))
   Path("hub.crt").write_bytes(device_cert.public_bytes(serialization.Encoding.PEM))
   Path("ca.crt").write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

Repeat step 2 for each device (node, router, etc.), giving each its own
key pair and a unique Common Name.

Key points:

- The **SubjectAlternativeName** extension must include the hostname or IP
  address that peers use to connect.  Use ``x509.DNSName`` for hostnames
  and ``x509.IPAddress`` for IP addresses -- Python's TLS hostname verifier
  requires IP addresses to appear as ``iPAddress`` SAN entries, not
  ``dNSName``.
- The CA's **BasicConstraints** must set ``ca=True`` and **KeyUsage** must
  include ``key_cert_sign`` so that device certificates pass chain
  validation.
- Device certificates set ``ca=False`` -- they are leaf certificates.

For a complete runnable example that generates a full test PKI (CA + hub +
two nodes) and verifies mutual TLS end-to-end, see
``examples/sc_generate_certs.py`` and the :ref:`examples guide
<examples-secure-connect>`.

For testing without any certificates, set ``allow_plaintext=True`` on
:class:`~bac_py.transport.sc.tls.SCTLSConfig` and use ``ws://`` URIs.
This disables all TLS and must never be used in production.


Failover: Primary and Failover Hub
------------------------------------

BACnet/SC supports hub failover. Configure both a primary and failover hub
URI in :class:`~bac_py.transport.sc.SCTransportConfig`:

.. code-block:: python

   from bac_py.transport.sc import SCTransportConfig

   config = SCTransportConfig(
       primary_hub_uri="wss://hub1.example.com:8443",
       failover_hub_uri="wss://hub2.example.com:8443",
   )

The :class:`~bac_py.transport.sc.hub_connector.SCHubConnector` connects to
the primary hub first. If the connection drops or cannot be established, it
automatically switches to the failover hub. When the primary hub becomes
available again, the connector reconnects to it. This provides continuous
operation even during hub maintenance or outages.


Address Resolution
------------------

In BACnet/SC, nodes do not use IP addresses directly for BACnet
communication. Instead, each node has a 6-byte
:class:`~bac_py.transport.sc.vmac.SCVMAC` (Virtual MAC Address) that
uniquely identifies it within the SC network.

Address resolution uses BVLC-SC Advertisement and Address-Resolution messages:

1. A node that wants to find the VMAC of a peer sends an
   Address-Resolution request through the hub.
2. The target node responds with an Address-Resolution-ACK containing its
   VMAC and optional direct-connection URI.
3. The requesting node caches the VMAC-to-URI mapping for subsequent
   direct connections.

From the application layer, addressing works the same as other BACnet
transports -- the network layer handles VMAC resolution transparently.

.. code-block:: python

   from bac_py.transport.sc.vmac import SCVMAC

   # Create a VMAC from bytes
   vmac = SCVMAC(b"\x01\x02\x03\x04\x05\x06")

   # VMACs are used internally by the transport layer;
   # application code typically uses standard BACnet addressing.
