"""migration.csv. Status: derived (published counts / published population).

 interprovincial_rate = interprovincial out-migrants (17-10-0015-01, GEO=Canada, i.e. the sum of
                        all provinces' out-migrants) / population
 emigration_rate      = emigrants (17-10-0014-01, 'Emigrants' component only: returning emigrants
                        and net temporary emigration are NOT netted off) / population
 population           = 17-10-0005-01 estimate on July 1 at the START of the migration period
                        (period 2023/2024 runs July 1 2023 - June 30 2024 -> July 1 2023 population;
                        the tables give age as of July 1).
Both genders, 5-year age groups as published, 90+ collapsed into one band. field is always `all`:
no published source breaks these flows down by field of study.
"""
import sys
from common import dirs, rows, write, fmt, num

GROUPS = [(f"{a} to {a+4} years", a, a + 4) for a in range(0, 90, 5)] + [("90 years and older", 90, 120)]
LABELS = {g[0] for g in GROUPS}


# 2024/2025 exists but is preliminary (interprovincial flows estimated from Canada child benefit
# records; age split modelled from earlier tax files). 2023/2024 is the latest period whose
# interprovincial counts are final (emigrants: "updated"). Override with a 3rd CLI argument.
DEFAULT_PERIOD = "2023/2024"


def counts(cache, pid, col, member, period):
    return {r["Age group"]: num(r) for r in rows(cache, pid)
            if r["GEO"] == "Canada" and r["Gender"].lower() == "total - gender" and r[col] == member
            and r["Age group"] in LABELS and r["REF_DATE"] == period}


def main():
    cache, out = dirs(sys.argv[:3])
    p1 = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_PERIOD
    outmig = counts(cache, "17100015", "Migrants", "Out-migrants", p1)
    emig = counts(cache, "17100014", "Type of migrant", "Emigrants", p1)
    start_year = p1.split("/")[0]
    pop = {r["Age group"]: num(r) for r in rows(cache, "17100005")
           if r["GEO"] == "Canada" and r["Gender"] == "Total - gender" and r["REF_DATE"] == start_year
           and r["Age group"] in LABELS}
    data = [("all", lo, hi, fmt(outmig[lab] / pop[lab]), fmt(emig[lab] / pop[lab])) for lab, lo, hi in GROUPS]
    print("migration period", p1, "| population July 1", start_year)
    write(out, "migration.csv", ["field", "age_lo", "age_hi", "interprovincial_rate", "emigration_rate"], data)


if __name__ == "__main__":
    main()
