# Job-VM snapshot

Every recovery runs in a fresh Vultr VM created from one prebuilt snapshot, then
destroyed. The snapshot bakes in Docker + gVisor (`runsc`) + the `keysmith/btcrecover`
image, so a job VM needs **zero install time** at boot — only the egress lock.

## Files

| File | Role |
|---|---|
| `Dockerfile` | the `keysmith/btcrecover` image (btcrecover, pinned, no network at runtime) |
| `provision.sh` | run on a builder VM: install Docker + gVisor, register `runsc`, build the image |
| `build-snapshot.sh` | drive the Vultr API: provision a builder, then snapshot it |
| `cloud-init.yaml` | applied to **each job VM** at boot: writes + enables the nftables lock first, before any workload |
| `nftables-ks.conf` | the egress ruleset (output **and** forward policy drop — the S3 spike fix) |

## Build it once

```bash
export VULTR_API_KEY=...            # from the Vultr console
# 1. Boot a builder VM (vc2-2c-4gb, Ubuntu 24.04) — e.g. the existing keysmith-builder.
# 2. Install everything and build the image on it:
scripts/snapshot/build-snapshot.sh provision <builder_ip> ~/keysmith-launch/ssh/id_ed25519
# 3. Snapshot it and copy the printed id:
scripts/snapshot/build-snapshot.sh snapshot <builder_vm_id>
#    -> export KEYSMITH_SNAPSHOT_ID=<id>
# 4. Delete or power off the builder to stop paying for it.
```

## Then the control VM needs

```
VULTR_API_KEY          # create/destroy job VMs
VULTR_INFERENCE_KEY    # the interview model
KEYSMITH_SNAPSHOT_ID   # from the build above
KEYSMITH_SSHKEY_ID     # Vultr SSH key id trusted by job VMs
KEYSMITH_SSH_KEY       # path to the matching private key (outside the repo)
```

With all five set, `keysmith.runner.build_default_runner()` returns the real
`SealedVmRunner`; without them it returns `NullRunner` and the app says so instead
of faking a run.

## Containment, as shipped

- Job VM cloud-init enables the nftables lock **before** Docker workloads.
- The cracker container runs `--runtime=runsc --network=none`, wallet mounted `:ro`.
- The agent/sandbox container has **no wallet mount** and no network.
- `/api/jobs/{id}/attack` runs the two break-in commands live; both are denied
  (see the run page and the teardown receipt).
