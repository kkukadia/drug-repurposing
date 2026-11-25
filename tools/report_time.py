import csv
import sys
from pathlib import Path

log = Path(__file__).resolve().parent.parent / "BUILD_TIME.csv"
rows = list(csv.DictReader(log.open())) if log.exists() else []
by = {}
for r in rows:
    by[r["label"]] = by.get(r["label"], 0) + int(r["seconds"])
total = sum(by.values())
for k, v in sorted(by.items(), key=lambda x: -x[1]):
    print(f"{k:30s} {v//3600}h {v%3600//60}m {v%60}s")
print(f"{'TOTAL active run time':30s} {total//3600}h {total%3600//60}m {total%60}s")
