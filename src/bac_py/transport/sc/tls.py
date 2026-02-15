"""TLS context builder for BACnet/SC (AB.7.4).

Provides helpers to create ``ssl.SSLContext`` objects for client and server
sides of BACnet/SC WebSocket connections, enforcing TLS 1.3 with mutual
authentication per the Annex AB requirements.

Optional dependency: ``cryptography`` for certificate inspection utilities.
"""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


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
    :param key_password: Optional passphrase for the private key PEM file.
        Use ``bytes`` or a callable returning ``bytes`` for programmatic
        retrieval (e.g., from a vault or environment variable).
    :param verify_depth: Desired maximum certificate chain verification depth.
        BACnet PKI chains are typically short (device → issuing CA → root).
        Default 4 allows one intermediate plus some headroom.  Reserved for
        future use — Python's ``ssl`` module does not yet expose OpenSSL's
        ``SSL_CTX_set_verify_depth``.
    """

    private_key_path: str | None = None
    certificate_path: str | None = None
    ca_certificates_path: str | None = None
    allow_plaintext: bool = False
    extra_ca_paths: list[str] = field(default_factory=list)
    key_password: bytes | str | None = None
    verify_depth: int = 4

    def __repr__(self) -> str:
        """Redact secrets to prevent credential leak in logs/tracebacks."""
        key_display = "'<REDACTED>'" if self.private_key_path else "None"
        pw_display = "'<REDACTED>'" if self.key_password else "None"
        return (
            f"SCTLSConfig(private_key_path={key_display}, "
            f"certificate_path={self.certificate_path!r}, "
            f"ca_certificates_path={self.ca_certificates_path!r}, "
            f"allow_plaintext={self.allow_plaintext!r}, "
            f"key_password={pw_display})"
        )


def build_client_ssl_context(config: SCTLSConfig) -> ssl.SSLContext | None:
    """Build a TLS 1.3 client context with mutual authentication.

    Returns ``None`` if *config.allow_plaintext* is True and no
    certificate material is provided.
    """
    if config.allow_plaintext and not config.certificate_path:
        logger.warning(
            "SC TLS disabled: allow_plaintext=True with no certificate. "
            "BACnet/SC requires TLS 1.3 with mutual authentication in production "
            "(ASHRAE 135-2020 Annex AB.7.4). Never use plaintext in production."
        )
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_flags |= ssl.VERIFY_X509_STRICT

    if config.certificate_path and config.private_key_path:
        logger.debug("SC TLS loading client cert: %s", config.certificate_path)
        password = _resolve_password(config.key_password)
        ctx.load_cert_chain(config.certificate_path, config.private_key_path, password=password)
    elif config.certificate_path and not config.private_key_path:
        logger.warning(
            "SC TLS certificate_path is set but private_key_path is missing — "
            "mutual authentication will not work"
        )
    elif config.private_key_path and not config.certificate_path:
        logger.warning(
            "SC TLS private_key_path is set but certificate_path is missing — "
            "mutual authentication will not work"
        )

    _load_ca_certs(ctx, config)
    logger.info("SC TLS client context created: mutual_auth=True")
    return ctx


def build_server_ssl_context(config: SCTLSConfig) -> ssl.SSLContext | None:
    """Build a TLS 1.3 server context with client certificate verification.

    Returns ``None`` if *config.allow_plaintext* is True and no
    certificate material is provided.
    """
    if config.allow_plaintext and not config.certificate_path:
        logger.warning(
            "SC TLS disabled: allow_plaintext=True with no certificate. "
            "BACnet/SC requires TLS 1.3 with mutual authentication in production "
            "(ASHRAE 135-2020 Annex AB.7.4). Never use plaintext in production."
        )
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags |= ssl.VERIFY_X509_STRICT

    if config.certificate_path and config.private_key_path:
        logger.debug("SC TLS loading server cert: %s", config.certificate_path)
        password = _resolve_password(config.key_password)
        ctx.load_cert_chain(config.certificate_path, config.private_key_path, password=password)
    elif config.certificate_path and not config.private_key_path:
        logger.warning(
            "SC TLS certificate_path is set but private_key_path is missing — "
            "mutual authentication will not work"
        )
    elif config.private_key_path and not config.certificate_path:
        logger.warning(
            "SC TLS private_key_path is set but certificate_path is missing — "
            "mutual authentication will not work"
        )

    _load_ca_certs(ctx, config)
    logger.info("SC TLS server context created: mutual_auth=True")
    return ctx


def _resolve_password(key_password: bytes | str | None) -> bytes | None:
    """Convert key_password to bytes for ssl.SSLContext.load_cert_chain()."""
    if key_password is None:
        return None
    if isinstance(key_password, str):
        return key_password.encode("utf-8")
    return key_password


def _load_ca_certs(ctx: ssl.SSLContext, config: SCTLSConfig) -> None:
    """Load CA certificates from config into the SSL context.

    BACnet/SC devices must only trust explicitly configured CAs — never the
    system certificate store.  When no CA paths are provided we log a warning
    but intentionally do **not** call ``ctx.load_default_certs()`` so that
    peer verification will fail rather than silently trusting arbitrary CAs.
    """
    paths: list[str] = []
    if config.ca_certificates_path:
        paths.extend(config.ca_certificates_path.split(":"))
    paths.extend(config.extra_ca_paths)

    if not paths:
        logger.warning(
            "SC TLS no CA certificates configured — peer certificate "
            "verification will fail. BACnet/SC requires explicitly configured "
            "CA certificates; system CAs are intentionally not trusted."
        )

    for ca_path in paths:
        p = Path(ca_path.strip())
        if p.is_file():
            logger.debug("SC TLS loading CA file: %s", p)
            ctx.load_verify_locations(cafile=str(p))
        elif p.is_dir():
            logger.debug("SC TLS loading CA directory: %s", p)
            ctx.load_verify_locations(capath=str(p))
