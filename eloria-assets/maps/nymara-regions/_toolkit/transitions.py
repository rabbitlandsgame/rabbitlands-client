"""The marches: where one region's country gives way to its neighbour's.

Nymara is one continent, but a player crosses it one map at a time. Without
help, every crossing is a hard cut: autumn forest on this side of a tile,
snowfield on the other. This module makes the last stretch of road before a
crossing belong to both regions at once.

Each declared crossing (`Crossing`) gets:

* a **march** - a fan of the neighbour's ground, painted into this region's
  terrain classes and thinning back into the local ground with distance, with
  the neighbour's growth scattered through it: pines and drifted boulders
  before the Whitehorn, crystal breaking out of the dust before the Barrens,
  dead snags and heather before the Moors, ferns before the jungle regions,
  reeds and beached boats before the lake;
* the **road furniture of the people who keep this side of the road** - lamp
  posts for the Luminous, cairns for the Votary, tuned shards for the
  Glasswardens, wind-banners for the Orun, bollards and a customs post for
  Greyhaven, stelae for the Ssarathi, standing stones for the Stoneborn,
  lantern-hung snags and mushroom rings for the Mycelari - spaced down the last
  eighty metres so the road reads as a road that goes somewhere;
* a **march stone** naming the country beyond, a signpost, and a small
  **waystation** off the road - somewhere a traveller would actually stop.

The geometry is the shared kits; nothing here is a new primitive. A region
calls `prepare()` before it scatters its own forest, so the clearing around the
station is kept, and `dress()` after, so the furniture stands on the ground the
region finally has. `paint()` goes between the region's own surface painting
and `despeckle_surfaces()`.

Materials: every material this module emits is listed per neighbour and per
culture in `MATERIALS_FOR`, so a region can pin exactly what its marches add.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from amberwood import architecture as ARCH
from amberwood import crystalcraft as CC
from amberwood import junglecraft as JC
from amberwood import mesh as M
from amberwood import moorcraft as MOOR
from amberwood import noise as N
from amberwood import props as PROPS
from amberwood import stonework as SW
from amberwood import terrain as TER
from amberwood import trees as TREES
from regionbuild import Placement, RegionBuild

# ---------------------------------------------------------------- the world
# Who keeps the roads in each region. Where a region is disputed the roadside
# is cast the way npc_dialogue.txt casts its posts: the Greyhaven league keeps
# the moor causeways, the Ssarathi keep the delta and the stair.
PEOPLE = {
    "mirrorhold": "luminous", "four_gates": "luminous",
    "whitehorn_range": "votary",
    "amethyst_barrens": "glasswarden",
    "sunmane_steppe": "orun",
    "westhaven": "greyhaven", "grey_moors": "greyhaven", "crownwater": "greyhaven",
    "ssarathi_ruins": "ssarathi", "manymouth_delta": "ssarathi", "verdant_stair": "ssarathi",
    "amberwood": "mycelari",
}

TITLES = {
    "mirrorhold": "Mirrorhold", "four_gates": "Four Gates",
    "whitehorn_range": "the Whitehorn Range", "amethyst_barrens": "the Amethyst Barrens",
    "sunmane_steppe": "the Sunmane Steppe", "westhaven": "Westhaven",
    "grey_moors": "the Grey Moors", "crownwater": "Crownwater",
    "ssarathi_ruins": "the Ssarathi Ruins", "manymouth_delta": "the Manymouth Delta",
    "verdant_stair": "the Verdant Stair", "amberwood": "the Amberwood",
}

# The ground of each region as a neighbour sees it: the material that is
# painted into the march. Deliberately one material per region, and one that
# the shared texture table can build, so a region embeds one extra texture
# set per neighbour rather than a whole second kit.
NEIGHBOUR_GROUND = {
    "whitehorn_range": "snow_pack",
    "mirrorhold": "alpine_turf",
    "amethyst_barrens": "amethyst_barrens_dust",
    "sunmane_steppe": "meadow_grass",
    "amberwood": "forest_floor",
    "grey_moors": "grey_heather_moor",
    "westhaven": "meadow_grass",
    "crownwater": "shore_shingle",
    "four_gates": "cobble_paving",
    "verdant_stair": "verdant_jungle_floor",
    "ssarathi_ruins": "verdant_jungle_floor",
    "manymouth_delta": "shore_shingle",
}

# Everything a march can emit, by the neighbour it faces and by the culture
# whose furniture lines it. `materials_for()` folds these for a region.
MATERIALS_FOR = {
    "ground": {region: {material} for region, material in NEIGHBOUR_GROUND.items()},
    "growth": {
        "whitehorn_range": {"bark_dark", "foliage_green", "cliff_rock", "snow_pack",
                            "grey_moor_granite"},
        "mirrorhold": {"bark_dark", "foliage_green", "pale_ashlar", "cliff_rock"},
        "amethyst_barrens": {"amethyst_crystal", "amethyst_storm_rock"},
        "sunmane_steppe": {"woven_cloth", "timber_dark", "cliff_rock"},
        "amberwood": {"bark_oak", "bark_dark", "foliage_amber", "foliage_rust"},
        "grey_moors": {"grey_moor_granite", "grey_dead_bark", "grey_moor_scrub"},
        "westhaven": {"timber_grey", "shore_shingle", "cliff_rock"},
        "crownwater": {"undergrowth", "timber_grey", "cliff_rock"},
        "four_gates": {"undergrowth", "dark_iron", "ashlar"},
        "verdant_stair": {"verdant_frond", "bark_dark", "bark_pale"},
        "ssarathi_ruins": {"verdant_frond", "bark_dark", "bark_pale"},
        "manymouth_delta": {"verdant_frond", "bark_dark", "timber_grey", "undergrowth"},
    },
    "culture": {
        "luminous": {"dark_iron", "ashlar", "amber_resin", "pale_ashlar", "slate_roof"},
        "votary": {"grey_moor_granite", "grey_votive_flame", "pale_ashlar", "ashlar",
                   "timber_dark"},
        "glasswarden": {"amethyst_crystal", "amethyst_brass", "amethyst_pale_stone",
                        "amethyst_storm_rock"},
        "orun": {"woven_cloth", "canvas_awning", "timber_dark", "timber_warm",
                 "rubble_stone", "dark_iron"},
        "greyhaven": {"timber_grey", "rubble_stone", "shingles", "dark_iron",
                      "timber_dark"},
        "ssarathi": {"verdant_carved_jade", "verdant_jade", "gilt_brass",
                     "verdant_terrace_stone"},
        "stoneborn": {"grey_moor_granite", "grey_carved_stone"},
        "mycelari": {"amber_resin", "bark_dark", "dark_iron", "timber_dark"},
    },
}


def _collect(meshes) -> set[str]:
    out: set[str] = set()
    for mesh in meshes:
        if mesh is None:
            continue
        parts = getattr(mesh, "all_parts", None)
        for part in (parts if parts is not None else [mesh]):
            out.add(part.material)
    return out


def materials_for(region: str, crossings) -> set[str]:
    """The material names the marches of `region` will reference.

    Derived by building one of each piece the marches place and reading the
    materials off it, rather than from a list kept by hand - a hand-kept list
    is exactly the thing that goes stale when a kit piece changes its roof.
    """
    culture = PEOPLE[region]
    furniture, _, _ = CULTURE_FURNITURE[culture]
    out = _collect([_station(culture, 1), _march_stone(culture, "x", 1),
                    PROPS.signpost(seed=1, arms=2), furniture(1)])
    for crossing in crossings:
        out |= MATERIALS_FOR["ground"][crossing.neighbour]
        for name, _count in GROWTH.get(crossing.neighbour, ()):
            out |= _collect(_growth_piece(name, 0, "sample", crossing))
    return out


@dataclass
class Crossing:
    """One map-to-map transition as this region sees it.

    `position` is the portal, in metres; `toward` is a point further along the
    road *out* of the region (the map edge the road leaves by), which fixes
    the direction the march faces. `radius` is how far the neighbour's ground
    reaches back into the region.
    """
    id: str
    neighbour: str
    position: tuple[float, float]
    toward: tuple[float, float]
    radius: float = 46.0
    road_width: float = 5.0
    ferry: bool = False
    name: str = ""
    ground_class: int | None = None
    station_position: tuple[float, float] | None = None

    def direction(self) -> tuple[float, float]:
        dx = self.toward[0] - self.position[0]
        dz = self.toward[1] - self.position[1]
        length = math.hypot(dx, dz) or 1.0
        return dx / length, dz / length


@dataclass
class March:
    """What `dress()` reports back for the manifest."""
    landmarks: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- terrain
_FREE_CLASSES = [11, 12, 13, 14, 19, 20, 21, 22, 33, 34, 35, 36, 37, 38, 39, 40]


def march_class(materials: dict[int, str], neighbour: str, label: str | None = None) -> int:
    """Allocate a terrain class for a neighbour's ground in this region.

    Terrain classes are small integers shared across the toolkit, and several
    regions reuse the same numbers for their own ground, so a march never
    borrows the neighbour's class id - it takes an unused one, names it, and
    maps it to the neighbour's material in the region's own table.
    """
    material = NEIGHBOUR_GROUND[neighbour]
    for class_id, existing in materials.items():
        if existing == material and TER.SURFACE_NAMES.get(class_id, "").startswith("March"):
            return class_id
    used = set(TER.SURFACE_NAMES) | set(materials)
    for class_id in _FREE_CLASSES:
        if class_id not in used:
            break
    else:
        raise RuntimeError("no free terrain class for a march")
    TER.SURFACE_NAMES[class_id] = label or f"March{neighbour.title().replace('_', '')}"
    materials[class_id] = material
    TER.AUTHORED_SURFACES.discard(class_id)
    return class_id


def prepare(t: TER.Terrain, crossings, *, clearing: float = 9.0) -> None:
    """Keep the waystation ground clear of the region's own scatter."""
    for crossing in crossings:
        sx, sz = _station_site(crossing)
        t.tree_block |= np.hypot(t.gx - sx, t.gz - sz) < clearing
        px, pz = crossing.position
        t.tree_block |= np.hypot(t.gx - px, t.gz - pz) < crossing.road_width * 1.6


