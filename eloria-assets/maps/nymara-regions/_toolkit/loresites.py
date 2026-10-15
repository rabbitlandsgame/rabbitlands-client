"""Lore sites: the places the world bible argues about, built where it says.

`config/eloria/npc_dialogue.txt` carries twelve running arguments - the thing
in the east, the ringing stone, the eleven measures, the drowned court, the
house seal, the barrow debt, the water lineage, the sour ground, the ledger
and the spore, the stair's slope, the snowline, the ninety candles. Every NPC
in a region tells the player about one of them and, until now, the region had
nothing to show for it. These are the set pieces those conversations point
at: small, walkable, readable from the road, and each one a thing a player
can stand in front of and recognise from what they were told.

Everything is built from the shared kits. A region calls one of these with a
position and gets a `MeshGroup` back; `place_site()` registers it on the
build with a landmark entry and a collision footprint.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

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


# ------------------------------------------------------------------ pieces
def watchers_line(count: int = 9, spacing: float = 7.0, seed: int = 0,
                  stone: str = "grey_moor_granite") -> SW.MeshGroup:
    """Thread A: the nine watchers that face the east. A line of tall stones,
    each with a lantern niche cut into its east face, and a fire before the
    middle one that is never let out."""
    out = SW.MeshGroup()
    rng = N.Rng(seed)
    for index in range(count):
        x = (index - (count - 1) / 2.0) * spacing
        stone_mesh = MOOR.menhir(height=3.4 + 0.5 * float(rng.uniform()), seed=seed + index,
                                 material=stone)
        out.add(stone_mesh.translate(x, 0.0, 0.0))
        out.add(PROPS.hanging_lantern(seed=seed + index, drop=0.3).translate(x, 2.2, 0.55))
    out.add(PROPS.brazier(seed=seed + 40).translate(0.0, 0.0, 2.6))
    out.add(PROPS.log_pile(length=2.4, rows=2, per_row=4, seed=seed + 41).translate(4.0, 0.0, 3.2))
    return out


def ringing_quarry(seed: int = 0, stone: str = "cliff_rock",
                   crystal: str = "amethyst_crystal") -> SW.MeshGroup:
    """Thread B: the quarry face that rings when it is struck. A cut bench, a
    tall face with one blank block half-drawn out of it, drills and a bell
    hung to test the note."""
    out = SW.MeshGroup()
    rng = N.Rng(seed)
    face = M.box((16.0, 7.0, 3.0), center=(0.0, 3.5, -4.5), uv_scale=0.5, material=stone)
    face.jitter(0.18, seed=seed)
    out.add(face)
    bench = M.box((16.0, 0.4, 7.0), center=(0.0, 0.2, 0.5), uv_scale=0.5, material=stone)
    out.add_walk(bench)
    # the blank, drawn a third of the way out of the face
    out.add(M.box((3.0, 2.6, 2.4), center=(1.5, 1.7, -2.2), uv_scale=0.6, material="pale_ashlar"))
    for index in range(3):
        out.add(M.box((2.2, 1.4, 1.1), center=(-5.5 + index * 0.6, 0.7 + index * 0.02, 1.6 + index * 1.2),
                      uv_scale=0.6, material="pale_ashlar").rotate_y(0.2 * index))
    # a bell frame and bell: the note is tested, not trusted
    out.add(M.cylinder(0.14, 0.12, 3.4, 7, uv_scale=1.0, material="timber_dark").translate(-6.5, 0.4, 3.0))
    out.add(M.cylinder(0.14, 0.12, 3.4, 7, uv_scale=1.0, material="timber_dark").translate(-4.3, 0.4, 3.0))
    out.add(M.box((2.6, 0.16, 0.16), center=(-5.4, 3.7, 3.0), uv_scale=1.0, material="timber_dark"))
    out.add(M.lathe([[0.0, 0.0], [0.42, 0.05], [0.52, 0.5], [0.34, 0.9], [0.0, 0.95]], 12,
                    material="dark_iron").translate(-5.4, 2.6, 3.0))
    out.add(CC.vein_scatter(radius=2.6, count=5, seed=seed + 7, material=crystal, height=0.6)
            .translate(5.0, 0.4, 1.5))
    out.add(PROPS.cart(seed=seed + 9).translate(6.5, 0.4, 3.6).rotate_y(0.4))
    return out


def measure_stones(count: int = 11, seed: int = 0, stone: str = "amethyst_pale_stone",
                   crystal: str = "amethyst_crystal", brass: str = "amethyst_brass") -> SW.MeshGroup:
    """Thread C: the eleven measures. Eleven calibration stones in an arc, each
    with a brass collar and a shard cut to one length, so a Glasswarden can
    tune a shard against every one of them in a walk."""
    out = SW.MeshGroup()
    radius = 9.0
    for index in range(count):
        angle = math.pi * (0.15 + 0.70 * index / max(count - 1, 1)) + math.pi
        x, z = math.cos(angle) * radius, math.sin(angle) * radius
        plinth = M.box((1.0, 0.9 + 0.08 * index, 1.0), center=(0.0, 0.45 + 0.04 * index, 0.0),
                       uv_scale=0.8, material=stone)
        out.add(plinth.translate(x, 0.0, z))
        out.add(M.cylinder(0.26, 0.26, 0.08, 12, uv_scale=1.0, material=brass)
                .translate(x, 0.9 + 0.08 * index, z))
        out.add(CC.shard(0.9 + 0.16 * index, 0.2, faces=6, seed=seed + index, material=crystal)
                .translate(x, 0.98 + 0.08 * index, z))
    out.add_walk(M.cylinder(radius + 1.6, radius + 1.6, 0.18, 24, uv_scale=0.4, material=stone)
                 .translate(0.0, 0.0, 0.0))
    out.add(M.box((1.6, 1.1, 0.9), center=(0.0, 0.55, 0.0), uv_scale=0.8, material=stone))
    out.add(M.box((1.2, 0.05, 0.7), center=(0.0, 1.13, 0.0), uv_scale=0.8, material=brass))
    return out


def filled_well(seed: int = 0, stone: str = "rubble_stone") -> SW.MeshGroup:
    """Thread H: the fourth well, filled in because the water hummed, under a
    cairn built badly on purpose. A well-head with its shaft packed with
    rubble, a leaning cairn over it, and the wolf-scratched ground around."""
    out = SW.MeshGroup()
    rng = N.Rng(seed)
    out.add(M.lathe([[1.1, 0.0], [1.1, 0.8], [0.85, 0.85], [0.85, 0.0]], 14, uv_scale=1.0,
                    material=stone))
    for index in range(9):
        angle = float(rng.uniform(0.0, math.tau))
        r = float(rng.uniform(0.0, 0.7))
        out.add(PROPS.boulder(radius=float(rng.uniform(0.25, 0.5)), seed=seed + index, material=stone)
                .translate(math.cos(angle) * r, 0.75 + float(rng.uniform(0.0, 0.5)), math.sin(angle) * r))
    cairn = MOOR.cairn(height=2.2, seed=seed + 20, lit=False)
    cairn.rotate_z(0.12)
    out.add(cairn.translate(0.3, 0.9, 0.0))
    for index in range(4):
        angle = math.tau * index / 4.0 + 0.4
        out.add(PROPS.rock_cluster(radius=0.9, count=3, seed=seed + 30 + index, material=stone)
                .translate(math.cos(angle) * 3.4, -0.2, math.sin(angle) * 3.4))
    return out


def scar_glade(seed: int = 0, bark: str = "bark_dark") -> SW.MeshGroup:
    """Thread A, from the forest's side: the deep grove, scarred. A ring of
    burnt snags around a charcoal circle, one living sapling in the middle,
    and the cut faces of the felled trees showing the char goes to the heart."""
    out = SW.MeshGroup()
    rng = N.Rng(seed)
    out.add_walk(M.cylinder(7.0, 7.0, 0.12, 20, uv_scale=0.4, material="scorched_ground"))
    for index in range(7):
        angle = math.tau * index / 7.0 + float(rng.uniform(-0.2, 0.2))
        wood, _ = TREES.build_tree("burnt_snag", seed=seed + index, detail="mid")
        wood = wood.with_material(bark)
        out.add(wood.scale(0.9, float(rng.uniform(0.6, 1.0)), 0.9)
                .translate(math.cos(angle) * 8.5, 0.0, math.sin(angle) * 8.5))
    for index in range(4):
        angle = math.tau * index / 4.0 + 0.5
        out.add(TREES.fallen_log(length=5.0, radius=0.42, seed=seed + 20 + index, material=bark)
                .rotate_y(angle).translate(math.cos(angle) * 4.5, 0.0, math.sin(angle) * 4.5))
    wood, leaves = TREES.build_tree("sapling", seed=seed + 50, detail="high")
    out.add(wood)
    out.add(leaves)
    out.add(PROPS.mushroom_cluster(seed=seed + 60, count=6, material="amber_resin").translate(1.2, 0.0, 0.8))
    return out


def stelae_field(count: int = 10, seed: int = 0) -> SW.MeshGroup:
    """Thread G: the stelae that record the water lineage, in the order the
    channels were claimed. Carved posts in two ranks with a reading path
    between them, and the tenth stone blank."""
    out = SW.MeshGroup()
    for index in range(count):
        row = index % 2
        x = (index // 2) * 3.4 - 6.8
        z = -2.2 if row == 0 else 2.2
        if index == count - 1:
            out.add(M.box((0.7, 2.4, 0.5), center=(0.0, 1.2, 0.0), uv_scale=0.8,
                          material="verdant_terrace_stone").translate(x, 0.0, z))
        else:
            out.add(JC.shrine_post(height=2.4 + 0.1 * (index % 3), seed=seed + index).translate(x, 0.0, z))
    out.add_walk(M.box((20.0, 0.14, 2.2), center=(0.0, 0.07, 0.0), uv_scale=0.5,
                       material="verdant_terrace_stone"))
    out.add(JC.relief_panel(width=2.2, height=1.4, seed=seed + 30).translate(10.5, 0.0, 0.0).rotate_y(0.0))
    return out


def post_house(seed: int = 0) -> SW.MeshGroup:
    """Thread E: the league's post-house, where the countersigns are checked.
    A watch platform, a letter-rack wall, sealed crates and the returned post
    stacked unopened beside the door."""
    out = SW.MeshGroup()
    out.add(PROPS.market_stall(width=3.6, depth=2.6, seed=seed))
    out.add(M.box((3.4, 2.2, 0.3), center=(0.0, 1.1, -1.6), uv_scale=0.8, material="timber_grey"))
    for row in range(4):
        for col in range(6):
            out.add(M.box((0.42, 0.34, 0.12), center=(-1.35 + col * 0.54, 0.55 + row * 0.42, -1.42),
                          uv_scale=1.0, material="carved_wood"))
    for index in range(5):
        out.add(PROPS.crate(size=0.55, seed=seed + index).translate(2.6 + (index % 2) * 0.6, (index // 2) * 0.48, 0.6 - (index % 3) * 0.5))
    out.add(PROPS.sack(seed=seed + 8).translate(-2.4, 0.0, 0.4))
    out.add(PROPS.sack(seed=seed + 9).translate(-2.9, 0.0, 0.9))
    out.add(SW.lamp_post(height=2.6).translate(-2.6, 0.0, -1.9))
    return out


def snowline_stones(seed: int = 0) -> SW.MeshGroup:
    """Thread K: the stones the snowline is read against. A stair of ten cut
    stones up a slope, each with a brass line where the snow stood the year it
    was set - and the last three above the snow."""
    out = SW.MeshGroup()
    for index in range(10):
        y = index * 0.55
        x = index * 1.6 - 7.2
        out.add(M.box((1.2, 1.4, 0.5), center=(0.0, 0.7, 0.0), uv_scale=0.8, material="pale_ashlar")
                .translate(x, y, 0.0))
        out.add(M.box((1.24, 0.05, 0.54), center=(0.0, 0.5 + 0.06 * index, 0.0), uv_scale=1.0,
                      material="gilt_brass").translate(x, y, 0.0))
    out.add_walk(M.box((18.0, 0.16, 3.0), center=(0.0, 0.08, 1.9), uv_scale=0.5, material="pale_ashlar"))
    out.add(MOOR.cairn(height=1.8, seed=seed, lit=True).translate(-9.0, 0.0, 2.0))
    return out


def candle_shrine(count: int = 90, seed: int = 0) -> SW.MeshGroup:
    """Thread L: the ninety candles. A drystone niche wall with ninety candle
    stubs set along its courses, most of them out, and the one that is not."""
    out = SW.MeshGroup()
    rng = N.Rng(seed)
    out.add(M.box((9.0, 2.8, 0.7), center=(0.0, 1.4, 0.0), uv_scale=0.7, material="ashlar"))
    lit = int(rng.integers(0, count))
    for index in range(count):
        row, col = divmod(index, 18)
        x = -4.1 + col * 0.48
        y = 0.45 + row * 0.5
        out.add(M.cylinder(0.05, 0.05, 0.12 + 0.02 * (index % 4), 6, uv_scale=1.0,
                           material="pale_ashlar").translate(x, y, 0.42))
        if index == lit:
            out.add(M.icosphere(0.06, subdivisions=1, material="amber_resin").translate(x, y + 0.2, 0.42))
    out.add(M.box((9.4, 0.3, 1.4), center=(0.0, 0.15, 0.5), uv_scale=0.7, material="ashlar"))
    out.add(PROPS.brazier(seed=seed).translate(3.6, 0.0, 1.8))
    return out


def moved_anchor(seed: int = 0) -> SW.MeshGroup:
    """Thread J: the stair's anchor stone, moved. A great carved block on log
    rollers, the ropes still on it, and the socket it was levered out of a few
    metres upslope."""
    out = SW.MeshGroup()
    out.add(JC.relief_panel(width=2.6, height=2.2, depth=1.8, seed=seed).translate(0.0, 0.6, 0.0))
    for index in range(4):
        out.add(M.cylinder(0.28, 0.28, 3.4, 9, uv_scale=1.0, material="bark_dark")
                .rotate_z(math.pi * 0.5).translate(0.0, 0.28, -1.2 + index * 0.8))
    out.add(M.box((3.2, 0.6, 3.0), center=(0.0, -0.3, -7.0), uv_scale=0.6, material="verdant_terrace_stone"))
    out.add(M.box((2.6, 0.7, 2.4), center=(0.0, 0.05, -7.0), uv_scale=0.6, material="packed_earth"))
    out.add(M.cylinder(0.04, 0.04, 7.0, 6, uv_scale=1.0, material="verdant_rope")
            .rotate_x(math.pi * 0.5).translate(0.9, 1.4, -3.5))
    out.add(M.cylinder(0.04, 0.04, 7.0, 6, uv_scale=1.0, material="verdant_rope")
            .rotate_x(math.pi * 0.5).translate(-0.9, 1.4, -3.5))
    return out


def drowned_grating(seed: int = 0) -> SW.MeshGroup:
    """Thread D: the grating over the drowned court, found open. A stone
    kerb round a dark opening, an iron grate thrown back on its hinge, a
    diver's rope and weights left on the kerb."""
    out = SW.MeshGroup()
    out.add(M.lathe([[2.4, 0.0], [2.4, 0.6], [1.8, 0.65], [1.8, 0.0]], 16, uv_scale=1.0, material="ashlar"))
    out.add(M.cylinder(1.75, 1.75, 0.05, 16, uv_scale=0.3, material="water_deep").translate(0.0, 0.1, 0.0))
    grate = SW.MeshGroup()
    for index in range(7):
        grate.add(M.box((3.6, 0.06, 0.08), center=(0.0, 0.0, -1.5 + index * 0.5), uv_scale=1.0, material="dark_iron"))
        grate.add(M.box((0.08, 0.06, 3.6), center=(-1.5 + index * 0.5, 0.0, 0.0), uv_scale=1.0, material="dark_iron"))
    grate.rotate_x(-1.25)
    out.add(grate.translate(0.0, 0.65, 2.2))
    out.add(M.cylinder(0.05, 0.05, 6.0, 6, uv_scale=1.0, material="timber_grey")
            .rotate_z(math.pi * 0.5).translate(2.8, 0.7, 0.4))
    for index in range(3):
        out.add(PROPS.boulder(radius=0.22, seed=seed + index, material="dark_iron").translate(2.6 + index * 0.4, 0.6, -0.8))
    return out


