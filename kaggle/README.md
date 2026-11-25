# Running the GPU stages on Kaggle

Wan 2.2 (moving shots) and ACE-Step 1.5 (music) need a GPU. Kaggle gives about 30 free GPU hours a week once your account is phone-verified. Everything else runs on your own machine.

## One-time setup

1. Verify your phone number in Kaggle → Settings, so GPU and Internet are available in notebooks.
2. Create a dataset called `mom-helper-code` and upload `kaggle/wan22_i2v.py` and `kaggle/ace_step_music.py`. Re-upload it as a new version when these scripts change.

## Moving shots (Wan 2.2 TI2V-5B)

```bash
python pipeline/shots.py export          # -> outputs/shots/kaggle_bundle.zip (only shots that changed)
```

1. Kaggle → Datasets → New Dataset: upload `kaggle_bundle.zip` as `mom-helper-shots` (or add a new version).
2. New Notebook → Settings: **Accelerator = GPU T4 x2**, **Internet = On**. Add inputs `mom-helper-shots` and `mom-helper-code`.
3. In a cell, run:
   ```python
   !python /kaggle/input/mom-helper-code/wan22_i2v.py
   ```
   Optional settings go before the command, for example `!MAX_MINUTES=240 STEPS=20 python ...`.
4. When it finishes, download `/kaggle/working/wan_output.zip` from the Output panel.
5. Back on your machine:
   ```bash
   python pipeline/shots.py import --from ~/Downloads/wan_output.zip
   make film
   ```

The first run downloads about 34 GB of model weights. Draft at 512×512 (the storyboard default) and raise `width`/`height` in `storyboard.json` only for the final shots. A 5-second clip on a T4 takes several minutes or more; measure it and record it in `COSTS.md`.

## Music (ACE-Step 1.5)

```bash
python pipeline/music.py export          # -> outputs/music/kaggle_bundle.zip (2 cues x 3 candidates)
```

Upload it as `mom-helper-music`, attach it with `mom-helper-code` to a GPU notebook, and run:

```python
!python /kaggle/input/mom-helper-code/ace_step_music.py
```

Then on your machine:

```bash
python pipeline/music.py import --from ~/Downloads/music_output.zip
# listen to outputs/music/candidates/*.wav, then:
python pipeline/music.py choose 1 --reason "softest texture, the voice stays clear"
make film
```

## When something fails

- **CUDA out of memory:** lower `width`/`height` or `num_frames` in `storyboard.json`, export again, and log it in `FAILURES.md`.
- **Session times out:** run the cell again. Finished clips are skipped.
- **Quota runs out:** `make film` still works. Shots without a Wan clip get a Ken Burns pan/zoom, and the film uses the placeholder score until you choose a candidate.
- **A model or package has moved:** record what replaced it in `FAILURES.md`. The brief asks for exactly this.
