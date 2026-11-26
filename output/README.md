# Finished films

- `film_vertical.mp4`: 9:16, the main deliverable
- `film_horizontal.mp4`: 16:9
- `assembly_report.json`: durations, loudness, and which source (Wan clip or Ken Burns) each shot used
- `radio_cut/`: the Phase 1 prototype (narration + music + subtitles on black)

Everything here is built by `python src/pipeline.py film`. Intermediate media lives in `audio/` and `assets/`;
each file there has a `.meta.json` input-hash sidecar so unchanged shots are never regenerated.
