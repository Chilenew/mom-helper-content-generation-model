PY ?= python3

.PHONY: help install validate smoke script narration radio radio-dry refs keyframes shots-export shots \
        music-export music film film-dry regen costs test clean

help:
	@echo "One command for the whole film:"
	@echo "  make film          validate -> narration -> keyframes -> shots -> music -> assemble"
	@echo "  make film-dry      the same with placeholder narration and frames: no API keys needed"
	@echo ""
	@echo "Stages:"
	@echo "  make install       install Python dependencies (ffmpeg must already be on PATH)"
	@echo "  make validate      check storyboard.json against the schema"
	@echo "  make smoke         call each hosted provider once, log latency to runs.jsonl"
	@echo "  make narration     Gemini TTS, one cached WAV per shot"
	@echo "  make radio         narration + radio cut (Phase 1 checkpoint)"
	@echo "  make refs          character reference-sheet candidates (then: keyframes.py approve ...)"
	@echo "  make keyframes     one keyframe per shot, conditioned on the approved references"
	@echo "  make shots-export  bundle changed shots for Wan 2.2 on Kaggle (see kaggle/README.md)"
	@echo "  make music-export  bundle music cues for ACE-Step on Kaggle"
	@echo "  make regen SHOT=s05  regenerate one shot's narration + keyframe, then re-assemble"
	@echo "  make costs         summarise runs.jsonl into COSTS.md"
	@echo "  make test          run the unit tests"

install:
	$(PY) -m pip install -r requirements.txt

validate:
	$(PY) pipeline/validate.py

smoke:
	$(PY) pipeline/smoke_test.py

script:
	$(PY) pipeline/script.py draft --brief story/brief.md

narration: validate
	$(PY) pipeline/narration.py

radio: narration
	$(PY) pipeline/radio_cut.py

radio-dry: validate
	$(PY) pipeline/narration.py --dry-run
	$(PY) pipeline/radio_cut.py

refs: validate
	$(PY) pipeline/keyframes.py refs --candidates 4

keyframes: validate
	$(PY) pipeline/keyframes.py shots

shots-export: keyframes
	$(PY) pipeline/shots.py export

shots: keyframes
	$(PY) pipeline/shots.py render

music-export: validate
	$(PY) pipeline/music.py export

music: validate
	$(PY) pipeline/music.py build

film: narration shots music
	$(PY) pipeline/assemble.py

film-dry: validate
	$(PY) pipeline/narration.py --dry-run
	$(PY) pipeline/keyframes.py shots --dry-run
	$(PY) pipeline/shots.py render
	$(PY) pipeline/music.py build
	$(PY) pipeline/assemble.py

regen: validate
	@test -n "$(SHOT)" || (echo "usage: make regen SHOT=s05" && exit 1)
	$(PY) pipeline/narration.py --only $(SHOT)
	$(PY) pipeline/keyframes.py shots --only $(SHOT)
	$(PY) pipeline/shots.py render
	$(PY) pipeline/music.py build
	$(PY) pipeline/assemble.py
	@echo "--- model calls logged in this run:" && tail -n 5 runs.jsonl

costs:
	$(PY) pipeline/costs_report.py

test:
	$(PY) -m pytest -q tests

clean:
	rm -rf outputs/radio_cut outputs/final/_work outputs/shots/_import outputs/music/_import
