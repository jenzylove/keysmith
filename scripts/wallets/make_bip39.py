#!/usr/bin/env python3
"""Generate a BIP39 seed with N words blanked out, plus the address it derives (test wallet, no funds)."""
import argparse, hashlib, hmac, json, random
from mnemonic import Mnemonic
from ecdsa import SECP256k1, SigningKey

N = SECP256k1.order
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _rmd160(msg):  # pure python fallback (OpenSSL 3 may lack ripemd160)
    rol = lambda x, n: ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF
    r1 = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13]
    r2 = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11]
    s1 = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6]
    s2 = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11]
    K1 = [0, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
    K2 = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0]
    M = 0xFFFFFFFF

    def f(j, x, y, z):
        if j < 16: return x ^ y ^ z
        if j < 32: return (x & y) | (~x & M & z)
        if j < 48: return (x | (~y & M)) ^ z
        if j < 64: return (x & z) | (y & ~z & M)
        return x ^ (y | (~z & M))

    ml = len(msg) * 8
    msg += b"\x80" + b"\0" * ((55 - len(msg)) % 64) + ml.to_bytes(8, "little")
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    for off in range(0, len(msg), 64):
        X = [int.from_bytes(msg[off + i * 4:off + i * 4 + 4], "little") for i in range(16)]
        a, b, c, d, e = h
        A, B, C, D, E = h
        for j in range(80):
            t = (rol((a + f(j, b, c, d) + X[r1[j]] + K1[j // 16]) & M, s1[j]) + e) & M
            a, e, d, c, b = e, d, rol(c, 10), b, t
            t = (rol((A + f(79 - j, B, C, D) + X[r2[j]] + K2[j // 16]) & M, s2[j]) + E) & M
            A, E, D, C, B = E, D, rol(C, 10), B, t
        t = (h[1] + c + D) & M
        h = [t, (h[2] + d + E) & M, (h[3] + e + A) & M, (h[4] + a + B) & M, (h[0] + b + C) & M]
    return b"".join(x.to_bytes(4, "little") for x in h)


def ripemd160(b):
    try:
        return hashlib.new("ripemd160", b).digest()
    except ValueError:
        return _rmd160(b)


def hash160(b):
    return ripemd160(hashlib.sha256(b).digest())


def b58check(payload):
    d = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(d, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(d) - len(d.lstrip(b"\0"))) + s


def bech32_polymod(v):
    g = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    c = 1
    for x in v:
        b = c >> 25
        c = ((c & 0x1ffffff) << 5) ^ x
        for i in range(5):
            if (b >> i) & 1:
                c ^= g[i]
    return c


def segwit_addr(hrp, prog):
    acc = bits = 0
    data = [0]
    for byte in prog:
        acc = (acc << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((acc >> bits) & 31)
    if bits:
        data.append((acc << (5 - bits)) & 31)
    hv = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    pm = bech32_polymod(hv + data + [0] * 6) ^ 1
    data += [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH[d] for d in data)


def pub(k):
    p = SigningKey.from_string(k.to_bytes(32, "big"), curve=SECP256k1).get_verifying_key().pubkey.point
    return bytes([2 + (p.y() & 1)]) + p.x().to_bytes(32, "big")


def derive(seed, path):
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    k, c = int.from_bytes(I[:32], "big"), I[32:]
    for part in path.split("/")[1:]:
        hard = part.endswith("'")
        i = int(part.rstrip("'")) + (0x80000000 if hard else 0)
        data = (b"\0" + k.to_bytes(32, "big") if hard else pub(k)) + i.to_bytes(4, "big")
        I = hmac.new(c, data, hashlib.sha512).digest()
        k, c = (int.from_bytes(I[:32], "big") + k) % N, I[32:]
    return k


def address(mnemonic, kind):
    seed = Mnemonic.to_seed(mnemonic)
    path = "m/44'/0'/0'/0/0" if kind == "p2pkh" else "m/84'/0'/0'/0/0"
    h = hash160(pub(derive(seed, path)))
    return (b58check(b"\0" + h) if kind == "p2pkh" else segwit_addr("bc", h)), path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--words", type=int, default=12, choices=[12, 15, 18, 21, 24])
    ap.add_argument("--missing", type=int, default=2)
    ap.add_argument("--type", default="p2pkh", choices=["p2pkh", "p2wpkh"],
                    help="p2pkh = BIP44 legacy 1..., p2wpkh = BIP84 bc1...")
    ap.add_argument("--out", default="seed.json")
    ap.add_argument("--answer", help="answer key path (default: <out minus .json>.answer.json)")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    mn = Mnemonic("english").generate({12: 128, 15: 160, 18: 192, 21: 224, 24: 256}[a.words])
    words = mn.split()
    pos = sorted(random.SystemRandom().sample(range(a.words), a.missing))
    partial = " ".join("?" if i in pos else w for i, w in enumerate(words))
    addr, path = address(mn, a.type)
    pub_out = {"partial": partial, "missing_positions": pos, "address": addr,
               "address_type": a.type, "path": path}
    base = a.out[:-5] if a.out.endswith(".json") else a.out
    ans = a.answer or base + ".answer.json"
    with open(a.out, "w") as f:
        json.dump(pub_out, f, indent=2)
    with open(ans, "w") as f:
        json.dump({"full_mnemonic": mn, **pub_out}, f, indent=2)
    print("wrote", a.out, "and", ans)
    if a.verify:
        with open(ans) as f:
            k = json.load(f)
        assert Mnemonic("english").check(k["full_mnemonic"])
        assert address(k["full_mnemonic"], k["address_type"])[0] == k["address"]
        print("OK")


if __name__ == "__main__":
    main()
