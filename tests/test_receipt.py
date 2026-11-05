import json
import unittest

from keysmith.receipt import (
    TeardownReceipt, ReceiptError,
    MODE_PER_JOB_VM, MODE_RUNNER_CONTAINER, OUTCOME_FOUND,
)


def _base(**kw):
    d = dict(
        job_id="job-1",
        mode=MODE_RUNNER_CONTAINER,
        wallet_type="metamask",
        outcome=OUTCOME_FOUND,
        created_at="2026-11-05T12:00:00Z",
        destroyed_at="2026-11-05T12:05:00Z",
        guesses_tried=1234,
        bytes_egressed_wallet=0,
    )
    d.update(kw)
    return TeardownReceipt(**d)


class TestReceipt(unittest.TestCase):
    def test_valid_runner(self):
        _base().validate()

    def test_per_job_vm_requires_vm_id(self):
        with self.assertRaises(ReceiptError):
            _base(mode=MODE_PER_JOB_VM).validate()
        _base(mode=MODE_PER_JOB_VM, vm_id="vultr-abc").validate()

    def test_bad_mode_and_outcome(self):
        with self.assertRaises(ReceiptError):
            _base(mode="weird").validate()
        with self.assertRaises(ReceiptError):
            _base(outcome="maybe").validate()

    def test_containment_held(self):
        self.assertTrue(_base().containment_held())
        self.assertFalse(_base(bytes_egressed_wallet=512).containment_held())
        self.assertFalse(_base(network_mode="bridge").containment_held())
        self.assertFalse(_base(agent_wallet_mounts=1).containment_held())

    def test_json_round_trip_has_containment_flag(self):
        d = json.loads(_base().to_json())
        self.assertIn("containment_held", d)
        self.assertTrue(d["containment_held"])
        self.assertEqual(d["bytes_egressed_wallet"], 0)


if __name__ == "__main__":
    unittest.main()
