"""Strict portable source closure for production road-ground fields."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote

SCHEMA = "rabbitlands-road-terrain-blend-v1"
MAX_METADATA = 16 * 1024 * 1024


class RoadGroundDependencyError(ValueError):
    pass


def _digest(value) -> str:
    if not isinstance(value, str) or not re.fullmatch("[0-9a-fA-F]{64}", value):
        raise RoadGroundDependencyError("Invalid road-ground SHA256")
    return value.lower()


def _path(asset_root: Path, parent: Path, uri, *, metadata=False) -> Path:
    if not isinstance(uri, str) or not uri or "\\" in uri or ":" in uri or "\0" in uri:
        raise RoadGroundDependencyError("Nonportable road-ground resource path")
    decoded = unquote(uri)
    relative = PurePosixPath(decoded)
    if relative.is_absolute() or ":" in decoded or "\\" in decoded or (metadata and ".." in relative.parts):
        raise RoadGroundDependencyError("Road-ground resource path escapes its package")
    path = (parent / decoded).resolve()
    if not path.is_relative_to(asset_root):
        raise RoadGroundDependencyError("Road-ground resource is outside the asset tree")
    return path


def dependencies(repository: Path, manifest_path: Path, config) -> dict[Path, str]:
    """Verify metadata and every declared runtime file; no image imports/decoding."""
    if config is None:
        return {}
    if not isinstance(config, dict) or not config:
        raise RoadGroundDependencyError("roadGround must be a nonempty object")
    asset_root = (repository.resolve() / "eloria-assets").resolve()
    metadata = _path(asset_root, manifest_path.resolve().parent, config.get("metadata"), metadata=True)
    expected = _digest(config.get("sha256"))
    try:
        raw = metadata.read_bytes()
        if len(raw) > MAX_METADATA or hashlib.sha256(raw).hexdigest() != expected:
            raise RoadGroundDependencyError("Road-ground metadata changed")
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get("schema") != SCHEMA:
            raise RoadGroundDependencyError("Unsupported road-ground metadata schema")
        resources = document.get("resources")
        if not isinstance(resources, dict) or not resources:
            raise RoadGroundDependencyError("Road-ground runtime resources are undeclared")
        result = {metadata: expected}
        for uri, declared in resources.items():
            path = _path(asset_root, metadata.parent, uri)
            digest = _digest(declared)
            if path in result and result[path] != digest:
                raise RoadGroundDependencyError("Conflicting road-ground resource hashes")
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != digest:
                raise RoadGroundDependencyError("Road-ground runtime resource changed: " + str(path))
            result[path] = digest
        return result
    except (OSError, json.JSONDecodeError) as exc:
        raise RoadGroundDependencyError("Cannot read road-ground source closure: " + str(exc)) from exc
