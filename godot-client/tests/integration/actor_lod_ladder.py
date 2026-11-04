"""Companion of actor_lod_ladder.gd (actor LODs C5, wave-2 gate G5).

    python actor_lod_ladder.py gate <out>        # G5 verdict + tables -> <out>/gate.md, <out>/gate.json
    python actor_lod_ladder.py compose <out>     # owner strips -> <out>/strips/<subject>__<quality>.png
    python actor_lod_ladder.py clip <clip dir> [--keep-frames]   # zoom clip frames ->
                                                    # <clip dir>/../clip_<renderer>__<variant>.mp4

<out> is the RABBITLANDS_LADDER_OUT folder of one or more ladder runs: one
<renderer>__<variant>/manifest.json per run (variants named as the runs were:
"off" for RABBITLANDS_ACTOR_GEOMETRY=off, anything else for a cooked root).

Gate G5 (schedule 1.4: the Compatibility ladder is a go/no-go): GO when, in
every cooked variant,
  1. Compatibility selects what Forward+ selects: at every subject, quality
     and distance its primitives differ from the LOD rule's prediction for
     its own meshes by exactly what Forward+'s differ from theirs (the
     prediction takes each renderer's own content: the RL head is drawn on
     Forward+ and Mobile only, so totals differ at High by design);
  2. where both draw the same pieces, both draw the same primitives (within
     PARITY);
  3. Compatibility (and Forward+) draw no more than the plain parse at any
     distance and fewer at the farthest, for every subject and quality.
Measured-vs-predicted agreement and the cells from STEP_FROM_METRES where a
chain has not switched yet (a level held back by its error clamp) are
reported, not judged, as is Mobile against Forward+ where both ran. Exit 0
for GO, 1 for NO-GO, 2 when runs are missing.

`clip` needs Pillow, and imageio-ffmpeg (or ffmpeg on PATH) to encode.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PARITY = 0.01
STEP_FROM_METRES = 18.0
FORWARD = "forward_plus"
COMPATIBILITY = "gl_compatibility"
MOBILE = "mobile"
PLAIN = "off"
BUDGET_TRIANGLES = 25000
CELL = 256


def load_runs(out: Path) -> dict[tuple[str, str], dict]:
    runs = {}
    for manifest in sorted(out.glob("*__*/manifest.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("mode", "ladder") != "ladder":
            continue
        data["_folder"] = manifest.parent
        runs[(data["renderer"], data["variant"])] = data
    return runs


def cells(run: dict) -> dict[tuple[str, str, float], dict]:
    return {(row["subject"], row["quality"], float(row["distance"])): row for row in run["rows"]}


def relative(a: int, b: int) -> float:
    return abs(a - b) / max(1, max(a, b))


def gate(out: Path) -> int:
    runs = load_runs(out)
    if not runs:
        print(f"no ladder runs under {out}")
        return 2
    variants = sorted({variant for _, variant in runs if variant != PLAIN})
    report: dict = {"runs": sorted(f"{r}__{v}" for r, v in runs), "parity": PARITY,
                    "step_from_metres": STEP_FROM_METRES, "variants": {}}
    lines = ["# Actor LOD ladder: gate G5", "",
             f"Runs: {', '.join(report['runs'])}. Parity tolerance {PARITY:.0%}; steps judged from "
             f"{STEP_FROM_METRES:.0f} m.", ""]
    verdict = True
    missing = False
    for variant in variants:
        entry: dict = {}
        forward = runs.get((FORWARD, variant))
        compat = runs.get((COMPATIBILITY, variant))
        if forward is None or compat is None:
            missing = True
            entry["missing"] = [name for name, run in ((FORWARD, forward), (COMPATIBILITY, compat)) if run is None]
            report["variants"][variant] = entry
            continue
        f_cells, c_cells = cells(forward), cells(compat)
        keys = sorted(set(f_cells) & set(c_cells))
        residual_equal = [k for k in keys if f_cells[k]["primitives"] - f_cells[k]["predicted"]
                          == c_cells[k]["primitives"] - c_cells[k]["predicted"]]
        same_content = [k for k in keys if set(f_cells[k]["pieces"]) == set(c_cells[k]["pieces"])]
        parity = [relative(f_cells[k]["primitives"], c_cells[k]["primitives"]) for k in same_content]
        entry["cells"] = len(keys)
        entry["selection_equal"] = len(residual_equal)
        entry["selection_differs"] = [list(k) for k in keys if k not in residual_equal]
        entry["same_content_cells"] = len(same_content)
        entry["same_content_exact"] = sum(1 for value in parity if value == 0)
        entry["same_content_max"] = max(parity) if parity else None
        differs = set()
        for k in keys:
            if k in same_content:
                continue
            only_f = sorted(set(f_cells[k]["pieces"]) - set(c_cells[k]["pieces"]))
            only_c = sorted(set(c_cells[k]["pieces"]) - set(f_cells[k]["pieces"]))
            differs.add(f"{k[0]} {k[1]}: Forward+ only {only_f}, Compatibility only {only_c}")
        entry["content_differs"] = sorted(differs)
        predicted = {}
        for name, run in ((FORWARD, forward), (COMPATIBILITY, compat)):
            deviations = [relative(row["primitives"], row["predicted"]) for row in run["rows"]]
            predicted[name] = {"cells": len(deviations), "exact": sum(1 for d in deviations if d == 0),
                               "max": max(deviations) if deviations else None,
                               "differ": [[row["subject"], row["quality"], row["distance"], row["primitives"],
                                           row["predicted"]] for row in run["rows"]
                                          if row["primitives"] != row["predicted"]]}
        entry["predicted"] = predicted
        steps = {}
        steps_ok = True
        for name in (FORWARD, COMPATIBILITY):
            plain = runs.get((name, PLAIN))
            if plain is None:
                missing = True
                steps_ok = False
                continue
            cooked_cells, plain_cells = cells(runs[(name, variant)]), cells(plain)
            common = sorted(set(cooked_cells) & set(plain_cells))
            more = [list(k) for k in common if cooked_cells[k]["primitives"] > plain_cells[k]["primitives"]]
            farthest = {}
            for k in common:
                if k[2] >= farthest.get((k[0], k[1]), -1.0):
                    farthest[(k[0], k[1])] = k[2]
            not_fewer_far = [[subject, quality, d] for (subject, quality), d in farthest.items()
                             if cooked_cells[(subject, quality, d)]["primitives"]
                             >= plain_cells[(subject, quality, d)]["primitives"]]
            judged = [k for k in common if k[2] >= STEP_FROM_METRES]
            fewer = [k for k in judged if cooked_cells[k]["primitives"] < plain_cells[k]["primitives"]]
            ratios = [cooked_cells[k]["primitives"] / max(1, plain_cells[k]["primitives"]) for k in judged]
            steps[name] = {"cells": len(judged), "fewer": len(fewer), "more_anywhere": more,
                           "not_fewer_at_farthest": not_fewer_far,
                           "not_fewer": [list(k) for k in judged if k not in fewer],
                           "mean_ratio_from_step": sum(ratios) / len(ratios) if ratios else None}
            steps_ok = steps_ok and not more and not not_fewer_far and bool(common)
        entry["steps"] = steps
        ok = (bool(keys) and len(residual_equal) == len(keys)
              and (entry["same_content_max"] is None or entry["same_content_max"] <= PARITY) and steps_ok)
        entry["go"] = ok
        verdict = verdict and ok
        report["variants"][variant] = entry
        lines += [f"## Variant `{variant}`: {'GO' if ok else 'NO-GO'}", ""]
        lines.append(f"- LOD selection: Compatibility's primitives minus the rule's prediction equal Forward+'s in "
                     f"{len(residual_equal)} of {len(keys)} cells"
                     + (f" (differ: {entry['selection_differs']})" if entry["selection_differs"] else ""))
        lines.append(f"- Same pieces drawn in {len(same_content)} of {len(keys)} cells: identical primitives in "
                     f"{entry['same_content_exact']}, max deviation {(entry['same_content_max'] or 0):.2%}")
        for text in entry["content_differs"]:
            lines.append(f"- Content differs by renderer: {text}")
        for name, p in predicted.items():
            lines.append(f"- {name}: measured = predicted in {p['exact']} of {p['cells']} cells, max deviation "
                         f"{(p['max'] or 0):.2%} (informational: the renderer bounds a skinned mesh by its posed "
                         f"skeleton)")
        for name, st in steps.items():
            more_text = "ok" if not st["more_anywhere"] else str(st["more_anywhere"])
            far_text = "ok" if not st["not_fewer_at_farthest"] else str(st["not_fewer_at_farthest"])
            line = (f"- {name}: never more than `{PLAIN}` ({more_text}); fewer at the farthest distance for every "
                    f"subject and quality ({far_text}); fewer in {st['fewer']} of {st['cells']} cells from "
                    f"{STEP_FROM_METRES:.0f} m, mean {(st['mean_ratio_from_step'] or 0):.0%} of `{PLAIN}`")
            if st["not_fewer"]:
                line += f" (not switched yet: {st['not_fewer']})"
            lines.append(line)
        lines.append("")
    mobile_lines = mobile_parity(runs, report)
    if mobile_lines:
        lines += ["## Mobile against Forward+ (informational, not part of G5)", ""] + mobile_lines + [""]
    lines += tables(runs)
    report["verdict"] = "GO" if verdict and not missing and variants else "NO-GO"
    if missing or not variants:
        report["verdict"] = "INCOMPLETE"
    lines.insert(2, f"**Verdict: {report['verdict']}**")
    lines.insert(3, "")
    (out / "gate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "gate.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(lines))
    return 0 if report["verdict"] == "GO" else (2 if report["verdict"] == "INCOMPLETE" else 1)


def mobile_parity(runs: dict, report: dict) -> list[str]:
    """Per variant with a Mobile and a Forward+ run: the cells where Mobile
    draws exactly Forward+'s visible and shadow primitives."""
    lines = []
    report["mobile"] = {}
    for variant in sorted({variant for renderer, variant in runs if renderer == MOBILE}):
        forward = runs.get((FORWARD, variant))
        if forward is None:
            continue
        f_cells, m_cells = cells(forward), cells(runs[(MOBILE, variant)])
        keys = sorted(set(f_cells) & set(m_cells))
        differ = [list(k) for k in keys if (f_cells[k]["primitives"], f_cells[k]["shadow_primitives"])
                  != (m_cells[k]["primitives"], m_cells[k]["shadow_primitives"])]
        report["mobile"][variant] = {"cells": len(keys), "equal": len(keys) - len(differ), "differ": differ}
        lines.append(f"- `{variant}`: Mobile draws Forward+'s primitives and shadow primitives in "
                     f"{len(keys) - len(differ)} of {len(keys)} cells" + (f" (differ: {differ})" if differ else ""))
    return lines


