"""Stage: audio. Narration (Gemini TTS), music (ACE-Step on Kaggle) and the radio cut prototype.

Narration: one WAV per shot, cached by a hash of its inputs.
  python src/generate_audio.py narration              # generate missing or changed lines only
  python src/generate_audio.py narration --only s05   # limit to one shot
  python src/generate_audio.py narration --force      # ignore the cache
  python src/generate_audio.py narration --dry-run    # no API call: silent placeholders sized to the text

Music: ACE-Step 1.5 runs on a Kaggle GPU; candidate choice and the final score are built here.
  1. python src/generate_audio.py music export   -> audio/music/kaggle_bundle.zip (jobs.json: cues x candidates)
     Upload as a Kaggle dataset, run kaggle/ace_step_music.py, download its output.
  2. python src/generate_audio.py music import --from ~/Downloads/music_output
  3. Listen to audio/music/candidates/<cue>_c<k>.wav under the radio cut, then
     python src/generate_audio.py music choose 1 --reason "quietest texture, voice stays clear"
  4. python src/generate_audio.py music build    -> audio/music/score.wav
     Each cue placed at its shot's start time with crossfades. Without candidates it falls back to the
     placeholder drone, so the film still assembles.

Radio cut: narration over placeholder music on a black 9:16 screen, with English subtitles and the end card.
The first prototype to show your audience (user test 1). It checks timing, ducking and loudness before
any pictures exist.
  python src/generate_audio.py radio                    # synthesised placeholder drone
  python src/generate_audio.py radio --music path.mp3   # your own licence-safe placeholder track

Reads:  shots[].narration, narration_settings, music, models.narration, models.music
Writes: audio/narration/<shot>.wav (+ .meta.json), audio/narration/timing.json,
        audio/music/candidates/*.wav, audio/music/score.wav, audio/subtitles/subtitles_en.srt,
        output/radio_cut/radio_cut.mp4
"""
import argparse
import json
import os
import shutil
import sys
import wave
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (MUSIC_DIR, NARRATION_DIR, NARRATION_EN_DIR, OUTPUT, RUNS_LOG, SUBTITLES_DIR, cache_valid,  # noqa: E402
                    ffprobe_duration, file_hash, filter_path, input_hash, load_env, load_storyboard, rel,
                    require_env, run_ffmpeg, save_storyboard, shot_timeline, with_retries, write_cache_meta)
from media import (build_voice_track, end_card_drawtext, mix, placeholder_music,  # noqa: E402
                   subtitle_cues, write_ass, write_srt)

SAMPLE_RATE = 24000  # Gemini TTS returns 24 kHz, 16-bit mono PCM
CAND_DIR = MUSIC_DIR / "candidates"
RADIO_DIR = OUTPUT / "radio_cut"
XFADE_S = 1.5
TAIL_S = 3.0


# ================================================================ narration

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


def edge_tts_wav(text, voice, params, out):
    """Microsoft neural voices through the free edge-tts library (no account; Edge read-aloud service).

    Fine for drafts and personal sharing; for a public release prefer a licensed service or a real recording.
    params: rate (e.g. "-12%"), pitch (e.g. "+0Hz")."""
    import asyncio
    import tempfile

    import edge_tts
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = Path(tmp) / "line.mp3"
        asyncio.run(edge_tts.Communicate(text, voice, rate=params.get("rate", "+0%"),
                                         pitch=params.get("pitch", "+0Hz")).save(str(mp3)))
        if not mp3.exists() or mp3.stat().st_size < 1000:
            raise RuntimeError("edge-tts returned no audio")
        run_ffmpeg(["-i", mp3, "-ar", str(SAMPLE_RATE), "-ac", "1", out])


def azure_tts(text, voice, params):
    """Azure AI Speech REST API -> 24 kHz 16-bit mono WAV bytes. Needs AZURE_SPEECH_KEY and AZURE_SPEECH_REGION.

    params: rate (e.g. "-10%"), pitch (e.g. "-2%"), break_ms (pause after sentence punctuation)."""
    import html
    import re
    import urllib.error
    import urllib.request
    key, region = require_env("AZURE_SPEECH_KEY"), require_env("AZURE_SPEECH_REGION")
    lang = "-".join(voice.split("-")[:2])  # am-ET-AmehaNeural -> am-ET
    body = html.escape(text)
    if params.get("break_ms"):  # a breath after each sentence or clause (Amharic and Latin punctuation)
        body = re.sub(r"([።፣፤…,.;])\s*", lambda m: f'{m.group(1)}<break time="{params["break_ms"]}ms"/>', body)
    ssml = (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>"
            f"<voice name='{voice}'><prosody rate='{params.get('rate', '0%')}' pitch='{params.get('pitch', '0%')}'>"
            f"{body}</prosody></voice></speak>")
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"),
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm", "User-Agent": "film-pipeline"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from e
    if len(audio) < 1000:
        raise RuntimeError("Azure returned no audio")
    return audio


