"""homeownership.csv. Status: derived (age x income is not cross-tabulated in any table we
could obtain, so the two published margins are combined multiplicatively).

 age_rate(a)    = owner households / all private households, by age of primary household
                  maintainer. Census 2021, table 98-10-0231-01, Canada, all dwelling types.
 income_rate(q) = Owner / All households in income quintile q; overall_rate = Owner / All.
                  Distributions of household economic accounts (DHEA), table 36-10-0101-01,
                  latest year. Quintiles there are of *equivalized household disposable income*;
                  lowest..highest are mapped to low, lower_middle, middle, upper_middle, high.
 owner_rate(a,q) = clip(age_rate(a) * income_rate(q) / overall_rate, 0.02, 0.98)
"""
import re
import sys
from common import dirs, rows, write, fmt, num

PID_AGE, PID_INC = "98100231", "36100101"
QUINT = {"Lowest quintile": "low", "Second quintile": "lower_middle", "Third quintile": "middle",
         "Fourth quintile": "upper_middle", "Highest quintile": "high"}
BANDS = ["low", "lower_middle", "middle", "upper_middle", "high"]


def main():
    cache, out = dirs(sys.argv)
    age_rate = {}
    for r in rows(cache, PID_AGE):
        if (r["GEO"] == "Canada" and r["Structural type of dwelling (10)"].startswith("Total")
                and r["Condominium status (3)"].startswith("Total")
                and r["Household type including census family structure (16)"].startswith("Total")
                and r["Statistics (3C)"] == "Number of private households"):
            lab = r["Age of primary household maintainer (15)"]
            m = re.match(r"(\d+) to (\d+) years", lab)
            if m:
                band = (int(m.group(1)), int(m.group(2)))
            elif lab == "85 years and over":
                band = (85, 120)
            else:
                continue
            age_rate[band] = float(r["Tenure (4):Owner[2]"]) / float(r["Tenure (4):Total - Tenure[1]"])

    inc = [r for r in rows(cache, PID_INC) if r["Socio-demographic characteristics"] in ("Owner", "All households")
           and r["VALUE"] != ""]
    year = max(r["REF_DATE"] for r in inc)
    cnt = {(r["Socio-demographic characteristics"], r["Quintile"]): num(r) for r in inc if r["REF_DATE"] == year}
    overall = cnt[("Owner", "All quintiles")] / cnt[("All households", "All quintiles")]
    inc_rate = {QUINT[q]: cnt[("Owner", q)] / cnt[("All households", q)] for q in QUINT}
    print("DHEA year", year, "overall", round(overall, 4), {k: round(v, 4) for k, v in inc_rate.items()})
    print("census age rates", {k: round(v, 4) for k, v in sorted(age_rate.items())})

    data = []
    for band in sorted(age_rate):
        for b in BANDS:
            raw = age_rate[band] * inc_rate[b] / overall
            if not 0.02 <= raw <= 0.98:
                print(f"  clipped {band} {b}: {raw:.4f}")
            data.append((band[0], band[1], b, fmt(min(0.98, max(0.02, raw)), 4)))
    write(out, "homeownership.csv", ["age_lo", "age_hi", "income_band", "owner_rate"], data)


if __name__ == "__main__":
    main()
