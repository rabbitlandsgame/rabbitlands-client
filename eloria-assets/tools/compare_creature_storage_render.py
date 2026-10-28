"""Compare hash-bound actual-Actor renders and preserve compact cycle previews."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def compare(job):
    folder = Path(job.get("render_directory", Path(job["output"]) / "actual-render"))
    capture = json.loads((folder / "render.json").read_text(encoding="utf-8"))
    samples = []
    for label in capture["frames"]:
        source = np.asarray(
            Image.open(folder / ("baseline-" + label + ".png")).convert("RGB"),
            dtype=np.int16,
        )
        candidate = np.asarray(
            Image.open(folder / ("candidate-" + label + ".png")).convert("RGB"),
            dtype=np.int16,
        )
        error = np.abs(source - candidate)
        border = np.concatenate(
            [
                source[:2].reshape(-1, 3),
                source[-2:].reshape(-1, 3),
                source[:, :2].reshape(-1, 3),
                source[:, -2:].reshape(-1, 3),
            ]
        )
        border_foreground = int((np.max(abs(border - source[0, 0]), axis=1) > 3).sum())
        samples.append(
            dict(
                label=label,
                different_pixels=int(np.any(error, axis=2).sum()),
                pixels_above_two_levels=int((error.max(2) > 2).sum()),
                mean_channel_error=float(error.mean()),
                maximum_channel_error=int(error.max()),
                border_foreground_pixels=border_foreground,
            )
        )
    report = dict(
        source_sha256=capture["placements"][0]["sha256"],
        candidate_sha256=capture["placements"][1]["sha256"],
        image_pairs=len(samples),
        width=int(source.shape[1]),
        height=int(source.shape[0]),
        different_image_pairs=sum(row["different_pixels"] > 0 for row in samples),
        maximum_different_pixels=max(row["different_pixels"] for row in samples),
        maximum_pixels_above_two_levels=max(
            row["pixels_above_two_levels"] for row in samples
        ),
        maximum_mean_channel_error=max(row["mean_channel_error"] for row in samples),
        maximum_channel_error=max(row["maximum_channel_error"] for row in samples),
        scope=capture["scope"],
        framing_passed=all(row["border_foreground_pixels"] == 0 for row in samples),
        clipped_frame_labels=[
            row["label"] for row in samples if row["border_foreground_pixels"] > 0
        ],
        maximum_border_foreground_pixels=max(
            row["border_foreground_pixels"] for row in samples
        ),
        samples=samples,
    )
    labels = [label for label in capture["frames"] if "frame-" not in label]
    chosen = [
        next(label for label in labels if label.startswith(prefix))
        for prefix in (
            "Walk-game-37",
            "Fly-side-37",
            "Fly-rear-79",
            "Sword_Attack-under-37",
        )
        if any(label.startswith(prefix) for label in labels)
    ]
    if not chosen:
        chosen = labels[:4]
    board = Image.new("RGB", (1024, 552 * len(chosen)), (22, 27, 33))
    draw = ImageDraw.Draw(board)
    for row, label in enumerate(chosen):
        for column, name in enumerate(("baseline", "candidate")):
            board.paste(
                Image.open(folder / (name + "-" + label + ".png")).resize((512, 512)),
                (column * 512, row * 552 + 40),
            )
            draw.text(
                (column * 512 + 12, row * 552 + 12),
                name.upper() + " | " + label,
                fill="white",
            )
    board.save(folder / "comparison.png")
    clips = sorted(
        {
            label.split("-game-frame-")[0]
            for label in capture["frames"]
            if "-game-frame-" in label
        }
    )
    for clip in clips:
        frames = []
        for label in capture["frames"]:
            if not label.startswith(clip + "-game-frame-"):
                continue
            frame = Image.new("RGB", (768, 414), (22, 27, 33))
            draw = ImageDraw.Draw(frame)
            for column, name in enumerate(("baseline", "candidate")):
                image = (
                    Image.open(folder / (name + "-" + label + ".png"))
                    .convert("RGB")
                    .resize((384, 384))
                )
                frame.paste(image, (column * 384, 30))
                draw.text(
                    (column * 384 + 10, 10), name.upper() + " | " + clip, fill="white"
                )
            frames.append(frame)
        frames[0].save(
            folder / (clip + "-comparison.webp"),
            save_all=True,
            append_images=frames[1:],
            duration=[
                round((i + 1) * 1000 / 24) - round(i * 1000 / 24)
                for i in range(len(frames))
            ],
            loop=0,
            lossless=True,
        )
    (folder / "pixel-comparison.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return {key: value for key, value in report.items() if key != "samples"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(compare(json.loads(args.job.read_text(encoding="utf-8"))), indent=2)
    )
