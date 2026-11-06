#!/usr/bin/env python3
"""Generate a MetaMask browser-extension vault encrypted with a chosen password (test wallet, no funds)."""
import argparse, base64, json, os, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from mnemonic import Mnemonic


def make_vault(password, iterations=10000, mnemonic=None):
    mnemonic = mnemonic or Mnemonic("english").generate(128)
    keyring = [{"type": "HD Key Tree",
                "data": {"mnemonic": mnemonic, "numberOfAccounts": 1, "hdPath": "m/44'/60'/0'/0"}}]
    plaintext = json.dumps(keyring, separators=(",", ":")).encode()
    salt, iv = os.urandom(32), os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, 32)
    ct = AESGCM(key).encrypt(iv, plaintext, None)  # ciphertext || 16 byte tag
    vault = {"data": base64.b64encode(ct).decode(), "iv": base64.b64encode(iv).decode(),
             "salt": base64.b64encode(salt).decode()}
    if iterations != 10000:
        vault["keyMetadata"] = {"algorithm": "PBKDF2", "params": {"iterations": iterations}}
    return vault, mnemonic


def decrypt_vault(vault, password):
    it = vault.get("keyMetadata", {}).get("params", {}).get("iterations", 10000)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(vault["salt"]), it, 32)
    pt = AESGCM(key).decrypt(base64.b64decode(vault["iv"]), base64.b64decode(vault["data"]), None)
    return json.loads(pt)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="vault.json")
    ap.add_argument("--iterations", type=int, default=10000,
                    help="10000 = legacy (no keyMetadata); other values (e.g. 600000) add keyMetadata")
    ap.add_argument("--answer", help="optional path to write the mnemonic answer key JSON")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    vault, mn = make_vault(a.password, a.iterations)
    with open(a.out, "w") as f:
        json.dump(vault, f)
    if a.answer:
        with open(a.answer, "w") as f:
            json.dump({"password": a.password, "mnemonic": mn, "iterations": a.iterations}, f, indent=2)
    print("wrote", a.out)
    if a.verify:
        with open(a.out) as f:
            kr = decrypt_vault(json.load(f), a.password)
        assert kr[0]["data"]["mnemonic"] == mn
        print("OK")


if __name__ == "__main__":
    main()
