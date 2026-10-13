"""Experimental digit-homoglyph post-pass for lexicon tokens.

This is a measurement tool only; it is deliberately not wired into a reader.
A token must contain both a 0/1 and a letter, and replacing each digit using
(0 -> o, 1 -> i or l) must produce exactly one published vocabulary word.
Ambiguous or non-vocabulary tokens are left unchanged.

Case policy:
  r4    case the repaired positions by majority case of existing letters
        (uppercase wins ties), matching lex_projection's R4 convention.
  upper uppercase the repaired positions, an intentionally aggressive control.

Pure numbers, pure-letter tokens, and tokens with other digits are untouched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402

VOCAB = frozenset(G._WORDS)
_DIGITS = frozenset("01")


def candidate_words(token: str, vocab=VOCAB) -> tuple[str, ...]:
    """Return vocabulary matches under the scoped 0/1 homoglyph choices.

    A 0 may be ``o``. A 1 may be ``i`` or ``l``; the word list, not a fixed
    character preference, resolves which reading is possible. Matching is
    case-insensitive but all non-digit letters must otherwise match exactly.
    """
    lowered = token.lower()
    if not any(c in _DIGITS for c in token) or not any(c.isalpha() for c in token):
        return ()
    found = []
    for word in vocab:
        if len(word) != len(lowered):
            continue
        if all(
            (wc == "o" if c == "0" else wc in ("i", "l") if c == "1"
             else wc == c)
            for c, wc in zip(lowered, word)
        ):
            found.append(word)
    return tuple(sorted(found))


def fix_token(token: str, policy: str = "r4") -> str:
    """Fix a uniquely resolved mixed 0/1 word token; otherwise return it."""
    if policy not in ("r4", "upper"):
        raise ValueError("policy must be 'r4' or 'upper'")
    matches = candidate_words(token)
    if len(matches) != 1:
        return token

    word = matches[0]
    if policy == "upper":
        uppercase = True
    else:
        ups = sum(1 for c in token if c.isalpha() and c.isupper())
        lows = sum(1 for c in token if c.isalpha() and c.islower())
        uppercase = ups >= lows

    # Only repair positions occupied by 0/1. Existing letters keep the OCR
    # reader's case, as in lex_projection R4; this avoids changing extra bits.
    return "".join(
        (word[i].upper() if uppercase else word[i].lower()) if c in _DIGITS else c
        for i, c in enumerate(token)
    )


def fix_text(text: str, policy: str = "r4") -> str:
    """Apply the experimental token rule while preserving literal spaces."""
    return " ".join(fix_token(tok, policy) for tok in text.split(" "))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--policy", choices=("r4", "upper"), default="r4")
    args = ap.parse_args(argv)
    for line in sys.stdin:
        print(fix_text(line.rstrip("\n"), args.policy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
