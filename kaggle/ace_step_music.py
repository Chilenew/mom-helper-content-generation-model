"""ACE-Step 1.5 score candidates on Kaggle (GPU T4). Run in a notebook cell:
    !python /kaggle/input/<your-code-dataset>/ace_step_music.py

Inputs : the dataset made from outputs/music/kaggle_bundle.zip (jobs.json), attached to the notebook
Outputs: /kaggle/working/music_output/<cue>_c<k>.wav + kaggle_runs.jsonl, zipped to music_output.zip

Notebook settings: Accelerator = GPU T4 x2 (one GPU is used), Internet = On.
ACE-Step is installed from its GitHub repo at a pinned tag (ACESTEP_REF) so the run is reproducible.
On a 16 GB T4 the DiT handler runs with CPU offload. If the LM handler fails to load, set USE_LM=0:
the cues already give bpm and key, so the LM's metadata reasoning ("thinking") is switched off anyway.
"""
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = "/kaggle/working/ACE-Step-1.5"
OUT = "/kaggle/working/music_output"
REF = os.environ.get("ACESTEP_REF", "v0.1.6")


def setup():
    if not os.path.exists(ROOT):
        subprocess.run(["git", "clone", "--depth", "1", "--branch", REF,
                        "https://github.com/ace-step/ACE-Step-1.5.git", ROOT], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-e", ROOT], check=True)
    sys.path.insert(0, ROOT)
    os.environ.setdefault("ACESTEP_PROJECT_ROOT", ROOT)


def main():
    setup()
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music

    hits = glob.glob("/kaggle/input/**/jobs.json", recursive=True)
    if not hits:
        sys.exit("jobs.json not found: attach the dataset made from outputs/music/kaggle_bundle.zip")
    spec = json.load(open(hits[0]))
    mparams = spec.get("params", {})
    os.makedirs(OUT, exist_ok=True)

    t0 = time.time()
    dit = AceStepHandler()
    dit.initialize_service(project_root=ROOT, config_path=spec["model"], device="cuda", offload_to_cpu=True)
    llm = None
    if os.environ.get("USE_LM", "1") == "1":
        try:
            from acestep.llm_inference import LLMHandler
            llm = LLMHandler()
            llm.initialize(checkpoint_dir=os.path.join(ROOT, "checkpoints"),
                           lm_model_path=mparams.get("lm_model", "acestep-5Hz-lm-0.6B"),
                           backend=os.environ.get("LM_BACKEND", "pt"), device="cuda")
        except Exception as e:  # noqa: BLE001
            print(f"LM handler not loaded ({e}); continuing without it")
            llm = None
    print(f"ACE-Step ready in {time.time() - t0:.0f}s; {len(spec['jobs'])} job(s)", flush=True)

    log = open(os.path.join(OUT, "kaggle_runs.jsonl"), "a")
    for job in spec["jobs"]:
        dst = os.path.join(OUT, job["out_name"] + ".wav")
        if os.path.exists(dst):
            continue
        params = GenerationParams(caption=job["caption"], instrumental=job["instrumental"], bpm=job["bpm"],
                                  keyscale=job["keyscale"], duration=job["duration"], seed=job["seed"],
                                  inference_steps=mparams.get("inference_steps", 8),
                                  thinking=mparams.get("thinking", False))
        config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[job["seed"]], audio_format="wav")
        start = time.time()
        status, error = "ok", None
        try:
            result = generate_music(dit, llm, params, config, save_dir=OUT)
            if not result.success:
                raise RuntimeError(result.error)
            os.replace(result.audios[0]["path"], dst)
        except Exception as e:  # noqa: BLE001
            status, error = "error", f"{type(e).__name__}: {e}"[:500]
        latency = time.time() - start
        log.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(), "run_id": f"kaggle-{datetime.now():%Y%m%dT%H%M}",
            "stage": "music", "shot_id": job["cue_id"], "model": f"ace-step-1.5/{spec['model']}",
            "provider": "kaggle_t4x2",
            "params": {"candidate": job["candidate"], "bpm": job["bpm"], "key": job["keyscale"],
                       "duration": job["duration"], "steps": mparams.get("inference_steps", 8), "gpu": "T4",
                       "lm": llm is not None},
            "seed": job["seed"], "latency_s": round(latency, 3), "gpu_minutes": round(latency / 60, 2),
            "cost_usd": 0.0, "status": status, "attempt": 1,
            "output": f"outputs/music/candidates/{job['out_name']}.wav" if status == "ok" else None,
            "error": error}) + "\n")
        log.flush()
        print(f"{job['out_name']}: {status} in {latency:.0f}s {error or ''}", flush=True)
    log.close()
    subprocess.run(["zip", "-qrj", "/kaggle/working/music_output.zip", OUT], check=True)
    print("done: download /kaggle/working/music_output.zip, then:\n"
          "  python pipeline/music.py import --from music_output.zip")


if __name__ == "__main__":
    main()
