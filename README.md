# Pothole Reporter

An Android app that runs entirely on the phone. It photographs potholes (or
watches the road continuously in Drive Mode), verifies and classifies them
with AI vision, resolves the road address, identifies the concerned city
corporation commissioner and the road contractor on public record, and opens
a ready-to-send complaint email for your review. The app never sends email
itself: you press send in your email app.

No server, no backend, no credentials in the APK. The app is the product.

**Coverage: Bengaluru only.** The officer directory holds the five Greater
Bengaluru Authority city corporations, and the bundled contracts are BBMP
contracts. Outside Bengaluru the app still detects the pothole and saves the
photo and location, but it will not name a recipient or a contractor, because
guessing would address your complaint to a body with no jurisdiction over that
road. Those reports are marked "Outside coverage". Extending to the rest of
Karnataka is on the roadmap below.

![How a photo becomes a complaint](docs/architecture.png)

Editable source: [`docs/architecture.excalidraw`](docs/architecture.excalidraw),
which you can open and change at [excalidraw.com](https://excalidraw.com).

## What it actually catches

This is a real photo taken with the app, and the real output it produced. Nothing
here is illustrative: the verdict, the routed officer and the contract were all
resolved by the pipeline on the phone.

<img src="docs/example-pothole.jpg" width="380" alt="Pothole on 17th Main Road, HSR Layout, Bengaluru">

| | |
|---|---|
| Verdict | **medium pothole**, confidence 0.78 |
| Description | Two medium-sized potholes (approx. 30–60 cm) on the near center-right lane of the road; uneven surface may cause hazard to two-wheelers. |
| Address | 17th Main Road, Sector 3, HSR Layout, Bengaluru South City Corporation, Bengaluru, Bangalore South, Bengaluru Urban, Karnataka, 560102, India |
| Routed to | Commissioner, Bengaluru South City Corporation (BSCC) |
| Probable contract | `BBMP/2024-25/RD/WORK_INDENT3877` |
| Contractor | SHARANAPPA SANGAMESH( SANGAMESH INFRASTRUCTURE INDIA PRIVATE LIMITED ) |

The complaint it drafted, which the app opens in your email app for you to send:

```text
Dear Commissioner, Bengaluru South City Corporation (BSCC),

I would like to report a pothole that needs urgent repair.

Location: 17th Main Road, Sector 3, HSR Layout, Bengaluru South City Corporation, Bengaluru, Bangalore South, Bengaluru Urban, Karnataka, 560102, India
Coordinates: 12.911500, 77.642700
Map link: https://maps.google.com/?q=12.911500,77.642700
Approximate size: medium
Details: Two medium-sized potholes (approx. 30–60 cm) on the near center-right lane of the road; uneven surface may cause hazard to two-wheelers.

A photograph of the pothole is attached to this email. This pothole poses a danger to two wheeler riders and other road users. I request the city corporation to inspect and repair it at the earliest, and to route it to the contractor responsible if this road section is still under a maintenance warranty. I am also filing this grievance on Sahaaya so it can be tracked to resolution.

Public procurement records indicate this road stretch probably falls under tender BBMP/2024-25/RD/WORK_INDENT3877 ("Pothole Filling Works under Maintenance Works in Ward No. 221-HSR Layout for the year 2024-25 in Bommanahalli Division."), awarded on 13-09-2024 to SHARANAPPA SANGAMESH( SANGAMESH INFRASTRUCTURE INDIA PRIVATE LIMITED ), and is possibly still within the maintenance period. If the defect liability or maintenance period is in force, I request that the repair be carried out by the contractor at no additional cost to the corporation. This is a probable record match; kindly verify against the tender documents.

Thank you for your service to the city.

Regards,
Gaurav Sen
```

## Install and set up (2 minutes)

1. Download `PotholeReporter.apk` from the
   [Releases page](https://github.com/coding-parrot/pothole-reporter/releases)
   and sideload it (allow "install from unknown sources"), or build it yourself
   (see Development below).
2. On first launch the Settings screen opens. Paste your OpenAI API key and
   your name. Both are stored only on the device.
3. Allow camera and location when prompted.

The app is bilingual: English and Kannada (ಕನ್ನಡ), switchable in Settings.
The complaint email, including the AI-written description, is drafted in the
selected language.

Settings (gear icon) also has:
- **Debug mode:** keep the recorded video of a drive after its footage has been
  analysed, instead of deleting it. Use it to diagnose missed potholes, since the
  video holds every frame rather than the ones the live pass happened to sample.
- **Delete all reports and photos:** wipes the on-device store.
- **Review and label frames:** step through captured frames and mark each one
  pothole or not a pothole. The model's own verdict is shown after the photo, so
  it nudges your eye as little as possible.
- **Export labelled dataset:** packs every frame *you* labelled, plus a
  `labels.json` recording your label alongside what the model said, into a zip
  and hands it to the Android share sheet. No account and no server: it goes to
  Drive, mail or a chat, and from there into `eval/` on a laptop.

Only human-labelled frames are exported. A benchmark built from the detector's
own verdicts cannot measure the detector.

## How it works

**Single shot.** Tap "Report a pothole", shoot. The pipeline runs on the phone
with live stage updates: compress, AI check (`gpt-5-mini`), reverse geocode
(OpenStreetMap Nominatim), officer routing, contract matching, complaint
drafting. Result: an editable draft with photo, address, coordinates, map
link, the routed commissioner, and the probable contract.

**Drive Mode.** Mount the phone facing the road. While you move, the loop polls
every 0.4 s and captures whenever you have covered 8 m, with up to 4 frames
analyzed concurrently, each by a single `gpt-5-mini` call. (A cheaper `gpt-5-nano`
pre-screen used to run first; an eval showed it rejected most real potholes
before the main model ever saw them, so it was removed.)
Frames are read straight off the live preview at its full resolution.
`ImageCapture.takePhoto()` used to be used instead, but it reconfigures the
capture session on every shot, which stutters the preview once a recorder shares
the camera, and it bought nothing: the preview is already 1920 wide, the size the
model is sent. Between 7 PM and 5 AM frames get an automatic brightness and
contrast boost. Sightings within 15 m of a confirmed pothole dedupe. The Stop
button sits on top of the video, the hardware back button also stops the
drive, and every drive ends with an explicit summary, including "No potholes
found in this drive (N frames checked)" when it comes up empty.

**Continuous recording.** A drive also records video, in self-contained clips
written straight to device storage so memory stays flat. Capture therefore never
depends on picking the right interval: the live pass still drafts complaints as
you drive, and the footage keeps the road you covered between frames. Afterwards,
expand the drive in history and tap **Analyse footage** to pull frames back out at
a chosen spacing and run them through the same pipeline. Positions come from a
timestamped GPS track recorded alongside, and results dedupe against what the
live pass already found. A drive offers this as soon as it ends, which is when the
footage is worth the most.

**What is kept.** Frames the AI rejected are never stored: the footage already
holds every frame, so keeping the rejects as separate images filled the device for
nothing. Confirmed potholes are kept as photos. The video itself is deleted once
its footage has been analysed, freeing the space, unless **Debug mode** is on, in
which case the video is kept too. Declining the analysis keeps the video, since it
is then the only copy of the road you covered. Recording runs about 18 MB per
minute, so a half-hour drive is roughly 500 MB before it is processed away.

The clips are re-analysable, which is the real reason to keep them: when
detection improves, old drives can be re-run, where discarded frames are gone.

**Review and send.** Every confirmed pothole is an editable draft. The
"Email" button opens your email app pre-filled: recipient, subject, body,
photo attached. You press send there. Canceling the composer leaves the
report editable and reopenable ("Opened in email" status). Walking works the
same as driving; there is no accelerometer involved anywhere.

**Your contribution.** A dashboard on the home screen totals potholes found,
complaints sent, frames checked, drives, kilometres of road covered (from the
recorded GPS tracks) and footage held, breaks the finds down by size and by city
corporation, and pins every located pothole on a map. Tapping a pin opens that
report. Leaflet is vendored into the APK rather than loaded from a CDN, so the app
still works offline; the map tiles do need a connection, and without one the same
points are plotted on a plain scatter instead.

**Storage.** Reports and their photos live in on-device IndexedDB and appear in
the history list with status chips: Draft, Opened in email, Not a pothole,
Outside coverage. Past drives collapse into a single row showing the date,
potholes found and frames actually checked; tap to expand. Inside a drive the
confirmed potholes sort above the frames that were checked and dismissed, so a
drive with three finds among two hundred frames does not bury them. Tap any photo to open
it full screen, pinch to zoom, and swipe or use the arrows to move between
records without going back to the list.

## Who receives complaints

BBMP was dissolved in September 2025; Bengaluru is run by the Greater
Bengaluru Authority (GBA) through five city corporations. Each complaint is
addressed to the commissioner whose corporation contains the pothole,
resolved from the reverse-geocoded address, with GBA HQ (`comm@bbmp.gov.in`)
as the fallback when the location cannot be resolved. The verified addresses
(official GBA site, Aug 2026) live in `static/standalone.js`. If GPS is
unavailable, single-shot still produces a draft (photo plus a note that the
location must be added); Drive Mode waits for a GPS fix before capturing.

Note: email is a contact channel. The tracked grievance channel with ticket
numbers is the Sahaaya 2.0 / Namma Bengaluru app; file there too when it
matters.

## Contract matching

The APK bundles 1,877 awarded road-work contracts (Aug 2023 to Apr 2026)
originating from KPPP, the Karnataka Public Procurement Portal, via the
public-domain snapshot at bengaluru-road-contracts.pages.dev. When a match
clears a confidence gate, the complaint names the tender number, contractor,
and an indicative warranty status, always worded as a probable match for the
officer to verify against the tender documents. Award records carry no defect
liability period, so warranty status is a reported-practice heuristic, not a
per-contract fact.

To refresh the dataset: update `data/tenders.csv`, run
`python3 make_tenders_json.py`, rebuild the APK.

## Costs

Every analyzed image is an OpenAI API call on your key: one `gpt-5-mini` call
per captured frame or photo, plus one text call to match the contract, made
only once a pothole is confirmed. Removing the `gpt-5-nano` pre-screen bought
recall at the price of running the main model on every frame, so a long drive
costs more than it used to: budget rupees per drive, not paise. Debug mode
does not add calls, it only stores what was already analyzed.

## Development

- Source of truth: `static/index.html` (UI) and `static/standalone.js` (the
  whole engine: OpenAI Responses API with structured outputs, IndexedDB,
  routing, tender matching, native email composer via Capacitor).
- Build: copy both files to `android-app/www/`, then in `android-app/` run
  `npx cap sync android`, and in `android-app/android/` run
  `./gradlew assembleDebug` with
  `ANDROID_HOME=/opt/homebrew/share/android-commandlinetools`.
- Test harness: serve `android-app/www/` with any static file server and open
  `http://localhost:8765/?key=sk-...` in Chromium launched with
  `--disable-web-security` (stands in for the WebView's CORS-free native
  HTTP).
- `reports.db` and `photos/` in the project root are archives from the
  retired server era; the app does not use them.

## Disclaimer

Contract matches are probabilistic and always worded as "probable match,
kindly verify against the tender documents"; keep that wording. The app never
sends email; every complaint is sent by you, from your account, and you are
responsible for what you send. This project is not legal advice and is not
affiliated with GBA, BBMP, or any government body.

## Credits

- Map: [Leaflet](https://leafletjs.com) (BSD-2-Clause), vendored in
  `static/vendor/`, with tiles from OpenStreetMap
- Contract data: public-domain KPPP award snapshot by
  [bengaluru-road-contracts.pages.dev](https://bengaluru-road-contracts.pages.dev)
  (ultimate source: Karnataka Public Procurement Portal)
- Officer directory: official GBA website (verified Aug 2026)
- Reverse geocoding: OpenStreetMap Nominatim
- Built with OpenAI vision models for detection and drafting

## License

MIT. See [LICENSE](LICENSE).

## Roadmap ideas

- Pan-Karnataka coverage. Karnataka has 319 urban local bodies (18 city
  corporations, then city and town councils and panchayats), plus PWD for state
  highways and the panchayat engineering department for rural roads. The state
  GIS (KGIS) answers "which body owns this point" from a lat/lng in one query
  and returns the national LGD code, which is the right key for an officer
  directory. Karnataka ULB emails are published per district on the NIC district
  sites. KPPP covers road contracts statewide, not just Bengaluru.
- Keystore-backed key storage
- Offline corporation routing via boundary polygons (no Nominatim dependency)
- Fresh tender data past Apr 2026 (KPPP API pull) and ward-polygon matching
- Post-drive batch analysis mode (cheaper, non-live) and a local YOLO
  pre-filter (RDD2022) for near-zero-cost continuous drives
- Sahaaya auto-filing if a public API ever appears
