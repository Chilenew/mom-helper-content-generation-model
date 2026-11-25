"""Stage: script. Uses Gemini to draft a storyboard from a story brief, and to translate narration.

It never overwrites storyboard.json on its own: drafts and translations are written to outputs/script/
for a human to review, then copied in deliberately. The storyboard stays the contract you control.

Usage:
  python pipeline/script.py draft --brief story/brief.md       # -> outputs/script/storyboard.draft.json
  python pipeline/script.py translate --lang om                # subtitle_en -> Afaan Oromo, for review
  python pipeline/script.py translate --lang am --apply        # write translations into storyboard.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (OUTPUTS, ROOT, load_env, load_storyboard, rel, require_env,  # noqa: E402
                    save_storyboard, with_retries)

OUT_DIR = OUTPUTS / "script"
LANG_NAMES = {"am": "Amharic", "om": "Afaan Oromo", "ti": "Tigrinya", "so": "Somali", "en": "English"}


def client_and_model(sb):
    from google import genai
    model = os.environ.get("TEXT_MODEL") or sb["models"].get("script", {}).get("name", "gemini-3.8-flash")
    return genai.Client(api_key=require_env("GEMINI_API_KEY")), model


def generate_json(client, model, prompt):
    from google.genai import types
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7))
    return json.loads(resp.text)


def draft(args, sb):
    brief = Path(args.brief).read_text(encoding="utf-8")
    schema = (ROOT / "schema" / "storyboard.schema.json").read_text(encoding="utf-8")
    prompt = (
        "You are a film director planning a 60-90 second vertical short film made with AI image and "
        "image-to-video models. Write a storyboard as JSON that validates against this JSON Schema.\n\n"
        f"SCHEMA:\n{schema}\n\nSTORY BRIEF:\n{brief}\n\n"
        "Rules: 8-12 shots of 5-9 seconds; one idea and one gentle movement per shot; vary shot sizes; "
        "every shot has a one-sentence reason; image prompts describe subject, setting, light and framing, "
        "with the subject centred; motion prompts describe only motion and camera; no readable text in images; "
        "narration in the narration language, short sentences written for the ear; subtitle_en is a faithful "
        "English translation; music cues are instrumental with a caption of style, mood, instruments and texture."
    )
    client, model = client_and_model(sb)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "storyboard.draft.json"

    def call():
        data = generate_json(client, model, prompt)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return data, out, {"brief_chars": len(brief)}

    with_retries(call, stage="script", model=model, provider="gemini_api", params={"task": "draft"})
    print(f"draft written to {rel(out)}. Validate it with: python pipeline/validate.py {rel(out)}")


def translate(args, sb):
    lang = args.lang
    name = LANG_NAMES.get(lang, lang)
    lines = {s["id"]: s["narration"]["subtitle_en"] for s in sb["shots"]}
    prompt = (
        f"Translate each English narration line into natural spoken {name}, as a warm family storyteller "
        "would say it aloud. Keep sentences short and easy for text-to-speech. Keep names unchanged. "
        "Return a JSON object mapping each id to its translation.\n\n" + json.dumps(lines, ensure_ascii=False))
    client, model = client_and_model(sb)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"translations_{lang}.json"

    def call():
        data = generate_json(client, model, prompt)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return data, out, {"lines": len(lines), "lang": lang}

    data = with_retries(call, stage="script", model=model, provider="gemini_api",
                        params={"task": "translate", "lang": lang})
    print(f"translations written to {rel(out)}. Ask a native speaker to check them before using.")
    if args.apply:
        for s in sb["shots"]:
            if s["id"] in data:
                s["narration"]["text"] = data[s["id"]]
        sb["language"]["narration"] = lang
        save_storyboard(sb)
        print("storyboard.json updated; bump its version and note the change in EXPERIMENTS.md.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--brief", default=str(ROOT / "story" / "brief.md"))
    t = sub.add_parser("translate")
    t.add_argument("--lang", required=True, help="am, om, ti, so ...")
    t.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    load_env()
    sb = load_storyboard()
    {"draft": draft, "translate": translate}[args.cmd](args, sb)


if __name__ == "__main__":
    main()
