"""interprovincial_flows.csv from StatCan 17-10-0022-01. Status: derived.
share(origin -> destination) = migrants(origin, destination) / sum over destinations.
Default period 2023/2024 = latest FINAL estimates (2024/2025 is preliminary, built from Canada
child benefit records, and has zero counts for several small flows). Override with a 3rd argument.
The combined 'Northwest Territories including Nunavut' series is dropped."""
import sys
from common import dirs, rows, write, fmt, num

PID = "17100022"
CODES = {"Newfoundland and Labrador": "NL", "Prince Edward Island": "PE", "Nova Scotia": "NS",
         "New Brunswick": "NB", "Quebec": "QC", "Ontario": "ON", "Manitoba": "MB", "Saskatchewan": "SK",
         "Alberta": "AB", "British Columbia": "BC", "Yukon": "YT", "Northwest Territories": "NT", "Nunavut": "NU"}
ORDER = list(CODES.values())


def main():
    cache, out = dirs(sys.argv[:3])
    flows = {}
    for r in rows(cache, PID):
        o = r["GEO"].replace(", province of origin", "")
        d = r["Geography, province of destination"].replace(", province of destination", "")
        if o in CODES and d in CODES and o != d and r["VALUE"] != "":
            flows.setdefault(r["REF_DATE"], {})[(CODES[o], CODES[d])] = num(r)
    period = sys.argv[3] if len(sys.argv) > 3 else "2023/2024"
    assert len(flows[period]) == 13 * 12
    f = flows[period]
    data = []
    for o in ORDER:
        tot = sum(f[(o, d)] for d in ORDER if d != o)
        for d in ORDER:
            if d != o:
                data.append((o, d, fmt(f[(o, d)] / tot)))
    print("reference period", period)
    write(out, "interprovincial_flows.csv", ["origin", "destination", "share"], data)


if __name__ == "__main__":
    main()
