# Running Keysmith

## Try the hosted demo (nothing to install)
Open https://95-179-195-57.sslip.io and click "Watch a demo wallet open".

## Run it locally
```bash
pip install -r requirements.txt
python -m keysmith            # serves on http://127.0.0.1:8000
# or: uvicorn keysmith.api:app --host 0.0.0.0 --port 8000
python -m pytest -q           # 71 tests
```
With no Vultr keys set the app serves a scripted demo and the runner ships as a
NullRunner, so it never fakes a real recovery.

## Run real sealed recoveries on Vultr
Set in the environment (or a repo-root `.env`):
```
VULTR_API_KEY=...             # Vultr API key (Account > API)
VULTR_INFERENCE_KEY=...       # Vultr Serverless Inference key
KEYSMITH_SSH_KEY=/path/to/private_key   # key that can SSH the runner
# Warm runner (fast, recommended): a pre-booted sealed VM
KEYSMITH_RUNNER=warm
KEYSMITH_RUNNER_IP=<runner vm ip>       # Docker + gVisor + keysmith/btcrecover baked in
# Or per-job VM mode (a fresh VM per recovery, from a snapshot):
# KEYSMITH_RUNNER=vm ; KEYSMITH_SNAPSHOT_ID=... ; KEYSMITH_SSHKEY_ID=...
```
Build the runner image / snapshot with `scripts/snapshot/build-snapshot.sh` and
deploy with `deploy/` (uvicorn service + Caddy). See docs/RUNBOOK.md and
docs/ARCHITECTURE.md.
