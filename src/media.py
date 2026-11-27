"""Shared media building blocks for the radio cut and the final assembly:
voice track, placeholder music, ducking + two-pass loudness, subtitles (SRT and frame-sized ASS), end card."""
import json
import re
from pathlib import Path

from common import NARRATION_DIR, drawtext_font, ffprobe_duration, run_ffmpeg, shot_timeline

NARR_DIR = NARRATION_DIR
LEAD_IN_S = 0.4  # a breath before each line


# ---------------------------------------------------------------- text helpers

def wrap(text, width=40):
    """At most two lines of about `width` characters, as the brief suggests."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    if len(lines) >= 2:  # two lines: break where the two halves are most even, so no word dangles alone
        best = min(range(1, len(words)),
                   key=lambda k: max(len(" ".join(words[:k])), len(" ".join(words[k:]))))
        lines = [" ".join(words[:best]), " ".join(words[best:])]
    return "\n".join(lines)


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def ass_time(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def drawtext_escape(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


# ---------------------------------------------------------------- subtitles

SUB_WIDTH = {"en": 40, "am": 26}  # characters per line; Ethiopic syllables are about 1.5x as wide as Latin letters


def subtitle_cues(sb, width=None, narr_dir=None, lang="en"):
    """(start, end, wrapped_text) per shot, timed to the measured narration rather than the planned duration.

    lang "en" shows narration.subtitle_en; lang "am" shows the Amharic narration text itself."""
    width = width or SUB_WIDTH[lang]
    starts, _, _ = shot_timeline(sb)
    cues = []
    for i, shot in enumerate(sb["shots"]):
        sub = (shot["narration"]["subtitle_en"] if lang == "en" else shot["narration"]["text"]).strip()
        if not sub:
            continue
        narr = (narr_dir or NARR_DIR) / f"{shot['id']}.wav"
        voice_len = ffprobe_duration(narr) if narr.exists() else shot["duration_s"] - 1
        start = starts[i] + LEAD_IN_S
        end = min(starts[i] + shot["duration_s"] - 0.1, start + max(voice_len, 1.5) + 0.3)
        # A line too long for two subtitle lines is shown in parts, each timed by its share of the characters.
        parts = subtitle_chunks(sub, width)
        total_chars = sum(len(p) for p in parts)
        t = start
        for p in parts:
            t_end = end if p is parts[-1] else t + (end - start) * len(p) / total_chars
            cues.append((round(t, 3), round(t_end, 3), wrap(p, width)))
            t = t_end
    return cues


def subtitle_chunks(text, width=40):
    """Split text into pieces that each fit in two lines of `width`, breaking at sentences, then clauses, then words."""
    limit = 2 * width
    if len(text) <= limit:
        return [text]
    pieces = re.split(r"(?<=[.!?…።፧])\s*", text)  # Latin and Ethiopic sentence ends
    pieces = [p for p in pieces if p]
    if any(len(p) > limit for p in pieces):
        pieces = [q for p in pieces for q in re.split(r"(?<=[,;:፣፤፥፦])\s*", p) if q]
    chunks, cur = [], ""
    for p in pieces:
        for w in (p.split() if len(p) > limit else [p]):
            if cur and len(cur) + 1 + len(w) > limit:
                chunks.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
    chunks.append(cur)
    return chunks


def write_srt(cues, path):
    body = "\n".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))
    Path(path).write_text(body, encoding="utf-8")


def write_ass(cues, width, height, path, font="DejaVu Sans", scale=1.0):
    """ASS with PlayRes = frame size so font sizes are real pixels, and WrapStyle 2 so our own
    two-line breaks are kept. (libass's default 384x288 canvas made subtitles wrap to 3 lines: FAILURES.md F01.)"""
    portrait = height > width
    size = int((width / 22 if portrait else height / 20) * scale)
    margin_v = int(height * (0.17 if portrait else 0.08))  # inside the safe area, above platform UI
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,"
        f"1,2,1,2,20,20,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{t.replace(chr(10), chr(92) + 'N')}"
             for a, b, t in cues]
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- end card

