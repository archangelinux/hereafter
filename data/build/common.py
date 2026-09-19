"""Shared helpers for the Hereafter data reduction scripts (stdlib only).

Every build_*.py script is run as:  python3 build_x.py <cache_dir> [out_dir]
<cache_dir> holds the raw StatCan downloads created by fetch.py.
[out_dir] defaults to the parent directory of this file (i.e. data/).
"""
import csv
import io
import os
import sys
import zipfile


def dirs(argv):
    if len(argv) < 2:
        sys.exit(f"usage: {argv[0]} <cache_dir> [out_dir]")
    cache = argv[1]
    out = argv[2] if len(argv) > 2 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return cache, out


def rows(cache, pid):
    """Yield dict rows from the data CSV inside <cache>/<pid>.zip."""
    with zipfile.ZipFile(os.path.join(cache, f"{pid}.zip")) as z:
        with z.open(f"{pid}.csv") as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))


def select(cache, pid, **eq):
    """Rows where row[col] == value for every filter. Column names with spaces
    are passed via a dict: select(cache, pid, **{"Age group": "x"})."""
    for r in rows(cache, pid):
        if all(r[k] == v for k, v in eq.items()):
            yield r


def num(r, col="VALUE"):
    v = r[col]
    if v in ("", None):
        raise ValueError(f"empty value in row {r}")
    return float(v)


def write(out_dir, name, header, data):
    path = os.path.join(out_dir, name)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(data)
    print(f"wrote {path}: {len(data)} rows")


def fmt(x, nd=6):
    """Fixed decimals, trailing zeros trimmed."""
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"
