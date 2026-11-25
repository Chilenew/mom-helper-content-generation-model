# Managing every update on GitHub

## First-time publish (once)

1. Go to <https://github.com/new>. Repository name: **`mom-helper-content-generation-model`**. Visibility: **Public**. Do **not** add a README, .gitignore or licence (the repo already has them). Click **Create repository**.
2. On your machine, inside the unzipped folder (it already contains the git history):
   ```bash
   cd mom-helper-content-generation-model
   git config user.name  "Your Name"
   git config user.email "you@example.com"        # the email on your GitHub account
   git remote add origin https://github.com/<your-username>/mom-helper-content-generation-model.git
   git push -u origin main --tags
   ```
   When asked for a password, use a **Personal Access Token** (GitHub → Settings → Developer settings → Tokens), or run `gh auth login` first if you have the GitHub CLI.
3. Open the repo's **Actions** tab: the `ci` workflow should go green within a few minutes.
4. In `README.md`, replace `<your-username>` in the clone URL, commit and push.

## Everyday loop

```bash
git status                       # what changed?
git add -A                       # stage it (.env is ignored, so keys never get in)
git commit -m "feat(keyframes): approve mother reference c2"
git push
```

Commit **small and often**: after every stage run, every experiment, every failure. The commit history is part of the evidence of how you worked.

### Commit message prefixes

| Prefix | Use for | Example |
|---|---|---|
| `feat(stage):` | new pipeline code or behaviour | `feat(music): crossfade between cues` |
| `fix(stage):` | a bug fix | `fix(assemble): hold last frame when clip is short` |
| `story:` | storyboard changes (bump `version`) | `story: v0.2.0 slower s06 after radio-cut test` |
| `gen(stage):` | new generated outputs | `gen(keyframes): s01-s11 with mother ref` |
| `exp:` | an experiment entry | `exp: E03 reference vs text-only consistency` |
| `docs:` | DESIGN / FAILURES / COSTS / README edits | `docs: user test 1 notes` |

### Tag each checkpoint

```bash
git tag -a v0.1-radio-cut  -m "Phase 1: radio cut + user test 1"
git tag -a v0.2-rough-cut  -m "Phase 2: picture for every shot + chosen score"
git tag -a v1.0-final      -m "Phase 3: final film, both aspect ratios"
git push --tags
```

Tags let a reviewer (or you, in the interview) jump to exactly what existed at each checkpoint.

## Before every push: quick checks

```bash
make validate && make test       # storyboard valid, tests pass (CI runs the same)
git ls-files | grep -E '\.env$'  # must print nothing
```

## Large files

GitHub rejects files over 100 MB and warns above 50 MB. The 720p films are well under that. If a file grows too large, lower the CRF quality or keep it out of git (add it to `.gitignore`) and link to it instead.

## If a key was committed by mistake

1. **Revoke the key immediately** in Google AI Studio / Cloudflare, and create a new one.
2. Remove the file: `git rm --cached .env && git commit -m "remove secret"`. The old key still exists in history, which is why step 1 comes first.
3. Record it in `FAILURES.md`.
