"""Stage: moving shots. Wan 2.2 image-to-video runs on a Kaggle GPU; everything else runs here.

Flow:
  1. python pipeline/shots.py export      -> outputs/shots/kaggle_bundle.zip (jobs.json + keyframes)
     Upload it as a Kaggle dataset, run kaggle/wan22_i2v.py in a GPU notebook, download its output zip.
  2. python pipeline/shots.py import --from ~/Downloads/wan_output
     -> copies clips whose input hash still matches, appends the Kaggle call log to runs.jsonl
  3. python pipeline/shots.py render      -> outputs/shots/manifest.json (default command)
     Uses the Wan clip where one exists; otherwise renders a Ken Burns pan/zoom over the keyframe,
     so the film can always be assembled even when the GPU quota runs out.

Only jobs whose inputs changed (keyframe file, motion prompt, seed, model params) are exported again.

Reads:  shots[].motion, outputs/keyframes/<shot>.png, models.shots
Writes: outputs/shots/<shot>.mp4 (Wan), outputs/shots/<shot>_kb.mp4 (Ken Burns), outputs/shots/manifest.json
"""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (OUTPUTS, RUNS_LOG, cache_valid, file_hash, input_hash, load_storyboard,  # noqa: E402
                    rel, run_ffmpeg, write_cache_meta)

KEY_DIR = OUTPUTS / "keyframes"
OUT_DIR = OUTPUTS / "shots"
BUNDLE_DIR = OUT_DIR / "kaggle_bundle"
KB_SIZE = 1080  # Ken Burns render size (square, cropped later to 9:16 and 16:9)
KB_CYCLE = ["zoom_in", "pan_right", "zoom_out", "pan_left"]  # varied fallback movement between shots


def wan_inputs(sb, shot):
    kf = KEY_DIR / f"{shot['id']}.png"
    m = sb["models"]["shots"]
    return {"model": m["name"], "params": m.get("params", {}), "keyframe": file_hash(kf),
            "prompt": shot["motion"]["prompt"], "seed": shot["motion"].get("seed")}


def kb_inputs(sb, shot, direction, amount):
    return {"keyframe": file_hash(KEY_DIR / f"{shot['id']}.png"), "direction": direction, "amount": amount,
            "duration": shot["duration_s"], "fps": sb["export"]["fps"], "size": KB_SIZE}


# ---------------------------------------------------------------- export / import (Kaggle)

def cmd_export(args, sb):
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    (BUNDLE_DIR / "keyframes").mkdir(parents=True)
    params = sb["models"]["shots"].get("params", {})
    jobs = []
    for shot in sb["shots"]:
        sid = shot["id"]
        if shot["motion"]["mode"] != "i2v" or (args.only and sid not in args.only):
            continue
        kf = KEY_DIR / f"{sid}.png"
        if not kf.exists():
            print(f"  {sid}: no keyframe yet, skipped")
            continue
        h = input_hash(wan_inputs(sb, shot))
        if not args.force and cache_valid(OUT_DIR / f"{sid}.mp4", h):
            continue
        shutil.copyfile(kf, BUNDLE_DIR / "keyframes" / kf.name)
        jobs.append({"shot_id": sid, "keyframe": f"keyframes/{kf.name}", "prompt": shot["motion"]["prompt"],
                     "seed": shot["motion"]["seed"], "input_hash": h, **params})
    if not jobs:
        print("shots: nothing to export, every i2v shot has an up-to-date clip")
        return
    (BUNDLE_DIR / "jobs.json").write_text(json.dumps({"model": sb["models"]["shots"]["name"], "jobs": jobs},
                                                     ensure_ascii=False, indent=2), encoding="utf-8")
    zpath = OUT_DIR / "kaggle_bundle.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in BUNDLE_DIR.rglob("*"):
            z.write(f, f.relative_to(BUNDLE_DIR))
    print(f"shots: {len(jobs)} job(s) -> {rel(zpath)}")
    print("Next: upload it as a Kaggle dataset, run kaggle/wan22_i2v.py on GPU T4 x2, download the output, "
          "then: python pipeline/shots.py import --from <folder>")


