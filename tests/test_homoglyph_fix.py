import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.homoglyph_fix import candidate_words, fix_text, fix_token  # noqa: E402


class HomoglyphFixTests(unittest.TestCase):
    def test_unique_lexicon_candidate_resolves_one_as_i_or_l(self):
        self.assertEqual(candidate_words("v1olet"), ("violet",))
        self.assertEqual(candidate_words("W1LL0W"), ("willow",))
        self.assertEqual(fix_token("v1olet", "r4"), "violet")
        self.assertEqual(fix_token("W1LL0W", "r4"), "WILLOW")

    def test_zero_maps_to_o_and_case_policies_are_explicit(self):
        self.assertEqual(candidate_words("M0ss"), ("moss",))
        self.assertEqual(fix_token("M0ss", "r4"), "Moss")
        self.assertEqual(fix_token("M0ss", "upper"), "MOss")

    def test_ambiguous_lexicon_matches_are_not_rewritten(self):
        self.assertEqual(candidate_words("1a", {"ia", "la"}), ("ia", "la"))
        # This synthetic token is not a unique match in the production vocab.
        self.assertEqual(fix_token("x1x"), "x1x")

    def test_non_scope_inputs_are_unchanged(self):
        for token in ("01", "pure", "B8acon", "x0x", "x1x"):
            with self.subTest(token=token):
                self.assertEqual(fix_token(token), token)

    def test_only_digit_positions_are_replaced(self):
        self.assertEqual(fix_token("R0setTE", "r4"), "ROsetTE")
        self.assertEqual(fix_token("R0setTE", "upper"), "ROsetTE")

    def test_text_spacing_is_preserved(self):
        self.assertEqual(fix_text("  v1olet  W1LL0W ", "r4"),
                         "  violet  WILLOW ")

    def test_invalid_case_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            fix_token("v1olet", "guess")


if __name__ == "__main__":
    unittest.main()
