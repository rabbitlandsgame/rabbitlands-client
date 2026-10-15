"""Seat the south-west isle's kit in its territory kit: the generated batch and the shared models.

Two kinds of model become territory prototypes (`godot-client/world_authoring/regions/sw_isle/assets/
prototypes/kit-*.glb`), which the Territories palette offers when the isle is open:

- GENERATED: the 20 Meshy pieces made for the isle (batch 1, the N8 redesign and the N20 landing beacon; N18 r1
  only as the buried fallback cliff piece). They are read from the folder seat_fixes.py writes (copies of the accepted,
  normalised kits with the local seating fixes applied). Node transforms are baked into the vertices first
  (some deliveries size models with wrapper nodes; these have none, so the bake is a no-op), then each model
  is checked against its size in SIZES (the normaliser already scaled it, so the factor is 1 and the
  geometry is left exactly as fixed) and stood by its origin kind:
    - "base": the normaliser's origin is kept in plan (a tower or trunk axis, not always the bounds centre)
      and the lowest point stands on 0;
    - "waterline": the WATERLINE set (N10 green lighthouse, N12 causeway arch span, N13 trestle pier span,
      N14 ferry ship) keeps its origin as delivered: the waterline or deck top is at 0 and the hull, piers
      or platform foot reach below it.
  Textures are re-encoded (JPEG, quality 88) at their delivered size and written once, content-addressed,
  to the territory's `assets/textures/`, and referenced by URI. Deck and platform tops stay in their
  `Walk_` child node, and the collider primitives and seating notes stay in the root node's extras.
- SHARED: the 95 owner-approved reuse models (confirmation pack section 4), the polish pass's 7 and the
  garden town's 8 are copied byte for byte from the region kit that seated them on this branch (SHARED
  below), with the textures they reference. Every
  model keeps the size and origin it has there. SHARED_TINTS (the two olives) only multiplies their
  materials' baseColorFactor, toward the isle's foliage greens.
- VARIANTS: pieces derived from a prepared generated piece by a linear map, with no new texture. The west
  gate's stone ramp (owner's decision: built from the N12 causeway arch spans) climbs at 0.37-0.53, where a
  level module would leave its deck floating up to 5.6 m and a rotated one would lean its piers 28 degrees.
  Each ramp module is the prepared N12 scaled along its span (X) and sheared up the grade (Y += grade * X)
  about its deck-top origin: the deck, parapets and arch crowns follow the grade and the piers stay vertical
  (rampant arches). The open cut ends of the 12 m module are capped with flat stone faces, so the ramp's
  bottom end does not show a hollow section. Normals follow the inverse transpose of the map; the `Walk_`
  deck child is sheared with the rest and stays the walk surface.
- DERIVED: the coast's deck-dressing pieces (coast design, slice 2), cut from a prepared generated piece
  with no new texture, so a causeway or pier reaches the ground or seabed without a floating foot:
    - the causeway tier (N12 without its parapets: every face of the piece whose centre stands above the
      deck top, +0.05 m, is dropped): stacked level under a top module, 8 m per tier, so the arcade
      continues down to the ground. Its deck child is renamed out of `Walk_`: a tier is never walked;
    - the long trestle spans (N13 with its four bent posts lengthened: the post feet, every vertex below
      -3.0 m, move from -6.0 m down to -24 or -40 m; braces and deck unchanged) for the seabed trenches
      under the piers. The `Walk_` deck stays the walk surface.
  The polish fix stage adds the lawn palms: the shared beach palms 1-3 without their sand-mound base (faces
  centred under 1.0 m and more than 1.2 m from the trunk axis dropped), for palms on grass, same textures.
    - the castle revetment (polish, fix plan P7): N3 without its merlons (faces centred above the 5.0 m wall
      walk, +0.05 m, are dropped), a plain 11.2 m x 5.0 m course of the curtain wall's own masonry, stacked
      down the castle pad's scarp and the west-gate ditch walls under the town wall, its back buried.
- GATES: an N12 module with an opening in one parapet, for the span whose parapet sealed ground off (owner's call,
  2026-10-04: AC-4(b) patch 406, the beach SE of the B14 causeway's west end, is reached through a gap in arch span
  061's SE parapet at the abutment, a clean opening with dressed ends). From the prepared N12: the parapet is taken away
  between the opening's ends and from under two new pier posts, one at each side (the module's own end half-post and
  its mirror, as two modules' halves make one over a pier; the face each turns to the opening, hidden by the parapet
  until now, takes the posts' outer-face texture: whole faces swapped, as the atlas keeps each triangle's texture in its
  own island); beyond the posts the parapet stays, out to the module's end posts. In the opening the deck's own paving
  runs out to the slab edge (a copy of it two 1.40 m courses further in) and meets the deck on a shared seam: both are
  cut at each other's seam corners and the copy takes the deck's own corners, so there is no crack and no T-junction;
  the slab top it covers stays under it, just below. A step stone stands below the opening by the low post, where the
  ground falls away: a block of the parapet's own stone (tread: the coping's flat top; front: the faces the parapet
  turns outward; ends: the post's outer face; all whole faces swapped onto the block, snapped to its edges) whose foot
  is below the ground everywhere under it. The opened slab edge's kerb band (its outer face above 1.3 m under the deck)
  and the step stone are in the `Walk_` child: the served grid walks the paving and the tread and steps off the slab
  edge (as body faces, the kerb and the step's sides would close the half-cells beside them); below the band the
  spandrel and the arch ring stay solid. No new texture; every face keeps the module's material.

`python prepare_meshy_kit.py --input <work-output/continent-v2/meshy/seated>` writes the kit and
`prepare-meshy-kit.json` (the SHA-256 of every input and output); `--check` confirms the committed files are
what the recorded inputs produce.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import struct
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
REGIONS = CLIENT / "godot-client/world_authoring/regions"
PROTOTYPES = REGIONS / "sw_isle/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
RECORD = HERE / "prepare-meshy-kit.json"

# name -> (piece id, measure, metres, texture px, origin kind). "height" is the top above the base,
# "length" the X extent, "width" the larger plan extent.
SIZES = {
    "sw-palace-keep": ("N1", "height", 32.0, 2048, "base"),
    "sw-wall-tower-round": ("N2", "height", 14.005, 1024, "base"),
    "sw-curtain-wall": ("N3", "length", 11.19, 2048, "base"),
    "sw-wall-bastion": ("N4", "height", 12.0, 2048, "base"),
    "sw-gatehouse": ("N5", "height", 17.0, 2048, "base"),
    "sw-domed-temple": ("N6", "height", 16.5, 2048, "base"),
    "sw-townhouse-blue": ("N7", "height", 10.5, 2048, "base"),
    "sw-townhouse-dome-arcade": ("N8", "height", 11.5, 2048, "base"),
    "sw-lighthouse-red": ("N9", "height", 23.0, 2048, "base"),
    "sw-lighthouse-green": ("N10", "width", 24.12, 2048, "waterline"),
    "sw-harbour-tower": ("N11", "height", 12.0, 1024, "base"),
    "sw-causeway-arch-span": ("N12", "length", 12.0, 2048, "waterline"),
    "sw-trestle-pier-span": ("N13", "length", 8.0, 2048, "waterline"),
    "sw-ferry-ship": ("N14", "length", 22.0, 2048, "waterline"),
    "sw-broadleaf-tree-a": ("N15", "height", 11.0, 1024, "base"),
    "sw-broadleaf-tree-b": ("N16", "height", 14.0, 1024, "base"),
    "sw-blossom-tree": ("N17", "height", 10.0, 2048, "base"),
    "sw-sea-cliff-face": ("N18r1", "height", 18.0, 2048, "base"),
    "sw-sea-cliff-corner": ("N19", "height", 18.0, 2048, "base"),
    # the landing beacon (game-look workflow, one paid task): its crystal is a second, emissive primitive
    "sw-landing-beacon": ("N20", "height", 13.5, 1024, "base"),
}
# delivered with their waterline or deck top, not their lowest point, at the origin
WATERLINE = {name for name, entry in SIZES.items() if entry[4] == "waterline"}

# Shared models, by confirmation-pack group: territory name -> region kit it is copied from (the island's
# own style first: Westhaven's harbour town, Crownwater's domes and boats, Ssarathi's beach palms).
# A model whose source file is not "kit-<name>.glb" says so after a colon.
SHARED = {
    # trees and shrubs (18)
    "beach-palm-tree-1": "ssarathi_ruins", "beach-palm-tree-2": "ssarathi_ruins",
    "beach-palm-tree-3": "ssarathi_ruins", "beach-palm-tree-4": "ssarathi_ruins",
    "fan-palm-tree-1": "manymouth_delta", "olive-tree-1": "westhaven", "olive-tree-2": "westhaven",
    "cypress-tree-1": "westhaven", "umbrella-pine-tree-1": "westhaven", "lemon-tree-1": "westhaven",
    "banyan-tree-1": "manymouth_delta", "flame-tree-1": "manymouth_delta", "tree-fern-1": "ssarathi_ruins",
    "tree-fern-2": "ssarathi_ruins", "bougainvillea-shrub-1": "westhaven", "flower-shrub-1": "westhaven",
    "flower-shrub-2": "westhaven", "flower-shrub-3": "four_gates",
    # ground cover (14)
    "flower-meadow-1": "westhaven", "flower-meadow-2": "westhaven", "flower-meadow-3": "westhaven",
    "flower-meadow-4": "four_gates", "undergrowth-1": "ssarathi_ruins", "undergrowth-2": "verdant_stair",
    "undergrowth-3": "ssarathi_ruins", "undergrowth-4": "verdant_stair", "undergrowth-5": "ssarathi_ruins",
    "jungle-undergrowth-1": "ssarathi_ruins", "jungle-undergrowth-2": "ssarathi_ruins",
    "beach-flower-mat-1": "westhaven", "dune-grass-1": "westhaven", "dune-grass-2": "westhaven",
    # coast and rock (14)
    "coastal-rock-1": "westhaven", "coastal-rock-2": "westhaven", "coastal-rock-3": "westhaven",
    "coastal-boulders-1": "sunmane_steppe", "coastal-boulders-2": "sunmane_steppe",
    "coastal-boulders-3": "sunmane_steppe", "coastal-boulders-4": "sunmane_steppe",
    "sea-stack-1": "westhaven", "sea-stack-2": "westhaven", "beach-rocks-1": "westhaven",
    "driftwood-1": "westhaven", "driftwood-2": "westhaven", "kelp-wrack-1": "grey_moors",
    "shell-scree-1": "westhaven",
    # harbour and boats (18)
    "fishing-boat-1": "westhaven", "fishing-boat-2": "westhaven", "rowing-boat-1": "westhaven",
    "sloop-1": "westhaven", "caravel-1": "westhaven", "mooring-buoy-1": "westhaven",
    "lamp-buoy-1": "crownwater", "mooring-posts-1": "westhaven", "quay-steps-1": "westhaven",
    "stone-landing-stage-1": "mirrorhold", "harbour-crane-1": "westhaven", "fish-crates-1": "westhaven",
    "lobster-pots-1": "westhaven", "rope-coils-1": "westhaven", "net-drying-frame-1": "westhaven",
    "fisher-hut-1": "westhaven", "net-shed-1": "manymouth_delta", "sea-wall-segment-1": "crownwater",
    # town and village (21)
    "haven-townhouse-1": "westhaven", "haven-townhouse-2": "westhaven", "haven-townhouse-3": "westhaven",
    "merchant-house-1": "westhaven", "corner-shop-1": "four_gates", "wallside-rowhouse-1": "four_gates",
    "market-canopy-0": "sunmane_steppe", "market-canopy-1": "sunmane_steppe",
    "market-canopy-2": "sunmane_steppe", "produce-stall-1": "four_gates", "flower-cart-1": "westhaven",
    "blue-dome-kiosk-1": "crownwater", "teal-dome-gazebo-1": "crownwater", "crown-fountain-1": "crownwater",
    "stone-well-1": "westhaven", "lantern-post-1": "whitehorn_range", "notice-board-1": "westhaven",
    "stone-bench-1": "westhaven", "garden-urn-1": "westhaven", "terracotta-pots-1": "westhaven",
    "citrus-planter-1": "crownwater",
    # farms (9)
    "vineyard-rows-1": "westhaven", "cabbage-rows-1": "four_gates", "wheat-stooks-1": "westhaven",
    "windmill-1": "westhaven", "dovecote-1": "westhaven", "beehive-skeps-1": "four_gates",
    "split-rail-fence-1": "four_gates", "drystone-dyke-1": "grey_moors", "drystone-dyke-2": "grey_moors",
    # beam marker (1 model in two parts): Four Gates' composed sanctuary beacon and its flame
    "sanctuary-beacon-1": "four_gates:sanctuary-beacon-c4a49eda0750.glb",
    "sanctuary-beacon-flame-1": "four_gates:sanctuary-beacon-flame-22cd9b2b2a64.glb",
    # polish (fix plan P7 and the slice-2 visual review's street-life items), 0 credits, from existing kits: the
    # L12 gorge lip's waterfall sheet (Ssarathi's), harbour banners (Crownwater's gilt poles), and harbour and
    # street clutter (Westhaven's barrels and crates, Four Gates' cart and sacks)
    "waterfall-sheet-1": "ssarathi_ruins:waterfall-east-0b8f59a222aa.glb",
    "harbour-banner-1": "crownwater:prop-banner-harbour-0-9ceb5d656d77.glb",
    "harbour-banner-2": "crownwater:prop-banner-harbour-1-97933fbe1b3a.glb",
    "barrel-stack-1": "westhaven", "crate-stack-1": "westhaven",
    "apple-cart-1": "four_gates", "feed-sacks-1": "four_gates",
    # garden town (polish, garden-town design v2, 2026-10-02), 0 credits, from existing kits: Crownwater's palace
    # garden pieces (balustrade on the keep terrace's front, parterre hedges, the east walk's pergolas, rose arches
    # at walk and court mouths, clipped topiary cones, flower planters, the rear lawn's reflecting pool) and Four
    # Gates' sundial plinth for the north court
    "marble-balustrade-1": "crownwater", "garden-hedge-1": "crownwater", "garden-pergola-1": "crownwater",
    "rose-arch-1": "crownwater", "topiary-cone-1": "crownwater", "flower-planter-1": "crownwater",
    "sundial-plinth-1": "four_gates", "reflecting-pool-1": "crownwater",
}

# Derived pieces: name -> (prepared generated piece, piece id, X scale, grade). The west-gate ramp's three
# modules (castle-town design, slice 2): two over the ditch at 0.5282 and one into the gate at 0.3708, each
# 10.558 m in plan (X scale 0.8799 of the 12.0 m module).
# Shared models whose material colour is multiplied here (sw_isle only; the source region keeps its own): the
# slice-2 visual review found the Westhaven olives reading as dead grey crumpled paper beside the isle's other
# foliage. Their base colour (median rgb 0.592, 0.561, 0.427 and 0.541, 0.482, 0.404; S 0.15-0.17, L 0.47-0.51,
# trunk and leaves in one material) is pulled to a sage olive green, median about (0.40, 0.45, 0.28), H 78,
# S 0.23, L 0.36, beside the umbrella pine (L 0.29, S 0.29) and the undergrowth (L 0.28-0.40): sRGB factors
# (0.676, 0.802, 0.656) and (0.739, 0.934, 0.693). glTF's baseColorFactor is linear and multiplies the decoded
# texture, so the factor stored is the sRGB factor ** 2.2. It goes in every material's baseColorFactor; textures
# and geometry are unchanged.
SHARED_TINTS = {
    "olive-tree-1": (0.423, 0.615, 0.396),
    "olive-tree-2": (0.514, 0.861, 0.446),
}

VARIANTS = {
    "sw-causeway-arch-ramp-g053": ("sw-causeway-arch-span", "N12-ramp", 0.8799, 0.5282),
    "sw-causeway-arch-ramp-g037": ("sw-causeway-arch-span", "N12-ramp", 0.8799, 0.3708),
}

# Coast deck-dressing pieces: name -> (prepared generated piece, piece id, operation, value).
#   "drop_above": faces of the piece's own mesh whose centre is above `value` are dropped (a parapet-less tier);
#   "post_foot": vertices of the piece's own mesh below -3.0 m move down by (value - (-6.0)) (longer posts);
#   "trim_top": as drop_above, for a base-origin piece (the castle revetment: N3 cut at its wall walk);
#   "trim_base": faces centred under value[0] m and more than value[1] m from the Y axis are dropped (a shared beach
#                palm without its sand-mound base; the base may be a shared model).
DERIVED = {
    "sw-causeway-arch-tier": ("sw-causeway-arch-span", "N12-tier", "drop_above", 0.05),
    "sw-trestle-pier-span-long24": ("sw-trestle-pier-span", "N13-long24", "post_foot", -24.0),
    "sw-trestle-pier-span-long40": ("sw-trestle-pier-span", "N13-long40", "post_foot", -40.0),
    "sw-curtain-revetment": ("sw-curtain-wall", "N3-revetment", "trim_top", 5.05),
    # polish fix stage: the shared beach palms without their sand-mound base (faces centred under 1.0 m and more
    # than 1.2 m from the trunk axis dropped), for palms planted on lawns (visual review D11), same textures
    "beach-palm-tree-1-clear": ("beach-palm-tree-1", "palm1-clear", "trim_base", [1.0, 1.2]),
    "beach-palm-tree-2-clear": ("beach-palm-tree-2", "palm2-clear", "trim_base", [1.0, 1.2]),
    "beach-palm-tree-3-clear": ("beach-palm-tree-3", "palm3-clear", "trim_base", [1.0, 1.2]),
}
N13_FOOT = -6.0
N13_POST_BELOW = -3.0

# Gate pieces: name -> (prepared generated piece, piece id, opened side, the opening (module X from, to), the step stone
# (module X range, its tread and its foot)). The B14 west abutment span 061 (owner, 2026-10-04) opens its -Z (SE)
# parapet between X -2.5 and 3.0, a pier post at each side: the served fold then joins the deck to patch 406 three tiles
# wide (rows 1366-1368; the low post bounds it on one side, the high post on the other). The high post stands where the
# bank comes up to the deck (level with it at the slab edge at X 2.0, up to 0.4 m over it by X 3.0); from it to the
# module's end the parapet stays and runs into the bank as before, so no paving lies under the grass beyond it. It can
# stand no nearer: a post from X 2.0 or 2.5 closes the deck tiles (1518, 1366) and (1519, 1366) beside the opening's
# third row, and the gap is 2 tiles (what-if exports, 2026-10-04). The step stone (tread 0.5 m under the
# deck, foot 1.6 m under it, below the ground everywhere under it) carries row 1368 down to ground 0.9-1.5 m under the
# deck.
GATES = {
    "sw-causeway-arch-span-gate": ("sw-causeway-arch-span", "N12-gate", "-z", (-2.5, 3.0),
                                   {"x": [-2.5, 0.0], "top": -0.5, "foot": -1.6}),
}
GATE_POST_X0 = 5.2       # the module end's half-post: faces with every corner at X >= this ...
GATE_POST_FACE = 5.23    # ... its inner face stands here
GATE_END_X = 6.0         # the module end (the half-post is open there)
GATE_POST_WIDTH = 2 * (GATE_END_X - GATE_POST_FACE)   # a full pier post: two end half-posts
GATE_PARAPET_Z = 4.9     # parapet and post faces lie at |Z| >= this
GATE_SLAB_TOP = 0.025    # a face whose highest corner is under this is slab (top, chamfer, outer face), not parapet
GATE_SLAB_EDGE = (5.9, 6.15)   # |Z| of the slab's outer face
GATE_EDGE_Z = 6.05       # the slab's outer edge at its top
GATE_EDGE_BAND = -1.3    # in the opening the slab's outer face above this (its kerb band over the bank) is stepped off
GATE_PAVING_SEAM = 4.78  # in the opening the deck is cut here (|Z|: the deck's own edge comes in to 4.79 there, so a
                         # cut further out would leave a slit between it and the copy) and its paving copied out ...
GATE_PAVING_SHIFT = 2.80  # ... to the slab edge from two 1.40 m paving courses further in
GATE_BACKING_DROP = 0.02  # the slab top under the copied paving stays, this far under the copy's lowest corner
GATE_STEP_GAP = 0.01     # the step stone stands this far out from the slab edge ...
GATE_STEP_DEPTH = 0.78   # ... and this deep (the coping's width)
GATE_SWAP_SNAP = 0.06    # a swapped face's corner this close to its rectangle's edge is put on the edge
GATE_STEP_RELIEF = 0.02  # the step's front keeps the parapet's relief at this scale (the coping edge 4 mm proud)


def _read(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError(f"{path.name} is not a binary glTF")
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    offset = 20 + json_length
    binary_length = struct.unpack_from("<I", data, offset)[0]
    return document, data[offset + 8:offset + 8 + binary_length]


def _view(document: dict, binary: bytes, index: int) -> bytes:
    view = document["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def _positions(document: dict, binary: bytes, accessor_index: int) -> np.ndarray:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    if accessor.get("componentType") != 5126 or accessor["type"] != "VEC3" or view.get("byteStride"):
        raise ValueError("expected tightly packed float VEC3 positions")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return np.frombuffer(binary, dtype="<f4", count=accessor["count"] * 3, offset=start).reshape(-1, 3)


def _texture(payload: bytes, mime: str, size: int) -> tuple[bytes, str]:
    image = Image.open(io.BytesIO(payload))
    image.load()
    if max(image.size) > size:
        image = image.resize((size, size) if image.size[0] == image.size[1]
                             else (size, round(size * image.size[1] / image.size[0])), Image.LANCZOS)
    out = io.BytesIO()
    if mime == "image/png":
        image.save(out, "PNG", optimize=True)
    else:
        image.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue(), mime


def _local_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    out = np.eye(4)
    out[:3, :3] = rotation * np.array(node.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    out[:3, 3] = node.get("translation", [0.0, 0.0, 0.0])
    return out


def _bake_node_transforms(document: dict, binary: bytes) -> bytes:
    """Moves every mesh node's world transform into its vertices (positions, and normals and tangents
    by the matching linear maps) and leaves every node untransformed. Some deliveries size a model with
    wrapper nodes rather than in its vertices; baked, every model is measured as it looks."""
    world: dict[int, np.ndarray] = {}

    def visit(index: int, parent: np.ndarray) -> None:
        world[index] = parent @ _local_matrix(document["nodes"][index])
        for child in document["nodes"][index].get("children", []):
            visit(child, world[index])

    for root in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4))
    out = bytearray(binary)
    done: dict[int, int] = {}
    for index, node in enumerate(document["nodes"]):
        if "mesh" not in node:
            continue
        matrix = world.get(index, np.eye(4))
        if np.array_equal(matrix, np.eye(4)):
            continue                                  # nothing to bake; leave the arrays untouched
        linear = matrix[:3, :3]
        normal_map = np.linalg.inv(linear).T
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            for key, accessor_index in primitive["attributes"].items():
                if key not in ("POSITION", "NORMAL", "TANGENT"):
                    continue
                if accessor_index in done:
                    if done[accessor_index] != index:
                        raise ValueError("a vertex array shared by two mesh nodes cannot be baked")
                    continue
                done[accessor_index] = index
                accessor = document["accessors"][accessor_index]
                view = document["bufferViews"][accessor["bufferView"]]
                columns = 4 if key == "TANGENT" else 3
                if accessor.get("componentType") != 5126 or view.get("byteStride"):
                    raise ValueError(f"expected tightly packed float {key}")
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                values = np.frombuffer(bytes(out[start:start + accessor["count"] * columns * 4]),
                                       dtype="<f4").reshape(-1, columns).astype(np.float64)
                if key == "POSITION":
                    values = values @ linear.T + matrix[:3, 3]
                    accessor["min"] = [float(v) for v in values.min(axis=0)]
                    accessor["max"] = [float(v) for v in values.max(axis=0)]
                else:
                    turned = values[:, :3] @ (normal_map if key == "NORMAL" else linear).T
                    turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-12)
                    values[:, :3] = turned
                    if key == "TANGENT" and np.linalg.det(linear) < 0:
                        values[:, 3] = -values[:, 3]
                out[start:start + values.size * 4] = values.astype("<f4").tobytes()
    for node in document["nodes"]:
        for key in ("matrix", "translation", "rotation", "scale"):
            node.pop(key, None)
    return bytes(out)


def prepare(source: Path, name: str) -> tuple[bytes, dict[str, bytes], dict]:
    """A generated piece: the prototype's bytes, the texture files it references, and what was measured."""
    piece, measure, metres, texture_size, origin = SIZES[name]
    document, binary = _read(source)
    binary = _bake_node_transforms(document, binary)
    position_accessors = sorted({primitive["attributes"]["POSITION"]
                                 for mesh in document["meshes"] for primitive in mesh["primitives"]})
    points = np.concatenate([_positions(document, binary, index) for index in position_accessors])
    low, high = points.min(axis=0).astype(np.float64), points.max(axis=0).astype(np.float64)
    size = high - low
    measured = {"height": high[1] if origin == "base" else size[1], "length": size[0],
                "width": max(size[0], size[2])}[measure]
    scale = metres / measured
    if abs(scale - 1.0) > 0.01:
        raise ValueError(f"{name}: measured {measured:.3f} m against {metres} m; the fixed copy is not at size")
    scale = 1.0 if abs(scale - 1.0) < 1e-3 else scale
    # The normaliser placed the origin (a tower or trunk axis, or the waterline / deck top): keep it in
    # plan; a "base" piece only has its lowest point stood on 0.
    rise = 0.0 if name in WATERLINE else 0.0 - float(low[1])
    replaced: dict[int, bytes] = {}
    if scale != 1.0 or rise != 0.0:
        for index in position_accessors:
            accessor = document["accessors"][index]
            moved = ((_positions(document, binary, index).astype(np.float64) + [0.0, rise, 0.0]) * scale
                     ).astype("<f4")
            accessor["min"] = [float(v) for v in moved.min(axis=0)]
            accessor["max"] = [float(v) for v in moved.max(axis=0)]
            if accessor.get("byteOffset", 0) != 0:
                raise ValueError("expected positions at the start of their buffer view")
            view = _view(document, binary, accessor["bufferView"])
            replaced[accessor["bufferView"]] = moved.tobytes() + view[moved.nbytes:]
    textures: dict[str, bytes] = {}
    image_views = set()
    for image in document.get("images", []):
        payload = _view(document, binary, image["bufferView"])
        encoded, mime = _texture(payload, image.get("mimeType", "image/png"), texture_size)
        file = hashlib.sha256(encoded).hexdigest() + (".png" if mime == "image/png" else ".jpg")
        textures[file] = encoded
        image_views.add(image.pop("bufferView"))
        image["uri"] = "../textures/" + file
        image["mimeType"] = mime
    for material in document.get("materials", []):
        material.setdefault("pbrMetallicRoughness", {})["metallicFactor"] = 0.0
    for node in document["nodes"]:
        node.pop("matrix", None)
    document["nodes"][0]["name"] = "kit-" + name
    document["asset"] = {"version": "2.0", "generator": "Eloria sw_isle prepare_meshy_kit"}
    out = bytearray()
    kept, renumber = [], {}
    for index, view in enumerate(document["bufferViews"]):
        if index in image_views:
            continue
        payload = replaced.get(index, _view(document, binary, index))
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
    facts = {"id": piece, "measure": measure, "metres": metres, "texturePixels": texture_size, "origin": origin,
             "scale": scale, "rise_m": round(rise, 6),
             "bounds_m": [round(float(v), 3) for v in size]}
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out)), textures, facts


