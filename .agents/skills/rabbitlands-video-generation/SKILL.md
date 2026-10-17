---
name: rabbitlands-video-generation
description: Generate Rabbit Lands videos, extend a continuous scene, or animate approved login artwork using local Wan 2.1 and VACE open weights. Use for silent concept videos, login ambience, and visual motion studies, not gameplay recording or rig animation export.
---

# Rabbit Lands video generation

Use the project helper at `C:\rabbitlands\rabbitlands-client\tools\video-generation\video.py` and its Python environment at `C:\rabbitlands\rabbitlands-client\.local\video-generation\venv\Scripts\python.exe`. Locate the client checkout and use its corresponding paths if the project has moved.

Short clips use **Wan2.1-T2V-1.3B-Diffusers**, pinned in `tools/video-generation/model.json`. Continuous scene extension uses **Wan2.1-VACE-1.3B**, pinned in `continuation-model.json`, sharing the existing text encoder, tokenizer, and VAE. Both have Apache-2.0 weights. These helpers generate silent video and do not export skeletons or game animation clips.

## Generate a clip

Run from the client checkout in PowerShell:

```powershell
$VideoPython = '.\.local\video-generation\venv\Scripts\python.exe'
& $VideoPython tools\video-generation\video.py doctor
& $VideoPython tools\video-generation\video.py generate --preset preview --seed 42 --prompt 'A small white rabbit hops once through a mossy fantasy forest clearing. Warm dawn light, gently moving ferns, fixed wide camera, stylized game cinematic.'
```

Default output is an ignored, timestamped MP4 under `.local/video-generation/outputs/`, with a JSON sidecar recording prompt, model revision, seed, settings, and elapsed time. Use `--output` for a particular destination; existing MP4s and sidecars are protected from overwrite. `--prompt-file` accepts a UTF-8 file and avoids shell quoting problems for long prompts.

| Preset | Resolution | Frames / playback | Steps | Use |
| --- | --- | --- | --- | --- |
| draft | 512 x 288 | 33 / 2.06 seconds | 16 | Fast composition check |
| preview | 512 x 288 | 49 / 3.06 seconds | 24 | Default motion study |
| standard | 832 x 480 | 81 / 5.06 seconds | 40 | Better finished clip |

Playback is 16 fps. Draft and preview trade quality for speed; 480p is the model's intended resolution. Adjust `--width`, `--height`, `--frames`, `--steps`, `--fps`, `--guidance`, or `--negative-prompt` when the request benefits. Dimensions must be divisible by 16; frame counts must be `4*k+1`. Increasing fps alone changes playback speed; it does not add motion frames. Keep the same seed when comparing prompts, while recognizing that results can change across hardware and runtime versions.

Describe the visible subject, one short action, setting, lighting, style, and camera movement in English. Preserve Eloria lore and use Rabbit Lands for product identity. For logos, readable captions, or precise UI, generate the background footage and compose those elements separately. View representative frames for subject fidelity, deformation, flicker, and framing before presenting a clip as finished. Link the MP4 and mention its duration and resolution.

## Longer continuous scenes

Use `tools/video-generation/long_video.py` for the user's preferred continuous-scene workflow. It conditions each new segment on the preceding clip's trailing frames, retains the existing footage, removes the duplicated conditioning prefix, and appends newly generated frames. It checkpoints each completed segment, reuses the model within a batch, and resumes without regenerating completed work.

Read [references/continuous-video.md](references/continuous-video.md) for creating a duration-based plan, extending an existing clip, reviewing seams, retrying a segment and its dependents, and increasing the target duration. Start with a small batch to inspect continuity, then continue toward the requested duration. Appearance and motion can still drift over many iterations; inspect the joins and use targeted retries when needed.

## Login-screen ambience

For the existing six login paintings, read [references/login-ambience.md](references/login-ambience.md). `tools/video-generation/login_motion.py` uses masked VACE generation, retains the original detailed artwork, and exports looping Godot-compatible video. Scene prompts, seeds, and motion regions live in `login-scenes.json`. Review a candidate before installing it over a runtime asset.

## Runtime and recovery

This setup uses CUDA, bfloat16 weights, a float32 VAE, tiled decoding, and CPU offload on a 16 GB RTX 5080 Laptop GPU. Allow several minutes for a 480p clip; system memory pressure can increase loading time. If memory is exhausted, reduce resolution/frame count or use `draft`; do not silently replace this with a paid service.

Model weights, caches, runtime, clips, and download receipts stay in the Git-ignored `.local/video-generation/` tree. Generation is offline and does not send prompts anywhere. Only explicit setup/download commands access PyTorch, PyPI, and Hugging Face. Keep those artifacts out of Git and do not use migration data as inputs.

If the runtime or weights are missing, run `tools/video-generation/setup.ps1` (Python 3.13 is the validated interpreter). It installs pinned dependencies and resumes the official model download, then checks all weight SHA-256 hashes. A download is approximately 28.9 GB plus the runtime. Run `video.py doctor --verify` to recheck integrity. See [references/model.md](references/model.md) for source and license references.
