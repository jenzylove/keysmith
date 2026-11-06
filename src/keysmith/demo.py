"""Demo wallet loader.

The public demo lets any visitor run a recovery end to end on a *test* wallet we
made with a chosen password and a written set of the owner's vague hints. These
wallets hold no mainnet funds and are labelled as test wallets.

``data/demo/manifest.json`` is the only committed part (see .gitignore). It lists,
per demo:

    {
      "id": "demo-rocky",
      "wallet_type": "metamask",
      "owner_story": "Ada made this in 2018 and forgot the password.",
      "notes": "Dog Rocky, year 98 or 99, maybe a '!'",
      "answers": { "names": "...", "years": "...", ... },   # prefilled interview
      "wallet_file": "rocky-vault.json",                     # sits next to manifest
      "seed": { "words": [...], "address": "..." }           # for bip39 demos
    }

The owner's password is **never** in the manifest or exposed by the API — the
whole point of the demo is to recover it live. The ``answers`` are the same
interview answers a real user would type, so the demo exercises the real path.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class DemoError(RuntimeError):
    pass


@dataclass
class DemoWallet:
    id: str
    wallet_type: str
    owner_story: str
    notes: str
    answers: Dict[str, str]
    wallet_file: Optional[str] = None
    seed: Optional[Dict[str, Any]] = None

    def public_dict(self) -> Dict[str, Any]:
        """Safe listing: never the password (there isn't one here) nor the file bytes."""
        return {
            "id": self.id,
            "wallet_type": self.wallet_type,
            "owner_story": self.owner_story,
            "notes": self.notes,
        }


class DemoStore:
    def __init__(self, demo_dir: str = "data/demo") -> None:
        self.demo_dir = demo_dir
        self._by_id: Dict[str, DemoWallet] = {}
        self._loaded = False

    def _manifest_path(self) -> str:
        return os.path.join(self.demo_dir, "manifest.json")

    def load(self) -> "DemoStore":
        self._by_id.clear()
        path = self._manifest_path()
        if not os.path.exists(path):
            self._loaded = True
            return self
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        items = raw.get("demos", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise DemoError("demo manifest must be a list (or {'demos': [...]})")
        for d in items:
            if "password" in d:
                # Guard: the manifest must never carry an answer key.
                raise DemoError(f"demo {d.get('id')!r} must not contain a password")
            wallet = DemoWallet(
                id=d["id"],
                wallet_type=d["wallet_type"],
                owner_story=d.get("owner_story", ""),
                notes=d.get("notes", ""),
                answers=d.get("answers", {}),
                wallet_file=d.get("wallet_file"),
                seed=d.get("seed"),
            )
            self._by_id[wallet.id] = wallet
        self._loaded = True
        return self

    def list(self) -> List[Dict[str, Any]]:
        if not self._loaded:
            self.load()
        return [w.public_dict() for w in self._by_id.values()]

    def get(self, demo_id: str) -> Optional[DemoWallet]:
        if not self._loaded:
            self.load()
        return self._by_id.get(demo_id)

    def wallet_bytes(self, demo: DemoWallet) -> Optional[bytes]:
        """Read the demo wallet file (test wallet, no funds). None for seed demos."""
        if not demo.wallet_file:
            return None
        path = os.path.join(self.demo_dir, demo.wallet_file)
        if not os.path.exists(path):
            raise DemoError(f"demo wallet file missing: {demo.wallet_file}")
        with open(path, "rb") as fh:
            return fh.read()
