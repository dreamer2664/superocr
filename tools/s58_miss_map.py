#!/usr/bin/env python3
"""S58 (t-20261014-d325): replay the S43 hard miss-map on the post-S55 reader.

Route censused: shipping `tools/reader_lex.py` = baseline.py floor +
`tools/lex_projection.fix_line` (R1-R5 + S25 + S55 band), canonical seed-1
hard suite, 100 items. S43's census (reports/s43_failure_analysis.md +
.json) mapped 77 misses on the settled 23/100 route; the post-S55 bench
(reports/s55-bench-seed1/, commit a530a8ffb059, dir_hash b2c460d2fb5a...)
settles at 25/100 hard exact, so the map must be rebuilt and every change
vs S43 listed.

Method: S43's, verbatim. Same decision tree, same proxy definitions, same
token-aware lex effect (copied from tools/s43_failure_census.py). The only
extension is live recovery of the per-item evidence S43 recomputed from
historical receipts:

  * floor   = baseline.read_text(image)          (in-process, models hot)
  * final   = fix_line(floor)                    (current lex_projection)
  * reader_words / glyph_pieces = the S25 route_pieces replication of the
    route's mask path (autocontrast -> otsu/S8 lean -> polarity guard ->
    despeck -> trim -> deskew -> R.segment), copied from
    tools/s25_piece_gap.py

Gates (any FAIL -> exit 1, the drift is the finding):

  G1  100 items; live manifest labels/families agree with the committed
      s55 bench receipt 100/100
  G2  live final == committed bench `got` 100/100 (route reproducibility)
  G3  final_exact == 25 and misses == 75 (the settled post-S55 numbers)
  G4  floor_exact == 12 (floor is image-side; S55 was text-side only)
  G5  no item exact at S43 is a miss now (S55 receipts record 0 breaks)

Usage:
  python3 tools/s58_miss_map.py                  # summary + gates
  python3 tools/s58_miss_map.py --table          # + per-item md tables
  python3 tools/s58_miss_map.py --json reports/census-s58/2026-10-14.json \
      --jsonl reports/census-s58/2026-10-14-reads.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import baseline as B  # noqa: E402
import reader as R  # noqa: E402
from lex_projection import fix_line  # noqa: E402

MANIFEST = ROOT / "data/hard/manifest.jsonl"
BENCH_RECEIPT = ROOT / "reports/s55-bench-seed1/20261013T211005Z-easy-hard.json"
S43_MAP = ROOT / "reports/s43_failure_analysis.json"

# settled expectations (see module docstring; drift here is the finding)
EXPECT_FLOOR_EXACT = 12
EXPECT_FINAL_EXACT = 25


# --- S25 route_pieces replication, copied verbatim from tools/s25_piece_gap.py
def route_pieces(img: Image.Image) -> tuple[int, list[int]]:
    """Replicate read_text's mask path; return (word count, glyphs per word)."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = B._family_mask(img, a, None)
    if mask is None:
        lv = B._otsu_level(a)
        mask = a < (lv * 0.85 if 128 <= lv <= 150 else lv)
        if mask.mean() > 0.5:
            mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    words = R.segment(mask)
    return len(words), [len(w) for w in words]


# --- S43 definitions, copied verbatim from tools/s43_failure_census.py
def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def collect() -> list[dict]:
    """Live per-item evidence on the current route; one row per hard item."""
    rows = []
    for line in MANIFEST.read_text().splitlines():
        m = json.loads(line)
        img = Image.open(ROOT / "data/hard" / m["image"])
        t0 = time.time()
        floor = B.read_text(img)[0]
        words, pieces = route_pieces(img)
        dt = time.time() - t0
        rows.append({
            "id": m["id"], "family": m["family"], "label": m["label"],
            "floor": floor, "final": fix_line(floor),
            "reader_words": words, "glyph_pieces": pieces,
            "seconds": round(dt, 3)})
    return rows


