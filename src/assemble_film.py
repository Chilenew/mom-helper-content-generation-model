"""Stage: assemble. Cuts the shots to the narration, ducks the score, normalises loudness, burns in
subtitles, adds the AI end card and exports both aspect ratios. All from the storyboard, all in code.

Usage:
  python src/assemble_film.py                  # both aspect ratios
  python src/assemble_film.py --aspect 9:16    # just one
  python src/assemble_film.py --narration en   # English voice-over versions: film_*_en.mp4
  python src/assemble_film.py --subtitles am   # all-Amharic versions (Amharic voice + subtitles): film_*_am.mp4

Reads:  assets/video/manifest.json, audio/narration/*.wav, audio/music/score.wav
Writes: output/film_vertical.mp4 (9:16), output/film_horizontal.mp4 (16:9), output/assembly_report.json,
        audio/subtitles/subtitles_en.srt
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (FILM_NAMES, MUSIC_DIR, NARRATION_DIR, NARRATION_EN_DIR, OUTPUT, ROOT, SUBTITLES_DIR, VIDEO_DIR,  # noqa: E402
                    ffprobe_duration, filter_path, load_storyboard, rel, run_ffmpeg, shot_timeline)
from media import build_voice_track, end_card_drawtext, mix, subtitle_cues, write_ass, write_srt  # noqa: E402

OUT_DIR = OUTPUT
WORK = OUT_DIR / "_work"
# Subtitle fonts: Amharic needs Ethiopic glyphs (Ebrima ships with Windows; on Linux install fonts-sil-abyssinica).
SUB_FONTS = {"en": "DejaVu Sans", "am": "Ebrima" if os.name == "nt" else "Abyssinica SIL"}
SUB_SCALE = {"en": 1.0, "am": 1.15}  # Ethiopic letters look smaller than Latin at the same size


def ass_fontsdir():
    """Point libass at the Windows fonts folder so it finds Ebrima by name (its default lookup may not)."""
    if os.name != "nt":
        return ""
    return ":fontsdir=" + filter_path(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")


SIZES = {"9:16": (720, 1280), "16:9": (1280, 720)}
HEAD_TRIM_S = 0.3   # many generated clips have a weak first frames
TAIL_TRIM_S = 0.2
MAX_SLOWDOWN = 1.5  # stretch short Wan clips at most this much, then hold the last frame


def segment_filter(i, entry, duration, fps, w, h):
    """Filter chain that turns input i into exactly `duration` seconds at w x h."""
    src = ROOT / entry["path"]
    chain = f"[{i}:v]"
    if entry["source"] == "wan":
        clip = ffprobe_duration(src)
        usable = max(0.5, clip - HEAD_TRIM_S - TAIL_TRIM_S)
        chain += f"trim=start={HEAD_TRIM_S}:duration={usable:.3f},setpts=PTS-STARTPTS,"
        if usable < duration:
            chain += f"setpts={min(duration / usable, MAX_SLOWDOWN):.4f}*PTS,"
        chain += f"tpad=stop_mode=clone:stop_duration={duration:.3f},"
    chain += (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
              f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,format=yuv420p[s{i}]")
    return chain


def render(sb, manifest, aspect, mix_path, cues, work, suffix="", sub_lang="en"):
    w, h = SIZES[aspect]
    fps = sb["export"]["fps"]
    _, shots_s, film_s = shot_timeline(sb)
    ass = work / f"subtitles_{w}x{h}.ass"
    write_ass(cues, w, h, ass, font=SUB_FONTS[sub_lang], scale=SUB_SCALE[sub_lang])

    ins, fc = [], []
    for i, shot in enumerate(sb["shots"]):
        entry = manifest[shot["id"]]
        ins += ["-i", ROOT / entry["path"]]
        fc.append(segment_filter(i, entry, shot["duration_s"], fps, w, h))
    n = len(sb["shots"])
    ec = sb["end_card"]["duration_s"]
    fc.append(f"color=c=black:s={w}x{h}:r={fps}:d={ec},format=yuv420p[s{n}]")
    fc.append("".join(f"[s{i}]" for i in range(n + 1)) + f"concat=n={n + 1}:v=1:a=0,"
              f"fade=t=in:st=0:d=0.6,fade=t=out:st={shots_s - 0.6:.3f}:d=0.6,"
              f"ass={filter_path(ass)}{ass_fontsdir()}," + ",".join(end_card_drawtext(sb, w, h, shots_s)) + "[v]")
    out = OUT_DIR / FILM_NAMES[aspect].replace(".mp4", f"{suffix}.mp4")
    run_ffmpeg([*ins, "-i", mix_path, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", f"{n}:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", fps, "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{film_s}", "-movflags", "+faststart", out])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aspect", choices=list(SIZES), nargs="*")
    ap.add_argument("--subtitles", choices=["en", "am"], default="en",
                    help="subtitle language; --narration am --subtitles am gives the all-Amharic film_*_am.mp4")
    ap.add_argument("--narration", choices=["am", "en"], default="am",
                    help="am: Amharic narration (film_*.mp4); en: English voice-over of the subtitles (film_*_en.mp4)")
    args = ap.parse_args()

    sb = load_storyboard()
    en = args.narration == "en"
    work = WORK / "en" if en else WORK
    narr_dir = NARRATION_EN_DIR if en else NARRATION_DIR
    if en and args.subtitles == "am":
        sys.exit("English voice with Amharic subtitles is not a supported combination")
    suffix = "_en" if en else ("_am" if args.subtitles == "am" else "")
    missing_voice = [s["id"] for s in sb["shots"] if not (narr_dir / f"{s['id']}.wav").exists()]
    if missing_voice:
        sys.exit(f"narration missing for {missing_voice}. Run: python src/generate_audio.py "
                 + ("narration-en" if en else "narration"))
    work.mkdir(parents=True, exist_ok=True)
    manifest_path = VIDEO_DIR / "manifest.json"
    if not manifest_path.exists():
        sys.exit("No shot manifest. Run: python src/generate_video.py render")
    manifest = json.loads(manifest_path.read_text())
    missing = [s["id"] for s in sb["shots"] if s["id"] not in manifest]
    if missing:
        sys.exit(f"shots missing from manifest: {missing}. Run: python src/generate_video.py render")
    score = MUSIC_DIR / "score.wav"
    if not score.exists():
        sys.exit("No score. Run: python src/generate_audio.py music build")

    voice = build_voice_track(sb, work / "voice.wav", narr_dir)
    loud = mix(sb, voice, score, work / "mix.wav", work)
    cues = subtitle_cues(sb, narr_dir=narr_dir, lang=args.subtitles)
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    write_srt(cues, SUBTITLES_DIR / (f"subtitles_am.srt" if args.subtitles == "am" else f"subtitles_en{suffix}.srt"))

    lo, hi = sb["export"]["min_total_s"], sb["export"]["max_total_s"]
    report = {"storyboard_version": sb["version"], "narration": args.narration, "subtitles": args.subtitles, "loudness": loud, "sources": manifest, "outputs": {}}
    for aspect in args.aspect or sb["export"]["aspect_ratios"]:
        out = render(sb, manifest, aspect, work / "mix.wav", cues, work, suffix, args.subtitles)
        d = ffprobe_duration(out)
        report["outputs"][aspect] = {"path": rel(out), "duration_s": round(d, 2), "within_limits": lo <= d <= hi}
        print(f"assemble: {rel(out)} ({d:.1f}s{'' if lo <= d <= hi else f', OUTSIDE {lo}-{hi}s'})")
    (OUT_DIR / f"assembly_report{suffix}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
