import unittest

from keysmith.hints import HintProfile, HintError


class TestHintProfile(unittest.TestCase):
    def test_valid_minimal(self):
        HintProfile(words=["rocky"]).validate()

    def test_old_password_only_is_enough(self):
        HintProfile(old_passwords=["hunter2"]).validate()

    def test_empty_profile_rejected(self):
        with self.assertRaises(HintError):
            HintProfile().validate()

    def test_blank_words_do_not_count_as_seed(self):
        with self.assertRaises(HintError):
            HintProfile(words=["   ", ""]).validate()

    def test_non_numeric_year_rejected(self):
        with self.assertRaises(HintError):
            HintProfile(words=["rocky"], years=["nineteen"]).validate()

    def test_bad_separator_rejected(self):
        with self.assertRaises(HintError):
            HintProfile(words=["rocky"], separators=["/"]).validate()

    def test_len_bounds(self):
        with self.assertRaises(HintError):
            HintProfile(words=["x"], min_len=5, max_len=3).validate()
        with self.assertRaises(HintError):
            HintProfile(words=["x"], min_len=0).validate()

    def test_cleaned_dedupes_and_strips(self):
        p = HintProfile(words=[" rocky ", "rocky", "Bella"]).cleaned()
        self.assertEqual(p.words, ["rocky", "Bella"])

    def test_round_trip_dict(self):
        p = HintProfile(words=["rocky"], years=["1998"], use_leet=True)
        self.assertEqual(HintProfile.from_dict(p.to_dict()), p)

    def test_unknown_field_rejected(self):
        with self.assertRaises(HintError):
            HintProfile.from_dict({"words": ["x"], "bogus": 1})


if __name__ == "__main__":
    unittest.main()
