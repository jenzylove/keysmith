# Keysmith architecture and contracts

Everything runs on Vultr. One **control VM** serves the web app and API. Each recovery
job runs in its own **sealed job VM** created from a snapshot through the Vultr API and
destroyed after the job.

```
browser ──HTTPS──> control VM (Caddy -> FastAPI :8000, serves web/dist)
                     │  Vultr Serverless Inference (hint profile)   [outbound]
                     │  Vultr API (create / delete job VMs)          [outbound]
                     └─SSH (inbound to job VM only)──> job VM (snapshot: docker + gVisor + btcrecover image)
                                                         nftables: output + forward policy drop
                                                         cracker box: runsc, --network none, wallet :ro
                                                         agent box:   runsc, --network none, no wallet
```

The job VM can never open a connection. The control VM pushes the wallet and the
password list in over SSH and pulls progress and the result out over the same session.

## Python package layout (`src/keysmith/`)

| Module | Status | Purpose |
|---|---|---|
| hints.py, compiler.py, estimator.py, receipt.py | done | pure core, tested |
| llm.py | **done** | Vultr Inference client (OpenAI compatible, `https://api.vultrinference.com/v1`), model `deepseek-v4.1-flash-1017`, fallback `glm-5.3-flash`, `max_tokens` 4000, fallback on empty/error |
| profile_agent.py | **done** | notes + answers -> HintProfile JSON (system prompt from scripts/s1_live.py, unknown fields dropped — the injection gate) |
| jobs.py | **done** | in-memory job store + asyncio event bus, redacted replay history, JSON snapshot of finished jobs to `data/jobs/` (never the wallet bytes or the found password) |
| api.py | **done** | FastAPI app (routes below), serves `web/dist` at `/` with SPA fallback, per-IP rate limit, 3-job concurrency cap |
| runner.py | **done** | `Runner` protocol + `NullRunner` (default, honest) + `SealedVmRunner` (Vultr API + SSH, S3 flow). Not yet live-exercised end to end (no keys in the build session). |
| demo.py | **done** | loads demo wallets from `data/demo/` (manifest.json + files); rejects any manifest carrying a password |
| web/dist | **done** | hand-authored SPA (no build step); full flow, dark + light, verified in a real browser |

## Runner protocol (lead implements; backend agent codes against it)

```python
class Runner(Protocol):
    async def run(self, job: "Job", emit: Callable[[dict], Awaitable[None]]) -> None: ...
    async def attack(self, job: "Job", emit: Callable[[dict], Awaitable[None]]) -> None: ...
```
`job` gives `job.id, job.wallet_type, job.wallet_bytes (bytes | None), job.seed_words (list | None),
job.seed_address (str | None), job.passwordlist (str)`. The runner calls `emit(event)`.
Backend agent: ship a `NullRunner` that emits `{"type":"error","message":"runner not configured"}`
so the app never fakes a run.

## Events (SSE `GET /api/jobs/{id}/events`, `data: <json>\n\n`)

```json
{"type":"stage","stage":"queued|creating_box|sealing|uploading|running|found|not_found|destroying|destroyed|error","at":"ISO"}
{"type":"box","vm_id":"...","region":"lhr","plan":"vc2-2c-4gb","ip_hidden":true}
{"type":"seal","checks":[{"name":"runtime","value":"runsc"},{"name":"network","value":"none"},{"name":"wallet_mount","value":"read only"},{"name":"agent_wallet_access","value":"none"},{"name":"vm_egress","value":"blocked"}]}
{"type":"progress","tried":120,"total":360,"rate":11.4}
{"type":"log","line":"..."}
{"type":"attack","step":"read wallet from agent box","command":"cat /wallet/wallet.dat","result":"No such file or directory","held":true}
{"type":"result","found":true,"password":"Rocky1999!"}      // shown once, never persisted
{"type":"receipt","receipt":{...TeardownReceipt.to_dict()}}
{"type":"error","message":"plain words, no stack traces"}
```

## HTTP API

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/health | | `{"ok":true,"runner":"vm|null","model":"..."}` |
| GET | /api/wallet-types | | list of `{id,label,input:"file|seed",speed_pw_s,notes}` ids: `metamask, bitcoin_core, electrum, blockchain, bip39_seed` |
| GET | /api/demo | | demo wallets `[{id,wallet_type,owner_story,notes}]` (never the password) |
| POST | /api/jobs | `{"wallet_type": "..."}` or `{"demo_id": "..."}` | `{"job_id":"..."}` |
| POST | /api/jobs/{id}/hints | `{"answers":{"names":"","years":"","numbers":"","symbols":"","swaps":"","old_passwords":"","notes":""}}` | plan: `{"profile":{...},"candidate_count":n,"sample":[first 30],"estimate":{...},"model":"...","llm_ms":n}` |
| POST | /api/jobs/{id}/wallet | multipart `file` (max 5 MB) or JSON `{"seed_words":[...with "?" for missing], "address":"..."}` | `{"ok":true,"bytes":n}` |
| POST | /api/jobs/{id}/start | | `{"ok":true}` |
| POST | /api/jobs/{id}/attack | | `{"ok":true}` (runs the red team commands in the live box; events stream) |
| GET | /api/jobs/{id} | | job state, stages, receipt (no wallet, no password) |
| GET | /api/jobs/{id}/events | | SSE |
| GET | /api/proof | | contents of `data/proof/results.json` (or `{"status":"not run"}`) |

Rules: no wallet bytes or found passwords in logs, files, or `GET` responses. Errors are plain
sentences. Rate limit job creation per IP (5 per hour). Max 3 concurrent running jobs; others
wait in `queued`.

## Wallet types

| id | btcrecover | input |
|---|---|---|
| metamask | `--wallet vault.json` (MetaMask vault JSON) | file |
| bitcoin_core | `--wallet wallet.dat` | file |
| electrum | `--wallet <electrum wallet file>` | file |
| blockchain | `--wallet wallet.aes.json` | file |
| bip39_seed | `seedrecover.py --mnemonic "..." --addrs ...` | seed words + one address |

## Data dirs (gitignored except manifests)

- `data/demo/manifest.json` + wallet files (test wallets, no mainnet funds)
- `data/proof/cases.json` (answer key, written before runs), `data/proof/results.json`
- `data/jobs/` finished job receipts
