"""Rule compiler: HintProfile -> ordered candidate passwords.

Design choice: we emit an explicit, ordered list of full candidate passwords
(a btcrecover ``--passwordlist``), not a ``--tokenlist`` with typo flags. Reasons:

* The count is *exact* and knowable before any run, so the plan screen and the
  estimator never lie.
* What we show the user ("here are the guesses we will try, in order") is
  literally what runs. No hidden expansion.
* The product's whole thesis is a *small, smart* candidate set, so an explicit
  list is the honest representation.

Everything here is pure and deterministic. The btcrecover syntax of the emitted
file is simple (one password per line) and is verified against real btcrecover
on the Vultr VM in Phase 2; nothing here touches a wallet or the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, Iterator, List

from .hints import HintProfile, HintError


class CompileError(ValueError):
    """Raised when a profile cannot be compiled within its candidate cap."""


# --- word variant expansion --------------------------------------------------

def _leet(word: str, leet_map: Dict[str, str]) -> str:
    return "".join(leet_map.get(c.lower(), c) for c in word)


def word_variants(word: str, *, case_variants: bool, use_leet: bool,
                  leet_map: Dict[str, str]) -> List[str]:
    """Bounded, priority-ordered variants of a single base word.

    Case variants are the three forms people actually use (lower, Capitalised,
    UPPER), most-likely first. Leet is applied as a single all-substitutions
    pass per case form, not per-character combinatorially, to keep the space
    human-sized. Order matters: earlier = tried earlier.
    """
    word = word.strip()
    if not word:
        return []

    forms: List[str] = []
    if case_variants:
        forms = [word.capitalize(), word.lower(), word.upper()]
    else:
        forms = [word]

    out: List[str] = []
    seen = set()
    for f in forms:
        for v in (f, _leet(f, leet_map)) if use_leet else (f,):
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


@dataclass
class Position:
    """One slot in the password, with its ordered alternatives. An optional
    position includes "" (absent) as its last alternative."""
    name: str
    alternatives: List[str]

    def count(self) -> int:
        return len(self.alternatives)


@dataclass
class CompiledPlan:
    """The compiled guessing plan: ordered positions whose cartesian product is
    the candidate set, plus the fixed extra candidates from old passwords."""
    positions: List[Position]
    extra_candidates: List[str]   # from old_passwords + their variants
    profile: HintProfile

    # --- counting ---------------------------------------------------------

    def structural_count(self) -> int:
        """Upper bound = product of position sizes + extras, before de-dup."""
        prod = 1
        for p in self.positions:
            prod *= max(1, p.count())
        return prod + len(self.extra_candidates)

    def count(self) -> int:
        """Exact candidate count after de-duplication and length filtering."""
        n = 0
        for _ in self.iter_candidates():
            n += 1
        return n

    # --- generation -------------------------------------------------------

    def iter_candidates(self) -> Iterator[str]:
        """Yield unique candidate passwords, priority order, length-filtered."""
        seen = set()
        prof = self.profile
        lo, hi = prof.min_len, prof.max_len

        def ok(cand: str) -> bool:
            if cand in seen:
                return False
            if lo is not None and len(cand) < lo:
                return False
            if hi is not None and len(cand) > hi:
                return False
            return True

        # Extras (remembered whole passwords) first: highest prior probability.
        for cand in self.extra_candidates:
            if ok(cand):
                seen.add(cand)
                yield cand

        if not self.positions:
            return
        alt_lists = [p.alternatives for p in self.positions]
        for combo in product(*alt_lists):
            cand = "".join(combo)
            if cand and ok(cand):
                seen.add(cand)
                yield cand

    def to_passwordlist(self) -> str:
        """The btcrecover ``--passwordlist`` content: one candidate per line."""
        return "\n".join(self.iter_candidates()) + "\n"


# --- old-password variants ---------------------------------------------------

def _old_password_variants(pw: str, prof: HintProfile) -> List[str]:
    """A remembered password, plus small honest tweaks: case forms, one leet
    pass, and each remembered symbol/number appended. People reuse a password
    with a year or a '!' bumped on the end."""
    base = word_variants(pw, case_variants=prof.case_variants,
                          use_leet=prof.use_leet, leet_map=prof.leet_map)
    if not prof.case_variants and not prof.use_leet:
        base = [pw]
    out: List[str] = []
    seen = set()
    tails = [""] + list(prof.symbols) + list(prof.years) + list(prof.numbers)
    for b in base:
        for t in tails:
            v = b + t
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


# --- top-level compile -------------------------------------------------------

def compile_profile(profile: HintProfile) -> CompiledPlan:
    """Compile a validated HintProfile into an ordered CompiledPlan.

    Raises CompileError if the structural candidate count exceeds the profile's
    ``max_candidates`` cap (fail closed: never silently build a brute force).
    """
    prof = profile.cleaned().validate()

    # Build positions: [ word ] [ separator? ] [ number? ] [ symbol? ]
    positions: List[Position] = []

    word_alts: List[str] = []
    seen = set()
    for w in prof.words:
        for v in word_variants(w, case_variants=prof.case_variants,
                               use_leet=prof.use_leet, leet_map=prof.leet_map):
            if v not in seen:
                seen.add(v)
                word_alts.append(v)
    if word_alts:
        positions.append(Position("word", word_alts))

    if prof.separators and word_alts:
        # "" first (most common: no separator), then the remembered ones.
        positions.append(Position("separator", [""] + list(prof.separators)))

    num_alts = list(prof.years) + [n for n in prof.numbers if n not in prof.years]
    if num_alts:
        positions.append(Position("number", num_alts + [""]))  # optional

    if prof.symbols:
        positions.append(Position("symbol", list(prof.symbols) + [""]))  # optional

    extras: List[str] = []
    seen_extra = set()
    for pw in prof.old_passwords:
        for v in _old_password_variants(pw, prof):
            if v not in seen_extra:
                seen_extra.add(v)
                extras.append(v)

    plan = CompiledPlan(positions=positions, extra_candidates=extras, profile=prof)

    structural = plan.structural_count()
    if structural > prof.max_candidates:
        raise CompileError(
            f"plan would generate ~{structural:,} candidates, over the cap of "
            f"{prof.max_candidates:,}. Narrow the hints (fewer words, known "
            f"length, drop separators) before running."
        )
    if not extras and not word_alts:
        raise HintError("nothing to guess: no words and no old passwords survived cleaning")
    return plan