def cmd_import(args, sb):
    src = Path(args.from_dir).expanduser()
    if src.suffix == ".zip":
        tmp = OUT_DIR / "_import"
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    shots = {s["id"]: s for s in sb["shots"]}
    imported, stale = 0, []
    for clip in sorted(src.rglob("*.mp4")):
        sid = clip.stem
        if sid not in shots:
            continue
        meta_file = clip.with_suffix(".json")
        job_hash = json.loads(meta_file.read_text())["input_hash"] if meta_file.exists() else None
        h = input_hash(wan_inputs(sb, shots[sid]))
        if job_hash != h:
            stale.append(sid)
            continue
        dst = OUT_DIR / f"{sid}.mp4"
        shutil.copyfile(clip, dst)
        write_cache_meta(dst, h, wan_inputs(sb, shots[sid]), source="kaggle")
        imported += 1
    # The Kaggle script logs each call in the same format as runs.jsonl; append the lines we have not seen.
    log = next(src.rglob("kaggle_runs.jsonl"), None)
    appended = 0
    if log:
        seen = set(RUNS_LOG.read_text(encoding="utf-8").splitlines()) if RUNS_LOG.exists() else set()
        with open(RUNS_LOG, "a", encoding="utf-8") as f:
            for line in log.read_text(encoding="utf-8").splitlines():
                if line.strip() and line not in seen:
                    f.write(line + "\n")
                    appended += 1
    print(f"shots: imported {imported} clip(s), appended {appended} log line(s) to runs.jsonl")
    if stale:
        print(f"  skipped stale clips (keyframe or prompt changed since export): {', '.join(stale)}")


# ---------------------------------------------------------------- local render

def ken_burns(src, out, duration, fps, direction, amount):
    n = int(round(duration * fps))
    z_in = f"1+{amount}*on/{n}"
    z_out = f"1+{amount}-{amount}*on/{n}"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    moves = {
        "zoom_in": (z_in, cx, cy),
        "zoom_out": (z_out, cx, cy),
        "pan_right": (f"1+{amount}", f"(iw-iw/zoom)*on/{n}", cy),
        "pan_left": (f"1+{amount}", f"(iw-iw/zoom)*(1-on/{n})", cy),
        "pan_down": (f"1+{amount}", cx, f"(ih-ih/zoom)*on/{n}"),
        "pan_up": (f"1+{amount}", cx, f"(ih-ih/zoom)*(1-on/{n})"),
    }
    z, x, y = moves[direction]
    # Upscale first so the slow zoom does not jitter on integer pixel steps.
    vf = (f"scale={KB_SIZE * 4}:{KB_SIZE * 4}:force_original_aspect_ratio=increase,crop={KB_SIZE * 4}:{KB_SIZE * 4},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={KB_SIZE}x{KB_SIZE}:fps={fps},format=yuv420p")
    run_ffmpeg(["-loop", "1", "-i", src, "-vf", vf, "-frames:v", n, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", out])


def cmd_render(args, sb):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest, fallbacks = {}, []
    for idx, shot in enumerate(sb["shots"]):
        sid, mode = shot["id"], shot["motion"]["mode"]
        kf = KEY_DIR / f"{sid}.png"
        if not kf.exists():
            sys.exit(f"{sid}: missing keyframe {rel(kf)}. Run: python pipeline/keyframes.py shots")
        clip = OUT_DIR / f"{sid}.mp4"
        if mode == "i2v" and cache_valid(clip, input_hash(wan_inputs(sb, shot))):
            manifest[sid] = {"source": "wan", "path": rel(clip)}
            continue
        if mode == "i2v":
            fallbacks.append(sid)
        kb = shot["motion"].get("ken_burns", {})
        direction = kb.get("direction", KB_CYCLE[idx % len(KB_CYCLE)])
        amount = kb.get("amount", 0.10) if mode != "still" else 0.0
        out = OUT_DIR / f"{sid}_kb.mp4"
        inputs = kb_inputs(sb, shot, direction, amount)
        h = input_hash(inputs)
        if not cache_valid(out, h):
            ken_burns(kf, out, shot["duration_s"], sb["export"]["fps"], direction if amount else "zoom_in", amount)
            write_cache_meta(out, h, inputs)
        manifest[sid] = {"source": "ken_burns" if mode != "still" else "still", "path": rel(out),
                         "fallback_for_i2v": mode == "i2v"}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    n_wan = sum(1 for m in manifest.values() if m["source"] == "wan")
    print(f"shots: {n_wan} Wan clip(s), {len(manifest) - n_wan} Ken Burns/still -> {rel(OUT_DIR / 'manifest.json')}")
    if fallbacks:
        print(f"  Ken Burns fallback used for i2v shots without a clip yet: {', '.join(fallbacks)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("export")
    e.add_argument("--only", nargs="*")
    e.add_argument("--force", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("--from", dest="from_dir", required=True, help="folder or zip downloaded from Kaggle")
    sub.add_parser("render")
    args = ap.parse_args()
    sb = load_storyboard()
    {"export": cmd_export, "import": cmd_import, "render": cmd_render, None: cmd_render}[args.cmd](args, sb)


if __name__ == "__main__":
    main()
