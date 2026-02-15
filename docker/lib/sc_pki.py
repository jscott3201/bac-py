"""Shared PKI generation for BACnet/SC Docker tests and benchmarks.

Generates a self-signed EC P-256 test CA and device certificates for mutual
TLS 1.3 authentication.  The generated certificates are suitable for local
and Docker testing only (1-year validity, self-signed CA, localhost + Docker
network SANs).

Functions:
    generate_test_pki  -- Generate full PKI into a directory
    tls_config_for     -- Build an SCTLSConfig for a named entity
"""

from __future__ import annotations

import datetime
import ipaddress
import shutil
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

if TYPE_CHECKING:
    from pathlib import Path

    from bac_py.transport.sc.tls import SCTLSConfig


def generate_test_pki(
    cert_dir: Path,
    names: list[str] | None = None,
) -> None:
    """Generate a self-signed CA and device certificates.

    :param cert_dir: Directory to write PEM files into (created if missing,
        removed first if it already exists).
    :param names: Device certificate names to generate.  Each name gets
        ``<name>.key`` and ``<name>.crt``.  Defaults to
        ``["hub", "node1", "node2", "stress"]``.
    """
    if names is None:
        names = ["hub", "node1", "node2", "stress"]

    if cert_dir.exists():
        shutil.rmtree(cert_dir)
    cert_dir.mkdir(parents=True)

    now = datetime.datetime.now(tz=datetime.UTC)
    validity = datetime.timedelta(days=365)

    # --- CA key + self-signed certificate ---
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BACnet Test CA")])
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
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
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(ca_ski, critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(cert_dir / "ca.key", ca_key)
    _write_cert(cert_dir / "ca.crt", ca_cert)

    # --- Device certificates ---
    ca_aki = x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski)
    for name in names:
        device_key = ec.generate_private_key(ec.SECP256R1())
        device_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, f"BACnet SC {name.title()}")]
        )
        device_cert = (
            x509.CertificateBuilder()
            .subject_name(device_name)
            .issuer_name(ca_name)
            .public_key(device_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + validity)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                        # Docker bridge network addresses (172.30.1.x)
                        x509.IPAddress(ipaddress.IPv4Network("172.30.0.0/16")),
                    ]
                ),
                critical=False,
            )
            .add_extension(ca_aki, critical=False)
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(device_key.public_key()),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        _write_key(cert_dir / f"{name}.key", device_key)
        _write_cert(cert_dir / f"{name}.crt", device_cert)


def tls_config_for(cert_dir: Path, name: str) -> SCTLSConfig:
    """Build an ``SCTLSConfig`` for a named entity.

    :param cert_dir: Directory containing the PKI files.
    :param name: Entity name (e.g. ``"hub"``, ``"node1"``, ``"stress"``).
    :returns: An ``SCTLSConfig`` instance configured with the entity's key,
        certificate, and the CA certificate.
    """
    from bac_py.transport.sc.tls import SCTLSConfig

    return SCTLSConfig(
        private_key_path=str(cert_dir / f"{name}.key"),
        certificate_path=str(cert_dir / f"{name}.crt"),
        ca_certificates_path=str(cert_dir / "ca.crt"),
    )


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    """Write an EC private key to a PEM file."""
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    """Write an X.509 certificate to a PEM file."""
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
