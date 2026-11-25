"""Stage: assemble. Cuts the shots to the narration, ducks the score, normalises loudness, burns in
subtitles, adds the AI end card and exports both aspect ratios. All from the storyboard, all in code.

Usage:
  python pipeline/assemble.py                  # both aspect ratios
  python pipeline/assemble.py --aspect 9:16    # just one

Reads:  outputs/shots/manifest.json, outputs/narration/*.wav, outputs/music/score.wav
Writes: outputs/final/film_9x16.mp4, outputs/final/film_16x9.mp4, outputs/final/assembly_report.json,
        outputs/subtitles/subtitles_en.srt
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (OUTPUTS, ROOT, ffprobe_duration, load_storyboard, rel, run_ffmpeg,  # noqa: E402
                    shot_timeline)
from media import build_voice_track, end_card_drawtext, mix, subtitle_cues, write_ass, write_srt  # noqa: E402

OUT_DIR = OUTPUTS / "final"
WORK = OUT_DIR / "_work"
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


def render(sb, manifest, aspect, mix_path, cues):
    w, h = SIZES[aspect]
    fps = sb["export"]["fps"]
    _, shots_s, film_s = shot_timeline(sb)
    ass = WORK / f"subtitles_{w}x{h}.ass"
    write_ass(cues, w, h, ass)

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
              f"ass={ass}," + ",".join(end_card_drawtext(sb, w, h, shots_s)) + "[v]")
    out = OUT_DIR / f"film_{aspect.replace(':', 'x')}.mp4"
    run_ffmpeg([*ins, "-i", mix_path, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", f"{n}:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", fps, "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{film_s}", "-movflags", "+faststart", out])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aspect", choices=list(SIZES), nargs="*")
    args = ap.parse_args()

    sb = load_storyboard()
    WORK.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUTS / "shots" / "manifest.json"
    if not manifest_path.exists():
        sys.exit("No shot manifest. Run: python pipeline/shots.py render")
    manifest = json.loads(manifest_path.read_text())
    missing = [s["id"] for s in sb["shots"] if s["id"] not in manifest]
    if missing:
        sys.exit(f"shots missing from manifest: {missing}. Run: python pipeline/shots.py render")
    score = OUTPUTS / "music" / "score.wav"
    if not score.exists():
        sys.exit("No score. Run: python pipeline/music.py build")

    voice = build_voice_track(sb, WORK / "voice.wav")
    loud = mix(sb, voice, score, WORK / "mix.wav", WORK)
    cues = subtitle_cues(sb)
    (OUTPUTS / "subtitles").mkdir(parents=True, exist_ok=True)
    write_srt(cues, OUTPUTS / "subtitles" / "subtitles_en.srt")

    lo, hi = sb["export"]["min_total_s"], sb["export"]["max_total_s"]
    report = {"storyboard_version": sb["version"], "loudness": loud, "sources": manifest, "outputs": {}}
    for aspect in args.aspect or sb["export"]["aspect_ratios"]:
        out = render(sb, manifest, aspect, WORK / "mix.wav", cues)
        d = ffprobe_duration(out)
        report["outputs"][aspect] = {"path": rel(out), "duration_s": round(d, 2), "within_limits": lo <= d <= hi}
        print(f"assemble: {rel(out)} ({d:.1f}s{'' if lo <= d <= hi else f', OUTSIDE {lo}-{hi}s'})")
    (OUT_DIR / "assembly_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
