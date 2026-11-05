#!/usr/bin/env python3
"""Generate the public demo wallets + the committed demo manifest.

Each demo is a real MetaMask test vault (no funds) encrypted with a password that
is *derivable from the committed interview answers* — so any visitor can play the
owner, answer the interview, and watch it open. The password lives only inside the
encrypted vault; the manifest never contains it (demo.py rejects a 'password' key).

We verify, offline, that the deterministic compiler — given the profile those
answers imply — actually produces the password as a candidate. That keeps the
demo honestly winnable without trusting the LLM at generation time. (At run time
the LLM writes the profile; the S1 spike showed it matches these.)

Run from the repo root:  python scripts/make_demo_wallets.py
Writes: data/demo/<id>.json (gitignored) + data/demo/manifest.json (committed).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "wallets"))

from keysmith.hints import HintProfile          # noqa: E402
from keysmith.compiler import compile_profile   # noqa: E402
from make_metamask import make_vault            # noqa: E402

DEMO_DIR = os.path.join(HERE, "..", "data", "demo")

# Each demo: the password (in the vault only), the interview answers a visitor
# would type (committed, no password), and the profile those answers imply (used
# only to self-check winnability here).
DEMOS = [
    {
        "id": "demo-rocky",
        "wallet_type": "metamask",
        "password": "Rocky1999!",
        "owner_story": "Ada made this MetaMask in 2018 for an NFT drop and never opened it again.",
        "notes": "dog Rocky, year 98 or 99, maybe a '!'",
        "answers": {
            "names": "Rocky (my dog)", "years": "1998 or 1999", "symbols": "!",
            "notes": "capital R, exclamation mark at the end",
        },
        "check_profile": {"words": ["Rocky"], "years": ["1998", "1999"],
                          "symbols": ["!"], "case_variants": True},
    },
    {
        "id": "demo-sara",
        "wallet_type": "metamask",
        "password": "Sara_Max7",
        "owner_story": "Tomas set up MetaMask in 2019 named after his wife and son, then lost the password.",
        "notes": "Sara and Max, a dash or underscore between, lucky number 7",
        "answers": {
            "names": "Sara (wife), Max (son)", "numbers": "7, my lucky number",
            "notes": "both names with capitals, an underscore or dash between them",
        },
        "check_profile": {"words": ["Sara", "Max"], "numbers": ["7"],
                          "separators": ["_", "-"], "case_variants": True},
    },
]


def main() -> int:
    os.makedirs(DEMO_DIR, exist_ok=True)
    manifest = {"note": "Public test wallets, no mainnet funds. Passwords live only in the encrypted vaults.",
                "demos": []}
    for d in DEMOS:
        # Self-check: the compiler must include the password as a candidate.
        prof = HintProfile.from_dict(d["check_profile"]).cleaned().validate()
        cands = list(compile_profile(prof).iter_candidates())
        if d["password"] not in cands:
            print(f"FAIL {d['id']}: password not in {len(cands)} candidates", file=sys.stderr)
            return 1
        rank = cands.index(d["password"]) + 1
        # Build the real encrypted vault.
        vault, _mn = make_vault(d["password"])
        fname = f"{d['id']}.json"
        with open(os.path.join(DEMO_DIR, fname), "w") as fh:
            json.dump(vault, fh)
        manifest["demos"].append({
            "id": d["id"], "wallet_type": d["wallet_type"],
            "owner_story": d["owner_story"], "notes": d["notes"],
            "wallet_file": fname, "answers": d["answers"],
        })
        print(f"  {d['id']}: winnable, password is candidate {rank}/{len(cands)} -> {fname}")

    with open(os.path.join(DEMO_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"wrote {os.path.join(DEMO_DIR, 'manifest.json')} ({len(manifest['demos'])} demos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
