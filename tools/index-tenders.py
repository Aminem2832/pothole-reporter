#!/usr/bin/env python3
"""Stamp each municipal contract with the LGD code of the body that owns it.

The app already knows which local body contains a pothole: the state GIS returns its
LGD code. Without this field the matcher could not use that, and fell back to scoring
every municipal contract in Karnataka by address tokens, which is both slow and how a
contract from the wrong town gets shortlisted in the first place.

Every municipal row names its body in the location field ("DMA City Corporation
Mysuru"), so the mapping is done once here rather than guessed at runtime.
"""
import json, re, difflib, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
rows = json.load(open(ROOT / "data/tenders-karnataka.json"))
rows = rows if isinstance(rows, list) else rows.get("tenders", [])
bodies = json.load(open(ROOT / "data/karnataka-bodies.json"))["bodies"]

# Bengaluru's five corporations replaced BBMP in 2025 and inherited its works, which the
# award records still file under BBMP zone names ("BBMP Bommanahalli Division"). Zone to
# corporation is not published, so a legacy BBMP contract is offered to any Bengaluru
# corporation rather than guessed at. Within Bengaluru that is the status quo.
BLR = "BLR"
BLR_CODES = {c for c, b in bodies.items()
             if any(w in b["name"].lower() for w in ("bengaluru", "bangalore"))}

VARIANTS = [("dharawada","dharwad"),("hubballi","hubli"),("bengaluru","bangalore"),
            ("mysuru","mysore"),("belagavi","belgaum"),("kalaburagi","gulbarga"),
            ("ballari","bellary"),("vijayapura","bijapur"),("shivamogga","shimoga"),
            ("tumakuru","tumkur"),("chikkamagaluru","chikmagalur"),
            ("chamarajanagara","chamarajanagar"),("uu","u"),("oo","o"),("aa","a"),
            ("ee","i"),("th","t"),("dh","d"),("bh","b"),("kh","k")]
STRIP = ["dma","bbmp","city corporation","city municipal council","town municipal council",
         "town panchayat","municipal corporation","nagara panchayat","corporation","council"]

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z]", " ", s)
    for a, b in VARIANTS: s = s.replace(a, b)
    return re.sub(r"\s+", "", s)

def body_part(loc):
    low = (loc or "").lower()
    for p in STRIP: low = low.replace(p, " ")
    return low.strip()

by_norm = {}
for code, b in bodies.items():
    by_norm.setdefault(norm(b["name"]), code)
keys = list(by_norm)

cache, stats = {}, {"mapped": 0, "blr": 0, "unmapped": 0}
for r in rows:
    agency = (r.get("tn") or "").split("/")[0].upper()
    if agency not in ("DMA", "BBMP"):
        r.pop("b", None)
        continue
    loc = (r.get("loc") or "").strip()
    if loc not in cache:
        if agency == "BBMP":
            cache[loc] = BLR
        else:
            n = norm(body_part(loc))
            code = by_norm.get(n)
            if not code:
                m = difflib.get_close_matches(n, keys, n=1, cutoff=0.86)
                code = by_norm[m[0]] if m else None
            cache[loc] = code
    code = cache[loc]
    if code == BLR: stats["blr"] += 1; r["b"] = BLR
    elif code:     stats["mapped"] += 1; r["b"] = code
    else:          stats["unmapped"] += 1; r.pop("b", None)

out = ROOT / "data/tenders-karnataka.json"
json.dump(rows, open(out, "w"), separators=(",", ":"))
json.dump(rows, open(ROOT / "android-app/www/tenders.json", "w"), separators=(",", ":"))

print(f"stamped {stats['mapped']} rows with a body code")
print(f"        {stats['blr']} legacy BBMP rows marked {BLR} (any Bengaluru corporation)")
print(f"        {stats['unmapped']} municipal rows left unstamped (body has no published address)")
idx = {}
for r in rows:
    if r.get("b"): idx.setdefault(r["b"], 0); idx[r["b"]] += 1
print(f"\nindexed bodies: {len(idx)}")
for code, n in sorted(idx.items(), key=lambda x: -x[1])[:8]:
    name = "Bengaluru (5 corporations)" if code == BLR else bodies[code]["name"]
    print(f"  {n:6}  {name}")