def paint(t: TER.Terrain, crossings, materials: dict[int, str], seed: int,
          sea_level: float = 0.0, keep=(), override=()) -> None:
    """Paint each crossing's march into the terrain classes.

    The neighbour's ground is dense at the crossing and breaks up with
    distance along a warped noise, so the edge reads as country changing
    rather than as a disc of a different colour. Authored surfaces - roads,
    paving, terraces - are never overpainted; `keep` names further classes a
    region wants left alone (its water margins, its own built ground), and
    `override` names authored classes a region *does* want the march to take
    - Amberwood's burnt ground, for one, which the turf of the citadel road
    should be seen to reclaim.
    """
    protected = (TER.AUTHORED_SURFACES | set(keep)) - set(override)
    authored = np.isin(t.surface, sorted(protected))
    dry = t.height > sea_level + 0.9
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    gentle = np.hypot(gradient_x, gradient_z) < 1.25
    for index, crossing in enumerate(crossings):
        if crossing.ground_class is None:
            crossing.ground_class = march_class(materials, crossing.neighbour)
        px, pz = crossing.position
        dirx, dirz = crossing.direction()
        dx = t.gx - px
        dz = t.gz - pz
        distance = np.hypot(dx, dz)
        along = dx * dirx + dz * dirz
        # dense at the portal, fading over the radius; fuller on the far side,
        # where the road has already left, than back towards the region
        weight = np.clip(1.0 - distance / crossing.radius, 0.0, 1.0) ** 0.75
        weight *= 0.62 + 0.38 * np.clip(along / crossing.radius + 0.6, 0.0, 1.0)
        noise = N.warped_fbm(t.gx * 0.045, t.gz * 0.045, warp=0.8, octaves=4,
                             seed=seed + 17 * index + N.stable_hash(crossing.id) % 211)
        mask = (weight * 0.85 + (noise - 0.5) * 0.55) > 0.34
        mask &= ~authored & dry & gentle
        t.surface = np.where(mask, crossing.ground_class, t.surface)


