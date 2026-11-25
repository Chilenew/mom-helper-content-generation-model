# Experiments

Each entry: **hypothesis → change → result → decision**, with evidence (log lines in `runs.jsonl`, file paths, measured numbers, or what testers said). Change one thing at a time and keep the seed fixed when comparing prompts.

Entries marked _planned_ are designed but not yet run. Replace the plan with what actually happened, including when the hypothesis was wrong.

---

## Template

### EXX — short title
- **Date:**
- **Hypothesis:** I expect … because …
- **Change:** (one variable; everything else fixed: seed, model, prompt)
- **Evidence:** `runs.jsonl` run_id …, files …, measurements …
- **Result:**
- **Decision:** kept / reverted / follow-up

---

## E01 — TTS style instruction vs. none (_planned_)
- **Hypothesis:** A short style instruction ("calm, warm, unhurried") makes the Amharic narration sound more natural than the bare text, without changing the voice.
- **Change:** generate s06 with and without `narration_settings.style_instruction` (same voice).
- **Evidence:** two WAVs, durations from `timing.json`, a blind preference from 3 Amharic speakers.
- **Result:**
- **Decision:**

## E02 — Voice choice for the narrator (_planned_)
- **Hypothesis:** A softer prebuilt voice fits the intimate tone better than the default.
- **Change:** s01–s03 with two voices; same style instruction.
- **Result:**

## E03 — Reference image vs. text-only description for the mother's consistency (_planned_)
- **Hypothesis:** Passing the approved reference sheet as `input_image_0` to FLUX.2 [klein] keeps the mother recognisably the same across s02, s03, s06 and s08 better than repeating the text description alone.
- **Change:** generate those four shots twice, with and without the reference, same seeds.
- **Evidence:** contact sheets side by side; ask 3 people "is this the same woman in all four?"
- **Result:**

## E04 — Selam from behind vs. in profile (_planned_)
- **Hypothesis:** Showing Selam only from behind gives fewer visible inconsistencies than profile, at the cost of less warmth.
- **Change:** s05 keyframe in both framings.
- **Result:**

## E05 — Wan 2.2 base vs. distilled FastWan on a T4 (_planned_)
- **Hypothesis:** FastWan2.2-TI2V-5B at 4 steps is about 5–8× faster than the base model at 30 steps on a T4, with acceptable quality for slow shots.
- **Change:** `MODEL_ID` and `STEPS` in the Kaggle notebook for s06 and s07.
- **Evidence:** `gpu_minutes` in `runs.jsonl`; side-by-side clips.
- **Result:**

## E06 — Motion prompt: "fixed camera" vs. "camera pushes in gently" (_planned_)
- **Hypothesis:** A fixed camera produces less face morphing in close-ups (s06).
- **Change:** motion prompt only, same seed.
- **Result:**

## E07 — 81 vs. 121 frames per clip (_planned_)
- **Hypothesis:** 81 frames (3.4 s) costs about 2/3 of the GPU time of 121 frames and is enough for shots slowed to 1.5× in assembly.
- **Result:**

## E08 — ACE-Step caption detail (_planned_)
- **Hypothesis:** A detailed caption (style + mood + instruments + texture) gives a score that sits under the voice better than a two-word caption.
- **Change:** `cue_waiting` caption, same seed, bpm and key.
- **Evidence:** listen under the narration at low volume; note which one masks the voice.
- **Result:**

## E09 — Ducking settings (_planned_)
- **Hypothesis:** Ratio 6 with a 1500 ms release keeps the score from "pumping" between sentences better than ratio 10 / 500 ms.
- **Result:**

## E10 — One square master vs. a separate 16:9 generation (_planned_)
- **Hypothesis:** Cropping 9:16 and 16:9 from one square keyframe loses nothing important for centred compositions, and halves GPU time.
- **Change:** generate s04 (the widest composition) natively at 16:9 and compare with the crop.
- **Result:**

## E11 — Ken Burns vs. Wan for the night shot s08 (_planned_)
- **Hypothesis:** For a still, emotional shot, a slow zoom over the keyframe is as effective as a generated clip, at zero GPU cost.
- **Evidence:** user test 2 reactions to s08.
- **Result:**

## E12 — Ceiling: Afaan Oromo narration (_planned_)
- **Hypothesis:** Gemini TTS handles Afaan Oromo less well than Amharic, especially names and long vowels.
- **Change:** `python pipeline/script.py translate --lang om`, a native speaker checks it, then narration into a separate output folder.
- **Evidence:** a native speaker's notes per line; where exactly it fails (log in FAILURES.md).
- **Result:**