def _array(document: dict, binary: bytes, index: int) -> np.ndarray:
    """A tightly packed accessor as (count, columns) float64 or int64."""
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    if view.get("byteStride"):
        raise ValueError("expected tightly packed accessors")
    dtype = {5126: "<f4", 5125: "<u4", 5123: "<u2"}[accessor["componentType"]]
    columns = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = np.frombuffer(binary, dtype=dtype, count=accessor["count"] * columns, offset=start)
    values = values.reshape(accessor["count"], columns)
    return values.astype(np.float64 if dtype == "<f4" else np.int64)


def _end_caps(positions: np.ndarray, uvs: np.ndarray, indices: np.ndarray, end_x: float,
              tolerance: float = 0.02) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Flat faces closing a mesh's open section in the plane x = end_x: (positions, normals, uvs) of new
    triangles, three vertices each, facing out along X. The section is every open (one-face) edge lying in
    the plane, noded and polygonised, filled whole and triangulated (constrained Delaunay). Each cap takes
    one texel: the centre of the largest face that meets the plane, so it reads as the stone beside it."""
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    faces = indices.reshape(-1, 3)
    _, weld = np.unique(np.round(positions, 4), axis=0, return_inverse=True)
    weld = weld.ravel()
    welded = weld[faces]
    edges = np.sort(np.concatenate([welded[:, [0, 1]], welded[:, [1, 2]], welded[:, [2, 0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    representative = np.zeros((int(weld.max()) + 1, 3))
    representative[weld] = positions
    open_edges = unique[counts == 1]
    in_plane = (np.abs(representative[open_edges][:, :, 0] - end_x) < tolerance).all(axis=1)
    lines = [LineString([(representative[a, 2], representative[a, 1]), (representative[b, 2], representative[b, 1])])
             for a, b in open_edges[in_plane]]
    empty = np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 2))
    if not lines:
        return empty
    section = unary_union(list(polygonize(unary_union(lines))))
    if section.is_empty:
        return empty
    touching = (np.abs(positions[faces][:, :, 0] - end_x) < tolerance).sum(axis=1) >= 2
    corners = positions[faces]
    areas = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    source = int(np.argmax(np.where(touching, areas, -1.0)))
    texel = uvs[faces[source]].mean(axis=0)
    out_points, out_normals = [], []
    outward = 1.0 if end_x > 0 else -1.0
    for triangle in constrained_delaunay_triangles(section).geoms:
        ring = np.asarray(triangle.exterior.coords)[:3]          # (z, y)
        signed = 0.5 * ((ring[1, 0] - ring[0, 0]) * (ring[2, 1] - ring[0, 1])
                        - (ring[2, 0] - ring[0, 0]) * (ring[1, 1] - ring[0, 1]))
        if abs(signed) < 1e-9:
            continue
        if signed * outward > 0:                                 # +X faces need a clockwise (z, y) winding
            ring = ring[[0, 2, 1]]
        out_points.append(np.column_stack([np.full(3, end_x), ring[:, 1], ring[:, 0]]))
        out_normals.append(np.tile([outward, 0.0, 0.0], (3, 1)))
    if not out_points:
        return empty
    points = np.concatenate(out_points)
    return points, np.concatenate(out_normals), np.tile(texel, (len(points), 1))


def variant(base_payload: bytes, name: str) -> tuple[bytes, dict]:
    """A derived piece (VARIANTS): the prepared base scaled along X and sheared up the grade about its
    origin, its cut ends capped. Returns the prototype's bytes and what was made."""
    base, piece, x_scale, grade = VARIANTS[name]
    data = base_payload
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    binary = data[20 + json_length + 8:]
    capped = 0
    arrays: list[np.ndarray] = []                                # in accessor order, rebuilt below
    for index in range(len(document["accessors"])):
        arrays.append(_array(document, binary, index))
    for mesh_index, mesh in enumerate(document["meshes"]):
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            if set(attributes) != {"POSITION", "NORMAL", "TEXCOORD_0"} or "indices" not in primitive:
                raise ValueError(f"{base}: expected POSITION, NORMAL, TEXCOORD_0 and indices")
            positions = arrays[attributes["POSITION"]]
            normals = arrays[attributes["NORMAL"]]
            uvs = arrays[attributes["TEXCOORD_0"]]
            indices = arrays[primitive["indices"]].ravel()
            if mesh_index == document["nodes"][0].get("mesh"):  # the root piece, not its Walk_ deck
                low, high = positions[:, 0].min(), positions[:, 0].max()
                for end_x in (low, high):
                    cap_points, cap_normals, cap_uvs = _end_caps(positions, uvs, indices, float(end_x))
                    if len(cap_points):
                        start = len(positions)
                        positions = np.concatenate([positions, cap_points])
                        normals = np.concatenate([normals, cap_normals])
                        uvs = np.concatenate([uvs, cap_uvs])
                        indices = np.concatenate([indices, start + np.arange(len(cap_points))])
                        capped += len(cap_points) // 3
            moved = positions.copy()
            moved[:, 0] *= x_scale
            moved[:, 1] += grade * moved[:, 0]
            turned = np.column_stack([normals[:, 0] / x_scale - grade * normals[:, 1], normals[:, 1], normals[:, 2]])
            turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-12)
            arrays[attributes["POSITION"]] = moved
            arrays[attributes["NORMAL"]] = turned
            arrays[attributes["TEXCOORD_0"]] = uvs
            arrays[primitive["indices"]] = indices.reshape(-1, 1)
    out = bytearray()
    views = []
    for index, values in enumerate(arrays):
        accessor = document["accessors"][index]
        if accessor["componentType"] == 5126:
            payload = values.astype("<f4").tobytes()
        else:
            accessor["componentType"] = 5125
            payload = values.astype("<u4").tobytes()
        while len(out) % 4:
            out.append(0)
        target = 34963 if accessor["type"] == "SCALAR" else 34962
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": len(payload), "target": target})
        out.extend(payload)
        accessor["bufferView"] = index
        accessor.pop("byteOffset", None)
        accessor["count"] = len(values)
        if accessor["type"] == "VEC3" and accessor.get("min") is not None:
            accessor["min"] = [float(v) for v in values.astype("<f4").min(axis=0)]
            accessor["max"] = [float(v) for v in values.astype("<f4").max(axis=0)]
    while len(out) % 4:
        out.append(0)
    document["bufferViews"] = views
    document["buffers"] = [{"byteLength": len(out)}]
    root = document["nodes"][0]
    root["name"] = "kit-" + name
    walk = f"Walk_{name}-deck"
    for child in root.get("children", []):
        if document["nodes"][child]["name"].startswith("Walk_"):
            document["nodes"][child]["name"] = walk
            document["meshes"][document["nodes"][child]["mesh"]]["name"] = walk
    document["meshes"][root["mesh"]]["name"] = "kit-" + name
    extras = root.setdefault("extras", {}).setdefault("eloria", {})
    extras.update({"id": piece, "kit": "kit-" + name, "variant_of": f"kit-{base}", "x_scale": x_scale,
                   "grade": grade, "origin": "waterline", "walk_node": walk,
                   "notes": (f"west-gate stone ramp module: kit-{base} scaled x{x_scale} along its span and sheared "
                             f"up a {grade} grade about the deck-top origin (rampant arches, piers vertical); "
                             f"Y=0 is the deck top at the module centre; cut ends capped")})
    extras.pop("collider", None)
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(out)
    every = np.concatenate([arrays[p["attributes"]["POSITION"]] for m in document["meshes"] for p in m["primitives"]])
    facts = {"id": piece, "variant_of": base, "x_scale": x_scale, "grade": grade, "cap_triangles": capped,
             "bounds_m": [round(float(v), 3) for v in np.ptp(every, axis=0)]}
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out)), facts


