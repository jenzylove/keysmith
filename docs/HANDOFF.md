# Handoff (read this first in a new session)

Project: Dormant, Vultr Agent Rush (lablab), Challenge 1 "Blast Radius Zero".
Deadline: **Nov 8 2026, 22:00 UTC** (23:00 WAT). Run `date` first.
Memory: `vultr-agent-rush-lablab.md` in the Claude memory folder.
Skill in use: hackathon-build (speed mode). Commit as jenzylove <jennifereze12@gmail.com>, no AI attribution lines.

## State as of 2026-11-05 ~13:00 WAT

- Idea LOCKED. PRD: `docs/PRD.md`. Plan: `docs/PLAN.md`. Checklist: `docs/SUBMISSION_CHECKLIST.md`.
- Repo: github.com/jenzylove/dormant (private until submission).
- User has the Vultr API key and Vultr Inference key; they go in `~/dormant/.env` as `VULTR_API_KEY` and `VULTR_INFERENCE_KEY` (gitignored). User OK'd storing them there and on the backend VM.
- PRD and plan gate: shown to the user; user said "lock and set up", treat as approved.

## Next step

Phase 0 spikes, in parallel (see PLAN.md):
1. S1: `GET https://api.vultrinference.com/v1/models`, pick a model, compile 5 hint sets into btcrecover tokenlists, validate.
2. S2: btcrecover speed per wallet type on a small Vultr CPU VM.
3. S3: create job VM via Vultr API, gVisor `--network none`, nftables egress drop, destroy; time it.
Write results to `docs/spikes/*.md`, append to `docs/BUILD_LOG.md`, update this file.

## Rules

- No fake states, no invented numbers. If a spike fails, stop and bring a changed plan to the user.
- Delegate routine work to sonnet/haiku subagents; keep spikes, isolation design and reviews.
- Destroy every Vultr VM created by a spike (credits are $200).
- Update this file at every milestone.