def tally_house(seed: int = 0) -> SW.MeshGroup:
    """Thread I: the ledger and the spore. A Greyhaven tally office set against
    a Mycelari daybook-tree: a counting bench with tally sticks and a wage
    book on one side, a mushroom-ringed stump with the same count cut into
    it on the other, and the bee boundary between them."""
    out = SW.MeshGroup()
    out.add(PROPS.workbench(length=2.4, seed=seed, tools=False).translate(-2.4, 0.0, 0.0))
    for index in range(12):
        out.add(M.box((0.05, 0.6, 0.05), center=(-3.4 + index * 0.17, 1.1, 0.4), uv_scale=1.0,
                      material="timber_grey"))
    out.add(M.box((0.5, 0.08, 0.36), center=(-1.6, 0.94, -0.2), uv_scale=1.0, material="carved_wood"))
    out.add(TREES.stump(radius=0.9, height=1.2, seed=seed + 5, material="bark_dark").translate(2.6, 0.0, 0.0))
    out.add(PROPS.mushroom_cluster(seed=seed + 6, count=8, material="amber_resin").translate(2.6, 1.2, 0.0))
    for index in range(4):
        out.add(PROPS.fence(length=1.6, height=0.9, seed=seed + 10 + index)
                .rotate_y(math.pi * 0.5).translate(0.0, 0.0, -3.2 + index * 1.6))
    out.add(PROPS.basket(seed=seed + 20).translate(1.4, 0.0, -2.6))
    out.add(PROPS.basket(seed=seed + 21).translate(1.9, 0.0, -2.2))
    return out


