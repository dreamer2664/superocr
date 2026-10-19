#!/usr/bin/env python3
"""S69 — glyph-residue evidence pack harness (t-20261014-df3c).

An evidence COPY of baseline.read_text (version-pinned to this commit):
same stages, same constants, plus capture of every internal decision —
per piece: mask metrics, matcher top-8, CNN opinion, pre/post-case
choice — so each miss can be attributed to a stage. No shipping-path
edits; report-only.

Usage:
    python3 tools/s69_evidence.py            # full pack -> stdout + gallery
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import baseline as B          # noqa: E402
import reader as R            # noqa: E402
from lex_projection import fix_line  # noqa: E402

# target set: union of (a) the current 7 same-length substitution misses
# on committed seed-1 r1, (b) the 4 S55 §6 glyph targets, (c) the
# S43-era 5th substitution (stitch-0001) as a recovery confirmation.
ITEMS = {
    "easy-0001":  ("easy", "Falcon BilTh",           "Falcon Birch"),
    "easy-0014":  ("easy", "OASIS breeze 73 FFNmPI", "OASIS breeze 73 FENNEL"),
    "easy-0023":  ("easy", "meSa SPARROW nT",        "Mesa SPARROW 07"),
    "easy-0068":  ("easy", "D1rch cRYStAL gq",       "birch cRYStAl 79"),
    "snow-0003":  ("hard", "HEATHER rert",           "HEATHER reef"),
    "strippy-0005": ("hard", "zztlz 1 rIJJz tide",   "sable 1 Forge tide"),
    "split-0006": ("hard", "brass tide canyon cafmon nebULA",
                                     "brass tide canyon carBon nebULA"),
    "dark-on-dark-0000": ("hard", "Vi ULL NECTAR raVen nnA",
                                     "VIOLET NECTAR raven 006"),
    "stitch-0001": ("hard", "TUNDRA harbor",         "TUNDRA harbor"),
}


def read_with_evidence(img: Image.Image):
    """Copy of baseline.read_text with capture. Returns (text, pieces)."""
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
    out, conf, pieces = [], [], []
    built = []
    for word in words:
        ps = []
        for x0, x1 in word:
            for g0 in B._merge_forced(B._split_marked(R.trim(mask[:, x0:x1]))):
                if g0.shape[0] >= 6 and g0.sum() >= 10:
                    for g in B._rescue_split(g0):
                        ps.append(g)
        if ps:
            built.append(ps)
    all_h = sorted(g.shape[0] for ps in built for g in ps)
    cap_glob = x_glob = None
    if len(all_h) >= 6:
        gap_at = max(range(len(all_h) - 1),
                     key=lambda i: all_h[i + 1] - all_h[i], default=0)
        if all_h[gap_at + 1] - all_h[gap_at] >= 0.18 * all_h[-1]:
            x_glob = float(np.median(all_h[:gap_at + 1]))
            cap_glob = float(np.median(all_h[gap_at + 1:]))
    net = B._piece_cnn()
    for ps in built:
        ops = net.opinions(ps) if net is not None else None
        matched = []
        for i, g in enumerate(ps):
            top = B._scan_native(g, 8) if B.CNN_RERANK_ON else None
            ch, s = (top[0] if top else B.match_native(g))
            cnn_op = ops[i] if ops is not None else None
            if cnn_op is not None and cnn_op[1] >= B.PIECE_MIN_PROB:
                ch, s = cnn_op
                src = "cnn-direct"
            elif (B.CNN_RERANK_ON and top and len(top) > 1
                    and (top[0][1] - top[1][1] < B.CNN_MARGIN
                         or top[0][1] < B.CNN_CONF
                         or (B._CNN_STEM_ALWAYS and ch in "ilI"
                             and any(c.isalpha() and c not in "ilI1"
                                     for c, _ in top[:4])))):
                vote = B._cnn_vote(g)
                if vote is not None and vote != ch \
                        and any(c == vote for c, _ in top):
                    ch = vote
                    src = "cnn-vote"
                else:
                    src = "native"
            else:
                src = "native"
            matched.append([g, ch, s, top, cnn_op, src])
        cap = B._cap_ref([(m[0], m[1], m[2]) for m in matched])
        allh = [m[0].shape[0] for m in matched]
        x_band = [h for h in allh if h <= 0.75 * cap]
        x_med = float(np.median(x_band)) if x_band else None

        def _case_of(g, ch):
            if ch not in B.SAME_SHAPE:
                return ch
            hgt = g.shape[0]
            if x_med is not None:
                return ch.upper() if hgt >= 1.25 * x_med else ch.lower()
            if x_glob is not None and cap_glob is not None:
                if hgt <= 1.15 * x_glob:
                    return ch.lower()
                if hgt >= 0.85 * cap_glob:
                    return ch.upper()
            return ch.lower() if hgt < 0.87 * cap else ch.upper()

        for m in matched:
            m[1] = _case_of(m[0], m[1])
        word_has_up = sum(1 for m in matched
                          if m[1].isupper() and m[1] not in B.SAME_SHAPE
                          and m[0].shape[1] > 7) >= 2
        word_has_dig = B._DIGIT_CTX_ON and any(
            m[1].isdigit() and m[2] >= 0.95 for m in matched)
        word_has_let = any(m[1].isalpha() and m[2] >= 0.9
                           and m[0].shape[1] > 4 for m in matched)
        chars = []
        for g, ch, s, top, cnn_op, src in matched:
            pre_ctx = ch
            if ch == "O" and word_has_dig:
                ch = "0"
            elif ch == "0" and not word_has_dig and any(
                    m[1].isalpha() and m[1] not in ("O", "0")
                    for m in matched):
                ch = "O"
            elif (B._LD_CTX_ON and top and ch.isdigit() and word_has_let
                    and not word_has_dig and len(ps) > 1):
                ch_alt = next((c for c, s2 in top if c.isalpha()
                               and s >= s2 and s - s2 < 0.06), None)
                if ch_alt is not None:
                    ch = _case_of(g, ch_alt)
            elif (B._LD_CTX_ON and top and ch.isalpha() and word_has_dig
                    and len(ps) > 1):
                ch_alt = next((c for c, s2 in top if c.isdigit()
                               and s >= s2 and s - s2 < 0.06), None)
                if ch_alt is not None:
                    ch = ch_alt
            ch = B._narrow_case_resolve(g, ch, word_has_up)
            pieces.append({"char": ch, "pre_ctx": pre_ctx, "score": s,
                           "src": src, "top": top, "cnn": cnn_op,
                           "h": g.shape[0], "w": g.shape[1],
                           "ink": int(g.sum()), "mask": g,
                           "word_has_up": word_has_up,
                           "word_has_dig": word_has_dig})
            chars.append(ch)
            conf.append(s)
        if chars:
            out.append("".join(chars))
    return " ".join(out), pieces


def main() -> int:
    gal = ROOT / "reports/glyph-residue/2026-10-15/gallery"
    gal.mkdir(parents=True, exist_ok=True)
    evidence = {}
    for iid, (suite, got_r1, label) in ITEMS.items():
        img = Image.open(ROOT / "data" / suite / "images" / f"{iid}.png")
        text, pieces = read_with_evidence(img)
        shipping = fix_line(text)
        # align: one piece per output char (pieces -> text in order)
        chars = [p["char"] for p in pieces]
        rows = []
        gl, rl = list(label), list(shipping)
        # per-position diff on the piece sequence vs label chars
        lab_pos = 0
        seq = []
        for p in pieces:
            seq.append(p)
        # simple positional walk: compare joined chars vs label
        joined = "".join(chars)
        # per-position diff (same-length or not): walk both with the
        # word structure preserved via spaces
        row = {"id": iid, "raw": text, "shipping": shipping,
               "got_r1": got_r1, "label": label, "pieces": []}
        for idx, p in enumerate(seq):
            entry = {"i": idx, "char": p["char"], "pre_ctx": p["pre_ctx"],
                     "score": round(p["score"], 4), "src": p["src"],
                     "h": p["h"], "w": p["w"], "ink": p["ink"],
                     "top": [(c, round(s, 4)) for c, s in p["top"]]
                            if p["top"] else None,
                     "cnn": [p["cnn"][0], round(p["cnn"][1], 4)]
                            if p["cnn"] else None,
                     "word_has_up": p["word_has_up"],
                     "word_has_dig": p["word_has_dig"]}
            row["pieces"].append(entry)
            # save mask crop
            m = p["mask"]
            im = Image.fromarray((255 - m.astype(np.uint8) * 255))
            im = im.resize((m.shape[1] * 8, m.shape[0] * 8), Image.NEAREST)
            im.save(gal / f"{iid}-p{idx:02d}-{p['char'].replace(' ','_')}.png")
        evidence[iid] = row
        same = "RECOVERED" if shipping == label else \
               ("raw-equal" if text == got_r1 else "DIFFERS-from-r1")
        print(f"{iid:18s} raw={text!r} shipping={shipping!r} "
              f"[r1 {got_r1!r}] label={label!r} -> {same}")
    out = ROOT / "reports/glyph-residue/2026-10-15/evidence.json"
    for v in evidence.values():
        for p in v["pieces"]:
            p.pop("mask", None)
    out.write_text(json.dumps(evidence, indent=1))
    print("evidence json:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
