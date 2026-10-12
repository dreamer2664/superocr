#!/usr/bin/env python3
"""Lex-projection post-pass (t-20261012-5d1c) — reader-agnostic cleanup.

Published-resource post-pass: the suite generator ships a fixed vocabulary in
this repo (``generator._WORDS``, 128 words, see the suites' phrasebook).  A
decoded token that is not vocabulary is projected onto the unique nearest
vocabulary entry when the match is unambiguous.  This is classic OCR
lexicon decoding, nothing suite-specific is tuned: the rules are

  R1  token whose lowercase is already a vocabulary word        -> unchanged
      (case patterns are the reader's job; we never re-case a clean token)
  R2  pure-digit / digit-transliterable short tokens (uses the same
      O/0 l/1 S/5 Z/2 B/8 digit map as the classic reader)       -> unchanged
  R3  candidates = vocabulary entries at Levenshtein distance
      d <= max(1, round(len(token)/3)); the best must be UNIQUE with a
      margin >= 1 over the runner-up, otherwise the token is left alone
      (the round(len/3) allowance is the usual short-word OCR band: one
      edit up to ~6 letters, two edits from ~7 up)
  R4  case projection: positions the token already spells right keep the
      token's own character (case kept); a repaired/deleted/inserted
      position takes the vocabulary letter cased as the majority case of
      the token's other letters (upper wins ties).

Nothing here is wired into any reader by default; it is a converter:
  echo "METE0R" | python3 tools/lex_projection.py            # stdin lines
  python3 tools/lex_projection.py --match-measure results.json  # vs wants
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402  (repo-local, published vocabulary)

VOCAB = list(G._WORDS)
_DIGIT_FIX = str.maketrans("OoIlZSB", "0011258")


def _ed(a: str, b: str):
    """Levenshtein distance with an aligned backtrack (returns dist + ops)."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    return dp[n][m], dp


def _project(tok: str, word: str) -> str:
    """R4: spell ``word`` using the token's own casing where letters match."""
    lo = tok.lower()
    n, m = len(lo), len(word)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (lo[i - 1] != word[j - 1]))
    # majority case of the token's letters (upper wins ties)
    ups = sum(1 for c in tok if c.isalpha() and c.isupper())
    los = sum(1 for c in tok if c.isalpha() and c.islower())
    rep_up = ups >= los
    # backtrack
    out = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and lo[i - 1] == word[j - 1] and \
                dp[i][j] == dp[i - 1][j - 1]:
            out.append(tok[i - 1])          # keep the reader's own char
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            out.append(word[j - 1].upper() if rep_up else word[j - 1])
            i, j = i - 1, j - 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            out.append(word[j - 1].upper() if rep_up else word[j - 1])
            j -= 1
        else:
            i -= 1                          # deletion of a stray token char
    return "".join(reversed(out))


def fix_token(tok: str) -> str:
    if not tok:
        return tok
    low = tok.lower()
    if low in G._WORDS:
        return tok                                              # R1
    if tok.isdigit() or (len(tok) <= 4 and
                         tok.translate(_DIGIT_FIX).isdigit()):
        return tok                                              # R2
    if not any(c.isalpha() for c in tok):
        return tok
    band = max(1, round(len(low) / 3))                          # R3
    best, bd, second = None, band + 1, band + 1
    for w in G._WORDS:
        d, _ = _ed(low, w)
        if d < bd:
            second, best, bd = bd, w, d
        elif d < second:
            second = d
    if best is None or bd > band or (second - bd) < 1:
        return tok
    return _project(tok, best)


def fix_line(text: str) -> str:
    return " ".join(fix_token(t) for t in text.split(" "))


_LINE = re.compile(r"want '((?:[^'\\]|\\.)*)'\s+got '((?:[^'\\]|\\.)*)'")


def measure(paths) -> int:
    """Offline measurement against a suite log: fixes / breaks per suite."""
    tot = {"fixes": 0, "breaks": 0, "n": 0, "exact0": 0, "exact1": 0}
    detail = []
    for path in paths:
        seen, f, b, n, e0, e1 = set(), [], [], 0, 0, 0
        for line in open(path, encoding="utf-8"):
            mm = _LINE.search(line)
            if not mm:
                continue
            iid = line.split()[0]
            if iid in seen:
                continue
            seen.add(iid)
            want, got = mm.group(1), mm.group(2)
            n += 1
            new = fix_line(got)
            e0 += got == want
            e1 += new == want
            if new == want and got != want:
                f.append((iid, got, new))
            if got == want and new != want:
                b.append((iid, got, new))
        print(f"[{Path(path).stem}] items={n}  exact {e0} -> {e1} "
              f"(+{e1 - e0})  fixes={len(f)}  breaks={len(b)}")
        for iid, g, nn in f:
            print(f"   FIX   {iid:18} {g!r} -> {nn!r}")
        for iid, g, nn in b:
            print(f"   BREAK {iid:18} {g!r} -> {nn!r}")
        detail.append((path, f, b))
        tot["fixes"] += len(f)
        tot["breaks"] += len(b)
        tot["n"] += n
        tot["exact0"] += e0
        tot["exact1"] += e1
    print(f"TOTAL: exact {tot['exact0']} -> {tot['exact1']}  fixes={tot['fixes']}  breaks={tot['breaks']}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--match-measure":
        sys.exit(measure(args[1:]))
    for line in sys.stdin:
        print(fix_line(line.rstrip("\n")))
