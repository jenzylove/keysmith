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

- 2026-11-05 (session 2): `git checkout build`; both keys present in env (set).
  Added api.vultrinference.com + api.vultr.com to Allowed domains (were proxy-403).
  - S1 local half DONE: scripts/s1_compile_validate.py compiles 5 messy hint sets,
    validator PASS on all 5 (36/33/15/78/9 candidates, best-first). See
    docs/spikes/inference.md.
  - S1 model list: /v1/models -> 200, 35 models (glm-5.3, deepseek-v4.1-flash,
    qwen3.8-27b, etc.). NOTE: /v1/models is PUBLIC (200 w/o auth), so it does not
    prove the key.
  - BLOCKED: both VULTR_INFERENCE_KEY and VULTR_API_KEY return 401 "Invalid API key"
    on the authenticated endpoints (chat completions AND api.vultr.com/v2/account),
    in every key/endpoint combination. Keys are well-formed (36 chars, no ws). So
    S1 live round-trip and all of S3 could not run. Not mocked.
  NEXT SESSION: regenerate both Vultr tokens from the console (Inference key +
  Account->API key), confirm $200 credit active, re-store in env secrets, fresh
  session, then run S1 live round-trip + S3 (create/seal/destroy VM < 3 min).