def classify(rows: list[dict]) -> tuple[list[dict], dict]:
    """S43 census decision tree, verbatim, over the collected rows."""
    misses, exact, floor_exact = [], 0, 0
    for r in rows:
        label, raw, final = r["label"], r["floor"], r["final"]
        floor_exact += raw == label
        if final == label:
            exact += 1
            continue
        lt = label.split()
        fd, xd = lev(raw, label), lev(final, label)
        if final.lower() == label.lower():
            primary, matching = "matching-case", "case-only"
        elif len(final) != len(label):
            primary = "segmentation"
            matching = ("glyphs-recovered"
                        if final.replace(" ", "").lower()
                        == label.replace(" ", "").lower()
                        else "not-isolable")
        else:
            primary, matching = "matching-glyph", "glyph-substitution"
        seg_word_ok = r["reader_words"] == len(lt)
        seg_piece_ok = seg_word_ok and r["glyph_pieces"] == [len(t) for t in lt]
        from collections import Counter as _C
        tok_f = sum((_C(raw.split()) & _C(label.split())).values())
        tok_x = sum((_C(final.split()) & _C(label.split())).values())
        if tok_x > tok_f or (tok_x == tok_f and xd < fd):
            lex = "helped"
        elif tok_x < tok_f or (tok_x == tok_f and xd > fd):
            lex = "hurt"
        else:
            lex = "neutral"
        misses.append({
            "id": r["id"], "family": r["family"], "label": label,
            "floor": raw, "final": final, "primary": primary,
            "matching": matching,
            "seg_word": "OK" if seg_word_ok else "FAIL",
            "seg_piece": "OK" if seg_piece_ok else "FAIL",
            "reader_words": r["reader_words"], "label_tokens": len(lt),
            "glyph_pieces": r["glyph_pieces"],
            "lex": lex, "lex_dist_floor": fd, "lex_dist_final": xd,
            "lex_tokens_floor": tok_f, "lex_tokens_final": tok_x})
    summary = {
        "items": len(rows), "floor_exact": floor_exact,
        "final_exact": exact, "misses": len(misses),
        "primary": dict(Counter(m["primary"] for m in misses)),
        "matching": dict(Counter(m["matching"] for m in misses)),
        "lex": dict(Counter(m["lex"] for m in misses)),
        "seg_word_fail": sum(m["seg_word"] == "FAIL" for m in misses),
        "seg_piece_fail": sum(m["seg_piece"] == "FAIL" for m in misses),
    }
    return misses, summary


def diff_s43(misses: list[dict], rows: list[dict]) -> dict:
    """Every classification change vs the S43 map, item by item."""
    s43 = json.loads(S43_MAP.read_text())
    old_miss = {m["id"]: m for m in s43["misses"]}
    now_miss = {m["id"]: m for m in misses}
    now_exact = {r["id"] for r in rows} - set(now_miss)
    fixed, still, regressions = [], [], []
    for i, m in sorted(old_miss.items()):
        if i in now_exact:
            fixed.append({"id": i, "was": m["primary"], "floor_was": m["floor"],
                          "label": m["label"]})
        else:
            n = now_miss[i]
            changed = (m["primary"] != n["primary"]
                       or m["matching"] != n["matching"])
            still.append({"id": i, "was": f"{m['primary']}/{m['matching']}",
                          "now": f"{n['primary']}/{n['matching']}",
                          "changed": changed})
    for m in misses:
        if m["id"] not in old_miss:
            regressions.append({"id": m["id"], "label": m["label"],
                                "floor": m["floor"], "final": m["final"]})
    return {
        "s43_misses": len(old_miss), "s43_final_exact": s43["summary"]["final_exact"],
        "fixed": fixed, "still_missing": still,
        "still_missing_changed_class": [s for s in still if s["changed"]],
        "regressions": regressions,
    }


