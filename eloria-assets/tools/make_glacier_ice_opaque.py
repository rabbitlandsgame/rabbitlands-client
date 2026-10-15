#!/usr/bin/env python3
"""Take the alpha off `glacier_ice` in the shipped region GLBs.

`glacier_ice` was authored for Mirrorhold's frozen lake as a blended material
at 94% opacity. Whitehorn Range then reused it for the ICE terrain class, so a
140 x 436 m glacier river - 128 m of relief, folded over itself down a gorge -
became one alpha-blended mesh. Blended geometry writes no depth and is sorted
one whole instance at a time, so the sheet drew over the seracs standing on it,
its own far triangles drew over its near ones, and it dropped out of the
directional shadow map. The 6% of translucency bought nothing: ice a metre
thick is not see-through, and no view in any of these maps looked through it.

The regions' own build scripts need the toolkit's native rasteriser to
regenerate a package, and rebuilding four packages to change one material would
rewrite every byte of their geometry, manifests and collision. This edits the
material entry in the GLB's JSON chunk and leaves the binary chunk alone, which
is the whole of the change. `_toolkit/amberwood/materials.py` carries the same
change, so a later rebuild produces the same material.

Idempotent: a package already opaque is reported and left alone.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / "maps" / "nymara-regions"
MATERIAL = "glacier_ice"

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if data[:4] != GLB_MAGIC:
        raise ValueError(f"{path} is not a binary glTF")
    version, total = struct.unpack("<II", data[4:12])
    if version != 2:
        raise ValueError(f"{path} is glTF {version}, expected 2")
    if total != len(data):
        raise ValueError(f"{path} declares {total} bytes but holds {len(data)}")
    offset = 12
    document: dict | None = None
    binary = b""
    while offset < len(data):
        length, kind = struct.unpack("<II", data[offset:offset + 8])
        payload = data[offset + 8:offset + 8 + length]
        if kind == CHUNK_JSON:
            document = json.loads(payload)
        elif kind == CHUNK_BIN:
            binary = payload
        else:
            raise ValueError(f"{path} carries an unknown chunk 0x{kind:08x}")
        offset += 8 + length
    if document is None:
        raise ValueError(f"{path} has no JSON chunk")
    return document, binary


def write_glb(path: Path, document: dict, binary: bytes) -> None:
    # The exporter writes compact JSON; matching it keeps the diff to the one
    # material rather than to every key in the document.
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    padded = binary + b"\x00" * (-len(binary) % 4)
    total = 12 + 8 + len(encoded) + (8 + len(padded) if padded else 0)
    out = bytearray()
    out += GLB_MAGIC
    out += struct.pack("<II", 2, total)
    out += struct.pack("<II", len(encoded), CHUNK_JSON)
    out += encoded
    if padded:
        out += struct.pack("<II", len(padded), CHUNK_BIN)
        out += padded
    path.write_bytes(bytes(out))


def make_opaque(document: dict) -> list[str]:
    """Drops the blend off every `glacier_ice` material. Returns what changed."""
    changed: list[str] = []
    for material in document.get("materials", []):
        if material.get("name") != MATERIAL:
            continue
        if material.pop("alphaMode", None) is not None:
            changed.append("alphaMode")
        pbr = material.get("pbrMetallicRoughness", {})
        factor = pbr.get("baseColorFactor")
        if factor is not None and len(factor) == 4 and factor[3] != 1.0:
            factor[3] = 1.0
            changed.append("baseColorFactor")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", default=str(MAPS), help="region packages root")
    parser.add_argument("--check", action="store_true",
                        help="report without writing, and fail if any map is blended")
    args = parser.parse_args()

    pending = 0
    for glb in sorted(Path(args.maps).rglob("world.glb")):
        document, binary = read_glb(glb)
        names = {material.get("name") for material in document.get("materials", [])}
        if MATERIAL not in names:
            continue
        changed = make_opaque(document)
        label = glb.relative_to(args.maps).parent
        if not changed:
            print(f"[ok]    {label}: {MATERIAL} already opaque")
            continue
        pending += 1
        if args.check:
            print(f"[blend] {label}: {MATERIAL} still {', '.join(changed)}")
            continue
        write_glb(glb, document, binary)
        print(f"[write] {label}: {MATERIAL} -> opaque ({', '.join(changed)})")
    return 1 if args.check and pending else 0


if __name__ == "__main__":
    sys.exit(main())
