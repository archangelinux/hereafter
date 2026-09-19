"""divorce.csv from StatCan 39-10-0054-01. Status: derived.

Published: divorce rate per 1,000 marriages by duration d (0..50) = divorces granted in the
reference year to the cohort married d years earlier / ORIGINAL size of that marriage cohort.
That is a density, not a hazard. Conversion to a conditional annual probability using the
synthetic-cohort (period) approach StatCan uses for its total divorce rate:
    r_d      = published rate / 1000
    S_d      = 1 - sum_{k<d} r_k          (share of marriages not yet divorced at duration d)
    hazard_d = r_d / S_d
Widowhood and migration are ignored (as in the published rate, table note 11).
Reference year defaults to 2019 (2020, the latest, is depressed by COVID-19 court closures).
"""
import re
import sys
from common import dirs, rows, write, fmt, num

PID = "39100054"


def main():
    cache, out = dirs(sys.argv[:3])
    year = sys.argv[3] if len(sys.argv) > 3 else "2019"
    r_d = {}
    for r in rows(cache, PID):
        if r["GEO"] == "Canada" and r["REF_DATE"] == year and r["Indicator"] == "Divorce rate":
            lab = r["Duration of marriage"]
            d = 0 if lab.startswith("Under") else int(re.match(r"(\d+) year", lab).group(1))
            r_d[d] = num(r) / 1000.0
    assert sorted(r_d) == list(range(51)), sorted(r_d)
    data, cum = [], 0.0
    for d in range(51):
        data.append((d, fmt(r_d[d] / (1.0 - cum))))
        cum += r_d[d]
    print("reference year", year, "| 50-year total divorce rate implied:", round(cum, 4))
    write(out, "divorce.csv", ["duration_years", "hazard"], data)


if __name__ == "__main__":
    main()
