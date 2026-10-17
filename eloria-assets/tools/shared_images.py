#!/usr/bin/env python3
"""Publish a map's embedded textures once, as the prop meshes already are.

Added 2026-10-13 for Eloria Client, after shared_meshes.py.

    python eloria-assets/tools/shared_images.py --scan
    python eloria-assets/tools/shared_images.py --apply

continent-v2 publishes its images content-addressed into a shared folder and
names them from the manifest's `externalResources`. The nymara regions, the
gauntlets, Four Gates and the shared prototypes still embed theirs in the GLB,
so the same bark or granite ships once per file that draws it: 541 MB of
embedded images in the tree, 176 MB of them distinct.

This pass is shared_meshes.py's twin. Every embedded image moves to

    maps/_shared/images/<sha256>.<jpg|png|webp>

and the GLB names it by URI, so the file carries the reference and not the
bytes. Where the GLB is a map package, the URI joins the manifest's
`externalResources` (which is what gives it `ExternalTexturePool` sharing on
the GPU and the sidecar path when one exists); where it is a prototype, it
joins that prototype's `images` in the pool index, which is where
`ExternalMeshPool` reads them from.

Nothing decodes or re-encodes: the bytes written are the bytes that were
embedded, so a package's pixels do not change and the pass is idempotent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shared_meshes
from shared_meshes import (INDEX, MAPS, POOL, SETS, _prune, package_glbs, manifest_for,  # noqa: E402
                           read_glb, sha256, write_glb, write_manifest, write_package_glb)

IMAGE_POOL = MAPS / "_shared" / "images"
MANIFEST_KEY = "externalResources"
MAGIC = ((b"\xff\xd8\xff", ".jpg", "image/jpeg"),
         (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
         (b"RIFF", ".webp", "image/webp"))


def _kind(data: bytes, declared: str) -> tuple[str, str]:
    for magic, suffix, mime in MAGIC:
        if data.startswith(magic):
            return suffix, mime
    if "png" in declared:
        return ".png", "image/png"
    if "webp" in declared:
        return ".webp", "image/webp"
    return ".jpg", "image/jpeg"


def externalise(glb: Path, dry_run: bool) -> dict:
    """Move this file's embedded images into the pool, leaving URIs behind."""
    document, binary = read_glb(glb)
    images = document.get("images", [])
    embedded = [i for i, image in enumerate(images) if "bufferView" in image]
    if not embedded:
        return {"moved": 0, "bytes": 0, "written": 0, "uris": {}}
    before = glb.stat().st_size
    written = 0
    uris: dict[str, str] = {}
    for index in embedded:
        image = images[index]
        view = document["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        data = binary[start:start + view["byteLength"]]
        digest = sha256(data)
        suffix, mime = _kind(data, str(image.get("mimeType", "")))
        target = IMAGE_POOL / f"{digest}{suffix}"
        if not target.exists():
            if not dry_run:
                IMAGE_POOL.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            written += 1
        image.pop("bufferView", None)
        image["uri"] = os.path.relpath(target, glb.parent).replace("\\", "/")
        image["mimeType"] = mime
        uris[image["uri"]] = digest
    document, binary = _prune(document, binary)
    data = write_glb(document, binary)
    if not dry_run:
        write_package_glb(glb, data)
    return {"moved": len(embedded), "bytes": before - len(data), "written": written, "uris": uris}


def record_manifest(glb: Path, uris: dict, dry_run: bool) -> bool:
    manifest_path = manifest_for(glb)
    if manifest_path is None or dry_run or not uris:
        return False
    text = manifest_path.read_bytes().decode("utf-8")
    manifest = json.loads(text)
    resources = manifest.get(MANIFEST_KEY)
    manifest[MANIFEST_KEY] = dict(sorted({**(resources if isinstance(resources, dict) else {}), **uris}.items()))
    write_manifest(manifest_path, manifest, text)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sets", default="all")
    options = parser.parse_args()
    names = list(SETS) if options.sets == "all" else [s for s in options.sets.split(",") if s]
    roots = [SETS[name] for name in names]
    # Every map package, plus the prototypes: a prototype embeds the textures
    # of the prop it holds, and two prototypes of the same tree carry the same
    # bark.
    files = [glb for root in roots for glb in package_glbs(root)]
    files += sorted(POOL.glob("*.glb"))
    # Map sets outside `SETS` (gauntlets, the towns) embed images too, and the
    # pool is global, so they come along when the whole tree is asked for.
    if options.sets == "all":
        known = {path.resolve() for path in files}
        for glb in sorted(MAPS.rglob("*.glb")):
            if glb.resolve() not in known and "_shared" not in glb.parts and not glb.name.startswith("world-lod"):
                parts = {p.lower() for p in glb.relative_to(MAPS).parts[:-1]}
                if not parts & {"source", "sources", "references", "captures", "godot-captures", "qa", "work"}:
                    files.append(glb)

    if options.scan or not options.apply:
        seen: dict[str, int] = {}
        total = 0
        for glb in files:
            document, binary = read_glb(glb)
            for image in document.get("images", []):
                if "bufferView" not in image:
                    continue
                view = document["bufferViews"][image["bufferView"]]
                data = binary[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
                total += len(data)
                seen[sha256(data)] = len(data)
        print(f"{len(files)} files hold {total / 1e6:.0f} MB of embedded images, "
              f"{sum(seen.values()) / 1e6:.0f} MB distinct: "
              f"{(total - sum(seen.values())) / 1e6:.0f} MB would stop shipping")
        if not options.apply:
            return 0

    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.is_file() else {"prototypes": {}}
    prototypes = index.get("prototypes", {})
    moved = saved = written = touched = 0
    for position, glb in enumerate(files, 1):
        result = externalise(glb, options.dry_run)
        if not result["moved"]:
            continue
        touched += 1
        moved += result["moved"]
        saved += result["bytes"]
        written += result["written"]
        if glb.parent == POOL:
            entry = prototypes.setdefault(glb.stem, {})
            entry["images"] = dict(sorted({**entry.get("images", {}), **result["uris"]}.items()))
            if not options.dry_run:
                entry["sha256"] = sha256(glb.read_bytes())
                entry["bytes"] = glb.stat().st_size
        else:
            record_manifest(glb, result["uris"], options.dry_run)
        if position % 200 == 0 or position == len(files):
            print(f"  [{position}/{len(files)}] {touched} files, {saved / 1e6:.0f} MB removed", flush=True)
    if not options.dry_run:
        index["prototypes"] = prototypes
        INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        # Rewriting a prototype changes the file sha every manifest that names
        # it recorded, and the packager refuses a package where those disagree.
        refreshed = shared_meshes.reconcile()
        if refreshed:
            print(f"refreshed externalMeshes hashes in {len(refreshed)} manifests")
    pool_bytes = sum(path.stat().st_size for path in IMAGE_POOL.glob("*")) if IMAGE_POOL.is_dir() else 0
    print(f"{'would move' if options.dry_run else 'moved'} {moved} embedded images out of {touched} files; "
          f"files {saved / 1e6:.0f} MB smaller, image pool {written} new files / {pool_bytes / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
