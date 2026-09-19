"""mortality.csv from StatCan 13-10-0114-01 (complete life tables, 3-year estimates).
Status: published. qx is copied as-is for the latest reference period, Canada."""
import re
import sys
from common import dirs, rows, write

PID = "13100114"
SEX = {"Males": "M", "Females": "F", "Both sexes": "both"}
QX = "Death probability between age x and x+1 (qx)"


def main():
    cache, out = dirs(sys.argv)
    keep = [r for r in rows(cache, PID) if r["GEO"] == "Canada" and r["Element"] == QX]
    period = max(r["REF_DATE"] for r in keep)
    data = []
    for r in keep:
        if r["REF_DATE"] != period:
            continue
        age = int(re.match(r"(\d+) year", r["Age group"]).group(1))  # "110 years and over" -> 110
        data.append((age, SEX[r["Sex"]], r["VALUE"].rstrip("0").rstrip(".") if float(r["VALUE"]) != 1 else "1"))
    order = {"M": 0, "F": 1, "both": 2}
    data.sort(key=lambda t: (order[t[1]], t[0]))
    print("reference period", period)
    write(out, "mortality.csv", ["age", "sex", "qx"], data)


if __name__ == "__main__":
    main()
