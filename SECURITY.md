# Security

Keysmith runs untrusted recovery code inside a sealed box and is built containment first.

## The model
- Each recovery runs in a gVisor (`runsc`) container with `--network=none`.
- The wallet file is mounted read only; the reasoning agent has no wallet mount at all.
- The host blocks all outbound traffic (nftables: output, forward and input policy drop, inbound SSH only).
- The box is destroyed after each job; the wallet file and candidate list are wiped. A teardown receipt records zero wallet bytes egressed.
- You can verify this live with the break in test on any run, and reproduce it from `docs/spikes/sealed-vm.md`.

## Secrets
- No keys or wallets are committed. `.env`, keypairs and wallet files are gitignored.
- The found password and the wallet bytes are never written to disk or returned by the API; the password is shown once from the live stream.

## Responsible use
Keysmith recovers the password of a wallet you own. It cannot verify ownership and adds no capability beyond the underlying open source tool. Do not use it on wallets that are not yours.

## Reporting
Open a GitHub issue, or contact the maintainer through the repository.
