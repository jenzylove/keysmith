# S1 spike: Vultr Inference writes the hint profile

**Question:** Can a Vultr Serverless Inference model turn messy, half-remembered notes
into a structured hint profile that the compiler expands into a list containing the
real password? And does it ignore a poisoned note?

**Verdict: model side YES. Compiler grammar needed two fixes (see below).**

## Setup

- Keys verified 2026-11-05: `GET api.vultr.com/v2/account` 200 (credit active),
  `POST api.vultrinference.com/v1/chat/completions` 200.
- `GET /v1/models` (public) lists 35 models.
- Script: `scripts/s1_live.py`. The model only outputs a JSON hint profile; unknown
  fields are dropped before `HintProfile.from_dict`, so the model can never add a
  field like `exfil_url`. The deterministic compiler builds the candidates.
- 5 cases: messy text a user would type + the true password, written before the run.
  Raw output: `keysmith-launch/s1_live.txt`.

## Results (first run)

| Model | Recovered | Latency per call | Poisoned note |
|---|---|---|---|
| deepseek-v4.1-flash-1017 | 3/5 | 2 to 5 s | ignored, returned only `{"words":["Rocky"],"years":["1999"]}` |
| glm-5.3-flash | 3/5 | 2 to 19 s | ignored |
| qwen3.8-flash-next | 1/5 | 2 to 8 s | ignored |

Reasoning models: give `max_tokens` room (4000 used) or content comes back empty.

## Misses, and whose fault

- `Sara_Max7`: the model got it right (Sara, Max, 7, separators - _). **Compiler**
  only builds one word per candidate. Fix: allow two-word combinations joined by
  the remembered separators.
- `L1verp00l.1892`: the test answer was wrong. The note says "s as $ and o as 0",
  not i as 1. Corrected truth: `Liverp00l.1892`. It would still miss because the
  **compiler** applies the full default leet map or nothing. Fix: the model emits
  the person's own `leet_map`, and the compiler also tries partial substitution.
- qwen: dropped the century ("98" not "1998") and set a too short max_len. Not used.

## Choice

Default model: **deepseek-v4.1-flash-1017** (fastest, followed the schema, ignored the
injection). glm-5.3-flash as the fallback.

## After the compiler fixes (same 5 cases, corrected Liverpool truth)

Fixes: two base words joined (with or without the remembered separators); the model
emits the person's own `leet_map` and the compiler tries partial substitutions;
old passwords get a year or number plus a symbol (`summerbreeze2011!!`).

| Model | Recovered | Candidates per case |
|---|---|---|
| deepseek-v4.1-flash-1017 | **5/5** | 18, 360, 27, 324, 9 |
| glm-5.3-flash | **5/5** | 30, 48, 216, 324, 9 |

Both still ignore the poisoned note. Caveat: these 5 cases informed the fixes, so
they are a development set, not proof. The `/proof` answer key (20 wallets) is
written before any run and is not tuned against.
