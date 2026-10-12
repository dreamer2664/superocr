"""Smoke tests for the S6 measurement tools (t-20261011-00c0).

These assert the tools RUN, report the promised schema and stay
deterministic — never that a score equals a specific number (suites are
generated, tiny counts, and the point of the tools is to move).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(tool, *args, timeout=600):
    p = subprocess.run([sys.executable, str(ROOT / "tools" / tool), *args],
                       capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    return p


class TestEnsembleSelect(unittest.TestCase):
    def test_schema_and_determinism(self):
        with tempfile.TemporaryDirectory() as td:
            out1, out2 = Path(td) / "a.json", Path(td) / "b.json"
            args = ["--count", "2", "--seed", "5", "--families", "snow,stitch"]
            r1 = _run("ensemble_select.py", *args, "--out", str(out1))
            self.assertEqual(r1.returncode, 0, r1.stderr[-400:])
            rep = json.loads(out1.read_text())
            self.assertEqual(rep["seed"], 5)
            self.assertIn("best_of_combined", rep)
            self.assertEqual(len(rep["per_family"]), 2)
            for row in rep["per_family"]:
                self.assertIn(row["winner"], row["chains"])
                for vals in row["chains"].values():
                    self.assertGreaterEqual(vals["exact"], 0.0)
                    self.assertLessEqual(vals["exact"], 1.0)


class TestAugmentSearch(unittest.TestCase):
    def test_identity_is_baseline_and_schema(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "a.json"
            r = _run("augment_search.py", "--count", "2", "--seed", "5",
                     "--families", "snow", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            rep = json.loads(out.read_text())
            self.assertEqual(rep["floor_exact"], rep["per_family"][0]
                             ["augmentations"]["identity"]["exact"])
            self.assertIn("augmentations", rep)
            self.assertIn(rep["per_family"][0]["winner"], rep["augmentations"])


class TestSelftrainCnn(unittest.TestCase):
    def test_audit_honest_and_no_regression_schema(self):
        if not (ROOT / "models" / "glyphcnn.npz").exists():
            self.skipTest("no committed CNN weights in this tree")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "a.json"
            r = _run("selftrain_cnn.py", "--per-family", "2", "--eval-count", "2",
                     "--families", "snow", "--epochs", "1", "--seed-eval", "5",
                     "--seed-train", "71", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            rep = json.loads(out.read_text())
            self.assertLessEqual(rep["pseudo"]["audit_correct"],
                                 rep["pseudo"]["kept"])
            self.assertEqual(set(rep["exact_before"]), set(rep["exact_after"]))
            self.assertIn("easy", rep["exact_before"])  # regression sentinel
            self.assertIn("delta_points", rep)


if __name__ == "__main__":
    unittest.main()
