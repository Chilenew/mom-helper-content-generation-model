# Failures

What broke, what I tried, and what fixed it, in the order it happened. Quota, memory, consistency and language failures are all worth recording: they are the evidence of how these models behave.

## Template

### FXX — short title
- **Date / stage:**
- **What happened:** (exact error or symptom; link the `logs/runs.jsonl` line if a model call failed)
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
- **What fixed it:** write the subtitles as an `.ass` file with `PlayResX/PlayResY` equal to the frame size and `WrapStyle: 2` (keep only my line breaks), and burn it with the `ass` filter. Font size is now in real pixels (frame width / 22). See `src/media.py: write_ass`.
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

### F04 — Image model made the family light-skinned; reference sheet leaked into shots
- **Date / stage:** 2026-11-26, keyframes (FLUX.2 [klein] 4B, Cloudflare)
- **What happened:** with "warm dark brown skin" in the description, most people came out light-skinned and did not read as Ethiopian. After approving a three-view reference sheet for the mother, shots showed her two or three times side by side, and in one shot the graduate son was replaced by a second copy of her.
- **What I tried:**
  1. More specific descriptions ("Ethiopian Habesha", "deep/dark brown skin", "East African facial features"): fixed the son and the young child, not the mother.
  2. Cropping the single front view from the sheet and adding "each person appears exactly once; not a collage": fixed the duplicates.
  3. Single-portrait reference candidates for each character: the son and the child are now consistent and dark-skinned. Two more rounds for the mother (8 candidates) all came out medium brown, lighter than her son.
- **Workaround:** use a consented real photo as the mother's reference (pending; see ETHICS.md).
- **What I learned:** the model's skin-tone bias depends on age and gender: young men rendered dark easily, older women did not, whatever the wording. Look at every contact sheet; never use a multi-view sheet as a reference.

### F05 — Gemini TTS not available to the API key
- **Date / stage:** 2026-11-26, smoke test / narration
- **What happened:** first key was rejected (`API key not valid`: a 26-character value, not a Gemini key). With a valid key, text generation worked, but every speech request failed: `400 INVALID_ARGUMENT: Unknown name "speechConfig" at 'generation_config'`.
- **What I tried:** 1. Listing the models visible to the key: 28 models, none with TTS. 2. The only plausible audio model, `gemini-omni-flash-preview`: same error.
- **What fixed it / workaround:** Azure AI Speech (same voices, official) was wired in (`azure_tts`) but an Azure account could not be created from here. Narration now uses the same Microsoft voice `am-ET-AmehaNeural` through the free `edge-tts` library (`provider: edge_tts`), rate -12%. It uses Edge's read-aloud service unofficially: fine for a draft, replace with a licensed service or a real recording before a public release. The real voice also ran 1.2 s over shot_03 and 2.5 s over shot_10, so durations were rebalanced (shots 5, 6, 7 shortened; total unchanged at 85 s).
- **What I learned:** run the smoke test before planning around a provider; model availability depends on the key, not just on the docs.
