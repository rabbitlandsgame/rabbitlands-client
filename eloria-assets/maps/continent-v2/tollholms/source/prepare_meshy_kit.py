"""Seat The Tollholms' kit in its territory kit: the isle kit's pieces it reuses and its own generated landmarks.

The Tollholms (`tollholms`, the island group's second map) is built from the same kit as the south-west isle
(adjacent-map design section 13: 0 credits required), plus the owner-approved Tollholms landmarks O1-O3
(island content plan, 2026-10-02). Two kinds of model become territory prototypes
(`godot-client/world_authoring/regions/tollholms/assets/prototypes/kit-*.glb`), which the Territories palette
offers when The Tollholms is open:

- SHARED: pieces copied byte for byte from sw_isle's prepared kit (`world_authoring/regions/sw_isle/assets/
  prototypes`, written by `sw_isle/source/prepare_meshy_kit.py`), with the content-addressed textures they
  reference. Every model keeps the size, origin, tint and derivation it has on the isle, so a haven townhouse, a
  trestle span or a broadleaf tree is the same object on both maps (and the client's shared image pool stores its
  textures once).
- GENERATED: the three Tollholms landmarks, read from the accepted pass-with-fixes copies (`work-output/
  continent-v2/meshy/tollholms/fix3/O1..O3`, review run 3). Each is checked against its size in SIZES (the fix
  pass already sized it, so the factor is 1 and the geometry is left as fixed), node transforms are baked into the
  vertices (a no-op: the deliveries have none), the lowest point stands on 0 (origin kind "base"; O2's slipway
  foot is its lowest point, at the waterline), the texture is re-encoded (JPEG, quality 88, 1024 px) and written
  once, content-addressed, to the territory's `assets/textures/`, and the root node names the kit and carries its
  seating notes in `extras.eloria`.
    - O1 `kit-th-ringholm-watch-tower`: the Ringholm watch tower, 17.0 m, limewashed with a slate cone (fix3:
      roof re-tinted to slate, window glow painted as shutters);
    - O2 `kit-th-tollholm-boathouse`: the Tollholm boathouse, 7.5 m, its slipway (stretched in fix3) running
      down along +Z to the waterline;
    - O3 `kit-th-spindle-beacon`: the Spindle Hill summit beacon, 7.5 m. Prepared for the summit path, which
      the owner put off (2026-10-02); it is not placed until that path is built.
- LIGHTENED: a shared piece with fewer triangles (same material, textures, size and origin), built by
  `lighten_kit.py` beside this tool, which needs Blender, and recorded in `lighten-kit.json`:
    - `kit-vineyard-rows-1-light`: the vineyard row at 2,212 of its 4,432 triangles, laid in every Tollholms
      vineyard so the north village chunk has triangles for its lawn (owner, 2026-10-03: "use lighter vineyard
      rows for the north lawn").
  This tool does not rebuild them: it records each one with the prepared heavy piece it came from, and refuses
  (or, with --check, reports stale) a lightened piece whose recorded input is no longer that prepared piece or
  whose file is not the recorded output.

`python prepare_meshy_kit.py --input <work-output/continent-v2/meshy/tollholms/fix3>` writes the kit and
`prepare-meshy-kit.json` (the SHA-256 of every input and output); `--check` confirms the committed files are
what the recorded inputs produce.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
REGIONS = CLIENT / "godot-client/world_authoring/regions"
PROTOTYPES = REGIONS / "tollholms/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
SOURCE_KIT = REGIONS / "sw_isle/assets/prototypes"
RECORD = HERE / "prepare-meshy-kit.json"

# The isle tool's GLB helpers (read, positions, texture re-encode, transform bake), reused as they are.
_spec = importlib.util.spec_from_file_location(
    "sw_isle_prepare_meshy_kit", CLIENT / "eloria-assets/maps/continent-v2/sw_isle/source/prepare_meshy_kit.py")
ISLE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ISLE)

# name -> (piece id, folder in --input, metres to the top above the base, texture px, notes)
SIZES = {
    "th-ringholm-watch-tower": ("O1", "O1", 17.0, 1024,
                                "Ringholm watch tower: stands on the tower court at the end of R32 (east islet)"),
    "th-tollholm-boathouse": ("O2", "O2", 7.5, 1024,
                              "Tollholm boathouse: the floor on the L21 quay, the slipway (+Z) down to the waterline"),
    "th-spindle-beacon": ("O3", "O3", 7.5, 1024,
                          "Spindle Hill summit beacon: waits for the summit path (owner, 2026-10-02); not placed"),
}

# Pieces copied from sw_isle's prepared kit, by use (adjacent-map design sections 6, 8, 9 and 10).
SHARED = [
    # Tollholm village: the Tollhouse, haven townhouses, the square, street clutter
    "merchant-house-1", "haven-townhouse-1", "haven-townhouse-2", "haven-townhouse-3",
    "stone-well-1", "notice-board-1", "market-canopy-1", "market-canopy-2", "produce-stall-1", "lantern-post-1",
    "stone-bench-1", "barrel-stack-1", "crate-stack-1", "feed-sacks-1", "apple-cart-1", "flower-cart-1",
    "terracotta-pots-1", "citrus-planter-1", "flower-planter-1",
    # fishers and the lagoon quay
    "fisher-hut-1", "net-shed-1", "stone-landing-stage-1", "quay-steps-1", "mooring-posts-1", "mooring-buoy-1",
    "lamp-buoy-1", "fishing-boat-1", "fishing-boat-2", "rowing-boat-1", "sloop-1", "net-drying-frame-1",
    "fish-crates-1", "lobster-pots-1", "rope-coils-1", "harbour-banner-1", "harbour-banner-2", "sea-wall-segment-1",
    # farms
    "vineyard-rows-1", "wheat-stooks-1", "cabbage-rows-1", "beehive-skeps-1", "windmill-1", "dovecote-1",
    "drystone-dyke-1", "drystone-dyke-2", "split-rail-fence-1",
    # the tower pier: N11 Toll Tower, N14 ferry, N13 trestles, N12 arches under the platform, N3 revetment courses
    # for the house pads' retaining faces, N19 corners at the L21 walls
    "sw-harbour-tower", "sw-ferry-ship", "sw-trestle-pier-span", "sw-trestle-pier-span-long24",
    "sw-causeway-arch-span", "sw-causeway-arch-tier", "sw-curtain-revetment", "sw-sea-cliff-corner",
    # trees
    "sw-broadleaf-tree-a", "sw-broadleaf-tree-b", "sw-blossom-tree", "beach-palm-tree-1", "beach-palm-tree-2",
    "beach-palm-tree-3", "beach-palm-tree-4", "beach-palm-tree-1-clear", "beach-palm-tree-2-clear",
    "beach-palm-tree-3-clear", "fan-palm-tree-1", "olive-tree-1", "olive-tree-2", "cypress-tree-1",
    "umbrella-pine-tree-1", "lemon-tree-1", "flame-tree-1", "tree-fern-1", "tree-fern-2",
    "bougainvillea-shrub-1", "flower-shrub-1", "flower-shrub-2", "flower-shrub-3",
    # ground cover
    "flower-meadow-1", "flower-meadow-2", "flower-meadow-3", "flower-meadow-4", "undergrowth-1", "undergrowth-2",
    "undergrowth-3", "undergrowth-4", "undergrowth-5", "jungle-undergrowth-1", "jungle-undergrowth-2",
    "beach-flower-mat-1", "dune-grass-1", "dune-grass-2",
    # coast and rock
    "coastal-rock-1", "coastal-rock-2", "coastal-rock-3", "coastal-boulders-1", "coastal-boulders-2",
    "coastal-boulders-3", "coastal-boulders-4", "sea-stack-1", "sea-stack-2", "beach-rocks-1", "driftwood-1",
    "driftwood-2", "kelp-wrack-1", "shell-scree-1",
]

# Lightened pieces: name -> the shared piece it is lightened from (lighten_kit.py builds them; see the docstring).
LIGHTENED = {
    "vineyard-rows-1-light": "vineyard-rows-1",
}
LIGHTEN_RECORD = HERE / "lighten-kit.json"


def prepare(source: Path, name: str) -> tuple[bytes, dict[str, bytes], dict]:
    """A generated landmark: the prototype's bytes, its texture files, and what was measured."""
    piece, _folder, metres, texture_size, notes = SIZES[name]
    document, binary = ISLE._read(source)
    binary = ISLE._bake_node_transforms(document, binary)
    accessors = sorted({p["attributes"]["POSITION"] for mesh in document["meshes"] for p in mesh["primitives"]})
    points = np.concatenate([ISLE._positions(document, binary, index) for index in accessors]).astype(np.float64)
    low, high = points.min(axis=0), points.max(axis=0)
    if abs(metres / (high[1] - low[1]) - 1.0) > 0.01:
        raise ValueError(f"{name}: measured {high[1] - low[1]:.3f} m against {metres} m; the fixed copy is not at size")
    rise = 0.0 - float(low[1])
    replaced: dict[int, bytes] = {}
    if rise != 0.0:
        for index in accessors:
            accessor = document["accessors"][index]
            moved = (ISLE._positions(document, binary, index).astype(np.float64) + [0.0, rise, 0.0]).astype("<f4")
            accessor["min"] = [float(v) for v in moved.min(axis=0)]
            accessor["max"] = [float(v) for v in moved.max(axis=0)]
            if accessor.get("byteOffset", 0) != 0:
                raise ValueError("expected positions at the start of their buffer view")
            view = ISLE._view(document, binary, accessor["bufferView"])
            replaced[accessor["bufferView"]] = moved.tobytes() + view[moved.nbytes:]
    textures: dict[str, bytes] = {}
    image_views = set()
    for image in document.get("images", []):
        payload = ISLE._view(document, binary, image["bufferView"])
        encoded, mime = ISLE._texture(payload, image.get("mimeType", "image/png"), texture_size)
        file = hashlib.sha256(encoded).hexdigest() + (".png" if mime == "image/png" else ".jpg")
        textures[file] = encoded
        image_views.add(image.pop("bufferView"))
        image["uri"] = "../textures/" + file
        image["mimeType"] = mime
    for material in document.get("materials", []):
        material.setdefault("pbrMetallicRoughness", {})["metallicFactor"] = 0.0
    root = document["nodes"][0]
    root["name"] = "kit-" + name
    size = high - low
    root["extras"] = {"eloria": {"id": piece, "kit": "kit-" + name, "origin": "base", "notes": notes,
                                 "bounds_m": [round(float(v), 3) for v in size]}}
    document["asset"] = {"version": "2.0", "generator": "Eloria tollholms prepare_meshy_kit"}
    out = bytearray()
    kept, renumber = [], {}
    for index, view in enumerate(document["bufferViews"]):
        if index in image_views:
            continue
        payload = replaced.get(index, ISLE._view(document, binary, index))
        while len(out) % 4:
            out.append(0)
        view["byteOffset"] = len(out)
        view["byteLength"] = len(payload)
        out.extend(payload)
        renumber[index] = len(kept)
        kept.append(view)
    document["bufferViews"] = kept
    for accessor in document["accessors"]:
        accessor["bufferView"] = renumber[accessor["bufferView"]]
    while len(out) % 4:
        out.append(0)
    document["buffers"] = [{"byteLength": len(out)}]
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(out)
    facts = {"id": piece, "measure": "height", "metres": metres, "texturePixels": texture_size, "origin": "base",
             "rise_m": round(rise, 6), "bounds_m": [round(float(v), 3) for v in size]}
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out)), textures, facts


