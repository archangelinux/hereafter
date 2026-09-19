"""first_marriage.csv from StatCan 39-10-0057-01. Status: derived.

Published: marriage rate per 1,000 *never legally married* persons, by 5-year age group.
 - sex=both : rate/1000 for the reference year, repeated for each single year in the group
              ("Under 20 years" is applied to ages 15-19, "70 to 74 years" to age 70).
 - sex=M/F  : Canada-level rates by gender are not published after 2002 (table note 8).
              hazard_sex(g) = hazard_both(g, ref year) * rate_sex(g, 2002) / rate_both(g, 2002),
              i.e. the most recent published male/female differential is carried forward.
Reference year defaults to 2019: 2020 is the latest year in the table but is depressed by
about a third by COVID-19 restrictions on weddings. Pass a third argument to override.
"""
import sys
from common import dirs, rows, write, fmt, num

PID = "39100057"
GROUPS = [("Under 20 years", 15, 19)] + [(f"{a} to {a+4} years", a, a + 4) for a in range(20, 70, 5)] \
         + [("70 to 74 years", 70, 70)]
GENDER = {"Total – Gender": "both", "Men+": "M", "Women+": "F"}
SEX_RATIO_YEAR = "2002"


def main():
    cache, out = dirs(sys.argv[:3])
    year = sys.argv[3] if len(sys.argv) > 3 else "2019"
    rate = {}
    for r in rows(cache, PID):
        if (r["GEO"] == "Canada" and r["Indicator"] == "Marriage rate"
                and r["Legal marital status prior to marriage"] == "Never legally married"
                and r["REF_DATE"] in (year, SEX_RATIO_YEAR) and r["VALUE"] != ""):
            rate[(r["REF_DATE"], GENDER[r["Gender"]], r["Age at marriage"])] = num(r) / 1000.0
    data = []
    for sex in ("M", "F", "both"):
        for label, lo, hi in GROUPS:
            h = rate[(year, "both", label)]
            if sex != "both":
                h *= rate[(SEX_RATIO_YEAR, sex, label)] / rate[(SEX_RATIO_YEAR, "both", label)]
            for age in range(lo, hi + 1):
                data.append((age, sex, fmt(h)))
    print("reference year", year, "| sex differential from", SEX_RATIO_YEAR)
    write(out, "first_marriage.csv", ["age", "sex", "hazard"], data)


if __name__ == "__main__":
    main()
