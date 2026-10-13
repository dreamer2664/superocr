#!/usr/bin/env python3
"""S55 post-processing validation harness (audit t-20261013-90e8).

Recomputes the S55 target set (the 14 non-segmentation misses of the S43
census) and measures generic post-processing candidates OFFLINE against the
committed receipts, on FULL suites (never just the 14 items).

Candidates (pre-registered; each is a rule class, no per-item rules):
  A  shipping: tools.lex_projection.fix_line as-is (baseline, must reproduce
     the canonical reader_lex seed-1 numbers 73/23 before anything is read
     into the other arms).
  B  lex R3 band widened by +1 for every token length.
  C  lex R3 band widened by +1 only for tokens of length >= 6.
  D  A + token-majority re-case of already-clean vocabulary tokens
     (the specific rule S24 measured at 5/18 token-correct on the TARGET
     positions' neighbourhood; re-measured here on full suites).

Guard sets: seed-2 rows are the raw reader rows of the S23 v2/v3 captures
(reports/s23-homoglyph-inputs/*-s2.json), evaluated the same way.

Nothing here modifies baseline.py or tools/lex_projection.py: variants are
local re-implementations that reuse lex_projection's helpers.

Output: reports/s55_postprocess_harness.json (and a table on stdout).
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lex_projection import (  # noqa: E402
    VOCAB, _DIGIT_FIX, _ed, _project, _repair_tokens, _s25_count_repairs,
    fix_line)
S43 = ROOT / "reports" / "s43_failure_analysis.json"

RECEIPTS = ROOT / "reports/post27-screens/20261012T170353Z-easy-hard.json"
S23 = ROOT / "reports" / "s23-homoglyph-inputs"
OUT = ROOT / "reports" / "s55_postprocess_harness.json"


def fix_token_wide(tok, extra_all=0, extra_ge6=0):
    """Verbatim copy of lex_projection.fix_token with a widened R3 band.

    With both extras 0 this is the pre-S55 shipping rule (candidate A,
    validated by the 73/23 reproduction assertion in main()); B/C differ
    from it ONLY in the band.
    """
    if not tok:
        return tok
    low = tok.lower()
    if low in VOCAB:
        return tok                                              # R1
    if tok.isdigit() or (len(tok) <= 4 and
                         tok.translate(_DIGIT_FIX).isdigit()):
        return tok                                              # R2
    if not any(c.isalpha() for c in tok):
        return tok
    band = max(1, round(len(low) / 3))                          # R3
    if extra_all:
        band += extra_all
    if extra_ge6 and len(low) >= 6:
        band += extra_ge6
    best, bd, second = None, band + 1, band + 1
    for w in VOCAB:
        d, _ = _ed(low, w)
        if d < bd:
            second, best, bd = bd, w, d
        elif d < second:
            second = d
    if best is None or bd > band or (second - bd) < 1:
        return tok
    return _project(tok, best)


def fix_line_variant(text, **kw):
    toks = _repair_tokens(text.split(" "))
    toks = [fix_token_wide(t, **kw) for t in toks]
    return " ".join(_s25_count_repairs(toks))


def case_majority(line):
    """Rule D: re-case clean-vocab mixed-case tokens to their majority case."""
    out = []
    for tok in line.split():
        if tok.isalpha() and tok.lower() in VOCAB and not (
                tok.isupper() or tok.islower()):
            up = sum(c.isupper() for c in tok)
            out.append(tok.upper() if up * 2 > len(tok) else tok.lower())
        else:
            out.append(tok)
    return " ".join(out)


CANDIDATES = {
    # A is the PRE-S55 shipping rule, pinned via the local variant copy
    # (extras=0) so this audit stays reproducible after the S55 change
    # landed in tools/lex_projection.py (where fix_line now equals B).
    "A_shipping": lambda line: fix_line_variant(line),
    "B_band+1_all": lambda line: fix_line_variant(line, extra_all=1),
    "C_band+1_len>=6": lambda line: fix_line_variant(line, extra_ge6=1),
    "D_A+case_majority": lambda line: case_majority(fix_line_variant(line)),
}


def suites_from_post27():
    d = json.loads(RECEIPTS.read_text())
    return {s: [(r["id"], r["label"], r["got"])
                for r in d["suites"][s]["results"]]
            for s in ("easy", "hard")}


def suites_from_s23(tag):
    rows = json.loads((S23 / f"{tag}.json").read_text())
    out = {"easy": [], "hard": []}
    for r in rows:
        out[r["suite"]].append((r["id"], r["label"], r["got"]))
    return out


def evaluate(rows_by_suite, fn):
    res = {}
    for suite, rows in rows_by_suite.items():
        exact = sum(fn(got) == label for _id, label, got in rows)
        res[suite] = exact
    return res


def main():
    # Targets are pinned to the COMMITTED S43 census (merged in PR #69):
    # recomputing the census under a changed lex would move the goalposts
    # (candidate B already makes stitch-0001 exact, by design).
    s43 = json.loads(S43.read_text())
    census_summary = s43["summary"]
    targets = [r for r in s43["misses"]
               if r["primary"] in ("matching-case", "matching-glyph")]
    assert len(targets) == 14, len(targets)
    target_ids = {r["id"] for r in targets}

    sets = {
        "seed1_floor(post27)": suites_from_post27(),
        "seed2_v2_raw": suites_from_s23("main-v2-s2"),
        "seed2_v3_raw": suites_from_s23("main-v3-s2"),
        "seed1_v2_raw_extra": suites_from_s23("main-v2-s1"),
        "seed1_v3_raw_extra": suites_from_s23("main-v3-s1"),
    }

    # Variant-equivalence check: the local copy with extras=0 must
    # reproduce the PRE-S55 shipping fix_token rule-for-rule, which the
    # 73/23 assertion below validates end-to-end; and the production
    # fix_line (post-S55) must equal candidate B on every evaluated line.
    for set_name, rows_by_suite in sets.items():
        for rows in rows_by_suite.values():
            for _id, _label, got in rows:
                assert fix_line(got) == fix_line_variant(
                    got, extra_all=1), (
                    f"production fix_line diverges from candidate B at "
                    f"{set_name}/{_id}")
    print("equivalence: production fix_line == candidate B on all "
          "evaluated lines; A pinned to pre-S55 shipping (extras=0)")

    report = {"targets": [{k: r[k] for k in
                           ("id", "family", "primary", "floor", "final",
                            "label")} for r in targets],
              "candidate_scores": {}, "target_recovery": {}}

    base = None
    for name, fn in CANDIDATES.items():
        scores = {}
        for set_name, rows in sets.items():
            scores[set_name] = evaluate(rows, fn)
        report["candidate_scores"][name] = scores
        # recovery on the 14 targets (seed-1 floor rows)
        rec = [r["id"] for r in targets if fn(r["floor"]) == r["label"]]
        report["target_recovery"][name] = rec
        # per-item fix/break diffing vs A on the primary sets, both suites
        primary = ("seed1_floor(post27)", "seed2_v3_raw")
        if name == "A_shipping":
            base = {sn: {i: fn(g) for rows in sets[sn].values()
                         for i, _l, g in rows} for sn in primary}
            base_labels = {sn: {i: l for rows in sets[sn].values()
                                for i, l, _g in rows} for sn in primary}
        else:
            diffs = {}
            for sn in primary:
                alt = {i: fn(g) for rows in sets[sn].values()
                       for i, _l, g in rows}
                labels = base_labels[sn]
                diffs[sn] = {
                    "fixes": sorted(i for i in labels
                                    if alt[i] == labels[i] != base[sn][i]),
                    "breaks": sorted(i for i in labels
                                     if base[sn][i] == labels[i] != alt[i]),
                }
            report.setdefault("diffs_vs_A", {})[name] = diffs

    a = report["candidate_scores"]["A_shipping"]["seed1_floor(post27)"]
    assert (a["easy"], a["hard"]) == (73, 23), (
        f"harness invalid: A reproduces {a}, expected shipping 73/23")
    OUT.write_text(json.dumps(report, indent=1) + "\n")

    print(f"targets: {len(targets)} "
          f"({sum(r['primary']=='matching-case' for r in targets)} case, "
          f"{sum(r['primary']=='matching-glyph' for r in targets)} glyph); "
          f"S43 census misses {census_summary['misses']} = "
          f"{census_summary['primary']}")
    hdr = f"{'candidate':22s} " + " ".join(
        f"{s.split('(')[0]:>18s}" for s in sets) + "  targets"
    print(hdr)
    for name in CANDIDATES:
        cells = []
        for set_name in sets:
            sc = report["candidate_scores"][name][set_name]
            cells.append(f"{sc['easy']:3d}/{sc['hard']:<14d}")
        print(f"{name:22s} " + " ".join(f"{c:>18s}" for c in cells)
              + f"  {len(report['target_recovery'][name])}/14 "
              + str(report["target_recovery"][name]))
    for name, d in report.get("diffs_vs_A", {}).items():
        for sn, dd in d.items():
            print(f"{name} [{sn}]: fixes {dd['fixes']} breaks {dd['breaks']}")
    print(f"wrote {OUT.relative_to(ROOT)} "
          f"(A validates: easy {a['easy']} / hard {a['hard']} == 73/23)")


if __name__ == "__main__":
    main()
