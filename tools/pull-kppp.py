#!/usr/bin/env python3
"""Pull awarded works statewide from KPPP and keep the road-related ones.

The search endpoint needs no login. It does not return the winning bidder, which only
the per-tender full view carries, so statewide rows name the tender and the department
and leave the contractor blank; the complaint template already says "no winning bidder
recorded" in that case rather than inventing one. Bengaluru winners already held in
data/tenders.csv are merged back in by tender number.
"""
import json, re, sys, time, urllib.request

API = ("https://kppp.karnataka.gov.in/supplier-registration-service/v1/api"
       "/portal-service/works/search-eproc-tenders")
HEADERS = {
    "content-type": "application/json",
    "Referer": "https://kppp.karnataka.gov.in/",
    "Post": "CONTRACTOR-EPROC-CONTRACTOR",          # the portal's own non-standard header
    "User-Agent": "Mozilla/5.0 (pothole-reporter dataset build)",
}
ROAD = re.compile(r"road|pothole|asphalt|black\s*top|\bbt\b|resurfac|re-surfac|tar(?:ring)?|"
                  r"drain|footpath|culvert|pavement|kerb|curb|patch", re.I)
SIZE = 1000

def page(n):
    req = urllib.request.Request(f"{API}?page={n}&size={SIZE}&order-by-tender-publish=true",
                                 data=json.dumps({"category": "WORKS", "status": "AWARDED"}).encode(),
                                 headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("x-total-count") or 0)
        body = json.loads(r.read())
    return (body if isinstance(body, list) else body.get("content", [])), total

kept, seen, total = [], set(), None
n = 0
while True:
    for attempt in range(3):
        try:
            rows, total = page(n); break
        except Exception as e:
            if attempt == 2:
                print(f"page {n} failed: {e}", file=sys.stderr); rows = []
            else: time.sleep(3)
    if not rows: break
    for r in rows:
        tn = (r.get("tenderNumber") or "").strip()
        title = (r.get("description") or r.get("title") or "").strip()
        if not tn or tn in seen or not ROAD.search(title): continue
        seen.add(tn)
        kept.append({"tn": tn, "t": title[:150],
                     "loc": (r.get("locationName") or r.get("deptName") or "").strip()[:60],
                     "c": "", "d": (r.get("publishedDate") or "")[:10]})
    n += 1
    if n % 10 == 0:
        print(f"  page {n}, kept {len(kept)} road works of {n*SIZE} scanned (total {total})", flush=True)
    if total and n * SIZE >= total: break
    time.sleep(0.3)                                  # be a decent guest on a state portal

print(f"scanned {n*SIZE} awarded works, kept {len(kept)} road-related")
json.dump(kept, open("/tmp/kppp_roads.json", "w"))
