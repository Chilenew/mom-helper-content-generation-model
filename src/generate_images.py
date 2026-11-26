"""Stage: images (keyframes). Character reference sheets first, then one keyframe per shot conditioned on them.

Model: FLUX.2 [klein] 4B on Cloudflare Workers AI (multipart form; up to 4 reference images, each < 512x512).
FLUX.1 schnell (JSON body, no references) also works as a fallback: set KEYFRAME_MODEL in .env.

Usage:
  python src/generate_images.py refs --candidates 4             # reference sheet candidates per character
  python src/generate_images.py approve mother 2                # pick candidate 2 as mother's golden reference
  python src/generate_images.py shots                           # one keyframe per shot (cached)
  python src/generate_images.py shots --only s06 --force        # regenerate one keyframe
  python src/generate_images.py shots --dry-run                 # placeholder frames, no API calls
  python src/generate_images.py sheet                           # contact sheet of all keyframes for review

Reads:  characters[], shots[].keyframe, style_block, models.keyframes
Writes: assets/references/<character>_c<k>.png, assets/images/<shot>.png (+ .meta.json),
        assets/images/contact_sheet.jpg
"""
import argparse
import base64
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (IMAGES_DIR, REFERENCES_DIR, ROOT, cache_valid, file_hash, input_hash, load_env, load_storyboard,  # noqa: E402
                    drawtext_font, rel, require_env, run_ffmpeg, save_storyboard, with_retries, write_cache_meta)

OUT_DIR = IMAGES_DIR
REF_DIR = REFERENCES_DIR
MAX_REFS = 4


# ---------------------------------------------------------------- Cloudflare client

def _multipart(fields, files):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (filename, data, ctype) in files.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def cloudflare_image(model, prompt, width, height, seed, ref_images=()):
    """Return JPEG/PNG bytes. FLUX.2 models take multipart; FLUX.1 schnell takes JSON."""
    acct, token = require_env("CF_ACCOUNT_ID"), require_env("CF_API_TOKEN")
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}"
    if "flux-2" in model:
        fields = {"prompt": prompt, "width": width, "height": height, "seed": seed}
        files = {f"input_image_{i}": (p.name, p.read_bytes(), "image/jpeg") for i, p in enumerate(ref_images)}
        body, ctype = _multipart(fields, files)
    else:
        body = json.dumps({"prompt": prompt, "steps": 4, "seed": seed}).encode()
        ctype = "application/json"
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from e
    image = (data.get("result") or {}).get("image")
    if not image:
        raise RuntimeError(f"no image in response: {str(data)[:300]}")
    return base64.b64decode(image)


def placeholder_image(out, label, width, height, hue):
    """Dry-run frame: a coloured gradient with the shot id, so the full pipeline runs without keys."""
    run_ffmpeg(["-f", "lavfi", "-i", f"gradients=s={width}x{height}:c0=0x{hue}:c1=0x101010:x0=0:y0=0:x1={width}:y1={height}:d=1",
                "-frames:v", "1", "-vf",
                f"drawtext={drawtext_font()}text='{label}':fontcolor=white:fontsize={width // 10}:x=(w-text_w)/2:y=(h-text_h)/2", out])


# ---------------------------------------------------------------- prompts

def character_block(sb, ids):
    chars = {c["id"]: c for c in sb["characters"]}
    return " ".join(f"{chars[i]['name'].split(' (')[0]}: {chars[i]['description']}." for i in ids)


def shot_prompt(sb, shot, ref_chars):
    parts = [shot["keyframe"]["prompt"] + "."]
    if shot["characters"]:
        parts.append(character_block(sb, shot["characters"]))
    if ref_chars:
        mapping = ", ".join(f"image {i} shows {c['name'].split(' (')[0]}" for i, c in enumerate(ref_chars))
        parts.append(f"Reference images: {mapping}; keep each person's face, clothing and colours identical. "
                     "Each person appears exactly once; one single scene, not a collage or reference sheet.")
    parts.append(f"Style: {sb['style_block']}.")
    parts.append("No text, letters or writing anywhere in the image.")
    return " ".join(parts)


def reference_characters(sb, shot, model):
    """Characters in this shot with an approved golden reference on disk (only FLUX.2 accepts references)."""
    if "flux-2" not in model:
        return []
    chars = {c["id"]: c for c in sb["characters"]}
    return [chars[c] for c in shot["characters"]
            if chars[c].get("reference_image") and (ROOT / chars[c]["reference_image"]).exists()][:MAX_REFS]


def reference_prompt(sb, character):
    return f"{character['reference_prompt']}. Style: {sb['style_block']}. No text or labels."


