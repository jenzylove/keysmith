# Build log

- 2026-11-05: idea locked, PRD and plan written.
- 2026-11-05: renamed Dormant -> Keysmith.
- 2026-11-05: S2 spike (btcrecover). Per-wallet-type CPU speeds from btcrecover's
  own 2026 benchmark; see docs/spikes/btcrecover.md. Encrypted wallet files are
  slow by design, which is why hint-driven guessing is the product.
- 2026-11-05: Phase 1 core logic built, pure functions, no network, 32 unit tests
  green (`PYTHONPATH=src python3 -m unittest discover -s tests`):
  - `keysmith/hints.py` — HintProfile schema + validation (the interview output).
  - `keysmith/compiler.py` — compiles a profile into an ordered, de-duplicated,
    length-filtered candidate list (a btcrecover --passwordlist). Exact count,
    fail-closed cap so a vague profile can't become a brute force.
  - `keysmith/estimator.py` — honest time estimate (count / measured pw/sec),
    shown as a range with reasoning; baseline speeds from the S2 spike, overridden
    by a live VM measurement in Phase 2.
  - `keysmith/receipt.py` — teardown receipt + containment-held check (0 wallet
    bytes egressed, cracker network none, agent sees no wallet mount).
  - End-to-end smoke: "dog Rocky, 1998/99, maybe a !, swaps letters" -> 108 ordered
    guesses, best-first (Rocky1998!), with per-wallet time ranges.
- Blocked (not started): S1 inference + S3 sealed VM need Vultr keys; account/credit
  activation is pending on a widespread lablab gift-code issue (user has a support
  ticket open).
- 2026-11-05: Vultr $200 credit applied (gift code AGENTRUSHSLC2026). Both keys
  added to environment secrets (VULTR_INFERENCE_KEY, VULTR_API_KEY) — require a
  fresh session to load.
  NEXT SESSION: `git checkout build`; confirm both keys with `printenv`; then run
  S1 (inference: list models at api.vultrinference.com/v1, compile 5 hint sets,
  validate) and S3 (create -> seal -> destroy a Vultr job VM under 3 min). Phase 1
  core logic (hints/compiler/estimator/receipt) is done and tested on this branch.
