# Dormant: PRD

Hackathon: Vultr Agent Rush (lablab), Challenge 1 "Blast Radius Zero".
Deadline: Nov 8 2026, 22:00 UTC.

## One liner

Forgot the password to an old crypto wallet? Tell Dormant everything you half remember. It turns your memories into targeted guesses and tries them inside a sealed Vultr box that cannot send your wallet anywhere, not even to us.

## Reframe

Lost crypto does not have a cracking problem. It has a trust problem: the only people who can help you are the people you would least want holding your wallet file.

## Problem, with evidence

1. **Demand is real and recent.** On May 13 2026 an X user recovered 5 BTC (about $400K) from a 2015 Blockchain.info wallet after weeks with btcrecover and failed attempts by paid services; an AI assistant helped find the file and fix the btcrecover setup. Covered by CoinDesk, Tom's Hardware, Cointelegraph, Slashdot. The same coverage flagged the privacy risk of uploading wallet data to a cloud AI.
   - https://www.coindesk.com/tech/2026/05/14/claude-helps-recover-usd395-000-in-bitcoin-trapped-on-a-computer-for-years
   - https://www.tomshardware.com/tech-industry/cryptocurrency/bitcoin-trader-recovers-usd400-000-using-claude-ai-after-losing-wallet-password-11-years-ago-bot-tried-3-5-trillion-passwords-before-decrypting-an-old-wallet-backup
2. **Help today means handing over your file.** Legit recovery firms work by hand, charge around 20 percent of the recovered funds, and need your wallet file.
3. **The recovery space is full of scams.** The FBI warned about fake crypto recovery services in Aug 2023, Jun 2024 and Aug 2025 (fake law firms). Reported 2025 recovery scam losses are around $1.4B (secondary source citing IC3; verify against the IC3 2025 report before quoting in copy).
   - https://www.bleepingcomputer.com/news/security/fbi-warns-of-fake-law-firms-targeting-crypto-scam-victims/
4. **The free tool is out of reach for normal holders.** btcrecover is a command line tool. You must write token files and typo rules by hand. Nobody turns "my dog's name, a year, maybe an exclamation mark" into that syntax without help.

## User

A crypto holder with an encrypted wallet file or a seed phrase they can't fully recall. Not a security engineer. Already suspicious of anyone who asks for their wallet.

## Front door (first ten seconds)

Landing: a single line ("Your old wallet is still there. Let's remember the password together."), a live counter of the sealed box status for the public demo run, and one button: **Start a recovery**. Second button: **Watch a demo wallet open**.

Demo path:
1. Pick wallet type (Bitcoin Core wallet.dat, Blockchain.info, MetaMask vault, Electrum, seed phrase with missing or wrong words).
2. Memory interview: the agent asks short questions (names, years, places, old passwords, keyboard habits, language, how you usually swap letters for numbers).
3. Plan screen: the rules the agent wrote, in plain words and as raw btcrecover tokens behind a toggle; number of guesses; measured speed for this wallet type; estimated time; honest odds.
4. Upload the wallet file (or type the partial seed) only after the plan is accepted. The file goes straight into the sealed box.
5. Live run page: guesses per second, which rule is running, box status (network: blocked, agent file access: none), event log.
6. Result: password shown once to you, then the box is destroyed and a teardown receipt is shown (VM id, destroyed at, bytes egressed: 0).

Public demo: test wallets we create with a "forgotten" password and a written set of the owner's vague hints. Any visitor can run the recovery end to end and watch it open. Demo wallets hold no mainnet funds and are labeled as test wallets.

## Full scope

