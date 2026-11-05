import json
import os
import tempfile
import unittest

from keysmith.demo import DemoStore, DemoError


class TestDemoStore(unittest.TestCase):
    def _store(self, manifest):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)
        return DemoStore(demo_dir=d), d

    def test_missing_manifest_is_empty(self):
        store = DemoStore(demo_dir=tempfile.mkdtemp())
        self.assertEqual(store.list(), [])

    def test_lists_and_hides_nothing_secret(self):
        store, _ = self._store({"demos": [
            {"id": "demo-rocky", "wallet_type": "metamask",
             "owner_story": "Ada forgot it.", "notes": "dog Rocky",
             "answers": {"names": "Rocky"}, "wallet_file": "v.json"},
        ]})
        listed = store.list()
        self.assertEqual(listed[0]["id"], "demo-rocky")
        self.assertNotIn("answers", listed[0])
        self.assertNotIn("wallet_file", listed[0])

    def test_password_in_manifest_rejected(self):
        store, _ = self._store({"demos": [
            {"id": "x", "wallet_type": "metamask", "password": "leaked"},
        ]})
        with self.assertRaises(DemoError):
            store.load()

    def test_get_and_answers(self):
        store, _ = self._store({"demos": [
            {"id": "d1", "wallet_type": "metamask", "answers": {"names": "Milo"}},
        ]})
        demo = store.get("d1")
        self.assertIsNotNone(demo)
        self.assertEqual(demo.answers["names"], "Milo")
        self.assertIsNone(store.get("nope"))


if __name__ == "__main__":
    unittest.main()
