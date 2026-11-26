"""Unit tests for the parts of the pipeline that do not call models."""
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import validate  # noqa: E402
from common import cache_valid, input_hash, shot_timeline, write_cache_meta  # noqa: E402
from media import ass_time, srt_time, subtitle_chunks, wrap  # noqa: E402

STORY = json.loads(validate.STORY_PATH.read_text(encoding="utf-8"))
CONFIG = json.loads(validate.CONFIG_PATH.read_text(encoding="utf-8"))
SB = validate.merge(STORY, CONFIG)


def run_validate(story, config, tmp_path):
    sp, cp = tmp_path / "story.json", tmp_path / "config.json"
    sp.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    cp.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([sys.executable, str(ROOT / "src" / "validate.py"), str(sp), str(cp)],
                          capture_output=True, text=True, encoding="utf-8")


def test_storyboard_is_valid():
    _, errors, _ = validate.check()
    assert not errors, errors


def test_validator_catches_errors(tmp_path):
    story, config = copy.deepcopy(STORY), copy.deepcopy(CONFIG)
    del story["shots"][1]["shot_reason"]
    story["end_card"]["disclosure"] = "Thank you"           # end card no longer says AI
    r = run_validate(story, config, tmp_path)
    assert r.returncode == 1
    assert "'shot_reason' is a required property" in r.stdout
    assert "end_card/text" in r.stdout


def test_cross_checks_run_on_the_merged_storyboard(tmp_path):
    config = copy.deepcopy(CONFIG)
    config["shots"]["shot_01"]["characters"] = ["ghost"]
    r = run_validate(STORY, config, tmp_path)
    assert r.returncode == 1 and "unknown character 'ghost'" in r.stdout


def test_every_story_shot_needs_config(tmp_path):
    config = copy.deepcopy(CONFIG)
    del config["shots"]["shot_05"]
    r = run_validate(STORY, config, tmp_path)
    assert r.returncode == 1 and "shot_05: missing from pipeline_config.json" in r.stdout


def test_real_person_requires_consent(tmp_path):
    config = copy.deepcopy(CONFIG)
    config["characters"][0]["real_person"] = True
    r = run_validate(STORY, config, tmp_path)
    assert r.returncode == 1 and "consent_ref" in r.stdout


def test_merge_maps_story_fields():
    s, m = STORY["shots"][0], SB["shots"][0]
    assert m["duration_s"] == s["duration"]
    assert m["keyframe"]["prompt"] == s["image_prompt"]
    assert m["narration"]["text"] == s["narration"]
    assert m["reason"] == s["shot_reason"]
    assert STORY["end_card"]["title"] in SB["end_card"]["text"]
    assert SB["export"]["aspect_ratios"] == STORY["aspect_ratios"]


def test_config_motion_prompt_overrides_story():
    sid = next(k for k, v in CONFIG["shots"].items() if v.get("motion_prompt"))
    merged = next(s for s in SB["shots"] if s["id"] == sid)
    assert merged["motion"]["prompt"] == CONFIG["shots"][sid]["motion_prompt"]


def test_write_back_keeps_files_separate(tmp_path):
    sp, cp = tmp_path / "story.json", tmp_path / "config.json"
    sp.write_text(json.dumps(STORY, ensure_ascii=False), encoding="utf-8")
    cp.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    sb = validate.merge(STORY, CONFIG)
    sb["music"]["chosen_candidate"] = 2
    sb["shots"][0]["narration"]["text"] = "new line"
    validate.write_back(sb, sp, cp)
    story, config = json.loads(sp.read_text(encoding="utf-8")), json.loads(cp.read_text(encoding="utf-8"))
    assert config["music"]["chosen_candidate"] == 2
    assert story["shots"][0]["narration"] == "new line"
    assert "music" not in story and "chosen_candidate" not in json.dumps(story)


def test_total_duration_in_range():
    _, shots_s, film_s = shot_timeline(SB)
    assert SB["export"]["min_total_s"] <= film_s <= SB["export"]["max_total_s"]
    assert film_s == shots_s + SB["end_card"]["duration_s"]


def test_hash_is_stable_and_order_independent():
    assert input_hash({"a": 1, "b": "x"}) == input_hash({"b": "x", "a": 1})
    assert input_hash({"a": 1}) != input_hash({"a": 2})


def test_cache_roundtrip(tmp_path):
    out = tmp_path / "x.wav"
    out.write_bytes(b"data")
    assert not cache_valid(out, "abc")
    write_cache_meta(out, "abc", {"k": 1})
    assert cache_valid(out, "abc")
    assert not cache_valid(out, "different")


def test_subtitles_at_most_two_lines():
    for s in SB["shots"]:
        for chunk in subtitle_chunks(s["narration"]["subtitle_en"]):
            lines = wrap(chunk).split("\n")
            assert len(lines) <= 2, s["id"]
            assert all(len(ln) <= 46 for ln in lines), (s["id"], lines)


def test_time_formats():
    assert srt_time(61.5) == "00:01:01,500"
    assert ass_time(61.5) == "0:01:01.50"


def test_every_shot_has_a_reason_and_seed():
    for s in SB["shots"]:
        assert len(s["reason"]) >= 10
        assert isinstance(s["keyframe"]["seed"], int)
        if s["motion"]["mode"] == "i2v":
            assert isinstance(s["motion"]["seed"], int)
