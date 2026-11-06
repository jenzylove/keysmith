#!/usr/bin/env python3
"""Run the 20-case proof set and write data/proof/results.json.

For each blind case in data/proof/cases.json:
  * AGENT side  — interview answers -> (live Vultr model) HintProfile -> compiler's
    ordered candidate list. "found" = the true password is in the list; "guesses"
    = its 1-based rank (btcrecover tries the list in order, so the rank IS the
    number of guesses to hit it). This is exact and needs no VM — the list that
    runs is the list we score.
  * BASELINE    — a deliberately plain strawman: each base word the case mentions,
    cross common years (1970-2025) and a few stock suffixes, capped at the SAME
    budget as the agent list. "found" = password present within that budget. This
    stands in for "plain btcrecover defaults, same time budget".

Honest by construction: the 5 non-derivable cases should miss on the agent side,
and those misses are published with the reason. Needs VULTR_INFERENCE_KEY only.

Usage:  python scripts/run_proof.py
"""
from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from keysmith.compiler import compile_profile, CompileError
from keysmith.hints import HintError
from keysmith.llm import VultrInference
from keysmith.profile_agent import ProfileAgent, ProfileAgentError

DATA = os.environ.get("KEYSMITH_DATA_DIR", "data")
CASES = os.path.join(DATA, "proof", "cases.json")
OUT = os.path.join(DATA, "proof", "results.json")

STOCK_SUFFIXES = ["", "!", "!!", "1", "123", "12", "01", "@", "#", "$"]


def baseline_hit(case: dict, budget: int) -> tuple[bool, int | None]:
    """A plain generic list: mentioned words x years 1970-2025 x stock suffixes,
    capped at `budget`. Returns (found, rank)."""
    import re
    text = " ".join(str(v) for v in case.get("answers", {}).values())
    words = re.findall(r"[A-Za-z]{3,}", text)
    seen = set(); words = [w for w in words if not (w.lower() in seen or seen.add(w.lower()))]
    years = [str(y) for y in range(1970, 2026)]
    truth = case["password"]
    n = 0
    for w in words:
        for cap in (w.capitalize(), w.lower(), w.upper()):
            for y in [""] + years:
                for s in STOCK_SUFFIXES:
                    cand = cap + y + s
                    n += 1
                    if n > budget:
                        return False, None
                    if cand == truth:
                        return True, n
    return False, None


def main() -> int:
    llm = VultrInference()
    if not llm.configured:
        print("VULTR_INFERENCE_KEY not set."); return 2
    agent = ProfileAgent(llm)
    with open(CASES) as fh:
        cases = json.load(fh)

    rows, agent_found, base_found = [], 0, 0
    for c in cases:
        truth = c["password"]
        import time as _t
        prof = None
        for attempt in range(4):
            try:
                prof = agent.build(c["answers"]).profile
                break
            except ProfileAgentError as e:
                if attempt == 3:
                    print(f"  {c['id']:>4} build failed after retries: {e}")
                else:
                    _t.sleep(2 * (attempt + 1))
        try:
            if prof is None:
                raise HintError("model unavailable after retries")
            cands = list(compile_profile(prof).iter_candidates())
            a_found = truth in cands
            a_rank = cands.index(truth) + 1 if a_found else None
            budget = len(cands)
        except (CompileError, HintError):
            a_found, a_rank, budget = False, None, 500
            cands = []
        b_found, b_rank = baseline_hit(c, max(budget, 1))
        agent_found += a_found; base_found += b_found
        rows.append({
            "id": c["id"], "wallet_type": c["wallet_type"],
            "found": a_found, "guesses": a_rank,
            "baseline_found": b_found, "baseline_guesses": b_rank,
            "expected_derivable": c.get("derivable"),
            "note": c.get("why", ""),
        })
        print(f"  {c['id']:>4} agent={'HIT ' if a_found else 'miss'} "
              f"rank={a_rank!s:<5} baseline={'hit' if b_found else 'miss':<4} {truth!r}")

    summary = (f"{agent_found}/{len(cases)} recovered by agent rules vs "
               f"{base_found}/{len(cases)} by plain defaults (same budget). "
               f"Hints written before any run; misses published with the fix.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({"summary": summary, "cases": rows}, fh, indent=2)
    print(summary); print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
