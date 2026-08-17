"""Regenerate the app's bundled contract dataset from data/tenders.csv.
Run after refreshing the CSV, then rebuild the APK.
Source: bengaluru-road-contracts.pages.dev (KPPP awards, public domain)."""

import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(BASE / "data" / "tenders.csv", encoding="utf-8")))
slim = [
    {"w": r["ward_number"], "tn": r["tender_number"], "t": r["title"],
     "loc": r["location"], "c": r["winner_name"], "d": r["published_date"][:10]}
    for r in rows
]
json.dump(slim, open(BASE / "android-app" / "www" / "tenders.json", "w"), ensure_ascii=False)
print(f"tenders.json regenerated: {len(slim)} contracts")