def shared(name: str) -> tuple[Path, bytes, dict[str, bytes]]:
    """A piece of the isle kit: its prepared prototype's bytes and the texture files it references."""
    source = SOURCE_KIT / f"kit-{name}.glb"
    payload = source.read_bytes()
    document, _ = ISLE._read(source)
    textures = {}
    for image in document.get("images", []):
        uri = image.get("uri", "")
        match = re.fullmatch(r"\.\./textures/([0-9a-f]{64}\.(?:png|jpg))", uri)
        if not match:
            raise ValueError(f"{source.name}: image {uri!r} is not a content-addressed territory texture")
        textures[match.group(1)] = (source.parent.parent / "textures" / match.group(1)).read_bytes()
    return source, payload, textures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True,
                        help="the accepted fix folder (work-output/continent-v2/meshy/tollholms/fix3)")
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    record = {"schema": "eloria-prepared-kit-v1", "tool": "prepare_meshy_kit.py", "models": {}}
    stale = []
    if not args.check:
        PROTOTYPES.mkdir(parents=True, exist_ok=True)
        TEXTURES.mkdir(parents=True, exist_ok=True)
    jobs = [(name, "generated") for name in sorted(SIZES)] + [(name, "shared") for name in sorted(SHARED)] + \
        [(name, "lightened") for name in sorted(LIGHTENED)]
    prepared: dict[str, tuple[bytes, dict[str, bytes]]] = {}
    lightened = json.loads(LIGHTEN_RECORD.read_text(encoding="utf-8")).get("models", {}) \
        if LIGHTEN_RECORD.exists() else {}
    for name, kind in jobs:
        if kind == "generated":
            source = args.input / SIZES[name][1] / f"kit-{name}.glb"
            payload, textures, facts = prepare(source, name)
            entry = {"kind": kind, "source": f"meshy/tollholms/fix3/{SIZES[name][1]}/kit-{name}.glb", **facts}
            entry["input"] = hashlib.sha256(source.read_bytes()).hexdigest()
        elif kind == "lightened":
            # built by lighten_kit.py (Blender); recorded here with the prepared heavy piece it was built from
            base_payload, textures = prepared[LIGHTENED[name]]
            built = lightened.get(name, {})
            target = PROTOTYPES / f"kit-{name}.glb"
            payload = target.read_bytes() if target.exists() else b""
            entry = {"kind": kind, "source": f"kit-{LIGHTENED[name]}.glb as prepared here, lightened by lighten_kit.py",
                     "input": hashlib.sha256(base_payload).hexdigest(),
                     "triangles": built.get("triangles", {}).get("final")}
            if built.get("input") != entry["input"] or built.get("output") != hashlib.sha256(payload).hexdigest():
                if not args.check:
                    raise SystemExit(f"{name}: not built from the prepared kit-{LIGHTENED[name]}.glb; "
                                     f"run lighten_kit.py --blender <blender.exe> first")
                stale.append(name)
        else:
            source, payload, textures = shared(name)
            prepared[name] = (payload, textures)
            entry = {"kind": kind, "source": source.relative_to(CLIENT).as_posix(),
                     "input": hashlib.sha256(payload).hexdigest()}
        target = PROTOTYPES / f"kit-{name}.glb"
        entry.update({"output": hashlib.sha256(payload).hexdigest(), "textures": sorted(textures)})
        record["models"][name] = entry
        if args.check:
            if not target.exists() or target.read_bytes() != payload or any(
                    not (TEXTURES / file).exists() or (TEXTURES / file).read_bytes() != data
                    for file, data in textures.items()):
                stale.append(name)
            continue
        # unchanged files are not rewritten, so the editor does not re-import them
        if not target.exists() or target.read_bytes() != payload:
            target.write_bytes(payload)
            print(f"{target.name}: {len(payload) // 1024} KB, {len(textures)} texture(s)", flush=True)
        for file, data in textures.items():
            if not (TEXTURES / file).exists() or (TEXTURES / file).read_bytes() != data:
                (TEXTURES / file).write_bytes(data)
    if args.check:
        recorded = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.exists() else {}
        if recorded != record:
            stale.append(RECORD.name)
        expected = {f"kit-{name}.glb" for name in record["models"]}
        extra = sorted(p.name for p in PROTOTYPES.glob("*.glb") if p.name not in expected) \
            if PROTOTYPES.exists() else []
        if extra:
            stale.append("unrecorded prototypes " + ", ".join(extra))
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
        print(f"{len(record['models'])} prototypes match the recorded inputs")
        return 0
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
