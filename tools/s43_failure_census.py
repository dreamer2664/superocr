#!/usr/bin/env python3
"""S43 (t-20261013-7eff): failure census of the 77 hard misses.

Receipt-based, no bench re-run. Inputs are committed artifacts:

  * reports/post27-screens/20261012T170353Z-easy-hard.json
      the post-#27 floor receipt (reader `python3 baseline.py {image}`,
      canonical seed-1 suites, dir_hash b2c460d2fb5a...): per-item
      raw floor `got` for all 100 hard items.
  * reports/s25-piece-gap/hard-reads.jsonl
      Cormac's S25 collection on the same suite: per-item reader word
      count and glyph-piece counts from replicating baseline's mask
      path (autocontrast -> otsu/S8 lean -> polarity guard -> despeck
      -> trim -> deskew -> R.segment).

The final shipping read is recomputed, not assumed:
`fix_line(floor_got)` with the current tools/lex_projection.py
(R1-R5 + S25 count repairs). Validation in this script: that
recomputation must give exactly 23/100 hard exact (the settled
shipping number), and the floor alone 12/100.

Classification (per hard miss, all definitions are proxies and are
named as such in reports/s43_failure_analysis.md):

  primary root cause, by decision tree on the FINAL read:
    1. matching-case   final.lower() == label.lower() (chars all
                       recovered, only case decisions wrong)
    2. segmentation    len(final) != len(label) (fewer/more chars:
                       the S22 segmentation signature)
    3. matching-glyph  same length, character substitutions remain

  segmentation diagnostics (reader stage, independent of primary):
    seg_word   FAIL if reader_words != label token count
    seg_piece  FAIL if seg_word FAIL or glyph_pieces != label token
               lengths (native R.segment pieces, before split_wide
               rescue -- a FAIL here is evidence, not proof: 7 of the
               14 matching-primary misses carry a native piece FAIL
               whose characters were nevertheless recovered)

  matching (only isolable when the text structure survives):
    case-only / glyph-substitution / not-isolable (segmentation
    masks it) / glyphs-recovered (only tokenisation wrong)

  lex effect (floor -> final), token-aware:
    helped  exact-token matches (multiset vs label) increased, or
            token matches equal and char Levenshtein distance fell
    hurt    the mirror image (split-0001 in an earlier char-only
            draft is the cautionary case: lex recovered the exact
            token `MEriDIAn`, yet global char distance rose 3->4
            because of the spurious `hE` token -- token-aware
            scoring classifies it, correctly, as helped)
    neutral neither (includes final == floor)

Usage:
  python3 tools/s43_failure_census.py                 # summary
  python3 tools/s43_failure_census.py --table         # + per-item md table
  python3 tools/s43_failure_census.py --json reports/s43_failure_analysis.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lex_projection import fix_line  # noqa: E402

FLOOR_RECEIPT = ROOT / "reports/post27-screens/20261012T170353Z-easy-hard.json"
S25_READS = ROOT / "reports/s25-piece-gap/hard-reads.jsonl"


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def census() -> tuple[list[dict], dict]:
    floor = json.loads(FLOOR_RECEIPT.read_text())
    hard = floor["suites"]["hard"]["results"]
    s25 = {r["id"]: r for r in
           (json.loads(l) for l in S25_READS.read_text().splitlines())}
    assert len(hard) == 100 and len(s25) == 100

    rows, exact = [], 0
    floor_exact = 0
    for r in hard:
        b = s25[r["id"]]
        assert r["label"] == b["want"] and r["family"] == b["family"], r["id"]
        label, raw = r["label"], r["got"]
        final = fix_line(raw)
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
        seg_word_ok = b["reader_words"] == len(lt)
        seg_piece_ok = seg_word_ok and b["glyph_pieces"] == [len(t) for t in lt]
        from collections import Counter as _C
        tok_f = sum((_C(raw.split()) & _C(label.split())).values())
        tok_x = sum((_C(final.split()) & _C(label.split())).values())
        if tok_x > tok_f or (tok_x == tok_f and xd < fd):
            lex = "helped"
        elif tok_x < tok_f or (tok_x == tok_f and xd > fd):
            lex = "hurt"
        else:
            lex = "neutral"
        rows.append({
            "id": r["id"], "family": r["family"], "label": label,
            "floor": raw, "final": final, "primary": primary,
            "matching": matching,
            "seg_word": "OK" if seg_word_ok else "FAIL",
            "seg_piece": "OK" if seg_piece_ok else "FAIL",
            "reader_words": b["reader_words"], "label_tokens": len(lt),
            "glyph_pieces": b["glyph_pieces"],
            "lex": lex, "lex_dist_floor": fd, "lex_dist_final": xd,
            "lex_tokens_floor": tok_f, "lex_tokens_final": tok_x,
        })
    summary = {
        "items": len(hard), "floor_exact": floor_exact,
        "final_exact": exact, "misses": len(rows),
        "dir_hash": floor["stamps"]["dir_hash"],
        "primary": dict(Counter(r["primary"] for r in rows)),
        "lex": dict(Counter(r["lex"] for r in rows)),
        "seg_word_fail": sum(r["seg_word"] == "FAIL" for r in rows),
        "seg_piece_fail": sum(r["seg_piece"] == "FAIL" for r in rows),
    }
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    rows, s = census()
    # settled-number gate: floor 12 -> shipping 23 -> 77 misses
    ok = (s["floor_exact"], s["final_exact"], s["misses"]) == (12, 23, 77)
    print(f"hard items {s['items']} | floor exact {s['floor_exact']} | "
          f"shipping (fix_line) exact {s['final_exact']} | misses {s['misses']}")
    print(f"dir_hash {s['dir_hash']}")
    print(f"primary: {s['primary']}")
    print(f"lex on misses: {s['lex']} | seg_word FAIL {s['seg_word_fail']}/77"
          f" | native seg_piece FAIL {s['seg_piece_fail']}/77")
    fam = defaultdict(Counter)
    for r in rows:
        fam[r["family"]][r["primary"]] += 1
    for f in sorted(fam):
        print(f"  {f:<13} {dict(fam[f])}")
    if a.json:
        a.json.write_text(json.dumps(
            {"summary": s, "misses": rows}, indent=1) + "\n")
        print(f"wrote {a.json}")
    if a.table:
        print("\n| id | family | primary | seg word/piece | matching | lex "
              "(dist floor→final) | final read vs label |")
        print("|---|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: (r["family"], r["id"])):
            print(f"| {r['id']} | {r['family']} | {r['primary']} | "
                  f"{r['seg_word']}/{r['seg_piece']} | {r['matching']} | "
                  f"{r['lex']} ({r['lex_dist_floor']}→{r['lex_dist_final']}) | "
                  f"`{r['final']}` ≠ `{r['label']}` |")
    print("VALIDATION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
