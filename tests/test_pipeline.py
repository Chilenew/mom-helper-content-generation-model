"""Unit tests for the parts of the pipeline that do not call models."""
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from common import cache_valid, input_hash, shot_timeline, write_cache_meta  # noqa: E402
from media import ass_time, srt_time, wrap  # noqa: E402

SB = json.loads((ROOT / "storyboard.json").read_text(encoding="utf-8"))


def run_validate(path):
    return subprocess.run([sys.executable, str(ROOT / "pipeline" / "validate.py"), str(path)],
                          capture_output=True, text=True)


def test_storyboard_is_valid():
    r = run_validate(ROOT / "storyboard.json")
    assert r.returncode == 0, r.stdout


def test_validator_catches_errors(tmp_path):
    bad = copy.deepcopy(SB)
    bad["shots"][0]["characters"] = ["ghost"]
    bad["end_card"]["text"] = "The end"
    del bad["shots"][1]["reason"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    r = run_validate(p)
    assert r.returncode == 1
    assert "unknown character 'ghost'" in r.stdout
    assert "'reason' is a required property" in r.stdout
    assert "end_card/text" in r.stdout


def test_real_person_requires_consent(tmp_path):
    bad = copy.deepcopy(SB)
    bad["characters"][0]["real_person"] = True
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    r = run_validate(p)
    assert r.returncode == 1 and "consent_ref" in r.stdout


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
        lines = wrap(s["narration"]["subtitle_en"]).split("\n")
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