# ---------------------------------------------------------------- placing
def _register(build: RegionBuild, key: str, item) -> str:
    if key not in build.meshes:
        build.meshes[key] = item
    return key


def _ground(t: TER.Terrain, x: float, z: float) -> float:
    return float(t.height_at(x, z))


def _open(t: TER.Terrain, x: float, z: float, sea_level: float) -> bool:
    if bool(t.blocked_at(x, z)):
        return False
    if _ground(t, x, z) < sea_level + 0.9:
        return False
    return float(t.slope_at(x, z)) < 0.9


def _station_site(crossing: Crossing) -> tuple[float, float]:
    """An authored shore apron, or the usual setback on an open land road."""
    if crossing.station_position is not None:
        return crossing.station_position
    dirx, dirz = crossing.direction()
    # perpendicular, to the right when walking out
    side = (dirz, -dirx)
    back = 22.0
    offset = crossing.road_width * 0.5 + 9.0
    return (crossing.position[0] - dirx * back + side[0] * offset,
            crossing.position[1] - dirz * back + side[1] * offset)


def _place(build: RegionBuild, t: TER.Terrain, node: str, key: str, mesh,
           x: float, z: float, *, rotation: float = 0.0, scale: float = 1.0,
           kind: str = "prop", collides: bool = False, sink: float = 0.0,
           landmark: str | None = None, y: float | None = None) -> Placement:
    _register(build, key, mesh)
    height = _ground(t, x, z) if y is None else y
    return build.place(Placement(node=node, mesh=key,
                                 position=(round(x, 3), round(height - sink, 3), round(z, 3)),
                                 rotation_y=rotation, scale=scale, collides=collides,
                                 kind=kind, landmark=landmark))


def _facing(from_xz, to_xz) -> float:
    return math.atan2(to_xz[0] - from_xz[0], to_xz[1] - from_xz[1])


