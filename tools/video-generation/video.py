"""Local, pinned Wan video generation for Rabbit Lands."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOCAL = ROOT / ".local" / "video-generation"
MODEL = LOCAL / "models" / "wan2.1-t2v-1.3b"
CONFIG = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
os.environ["HF_HOME"] = str(LOCAL / "cache" / "huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")

PRESETS = {
    "draft": (512, 288, 33, 16),
    "preview": (512, 288, 49, 24),
    "standard": (832, 480, 81, 40),
}
NEGATIVE = (
    "blurry, low quality, overexposed, subtitles, text, watermark, logo, "
    "deformed, disfigured, extra limbs, static image, flickering"
)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_model(full=False, config=CONFIG, model=MODEL):
    receipt_path = model / "download-receipt.json"
    if not receipt_path.exists():
        raise RuntimeError(f"Model is not installed at {model}. Run its download command first.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["repo_id"] != config["repo_id"] or receipt["revision"] != config["revision"]:
        raise RuntimeError("Installed model does not match model.json; rerun download.")
    for entry in receipt["files"]:
        path = model / entry["name"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise RuntimeError(f"Missing or incomplete model file: {entry['name']}")
        if full and entry.get("sha256") and sha256(path) != entry["sha256"]:
            raise RuntimeError(f"Checksum mismatch: {entry['name']}")
    return receipt


def download(_args, config=CONFIG, model=MODEL):
    from huggingface_hub import HfApi, hf_hub_url
    from download_ranges import download_file

    info = HfApi(token=False).model_info(
        config["repo_id"], revision=config["revision"], files_metadata=True
    )
    entries = []
    for item in info.siblings:
        if not any(fnmatch.fnmatchcase(item.rfilename, p) for p in config["allow_patterns"]):
            continue
        entries.append({"name": item.rfilename, "size": item.size,
                        "sha256": item.lfs.sha256 if item.lfs else None})
    print(f"Downloading {sum(e['size'] for e in entries) / 1e9:.2f} GB to {model}", flush=True)
    print("Each weight is checked against its official SHA-256 before installation completes.", flush=True)
    for entry in entries:
        path = model / entry["name"]
        was_present = path.is_file()
        url = hf_hub_url(config["repo_id"], entry["name"], revision=config["revision"])
        download_file(
            url, path, entry["size"], workers=_args.workers,
        )
        if entry["sha256"] and sha256(path) != entry["sha256"]:
            if was_present:
                print(f"Replacing corrupted local weight: {entry['name']}", flush=True)
                path.unlink()
                download_file(url, path, entry["size"], workers=_args.workers)
            if sha256(path) != entry["sha256"]:
                raise RuntimeError(f"Checksum mismatch: {entry['name']}; remove this file and rerun download.")
    write_json(model / "download-receipt.json", {
        "repo_id": config["repo_id"], "revision": config["revision"],
        "license": config["license"], "license_url": config["license_url"], "files": entries,
    })
    receipt = check_model(config=config, model=model)
    print(f"Verified {len(receipt['files'])} files. Model ready.", flush=True)


def doctor(args):
    import torch

    result = {
        "python": sys.version.split()[0], "torch": torch.__version__,
        "cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
        "model_path": str(MODEL), "repo_id": CONFIG["repo_id"], "revision": CONFIG["revision"],
    }
    if torch.cuda.is_available():
        result["gpu"] = torch.cuda.get_device_name(0)
        result["vram_gib"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 2)
        # Execute a kernel; detecting a GPU alone does not prove architecture compatibility.
        result["cuda_kernel_ok"] = (torch.ones(2, device="cuda") + 1).tolist() == [2.0, 2.0]
    for package in ("diffusers", "transformers", "accelerate", "imageio-ffmpeg"):
        result[package] = importlib.metadata.version(package)
    try:
        receipt = check_model(full=args.verify)
        result["model_ready"] = True
        result["model_bytes"] = sum(e["size"] for e in receipt["files"])
    except RuntimeError as error:
        result["model_ready"] = False
        result["model_error"] = str(error)
    print(json.dumps(result, indent=2))
    return 0 if result["cuda_available"] and result["model_ready"] else 1


def generate(args):
    # All inference uses local files; prompts are never sent to a service.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    check_model()
    width, height, frames, steps = PRESETS[args.preset]
    width = width if args.width is None else args.width
    height = height if args.height is None else args.height
    frames = frames if args.frames is None else args.frames
    steps = steps if args.steps is None else args.steps
    if width < 128 or height < 128 or width % 16 or height % 16:
        raise ValueError("Width and height must be at least 128 and divisible by 16.")
    if frames < 5 or (frames - 1) % 4 or steps < 1 or args.fps <= 0:
        raise ValueError("Frames must be 4*k+1 (at least 5), steps positive, and fps positive.")
    prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip() if args.prompt_file else args.prompt
    if not prompt or not prompt.strip():
        raise ValueError("Supply a non-empty --prompt or --prompt-file.")
    output = Path(args.output).resolve() if args.output else LOCAL / "outputs" / f"clip-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    if output.suffix.lower() != ".mp4":
        raise ValueError("Output must have an .mp4 extension.")
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError(f"Output already exists; choose a new filename: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    import torch
    from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanPipeline
    from diffusers.utils import export_to_video

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Use the project video-generation Python environment.")
    started = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    print("Loading local model (CPU offload enabled)...", flush=True)
    vae = AutoencoderKLWan.from_pretrained(
        MODEL, subfolder="vae", torch_dtype=torch.float32, local_files_only=True, use_safetensors=True
    )
    pipe = WanPipeline.from_pretrained(
        MODEL, vae=vae, torch_dtype=torch.bfloat16, local_files_only=True, use_safetensors=True
    )
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=5.0)
    pipe.vae.enable_tiling()
    pipe.enable_model_cpu_offload()
    print(f"Generating {frames} frames at {width}x{height}, {steps} steps...", flush=True)
    with torch.inference_mode():
        video = pipe(
            prompt=prompt, negative_prompt=args.negative_prompt, width=width, height=height,
            num_frames=frames, num_inference_steps=steps, guidance_scale=args.guidance,
            generator=torch.Generator(device="cpu").manual_seed(args.seed),
        ).frames[0]
    export_to_video(video, str(output), fps=args.fps)
    elapsed = round(time.monotonic() - started, 2)
    write_json(output.with_suffix(".json"), {
        "model": CONFIG["repo_id"], "revision": CONFIG["revision"], "license": CONFIG["license"],
        "prompt": prompt, "negative_prompt": args.negative_prompt, "seed": args.seed,
        "width": width, "height": height, "frames": len(video), "fps": args.fps,
        "duration_seconds": len(video) / args.fps, "steps": steps, "guidance": args.guidance,
        "flow_shift": 5.0, "elapsed_seconds": elapsed,
        "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
        "diffusers": importlib.metadata.version("diffusers"),
        "transformers": importlib.metadata.version("transformers"),
    })
    print(f"Saved {output} ({elapsed:.1f}s generation time)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download", help="Download and verify the pinned official model")
    fetch.add_argument("--workers", type=int, choices=range(1, 33), default=12, metavar="1-32")
    fetch.set_defaults(run=download)
    health = commands.add_parser("doctor", help="Check runtime, CUDA, and downloaded files")
    health.add_argument("--verify", action="store_true", help="Rehash all model weights")
    health.set_defaults(run=doctor)
    gen = commands.add_parser("generate", help="Generate a silent MP4 locally from text")
    prompts = gen.add_mutually_exclusive_group(required=True)
    prompts.add_argument("--prompt")
    prompts.add_argument("--prompt-file", help="UTF-8 prompt file")
    gen.add_argument("--preset", choices=PRESETS, default="preview")
    gen.add_argument("--output")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--width", type=int)
    gen.add_argument("--height", type=int)
    gen.add_argument("--frames", type=int)
    gen.add_argument("--steps", type=int)
    gen.add_argument("--fps", type=int, default=16)
    gen.add_argument("--guidance", type=float, default=6.0)
    gen.add_argument("--negative-prompt", default=NEGATIVE)
    gen.set_defaults(run=generate)
    args = parser.parse_args()
    try:
        return args.run(args) or 0
    except (RuntimeError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
