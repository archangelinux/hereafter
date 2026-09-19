"""Rebuild every CSV in data/.  usage: python3 build_all.py <cache_dir> [out_dir]
Run fetch.py <cache_dir> first, then check.py [out_dir] afterwards."""
import subprocess
import sys
import os

STEPS = ["mortality", "first_marriage", "divorce", "fertility", "income", "income_bands",
         "homeownership", "job_tenure", "migration", "interprovincial_flows"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: build_all.py <cache_dir> [out_dir]")
    here = os.path.dirname(os.path.abspath(__file__))
    for s in STEPS:
        print(f"== {s}")
        subprocess.run([sys.executable, os.path.join(here, f"build_{s}.py")] + sys.argv[1:3], check=True, cwd=here)
