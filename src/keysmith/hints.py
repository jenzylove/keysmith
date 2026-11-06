"""Hint profile: the structured memory of a wallet owner.

This is the output of the interview agent and the input to the rule compiler.
It holds *only* the fragments a person half-remembers about their own password,
never the wallet file itself. Pure data + validation, no network, no secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# Default leet substitutions people actually use. char -> replacement.
# One replacement per char keeps the candidate space bounded and honest; the
# interview agent can override this map per user (e.g. someone who always wrote
# "a" as "@").
DEFAULT_LEET: Dict[str, str] = {
    "a": "@",
    "e": "3",
    "i": "1",
    "o": "0",
    "s": "$",
    "t": "7",
}

# Separators people put between words/numbers. "" (no separator) is always tried
# and is added by the compiler, so it is not listed here.
COMMON_SEPARATORS: List[str] = ["-", "_", ".", " "]


class HintError(ValueError):
    """Raised when a hint profile is structurally invalid."""


@dataclass
class HintProfile:
    """What the user remembers. Every field is optional except that at least one
    base word *or* one old password must be present, otherwise there is nothing
    to build guesses from."""

    # Memorable base words: names, pets, places, teams, bands, etc.
    words: List[str] = field(default_factory=list)
    # Years and standalone numbers they tend to append (e.g. "1998", "07").
    years: List[str] = field(default_factory=list)
    numbers: List[str] = field(default_factory=list)
    # Trailing symbols / suffixes they favour (e.g. "!", "!!", "$").
    symbols: List[str] = field(default_factory=list)
    # Whole old passwords they remember using before, as seeds for variation.
    old_passwords: List[str] = field(default_factory=list)

    # Habits.
    use_leet: bool = False
    leet_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_LEET))
    case_variants: bool = True          # try lower / Capitalised / UPPER
    separators: List[str] = field(default_factory=list)  # from COMMON_SEPARATORS

    # Known length bounds, if the user remembers them.
    min_len: Optional[int] = None
    max_len: Optional[int] = None

    # Safety cap: the compiler refuses to build a plan larger than this many
    # candidates. Keeps a vague profile from exploding into a brute force.
    max_candidates: int = 5_000_000

    def validate(self) -> "HintProfile":
        """Check structure. Returns self so it can be chained. Raises HintError."""
        has_seed = bool(self._clean(self.words)) or bool(self._clean(self.old_passwords))
        if not has_seed:
            raise HintError("need at least one base word or one old password to build guesses")

        for name in ("words", "years", "numbers", "symbols", "old_passwords", "separators"):
            val = getattr(self, name)
            if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
                raise HintError(f"{name} must be a list of strings")

        for name in ("years", "numbers"):
            for v in self._clean(getattr(self, name)):
                if not v.isdigit():
                    raise HintError(f"{name} entry {v!r} is not numeric")

        for sep in self._clean(self.separators):
            if sep not in COMMON_SEPARATORS:
                raise HintError(f"separator {sep!r} is not one of {COMMON_SEPARATORS}")

        if self.min_len is not None and self.min_len < 1:
            raise HintError("min_len must be >= 1")
        if self.max_len is not None and self.max_len < 1:
            raise HintError("max_len must be >= 1")
        if (self.min_len is not None and self.max_len is not None
                and self.min_len > self.max_len):
            raise HintError("min_len cannot exceed max_len")
        if self.max_candidates < 1:
            raise HintError("max_candidates must be >= 1")
        return self

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _clean(items: List[str]) -> List[str]:
        """Strip blanks and de-duplicate, preserving order."""
        seen = set()
        out = []
        for x in items:
            x = x.strip()
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def cleaned(self) -> "HintProfile":
        """Return a copy with all string lists stripped and de-duplicated."""
        return HintProfile(
            words=self._clean(self.words),
            years=self._clean(self.years),
            numbers=self._clean(self.numbers),
            symbols=self._clean(self.symbols),
            old_passwords=self._clean(self.old_passwords),
            use_leet=self.use_leet,
            leet_map=dict(self.leet_map),
            case_variants=self.case_variants,
            separators=self._clean(self.separators),
            min_len=self.min_len,
            max_len=self.max_len,
            max_candidates=self.max_candidates,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HintProfile":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(d) - allowed
        if unknown:
            raise HintError(f"unknown hint fields: {sorted(unknown)}")
        return cls(**d)
