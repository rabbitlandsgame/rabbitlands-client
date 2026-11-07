"""Add verified, derived prototype LODs to their existing lazy asset archives."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

POLICY = "rl-browser-prototype-lods-v1"
SUFFIX = ".browser-lods.json"
LIMIT = 32 * 1024 * 1024


def apply(catalog: dict, index_path: Path, assets: Path, repository: Path) -> tuple[dict, dict]:
    repository = repository.resolve()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if (index.get("schema") != 1 or index.get("policy") != POLICY or not isinstance(index.get("sources"), dict)
            or not isinstance(index.get("engine"), str) or not 1 <= len(index["engine"]) <= 128):
        raise ValueError("Invalid browser prototype LOD index")
    sidecars = {}
    for name, entry in index["sources"].items():
        logical = PurePosixPath(name)
        if (logical.is_absolute() or ".." in logical.parts or "\\" in name or logical.suffix != ".glb"
                or not name.startswith(("eloria-assets/", "godot-client/assets/world/"))):
            raise ValueError("Unsafe prototype LOD source")
        source = (repository / name).resolve()
        sidecar = Path(entry["sidecar_path"]).resolve()
        expected = entry.get("source_sha256", "")
        if (not source.is_relative_to(repository) or not re.fullmatch(r"[a-f0-9]{64}", expected)
                or not sidecar.is_relative_to(repository / ".local") or not 0 < sidecar.stat().st_size <= LIMIT):
            raise ValueError("Invalid local prototype LOD artifact")
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("Prototype source changed after LOD preparation: " + name)
        body = sidecar.read_bytes()
        document = json.loads(body)
        if (document.get("schema") != 1 or document.get("policy") != POLICY
                or document.get("source_sha256") != expected or document.get("engine") != index.get("engine")):
            raise ValueError("Prototype LOD identity mismatch: " + name)
        sidecars[name] = body
    result = copy.deepcopy(catalog)
    replacements = {}
    used = set()
    for group in result["groups"].values():
        added = 0
        for row in group["archives"]:
            old_name = row["file"]
            if old_name not in replacements:
                original = assets / old_name
                if (not re.fullmatch(r"[a-f0-9]{64}", row["sha256"]) or old_name != row["sha256"] + ".zip"
                        or original.stat().st_size != row["bytes"]):
                    raise ValueError("Invalid source archive")
                with zipfile.ZipFile(original) as incoming:
                    names = incoming.namelist()
                    matched = sorted(set(name.split(".__rlpart_", 1)[0] for name in names) & sidecars.keys())
                    if not matched:
                        replacements[old_name] = (dict(row), 0, [])
                    else:
                        temporary = assets / "prototype-lods-packing.tmp"
                        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as outgoing:
                            for info in incoming.infolist():
                                if info.filename.endswith(SUFFIX):
                                    raise ValueError("Start from a catalog without derived prototype LODs")
                                outgoing.writestr(info, incoming.read(info))
                            for name in matched:
                                info = zipfile.ZipInfo(name + SUFFIX, (1980, 1, 1, 0, 0, 0))
                                info.compress_type = zipfile.ZIP_DEFLATED
                                info.external_attr = 0o100644 << 16
                                outgoing.writestr(info, sidecars[name], compresslevel=6)
                        if temporary.stat().st_size > 64 * 1024 * 1024:
                            raise ValueError("Prototype LOD archive exceeds the browser download limit")
                        with temporary.open("rb") as stream:
                            digest = hashlib.file_digest(stream, "sha256").hexdigest()
                        replacement = {"file": digest + ".zip", "sha256": digest, "bytes": temporary.stat().st_size}
                        temporary.replace(assets / replacement["file"])
                        replacements[old_name] = (replacement, sum(len(sidecars[name]) for name in matched), matched)
            replacement, length, matched = replacements[old_name]
            row.update(replacement)
            added += length
            used.update(matched)
        group["unpacked_bytes"] += added
    if used != sidecars.keys():
        raise ValueError("Prototype LOD index includes sources absent from this browser catalog")
    return result, {"policy": POLICY, "sources": len(used), "unpacked_bytes": sum(map(len, sidecars.values())),
                    "changed_archives": sum(bool(value[2]) for value in replacements.values())}
