# S3 spike — sealed job VM

**Question:** Can we create a job VM via the Vultr API, block egress, run gVisor
`--network none`, and destroy it, in under 3 minutes?

**Status (2026-11-05):** NOT RUN — blocked before the first call.

The Vultr control API (`api.vultr.com`) rejects `VULTR_API_KEY` with HTTP 401
(Invalid API key). See `docs/spikes/inference.md` for the full credential
diagnosis. No VM can be created until the token authenticates, so no timings, no
blocked-curl evidence, and no delete response could be captured. These will NOT be
mocked.

**Unblock, then run (per docs/PLAN.md):**
1. Regenerate the control API token from Vultr Account → API; confirm credit active.
2. `GET /v2/account` returns 200.
3. Create a small job VM; time boot-to-ready.
4. Confirm egress blocked from inside (a curl to a public host fails) and the
   agent sees no wallet mount; gVisor `--network none` for the cracker.
5. `DELETE` the instance; capture the response and total elapsed.
6. If boot is too slow for a live demo, record the fallback (per-job gVisor
   containers on a persistent runner VM) here and note it on the run page.
