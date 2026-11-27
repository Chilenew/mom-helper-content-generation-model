"""Smoke test: call each hosted provider once and log latency to logs/runs.jsonl. Tells you on day one what works.

Usage: python src/pipeline.py smoke
Checks Gemini text, Gemini TTS, Azure Speech (Amharic) and a Cloudflare Workers AI image.
Kaggle (Wan 2.2, ACE-Step) is checked inside its notebook: see kaggle/README.md.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LOGS, load_env, log_call  # noqa: E402

OUT = LOGS / "smoke"


def timed(stage_model, provider, params, fn):
    t = time.monotonic()
    try:
        result = fn()
        log_call("smoke", stage_model, provider, params, time.monotonic() - t, "ok")
        return result
    except Exception as e:
        log_call("smoke", stage_model, provider, params, time.monotonic() - t, "error", error=str(e)[:500])
        raise


def check(name, fn):
    start = time.monotonic()
    try:
        detail = fn()
        print(f"  OK    {name:<18} {time.monotonic() - start:6.1f}s  {detail}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {name:<18} {time.monotonic() - start:6.1f}s  {type(exc).__name__}: {str(exc)[:200]}")
        return False


def gemini_text():
    from google import genai
    model = os.environ.get("TEXT_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = timed(model, "gemini_api", {}, lambda: client.models.generate_content(
        model=model, contents="Reply with the Amharic word for 'mother' and nothing else."))
    return f"{model}: {r.text.strip()[:40]}"


def gemini_tts():
    from google import genai
    from generate_audio import gemini_tts as tts, write_wav
    model = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    pcm = timed(model, "gemini_api", {"voice": "Kore"}, lambda: tts(client, model, "Kore", "Say warmly: ሰላም እናቴ"))
    OUT.mkdir(parents=True, exist_ok=True)
    write_wav(OUT / "tts_am.wav", pcm)
    return f"{model}: {len(pcm) / 48000:.1f}s of audio -> logs/smoke/tts_am.wav (listen: is the Amharic right?)"


def azure_speech():
    from generate_audio import azure_tts
    audio = timed("am-ET-AmehaNeural", "azure_speech", {}, lambda: azure_tts("ሰላም እናቴ።", "am-ET-AmehaNeural", {}))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "azure_am.wav").write_bytes(audio)
    return f"am-ET-AmehaNeural: {len(audio) / 48000:.1f}s of audio -> logs/smoke/azure_am.wav (listen: is the Amharic right?)"


def cloudflare_image():
    from generate_images import cloudflare_image as cf
    model = os.environ.get("KEYFRAME_MODEL", "@cf/black-forest-labs/flux-2-klein-4b")
    img = timed(model, "cloudflare_workers_ai", {"w": 512, "h": 512}, lambda: cf(
        model, "hand-painted illustration of a large warka tree on green Ethiopian hills, no text", 512, 512, 7))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "image.png").write_bytes(img)
    return f"{model}: -> logs/smoke/image.png"


def main():
    load_env()
    print("Smoke test (each call is logged to logs/runs.jsonl):")
    results = []
    if os.environ.get("GEMINI_API_KEY"):
        results.append(check("Gemini text", gemini_text))
        results.append(check("Gemini TTS", gemini_tts))
    else:
        print("  SKIP  Gemini             GEMINI_API_KEY not set")
    if os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"):
        results.append(check("Azure speech", azure_speech))
    else:
        print("  SKIP  Azure speech       AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set")
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        results.append(check("Cloudflare image", cloudflare_image))
    else:
        print("  SKIP  Cloudflare         CF_ACCOUNT_ID / CF_API_TOKEN not set")
    print("Write what failed, and the model names that actually worked, in FAILURES.md and COSTS.md.")
    sys.exit(0 if results and all(results) else 1)


if __name__ == "__main__":
    main()
