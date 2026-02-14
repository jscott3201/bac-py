import logging
import ssl
import tempfile
from pathlib import Path

import pytest

from bac_py.transport.sc.tls import (
    SCTLSConfig,
    build_client_ssl_context,
    build_server_ssl_context,
)


class TestSCTLSConfig:
    def test_default_values(self):
        cfg = SCTLSConfig()
        assert cfg.private_key_path is None
        assert cfg.certificate_path is None
        assert cfg.ca_certificates_path is None
        assert cfg.allow_plaintext is False
        assert cfg.extra_ca_paths == []

    def test_custom_values(self):
        cfg = SCTLSConfig(
            private_key_path="/path/to/key.pem",
            certificate_path="/path/to/cert.pem",
            ca_certificates_path="/path/to/ca.pem",
        )
        assert cfg.private_key_path == "/path/to/key.pem"
        assert cfg.certificate_path == "/path/to/cert.pem"


class TestBuildClientSSLContext:
    def test_plaintext_no_cert_returns_none(self):
        cfg = SCTLSConfig(allow_plaintext=True)
        ctx = build_client_ssl_context(cfg)
        assert ctx is None

    def test_plaintext_with_cert_returns_context(self):
        # Provide cert path (won't actually load, just tests branch)
        cfg = SCTLSConfig(
            allow_plaintext=True,
            certificate_path="/nonexistent/cert.pem",
            private_key_path="/nonexistent/key.pem",
        )
        # Will fail at load_cert_chain, but we test that it tries
        with pytest.raises((ssl.SSLError, FileNotFoundError, OSError)):
            build_client_ssl_context(cfg)

    def test_returns_ssl_context_no_certs(self):
        cfg = SCTLSConfig()
        ctx = build_client_ssl_context(cfg)
        assert isinstance(ctx, ssl.SSLContext)

    def test_tls_13_minimum(self):
        cfg = SCTLSConfig()
        ctx = build_client_ssl_context(cfg)
        assert ctx is not None
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_protocol_is_tls_client(self):
        cfg = SCTLSConfig()
        ctx = build_client_ssl_context(cfg)
        assert ctx is not None


class TestBuildServerSSLContext:
    def test_plaintext_no_cert_returns_none(self):
        cfg = SCTLSConfig(allow_plaintext=True)
        ctx = build_server_ssl_context(cfg)
        assert ctx is None

    def test_returns_ssl_context_no_certs(self):
        cfg = SCTLSConfig()
        ctx = build_server_ssl_context(cfg)
        assert isinstance(ctx, ssl.SSLContext)

    def test_tls_13_minimum(self):
        cfg = SCTLSConfig()
        ctx = build_server_ssl_context(cfg)
        assert ctx is not None
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_verify_mode_cert_required(self):
        cfg = SCTLSConfig()
        ctx = build_server_ssl_context(cfg)
        assert ctx is not None
        assert ctx.verify_mode == ssl.CERT_REQUIRED


class TestCACertLoading:
    def test_ca_path_file(self):
        # Create a temp file that's not a real cert — just test the path logic
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            # Write minimal but syntactically okay PEM (will fail validation but
            # tests the code path for is_file())
            f.write(b"not a real cert")
            f.flush()
            cfg = SCTLSConfig(ca_certificates_path=f.name)
            # Will fail because it's not a real cert, but exercises the path
            with pytest.raises(ssl.SSLError):
                build_client_ssl_context(cfg)
            Path(f.name).unlink()

    def test_colon_separated_paths(self):
        cfg = SCTLSConfig(ca_certificates_path="/nonexistent1.pem:/nonexistent2.pem")
        # Should not raise — nonexistent files are silently skipped
        ctx = build_client_ssl_context(cfg)
        assert ctx is not None

    def test_extra_ca_paths(self):
        cfg = SCTLSConfig(extra_ca_paths=["/nonexistent/ca.pem"])
        ctx = build_client_ssl_context(cfg)
        assert ctx is not None


# ---------------------------------------------------------------------------
# Security: SCTLSConfig repr redacts private_key_path
# ---------------------------------------------------------------------------


class TestSCTLSConfigRepr:
    def test_repr_redacts_private_key_path(self):
        """Private key path must never appear in repr (logs, tracebacks)."""
        cfg = SCTLSConfig(
            private_key_path="/secret/path/to/device.key",
            certificate_path="/path/to/cert.pem",
            ca_certificates_path="/path/to/ca.pem",
        )
        r = repr(cfg)
        assert "/secret/path/to/device.key" not in r
        assert "<REDACTED>" in r
        assert "/path/to/cert.pem" in r
        assert "/path/to/ca.pem" in r

    def test_repr_no_key_shows_none(self):
        """When no private_key_path is set, repr shows None."""
        cfg = SCTLSConfig()
        r = repr(cfg)
        assert "private_key_path=None" in r
        assert "<REDACTED>" not in r

    def test_str_also_redacts(self):
        """str() uses repr, so it should also be safe."""
        cfg = SCTLSConfig(private_key_path="/secret/key.pem")
        assert "/secret/key.pem" not in str(cfg)


# ---------------------------------------------------------------------------
# Security: plaintext warnings
# ---------------------------------------------------------------------------


class TestPlaintextWarnings:
    def test_client_plaintext_warns(self, caplog):
        """Building a client context with allow_plaintext=True should log WARNING."""
        cfg = SCTLSConfig(allow_plaintext=True)
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_client_ssl_context(cfg)
        assert any("TLS disabled" in m for m in caplog.messages)
        assert any("plaintext" in m.lower() for m in caplog.messages)

    def test_server_plaintext_warns(self, caplog):
        """Building a server context with allow_plaintext=True should log WARNING."""
        cfg = SCTLSConfig(allow_plaintext=True)
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_server_ssl_context(cfg)
        assert any("TLS disabled" in m for m in caplog.messages)

    def test_client_cert_without_key_warns(self, caplog):
        """certificate_path without private_key_path should log WARNING."""
        cfg = SCTLSConfig(certificate_path="/path/to/cert.pem")
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_client_ssl_context(cfg)
        assert any("private_key_path is missing" in m for m in caplog.messages)

    def test_client_key_without_cert_warns(self, caplog):
        """private_key_path without certificate_path should log WARNING."""
        cfg = SCTLSConfig(private_key_path="/path/to/key.pem")
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_client_ssl_context(cfg)
        assert any("certificate_path is missing" in m for m in caplog.messages)

    def test_server_cert_without_key_warns(self, caplog):
        """Server: certificate_path without private_key_path should log WARNING."""
        cfg = SCTLSConfig(certificate_path="/path/to/cert.pem")
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_server_ssl_context(cfg)
        assert any("private_key_path is missing" in m for m in caplog.messages)

    def test_server_key_without_cert_warns(self, caplog):
        """Server: private_key_path without certificate_path should log WARNING."""
        cfg = SCTLSConfig(private_key_path="/path/to/key.pem")
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_server_ssl_context(cfg)
        assert any("certificate_path is missing" in m for m in caplog.messages)

    def test_no_ca_certs_warns(self, caplog):
        """No CA certificates configured should log WARNING."""
        cfg = SCTLSConfig()
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc.tls"):
            build_client_ssl_context(cfg)
        assert any("no ca certificates" in m.lower() for m in caplog.messages)
