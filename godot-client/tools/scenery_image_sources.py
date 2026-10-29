"""Verified ordinary scenery-GLB image declarations shared by build tools.

All paths are relative GLB URIs; content identity is the complete encoded byte
SHA, not decoded pixels, timestamps or an imported Godot resource.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

SCHEMA = "rabbitlands-scenery-images-v1"
KEY = "rabbitlands_scenery_images"
POLICY = "rl_texture_policy_directory"
ELIGIBLE = "rl_texture_sidecar_eligible"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def glb_chunks(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if len(raw) < 20 or struct.unpack_from("<4sII", raw) != (b"glTF", 2, len(raw)):
        raise ValueError(f"invalid ordinary GLB: {path}")
    size, kind = struct.unpack_from("<I4s", raw, 12)
    if kind != b"JSON" or size > len(raw) - 20:
        raise ValueError(f"invalid GLB JSON: {path}")
    document = json.loads(raw[20:20 + size])
    at = 20 + size
    binary = b""
    if at < len(raw):
        count, kind = struct.unpack_from("<I4s", raw, at)
        if kind != b"BIN\0" or at + 8 + count != len(raw):
            raise ValueError(f"unsupported GLB chunks: {path}")
        binary = raw[at + 8:]
    return document, binary


def relative_path(base: Path, uri: object, roots: list[Path]) -> Path:
    if not isinstance(uri, str) or not uri or any(c in uri for c in (":", "\\", "%")) or Path(uri).is_absolute():
        raise ValueError(f"unsafe scenery image URI: {uri!r}")
    result = (base / uri).resolve()
    if not any(result.is_relative_to(root.resolve()) for root in roots):
        raise ValueError(f"scenery image path outside allowed roots: {uri}")
    return result


def validate(root: Path, glb: Path, document: dict | None = None, *, verify_bytes: bool = True,
             client_directory: str = "godot-client") -> dict:
    root, glb = root.resolve(), glb.resolve()
    if client_directory not in {"godot-client", "app"}:
        raise ValueError("invalid scenery client directory")
    world = root / client_directory / "assets/world"
    if not glb.is_relative_to(world):
        raise ValueError(f"scenery source outside world assets: {glb}")
    document = glb_chunks(glb)[0] if document is None else document
    extra = document.get("extras", {})
    metadata = extra.get(KEY) if isinstance(extra, dict) else None
    if metadata is None:
        return {"tagged": False, "resources": {}, "policies": {}, "images": []}
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA or metadata.get("mipPolicy") != "full":
        raise ValueError("invalid scenery image schema/full-mip policy")
    resources, policies = metadata.get("resources"), metadata.get("imagePolicies")
    if not isinstance(resources, dict) or not isinstance(policies, dict):
        raise ValueError("scenery image resources/policies must be objects")
    allowed = [world, root / "eloria-assets/maps", root / "eloria-assets/world"]
    used, images = {}, []
    for index, image in enumerate(document.get("images", [])):
        if not isinstance(image, dict) or "bufferView" in image:
            raise ValueError("tagged scenery image must be an external URI")
        uri, extras = image.get("uri"), image.get("extras", {})
        path = relative_path(glb.parent, uri, allowed)
        if not isinstance(extras, dict) or type(extras.get(ELIGIBLE)) is not bool:
            raise ValueError("scenery image needs explicit sidecar eligibility")
        directory = relative_path(glb.parent, extras.get(POLICY), [world])
        if directory != glb.parent:
            raise ValueError("scenery image must retain its original GLB policy directory")
        declared = policies.get(uri)
        if not isinstance(declared, list) or not declared or extras[POLICY] not in declared:
            raise ValueError(f"undeclared scenery image policy: {uri}")
        for policy in declared:
            if relative_path(glb.parent, policy, [world]) != glb.parent:
                raise ValueError(f"unexpected scenery original policy directory: {policy}")
        digest = resources.get(uri)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"invalid scenery image SHA: {uri}")
        if verify_bytes and (not path.is_file() or sha(path.read_bytes()) != digest):
            raise ValueError(f"scenery image missing/changed: {uri}")
        used[uri] = path
        images.append({"index": index, "uri": uri, "path": path, "sha256": digest,
                       "policy_directory": directory, "sidecar_eligible": extras[ELIGIBLE]})
    if set(used) != set(resources) or set(used) != set(policies):
        raise ValueError("scenery image closure has missing or unused declarations")
    return {"tagged": True, "resources": resources, "policies": policies, "images": images}
