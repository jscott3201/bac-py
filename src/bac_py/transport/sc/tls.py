"""TLS context builder for BACnet/SC (AB.7.4).

Provides helpers to create ``ssl.SSLContext`` objects for client and server
sides of BACnet/SC WebSocket connections, enforcing TLS 1.3 with mutual
authentication per the Annex AB requirements.

Optional dependency: ``cryptography`` for certificate inspection utilities.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SCTLSConfig:
    """TLS configuration for a BACnet/SC node.

    :param private_key_path: PEM file containing the device's private key.
    :param certificate_path: PEM file containing the device's operational
        certificate.
    :param ca_certificates_path: PEM file (or colon-separated list of PEM
        files) containing the trusted CA certificates.
    :param allow_plaintext: If True, allow ``ws://`` connections (testing
        only — production BACnet/SC requires TLS 1.3).
    """

    private_key_path: str | None = None
    certificate_path: str | None = None
    ca_certificates_path: str | None = None
    allow_plaintext: bool = False
    extra_ca_paths: list[str] = field(default_factory=list)


def build_client_ssl_context(config: SCTLSConfig) -> ssl.SSLContext | None:
    """Build a TLS 1.3 client context with mutual authentication.

    Returns ``None`` if *config.allow_plaintext* is True and no
    certificate material is provided.
    """
    if config.allow_plaintext and not config.certificate_path:
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3

    if config.certificate_path and config.private_key_path:
        ctx.load_cert_chain(config.certificate_path, config.private_key_path)

    _load_ca_certs(ctx, config)
    return ctx


def build_server_ssl_context(config: SCTLSConfig) -> ssl.SSLContext | None:
    """Build a TLS 1.3 server context with client certificate verification.

    Returns ``None`` if *config.allow_plaintext* is True and no
    certificate material is provided.
    """
    if config.allow_plaintext and not config.certificate_path:
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_mode = ssl.CERT_REQUIRED

    if config.certificate_path and config.private_key_path:
        ctx.load_cert_chain(config.certificate_path, config.private_key_path)

    _load_ca_certs(ctx, config)
    return ctx


def _load_ca_certs(ctx: ssl.SSLContext, config: SCTLSConfig) -> None:
    """Load CA certificates from config into the SSL context."""
    paths: list[str] = []
    if config.ca_certificates_path:
        paths.extend(config.ca_certificates_path.split(":"))
    paths.extend(config.extra_ca_paths)

    for ca_path in paths:
        p = Path(ca_path.strip())
        if p.is_file():
            ctx.load_verify_locations(cafile=str(p))
        elif p.is_dir():
            ctx.load_verify_locations(capath=str(p))
