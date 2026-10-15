#!/usr/bin/env python3
"""Remove buffer data that nothing in an actor GLB references.

Added 2026-09-16 for Eloria Client.

    python tools/strip_unused_glb_data.py --dry-run
    python tools/strip_unused_glb_data.py --archive ../../archive/glb-unused-data-2026-09-16

The basic-expansion creatures carried 499 MB of accessors no mesh, morph
target, animation or skin uses - flesh_golem.glb was 51 MB, 39 MB of it
unreachable - most likely clips and surface frames an earlier pipeline step
dropped without compacting the buffer. A loader never reads them, so removing
them changes nothing that renders.

An accessor is kept when a mesh primitive (attribute, indices, morph target),
an animation sampler or a skin's inverse bind matrices names it; a buffer view
is kept when a kept accessor or an image names it. Everything kept is
re-indexed and repacked, then every kept accessor and image is compared byte
for byte with the original. The tool refuses GLBs whose extensions or sparse
accessors could reference accessors from somewhere else.

Only godot-client/assets/actors is touched. Map GLBs are not: their bytes are
the digest the server checks (ELORIA_MAP_DIGEST).

Originals are archived at their repository path with a manifest, and the
sha256/bytes build records are updated the same way
shrink_actor_textures.py does it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from shrink_actor_textures import (REPO, read_glb, records_from_manifest, repo_path, sha256,
                                   tracked, update_records, view_bytes, write_glb)

# Extensions known not to reference accessors.
SAFE_EXTENSIONS = {"KHR_materials_specular", "KHR_materials_ior", "KHR_materials_emissive_strength",
                   "KHR_texture_transform", "KHR_materials_unlit"}
COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def accessor_bytes(document: dict, binary: bytes, index: int) -> bytes:
    accessor = document["accessors"][index]
    if "bufferView" not in accessor:
        return b""
    view = document["bufferViews"][accessor["bufferView"]]
    element = COMPONENT_BYTES[accessor["componentType"]] * TYPE_COUNT[accessor["type"]]
    stride = view.get("byteStride", element)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    length = stride * (accessor["count"] - 1) + element if accessor["count"] else 0
    return binary[start:start + length]


def strip(document: dict, binary: bytes) -> tuple[dict, bytes] | None:
    unknown = set(document.get("extensionsUsed", [])) - SAFE_EXTENSIONS
    if unknown:
        raise ValueError(f"unhandled extensions {sorted(unknown)}")
    if any("sparse" in accessor for accessor in document.get("accessors", [])):
        raise ValueError("sparse accessors are not handled")

    used_accessors: set[int] = set()
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            used_accessors.update(primitive["attributes"].values())
            if "indices" in primitive:
                used_accessors.add(primitive["indices"])
            for target in primitive.get("targets", []):
                used_accessors.update(target.values())
    for animation in document.get("animations", []):
        for sampler in animation["samplers"]:
            used_accessors.update((sampler["input"], sampler["output"]))
    for skin in document.get("skins", []):
        if "inverseBindMatrices" in skin:
            used_accessors.add(skin["inverseBindMatrices"])
    used_views = {document["accessors"][i]["bufferView"] for i in used_accessors
                  if "bufferView" in document["accessors"][i]}
    used_views.update(image["bufferView"] for image in document.get("images", []) if "bufferView" in image)

    accessors = document.get("accessors", [])
    views = document.get("bufferViews", [])
    if len(used_accessors) == len(accessors) and len(used_views) == len(views):
        return None

    original = json.loads(json.dumps(document))
    accessor_map = {old: new for new, old in enumerate(sorted(used_accessors))}
    view_map = {old: new for new, old in enumerate(sorted(used_views))}

    packed = bytearray()
    new_views = []
    for old in sorted(used_views):
        packed.extend(b"\0" * ((-len(packed)) % 4))
        view = dict(views[old], byteOffset=len(packed))
        packed.extend(view_bytes(document, binary, old))
        new_views.append(view)
    packed.extend(b"\0" * ((-len(packed)) % 4))

    new_accessors = []
    for old in sorted(used_accessors):
        accessor = dict(accessors[old])
        if "bufferView" in accessor:
            accessor["bufferView"] = view_map[accessor["bufferView"]]
        new_accessors.append(accessor)
    document["accessors"] = new_accessors
    document["bufferViews"] = new_views
    document["buffers"][0]["byteLength"] = len(packed)
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            primitive["attributes"] = {k: accessor_map[v] for k, v in primitive["attributes"].items()}
            if "indices" in primitive:
                primitive["indices"] = accessor_map[primitive["indices"]]
            primitive["targets"] = [{k: accessor_map[v] for k, v in target.items()}
                                    for target in primitive.get("targets", [])] or None
            if primitive["targets"] is None:
                del primitive["targets"]
    for animation in document.get("animations", []):
        for sampler in animation["samplers"]:
            sampler["input"] = accessor_map[sampler["input"]]
            sampler["output"] = accessor_map[sampler["output"]]
    for skin in document.get("skins", []):
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = accessor_map[skin["inverseBindMatrices"]]
    for image in document.get("images", []):
        if "bufferView" in image:
            image["bufferView"] = view_map[image["bufferView"]]

    new_binary = bytes(packed)
    for old, new in accessor_map.items():
        if accessor_bytes(original, binary, old) != accessor_bytes(document, new_binary, new):
            raise ValueError(f"accessor {old} changed while repacking")
    for old_image, new_image in zip(original.get("images", []), document.get("images", [])):
        if "bufferView" in old_image and (view_bytes(original, binary, old_image["bufferView"])
                                          != view_bytes(document, new_binary, new_image["bufferView"])):
            raise ValueError("image bytes changed while repacking")
    return document, new_binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    if not options.dry_run and not options.archive:
        parser.error("--archive is required unless --dry-run")

    changes = []
    for path in tracked("godot-client/assets/actors/*.glb", "godot-client/assets/actors/**/*.glb"):
        document, binary = read_glb(path)
        result = strip(document, binary)
        if result:
            original = path.read_bytes()
            data = write_glb(*result)
            changes.append((path, original, data))
    before = sum(len(o) for _, o, _ in changes)
    after = sum(len(d) for _, _, d in changes)
    print(f"{len(changes)} GLBs with unused data: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
    if options.dry_run or not changes:
        return 0

    archive = options.archive.resolve()
    manifest_path = archive / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    earlier = {path: (entry.get("newSha256"), entry.get("newBytes")) for path, entry in manifest.items()}
    for path, original, _ in changes:
        target = archive / repo_path(path)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if target.read_bytes() != original and repo_path(path) not in manifest:
            raise SystemExit(f"archive copy of {repo_path(path)} does not match the file being replaced")
    for path, original, data in changes:
        path.write_bytes(data)
        entry = manifest.setdefault(repo_path(path), {"sha256": sha256(original), "bytes": len(original)})
        entry.update({"newSha256": sha256(data), "newBytes": len(data)})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    updated = update_records(*records_from_manifest(manifest, earlier))
    print(f"updated hash records in {len(updated)} files")
    for path in updated:
        print("  " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
