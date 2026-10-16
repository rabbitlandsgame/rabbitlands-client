"""Generate masked VACE ambience while preserving the approved login paintings."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import video
import long_video

ASSETS = video.ROOT / "godot-client" / "assets" / "ui" / "start_screen"
SCENE_CONFIG = json.loads((video.HERE / "login-scenes.json").read_text(encoding="utf-8"))
SCENES = SCENE_CONFIG["scenes"]
DEFAULT_WORK = video.LOCAL / "login-motion-v1"
NEGATIVE = ("camera movement, camera pan, zoom, shake, cuts, time lapse, bending buildings, "
            "warped architecture, changing mountains, new objects, people walking, extra towers, "
            "text, logos, subtitles, rapid flashing, lightning, changing colors, day night transition")


def masks(scene, size):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    width, height = size
    alpha = np.zeros((height, width), dtype=np.float32)
    binary = Image.new("L", size, 0)
    for region in scene["regions"]:
        shape = Image.new("L", size, 0)
        points = [(round(x * (width - 1)), round(y * (height - 1))) for x, y in region["points"]]
        ImageDraw.Draw(shape).polygon(points, fill=255)
        ImageDraw.Draw(binary).polygon(points, fill=255)
        feathered = np.asarray(shape.filter(ImageFilter.GaussianBlur(max(2, width / 150))), dtype=np.float32) / 255
        alpha = np.maximum(alpha, feathered * region["gain"])
    return binary.convert("RGB"), alpha


def settings(scene, args):
    return {"scene": scene, "source_sha256": video.sha256(ASSETS / (scene["file"] + "-poster.jpg")),
            "width": args.width, "height": args.height, "frames": args.frames, "steps": args.steps,
            "guidance": 5.0, "conditioning_scale": 1.0, "negative_prompt": NEGATIVE,
            "model": long_video.MODEL_CONFIG, "base_model": video.CONFIG["revision"]}


def paths(work, scene, recipe):
    stem = scene["file"] + "-" + long_video.fingerprint(recipe)[:12]
    return work / "raw" / (stem + ".mp4"), work / "raw" / (stem + ".json")


def generate(args, selected):
    import numpy as np
    from PIL import Image
    work = Path(args.work).resolve()
    (work / "raw").mkdir(parents=True, exist_ok=True)
    pipe = None
    for scene in selected:
        recipe = settings(scene, args)
        output, sidecar = paths(work, scene, recipe)
        if output.exists() and sidecar.exists():
            existing = json.loads(sidecar.read_text(encoding="utf-8"))
            if existing["recipe"] == recipe and video.sha256(output) == existing["sha256"]:
                print(f"Already generated: {scene['id']}", flush=True)
                continue
            raise ValueError(f"Changed candidate: {output}; choose a new work folder or seed.")
        if output.exists() or sidecar.exists():
            raise ValueError(f"Incomplete candidate exists: {output}; preserve it and choose a new work folder.")
        poster = Image.open(ASSETS / (scene["file"] + "-poster.jpg")).convert("RGB")
        poster = poster.resize((args.width, args.height), Image.Resampling.LANCZOS)
        region_mask, _ = masks(scene, poster.size)
        known = np.asarray(poster)
        hidden = np.array(known, copy=True)
        hidden[np.asarray(region_mask)[:, :, 0] > 127] = 127
        missing = Image.fromarray(hidden)
        black = Image.new("RGB", poster.size, (0, 0, 0))
        # Original art is known at both ends, and outside motion regions at every frame.
        inputs = [poster] + [missing] * (args.frames - 2) + [poster]
        input_masks = [black] + [region_mask] * (args.frames - 2) + [black]
        if pipe is None:
            pipe = long_video.load_pipeline()
        import torch
        from diffusers.utils import export_to_video
        torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        print(f"Animating {scene['id']}: {args.width}x{args.height}, {args.frames} frames, {args.steps} steps", flush=True)
        with torch.inference_mode():
            frames = pipe(prompt=scene["prompt"], negative_prompt=NEGATIVE, video=inputs, mask=input_masks,
                          width=args.width, height=args.height, num_frames=args.frames,
                          num_inference_steps=args.steps, guidance_scale=5.0, conditioning_scale=1.0,
                          generator=torch.Generator(device="cpu").manual_seed(scene["seed"])).frames[0]
        export_to_video(frames, str(output), fps=16, quality=9)
        info = long_video.probe(output)
        if info["frames"] != args.frames or (info["width"], info["height"]) != poster.size:
            raise RuntimeError(f"Invalid generated video for {scene['id']}: {info}")
        long_video.save(sidecar, {"recipe": recipe, "sha256": video.sha256(output), **info,
                                 "elapsed_seconds": round(time.monotonic() - started, 2),
                                 "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                                 "torch": torch.__version__, "diffusers": importlib.metadata.version("diffusers")})
        print(f"Candidate checkpoint saved: {output}", flush=True)


def circular_frames(frames, overlap):
    import numpy as np
    if overlap < 2 or 2 * overlap >= len(frames):
        raise ValueError("Loop overlap must be at least 2 and less than half the frame count.")
    result = [frame.astype(np.float32) for frame in frames[overlap:-overlap]]
    for index in range(overlap):
        weight = (index + 1) / (overlap + 1)
        weight = weight * weight * (3 - 2 * weight)
        result.append(frames[-overlap + index].astype(np.float32) * (1 - weight)
                      + frames[index].astype(np.float32) * weight)
    return np.stack(result)


def probe_runtime(path):
    import imageio_ffmpeg
    # ImageIO's high-level FFmpeg plugin rejects the .ogv suffix even though
    # its bundled FFmpeg can decode Theora. Probe the runtime container directly.
    reader = imageio_ffmpeg.read_frames(str(path))
    try:
        metadata = next(reader)
    finally:
        reader.close()
    # Theora's identification header occupies the first Ogg page. Read its
    # nominal rate: FFmpeg reports "tbr" here, which ImageIO does not parse.
    with path.open("rb") as stream:
        page = stream.read(27)
        if page[:4] != b"OggS":
            raise ValueError(f"Not an Ogg runtime video: {path}")
        sizes = stream.read(page[26])
        header = stream.read(sum(sizes))
    if header[:7] != b"\x80theora":
        raise ValueError(f"Not a Theora runtime video: {path}")
    numerator = int.from_bytes(header[22:26], "big")
    denominator = int.from_bytes(header[26:30], "big")
    if numerator <= 0 or denominator <= 0:
        raise ValueError(f"Invalid Theora frame rate: {path}")
    decoded, _ = imageio_ffmpeg.count_frames_and_secs(str(path))
    # Low-motion Theora may hold the preceding picture for a display slot.
    # Count presentation slots at the stream's own rate, including those holds.
    # https://wiki.xiph.org/Notes_on_testing_theora#Frame_drops
    process = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-map", "0:v:0", "-vf", f"fps={numerator}/{denominator}", "-f", "null", "-",
        "-progress", "pipe:1", "-nostats"], capture_output=True, text=True, check=True)
    progress = dict(line.split("=", 1) for line in process.stdout.splitlines() if "=" in line)
    count = int(progress["frame"])
    seconds = int(progress["out_time_us"]) / 1e6
    if not 0 < decoded <= count or seconds <= 0:
        raise ValueError(f"Invalid Theora presentation timeline: {path}")
    return {"frames": count, "decoded_frames": decoded, "held_frame_slots": count - decoded,
            "fps": numerator / denominator, "duration_seconds": seconds,
            "width": metadata["size"][0], "height": metadata["size"][1]}


def export(args, selected):
    import imageio.v2 as imageio
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image
    work = Path(args.work).resolve()
    exports = work / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    for scene in selected:
        recipe = settings(scene, args)
        raw, sidecar = paths(work, scene, recipe)
        receipt = json.loads(sidecar.read_text(encoding="utf-8"))
        if video.sha256(raw) != receipt["sha256"]:
            raise ValueError(f"Candidate checksum changed: {raw}")
        with imageio.get_reader(str(raw)) as reader:
            frames = [np.asarray(frame) for frame in reader]
        loop = circular_frames(frames, args.loop_overlap)
        poster = Image.open(ASSETS / (scene["file"] + "-poster.jpg")).convert("RGB")
        base = np.asarray(poster, dtype=np.float32)
        _, alpha = masks(scene, poster.size)
        strength = SCENE_CONFIG.get("export", {}).get(scene["id"], {}).get("motion_strength", 1.0)
        if not 0 < strength <= 3:
            raise ValueError("Export motion strength must be positive and at most 3.")
        alpha *= strength
        mean = Image.fromarray(np.uint8(np.clip(loop.mean(axis=0), 0, 255))).resize(poster.size, Image.Resampling.BICUBIC)
        mean = np.asarray(mean, dtype=np.float32)
        output = exports / (scene["file"] + ".mp4")
        count = round(args.seconds * args.fps)
        first, last, sample = None, None, None
        with imageio.get_writer(str(output), fps=args.fps, codec="libx264", quality=8,
                               macro_block_size=1, ffmpeg_log_level="error") as writer:
            for index in range(count):
                position = index / count * len(loop)
                left = int(position)
                fraction = position - left
                motion_frame = loop[left] * (1 - fraction) + loop[(left + 1) % len(loop)] * fraction
                current = Image.fromarray(np.uint8(np.clip(motion_frame, 0, 255))).resize(poster.size, Image.Resampling.BICUBIC)
                # Transfer the model's changing detail, keeping the original high-resolution
                # painting, mean palette, architecture, and unmasked foreground intact.
                difference = np.clip(np.asarray(current, dtype=np.float32) - mean, -48, 48)
                result = np.uint8(np.clip(base + difference * alpha[:, :, None], 0, 255))
                writer.append_data(result)
                if index == 0:
                    first = result
                if index == count // 2:
                    sample = result
                last = result
        ogv = exports / (scene["file"] + ".ogv")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(output), "-an", "-c:v", "libtheora", "-q:v", "7", "-pix_fmt", "yuv420p",
                        "-r", str(args.fps), str(ogv)], check=True)
        info = probe_runtime(ogv)
        if info["frames"] != count or info["fps"] != args.fps or (info["width"], info["height"]) != poster.size:
            raise RuntimeError(f"Export does not match its target: {info}")
        long_video.save(exports / (scene["file"] + ".json"), {
            "scene": scene["id"], "recipe": recipe, "raw_sha256": receipt["sha256"],
            "ogv_sha256": video.sha256(ogv), "mp4_sha256": video.sha256(output), **info,
            "seconds": count / args.fps, "bytes": ogv.stat().st_size,
            "loop_overlap_frames": args.loop_overlap,
            "motion_strength": strength,
            "loop_seam_mean_pixel_change": float(np.mean(np.abs(first.astype(float) - last.astype(float)))),
            "half_cycle_mean_pixel_change": float(np.mean(np.abs(first.astype(float) - sample.astype(float)))),
            "unchanged_fraction": float(np.mean(alpha < 0.001)),
        })
        print(f"Exported {scene['id']}: {info}, {ogv.stat().st_size / 1e6:.2f} MB", flush=True)


def install(args, selected):
    work = Path(args.work).resolve()
    backups = work / "previous"
    backups.mkdir(parents=True, exist_ok=True)
    for scene in selected:
        filename = scene["file"] + ".ogv"
        candidate = work / "exports" / filename
        receipt = json.loads((work / "exports" / (scene["file"] + ".json")).read_text(encoding="utf-8"))
        if video.sha256(candidate) != receipt["ogv_sha256"]:
            raise ValueError(f"Export changed: {candidate}")
        destination = ASSETS / filename
        if not (backups / filename).exists():
            shutil.copy2(destination, backups / filename)
        shutil.copy2(candidate, destination)
        print(f"Installed {scene['id']}", flush=True)
    manifest_path = ASSETS / "motion-generation.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"version": 1, "scenes": {}}
    for scene in selected:
        manifest["scenes"][scene["id"]] = json.loads((work / "exports" / (scene["file"] + ".json")).read_text())
    long_video.save(manifest_path, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "export", "install"))
    parser.add_argument("--work", default=str(DEFAULT_WORK))
    parser.add_argument("--scenes", nargs="+", choices=[s["id"] for s in SCENES])
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=368)
    parser.add_argument("--frames", type=int, default=81)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--seconds", type=float, default=12)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--loop-overlap", type=int, default=8)
    args = parser.parse_args()
    if args.width < 128 or args.height < 128 or args.width % 16 or args.height % 16:
        parser.error("Model dimensions must be at least 128 and divisible by 16.")
    if args.frames < 5 or args.frames > 81 or (args.frames - 1) % 4 or args.steps < 1:
        parser.error("Use 5-81 frames with a count of 4*k+1 and positive steps.")
    if args.seconds <= 0 or args.fps <= 0:
        parser.error("Output duration and FPS must be positive.")
    selected = [s for s in SCENES if args.scenes is None or s["id"] in args.scenes]
    try:
        {"generate": generate, "export": export, "install": install}[args.command](args, selected)
        return 0
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
