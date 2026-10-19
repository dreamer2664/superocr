#!/usr/bin/env python3
"""S37 — offline ensemble probe: word-majority voting across measured arms.

Task: t-20261013-1cbf. Question: can word-level majority voting across
currently-invokable members beat the best single arm (shipping 73/23 seed-1)
on the canonical suites, offline?

ARMS FIXED UP-FRONT (S51 gated template — decided before any numbers):

  members (all in-process on current main code, deterministic):
    M-off  = fix_line(baseline.read_text(img, None))      [shipping wrapper;
             byte semantics verified vs tools/reader_lex.py in the S39/S51/S31
             receipt chain]
    M-nlex = baseline.read_text(img, None) raw            [floor, no lexicon;
             same call as M-off before fix_line]
    M-auto = fix_line(typer.recognise(img, "auto"))       [preclassifier
             family chain + lexicon]
    M-v7b  = fix_line(read_text with baseline._CNN = glyphcnn-v7b)
             [S31 Lever-2 slot swap, same injection method; expected to
             reproduce the committed s31-slot-rows v7b arm 70/24]

  arms:
    OFF    = M-off alone. GATE: must reproduce the settled shipping line
             exactly (easy 73/100, hard 23/100 on canonical seed-1) or the
             whole probe is VOID.
    E3a    = word-majority {M-off, M-nlex, M-auto}
    E3b    = word-majority {M-off, M-auto, M-v7b}
    E4     = word-majority {M-off, M-nlex, M-auto, M-v7b}

  voting rules (fixed):
    - tokenise reads on whitespace;
    - if any member's word count differs from M-off's, the arm takes M-off's
      read for that item (row flag fallback="count") — conservative;
    - per word position, exact-string majority; any tie (incl. 2-2) resolves
      to M-off's word;
    - labels are compared exact and case-sensitive (the bench rule).

Rows are committed per item; seed-2 is UNTOUCHED (winner's-curse law: a
seed-1 gain gets a separate held-out confirmation receipt before any ship
claim). Zero reader-path change: probe tool + rows + report only.

Usage:
    python3 tools/s37_ensemble_probe.py --suites <seed1-dir> \
        --out reports/s37-ensemble-rows.jsonl [--only easy|hard]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import baseline  # noqa: E402
import typer as T  # noqa: E402
from lex_projection import fix_line  # noqa: E402
from readers.glyphcnn import GlyphCNN  # noqa: E402

MEMBER_ARMS = ("off", "nlex", "auto", "v7b")
ENSEMBLE_ARMS = {
    "E3a": ("off", "nlex", "auto"),
    "E3b": ("off", "auto", "v7b"),
    "E4": ("off", "nlex", "auto", "v7b"),
}


def member_reads(img: Image.Image, v7b: GlyphCNN) -> dict[str, str]:
    floor_text, _ = baseline.read_text(img, None)
    out = {"off": fix_line(floor_text), "nlex": floor_text}
    auto_text, _, _fam = T.recognise(img, "auto")
    out["auto"] = fix_line(auto_text)
    saved = baseline._CNN
    try:
        baseline._CNN = v7b
        v7b_floor, _ = baseline.read_text(img, None)
    finally:
        baseline._CNN = saved
    out["v7b"] = fix_line(v7b_floor)
    return out


def vote(reads: dict[str, str], members: tuple[str, ...]) -> tuple[str, str | None]:
    """Word-majority across members; ties and count-mismatches fall back to
    the OFF read. Returns (text, fallback_reason_or_None)."""
    off_words = reads["off"].split()
    words = {m: reads[m].split() for m in members}
    if any(len(words[m]) != len(off_words) for m in members):
        return reads["off"], "count"
    out = []
    tie = False
    for i, off_w in enumerate(off_words):
        c = Counter(words[m][i] for m in members)
        top, n = c.most_common(1)[0]
        if n * 2 <= len(members) or sum(1 for v in c.values() if v == n) > 1:
            # no strict majority, or top tie -> OFF word wins
            out.append(off_w)
            tie = True
        else:
            out.append(top)
    return " ".join(out), ("tie" if tie else None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suites", required=True, help="suite dir (easy/ hard/ inside)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=("easy", "hard"))
    args = ap.parse_args()

    suites_dir = Path(args.suites)
    v7b = GlyphCNN.load(str(ROOT / "models" / "glyphcnn-v7b.npz"))
    started_all = time.perf_counter()
    rows = []
    for suite in ("easy", "hard"):
        if args.only and suite != args.only:
            continue
        manifest = suites_dir / suite / "manifest.jsonl"
        for line in manifest.read_text().splitlines():
            item = json.loads(line)
            img = Image.open(manifest.parent / item["image"])
            t0 = time.perf_counter()
            reads = member_reads(img, v7b)
            sec = round(time.perf_counter() - t0, 3)
            row = {
                "suite": suite, "id": Path(item["image"]).stem,
                "family": item.get("family", suite), "label": item["label"],
                "sec": sec,
            }
            for m in MEMBER_ARMS:
                row[f"got_{m}"] = reads[m]
                row[f"exact_{m}"] = (reads[m] == item["label"])
            for arm, members in ENSEMBLE_ARMS.items():
                text, fb = vote(reads, members)
                row[f"got_{arm}"] = text
                row[f"exact_{arm}"] = (text == item["label"])
                if fb:
                    row[f"fallback_{arm}"] = fb
            rows.append(row)
            print(f"{row['suite']}/{row['id']} off={row['exact_off']} "
                  f"E4={row['exact_E4']} ({sec}s)", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
        fh.write(json.dumps({"event": "done", "rows": len(rows),
                             "wall_s": round(time.perf_counter() - started_all, 1)}) + "\n")

    totals: dict[str, list[int]] = {}
    for arm in MEMBER_ARMS + tuple(ENSEMBLE_ARMS):
        for suite in ("easy", "hard"):
            sel = [r for r in rows if r["suite"] == suite]
            totals[f"{arm}/{suite}"] = [sum(r[f"exact_{arm}"] for r in sel), len(sel)]
    print(json.dumps(totals, indent=1))
    print(f"report {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
