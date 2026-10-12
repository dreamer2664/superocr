"""Tests for the reproducibility-gate validator (t-20261012-eb76).

The validator is the reviewer side of the four stamps — these tests pin the
three verdicts (PASS/FAIL/UNSTAMPED), the re-hash check that killed S14's
0.707-vs-0.302 ambiguity, and the legal 'absent' value for optional libs.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_suites import dir_hash  # noqa: E402


def _run(*args, timeout=120):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate_report.py"), *args],
        capture_output=True, text=True, timeout=timeout, cwd=ROOT)


def _data_dir(td: str) -> Path:
    """A tiny deterministic 'suite root' to hash and re-hash."""
    root = Path(td) / "data"
    (root / "easy").mkdir(parents=True)
    (root / "easy" / "a.png").write_bytes(b"fake-png-bytes")
    (root / "easy" / "manifest.jsonl").write_text('{"id": "e1"}\n', encoding="utf-8")
    return root


def _stamped(dh: str) -> dict:
    return {
        "bench": "bench.py", "run_id": "test-run",
        "reader": {"command": "python3 baseline.py {image}", "name": "baseline.py"},
        "totals": {"correct": 28, "total": 100, "pct": 28.0},
        "stamps": {
            "dir_hash": dh,
            "reader_command": "python3 baseline.py {image}",
            "env": {"python": "3.11.0", "pillow": "10.0.0",
                    "numpy": "1.26.0", "cv2": "4.9.0"},
            "scorer": "author",
        },
    }


class TestVerdicts(unittest.TestCase):
    def test_pass_with_rehash(self):
        with tempfile.TemporaryDirectory() as td:
            data = _data_dir(td)
            report = _stamped(dir_hash(data))
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp), "--data", str(data))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)

    def test_fail_on_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            data = _data_dir(td)
            report = _stamped("0" * 64)  # tampered / quoted-from-elsewhere
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp), "--data", str(data))
            self.assertEqual(r.returncode, 1)
            self.assertIn("dir_hash", r.stdout)
            self.assertIn("re-hash", r.stdout)

    def test_unstamped_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            report = _stamped("x")  # then strip stamps below
            report.pop("stamps")
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp))
            self.assertEqual(r.returncode, 2)
            self.assertIn("UNSTAMPED", r.stdout)
            # --strict turns the legacy verdict into a FAIL
            r2 = _run(str(rp), "--strict")
            self.assertEqual(r2.returncode, 1)
            self.assertIn("FAIL", r2.stdout)

    def test_fail_on_bad_scorer(self):
        with tempfile.TemporaryDirectory() as td:
            report = _stamped("0" * 64)
            report["stamps"]["scorer"] = "yours-truly"
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp))
            self.assertEqual(r.returncode, 1)
            self.assertIn("scorer", r.stdout)

    def test_fail_on_scorer_expectation(self):
        with tempfile.TemporaryDirectory() as td:
            report = _stamped("0" * 64)
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp), "--expect-scorer", "both")
            self.assertEqual(r.returncode, 1)
            self.assertIn("expected", r.stdout)

    def test_absent_cv2_is_legal(self):
        with tempfile.TemporaryDirectory() as td:
            report = _stamped("0" * 64)
            report["stamps"]["env"]["cv2"] = "absent"
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fail_on_reader_command_drift(self):
        with tempfile.TemporaryDirectory() as td:
            report = _stamped("0" * 64)
            report["stamps"]["reader_command"] = "python3 reader.py {image}"
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp))
            self.assertEqual(r.returncode, 1)
            self.assertIn("disagrees", r.stdout)

    def test_json_output_shape(self):
        with tempfile.TemporaryDirectory() as td:
            report = _stamped("0" * 64)
            rp = Path(td) / "run.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            r = _run(str(rp), "--json")
            self.assertEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertEqual(out["verdict"], "PASS")
            self.assertEqual(out["stamps"]["scorer"], "author")


if __name__ == "__main__":
    unittest.main()