def tables(runs: dict) -> list[str]:
    """Primitives per subject, quality and distance for every run, and the
    equipped Humans against the ~25k High budget beyond the first band."""
    lines = ["## Primitives drawn (visible pass)", ""]
    any_run = next(iter(runs.values()))
    distances = [float(d) for d in any_run["distances"]]
    names = sorted(runs)
    subjects = []
    for run in runs.values():
        for row in run["rows"]:
            if row["subject"] not in subjects:
                subjects.append(row["subject"])
    for subject in subjects:
        lines += [f"### {subject}", "", "| run | quality | " + " | ".join(f"{d:.0f} m" for d in distances) + " |",
                  "| --- | --- | " + " | ".join("---:" for _ in distances) + " |"]
        for quality in ("high", "medium", "low"):
            for name in names:
                run_cells = cells(runs[name])
                values = [run_cells.get((subject, quality, d)) for d in distances]
                if all(v is None for v in values):
                    continue
                lines.append(f"| {name[0]}__{name[1]} | {quality} | " + " | ".join(
                    f"{v['primitives']:,}" if v else "" for v in values) + " |")
        lines.append("")
    lines += ["## Equipped Humans against the High budget (about 25k triangles beyond 8 m)", "",
              "| run | subject | quality | 12 m | 26 m | 50 m |", "| --- | --- | --- | ---: | ---: | ---: |"]
    for name in names:
        run_cells = cells(runs[name])
        for subject in subjects:
            if not subject.endswith("_human"):
                continue
            for quality in ("high", "medium", "low"):
                values = [run_cells.get((subject, quality, d)) for d in (12.0, 26.0, 50.0)]
                if all(v is None for v in values):
                    continue
                lines.append(f"| {name[0]}__{name[1]} | {subject} | {quality} | " + " | ".join(
                    (f"**{v['primitives']:,}**" if v["primitives"] > BUDGET_TRIANGLES else f"{v['primitives']:,}")
                    if v else "" for v in values) + " |")
    lines.append("")
    return lines


