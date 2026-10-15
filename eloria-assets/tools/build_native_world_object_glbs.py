#!/usr/bin/env python3
"""Build the GLBs the Godot client draws for server-declared world objects.

Added 2026-08-29 for Eloria Client.

The server tells the client where every clickable world object stands and what
kind it is (`ELORIA_MAP_OBJECTS`), and the client drew each one as a coloured
ring on the ground: green for a harvest node, blue for an interactive. A ring
says "this is clickable" and nothing else, so a plaza full of service points
and a hillside full of ore read as the same row of circles.

The geometry is not invented here. Harvest nodes come straight out of
`harvestables.py`, which is already the single source of truth for every
resource in the world and authors each one to the regional-kit fidelity
contract; this module converts that authored geometry into glTF and writes the
material the same generator writes for the legacy pack, so the two renderers
draw the same plant. Interactive props are authored here because nothing else
described them: the server states a role for each one, and each role gets the
object its own player-facing text describes.

Two conversions matter:

* the harvestable geometry is authored Z-up, because the legacy E3D format is;
  glTF is Y-up, so positions and normals are rotated (x, y, z) -> (x, z, -y);
* foliage declares `alphaMode: MASK` and `doubleSided`, which is what the leaf
  cards need for the same reason `3d_objects.c` enables alpha test and disables
  back-face culling for them - a one-sided leaf card disappears from behind.

The registry is written whole, so a harvest node modelled anywhere else (the
reviewed Meshy nodes) is listed in `imported_world_objects.py`. Those GLBs are
not written here: the table is checked before anything is written, then each
GLB is measured where it sits (and refused outside the imported triangle
band), added beside the procedural models, and given its resource label when
its row says it answers it.
Reviewed interactive replacements retain their role and model id; the
generator measures their existing GLB and skips its procedural fallback.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harvestables as H
from build_native_nymara_glbs import GLB
from imported_world_objects import check_rows, imported_interactive_entries, merge_imported
from png_writer import png

CLIENT_HARVESTABLE_DIR = "assets/world/harvestables"
CLIENT_INTERACTIVE_DIR = "assets/world/interactives"
REGISTRY = "data/world/objects.json"


def authored_doorways() -> dict:
    """Pick targets for entrances whose art already belongs to map packages."""
    source = Path(__file__).resolve().parents[1] / "maps/continent-v2/_continent_v2/content/underground.json"
    if not source.is_file():
        return {}
    plan = json.loads(source.read_text(encoding="utf-8"))
    return {str(section["entrance"]["object"]):
            {"height": 3.6, "radius": 1.6, "label": section["name"]}
            for section in plan["sections"]}

# Metres per authored unit. The authored harvestable geometry is already in
# metres - a reed bed stands 1.4 units tall against a 1.8 unit person - and the
# Godot world is in metres whatever a map's `metresPerTile` is, so nothing is
# rescaled. Named rather than left as a bare 1.0 because that is a claim about
# the source geometry, not an arbitrary constant.
HARVEST_SCALE = 1.0


# ---------------------------------------------------------------------------
# authored geometry -> glTF
# ---------------------------------------------------------------------------

def as_gltf_arrays(vertices: list, indices: list):
    """Split the authored (u, v, nx, ny, nz, x, y, z) rows into glTF arrays.

    The rotation to Y-up is applied here rather than in a node transform so the
    file needs no import adapter: what the client loads is already oriented.
    """
    raw = np.asarray(vertices, dtype="float32")
    uvs = raw[:, 0:2].copy()
    normals = raw[:, 2:5]
    positions = raw[:, 5:8]
    y_up_positions = np.stack(
        (positions[:, 0], positions[:, 2], -positions[:, 1]), axis=1)
    y_up_normals = np.stack(
        (normals[:, 0], normals[:, 2], -normals[:, 1]), axis=1)
    return (np.ascontiguousarray(y_up_positions),
            np.ascontiguousarray(y_up_normals),
            np.ascontiguousarray(uvs),
            np.asarray(indices, dtype="uint32"))


def material_png(colours, scratch: Path) -> bytes:
    """The authored 256x256 quartered material, as PNG bytes.

    `harvestables.material_pixel` is the same function that paints the legacy
    pack's texture, so a resource looks the same in both clients.
    """
    png(scratch, H.TEXTURE_SIZE, H.TEXTURE_SIZE, H.material_pixel(*colours))
    data = scratch.read_bytes()
    scratch.unlink()
    return data


def write_object_glb(path: Path, name: str, build, colours, *,
                     foliage: bool, scratch: Path,
                     scale: float = 1.0) -> dict:
    vertices: list = []
    indices: list = []
    build(vertices, indices)
    positions, normals, uvs, triangles = as_gltf_arrays(vertices, indices)
    if scale != 1.0:
        positions = np.ascontiguousarray(positions * scale)
    glb = GLB(generator="Eloria world object builder")
    material = glb.material(
        name, colours[1], roughness=0.86,
        texture_png=material_png(colours, scratch),
        double_sided=foliage, alpha_mode="MASK" if foliage else None)
    glb.mesh_node(name, [glb.primitive(positions, normals, uvs, triangles,
                                       material)])
    glb.write(path)
    return {"vertices": int(len(positions)),
            "triangles": int(len(triangles) // 3),
            "alphaTested": bool(foliage),
            "height": round(float(positions[:, 1].max()), 3)}


# ---------------------------------------------------------------------------
# harvest nodes
# ---------------------------------------------------------------------------

def harvest_entries():
    """Every authored resource: the regional catalogue, then the bootstrap
    set, then the continent-v2 isle crops."""
    for rid, label, kind, tier, _regions, colours, model in H.CATALOGUE:
        yield rid, label, kind, tier, colours, model
    for rid, label, kind, tier, colours, model in H.BOOTSTRAP:
        yield rid, label, kind, tier, colours, model
    for rid, label, kind, tier, colours, model in H.ISLE_CROPS:
        yield rid, label, kind, tier, colours, model


def build_harvestables(client_root: Path, scratch: Path) -> dict:
    output = client_root / CLIENT_HARVESTABLE_DIR
    models: dict[str, dict] = {}
    resources: dict[str, str] = {}
    for rid, label, kind, tier, colours, (build, foliage) in harvest_entries():
        stats = write_object_glb(output / f"{rid}.glb", rid, build, colours,
                                 foliage=foliage, scratch=scratch,
                                 scale=HARVEST_SCALE)
        models[rid] = {"scene": f"res://{CLIENT_HARVESTABLE_DIR}/{rid}.glb",
                       "label": label, "kind": kind, "tier": tier, **stats}
        # The server names a node by its resource label and nothing else, so
        # the label is the key the client has to resolve. Recording it here
        # rather than slugifying at runtime is what lets Slate and Deep Coal
        # keep their bootstrap model names.
        resources[label] = rid
    return {"models": models, "resources": resources}


# ---------------------------------------------------------------------------
# interactive props
# ---------------------------------------------------------------------------
# One prop per interactive role. The role is all the server states about an
# interactive that is not free text: `map_object_entries` sends
# `role.replace("_", " ").title()` as the label and the player-facing sentence
# as the detail. Choosing a prop from the sentence would be the same mistake as
# the stock client matching harvest state out of the chat stream - it breaks on
# any rewording and on every translation - so the four Emberhaven crafting
# stations share one bench until the server states which craft each one is.

def _box(v, i, centre, size, uv):
    cx, cy, cz = centre
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    corners = {
        "north": ((-hx, hy, -hz), (hx, hy, -hz), (hx, hy, hz), (-hx, hy, hz)),
        "south": ((hx, -hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (hx, -hy, hz)),
        "east": ((hx, hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (hx, hy, hz)),
        "west": ((-hx, -hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (-hx, -hy, hz)),
        "top": ((-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)),
        "bottom": ((-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz)),
    }
    normals = {"north": (0, 1, 0), "south": (0, -1, 0), "east": (1, 0, 0),
               "west": (-1, 0, 0), "top": (0, 0, 1), "bottom": (0, 0, -1)}
    for face, points in corners.items():
        H.quad(v, i, [(cx + x, cy + y, cz + z) for x, y, z in points],
               normals[face], uv)


def obelisk(v, i):
    """A waygate: a stepped plinth under a tapering pillar."""
    H.bed(v, i, 0.86, 0.06)
    H.prism(v, i, 0.06, 0.30, 0.72, 0.62, 8, uv=H.UV_BED)
    H.cap(v, i, 0.30, 0.62, 8, uv=H.UV_BED)
    H.prism(v, i, 0.30, 2.55, 0.34, 0.20, 6, uv=H.UV_STALK)
    H.prism(v, i, 2.55, 3.05, 0.20, 0.02, 6, uv=H.UV_BLOOM)
    for step in range(4):
        angle = 1.5708 * step + 0.4
        H.blade(v, i, (0.18 * np.cos(angle), 0.18 * np.sin(angle)), angle,
                0.30, 0.12, 1.85, 0.10, uv=H.UV_BLOOM, segments=2)


def notice_board(v, i):
    """An information board: two posts, a planked face and a shingle roof."""
    H.bed(v, i, 0.68, 0.05)
    for side in (-0.62, 0.62):
        H.prism(v, i, 0.05, 1.90, 0.09, 0.075, 6, (side, 0.0), H.UV_STALK)
    _box(v, i, (0.0, 0.02, 1.22), (1.32, 0.10, 0.92), H.UV_BED)
    for plank in (-0.40, 0.0, 0.40):
        _box(v, i, (plank, -0.06, 1.22), (0.34, 0.05, 0.84), H.UV_BLOOM)
    H.prism(v, i, 1.74, 2.02, 0.86, 0.52, 4, uv=H.UV_BED)
    H.cap(v, i, 2.02, 0.52, 4, uv=H.UV_BED)


def storage_cache(v, i):
    """A wayfarer's cache: a banded chest with a domed lid."""
    H.bed(v, i, 0.72, 0.05)
    _box(v, i, (0.0, 0.0, 0.38), (1.28, 0.78, 0.66), H.UV_BED)
    H.prism(v, i, 0.71, 0.94, 0.66, 0.40, 8, uv=H.UV_BLOOM)
    H.cap(v, i, 0.94, 0.40, 8, uv=H.UV_BLOOM)
    for band in (-0.42, 0.42):
        _box(v, i, (band, 0.0, 0.38), (0.11, 0.82, 0.70), H.UV_STALK)
    _box(v, i, (0.0, -0.40, 0.52), (0.20, 0.09, 0.22), H.UV_STALK)


