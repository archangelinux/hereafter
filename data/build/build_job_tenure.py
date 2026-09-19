"""job_tenure.csv from StatCan 14-10-0051-01 (Labour Force Survey, annual). Status: derived.

Canada, both genders, full- and part-time combined, latest year. Published values are employed
persons (thousands) per tenure bucket. A suppressed cell is replaced by the residual
(Total employed - sum of published buckets), floored at 0. share = bucket / sum of the seven buckets for that age group.
The 45-54 group is not published directly: count(45-54) = count(25-54) - count(25-44).
Bounds are inclusive months as labelled by StatCan, except that the first bucket ("1 to 3
months") is written as 0-3 so that jobs under one month have a home; top bucket hi = 9999.
"""
import sys
from common import dirs, rows, write, fmt, num

PID = "14100051"
BUCKETS = {"1 to 3 months": (0, 3), "4 to 6 months": (4, 6), "7 to 12 months": (7, 12),
           "13 to 60 months": (13, 60), "61 to 120 months": (61, 120),
           "121 to 240 months": (121, 240), "241 months or more": (241, 9999)}


def main():
    cache, out = dirs(sys.argv)
    keep = [r for r in rows(cache, PID)
            if r["GEO"] == "Canada" and r["Type of work"] == "Both full and part-time employment"
            and r["Gender"] == "Total - Gender" and (r["Job tenure"] in BUCKETS or r["Job tenure"] == "Total employed")]
    year = max(r["REF_DATE"] for r in keep if r["VALUE"] != "")
    c = {(r["Age group"], r["Job tenure"]): num(r) for r in keep if r["REF_DATE"] == year and r["VALUE"] != ""}
    # Suppressed cells (status 'x'; in practice only 15-24 x '241 months or more', which is
    # near-impossible) are set to the residual: Total employed - sum of the published buckets.
    for age in sorted({a for a, _ in c}):
        missing = [b for b in BUCKETS if (age, b) not in c]
        assert len(missing) <= 1, (age, missing)
        for b in missing:
            resid = max(0.0, c[(age, "Total employed")] - sum(c[(age, x)] for x in BUCKETS if x != b))
            print(f"  suppressed cell {age} / {b}: residual {resid:.1f} thousand")
            c[(age, b)] = resid
    groups = {
        (15, 24): lambda b: c[("15 to 24 years", b)],
        (25, 44): lambda b: c[("25 to 44 years", b)],
        (45, 54): lambda b: c[("25 to 54 years", b)] - c[("25 to 44 years", b)],
        (55, 64): lambda b: c[("55 to 64 years", b)],
        (65, 120): lambda b: c[("65 years and over", b)],
    }
    data = []
    for (lo, hi), f in groups.items():
        counts = {b: f(b) for b in BUCKETS}
        assert all(v >= 0 for v in counts.values()), counts
        tot = sum(counts.values())
        shares = [round(counts[b] / tot, 4) for b in BUCKETS]
        shares[3] = round(shares[3] + (1.0 - sum(shares)), 4)  # put rounding residual in the largest-ish bucket
        for b, s in zip(BUCKETS, shares):
            data.append((lo, hi, BUCKETS[b][0], BUCKETS[b][1], fmt(s, 4)))
    print("reference year", year)
    write(out, "job_tenure.csv", ["age_lo", "age_hi", "tenure_lo_months", "tenure_hi_months", "share"], data)


if __name__ == "__main__":
    main()
