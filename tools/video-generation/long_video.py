"""Resume a continuous Wan VACE scene in bounded, frame-conditioned segments."""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time

import video

MODEL_CONFIG = json.loads((video.HERE / "continuation-model.json").read_text(encoding="utf-8"))
MODEL = video.LOCAL / "models" / "wan2.1-vace-1.3b"


def save(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def probe(path):
    import imageio.v2 as imageio
    with imageio.get_reader(str(path)) as reader:
        metadata = reader.get_meta_data()
        return {"frames": reader.count_frames(), "fps": metadata["fps"],
                "width": metadata["size"][0], "height": metadata["size"][1]}


def read_project(root):
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8-sig"))
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    if plan.get("version") != 1 or state.get("version") != 1:
        raise ValueError("Unsupported project version.")
    for key in ("width", "height", "fps", "frames", "overlap", "steps", "seed"):
        if type(plan[key]) is not int:
            raise ValueError(f"{key} must be an integer.")
    if min(plan["width"], plan["height"]) < 128 or plan["width"] % 16 or plan["height"] % 16:
        raise ValueError("Dimensions must be at least 128 and divisible by 16.")
    if not 5 <= plan["frames"] <= 81 or (plan["frames"] - 1) % 4:
        raise ValueError("Each segment must have 5-81 frames with a frame count of 4*k+1.")
    if not 1 <= plan["overlap"] < plan["frames"] or (plan["overlap"] - 1) % 4:
        raise ValueError("Overlap must be 4*k+1 frames and shorter than a segment.")
    if plan["fps"] <= 0 or plan["steps"] <= 0 or not 0 <= plan["seed"] < 2**63:
        raise ValueError("FPS/steps must be positive and seed must be nonnegative and below 2**63.")
    if not math.isfinite(plan["seconds"]) or plan["seconds"] <= 0:
        raise ValueError("Target seconds must be finite and positive.")
    if not isinstance(plan["prompt"], str) or not plan["prompt"].strip():
        raise ValueError("Supply a nonempty scene prompt.")
    for key in ("guidance", "conditioning_scale"):
        if not math.isfinite(plan[key]) or plan[key] < 0:
            raise ValueError(f"{key} must be finite and nonnegative.")
    beats = plan.get("segment_prompts", {})
    if not isinstance(beats, dict) or any(not isinstance(v, str) for v in beats.values()):
        raise ValueError("segment_prompts must map segment indexes to descriptive text.")
    return plan, state


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Checkpoint path escapes the project.")
    return path


def recipe(plan, index, upstream):
    # Target duration is deliberately excluded: increasing it reuses every completed segment.
    return {
        **{key: plan[key] for key in ("prompt", "negative_prompt", "width", "height", "fps",
                                    "frames", "overlap", "steps", "guidance", "conditioning_scale", "seed")},
        "beat": plan.get("segment_prompts", {}).get(str(index), ""),
        "model_revision": MODEL_CONFIG["revision"], "base_revision": video.CONFIG["revision"],
        "upstream_sha256": upstream,
    }


def valid_segments(root, plan, state):
    for index, item in enumerate(state["segments"]):
        path = safe_path(root, item["path"])
        if not path.is_file() or video.sha256(path) != item["sha256"]:
            raise ValueError(f"Segment {index} is missing or changed. Use run --retry-from {index}.")
        if item.get("source"):
            if any(item[key] != plan[key] for key in ("width", "height", "fps")):
                raise ValueError("Project dimensions/FPS no longer match the imported source.")
            continue
        upstream = state["segments"][index - 1]["sha256"] if index else None
        if item["recipe"] != fingerprint(recipe(plan, index, upstream)):
            return index
    return len(state["segments"])


def new_path(root, folder, stem):
    directory = root / folder
    directory.mkdir(exist_ok=True)
    number = 1
    while True:
        path = directory / f"{stem}-take-{number:03d}.mp4"
        if not path.exists() and not path.with_suffix(".json").exists():
            return path, number
        number += 1


def init(args):
    root = Path(args.project).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Choose a new or empty project folder.")
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        raise ValueError("Seconds must be finite and positive.")
    width, height, frames, steps = video.PRESETS[args.preset]
    source_info = probe(Path(args.source)) if args.source else None
    if source_info and (source_info["width"], source_info["height"], source_info["fps"]) != (width, height, 16):
        raise ValueError("Source dimensions/FPS must match the chosen preset (16 fps).")
    if source_info and source_info["frames"] < args.overlap:
        raise ValueError("Source clip is shorter than the requested overlap.")
    root.mkdir(parents=True, exist_ok=True)
    plan = {"version": 1, "title": args.title, "seconds": args.seconds,
            "prompt": args.prompt, "negative_prompt": video.NEGATIVE,
            "width": width, "height": height, "frames": frames, "steps": steps,
            "fps": 16, "overlap": args.overlap, "guidance": 5.0,
            "conditioning_scale": 1.0, "seed": args.seed, "segment_prompts": {}}
    state = {"version": 1, "segments": [], "history": [], "renders": []}
    if args.source:
        source = root / "source.mp4"
        shutil.copyfile(args.source, source)
        state["segments"].append({"path": "source.mp4", "source": True,
                                  "sha256": video.sha256(source), "append_from": 0, **source_info})
    save(root / "plan.json", plan)
    save(root / "state.json", state)
    read_project(root)
    print(f"Created {root / 'plan.json'}", flush=True)
    report(plan, state)


def load_pipeline():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    video.check_model()
    video.check_model(config=MODEL_CONFIG, model=MODEL)
    import torch
    from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanVACEPipeline, WanVACETransformer3DModel
    from transformers import AutoTokenizer, UMT5EncoderModel

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; use the project video Python environment.")
    print("Loading continuation model and shared local components once...", flush=True)
    common = {"local_files_only": True}
    text_encoder = UMT5EncoderModel.from_pretrained(
        video.MODEL / "text_encoder", torch_dtype=torch.bfloat16, use_safetensors=True, **common)
    transformer = WanVACETransformer3DModel.from_pretrained(
        MODEL / "transformer", torch_dtype=torch.bfloat16, use_safetensors=True, **common)
    vae = AutoencoderKLWan.from_pretrained(
        video.MODEL / "vae", torch_dtype=torch.float32, use_safetensors=True, **common)
    pipe = WanVACEPipeline(
        tokenizer=AutoTokenizer.from_pretrained(video.MODEL / "tokenizer", **common),
        text_encoder=text_encoder, transformer=transformer, vae=vae,
        scheduler=UniPCMultistepScheduler.from_pretrained(video.MODEL / "scheduler", flow_shift=5.0, **common))
    pipe.vae.enable_tiling()
    # Conditioning is VAE-encoded before denoising; offload the large text
    # encoder before that encoding stage rather than keeping both on the GPU.
    pipe.model_cpu_offload_seq = "text_encoder->vae->transformer"
    pipe.enable_model_cpu_offload()
    return pipe


def context_inputs(previous, overlap, frames, width, height):
    import imageio.v2 as imageio
    from PIL import Image
    with imageio.get_reader(str(previous)) as reader:
        tail = list(deque((Image.fromarray(frame) for frame in reader), maxlen=overlap))
    if len(tail) != overlap or any(frame.size != (width, height) for frame in tail):
        raise ValueError("Source context does not match the project dimensions/overlap.")
    blank = Image.new("RGB", (width, height), (127, 127, 127))
    black = Image.new("RGB", (width, height), (0, 0, 0))
    white = Image.new("RGB", (width, height), (255, 255, 255))
    return tail + [blank] * (frames - overlap), [black] * overlap + [white] * (frames - overlap)


def total_frames(state):
    return sum(item["frames"] - item["append_from"] for item in state["segments"])


def report(plan, state, valid_count=None):
    count = len(state["segments"]) if valid_count is None else valid_count
    available = sum(item["frames"] - item["append_from"] for item in state["segments"][:count])
    print(json.dumps({"completed_segments": count,
                      "stale_segments": len(state["segments"]) - count,
                      "available_seconds": round(available / plan["fps"], 3),
                      "target_seconds": plan["seconds"],
                      "target_reached": available >= max(1, round(plan["seconds"] * plan["fps"])),
                      "latest_video": state["renders"][-1]["path"] if state["renders"] else None}, indent=2))


def assemble(root, plan, state):
    import imageio.v2 as imageio
    if not state["segments"]:
        raise ValueError("No completed segments to assemble.")
    if valid_segments(root, plan, state) != len(state["segments"]):
        raise ValueError("Plan changed; run again to regenerate affected segments before assembly.")
    target = min(total_frames(state), max(1, round(plan["seconds"] * plan["fps"])))
    signature = fingerprint({"segments": [(s["sha256"], s["append_from"]) for s in state["segments"]],
                             "frames": target, "fps": plan["fps"]})
    if state["renders"]:
        latest = state["renders"][-1]
        path = safe_path(root, latest["path"])
        if latest["signature"] == signature and path.is_file() and video.sha256(path) == latest["sha256"]:
            print(f"Assembly unchanged: {path}", flush=True)
            return path
    output, _ = new_path(root, "renders", "scene")
    written = 0
    with imageio.get_writer(str(output), fps=plan["fps"], codec="libx264", quality=8,
                           macro_block_size=16, ffmpeg_log_level="error") as writer:
        for item in state["segments"]:
            with imageio.get_reader(str(safe_path(root, item["path"]))) as reader:
                for index, frame in enumerate(reader):
                    if index < item["append_from"]:
                        continue
                    if written == target:
                        break
                    writer.append_data(frame)
                    written += 1
            if written == target:
                break
    info = probe(output)
    if info["frames"] != target:
        raise RuntimeError("Assembled video has an unexpected frame count.")
    record = {"path": output.relative_to(root).as_posix(), "signature": signature,
              "sha256": video.sha256(output), "seconds": written / plan["fps"], **info,
              "segments": [dict(item) for item in state["segments"]],
              "continuation_model": MODEL_CONFIG, "plan": plan}
    save(output.with_suffix(".json"), record)
    state["renders"].append({k: record[k] for k in ("path", "signature", "sha256", "seconds")})
    save(root / "state.json", state)
    print(f"Saved continuous video: {output} ({record['seconds']:.2f}s)", flush=True)
    return output


def run(root, args, plan, state):
    if args.limit is not None and args.limit < 1:
        raise ValueError("Limit must be positive.")
    if args.retry_from is not None and not 0 <= args.retry_from < len(state["segments"]):
        raise ValueError("retry-from must name an existing segment index (starting at 0).")
    if args.retry_from == 0 and state["segments"][0].get("source"):
        raise ValueError("The imported source cannot be regenerated; start a new project to replace it.")
    keep = args.retry_from if args.retry_from is not None else valid_segments(root, plan, state)
    if keep < len(state["segments"]):
        state["history"].append({"time": time.time(), "segments": state["segments"][keep:]})
        state["segments"] = state["segments"][:keep]
        save(root / "state.json", state)
        print(f"Rebuilding from segment {keep}; previous takes are retained.", flush=True)
    target = max(1, round(plan["seconds"] * plan["fps"]))
    pipe, generated = None, 0
    while total_frames(state) < target and (args.limit is None or generated < args.limit):
        index = len(state["segments"])
        overlap = min(plan["overlap"], state["segments"][-1]["frames"]) if index else 0
        if overlap:
            overlap = (overlap - 1) // 4 * 4 + 1
        # Keep the proven temporal shape across iterations; trim only the
        # assembled movie, rather than changing the VAE's final input window.
        frames = plan["frames"]
        output, take = new_path(root, "segments", f"segment-{index:03d}")
        seed = (plan["seed"] + index * 1009 + (take - 1) * 1000003) % (2**63)
        upstream = state["segments"][-1]["sha256"] if index else None
        settings = recipe(plan, index, upstream)
        prompt = plan["prompt"] + (" " + settings["beat"] if settings["beat"] else "")
        conditioning = {}
        if index:
            inputs, masks = context_inputs(safe_path(root, state["segments"][-1]["path"]),
                                           overlap, frames, plan["width"], plan["height"])
            conditioning = {"video": inputs, "mask": masks}
        if pipe is None:
            pipe = load_pipeline()
        import torch
        from diffusers.utils import export_to_video
        torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        print(f"Segment {index}, take {take}: {frames} frames, {overlap} context frames, seed {seed}", flush=True)
        with torch.inference_mode():
            result = pipe(prompt=prompt, negative_prompt=plan["negative_prompt"],
                          width=plan["width"], height=plan["height"], num_frames=frames,
                          num_inference_steps=plan["steps"], guidance_scale=plan["guidance"],
                          conditioning_scale=plan["conditioning_scale"],
                          generator=torch.Generator(device="cpu").manual_seed(seed), **conditioning).frames[0]
        export_to_video(result, str(output), fps=plan["fps"])
        info = probe(output)
        if info != {"frames": frames, "fps": plan["fps"], "width": plan["width"], "height": plan["height"]}:
            raise RuntimeError("Generated segment dimensions/frame count/FPS do not match the plan.")
        record = {"path": output.relative_to(root).as_posix(), "recipe": fingerprint(settings),
                  "sha256": video.sha256(output), "seed": seed, "append_from": overlap,
                  "elapsed_seconds": round(time.monotonic() - started, 2),
                  "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                  "conditioning": "previous_clip_tail" if index else "text", **info}
        save(output.with_suffix(".json"), {**record, "settings": settings})
        state["segments"].append(record)
        save(root / "state.json", state)
        generated += 1
        print(f"Checkpoint saved: {total_frames(state) / plan['fps']:.2f}s available", flush=True)
    if state["segments"]:
        assemble(root, plan, state)
    report(plan, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dl = commands.add_parser("download", help="Download only the additional continuation weights")
    dl.add_argument("--workers", type=int, choices=range(1, 33), default=12, metavar="1-32")
    create = commands.add_parser("init", help="Create an editable continuous-scene plan")
    create.add_argument("--project", required=True)
    create.add_argument("--prompt", required=True)
    create.add_argument("--title", default="Rabbit Lands continuous scene")
    create.add_argument("--seconds", type=float, default=30)
    create.add_argument("--preset", choices=video.PRESETS, default="preview")
    create.add_argument("--overlap", type=int, default=13)
    create.add_argument("--seed", type=int, default=42)
    create.add_argument("--source", help="Optional existing MP4, copied into this project")
    for command in ("run", "assemble", "status"):
        sub = commands.add_parser(command)
        sub.add_argument("--project", required=True)
        if command == "run":
            sub.add_argument("--limit", type=int, help="Generate at most this many new segments, then save a preview")
            sub.add_argument("--retry-from", type=int, help="Regenerate this segment and dependent later segments; preserve old takes")
    args = parser.parse_args()
    try:
        if args.command == "download":
            video.download(args, config=MODEL_CONFIG, model=MODEL)
        elif args.command == "init":
            init(args)
        elif args.command == "status":
            # Checkpoints are atomically replaced, so progress can be inspected
            # while the GPU runner holds its mutation lock.
            root = Path(args.project).resolve()
            plan, state = read_project(root)
            report(plan, state, valid_segments(root, plan, state))
        else:
            from filelock import FileLock
            root = Path(args.project).resolve()
            with FileLock(str(root / ".runner.lock"), timeout=0):
                plan, state = read_project(root)
                if args.command == "run":
                    run(root, args, plan, state)
                elif args.command == "assemble":
                    assemble(root, plan, state)
        return 0
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
