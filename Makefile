PY ?= python3

.PHONY: help install validate prompts smoke script narration radio radio-dry refs keyframes shots-export shots \
        music-export music film film-dry regen costs test clean

help:
	@echo "One command for the whole film (same as: python src/pipeline.py film):"
	@echo "  make film          validate -> prompts -> narration -> images -> video -> music -> assemble"
	@echo "  make film-dry      the same with placeholder narration and frames: no API keys needed"
	@echo ""
	@echo "Stages:"
	@echo "  make install       install Python dependencies (ffmpeg must already be on PATH)"
	@echo "  make validate      check storyboard/storyboard.json against the schema"
	@echo "  make prompts       write prompts/*.md from the storyboard"
	@echo "  make smoke         call each hosted provider once, log latency to logs/runs.jsonl"
	@echo "  make narration     Gemini TTS, one cached WAV per shot -> audio/narration/"
	@echo "  make radio         narration + radio cut (Phase 1 checkpoint) -> output/radio_cut/"
	@echo "  make refs          character reference-sheet candidates (then: generate_images.py approve ...)"
	@echo "  make keyframes     one image per shot, conditioned on the approved references -> assets/images/"
	@echo "  make shots-export  bundle changed shots for Wan 2.2 on Kaggle (see kaggle/README.md)"
	@echo "  make music-export  bundle music cues for ACE-Step on Kaggle"
	@echo "  make regen SHOT=s05  regenerate one shot's narration + image, then re-assemble"
	@echo "  make costs         summarise logs/runs.jsonl into COSTS.md"
	@echo "  make test          run the unit tests"

install:
	$(PY) -m pip install -r requirements.txt

validate:
	$(PY) src/pipeline.py validate

prompts:
	$(PY) src/pipeline.py prompts

smoke:
	$(PY) src/pipeline.py smoke

script:
	$(PY) src/pipeline.py script draft --brief STORY.md

narration: validate
	$(PY) src/generate_audio.py narration

radio:
	$(PY) src/pipeline.py radio

radio-dry:
	$(PY) src/pipeline.py radio --dry-run

refs: validate
	$(PY) src/generate_images.py refs --candidates 4

keyframes: validate
	$(PY) src/generate_images.py shots

shots-export: keyframes
	$(PY) src/generate_video.py export

shots: keyframes
	$(PY) src/generate_video.py render

music-export: validate
	$(PY) src/generate_audio.py music export

music: validate
	$(PY) src/generate_audio.py music build

film:
	$(PY) src/pipeline.py film

film-dry:
	$(PY) src/pipeline.py film --dry-run

regen:
	@test -n "$(SHOT)" || (echo "usage: make regen SHOT=s05" && exit 1)
	$(PY) src/pipeline.py regen $(SHOT)

costs:
	$(PY) src/pipeline.py costs

test:
	$(PY) -m pytest -q tests

clean:
	rm -rf output/radio_cut output/_work assets/video/_import audio/music/_import
