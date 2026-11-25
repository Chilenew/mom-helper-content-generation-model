"""Validate storyboard.json against the JSON Schema, plus cross-field checks the schema cannot express.

Usage: python pipeline/validate.py [storyboard.json] [schema/storyboard.schema.json]
Exits non-zero on any error, so every other stage can call it first.
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cross_checks(sb):
    errors = []
    shot_ids = [s["id"] for s in sb["shots"]]
    char_ids = {c["id"] for c in sb["characters"]}
    cue_ids = {c["id"] for c in sb["music"]["cues"]}

    if len(shot_ids) != len(set(shot_ids)):
        errors.append("shot ids are not unique")

    for s in sb["shots"]:
        for c in s["characters"]:
            if c not in char_ids:
                errors.append(f"{s['id']}: unknown character '{c}'")
        if s.get("music_cue") and s["music_cue"] not in cue_ids:
            errors.append(f"{s['id']}: unknown music cue '{s['music_cue']}'")

    for cue in sb["music"]["cues"]:
        for key in ("start_shot", "end_shot"):
            if cue[key] not in shot_ids:
                errors.append(f"cue {cue['id']}: {key} '{cue[key]}' is not a shot id")
        if cue["start_shot"] in shot_ids and cue["end_shot"] in shot_ids:
            if shot_ids.index(cue["start_shot"]) > shot_ids.index(cue["end_shot"]):
                errors.append(f"cue {cue['id']}: start_shot comes after end_shot")

    shots_total = sum(s["duration_s"] for s in sb["shots"])
    total = shots_total + sb["end_card"]["duration_s"]
    lo, hi = sb["export"]["min_total_s"], sb["export"]["max_total_s"]
    if not lo <= total <= hi:
        errors.append(f"total duration {total}s is outside {lo}-{hi}s")

    seeds = [s["keyframe"]["seed"] for s in sb["shots"]]
    if len(seeds) != len(set(seeds)):
        errors.append("keyframe seeds are not unique (fine if intentional, but check)")

    return errors, shots_total, total


def main():
    sb_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "storyboard.json"
    schema_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "schema" / "storyboard.schema.json"
    sb, schema = load(sb_path), load(schema_path)

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(sb), key=lambda e: list(e.path))
    for e in schema_errors:
        print(f"SCHEMA  {'/'.join(map(str, e.path)) or '<root>'}: {e.message}")

    extra, shots_total, total = cross_checks(sb)
    for e in extra:
        print(f"CHECK   {e}")

    if schema_errors or extra:
        sys.exit(1)

    words = sum(len(s["narration"]["text"].split()) for s in sb["shots"])
    print(f"OK  {len(sb['shots'])} shots, {shots_total}s of shots + "
          f"{sb['end_card']['duration_s']}s end card = {total}s, {words} narration words")


if __name__ == "__main__":
    main()