def breached_barrow(seed: int = 0) -> SW.MeshGroup:
    """Thread F: one of the eleven breached barrows. A turf mound with its
    kerb, the passage forced and the spoil thrown beside it, and the
    return-field stakes in a row before the door, their tags left blank."""
    out = SW.MeshGroup()
    rng = N.Rng(seed)
    mound = M.icosphere(6.2, subdivisions=2, material="grey_barrow_turf")
    out.add(mound.scale(1.0, 0.36, 1.0))
    for index in range(14):
        angle = math.tau * index / 14.0 + float(rng.uniform(-0.1, 0.1))
        if abs(angle - math.pi * 0.5) < 0.3:
            continue
        out.add(MOOR.fallen_stone(length=1.1 + 0.3 * (index % 3), seed=seed + index)
                .rotate_y(-angle).translate(math.cos(angle) * 6.5, 0.0, math.sin(angle) * 6.5))
    out.add(MOOR.barrow_portal(width=1.5, height=2.1, seed=seed).translate(0.0, 0.0, 5.3))
    out.add(PROPS.rock_cluster(radius=1.7, count=7, seed=seed + 20, material="rubble_stone")
            .translate(3.4, -0.1, 6.4))
    out.add(PROPS.rock_cluster(radius=1.1, count=4, seed=seed + 21, material="grey_barrow_turf")
            .translate(-3.0, -0.2, 6.8))
    for index in range(6):
        x = -4.0 + index * 1.6
        out.add(M.box((0.09, 1.35, 0.09), center=(x, 0.67, 9.2), uv_scale=1.0, material="timber_grey"))
        out.add(M.box((0.36, 0.22, 0.03), center=(x, 1.2, 9.26), uv_scale=1.0, material="pale_ashlar"))
    out.add(MOOR.votive_candle(seed=seed + 30).translate(-1.1, 0.0, 7.4))
    out.add(MOOR.votive_candle(seed=seed + 31).translate(1.0, 0.0, 7.6))
    out.add_walk(M.box((10.0, 0.12, 4.6), center=(0.0, 0.06, 9.4), uv_scale=0.5,
                       material="grey_moor_track"))
    return out


