#!/usr/bin/env python3
"""Offline, no-OCR tests for S38's receipt gate and independent-seed statistics."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import s38_compare as C


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.a = json.loads((ROOT / "reports/s25-piece-gap/receipt-final/20261013T081536Z-easy-hard.json").read_text())
        # Synthetic receipt only for unit tests, NEVER a benchmark artifact.
        self.b = copy.deepcopy(self.a)
        self.b["seed"] = 2
        self.b["stamps"]["dir_hash"] = C.HASHES[2]

    def reject(self, mutate):
        mutate(self.b)
        with self.assertRaises(ValueError):
            C.compare(self.a, self.b)

    def test_valid_and_zero_difference(self):
        result = C.compare(self.a, self.b)
        self.assertEqual(result["suites"]["hard"]["delta_percentage_points"], 0)
        self.assertEqual(result["suites"]["hard"]["fisher_two_sided_p"], 1)
        self.assertEqual(result["suites"]["easy"]["pooled_correct"], 146)

    def test_wrong_seed(self):
        self.reject(lambda r: r.update(seed=1))

    def test_wrong_hash(self):
        self.reject(lambda r: r["stamps"].update(dir_hash="0" * 64))

    def test_wrong_command(self):
        self.reject(lambda r: r["reader"].update(command="python3 baseline.py {image}"))

    def test_environment_mismatch(self):
        self.reject(lambda r: r["stamps"]["env"].update(pillow="different"))

    def test_missing_environment(self):
        self.reject(lambda r: r["stamps"]["env"].pop("numpy"))

    def test_invalid_scorer(self):
        self.reject(lambda r: r["stamps"].update(scorer="unknown"))

    def test_override(self):
        self.reject(lambda r: r.update(bar_overridden=True))

    def test_unfinished(self):
        self.reject(lambda r: r["coop"].update(finished=False))

    def test_missing_suite(self):
        self.reject(lambda r: r["suites"].pop("hard"))

    def test_missing_item(self):
        self.reject(lambda r: r["suites"]["hard"]["results"].pop())

    def test_duplicate(self):
        self.reject(lambda r: r["suites"]["hard"]["results"][1].update(id=r["suites"]["hard"]["results"][0]["id"]))

    def test_excluded(self):
        self.reject(lambda r: r["suites"]["hard"]["results"][0].update(excluded=True))

    def test_timeout(self):
        self.reject(lambda r: r["suites"]["hard"]["results"][0].update(error="timeout"))

    def test_bad_match(self):
        self.reject(lambda r: r["suites"]["hard"]["results"][0].update(match=True))

    def test_bad_total(self):
        self.reject(lambda r: r["suites"]["hard"].update(correct=24))

    def test_bad_bar_verdict(self):
        self.reject(lambda r: r["suites"]["hard"].update(passed=True))

    def test_bad_family_counts(self):
        self.reject(lambda r: r["suites"]["hard"]["families"]["snow"].update(correct=9))

    def test_signatures(self):
        self.assertEqual(C.signature({"got": "aB", "label": "aB"}), "exact")
        self.assertEqual(C.signature({"got": "Ab", "label": "aB"}), "case-only")
        self.assertEqual(C.signature({"got": "a", "label": "aB"}), "shorter-output")
        self.assertEqual(C.signature({"got": "aBB", "label": "aB"}), "longer-output")
        self.assertEqual(C.signature({"got": "aC", "label": "aB"}), "same-length-substitution")

    def test_fisher_known_table_and_symmetry(self):
        self.assertAlmostEqual(C.fisher_two_sided(1, 10, 11, 14), 0.0027594561852200836)
        self.assertEqual(C.fisher_two_sided(23, 100, 31, 100), C.fisher_two_sided(31, 100, 23, 100))

    def test_wilson_edges(self):
        lo, hi = C.wilson(0, 100)
        self.assertAlmostEqual(lo, 0, places=3)
        self.assertAlmostEqual(hi, 3.699, places=3)
        lo, hi = C.wilson(100, 100)
        self.assertAlmostEqual(lo, 96.301, places=3)
        self.assertAlmostEqual(hi, 100, places=3)


if __name__ == "__main__":
    unittest.main()
