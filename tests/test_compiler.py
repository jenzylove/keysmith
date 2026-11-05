import unittest

from keysmith.hints import HintProfile
from keysmith.compiler import (
    compile_profile, word_variants, CompileError,
)


class TestWordVariants(unittest.TestCase):
    def test_case_variants_order(self):
        v = word_variants("rocky", case_variants=True, use_leet=False, leet_map={})
        self.assertEqual(v, ["Rocky", "rocky", "ROCKY"])

    def test_no_case_variants(self):
        v = word_variants("rocky", case_variants=False, use_leet=False, leet_map={})
        self.assertEqual(v, ["rocky"])

    def test_leet_applied(self):
        v = word_variants("sea", case_variants=False, use_leet=True,
                          leet_map={"s": "$", "e": "3", "a": "@"})
        self.assertIn("$3@", v)
        self.assertIn("sea", v)  # original kept


class TestCompile(unittest.TestCase):
    def test_exact_count_matches_generation(self):
        p = HintProfile(words=["rocky"], years=["1998", "99"], symbols=["!"],
                        case_variants=True, use_leet=False)
        plan = compile_profile(p)
        gen = list(plan.iter_candidates())
        self.assertEqual(plan.count(), len(gen))
        self.assertEqual(len(gen), len(set(gen)))  # all unique

    def test_known_candidate_present(self):
        p = HintProfile(words=["rocky"], years=["1998"], symbols=["!"])
        cands = set(compile_profile(p).iter_candidates())
        self.assertIn("Rocky1998!", cands)
        self.assertIn("rocky1998", cands)   # number optional, symbol optional

    def test_old_password_variants_come_first(self):
        p = HintProfile(old_passwords=["hunter2"], symbols=["!"], case_variants=True)
        first = next(iter(compile_profile(p).iter_candidates()))
        self.assertTrue(first.lower().startswith("hunter2"))

    def test_length_filter(self):
        p = HintProfile(words=["rocky"], years=["1998"], min_len=9, max_len=10)
        for c in compile_profile(p).iter_candidates():
            self.assertTrue(9 <= len(c) <= 10)

    def test_cap_enforced(self):
        # Many words with case+leet blows past a tiny cap -> fail closed.
        p = HintProfile(words=[f"word{i}" for i in range(50)],
                        years=[str(y) for y in range(1950, 2025)],
                        symbols=list("!@#$%"), use_leet=True,
                        max_candidates=100)
        with self.assertRaises(CompileError):
            compile_profile(p)

    def test_separator_position(self):
        p = HintProfile(words=["rocky"], years=["1998"], separators=["-"],
                        case_variants=False, use_leet=False)
        cands = set(compile_profile(p).iter_candidates())
        self.assertIn("rocky-1998", cands)
        self.assertIn("rocky1998", cands)  # "" separator also tried

    def test_passwordlist_format(self):
        p = HintProfile(words=["rocky"], years=["1998"])
        text = compile_profile(p).to_passwordlist()
        self.assertTrue(text.endswith("\n"))
        lines = [l for l in text.splitlines() if l]
        self.assertEqual(len(lines), len(set(lines)))

    def test_two_words_joined_with_separator(self):
        p = HintProfile(words=["Sara", "Max"], numbers=["7"], separators=["_"],
                        case_variants=False)
        cands = set(compile_profile(p).iter_candidates())
        self.assertIn("Sara_Max7", cands)
        self.assertIn("MaxSara", cands)

    def test_partial_leet_from_user_map(self):
        p = HintProfile(words=["Liverpool"], years=["1892"], separators=["."],
                        use_leet=True, leet_map={"s": "$", "o": "0"}, case_variants=False)
        self.assertIn("Liverp00l.1892", set(compile_profile(p).iter_candidates()))

    def test_old_password_gets_year_and_symbol(self):
        p = HintProfile(old_passwords=["summerbreeze"], years=["2011"], symbols=["!!"],
                        case_variants=False)
        self.assertIn("summerbreeze2011!!", set(compile_profile(p).iter_candidates()))


if __name__ == "__main__":
    unittest.main()
