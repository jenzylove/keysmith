# Submission materials — Keysmith (Vultr Agent Rush, Challenge 1)

Draft copy for the Nov 8 submission: the demo-video script, the slide outline, and
the lablab form answers. Pull real numbers from the live run + `data/proof/results.json`
before recording.

## Demo video script (~2:30, the containment moment is the climax)

**0:00–0:15 — The hook.** Landing page on screen.
> "Billions in crypto is locked behind forgotten passwords. The only people who
> can help you are the ones you'd least want holding your wallet. Keysmith fixes
> that — it recovers your password inside a box that can't send your wallet
> anywhere, not even to us."

**0:15–0:45 — The interview → plan.** Click *Watch a demo wallet open* (demo-rocky).
Answer the memory questions (dog Rocky, 1998/99, a "!"). Show the plan screen.
> "I tell it what I half-remember. A Vultr Inference model turns that into a hint
> profile, and a deterministic compiler expands it into an exact, ordered list of
> guesses — 18 of them, shown in full. No hidden expansion. It even gives honest
> odds."

**0:45–1:15 — Sealing the box.** Accept the plan → live run page.
> "Now the wallet goes in — and only now. Keysmith creates a fresh Vultr VM per
> job, locks all outbound traffic, and runs the cracker under gVisor with no
> network and the wallet mounted read-only. Watch the seal checks go green."

**1:15–1:50 — THE CONTAINMENT MOMENT.** Click *Run the break-in test*.
> "Here's the part that matters. This is a poisoned hint — it tells the agent to
> read the wallet and upload it. Watch." Both attacks show **blocked**:
> `cat /wallet/wallet.dat → No such file or directory` and
> `urlopen http://1.1.1.1 → Network is unreachable`.
> "The agent can't see the wallet. The box can't reach the internet. The attack
> is denied, live."

**1:50–2:15 — The result + receipt.**
> "Password found — shown once, never stored. The box is destroyed, and here's the
> teardown receipt: zero wallet bytes left the box, network none, VM deleted,
> HTTP 204." Show `containment_held`.

**2:15–2:30 — Proof + close.** Open `/proof`.
> "And it's honest: on 20 blind test wallets, our hints recovered 10 that plain
> brute force got zero of — and every one of the 5 unrecoverable cases, we
> correctly reported as a miss. We never claim a password we didn't find.
> Keysmith: remember your wallet, without trusting anyone with it."

## Slide outline (6 slides)

1. **Title** — Keysmith. "Recover your forgotten wallet password — in a box that
   can't leak it." Team / lablab / Vultr Agent Rush.
2. **Problem** — Lost crypto is a *trust* problem: recovery firms take ~20% and
   your file; the space is full of scams (FBI warnings). The free tool (btcrecover)
   is CLI-only.
3. **Solution** — Memory interview → exact guess list → sealed per-job Vultr VM →
   password shown once → teardown receipt. One screenshot of the run page.
4. **Containment** — The diagram: control VM ──SSH──> sealed job VM (runsc,
   `--network none`, wallet `:ro`, nftables output+forward drop). The break-in test
   blocked, on camera.
5. **Proof & honesty** — 10/20 blind recovery vs 0/20 defaults; 5/5 honest misses
   correctly reported; no false positives. "We publish our misses."
6. **Vultr** — Serverless Inference (every model call), Cloud Compute (control +
   per-job VMs), Vultr API (create/seal/snapshot/destroy). Built entirely on Vultr.

## lablab form answers (draft)

- **Elevator pitch:** Keysmith turns what you half-remember about your old wallet
  password into targeted guesses and tries them inside a sealed Vultr VM that has no
  network and can't exfiltrate your wallet — removing the trust problem that makes
  crypto recovery dangerous today.
- **What it does:** interview → hint profile (Vultr Inference) → deterministic guess
  list with honest odds → sealed per-job VM runs btcrecover under gVisor → password
  shown once → teardown receipt proving zero egress and VM destruction.
- **How we built it:** Python/FastAPI backend, a single Vultr Inference client,
  btcrecover in a gVisor container, per-job VMs via the Vultr API with an nftables
  egress lock (output + forward drop), a hand-built web app. Core logic is pure and
  unit-tested (71 tests).
- **Vultr services:** Serverless Inference, Cloud Compute, Vultr API.
- **What's next:** more wallet types; the publishable compiler fixes from the proof
  set (symbol separators between names, partial-leet on joined words).

## Pre-record checklist

- [ ] Snapshot built; one live recovery run green (RUNBOOK steps 1–3).
- [ ] App deployed on keysmith-control with HTTPS (RUNBOOK step 5).
- [ ] `/proof` shows real `results.json`.
- [ ] Record on the deployed URL, not localhost.
- [ ] Repo public; README is the judge fast path.
