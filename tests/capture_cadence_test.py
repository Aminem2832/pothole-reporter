# -*- coding: utf-8 -*-
"""While the car is moving, the app must keep looking at the road.

Taken from a real drive: 45 seconds down a street with at least five potholes produced
5 frames checked, one every 9 seconds, which is exactly STILL_CAPTURE_MS. Every capture
came from the stationary fallback, so the movement gate never fired once and the HUD read
"Holding position" while the road streamed past.

The cause is that a phone can redeliver the same fix, or a coarse one that barely moves.
Staleness was measured from delivery time, so a stuck fix looked perpetually fresh, and
displacement then said the car had not moved.
"""
import os, sys, pathlib
from dotenv import load_dotenv
ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
from playwright.sync_api import sync_playwright

KEY = os.environ["OPENAI_API_KEY"]
SECONDS = 20

SCENARIOS = [
    # name, how the position behaves, whether speed is reported
    ("a fix that never moves, speed reported", "stuck", True),
    ("a fix that never moves, no speed",       "stuck", False),
    ("a coarse fix jittering under 8 m",       "jitter", False),
    ("genuinely parked, precise fix, speed 0",  "parked", True),
]

JS = r"""
async ([mode, withSpeed, seconds]) => {
  // Drive the app with a synthetic geolocation source and count what it captures.
  let captures = 0;
  const realFetchFrame = StandaloneAPI.handle;
  StandaloneAPI.handle = async (path, opts) => {
    if (path === "/api/frame") { captures++; return { found: false }; }
    return realFetchFrame(path, opts);
  };
  const base = { lat: 12.9115, lng: 77.6427 };
  let cbs = [];
  const realWatch = navigator.geolocation.watchPosition.bind(navigator.geolocation);
  navigator.geolocation.watchPosition = (ok) => { cbs.push(ok); return 1; };
  navigator.geolocation.clearWatch = () => {};
  navigator.geolocation.getCurrentPosition = (ok) => ok(mk());
  function mk() {
    let lat = base.lat, lng = base.lng;
    if (mode === "jitter") { lat += (Math.random() - 0.5) * 0.00005; lng += (Math.random() - 0.5) * 0.00005; }
    const speed = mode === "parked" ? 0 : (withSpeed ? 8.3 : null);
    return { coords: { latitude: lat, longitude: lng, accuracy: mode === "jitter" ? 60 : 12,
                       speed },
             timestamp: Date.now() };  // a phone stamps each delivery, even a stale one
  }
  await startDrive();
  const pump = setInterval(() => cbs.forEach((cb) => cb(mk())), 500);
  await new Promise((r) => setTimeout(r, seconds * 1000));
  clearInterval(pump);
  try { await stopDrive(); } catch (e) {}
  StandaloneAPI.handle = realFetchFrame;
  navigator.geolocation.watchPosition = realWatch;
  return captures;
}
"""

fails = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-web-security", "--allow-running-insecure-content",
                                "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = b.new_context(viewport={"width": 390, "height": 844},
                        permissions=["geolocation", "camera"],
                        geolocation={"latitude": 12.9115, "longitude": 77.6427})
    for name, mode, withSpeed in SCENARIOS:
        # A fresh page per scenario. Sharing one page let drive state and patched globals
        # leak across runs, which made a correct build look broken.
        pg = ctx.new_page()
        pg.goto(f"http://localhost:8765/?key={KEY}"); pg.wait_for_load_state("networkidle")
        pg.wait_for_function("typeof startDrive === 'function'", timeout=30000)
        pg.evaluate("window.alert = () => {}; window.confirm = () => true;")
        n = pg.evaluate(JS, [mode, withSpeed, SECONDS])
        pg.close()
        rate = n / SECONDS
        # At 30 km/h, one frame every 8 s is 66 m of unlooked-at road. The real drive
        # managed one per 9 s. Anything slower than one per 4 s is not scanning a street.
        # Parked with a precise fix is the one case that SHOULD be slow: there is no new
        # road to look at, and photographing the same spot costs money for nothing.
        # Moving: at least one frame every 2 s, so a city street is actually scanned.
        ok = (rate <= 0.2) if mode == "parked" else (rate >= 0.5)
        print(f"  {name:40} {n:3} frames in {SECONDS}s  ({1/rate:.1f}s apart)" if n else
              f"  {name:40} {n:3} frames in {SECONDS}s")
        if not ok:
            fails.append(f"{name}: {n} frames in {SECONDS}s, "
                         + ("faster than one every 5 s while parked" if mode == "parked"
                            else "slower than one every 2 s"))
    b.close()

print()
if fails:
    print("FAIL"); [print("  -", f) for f in fails]; sys.exit(1)
print("CAPTURE CADENCE TEST PASS")
