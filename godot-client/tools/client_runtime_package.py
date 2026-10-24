"""Verified optional native payload and isolated human-testing launchers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil

ABI = 1
LIBRARIES = {"windows": "client_runtime.dll", "linux": "client_runtime.so", "macos": "client_runtime.dylib"}
NATIVE_PATH = Path("godot-client/native/client_runtime")
EXTERNAL_SOURCE_INPUTS = (
    Path("godot-client/native/shared/cape_constraint_math.h"),
    Path("godot-client/native/shared/mounted_cape_surface_math.h"),
    Path("godot-client/native/native_crowd/src/native_spell_flight_geometry.cpp"),
    Path("godot-client/native/native_crowd/src/native_spell_flight_geometry.h"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest(repository: Path) -> str:
    root = repository / NATIVE_PATH
    files = []
    for directory, folders, names in os.walk(root):
        folders[:] = [name for name in folders if name not in {"target", "build", ".deps", ".git"}]
        for name in names:
            path = Path(directory) / name
            if path.suffix in {".rs", ".h", ".cpp", ".toml", ".lock", ".in", ".json"} or name == "CMakeLists.txt":
                files.append(path)
    if not files:
        raise ValueError("No client runtime source inputs")
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    for relative in EXTERNAL_SOURCE_INPUTS:
        path = repository / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing or linked external native source input: " + relative.as_posix())
        digest.update(b"external/" + relative.as_posix().encode() + b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def validate_payload(directory: Path, repository: Path, platform: str) -> dict:
    manifest = json.loads((directory / "runtime-manifest.json").read_text(encoding="utf-8"))
    library = LIBRARIES[platform]
    if manifest.get("abi") != ABI or (manifest.get("engine_major"), manifest.get("engine_minor")) != (4, 7):
        raise ValueError("Native runtime API mismatch")
    if manifest.get("platform") != platform or manifest.get("architecture") != "x86_64" or manifest.get("library") != library:
        raise ValueError("Native runtime platform mismatch; omit it to retain the legacy platform path")
    if manifest.get("source_digest") != source_digest(repository):
        raise ValueError("Native runtime was built from different source inputs")
    for name, key in ((library, "library_sha256"), ("client_runtime.gdextension", "descriptor_sha256")):
        path = directory / name
        if not path.is_file() or path.is_symlink() or sha256(path) != manifest.get(key):
            raise ValueError("Native runtime payload checksum mismatch: " + name)
    return manifest


def stage_payload(directory: Path, repository: Path, app: Path, platform: str) -> dict:
    manifest = validate_payload(directory, repository, platform)
    destination = app / "bin/client_runtime"
    destination.mkdir(parents=True, exist_ok=False)
    for name in (LIBRARIES[platform], "runtime-manifest.json", "client_runtime.gdextension"):
        shutil.copy2(directory / name, destination / name)
    validate_payload(destination, repository, platform)
    return manifest


def write_launchers(stage: Path, platform: str) -> None:
    # A global legacy profile supplies defaults, not a veto on individual
    # overrides. Reset every family so an inherited experimental environment
    # cannot turn a legacy control or an isolated pilot into a mixed run.
    legacy = {
        "RABBITLANDS_CLIENT_RUNTIME": "legacy",
        "RABBITLANDS_REMOTE_PRESENTATION": "legacy",
        "RABBITLANDS_RUST_EFFECTS": "legacy",
        "RABBITLANDS_RESOURCE_ADMISSION": "legacy",
        "RABBITLANDS_PREPARED_CONTENT": "raw",
        "RABBITLANDS_PREPARED_NODE_POLICY": "retain",
    }
    human_testing = {
        "RABBITLANDS_CLIENT_RUNTIME": "rust",
        "RABBITLANDS_REMOTE_PRESENTATION": "rust",
        "RABBITLANDS_RUST_EFFECTS": "heat_bolt",
        "RABBITLANDS_RESOURCE_ADMISSION": "rust",
        "RABBITLANDS_PREPARED_CONTENT": "auto",
        "RABBITLANDS_PREPARED_NODE_POLICY": "lazy-source-v1",
    }
    profiles = (
        ("optimization testing", "human-testing", human_testing),
        ("legacy runtime", "legacy", {}),
        ("Rust rider pilot", "legacy", {"RABBITLANDS_CLIENT_RUNTIME": "rust"}),
        ("Rust comparison", "legacy", {"RABBITLANDS_CLIENT_RUNTIME": "compare"}),
        ("Rust heat bolt pilot", "legacy", {
            "RABBITLANDS_CLIENT_RUNTIME": "rust", "RABBITLANDS_RUST_EFFECTS": "heat_bolt"}),
    )
    for name, profile, overrides in profiles:
        environment = {"RABBITLANDS_OPTIMIZATION_PROFILE": profile, **legacy, **overrides,
                       "ELORIA_NATIVE_PRESENTATION": "0", "ELORIA_NATIVE_CROWD": "0"}
        if platform == "windows":
            body = '@echo off\r\nsetlocal\r\n'
            body += ''.join(f'set "{key}={value}"\r\n' for key, value in environment.items())
            body += 'call "%~dp0RabbitLands.bat" %*\r\n'
            (stage / f"RabbitLands ({name}).bat").write_bytes(body.encode("utf-8"))
        elif platform == "linux":
            script = stage / f"RabbitLands ({name}).sh"
            body = '#!/bin/sh\n'
            body += ''.join(f'export {key}={value}\n' for key, value in environment.items())
            body += 'exec "$(dirname "$0")/RabbitLands.sh" "$@"\n'
            script.write_text(body, encoding="utf-8")
            script.chmod(0o755)
