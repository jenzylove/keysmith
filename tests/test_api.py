import json
import unittest

from fastapi.testclient import TestClient

from keysmith.api import create_app, AppState
from keysmith.llm import LLMResult
from keysmith.profile_agent import ProfileAgent


class FakeLLM:
    configured = True

    def __init__(self, content):
        self.content = content

    def chat(self, system, user, **kw):
        return LLMResult(content=self.content, model="fake-model", latency_ms=7)


def make_client(profile_json='{"words":["Rocky"],"years":["1998","1999"],"symbols":["!"]}'):
    st = AppState()
    st.llm = FakeLLM(profile_json)        # health reports configured
    st.agent = ProfileAgent(FakeLLM(profile_json))
    app = create_app(st)
    return TestClient(app), st


class TestCatalog(unittest.TestCase):
    def test_health(self):
        client, _ = make_client()
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["runner"], "null")  # no Vultr env in tests

    def test_wallet_types(self):
        client, _ = make_client()
        r = client.get("/api/wallet-types")
        ids = {w["id"] for w in r.json()}
        self.assertEqual(ids, {"metamask", "bitcoin_core", "electrum", "blockchain", "bip39_seed"})
        for w in r.json():
            self.assertIn("speed_pw_s", w)


class TestJobFlow(unittest.TestCase):
    def test_create_requires_valid_type(self):
        client, _ = make_client()
        r = client.post("/api/jobs", json={"wallet_type": "nonsense"})
        self.assertEqual(r.status_code, 400)

    def test_hints_returns_plan_with_sample_and_estimate(self):
        client, _ = make_client()
        job_id = client.post("/api/jobs", json={"wallet_type": "metamask"}).json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/hints",
                        json={"answers": {"names": "Rocky", "years": "98 or 99", "symbols": "!"}})
        self.assertEqual(r.status_code, 200, r.text)
        plan = r.json()
        self.assertGreater(plan["candidate_count"], 0)
        self.assertLessEqual(len(plan["sample"]), 30)
        self.assertIn("expected_s", plan["estimate"])
        self.assertEqual(plan["model"], "fake-model")

    def test_sample_contains_expected_candidate(self):
        client, _ = make_client()
        job_id = client.post("/api/jobs", json={"wallet_type": "metamask"}).json()["job_id"]
        plan = client.post(f"/api/jobs/{job_id}/hints",
                           json={"answers": {"names": "Rocky", "years": "1998,1999", "symbols": "!"}}).json()
        # The compiler builds an ordered list; the true password is in it.
        self.assertIn("Rocky1999!", "\n".join(plan["sample"]))

    def test_wallet_upload_size_limit(self):
        client, _ = make_client()
        job_id = client.post("/api/jobs", json={"wallet_type": "metamask"}).json()["job_id"]
        big = b"x" * (5 * 1024 * 1024 + 1)
        r = client.post(f"/api/jobs/{job_id}/wallet",
                        files={"file": ("w.json", big, "application/json")})
        self.assertEqual(r.status_code, 413)

    def test_wallet_upload_ok(self):
        client, _ = make_client()
        job_id = client.post("/api/jobs", json={"wallet_type": "metamask"}).json()["job_id"]
        r = client.post(f"/api/jobs/{job_id}/wallet",
                        files={"file": ("w.json", b'{"vault":"x"}', "application/json")})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["bytes"], 13)

    def test_start_requires_wallet(self):
        client, _ = make_client()
        job_id = client.post("/api/jobs", json={"wallet_type": "metamask"}).json()["job_id"]
        client.post(f"/api/jobs/{job_id}/hints",
                    json={"answers": {"names": "Rocky", "years": "1999"}})
        r = client.post(f"/api/jobs/{job_id}/start")
        self.assertEqual(r.status_code, 400)

    def test_null_runner_streams_honest_error(self):
        client, _ = make_client()
        job_id = client.post("/api/jobs", json={"wallet_type": "metamask"}).json()["job_id"]
        client.post(f"/api/jobs/{job_id}/hints",
                    json={"answers": {"names": "Rocky", "years": "1999"}})
        client.post(f"/api/jobs/{job_id}/wallet",
                    files={"file": ("w.json", b'{"vault":"x"}', "application/json")})
        self.assertEqual(client.post(f"/api/jobs/{job_id}/start").status_code, 200)

        events = []
        with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                    if events[-1].get("type") == "stage" and events[-1].get("stage") == "error":
                        break
        types = [e.get("type") for e in events]
        self.assertIn("error", types)
        msg = next(e["message"] for e in events if e.get("type") == "error")
        self.assertIn("not configured", msg)

    def test_rate_limit(self):
        client, _ = make_client()
        codes = [client.post("/api/jobs", json={"wallet_type": "metamask"}).status_code
                 for _ in range(6)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)


class TestProof(unittest.TestCase):
    def test_proof_endpoint(self):
        client, _ = make_client()
        r = client.get("/api/proof")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        # Either the honest "not run" status, or real results (summary + cases).
        self.assertTrue("status" in body or ("summary" in body and "cases" in body),
                        f"unexpected proof payload: {body}")


if __name__ == "__main__":
    unittest.main()