def field_station(v, i):
    """A crafting station: a bench, an anvil block and a stone hearth."""
    H.bed(v, i, 0.88, 0.05)
    _box(v, i, (-0.10, 0.0, 0.86), (1.50, 0.72, 0.12), H.UV_BED)
    for x in (-0.72, 0.60):
        for y in (-0.28, 0.28):
            H.prism(v, i, 0.05, 0.80, 0.08, 0.07, 5, (x, y), H.UV_STALK)
    H.prism(v, i, 0.05, 0.52, 0.26, 0.20, 6, (0.78, 0.30), H.UV_BED)
    _box(v, i, (0.78, 0.30, 0.66), (0.62, 0.26, 0.24), H.UV_STALK)
    H.prism(v, i, 0.05, 0.44, 0.44, 0.40, 7, (0.62, -0.46), H.UV_BED)
    H.cap(v, i, 0.44, 0.40, 7, (0.62, -0.46), H.UV_BLOOM)
    for tool in (-0.44, -0.14, 0.16):
        H.prism(v, i, 0.98, 1.20, 0.05, 0.035, 5, (tool, 0.06), H.UV_BLOOM)


def water_well(v, i):
    """A water source: a coped ring with a windlass under a small roof."""
    H.bed(v, i, 0.90, 0.05)
    H.prism(v, i, 0.05, 0.72, 0.70, 0.66, 10, uv=H.UV_BED)
    H.prism(v, i, 0.72, 0.84, 0.72, 0.60, 10, uv=H.UV_BLOOM)
    H.cap(v, i, 0.84, 0.60, 10, uv=H.UV_BLOOM)
    for side in (-0.58, 0.58):
        H.prism(v, i, 0.80, 1.86, 0.08, 0.065, 5, (side, 0.0), H.UV_STALK)
    H.prism(v, i, 1.62, 2.00, 0.86, 0.44, 4, uv=H.UV_BED)
    H.cap(v, i, 2.00, 0.44, 4, uv=H.UV_BED)
    _box(v, i, (0.0, 0.0, 1.58), (1.10, 0.16, 0.16), H.UV_STALK)


