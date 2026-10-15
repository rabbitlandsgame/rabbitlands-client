"""Secret rooms: the hidden insides a region keeps behind its scenery.

A secret is a small authored room on the region's `<region>_secrets` map,
reached by *using* a feature of the ground above - a loose stone, a hollow
tree, a crack in the ice - sometimes only with an item in the pack. Every
secret does one thing better than the world above it, and that one thing is
what its kind is named for:

    grotto     a harvest hollow, richer than the open ground
    garden     an open-to-sky pocket where several resources grow together
               and the ground yields faster (harvest_speed)
    cache      a cellar with a storage chest beside its harvest nodes
    vault      a strongroom where the same work teaches more (experience)
    pen        a training chamber with a denser, chosen spawn
    school     a reading room where books read faster (fast_reading)
    spring     a warm chamber where wounds close faster (fast_regeneration)
    range      a long gallery with slow targets for ranging practice
    reliquary  a lore chamber: plaques on one of the region's threads
    nullwell   a warded pit where nothing casts (no_magic)
    focus      a chamber where the ether comes cheaper (cheap_magic)
    tunnel     a passage out under the border into a neighbouring region
    waystone   a hub whose stones open onto other regions' hubs
    eyrie      a lookout with water, a plaque on the game's mechanics, and
               quicker breath (fast_regeneration)

Rooms are built from the interiors kit (`chamber`, `passage`) so they share
the walk, roof and material contracts of every other inside; the composer in
`secrets_build.py` lays them out with void between, one map per region.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from amberwood import crystalcraft as CC
from amberwood import interiors as I
from amberwood import junglecraft as JC
from amberwood import mesh as M
from amberwood import moorcraft as MOOR
from amberwood import props as P
from amberwood import stonework as S
from amberwood import trees as TREES
from amberwood.interiors import Interior, chamber, hanging_lamps, passage
from amberwood.smallrooms import _link, _palette

KINDS = ("grotto", "garden", "cache", "vault", "pen", "school", "spring", "range",
         "reliquary", "nullwell", "focus", "tunnel", "waystone", "eyrie")

# What the ground above offers to be used. The prop is what the region places;
# the label is what the server tells a player who uses it.
ENTRANCES = {
    "loose_stone": "A loose stone in the rock; something moves behind it.",
    "hollow_tree": "A hollow tree. The dark inside it goes down, not in.",
    "ice_crack": "A crack in the ice, wider than it looks, and warm air rising from it.",
    "cracked_slab": "A cracked flagstone that rings hollow underfoot.",
    "reed_hide": "A hide of cut reeds, and a plank floor under it where there should be mud.",
    "root_door": "A knot of roots grown over a door frame.",
    "shrine_slab": "A shrine slab with fresh scratches where it has been slid aside.",
    "well_shaft": "A dry well. Handholds have been cut into its shaft.",
    "crystal_seam": "A seam of crystal that hums at a touch; the rock behind it is thin.",
    "drain_grate": "An iron drain grate, its bolts drawn.",
    "tide_cave": "A cave mouth the tide leaves open for an hour a day.",
    "cellar_hatch": "A cellar hatch under the leaves.",
    "cairn": "A cairn built over nothing, or over something.",
    "chimney": "A chimney with no house, still warm.",
    "ivy_arch": "An arch so grown with vine it reads as hedge.",
    "sand_sink": "A sink in the sand that never fills.",
}


@dataclass
class Secret:
    """One secret a region asks for. `at` is a landmark id or an (x, z) pair
    on the region; `door_map` moves the entrance onto an insides map."""
    id: str
    name: str
    kind: str
    entrance: str = "loose_stone"
    at: object = None
    offset: tuple = (0.0, 0.0)
    key: str = ""
    door_map: str = ""
    door_space: str = ""
    resources: tuple = ()
    creatures: tuple = ()
    area: tuple = ()
    texts: tuple = ()
    links: tuple = ()
    label: str = ""
    note: str = ""
    size: float = 1.0
    # filled by the region build once the entrance is placed
    door_position: list = field(default_factory=list)
    door_tile: list = field(default_factory=list)
    # Prefer nearby paving over distant vegetation-free ground when a precinct
    # reservation is only keeping trees off an otherwise usable forecourt.
    prefer_near: bool = False


def label_for(secret: Secret) -> str:
    return secret.label or ENTRANCES.get(secret.entrance, "A way down.")


# ------------------------------------------------------------------ helpers
def _plaque(it: Interior, ident: str, title: str, text: str, x: float, y: float, z: float,
            material: str = "carved_wood") -> None:
    it.group.add(M.box((1.1, 1.4, 0.12), center=(x, y + 0.9, z), uv_scale=1.0, material=material))
    it.group.add(M.box((0.14, 0.9, 0.14), center=(x, y + 0.45, z), uv_scale=1.0, material=material))
    it.interactives.append({"id": ident, "kind": "information", "target": "lore",
                            "label": title, "text": text,
                            "position": [round(x, 2), round(y + 1.0, 2), round(z, 2)]})


def _node(it: Interior, ident: str, resource: str, x: float, y: float, z: float,
          seed: int, material: str) -> None:
    """A harvest node: a small authored clump the server names by resource."""
    it.group.add(P.mushroom_cluster(seed=seed, count=4, material=material)
                 .translate(x, y, z))
    it.harvestables.append({"id": ident, "resource": resource,
                            "position": [round(x, 2), round(y, 2), round(z, 2)]})


def _storage(it: Interior, ident: str, x: float, y: float, z: float, seed: int, pal: dict) -> None:
    chest = S.MeshGroup()
    chest.add(P.crate(size=0.9, seed=seed, material=pal["timber"]).translate(0.0, 0.0, 0.0))
    chest.add(M.box((1.0, 0.08, 0.7), center=(0.0, 0.94, 0.0), uv_scale=1.0, material="dark_iron"))
    it.group.add(chest.translate(x, y, z))
    it.interactives.append({"id": ident, "kind": "storage", "target": "shared",
                            "label": "Cache", "text": "A cache; it opens your shared storage.",
                            "position": [round(x, 2), round(y + 0.5, 2), round(z, 2)]})


def _station(it: Interior, ident: str, x: float, y: float, z: float, seed: int, pal: dict) -> None:
    it.group.add(P.workbench(length=2.2, seed=seed, tools=True).translate(x, y, z))
    it.interactives.append({"id": ident, "kind": "crafting_station", "target": "field",
                            "label": "Bench", "text": "A bench for ordinary mixing and crafting.",
                            "position": [round(x, 2), round(y + 0.9, 2), round(z, 2)]})


def _brazier(it: Interior, x: float, y: float, z: float, seed: int) -> None:
    it.group.add(P.brazier(seed=seed).translate(x, y, z))
    it.lamps.append([round(x, 2), round(y + 1.6, 2), round(z, 2)])


def _room(it: Interior, key: str, x0, z0, x1, z1, floor_y, height, pal, *, ceiling="flat",
          doors=(), vault_rise=2.2, walls=None, floor=None, ceil=None, open_sky=False):
    it.space(key, x0, z0, x1, z1, floor_y, height,
             floor_mat=floor or pal["floor"], wall_mat=walls or pal["wall"],
             ceil_mat=ceil or pal["ceil"], doors=list(doors),
             ceiling="open" if open_sky else ceiling, vault_rise=vault_rise)


def _area(it: Interior, kind: str, multiplier: int, *spaces: str) -> None:
    it.areas.append({"kind": kind, "multiplier": int(multiplier), "spaces": list(spaces)})


def _spawn(it: Interior, creature: str, count: int, space: str) -> None:
    it.spawns.append({"creature": creature, "count": int(count), "space": space})


def _begin(secret: Secret, palette: dict, klass: str) -> tuple[Interior, dict]:
    pal = _palette(palette, floor="packed_earth", wall="cliff_rock", ceil="cliff_rock",
                   rock="cliff_rock", timber="timber_dark", stone="ashlar",
                   water="water_pool", crystal="amethyst_crystal", cloth="woven_cloth",
                   node="amber_resin", metal="dark_iron", turf="meadow_grass")
    it = Interior(secret.id, secret.name, klass, f"secret-{secret.id}", [0.0, 0.0, 0.0],
                  secret.id)
    it.areas = []
    it.spawns = []
    it.exits = []
    it.kind = secret.kind
    it.secret = secret
    return it, pal


def _finish(it: Interior, entrance_space: str, lamp_points, seed: int, ambient=(0.10, 0.10, 0.12)):
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    it.group.add(lamps)
    it.lamps.extend(placed)
    it.spawn_space = entrance_space
    it.entrance_space = entrance_space
    it.landmark(f"{it.ident}-room", it.name, entrance_space, 1.6)
    it.environment = {"sky": "none",
                      "ambient": {"colour": list(ambient), "energy": 0.5},
                      "fog": {"enabled": True, "colour": [0.02, 0.02, 0.03],
                              "begin": 14.0, "end": 48.0}}
    return it


def _entry_hall(it: Interior, pal: dict, seed: int, depth: float = 4.0, width: float = 5.0):
    """The room a player arrives in: a landing under the entrance, and a
    passage down to whatever the secret is. Every kind starts this way so the
    arrival is always on level ground with the way back behind it."""
    h = width * 0.5
    _room(it, "landing", -h, -h, h, h, 0.0, 4.2, pal, ceiling="vault",
          doors=[("north", 0.0, 3.6, 3.0)], vault_rise=1.8, walls=pal["rock"], ceil=pal["rock"])
    _link(it, "way", (0, h), (0, h + 8.0), 3.6, 0.0, -depth, 3.8,
          floor=pal["floor"], wall=pal["rock"], ceil=pal["rock"], steps=6, seed=seed)
    return h + 8.0, -depth


# --------------------------------------------------------------- the kinds
def grotto(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "cave")
    rng = np.random.default_rng(seed)
    z, depth = _entry_hall(it, pal, seed)
    w = 12.0 * secret.size
    _room(it, "hollow", -w, z, w, z + 2 * w, depth, 8.0, pal, ceiling="vault", vault_rise=3.8,
          doors=[("south", 0.0, 3.6, 3.0)], walls=pal["rock"], ceil=pal["rock"])
    cx, cz = 0.0, z + w
    for index in range(8):
        angle = float(rng.uniform(0, math.tau))
        it.group.add(P.boulder(radius=float(rng.uniform(0.5, 1.3)), seed=seed + index,
                               material=pal["rock"])
                     .translate(cx + math.cos(angle) * w * 0.85, depth, cz + math.sin(angle) * w * 0.8))
    it.group.add(M.box((w * 0.9, 0.06, w * 0.6), center=(cx + w * 0.35, depth + 0.05, cz + w * 0.5),
                       uv_scale=0.25, material=pal["water"]))
    index = 0
    for resource, count in secret.resources:
        for k in range(count):
            angle = math.tau * (index * 0.37 + 0.11)
            radial = 0.35 + 0.45 * ((index * 7) % 5) / 5.0
            _node(it, f"{secret.id}-node-{index:02d}", resource,
                  cx + math.cos(angle) * w * radial, depth, cz + math.sin(angle) * w * radial,
                  seed + 100 + index, pal["node"])
            index += 1
    if secret.area:
        _area(it, secret.area[0], secret.area[1], "hollow")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (-w * 0.5, depth + 4.0, cz), (w * 0.5, depth + 4.0, cz)], seed)


def garden(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "garden")
    rng = np.random.default_rng(seed)
    z, depth = _entry_hall(it, pal, seed, depth=2.0)
    w = 11.0 * secret.size
    _room(it, "court", -w, z, w, z + 2 * w, depth, 6.0, pal, open_sky=True,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["turf"], walls=pal["stone"], ceil=pal["stone"])
    cx, cz = 0.0, z + w
    # raised beds in two ranks, a resource to each bed, so the pairs a recipe
    # wants stand a step apart
    beds = []
    for row in range(2):
        for col in range(3):
            bx = cx - w * 0.55 + col * w * 0.55
            bz = cz - w * 0.4 + row * w * 0.8
            it.group.add(M.box((w * 0.42, 0.5, w * 0.34), center=(bx, depth + 0.25, bz), uv_scale=0.6,
                               material=pal["stone"]))
            beds.append((bx, bz))
    index = 0
    for slot, (resource, count) in enumerate(secret.resources):
        bx, bz = beds[slot % len(beds)]
        for k in range(count):
            _node(it, f"{secret.id}-node-{index:02d}", resource,
                  bx - w * 0.14 + (k % 3) * w * 0.14, depth + 0.5, bz - 0.8 + (k // 3) * 1.6,
                  seed + 100 + index, pal["node"])
            index += 1
    it.group.add(P.well(radius=0.9, seed=seed).translate(cx, depth, cz))
    it.interactives.append({"id": f"{secret.id}-well", "kind": "water_source", "target": "refreshment",
                            "label": "Garden well", "text": "Cold water from the garden well.",
                            "position": [cx, depth + 1.0, cz]})
    for corner in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        wood, leaves = TREES.build_tree("sapling", seed=seed + 5 + corner[0] + 2 * corner[1], detail="mid")
        it.group.add(wood.translate(cx + corner[0] * w * 0.8, depth, cz + corner[1] * w * 0.85))
        it.group.add(leaves.translate(cx + corner[0] * w * 0.8, depth, cz + corner[1] * w * 0.85))
    _area(it, *(secret.area or ("harvest_speed", 2)), "court")
    it = _finish(it, "landing", [(0.0, 3.0, 0.0)], seed, ambient=(0.30, 0.32, 0.28))
    it.environment["sky"] = "none"
    return it


def cache(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "cellar")
    z, depth = _entry_hall(it, pal, seed, depth=3.0)
    w = 7.0 * secret.size
    _room(it, "cellar", -w, z, w, z + 1.6 * w, depth, 4.4, pal, doors=[("south", 0.0, 3.6, 3.0)],
          floor=pal["floor"], walls=pal["wall"], ceil=pal["timber"])
    cx, cz = 0.0, z + 0.8 * w
    _storage(it, f"{secret.id}-cache", cx, depth, cz + 0.5 * w, seed, pal)
    _station(it, f"{secret.id}-bench", cx - w * 0.6, depth, cz + 0.5 * w, seed + 1, pal)
    for k in range(3):
        it.group.add(P.barrel(seed=seed + k).translate(cx + w * 0.7, depth, cz - w * 0.5 + k * 1.1))
    index = 0
    for resource, count in secret.resources:
        for k in range(count):
            _node(it, f"{secret.id}-node-{index:02d}", resource,
                  cx - w * 0.75 + (index % 4) * w * 0.5, depth, cz - w * 0.55 + (index // 4) * 1.8,
                  seed + 100 + index, pal["node"])
            index += 1
    if secret.area:
        _area(it, secret.area[0], secret.area[1], "cellar")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (cx, depth + 3.4, cz)], seed)


def vault(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "vault")
    z, depth = _entry_hall(it, pal, seed, depth=5.0)
    w = 8.0 * secret.size
    _room(it, "strongroom", -w, z, w, z + 1.4 * w, depth, 5.0, pal, ceiling="vault", vault_rise=2.4,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["stone"], ceil=pal["stone"])
    cx, cz = 0.0, z + 0.7 * w
    _storage(it, f"{secret.id}-strongbox", cx, depth, cz + 0.55 * w, seed, pal)
    _station(it, f"{secret.id}-bench", cx + w * 0.55, depth, cz, seed + 1, pal)
    for k in range(4):
        it.group.add(M.box((0.6, 2.4, 0.3), center=(cx - w * 0.85, depth + 1.2, cz - w * 0.5 + k * w * 0.33),
                           uv_scale=0.8, material=pal["timber"]))
    _brazier(it, cx - w * 0.4, depth, cz - w * 0.55, seed)
    _brazier(it, cx + w * 0.4, depth, cz - w * 0.55, seed + 1)
    for title, text in secret.texts:
        _plaque(it, f"{secret.id}-plaque-{len(it.interactives)}", title, text, cx, depth, cz - w * 0.62)
    _area(it, *(secret.area or ("experience", 2)), "strongroom")
    return _finish(it, "landing", [(0.0, 3.0, 0.0)], seed)


def pen(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "pit")
    rng = np.random.default_rng(seed)
    z, depth = _entry_hall(it, pal, seed, depth=4.0)
    w = 10.0 * secret.size
    _room(it, "pit", -w, z, w, z + 2 * w, depth, 7.0, pal, ceiling="vault", vault_rise=3.0,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["floor"], walls=pal["rock"], ceil=pal["rock"])
    cx, cz = 0.0, z + w
    for k in range(4):
        it.group.add(M.box((0.3, 3.0, 0.3), center=(cx - w * 0.85 + k * w * 0.57, depth + 1.5, cz - w * 0.9),
                           uv_scale=1.0, material=pal["timber"]))
    for index in range(6):
        bone = M.cylinder(0.08, 0.06, float(rng.uniform(0.8, 1.6)), 6, uv_scale=1.0, material="pale_ashlar")
        bone.rotate_z(math.pi * 0.5).rotate_y(float(rng.uniform(0.0, math.tau)))
        it.group.add(bone.translate(cx + float(rng.uniform(-w * 0.7, w * 0.7)), depth + 0.08,
                                    cz + float(rng.uniform(-w * 0.7, w * 0.7))))
    it.group.add(M.box((0.4, 1.9, 0.4), center=(cx - w * 0.8, depth + 0.95, cz + w * 0.85), uv_scale=1.0,
                       material=pal["timber"]))
    it.interactives.append({"id": f"{secret.id}-post", "kind": "training", "target": "combat",
                            "label": "Training post", "text": "The post lists your recent combat results.",
                            "position": [round(cx - w * 0.8, 2), round(depth + 1.0, 2), round(cz + w * 0.85, 2)]})
    for creature, count in secret.creatures:
        _spawn(it, creature, count, "pit")
    if secret.area:
        _area(it, secret.area[0], secret.area[1], "pit")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (cx - w * 0.5, depth + 4.5, cz), (cx + w * 0.5, depth + 4.5, cz)], seed)


def school(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "school")
    z, depth = _entry_hall(it, pal, seed, depth=2.0)
    w = 9.0 * secret.size
    _room(it, "hall", -w, z, w, z + 1.5 * w, depth, 5.2, pal, ceiling="vault", vault_rise=2.2,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["wall"], ceil=pal["timber"])
    cx, cz = 0.0, z + 0.75 * w
    for row in range(3):
        for side in (-1, 1):
            it.group.add(M.box((3.0, 0.45, 0.5), center=(cx + side * w * 0.4, depth + 0.22, cz - w * 0.45 + row * w * 0.35),
                               uv_scale=1.0, material=pal["timber"]))
    it.group.add(M.box((1.4, 1.2, 0.6), center=(cx, depth + 0.6, cz + w * 0.55), uv_scale=1.0, material=pal["timber"]))
    for index, (title, text) in enumerate(secret.texts):
        _plaque(it, f"{secret.id}-plaque-{index}", title, text,
                cx - w * 0.8 + index * (w * 1.6 / max(1, len(secret.texts) - 1) if len(secret.texts) > 1 else 0),
                depth, cz + w * 0.68)
    for k in range(5):
        it.group.add(M.box((0.5, 2.6, 0.3), center=(cx - w * 0.9, depth + 1.3, cz - w * 0.6 + k * w * 0.3),
                           uv_scale=0.8, material=pal["timber"]))
    _area(it, *(secret.area or ("fast_reading", 3)), "hall")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (cx, depth + 3.8, cz)], seed, ambient=(0.16, 0.14, 0.12))


def spring(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "spring")
    rng = np.random.default_rng(seed)
    z, depth = _entry_hall(it, pal, seed, depth=3.0)
    w = 8.0 * secret.size
    _room(it, "bath", -w, z, w, z + 1.6 * w, depth, 6.0, pal, ceiling="vault", vault_rise=2.8,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["rock"], ceil=pal["rock"])
    cx, cz = 0.0, z + 0.8 * w
    it.group.add(M.box((w * 1.2, 0.5, w * 0.9), center=(cx, depth + 0.25, cz + 0.2 * w), uv_scale=0.6, material=pal["stone"]))
    it.group.add(M.box((w * 1.05, 0.06, w * 0.75), center=(cx, depth + 0.52, cz + 0.2 * w), uv_scale=0.25, material=pal["water"]))
    for index in range(6):
        angle = float(rng.uniform(0, math.tau))
        it.group.add(P.boulder(radius=float(rng.uniform(0.4, 0.9)), seed=seed + index, material=pal["rock"])
                     .translate(cx + math.cos(angle) * w * 0.85, depth, cz + math.sin(angle) * w * 0.75))
    it.interactives.append({"id": f"{secret.id}-spring", "kind": "water_source", "target": "refreshment",
                            "label": "Warm spring", "text": "The spring is warm and mineral; it restores you.",
                            "position": [round(cx, 2), round(depth + 1.0, 2), round(cz - w * 0.35, 2)]})
    _area(it, *(secret.area or ("fast_regeneration", 3)), "bath")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (cx, depth + 4.2, cz)], seed, ambient=(0.14, 0.16, 0.18))


def range_(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "gallery")
    z, depth = _entry_hall(it, pal, seed, depth=2.0)
    length = 30.0 * secret.size
    _room(it, "gallery", -4.0, z, 4.0, z + length, depth, 5.0, pal, ceiling="vault", vault_rise=2.0,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["floor"], walls=pal["wall"], ceil=pal["timber"])
    # a firing line, and straw butts at the far end
    it.group.add(M.box((7.0, 0.12, 0.6), center=(0.0, depth + 0.06, z + 4.0), uv_scale=0.5, material=pal["timber"]))
    for k in range(3):
        butt = S.MeshGroup()
        butt.add(M.cylinder(0.7, 0.7, 0.5, 12, uv_scale=1.0, material="thatch_reed").rotate_x(math.pi * 0.5)
                 .translate(0.0, 1.2, 0.0))
        butt.add(M.box((0.2, 1.2, 0.2), center=(0.0, 0.6, 0.0), uv_scale=1.0, material=pal["timber"]))
        it.group.add(butt.translate(-2.4 + k * 2.4, depth, z + length - 2.0))
    it.interactives.append({"id": f"{secret.id}-butts", "kind": "training", "target": "combat",
                            "label": "Butts", "text": "The butts list your recent combat results.",
                            "position": [0.0, round(depth + 1.0, 2), round(z + 3.0, 2)]})
    for creature, count in secret.creatures:
        _spawn(it, creature, count, "gallery")
    _area(it, *(secret.area or ("experience", 2)), "gallery")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (0.0, depth + 3.6, z + length * 0.5)], seed)


def reliquary(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "reliquary")
    z, depth = _entry_hall(it, pal, seed, depth=5.0)
    w = 7.0 * secret.size
    _room(it, "cella", -w, z, w, z + 1.8 * w, depth, 6.0, pal, ceiling="vault", vault_rise=3.0,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["stone"], ceil=pal["stone"])
    cx, cz = 0.0, z + 0.9 * w
    it.group.add(M.box((2.2, 1.0, 1.2), center=(cx, depth + 0.5, cz + w * 0.6), uv_scale=0.8, material=pal["stone"]))
    it.group.add(M.box((1.6, 0.06, 0.8), center=(cx, depth + 1.03, cz + w * 0.6), uv_scale=1.0, material="gilt_brass"))
    _brazier(it, cx - w * 0.6, depth, cz + w * 0.5, seed)
    _brazier(it, cx + w * 0.6, depth, cz + w * 0.5, seed + 1)
    for index, (title, text) in enumerate(secret.texts):
        side = -1 if index % 2 == 0 else 1
        _plaque(it, f"{secret.id}-plaque-{index}", title, text, cx + side * w * 0.85, depth,
                cz - w * 0.6 + (index // 2) * w * 0.55, material=pal["stone"])
    it.interactives.append({"id": f"{secret.id}-relic", "kind": "scenery_effect", "target": "relic",
                            "label": secret.name, "text": secret.note or "A relic on its altar.",
                            "position": [round(cx, 2), round(depth + 1.2, 2), round(cz + w * 0.6, 2)]})
    if secret.area:
        _area(it, secret.area[0], secret.area[1], "cella")
    return _finish(it, "landing", [(0.0, 3.0, 0.0)], seed, ambient=(0.12, 0.10, 0.08))


def nullwell(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "pit")
    # five metres down, not six: the server lets a step climb 0.4 m, and the
    # entry stair at six left the well floor unreachable from the landing
    z, depth = _entry_hall(it, pal, seed, depth=5.0)
    w = 9.0 * secret.size
    _room(it, "well", -w, z, w, z + 2 * w, depth, 8.0, pal, ceiling="vault", vault_rise=3.6,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["rock"], ceil=pal["rock"])
    cx, cz = 0.0, z + w
    it.group.add(M.lathe([[2.0, 0.0], [2.0, 0.9], [1.6, 0.95], [1.6, 0.0]], 16, uv_scale=1.0,
                         material=pal["stone"]).translate(cx, depth, cz))
    for k in range(6):
        angle = math.tau * k / 6.0
        it.group.add(MOOR.menhir(height=2.6, seed=seed + k, material=pal["stone"])
                     .translate(cx + math.cos(angle) * w * 0.7, depth, cz + math.sin(angle) * w * 0.7))
    it.interactives.append({"id": f"{secret.id}-post", "kind": "training", "target": "combat",
                            "label": "Ward post", "text": "Nothing casts within these stones. The post lists your recent combat results.",
                            "position": [round(cx - w * 0.85, 2), round(depth + 1.0, 2), round(cz - w * 0.85, 2)]})
    for creature, count in secret.creatures:
        _spawn(it, creature, count, "well")
    _area(it, *(secret.area or ("no_magic", 2)), "well")
    return _finish(it, "landing", [(0.0, 3.0, 0.0), (cx, depth + 5.0, cz)], seed, ambient=(0.08, 0.08, 0.10))


def focus(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "focus")
    z, depth = _entry_hall(it, pal, seed, depth=3.0)
    w = 8.0 * secret.size
    _room(it, "chamber", -w, z, w, z + 1.8 * w, depth, 6.4, pal, ceiling="vault", vault_rise=3.0,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["stone"], ceil=pal["stone"])
    cx, cz = 0.0, z + 0.9 * w
    for k in range(4):
        angle = math.tau * k / 4.0 + math.pi * 0.25
        _brazier(it, cx + math.cos(angle) * w * 0.6, depth, cz + math.sin(angle) * w * 0.6, seed + k)
    it.group.add(CC.cluster(count=5, radius=1.4, height=3.0, seed=seed, material=pal["crystal"])
                 .translate(cx, depth, cz))
    for creature, count in secret.creatures:
        _spawn(it, creature, count, "chamber")
    _area(it, *(secret.area or ("cheap_magic", 2)), "chamber")
    return _finish(it, "landing", [(0.0, 3.0, 0.0)], seed, ambient=(0.14, 0.10, 0.18))


def tunnel(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    """A passage under the border. Its far end is an exit onto another map;
    the composer turns `links` into portals and the far region's own entrance
    points back at `<id>-far`."""
    it, pal = _begin(secret, palette, "tunnel")
    rng = np.random.default_rng(seed)
    z, depth = _entry_hall(it, pal, seed, depth=5.0)
    length = 56.0 * secret.size
    half = 2.4
    _room(it, "bore", -half - 0.5, z, half + 0.5, z + 6.0, depth, 4.0, pal, ceiling="vault", vault_rise=1.6,
          doors=[("south", 0.0, 3.6, 3.0), ("north", 0.0, 3.6, 3.0)], walls=pal["rock"], ceil=pal["rock"])
    _link(it, "run", (0, z + 6.0), (0, z + length - 6.0), 4.2, depth, depth, 3.8,
          floor=pal["floor"], wall=pal["rock"], ceil=pal["rock"], steps=0, seed=seed)
    _room(it, "far", -3.0, z + length - 6.0, 3.0, z + length, depth, 4.2, pal, ceiling="vault", vault_rise=1.8,
          doors=[("south", 0.0, 3.6, 3.0)], walls=pal["rock"], ceil=pal["rock"])
    for k in range(6):
        it.group.add(M.box((0.25, 3.4, 0.25), center=(-half + 0.1 if k % 2 else half - 0.1, depth + 1.7,
                                                      z + 10.0 + k * (length - 20.0) / 5.0),
                           uv_scale=1.0, material=pal["timber"]))
    index = 0
    for resource, count in secret.resources:
        for k in range(count):
            side = -1 if index % 2 else 1
            _node(it, f"{secret.id}-node-{index:02d}", resource, side * 1.5, depth,
                  z + 9.0 + index * (length - 18.0) / max(1, sum(c for _, c in secret.resources)),
                  seed + 100 + index, pal["node"])
            index += 1
    for target_map, target_spawn, label in secret.links:
        it.exits.append({"space": "far", "map": target_map, "spawn": target_spawn, "label": label})
    lamp_points = [(0.0, 3.0, 0.0)] + [(0.0, depth + 3.2, z + 12.0 + k * 14.0) for k in range(int(length // 14))]
    return _finish(it, "landing", lamp_points, seed)


def waystone(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    """A hub: a stone per linked hub, each an exit onto that map."""
    it, pal = _begin(secret, palette, "waystone")
    z, depth = _entry_hall(it, pal, seed, depth=4.0)
    w = 9.0 * secret.size
    _room(it, "ring", -w, z, w, z + 2 * w, depth, 7.0, pal, ceiling="vault", vault_rise=3.4,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["stone"], ceil=pal["stone"])
    cx, cz = 0.0, z + w
    it.group.add(M.cylinder(w * 0.55, w * 0.55, 0.18, 24, uv_scale=0.4, material=pal["stone"])
                 .translate(cx, depth, cz))
    count = max(1, len(secret.links))
    for index, (target_map, target_spawn, label) in enumerate(secret.links):
        angle = math.pi + math.tau * (index + 1) / (count + 1)
        sx, sz = cx + math.cos(angle) * w * 0.72, cz + math.sin(angle) * w * 0.72
        it.group.add(MOOR.menhir(height=3.2, seed=seed + index, material=pal["stone"]).translate(sx, depth, sz))
        it.group.add(M.box((0.5, 0.5, 0.12), center=(sx, depth + 1.6, sz - 0.5), uv_scale=1.0, material="gilt_brass"))
        it.exits.append({"space": "ring", "map": target_map, "spawn": target_spawn, "label": label,
                         "position": [round(sx + math.cos(angle + math.pi) * 1.6, 2), round(depth, 2),
                                      round(sz + math.sin(angle + math.pi) * 1.6, 2)]})
    _brazier(it, cx, depth, cz, seed)
    return _finish(it, "landing", [(0.0, 3.0, 0.0)], seed, ambient=(0.12, 0.12, 0.16))


def eyrie(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    it, pal = _begin(secret, palette, "eyrie")
    z, depth = _entry_hall(it, pal, seed, depth=-3.0)
    w = 6.0 * secret.size
    _room(it, "perch", -w, z, w, z + 1.6 * w, depth, 4.6, pal, open_sky=True,
          doors=[("south", 0.0, 3.6, 3.0)], floor=pal["stone"], walls=pal["rock"], ceil=pal["rock"])
    cx, cz = 0.0, z + 0.8 * w
    it.group.add(P.well(radius=0.7, seed=seed).translate(cx + w * 0.5, depth, cz))
    it.interactives.append({"id": f"{secret.id}-water", "kind": "water_source", "target": "refreshment",
                            "label": "Cistern", "text": "Rainwater from the cistern.",
                            "position": [round(cx + w * 0.5, 2), round(depth + 1.0, 2), round(cz, 2)]})
    for index, (title, text) in enumerate(secret.texts):
        _plaque(it, f"{secret.id}-plaque-{index}", title, text, cx - w * 0.6 + index * 2.2, depth, cz + w * 0.65)
    it.group.add(P.log_pile(length=2.0, rows=2, per_row=4, seed=seed).translate(cx - w * 0.7, depth, cz - w * 0.5))
    _area(it, *(secret.area or ("fast_regeneration", 2)), "perch")
    return _finish(it, "landing", [(0.0, 3.0, 0.0)], seed, ambient=(0.28, 0.30, 0.34))


BUILDERS = {
    "grotto": grotto, "garden": garden, "cache": cache, "vault": vault, "pen": pen,
    "school": school, "spring": spring, "range": range_, "reliquary": reliquary,
    "nullwell": nullwell, "focus": focus, "tunnel": tunnel, "waystone": waystone, "eyrie": eyrie,
}


def build(secret: Secret, palette: dict, seed: int = 0) -> Interior:
    if secret.kind not in BUILDERS:
        raise KeyError(f"{secret.id}: unknown secret kind {secret.kind!r}")
    return BUILDERS[secret.kind](secret, palette, seed)


# ------------------------------------------------------- the entrance props
def entrance_prop(kind: str, palette: dict | None = None, seed: int = 0) -> S.MeshGroup:
    """What stands on the ground above: small, readable, and solid."""
    pal = _palette(palette, rock="cliff_rock", timber="timber_dark", stone="ashlar",
                   turf="meadow_grass", crystal="amethyst_crystal", metal="dark_iron",
                   reed="thatch_reed", bark="bark_dark", ice="glacier_ice", sand="shore_shingle")
    out = S.MeshGroup()
    rng = np.random.default_rng(seed)
    if kind == "loose_stone":
        out.add(P.rock_cluster(radius=1.4, count=4, seed=seed, material=pal["rock"]))
        out.add(M.box((1.2, 1.4, 0.5), center=(0.0, 0.7, 0.9), uv_scale=1.0, material=pal["rock"]).rotate_y(0.3))
    elif kind == "hollow_tree":
        out.add(TREES.stump(radius=1.1, height=2.6, seed=seed, material=pal["bark"]))
        out.add(M.box((0.9, 1.4, 0.4), center=(0.0, 0.8, 1.05), uv_scale=1.0, material=pal.get("dark", "scorched_ground")))
    elif kind == "ice_crack":
        out.add(P.boulder(radius=1.6, seed=seed, material=pal["ice"]))
        out.add(M.box((0.35, 1.2, 2.4), center=(0.0, 0.8, 0.0), uv_scale=1.0, material=pal.get("dark", "scorched_ground")))
    elif kind == "cracked_slab":
        out.add(M.box((2.2, 0.18, 2.2), center=(0.0, 0.09, 0.0), uv_scale=0.8, material=pal["stone"]).rotate_y(0.15))
        out.add(M.box((0.16, 0.04, 2.0), center=(0.2, 0.2, 0.0), uv_scale=1.0, material=pal.get("dark", "scorched_ground")).rotate_y(0.4))
    elif kind == "reed_hide":
        out.add(P.undergrowth_patch(radius=1.6, count=9, seed=seed, height=1.8))
        out.add(M.box((1.6, 0.1, 1.2), center=(0.0, 0.05, 0.0), uv_scale=1.0, material=pal["timber"]))
    elif kind == "root_door":
        out.add(TREES.stump(radius=0.7, height=1.4, seed=seed, material=pal["bark"]).translate(-1.2, 0.0, 0.0))
        out.add(TREES.stump(radius=0.7, height=1.4, seed=seed + 1, material=pal["bark"]).translate(1.2, 0.0, 0.0))
        out.add(M.box((2.8, 0.4, 0.5), center=(0.0, 2.0, 0.0), uv_scale=1.0, material=pal["bark"]))
        out.add(M.box((1.4, 1.9, 0.14), center=(0.0, 0.95, 0.0), uv_scale=1.0, material=pal["timber"]))
    elif kind == "shrine_slab":
        out.add(M.box((1.8, 0.3, 1.2), center=(0.0, 0.15, 0.0), uv_scale=0.8, material=pal["stone"]))
        out.add(MOOR.votive_candle(seed=seed).translate(0.6, 0.3, 0.3))
        out.add(MOOR.votive_candle(seed=seed + 1).translate(-0.5, 0.3, -0.2))
    elif kind == "well_shaft":
        out.add(P.well(radius=0.95, seed=seed))
    elif kind == "crystal_seam":
        out.add(CC.vein_scatter(radius=1.8, count=7, seed=seed, material=pal["crystal"]))
        out.add(M.box((1.0, 1.6, 0.4), center=(0.0, 0.8, 0.8), uv_scale=1.0, material=pal["rock"]))
    elif kind == "drain_grate":
        out.add(M.box((1.6, 0.16, 1.6), center=(0.0, 0.08, 0.0), uv_scale=1.0, material=pal["stone"]))
        for k in range(5):
            out.add(M.box((1.2, 0.05, 0.06), center=(0.0, 0.18, -0.5 + k * 0.25), uv_scale=1.0, material=pal["metal"]))
    elif kind == "tide_cave":
        out.add(P.boulder(radius=1.8, seed=seed, material=pal["rock"]).translate(-1.4, 0.0, 0.0))
        out.add(P.boulder(radius=1.6, seed=seed + 1, material=pal["rock"]).translate(1.5, 0.0, 0.0))
        out.add(M.box((3.6, 0.5, 1.4), center=(0.0, 2.2, 0.0), uv_scale=1.0, material=pal["rock"]))
    elif kind == "cellar_hatch":
        out.add(M.box((1.8, 0.2, 1.4), center=(0.0, 0.1, 0.0), uv_scale=1.0, material=pal["timber"]).rotate_y(0.2))
        out.add(M.box((0.3, 0.08, 0.5), center=(0.5, 0.24, 0.0), uv_scale=1.0, material=pal["metal"]))
    elif kind == "cairn":
        out.add(MOOR.cairn(height=1.9, seed=seed, lit=False))
    elif kind == "chimney":
        out.add(M.cylinder(0.7, 0.55, 2.6, 10, uv_scale=1.0, material=pal["stone"]))
        out.add(M.cylinder(0.75, 0.75, 0.2, 10, uv_scale=1.0, material=pal["stone"]).translate(0.0, 2.6, 0.0))
    elif kind == "ivy_arch":
        out.add(M.box((0.5, 2.6, 0.5), center=(-1.3, 1.3, 0.0), uv_scale=1.0, material=pal["stone"]))
        out.add(M.box((0.5, 2.6, 0.5), center=(1.3, 1.3, 0.0), uv_scale=1.0, material=pal["stone"]))
        out.add(M.box((3.2, 0.5, 0.6), center=(0.0, 2.85, 0.0), uv_scale=1.0, material=pal["stone"]))
        out.add(P.undergrowth_patch(radius=1.3, count=8, seed=seed, height=2.4))
    elif kind == "sand_sink":
        out.add(M.lathe([[2.2, 0.0], [1.6, -0.5], [0.6, -1.2], [0.0, -1.3]], 16, uv_scale=1.0,
                        material=pal["sand"]))
        out.add(P.rock_cluster(radius=1.0, count=3, seed=seed, material=pal["rock"]).translate(1.8, 0.0, 0.6))
    else:
        raise KeyError(f"unknown entrance prop {kind!r}")
    return out


def prop_materials(kinds, palette: dict | None = None) -> set[str]:
    """The materials the entrance props of these kinds use under `palette`.

    Built with the same palette the dresser builds them with, so the pin a
    region derives from this is the set its props really reference.
    """
    out: set[str] = set()
    for kind in set(kinds):
        for part in entrance_prop(kind, palette, seed=1).all_parts:
            out.add(part.material)
    return out
