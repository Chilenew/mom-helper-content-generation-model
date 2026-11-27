"""Wan 2.2 TI2V-5B image-to-video on Kaggle (GPU T4 x2). Paste into a Kaggle notebook cell, or upload and run:
    !python /kaggle/input/<your-code-dataset>/wan22_i2v.py

Inputs : the dataset made from assets/video/kaggle_bundle.zip (jobs.json + keyframes/), attached to the notebook
Outputs: /kaggle/working/wan_output/<shot>.mp4 + <shot>.json + kaggle_runs.jsonl, zipped to wan_output.zip

Notebook settings: Accelerator = GPU T4 x2, Internet = On (to download the model, ~34 GB on first run).
Each of the two T4s takes every other job, so two clips render at once. Finished clips are skipped on re-run,
so a session that dies can be resumed. Set MAX_MINUTES to stop before your weekly quota is spent.

Faster option for the T4: set MODEL_ID=FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers and STEPS=4
(a distilled variant: compare it against the base model in EXPERIMENTS.md).
"""
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

OUT = "/kaggle/working/wan_output"
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "600"))


def find_jobs():
    hits = glob.glob("/kaggle/input/**/jobs.json", recursive=True)
    if not hits:
        sys.exit("jobs.json not found: attach the dataset made from assets/video/kaggle_bundle.zip")
    return hits[0]


def worker(gpu, n_workers):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    jobs_path = find_jobs()
    base = os.path.dirname(jobs_path)
    spec = json.load(open(jobs_path))
    model_id = os.environ.get("MODEL_ID", spec["model"])
    jobs = spec["jobs"][gpu::n_workers]
    os.makedirs(OUT, exist_ok=True)
    log_path = os.path.join(OUT, f"kaggle_runs_gpu{gpu}.jsonl")

    t0 = time.time()
    # The T4 has no fast bfloat16, so the transformer runs in float16; the VAE stays float32 for quality.
    vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(model_id, vae=vae, torch_dtype=torch.float16)
    pipe.enable_model_cpu_offload()  # 16 GB T4: keep only the active module on the GPU
    print(f"[gpu{gpu}] model loaded in {time.time() - t0:.0f}s, {len(jobs)} job(s)", flush=True)

    for job in jobs:
        sid = job["shot_id"]
        clip = os.path.join(OUT, f"{sid}.mp4")
        meta = os.path.join(OUT, f"{sid}.json")
        if os.path.exists(clip) and os.path.exists(meta) and json.load(open(meta))["input_hash"] == job["input_hash"]:
            print(f"[gpu{gpu}] {sid}: already done", flush=True)
            continue
        if (time.time() - t0) / 60 > MAX_MINUTES:
            print(f"[gpu{gpu}] stopping: MAX_MINUTES reached", flush=True)
            break
        w, h = job.get("width", 512), job.get("height", 512)
        steps = int(os.environ.get("STEPS", job.get("num_inference_steps", 30)))
        params = {"width": w, "height": h, "num_frames": job.get("num_frames", 121), "steps": steps,
                  "guidance_scale": job.get("guidance_scale", 5.0), "fps": job.get("fps", 24), "gpu": "T4"}
        image = load_image(os.path.join(base, job["keyframe"])).resize((w, h))
        start = time.time()
        status, error = "ok", None
        try:
            frames = pipe(image=image, prompt=job["prompt"], negative_prompt=job.get("negative_prompt", ""),
                          height=h, width=w, num_frames=params["num_frames"], num_inference_steps=steps,
                          guidance_scale=params["guidance_scale"],
                          generator=torch.Generator("cpu").manual_seed(job["seed"])).frames[0]
            export_to_video(frames, clip, fps=params["fps"])
            json.dump({"input_hash": job["input_hash"], "shot_id": sid}, open(meta, "w"))
        except Exception as e:  # noqa: BLE001 - logged; e.g. CUDA out of memory, then move on
            status, error = "error", f"{type(e).__name__}: {e}"[:500]
            torch.cuda.empty_cache()
        latency = time.time() - start
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "run_id": f"kaggle-{datetime.now():%Y%m%dT%H%M}",
               "stage": "shots", "shot_id": sid, "model": model_id, "provider": "kaggle_t4x2", "params": params,
               "seed": job["seed"], "latency_s": round(latency, 3), "gpu_minutes": round(latency / 60, 2),
               "cost_usd": 0.0, "status": status, "attempt": 1,
               "output": f"assets/video/{sid}.mp4" if status == "ok" else None, "error": error}
        with open(log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[gpu{gpu}] {sid}: {status} in {latency / 60:.1f} min {error or ''}", flush=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(int(sys.argv[2]), int(sys.argv[3]))
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "diffusers>=0.35", "transformers>=4.48",
                    "accelerate", "ftfy", "imageio", "imageio-ffmpeg"], check=True)
    import torch
    n = max(1, torch.cuda.device_count())
    print(f"{n} GPU(s) found", flush=True)
    procs = [subprocess.Popen([sys.executable, __file__, "--worker", str(g), str(n)]) for g in range(n)]
    for p in procs:
        p.wait()
    # Merge the per-GPU logs and zip everything for download.
    with open(os.path.join(OUT, "kaggle_runs.jsonl"), "w") as out:
        for f in sorted(glob.glob(os.path.join(OUT, "kaggle_runs_gpu*.jsonl"))):
            out.write(open(f).read())
    subprocess.run(["zip", "-qrj", "/kaggle/working/wan_output.zip", OUT], check=True)
    print("done: download /kaggle/working/wan_output.zip, then on your machine:\n"
          "  python src/generate_video.py import --from wan_output.zip")


if __name__ == "__main__":
    main()