PIECES = {
    "watchers_line": watchers_line, "ringing_quarry": ringing_quarry,
    "breached_barrow": breached_barrow,
    "measure_stones": measure_stones, "filled_well": filled_well, "scar_glade": scar_glade,
    "stelae_field": stelae_field, "post_house": post_house, "snowline_stones": snowline_stones,
    "candle_shrine": candle_shrine, "moved_anchor": moved_anchor,
    "drowned_grating": drowned_grating, "tally_house": tally_house,
}


# ------------------------------------------------------------------ placing
@dataclass
class Site:
    """One lore site a region asks for. `position` is where the NPC who talks
    about it stands, roughly; `prepare()` looks for the flattest open ground
    within `search` metres of it and records the spot in `resolved`."""
    id: str
    name: str
    piece: str
    position: tuple
    rotation: float = 0.0
    thread: str = ""
    note: str = ""
    clearing: float = 12.0
    search: float = 36.0
    level: bool = True
    kwargs: dict = field(default_factory=dict)
    resolved: tuple | None = None
    remark: str = ""


def _samples(x: float, z: float, radius: float):
    pts = [(x, z)]
    for ring in (0.55, 1.0):
        for index in range(8):
            angle = math.tau * index / 8.0
            pts.append((x + math.cos(angle) * radius * ring, z + math.sin(angle) * radius * ring))
    return pts


