"""Tests for example scripts.

Verifies that all example scripts in the examples/ directory have valid syntax,
can be imported without errors, and that testable helper functions work correctly.
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# All example scripts (keep in sync with examples/ directory)
ALL_EXAMPLES = sorted(p.stem for p in EXAMPLES_DIR.glob("*.py"))

# SC examples require websockets + cryptography (optional deps)
SC_EXAMPLES = {
    "secure_connect",
    "secure_connect_hub",
    "ip_to_sc_router",
    "sc_generate_certs",
    "sc_server",
}


class TestExampleSyntax:
    """Verify every example script has valid Python syntax."""

    @pytest.mark.parametrize("name", ALL_EXAMPLES)
    def test_syntax(self, name: str) -> None:
        source = (EXAMPLES_DIR / f"{name}.py").read_text()
        ast.parse(source, filename=f"{name}.py")

    @pytest.mark.parametrize("name", ALL_EXAMPLES)
    def test_has_module_docstring(self, name: str) -> None:
        source = (EXAMPLES_DIR / f"{name}.py").read_text()
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        assert docstring, f"{name}.py is missing a module docstring"

    @pytest.mark.parametrize("name", ALL_EXAMPLES)
    def test_has_main_guard(self, name: str) -> None:
        source = (EXAMPLES_DIR / f"{name}.py").read_text()
        assert 'if __name__ == "__main__"' in source, (
            f'{name}.py is missing \'if __name__ == "__main__" guard'
        )

    @pytest.mark.parametrize("name", ALL_EXAMPLES)
    def test_has_async_main(self, name: str) -> None:
        source = (EXAMPLES_DIR / f"{name}.py").read_text()
        tree = ast.parse(source)
        has_main = any(
            isinstance(node, ast.AsyncFunctionDef) and node.name == "main"
            for node in ast.walk(tree)
        )
        assert has_main, f"{name}.py is missing 'async def main()'"


class TestExampleImports:
    """Verify every example can be imported (dependencies resolve)."""

    @pytest.fixture(autouse=True)
    def _add_examples_to_path(self):
        """Temporarily add examples/ to sys.path for importlib."""
        examples_str = str(EXAMPLES_DIR)
        sys.path.insert(0, examples_str)
        yield
        sys.path.remove(examples_str)

    @pytest.mark.parametrize(
        "name",
        [n for n in ALL_EXAMPLES if n not in SC_EXAMPLES],
    )
    def test_import_core_example(self, name: str) -> None:
        mod = importlib.import_module(name)
        assert hasattr(mod, "main"), f"{name} module has no main() function"
        # Clean up to avoid cross-test pollution
        del sys.modules[name]

    @pytest.mark.parametrize("name", sorted(SC_EXAMPLES))
    def test_import_sc_example(self, name: str) -> None:
        pytest.importorskip("websockets")
        pytest.importorskip("cryptography")
        mod = importlib.import_module(name)
        assert hasattr(mod, "main"), f"{name} module has no main() function"
        del sys.modules[name]


class TestExampleHelpers:
    """Test helper functions from examples that can run without a network."""

    def test_secure_connect_hub_create_object_database(self) -> None:
        pytest.importorskip("websockets")
        examples_str = str(EXAMPLES_DIR)
        sys.path.insert(0, examples_str)
        try:
            from bac_py.types.enums import ObjectType, PropertyIdentifier
            from bac_py.types.primitives import ObjectIdentifier

            mod = importlib.import_module("secure_connect_hub")
            db = mod.create_object_database()

            # Should have a device object and two analog inputs
            objects = list(db)
            assert len(objects) == 3

            # Device object should be instance 1000
            device = db.get(ObjectIdentifier(ObjectType.DEVICE, 1000))
            assert device is not None
            name = device.read_property(PropertyIdentifier.OBJECT_NAME)
            assert name == "SC-Hub-Device"

            # Analog inputs should have present values set
            ai1 = db.get(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
            assert ai1 is not None
            pv = ai1.read_property(PropertyIdentifier.PRESENT_VALUE)
            assert pv == 72.5

            del sys.modules["secure_connect_hub"]
        finally:
            sys.path.remove(examples_str)

    def test_sc_generate_certs_pki(self, tmp_path: Path) -> None:
        pytest.importorskip("websockets")
        pytest.importorskip("cryptography")
        examples_str = str(EXAMPLES_DIR)
        sys.path.insert(0, examples_str)
        try:
            mod = importlib.import_module("sc_generate_certs")

            cert_dir = tmp_path / "test_certs"
            mod.generate_test_pki(cert_dir)

            # Should create 8 PEM files
            expected_files = [
                "ca.key",
                "ca.crt",
                "hub.key",
                "hub.crt",
                "node1.key",
                "node1.crt",
                "node2.key",
                "node2.crt",
            ]
            for filename in expected_files:
                path = cert_dir / filename
                assert path.exists(), f"Missing {filename}"
                content = path.read_text()
                if filename.endswith(".key"):
                    assert "BEGIN PRIVATE KEY" in content
                else:
                    assert "BEGIN CERTIFICATE" in content

            del sys.modules["sc_generate_certs"]
        finally:
            sys.path.remove(examples_str)

    def test_sc_generate_certs_pki_overwrites(self, tmp_path: Path) -> None:
        """Calling generate_test_pki twice overwrites existing certs."""
        pytest.importorskip("websockets")
        pytest.importorskip("cryptography")
        examples_str = str(EXAMPLES_DIR)
        sys.path.insert(0, examples_str)
        try:
            mod = importlib.import_module("sc_generate_certs")

            cert_dir = tmp_path / "test_certs"
            mod.generate_test_pki(cert_dir)
            first_ca = (cert_dir / "ca.crt").read_text()

            mod.generate_test_pki(cert_dir)
            second_ca = (cert_dir / "ca.crt").read_text()

            # New key material each time
            assert first_ca != second_ca

            del sys.modules["sc_generate_certs"]
        finally:
            sys.path.remove(examples_str)


class TestExampleCompleteness:
    """Ensure the test covers all example scripts in the directory."""

    def test_all_examples_are_listed(self) -> None:
        actual = sorted(p.stem for p in EXAMPLES_DIR.glob("*.py"))
        assert actual == ALL_EXAMPLES, (
            f"Example list is out of date. "
            f"Missing: {set(actual) - set(ALL_EXAMPLES)}, "
            f"Extra: {set(ALL_EXAMPLES) - set(actual)}"
        )

    def test_example_count(self) -> None:
        assert len(ALL_EXAMPLES) >= 25, f"Expected at least 25 examples, found {len(ALL_EXAMPLES)}"