def cmd_narration(args, sb):
    load_env()
    NARRATION_DIR.mkdir(parents=True, exist_ok=True)

    model = os.environ.get("TTS_MODEL") or sb["models"]["narration"]["name"]
    provider = sb["models"]["narration"]["provider"]
    params = sb["models"]["narration"].get("params", {})
    voice = sb["narration_settings"]["voice"]
    style = sb["narration_settings"]["style_instruction"]
    wps = sb["narration_settings"].get("words_per_second_estimate", 2.0)

    client = None  # created only if a line actually needs generating, so cached runs need no key

    generated, cached, timing = 0, 0, {}
    for shot in sb["shots"]:
        sid = shot["id"]
        text = shot["narration"]["text"].strip()
        out = NARRATION_DIR / f"{sid}.wav"
        if args.only and sid not in args.only:
            if out.exists():
                timing[sid] = {"planned_s": shot["duration_s"], "narration_s": round(ffprobe_duration(out), 2)}
            continue

        inputs = {"model": model, "voice": voice, "style": style, "text": text, "dry_run": args.dry_run}
        if provider != "gemini_api":
            inputs.update(provider=provider, params=params)
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
        elif provider == "edge_tts":
            def call(out=out, text=text):
                edge_tts_wav(text, voice, params, out)
                return None, out, {"chars": len(text)}

            with_retries(call, stage="narration", model=voice, provider=provider,
                         params={"voice": voice, "chars": len(text), **params}, shot_id=sid)
            write_cache_meta(out, h, inputs)
            generated += 1
            print(f"  {sid}: generated")
        elif provider == "azure_speech":
            def call(out=out, text=text):
                audio = azure_tts(text, voice, params)
                out.write_bytes(audio)
                return None, out, {"chars": len(text)}

            with_retries(call, stage="narration", model=voice, provider=provider,
                         params={"voice": voice, "chars": len(text), **params}, shot_id=sid)
            write_cache_meta(out, h, inputs)
            generated += 1
            print(f"  {sid}: generated")
        else:
            if client is None:
                from google import genai
                client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
            prompt = tts_prompt(style, text)

            def call(out=out, prompt=prompt, text=text):
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
    (NARRATION_DIR / "timing.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")

    total_voice = sum(t["narration_s"] for t in timing.values())
    tight = [sid for sid, t in timing.items() if not t["fits"]]
    print(f"narration: {generated} generated, {cached} cached, {total_voice:.1f}s of voice")
    if tight:
        print(f"  WARNING: narration is longer than (or within 0.5s of) the shot in: {', '.join(tight)}. "
              "Lengthen that shot's duration in storyboard/storyboard.json or shorten the line.")


def cmd_narration_en(args, sb):
    """English voice-over: reads each shot's subtitle_en aloud, for the film_*_en.mp4 versions."""
    NARRATION_EN_DIR.mkdir(parents=True, exist_ok=True)
    ev = sb["narration_settings"].get("english_voice") or sys.exit("narration_settings.english_voice is not set")
    voice, params = ev["voice"], {k: v for k, v in ev.items() if k != "voice"}
    made = cached = 0
    for shot in sb["shots"]:
        sid = shot["id"]
        if args.only and sid not in args.only:
            continue
        text = shot["narration"]["subtitle_en"].strip()
        out = NARRATION_EN_DIR / f"{sid}.wav"
        inputs = {"provider": "edge_tts", "voice": voice, "params": params, "text": text, "dry_run": args.dry_run}
        h = input_hash(inputs)
        if not args.force and cache_valid(out, h):
            cached += 1
            continue
        if args.dry_run or not text:
            est = max(1.0, len(text.split()) / 2.5) if text else 0.1
            run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{est:.2f}", out])
        else:
            def call(out=out, text=text):
                edge_tts_wav(text, voice, params, out)
                return None, out, {"chars": len(text)}
            with_retries(call, stage="narration_en", model=voice, provider="edge_tts",
                         params={"voice": voice, "chars": len(text), **params}, shot_id=sid)
        write_cache_meta(out, h, inputs)
        made += 1
    tight = []
    for shot in sb["shots"]:
        f = NARRATION_EN_DIR / f"{shot['id']}.wav"
        if f.exists() and ffprobe_duration(f) > shot["duration_s"] - 0.6:  # 0.4 s lead-in + a little air
            tight.append(f"{shot['id']} ({ffprobe_duration(f):.1f}s of {shot['duration_s']}s)")
    print(f"narration (English, {voice}): {made} generated, {cached} cached")
    if tight:
        print(f"  WARNING: English line too long for the shot: {', '.join(tight)}. Shorten subtitle_en or speed up rate.")