# ---------------------------------------------------------------- furniture
def _lamp(seed: int) -> SW.MeshGroup:
    return SW.lamp_post(height=2.9)


def _cairn(seed: int) -> SW.MeshGroup:
    return MOOR.cairn(height=1.6 + 0.3 * (seed % 3), seed=seed, lit=True)


def _tuned_shard(seed: int) -> SW.MeshGroup:
    out = SW.MeshGroup()
    out.add(M.box((0.9, 0.5, 0.9), center=(0.0, 0.25, 0.0), uv_scale=0.8,
                  material="amethyst_pale_stone"))
    out.add(M.cylinder(0.22, 0.22, 0.08, 12, uv_scale=1.0, material="amethyst_brass")
            .translate(0.0, 0.5, 0.0))
    out.add(CC.shard(1.9 + 0.2 * (seed % 3), 0.28, faces=6, seed=seed,
                     material="amethyst_crystal").translate(0.0, 0.55, 0.0))
    return out


def _wind_banner(seed: int) -> SW.MeshGroup:
    out = SW.MeshGroup()
    out.add(M.cylinder(0.08, 0.06, 4.2, 7, uv_scale=1.2, material="timber_dark"))
    out.add(M.box((0.9, 0.06, 0.06), center=(0.45, 4.0, 0.0), uv_scale=1.0,
                  material="timber_dark"))
    cloth = PROPS.banner(width=0.7, height=2.3, seed=seed, material="woven_cloth")
    out.add(cloth.translate(0.5, 3.95, 0.0))
    return out


def _bollard(seed: int) -> SW.MeshGroup:
    out = SW.MeshGroup()
    out.add(M.cylinder(0.24, 0.20, 1.05, 10, uv_scale=1.0, material="timber_grey"))
    out.add(M.cylinder(0.26, 0.26, 0.10, 10, uv_scale=1.0, material="dark_iron")
            .translate(0.0, 0.62, 0.0))
    return out


def _stela(seed: int) -> SW.MeshGroup:
    return JC.shrine_post(height=2.4 + 0.2 * (seed % 3), seed=seed)


def _menhir(seed: int) -> M.Mesh:
    return MOOR.menhir(height=2.4 + 0.4 * (seed % 3), seed=seed)


def _lantern_snag(seed: int) -> SW.MeshGroup:
    out = SW.MeshGroup()
    wood, _ = TREES.build_tree("burnt_snag", seed=seed, detail="mid")
    wood = wood.with_material("bark_dark")
    out.add(wood.scale(0.45, 0.42, 0.45))
    out.add(PROPS.hanging_lantern(seed=seed, drop=0.6).translate(0.35, 2.9, 0.1))
    out.add(PROPS.mushroom_cluster(seed=seed + 3, count=5, material="amber_resin")
            .translate(0.4, 0.0, 0.5))
    return out


CULTURE_FURNITURE = {
    "luminous": (_lamp, 12.0, "both"),
    "votary": (_cairn, 10.0, "alternate"),
    "glasswarden": (_tuned_shard, 14.0, "alternate"),
    "orun": (_wind_banner, 11.0, "alternate"),
    "greyhaven": (_bollard, 6.0, "both"),
    "ssarathi": (_stela, 12.0, "alternate"),
    "stoneborn": (_menhir, 12.0, "alternate"),
    "mycelari": (_lantern_snag, 13.0, "alternate"),
}


