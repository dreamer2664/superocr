#!/usr/bin/env python3
"""s10c_cnn_cuts.py — CNN-scored cut search for fused joins (S10c prep).

Companion to s10c_fused_scan.py. For a piece suspected of hiding two touching
glyphs, enumerate the interior column cuts (profile minima), read BOTH halves
with glyphcnn-v2, and accept a split only when the CNN is confident about
both halves - the scorer-side alternative to the template rescue in
tools/s8_resplit.py / barry's PR #27.

Acceptance rules measured (all must hold):
  * the fused piece's own template score is below --conf-gate (it is a doubt),
  * both halves are non-trivial (min height / min ink),
  * min(cnn_p_left, cnn_p_right) or their product clears --cnn-gate,
  * the CNN product beats the fused piece's own CNN probability (the halves
    read better than the whole), by --cnn-margin.

Nothing here is wired into anything: it is the experiment runner. Numbers per
suite item: flips solved, flips lost, untouched. Held-out seed-2 suite is the
check that decides whether any of it ever ships.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "readers"))

from s10b_gate import chain_pieces, apply_case  # noqa: E402
from s10c_fused_scan import profile_minima  # noqa: E402
from piece_cnn import PieceCNN  # noqa: E402
import baseline as B  # noqa: E402



def top_chars(mask: np.ndarray, k: int = 8) -> list[tuple[str, float]]:
    """The matcher's own top-k candidates for this mask (same scan as
    match_native, ordered by height proximity then score) - the honesty
    boundary: a CNN pick must be inside this list to be allowed."""
    h = mask.shape[0]
    scored = []
    for ch, face, t in sorted(B._cands_for_height(h),
                              key=lambda cf: (abs(cf[2].shape[0] - h), cf[1])):
        scored.append((ch, float(B.R._score_glyph(mask, t))))
    scored.sort(key=lambda cs: -cs[1])
    seen, out = set(), []
    for ch, sc in scored:
        if ch in seen:
            continue
        seen.add(ch)
        out.append((ch, sc))
        if len(out) >= k:
            break
    return out

def cnn_score_halves(net: PieceCNN, left: np.ndarray, right: np.ndarray):
    (lc, lp), (rc, rp) = net.opinions([left, right])
    return lc, lp, rc, rp


def try_split(net: PieceCNN, piece: np.ndarray, fused_cnn_p: float,
              conf_gate: float, cnn_gate: float, cnn_margin: float,
              min_h: int = 6, min_ink: int = 8, criterion: str = "beat-fused"):
    """Best accepted cut for this piece, or None.

    criterion:
      beat-fused    prod of half probabilities must beat the fused piece's
                    own CNN probability by --cnn-margin (strictest)
      halves-only   both halves at --cnn-gate is enough; product ranks cuts
      precondition  like halves-only, but the piece must ALSO be genuinely
                    doubtful: fused template score < --conf-gate
      top8-contain  halves-only + each half's CNN pick must be inside that
                    half's matcher top-8 + the fused piece must trip the
                    wave-3 trigger (top-2 margin < 0.01 or top-1 < 0.85)
    """
    h, w = piece.shape
    best = None
    for c in profile_minima(piece):
        left, right = piece[:, :c], piece[:, c:]
        if left.shape[1] < 2 or right.shape[1] < 2:
            continue
        if left.shape[0] < min_h or right.shape[0] < min_h:
            continue
        if left.sum() < min_ink or right.sum() < min_ink:
            continue
        lc, lp, rc, rp = cnn_score_halves(net, left, right)
        prod = lp * rp
        if min(lp, rp) < cnn_gate:
            continue
        if criterion == "beat-fused" and prod < fused_cnn_p + cnn_margin:
            continue
        if criterion == "precondition":
            _tch, ts = B.match_native(piece)
            if ts >= conf_gate:
                continue
        if criterion == "top8-contain":
            # barry's wave-3 honesty rule, applied per half: each half's CNN
            # pick must be inside that half's own matcher top-8, and the FUSED
            # piece must trip the same trigger his vote uses (tie or dip)
            ltop = [c for c, _ in top_chars(left)]
            rtop = [c for c, _ in top_chars(right)]
            if lc not in ltop or rc not in rtop:
                continue
            ftop = top_chars(piece, k=2)
            if len(ftop) < 2:
                continue
            if not (ftop[0][1] - ftop[1][1] < 0.01 or ftop[0][1] < 0.85):
                continue
        if best is None or prod > best[0]:
            best = (prod, lc, lp, rc, rp, c)
    return best


def read_with_cuts(im: Image.Image, net: PieceCNN, conf_gate: float,
                   cnn_gate: float, cnn_margin: float = 0.0,
                   criterion: str = "beat-fused") -> tuple[str, int]:
    """Floor layout + CNN characters, with the cut search applied on the
    doubtful pieces. Returns (text, cuts_accepted)."""
    words = chain_pieces(im)
    out, accepted = [], 0
    for pieces in words:
        cap = max(g.shape[0] for g in pieces)
        ops = net.opinions(pieces)
        chars = []
        for g, (cch, cp) in zip(pieces, ops):
            tmpl_ch, tmpl_s = B.match_native(g)
            h, w = g.shape
            aspect = w / max(h, 1)
            doubtful = (tmpl_s < conf_gate) or (aspect > 0.85)
            if criterion == "none":
                doubtful = False
            if doubtful:
                best = try_split(net, g, cp, conf_gate, cnn_gate, cnn_margin,
                                 criterion=criterion)
                if best is not None:
                    _, lc, lp, rc, rp, cut = best
                    chars.append(apply_case(lc, left_h(g, cut), cap))
                    chars.append(apply_case(rc, right_h(g, cut), cap))
                    accepted += 1
                    continue
            chars.append(apply_case(cch, h, cap))
        if chars:
            out.append("".join(chars))
    return " ".join(out), accepted


def left_h(g: np.ndarray, cut: int) -> int:
    col = g[:, :cut]
    rows = np.where(col.any(axis=1))[0]
    return int(rows[-1] - rows[0] + 1) if rows.size else g.shape[0]


def right_h(g: np.ndarray, cut: int) -> int:
    col = g[:, cut:]
    rows = np.where(col.any(axis=1))[0]
    return int(rows[-1] - rows[0] + 1) if rows.size else g.shape[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-dir", default="/tmp/s10-suites")
    ap.add_argument("--suites", default="easy")
    ap.add_argument("--weights", default=None)
    ap.add_argument("--conf-gate", type=float, default=0.72)
    ap.add_argument("--cnn-gate", type=float, default=0.5)
    ap.add_argument("--cnn-margin", type=float, default=0.0)
    ap.add_argument("--criterion", default="beat-fused",
                    choices=("none", "beat-fused", "halves-only", "precondition",
                             "top8-contain"))
    ap.add_argument("--baseline-json", default=None,
                    help="rows json from route_check2-style run for before/after diff")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    net = PieceCNN(args.weights)
    report = {}
    for suite in args.suites.split(","):
        base = Path(args.suite_dir) / suite
        manifest = [json.loads(l) for l in (base / "manifest.jsonl").read_text().splitlines()
                    if l.strip()]
        if args.limit:
            manifest = manifest[:args.limit]
        before = {}
        if args.baseline_json:
            before = {x["id"]: x for x in json.load(open(args.baseline_json))
                      if x.get("suite", suite) == suite}
        kept = solved = lost = 0
        cuts_total = 0
        rows = []
        for n, item in enumerate(manifest, 1):
            with Image.open(base / item["image"]) as im:
                im = im.convert("RGB")
                text, acc = read_with_cuts(im, net, args.conf_gate, args.cnn_gate,
                                           args.cnn_margin, criterion=args.criterion)
            cuts_total += acc
            match = text == item["label"]
            if before:
                was = before[item["id"]]["match"]
                kept += was and match
                solved += (not was) and match
                lost += was and (not match)
            rows.append({"id": item["id"], "label": item["label"], "got": text,
                         "match": match, "cuts": acc})
            if n % 25 == 0:
                print(f"  [{suite}] {n}/{len(manifest)}", flush=True)
        exact = sum(r["match"] for r in rows)
        report[suite] = {"exact": exact, "total": len(rows), "cuts": cuts_total,
                         "kept": kept, "solved": solved, "lost": lost, "rows": rows}
        print(f"\n{suite}: exact {exact}/{len(rows)} | cuts accepted {cuts_total} "
              f"| vs before: kept {kept}, SOLVED {solved}, LOST {lost}")
    if args.json:
        json.dump(report, open(args.json, "w"), indent=1)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