def practice_target(v, i):
    """A training post: a straw butt on a stake with a scored face."""
    H.bed(v, i, 0.56, 0.05)
    H.prism(v, i, 0.05, 1.06, 0.11, 0.09, 6, uv=H.UV_STALK)
    H.prism(v, i, 1.02, 1.14, 0.16, 0.54, 10, uv=H.UV_BED)
    H.prism(v, i, 1.14, 1.62, 0.54, 0.54, 10, uv=H.UV_BED)
    H.prism(v, i, 1.62, 1.72, 0.54, 0.18, 10, uv=H.UV_BED)
    H.cap(v, i, 1.72, 0.18, 10, uv=H.UV_BLOOM)
    for ring, radius in ((1.38, 0.34), (1.38, 0.16)):
        H.prism(v, i, ring - 0.02, ring + 0.02, radius, radius, 10,
                (0.0, -0.56), H.UV_BLOOM)


def brazier(v, i):
    """A scenery effect: a footed bowl with a standing flame."""
    H.bed(v, i, 0.52, 0.05)
    for leg in range(3):
        angle = 2.0944 * leg + 0.5
        H.prism(v, i, 0.05, 0.78, 0.09, 0.06, 5,
                (0.28 * np.cos(angle), 0.28 * np.sin(angle)), H.UV_STALK)
    H.prism(v, i, 0.74, 1.06, 0.26, 0.54, 10, uv=H.UV_BED)
    H.prism(v, i, 1.06, 1.14, 0.54, 0.50, 10, uv=H.UV_BLOOM)
    for tongue in range(5):
        angle = 1.2566 * tongue + 0.3
        top = 1.14 + 0.52 + 0.18 * (tongue % 3)
        H.prism(v, i, 1.06, top, 0.17, 0.02, 5,
                (0.18 * np.cos(angle), 0.18 * np.sin(angle)), H.UV_BLOOM,
                lean=(np.cos(angle) * 0.10, np.sin(angle) * 0.10))


