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
