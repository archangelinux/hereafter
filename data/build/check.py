"""Sanity checks on the finished CSVs.  usage: python3 check.py [data_dir]"""
import csv
import os
import sys
from collections import defaultdict

D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANDS = ["low", "lower_middle", "middle", "upper_middle", "high"]
FIELDS = {"education", "arts", "humanities", "social_sciences_law", "business", "sciences", "math_cs",
          "engineering", "agriculture", "health", "services", "all"}
problems = []


def load(name, header):
    with open(os.path.join(D, name)) as fh:
        rd = csv.DictReader(fh)
        assert rd.fieldnames == header, (name, rd.fieldnames)
        rs = list(rd)
    for r in rs:
        for k, v in r.items():
            if v is None or v.strip() == "":
                problems.append(f"{name}: empty cell {k} in {r}")
    print(f"{name}: {len(rs)} rows")
    return rs


def check(cond, msg):
    if not cond:
        problems.append(msg)


def prob(name, rs, col):
    for r in rs:
        check(0.0 <= float(r[col]) <= 1.0, f"{name}: {col} out of [0,1]: {r}")


m = load("mortality.csv", ["age", "sex", "qx"])
prob("mortality", m, "qx")
for sex in ("M", "F", "both"):
    q = {int(r["age"]): float(r["qx"]) for r in m if r["sex"] == sex}
    check(sorted(q) == list(range(0, max(q) + 1)) and max(q) >= 109, f"mortality {sex}: ages {min(q)}..{max(q)}")
    bad = [a for a in range(31, max(q) + 1) if q[a] < q[a - 1]]
    check(not bad, f"mortality {sex}: non-monotone after 30 at ages {bad}")
    e0, l = 0.0, 1.0
    for a in sorted(q):
        e0 += l * (1 - q[a] / 2)
        l *= 1 - q[a]
    print(f"   {sex}: implied life expectancy at birth ~ {e0:.1f}")

fm = load("first_marriage.csv", ["age", "sex", "hazard"])
prob("first_marriage", fm, "hazard")
for sex in ("M", "F", "both"):
    h = {int(r["age"]): float(r["hazard"]) for r in fm if r["sex"] == sex}
    check(sorted(h) == list(range(15, 71)), f"first_marriage {sex}: ages")
    s = 1.0
    for a in range(15, 51):
        s *= 1 - h[a]
    print(f"   {sex}: implied share ever legally married by 50 ~ {1 - s:.3f}")

dv = load("divorce.csv", ["duration_years", "hazard"])
prob("divorce", dv, "hazard")
check([int(r["duration_years"]) for r in dv] == list(range(51)), "divorce: durations")
s = 1.0
for r in dv:
    s *= 1 - float(r["hazard"])
print(f"   implied share of marriages divorced within 50 years ~ {1 - s:.3f}")

f = load("fertility.csv", ["age", "rate"])
prob("fertility", f, "rate")
check([int(r["age"]) for r in f] == list(range(15, 50)), "fertility: ages")
print(f"   implied total fertility rate ~ {sum(float(r['rate']) for r in f):.3f}")

inc = load("income.csv", ["field", "age_lo", "age_hi", "p10", "p25", "p50", "p75", "p90"])
check({r["field"] for r in inc} == FIELDS, "income: field slugs")
per_field = defaultdict(list)
for r in inc:
    v = [float(r[p]) for p in ("p10", "p25", "p50", "p75", "p90")]
    check(v == sorted(v) and v[0] > 0, f"income: percentiles not increasing {r}")
    per_field[r["field"]].append((int(r["age_lo"]), int(r["age_hi"])))
for fld, bands in per_field.items():
    check(bands == [(15, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 120)], f"income: bands for {fld}")

ib = load("income_bands.csv", ["band", "lo", "hi"])
check([r["band"] for r in ib] == BANDS, "income_bands: names")
check(all(float(ib[i]["hi"]) == float(ib[i + 1]["lo"]) for i in range(4)), "income_bands: contiguous")
check(float(ib[0]["lo"]) == 0 and float(ib[4]["hi"]) == 1e12, "income_bands: ends")

ho = load("homeownership.csv", ["age_lo", "age_hi", "income_band", "owner_rate"])
for r in ho:
    check(0.02 <= float(r["owner_rate"]) <= 0.98, f"homeownership: {r}")
by_age = defaultdict(list)
for r in ho:
    by_age[(int(r["age_lo"]), int(r["age_hi"]))].append(r["income_band"])
check(all(v == BANDS for v in by_age.values()), "homeownership: bands per age")
ages = sorted(by_age)
check(ages[0][0] == 15 and ages[-1][1] == 120 and all(ages[i][1] + 1 == ages[i + 1][0] for i in range(len(ages) - 1)),
      "homeownership: age coverage")

jt = load("job_tenure.csv", ["age_lo", "age_hi", "tenure_lo_months", "tenure_hi_months", "share"])
tot = defaultdict(float)
for r in jt:
    tot[(r["age_lo"], r["age_hi"])] += float(r["share"])
for k, v in tot.items():
    check(abs(v - 1) < 1e-9, f"job_tenure: shares for {k} sum to {v}")
check(all(r["tenure_hi_months"] == "9999" for r in jt if r["tenure_lo_months"] == "241"), "job_tenure: top bucket")

mg = load("migration.csv", ["field", "age_lo", "age_hi", "interprovincial_rate", "emigration_rate"])
prob("migration", mg, "interprovincial_rate")
prob("migration", mg, "emigration_rate")
check(all(r["field"] == "all" for r in mg), "migration: field")

fl = load("interprovincial_flows.csv", ["origin", "destination", "share"])
tot = defaultdict(float)
for r in fl:
    tot[r["origin"]] += float(r["share"])
    check(r["origin"] != r["destination"] and float(r["share"]) > 0, f"flows: {r}")
check(len(tot) == 13, "flows: 13 origins")
for k, v in tot.items():
    check(abs(v - 1) < 1e-4, f"flows: shares for {k} sum to {v}")

print("\nPROBLEMS:" if problems else "\nall checks passed")
for p in problems:
    print(" -", p)
sys.exit(1 if problems else 0)
