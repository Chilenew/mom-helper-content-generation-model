"""Radio cut: narration over placeholder music on a black 9:16 screen, with English subtitles and the end card.

The first prototype to show your audience (user test 1). It also checks timing, ducking and loudness
before any pictures exist.

Usage:
  python pipeline/radio_cut.py                      # synthesised placeholder drone
  python pipeline/radio_cut.py --music path.mp3     # your own licence-safe placeholder track

Reads:  storyboard.json, outputs/narration/*.wav
Writes: outputs/radio_cut/radio_cut.mp4, outputs/subtitles/subtitles_en.srt
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUTPUTS, ffprobe_duration, load_storyboard, rel, run_ffmpeg, shot_timeline  # noqa: E402
from media import (NARR_DIR, build_voice_track, end_card_drawtext, mix, placeholder_music,  # noqa: E402
                   subtitle_cues, write_ass, write_srt)

OUT_DIR = OUTPUTS / "radio_cut"
SUB_DIR = OUTPUTS / "subtitles"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--music", help="placeholder music file; default is a synthesised soft drone")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    args = ap.parse_args()

    sb = load_storyboard()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUB_DIR.mkdir(parents=True, exist_ok=True)

    missing = [s["id"] for s in sb["shots"] if not (NARR_DIR / f"{s['id']}.wav").exists()]
    if missing:
        sys.exit(f"Missing narration for {missing}. Run: python pipeline/narration.py")

    _, shots_s, film_s = shot_timeline(sb)
    voice = build_voice_track(sb, OUT_DIR / "voice.wav")
    music = Path(args.music) if args.music else placeholder_music(film_s, OUT_DIR / "placeholder_music.wav")
    loud = mix(sb, voice, music, OUT_DIR / "mix.wav", OUT_DIR)

    cues = subtitle_cues(sb)
    write_srt(cues, SUB_DIR / "subtitles_en.srt")
    ass = OUT_DIR / f"subtitles_{args.width}x{args.height}.ass"
    write_ass(cues, args.width, args.height, ass)

    vf = ",".join([f"ass={ass}", *end_card_drawtext(sb, args.width, args.height, shots_s)])
    out = OUT_DIR / "radio_cut.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={args.width}x{args.height}:r={sb['export']['fps']}:d={film_s}",
                "-i", OUT_DIR / "mix.wav", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", out])

    print(f"radio cut: {rel(out)} ({ffprobe_duration(out):.1f}s, pre-norm loudness "
          f"{loud['measured_input_i']:.1f} LUFS -> target {sb['export']['loudness_lufs']} LUFS)")
    print(f"subtitles: {rel(SUB_DIR / 'subtitles_en.srt')}")


if __name__ == "__main__":
    main()