# ================================================================ music

def cue_windows(sb):
    """Start and end time of every cue on the film timeline; the last cue runs under the end card."""
    starts, shots_s, film_s = shot_timeline(sb)
    idx = {s["id"]: i for i, s in enumerate(sb["shots"])}
    wins = []
    for n, cue in enumerate(sb["music"]["cues"]):
        a = starts[idx[cue["start_shot"]]]
        e = idx[cue["end_shot"]]
        b = starts[e] + sb["shots"][e]["duration_s"]
        if n == len(sb["music"]["cues"]) - 1:
            b = film_s
        wins.append((cue, a, b))
    return wins


def cmd_music_export(args, sb):
    bundle = MUSIC_DIR / "kaggle_bundle"
    shutil.rmtree(bundle, ignore_errors=True)
    bundle.mkdir(parents=True)
    m = sb["models"]["music"]
    jobs = []
    for cue, a, b in cue_windows(sb):
        dur = round(b - a + XFADE_S + TAIL_S, 1)
        for k in range(sb["music"]["candidates"]):
            jobs.append({"cue_id": cue["id"], "candidate": k, "caption": cue["caption"], "bpm": cue["bpm"],
                         "keyscale": cue["key"], "instrumental": cue["instrumental"], "duration": dur,
                         "seed": cue["seed"] + k, "out_name": f"{cue['id']}_c{k}"})
    (bundle / "jobs.json").write_text(json.dumps({"model": m["name"], "params": m.get("params", {}), "jobs": jobs},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    zpath = MUSIC_DIR / "kaggle_bundle.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(bundle / "jobs.json", "jobs.json")
    print(f"music: {len(jobs)} job(s) -> {rel(zpath)}. Run kaggle/ace_step_music.py with it attached.")


def cmd_music_import(args, sb):
    src = Path(args.from_dir).expanduser()
    if src.suffix == ".zip":
        tmp = MUSIC_DIR / "_import"
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(list(src.rglob("*_c[0-9]*.wav")) + list(src.rglob("*_c[0-9]*.flac"))):
        dst = CAND_DIR / (f.stem + ".wav")
        run_ffmpeg(["-i", f, "-ar", "48000", "-ac", "2", dst])
        n += 1
    log = next(src.rglob("kaggle_runs.jsonl"), None)
    appended = 0
    if log:
        RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
        seen = set(RUNS_LOG.read_text(encoding="utf-8").splitlines()) if RUNS_LOG.exists() else set()
        with open(RUNS_LOG, "a", encoding="utf-8") as fh:
            for line in log.read_text(encoding="utf-8").splitlines():
                if line.strip() and line not in seen:
                    fh.write(line + "\n")
                    appended += 1
    print(f"music: imported {n} candidate(s) to {rel(CAND_DIR)}, appended {appended} log line(s)")


def cmd_music_choose(args, sb):
    missing = [c["id"] for c in sb["music"]["cues"] if not (CAND_DIR / f"{c['id']}_c{args.candidate}.wav").exists()]
    if missing:
        sys.exit(f"candidate {args.candidate} missing for cues {missing}")
    sb["music"]["chosen_candidate"] = args.candidate
    sb["music"]["chosen_reason"] = args.reason
    save_storyboard(sb)
    print(f"chosen candidate {args.candidate}: {args.reason}\nAdd this comparison to EXPERIMENTS.md.")


def cmd_music_build(args, sb):
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    _, _, film_s = shot_timeline(sb)
    out = MUSIC_DIR / "score.wav"
    k = sb["music"].get("chosen_candidate")
    wins = cue_windows(sb)
    files = [CAND_DIR / f"{cue['id']}_c{k}.wav" for cue, _, _ in wins] if k is not None else []
    if k is None or not all(f.exists() for f in files):
        inputs = {"fallback": "placeholder", "film_s": film_s}
        if not cache_valid(out, input_hash(inputs)):
            placeholder_music(film_s, out)
            write_cache_meta(out, input_hash(inputs), inputs)
        print("music: no chosen ACE-Step candidate yet -> placeholder drone used as the score")
        return
    inputs = {"files": [file_hash(f) for f in files], "windows": [(c["id"], a, b) for c, a, b in wins],
              "film_s": film_s, "xfade": XFADE_S}
    h = input_hash(inputs)
    if cache_valid(out, h):
        print("music: score cached")
        return
    ins, fc = [], []
    for i, ((cue, a, b), f) in enumerate(zip(wins, files)):
        ins += ["-i", f]
        first, last = i == 0, i == len(wins) - 1
        start = a if first else a - XFADE_S
        length = (b - start) + (0 if last else XFADE_S)
        chain = f"[{i}:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS"
        chain += ",afade=t=in:d=2" if first else f",afade=t=in:d={XFADE_S}"
        chain += f",afade=t=out:st={length - 3:.3f}:d=3" if last else f",afade=t=out:st={length - XFADE_S:.3f}:d={XFADE_S}"
        chain += f",adelay={int(start * 1000)}|{int(start * 1000)}[c{i}]"
        fc.append(chain)
    fc.append("".join(f"[c{i}]" for i in range(len(wins))) +
              f"amix=inputs={len(wins)}:normalize=0:duration=longest,atrim=0:{film_s}[score]")
    run_ffmpeg([*ins, "-filter_complex", ";".join(fc), "-map", "[score]", "-ar", "48000", "-ac", "2", out])
    write_cache_meta(out, h, inputs)
    print(f"music: score built from candidate {k} -> {rel(out)}")


# ================================================================ radio cut

def cmd_radio(args, sb):
    RADIO_DIR.mkdir(parents=True, exist_ok=True)
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)

    missing = [s["id"] for s in sb["shots"] if not (NARRATION_DIR / f"{s['id']}.wav").exists()]
    if missing:
        sys.exit(f"Missing narration for {missing}. Run: python src/generate_audio.py narration")

    _, shots_s, film_s = shot_timeline(sb)
    voice = build_voice_track(sb, RADIO_DIR / "voice.wav")
    music = Path(args.music) if args.music else placeholder_music(film_s, RADIO_DIR / "placeholder_music.wav")
    loud = mix(sb, voice, music, RADIO_DIR / "mix.wav", RADIO_DIR)

    cues = subtitle_cues(sb)
    write_srt(cues, SUBTITLES_DIR / "subtitles_en.srt")
    ass = RADIO_DIR / f"subtitles_{args.width}x{args.height}.ass"
    write_ass(cues, args.width, args.height, ass)

    vf = ",".join([f"ass={filter_path(ass)}", *end_card_drawtext(sb, args.width, args.height, shots_s)])
    out = RADIO_DIR / "radio_cut.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={args.width}x{args.height}:r={sb['export']['fps']}:d={film_s}",
                "-i", RADIO_DIR / "mix.wav", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", out])

    print(f"radio cut: {rel(out)} ({ffprobe_duration(out):.1f}s, pre-norm loudness "
          f"{loud['measured_input_i']:.1f} LUFS -> target {sb['export']['loudness_lufs']} LUFS)")
    print(f"subtitles: {rel(SUBTITLES_DIR / 'subtitles_en.srt')}")


# ================================================================ CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("narration", help="Gemini TTS, one cached WAV per shot")
    n.add_argument("--only", nargs="*", help="shot ids to process")
    n.add_argument("--force", action="store_true")
    n.add_argument("--dry-run", action="store_true")
    n.set_defaults(fn=cmd_narration)

    ne = sub.add_parser("narration-en", help="English voice-over of subtitle_en (male voice by default)")
    ne.add_argument("--only", nargs="*", help="shot ids to process")
    ne.add_argument("--force", action="store_true")
    ne.add_argument("--dry-run", action="store_true")
    ne.set_defaults(fn=cmd_narration_en)

    m = sub.add_parser("music", help="ACE-Step candidates via Kaggle, then build the score")
    msub = m.add_subparsers(dest="music_cmd")
    msub.add_parser("export").set_defaults(fn=cmd_music_export)
    i = msub.add_parser("import")
    i.add_argument("--from", dest="from_dir", required=True)
    i.set_defaults(fn=cmd_music_import)
    c = msub.add_parser("choose")
    c.add_argument("candidate", type=int)
    c.add_argument("--reason", required=True, help="why this one: write it down, the brief asks for it")
    c.set_defaults(fn=cmd_music_choose)
    msub.add_parser("build").set_defaults(fn=cmd_music_build)
    m.set_defaults(fn=cmd_music_build)  # `music` alone builds the score

    r = sub.add_parser("radio", help="radio cut: narration + music + subtitles on a black screen")
    r.add_argument("--music", help="placeholder music file; default is a synthesised soft drone")
    r.add_argument("--width", type=int, default=720)
    r.add_argument("--height", type=int, default=1280)
    r.set_defaults(fn=cmd_radio)

    args = ap.parse_args()
    sb = load_storyboard()
    args.fn(args, sb)


if __name__ == "__main__":
    main()
