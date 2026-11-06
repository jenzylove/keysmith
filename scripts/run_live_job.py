#!/usr/bin/env python3
"""Run ONE real sealed-VM recovery end to end, from a machine with SSH.

This exercises the whole live stack: the Vultr Inference interview (profile_agent),
the deterministic compiler, and the SealedVmRunner (create a job VM from the
snapshot -> seal -> SSH-push wallet + candidate list -> btcrecover under gVisor
--network none -> stream -> destroy -> teardown receipt). It also fires the
containment break-in test against the live box.

Must run where SSH works (your PC or the control VM) with these set:
  VULTR_API_KEY, VULTR_INFERENCE_KEY,
  KEYSMITH_SNAPSHOT_ID, KEYSMITH_SSHKEY_ID, KEYSMITH_SSH_KEY   (see docs/RUNBOOK.md)

Usage:
  python scripts/run_live_job.py                 # demo-rocky from data/demo
  python scripts/run_live_job.py demo-sara
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from keysmith.compiler import compile_profile
from keysmith.demo import DemoStore
from keysmith.estimator import estimate
from keysmith.jobs import Job
from keysmith.llm import VultrInference
from keysmith.profile_agent import ProfileAgent
from keysmith.runner import VmConfig, SealedVmRunner, NullRunner

DATA_DIR = os.environ.get("KEYSMITH_DATA_DIR", "data")
ESTIMATOR_KEY = {"metamask": "metamask", "bitcoin_core": "bitcoin_core_bdb",
                 "electrum": "electrum_passphrase", "blockchain": "blockchain_v3",
                 "bip39_seed": "bip39_seed"}


async def main() -> int:
    demo_id = sys.argv[1] if len(sys.argv) > 1 else "demo-rocky"
    demos = DemoStore(demo_dir=os.path.join(DATA_DIR, "demo")).load()
    demo = demos.get(demo_id)
    if not demo:
        print(f"no demo {demo_id!r}; have: {[d['id'] for d in demos.list()]}")
        return 2

    cfg = VmConfig.from_env()
    if cfg is None:
        print("Vultr runner not configured. Set VULTR_API_KEY, KEYSMITH_SNAPSHOT_ID, "
              "KEYSMITH_SSHKEY_ID, KEYSMITH_SSH_KEY. (See docs/RUNBOOK.md.)")
        return 2
    runner = SealedVmRunner(cfg)

    # Build the real plan from the demo's interview answers via the live model.
    llm = VultrInference()
    if not llm.configured:
        print("VULTR_INFERENCE_KEY not set.")
        return 2
    print(f"[plan] interviewing model for {demo_id} …")
    result = ProfileAgent(llm).build(demo.answers)
    plan = compile_profile(result.profile)
    candidates = list(plan.iter_candidates())

    job = Job(demo.wallet_type, demo_id=demo_id)
    job.wallet_bytes = demos.wallet_bytes(demo)
    if demo.seed:
        job.seed_words = list(demo.seed.get("words", []))
        job.seed_address = demo.seed.get("address")
    job.passwordlist = "\n".join(candidates) + "\n"
    job.candidate_count = len(candidates)
    est = estimate(job.candidate_count, ESTIMATOR_KEY[job.wallet_type], vcpus=cfg.vcpus)
    print(f"[plan] model={result.model} candidates={job.candidate_count} "
          f"expected≈{est.expected_low_s:.0f}-{est.expected_high_s:.0f}s")

    async def emit(ev: dict) -> None:
        t = ev.get("type")
        if t == "stage":
            print(f"  [stage] {ev['stage']}")
        elif t == "box":
            print(f"  [box] {ev.get('vm_id')} {ev.get('region')} {ev.get('plan')}")
        elif t == "seal":
            print("  [seal] " + ", ".join(f"{c['name']}={c['value']}" for c in ev.get("checks", [])))
        elif t == "progress":
            print(f"  [progress] {ev.get('tried')}/{ev.get('total')} @ {ev.get('rate')}/s")
        elif t == "attack":
            print(f"  [attack] {ev['step']}: {ev['result']!r} held={ev['held']}")
        elif t == "result":
            print(f"  [result] found={ev.get('found')}"
                  + (f" password={ev.get('password')!r}" if ev.get("found") else ""))
        elif t == "receipt":
            r = ev["receipt"]
            print(f"  [receipt] containment_held={r['containment_held']} "
                  f"vm={r['vm_id']} outcome={r['outcome']} egress={r['bytes_egressed_wallet']} "
                  f"delete={r['api_delete_status']}")
        elif t == "log":
            print(f"    · {ev['line']}")
        elif t == "error":
            print(f"  [error] {ev['message']}")

    print(f"[run] launching sealed job for {demo_id} …")
    # Fire the containment attack mid-run once the box is sealed.
    attack_started = {"done": False}
    orig_emit = emit
    async def emit_and_attack(ev: dict) -> None:
        await orig_emit(ev)
        if ev.get("type") == "seal" and not attack_started["done"]:
            attack_started["done"] = True
            asyncio.create_task(runner.attack(job, orig_emit))

    await runner.run(job, emit_and_attack)
    print("[done] job finished; VM destroyed. Password (if found) was shown once above "
          "and is not stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
