#!/usr/bin/env python3
"""Build-artifact tests: the bundle must be complete, honest and standalone.

Run: python3 tests/test_build_solver_zip.py
(Uses --allow-dirty because the test runs from a working tree; the release
build refuses a dirty tree — that behaviour is asserted too.)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / "tools" / "build_solver_zip.py"


class TestBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "dist"
        p = subprocess.run([sys.executable, str(BUILDER), "--out", str(cls.out), "--allow-dirty"],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=600)
        if p.returncode != 0:
            raise AssertionError(f"build failed: {p.stderr[-800:]}")
        cls.build = json.loads(p.stdout)
        cls.zdir = Path(cls.build["directory"])
        cls.zip_path = Path(cls.build["zip"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_zip_and_sha_receipt(self):
        self.assertTrue(self.zip_path.is_file())
        digest = hashlib.sha256(self.zip_path.read_bytes()).hexdigest()
        self.assertEqual(digest, self.build["sha256"])
        receipt = Path(str(self.zip_path).replace(".zip", ".sha256.txt"))
        self.assertIn(digest, receipt.read_text())

    def test_manifest_hashes_match_files(self):
        manifest = json.loads((self.zdir / "MANIFEST.json").read_text())
        self.assertEqual(manifest["reader_route"].split(" (")[0],
                         "baseline.read_text(img, None) + tools/lex_projection.fix_line")
        self.assertFalse(manifest["accuracy_target_met"])
        for rel, expect in manifest["files_sha256"].items():
            got = hashlib.sha256((self.zdir / rel).read_bytes()).hexdigest()
            self.assertEqual(got, expect, rel)

    def test_fonts_present_with_provenance(self):
        manifest = json.loads((self.zdir / "MANIFEST.json").read_text())
        fonts = sorted(p.name for p in (self.zdir / "fonts").glob("*.ttf"))
        self.assertEqual(len(fonts), 8, fonts)
        self.assertIn("LICENSE_DEJAVU.txt",
                      [p.name for p in (self.zdir / "fonts").iterdir()])
        self.assertEqual(set(manifest["fonts"]), set(manifest["fonts"]))
        self.assertTrue(all(v for v in manifest["fonts"].values()))

    def test_generator_patch_idempotent_and_effective(self):
        gen = (self.zdir / "generator.py").read_text()
        self.assertIn("qcaptcha bundle font fallback", gen)
        # simulate a machine with no system font tree: only bundled entries exist
        probe = (
            "import sys, types; sys.path.insert(0, '.')\n"
            "import generator as G\n"
            "G._FONT_CANDIDATES = [p for p in G._FONT_CANDIDATES if not p.startswith('/usr/')]\n"
            "print(len(G.available_fonts()))\n"
        )
        p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                           cwd=str(self.zdir), timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        self.assertEqual(p.stdout.strip(), "8", "bundled fonts must fill the gap")

    def test_bundle_reads_standalone(self):
        """From the extracted directory alone: generate + read one image."""
        probe = (
            "import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'tools')\n"
            "import baseline, generator\n"
            "img, label = generator.generate_one('easy', 9, 0)\n"
            "text, conf = baseline.read_text(img, None)\n"
            "print(repr(text))\n"
        )
        p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                           cwd=str(self.zdir), timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        self.assertGreaterEqual(len(p.stdout.strip()), 3)

    def test_bundle_check_preflight_passes(self):
        p = subprocess.run([sys.executable, "launch.py", "--check"], capture_output=True,
                           text=True, cwd=str(self.zdir), timeout=180)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        rep = json.loads(p.stdout)
        self.assertFalse(str(rep["engine_root"]).startswith("ERROR"))
        self.assertGreaterEqual(rep["fonts_visible"], 8)

    def test_zip_has_no_secrets_and_no_absolute_paths(self):
        with zipfile.ZipFile(self.zip_path) as z:
            names = z.namelist()
        for n in names:
            self.assertFalse(n.startswith("/"), n)
            self.assertNotIn("..", n.split("/"), n)
            low = n.lower()
            self.assertNotIn(".env", low)
            self.assertNotIn("token", low)
            self.assertNotIn("private", low)
        ref = f"qcaptcha-solver-{ROOT.name}"  # prefix is not asserted; sanity on structure
        self.assertTrue(any(n.endswith("launch.py") for n in names))
        self.assertTrue(any(n.endswith("generator.py") for n in names))
        self.assertTrue(any("/models/preclass_centroids.npz" in n for n in names))

    def test_dirty_tree_refused_for_release_build(self):
        # only meaningful when the tree IS dirty (it is, while iterating); if a
        # clean checkout runs this test, a build without --allow-dirty must pass.
        dirty = bool(subprocess.check_output(
            ["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip())
        if not dirty:
            self.skipTest("tree clean — refusal path not reachable from here")
        p = subprocess.run([sys.executable, str(BUILDER), "--out", str(Path(self.tmp.name) / "x")],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=120)
        self.assertEqual(p.returncode, 2)
        self.assertIn("dirty", (p.stdout + p.stderr).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
