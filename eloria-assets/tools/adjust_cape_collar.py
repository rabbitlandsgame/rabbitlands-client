"""Rework the cape collars: a back arc riding high, the cloth hung from it.

The machine-built capes carry a full golden oval around the neck whose
front half cuts across the chest, and the cloth sheet's top row sits
inside the shoulders.  Reviewed in game, the collar becomes a third of
the ring on the back side only, raised toward the shoulder line, and the
sheet's top edge is re-hung along that arc so the cape springs from the
collar instead of slicing through the wearer.

Layout assumptions (all builder-made capes share them): primitive 0
"... Base" is the cloth, primitive 1 "... Trim" is the collar ring plus
hem accents; collar verts are the Trim verts in the top band.  Capes
without that layout are left untouched.

Usage:
    python adjust_cape_collar.py [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import json
import struct
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
EQUIPMENT = (TOOLS.parent.parent / "godot-client" / "assets" / "actors"
             / "native" / "equipment")

#: Half-angle of the kept arc, degrees from due back (60 = a third of
#: the ring).
ARC_HALF_ANGLE = 60.0
#: How far the collar (and the sheet's attachment) rises.
COLLAR_LIFT = 0.05
#: Trim vertices above this height belong to the collar, below it to the
#: hem accents.
COLLAR_BAND = 1.30
#: The cloth's top edge blends onto the arc from here up.
SHEET_BLEND_LO = 1.32
SHEET_BLEND_HI = 1.44
#: The sheet stays at least this far behind the wearer's own back.
BACK_CLEARANCE = 0.02
RACES = TOOLS.parent.parent / "godot-client" / "assets" / "actors"     / "native" / "races"


def smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 3 * t * t - 2 * t * t * t


def read_glb(path: Path):
    data = path.read_bytes()
    assert data[:4] == b"glTF", path
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    assert json_type == b"JSON"
    document = json.loads(data[20:20 + json_len])
    binary = bytearray(data[20 + json_len:])
    bin_len, bin_tag = struct.unpack_from("<I4s", binary, 0)
    assert bin_tag[:3] == b"BIN", bin_tag
    return document, binary


def write_glb(path: Path, document, binary) -> None:
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    out = bytearray(b"glTF")
    out += struct.pack("<II", 2, 12 + 8 + len(payload) + len(binary))
    out += struct.pack("<I4s", len(payload), b"JSON")
    out += payload
    out += binary
    path.write_bytes(bytes(out))


def accessor_slice(document, binary, index):
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    offset = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return acc, offset, view.get("byteStride")


def positions_of(document, binary, prim):
    acc, offset, stride = accessor_slice(document, binary,
                                         prim["attributes"]["POSITION"])
    stride = stride or 12
    out = np.empty((acc["count"], 3), dtype=np.float64)
    for v in range(acc["count"]):
        out[v] = struct.unpack_from("<3f", binary, offset + v * stride)
    return out


def write_positions(document, binary, prim, points) -> None:
    acc, offset, stride = accessor_slice(document, binary,
                                         prim["attributes"]["POSITION"])
    stride = stride or 12
    for v in range(acc["count"]):
        struct.pack_into("<3f", binary, offset + v * stride,
                         *[float(c) for c in points[v]])


def back_profile():
    """The wearer's back line: most-negative z of the trunk per height
    band, so the sheet can be held behind it."""
    document, binary = read_glb(RACES / "luminous_male.glb")
    zs = {}
    for node in document["nodes"]:
        if "mesh" not in node or "skin" not in node:
            continue
        for prim in document["meshes"][node["mesh"]]["primitives"]:
            pts = positions_of(document, binary, prim)
            trunk = (np.abs(pts[:, 0]) < 0.20) & (pts[:, 1] > 0.95)
            for x, y, z in pts[trunk]:
                band = round(y * 20) / 20
                zs[band] = min(zs.get(band, 0.0), float(z))
        break
    bands = sorted(zs)
    return np.array(bands), np.array([zs[b] for b in bands])


def clamp_behind_back(document, binary, base_prim, dry: bool) -> int:
    bands, depth = back_profile()
    base = positions_of(document, binary, base_prim)
    moved = 0
    for i in range(len(base)):
        y = base[i, 1]
        if y < 1.0 or abs(base[i, 0]) > 0.30:
            continue
        limit = float(np.interp(y, bands, depth)) - BACK_CLEARANCE
        if base[i, 2] > limit:
            base[i, 2] = limit
            moved += 1
    if not dry and moved:
        write_positions(document, binary, base_prim, base)
    return moved


def rework(path: Path, dry: bool) -> str:
    document, binary = read_glb(path)
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    marker = extras.get("eloriaCapeCollar")
    if marker and marker.get("version", 1) >= 2:
        return "already reworked"
    if marker:
        # Version 1 shipped without the back clamp; apply just that.
        base_prim = document["meshes"][0]["primitives"][0]
        moved = clamp_behind_back(document, binary, base_prim, dry)
        if not dry:
            marker["version"] = 2
            extras["eloriaCapeCollar"] = marker
            write_glb(path, document, binary)
        return "back-clamped %d verts (v1 -> v2)" % moved
    meshes = document.get("meshes", [])
    if not meshes or len(meshes[0]["primitives"]) < 2:
        return "no trim primitive"
    base_prim, trim_prim = meshes[0]["primitives"][0], meshes[0]["primitives"][1]
    trim = positions_of(document, binary, trim_prim)
    collar = trim[:, 1] > COLLAR_BAND
    if int(collar.sum()) < 24 or float(trim[collar][:, 2].max()) < 0.0:
        return "no forward collar"

    centre = np.array([float(np.median(trim[collar][:, 0])),
                       float(np.median(trim[collar][:, 2]))])
    radial = trim[collar][:, [0, 2]] - centre
    radius = float(np.median(np.linalg.norm(radial, axis=1)))

    # 1. The collar keeps only its back arc, raised.  Dropped verts are
    # collapsed onto the nearest kept arc end rather than deleted, so the
    # index buffer stays valid and the discarded ring faces degenerate to
    # zero area.
    angles = np.degrees(np.arctan2(trim[:, 0] - centre[0],
                                   -(trim[:, 2] - centre[1])))
    new_trim = trim.copy()
    for i in np.nonzero(collar)[0]:
        angle = float(angles[i])
        clipped = float(np.clip(angle, -ARC_HALF_ANGLE, ARC_HALF_ANGLE))
        r = float(np.linalg.norm(trim[i, [0, 2]] - centre))
        if abs(angle) > ARC_HALF_ANGLE + 1e-6:
            r = radius
        rad = np.radians(clipped)
        new_trim[i, 0] = centre[0] + r * np.sin(rad)
        new_trim[i, 2] = centre[1] - r * np.cos(rad)
        new_trim[i, 1] = trim[i, 1] + COLLAR_LIFT
    if not dry:
        write_positions(document, binary, trim_prim, new_trim)

    # 2. The sheet's top edge hangs from that arc: blend each high vertex
    # onto the arc line at its own (clamped) bearing and lift it with the
    # collar.
    base = positions_of(document, binary, base_prim)
    new_base = base.copy()
    for i in range(len(base)):
        weight = smoothstep((base[i, 1] - SHEET_BLEND_LO)
                            / (SHEET_BLEND_HI - SHEET_BLEND_LO))
        if weight <= 0.0:
            continue
        angle = float(np.degrees(np.arctan2(
            base[i, 0] - centre[0], -(base[i, 2] - centre[1]))))
        clipped = np.radians(np.clip(angle, -ARC_HALF_ANGLE, ARC_HALF_ANGLE))
        target = np.array([centre[0] + radius * np.sin(clipped),
                           base[i, 1] + COLLAR_LIFT,
                           centre[1] - radius * np.cos(clipped)])
        new_base[i] = base[i] * (1.0 - weight) + target * weight
    if not dry:
        write_positions(document, binary, base_prim, new_base)
    clamped = clamp_behind_back(document, binary, base_prim, dry)
    if not dry:
        extras["eloriaCapeCollar"] = {"arc": ARC_HALF_ANGLE,
                                      "lift": COLLAR_LIFT, "version": 2}
        write_glb(path, document, binary)
    return "reworked (collar %d verts, radius %.3f)" % (
        int(collar.sum()), radius)


def main() -> int:
    ap = argparse.ArgumentParser(description="rework cape collars in place")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for path in sorted(EQUIPMENT.glob("*cape*.glb")):
        print("%-40s %s" % (path.name, rework(path, args.dry_run)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
