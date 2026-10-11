#!/usr/bin/env python3
"""Integrity of the reference pack (t-20261011-4e49). One command, offline:

    python3 tests/test_reference_pack.py
    python3 -m unittest tests.test_reference_pack -v
    python3 -m pytest tests/test_reference_pack.py

Enforces the pact between tiles/ and labels.json:
  - every labels.json entry points at an existing tile file (and vice versa,
    no orphan tiles), no duplicates
  - every scored tile has a non-trivial exact-case label; every '?' tile is
    marked scored=false
  - labels are plausible captcha strings (A-Za-z0-9, 3-12 chars)
  - meta counts agree with the tile list
  - the sha256 manifest is fresh
  - the crop spec regenerates byte-identical tiles
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(ROOT, "reference")
TILES = os.path.join(REF, "tiles")


class ReferencePackTest(unittest.TestCase):
    """Integrity of Carlo's tiled, labeled sheets."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REF, "labels.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        cls.tiles = doc["tiles"]
        cls.meta = doc["meta"]
        cls.on_disk = set()
        for dirpath, _, names in os.walk(TILES):
            for n in names:
                if n.endswith(".png"):
                    cls.on_disk.add(os.path.relpath(os.path.join(dirpath, n), REF))
        cls.wanted = set(t["file"] for t in cls.tiles)

    def test_ids_are_unique(self):
        ids = [t["id"] for t in self.tiles]
        self.assertEqual(len(ids), len(set(ids)))

    def test_label_rules(self):
        label_rx = re.compile(r"^[A-Za-z0-9]{3,12}$")
        for t in self.tiles:
            if t.get("scored"):
                self.assertRegex(str(t.get("label", "")), label_rx, t["id"])
            else:
                self.assertEqual(t.get("label"), "?", t["id"])
            for key in ("file", "sheet", "family", "note"):
                self.assertIn(key, t, t["id"])

    def test_every_entry_has_a_file(self):
        for t in self.tiles:
            self.assertTrue(
                os.path.exists(os.path.join(REF, t["file"])), t["file"])

    def test_no_orphans_no_missing(self):
        self.assertEqual(self.on_disk, self.wanted,
                         f"extra: {sorted(self.on_disk - self.wanted)[:3]} "
                         f"missing: {sorted(self.wanted - self.on_disk)[:3]}")

    def test_meta_counts_are_honest(self):
        n_scored = sum(1 for t in self.tiles if t.get("scored"))
        n_unknown = sum(1 for t in self.tiles if not t.get("scored"))
        self.assertEqual(self.meta["tiles"], len(self.tiles))
        self.assertEqual(self.meta["labeled"], n_scored)
        self.assertEqual(self.meta["unknown"], n_unknown)

    def test_manifest_is_fresh(self):
        with open(os.path.join(TILES, "manifest.sha256.json")) as fh:
            manifest = json.load(fh)
        for rel in sorted(self.wanted):
            actual = hashlib.sha256(
                open(os.path.join(REF, rel), "rb").read()).hexdigest()
            self.assertEqual(manifest.get(rel.replace(os.sep, "/")), actual, rel)

    def test_tiles_regenerate_byte_identically(self):
        p = subprocess.run([sys.executable,
                            os.path.join(ROOT, "tools", "tile_reference.py"),
                            "--check"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, (p.stdout + p.stderr)[-300:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
