"""Tests for scripts/ — syntax, imports, and helpers."""

import ast
import importlib
import struct
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

ALL_SCRIPTS = sorted(p.stem for p in SCRIPTS_DIR.glob("*.py"))


def _import_script(name: str):
    """Import a script module by name from the scripts directory."""
    scripts_str = str(SCRIPTS_DIR)
    sys.path.insert(0, scripts_str)
    try:
        if name in sys.modules:
            return importlib.reload(sys.modules[name])
        return importlib.import_module(name)
    finally:
        sys.path.remove(scripts_str)


class TestScriptSyntax:
    """Verify every script has valid Python syntax."""

    @pytest.mark.parametrize("name", ALL_SCRIPTS)
    def test_syntax(self, name: str) -> None:
        source = (SCRIPTS_DIR / f"{name}.py").read_text()
        ast.parse(source, filename=f"{name}.py")

    @pytest.mark.parametrize("name", ALL_SCRIPTS)
    def test_has_module_docstring(self, name: str) -> None:
        source = (SCRIPTS_DIR / f"{name}.py").read_text()
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        assert docstring, f"{name}.py is missing a module docstring"


class TestBenchSCHelpers:
    """Test pure helper functions from bench_sc.py without networking."""

    def _import_bench_sc(self):
        return _import_script("bench_sc")

    def test_stats_initial(self) -> None:
        mod = self._import_bench_sc()
        stats = mod.Stats()
        assert stats.total_ok == 0
        assert stats.messages_sent == 0
        assert stats.errors == 0

    def test_stats_snapshot(self) -> None:
        mod = self._import_bench_sc()
        stats = mod.Stats()
        stats.unicast_latencies.append(1.0)
        stats.broadcast_latencies.append(2.0)
        stats.messages_sent = 5
        stats.messages_received = 3
        stats.bytes_sent = 100
        stats.bytes_received = 50
        stats.errors = 1

        snap = stats.snapshot()
        assert snap == (1, 1, 5, 3, 100, 50, 1)
        assert stats.total_ok == 2

    def test_make_payload(self) -> None:
        mod = self._import_bench_sc()
        payload = mod._make_payload(worker_id=1, seq=42)
        assert isinstance(payload, bytes)
        assert len(payload) >= 6  # At least the tag
        # Tag should contain worker_id and seq
        worker_id, seq = struct.unpack(">HI", payload[:6])
        assert worker_id == 1
        assert seq == 42

    def test_make_payload_sizes_in_distribution(self) -> None:
        mod = self._import_bench_sc()
        sizes = set()
        for _ in range(200):
            payload = mod._make_payload(worker_id=0, seq=0)
            sizes.add(len(payload))
        # Should hit at least 3 of the 4 payload sizes
        expected = {25, 200, 800, 1400}
        assert len(sizes & expected) >= 3

    def test_percentile_empty(self) -> None:
        mod = self._import_bench_sc()
        assert mod._percentile([], 0.5) == 0.0

    def test_percentile_values(self) -> None:
        mod = self._import_bench_sc()
        data = list(range(100))
        assert mod._percentile(data, 0.50) == 50
        assert mod._percentile(data, 0.95) == 95
        assert mod._percentile(data, 0.99) == 99

    def test_latency_summary_empty(self) -> None:
        mod = self._import_bench_sc()
        assert mod._latency_summary([]) == "n/a"

    def test_latency_summary_values(self) -> None:
        mod = self._import_bench_sc()
        result = mod._latency_summary([1.0, 2.0, 3.0])
        assert "p50=" in result
        assert "p95=" in result
        assert "mean=" in result

    def test_latency_dict_empty(self) -> None:
        mod = self._import_bench_sc()
        d = mod._latency_dict([])
        assert d == {"mean": 0, "p50": 0, "p95": 0, "p99": 0}

    def test_latency_dict_values(self) -> None:
        mod = self._import_bench_sc()
        d = mod._latency_dict([1.0, 2.0, 3.0, 4.0, 5.0])
        assert d["mean"] == 3.0
        assert d["p50"] == 3.0
        assert "p95" in d
        assert "p99" in d

    def test_parse_args_defaults(self) -> None:
        mod = self._import_bench_sc()
        old_argv = sys.argv
        sys.argv = ["bench_sc.py"]
        try:
            args = mod._parse_args()
            assert args.unicast == 8
            assert args.broadcast == 2
            assert args.warmup == 5
            assert args.sustain == 30
            assert args.port == 0
            assert args.json is False
        finally:
            sys.argv = old_argv

    def test_parse_args_custom(self) -> None:
        mod = self._import_bench_sc()
        old_argv = sys.argv
        sys.argv = [
            "bench_sc.py",
            "--unicast",
            "16",
            "--broadcast",
            "4",
            "--sustain",
            "60",
            "--warmup",
            "10",
            "--json",
        ]
        try:
            args = mod._parse_args()
            assert args.unicast == 16
            assert args.broadcast == 4
            assert args.sustain == 60
            assert args.warmup == 10
            assert args.json is True
        finally:
            sys.argv = old_argv


