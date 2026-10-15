#!/usr/bin/env python3
"""Restore rebuilt GLBs whose geometry did not actually change.

Added 2026-08-29 for Eloria Client.  A rebuild rewrites every GLB it touches and
the bytes differ even when nothing about the model does: buffer padding moves,
accessor bounds are recomputed, and a coordinate that ought to be zero comes
back as a denormal one ulp away from it.  Committing all of that turns a change
to one garment set into a hundred-file diff nobody can review, and hides the
twenty files that matter inside it.

Geometry decides, and it decides with a tolerance.  A file is kept only when
some vertex actually moved by more than ``--tolerance`` metres - one micron by
default, which is four orders of magnitude below anything the renderer or the
fit checker can see.  Eight props came back from a rebuild differing by 2e-19 m
in a handful of near-zero coordinates; that is not a change to a bow.

    python prune_unchanged_glbs.py --repo . --path godot-client/assets
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
from pathlib import Path

import numpy as np

_DTYPES = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2",
           5125: "<u4", 5126: "<f4"}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

#: What is compared.  Positions and topology are the model; the skin binding is
#: part of it too, because a garment bound to the wrong bones is a different
#: garment even where every vertex is in the same place.  Normals and UVs follow
#: from positions and are left out so a recomputed normal cannot, on its own,
#: keep an otherwise identical file in the diff.
_ATTRIBUTES = ("POSITION", "JOINTS_0", "WEIGHTS_0")


def geometry(raw: bytes):
    """Every primitive's compared arrays, in document order."""
    if raw[:4] != b"glTF":
        return None
    json_size = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20:20 + json_size])
    offset = 20 + json_size
    binary_size = struct.unpack_from("<I", raw, offset)[0]
    binary = raw[offset + 8:offset + 8 + binary_size]

    def read(index: int) -> np.ndarray:
        spec = document["accessors"][index]
        view = document["bufferViews"][spec["bufferView"]]
        dtype = np.dtype(_DTYPES[spec["componentType"]])
        width = _WIDTHS[spec["type"]]
        start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
        stride = view.get("byteStride", dtype.itemsize * width)
        shape = (spec["count"],) if width == 1 else (spec["count"], width)
        strides = (stride,) if width == 1 else (stride, dtype.itemsize)
        return np.ndarray(shape, dtype=dtype, buffer=binary, offset=start,
                          strides=strides).astype(np.float64)

    out = []
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            entry = {"name": mesh.get("name", "")}
            for name in _ATTRIBUTES:
                index = primitive.get("attributes", {}).get(name)
                if index is not None:
                    entry[name] = read(index)
            if "indices" in primitive:
                entry["indices"] = read(primitive["indices"])
            out.append(entry)
    return out


def moved(before, after, tolerance: float) -> bool:
    """Did anything shift by more than the tolerance?"""
    if before is None or after is None or len(before) != len(after):
        return True
    for left, right in zip(before, after):
        if left.get("name") != right.get("name"):
            return True
        for key in set(left) | set(right):
            if key == "name":
                continue
            if key not in left or key not in right:
                return True
            a, b = left[key], right[key]
            if a.shape != b.shape:
                return True
            # Joint indices and triangle indices are exact; only the float
            # attributes get the tolerance.
            limit = tolerance if key in {"POSITION", "WEIGHTS_0"} else 0.0
            if np.abs(a - b).max(initial=0.0) > limit:
                return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--path", default="godot-client/assets")
    parser.add_argument("--tolerance", type=float, default=1e-6,
                        help="metres a vertex may drift and still count as unchanged")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    changed = subprocess.run(
        ["git", "diff", "--name-only", "--", arguments.path],
        cwd=arguments.repo, capture_output=True, text=True, check=True
    ).stdout.split()
    restore, kept = [], []
    for name in changed:
        if not name.endswith(".glb"):
            continue
        path = arguments.repo / name
        if not path.is_file():
            continue
        committed = subprocess.run(
            ["git", "show", f"HEAD:{name}"], cwd=arguments.repo,
            capture_output=True, check=True).stdout
        if moved(geometry(committed), geometry(path.read_bytes()),
                 arguments.tolerance):
            kept.append(name)
        else:
            restore.append(name)
    print(f"{len(kept)} GLBs changed geometry, {len(restore)} did not")
    for name in kept:
        print("  keep", name.rsplit("/", 1)[-1])
    if restore and not arguments.dry_run:
        for start in range(0, len(restore), 200):
            subprocess.run(["git", "checkout", "--", *restore[start:start + 200]],
                           cwd=arguments.repo, check=True)
        print(f"restored {len(restore)}")


if __name__ == "__main__":
    main()
