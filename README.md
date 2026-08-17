# Pothole Reporter

An Android app that runs entirely on the phone. It photographs potholes (or
watches the road continuously in Drive Mode), verifies and classifies them
with AI vision, resolves the road address, identifies the concerned city
corporation commissioner and the road contractor on public record, and opens
a ready-to-send complaint email for your review. The app never sends email
itself: you press send in your email app.

No server, no backend, no credentials in the APK. The app is the product.

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
- **Debug mode:** keep every Drive Mode frame, including screened-out and
  rejected ones, as reviewable entries with the reason each failed. Use it to
  diagnose missed potholes; frames add up, so clear them afterwards.
- **Delete all reports and photos:** wipes the on-device store.

## How it works

**Single shot.** Tap "Report a pothole", shoot. The pipeline runs on the phone
with live stage updates: compress, AI check (`gpt-5-mini`), reverse geocode
(OpenStreetMap Nominatim), officer routing, contract matching, complaint
drafting. Result: an editable draft with photo, address, coordinates, map
link, the routed commissioner, and the probable contract.

**Drive Mode.** Mount the phone facing the road. While you move, frames are
captured every 1.2 s with 10 m minimum spacing and up to 3 analyzed
concurrently: a cheap screen (`gpt-5-nano`) first, then the main model
confirms. Frames are true camera stills via `ImageCapture.takePhoto()` where
the device supports it (sharper, photo-grade exposure; the HUD shows
"stills"), with automatic per-drive fallback to preview grabs ("preview"). Between 7 PM and 5 AM frames get an automatic brightness and
contrast boost. Sightings within 15 m of a confirmed pothole dedupe. The Stop
button sits on top of the video, the hardware back button also stops the
drive, and every drive ends with an explicit summary, including "No potholes
found in this drive (N frames checked)" when it comes up empty.

**Review and send.** Every confirmed pothole is an editable draft. The
"Email" button opens your email app pre-filled: recipient, subject, body,
photo attached. You press send there. Canceling the composer leaves the
report editable and reopenable ("Opened in email" status). Walking works the
same as driving; there is no accelerometer involved anywhere.

**Storage.** Reports and their (downscaled) photos live in on-device
IndexedDB and appear in the history list with status chips: Draft, Opened in
email, Not a pothole. Drive Mode reports group by drive session, with a
per-drive header showing frames checked and potholes found.

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
per single shot (plus one text call when contract candidates exist), and in
Drive Mode one `gpt-5-nano` screen per captured frame plus a `gpt-5-mini`
confirmation for frames that pass. A typical city drive costs rupees, not
hundreds; Debug mode does not add calls, it only stores what was already
analyzed.

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

- Contract data: public-domain KPPP award snapshot by
  [bengaluru-road-contracts.pages.dev](https://bengaluru-road-contracts.pages.dev)
  (ultimate source: Karnataka Public Procurement Portal)
- Officer directory: official GBA website (verified Aug 2026)
- Reverse geocoding: OpenStreetMap Nominatim
- Built with OpenAI vision models for detection and drafting

## License

MIT. See [LICENSE](LICENSE).

## Roadmap ideas

- Keystore-backed key storage
- Offline corporation routing via boundary polygons (no Nominatim dependency)
- Fresh tender data past Apr 2026 (KPPP API pull) and ward-polygon matching
- Post-drive batch analysis mode (cheaper, non-live) and a local YOLO
  pre-filter (RDD2022) for near-zero-cost continuous drives
- Sahaaya auto-filing if a public API ever appears
