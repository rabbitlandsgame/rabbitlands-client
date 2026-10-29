"""Stable, deterministic update packages, streamed one bounded part at a time.

Package membership depends on paths, never release dates or byte offsets in a
whole-game ZIP. Adding a file does not move its neighbours to another package.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import zipfile

import client_release
from release_storage import PartWriter

PREPARED_WORLD_BLOB_BUCKETS = 128
PREPARED_WORLD_METADATA_BUCKETS = 8


def package_id(relative: str) -> str:
    parts = relative.split("/")
    if relative in ("app/RabbitLands.exe", "app/RabbitLands.x86_64"):
        return "engine"
    if relative in ("app/RabbitLands.pck", "app/client-release.json"):
        return "client"
    if relative.startswith("app/prepared-world/") and len(parts) >= 4:
        # Compatibility describes native format/renderer policy, never the
        # game release. Code-only releases can reuse every world package.
        # Hashing also keeps IDs bounded without truncating distinct variants.
        variant = hashlib.sha256(parts[2].encode()).hexdigest()[:16]
        prefix = "prepared-world-" + variant
        if len(parts) == 4 and parts[3] == "catalog.json":
            return prefix + "-catalog"
        # Geometry, collision and paving may each have a policy directory.
        # Content-addressed payloads stay separate from small entry metadata.
        if "blobs" in parts[3:-1]:
            group, slots = prefix + "-blobs", PREPARED_WORLD_BLOB_BUCKETS
        else:
            group, slots = prefix + "-metadata", PREPARED_WORLD_METADATA_BUCKETS
    elif relative.startswith("app/assets/actors/"):
        group, slots = "actors-" + "-".join(parts[3:5]), 16
    elif relative.startswith("eloria-assets/maps/"):
        group, slots = "map-" + parts[2], 8
    elif relative.startswith("app/assets/audio/"):
        group, slots = "audio", 8
    elif relative.startswith("app/assets/"):
        group, slots = "assets-" + parts[2], 8
    else:
        group, slots = "records", 8
    # Fixed buckets also bound large collections of models and shared textures.
    group = re.sub(r"[^a-z0-9-]", "-", group.lower())[:72].strip("-")
    bucket = int(hashlib.sha256(relative.encode()).hexdigest()[:8], 16) % slots
    return f"{group}-{bucket:02d}"


def write_payload(stage: Path, files: list[dict], output) -> None:
    def write(archive, name, data):
        info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data, compresslevel=1)

    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for index, entry in enumerate(files):
            path = stage / entry["path"]
            with path.open("rb") as source:
                chunk = 0
                while data := source.read(client_release.CHUNK_BYTES):
                    write(archive, f"files/{index:06d}/{chunk:06d}", data)
                    chunk += 1
        write(archive, "inventory.json", json.dumps(files, separators=(",", ":")).encode())


def build(stage: Path, base: str, *, accept_part=None, budget=None, shared=False,
          previous_packages=None, reuse_package=None) -> list[dict]:
    groups = defaultdict(list)
    seen = set()
    for root in ("app", "eloria-assets"):
        for path in sorted((stage / root).rglob("*")):
            if path.is_symlink():
                raise ValueError("Update packages cannot include links.")
            if not path.is_file():
                continue
            relative = path.relative_to(stage).as_posix()
            if relative.lower() in seen:
                raise ValueError("Update packages contain case-colliding paths.")
            seen.add(relative.lower())
            groups[package_id(relative)].append({"path": relative, "size": path.stat().st_size,
                                                "sha256": client_release.digest(path)})
    packages = []
    for name, files in sorted(groups.items()):
        previous = (previous_packages or {}).get(name)
        if (shared and previous and previous.get("files") == files and reuse_package
                and reuse_package(previous)):
            packages.append(previous)
            continue
        archive = stage.parent / f"{stage.name}.pkg.{name}.zip"
        with PartWriter(archive, base, client_release.PART_BYTES, accept_part, budget, shared=shared) as writer:
            write_payload(stage, files, writer)
        packages.append({"id": name, "sha256": writer.sha256, "size": writer.size,
                         "unpacked_size": sum(f["size"] for f in files),
                         "file_count": len(files), "files": files, "parts": writer.parts})
    if not packages or sum(len(p["parts"]) for p in packages) > 850:
        raise ValueError("Invalid package count; leave room for installers and platform metadata.")
    return packages
