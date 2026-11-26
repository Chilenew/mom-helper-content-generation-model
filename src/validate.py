"""Load and validate the storyboard: the story (storyboard.json) plus the pipeline settings (pipeline_config.json).

The two files are kept apart on purpose:
  storyboard/storyboard.json        the story as written: shots, narration, prompts, reasons, end card.
                                    Validated by storyboard/storyboard.schema.json.
  storyboard/pipeline_config.json   what the story does not say but the pipeline needs: models, seeds,
                                    characters, shot sizes, English subtitles, music cue ids, export settings.

merge() combines them into the single structure every stage reads, which is validated against
storyboard/pipeline.schema.json, then cross-checked for things a schema cannot express.

Usage: python src/validate.py [storyboard/storyboard.json] [storyboard/pipeline_config.json]
Exits non-zero on any error, so every other stage can call it first.
"""
import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
STORY_PATH = ROOT / "storyboard" / "storyboard.json"
CONFIG_PATH = ROOT / "storyboard" / "pipeline_config.json"
STORY_SCHEMA = ROOT / "storyboard" / "storyboard.schema.json"
PIPELINE_SCHEMA = ROOT / "storyboard" / "pipeline.schema.json"

SEP = " · "  # end card lines; media.end_card_drawtext splits on it


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- story + config <-> merged

def merge(story, config):
    """The structure the stages read. Tolerant of missing keys, so validation can report every problem at once."""
    vc = story.get("visual_consistency", {})
    style_parts = [story.get("style", ""), vc.get("environment", ""), vc.get("lighting", "")]
    cshots = config.get("shots", {})
    shots = []
    for s in story.get("shots", []):
        c = cshots.get(s.get("id"), {})
        motion = {"mode": "i2v", **copy.deepcopy(c.get("motion", {}))}
        motion["prompt"] = c.get("motion_prompt") or s.get("motion_prompt", "")
        shot = {
            "id": s.get("id", ""),
            "duration_s": s.get("duration", 0),
            "shot_size": c.get("shot_size", "medium"),
            "reason": s.get("shot_reason", ""),
            "characters": list(c.get("characters", [])),
            "keyframe": {"prompt": c.get("keyframe_prompt") or s.get("image_prompt", ""),
                         "seed": c.get("keyframe_seed")},
            "motion": motion,
            "narration": {"text": s.get("narration", ""), "subtitle_en": c.get("subtitle_en", "")},
            "notes": " ".join(x for x in (f"Music: {s['music_cue']}" if s.get("music_cue") else "",
                                          c.get("notes", "")) if x),
        }
        if c.get("music_cue"):
            shot["music_cue"] = c["music_cue"]
        shots.append(shot)

    ec = story.get("end_card", {})
    sb = {
        "version": config.get("version", "0.0.0"),
        "title": story.get("title", ""),
        "english_title": story.get("english_title", ""),
        "genre": story.get("genre", ""),
        "target_duration": story.get("target_duration", 0),
        "logline": story.get("purpose", ""),
        "audience": story.get("target_audience", ""),
        "intent": story.get("central_message", ""),
        "language": config.get("language", {}),
        "style_block": ", ".join(p.strip().rstrip(".") for p in style_parts if p.strip()),
        "negative_prompt": config.get("negative_prompt", ""),
        "visual_consistency": vc,
        "models": config.get("models", {}),
        "characters": copy.deepcopy(config.get("characters", [])),
        "narration_settings": config.get("narration_settings", {}),
        "music": copy.deepcopy(config.get("music", {})),
        "shots": shots,
        "end_card": {"text": SEP.join(x for x in (ec.get("title"), ec.get("subtitle"), ec.get("disclosure")) if x),
                     "duration_s": ec.get("duration_seconds", 0)},
        "export": {"aspect_ratios": story.get("aspect_ratios", []), **config.get("export", {})},
    }
    return sb


def write_back(sb, story_path=STORY_PATH, config_path=CONFIG_PATH):
    """Persist the fields a command may change (approved references, chosen music, narration translations).

    Each goes back to the file that owns it; the story file is rewritten only if one of its fields changed."""
    story, config = load(story_path), load(config_path)
    config["characters"] = sb["characters"]
    config["music"] = sb["music"]
    config["language"] = sb["language"]
    config["version"] = sb["version"]
    Path(config_path).write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    by_id = {s["id"]: s for s in sb["shots"]}
    changed = False
    for s in story["shots"]:
        text = by_id[s["id"]]["narration"]["text"]
        if s["narration"] != text:
            s["narration"] = text
            changed = True
    if changed:
        Path(story_path).write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- checks