def end_card_drawtext(sb, width, height, start_s):
    """drawtext filters for the end card, split on '·' and wrapped to fit the frame."""
    chars_per_line = max(16, int(width / 26))
    lines = []
    for part in sb["end_card"]["text"].split("·"):
        lines += wrap(part.strip(), chars_per_line).split("\n")
    fs = int(min(width, height) / 22)
    gap = int(fs * 1.45)
    y0 = f"(h-{gap * len(lines)})/2"
    return [
        f"drawtext={drawtext_font()}text='{drawtext_escape(ln)}':fontcolor=white:fontsize={fs}:"
        f"x=(w-text_w)/2:y={y0}+{i * gap}:enable='gte(t,{start_s})'"
        for i, ln in enumerate(lines)
    ]


# ---------------------------------------------------------------- audio

def build_voice_track(sb, out_path, narr_dir=None):
    """Each shot's narration, delayed by LEAD_IN_S and padded/trimmed to the shot's planned duration."""
    _, _, film_s = shot_timeline(sb)
    inputs, filters = [], []
    for i, s in enumerate(sb["shots"]):
        inputs += ["-i", (narr_dir or NARR_DIR) / f"{s['id']}.wav"]
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,"
                       f"adelay={int(LEAD_IN_S * 1000)},apad,atrim=0:{s['duration_s']}[v{i}]")
    n = len(sb["shots"])
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,apad,atrim=0:{film_s}[voice]")
    run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[voice]", "-ar", "48000", out_path])
    return out_path


def placeholder_music(film_s, out_path):
    """A quiet two-note drone (C and G), used for the radio cut and as the fallback score."""
    expr = ("0.08*sin(2*PI*130.81*t)+0.05*sin(2*PI*196*t)+0.03*sin(2*PI*261.6*t)"
            "*(0.6+0.4*sin(2*PI*0.1*t))")
    run_ffmpeg(["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={film_s}",
                "-af", f"afade=t=in:d=2,afade=t=out:st={max(0, film_s - 3)}:d=3", "-ac", "2", out_path])
    return out_path


def loudnorm_two_pass(in_path, out_path, target_i, target_tp, lra=11):
    """EBU R128 normalisation in two passes: measure, then apply with the measured values (more accurate)."""
    stderr = run_ffmpeg(["-i", in_path, "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={lra}:print_format=json",
                         "-f", "null", "-"], capture_stderr=True)
    m = json.loads(re.findall(r"\{[^{}]*\}", stderr, re.S)[-1])
    af = (f"loudnorm=I={target_i}:TP={target_tp}:LRA={lra}:measured_I={m['input_i']}:"
          f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true")
    run_ffmpeg(["-i", in_path, "-af", af, "-ar", "48000", out_path])
    return {"measured_input_i": float(m["input_i"]), "measured_input_tp": float(m["input_tp"])}


def mix(sb, voice_path, music_path, out_path, work_dir):
    """Music ducked under the voice (sidechaincompress, settings from the storyboard), then two-pass loudnorm."""
    _, _, film_s = shot_timeline(sb)
    dk = sb["music"].get("ducking", {})
    duck = (f"threshold={dk.get('threshold', 0.02)}:ratio={dk.get('ratio', 6)}:"
            f"attack={dk.get('attack_ms', 300)}:release={dk.get('release_ms', 1500)}")
    pre = Path(work_dir) / "mix_prenorm.wav"
    fc = (f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{film_s},volume=0.6[m];"
          f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][sc];"
          f"[m][sc]sidechaincompress={duck}[ducked];"
          f"[vo][ducked]amix=inputs=2:duration=first:normalize=0[mix]")
    run_ffmpeg(["-i", voice_path, "-i", music_path, "-filter_complex", fc, "-map", "[mix]",
                "-ar", "48000", "-t", f"{film_s}", pre])
    return loudnorm_two_pass(pre, out_path, sb["export"]["loudness_lufs"], sb["export"]["true_peak_db"])
