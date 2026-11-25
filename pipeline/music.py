"""Stage: music. ACE-Step 1.5 runs on a Kaggle GPU; candidate choice and the final score are built here.

Flow:
  1. python pipeline/music.py export          -> outputs/music/kaggle_bundle.zip (jobs.json: cues x candidates)
     Upload as a Kaggle dataset, run kaggle/ace_step_music.py, download its output.
  2. python pipeline/music.py import --from ~/Downloads/music_output
  3. Listen to outputs/music/candidates/<cue>_c<k>.wav under the radio cut, then
     python pipeline/music.py choose 1 --reason "quietest texture, voice stays clear"
  4. python pipeline/music.py build           -> outputs/music/score.wav (default command)
     Each cue placed at its shot's start time with crossfades. Without candidates it falls back to the
     placeholder drone, so the film still assembles.

Reads:  music.cues, music.candidates, music.chosen_candidate, shot timing
Writes: outputs/music/candidates/*.wav, outputs/music/score.wav (+ .meta.json)
"""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (OUTPUTS, RUNS_LOG, cache_valid, file_hash, input_hash, load_storyboard, rel,  # noqa: E402
                    run_ffmpeg, save_storyboard, shot_timeline, write_cache_meta)
from media import placeholder_music  # noqa: E402

OUT_DIR = OUTPUTS / "music"
CAND_DIR = OUT_DIR / "candidates"
XFADE_S = 1.5
TAIL_S = 3.0


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


def cmd_export(args, sb):
    bundle = OUT_DIR / "kaggle_bundle"
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
    zpath = OUT_DIR / "kaggle_bundle.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(bundle / "jobs.json", "jobs.json")
    print(f"music: {len(jobs)} job(s) -> {rel(zpath)}. Run kaggle/ace_step_music.py with it attached.")


def cmd_import(args, sb):
    src = Path(args.from_dir).expanduser()
    if src.suffix == ".zip":
        tmp = OUT_DIR / "_import"
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
        seen = set(RUNS_LOG.read_text(encoding="utf-8").splitlines()) if RUNS_LOG.exists() else set()
        with open(RUNS_LOG, "a", encoding="utf-8") as fh:
            for line in log.read_text(encoding="utf-8").splitlines():
                if line.strip() and line not in seen:
                    fh.write(line + "\n")
                    appended += 1
    print(f"music: imported {n} candidate(s) to {rel(CAND_DIR)}, appended {appended} log line(s)")


def cmd_choose(args, sb):
    missing = [c["id"] for c in sb["music"]["cues"] if not (CAND_DIR / f"{c['id']}_c{args.candidate}.wav").exists()]
    if missing:
        sys.exit(f"candidate {args.candidate} missing for cues {missing}")
    sb["music"]["chosen_candidate"] = args.candidate
    sb["music"]["chosen_reason"] = args.reason
    save_storyboard(sb)
    print(f"chosen candidate {args.candidate}: {args.reason}\nAdd this comparison to EXPERIMENTS.md.")


def cmd_build(args, sb):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _, _, film_s = shot_timeline(sb)
    out = OUT_DIR / "score.wav"
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("export")
    i = sub.add_parser("import")
    i.add_argument("--from", dest="from_dir", required=True)
    c = sub.add_parser("choose")
    c.add_argument("candidate", type=int)
    c.add_argument("--reason", required=True, help="why this one: write it down, the brief asks for it")
    sub.add_parser("build")
    args = ap.parse_args()
    sb = load_storyboard()
    {"export": cmd_export, "import": cmd_import, "choose": cmd_choose, "build": cmd_build,
     None: cmd_build}[args.cmd](args, sb)


if __name__ == "__main__":
    main()
