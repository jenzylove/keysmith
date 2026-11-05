"""Local dev/demo server — NOT the production path.

Boots the real FastAPI app but swaps in:
  * a FakeLLM (so the interview works offline, no Vultr key), and
  * a FakeRunner that scripts a realistic sealed-box run (stages, seal checks,
    progress, the containment break-in test, a found password, a teardown receipt).

The shipped default is still NullRunner (see runner.build_default_runner); this
file exists only to exercise and screenshot the UI without live Vultr. Usage:

    python scripts/devserver.py            # serves on http://127.0.0.1:8000
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from keysmith.llm import LLMResult  # noqa: E402
from keysmith.profile_agent import ProfileAgent  # noqa: E402
from keysmith.receipt import TeardownReceipt, MODE_PER_JOB_VM, OUTCOME_FOUND  # noqa: E402


DEMO_PASSWORD = "Rocky1999!"  # the FakeRunner "finds" this; real runs never hardcode.


class FakeLLM:
    configured = True

    def chat(self, system, user, **kw):
        # A plausible profile for the demo story (dog Rocky, late 90s, "!").
        prof = {"words": ["Rocky"], "years": ["1998", "1999"], "symbols": ["!"],
                "case_variants": True}
        return LLMResult(content=json.dumps(prof), model="deepseek-v4.1-flash-1017",
                         latency_ms=1840)


class FakeRunner:
    name = "vm"

    async def run(self, job, emit):
        await emit({"type": "stage", "stage": "creating_box"})
        await asyncio.sleep(0.6)
        await emit({"type": "box", "vm_id": "a1b2c3d4", "region": "lhr",
                    "plan": "vc2-2c-4gb", "ip_hidden": True})
        await emit({"type": "stage", "stage": "sealing"})
        await asyncio.sleep(0.5)
        await emit({"type": "seal", "checks": [
            {"name": "runtime", "value": "runsc"},
            {"name": "network", "value": "none"},
            {"name": "wallet_mount", "value": "read only"},
            {"name": "agent_wallet_access", "value": "none"},
            {"name": "vm_egress", "value": "blocked"},
        ]})
        await emit({"type": "stage", "stage": "uploading"})
        await emit({"type": "log", "line": "wallet and candidate list uploaded over SSH"})
        await asyncio.sleep(0.4)
        await emit({"type": "stage", "stage": "running"})
        total = job.candidate_count or 108
        for frac in (0.15, 0.35, 0.6, 0.85):
            tried = int(total * frac)
            await emit({"type": "progress", "tried": tried, "total": total, "rate": 690.0})
            await emit({"type": "log", "line": f"tried {tried}/{total}  …{DEMO_PASSWORD[:2]}***"})
            await asyncio.sleep(0.5)
        await emit({"type": "progress", "tried": total, "total": total, "rate": 690.0})
        await emit({"type": "stage", "stage": "found"})
        await emit({"type": "log", "line": "Password found."})
        await emit({"type": "result", "found": True, "password": DEMO_PASSWORD})
        await emit({"type": "stage", "stage": "destroying"})
        await asyncio.sleep(0.4)
        await emit({"type": "stage", "stage": "destroyed"})
        r = TeardownReceipt(
            job_id=job.id, mode=MODE_PER_JOB_VM, wallet_type=job.wallet_type,
            outcome=OUTCOME_FOUND, created_at="2026-11-05T22:00:00+00:00",
            destroyed_at="2026-11-05T22:02:13+00:00", guesses_tried=total,
            bytes_egressed_wallet=0, vm_id="a1b2c3d4",
            api_delete_status="HTTP 204 deleted", network_mode="none",
            agent_wallet_mounts=0,
        )
        await emit({"type": "receipt", "receipt": r.to_dict()})

    async def attack(self, job, emit):
        await asyncio.sleep(0.3)
        await emit({"type": "attack", "step": "read wallet from agent box",
                    "command": "cat /wallet/wallet.dat",
                    "result": "cat: /wallet/wallet.dat: No such file or directory", "held": True})
        await asyncio.sleep(0.3)
        await emit({"type": "attack", "step": "outbound connect from cracker box",
                    "command": "urlopen http://1.1.1.1",
                    "result": "urlopen error [Errno 101] Network is unreachable", "held": True})


def build():
    data_dir = tempfile.mkdtemp(prefix="keysmith-dev-")
    os.makedirs(os.path.join(data_dir, "demo"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "proof"), exist_ok=True)
    # a placeholder demo wallet file so has_wallet_input is satisfied (the
    # FakeRunner scripts the result; real demos ship a real test vault)
    with open(os.path.join(data_dir, "demo", "rocky-vault.json"), "w") as fh:
        fh.write('{"data":"demo","iv":"demo","salt":"demo"}')
    with open(os.path.join(data_dir, "demo", "manifest.json"), "w") as fh:
        json.dump({"demos": [
            {"id": "demo-rocky", "wallet_type": "metamask",
             "owner_story": "Ada made this MetaMask in 2018 for an NFT drop and never opened it again.",
             "notes": "dog Rocky, year 98 or 99, maybe a '!'",
             "wallet_file": "rocky-vault.json",
             "answers": {"names": "Rocky", "years": "1998 or 1999", "symbols": "!",
                         "notes": "capital R, exclamation at the end"}},
        ]}, fh)
    # a sample proof results file so /proof renders a table
    with open(os.path.join(data_dir, "proof", "results.json"), "w") as fh:
        json.dump({"summary": "20 test wallets, hints written before any run. Agent rules vs plain defaults.",
                   "cases": [
                       {"id": "p01", "wallet_type": "metamask", "found": True, "guesses": 18, "note": "name + year + !"},
                       {"id": "p05", "wallet_type": "bitcoin_core", "found": False, "guesses": None,
                        "note": "honest miss: used a word not in the hints"},
                   ]}, fh)
    os.environ["KEYSMITH_DATA_DIR"] = data_dir
    os.environ["KEYSMITH_WEB_DIST"] = os.path.join(os.path.dirname(__file__), "..", "web", "dist")

    import importlib
    import keysmith.api as api_mod
    importlib.reload(api_mod)
    st = api_mod.AppState()
    st.llm = FakeLLM()
    st.agent = ProfileAgent(FakeLLM())
    st.runner = FakeRunner()
    return api_mod.create_app(st)


app = build()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), log_level="warning")