def derived(base_payload: bytes, name: str) -> tuple[bytes, dict]:
    """A coast deck-dressing piece (DERIVED): the prepared base with its own mesh cut (drop_above) or its post
    feet moved down (post_foot). Returns the prototype's bytes and what was made."""
    base, piece, operation, value = DERIVED[name]
    data = base_payload
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    binary = data[20 + json_length + 8:]
    arrays = [_array(document, binary, index) for index in range(len(document["accessors"]))]
    root = document["nodes"][0]
    changed = 0
    for primitive in document["meshes"][root["mesh"]]["primitives"]:
        attributes = primitive["attributes"]
        positions = arrays[attributes["POSITION"]]
        indices = arrays[primitive["indices"]].ravel()
        if operation in ("drop_above", "trim_top"):
            faces = indices.reshape(-1, 3)
            keep = positions[faces][:, :, 1].mean(axis=1) <= value
            changed += int((~keep).sum())
            arrays[primitive["indices"]] = faces[keep].reshape(-1, 1)
        elif operation == "trim_base":
            faces = indices.reshape(-1, 3)
            centres = positions[faces].mean(axis=1)
            keep = ~((centres[:, 1] < value[0]) & (np.hypot(centres[:, 0], centres[:, 2]) > value[1]))
            changed += int((~keep).sum())
            arrays[primitive["indices"]] = faces[keep].reshape(-1, 1)
        elif operation == "post_foot":
            moved = positions.copy()
            low = moved[:, 1] < N13_POST_BELOW
            moved[low, 1] += value - N13_FOOT
            changed += int(low.sum())
            arrays[attributes["POSITION"]] = moved
        else:
            raise ValueError(f"{name}: unknown operation {operation}")
    out = bytearray()
    views = []
    for index, values in enumerate(arrays):
        accessor = document["accessors"][index]
        if accessor["componentType"] == 5126:
            payload = values.astype("<f4").tobytes()
        else:
            accessor["componentType"] = 5125
            payload = values.astype("<u4").tobytes()
        while len(out) % 4:
            out.append(0)
        target = 34963 if accessor["type"] == "SCALAR" else 34962
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": len(payload), "target": target})
        out.extend(payload)
        accessor["bufferView"] = index
        accessor.pop("byteOffset", None)
        accessor["count"] = len(values)
        if accessor["type"] == "VEC3" and accessor.get("min") is not None:
            accessor["min"] = [float(v) for v in values.astype("<f4").min(axis=0)]
            accessor["max"] = [float(v) for v in values.astype("<f4").max(axis=0)]
    while len(out) % 4:
        out.append(0)
    document["bufferViews"] = views
    document["buffers"] = [{"byteLength": len(out)}]
    root["name"] = "kit-" + name
    document["meshes"][root["mesh"]]["name"] = "kit-" + name
    walk = None
    for child in root.get("children", []):
        node = document["nodes"][child]
        if not node["name"].startswith("Walk_"):
            continue
        # a tier's deck is the arcade's intermediate floor, never walked; a long span keeps its walk deck
        node["name"] = (f"Deck_{name}-floor" if operation == "drop_above" else f"Walk_{name}-deck")
        document["meshes"][node["mesh"]]["name"] = node["name"]
        walk = node["name"] if node["name"].startswith("Walk_") else None
    extras = root.setdefault("extras", {}).setdefault("eloria", {})
    extras.pop("collider", None)
    if walk is None:
        extras.pop("walk_node", None)
    else:
        extras["walk_node"] = walk
    origin = "waterline"
    if operation == "drop_above":
        notes = (f"causeway tier: kit-{base} without its parapets (faces centred above +{value} m dropped), "
                 f"stacked level under a top module (8 m per tier: its deck top meets the feet above); "
                 f"Y=0 is the tier's deck top; its deck is not a walk surface")
    elif operation == "trim_base":
        origin = "base"
        notes = (f"lawn palm: kit-{base} without its sand-mound base (faces centred under {value[0]} m and more than "
                 f"{value[1]} m from the trunk axis dropped), for palms planted on grass; same textures; Y=0 is its "
                 f"foot")
    elif operation == "trim_top":
        origin = "base"
        notes = (f"castle revetment: kit-{base} without its merlons (faces centred above +{value} m dropped), a "
                 f"plain course of the curtain wall's masonry stacked down the castle pad's scarp under the town "
                 f"wall (5.0 m per course), its back buried in the scarp; Y=0 is its foot")
    else:
        notes = (f"long trestle span: kit-{base} with its four bent posts lengthened (feet {N13_FOOT} -> {value} m "
                 f"below the deck top) for the seabed trenches under the piers; Y=0 is the deck top")
    extras.update({"id": piece, "kit": "kit-" + name, "variant_of": f"kit-{base}", "operation": operation,
                   "value": value, "origin": origin, "notes": notes})
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(out)
    every = np.concatenate([arrays[p["attributes"]["POSITION"]][np.unique(arrays[p["indices"]].ravel())]
                            for m in document["meshes"] for p in m["primitives"]])
    facts = {"id": piece, "variant_of": base, "operation": operation, "value": value,
             ("faces_dropped" if operation in ("drop_above", "trim_top", "trim_base") else "vertices_moved"): changed,
             "bounds_m": [round(float(v), 3) for v in np.ptp(every, axis=0)],
             "low_m": round(float(every[:, 1].min()), 3), "high_m": round(float(every[:, 1].max()), 3)}
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out)), facts


