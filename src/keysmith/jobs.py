"""In-memory job store and event bus.

A ``Job`` holds everything one recovery needs while it runs and nothing it should
not keep afterwards. Two hard rules, enforced here so no caller can break them:

* **Wallet bytes and seed words never leave this process.** They live only on the
  live ``Job`` object (to be streamed over SSH to the sealed VM) and are never
  written to disk, logs, SSE history, or any ``GET`` response.
* **A found password is shown once.** The live SSE push carries it to the one
  connected viewer; the replay history keeps only ``found: true``. It is never
  stored on the job or persisted.

The event bus is a set of ``asyncio.Queue``s. ``emit`` appends a redacted copy to
the replay history, folds the event into job state, and pushes the full event to
every current subscriber.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STAGES = (
    "queued", "creating_box", "sealing", "uploading", "running",
    "found", "not_found", "destroying", "destroyed", "error",
)
TERMINAL_STAGES = {"destroyed", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of an event safe to keep in replay history or persist: a found
    password is stripped; everything else is preserved."""
    if event.get("type") == "result":
        clone = dict(event)
        clone.pop("password", None)
        return clone
    return event


class Job:
    """One recovery job. Carries the secret inputs (wallet/seed) in memory only."""

    def __init__(self, wallet_type: str, *, demo_id: Optional[str] = None,
                 job_id: Optional[str] = None) -> None:
        self.id: str = job_id or uuid.uuid4().hex[:12]
        self.wallet_type: str = wallet_type
        self.demo_id: Optional[str] = demo_id
        self.created_at: str = _now()
        self.updated_at: str = self.created_at

        # Secret inputs — never serialized, never logged.
        self.wallet_bytes: Optional[bytes] = None
        self.seed_words: Optional[List[str]] = None
        self.seed_address: Optional[str] = None
        self.passwordlist: str = ""

        # Plan (safe to expose).
        self.profile: Optional[Dict[str, Any]] = None
        self.candidate_count: Optional[int] = None
        self.sample: List[str] = []
        self.estimate: Optional[Dict[str, Any]] = None
        self.model: Optional[str] = None

        # Run state (safe to expose).
        self.status: str = "new"
        self.stages: List[Dict[str, str]] = []
        self.box: Optional[Dict[str, Any]] = None
        self.seal: Optional[List[Dict[str, Any]]] = None
        self.progress: Optional[Dict[str, Any]] = None
        self.attacks: List[Dict[str, Any]] = []
        self.found: Optional[bool] = None
        self.receipt: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None

        self._history: List[Dict[str, Any]] = []
        self._subscribers: "set[asyncio.Queue]" = set()
        self._started: bool = False
        self._attack_requested: bool = False

    # --- input readiness -----------------------------------------------------

    @property
    def has_wallet_input(self) -> bool:
        return bool(self.wallet_bytes) or bool(self.seed_words)

    @property
    def plan_ready(self) -> bool:
        return bool(self.passwordlist) and self.candidate_count is not None

    @property
    def started(self) -> bool:
        return self._started

    def mark_started(self) -> None:
        self._started = True

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STAGES

    # --- event bus -----------------------------------------------------------

    def subscribe(self) -> "asyncio.Queue":
        q: "asyncio.Queue" = asyncio.Queue()
        # Replay redacted history first so a late viewer sees the run so far.
        for ev in self._history:
            q.put_nowait(ev)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue") -> None:
        self._subscribers.discard(q)

    async def emit(self, event: Dict[str, Any]) -> None:
        """Record, fold into state, and fan out one event. Awaitable so the
        Runner protocol (`emit: Callable[[dict], Awaitable[None]]`) is satisfied."""
        if "at" not in event:
            event = {**event, "at": _now()}
        self.updated_at = event["at"]
        self._fold(event)
        self._history.append(_redact_event(event))
        for q in list(self._subscribers):
            q.put_nowait(event)

    def _fold(self, event: Dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "stage":
            stage = event.get("stage", "")
            if stage:
                self.status = stage
                self.stages.append({"stage": stage, "at": event["at"]})
        elif etype == "box":
            self.box = {k: v for k, v in event.items() if k != "type"}
        elif etype == "seal":
            self.seal = event.get("checks")
        elif etype == "progress":
            self.progress = {k: event.get(k) for k in ("tried", "total", "rate")}
        elif etype == "attack":
            self.attacks.append({k: v for k, v in event.items() if k != "type"})
        elif etype == "result":
            self.found = bool(event.get("found"))
        elif etype == "receipt":
            self.receipt = event.get("receipt")
        elif etype == "error":
            self.error = event.get("message")

    # --- views ---------------------------------------------------------------

    def public_dict(self) -> Dict[str, Any]:
        """Job state for ``GET /api/jobs/{id}``. No wallet, no password."""
        return {
            "job_id": self.id,
            "wallet_type": self.wallet_type,
            "demo_id": self.demo_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "has_wallet_input": self.has_wallet_input,
            "plan_ready": self.plan_ready,
            "candidate_count": self.candidate_count,
            "estimate": self.estimate,
            "model": self.model,
            "stages": self.stages,
            "box": self.box,
            "seal": self.seal,
            "progress": self.progress,
            "attacks": self.attacks,
            "found": self.found,
            "receipt": self.receipt,
            "error": self.error,
        }

    def persist_dict(self) -> Dict[str, Any]:
        """What gets written to ``data/jobs/{id}.json`` when a job finishes.
        A deliberately narrow, secret-free record."""
        return {
            "job_id": self.id,
            "wallet_type": self.wallet_type,
            "demo_id": self.demo_id,
            "created_at": self.created_at,
            "finished_at": self.updated_at,
            "status": self.status,
            "candidate_count": self.candidate_count,
            "found": self.found,
            "receipt": self.receipt,
            "attacks": self.attacks,
            "error": self.error,
        }


class JobStore:
    """Holds live jobs, enforces the concurrency cap, and persists receipts."""

    def __init__(self, data_dir: str = "data/jobs", max_concurrent: int = 3) -> None:
        self.data_dir = data_dir
        self.max_concurrent = max_concurrent
        self._jobs: Dict[str, Job] = {}

    def create(self, wallet_type: str, *, demo_id: Optional[str] = None) -> Job:
        job = Job(wallet_type, demo_id=demo_id)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def running_count(self) -> int:
        active = {"creating_box", "sealing", "uploading", "running", "destroying"}
        return sum(1 for j in self._jobs.values() if j.status in active)

    def can_start_now(self) -> bool:
        return self.running_count() < self.max_concurrent

    def persist(self, job: Job) -> str:
        """Write the secret-free receipt record. Returns the path written."""
        os.makedirs(self.data_dir, exist_ok=True)
        path = os.path.join(self.data_dir, f"{job.id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(job.persist_dict(), fh, indent=2, sort_keys=True)
        return path