def _fits(t: TER.Terrain, x: float, z: float, radius: float, sea_level: float,
          protected) -> float | None:
    """The relief across the clearing, or None where the ground will not do."""
    margin = radius + 14.0
    if not (t.x0 + margin < x < t.x0 + t.size_x - margin
            and t.z0 + margin < z < t.z0 + t.size_z - margin):
        return None
    heights = []
    for sx, sz in _samples(x, z, radius):
        if bool(t.blocked_at(sx, sz)):
            return None
        if int(t.surface_at(sx, sz)) in protected:
            return None
        h = float(t.height_at(sx, sz))
        if h < sea_level + 1.0:
            return None
        heights.append(h)
    return max(heights) - min(heights)


def _level(t: TER.Terrain, x: float, z: float, radius: float, protected) -> None:
    """Settle a soft pad under the site: flat inside, feathered to the slope."""
    d = np.hypot(t.gx - x, t.gz - z)
    inner = radius * 0.62
    outer = radius * 1.15
    target = float(np.mean([t.height_at(sx, sz) for sx, sz in _samples(x, z, inner)]))
    w = np.clip((outer - d) / (outer - inner), 0.0, 1.0)
    w = w * w * (3.0 - 2.0 * w)
    keep = np.isin(t.surface, sorted(protected))
    w = np.where(keep, 0.0, w)
    t.height = t.height * (1.0 - w) + target * w