class TestBenchBIPHelpers:
    """Test pure helper functions from bench_bip.py without networking."""

    def _import_bench_bip(self):
        return _import_script("bench_bip")

    def test_stats_initial(self) -> None:
        mod = self._import_bench_bip()
        stats = mod.Stats()
        assert stats.total_ok == 0
        assert stats.errors == 0
        assert stats.cov_notifications == 0

    def test_stats_snapshot(self) -> None:
        mod = self._import_bench_bip()
        stats = mod.Stats()
        stats.read_latencies.append(1.0)
        stats.write_latencies.append(2.0)
        stats.rpm_latencies.append(3.0)
        stats.wpm_latencies.append(4.0)
        stats.objlist_latencies.append(5.0)
        stats.cov_latencies.append(6.0)
        stats.cov_notifications = 10
        stats.errors = 2

        snap = stats.snapshot()
        assert snap == (1, 1, 1, 1, 1, 1, 10, 2)
        assert stats.total_ok == 6

    def test_stats_combined_latencies(self) -> None:
        mod = self._import_bench_bip()
        stats = mod.Stats()
        stats.read_latencies.append(1.0)
        stats.write_latencies.append(2.0)
        combined = stats.combined_latencies()
        assert 1.0 in combined
        assert 2.0 in combined

    def test_object_pool_counts(self) -> None:
        mod = self._import_bench_bip()
        assert len(mod.READABLE_OBJECTS) == 18  # 10 AI + 5 BI + 3 MSI
        assert len(mod.WRITABLE_OBJECTS) == 5  # 5 AV
        assert len(mod.RPM_SPECS) == 5
        assert len(mod.WPM_SPECS) == 3

    def test_percentile_empty(self) -> None:
        mod = self._import_bench_bip()
        assert mod._percentile([], 0.5) == 0.0

    def test_percentile_values(self) -> None:
        mod = self._import_bench_bip()
        data = list(range(100))
        assert mod._percentile(data, 0.50) == 50
        assert mod._percentile(data, 0.95) == 95

    def test_latency_summary_empty(self) -> None:
        mod = self._import_bench_bip()
        assert mod._latency_summary([]) == "n/a"

    def test_latency_dict_empty(self) -> None:
        mod = self._import_bench_bip()
        d = mod._latency_dict([])
        assert d == {"mean": 0, "p50": 0, "p95": 0, "p99": 0}

    def test_latency_dict_values(self) -> None:
        mod = self._import_bench_bip()
        d = mod._latency_dict([1.0, 2.0, 3.0, 4.0, 5.0])
        assert d["mean"] == 3.0
        assert d["p50"] == 3.0

    def test_parse_args_defaults(self) -> None:
        mod = self._import_bench_bip()
        old_argv = sys.argv
        sys.argv = ["bench_bip.py"]
        try:
            args = mod._parse_args()
            assert args.pools == 1
            assert args.readers == 2
            assert args.writers == 1
            assert args.rpm == 1
            assert args.wpm == 1
            assert args.objlist == 1
            assert args.cov == 1
            assert args.warmup == 5
            assert args.sustain == 30
            assert args.port == 0
            assert args.json is False
        finally:
            sys.argv = old_argv

    def test_parse_args_custom(self) -> None:
        mod = self._import_bench_bip()
        old_argv = sys.argv
        sys.argv = [
            "bench_bip.py",
            "--pools",
            "2",
            "--readers",
            "4",
            "--writers",
            "2",
            "--sustain",
            "60",
            "--json",
        ]
        try:
            args = mod._parse_args()
            assert args.pools == 2
            assert args.readers == 4
            assert args.writers == 2
            assert args.sustain == 60
            assert args.json is True
        finally:
            sys.argv = old_argv

    def test_create_stress_objects(self) -> None:
        mod = self._import_bench_bip()
        from unittest.mock import MagicMock

        from bac_py.app.application import BACnetApplication, DeviceConfig

        app = MagicMock(spec=BACnetApplication)
        app._config = DeviceConfig(instance_number=400, name="Test")
        app.object_db = MagicMock()
        added_objects: list = []
        app.object_db.add = lambda obj: added_objects.append(obj)
        app.object_db.__iter__ = lambda self: iter(added_objects)

        mod._create_stress_objects(app)
        assert len(added_objects) == 40  # 39 objects + 1 device


