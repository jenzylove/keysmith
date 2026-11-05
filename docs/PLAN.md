# Dormant: build plan

Deadline Nov 8 2026, 22:00 UTC. Stack: Python (FastAPI) backend, btcrecover, Docker + gVisor, a light frontend served by the backend. All on Vultr.

## Phase 0. Keys and spikes (Nov 5)

Needs from the user: Vultr API key, Vultr Serverless Inference key, credits claimed.

| Spike | Question | Done when |
|---|---|---|
| S1 models | Which models does Vultr Inference serve, and can one write valid btcrecover token files from messy hints? | `docs/spikes/inference.md`: model list, 5 hint sets compiled, validator passes on all 5 |
| S2 btcrecover | Does btcrecover open each of the 5 test wallet types with a known token file on a CPU VM, and what is the speed? | `docs/spikes/btcrecover.md`: speed per wallet type |
| S3 sealed VM | Can we create a job VM via the API, block egress, run gVisor `--network none`, and destroy it, in under 3 minutes? | `docs/spikes/sealed-vm.md`: timings, a blocked curl, delete response |

If S3 boot time is too slow for a live demo, use the fallback (per job gVisor containers on a runner VM) and say so on the run page.

## Phase 1. Core logic, no network (Nov 6 morning)

- Hint profile schema, rule compiler output validator, candidate counter, estimator, receipt model.
- Unit tests for each. Done when `pytest` passes.

## Phase 2. Integration on Vultr (Nov 6)

- LLM client (Vultr Inference only), interview and compiler prompts.
- Job orchestrator: create VM, wait, push token files + wallet, run, stream progress, destroy.
- Agent sandbox shell (separate container, no wallet, no network).
- Done when one real job runs end to end on Vultr and the VM is destroyed, logged in BUILD_LOG.

## Phase 3. Containment and proof (Nov 7 morning)

- Poisoned hint test: logged denial + blocked egress.
- 20 test wallets + hint sets written before running; `/proof` results with agent vs defaults.
- Done when `/proof` shows real results from runs on Vultr.

## Phase 4. Web app and design (Nov 7)

- Landing, start, interview, plan, run (live), result + receipt, proof, demo wallet path.
- Own look. Render in headless browser dark and light; screenshots to the user.
- Deployed on the backend VM with a stable public URL.

## Phase 5. Audit and approval (Nov 8 morning)

- release-readiness-audit on repo + live; fix findings; secret scan of history.
- User approves.

## Phase 6. Launch (Nov 8, before 20:00 UTC)

- README (judge fast path, what is real, Vultr services used, architecture).
- Demo video with the containment moment, slides, cover image.
- Repo public, lablab submission done with 2 hours buffer.

## Risks

| Risk | Status |
|---|---|
| Vultr Inference models too weak for token syntax | needs a spike (S1); fallback: deterministic compiler with the LLM filling only the hint profile |
| Job VM boot too slow | needs a spike (S3); fallback runner mode |
| btcrecover speed on CPU for MetaMask (high iteration counts) | needs a spike (S2); show honest estimates |
| gVisor on Vultr images | needs a spike (S3) |
| Dual use (stolen wallet files) | known; policy page, no claim of ownership checks |
| Credits run out | known; $200 covers many short lived small VMs, destroy after every job |
