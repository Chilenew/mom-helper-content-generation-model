# Changelog

All notable changes to the pipeline and the storyboard. Storyboard versions are listed with the reason for the change (see DESIGN.md for the user-test evidence).

## [Unreleased]
### Changed
- Repository restructured: `storyboard/` (storyboard + schema), `src/` (pipeline code), `audio/`, `assets/`,
  `output/`, `logs/runs.jsonl`, `STORY.md` (was `story/brief.md`).
- Stages renamed: `generate_images.py` (was keyframes), `generate_video.py` (was shots), `generate_audio.py`
  (narration, music and radio cut, was three scripts), `assemble_film.py` (was assemble).
- Films renamed: `output/film_vertical.mp4` (9:16) and `output/film_horizontal.mp4` (16:9).
### Story
- New film, storyboard v0.2.0: "ጠንካራዋ እናቴ / My Strong Mother", 10 shots, 85 s + 3 s end card.
- `storyboard/storyboard.json` now holds only the story, in its own schema; pipeline settings moved to
  `storyboard/pipeline_config.json`. The merge is validated against `storyboard/pipeline.schema.json`.
- Long subtitles are shown in timed parts; the end card uses Ebrima on Windows so Amharic renders.
### Added
- `src/pipeline.py`: one front door for the whole film (`film`, `film --dry-run`, `regen`, `radio`, ...).
- `prompts/`: every model prompt written out from the storyboard for review (`make prompts`).

## [0.1.0] - 2026-11-25
### Added
- `storyboard/storyboard.json` v0.1.0: 11 shots, 80 s + 3 s end card, Amharic narration with English subtitles, three characters (one face shown), two music cues.
- JSON Schema and validator with cross-checks (unknown characters/cues, cue order, 60–90 s total, consent required for real people, "AI" required on the end card).
- Stages: script, narration, keyframes (reference sheets + approve + shots), shots (Kaggle export/import + Ken Burns fallback), music (Kaggle export/import/choose/build), assemble (both aspect ratios), radio cut.
- Kaggle scripts for Wan 2.2 TI2V-5B (two T4s in parallel, resumable) and ACE-Step 1.5.
- Shared logging to `logs/runs.jsonl`, input-hash caching with `.meta.json` sidecars, retries with backoff.
- `make film`, `make film-dry`, `make regen SHOT=…`, `make costs`.
- CI: validation, unit tests and a full dry-run film on every push.
- Documentation: README, ARCHITECTURE, DESIGN, EXPERIMENTS, FAILURES, COSTS, ETHICS, git workflow, report template.

### Fixed
- Subtitles wrapping to three lines (FAILURES.md F01) and end card overflow in 9:16 (F02).