class TestBenchRouterHelpers:
    """Test pure helper functions from bench_router.py without networking."""

    def _import_bench_router(self):
        return _import_script("bench_router")

    def test_stats_initial(self) -> None:
        mod = self._import_bench_router()
        stats = mod.Stats()
        assert stats.total_ok == 0
        assert stats.errors == 0
        assert stats.route_discoveries == 0

    def test_stats_snapshot(self) -> None:
        mod = self._import_bench_router()
        stats = mod.Stats()
        stats.read_latencies.append(1.0)
        stats.write_latencies.append(2.0)
        stats.route_check_latencies.append(3.0)
        stats.route_discoveries = 5
        stats.errors = 1

        snap = stats.snapshot()
        assert snap == (1, 1, 0, 0, 0, 1, 5, 1)
        assert stats.total_ok == 3

    def test_object_pool_counts(self) -> None:
        mod = self._import_bench_router()
        assert len(mod.READABLE_OBJECTS) == 18
        assert len(mod.WRITABLE_OBJECTS) == 5

    def test_percentile_empty(self) -> None:
        mod = self._import_bench_router()
        assert mod._percentile([], 0.5) == 0.0

    def test_latency_dict_empty(self) -> None:
        mod = self._import_bench_router()
        d = mod._latency_dict([])
        assert d == {"mean": 0, "p50": 0, "p95": 0, "p99": 0}

    def test_parse_args_defaults(self) -> None:
        mod = self._import_bench_router()
        old_argv = sys.argv
        sys.argv = ["bench_router.py"]
        try:
            args = mod._parse_args()
            assert args.pools == 1
            assert args.readers == 2
            assert args.writers == 1
            assert args.rpm == 1
            assert args.wpm == 1
            assert args.objlist == 1
            assert args.warmup == 5
            assert args.sustain == 30
            assert args.json is False
        finally:
            sys.argv = old_argv

    def test_parse_args_custom(self) -> None:
        mod = self._import_bench_router()
        old_argv = sys.argv
        sys.argv = ["bench_router.py", "--pools", "3", "--sustain", "60", "--json"]
        try:
            args = mod._parse_args()
            assert args.pools == 3
            assert args.sustain == 60
            assert args.json is True
        finally:
            sys.argv = old_argv

    def test_create_stress_objects(self) -> None:
        mod = self._import_bench_router()
        from unittest.mock import MagicMock

        from bac_py.app.application import BACnetApplication, DeviceConfig

        app = MagicMock(spec=BACnetApplication)
        app._config = DeviceConfig(instance_number=501, name="Test")
        app.object_db = MagicMock()
        added_objects: list = []
        app.object_db.add = lambda obj: added_objects.append(obj)
        app.object_db.__iter__ = lambda self: iter(added_objects)

        mod._create_stress_objects(app, "Test-Server")
        assert len(added_objects) == 40


