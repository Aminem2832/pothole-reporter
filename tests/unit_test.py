# -*- coding: utf-8 -*-
"""Unit tests for the engine's pure logic.

These reach the real functions through StandaloneAPI.__pure, so a test exercises exactly
the code that runs in production. No network, no photo, no model: everything here is
deterministic and should stay that way.
"""
import json, sys, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = r"""
(() => {
  const P = StandaloneAPI.__pure;
  const out = [];
  const eq = (name, got, want) => out.push([name, JSON.stringify(got) === JSON.stringify(want), got, want]);
  const ok = (name, cond, detail) => out.push([name, !!cond, detail === undefined ? cond : detail, true]);

  // ---- distMeters: the dedupe radius and the 8 m capture spacing both rest on this ----
  const d = P.distMeters(12.9115, 77.6427, 12.9115, 77.6427);
  ok("distMeters: same point is zero", d === 0, d);
  const north = P.distMeters(12.9115, 77.6427, 12.91240, 77.6427);   // ~100 m north
  ok("distMeters: 100 m north", Math.abs(north - 100) < 3, Math.round(north));
  // A degree of longitude is shorter at this latitude; a formula ignoring that reads ~111 m.
  const east = P.distMeters(12.9115, 77.6427, 12.9115, 77.64362);
  ok("distMeters: east distance accounts for latitude", Math.abs(east - 100) < 5, Math.round(east));

  // ---- peekVerdict: reads a streaming JSON response before it is complete ----
  eq("peek: nothing yet", P.peekVerdict('{"is_'), null);
  eq("peek: false needs no confidence", P.peekVerdict('{"is_pothole": false'), {is_pothole:false, size:null});
  eq("peek: true without confidence waits", P.peekVerdict('{"is_pothole": true, "size": "large"'), null);
  // The bug this guards: a number arrives in pieces, so 0.8 can be read mid-stream as "0."
  eq("peek: half-arrived number is not read",
     P.peekVerdict('{"is_pothole": true, "size": "large", "confidence": 0.'), null);
  eq("peek: complete number is read",
     P.peekVerdict('{"is_pothole": true, "size": "large", "confidence": 0.8,'),
     {is_pothole:true, size:"large"});
  eq("peek: below the gate is not a pothole",
     P.peekVerdict('{"is_pothole": true, "size": "small", "confidence": 0.4,'),
     {is_pothole:false, size:"small"});
  eq("peek: exactly at the gate counts",
     P.peekVerdict('{"is_pothole": true, "size": "small", "confidence": 0.5,'),
     {is_pothole:true, size:"small"});

  // ---- peekReject: decides when Drive Mode may stop reading the response early ----
  ok("reject: not yet decidable", P.peekReject('{"is_pothole"') === false);
  ok("reject: false is immediately final", P.peekReject('{"is_pothole": false') === true);
  ok("reject: true alone is not final", P.peekReject('{"is_pothole": true, "size": "large"') === false);
  ok("reject: half-arrived number does not decide",
     P.peekReject('{"is_pothole": true, "size": "large", "confidence": 0.') === false);
  ok("reject: low confidence is final",
     P.peekReject('{"is_pothole": true, "size": "large", "confidence": 0.3}') === true);
  ok("reject: high confidence must not abort",
     P.peekReject('{"is_pothole": true, "size": "large", "confidence": 0.9,') === false);

  // An accepted frame must never be reported as rejected, at any prefix of the response.
  const accepted = '{"is_pothole": true, "size": "large", "confidence": 0.87, "looks_like_speed_breaker": false, "description": "x"}';
  let wrongAbort = null;
  for (let i = 1; i <= accepted.length; i++) if (P.peekReject(accepted.slice(0, i))) { wrongAbort = i; break; }
  ok("reject: never aborts an accepted frame at any prefix", wrongAbort === null, wrongAbort);

  // ---- rejectedVerdict: what the caller receives after an early abort ----
  const rv = P.rejectedVerdict('{"is_pothole": false, "size"');
  ok("rejectedVerdict: not a pothole", rv.is_pothole === false, rv);
  ok("rejectedVerdict: shape is complete",
     "confidence" in rv && "size" in rv && "description" in rv, Object.keys(rv));

  // ---- warrantyFor: decides a sentence in a letter naming a private company ----
  const NOW = Date.UTC(2026, 7, 20);
  eq("warranty: 6 months old is defect liability",
     P.warrantyFor("20-02-2026", NOW), {warranty:"within the defect liability period", warranty_code:"dlp"});
  eq("warranty: 2 years old is maintenance",
     P.warrantyFor("20-08-2024", NOW), {warranty:"within the maintenance period", warranty_code:"maint"});
  eq("warranty: 5 years old claims nothing",
     P.warrantyFor("20-08-2021", NOW), {warranty:"recorded for this stretch", warranty_code:"record"});
  eq("warranty: unparseable date claims nothing",
     P.warrantyFor("not a date", NOW), {warranty:"recorded for this stretch", warranty_code:"record"});
  eq("warranty: missing date claims nothing",
     P.warrantyFor(null, NOW), {warranty:"recorded for this stretch", warranty_code:"record"});
  eq("warranty: a future date claims nothing",
     P.warrantyFor("20-08-2027", NOW), {warranty:"recorded for this stretch", warranty_code:"record"});
  eq("warranty: month 13 is not a date",
     P.warrantyFor("20-13-2025", NOW), {warranty:"recorded for this stretch", warranty_code:"record"});

  // ---- listDict: the list must never carry the full-size evidence photo ----
  const rec = {id:1, photo:"P", photo_full:"F", status:"draft"};
  ok("listDict: omits the evidence copy", P.listDict(rec).photo_full === undefined, P.listDict(rec));
  ok("listDict: keeps the thumbnail", P.listDict(rec).photo_url === "P");
  ok("toDict: the detail form keeps both",
     P.toDict(rec).photo_full === "F" && P.toDict(rec).photo_url === "P");

  // ---- inCoverage: only ever gates speculation, never routing ----
  ok("inCoverage: no location is not covered", P.inCoverage(null, null, null) === false);

  return out;
})()
"""

def main():
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-web-security"])
        pg = b.new_context(viewport={"width": 390, "height": 844}).new_page()
        pg.goto("http://localhost:8765/"); pg.wait_for_load_state("networkidle")
        pg.wait_for_function("typeof StandaloneAPI !== 'undefined' && StandaloneAPI.__pure", timeout=30000)
        results = pg.evaluate(CASES)
        b.close()
    for name, passed, got, want in results:
        if passed:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name}\n         got  {got}\n         want {want}")
            fails.append(name)
    print()
    if fails:
        print(f"{len(fails)} of {len(results)} failed"); sys.exit(1)
    print(f"UNIT TESTS PASS ({len(results)} checks)")

main()
