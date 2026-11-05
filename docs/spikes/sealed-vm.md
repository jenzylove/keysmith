# S3 spike: sealed job VM

**Question:** Can we create a job VM via the Vultr API, block egress, run gVisor
`--network none`, and destroy it, in under 3 minutes?

**Verdict: YES (2026-11-05, run from the dev PC against the real Vultr API).**

## What was run

Vultr `vc2-2c-4gb`, region `lhr`, Ubuntu 24.04 (os_id 2284), SSH key registered via API.
Scripts kept outside the repo in `keysmith-launch/` (s3_setup.sh, s3_contain.sh, s3_lock2.sh).

| Step | Result |
|---|---|
| `POST /v2/instances` to SSH ready | **71 s** |
| Install gVisor (apt repo) + `runsc install` + pull python:3.12-slim | **20 s** (Docker itself installed in a prior step, ~40 s) |
| `DELETE /v2/instances/{id}` | HTTP **204**, instance 404 after **2 s** |

## Containment evidence (real output)

1. Cracker box, `--runtime=runsc --network=none`, wallet mounted `:ro`:
   - `Starting gVisor...` (dmesg inside the box)
   - outbound `urlopen http://1.1.1.1` -> `Network is unreachable`
   - write to `/wallet` -> `Read-only file system`
2. Agent box, `--runtime=runsc --network=none`, **no wallet mount**:
   - `cat /wallet/wallet.dat` -> `No such file or directory`
3. Host egress lock (nftables, `table inet ks`):
   - output chain policy drop (lo + established/related allowed) -> host `curl https://example.com` fails (exit 6)
   - **Finding:** an output only lock does NOT stop Docker containers on the default
     bridge: a runc container still got `HTTP 403` back from 1.1.1.1, because container
     traffic goes through the forward hook. Fixed with a forward chain, policy drop.
     After the fix both runsc and runc containers on the bridge time out.
   - SSH from the backend still works after the lock (inbound + established).

## Design consequences

- Job flow: create VM from a **prebuilt snapshot** (Docker + gVisor + btcrecover image
  baked in) -> cloud init applies the nftables lock (output + forward drop) before
  anything else -> backend pushes wallet + passwordlist over inbound SSH -> cracker runs
  `--network none` -> backend pulls progress/result over SSH -> `DELETE`.
  The VM can never open a connection; the only channel is the backend's inbound SSH.
- Budget: ~71 s boot + lock; with a snapshot no install time. Under 3 min.
- Run page should show: runtime `runsc`, network `none`, wallet mount `ro` and absent
  from the agent box, nft ruleset, interface tx bytes, and the DELETE response.
