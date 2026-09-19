"""income_bands.csv. Status: derived.

Input: Census 2021 table 98-10-0064-01 (total income groups, income year 2020, Canada, both
genders, all ages 15+, persons WITH total income). The 20th/40th/60th/80th percentiles are
interpolated linearly inside the published $5,000/$10,000 brackets (binned.py) and rounded to
the nearest $100. low starts at 0 (negative incomes should be treated as `low`), high ends at 1e12.
"""
import sys
from common import dirs, rows, write
from binned import percentile, parse_bracket

PID = "98100064"
YEAR_COL = "Year (2):2020[1]"
NAMES = ["low", "lower_middle", "middle", "upper_middle", "high"]


def main():
    cache, out = dirs(sys.argv)
    bins = []
    for r in rows(cache, PID):
        if r["GEO"] == "Canada" and r["Gender (3a)"] == "Total - Gender" and r["Age (11)"] == "Total - Age":
            label = r["Total income groups (24)"]
            b = parse_bracket(label)
            # '$100,000 and over' is a subtotal of the two brackets below it: skip it
            if b and label != "$100,000 and over":
                bins.append((b[0], b[1], float(r[YEAR_COL])))
    bins.sort()
    cuts = []
    for p in (0.2, 0.4, 0.6, 0.8):
        v, extrap = percentile(bins, p)
        assert not extrap
        cuts.append(int(round(v / 100.0) * 100))
    print("quintile cut-offs", cuts, "| median check", percentile(bins, 0.5)[0])
    edges = [0] + cuts + ["1e12"]
    write(out, "income_bands.csv", ["band", "lo", "hi"], [(NAMES[i], edges[i], edges[i + 1]) for i in range(5)])


if __name__ == "__main__":
    main()