def standing_stone(v, i):
    """A waystone: a cairn footing under a rough stone with a carved band."""
    H.bed(v, i, 0.80, 0.06)
    for stone in range(5):
        angle = 1.2566 * stone + 0.7
        H.prism(v, i, 0.06, 0.26 + 0.07 * (stone % 3), 0.21, 0.15, 5,
                (0.50 * np.cos(angle), 0.50 * np.sin(angle)), H.UV_BED)
    H.prism(v, i, 0.06, 1.04, 0.44, 0.38, 5, uv=H.UV_BED)
    H.prism(v, i, 1.18, 2.06, 0.36, 0.24, 5, uv=H.UV_BED, lean=(0.05, 0.03))
    H.cap(v, i, 2.06, 0.24, 5, (0.05, 0.03), H.UV_BED)
    # The band the road home is cut into, which is the whole point of a
    # waystone and the one part of it a player looks at.
    H.prism(v, i, 1.04, 1.18, 0.46, 0.46, 5, uv=H.UV_BLOOM)


def strongbox(v, i):
    """A run's cache: an iron-strapped stone coffer on a flagged plinth."""
    H.bed(v, i, 0.74, 0.05)
    _box(v, i, (0.0, 0.0, 0.12), (1.36, 0.92, 0.14), H.UV_BED)
    _box(v, i, (0.0, 0.0, 0.48), (1.16, 0.74, 0.58), H.UV_BED)
    _box(v, i, (0.0, 0.0, 0.80), (1.22, 0.80, 0.10), H.UV_STALK)
    for strap in (-0.36, 0.36):
        _box(v, i, (strap, 0.0, 0.48), (0.10, 0.78, 0.62), H.UV_STALK)
    # The lock plate: a cache opens once for each of the party, so it reads as
    # something counted rather than something forced.
    _box(v, i, (0.0, -0.39, 0.52), (0.26, 0.08, 0.26), H.UV_BLOOM)
    _box(v, i, (0.0, -0.42, 0.52), (0.10, 0.05, 0.10), H.UV_BED)


def barred_gate(v, i):
    """A gauntlet gate: a ring of heavy bars under a banded lintel.

    The six flavours the server states - roots, a portcullis, a jade door, a
    stone slab, a wall of ice, an iron bar gate - are one role on the wire, so
    they are one prop, and the shape has to say "shut" rather than say which.

    It is a ring rather than a wall because `MapObject3D` yaws every prop by
    its object id: the server sends a tile and no facing, so a barrier built
    across one axis would stand at a random angle to the corridor it closes.
    A ring closes the tile from every approach and reads the same at any yaw.
    """
    H.bed(v, i, 0.96, 0.06)
    H.prism(v, i, 0.06, 0.22, 0.92, 0.86, 12, uv=H.UV_BED)
    for bar in range(12):
        angle = 0.5236 * bar
        H.prism(v, i, 0.20, 2.32, 0.09, 0.07, 4,
                (0.80 * np.cos(angle), 0.80 * np.sin(angle)), H.UV_STALK)
    H.prism(v, i, 2.20, 2.44, 0.90, 0.90, 12, uv=H.UV_BLOOM)
    H.prism(v, i, 2.44, 2.62, 0.90, 0.72, 12, uv=H.UV_BED)
    H.cap(v, i, 2.62, 0.72, 12, uv=H.UV_BED)


