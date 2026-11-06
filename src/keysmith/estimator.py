"""Honest time estimator.

time = candidate_count / (passwords_per_second on the job VM for this wallet type)

The product promise is that we never show a single fake number. We show a range
and the reasoning, and we distinguish worst case (full scan) from expected
(found about halfway through an ordered list).

Baseline speeds come from btcrecover's own published 2026 benchmark (see
docs/spikes/btcrecover.md), measured on a 16-thread i7-10700K. They are
placeholders until Phase 2 overwrites them with a real measurement on the chosen
Vultr instance, via ``benchmark.py`` on that VM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# Wallet type -> passwords/sec on a 16-thread i7-10700K (btcrecover 2026 bench).
# Source: docs/spikes/btcrecover.md. Override per-run with a live VM figure.
BASELINE_PW_PER_SEC_16T: Dict[str, float] = {
    "bitcoin_core_bdb": 82.6,
    "bitcoin_core_sqlite": 22.9,
    "blockchain_v2": 431.0,
    "blockchain_v3": 698.0,
    "metamask": 690.0,
    "electrum_passphrase": 4673.0,
    "bip39_passphrase": 2403.0,
    "bip39_seed": 36000.0,
}

BASELINE_THREADS = 16

# How wide we draw the honest band around the nominal rate.
SLOW_FACTOR = 0.5   # could run half as fast
FAST_FACTOR = 2.0   # could run twice as fast


class EstimatorError(ValueError):
    pass


@dataclass
class Estimate:
    wallet_type: str
    candidate_count: int
    pw_per_sec: float          # the rate actually used (scaled to the VM)
    worst_case_low_s: float    # full scan, optimistic rate
    worst_case_high_s: float   # full scan, pessimistic rate
    expected_low_s: float      # ~half the list, optimistic rate
    expected_high_s: float     # ~half the list, pessimistic rate
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "wallet_type": self.wallet_type,
            "candidate_count": self.candidate_count,
            "pw_per_sec": round(self.pw_per_sec, 2),
            "worst_case_s": [round(self.worst_case_low_s, 1), round(self.worst_case_high_s, 1)],
            "expected_s": [round(self.expected_low_s, 1), round(self.expected_high_s, 1)],
            "reasoning": self.reasoning,
        }


def _scaled_rate(wallet_type: str, vcpus: int, measured_pw_per_sec: float | None) -> float:
    if measured_pw_per_sec is not None:
        if measured_pw_per_sec <= 0:
            raise EstimatorError("measured_pw_per_sec must be > 0")
        return measured_pw_per_sec
    if wallet_type not in BASELINE_PW_PER_SEC_16T:
        raise EstimatorError(
            f"unknown wallet_type {wallet_type!r}; known: "
            f"{sorted(BASELINE_PW_PER_SEC_16T)}"
        )
    if vcpus < 1:
        raise EstimatorError("vcpus must be >= 1")
    base = BASELINE_PW_PER_SEC_16T[wallet_type]
    # Linear scaling by thread count is a rough approximation; the band around
    # the nominal rate absorbs the error, and Phase 2 replaces this with a
    # measured figure.
    return base * (vcpus / BASELINE_THREADS)


def estimate(candidate_count: int, wallet_type: str, *, vcpus: int = 4,
             measured_pw_per_sec: float | None = None) -> Estimate:
    """Estimate time to try ``candidate_count`` guesses.

    Pass ``measured_pw_per_sec`` once Phase 2 has a real rate from the job VM;
    otherwise a baseline is scaled from 16 threads to ``vcpus``.
    """
    if candidate_count < 0:
        raise EstimatorError("candidate_count must be >= 0")

    rate = _scaled_rate(wallet_type, vcpus, measured_pw_per_sec)
    nominal = candidate_count / rate                     # full scan, nominal rate
    worst_low = nominal / FAST_FACTOR
    worst_high = nominal / SLOW_FACTOR
    exp_low = (nominal / 2) / FAST_FACTOR
    exp_high = (nominal / 2) / SLOW_FACTOR

    src = ("measured on the job VM" if measured_pw_per_sec is not None
           else f"scaled from a 16-thread baseline to {vcpus} vCPU")
    reasoning = (
        f"{candidate_count:,} candidates / ~{rate:,.0f} guesses/sec "
        f"({wallet_type}, {src}). Expected assumes the password is found about "
        f"halfway through the ordered list; worst case is a full scan. Rate band "
        f"is x{SLOW_FACTOR}-x{FAST_FACTOR}."
    )
    return Estimate(
        wallet_type=wallet_type,
        candidate_count=candidate_count,
        pw_per_sec=rate,
        worst_case_low_s=worst_low,
        worst_case_high_s=worst_high,
        expected_low_s=exp_low,
        expected_high_s=exp_high,
        reasoning=reasoning,
    )


def human_duration(seconds: float) -> str:
    """Short human string for a duration, for the plan screen."""
    s = float(seconds)
    if s < 1:
        return "under a second"
    units = [("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)]
    for name, size in units:
        if s >= size:
            n = s / size
            return f"{n:.0f} {name}{'s' if round(n) != 1 else ''}"
    return "under a second"
