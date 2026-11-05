# Test wallet generators

Fund-free wallets with passwords we choose, for the public demo and the answer key.
Install: `pip install -r requirements.txt`. Every script takes `--verify` (decrypts or rederives with the known password and prints `OK`).

| Script | Example | btcrecover |
|---|---|---|
| `make_metamask.py` | `python make_metamask.py --password P --out vault.json [--iterations 600000] [--answer ans.json] --verify` | `python btcrecover.py --wallet vault.json --passwordlist list.txt` (or `--tokenlist`) |
| `make_blockchain.py` | `python make_blockchain.py --password P --out wallet.aes.json --version 3 --verify` | `python btcrecover.py --wallet wallet.aes.json --tokenlist tokens.txt` |
| `make_bip39.py` | `python make_bip39.py --words 12 --missing 2 [--type p2wpkh] --out seed.json --verify` | `python seedrecover.py --wallet-type bip39 --mnemonic "<partial>" --mnemonic-length 12 --addrs <address> --addr-limit 1` |

Notes:
- MetaMask: default is the legacy vault (10000 PBKDF2-SHA256 iterations, no `keyMetadata`); `--iterations` adds `keyMetadata`. btcrecover reads only the first 16 bytes of `data` (AES-GCM keystream) and looks for `"type"`, `version` or `mnemonic`.
- Blockchain: payload is base64(iv16 + AES-256-CBC), key PBKDF2-HMAC-SHA1 with the IV as salt, ISO 10126 padding. btcrecover checks the first block for `"guid"`.
- Seeds: `seed.json` is the public file (partial mnemonic with `?`, address, path); `seed.answer.json` holds the full mnemonic. Keep the answer file out of the repo. For BIP84 (bc1...) `seedrecover.py` derives addresses across common paths by default; use `--bip32-path "m/84'/0'/0'/0"` to force it. Unknown words are written as `?`; btcrecover treats any non-word token as "try all seed words here".
- Do not crack with these scripts; they only create wallets from a known password.