def prepare(t: TER.Terrain, sites, *, sea_level: float = 0.0, keep=()) -> None:
    """Choose each site's ground, level it and keep the region's scatter off it.

    Runs before the region populates, the way the marches do, so the trees and
    rocks never have to be argued with afterwards.
    """
    protected = set(TER.AUTHORED_SURFACES) | set(keep)
    for site in sites:
        px, pz = site.position
        best = None
        candidates = [(px, pz)]
        step = 6.0
        ring = step
        while ring <= site.search:
            count = max(8, int(ring * 1.2))
            for index in range(count):
                angle = math.tau * index / count
                candidates.append((px + math.cos(angle) * ring, pz + math.sin(angle) * ring))
            ring += step
        for cx, cz in candidates:
            relief = _fits(t, cx, cz, site.clearing, sea_level, protected)
            if relief is None:
                continue
            score = relief + 0.04 * math.hypot(cx - px, cz - pz)
            if best is None or score < best[0]:
                best = (score, cx, cz, relief)
        if best is None:
            site.resolved = (px, pz)
            site.remark = "no open ground within reach; placed where asked"
        else:
            _score, cx, cz, relief = best
            site.resolved = (round(cx, 2), round(cz, 2))
            site.remark = f"relief {relief:.2f} m, {math.hypot(cx - px, cz - pz):.0f} m from the ask"
        x, z = site.resolved
        if site.level:
            _level(t, x, z, site.clearing, protected)
        t.tree_block |= np.hypot(t.gx - x, t.gz - z) < site.clearing


def dress(build: RegionBuild, t: TER.Terrain, sites, seed: int) -> list[dict]:
    """Build and place every prepared site. Returns the landmark entries."""
    out = []
    for index, site in enumerate(sites):
        if site.resolved is None:
            raise RuntimeError(f"lore site {site.id} was not prepared")
        x, z = site.resolved
        piece = PIECES[site.piece](seed=seed * 7 + index, **site.kwargs)
        key = "Lore_" + site.id.replace("-", "_")
        build.meshes[key] = piece
        y = float(t.height_at(x, z))
        build.place(Placement(node=key, mesh=key,
                              position=(round(x, 3), round(y - 0.06, 3), round(z, 3)),
                              rotation_y=site.rotation, scale=1.0, collides=True,
                              kind="landmark", landmark=site.id))
        entry = {"id": site.id, "name": site.name, "node": key, "type": "lore-site",
                 "thread": site.thread, "position": [round(x, 2), round(y, 2), round(z, 2)],
                 "note": site.note}
        build.landmarks.append(entry)
        build.notes.append(f"lore site {site.id} ({site.name}): {site.remark}")
        out.append(entry)
    return out


def materials(piece_names) -> set[str]:
    """Every material the named pieces reference, for a region's pin."""
    out: set[str] = set()
    for name in piece_names:
        piece = PIECES[name](seed=1)
        for part in piece.all_parts:
            out.add(part.material)
    return out
