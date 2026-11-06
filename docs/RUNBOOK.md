# Live runbook — finish Keysmith on a machine with SSH

The cloud build session can only make HTTPS calls, so it cannot SSH into Vultr.
Everything below must run from a shell that **can** SSH: your PC (Git Bash or WSL)
or the `keysmith-control` VM. You need the repo, the Vultr keys, and the VM SSH key.

```bash
# --- set these once (bash) ---
export VULTR_API_KEY=...            # from .env
export VULTR_INFERENCE_KEY=...      # from .env
export KEYSMITH_SSH_KEY=~/keysmith-launch/ssh/id_ed25519   # Windows: /c/Users/LENOVO/keysmith-launch/ssh/id_ed25519
```

Quick helper used below:
```bash
v(){ curl -s -H "Authorization: Bearer $VULTR_API_KEY" "https://api.vultr.com/v2/$1"; }
```

## 1. Build the job-VM snapshot (slowest — do first)

The existing `keysmith-builder` already trusts your `keysmith-spike` SSH key, so
provision it, then snapshot it.

```bash
# find the builder's IP and id, and your ssh key id
v instances | python3 -c "import sys,json;[print(i['id'],i['label'],i['main_ip']) for i in json.load(sys.stdin)['instances']]"
v ssh-keys  | python3 -c "import sys,json;[print(k['id'],k['name']) for k in json.load(sys.stdin)['ssh_keys']]"

# install docker+gVisor+btcrecover image on the builder (takes a few min)
scripts/snapshot/build-snapshot.sh provision <builder_ip> "$KEYSMITH_SSH_KEY"

# snapshot it; copy the printed id
scripts/snapshot/build-snapshot.sh snapshot <builder_vm_id>
export KEYSMITH_SNAPSHOT_ID=<printed id>
```

If `provision` fails, read `/var/log/keysmith-setup.log` on the builder over SSH —
that is exactly the visibility the cloud sandbox did not have.

## 2. Set the three runner settings

```bash
export KEYSMITH_SNAPSHOT_ID=<from step 1>
export KEYSMITH_SSHKEY_ID=<keysmith-spike id from step 1>
export KEYSMITH_SSH_KEY=~/keysmith-launch/ssh/id_ed25519
```

## 3. One real recovery, end to end

```bash
pip install -r requirements.txt
python scripts/run_live_job.py            # demo-rocky (MetaMask test vault)
```
Expect: creating_box → sealing (runsc / network none / wallet read-only) → the
break-in test blocked → progress → `found password='Rocky1999!'` → destroyed →
teardown receipt with `containment_held=True`, `bytes_egressed_wallet=0`. Record
the timings in `docs/BUILD_LOG.md`. This is the demo-video moment.

## 4. The 20-case proof set

Runs the blind answer key (`data/proof/cases.json`): agent-compiled list vs plain
btcrecover defaults, same budget. For speed, run them on one provisioned VM (not a
fresh sealed VM each) — it is a benchmark, not the privacy demo.

```bash
python scripts/run_proof.py <builder_ip> "$KEYSMITH_SSH_KEY"   # writes data/proof/results.json
```
Publish the misses with the fix, per the PRD. `/api/proof` then serves the results.

## 5. Deploy the app on keysmith-control (HTTPS)

```bash
# on keysmith-control (Ubuntu):
sudo apt-get update && sudo apt-get install -y python3-venv caddy
sudo mkdir -p /opt/keysmith && sudo chown $USER /opt/keysmith
git clone <repo> /opt/keysmith && cd /opt/keysmith
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python scripts/make_demo_wallets.py          # regenerate demo vaults (gitignored)

sudo tee /etc/keysmith.env >/dev/null <<EOF
VULTR_API_KEY=...
VULTR_INFERENCE_KEY=...
KEYSMITH_SNAPSHOT_ID=...
KEYSMITH_SSHKEY_ID=...
KEYSMITH_SSH_KEY=/root/keysmith-launch/ssh/id_ed25519
KEYSMITH_DATA_DIR=/var/lib/keysmith
KEYSMITH_WEB_DIST=/opt/keysmith/web/dist
EOF
sudo mkdir -p /var/lib/keysmith
sudo cp deploy/keysmith.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now keysmith
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # set your domain/sslip.io host first
sudo systemctl restart caddy
curl -s http://127.0.0.1:8000/api/health        # {"ok":true,"runner":"vm",...}
```

Note: the control VM needs `openssh-client` (for the runner's SSH) — it is standard
on Ubuntu; confirm `ssh` is on PATH.

## 6. Submission (deadline Nov 8, 22:00 UTC)

README (done), demo video (show the break-in test blocked + teardown receipt),
slides, cover image, public repo, lablab form. See `docs/SUBMISSION_CHECKLIST.md`.
