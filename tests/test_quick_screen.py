#!/usr/bin/env python3
"""Tests for tools/quick_screen.py (t-20261014-5830, S74).

Covers: the banner is loud and unmissable; canonical seeds are refused;
determinism (same command -> same rows); table correctness on fixtures;
the lex route equals floor + fix_line; unknown families/reader rejected.
Fast: uses tiny counts and a stub-free run against the real generator
(3 families x 2 items).
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "quick_screen.py"


def run(*argv, expect_rc=0):
    p = subprocess.run([sys.executable, str(TOOL), *argv],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == expect_rc, (
        f"rc={p.returncode} (expected {expect_rc})\n"
        f"stdout:\n{p.stdout[-2000:]}\nstderr:\n{p.stderr[-2000:]}")
    return p


def test_banner_is_loud():
    out = run("--seed", "901", "--count", "1", "--families", "easy",
              "--quiet").stdout
    assert "SCREEN, not proof" in out
    assert out.count("SCREEN, not proof") >= 2      # header + footer
    assert "headline number" in out


def test_canonical_seeds_refused():
    for seed in ("1", "2", "3", "4", "53"):
        p = run("--seed", seed, "--count", "1", "--families", "easy",
                expect_rc=2)
        assert "evaluation-only" in p.stderr


def test_determinism_and_json():
    a = run("--seed", "905", "--count", "2", "--families",
            "corrosion,strippy,easy", "--quiet", "--out",
            "/tmp/qs_a.json").stdout
    b = run("--seed", "905", "--count", "2", "--families",
            "corrosion,strippy,easy", "--quiet", "--out",
            "/tmp/qs_b.json").stdout
    def table(stdout):
        return [l for l in stdout.splitlines()
                if l.startswith("  ") and "SCREEN" not in l]
    assert table(a) == table(b), "printed tables must be identical"
    da, db = json.loads(Path("/tmp/qs_a.json").read_text()), \
        json.loads(Path("/tmp/qs_b.json").read_text())
    assert da["rows"] == db["rows"], "rows must be deterministic"
    assert da["banner"].startswith("SCREEN, not proof")
    assert da["reader"] == "plain" and da["seed"] == 905


def test_table_matches_rows():
    run("--seed", "906", "--count", "3", "--families", "snow,split",
        "--quiet", "--out", "/tmp/qs_t.json")
    d = json.loads(Path("/tmp/qs_t.json").read_text())
    per_fam = {}
    for r in d["rows"]:
        per_fam.setdefault(r["family"], []).append(r["exact"])
    assert d["screen_total"][1] == len(d["rows"]) == 6
    assert sum(per_fam["snow"]) + sum(per_fam["split"]) == \
        d["screen_total"][0]
    # per-family printed table rows agree with the JSON
    out = run("--seed", "906", "--count", "3", "--families", "snow,split",
              "--quiet").stdout
    for fam, hits in per_fam.items():
        line = f"  {fam:14s} {sum(hits):3d}/3  "
        assert any(l.startswith(f"  {fam:14s}") and
                   f"{sum(hits):3d}/3" in l for l in out.splitlines()), fam


def test_lex_route_is_floor_plus_fixline():
    run("--seed", "907", "--count", "2", "--families", "easy", "--quiet",
        "--out", "/tmp/qs_lex.json", "--reader", "lex")
    d = json.loads(Path("/tmp/qs_lex.json").read_text())
    assert d["reader"] == "lex"
    sys.path.insert(0, str(ROOT / "tools"))
    from lex_projection import fix_line
    for r in d["rows"][:2]:
        # lex output must be a fix_line of SOME floor output; regenerate
        # the floor read directly and compare end-to-end.
        import generator as G
        import baseline as B
        img, label = G.generate_one(r["family"], seed=r["seed"],
                                    index=r["index"])
        raw, _ = B.read_text(img, None)
        assert r["got"] == fix_line(raw), (r["id"], r["got"], fix_line(raw))
        assert r["label"] == label


def test_bad_inputs_rejected():
    run("--families", "nope", expect_rc=2)
    run("--reader", "typer", expect_rc=2)
    run("--count", "0", expect_rc=2)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all quick_screen tests passed")