# ---------------------------------------------------------------- stations
def _station(culture: str, seed: int) -> SW.MeshGroup:
    """A small place to stop, in the manner of the people who keep the road."""
    rng = N.Rng(seed)
    out = SW.MeshGroup()
    if culture == "luminous":
        # a lantern pavilion: the register's light at the edge of its writ
        out.add(SW.rotunda(radius=2.4, height=3.6, columns=6, seed=seed))
        out.add(SW.lamp_post(height=2.4).translate(0.0, 0.9, 0.0))
    elif culture == "votary":
        # a drystone shelter with a low door, a bench and a cairn beside it
        shelter = SW.MeshGroup()
        for sign in (-1.0, 1.0):
            shelter.add(M.box((0.6, 2.4, 5.0), center=(sign * 2.4, 1.2, 0.0), uv_scale=0.6,
                              material="pale_ashlar"))
        shelter.add(M.box((5.4, 2.4, 0.6), center=(0.0, 1.2, -2.2), uv_scale=0.6,
                          material="pale_ashlar"))
        shelter.add(M.gable_roof(5.8, 5.6, 1.6, overhang=0.4, material="timber_dark")
                    .translate(0.0, 2.4, 0.0))
        shelter.add(M.box((3.6, 0.42, 0.7), center=(0.0, 0.21, -1.4), uv_scale=0.6,
                          material="ashlar"))
        out.add(shelter)
        out.add(MOOR.cairn(height=1.9, seed=seed, lit=True).translate(4.4, 0.0, 1.2))
    elif culture == "glasswarden":
        # a tuning stand: brass ring on a plinth, shards set to it
        out.add(M.cylinder(2.2, 2.4, 0.5, 16, uv_scale=0.6, material="amethyst_pale_stone"))
        ring = M.lathe([[1.5, 0.0], [1.6, 0.0], [1.6, 0.14], [1.5, 0.14]], 32,
                       material="amethyst_brass")
        out.add(ring.translate(0.0, 0.5, 0.0))
        for index in range(5):
            angle = 2.0 * math.pi * index / 5.0
            out.add(CC.shard(1.6 + 0.4 * (index % 2), 0.26, faces=6, seed=seed + index,
                             material="amethyst_crystal")
                    .translate(math.cos(angle) * 1.1, 0.5, math.sin(angle) * 1.1))
        out.add(CC.outcrop(seed=seed + 9, radius=1.6, height=2.2).translate(-4.0, -0.3, 1.5))
    elif culture == "orun":
        # a caravan halt: an awning, a trough, a stack of stores, banners
        out.add(PROPS.market_stall(width=3.2, depth=2.4, seed=seed))
        out.add(PROPS.barrel(seed=seed + 1).translate(2.4, 0.0, 1.4))
        out.add(PROPS.barrel(seed=seed + 2).translate(2.9, 0.0, 0.8))
        out.add(PROPS.crate(seed=seed + 3).translate(-2.6, 0.0, 1.5))
        out.add(M.box((2.8, 0.7, 0.9), center=(0.0, 0.35, 3.2), uv_scale=0.8,
                      material="rubble_stone"))
        for index, sx in enumerate((-3.4, 3.4)):
            out.add(_wind_banner(seed + 10 + index).translate(sx, 0.0, -1.5))
    elif culture == "greyhaven":
        # a customs post: the league weighs what crosses
        out.add(ARCH.watchtower(height=8.0, seed=seed, radius=1.5))
        out.add(PROPS.fence(length=4.0, height=1.1, seed=seed).translate(3.6, 0.0, 1.2))
        out.add(PROPS.crate(seed=seed + 4).translate(-2.6, 0.0, 1.8))
        out.add(PROPS.crate(size=0.5, seed=seed + 5).translate(-2.6, 0.57, 1.8))
        out.add(PROPS.barrel(seed=seed + 6).translate(-3.3, 0.0, 1.1))
        out.add(PROPS.cart(seed=seed + 7).translate(2.2, 0.0, -2.8))
    elif culture == "ssarathi":
        # a water shrine: a small pagoda over a carved basin
        out.add(JC.pagoda(radius=2.6, tiers=2, height=4.6, seed=seed, columns=6))
        out.add(JC.relief_panel(width=1.6, height=1.0, seed=seed).translate(0.0, 0.0, 3.2))
    elif culture == "stoneborn":
        out.add(MOOR.stone_ring(radius=3.6, count=6, seed=seed, altar=True, height=2.2))
    else:  # mycelari
        out.add(TREES.fallen_log(length=6.5, radius=0.6, seed=seed))
        out.add(PROPS.mushroom_cluster(seed=seed + 1, count=6, material="amber_resin")
                .translate(1.4, 0.0, 1.2))
        out.add(PROPS.mushroom_cluster(seed=seed + 2, count=4, material="amber_resin")
                .translate(-2.2, 0.0, -1.0))
        out.add(PROPS.hanging_lantern(seed=seed, drop=0.5).translate(0.0, 2.2, 0.0))
        out.add(M.cylinder(0.07, 0.06, 2.3, 6, uv_scale=1.0, material="timber_dark")
                .translate(0.0, 0.0, 0.0))
    return out


