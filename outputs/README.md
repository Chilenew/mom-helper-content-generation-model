# Generated outputs

Every stage writes here, with a `.meta.json` input-hash sidecar per file. Outputs are committed so a run can be inspected and a clean clone can rebuild the film without new model calls.

- `narration/` one WAV per shot + timing.json
- `keyframes/` reference sheets (refs/), one PNG per shot, contact sheet
- `shots/` Wan clips, Ken Burns fallbacks, manifest.json
- `music/` candidates and the final score
- `subtitles/` English SRT
- `radio_cut/` the Phase 1 prototype
- `final/` film_9x16.mp4, film_16x9.mp4, assembly_report.json