def _soup(document: dict, binary: bytes, mesh_index: int) -> np.ndarray:
    """A one-primitive mesh as a triangle soup (F, 3, 8): position, normal and uv per corner."""
    primitives = document["meshes"][mesh_index]["primitives"]
    if len(primitives) != 1 or set(primitives[0]["attributes"]) != {"POSITION", "NORMAL", "TEXCOORD_0"}:
        raise ValueError("expected one primitive with POSITION, NORMAL and TEXCOORD_0")
    attributes = primitives[0]["attributes"]
    vertices = np.concatenate([_array(document, binary, attributes[key])
                               for key in ("POSITION", "NORMAL", "TEXCOORD_0")], axis=1)
    return vertices[_array(document, binary, primitives[0]["indices"]).ravel().reshape(-1, 3)]


def _soup_arrays(soup: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A triangle soup back to indexed float32 arrays, exactly equal corners welded."""
    unique, inverse = np.unique(soup.reshape(-1, soup.shape[2]).astype("<f4"), axis=0, return_inverse=True)
    normals = unique[:, 3:6].astype(np.float64)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return unique[:, :3], normals.astype("<f4"), unique[:, 6:8], inverse.ravel().astype("<u4")


def _clip_triangle(corners: np.ndarray, axis: int, value: float, keep_below: bool) -> list[np.ndarray]:
    """One triangle's corners clipped to coordinate `axis` < value (keep_below) or >= value: the kept polygon fanned
    into triangles, every attribute interpolated along the cut edges."""
    d = (value - corners[:, axis]) if keep_below else (corners[:, axis] - value)
    out = []
    for i in range(3):
        a, b = corners[i], corners[(i + 1) % 3]
        if d[i] >= 0:
            out.append(a)
        if (d[i] >= 0) != (d[(i + 1) % 3] >= 0):
            out.append(a + d[i] / (d[i] - d[(i + 1) % 3]) * (b - a))
    return [np.stack([out[0], out[k], out[k + 1]]) for k in range(1, len(out) - 1)] if len(out) >= 3 else []


def _split_soup(soup: np.ndarray, value: float, axis: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """A soup split at coordinate `axis` = value: (the part below, the part at or above)."""
    below, above = [], []
    for corners in soup:
        if (corners[:, axis] <= value).all():
            below.append(corners)
        elif (corners[:, axis] >= value).all():
            above.append(corners)
        else:
            below.extend(_clip_triangle(corners, axis, value, True))
            above.extend(_clip_triangle(corners, axis, value, False))
    empty = np.zeros((0, 3, soup.shape[2]))
    return (np.stack(below) if below else empty), (np.stack(above) if above else empty)


def _box_soup(soup: np.ndarray, **limits: tuple[float, float]) -> np.ndarray:
    """The part of a soup inside axis-aligned limits, e.g. x=(a, b), z=(c, d)."""
    for key, (low, high) in limits.items():
        axis = "xyz".index(key)
        soup = _split_soup(_split_soup(soup, low, axis)[1], high, axis)[0]
    return soup


def _moved_soup(soup: np.ndarray, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> np.ndarray:
    out = soup.copy()
    out[:, :, :3] += (dx, dy, dz)
    return out


def _soup_area(soup: np.ndarray) -> np.ndarray:
    p = soup[:, :, :3]
    return 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)


def _rect(axes: tuple[int, int], low: tuple[float, float], high: tuple[float, float], plane: float,
          normal: tuple[float, float, float]) -> np.ndarray:
    """A flat rectangle (two triangles, as a soup) over [low, high] on `axes`, at `plane` on the third axis, facing
    `normal`: a target for _swap_face (its corners and normal are read; it carries no texture of its own)."""
    other = 3 - sum(axes)
    corners = []
    for u, v in ((low[0], low[1]), (high[0], low[1]), (high[0], high[1]), (low[0], high[1])):
        point = np.zeros(8)
        point[axes[0]], point[axes[1]], point[other] = u, v, plane
        point[3:6] = normal
        corners.append(point)
    return np.stack([np.stack([corners[0], corners[1], corners[2]]), np.stack([corners[0], corners[2], corners[3]])])


def _swap_face(donor: np.ndarray, d_axes: tuple[int, int], target: np.ndarray, t_axes: tuple[int, int],
               snap: float = GATE_SWAP_SNAP, relief: float = 0.0) -> np.ndarray:
    """The donor faces laid over the target faces' rectangle (each donor corner's place, normalised over the donor's
    bounds in d_axes, at the same place over the target's bounds in t_axes, on the target's plane, with its normal).
    Every donor triangle keeps its own UVs: the atlas keeps each triangle's texture in its own island, so a face's
    texture is changed by swapping whole faces, never by re-mapping corners. A donor's outline is not quite its
    bounding box (a chamfer or a worn arris leaves slivers a few centimetres wide along its edges), so a corner within
    `snap` of the rectangle's edge is put on it, and the swapped faces cover the rectangle out to its edges. With
    `relief`, each corner stands out from the target's plane by that fraction of its depth out from the donor's
    innermost corner, so donor faces that overlap once laid flat keep the order they are seen in, not coplanar."""
    t_low = target[:, :, list(t_axes)].reshape(-1, 2).min(axis=0)
    t_high = target[:, :, list(t_axes)].reshape(-1, 2).max(axis=0)
    d_low = donor[:, :, list(d_axes)].reshape(-1, 2).min(axis=0)
    d_high = donor[:, :, list(d_axes)].reshape(-1, 2).max(axis=0)
    normal = target[:, :, 3:6].reshape(-1, 3).mean(axis=0)
    normal /= np.linalg.norm(normal)
    out = donor.copy()
    out[:, :, :3] = 0.0
    placed = t_low + (donor[:, :, list(d_axes)] - d_low) / np.maximum(d_high - d_low, 1e-9) * (t_high - t_low)
    placed = np.where(placed - t_low < snap, t_low, np.where(t_high - placed < snap, t_high, placed))
    out[:, :, list(t_axes)] = placed
    plane = 3 - sum(t_axes)
    out[:, :, plane] = target[:, :, plane].mean()
    if relief:
        depth_axis = 3 - sum(d_axes)
        outward = np.sign(donor[:, :, 3 + depth_axis].mean())
        inner = donor[:, :, depth_axis].max() if outward < 0 else donor[:, :, depth_axis].min()
        out[:, :, plane] += relief * (donor[:, :, depth_axis] - inner) * outward * np.sign(normal[plane])
    out[:, :, 3:6] = normal
    for k, corners in enumerate(out):
        if np.cross(corners[1, :3] - corners[0, :3], corners[2, :3] - corners[0, :3]) @ normal < 0:
            out[k] = corners[[0, 2, 1]]
    return out


def _shared_seam(deck: np.ndarray, copy: np.ndarray, z: float) -> tuple[np.ndarray, np.ndarray, dict]:
    """The deck and the copied paving made to meet on the seam Z = z without a crack: both are cut across X at every
    seam corner of either (so the two seam lines have the same corners and no T-junction), and each copy corner on the
    seam takes the deck's own corner there (its X, Y and Z): the copy bends the few centimetres the deck's seam rises
    and falls, the deck is untouched."""
    def seam(soup):
        return np.abs(soup[:, :, 2] - z) < 1e-6

    xs = np.unique(np.round(np.concatenate([deck[:, :, 0][seam(deck)], copy[:, :, 0][seam(copy)]]), 6))
    for x in xs:
        deck = np.concatenate([part for part in _split_soup(deck, float(x)) if len(part)])
        copy = np.concatenate([part for part in _split_soup(copy, float(x)) if len(part)])
    on_deck, on_copy = seam(deck), seam(copy)
    keys = np.round(deck[:, :, 0][on_deck], 6)
    heights: dict[float, float] = {}
    for key, height in zip(keys.tolist(), deck[:, :, 1][on_deck].tolist()):
        heights[key] = max(height, heights.get(key, -np.inf))
    deck[:, :, 0][on_deck] = keys
    deck[:, :, 1][on_deck] = [heights[key] for key in keys.tolist()]
    deck[:, :, 2][on_deck] = z
    copy_keys = np.round(copy[:, :, 0][on_copy], 6)
    missing = sorted(set(copy_keys.tolist()) - set(heights))
    if missing:
        raise ValueError(f"the copied paving's seam has corners the deck's has not: {missing[:5]}")
    moved = np.abs(copy[:, :, 1][on_copy] - [heights[key] for key in copy_keys.tolist()])
    copy[:, :, 0][on_copy] = copy_keys
    copy[:, :, 1][on_copy] = [heights[key] for key in copy_keys.tolist()]
    copy[:, :, 2][on_copy] = z
    facts = {"corners": len(heights), "copyCornersMoved_m": round(float(moved.max()) if len(moved) else 0.0, 4)}
    return deck, copy, facts


def _gate_geometry(body: np.ndarray, walk: np.ndarray, opening: tuple[float, float],
                   step: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """GATES' cut on soups of the module's body and Walk_ deck, the opening on the -Z side between opening[0] and
    opening[1] with a pier post at each side: (the new body, the new Walk_ deck, what was done)."""
    start, end = opening
    p = body[:, :, :3]
    n = body[:, :, 3:6].mean(axis=1)
    z = -p[:, :, 2]                                             # out toward the opened side
    top = p[:, :, 1].max(axis=1)
    post = ((p[:, :, 0] >= GATE_POST_X0).all(axis=1) & (z >= GATE_PARAPET_Z).all(axis=1) & (z <= 5.9).all(axis=1)
            & (top > 0.1))
    parapet = ((z.mean(axis=1) >= GATE_PARAPET_Z + 0.03) & (z <= 5.95).all(axis=1) & (top > 0.2)
               & ~(p[:, :, 0] >= GATE_POST_X0).all(axis=1) & ~(p[:, :, 0] <= -GATE_POST_X0).all(axis=1))
    slab = (z.mean(axis=1) >= 4.7) & (top <= GATE_SLAB_TOP) & ~parapet
    up = slab & (n[:, 1] > 0.5) & (p[:, :, 1].min(axis=1) >= -1.25)
    edge = slab & (z >= GATE_SLAB_EDGE[0]).all(axis=1) & (z <= GATE_SLAB_EDGE[1]).all(axis=1) & (-n[:, 2] > 0.5)
    # The parapet goes from the opening and from under its two new posts (its ends 2 cm inside them); on both sides
    # beyond them it stays, out to the module's end posts.
    keep_low, rest = _split_soup(body[parapet], start - GATE_POST_WIDTH + 0.02)
    taken, keep_high = _split_soup(rest, end + GATE_POST_WIDTH - 0.02)
    up_out, up_in = _split_soup(body[up], start)                # the slab top under the old parapet gives way ...
    up_in, up_end = _split_soup(up_in, end)                     # ... to paving in the opening
    # The slab's outer face in the opening: its kerb band over the bank (above GATE_EDGE_BAND) is stepped off (as body
    # faces 0.1-0.6 m over the ground they close the half-cells along the slab edge, and the opening with them); below
    # it the spandrel and the arch ring stay solid.
    edge_out, edge_in = _split_soup(body[edge], start)
    edge_in, edge_end = _split_soup(edge_in, end)
    edge_low, edge_band = _split_soup(edge_in, GATE_EDGE_BAND, 1)
    # The two posts: the module end's half-post and its mirror about the module end make one pier post, as two modules'
    # halves do over a pier. The face each turns to the opening (hidden by the parapet until now) takes the outer
    # face's texture; the face against the kept parapet keeps its own.
    half = body[post]
    half_normals = half[:, :, 3:6].mean(axis=1)
    inner = (half_normals[:, 0] < -0.97) & (_soup_area(half) > 0.05)
    outer = (half_normals[:, 2] < -0.97) & (_soup_area(half) > 0.05)
    mirror = half[:, ::-1].copy()                               # reversed winding keeps the faces outward
    mirror[:, :, 0] = 2 * GATE_END_X - mirror[:, :, 0]
    mirror[:, :, 3] = -mirror[:, :, 3]
    dressed_mirror = _swap_face(half[outer], (0, 1), mirror[inner], (2, 1))
    dressed_half = _swap_face(half[outer], (0, 1), half[inner], (2, 1))
    low_post = _moved_soup(np.concatenate([half, mirror[~inner], dressed_mirror]),
                           dx=start - (2 * GATE_END_X - GATE_POST_FACE))
    high_post = _moved_soup(np.concatenate([half[~inner], dressed_half, mirror]), dx=end - GATE_POST_FACE)
    new_body = np.concatenate([body[~(parapet | up | edge)], keep_low, keep_high, up_out, up_end, edge_out, edge_end,
                               edge_low, low_post, high_post])
    # The deck: in the opening its paving runs out to the slab edge, a copy of its own paving two courses further in,
    # meeting the deck on a shared seam; the slab top stays under the copy, just below it.
    deck_out, deck_in = _split_soup(walk, start)
    deck_in, deck_end = _split_soup(deck_in, end)
    deck_in = _split_soup(deck_in, -GATE_PAVING_SEAM, 2)[1]
    width = GATE_EDGE_Z - GATE_PAVING_SEAM
    paving = _moved_soup(_box_soup(walk, x=(start, end), z=(-GATE_PAVING_SEAM - width + GATE_PAVING_SHIFT,
                                                            -GATE_PAVING_SEAM + GATE_PAVING_SHIFT)),
                         dz=-GATE_PAVING_SHIFT)
    deck_in, paving, seam_facts = _shared_seam(deck_in, paving, -GATE_PAVING_SEAM)
    backing = _moved_soup(up_in, dy=float(paving[:, :, 1].min()) - GATE_BACKING_DROP - float(up_in[:, :, 1].max()))
    # The step stone: a block of the parapet's own stone set out against the slab edge, its tread the coping's flat top
    # face, its front every face the parapet turns outward (stem, coping edge and its chamfer: together they tile the
    # parapet's height), its ends the post's outer face (whole faces swapped), its foot under the ground everywhere
    # below it. All of it is in the Walk_ child: the tread is walked, and its sides as body faces would close the
    # half-cells beside it (an actor's floor clearance is 6 cm), where Walk_ faces steeper than 0.65 are neither walk
    # nor solid.
    x0, x1 = step["x"]
    z_in = -(GATE_EDGE_Z + GATE_STEP_GAP)
    z_out = z_in - GATE_STEP_DEPTH
    tread = _swap_face(_box_soup(body[parapet & (n[:, 1] > 0.9)], x=(x0, x1)), (0, 2),
                       _rect((0, 2), (x0, z_out), (x1, z_in), step["top"], (0.0, 1.0, 0.0)), (0, 2))
    front = _swap_face(_box_soup(body[parapet & (n[:, 2] < -0.3)], x=(x0, x1)), (0, 1),
                       _rect((0, 1), (x0, step["foot"]), (x1, step["top"]), z_out, (0.0, 0.0, -1.0)), (0, 1),
                       relief=GATE_STEP_RELIEF)
    ends = [_swap_face(half[outer], (0, 1),
                       _rect((2, 1), (z_out, step["foot"]), (z_in, step["top"]), x, (sign, 0.0, 0.0)), (2, 1))
            for x, sign in ((x0, -1.0), (x1, 1.0))]
    stone = np.concatenate([tread, front, *ends])
    new_walk = np.concatenate([part for part in (deck_out, deck_in, deck_end, paving, backing, edge_band, stone)
                               if len(part)])
    facts = {"opening": [start, end], "posts": [[round(start - GATE_POST_WIDTH, 4), start],
                                                [end, round(end + GATE_POST_WIDTH, 4)]],
             "parapetFacesTaken": int(len(taken)), "parapetAreaTaken_m2": round(float(_soup_area(taken).sum()), 3),
             "postFacesRetextured": int(inner.sum()) * 2, "slabTopFacesUnderPaving": int(len(up_in)),
             "pavingFaces": int(len(paving)), "seam": seam_facts, "slabEdgeBand": [GATE_EDGE_BAND, 0.0],
             "slabEdgeFacesToWalk": int(len(edge_band)),
             "step": {"x": [x0, x1], "top": step["top"], "foot": step["foot"],
                      "z": [round(z_out, 4), round(z_in, 4)], "faces": int(len(stone))}}
    return new_body, new_walk, facts


def gate(base_payload: bytes, name: str) -> tuple[bytes, dict]:
    """A gate piece (GATES): the prepared base with an opening in one parapet. Returns the prototype's bytes and what
    was made."""
    base, piece, side, opening, step = GATES[name]
    if side != "-z":
        raise ValueError(f"{name}: only a -Z opening is made ({side!r})")
    json_length = struct.unpack_from("<I", base_payload, 12)[0]
    document = json.loads(base_payload[20:20 + json_length])
    binary = base_payload[20 + json_length + 8:]
    root = document["nodes"][0]
    walk_node = next(document["nodes"][child] for child in root["children"]
                     if document["nodes"][child]["name"].startswith("Walk_"))
    if document["meshes"][root["mesh"]]["primitives"][0]["material"] != \
            document["meshes"][walk_node["mesh"]]["primitives"][0]["material"]:
        raise ValueError(f"{base}: expected the body and the deck to share one material")
    body, walk, facts = _gate_geometry(_soup(document, binary, root["mesh"]),
                                       _soup(document, binary, walk_node["mesh"]), opening, step)
    out = bytearray()
    views, accessors = [], []

    def add(values: np.ndarray, kind: str, target: int, component: int) -> int:
        payload = values.tobytes()
        while len(out) % 4:
            out.append(0)
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": len(payload), "target": target})
        out.extend(payload)
        accessor = {"bufferView": len(views) - 1, "componentType": component, "count": int(len(values)), "type": kind}
        if kind == "VEC3" and component == 5126:
            accessor["min"] = [float(v) for v in values.min(axis=0)]
            accessor["max"] = [float(v) for v in values.max(axis=0)]
        accessors.append(accessor)
        return len(accessors) - 1

    every = []
    for node, soup in ((root, body), (walk_node, walk)):
        positions, normals, uvs, indices = _soup_arrays(soup)
        every.append(positions)
        primitive = document["meshes"][node["mesh"]]["primitives"][0]
        primitive["attributes"] = {"POSITION": add(positions, "VEC3", 34962, 5126),
                                   "NORMAL": add(normals, "VEC3", 34962, 5126),
                                   "TEXCOORD_0": add(uvs, "VEC2", 34962, 5126)}
        primitive["indices"] = add(indices.reshape(-1, 1), "SCALAR", 34963, 5125)
    while len(out) % 4:
        out.append(0)
    document["accessors"] = accessors
    document["bufferViews"] = views
    document["buffers"] = [{"byteLength": len(out)}]
    walk_name = f"Walk_{name}-deck"
    root["name"] = "kit-" + name
    document["meshes"][root["mesh"]]["name"] = "kit-" + name
    walk_node["name"] = walk_name
    document["meshes"][walk_node["mesh"]]["name"] = walk_name
    extras = root.setdefault("extras", {}).setdefault("eloria", {})
    extras.pop("collider", None)
    extras.update({"id": piece, "kit": "kit-" + name, "variant_of": f"kit-{base}", "origin": "waterline",
                   "walk_node": walk_name, "opening": {"side": side, "x": list(opening)},
                   "notes": (f"gate module: kit-{base} with its {side} parapet opened from X {opening[0]} to "
                             f"{opening[1]} between two new pier posts (X {facts['posts'][0][0]}..{opening[0]} and "
                             f"{opening[1]}..{facts['posts'][1][1]}), the deck's paving run out to the slab edge on a "
                             f"shared seam, and a step stone (tread {step['top']} m, foot {step['foot']} m) below the "
                             f"opening at X {step['x'][0]}..{step['x'][1]}; the opened slab edge's kerb band (above Y "
                             f"{GATE_EDGE_BAND}) and the step are in the Walk_ child; Y=0 is the deck top")})
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(out)
    every = np.concatenate(every)
    facts = {"id": piece, "variant_of": base, "side": side, **facts,
             "triangles": [int(len(body)), int(len(walk))],
             "bounds_m": [round(float(v), 3) for v in np.ptp(every, axis=0)]}
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out)), facts


def shared(name: str) -> tuple[Path, bytes, dict[str, bytes]]:
    """A shared model: its source prototype, its bytes, and the texture files it references."""
    region, _, file = SHARED[name].partition(":")
    source = REGIONS / region / "assets/prototypes" / (file or f"kit-{name}.glb")
    payload = source.read_bytes()
    document, _ = _read(source)
    textures = {}
    for image in document.get("images", []):
        uri = image.get("uri", "")
        match = re.fullmatch(r"\.\./textures/([0-9a-f]{64}\.(?:png|jpg))", uri)
        if not match:
            raise ValueError(f"{source.name}: image {uri!r} is not a content-addressed territory texture")
        textures[match.group(1)] = (source.parent.parent / "textures" / match.group(1)).read_bytes()
    if name in SHARED_TINTS:
        payload = _tinted(payload, SHARED_TINTS[name])
    return source, payload, textures


def _tinted(payload: bytes, factor: tuple[float, float, float]) -> bytes:
    """The GLB with every material's baseColorFactor multiplied by `factor` (alpha kept)."""
    json_length = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20:20 + json_length])
    tail = payload[20 + json_length:]
    for material in document.get("materials", []):
        pbr = material.setdefault("pbrMetallicRoughness", {})
        base = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
        pbr["baseColorFactor"] = [round(base[0] * factor[0], 4), round(base[1] * factor[1], 4),
                                  round(base[2] * factor[2], 4), base[3]]
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + len(tail)
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + tail)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True,
                        help="the folder seat_fixes.py wrote (work-output/continent-v2/meshy/seated)")
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    record = {"schema": "eloria-prepared-kit-v1", "tool": "prepare_meshy_kit.py", "models": {}}
    stale = []
    PROTOTYPES.mkdir(parents=True, exist_ok=True)
    TEXTURES.mkdir(parents=True, exist_ok=True)
    jobs = [(name, "generated") for name in sorted(SIZES)] + [(name, "shared") for name in sorted(SHARED)] + \
        [(name, "variant") for name in sorted(VARIANTS)] + [(name, "derived") for name in sorted(DERIVED)] + \
        [(name, "gate") for name in sorted(GATES)]
    prepared: dict[str, tuple[bytes, dict[str, bytes]]] = {}
    for name, kind in jobs:
        if kind == "generated":
            source = args.input / f"kit-{name}.glb"
            payload, textures, facts = prepare(source, name)
            prepared[name] = (payload, textures)
            entry = {"kind": kind, "source": f"seated/kit-{name}.glb", **facts}
            entry["input"] = hashlib.sha256(source.read_bytes()).hexdigest()
        elif kind == "variant":
            base_payload, textures = prepared[VARIANTS[name][0]]
            payload, facts = variant(base_payload, name)
            entry = {"kind": kind, "source": f"kit-{VARIANTS[name][0]}.glb as prepared here", **facts}
            entry["input"] = hashlib.sha256(base_payload).hexdigest()
        elif kind == "derived":
            base_payload, textures = prepared[DERIVED[name][0]]
            payload, facts = derived(base_payload, name)
            entry = {"kind": kind, "source": f"kit-{DERIVED[name][0]}.glb as prepared here", **facts}
            entry["input"] = hashlib.sha256(base_payload).hexdigest()
        elif kind == "gate":
            base_payload, textures = prepared[GATES[name][0]]
            payload, facts = gate(base_payload, name)
            entry = {"kind": kind, "source": f"kit-{GATES[name][0]}.glb as prepared here", **facts}
            entry["input"] = hashlib.sha256(base_payload).hexdigest()
        else:
            source, payload, textures = shared(name)
            prepared[name] = (payload, textures)
            entry = {"kind": kind, "source": source.relative_to(CLIENT).as_posix()}
            entry["input"] = hashlib.sha256(source.read_bytes()).hexdigest()
            if name in SHARED_TINTS:
                entry["baseColorFactorTint"] = list(SHARED_TINTS[name])
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
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
        print(f"{len(record['models'])} prototypes match the recorded inputs")
        return 0
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