def _march_stone(culture: str, neighbour: str, seed: int) -> SW.MeshGroup:
    """The boundary marker. Every people cuts one; they differ in what they cut."""
    out = SW.MeshGroup()
    if culture in ("stoneborn", "votary", "greyhaven"):
        out.add(MOOR.menhir(height=3.2, seed=seed, material="grey_moor_granite"))
        out.add(M.box((0.8, 0.6, 0.12), center=(0.0, 1.5, 0.42), uv_scale=1.0,
                      material="grey_carved_stone" if culture == "stoneborn" else "ashlar"))
    elif culture == "glasswarden":
        out.add(M.box((1.2, 0.9, 1.2), center=(0.0, 0.45, 0.0), uv_scale=0.8,
                      material="amethyst_pale_stone"))
        out.add(CC.cluster(count=4, radius=0.5, height=2.6, seed=seed,
                           material="amethyst_crystal").translate(0.0, 0.9, 0.0))
    elif culture == "ssarathi":
        out.add(M.box((1.4, 0.5, 1.4), center=(0.0, 0.25, 0.0), uv_scale=0.8,
                      material="verdant_terrace_stone"))
        out.add(JC.relief_panel(width=1.2, height=2.2, depth=0.4, seed=seed)
                .translate(0.0, 0.5, 0.0))
    elif culture == "orun":
        out.add(M.box((1.0, 0.4, 1.0), center=(0.0, 0.2, 0.0), uv_scale=0.8,
                      material="rubble_stone"))
        for index in range(3):
            out.add(_wind_banner(seed + index).translate((index - 1) * 0.7, 0.4, 0.0))
    elif culture == "mycelari":
        out.add(TREES.stump(radius=1.0, height=1.5, seed=seed, material="bark_dark"))
        out.add(PROPS.mushroom_cluster(seed=seed + 1, count=7, material="amber_resin")
                .translate(0.0, 1.5, 0.0))
    else:  # luminous
        out.add(M.box((1.3, 0.35, 1.3), center=(0.0, 0.17, 0.0), uv_scale=0.8, material="ashlar"))
        out.add(M.box((0.7, 2.6, 0.5), center=(0.0, 1.65, 0.0), uv_scale=0.8, material="pale_ashlar"))
        out.add(M.icosphere(0.22, subdivisions=1, material="amber_resin").translate(0.0, 3.1, 0.0))
    return out


# ---------------------------------------------------------------- growth
# What of each neighbour's country crosses the march, and how much of it.
# `tree:<species>[:<foliage>]` grows a tree of that kind through the shared
# generator; everything else names a kit piece built by `_growth_piece`.
GROWTH = {
    "whitehorn_range": [("tree:dark_pine", 9), ("snow_boulder", 6), ("cairn", 4)],
    "mirrorhold": [("tree:dark_pine", 5), ("turf_rock", 5)],
    "amethyst_barrens": [("outcrop", 4), ("vein", 8), ("shard", 4)],
    "sunmane_steppe": [("banner", 4), ("steppe_rock", 5), ("paddock", 3)],
    "amberwood": [("tree:amber_oak:foliage_amber", 6), ("tree:rust_maple:foliage_rust", 6)],
    "grey_moors": [("snag", 4), ("scrub", 12), ("moor_stone", 3)],
    "westhaven": [("haven_fence", 4), ("haven_rock", 4), ("cart", 1)],
    "crownwater": [("reeds", 10), ("boat", 2)],
    "four_gates": [("reeds", 8), ("boat", 1), ("lamp", 2)],
    "manymouth_delta": [("reeds", 10), ("boat", 2), ("fern", 5)],
    "verdant_stair": [("treefern", 6), ("frond", 10)],
    "ssarathi_ruins": [("treefern", 6), ("frond", 10)],
}

# kind, collides, sink, scale range, per growth piece
GROWTH_PLACEMENT = {
    "tree": ("tree", True, 0.05, (0.85, 1.15)),
    "snow_boulder": ("rock", True, 0.4, (0.9, 1.3)),
    "cairn": ("prop", False, 0.05, (0.9, 1.1)),
    "turf_rock": ("rock", True, 0.3, (0.9, 1.2)),
    "outcrop": ("crystal", True, 0.3, (0.9, 1.2)),
    "vein": ("crystal", False, 0.1, (0.9, 1.2)),
    "shard": ("crystal", True, 0.05, (0.9, 1.2)),
    "banner": ("prop", False, 0.05, (0.95, 1.05)),
    "steppe_rock": ("rock", True, 0.35, (0.9, 1.2)),
    "paddock": ("prop", False, 0.05, (1.0, 1.0)),
    "snag": ("tree", True, 0.05, (0.9, 1.2)),
    "scrub": ("undergrowth", False, 0.05, (0.9, 1.3)),
    "moor_stone": ("prop", True, 0.05, (0.9, 1.2)),
    "haven_fence": ("prop", False, 0.05, (1.0, 1.0)),
    "haven_rock": ("rock", True, 0.35, (0.9, 1.2)),
    "cart": ("prop", True, 0.05, (1.0, 1.0)),
    "reeds": ("undergrowth", False, 0.05, (0.9, 1.3)),
    "boat": ("prop", True, 0.2, (1.0, 1.0)),
    "lamp": ("prop", False, 0.04, (1.0, 1.0)),
    "fern": ("tree", True, 0.05, (0.9, 1.2)),
    "treefern": ("tree", True, 0.05, (0.9, 1.2)),
    "frond": ("undergrowth", False, 0.05, (0.9, 1.3)),
}


