"""Lining pose sheet comparison (actor LODs C4), the companion of
actor_lining_pose_sheet.gd: counts the pixels that change between the
rebuilt (plain index buffer) and masked captures of every pose and view, and
the rebuild's own change (plain vs rebuilt), on the pixels that held still
between the repeated captures (rebuilt / rebuilt2, plain / plain2; the RL
head's eyes move by themselves), writes summary.json / summary.md and
composes one contact sheet per configuration (rows: poses; per view the
masked capture with changed pixels outlined in red) plus the fade pair.

    python actor_lining_pose_sheet.py <sheet folder>

Exit status 1 when any pose or view changes (the masks must be lossless) or
the rebuild is not pixel-identical to the worn mesh. The half-faded corpse
pass is reported, not judged: hidden faces may show through a translucent
shell there.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def load(path: Path) -> np.ndarray | None:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16) if path.is_file() else None


def changed(a: np.ndarray | None, b: np.ndarray | None) -> np.ndarray | None:
    if a is None or b is None or a.shape != b.shape:
        return None
    return np.abs(a - b).max(axis=2) > 0


def outlined(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = image.astype(np.uint8).copy()
    if mask.any():
        grown = mask.copy()
        for axis in (0, 1):
            for shift in (-2, -1, 1, 2):
                grown |= np.roll(mask, shift, axis=axis)
        out[grown] = (255, 0, 0)
    return out


def compose(rows: list[list[np.ndarray]], gap: int = 4) -> Image.Image:
    height = max(cell.shape[0] for row in rows for cell in row)
    width = max(cell.shape[1] for row in rows for cell in row)
    columns = max(len(row) for row in rows)
    sheet = np.full((len(rows) * (height + gap) + gap, columns * (width + gap) + gap, 3), 24, np.uint8)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            y, x = gap + r * (height + gap), gap + c * (width + gap)
            sheet[y:y + cell.shape[0], x:x + cell.shape[1]] = cell
    return Image.fromarray(sheet)


def main(argv: list[str]) -> int:
    folder = Path(argv[1])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    summary = {"configs": {}, "changed_views": 0, "rebuild_noise_views": 0, "views": 0}
    lines = ["| config | masked linings | views | changed views | changed px (max in a view) | rebuild-changed views | "
             "self-moving px (not judged) | fade changed px |",
             "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |"]
    for label, config in manifest["configs"].items():
        masked = [lining for lining in config["linings"] if lining.get("status") == "masked"]
        row = {"masked_linings": [f"{item['lining']} (-{item.get('stats', {}).get('removed_triangles', '?')})"
                                  for item in masked],
               "views": 0, "changed_views": 0, "changed_pixels": 0, "max_pixels": 0, "noise_views": 0, "fade": {}}
        sheet_rows = []
        for pose in manifest["poses"]:
            cells = []
            for view in manifest["views"]:
                stem = folder / label / f"{pose}__{view}__"
                plain = load(Path(f"{stem}plain.png"))
                rebuilt = load(Path(f"{stem}rebuilt.png"))
                masked_image = load(Path(f"{stem}masked.png"))
                rebuilt2 = load(Path(f"{stem}rebuilt2.png"))
                plain2 = load(Path(f"{stem}plain2.png"))
                if rebuilt is None or masked_image is None or rebuilt2 is None or plain2 is None:
                    if plain is not None:
                        cells.append(plain.astype(np.uint8))
                    continue
                row["views"] += 1
                moving = changed(rebuilt, rebuilt2) | changed(plain, plain2)
                row["moving_pixels"] = row.get("moving_pixels", 0) + int(moving.sum())
                difference = changed(rebuilt, masked_image) & changed(rebuilt2, masked_image) & ~moving
                noise = changed(plain, rebuilt) & ~moving
                count = int(difference.sum()) if difference is not None else -1
                row["changed_pixels"] += max(count, 0)
                row["max_pixels"] = max(row["max_pixels"], count)
                row["changed_views"] += int(count != 0)
                row["noise_views"] += int(bool(noise.any()))
                cells.append(outlined(masked_image, difference if difference is not None else np.zeros(masked_image.shape[:2], bool)))
            if cells:
                sheet_rows.append(cells)
        for view in manifest["views"]:
            rebuilt = load(folder / label / f"fade__{view}__rebuilt.png")
            masked_image = load(folder / label / f"fade__{view}__masked.png")
            rebuilt2 = load(folder / label / f"fade__{view}__rebuilt2.png")
            difference = changed(rebuilt, masked_image)
            if difference is not None and rebuilt2 is not None:
                difference &= changed(rebuilt2, masked_image) & ~changed(rebuilt, rebuilt2)
                row["fade"][view] = int(difference.sum())
                sheet_rows.append([rebuilt.astype(np.uint8), outlined(masked_image, difference)])
        if sheet_rows:
            compose(sheet_rows).save(folder / f"sheet__{label}.png")
        summary["configs"][label] = row
        summary["views"] += row["views"]
        summary["changed_views"] += row["changed_views"]
        summary["rebuild_noise_views"] += row["noise_views"]
        lines.append(f"| {label} | {', '.join(row['masked_linings']) or 'none'} | {row['views']} | {row['changed_views']} | "
                     f"{row['changed_pixels']} ({row['max_pixels']}) | {row['noise_views']} | {row.get('moving_pixels', 0)} | "
                     f"{', '.join(f'{k} {v}' for k, v in row['fade'].items()) or '-'} |")
    (folder / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    (folder / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if summary["changed_views"] or summary["rebuild_noise_views"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