class TestBenchBBMDHelpers:
    """Test pure helper functions from bench_bbmd.py without networking."""

    def _import_bench_bbmd(self):
        return _import_script("bench_bbmd")

    def test_stats_initial(self) -> None:
        mod = self._import_bench_bbmd()
        stats = mod.Stats()
        assert stats.total_ok == 0
        assert stats.errors == 0
        assert stats.fdt_reads == 0
        assert stats.bdt_reads == 0

    def test_stats_snapshot(self) -> None:
        mod = self._import_bench_bbmd()
        stats = mod.Stats()
        stats.read_latencies.append(1.0)
        stats.fdt_latencies.append(2.0)
        stats.fdt_reads = 3
        stats.bdt_latencies.append(3.0)
        stats.bdt_reads = 4
        stats.errors = 1

        snap = stats.snapshot()
        assert snap == (1, 0, 0, 0, 0, 3, 4, 1)
        assert stats.total_ok == 3

    def test_object_pool_counts(self) -> None:
        mod = self._import_bench_bbmd()
        assert len(mod.READABLE_OBJECTS) == 18
        assert len(mod.WRITABLE_OBJECTS) == 5

    def test_percentile_empty(self) -> None:
        mod = self._import_bench_bbmd()
        assert mod._percentile([], 0.5) == 0.0

    def test_latency_dict_empty(self) -> None:
        mod = self._import_bench_bbmd()
        d = mod._latency_dict([])
        assert d == {"mean": 0, "p50": 0, "p95": 0, "p99": 0}

    def test_parse_args_defaults(self) -> None:
        mod = self._import_bench_bbmd()
        old_argv = sys.argv
        sys.argv = ["bench_bbmd.py"]
        try:
            args = mod._parse_args()
            assert args.pools == 1
            assert args.readers == 2
            assert args.writers == 1
            assert args.rpm == 1
            assert args.wpm == 1
            assert args.objlist == 1
            assert args.fdt_workers == 1
            assert args.bdt_workers == 1
            assert args.warmup == 5
            assert args.sustain == 30
            assert args.port == 0
            assert args.json is False
        finally:
            sys.argv = old_argv

    def test_parse_args_custom(self) -> None:
        mod = self._import_bench_bbmd()
        old_argv = sys.argv
        sys.argv = [
            "bench_bbmd.py",
            "--pools",
            "2",
            "--fdt-workers",
            "3",
            "--bdt-workers",
            "2",
            "--sustain",
            "60",
            "--json",
        ]
        try:
            args = mod._parse_args()
            assert args.pools == 2
            assert args.fdt_workers == 3
            assert args.bdt_workers == 2
            assert args.sustain == 60
            assert args.json is True
        finally:
            sys.argv = old_argv

    def test_create_stress_objects(self) -> None:
        mod = self._import_bench_bbmd()
        from unittest.mock import MagicMock

        from bac_py.app.application import BACnetApplication, DeviceConfig

        app = MagicMock(spec=BACnetApplication)
        app._config = DeviceConfig(instance_number=551, name="Test")
        app.object_db = MagicMock()
        added_objects: list = []
        app.object_db.add = lambda obj: added_objects.append(obj)
        app.object_db.__iter__ = lambda self: iter(added_objects)

        mod._create_stress_objects(app)
        assert len(added_objects) == 40


class TestScriptCompleteness:
    """Ensure we test all scripts in the directory."""

    def test_all_scripts_listed(self) -> None:
        actual = sorted(p.stem for p in SCRIPTS_DIR.glob("*.py"))
        assert actual == ALL_SCRIPTS

    def test_script_count(self) -> None:
        assert len(ALL_SCRIPTS) >= 4, f"Expected at least 4 scripts, found {len(ALL_SCRIPTS)}"