def small_ref(path):
    """References must be under 512x512 for Workers AI: make a 448px JPEG copy."""
    out = REF_DIR / "small" / (Path(path).stem + "_448.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.stat().st_mtime < Path(path).stat().st_mtime:
        run_ffmpeg(["-i", path, "-vf", "scale=448:448:force_original_aspect_ratio=decrease", "-q:v", "3", out])
    return out


# ---------------------------------------------------------------- commands

def model_settings(sb):
    m = sb["models"]["keyframes"]
    name = os.environ.get("KEYFRAME_MODEL") or m["name"]
    p = m.get("params", {})
    return name, m["provider"], p.get("width", 1024), p.get("height", 1024)


def cmd_refs(args, sb):
    model, provider, w, h = model_settings(sb)
    REF_DIR.mkdir(parents=True, exist_ok=True)
    for c in sb["characters"]:
        if args.only and c["id"] not in args.only:
            continue
        for k in range(args.candidates):
            seed = c["seed"] + k
            prompt = reference_prompt(sb, c)
            out = REF_DIR / f"{c['id']}_c{k}.png"
            inputs = {"model": model, "prompt": prompt, "seed": seed, "w": w, "h": h, "dry": args.dry_run}
            hsh = input_hash(inputs)
            if not args.force and cache_valid(out, hsh):
                continue
            if args.dry_run:
                placeholder_image(out, f"{c['id']} c{k}", w, h, "5a3e2b")
            else:
                def call(out=out, prompt=prompt, seed=seed):
                    out.write_bytes(cloudflare_image(model, prompt, w, h, seed))
                    return None, out, None
                with_retries(call, stage="keyframes_ref", model=model, provider=provider,
                             params={"w": w, "h": h, "character": c["id"]}, shot_id=c["id"], seed=seed)
            write_cache_meta(out, hsh, inputs)
            print(f"  {rel(out)}")
    print("Now look at the candidates and approve one per character: "
          "python src/generate_images.py approve <character> <k>")


def cmd_approve(args, sb):
    src = REF_DIR / f"{args.character}_c{args.candidate}.png"
    if not src.exists():
        sys.exit(f"{rel(src)} does not exist; run `generate_images.py refs` first")
    dst = REF_DIR / f"{args.character}.png"
    shutil.copyfile(src, dst)
    for c in sb["characters"]:
        if c["id"] == args.character:
            c["reference_image"] = rel(dst)
    save_storyboard(sb)
    print(f"{args.character}: golden reference = {rel(dst)} (storyboard updated). "
          "Every keyframe with this character will now be regenerated against it.")


def cmd_shots(args, sb):
    model, provider, w, h = model_settings(sb)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = cached = 0
    for idx, shot in enumerate(sb["shots"]):
        sid = shot["id"]
        if args.only and sid not in args.only:
            continue
        ref_chars = reference_characters(sb, shot, model)
        refs = [small_ref(ROOT / c["reference_image"]) for c in ref_chars]
        prompt = shot_prompt(sb, shot, ref_chars)
        seed = shot["keyframe"]["seed"]
        out = OUT_DIR / f"{sid}.png"
        inputs = {"model": model, "prompt": prompt, "seed": seed, "w": w, "h": h,
                  "refs": [file_hash(r) for r in refs], "dry": args.dry_run}
        hsh = input_hash(inputs)
        if not args.force and cache_valid(out, hsh):
            cached += 1
            continue
        if args.dry_run:
            placeholder_image(out, sid, w, h, ["6b4f2a", "2f5d3a", "7a5a1e", "3b4a6b"][idx % 4])
        else:
            def call(out=out, prompt=prompt, seed=seed, refs=refs):
                out.write_bytes(cloudflare_image(model, prompt, w, h, seed, refs))
                return None, out, {"n_refs": len(refs)}
            with_retries(call, stage="keyframes", model=model, provider=provider,
                         params={"w": w, "h": h, "n_refs": len(refs)}, shot_id=sid, seed=seed)
        write_cache_meta(out, hsh, inputs)
        made += 1
        print(f"  {sid}: generated")
    print(f"keyframes: {made} generated, {cached} cached")
    if made:
        cmd_sheet(args, sb)
        print("Check faces and hands on every keyframe before spending GPU time animating it.")


def cmd_sheet(args, sb):
    frames = [OUT_DIR / f"{s['id']}.png" for s in sb["shots"] if (OUT_DIR / f"{s['id']}.png").exists()]
    if not frames:
        return
    cols = 4
    rows = (len(frames) + cols - 1) // cols
    inputs = []
    for f in frames:
        inputs += ["-i", f]
    fc = "".join(f"[{i}:v]scale=320:320,drawtext={drawtext_font()}text='{f.stem}':fontcolor=white:fontsize=24:x=8:y=8[t{i}];"
                 for i, f in enumerate(frames))
    pad = cols * rows - len(frames)
    for j in range(pad):
        fc += f"color=c=black:s=320x320:d=1[p{j}];"
    labels = "".join(f"[t{i}]" for i in range(len(frames))) + "".join(f"[p{j}]" for j in range(pad))
    layout = "|".join(f"{(i % cols) * 320}_{(i // cols) * 320}" for i in range(cols * rows))
    fc += f"{labels}xstack=inputs={cols * rows}:layout={layout}[out]"
    run_ffmpeg([*inputs, "-filter_complex", fc, "-map", "[out]", "-frames:v", "1", "-q:v", "3",
                OUT_DIR / "contact_sheet.jpg"])
    print(f"  contact sheet: {rel(OUT_DIR / 'contact_sheet.jpg')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("refs")
    r.add_argument("--candidates", type=int, default=4)
    r.add_argument("--only", nargs="*")
    r.add_argument("--force", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    a = sub.add_parser("approve")
    a.add_argument("character")
    a.add_argument("candidate", type=int)
    s = sub.add_parser("shots")
    s.add_argument("--only", nargs="*")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("sheet")
    args = ap.parse_args()
    if args.cmd is None:  # default: shots
        args = ap.parse_args(["shots", *sys.argv[1:]])

    load_env()
    sb = load_storyboard()
    {"refs": cmd_refs, "approve": cmd_approve, "shots": cmd_shots, "sheet": cmd_sheet}[args.cmd](args, sb)


if __name__ == "__main__":
    main()
