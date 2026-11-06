import unittest

from keysmith.estimator import estimate, human_duration, EstimatorError


class TestEstimator(unittest.TestCase):
    def test_basic_scaling(self):
        # 690 pw/s at 16 threads -> ~172.5 at 4 vCPU.
        e = estimate(1725, "metamask", vcpus=4)
        self.assertAlmostEqual(e.pw_per_sec, 690 * 4 / 16, places=2)
        # full scan nominal = 1725 / 172.5 = 10s; band x0.5-x2 => 5s..20s
        self.assertAlmostEqual(e.worst_case_low_s, 5.0, places=1)
        self.assertAlmostEqual(e.worst_case_high_s, 20.0, places=1)

    def test_expected_is_half_of_worst(self):
        e = estimate(1000, "metamask", vcpus=16)
        self.assertAlmostEqual(e.expected_low_s, e.worst_case_low_s / 2, places=6)
        self.assertAlmostEqual(e.expected_high_s, e.worst_case_high_s / 2, places=6)

    def test_measured_rate_overrides_baseline(self):
        e = estimate(1000, "metamask", measured_pw_per_sec=500)
        self.assertEqual(e.pw_per_sec, 500)
        self.assertIn("measured on the job VM", e.reasoning)

    def test_unknown_wallet_type(self):
        with self.assertRaises(EstimatorError):
            estimate(10, "nope")

    def test_bad_inputs(self):
        with self.assertRaises(EstimatorError):
            estimate(-1, "metamask")
        with self.assertRaises(EstimatorError):
            estimate(10, "metamask", vcpus=0)
        with self.assertRaises(EstimatorError):
            estimate(10, "metamask", measured_pw_per_sec=0)

    def test_zero_candidates(self):
        e = estimate(0, "metamask")
        self.assertEqual(e.worst_case_high_s, 0.0)

    def test_human_duration(self):
        self.assertEqual(human_duration(0.4), "under a second")
        self.assertEqual(human_duration(1), "1 second")
        self.assertEqual(human_duration(90), "2 minutes")
        self.assertEqual(human_duration(3600), "1 hour")
        self.assertEqual(human_duration(172800), "2 days")


if __name__ == "__main__":
    unittest.main()
