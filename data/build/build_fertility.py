"""fertility.csv from StatCan 13-10-0418-01. Status: derived (unit change + step expansion).
Published age-specific fertility rates are per 1,000 females in 5-year groups; we divide by
1,000 and repeat each group's rate for its five single years of age."""
import re
import sys
from common import dirs, rows, write, fmt, num

PID = "13100418"


def main():
    cache, out = dirs(sys.argv)
    keep = [r for r in rows(cache, PID)
            if r["GEO"].startswith("Canada,") and r["Characteristics"].startswith("Age-specific fertility rate")
            and r["VALUE"] != ""]
    period = max(r["REF_DATE"] for r in keep)
    data = []
    for r in keep:
        if r["REF_DATE"] != period:
            continue
        lo, hi = map(int, re.search(r"(\d+) to (\d+) years", r["Characteristics"]).groups())
        for age in range(lo, hi + 1):
            data.append((age, fmt(num(r) / 1000.0)))
    data.sort()
    print("reference period", period, "TFR implied", sum(float(d[1]) for d in data))
    write(out, "fertility.csv", ["age", "rate"], data)


if __name__ == "__main__":
    main()
