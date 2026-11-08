# Keysmith

[![live demo](https://img.shields.io/badge/live%20demo-95--179--195--57.sslip.io-0B8457)](https://95-179-195-57.sslip.io) [![built on Vultr](https://img.shields.io/badge/built%20on-Vultr-007BFC)](https://www.vultr.com) [![license MIT](https://img.shields.io/badge/license-MIT-16130E)](LICENSE) [![tests](https://img.shields.io/badge/tests-71%20passing-0B8457)](tests)

![Keysmith](docs/hero.png)


**Forgot the password to an old crypto wallet? Tell Keysmith what you half remember.
It turns your memories into a short list of targeted guesses and tries them inside a
sealed Vultr box that cannot send your wallet anywhere, not even to us.**

Lost crypto does not have a cracking problem. It has a trust problem: the only people
who can help you are the people you would least want holding your wallet file. Keysmith
removes the trust. Every recovery runs in a sealed box with no network, your wallet
mounted read only, the reasoning agent locked away from the file, and the box destroyed
afterwards with a receipt that proves nothing left.

Built for the Vultr Agent Rush hackathon, Challenge 1, Blast Radius Zero.

## Try it in one minute (no keys, no setup)

Open **https://95-179-195-57.sslip.io** and click **Watch a demo wallet open**.

A real encrypted test wallet (no funds) opens end to end in front of you:
1. A model on Vultr Serverless Inference turns the owner's fuzzy memories into guesses.
2. A sealed box opens on Vultr, the containment checks go green.
3. btcrecover tries the guesses and the password appears.
4. Press **Run the break in test**: a poisoned hint tries to read and upload the wallet, and you watch it get denied, live.
5. The box is destroyed and a teardown receipt shows zero wallet bytes left.

The whole run takes a few seconds. Bring your own wallet instead with **Start a recovery**.

## What is real, and what is not

| Part | Status |
|---|---|
| Recovery logic (hint schema, rule compiler, estimator, receipt) | Real. Pure, deterministic, 71 tests. |
| Interview writes the guess profile | Real. Vultr Serverless Inference, `src/keysmith/llm.py`. |
| Sealed box runs the guesses | Real. gVisor container, no network, wallet read only, on a Vultr VM. |
| Containment (no network, wallet read only, agent has no access, host egress blocked) | Real. Observed live on the run page and in the break in test, not asserted. |
| Proof: our rules vs plain defaults | Real. 20 test wallets, hints written blind before any run. 10 of 20 recovered, 0 of 20 by defaults, misses published. |
| Found password / wallet bytes | Never stored. Shown once from the live stream, then gone. |
| Payments | Not built for the hackathon. Pricing is stated, not charged. |

## How the sealed box works

```
your wallet ──inbound SSH──> sealed Vultr box
                              nftables: output + forward + input(drop, SSH only)
                              cracker container: runsc, --network=none, wallet :ro
                              agent container:   runsc, --network=none, NO wallet
                              <── progress only ──  (the wallet can never leave)
                              then: container removed, job files wiped
```

The box can open no outbound connection. The only channel is the control VM's inbound
SSH, and only progress numbers and the final result travel back. A poisoned hint that
tells the agent to read the wallet and phone home fails twice: the agent has no wallet
mount, and the network is off. Both failures are shown on camera.

## Vultr services used

| Service | Where |
|---|---|
| Serverless Inference (`api.vultrinference.com`) | Every model call. The interview turns memories into a hint profile. One client: `src/keysmith/llm.py`, model `deepseek-v4.1-flash-1017`. |
| Cloud Compute | The control VM that serves the app, and the sealed runner VM that runs recoveries. |
| Vultr API (`api.vultr.com/v2`) | Builds the hardened snapshot image, and (in per job mode) creates and destroys a fresh VM per recovery. |

## Architecture

One **control VM** serves the web app and API. A **warm sealed runner VM** stays booted
with Docker, gVisor and the btcrecover image baked in. Each recovery runs as a fresh
gVisor container on it, so a run starts in seconds instead of waiting on a VM boot. The
host egress lock and per container `--network=none` make the box unable to talk out; the
container and the job's files are wiped after each run. A per job VM mode (a fresh Vultr
VM created and destroyed for every job, from a snapshot) ships in the same code for teams
that want one throwaway machine per recovery; it is slower but never reuses a host.

See `docs/ARCHITECTURE.md` for the full contract and `docs/BUILD_LOG.md` for the spikes
that proved containment and speed on real infrastructure.

## The number that matters

Recovery firms take around 20 percent of the coins and need your wallet file in their
hands. Keysmith is a flat fee per job and never holds your file. On a 5 BTC wallet, that
is the difference between keeping your coins and handing over about one of them.

## Run it in your own Vultr account

The whole thing is open. Point it at your own Vultr account and the wallet never touches
a server anyone else controls.

```bash
git clone https://github.com/jenzylove/keysmith && cd keysmith
pip install -r requirements.txt
# set VULTR_API_KEY, VULTR_INFERENCE_KEY, and either warm-runner or snapshot env vars
python -m keysmith          # serves on :8000
```

Running locally with no Vultr keys, the app serves a scripted demo of the full flow
(`scripts/devserver.py`) so the experience is visible without an account. It never fakes
a real recovery: the live runner ships as a `NullRunner` until the Vultr env vars are set.

## Scope and limits

- Works when your password came from things you can still half remember. It will not
  crack a strong random password, and it says so before you spend time.
- The seed phrase option recovers up to two missing or wrong words from a known address,
  not an entirely lost phrase.
- It cannot verify wallet ownership. The policy is stated plainly, it stores nothing,
  and it adds no capability the underlying open tool does not already have.