# role, label the server derives from it, prop, (base, accent, bloom), foliage
INTERACTIVES = (
    ("portal", "Portal", obelisk,
     ((72, 84, 110), (126, 142, 176), (128, 214, 240)), False),
    ("information", "Information", notice_board,
     ((92, 70, 48), (140, 110, 74), (226, 214, 186)), False),
    ("storage", "Storage", storage_cache,
     ((84, 62, 42), (132, 100, 64), (168, 140, 84)), False),
    ("crafting_station", "Crafting Station", field_station,
     ((78, 68, 60), (124, 110, 96), (150, 92, 54)), False),
    ("water_source", "Water Source", water_well,
     ((94, 98, 100), (146, 152, 156), (96, 158, 178)), False),
    ("training", "Training", practice_target,
     ((104, 88, 56), (170, 148, 92), (188, 78, 62)), False),
    ("scenery_effect", "Scenery Effect", brazier,
     ((70, 72, 80), (118, 122, 132), (108, 178, 232)), False),
    ("waystone", "Waystone", standing_stone,
     ((88, 88, 94), (140, 142, 148), (198, 204, 210)), False),
    ("cache", "Cache", strongbox,
     ((66, 68, 72), (112, 114, 120), (166, 138, 78)), False),
    ("gate", "Gate", barred_gate,
     ((58, 56, 60), (102, 100, 108), (132, 112, 76)), False),
)

# Roles whose object is already standing in the world: the region packages
# author a secret's door - the hollow tree, the cellar hatch, the cracked slab
# - as `Secret_*` nodes in the region mesh, at the tile the server states. The
# client places nothing on those and draws no ring under them, because a ring
# on a hollow tree is both a duplicate and a sign saying "secret here".
MAP_AUTHORED = {"Secret": "secret"}


def build_interactives(client_root: Path, scratch: Path) -> dict:
    output = client_root / CLIENT_INTERACTIVE_DIR
    models: dict[str, dict] = {}
    roles: dict[str, str] = {}
    imported = imported_interactive_entries(
        client_root, CLIENT_INTERACTIVE_DIR,
        {role: label for role, label, *_rest in INTERACTIVES})
    for role, label, build, colours, foliage in INTERACTIVES:
        if role in imported:
            models[role] = imported[role]
        else:
            stats = write_object_glb(output / f"{role}.glb", role, build, colours,
                                     foliage=foliage, scratch=scratch)
            models[role] = {"scene": f"res://{CLIENT_INTERACTIVE_DIR}/{role}.glb",
                            "label": label, **stats}
        roles[label] = role
    return {"models": models, "roles": roles, "mapAuthored": MAP_AUTHORED}


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--client", type=Path,
                        default=repo_root / "godot-client")
    arguments = parser.parse_args()
    client = arguments.client
    scratch = client / CLIENT_HARVESTABLE_DIR / "_material.png"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    (client / CLIENT_INTERACTIVE_DIR).mkdir(parents=True, exist_ok=True)

    # The imported table is checked before any GLB is written: a row that
    # shadowed a procedural id would otherwise see its committed GLB
    # overwritten by the procedural one before the clash was noticed.
    check_rows({rid for rid, *_rest in harvest_entries()})
    imported_interactive_entries(
        client, CLIENT_INTERACTIVE_DIR,
        {role: label for role, label, *_rest in INTERACTIVES})
    harvest = merge_imported(build_harvestables(client, scratch), client,
                             CLIENT_HARVESTABLE_DIR)
    interactive = build_interactives(client, scratch)
    registry = {
        "schemaVersion": 1,
        "harvestables": harvest,
        "interactives": interactive,
    }
    if authored := authored_doorways():
        registry["authoredObjects"] = authored
    path = client / REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    imported = [m for m in harvest["models"].values() if m.get("imported")]
    triangles = sum(m["triangles"] for m in harvest["models"].values()
                    if not m.get("imported"))
    print(f"{len(harvest['models']) - len(imported)} harvest node models, "
          f"{triangles} triangles total")
    print(f"{len(imported)} imported harvest node models, "
          f"{sum(m['triangles'] for m in imported)} triangles total")
    print(f"{len(interactive['models'])} interactive props, "
          f"{sum(m['triangles'] for m in interactive['models'].values())} "
          "triangles total")
    print(f"registry: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