def schema_errors(instance, schema_path, label):
    schema = load(schema_path)
    Draft202012Validator.check_schema(schema)
    errs = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(map(str, e.path)))
    return [f"{label:<8}{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errs]


def pairing_errors(story, config):
    story_ids = [s.get("id") for s in story.get("shots", [])]
    config_ids = list(config.get("shots", {}))
    errors = [f"CONFIG  shots/{sid}: missing from pipeline_config.json" for sid in story_ids if sid not in config_ids]
    errors += [f"CONFIG  shots/{sid}: not in storyboard.json" for sid in config_ids if sid not in story_ids]
    return errors


def cross_checks(sb):
    errors, notes = [], []
    shot_ids = [s["id"] for s in sb["shots"]]
    char_ids = {c["id"] for c in sb["characters"]}
    cue_ids = {c["id"] for c in sb["music"].get("cues", [])}

    if len(shot_ids) != len(set(shot_ids)):
        errors.append("shot ids are not unique")

    for s in sb["shots"]:
        for c in s["characters"]:
            if c not in char_ids:
                errors.append(f"{s['id']}: unknown character '{c}'")
        if s.get("music_cue") and s["music_cue"] not in cue_ids:
            errors.append(f"{s['id']}: unknown music cue '{s['music_cue']}'")

    for cue in sb["music"].get("cues", []):
        for key in ("start_shot", "end_shot"):
            if cue[key] not in shot_ids:
                errors.append(f"cue {cue['id']}: {key} '{cue[key]}' is not a shot id")
        if cue["start_shot"] in shot_ids and cue["end_shot"] in shot_ids:
            if shot_ids.index(cue["start_shot"]) > shot_ids.index(cue["end_shot"]):
                errors.append(f"cue {cue['id']}: start_shot comes after end_shot")

    shots_total = sum(s["duration_s"] for s in sb["shots"])
    total = shots_total + sb["end_card"]["duration_s"]
    lo, hi = sb["export"].get("min_total_s", 0), sb["export"].get("max_total_s", 0)
    if not lo <= total <= hi:
        errors.append(f"total duration {total}s is outside {lo}-{hi}s")
    if sb.get("target_duration") and shots_total != sb["target_duration"]:
        notes.append(f"shots add up to {shots_total}s but target_duration is {sb['target_duration']}s")

    seeds = [s["keyframe"]["seed"] for s in sb["shots"]]
    if len(seeds) != len(set(seeds)):
        errors.append("keyframe seeds are not unique (fine if intentional, but check)")

    return errors, notes, shots_total, total


def check(story_path=STORY_PATH, config_path=CONFIG_PATH):
    """Return (merged storyboard, errors, notes). Errors are formatted lines; empty means valid."""
    story, config = load(story_path), load(config_path)
    errors = schema_errors(story, STORY_SCHEMA, "STORY") + pairing_errors(story, config)
    sb = merge(story, config)
    errors += schema_errors(sb, PIPELINE_SCHEMA, "MERGED")
    notes = []
    if not errors:
        extra, notes, _, _ = cross_checks(sb)
        errors += [f"CHECK   {e}" for e in extra]
    return sb, errors, notes


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Amharic in messages on a Windows console
    story_path = Path(sys.argv[1]) if len(sys.argv) > 1 else STORY_PATH
    config_path = Path(sys.argv[2]) if len(sys.argv) > 2 else CONFIG_PATH
    sb, errors, notes = check(story_path, config_path)
    for e in errors:
        print(e)
    if errors:
        sys.exit(1)
    for n in notes:
        print(f"NOTE    {n}")
    _, _, shots_total, total = cross_checks(sb)
    words = sum(len(s["narration"]["text"].split()) for s in sb["shots"])
    print(f"OK  {len(sb['shots'])} shots, {shots_total}s of shots + "
          f"{sb['end_card']['duration_s']}s end card = {total}s, {words} narration words")


if __name__ == "__main__":
    main()
