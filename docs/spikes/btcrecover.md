# Spike S2: btcrecover feasibility and speed per wallet type

**Question:** Does btcrecover support each of our 5 target wallet types, and what is
the recovery speed on CPU (no GPU at this event)?

**Status: partially answered (speeds from published data).** Live timed runs on the
actual Vultr CPU VM move to Phase 2, where the VM is the real target hardware. A local
benchmark run in the build container was blocked by the harness as password-cracking
(expected; it is running the cracker). The numbers below come from reading btcrecover's
own shipped benchmark results, not from a run here.

## Source

btcrecover (`3rdIteration/btcrecover`, shallow clone) ships dated benchmark JSON under
`benchmark-results/`. Numbers below are the **Intel i7-10700K (16 threads, 3.8 GHz),
2026-04-12** run — the closest consumer CPU in the set to a Vultr vCPU. Difficulty is
the per-candidate work, which does not change with hardware.

## Speeds for our 5 target types

| Our wallet type | btcrecover label | pw/sec (i7, 16 thr) | per-candidate work |
|---|---|---|---|
| Bitcoin Core `wallet.dat` (legacy BDB) | Bitcoin Core (BDB) | **82.6** | 67,908 SHA-512 iters |
| Bitcoin Core `wallet.dat` (newer SQLite) | Bitcoin Core (SQLite) | **22.9** | 267,488 SHA-512 iters |
| Blockchain.info (v2 / v3) | Blockchain.com v2 / v3 | **431 / 698** | 5k–10k PBKDF2-SHA1 |
| MetaMask vault (Chrome) | MetaMask (Chrome) | **690** | 10,000 PBKDF2-SHA256 |
| Electrum 2.8+ (passphrase) | Electrum 2.8+ Passphrase | **4,674** | 1024 PBKDF2-SHA512 + ECC |
| BIP39 seed — missing/wrong **words** | BIP39 12/24-word Seed | **36k / 155k** | none (seed derivation) |
| BIP39 **passphrase** (25th word) | BIP39 Passphrase | **2,403** | 2048 PBKDF2-SHA512 + ECC |

(Context, same run: Ethereum keystore scrypt 16/sec, BIP38 15/sec, raw privkey 73k/sec.)

## What this means for the product

1. **Password cracking and seed-word recovery are two different speed regimes.**
   - Encrypted *wallet files* (Bitcoin Core, MetaMask, Blockchain, Electrum passphrase)
     are deliberately slow: tens to a few thousand candidates/sec. You can only afford a
     **small, smart candidate set** — which is exactly why hint-driven guessing is the
     whole game here, not a nice-to-have.
   - Missing/wrong *seed words* from known positions are fast (tens of thousands/sec), so
     there the trust/sealed-box angle carries the product, not speed.

2. **Bitcoin Core is the hardest type** (23–83/sec). Honest estimator math: a targeted
   hint set of ~100k candidates ≈ 20 min–1 hr on one 16-thread box; ~1M ≈ 3–12 hr. Blind
   brute force is hopeless — this is the strongest case for the "memory → targeted guesses"
   pitch. Lead the live demo with a Bitcoin Core or MetaMask wallet, not a fast seed type.

3. **Scaling:** these are whole-machine (16-thread) figures. A Vultr `vc2-4c` ≈ divide by
   ~4; provision more vCPUs per job to hit demo-friendly times. Confirm real numbers on the
   VM in Phase 2 (`benchmark.py` on the target instance).

4. **Estimator is honest and buildable:** candidate count (from btcrecover `--listpass`
   count) × measured pw/sec on the job VM = time. Show as a range with the reasoning, never
   a single fake number — the PRD already commits to this.

## Open items for the live VM (Phase 2)

- Confirm each of the 5 types loads and opens with a known token file on the Vultr VM.
- Record actual pw/sec per type on the chosen instance size.
- Pick the demo wallet type for the best "opens on camera in demo time" story.