def compose(out: Path) -> int:
    from PIL import Image, ImageDraw
    runs = load_runs(out)
    if not runs:
        print(f"no ladder runs under {out}")
        return 2
    strips = out / "strips"
    strips.mkdir(exist_ok=True)
    order = sorted(runs, key=lambda key: (key[0] != FORWARD, key[0], key[1] != PLAIN, key[1]))
    any_run = runs[order[0]]
    distances = [float(d) for d in any_run["distances"]]
    groups: dict[tuple[str, str], None] = {}
    for key in order:
        for row in runs[key]["rows"]:
            groups[(row["subject"], row["quality"])] = None
    written = 0
    for subject, quality in groups:
        label_h = 34
        rows = [key for key in order if any(r["subject"] == subject and r["quality"] == quality
                                            for r in runs[key]["rows"])]
        native_h = 0
        native_w = 0
        for key in rows:
            run_cells = cells(runs[key])
            heights = [run_cells[(subject, quality, d)]["crop"][3] for d in distances
                       if (subject, quality, d) in run_cells and "crop" in run_cells[(subject, quality, d)]]
            widths = [run_cells[(subject, quality, d)]["crop"][2] for d in distances
                      if (subject, quality, d) in run_cells and "crop" in run_cells[(subject, quality, d)]]
            native_h = max(native_h, max(heights, default=0))
            native_w = max(native_w, sum(widths) + 8 * len(widths))
        width = max(native_w, len(distances) * (CELL + 8)) + 240
        height = len(rows) * (native_h + label_h) + len(rows) * (CELL + label_h) + 2 * label_h + 16
        sheet = Image.new("RGB", (width, height), (24, 26, 30))
        draw = ImageDraw.Draw(sheet)
        draw.text((8, 6), f"{subject} - {quality} - 1920x1080, FOV 50, orbit distance; native pixels, then "
                          f"each crop scaled to {CELL} px (nearest)", fill=(230, 230, 230))
        y = label_h
        reference = {}
        for section in ("native", "zoom"):
            for key in rows:
                run_cells = cells(runs[key])
                draw.text((8, y + 4), f"{key[0]}__{key[1]}", fill=(255, 220, 120))
                x = 240
                band = native_h if section == "native" else CELL
                for d in distances:
                    row = run_cells.get((subject, quality, d))
                    if row is None or "image" not in row:
                        x += CELL + 8
                        continue
                    crop = Image.open(runs[key]["_folder"] / row["image"]).convert("RGB")
                    if section == "zoom":
                        factor = CELL / max(crop.height, 1)
                        size = (max(1, round(crop.width * factor)), CELL)
                        crop = crop.resize(size, Image.NEAREST if factor >= 1 else Image.LANCZOS)
                    sheet.paste(crop, (x, y + label_h + band - crop.height))
                    text = f"{d:.0f} m  {row['primitives'] / 1000:.1f}k"
                    if key[1] != PLAIN and (key[0], subject, quality, d) in reference:
                        plain = reference[(key[0], subject, quality, d)]
                        text += f" ({row['primitives'] / max(1, plain) - 1:+.0%})"
                    draw.text((x, y + 18), text, fill=(200, 200, 200))
                    if key[1] == PLAIN:
                        reference[(key[0], subject, quality, d)] = row["primitives"]
                    x += max(crop.width, 150 if section == "native" else CELL) + 8
                y += band + label_h
        sheet.save(strips / f"{subject}__{quality}.png")
        written += 1
    print(f"{written} strips in {strips}")
    return 0


def ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def clip(folder: Path, keep_frames: bool) -> int:
    from PIL import Image, ImageDraw
    data = json.loads((folder / "clip.json").read_text(encoding="utf-8"))
    frames = data["frames"]
    exe = ffmpeg_exe()
    if exe is None:
        print("no ffmpeg (pip install imageio-ffmpeg)")
        return 2
    labelled = folder / "labelled"
    labelled.mkdir(exist_ok=True)
    width = int(data["size"][0])
    for frame in frames:
        source = folder / f"frame_{frame['frame']:05d}.jpg"
        image = Image.open(source).convert("RGB")
        draw = ImageDraw.Draw(image)
        for index, name in enumerate(data["order"]):
            draw.text((width * (2 * index + 1) // 6 - 20, 12), name.upper(), fill=(255, 230, 140))
        draw.text((12, image.height - 24), f"{data['renderer']} {data['variant']}  {frame['distance']:5.1f} m  "
                                           f"{frame['primitives']:,} primitives (all three)", fill=(230, 230, 230))
        image.save(labelled / source.name, quality=92)
    target = folder.parent / f"clip_{data['renderer']}__{data['variant']}.mp4"
    command = [exe, "-y", "-loglevel", "error", "-framerate", str(data["fps"]), "-i",
               str(labelled / "frame_%05d.jpg"), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(target)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        return 1
    if not keep_frames:
        shutil.rmtree(labelled)
        for frame in frames:
            (folder / f"frame_{frame['frame']:05d}.jpg").unlink(missing_ok=True)
    print(f"{target} ({len(frames)} frames, {target.stat().st_size / 1e6:.1f} MB)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("gate", "compose"):
        sub.add_parser(name).add_argument("out", type=Path)
    clip_parser = sub.add_parser("clip")
    clip_parser.add_argument("folder", type=Path)
    clip_parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "gate":
        return gate(args.out)
    if args.command == "compose":
        return compose(args.out)
    return clip(args.folder, args.keep_frames)


if __name__ == "__main__":
    sys.exit(main())