def gates(rows, misses, s, d) -> list[tuple[str, bool, str]]:
    bench = json.loads(BENCH_RECEIPT.read_text())
    br = {r["id"]: r for r in bench["suites"]["hard"]["results"]}
    g1 = len(rows) == 100 and all(
        br[r["id"]]["label"] == r["label"] and br[r["id"]]["family"] == r["family"]
        for r in rows)
    agree = sum(br[r["id"]]["got"] == r["final"] for r in rows)
    g2 = len(rows) == 100 and agree == 100
    g3 = s["final_exact"] == EXPECT_FINAL_EXACT and s["misses"] == 100 - EXPECT_FINAL_EXACT
    g4 = s["floor_exact"] == EXPECT_FLOOR_EXACT
    g5 = not d["regressions"]
    return [
        ("G1 manifest==receipt labels/families", g1, "100/100 agreement"),
        ("G2 live final==bench got", g2, f"{agree}/100 items agree"),
        ("G3 settled numbers", g3,
         f"final_exact {s['final_exact']} (expect {EXPECT_FINAL_EXACT}), "
         f"misses {s['misses']} (expect {100 - EXPECT_FINAL_EXACT})"),
        ("G4 floor settled", g4,
         f"floor_exact {s['floor_exact']} (expect {EXPECT_FLOOR_EXACT})"),
        ("G5 zero regressions vs S43", g5,
         f"{len(d['regressions'])} regression(s)"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--jsonl", type=Path)
    a = ap.parse_args()

    rows = collect()
    misses, s = classify(rows)
    d = diff_s43(misses, rows)
    gr = gates(rows, misses, s, d)

    print(f"hard items {s['items']} | floor exact {s['floor_exact']} | "
          f"shipping (fix_line) exact {s['final_exact']} | misses {s['misses']}")
    print(f"primary: {s['primary']}")
    print(f"lex on misses: {s['lex']} | seg_word FAIL {s['seg_word_fail']}/{s['misses']}"
          f" | native seg_piece FAIL {s['seg_piece_fail']}/{s['misses']}")
    fam = defaultdict(Counter)
    fam_tot = Counter(r["family"] for r in rows)
    for m in misses:
        fam[m["family"]][m["primary"]] += 1
    for f in sorted(fam):
        print(f"  {f:<13} misses {sum(fam[f].values())}/{fam_tot[f]} {dict(fam[f])}")
    print(f"vs S43: {len(d['fixed'])} fixed, {len(d['still_missing'])} still missing "
          f"({len(d['still_missing_changed_class'])} changed class), "
          f"{len(d['regressions'])} regressions")
    for m in d["fixed"]:
        print(f"  FIXED {m['id']} (was {m['was']}): floor was `{m['floor_was']}`")
    for m in d["still_missing_changed_class"]:
        print(f"  CHANGED {m['id']}: {m['was']} -> {m['now']}")
    for m in d["regressions"]:
        print(f"  REGRESSION {m['id']}: `{m['final']}` != `{m['label']}`")

    if a.jsonl:
        a.jsonl.parent.mkdir(parents=True, exist_ok=True)
        a.jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"wrote {a.jsonl}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(
            {"summary": s, "vs_s43": d, "misses": misses}, indent=1) + "\n")
        print(f"wrote {a.json}")
    if a.table:
        print("\n| id | family | primary | seg word/piece | matching | lex "
              "(dist floor→final) | final read vs label |")
        print("|---|---|---|---|---|---|---|")
        for m in sorted(misses, key=lambda m: (m["family"], m["id"])):
            print(f"| {m['id']} | {m['family']} | {m['primary']} | "
                  f"{m['seg_word']}/{m['seg_piece']} | {m['matching']} | "
                  f"{m['lex']} ({m['lex_dist_floor']}→{m['lex_dist_final']}) | "
                  f"`{m['final']}` ≠ `{m['label']}` |")

    ok = all(g for _, g, _ in gr)
    print("\nGATES:")
    for name, g, detail in gr:
        print(f"  {'PASS' if g else 'FAIL'}  {name} — {detail}")
    print("VALIDATION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
