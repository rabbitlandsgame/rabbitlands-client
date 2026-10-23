"""Actual byte identities for the asset portion of a local benchmark export.

Only standalone, unencrypted, non-sparse Godot PCK formats 2--4 are supported.
Layout follows Godot ed1daf0bf001b61586d9930840f2f1394092c079:
core/io/file_access_pack.{h,cpp} and core/io/pck_packer.cpp. This never launches
Godot, extracts a pack, trusts directory MD5 values, or loads project scripts.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

POLICY = "rabbitlands-exported-assets-v1"
SCOPE = "complete-exported-asset-closure"
PCK_PATH = "app/RabbitLands.pck"
GENERATED_PCK = frozenset({"data/client_release.json", "data/benchmark_profile.json"})
GENERATED_LOOSE = frozenset({"benchmark-package.json", ".eloria-package", "README.txt",
    "launcher-defaults.json", "app/client-release.json", "app/data/client_release.json",
    "app/data/benchmark_profile.json", "app/project.binary", "app/project.godot"})
CODE_SUFFIXES = (".gd", ".gdc", ".gd.remap", ".gd.uid", ".gdshader", ".gdshaderinc",
    ".gdshader.uid", ".gdshaderinc.uid", ".gdextension", ".cs", ".cs.uid", ".cs.remap",
    ".dll", ".so", ".dylib", ".exe", ".pdb", ".py", ".pyc", ".rs", ".cpp", ".h", ".hpp",
    ".bat", ".cmd", ".sh", ".ps1")
GENERATED_PCK_CACHE = frozenset({"project.binary", "project.godot", ".godot/uid_cache.bin",
                               ".godot/global_script_class_cache.cfg"})
COVERAGE = {
    "pck": "all non-code payload files; assets/, data/, schemas/, scenes/resources/remaps and every .godot/imported product included",
    "loose": "all non-code staged files, including app/assets, app/data, app/schemas, all eloria-assets maps/pools/sidecars and unknown roots",
    "generatedPckExclusions": sorted(GENERATED_PCK),
    "generatedLooseExclusions": sorted(GENERATED_LOOSE),
    "generatedPckCacheExclusions": sorted(GENERATED_PCK_CACHE),
    "codeSuffixExclusions": list(CODE_SUFFIXES),
    "scenesAndResourcesIncluded": True,
    "importProductsAlwaysIncluded": True,
    "packageContainerCodeAndLaunchMetadataIncluded": False,
    "semanticReferenceValidation": "normal packager checks remain separate; this is a conservative actual staged content identity",
}


class AssetClosureError(ValueError):
    pass


def _canonical(name: str) -> str:
    name = name.removeprefix("res://")
    if not name or "\\" in name or ":" in name or "\x00" in name \
            or any(ord(character) < 32 for character in name) \
            or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/")):
        raise AssetClosureError("noncanonical or escaping PCK/inventory path")
    return PurePosixPath(name).as_posix()


def _exact(stream, size: int) -> bytes:
    result = stream.read(size)
    if len(result) != size:
        raise AssetClosureError("truncated PCK header/directory/payload")
    return result


def pck_index(path: Path) -> dict:
    """Validate the entire standalone pack directory before reading payloads.

    Godot adds PCK start to V3/4 file_base and directory_offset; V2 file_base
    is relative only with flag2. Our standalone start is exactly zero. Entry
    offsets are always relative to that file_base, never directory offsets.
    """
    path = Path(path)
    if not path.is_file():
        raise AssetClosureError("required standalone PCK is missing")
    size = path.stat().st_size
    with path.open("rb") as stream:
        if _exact(stream, 4) != b"GDPC":
            raise AssetClosureError("standalone PCK header must start at byte zero")
        version, major, minor, patch = struct.unpack("<4I", _exact(stream, 16))
        if version not in (2, 3, 4):
            raise AssetClosureError("unsupported PCK format; require 2, 3 or 4")
        flags, = struct.unpack("<I", _exact(stream, 4))
        if flags & ~2:
            raise AssetClosureError("encrypted, sparse or unknown PCK flags are unsupported")
        file_base, = struct.unpack("<Q", _exact(stream, 8))
        if version >= 3:
            directory, = struct.unpack("<Q", _exact(stream, 8))
            _exact(stream, 64)  # Current packer reserves sixteen uint32 words.
        else:
            _exact(stream, 64)
            directory = stream.tell()
        header_end = stream.tell()
        if directory < header_end or directory > size - 4 or file_base > size:
            raise AssetClosureError("PCK directory/file base is outside the standalone file")
        stream.seek(directory)
        count, = struct.unpack("<I", _exact(stream, 4))
        if count > 1_000_000 or count > (size - stream.tell()) // 41:
            raise AssetClosureError("invalid PCK directory entry count")
        entries, names = [], set()
        for unused in range(count):
            length, = struct.unpack("<I", _exact(stream, 4))
            if not 0 < length <= 1_048_576 or length > size - stream.tell() - 36:
                raise AssetClosureError("invalid PCK path length")
            encoded = _exact(stream, length).rstrip(b"\x00")
            try:
                name = _canonical(encoded.decode("utf-8", "strict"))
            except UnicodeError as error:
                raise AssetClosureError("invalid UTF-8 PCK path") from error
            if name.casefold() in names:
                raise AssetClosureError("duplicate or case-ambiguous PCK path")
            names.add(name.casefold())
            offset, length = struct.unpack("<QQ", _exact(stream, 16))
            _exact(stream, 16)  # Directory MD5 is not used as content evidence.
            entry_flags, = struct.unpack("<I", _exact(stream, 4))
            if entry_flags:
                raise AssetClosureError("encrypted, removal, delta or unknown PCK entry flags")
            absolute = file_base + offset
            if absolute < header_end or absolute > size or length > size - absolute:
                raise AssetClosureError("PCK payload range is outside file or overlaps header")
            entries.append({"path": name, "offset": absolute, "bytes": length})
        directory_end = stream.tell()
        ranges = sorted((row["offset"], row["offset"] + row["bytes"]) for row in entries if row["bytes"])
        previous_end = header_end
        for begin, end in ranges:
            if begin < previous_end or begin < directory_end and end > directory:
                raise AssetClosureError("overlapping PCK payload/directory ranges")
            previous_end = end
        if any(directory <= row["offset"] < directory_end
               and (row["bytes"] or row["offset"] != directory) for row in entries):
            raise AssetClosureError("PCK payload starts inside directory")
    return {"formatVersion": version, "engineVersion": [major, minor, patch],
            "entryCount": count, "entries": sorted(entries, key=lambda row: row["path"])}


def _pck_exclusion(name: str) -> str | None:
    if name.startswith(".godot/imported/"):
        return None  # Never omit imported products, even with a code-like suffix.
    if name in GENERATED_PCK:
        return "generated release/profile metadata"
    if name in GENERATED_PCK_CACHE:
        return "generated project/script UID/class cache"
    if name.endswith(CODE_SUFFIXES):
        return "explicit code/bytecode/script UID/launcher"
    return None  # Unknown roots and every scene/resource/remap are included.


def _loose_exclusion(name: str) -> str | None:
    if name in GENERATED_LOOSE:
        return "known generated manifest/release/project/launch metadata"
    local = name.removeprefix("app/")
    if local.startswith(".godot/imported/"):
        return None
    if local in GENERATED_PCK_CACHE:
        return "generated project/script UID/class cache"
    if name.endswith(CODE_SUFFIXES):
        return "explicit code/bytecode/script UID/launcher"
    return None


def _sha_payload(stream, start: int, length: int) -> str:
    stream.seek(start)
    digest = hashlib.sha256()
    remaining = length
    while remaining:
        part = _exact(stream, min(1024 * 1024, remaining))
        digest.update(part)
        remaining -= len(part)
    return digest.hexdigest()


def build_asset_closure(stage: Path) -> dict:
    stage = Path(stage).resolve()
    if not stage.is_dir():
        raise AssetClosureError("staged package directory is missing")
    files, names = {}, set()
    for path in sorted(stage.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(stage):
            raise AssetClosureError("staged asset inventory contains symlink/escaping path")
        if not path.is_file():
            continue
        name = _canonical(path.relative_to(stage).as_posix())
        if name == "benchmark-package.json":
            continue  # Self identity must be stable before and after first write.
        if name.casefold() in names:
            raise AssetClosureError("duplicate/case-ambiguous staged inventory")
        names.add(name.casefold())
        files[name] = path
    packs = sorted(name for name in files if name.lower().endswith(".pck"))
    if packs != [PCK_PATH]:
        raise AssetClosureError("asset closure needs exactly app/RabbitLands.pck; overlays/embedded packs unsupported")
    index = pck_index(files[PCK_PATH])
    packed, loose, excluded = [], [], []
    with files[PCK_PATH].open("rb") as stream:
        for row in index["entries"]:
            reason = _pck_exclusion(row["path"])
            if reason:
                excluded.append({"kind": "pck", "path": row["path"], "reason": reason})
            else:
                packed.append({"path": row["path"], "bytes": row["bytes"],
                               "sha256": _sha_payload(stream, row["offset"], row["bytes"])})
    if not packed:
        raise AssetClosureError("PCK asset closure has no included payload files")
    for name, path in sorted(files.items()):
        if name == PCK_PATH:
            continue
        reason = _loose_exclusion(name)
        if reason:
            excluded.append({"kind": "loose", "path": name, "reason": reason})
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        loose.append({"path": name, "bytes": path.stat().st_size, "sha256": digest})
    identities = [{"kind": kind, **row} for kind, rows in (("pck", packed), ("loose", loose)) for row in rows]
    encoded = json.dumps({"policy": POLICY, "files": identities}, sort_keys=True, separators=(",", ":")).encode()
    return {"schemaVersion": 1, "status": "complete", "scope": SCOPE, "policy": POLICY,
            "hashAlgorithm": "sha256", "contentHash": hashlib.sha256(encoded).hexdigest(),
            "coverage": copy.deepcopy(COVERAGE), "unknowns": [],
            "pck": {"path": PCK_PATH, "formatVersion": index["formatVersion"],
                    "engineVersion": index["engineVersion"], "directoryEntryCount": index["entryCount"],
                    "files": packed}, "looseFiles": loose, "excluded": excluded}


def verify_asset_closure(stage: Path, declared: dict) -> dict:
    if not isinstance(declared, dict) or declared.get("schemaVersion") != 1 \
            or type(declared.get("schemaVersion")) is not int or declared.get("status") != "complete" \
            or declared.get("scope") != SCOPE or declared.get("policy") != POLICY:
        raise AssetClosureError("unsupported/malformed declared asset closure")
    actual = build_asset_closure(stage)
    if actual != declared:
        raise AssetClosureError("actual asset closure inventory/content/coverage differs from manifest")
    packed, loose = actual["pck"]["files"], actual["looseFiles"]
    return {"schemaVersion": 1, "status": "complete", "scope": SCOPE, "policy": POLICY,
            "assetClosureHash": actual["contentHash"], "coverage": actual["coverage"], "unknowns": [],
            "pckPayloadFileCount": len(packed), "pckPayloadBytes": sum(row["bytes"] for row in packed),
            "looseFileCount": len(loose), "looseBytes": sum(row["bytes"] for row in loose)}
