import sys
sys.path.insert(0, "src")
from keysmith.hints import HintProfile
from keysmith.compiler import compile_profile

# 5 hint sets, messy-to-structured, as the interview agent would emit.
HINT_SETS = [
    ("dog Rocky, year 1998 or 1999, maybe a '!'",
     dict(words=["Rocky"], years=["1998","1999"], symbols=["!"],
          use_leet=True, case_variants=True, min_len=5, max_len=16)),
    ("wife Sara + son Max, separators, a 7 somewhere",
     dict(words=["Sara","Max"], numbers=["7"], separators=["-","_"],
          case_variants=True, min_len=4, max_len=20)),
    ("old password 'summerbreeze', bumps a year/! on the end",
     dict(old_passwords=["summerbreeze"], years=["2010","2011"], symbols=["!","!!"],
          case_variants=True, use_leet=False, min_len=8, max_len=24)),
    ("Liverpool fan, YNWA, 1892, sometimes $ and leet",
     dict(words=["Liverpool","YNWA"], years=["1892"], symbols=["$"],
          use_leet=True, case_variants=True, separators=["."], min_len=6, max_len=18)),
    ("just a pet name 'Milo' and a 2 or 22, no symbols",
     dict(words=["Milo"], numbers=["2","22"], case_variants=True,
          use_leet=False, min_len=4, max_len=12)),
]

all_ok = True
for i,(desc,d) in enumerate(HINT_SETS, 1):
    try:
        prof = HintProfile.from_dict(d).cleaned().validate()
        plan = compile_profile(prof)
        cands = list(plan.iter_candidates())
        n = len(cands)
        # validator: non-empty, unique, within length bounds, one-per-line file parses
        assert n == len(set(cands)), "duplicates present"
        lo, hi = prof.min_len, prof.max_len
        assert all((lo is None or len(c)>=lo) and (hi is None or len(c)<=hi) for c in cands), "length bound violated"
        pwl = plan.to_passwordlist()
        lines = [l for l in pwl.splitlines() if l]
        assert len(lines) == n, "passwordlist line count mismatch"
        print(f"[{i}] OK  {desc}")
        print(f"      candidates={n:<6} first5={cands[:5]}")
    except Exception as e:
        all_ok = False
        print(f"[{i}] FAIL {desc}\n      {type(e).__name__}: {e}")

print("\nVALIDATOR RESULT:", "PASS on all 5" if all_ok else "FAILURES ABOVE")
sys.exit(0 if all_ok else 1)
