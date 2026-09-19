"""income.csv. Status: derived.

Inputs (Census of Population 2021, income year 2020, Canada, both genders, persons 15+ in
private households with employment income):
 A. 98-10-0066-01  counts of persons by employment-income bracket, by age band, plus the
    published median.
 B. 98-10-0410-01  published MEDIAN employment income by CIP-2021 primary field-of-study
    grouping and age band (72 cells pulled via WDS by fetch.py).

field=all rows: p10/p25/p75/p90 are interpolated from the brackets in A (see binned.py; a
  percentile falling in the open '$100,000 and over' bracket uses a Pareto tail and is reported
  on stdout), p50 is the published median from A.
field rows: every percentile of the `all` row for the same age band is multiplied by
  (field median / all-fields median), both medians from B. Only the median is published by
  field, so the *shape* of each field's distribution is assumed equal to the overall shape.
All values rounded to the nearest $100, except p50 of the `all` rows (published value kept).
"""
import json
import os
import sys
from common import dirs, rows, write
from binned import percentile, parse_bracket

PID_GROUPS = "98100066"
YEAR_COL = "Year (2):2020[1]"
BANDS = {"15 to 24 years": (15, 24), "25 to 34 years": (25, 34), "35 to 44 years": (35, 44),
         "45 to 54 years": (45, 54), "55 to 64 years": (55, 64), "65 years and over": (65, 120)}
FIELDS = ["education", "arts", "humanities", "social_sciences_law", "business", "sciences",
          "math_cs", "engineering", "agriculture", "health", "services", "all"]
PCTS = [0.10, 0.25, 0.50, 0.75, 0.90]


def main():
    cache, out = dirs(sys.argv)
    bins, median = {}, {}
    for r in rows(cache, PID_GROUPS):
        if r["GEO"] != "Canada" or r["Gender (3a)"] != "Total - Gender" or r["Age (11)"] not in BANDS:
            continue
        band = BANDS[r["Age (11)"]]
        label = r["Employment income groups (21)"]
        if label.startswith("Median employment income"):
            median[band] = float(r[YEAR_COL])
        b = parse_bracket(label)
        if b:
            bins.setdefault(band, []).append((b[0], b[1], float(r[YEAR_COL])))

    base = {}
    for band in sorted(bins):
        bl = sorted(bins[band])
        vals = []
        for p in PCTS:
            v, extrap = percentile(bl, p)
            if extrap:
                print(f"  NOTE age {band}: p{int(p*100)} = {v:,.0f} is a Pareto-tail extrapolation")
            vals.append(v)
        print(f"age {band}: interpolated median {vals[2]:,.0f} vs published {median[band]:,.0f}")
        vals[2] = median[band]
        assert vals == sorted(vals)
        base[band] = vals

    with open(os.path.join(cache, "98100410_wds.json")) as fh:
        cells = json.load(fh)["cells"]
    fmed = {(c["field"], (c["age_lo"], c["age_hi"])): c["median_employment_income"] for c in cells}
    data = []
    for field in FIELDS:
        for band in sorted(base):
            k = 1.0 if field == "all" else fmed[(field, band)] / fmed[("all", band)]
            vals = [int(round(v * k / 100.0) * 100) for v in base[band]]
            if field == "all":
                vals[2] = int(median[band])  # keep the published median exactly
            data.append([field, band[0], band[1]] + vals)
    write(out, "income.csv", ["field", "age_lo", "age_hi", "p10", "p25", "p50", "p75", "p90"], data)


if __name__ == "__main__":
    main()
