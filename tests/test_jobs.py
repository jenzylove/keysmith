import asyncio
import json
import os
import tempfile
import unittest

from keysmith.jobs import Job, JobStore


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestJobEvents(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_stage_folds_into_status(self):
        job = Job("metamask")
        self.loop.run_until_complete(job.emit({"type": "stage", "stage": "running"}))
        self.assertEqual(job.status, "running")
        self.assertEqual(job.stages[-1]["stage"], "running")

    def test_found_password_not_persisted_or_in_history(self):
        job = Job("metamask")
        q = job.subscribe()
        self.loop.run_until_complete(
            job.emit({"type": "result", "found": True, "password": "Rocky1999!"}))
        # Live subscriber sees the password once...
        live = q.get_nowait()
        self.assertEqual(live.get("password"), "Rocky1999!")
        # ...but it is stripped from replay history and from job state.
        self.assertTrue(job.found)
        q2 = job.subscribe()
        replayed = q2.get_nowait()
        self.assertEqual(replayed.get("type"), "result")
        self.assertNotIn("password", replayed)
        self.assertNotIn("Rocky1999!", json.dumps(job.public_dict()))
        self.assertNotIn("Rocky1999!", json.dumps(job.persist_dict()))

    def test_public_dict_has_no_secrets(self):
        job = Job("metamask")
        job.wallet_bytes = b"secret-wallet-bytes"
        job.passwordlist = "guess1\nguess2\n"
        blob = json.dumps(job.public_dict())
        self.assertNotIn("secret-wallet-bytes", blob)
        self.assertNotIn("guess1", blob)

    def test_error_event_sets_error_not_terminal_status(self):
        job = Job("metamask")
        self.loop.run_until_complete(job.emit({"type": "error", "message": "nope"}))
        self.assertEqual(job.error, "nope")
        # a bare error event is not a terminal stage; only stage 'error' is.
        self.assertFalse(job.terminal)
        self.loop.run_until_complete(job.emit({"type": "stage", "stage": "error"}))
        self.assertTrue(job.terminal)


class TestJobStore(unittest.TestCase):
    def test_persist_writes_secret_free_record(self):
        with tempfile.TemporaryDirectory() as d:
            store = JobStore(data_dir=d)
            job = store.create("metamask")
            job.wallet_bytes = b"xyz"
            job.candidate_count = 108
            path = store.persist(job)
            self.assertTrue(os.path.exists(path))
            with open(path) as fh:
                saved = json.load(fh)
            self.assertEqual(saved["candidate_count"], 108)
            self.assertNotIn("wallet_bytes", saved)

    def test_concurrency_cap(self):
        store = JobStore(max_concurrent=2)
        self.assertTrue(store.can_start_now())
        j1 = store.create("metamask")
        j1.status = "running"
        j2 = store.create("metamask")
        j2.status = "creating_box"
        self.assertEqual(store.running_count(), 2)
        self.assertFalse(store.can_start_now())


if __name__ == "__main__":
    unittest.main()