def _growth_piece(name: str, index: int, prefix: str, crossing: Crossing):
    """The mesh (or wood and canopy) for one growth entry, as a list."""
    variant = index % 3
    seed = 100 + variant + N.stable_hash(name) % 900
    if name.startswith("tree:"):
        parts = name.split(":")
        species = parts[1]
        foliage = parts[2] if len(parts) > 2 else None
        profile = TREES.PROFILES[species]
        previous = profile.foliage_material
        if foliage:
            profile.foliage_material = foliage
        wood, leaves = TREES.build_tree(species, seed=4000 + variant * 31 + N.stable_hash(species) % 700,
                                        detail="mid", canopy_floor=0.30)
        profile.foliage_material = previous
        return [wood, leaves if leaves.triangle_count else None]
    if name == "snow_boulder":
        return [PROPS.boulder(radius=1.0 + 0.3 * variant, seed=seed, material="snow_pack")]
    if name == "cairn":
        return [MOOR.cairn(height=1.3, seed=seed, lit=False)]
    if name == "turf_rock":
        return [PROPS.rock_cluster(radius=1.6 + 0.4 * variant, count=4 + variant, seed=seed,
                                   material="pale_ashlar")]
    if name == "outcrop":
        return [CC.outcrop(seed=seed, radius=1.8 + 0.4 * variant, height=2.4 + 0.6 * variant)]
    if name == "vein":
        return [CC.vein_scatter(radius=2.4, count=6 + variant, seed=seed)]
    if name == "shard":
        return [CC.shard(2.2 + 0.7 * variant, 0.42, faces=6, seed=seed, tilt=0.25)]
    if name == "banner":
        return [_wind_banner(seed)]
    if name == "steppe_rock":
        return [PROPS.rock_cluster(radius=1.4 + 0.5 * variant, count=3 + variant, seed=seed,
                                   material="cliff_rock")]
    if name == "paddock":
        return [PROPS.fence(length=5.0, height=1.1, seed=seed)]
    if name == "snag":
        return [MOOR.dead_tree(seed=seed, detail="mid")]
    if name == "scrub":
        return [MOOR.scrub_clump(seed=seed, radius=1.1, cards=4)]
    if name == "moor_stone":
        return [MOOR.menhir(height=1.6 + 0.5 * variant, seed=seed)]
    if name == "haven_fence":
        return [PROPS.fence(length=4.0, height=1.1, seed=seed)]
    if name == "haven_rock":
        return [PROPS.rock_cluster(radius=1.5, count=4, seed=seed, material="cliff_rock")]
    if name == "cart":
        return [PROPS.cart(seed=seed)]
    if name == "reeds":
        return [PROPS.undergrowth_patch(radius=1.4 + 0.3 * variant, count=6, seed=seed, height=1.3)]
    if name == "boat":
        return [PROPS.rowing_boat(seed=seed)]
    if name == "lamp":
        return [SW.lamp_post(height=2.6)]
    if name == "fern":
        return [JC.tree_fern(height=3.6 + 0.6 * variant, seed=seed)]
    if name == "treefern":
        return [JC.tree_fern(height=4.2 + 0.8 * variant, seed=seed)]
    if name == "frond":
        return [JC.frond_cluster(radius=1.4 + 0.3 * variant, count=6, seed=seed)]
    raise KeyError(name)


def _growth(build: RegionBuild, t: TER.Terrain, crossing: Crossing, rng: N.Rng,
            sea_level: float, prefix: str) -> int:
    """Scatter the neighbour's growth through the march. Returns the count."""
    px, pz = crossing.position
    dirx, dirz = crossing.direction()
    placed = 0

    def spot(min_r: float = 8.0):
        max_r = crossing.radius
        for _ in range(30):
            angle = rng.uniform(0.0, math.tau)
            distance = rng.uniform(min_r, max_r)
            x = px + math.cos(angle) * distance
            z = pz + math.sin(angle) * distance
            # keep off the road itself: the line through the portal along the
            # direction of travel
            offset = abs((x - px) * dirz - (z - pz) * dirx)
            if offset < crossing.road_width * 0.9 + 1.5:
                continue
            if not _open(t, x, z, sea_level):
                continue
            if not (t.x0 + 6 < x < t.x0 + t.size_x - 6 and t.z0 + 6 < z < t.z0 + t.size_z - 6):
                continue
            return x, z
        return None

    for name, count in GROWTH.get(crossing.neighbour, ()):
        family = "tree" if name.startswith("tree:") else name
        kind, collides, sink, scale_range = GROWTH_PLACEMENT[family]
        if name == "boat" and not crossing.ferry:
            count = 1
        for index in range(count):
            site = spot()
            if site is None:
                continue
            x, z = site
            rotation = rng.uniform(0.0, math.tau)
            size = rng.uniform(*scale_range)
            variant = index % 3
            key = f"{prefix}_{family}_{name.replace(':', '_')}_{variant}"
            meshes = _growth_piece(name, index, prefix, crossing)
            node = f"{prefix}_{family}_{placed:03d}"
            _place(build, t, node, key, meshes[0], x, z, rotation=rotation, scale=size,
                   kind=kind, collides=collides, sink=sink)
            if len(meshes) > 1 and meshes[1] is not None:
                _place(build, t, node + "_Canopy", key + "_canopy", meshes[1], x, z,
                       rotation=rotation, scale=size, kind="foliage", sink=sink)
            placed += 1
            if collides:
                t.mark_blocked_disc((x, z), 0.8)
    return placed


