"""tests/test_s10_recipe.py — recipe fingerprints + dataset determinism (S10).

The hole this closes: the recorded command trained on data that depends on
generator.py and the segmenter, both of which move. A recipe without source
fingerprints can silently stop reproducing ("same seed, different val") while
looking perfectly deterministic. These tests pin the property.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _train(tmp_path, seed=11, per_class=3):
    out = Path(tmp_path) / f"m{seed}.npz"
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "train_glyphs.py"),
         "--per-class", str(per_class), "--epochs", "1", "--seed", str(seed),
         "--generator-sheets", "2", "--no-cache", "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(out.with_suffix(".json").read_text())


def test_recipe_records_fingerprints(tmp_path):
    rec = _train(tmp_path)
    assert len(rec["data_sha256"]) == 16
    assert "generator.py" in rec["source_files"]
    assert "readers/segmentation.py" in rec["source_files"]
    # generator.py exists in this repo, so its fingerprint must be real
    assert rec["source_files"]["generator.py"] is not None


def test_dataset_reproducible_for_same_seed(tmp_path):
    a = _train(tmp_path, seed=11)
    b = _train(tmp_path, seed=11)
    assert a["data_sha256"] == b["data_sha256"]


def test_dataset_hash_moves_with_seed(tmp_path):
    a = _train(tmp_path, seed=11)
    c = _train(tmp_path, seed=12)
    assert a["data_sha256"] != c["data_sha256"]
