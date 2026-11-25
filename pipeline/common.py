"""Shared helpers for every stage: config, storyboard I/O, run logging, caching and retries."""
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
STORYBOARD = ROOT / "storyboard.json"
RUNS_LOG = ROOT / "runs.jsonl"
RUN_ID = os.environ.get("RUN_ID") or (
    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])


# ---------------------------------------------------------------- config and secrets

def load_env(path=ROOT / ".env"):
    """Minimal .env loader so secrets stay out of code and out of git."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return value


# ---------------------------------------------------------------- storyboard

def load_storyboard(path=STORYBOARD):
    """Validate first, then load. Every stage calls this, so a broken storyboard never reaches a model."""
    result = subprocess.run([sys.executable, str(ROOT / "pipeline" / "validate.py"), str(path)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("Storyboard failed validation:\n" + result.stdout + result.stderr)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_storyboard(sb, path=STORYBOARD):
    """Write back (used only by approval commands such as choosing a reference or a music candidate)."""
    Path(path).write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def shot_timeline(sb):
    """Start time of every shot, total length of shots, and film length including the end card."""
    starts, t = [], 0.0
    for s in sb["shots"]:
        starts.append(t)
        t += s["duration_s"]
    return starts, t, t + sb["end_card"]["duration_s"]


# ---------------------------------------------------------------- caching

def input_hash(obj):
    """Stable hash of everything that affects an output. Same inputs -> same hash -> cache hit."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def file_hash(path):
    """Content hash of an upstream file, so a downstream cache invalidates when it changes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def meta_path(output_path):
    output_path = Path(output_path)
    return output_path.with_suffix(output_path.suffix + ".meta.json")


def cache_valid(output_path, h):
    """An output is reusable if it exists and its sidecar records the same input hash."""
    output_path, meta = Path(output_path), meta_path(output_path)
    if not output_path.exists() or not meta.exists():
        return False
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("input_hash") == h
    except json.JSONDecodeError:
        return False


def write_cache_meta(output_path, h, inputs, **extra):
    record = {"input_hash": h, "inputs": inputs, "written_at": datetime.now(timezone.utc).isoformat(), **extra}
    meta_path(output_path).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- logging

def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def log_call(stage, model, provider, params, latency_s, status, shot_id=None, seed=None,
             cost_usd=0.0, gpu_minutes=None, output=None, error=None, attempt=1, extra=None):
    """Append one line per model call to runs.jsonl. Cache hits are not model calls and are not logged."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "stage": stage,
        "shot_id": shot_id,
        "model": model,
        "provider": provider,
        "params": params,
        "seed": seed,
        "latency_s": round(float(latency_s), 3),
        "gpu_minutes": gpu_minutes,
        "cost_usd": cost_usd,
        "status": status,
        "attempt": attempt,
        "output": rel(output) if output else None,
        "error": error,
    }
    if extra:
        record.update(extra)
    with open(RUNS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- retries

def is_rate_limit(exc):
    text = str(exc).lower()
    return any(k in text for k in ("429", "resource_exhausted", "quota", "rate limit", "too many requests"))


def with_retries(fn, *, stage, model, provider, params, shot_id=None, seed=None,
                 max_attempts=3, base_delay=4.0):
    """Call fn(); log every attempt; back off exponentially, four times longer on rate limits.

    fn must return (result, output_path_or_None, extra_dict_or_None).
    """
    for attempt in range(1, max_attempts + 1):
        start = time.monotonic()
        try:
            result, output, extra = fn()
            log_call(stage, model, provider, params, time.monotonic() - start, "ok",
                     shot_id=shot_id, seed=seed, output=output, attempt=attempt, extra=extra)
            return result
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised after the last attempt
            log_call(stage, model, provider, params, time.monotonic() - start, "error",
                     shot_id=shot_id, seed=seed, error=f"{type(exc).__name__}: {exc}"[:500], attempt=attempt)
            if attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1)) * (4 if is_rate_limit(exc) else 1) + random.uniform(0, 1)
            print(f"  [{shot_id or stage}] attempt {attempt} failed ({str(exc)[:120]}); retrying in {delay:.0f}s")
            time.sleep(delay)


# ---------------------------------------------------------------- ffmpeg

def ffprobe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def run_ffmpeg(args, capture_stderr=False):
    cmd = ["ffmpeg", "-hide_banner", "-y", *map(str, args)]
    if not capture_stderr:
        cmd[2:2] = ["-loglevel", "error"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + result.stderr[-3000:])
    return result.stderr