# ---------------------------------------------------------------- dress
def dress(build: RegionBuild, region: str, crossings, seed: int, *,
          sea_level: float = 0.0, station_scale: float = 1.0) -> March:
    """Furnish every crossing. Call after the region has placed its own things."""
    t = build.terrain
    culture = PEOPLE[region]
    furniture, spacing, sides = CULTURE_FURNITURE[culture]
    report = March()
    for index, crossing in enumerate(crossings):
        rng = N.Rng(seed + 1009 * index + N.stable_hash(crossing.id) % 977)
        prefix = f"March_{crossing.id.replace('-', '_')}"
        px, pz = crossing.position
        dirx, dirz = crossing.direction()
        side = (dirz, -dirx)
        half = crossing.road_width * 0.5 + 1.6

        # the road furniture, back from the portal into the region
        run = 0
        for step in range(1, 8):
            back = step * spacing
            for which, sign in enumerate((1.0, -1.0)):
                if sides == "alternate" and (step + which) % 2:
                    continue
                x = px - dirx * back + side[0] * half * sign
                z = pz - dirz * back + side[1] * half * sign
                if not _open(t, x, z, sea_level):
                    continue
                piece = furniture(seed + step * 7 + which)
                key = f"{prefix}_furniture_{step}_{which}"
                _place(build, t, f"{prefix}_Furniture_{run:02d}", key, piece, x, z,
                       rotation=_facing((x, z), (px, pz)), kind="prop", collides=False,
                       sink=0.04)
                run += 1

        # the march stone, beside the road six metres before the crossing
        sx = px - dirx * 6.0 + side[0] * (half + 1.2)
        sz = pz - dirz * 6.0 + side[1] * (half + 1.2)
        stone_node = f"{prefix}_Stone"
        _place(build, t, stone_node, f"{prefix}_stone", _march_stone(culture, crossing.neighbour, seed + index),
               sx, sz, rotation=_facing((sx, sz), (px - dirx * 40.0, pz - dirz * 40.0)),
               kind="landmark", collides=True, sink=0.05, landmark=f"march-{crossing.id}")
        t.mark_blocked_disc((sx, sz), 1.0)

        # the signpost across the road from the stone, arms for both ways
        gx = px - dirx * 9.0 - side[0] * (half + 0.6)
        gz = pz - dirz * 9.0 - side[1] * (half + 0.6)
        _place(build, t, f"{prefix}_Signpost", f"{prefix}_signpost", PROPS.signpost(seed=seed + index, arms=2),
               gx, gz, rotation=_facing((gx, gz), (px, pz)), kind="prop", collides=False, sink=0.03)

        # the waystation, off the road
        stx, stz = _station_site(crossing)
        station = _station(culture, seed + 31 * index)
        _place(build, t, f"{prefix}_Station", f"{prefix}_station", station, stx, stz,
               rotation=_facing((stx, stz), (px - dirx * 22.0, pz - dirz * 22.0)) + math.pi,
               scale=station_scale, kind="landmark", collides=True, sink=0.08,
               landmark=f"station-{crossing.id}")
        t.mark_blocked_disc((stx, stz), 4.5 * station_scale)

        # and the neighbour's country creeping in
        grown = _growth(build, t, crossing, rng, sea_level, prefix)

        title = TITLES[crossing.neighbour]
        report.landmarks.append({
            "id": f"march-{crossing.id}",
            "name": crossing.name or f"The {title.replace('the ', '').title()} March",
            "node": stone_node, "type": "transition",
            "position": [round(sx, 2), round(_ground(t, sx, sz), 2), round(sz, 2)],
            "note": (f"Where {TITLES[region]} gives way to {title}: {culture} road furniture, "
                     f"a march stone, a waystation, and {grown} pieces of the country beyond."),
        })
        report.landmarks.append({
            "id": f"station-{crossing.id}",
            "name": f"{title.replace('the ', '').title()} Road Station",
            "node": f"{prefix}_Station", "type": "waystation",
            "position": [round(stx, 2), round(_ground(t, stx, stz), 2), round(stz, 2)],
        })
        report.notes.append(f"march {crossing.id}: {run} road pieces, {grown} of {crossing.neighbour}'s growth")
    return report
