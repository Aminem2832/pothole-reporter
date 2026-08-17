// The app engine: the entire pipeline on-device, no server anywhere.
// The page's api() delegates every call here.
(() => {
  const NATIVE = !!(window.Capacitor && Capacitor.isNativePlatform && Capacitor.isNativePlatform());

  // Test harness (browser, non-native): ?key=sk-... seeds the key. Never runs in the APK.
  if (!NATIVE) {
    const k = new URLSearchParams(location.search).get("key");
    if (k) localStorage.setItem("openai_key", k);
  }

  const S = {
    get key() { return (localStorage.getItem("openai_key") || "").trim(); },
    get name() { return (localStorage.getItem("sender_name") || "").trim() || "A concerned citizen"; },
    get debug() { return localStorage.getItem("debug_mode") === "1"; },
  };

  const MODEL = "gpt-5-mini";
  const SCREEN_MODEL = "gpt-5-nano";
  const MIN_CONFIDENCE = 0.5;
  const DEDUPE_RADIUS_M = 15;
  const DEDUPE_WINDOW_S = 30 * 60;

  const OFFICERS = {
    "bengaluru central city corporation": ["Commissioner, Bengaluru Central City Corporation (BCCC)", "commissionerbccc@gmail.com"],
    "bengaluru east city corporation": ["Commissioner, Bengaluru East City Corporation (BECC)", "commissioner.becc@gmail.com"],
    "bengaluru north city corporation": ["Commissioner, Bengaluru North City Corporation (BNCC)", "bengalurunorthcitycorporation@gmail.com"],
    "bengaluru south city corporation": ["Commissioner, Bengaluru South City Corporation (BSCC)", "comm.south.gba@gmail.com"],
    "bengaluru west city corporation": ["Commissioner, Bengaluru West City Corporation (BWCC)", "commissioner.bwcc@gmail.com"],
  };
  const HQ = ["Commissioner, Greater Bengaluru Authority (HQ)", "comm@bbmp.gov.in"];

  const DETECT_PROMPT = `You are inspecting a road photo taken in Bengaluru for a civic complaint app.

Decide whether the photo clearly shows a pothole on a road surface.
- Classify size like pizzas: small (below 30 cm wide), medium (30 to 60 cm), large (above 60 cm or a cluster).
- Beware of speed breakers: from a distance they can look like potholes. Set looks_like_speed_breaker accordingly, and if it is actually a speed breaker, is_pothole must be false.
- Shadows, manhole covers, wet patches, and road repair scars are NOT potholes.
- confidence is your 0 to 1 confidence in the is_pothole verdict. Be conservative: this triggers a government complaint.
- description: one or two factual sentences usable in a complaint (surface condition, position on the road, hazard posed).
- Some images are dashcam frames from a moving vehicle: moderate motion blur, low light, or a boosted-brightness look are normal; judge the road surface itself.`;

  const SCREEN_PROMPT = `This is a dashcam frame from a car in Bengaluru. Decide only whether this
frame could POSSIBLY show road damage: a pothole, broken or patched asphalt,
exposed sub-base, loose stones, or any suspicious dark patch or depression on
the road surface. This is a permissive pre-filter and a stronger model makes
the final call, so false positives are fine and false negatives are costly.
Answer false ONLY when the visible road surface is clearly smooth and intact
with nothing questionable. If there is any doubt at all, answer true.`;

  const ASSESS_SCHEMA = {
    type: "object", additionalProperties: false,
    required: ["is_pothole", "size", "confidence", "looks_like_speed_breaker", "description"],
    properties: {
      is_pothole: { type: "boolean" },
      size: { type: ["string", "null"], enum: ["small", "medium", "large", null] },
      confidence: { type: "number" },
      looks_like_speed_breaker: { type: "boolean" },
      description: { type: "string" },
    },
  };
  const SCREEN_SCHEMA = {
    type: "object", additionalProperties: false,
    required: ["possible_pothole"],
    properties: { possible_pothole: { type: "boolean" } },
  };
  const TENDER_SCHEMA = {
    type: "object", additionalProperties: false,
    required: ["match_index", "confidence", "reason"],
    properties: {
      match_index: { type: ["integer", "null"] },
      confidence: { type: "number" },
      reason: { type: "string" },
    },
  };

  // ---------- OpenAI ----------
  async function oai(body) {
    if (!S.key) throw new Error("OpenAI API key missing. Tap the gear icon and paste it.");
    const res = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${S.key}` },
      body: JSON.stringify(body),
    });
    if (res.status === 401) throw new Error("OpenAI rejected the API key. Check it in settings.");
    if (res.status === 429) throw new Error("Rate limited by OpenAI. Try again in a minute.");
    if (!res.ok) throw new Error(`OpenAI error ${res.status}: ${(await res.text()).slice(0, 160)}`);
    const data = await res.json();
    const msg = (data.output || []).find((o) => o.type === "message");
    const text = msg && msg.content && msg.content.find((c) => c.type === "output_text");
    if (!text || !text.text) throw new Error("Empty model response.");
    return JSON.parse(text.text);
  }
  const fmt = (name, schema) => ({ format: { type: "json_schema", name, schema, strict: true } });
  const progress = (m) => { try { window.dispatchEvent(new CustomEvent("pipeline-progress", { detail: m })); } catch (e) {} };

  function analyzeImage(dataUrl, prompt, name, schema, model) {
    return oai({
      model,
      input: [{ role: "user", content: [
        { type: "input_image", image_url: dataUrl },
        { type: "input_text", text: prompt },
      ] }],
      text: fmt(name, schema),
    });
  }

  // ---------- location ----------
  async function reverseGeocode(lat, lng) {
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=jsonv2&zoom=17`);
      if (!res.ok) return null;
      return (await res.json()).display_name || null;
    } catch (e) { return null; }
  }

  function routeOfficer(address) {
    if (address) {
      const low = address.toLowerCase();
      for (const [needle, officer] of Object.entries(OFFICERS)) {
        if (low.includes(needle)) return officer;
      }
    }
    return HQ;
  }

  function distMeters(lat1, lng1, lat2, lng2) {
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad, dLng = (lng2 - lng1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(a));
  }

  // ---------- tenders ----------
  let _tenders = null;
  async function tenders() {
    if (_tenders) return _tenders;
    try {
      const res = await fetch("tenders.json");
      _tenders = res.ok ? await res.json() : [];
    } catch (e) { _tenders = []; }
    return _tenders;
  }

  const TENDER_STOP = new Set(["road", "roads", "street", "cross", "main", "layout", "bengaluru", "bangalore",
    "karnataka", "india", "ward", "city", "corporation", "south", "north", "east",
    "west", "central", "urban", "sector", "stage", "block", "phase"]);

  async function matchTender(address) {
    if (!address || !S.key) return null;
    const tokens = new Set();
    for (const part of address.split(",").slice(0, 4)) {
      for (const w of part.trim().toLowerCase().replace(/[()]/g, " ").split(/\s+/)) {
        if (w.length > 2 && !TENDER_STOP.has(w)) tokens.add(w);
      }
    }
    if (!tokens.size) return null;
    const scored = [];
    for (const t of await tenders()) {
      const hay = (t.t + " " + t.loc).toLowerCase();
      let score = 0;
      for (const tok of tokens) if (hay.includes(tok)) score++;
      if (score >= 1) scored.push([score, t]);
    }
    scored.sort((a, b) => b[0] - a[0]);
    const candidates = scored.slice(0, 25).map((x) => x[1]);
    if (!candidates.length) return null;
    const listing = candidates.map((t, i) =>
      `${i}: ${t.t.slice(0, 150)} | ${t.loc} | contractor: ${t.c || "not named"} | awarded: ${t.d}`).join("\n");
    const prompt = `You match a pothole's location to Bengaluru road-work contracts.
The pothole's reverse-geocoded address is:
${address}

Candidate contracts (index: work description | division | contractor | awarded):
${listing}

Pick the single contract whose work description covers this exact road stretch or
its immediate locality (same layout, ward or named road). Road names repeat across
Bengaluru localities, so the locality and ward context must agree, not just the
road name. A ward-wide maintenance or pothole-filling contract for the pothole's
own layout or ward is a valid match. If no candidate clearly covers this location,
match_index must be null. confidence is your 0 to 1 confidence in the match.`;
    let m;
    try {
      m = await oai({ model: MODEL, input: prompt, text: fmt("tender_match", TENDER_SCHEMA) });
    } catch (e) { return null; }
    if (!m || m.match_index === null || m.match_index < 0 || m.match_index >= candidates.length || m.confidence < 0.6) return null;
    const t = candidates[m.match_index];
    let warranty = "on record for this stretch";
    const dm = /^(\d{2})-(\d{2})-(\d{4})/.exec(t.d);
    if (dm) {
      const ageYears = (Date.now() - new Date(`${dm[3]}-${dm[2]}-${dm[1]}`).getTime()) / (365.25 * 24 * 3600 * 1000);
      if (ageYears <= 1) warranty = "likely still within the defect liability period";
      else if (ageYears <= 3) warranty = "possibly still within the maintenance period";
    }
    const contractor = t.c || "contractor not named in the award record";
    return {
      tender_number: t.tn, contractor, title: t.t, published: t.d, warranty,
      note: `Probable contract: ${t.tn}, ${contractor}, awarded ${t.d}`,
    };
  }

  // ---------- drafting ----------
  function draftEmail(a, lat, lng, address, officerName, tender) {
    const where = address || "location attached below";
    let locLines;
    if (lat != null) {
      locLines = `Location: ${where}\nCoordinates: ${lat.toFixed(6)}, ${lng.toFixed(6)}\nMap link: https://maps.google.com/?q=${lat.toFixed(6)},${lng.toFixed(6)}`;
    } else {
      locLines = "Location: could not be determined automatically. Please see the attached photo for landmarks.";
    }
    const subject = `Pothole complaint: ${a.size || "unclassified"} pothole` + (address ? ` near ${address.split(",")[0]}` : "");
    let body = `Dear ${officerName || "Sir or Madam"},

I would like to report a pothole that needs urgent repair.

${locLines}
Approximate size: ${a.size || "not classified"}
Details: ${a.description}

A photograph of the pothole is attached to this email. This pothole poses a danger to two wheeler riders and other road users. I request the city corporation to inspect and repair it at the earliest, and to route it to the contractor responsible if this road section is still under a maintenance warranty. I am also filing this grievance on Sahaaya so it can be tracked to resolution.

Thank you for your service to the city.

Regards,
${S.name}`;
    if (tender) {
      const para = `Public procurement records indicate this road stretch probably falls under tender ${tender.tender_number} ("${tender.title.slice(0, 140).trim()}"), awarded on ${tender.published} to ${tender.contractor}, and is ${tender.warranty}. If the defect liability or maintenance period is in force, I request that the repair be carried out by the contractor at no additional cost to the corporation. This is a probable record match; kindly verify against the tender documents.`;
      body = body.replace("\n\nThank you", `\n\n${para}\n\nThank you`);
    }
    return [subject, body];
  }

  // ---------- storage (IndexedDB) ----------
  let _db = null;
  function idb() {
    return new Promise((resolve, reject) => {
      if (_db) return resolve(_db);
      const req = indexedDB.open("potholes", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("reports", { keyPath: "id", autoIncrement: true });
      req.onsuccess = () => { _db = req.result; resolve(_db); };
      req.onerror = () => reject(req.error);
    });
  }
  function op(mode, fn) {
    return idb().then((d) => new Promise((resolve, reject) => {
      const store = d.transaction("reports", mode).objectStore("reports");
      const req = fn(store);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    }));
  }
  const allReports = () => op("readonly", (s) => s.getAll());
  const getReport = (id) => op("readonly", (s) => s.get(Number(id)));
  const putReport = (r) => op("readwrite", (s) => s.put(r));
  const addReport = (r) => op("readwrite", (s) => s.add(r));
  const delReport = (id) => op("readwrite", (s) => s.delete(Number(id)));

  const toDict = (r) => ({ ...r, photo_url: r.photo });

  // ---------- image ----------
  async function toDataUrl(blob, maxDim) {
    const bmp = await createImageBitmap(blob);
    const scale = Math.min(1, maxDim / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * scale);
    c.height = Math.round(bmp.height * scale);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.85);
  }

  // ---------- pipeline ----------
  async function createReport(fd, driveMode) {
    const photo = fd.get("photo");
    if (!photo || !photo.size) throw new Error("Empty photo.");
    const latRaw = fd.get("lat"), lngRaw = fd.get("lng");
    const lat = latRaw != null && latRaw !== "" ? parseFloat(latRaw) : null;
    const lng = lngRaw != null && lngRaw !== "" ? parseFloat(lngRaw) : null;
    const driveId = driveMode ? (fd.get("drive_id") || null) : null;

    if (driveMode && lat != null) {
      const cutoff = Date.now() / 1000 - DEDUPE_WINDOW_S;
      for (const r of await allReports()) {
        if ((r.status === "draft" || r.status === "queued" || r.status === "sent") && r.lat != null &&
            r.created_at > cutoff && distMeters(lat, lng, r.lat, r.lng) < DEDUPE_RADIUS_M) {
          return { found: false, skipped: "already reported nearby" };
        }
      }
    }

    progress(driveMode ? "Capturing frame..." : "Compressing photo...");
    const dataUrl = await toDataUrl(photo, driveMode ? 1280 : 2000);
    // Geocoding runs in parallel with the AI calls; it never gates detection.
    const geoP = lat != null ? reverseGeocode(lat, lng).catch(() => null) : Promise.resolve(null);
    if (driveMode) {
      progress("Quick road scan...");
      const s = await analyzeImage(dataUrl, SCREEN_PROMPT, "screen", SCREEN_SCHEMA, SCREEN_MODEL);
      if (!s.possible_pothole) {
        if (S.debug) await saveDebugFrame(dataUrl, lat, lng, "Debug frame: screened out by the quick road scan.", 0, driveId);
        return { found: false };
      }
    }
    progress("AI checking for potholes...");
    // Contract adjudication runs speculatively in parallel with confirmation:
    // total wait becomes the max of the two instead of their sum. The rare
    // waste is one cheap text call when a screened frame ends up rejected.
    const tenderP = geoP.then((addr) => matchTender(addr)).catch(() => null);
    const a = await analyzeImage(dataUrl, DETECT_PROMPT, "assessment", ASSESS_SCHEMA, MODEL);
    const accepted = a.is_pothole && a.confidence >= MIN_CONFIDENCE;
    if (driveMode && !accepted) {
      if (S.debug) await saveDebugFrame(dataUrl, lat, lng, `Debug frame: analyzed, no pothole confirmed (${Math.round(a.confidence * 100)}%). ${a.description}`, a.confidence, driveId);
      return { found: false };
    }

    if (accepted) progress("Finalizing address and contract...");
    const address = accepted ? await geoP : null;
    const [officerName, officerEmail] = accepted ? routeOfficer(address) : [null, null];
    const tender = accepted ? await tenderP : null;
    if (accepted) progress("Writing the complaint...");
    const [subject, body] = accepted ? draftEmail(a, lat, lng, address, officerName, tender) : [null, null];

    const rec = {
      created_at: Date.now() / 1000, lat, lng, address, photo: dataUrl,
      is_pothole: a.is_pothole ? 1 : 0, size: a.size, confidence: a.confidence,
      description: a.description, email_subject: subject, email_body: body,
      status: accepted ? "draft" : "rejected",
      officer_name: officerName, officer_email: officerEmail,
      tender_number: tender ? tender.tender_number : null,
      contractor: tender ? tender.contractor : null,
      tender_note: tender ? tender.note : null,
      sent_at: null,
      drive_id: driveId,
    };
    rec.id = await addReport(rec);
    return driveMode ? { found: true, report: toDict(rec) } : toDict(rec);
  }

  async function saveDebugFrame(dataUrl, lat, lng, description, confidence = 0, driveId = null) {
    const rec = {
      created_at: Date.now() / 1000, lat, lng, address: null, photo: dataUrl,
      is_pothole: 0, size: null, confidence, description,
      email_subject: null, email_body: null, status: "rejected",
      officer_name: null, officer_email: null,
      tender_number: null, contractor: null, tender_note: null, sent_at: null,
      drive_id: driveId,
    };
    rec.id = await addReport(rec);
  }

  async function openInGmail(rec) {
    // Always the routed officer. The app never sends; the user does, in their email app.
    const to = rec.officer_email || HQ[1];
    progress("Opening your email app...");
    if (NATIVE) {
      // Vanilla-JS WebView: the injected runtime exposes plugins via Capacitor.Plugins
      // and has no registerPlugin. Support both for bundler compatibility.
      const EmailComposer = Capacitor.registerPlugin
        ? Capacitor.registerPlugin("EmailComposer")
        : Capacitor.Plugins.EmailComposer;
      await EmailComposer.open({
        to: [to],
        subject: rec.email_subject || "",
        body: rec.email_body || "",
        attachments: [{ type: "base64", name: "pothole.jpg", path: rec.photo.split(",")[1] }],
      });
    } else {
      console.log("[harness] would open native compose to:", to);
    }
    rec.status = "queued";
    rec.sent_at = Date.now() / 1000;
    await putReport(rec);
    return toDict(rec);
  }

  // ---------- API dispatch ----------
  async function handle(path, opts) {
    const method = ((opts && opts.method) || "GET").toUpperCase();
    let m;
    if (path === "/api/health") {
      return { ai_configured: !!S.key, provider: "openai", delivery: "gmail_compose", email_configured: true };
    }
    if (path === "/api/reports" && method === "GET") {
      return (await allReports()).sort((a, b) => b.id - a.id).map(toDict);
    }
    if (path === "/api/reports" && method === "DELETE") {
      await op("readwrite", (s) => s.clear());
      return { ok: true };
    }
    if (path === "/api/report" && method === "POST") return createReport(opts.body, false);
    if (path === "/api/frame" && method === "POST") return createReport(opts.body, true);
    if ((m = path.match(/^\/api\/reports\/(\d+)\/send$/)) && method === "POST") {
      const rec = await getReport(m[1]);
      if (!rec) throw new Error("Report not found.");
      // "queued" stays reopenable: canceling the Gmail composer must not strand the report.
      if (rec.status !== "draft" && rec.status !== "queued") throw new Error("This report is not a sendable draft.");
      return openInGmail(rec);
    }
    if ((m = path.match(/^\/api\/reports\/(\d+)$/))) {
      const rec = await getReport(m[1]);
      if (!rec) throw new Error("Report not found.");
      if (method === "PATCH") {
        if (rec.status !== "draft" && rec.status !== "queued") throw new Error("Only drafts can be edited.");
        const upd = JSON.parse(opts.body);
        rec.email_subject = upd.email_subject;
        rec.email_body = upd.email_body;
        await putReport(rec);
        return toDict(rec);
      }
      if (method === "DELETE") {
        if (rec.status === "sent") throw new Error("Sent reports cannot be discarded.");
        await delReport(rec.id);
        return { ok: true };
      }
    }
    throw new Error(`Unhandled: ${method} ${path}`);
  }

  // Native hardware back button routes through window.handleAppBack (defined by the UI).
  if (NATIVE) {
    try {
      const App = Capacitor.Plugins.App;
      if (App && App.addListener) {
        App.addListener("backButton", () => {
          if (!(window.handleAppBack && window.handleAppBack())) App.exitApp();
        });
      }
    } catch (e) {}
  }

  window.StandaloneAPI = { handle };

  // First run: open settings if no key yet (after the main script wires the UI).
  window.addEventListener("load", () => {
    if (!S.key && typeof window.openSettings === "function") window.openSettings(true);
  });
})();
