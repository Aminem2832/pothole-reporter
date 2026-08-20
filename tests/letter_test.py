# -*- coding: utf-8 -*-
"""The letter must be true for whoever receives it.

164 of the 182 addressable bodies are municipal councils or town panchayats, headed by a
Chief Officer. Calling them "the city corporation" is wrong for nine recipients in ten, and
a letter that gets the reader's own office wrong is easy to dismiss.
"""
import sys, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
fails = []

JS = r"""
(() => {
  const P = StandaloneAPI.__pure;
  const a = { is_pothole: true, size: "medium", confidence: 0.8, description: "d" };
  const tender = { tender_number: "DMA/1", contractor: "ACME", title: "Road work",
                   published: "01-02-2026", warranty: "within the defect liability period",
                   warranty_code: "dlp" };
  const out = {};
  const [, councilBody] = P.draftEmail(a, 12.9, 77.6, "Main Road, Channagiri, 577213",
                                       "Chief Officer, Channagiri", tender);
  const [, corpBody] = P.draftEmail(a, 12.9, 77.6, "17th Main, HSR Layout, Bengaluru",
                                    "Commissioner, Bengaluru South City Corporation", tender);
  out.council = councilBody;
  out.corporation = corpBody;
  // and the no-contract case, which most complaints are
  const [, noTender] = P.draftEmail(a, 12.9, 77.6, "Main Road, Channagiri, 577213",
                                    "Chief Officer, Channagiri", null);
  out.noTender = noTender;
  return out;
})()
"""

with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-web-security"])
    pg = b.new_context(viewport={"width": 390, "height": 844}).new_page()
    pg.goto("http://localhost:8765/"); pg.wait_for_load_state("networkidle")
    pg.wait_for_function("typeof StandaloneAPI !== 'undefined' && StandaloneAPI.__pure", timeout=30000)
    r = pg.evaluate(JS)
    b.close()

council = r["council"]
print("  letter to a Chief Officer of a town municipal council:")
for line in council.split("\n"):
    if line.strip(): print(f"    | {line[:104]}")

for phrase in ("city corporation", "the city"):
    if phrase in council:
        fails.append(f'a letter to a Chief Officer says "{phrase}", but that body is not a corporation')
if "Chief Officer, Channagiri" not in council:
    fails.append("the greeting does not address the routed officer")
if "probable" not in council.lower() and "may still be" not in council.lower():
    fails.append("the contract claim lost its hedge")
if "ACME" not in council:
    fails.append("the contractor is not named when one is recorded")
if "no winning bidder" in r["noTender"] or "ACME" in r["noTender"]:
    fails.append("a report with no contract still discusses one")

print()
if fails:
    print("FAIL"); [print("  -", f) for f in fails]; sys.exit(1)
print("LETTER TEST PASS")
