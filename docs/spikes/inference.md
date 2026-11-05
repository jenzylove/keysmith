# S1 spike — Vultr Inference + hint compilation

**Question:** Which models does Vultr Inference serve, and can we turn messy,
half-remembered hints into a *valid* btcrecover candidate list?

**Status (2026-11-05):** Local half PASS. Live inference + control API BLOCKED on
invalid credentials (not network).

## Done criteria vs. result

| Criterion | Result |
|---|---|
| Model list | ✅ `GET /v1/models` → HTTP 200, 35 models (list below). ⚠️ endpoint is **public** — returns 200 with no auth, so it does not prove the key works. |
| 5 hint sets compiled | ✅ `scripts/s1_compile_validate.py` compiles 5 messy→structured hint sets. |
| Validator passes on all 5 | ✅ PASS on all 5 (non-empty, unique, length-bounded, passwordlist line count matches candidate count). |
| Live round-trip (messy text → HintProfile via a model → compile) | ❌ BLOCKED — chat completions returns 401. |

## Models served (35)

Chat/reasoning candidates for the interview + profile-extraction step:
`glm-5.3`, `glm-5.2`, `glm-5.3-flash`, `deepseek-v4.1-flash-1017`,
`qwen3.8-27b`, `qwen3.8-flash-next`, `mimo-v2.6-pro`, `mimo-v2.6-flash`,
`minimax-m3.1-flash`, `nemotron-3-nano-omni-30b-a3b-reasoning`,
`muse-glimmer-30b`, `raon-1-mini-preview`.
Plus embedding/rerank (`bge-reranker-v2-m3`, `qwen3-embedding-4b`,
`vultron-retriever-*`), speech/audio, and image/music models not needed here.

## Local compile/validate results

Run: `PYTHONPATH=src python3 scripts/s1_compile_validate.py`

| # | Hint set | Candidates | Best-first example |
|---|---|---|---|
| 1 | dog Rocky, 1998/1999, maybe `!`, leet | 36 | `Rocky1998!` |
| 2 | wife Sara + son Max, separators, a 7 | 33 | `Sara7` |
| 3 | old pw `summerbreeze`, year/`!` tail | 15 | `Summerbreeze` |
| 4 | Liverpool/YNWA, 1892, `$`, leet, `.` | 78 | `Liverpool1892$` |
| 5 | pet `Milo`, 2 or 22, no symbols | 9 | `Milo2` |

All small, best-first, human-sized — the product thesis holds on the compiler side.

## Credential block (blocks live round-trip + all of S3)

Both env secrets are present and well-formed (36 chars, no whitespace), but
rejected by Vultr:

| Call | Key | HTTP |
|---|---|---|
| `POST /v1/chat/completions` | `VULTR_INFERENCE_KEY` | 401 Invalid API key |
| `POST /v1/chat/completions` | `VULTR_API_KEY` | 401 |
| `GET api.vultr.com/v2/account` | `VULTR_INFERENCE_KEY` | 401 |
| `GET api.vultr.com/v2/account` | `VULTR_API_KEY` | 401 |

No key/endpoint combination authenticates. Error is a clean `auth_error` JSON, so
the Bearer scheme is understood and the key *value* is what's rejected. Likely the
Vultr account / API tokens were never fully activated (see the lablab gift-code
issue in BUILD_LOG) or the tokens were regenerated.

**Next session:** regenerate both tokens from the Vultr console — Inference key
from the Serverless Inference product page, control key from Account → API —
confirm the account shows the $200 credit as active, re-store both in environment
secrets, start a fresh session, then re-run this spike's live round-trip and S3.

## Network note

`api.vultrinference.com` and `api.vultr.com` must be on the environment's Allowed
domains list (they were added 2026-11-05). Before that, both returned proxy 403.
