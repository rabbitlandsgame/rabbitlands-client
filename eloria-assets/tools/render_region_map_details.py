#!/usr/bin/env python3
"""Render high-resolution regional map sidecars from current published chunks.

The low-resolution continent pictures and their framing stay unchanged. Detailed
images have exactly the Tab map's world extent and are loaded only when needed.
Run with --work <ignored-folder> --apply; --check verifies every published detail.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eloria-assets/maps/continent-v2/_continent_v2"))
import render_minimap as RM
import build_continent_map as B
import render_region_cartography as RC

IMAGE = "map-detail.webp"
GENERATOR = "eloria-assets/tools/render_region_map_details.py"
INDEX = ROOT / "godot-client/data/maps/map-details.json"


def regions():
    for name in ("cartography.json", "cartography-continent-v2.json"):
        yield from B.load_json(ROOT / "godot-client/data/maps" / name)["regions"]


def current(region, ppm=4, supersample=1):
    package = RM.package_of(ROOT, region["serverMap"])
    manifest = B.load_json(package / "world.json")
    detail = manifest.get("minimap", {}).get("detail", {})
    tab = region["tabMap"]
    if not detail or detail.get("pixelsPerMetre") != ppm:
        return False
    if detail.get("chunkReaderVersion") != RM.CHUNK_READER_VERSION:
        return False
    if detail.get("styleVersion") != RC.STYLE_VERSION or detail.get("supersample") != supersample:
        return False
    if detail.get("retirementSha256") != RM.PC.sha(ROOT / RM.RETIREMENT):
        return False
    if detail.get("worldMin") != tab["worldMin"] or detail.get("worldMax") != tab["worldMax"]:
        return False
    size = [int((tab["worldMax"][i] - tab["worldMin"][i]) * ppm) for i in range(2)]
    if detail.get("imageSize") != size:
        return False
    image = package / IMAGE
    if not image.is_file() or RM.PC.sha(image) != detail.get("imageSha256"):
        return False
    with Image.open(image) as opened:
        if list(opened.size) != size:
            return False
    return not RM.drawn_from(ROOT, region["serverMap"], detail.get("chunksSha256"),
                             detail.get("neighbourChunksSha256", {}))


def publish(region, work, report):
    identity = region["serverMap"]
    if RM.drawn_from(ROOT, identity, report["chunksSha256"], report["neighbourChunksSha256"]):
        raise RM.MinimapError(f"{identity}: geometry changed during render")
    package = RM.package_of(ROOT, identity)
    source = work / identity / RM.PC.MINIMAP
    if RM.PC.sha(source) != report["imageSha256"]:
        raise RM.MinimapError(f"{identity}: rendered detail changed before publication")
    (package / IMAGE).write_bytes(source.read_bytes())
    manifest = B.load_json(package / "world.json")
    manifest["minimap"]["detail"] = {key: report[key] for key in (
        "worldMin", "worldMax", "imageSize", "pixelsPerMetre", "imageSha256",
        "chunksSha256", "neighbourChunksSha256", "styleVersion", "supersample",
        "chunkReaderVersion", "retirementSha256")}
    manifest["minimap"]["detail"].update({"image": IMAGE, "generator": GENERATOR})
    path = package / "world.json"
    raw = path.read_bytes()
    indent = re.search(rb'\n( +)"', raw).group(1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    staged = path.with_name(f".{path.name}.{os.getpid()}.map-detail.tmp")
    staged.write_text(json.dumps(manifest, indent=len(indent), ensure_ascii=False) + "\n",
                      encoding="utf-8", newline=newline)
    staged.replace(path)


def index_data():
    entries = {}
    for region in regions():
        identity = region["serverMap"]
        package = RM.package_of(ROOT, identity)
        detail = B.load_json(package / "world.json").get("minimap", {}).get("detail")
        if not detail:
            continue
        entries[identity] = {"texture": B.path_to_resource(package / IMAGE),
                             **{key: detail[key] for key in ("worldMin", "worldMax", "imageSize", "pixelsPerMetre")},
                             "sha256": detail["imageSha256"]}
    return {"schemaVersion": 1, "generator": GENERATOR, "regions": entries}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", action="append")
    ap.add_argument("--work", type=Path)
    ap.add_argument("--pixels-per-metre", type=int, choices=(2, 4, 8), default=4)
    ap.add_argument("--supersample", type=int, choices=(1, 2), default=1)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-index", action="store_true", help="defer index generation while rendering disjoint batches")
    args = ap.parse_args()
    rows = [r for r in regions() if not args.region or r["serverMap"] in args.region]
    if args.region and set(args.region) - {r["serverMap"] for r in rows}:
        ap.error("unknown region")
    if not args.check and args.work is None:
        ap.error("--work is required to render")
    if args.work and args.work.resolve().is_relative_to(ROOT / "eloria-assets/maps"):
        ap.error("render intermediates must be outside the published map folders")
    stale = []
    for row in rows:
        identity = row["serverMap"]
        if current(row, args.pixels_per_metre, args.supersample):
            print(f"{identity}: detail current", flush=True)
            continue
        if args.check:
            stale.append(identity)
            continue
        print(f"{identity}: rendering {args.pixels_per_metre} pixels/metre", flush=True)
        tab = row["tabMap"]
        report = RM.render(ROOT, identity, args.work, supersample=args.supersample,
                           pixels_per_metre=args.pixels_per_metre,
                           world_frame=(tab["worldMin"], tab["worldMax"]))
        if args.apply:
            publish(row, args.work, report)
            if not args.no_index:
                RM.PC.json_write(INDEX, index_data())
            print(f"{identity}: published {report['imageSize']} ({report['imageBytes']:,} bytes)", flush=True)
    if args.check:
        if not INDEX.is_file() or B.load_json(INDEX) != index_data():
            stale.append("map-details.json")
        count = sum(row["serverMap"] not in stale for row in rows)
        print(f"Details: {count}/{len(rows)} current; stale: {stale}", flush=True)
    elif args.apply and not args.no_index:
        RM.PC.json_write(INDEX, index_data())
    return int(bool(stale))


if __name__ == "__main__":
    raise SystemExit(main())
