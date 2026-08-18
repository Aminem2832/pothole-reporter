# Detection benchmark

The detector is a vision model behind a confidence gate, so "did that change help?"
can only be answered by measuring. This directory holds the labels, the arms, and
the harness.

```bash
python3 eval/run_eval.py --trials 5
python3 eval/run_eval.py --trials 5 --arms baseline,carriageway
```

`OPENAI_API_KEY` comes from the environment or the repo-root `.env`. A run of 5
trials over the seed set is about 180 calls on `gpt-5-mini`, a few rupees.

## The one rule: measure the noise floor first

This detector is **stochastic**. Byte-identical input, same prompt, same
parameters, re-run: the true-positive rate has swung 30 points and a single frame
has swung 80 points (accepted 4 of 5 in one run, 0 of 5 in the next). That is not
transport error. Every call returned valid structured output.

So `run_eval.py` always runs the control arm **twice on identical bytes** and
prints the gap between them as the noise floor. Any difference between real arms
smaller than that gap is not a result, however good the story sounds.

The noise is asymmetric and that matters. Losses on confirmed potholes have shown
almost no drift (56 consecutive true-positive calls with zero variation in one
batch), while the false-positive rate wobbles by 5 to 15 points on its own. So a
change that costs real potholes is believable at low trial counts, and a change
that appears to reduce false alarms usually is not.

## Images and labels

Images are **not committed**: they are large, and third-party sources carry their
own licence and attribution terms. `eval/images/` is gitignored. `labels.json`
records the path, the label, why it is labelled that way, the source and the
licence, so an image set can be rebuilt and its provenance stays auditable.

Labels are `pothole`, `not_pothole`, or `unlabelled`. Unlabelled images are still
run and reported but excluded from the rates, which is where genuinely ambiguous
frames belong: forcing a label on them corrupts the metric.

To reproduce the seed set, drop the owner's photos and drive frames into
`eval/images/seed/`. When adding third-party imagery, record its licence and
attribution in `labels.json`. Openly licensed street-level imagery is suitable for
evaluation; it is **not** suitable for filing complaints, because a complaint
asserts a current condition on a road you observed.

## Arms

`baseline` is read live from `DETECT_PROMPT` in `static/standalone.js`, so the
control cannot silently drift from what ships. Every `.txt` file in
`eval/prompts/` becomes an additional arm named after the file.

## Results log

Kept so nobody re-runs a dead end.

| Change | Verdict | Evidence |
|---|---|---|
| Remove the `gpt-5-nano` pre-screen | **Shipped** | nano missed 8 of 9 potholes the main model caught, including a confirmed one at 0.28 confidence |
| Drive Mode at full resolution instead of 1280px | **Shipped** | 1280px dropped a real pothole to 0.46, under the gate, that holds at 0.60 full size |
| `reasoning: minimal` on detection | **Shipped** | 6/6 on confirmed potholes at identical median confidence, roughly half the latency |
| JPEG q95 instead of q85 | Rejected | apparent gain sat inside the noise floor; 1.75x the bytes for nothing |
| Crop to the road band | Rejected | destroys true positives (1/10): a narrow band excludes mid-lane damage |
| Crop keeping horizon and hood as anchors | Rejected | anchors restore true positives but false positives rise with road resolution: 50% → 75% → 85% as the road band goes 1.04x → 1.42x → 1.90x |
| Unsharp mask | Rejected | only variant with a negative confidence delta; lost the hard case outright |
| Carriageway / kerb-exclusion prompt (`prompts/carriageway.txt`) | Rejected | cost real potholes (18/18 → 15/18 photos, 10/10 → 8/10 dashcam) with no false-positive gain, and *raised* false-positive confidence by handing the model the word "carriageway" to assert |
| Raise the gate to 0.60 or 0.65 | Rejected | 0.65 cuts false alarms 48% → 8% but dashcam true positives collapse to 9/20, and Drive Mode is exactly where distant real potholes live |

Two corrections worth remembering, both cases of a confident story that the data
did not support:

- An earlier run found 22 of 51 accepted negatives describing a kerb, drain or
  shoulder, which looked like a clear failure mode. It **did not reproduce**: a
  byte-identical control arm hit zero edge-worded false positives with no prompt
  change at all.
- A claimed 1536-patch cap on the vision endpoint does not exist. Calibrated
  across 8 probe sizes: the long side is clamped to 2048, patches are
  `ceil(w/32) * ceil(h/32)`, tokens are `285 + 1.2 * patches`, no cap.

## What the data says to try next

The surviving false positives are not at the road edge. They concentrate on
mid-lane texture: an erosion and silt strip, and an intact but dusty road. The
hypothesis the evidence supports is a clause requiring a **visible depth cue or a
defined rim**, rather than anything about where on the road the defect sits.

The seed set is too small to settle this: 6 confirmed potholes, 4 confirmed
negatives, and 5 frames nobody has reviewed. Growing it with openly licensed
Indian street-level imagery is the highest-value work available here.
