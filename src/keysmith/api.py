"""Keysmith HTTP API + static web app.

FastAPI app serving the routes in docs/ARCHITECTURE.md and the built web app at
``/`` with SPA fallback. The contract is strict about secrecy:

* No wallet bytes, seed words, or found passwords ever appear in a ``GET``
  response, a log line, or a file. The job store enforces it; the routes here
  only ever expose ``public_dict()`` / the plan / the demo listing.
* The run is never faked: with no runner configured the app uses ``NullRunner``,
  which emits an honest "not configured" error.

Run with: ``uvicorn keysmith.api:app`` (the control VM puts Caddy in front).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse

from . import estimator as est
from .compiler import compile_profile, CompileError
from .demo import DemoStore, DemoError
from .hints import HintError
from .jobs import JobStore, Job
from .llm import VultrInference, DEFAULT_MODEL
from .profile_agent import ProfileAgent, ProfileAgentError
from .runner import Runner, build_default_runner

# --- static config -----------------------------------------------------------

MAX_WALLET_BYTES = 5 * 1024 * 1024
RATE_LIMIT_PER_HOUR = 5
VM_VCPUS = 2  # vc2-2c-4gb

WEB_DIST = os.environ.get(
    "KEYSMITH_WEB_DIST",
    os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist"),
)
DATA_DIR = os.environ.get("KEYSMITH_DATA_DIR", "data")

# wallet type id -> (label, input, estimator key, notes)
WALLET_TYPES = [
    ("metamask", "MetaMask password", "file", "metamask",
     "The password that unlocks MetaMask on your browser, not your seed phrase. We open your local vault file so you can log back in."),
    ("bitcoin_core", "Bitcoin Core password", "file", "bitcoin_core_bdb",
     "The password for a Bitcoin Core wallet.dat file. Slow by design, so smart guesses matter most here."),
    ("electrum", "Electrum password", "file", "electrum_passphrase",
     "The password that unlocks an Electrum wallet file."),
    ("blockchain", "Blockchain.com password", "file", "blockchain_v3",
     "The password for a Blockchain.com wallet backup (the wallet.aes.json file)."),
]
WALLET_IDS = {w[0] for w in WALLET_TYPES}
WALLET_ESTIMATOR_KEY = {w[0]: w[3] for w in WALLET_TYPES}
BIP39_WORDLIST_SIZE = 2048


class AppState:
    def __init__(self) -> None:
        self.jobs = JobStore(data_dir=os.path.join(DATA_DIR, "jobs"))
        self.demos = DemoStore(demo_dir=os.path.join(DATA_DIR, "demo"))
        self.llm = VultrInference()
        self.agent = ProfileAgent(self.llm)
        self.runner: Runner = build_default_runner()
        self.sem = asyncio.Semaphore(self.jobs.max_concurrent)
        self._rate: Dict[str, Deque[float]] = defaultdict(deque)

    def client_ip(self, request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def rate_ok(self, ip: str) -> bool:
        now = time.time()
        window = self._rate[ip]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_HOUR:
            return False
        window.append(now)
        return True


def create_app(state: Optional[AppState] = None) -> FastAPI:
    app = FastAPI(title="Keysmith", docs_url=None, redoc_url=None)
    st = state or AppState()
    app.state.ks = st

    # --- health & catalog ---------------------------------------------------

    @app.get("/api/health")
    async def health():
        return {
            "ok": True,
            "runner": getattr(st.runner, "name", "unknown"),
            "model": DEFAULT_MODEL if st.llm.configured else None,
            "llm_configured": st.llm.configured,
        }

    @app.get("/api/wallet-types")
    async def wallet_types():
        out = []
        for wid, label, inp, ekey, notes in WALLET_TYPES:
            speed = est.BASELINE_PW_PER_SEC_16T[ekey] * (VM_VCPUS / est.BASELINE_THREADS)
            out.append({"id": wid, "label": label, "input": inp,
                        "speed_pw_s": round(speed, 1), "notes": notes})
        return out

    @app.get("/api/demo")
    async def demo_list():
        try:
            return st.demos.list()
        except DemoError as exc:
            raise HTTPException(500, str(exc))

    # --- job lifecycle ------------------------------------------------------

    @app.post("/api/jobs")
    async def create_job(request: Request):
        ip = st.client_ip(request)
        if not st.rate_ok(ip):
            raise HTTPException(429, "too many recoveries from here in the last hour; please wait.")
        body = await _json_body(request)
        demo_id = body.get("demo_id")
        wallet_type = body.get("wallet_type")

        if demo_id:
            demo = st.demos.get(demo_id)
            if not demo:
                raise HTTPException(404, f"no demo wallet {demo_id!r}")
            job = st.jobs.create(demo.wallet_type, demo_id=demo_id)
            # Preload the demo wallet/seed so the user only drives the interview.
            try:
                if demo.wallet_file:
                    job.wallet_bytes = st.demos.wallet_bytes(demo)
                if demo.seed:
                    job.seed_words = list(demo.seed.get("words", []))
                    job.seed_address = demo.seed.get("address")
            except DemoError as exc:
                raise HTTPException(500, str(exc))
            return {"job_id": job.id, "demo_id": demo_id,
                    "prefill_answers": demo.answers}

        if wallet_type not in WALLET_IDS:
            raise HTTPException(400, f"wallet_type must be one of {sorted(WALLET_IDS)}")
        job = st.jobs.create(wallet_type)
        return {"job_id": job.id}

    @app.post("/api/jobs/{job_id}/hints")
    async def submit_hints(job_id: str, request: Request):
        job = _require_job(st, job_id)
        body = await _json_body(request)
        answers = body.get("answers", {})
        if not isinstance(answers, dict):
            raise HTTPException(400, "answers must be an object")

        # Seed wallets don't use a password hint profile; plan from the seed space.
        if job.wallet_type == "bip39_seed":
            return _seed_plan(job)

        try:
            result = st.agent.build(answers)
        except ProfileAgentError as exc:
            raise HTTPException(400, str(exc))
        try:
            plan = compile_profile(result.profile)
            candidates = list(plan.iter_candidates())
        except (CompileError, HintError) as exc:
            raise HTTPException(400, str(exc))

        job.profile = result.profile.to_dict()
        job.passwordlist = "\n".join(candidates) + "\n"
        job.candidate_count = len(candidates)
        job.sample = candidates[:30]
        job.model = result.model

        ekey = WALLET_ESTIMATOR_KEY[job.wallet_type]
        estimate = est.estimate(job.candidate_count, ekey, vcpus=VM_VCPUS)
        job.estimate = estimate.to_dict()
        return {
            "profile": job.profile,
            "candidate_count": job.candidate_count,
            "sample": job.sample,
            "estimate": job.estimate,
            "model": result.model,
            "llm_ms": result.llm_ms,
        }

    @app.post("/api/jobs/{job_id}/wallet")
    async def upload_wallet(job_id: str, request: Request):
        job = _require_job(st, job_id)
        ctype = request.headers.get("content-type", "")
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise HTTPException(400, "expected a file field named 'file'")
            data = await upload.read()
            if len(data) > MAX_WALLET_BYTES:
                raise HTTPException(413, "wallet file is larger than 5 MB")
            if not data:
                raise HTTPException(400, "the wallet file was empty")
            job.wallet_bytes = data
            return {"ok": True, "bytes": len(data)}

        body = await _json_body(request)
        words = body.get("seed_words")
        address = body.get("address")
        if not isinstance(words, list) or not words:
            raise HTTPException(400, "provide a file, or seed_words (with '?' for missing) + address")
        if not address:
            raise HTTPException(400, "a seed recovery needs one known address to check against")
        job.seed_words = [str(w) for w in words]
        job.seed_address = str(address)
        return {"ok": True, "bytes": 0, "seed_words": len(job.seed_words)}

    @app.post("/api/jobs/{job_id}/start")
    async def start_job(job_id: str):
        job = _require_job(st, job_id)
        if job.started:
            raise HTTPException(409, "this recovery has already started")
        if not job.has_wallet_input:
            raise HTTPException(400, "upload the wallet (or enter the seed) before starting")
        if job.wallet_type != "bip39_seed" and not job.plan_ready:
            raise HTTPException(400, "accept a plan (submit hints) before starting")
        if job.wallet_type == "bip39_seed" and job.candidate_count is None:
            _seed_plan(job)  # ensure an estimate exists
        job.mark_started()
        await job.emit({"type": "stage", "stage": "queued"})
        asyncio.create_task(_run_job(st, job))
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/attack")
    async def attack_job(job_id: str):
        job = _require_job(st, job_id)
        if not job.started:
            raise HTTPException(409, "start the recovery first; the containment test runs in the live box")
        asyncio.create_task(st.runner.attack(job, job.emit))
        return {"ok": True}

    @app.get("/api/jobs/{job_id}")
    async def job_state(job_id: str):
        job = _require_job(st, job_id)
        return job.public_dict()

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        job = _require_job(st, job_id)
        return StreamingResponse(
            _sse(job),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/proof")
    async def proof():
        path = os.path.join(DATA_DIR, "proof", "results.json")
        if not os.path.exists(path):
            return {"status": "not run"}
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # --- static web app (SPA) ----------------------------------------------

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        dist = os.path.abspath(WEB_DIST)
        if os.path.isdir(dist):
            candidate = os.path.abspath(os.path.join(dist, full_path))
            if candidate.startswith(dist) and os.path.isfile(candidate):
                return FileResponse(candidate)
            index = os.path.join(dist, "index.html")
            if os.path.isfile(index):
                return FileResponse(index)
        return JSONResponse(
            {"error": "web app not built", "hint": "web/dist is missing"}, status_code=404,
        )

    return app


# --- helpers ----------------------------------------------------------------

async def _json_body(request: Request) -> dict:
    try:
        raw = await request.body()
        if not raw:
            return {}
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "request body must be valid JSON")
    if not isinstance(data, dict):
        raise HTTPException(400, "request body must be a JSON object")
    return data


def _require_job(st: AppState, job_id: str) -> Job:
    job = st.jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"no job {job_id!r}")
    return job


def _seed_plan(job: Job) -> dict:
    """Plan for a seed recovery: the search space is the BIP39 wordlist raised to
    the number of unknown words. Honest, bounded, computed without the LLM."""
    words = job.seed_words or []
    missing = sum(1 for w in words if str(w).strip() in ("?", "", "*"))
    missing = max(missing, 1 if not job.candidate_count else missing)
    count = BIP39_WORDLIST_SIZE ** max(missing, 0) if missing else 1
    job.candidate_count = count
    job.passwordlist = ""  # seedrecover expands the space itself
    estimate = est.estimate(count, "bip39_seed", vcpus=VM_VCPUS)
    job.estimate = estimate.to_dict()
    return {
        "profile": {"missing_words": missing},
        "candidate_count": count,
        "sample": [w if str(w).strip() not in ("?", "", "*") else "????" for w in words],
        "estimate": job.estimate,
        "model": None,
        "llm_ms": 0,
    }


async def _run_job(st: AppState, job: Job) -> None:
    """Acquire a concurrency slot, run, then persist a secret-free receipt."""
    async with st.sem:
        try:
            await st.runner.run(job, job.emit)
        finally:
            try:
                st.jobs.persist(job)
            except Exception:  # pragma: no cover - persistence must not crash a run
                pass


async def _sse(job: Job):
    q = job.subscribe()
    try:
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                if job.terminal and q.empty():
                    break
                continue
            yield f"data: {json.dumps(ev)}\n\n"
            # The receipt is always a run's last event; a terminal 'error' stage
            # closes a run that never created a box.
            if ev.get("type") == "receipt":
                break
            if ev.get("type") == "stage" and ev.get("stage") == "error":
                break
    finally:
        job.unsubscribe(q)


# Module-level app for `uvicorn keysmith.api:app`.
app = create_app()
