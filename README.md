# Keysmith

**Forgot the password to an old crypto wallet? Tell Keysmith what you half-remember.
It turns your memories into targeted guesses and tries them inside a sealed Vultr box
that cannot send your wallet anywhere — not even to us.**

Lost crypto doesn't have a cracking problem. It has a *trust* problem: the only people
who can help you are the people you'd least want holding your wallet file. Keysmith
removes the trust: a fresh per-job box with no network, your wallet mounted read-only,
destroyed after the run, with a teardown receipt that proves it.

Built for the Vultr Agent Rush hackathon (Challenge 1, "Blast Radius Zero").

## Live demo

**https://95-179-195-57.sslip.io** — the real app on a Vultr control VM. Click
*Watch a demo wallet open*; a fresh sealed Vultr VM is created per job (allow
~8 min for the snapshot restore), the containment break-in test is blocked on
screen, the password is recovered, and the VM is destroyed with a teardown
receipt. Verified end to end on real infrastructure (see `docs/BUILD_LOG.md`,
2026-11-07).

## Judge fast path (offline, no keys)

```bash
pip install -r requirements.txt
python scripts/devserver.py          # http://127.0.0.1:8000  (scripted demo, no Vultr)
```

Open it, click **Watch a demo wallet open**, answer the short interview, accept the
plan, and watch the box open a real test vault — then hit **Run the break-in test** to
see a poisoned hint's attempt to read and upload the wallet get denied, live. The
dev server scripts the box so you can see the whole UX without Vultr; the production
path is the same code with the real runner (below).

## What's real

- **Core recovery logic** (`src/keysmith/`): hint schema, deterministic rule compiler
  (exact, ordered, capped candidate list), honest estimator, teardown receipt. 71 tests.
- **Sealed-VM runner** (`src/keysmith/runner.py`): creates a Vultr VM from a prebuilt
  snapshot, verifies containment, pushes the wallet + candidate list over inbound SSH,
  runs btcrecover under gVisor `--network=none`, streams progress, destroys the VM.
  Ships as `NullRunner` until the five Vultr env vars are set — it never fakes a run.
  **Proven live end to end on Vultr (2026-11-07): sealed box, containment held,
  password recovered, VM destroyed, zero wallet bytes egressed.**
- **Containment**, proven in the S3 spike and shown on the run page: output **and**
  forward nftables chains drop, `runsc` runtime, wallet `:ro`, agent box has no wallet.
- **Demo + proof**: real test vaults (no funds), and a 20-case answer key written blind
  (`data/proof/cases.json`) — 15 derivable, 5 honest misses, published with the fix.

## Vultr services used

| Service | Where |
|---|---|
| Serverless Inference (`api.vultrinference.com`) | every model call — the interview writes the hint profile. One client module: `src/keysmith/llm.py`. |
| Cloud Compute | the control VM, and one sealed job VM per recovery. |
| Vultr API (`api.vultr.com/v2`) | create / poll / snapshot / destroy job VMs. |

## Architecture

See `docs/ARCHITECTURE.md` for routes, SSE events, the runner protocol and data dirs;
`docs/PRD.md` for the product; `scripts/snapshot/` for the job-VM image; `deploy/` for
the control-VM Caddy + systemd setup.

## Honest limits

- Won't crack strong random passwords, or seeds missing more than ~2 words. It says so
  before the run.
- Stores no wallet files, passwords, or hints after a job.
- Has **no way to verify wallet ownership** — only run it on wallets you own. Stated
  plainly before every upload.
