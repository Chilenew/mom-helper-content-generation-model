# Changelog

All notable changes to the pipeline and the storyboard. Storyboard versions are listed with the reason for the change (see DESIGN.md for the user-test evidence).

## [0.1.0] - 2026-11-25
### Added
- `storyboard.json` v0.1.0: 11 shots, 80 s + 3 s end card, Amharic narration with English subtitles, three characters (one face shown), two music cues.
- JSON Schema and validator with cross-checks (unknown characters/cues, cue order, 60–90 s total, consent required for real people, "AI" required on the end card).
- Stages: script, narration, keyframes (reference sheets + approve + shots), shots (Kaggle export/import + Ken Burns fallback), music (Kaggle export/import/choose/build), assemble (both aspect ratios), radio cut.
- Kaggle scripts for Wan 2.2 TI2V-5B (two T4s in parallel, resumable) and ACE-Step 1.5.
- Shared logging to `runs.jsonl`, input-hash caching with `.meta.json` sidecars, retries with backoff.
- `make film`, `make film-dry`, `make regen SHOT=…`, `make costs`.
- CI: validation, unit tests and a full dry-run film on every push.
- Documentation: README, ARCHITECTURE, DESIGN, EXPERIMENTS, FAILURES, COSTS, ETHICS, git workflow, report template.

### Fixed
- Subtitles wrapping to three lines (FAILURES.md F01) and end card overflow in 9:16 (F02).
