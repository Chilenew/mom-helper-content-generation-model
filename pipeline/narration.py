"""Stage: narration. One WAV per shot from Gemini TTS, cached by a hash of its inputs.

Usage:
  python pipeline/narration.py              # generate missing or changed lines only
  python pipeline/narration.py --only s05   # limit to one shot
  python pipeline/narration.py --force      # ignore the cache
  python pipeline/narration.py --dry-run    # no API call: silent placeholders sized to the text

Reads:  shots[].narration.text, narration_settings, models.narration
Writes: outputs/narration/<shot>.wav (+ .meta.json), outputs/narration/timing.json
"""
import argparse
import json
import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (OUTPUTS, cache_valid, ffprobe_duration, input_hash, load_env,  # noqa: E402
                    load_storyboard, require_env, run_ffmpeg, with_retries, write_cache_meta)

OUT_DIR = OUTPUTS / "narration"
SAMPLE_RATE = 24000  # Gemini TTS returns 24 kHz, 16-bit mono PCM


def tts_prompt(style_instruction, text):
    # The style instruction goes in front of the line; Gemini TTS treats it as direction, not speech.
    return f"{style_instruction}\n\n{text}"


def write_wav(path, pcm_bytes):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)


def gemini_tts(client, model, voice, prompt):
    from google.genai import types
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))),
    )
    part = resp.candidates[0].content.parts[0]
    if not getattr(part, "inline_data", None) or not part.inline_data.data:
        raise RuntimeError("TTS response contained no audio")
    return part.inline_data.data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="shot ids to process")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    sb = load_storyboard()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    model = os.environ.get("TTS_MODEL") or sb["models"]["narration"]["name"]
    provider = sb["models"]["narration"]["provider"]
    voice = sb["narration_settings"]["voice"]
    style = sb["narration_settings"]["style_instruction"]
    wps = sb["narration_settings"].get("words_per_second_estimate", 2.0)

    client = None  # created only if a line actually needs generating, so cached runs need no key

    generated, cached, timing = 0, 0, {}
    for shot in sb["shots"]:
        sid = shot["id"]
        text = shot["narration"]["text"].strip()
        out = OUT_DIR / f"{sid}.wav"
        if args.only and sid not in args.only:
            if out.exists():
                timing[sid] = {"planned_s": shot["duration_s"], "narration_s": round(ffprobe_duration(out), 2)}
            continue

        inputs = {"model": model, "voice": voice, "style": style, "text": text, "dry_run": args.dry_run}
        h = input_hash(inputs)

        if not args.force and cache_valid(out, h):
            cached += 1
        elif not text:
            run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", "0.1", out])
            write_cache_meta(out, h, inputs)
        elif args.dry_run:
            est = max(1.0, len(text.split()) / wps)
            run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{est:.2f}", out])
            write_cache_meta(out, h, inputs)
            generated += 1
            print(f"  {sid}: dry-run placeholder {est:.1f}s")
        else:
            if client is None:
                from google import genai
                client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
            prompt = tts_prompt(style, text)

            def call():
                pcm = gemini_tts(client, model, voice, prompt)
                write_wav(out, pcm)
                return pcm, out, {"chars": len(text), "audio_s": round(len(pcm) / (2 * SAMPLE_RATE), 2)}

            with_retries(call, stage="narration", model=model, provider=provider,
                         params={"voice": voice, "style": style, "chars": len(text)}, shot_id=sid)
            write_cache_meta(out, h, inputs)
            generated += 1
            print(f"  {sid}: generated")

        timing[sid] = {"planned_s": shot["duration_s"], "narration_s": round(ffprobe_duration(out), 2)}

    # Timing report: the voice sets the cut. Shots where narration does not fit need a longer duration.
    for t in timing.values():
        t["headroom_s"] = round(t["planned_s"] - t["narration_s"], 2)
        t["fits"] = t["headroom_s"] >= 0.5
    (OUT_DIR / "timing.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")

    total_voice = sum(t["narration_s"] for t in timing.values())
    tight = [sid for sid, t in timing.items() if not t["fits"]]
    print(f"narration: {generated} generated, {cached} cached, {total_voice:.1f}s of voice")
    if tight:
        print(f"  WARNING: narration is longer than (or within 0.5s of) the shot in: {', '.join(tight)}. "
              "Lengthen duration_s in storyboard.json or shorten the line.")


if __name__ == "__main__":
    main()
