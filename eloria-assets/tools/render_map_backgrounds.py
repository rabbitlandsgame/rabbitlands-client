#!/usr/bin/env python3
"""Publish mandatory north-up 2D map backgrounds for every registered map.

Existing certified regional detail images are reused. Other maps are rendered
from their current published GLBs with the maintained cartography chunk reader
and native CPU rasterizer. Sectioned maps publish only separately filtered
section images, never an aggregate image that could reveal other rooms.

This adds pictures and an independent catalog; it changes no world geometry,
materials, collision, map manifests, or geometry-cache policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = "eloria-assets/tools/render_map_backgrounds.py"
CATALOG = "godot-client/data/maps/map-backgrounds.json"
DETAILS = "godot-client/data/maps/map-details.json"
READER = "eloria-assets/maps/continent-v2/_continent_v2"
sys.path.insert(0, str(ROOT / "godot-client/tools"))
import map_background_package as Contract


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def renderer_inputs(root: Path) -> dict[str, str]:
    names = [GENERATOR, "godot-client/tools/map_background_package.py",
             READER + "/render_minimap.py", "eloria-assets/tools/render_region_cartography.py",
             "eloria-assets/tools/atlas_soft_ground.py",
             "eloria-assets/maps/nymara-regions/_toolkit/native/raster.c",
             "eloria-assets/maps/nymara-regions/_toolkit/amberwood/render.py",
             "eloria-assets/maps/nymara-regions/_toolkit/amberwood/mesh.py",
             "godot-client/src/world/soft_ground.gdshader",
             "godot-client/data/assets/retired_procedural_models.json", DETAILS]
    return {name: sha(root / name) for name in names}


def validate_catalog(root: Path = ROOT, catalog=None, verify_sources=True, verify_images=True) -> list[str]:
    """Standard-library-only entry point shared with release tooling."""
    return Contract.validate_catalog(root, catalog, verify_sources, verify_images)


def dimensions(low, high, ppm=4.0, minimum=512, maximum=2048) -> list[int]:
    span = [float(high[i]) - float(low[i]) for i in range(2)]
    if any(not math.isfinite(v) or v <= 0 for v in span):
        raise Contract.BackgroundError("Non-positive map image extent")
    scale = min(maximum / max(span), max(ppm, minimum / max(span)))
    return [max(1, round(v * scale)) for v in span]


def _renderer():
    sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
    sys.path.insert(0, str(ROOT / READER))
    import numpy as np
    from PIL import Image
    import render_minimap as Reader
    import render_region_cartography as Raster
    return np, Image, Reader, Raster


def section_at(point, sections, margin=1.0) -> str:
    """SecretSections._section_at, preserving declaration order and margin."""
    for section in sections:
        low, high = section["bounds"]["min"], section["bounds"]["max"]
        if all(low[i] - margin <= point[i] <= high[i] + margin for i in range(2)):
            return section["id"]
    return ""


def named_section(name: str, sections) -> str:
    for section in sections:
        identity = section["id"]
        if name.startswith("Section_" + identity) or any(
                name.startswith(prefix + identity + "_") for prefix in ("Walk_", "Build_", "Roof_")):
            return identity
    return ""


class SectionLabels:
    """Assign the same mesh-node ownership as SecretSections before rastering.

    The runtime checks a transformed mesh AABB centre, not triangle centres.
    All primitives of one glTF mesh instance therefore receive one label.
    Unclaimed geometry remains visible, matching the runtime's loose nodes.
    """
    def __init__(self, sections, raster):
        self.sections = sections
        self.raster = raster
        self._centres = {}

    def __call__(self, name, mesh_index, transform, document, binary):
        identity = named_section(name, self.sections)
        if identity:
            return identity
        import numpy as np
        if mesh_index not in self._centres:
            points = [self.raster.accessor(document, binary, p["attributes"]["POSITION"])
                      for p in document["meshes"][mesh_index]["primitives"]]
            low = np.min([p.min(axis=0) for p in points], axis=0)
            high = np.max([p.max(axis=0) for p in points], axis=0)
            self._centres[mesh_index] = (low + high) * 0.5
        centre = transform @ np.append(self._centres[mesh_index], 1.0)
        return section_at((centre[0], centre[2]), self.sections)


def _glb_nodes(path: Path):
    with path.open("rb") as stream:
        magic, version, total = struct.unpack("<4sII", stream.read(12))
        size, kind = struct.unpack("<II", stream.read(8))
        if magic != b"glTF" or version != 2 or kind != 0x4E4F534A or size > 64 * 1024 * 1024:
            raise Contract.BackgroundError(f"Invalid published GLB: {path}")
        return json.loads(stream.read(size)).get("nodes", [])


def _hidden_nodes(manifest, glb):
    hidden = set(manifest.get("cutaway", {}).get("hideNodes", []))
    # Older Sunmane caves have no cutaway declaration. Their clearly named
    # cave lids are the occluding surfaces, rather than useful floor plans.
    hidden.update(n.get("name", "") for n in _glb_nodes(glb)
                  if n.get("name", "").startswith("Structure_CaveRoof_"))
    return sorted(hidden)


def _picture(path: Path, low, high, image, root: Path) -> dict:
    return {"path": "res://../" + path.relative_to(root).as_posix(),
            "worldMin": low, "worldMax": high, "imageSize": list(image.size), "sha256": sha(path)}


def _atomic_image(image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    image.save(temporary, format="WEBP", lossless=True, method=4, exact=True)
    temporary.replace(path)


def _atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _current(row, definition, inputs, root: Path, old_renderer, current_renderer) -> bool:
    if not isinstance(row, dict) or row.get("sourceInputs") != inputs or old_renderer != current_renderer:
        return False
    document = definition["document"]
    low, high = Contract.frame_for(document)
    if row.get("worldMin") != low or row.get("worldMax") != high:
        return False
    sectioned = bool(document.get("secret") or document.get("sectioned"))
    expected_sections = {s["id"] for s in document.get("sections", [])} if sectioned else set()
    if set(row.get("sections", {})) != expected_sections or (sectioned and row.get("path")):
        return False
    try:
        pictures = list(row.get("sections", {}).values()) if sectioned else [row]
        return all(sha(Contract.resource_path(root, p["path"])) == p["sha256"]
                   and Contract.image_size(Contract.resource_path(root, p["path"])) == tuple(p["imageSize"])
                   for p in pictures)
    except (OSError, KeyError, Contract.BackgroundError):
        return False


def _check_scope(previous, renderer, settings, selected):
    # A scoped run may refresh changed map inputs, but must not certify
    # untouched old pictures under a different renderer or render setting.
    if selected and previous.get("maps") and (previous.get("rendererInputs") != renderer
                                             or previous.get("renderSettings") != settings):
        raise Contract.BackgroundError("Renderer/settings changed: regenerate all maps without --map")


def render_map(identity, definition, inputs, root, work, apply=True, ppm=4.0, supersample=1):
    np, Image, Reader, Raster = _renderer()
    document = definition["document"]
    manifest_path = Contract.resource_path(root, definition["manifest"])
    glb = manifest_path.parent / document["asset"]["glb"]
    sectioned = bool(document.get("secret") or document.get("sectioned"))
    sections = document.get("sections", []) if sectioned else []
    hidden = _hidden_nodes(document, glb)
    retirement = json.loads((root / "godot-client/data/assets/retired_procedural_models.json").read_text())
    pool = Reader.Pool(Raster, root / "eloria-assets")
    chunk = Reader.read_chunk(Raster, pool, glb, document.get("externalResources", {}), identity,
                              retirement, root, hidden_nodes=hidden,
                              node_label=SectionLabels(sections, Raster) if sections else None)
    low, high = Contract.frame_for(document)
    row = {"worldMin": low, "worldMax": high, "rendererPolicy": Contract.POLICY,
           "sourceInputs": inputs, "sections": {}}
    report = {"map": identity, "hiddenNodes": hidden, "sectioned": sectioned, "pictures": {}}
    folder = work / identity
    folder.mkdir(parents=True, exist_ok=True)
    views = [(s["id"], *Contract.frame_for(document, s["id"])) for s in sections] \
        if sectioned else [("", low, high)]
    for section_id, view_low, view_high in views:
        selected = chunk
        if sectioned:
            selected = dict(chunk)
            selected["parts"] = [p for p, label in zip(chunk["parts"], chunk["part_labels"])
                                 if label in ("", section_id)]
        if not selected["parts"]:
            raise Contract.BackgroundError(f"{identity}/{section_id}: no visible geometry; refusing blank map")
        scene, colors = Reader.window_scene(Raster, pool, [(selected, (0.0, 0.0))])
        size = dimensions(view_low, view_high, ppm)
        rgb, rgba, coverage, counts = Raster.raster(scene, colors, np.asarray(view_low), np.asarray(view_high),
                                                   size, supersample, native_cache=work / "_atlas_native")
        if counts["coveredSamples"] <= 0 or not np.asarray(coverage).any():
            raise Contract.BackgroundError(f"{identity}/{section_id}: empty raster; refusing blank map")
        relative = "map-backgrounds/" + re.sub(r"[^a-zA-Z0-9_-]", "_", section_id) + ".webp" \
            if section_id else "map-background.webp"
        staged = folder / relative
        _atomic_image(rgba, staged)
        destination = manifest_path.parent / relative
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
            temporary.write_bytes(staged.read_bytes())
            temporary.replace(destination)
        picture = _picture(destination if apply else staged, view_low, view_high, rgba, root if apply else work)
        if section_id:
            row["sections"][section_id] = picture
        else:
            row.update(picture)
        report["pictures"][section_id or "map"] = {"triangles": scene.triangle_count(), **counts,
                                                     "imageSize": size, "imageSha256": picture["sha256"]}
    if sectioned:
        row["sectioned"] = True
    if Contract.source_inputs(root, definition["manifest"]) != inputs:
        raise Contract.BackgroundError(f"{identity}: source geometry changed during rendering")
    _atomic_json(folder / "render-report.json", report)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--map", action="append", dest="selected")
    parser.add_argument("--pixels-per-metre", type=float, default=4.0)
    parser.add_argument("--supersample", type=int, choices=(1, 2), default=1)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        errors = validate_catalog(ROOT)
        print("Map backgrounds: " + ("PASS" if not errors else "FAIL"), flush=True)
        for error in errors:
            print(error, flush=True)
        return int(bool(errors))
    if args.work is None or not math.isfinite(args.pixels_per_metre) or args.pixels_per_metre <= 0:
        parser.error("rendering needs --work and a positive --pixels-per-metre")
    work = args.work.resolve()
    if work.is_relative_to(ROOT / "eloria-assets/maps"):
        parser.error("intermediates must remain outside published map folders")
    inventory = Contract.inventory(ROOT)
    unknown = set(args.selected or []) - set(inventory["maps"])
    if unknown:
        parser.error("unknown canonical map: " + ", ".join(sorted(unknown)))
    current_renderer = renderer_inputs(ROOT)
    settings = {"pixelsPerMetre": args.pixels_per_metre, "supersample": args.supersample,
                "minimumLongestSide": 512, "maximumLongestSide": 2048,
                "roofPolicy": "declared-cutaway-and-named-cave-lids"}
    previous = Contract.read_json(ROOT / CATALOG) if (ROOT / CATALOG).is_file() else {}
    _check_scope(previous, current_renderer, settings, args.selected)
    catalog = {"schemaVersion": 1, "generator": GENERATOR, "rendererInputs": current_renderer,
               "renderSettings": settings, "aliases": inventory["aliases"],
               "maps": dict(previous.get("maps", {}))}
    details = Contract.read_json(ROOT / DETAILS)["regions"]
    for identity, definition in inventory["maps"].items():
        if args.selected and identity not in args.selected:
            continue
        started = time.monotonic()
        inputs = Contract.source_inputs(ROOT, definition["manifest"])
        if not args.force and previous.get("renderSettings") == settings and _current(
                catalog["maps"].get(identity), definition, inputs, ROOT,
                previous.get("rendererInputs"), current_renderer):
            print(f"{identity}: current", flush=True)
            continue
        if identity in details:
            # Do not bind an old regional image to today's geometry merely
            # because its bytes still match an old index. Its maintained
            # publication contract must independently certify the inputs.
            import render_region_map_details as Regional
            region = next(r for r in Regional.regions() if r["serverMap"] == identity)
            if not Regional.current(region):
                raise Contract.BackgroundError(f"{identity}: regional detail is stale; rerun render_region_map_details.py")
            detail = details[identity]
            path = Contract.resource_path(ROOT, detail["texture"])
            low, high = Contract.frame_for(definition["document"])
            if (detail["worldMin"], detail["worldMax"]) != (low, high) or sha(path) != detail["sha256"]:
                raise Contract.BackgroundError(f"{identity}: regional detail is missing or incorrectly framed")
            row = {"path": detail["texture"], "worldMin": low, "worldMax": high,
                   "imageSize": detail["imageSize"], "sha256": detail["sha256"], "sections": {},
                   "sourceInputs": inputs, "rendererPolicy": Contract.POLICY}
            print(f"{identity}: reused regional detail", flush=True)
        else:
            print(f"{identity}: rendering published geometry", flush=True)
            row = render_map(identity, definition, inputs, ROOT, work, args.apply,
                             args.pixels_per_metre, args.supersample)
            print(f"{identity}: rendered {len(row['sections']) or 1} image(s) in {time.monotonic()-started:.2f}s", flush=True)
        catalog["maps"][identity] = row
        _atomic_json(ROOT / CATALOG if args.apply else work / "map-backgrounds.json", catalog)
    if args.apply:
        _atomic_json(ROOT / CATALOG, catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