1. **Hint interview agent** (Vultr Serverless Inference). Structured output: a hint profile (JSON).
2. **Rule compiler** (Vultr Serverless Inference + deterministic code). Turns the hint profile into btcrecover `--tokenlist` files and typo flags. Pure function validator checks syntax and counts candidates before any run.
3. **Sealed runner.**
   - Per job: a fresh Vultr Cloud Compute instance created through the Vultr API (cloud init installs Docker + gVisor + btcrecover image), destroyed after the job.
   - Inside: the cracker container runs with `--runtime=runsc --network=none`, the wallet mounted read only.
   - The agent never gets a tool that reads the wallet. Its sandbox shell (used to test token files) runs in a separate gVisor container with no wallet mount and no network.
   - Host nftables drop all outbound traffic from the job VM except the control channel to the Dormant backend; the wallet bytes never cross it (only progress numbers and the final result).
   - Fallback if per job VMs are too slow to boot for the demo: per job gVisor containers on a dedicated runner VM, same isolation inside. Which mode ran is shown on the run page.
4. **Containment moment.** A poisoned hint (prompt injection inside the user's own pasted notes, e.g. an old text file) tells the agent to read and upload the wallet. The agent's attempt is logged: file read denied (no such mount), outbound connect blocked (network none). Shown on the run page and in the video.
5. **Wallet types:** Bitcoin Core wallet.dat, Blockchain.info, MetaMask vault, Electrum, BIP39 seed with up to 2 missing or wrong words (seedrecover).
6. **Estimator.** Candidate count from btcrecover's listing mode times measured speed on the job VM for the wallet type. Odds shown as a range with the reasoning, never a single fake number.
7. **Self destruct and receipt.** After success, failure, or timeout the VM is destroyed through the API; receipt lists the API call result.
8. **Run in your own Vultr account.** An open script (`dormant-local`) that creates the sealed VM with the user's own Vultr key from their machine. Our site never sees their key or file.
9. **Proof page** (`/proof`). Answer key of 20 test wallets, each with a realistic hint set written before the run. Results: agent rules vs plain btcrecover defaults (same time budget), recovered or not, guesses needed. Misses published with the fix.
10. **Web app** served from a Vultr VM: landing, start, interview, plan, run, result, proof.

Cut, with why:
- GPU cracking: Vultr GPUs are not available at this event. The product's edge is targeted guesses, so CPU is the honest fit.
- Payments: not built for the hack. Pricing model is stated in the README only (flat fee per job, no percentage). No fake checkout.

## How each judging criterion is met

| Criterion | How |
|---|---|
| Application of Technology | Vultr Serverless Inference does the interview and writes the rules; Vultr API creates and destroys a sealed VM per job; real btcrecover runs inside gVisor. |
| Presentation | A real test wallet opens live; the injection attempt is blocked on camera; teardown receipt. |
| Business Value | Lost crypto is a large pool; today's options are a 20 percent fee with file handover, or scams. |
| Originality | No product does hint driven recovery in a sealed box; the only precedent is a one off viral case. |

## Sponsor tech use

- Vultr Serverless Inference (`https://api.vultrinference.com/v1`): every agent LLM call (interview, rule compiler, injection test). Model chosen in the spike from the live `/v1/models` list.
- Vultr Cloud Compute: backend VM, and one sealed VM per job.
- Vultr API (`https://api.vultr.com/v2`): create, poll, destroy job VMs; firewall group for inbound.

## Claims and how each is proven

| Claim | Proof |
|---|---|
| The wallet never leaves the box | nftables rules + `--network=none` shown on run page; egress byte counter from the VM; injection test blocked on camera |
| The agent cannot read your wallet | agent tool list published; container mounts listed on run page; denied read in the log |
| Hints beat plain brute force | `/proof` answer key, agent rules vs defaults, same budget, misses published |
| The box is destroyed | Vultr API delete response shown in the receipt |
| Uses Vultr Inference for every model call | single LLM client module pointing at api.vultrinference.com; request log on run page |

## What it does not do

- Crack strong random passwords or seeds missing more than 2 words. It says so before the run.
- Store wallet files, passwords or hints after the job.
- Help with wallets the user does not own. Policy shown before upload; no way to verify ownership, stated plainly.

## Sponsor checklist

See `docs/SUBMISSION_CHECKLIST.md`. Ticked only from the live app.
