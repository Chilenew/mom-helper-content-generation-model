# Failures

What broke, what I tried, and what fixed it, in the order it happened. Quota, memory, consistency and language failures are all worth recording: they are the evidence of how these models behave.

## Template

### FXX — short title
- **Date / stage:**
- **What happened:** (exact error or symptom; link the `runs.jsonl` line if a model call failed)
- **What I tried:** 1. … 2. …
- **What fixed it / workaround:**
- **What I learned:**

---

### F01 — Subtitles wrapped onto three lines, then became huge
- **Date / stage:** 2026-11-25, radio cut (dry run, no API calls)
- **What happened:** Lines pre-wrapped to two lines of ≤ 40 characters were shown on **three** lines in the 720×1280 frame.
- **What I tried:**
  1. `force_style='FontSize=11'` with the `subtitles` filter: still three lines. libass renders SRT on a default 384×288 canvas and scales it up, so the font size isn't in real pixels and the margins scale too.
  2. `original_size=720x1280`: the text became enormous, one word per line. The scaling went the other way.
- **What fixed it:** write the subtitles as an `.ass` file with `PlayResX/PlayResY` equal to the frame size and `WrapStyle: 2` (keep only my line breaks), and burn it with the `ass` filter. Font size is now in real pixels (frame width / 22). See `pipeline/media.py: write_ass`.
- **What I learned:** check frames visually, not just the exit code. The first two versions "succeeded".

### F02 — End card text ran off the vertical frame
- **Date / stage:** 2026-11-25, radio cut
- **What happened:** "Made with AI · A story inspired by mothers in rural Ethiopia" was drawn on one line and cut off on both sides in 9:16.
- **What fixed it:** split the end card on "·", wrap each part to the frame width, and draw each line with its own `drawtext` (`media.py: end_card_drawtext`).
- **What I learned:** anything designed for 16:9 needs checking at 9:16 first, since the phone is the main audience.

### F03 — Model names in the brief vs. what the API accepts (_to verify at smoke test_)
- **Date / stage:** _(fill in after `make smoke`)_
- **What happened:** _(e.g. `gemini-3.8-flash-tts` rejected / renamed?)_
- **What I tried:**
- **What fixed it:** override in `.env` (`TTS_MODEL=...`) without touching code.
