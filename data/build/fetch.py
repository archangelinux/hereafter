"""Download every raw input into <cache_dir>.  usage: python3 fetch.py <cache_dir>

Full-table CSV zips come from https://www150.statcan.gc.ca/n1/tbl/csv/<PID>-eng.zip.
Table 98-10-0410-01 is ~287 MB zipped, so only the 72 cells we need are pulled
through the StatCan Web Data Service (WDS) and stored as 98100410_wds.json.
"""
import json
import os
import sys
import urllib.request

ZIP_PIDS = [
    "13100114",  # life tables
    "13100418",  # fertility
    "39100057",  # marriage rates by age / legal marital status
    "39100054",  # divorces by duration of marriage
    "14100051",  # job tenure
    "17100005",  # population July 1
    "17100014",  # international migration components by age
    "17100015",  # interprovincial migration by age
    "17100022",  # interprovincial origin-destination
    "36100101",  # DHEA households by income quintile x characteristic (owner/renter)
    "98100231",  # Census 2021 tenure by age of primary household maintainer
    "98100064",  # Census 2021 total income groups by age
    "98100066",  # Census 2021 employment income groups by age
]

# 98-10-0410-01 coordinates: geo.gender.age.education.work_activity.income_year.field.statistic
WDS_PID = 98100410
AGE_MEMBERS = {3: (15, 24), 8: (25, 34), 11: (35, 44), 14: (45, 54), 17: (55, 64), 20: (65, 120)}
FIELD_MEMBERS = {1: "all", 3: "education", 4: "arts", 5: "humanities", 6: "social_sciences_law",
                 7: "business", 8: "sciences", 9: "math_cs", 10: "engineering", 11: "agriculture",
                 12: "health", 13: "services"}
INCOME_YEAR_MEMBER = 1   # 1 = 2020, 2 = 2019
STAT_MEDIAN = 3          # Median employment income ($)


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                          "User-Agent": "hereafter-data-build"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: fetch.py <cache_dir>")
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)
    for pid in ZIP_PIDS:
        dest = os.path.join(cache, f"{pid}.zip")
        if os.path.exists(dest) and os.path.getsize(dest) > 10000:
            print("cached", pid)
            continue
        print("downloading", pid)
        with open(dest, "wb") as fh:
            fh.write(get(f"https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip"))

    dest = os.path.join(cache, f"{WDS_PID}_wds.json")
    if not os.path.exists(dest):
        print("querying WDS for", WDS_PID)
        reqs = [{"productId": WDS_PID,
                 "coordinate": f"1.1.{a}.1.1.{INCOME_YEAR_MEMBER}.{f}.{STAT_MEDIAN}.0.0",
                 "latestN": 1}
                for a in AGE_MEMBERS for f in FIELD_MEMBERS]
        raw = get("https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods",
                  json.dumps(reqs).encode())
        cells = []
        for item in json.loads(raw):
            if item["status"] != "SUCCESS":
                raise SystemExit(f"WDS failure: {item}")
            o = item["object"]
            c = o["coordinate"].split(".")
            dp = o["vectorDataPoint"][0]
            lo, hi = AGE_MEMBERS[int(c[2])]
            cells.append({"coordinate": o["coordinate"], "field": FIELD_MEMBERS[int(c[6])],
                          "age_lo": lo, "age_hi": hi, "income_year": 2020,
                          "median_employment_income": dp["value"],
                          "statusCode": dp["statusCode"], "symbolCode": dp["symbolCode"],
                          "refPer": dp["refPer"], "releaseTime": dp["releaseTime"]})
        with open(dest, "w") as fh:
            json.dump({"productId": WDS_PID, "cells": cells}, fh, indent=1)
    print("done")


if __name__ == "__main__":
    main()
