#!/usr/bin/env python3
"""Generate a Blockchain.com (blockchain.info) v2/v3 wallet backup with a chosen password (test wallet, no funds)."""
import argparse, base64, json, os, uuid, hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def encrypt(password, iterations, payload_obj):
    pt = json.dumps(payload_obj, separators=(",", ":")).encode()
    # ISO 10126 padding: random fill, last byte = pad length (btcrecover reads the last byte)
    n = 16 - len(pt) % 16
    pt += os.urandom(n - 1) + bytes([n])
    iv = os.urandom(16)  # IV doubles as PBKDF2 salt
    key = hashlib.pbkdf2_hmac("sha1", password.encode(), iv, iterations, 32)
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(iv + enc.update(pt) + enc.finalize()).decode()


def decrypt(wrapper, password):
    raw = base64.b64decode(wrapper["payload"])
    iv, ct = raw[:16], raw[16:]
    key = hashlib.pbkdf2_hmac("sha1", password.encode(), iv, wrapper["pbkdf2_iterations"], 32)
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    pt = d.update(ct) + d.finalize()
    pad = pt[-1]
    assert 1 <= pad <= 16
    return json.loads(pt[:-pad])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="wallet.aes.json")
    ap.add_argument("--version", type=int, default=3, choices=[2, 3])
    ap.add_argument("--iterations", type=int, default=5000)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    guid, sk = str(uuid.uuid4()), str(uuid.uuid4())
    inner = {"guid": guid, "sharedKey": sk, "double_encryption": False,
             "options": {"pbkdf2_iterations": a.iterations}, "keys": []}
    wrapper = {"version": a.version, "pbkdf2_iterations": a.iterations,
               "payload": encrypt(a.password, a.iterations, inner)}
    with open(a.out, "w") as f:
        json.dump(wrapper, f)
    print("wrote", a.out)
    if a.verify:
        with open(a.out) as f:
            assert decrypt(json.load(f), a.password)["guid"] == guid
        print("OK")


if __name__ == "__main__":
    main()
