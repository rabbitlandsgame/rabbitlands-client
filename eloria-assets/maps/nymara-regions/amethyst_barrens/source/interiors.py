"""The Amethyst Barrens interiors.

Four authored insides reached from named landmarks on the 576 m region map. The
room, passage and lamp helpers come from the shared toolkit's `interiors` module,
so a doorway, a stair tread and a vault rib are the same construction here as in
Amberwood's; only the four compositions below are this region's.

They are deliberately four different kinds of place, because a region whose
interiors are all the same room with different props has no interiors:

    resonant_vault    dressed, brass, lit, occupied  - the Glasswardens working
    geode_hollow      no straight line anywhere      - the crystal as it grows
    shardworks        timber, iron, spoil, noise     - people cutting it out
    storm_barrow      old masonry, open to the sky   - what was here before

The Resonant Vault follows the ten subjects its concept package already
specifies. The other three are authored from the region's surface landmarks and
its ten-panel board.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import crystalcraft as CC
from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S
from amberwood.interiors import (EYE, Interior, chamber, hanging_lamps, passage,
                                 WALL_T)

# -- the region's palette, indoors ----------------------------------------
# `veined_marble`, `pale_ashlar` and `blue_crystal` are Mirrorhold's, reused by
# name rather than duplicated: they landed first and they are exactly right for
# a Glasswarden laboratory.
VAULT_FLOOR = "amethyst_vault_floor"
DARK_STONE = "amethyst_storm_rock"
PALE_STONE = "amethyst_pale_stone"
MARBLE = "veined_marble"
ASHLAR = "pale_ashlar"
BRASS = "amethyst_brass"
VERDIGRIS = "amethyst_verdigris"
CRYSTAL = "amethyst_crystal"
BLUE_CRYSTAL = "blue_crystal"
CRYSTAL_GROUND = "amethyst_crystal_field"
DUST = "amethyst_barrens_dust"
BANNER = "amethyst_banner"
IRON = "dark_iron"
TIMBER = "timber_warm"
TIMBER_DARK = "timber_dark"
RUBBLE = "rubble_stone"
PAVING = "cobble_paving"
WATER = "water_deep"


# --------------------------------------------------------------------------
# shared fittings
# --------------------------------------------------------------------------
def brass_ring(radius: float, thickness: float = 0.10, segments: int = 40,
               material: str = BRASS) -> M.Mesh:
    """A horizontal brass hoop - the vault's most repeated motif."""
    angles = np.linspace(0.0, 2.0 * math.pi, segments + 1)
    path = np.stack([np.cos(angles) * radius, np.zeros_like(angles),
                     np.sin(angles) * radius], axis=-1)
    return M.tube(path, np.full(len(path), thickness), segments=7, material=material)


def railed_dais(radius: float, height: float, seed: int = 0,
                steps: int = 3, floor_mat: str = VAULT_FLOOR,
                rail_mat: str = BRASS) -> S.MeshGroup:
    """A circular stepped platform with a brass rail: panels 4, 7 and 9.

    The treads are walk surfaces; the rail is not. A rail marked walkable is a
    waist-high ledge the grounding ray will happily stand an actor on.
    """
    out = S.MeshGroup()
    for index in range(steps):
        r = radius * (1.0 - index * 0.12)
        y = height * index / max(steps, 1)
        out.add_walk(M.cylinder(r, r, height / max(steps, 1) + 0.02, 24,
                                uv_scale=0.4, material=floor_mat).translate(0, y, 0))
    top = height
    for index in range(14):
        angle = 2.0 * math.pi * index / 14.0
        post = M.cylinder(0.06, 0.05, 1.05, 6, uv_scale=0.6, material=rail_mat)
        out.add(post.translate(math.cos(angle) * radius * 0.78, top,
                               math.sin(angle) * radius * 0.78))
    out.add(brass_ring(radius * 0.78, 0.07, material=rail_mat).translate(0, top + 1.05, 0))
    return out


def instrument_bench(length: float = 2.4, seed: int = 0) -> S.MeshGroup:
    """Panel 5: a working bench - brass armature, vessels, a crystal under test."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    top_y = 0.92
    out.add(M.box((length, 0.10, 0.95), center=(0, top_y, 0), uv_scale=0.7,
                  material=TIMBER_DARK))
    for sx in (-1, 1):
        for sz in (-1, 1):
            leg = M.cylinder(0.06, 0.05, top_y, 6, uv_scale=0.6, material=BRASS)
            out.add(leg.translate(sx * (length * 0.5 - 0.18), 0.0, sz * 0.36))
    # the armature: an upright with a swung arm and a lens
    out.add(M.cylinder(0.05, 0.04, 1.15, 8, uv_scale=0.6, material=BRASS)
            .translate(length * 0.32, top_y + 0.05, -0.28))
    arm = M.cylinder(0.035, 0.03, 0.85, 6, uv_scale=0.6, material=BRASS)
    arm.rotate_z(math.pi * 0.5)
    out.add(arm.translate(length * 0.32 - 0.42, top_y + 1.06, -0.28))
    out.add(brass_ring(0.16, 0.028, segments=18)
            .rotate_x(math.pi * 0.5)
            .translate(length * 0.32 - 0.84, top_y + 1.06, -0.28))
    # the specimen, and the glassware around it
    out.add(CC.shard(0.34, 0.11, faces=6, seed=seed + 3, material=CRYSTAL)
            .translate(length * 0.32 - 0.84, top_y + 0.05, -0.28))
    for index in range(4):
        x = float(rng.uniform(-length * 0.42, length * 0.18))
        out.add(M.icosphere(float(rng.uniform(0.09, 0.15)), subdivisions=1,
                            material=BLUE_CRYSTAL)
                .translate(x, top_y + 0.16, float(rng.uniform(-0.28, 0.30))))
    out.add(M.box((0.42, 0.02, 0.30), center=(-length * 0.26, top_y + 0.06, 0.24),
                  uv_scale=0.9, material=PALE_STONE))
    return out


def archive_rack(length: float = 4.0, height: float = 3.4, seed: int = 0,
                 shelves: int = 5) -> S.MeshGroup:
    """Panel 3: a tall rack of stoppered vessels, lit from within."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    depth = 0.62
    for sx in (-1, 1):
        out.add(M.box((0.14, height, depth),
                      center=(sx * length * 0.5, height * 0.5, 0), uv_scale=0.6,
                      material=TIMBER_DARK))
    for index in range(shelves):
        y = height * (index + 0.6) / shelves
        out.add(M.box((length, 0.08, depth), center=(0, y, 0), uv_scale=0.6,
                      material=TIMBER_DARK))
        count = int(rng.integers(4, 8))
        for slot in range(count):
            x = -length * 0.44 + length * 0.88 * slot / max(count - 1, 1)
            material = CRYSTAL if rng.random() < 0.55 else BLUE_CRYSTAL
            out.add(M.icosphere(float(rng.uniform(0.08, 0.13)), subdivisions=1,
                                material=material).translate(x, y + 0.16, 0.0))
            out.add(M.cylinder(0.05, 0.04, 0.10, 6, uv_scale=0.6, material=BRASS)
                    .translate(x, y + 0.05, 0.0))
    return out


def containment_cage(radius: float = 1.5, height: float = 3.6, seed: int = 0,
                     bars: int = 12) -> S.MeshGroup:
    """Panel 7: a brass cage with a shard held, and lit, inside it."""
    out = S.MeshGroup()
    for index in range(bars):
        angle = 2.0 * math.pi * index / bars
        bar = M.cylinder(0.055, 0.05, height, 6, uv_scale=0.6, material=BRASS)
        out.add(bar.translate(math.cos(angle) * radius, 0.0, math.sin(angle) * radius))
    for y in (0.0, height * 0.5, height):
        out.add(brass_ring(radius, 0.08).translate(0, y, 0))
    # the held shard, point down, floating clear of the floor
    shard = CC.shard(height * 0.42, height * 0.13, faces=8, seed=seed,
                     material=CRYSTAL)
    shard.rotate_z(math.pi)
    out.add(shard.translate(0.0, height * 0.72, 0.0))
    out.add(M.icosphere(0.22, subdivisions=1, material=BLUE_CRYSTAL)
            .translate(0.0, height * 0.16, 0.0))
    return out


def timber_prop(height: float, seed: int = 0, width: float = 2.6) -> S.MeshGroup:
    """A mine's roof support: two legs and a cap, the Shardworks' rhythm."""
    out = S.MeshGroup()
    for sx in (-1, 1):
        out.add(M.box((0.26, height, 0.26), center=(sx * width * 0.5, height * 0.5, 0),
                      uv_scale=0.7, material=TIMBER))
    out.add(M.box((width + 0.5, 0.28, 0.30), center=(0, height + 0.14, 0),
                  uv_scale=0.7, material=TIMBER))
    for sx in (-1, 1):
        brace = M.box((0.8, 0.16, 0.22), uv_scale=0.7, material=TIMBER)
        brace.rotate_z(sx * 0.7)
        out.add(brace.translate(sx * (width * 0.5 - 0.3), height - 0.5, 0))
    return out


# --------------------------------------------------------------------------
# 1. The Resonant Vault
# --------------------------------------------------------------------------
def resonant_vault(seed: int = 20260901) -> Interior:
    """Under the Glasswarden Observatory: where the crystal is actually studied.

    Follows the ten subjects in `interiors/resonant_vault/concept.json` - sealed
    approach, laboratory gallery, archive aisle, crystal brazier, experiment
    table, lens room, containment cell, energy crossing, research hall, and the
    material study. Dressed dark slate and brass throughout, against the ochre
    dust of the region above.
    """
    # `resonant_vault`, not `amethyst_resonant_vault`: the server's map table
    # already carries this key, and the concept package at
    # `interiors/resonant_vault/` is this interior's brief. The other three are
    # new and take the region prefix, as Amberwood's do.
    it = Interior("resonant_vault", "The Resonant Vault", "dungeon",
                  "glasswarden-observatory", [-78.0, 8.15, -204.0],
                  "resonant-vault-stair")
    rng = np.random.default_rng(seed)
    g = it.group

    # -- rooms ------------------------------------------------------------
    it.space("approach", -6, -8, 6, 8, 0.0, 5.2, floor_mat=VAULT_FLOOR,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=2.4, doors=[("north", 0.0, 4.4, 3.4)])
    it.space("gallery", -13, 22, 13, 44, -4.0, 7.0, floor_mat=VAULT_FLOOR,
             wall_mat=ASHLAR, ceil_mat=DARK_STONE, ceiling="vault", vault_rise=3.6,
             doors=[("south", 0.0, 4.4, 3.4), ("east", 33.0, 4.0, 3.2),
                    ("north", -4.0, 4.0, 3.2)])
    it.space("archive", 26, 26, 44, 52, -4.0, 8.2, floor_mat=VAULT_FLOOR,
             wall_mat=ASHLAR, ceil_mat=DARK_STONE, ceiling="vault", vault_rise=4.2,
             doors=[("west", 33.0, 4.0, 3.2), ("north", 35.0, 4.0, 3.2)])
    it.space("brazier", -22, 56, 6, 82, -6.4, 9.0, floor_mat=VAULT_FLOOR,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=4.6, doors=[("south", -4.0, 4.0, 3.2), ("east", 70.0, 4.0, 3.2)])
    it.space("lens", 30, 62, 52, 84, -4.0, 8.6, floor_mat=VAULT_FLOOR,
             wall_mat=ASHLAR, ceil_mat=DARK_STONE, ceiling="vault", vault_rise=4.0,
             doors=[("south", 35.0, 4.0, 3.2), ("west", 74.0, 4.0, 3.2)])
    it.space("hall", -20, 96, 20, 136, -9.0, 12.5, floor_mat=VAULT_FLOOR,
             wall_mat=MARBLE, ceil_mat=DARK_STONE, ceiling="vault", vault_rise=6.0,
             doors=[("south", 0.0, 5.0, 3.8)])

    links = [
        ("stairhead", (0, 8), (0, 22), 4.4, 0.0, -4.0, 4.2, 14),
        ("archiveway", (13, 33), (26, 33), 4.0, -4.0, -4.0, 3.8, 0),
        ("brazierway", (-4, 44), (-4, 56), 4.0, -4.0, -6.4, 3.8, 8),
        ("lensway", (35, 52), (35, 62), 4.0, -4.0, -4.0, 3.8, 0),
        ("crossing", (6, 70), (30, 74), 4.6, -6.4, -4.0, 4.4, 8),
        ("hallway", (0, 82), (0, 96), 5.0, -6.4, -9.0, 4.6, 10),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=VAULT_FLOOR, wall_mat=DARK_STONE,
                      ceil_mat=DARK_STONE, steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- 1. sealed approach: the great wheel door -------------------------
    door_z = 8.0 - WALL_T * 0.5
    g.add(M.cylinder(3.3, 3.3, 0.45, 40, uv_scale=0.5, material=DARK_STONE)
          .rotate_x(math.pi * 0.5).translate(0.0, 2.6, door_z))
    g.add(M.cylinder(2.85, 2.85, 0.30, 40, uv_scale=0.5, material=BRASS)
          .rotate_x(math.pi * 0.5).translate(0.0, 2.6, door_z - 0.24))
    for index in range(12):
        angle = 2.0 * math.pi * index / 12.0
        spoke = M.box((0.22, 2.5, 0.16), uv_scale=0.7, material=BRASS)
        spoke.rotate_z(angle)
        g.add(spoke.translate(math.sin(angle) * 1.25, 2.6 + math.cos(angle) * 1.25,
                              door_z - 0.42))
    g.add(brass_ring(1.35, 0.11).rotate_x(math.pi * 0.5)
          .translate(0.0, 2.6, door_z - 0.46))
    g.add(M.icosphere(0.38, subdivisions=2, material=CRYSTAL)
          .translate(0.0, 2.6, door_z - 0.62))
    for sx in (-1, 1):
        g.add(CC.shard(1.9, 0.30, faces=6, seed=seed + 10 + sx, material=CRYSTAL)
              .translate(sx * 4.6, 0.0, 5.4))
        g.add(S.column(height=5.2, radius=0.42, material=PALE_STONE)
              .translate(sx * 5.2, 0.0, -4.6))

    # -- 2. laboratory gallery: benches down a long lit hall ---------------
    gx, gz = it.centre("gallery")
    for index in range(5):
        z = 25.0 + index * 4.2
        for sx in (-1, 1):
            bench = instrument_bench(2.4, seed=seed + 20 + index * 2 + (sx > 0))
            bench.rotate_y(0.0 if sx < 0 else math.pi)
            g.add(bench.translate(sx * 7.6, -4.0, z))
    for index in range(6):
        z = 24.0 + index * 3.8
        for sx in (-1, 1):
            g.add(S.column(height=7.0, radius=0.40, material=ASHLAR)
                  .translate(sx * 11.4, -4.0, z))
    # a gallery walkway above the benches, reached from nowhere: it is scenery,
    # and it is not a walk surface for exactly that reason
    for sx in (-1, 1):
        g.add(M.box((2.2, 0.24, 20.0), center=(sx * 11.0, 0.4, gz), uv_scale=0.5,
                    material=DARK_STONE))
        g.add(brass_ring(0.05).translate(0, 0, 0))  # keeps material set stable
        for index in range(9):
            g.add(M.cylinder(0.05, 0.045, 1.0, 6, uv_scale=0.6, material=BRASS)
                  .translate(sx * 10.0, 0.52, 24.0 + index * 2.4))

    # -- 3. archive aisle --------------------------------------------------
    ax, az = it.centre("archive")
    for index in range(5):
        z = 28.5 + index * 4.6
        for sx in (-1, 1):
            rack = archive_rack(4.0, 3.4, seed=seed + 40 + index * 2 + (sx > 0))
            rack.rotate_y(math.pi * 0.5)
            g.add(rack.translate(ax + sx * 6.4, -4.0, z))
    g.add(M.cylinder(2.2, 2.2, 0.3, 32, uv_scale=0.5, material=BLUE_CRYSTAL)
          .rotate_x(math.pi * 0.5).translate(ax, 2.4, 52.0 - WALL_T))
    g.add(brass_ring(2.3, 0.12).rotate_x(math.pi * 0.5)
          .translate(ax, 2.4, 52.0 - WALL_T - 0.18))

    # -- 4. crystal brazier: the hero dais ---------------------------------
    bx, bz = it.centre("brazier")
    g.add(railed_dais(5.4, 1.2, seed=seed + 60, steps=3).translate(bx, -6.4, bz))
    g.add(CC.cluster(count=9, radius=2.1, height=5.4, seed=seed + 61,
                     material=CRYSTAL).translate(bx, -5.2, bz))
    for index in range(8):
        angle = 2.0 * math.pi * index / 8.0
        g.add(S.column(height=9.0, radius=0.46, material=DARK_STONE)
              .translate(bx + math.cos(angle) * 9.5, -6.4,
                         bz + math.sin(angle) * 10.5))
    for index in range(4):
        angle = math.pi * 0.25 + math.pi * 0.5 * index
        g.add(P.brazier(seed=seed + 70 + index).translate(
            bx + math.cos(angle) * 7.0, -6.4, bz + math.sin(angle) * 7.6))

    # -- 6. lens room: the great window over the barrens -------------------
    lx, lz = it.centre("lens")
    g.add(M.cylinder(3.6, 3.6, 0.22, 40, uv_scale=0.5, material=BLUE_CRYSTAL)
          .rotate_x(math.pi * 0.5).translate(lx, 3.2, 84.0 - WALL_T))
    g.add(brass_ring(3.7, 0.16).rotate_x(math.pi * 0.5)
          .translate(lx, 3.2, 84.0 - WALL_T - 0.16))
    for index in range(8):
        angle = 2.0 * math.pi * index / 8.0
        spoke = M.box((0.14, 7.0, 0.12), uv_scale=0.7, material=BRASS)
        spoke.rotate_z(angle)
        g.add(spoke.translate(lx, 3.2, 84.0 - WALL_T - 0.30))
    g.add(instrument_bench(3.0, seed=seed + 80).translate(lx, -4.0, lz - 3.0))
    for sx in (-1, 1):
        g.add(M.box((0.3, 1.0, 8.0), center=(lx + sx * 5.0, -3.2, lz), uv_scale=0.6,
                    material=BRASS))

    # -- 7. containment cell, off the crossing -----------------------------
    g.add(containment_cage(1.6, 3.8, seed=seed + 90).translate(18.0, -5.4, 72.0))
    g.add(railed_dais(3.0, 0.6, seed=seed + 91, steps=2).translate(18.0, -6.0, 72.0))

    # -- 8. energy crossing: brass pillars either side of the run ----------
    for index in range(5):
        t = index / 4.0
        x = 6.0 + (30.0 - 6.0) * t
        z = 70.0 + (74.0 - 70.0) * t
        for side in (-1, 1):
            g.add(M.cylinder(0.34, 0.28, 4.0, 12, uv_scale=0.6, material=BRASS)
                  .translate(x, -6.4 + 2.4 * t, z + side * 3.1))
            g.add(M.icosphere(0.30, subdivisions=1, material=CRYSTAL)
                  .translate(x, -6.4 + 2.4 * t + 4.2, z + side * 3.1))

    # -- 9. research hall: the domed chamber at the bottom -----------------
    hx, hz = it.centre("hall")
    g.add(railed_dais(9.0, 1.8, seed=seed + 100, steps=3).translate(hx, -9.0, hz))
    for tier, (r, y) in enumerate(((13.5, -9.0), (16.5, -6.2))):
        for index in range(16):
            angle = 2.0 * math.pi * index / 16.0
            g.add(S.column(height=5.6, radius=0.44, material=MARBLE)
                  .translate(hx + math.cos(angle) * r, y, hz + math.sin(angle) * r))
        g.add(brass_ring(r, 0.16).translate(hx, y + 5.7, hz))
    g.add(CC.cluster(count=7, radius=1.6, height=4.2, seed=seed + 101,
                     material=CRYSTAL).translate(hx, -7.2, hz))
    g.add(containment_cage(2.2, 5.0, seed=seed + 102).translate(hx, -7.2, hz))
    for index in range(6):
        angle = 2.0 * math.pi * index / 6.0
        g.add(instrument_bench(2.2, seed=seed + 110 + index)
              .rotate_y(angle)
              .translate(hx + math.cos(angle) * 11.0, -9.0,
                         hz + math.sin(angle) * 11.0))

    # -- 10. the material study, on a bench by the hall stair --------------
    g.add(M.box((2.0, 0.9, 1.1), center=(hx - 9.0, -8.55, hz - 13.0), uv_scale=0.7,
                material=DARK_STONE))
    for index in range(3):
        g.add(CC.cluster(count=3, radius=0.5, height=0.7, seed=seed + 120 + index,
                         material=CRYSTAL)
              .translate(hx - 9.6 + index * 0.62, -8.1, hz - 13.0))
    for index in range(3):
        g.add(M.cylinder(0.11, 0.11, 0.52, 10, uv_scale=0.7, material=BRASS)
              .rotate_z(math.pi * 0.5)
              .translate(hx - 8.4, -8.02, hz - 13.4 + index * 0.34))

    lamp_points = [
        (-4.2, 3.2, -3.0), (4.2, 3.2, 3.0),
        (0.0, 0.4, 14.0), (0.0, -1.6, 19.0),
        (-9.0, -0.6, 26.0), (9.0, -0.6, 34.0), (0.0, -0.6, 30.0), (0.0, -0.6, 40.0),
        (30.0, -0.6, 30.0), (40.0, -0.6, 40.0), (35.0, -0.6, 48.0),
        (-4.0, -1.0, 50.0),
        (-16.0, -2.4, 62.0), (0.0, -2.4, 76.0), (-8.0, -2.4, 70.0),
        (36.0, -0.6, 58.0),
        (36.0, -0.6, 68.0), (46.0, -0.6, 78.0), (40.0, -0.6, 74.0),
        (14.0, -2.6, 71.0), (24.0, -1.6, 73.0),
        (0.0, -3.0, 88.0),
        (-12.0, -3.6, 104.0), (12.0, -3.6, 128.0), (0.0, -3.6, 116.0),
        (-14.0, -3.6, 126.0), (14.0, -3.6, 106.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "approach"
    it.subjects = [
        ("concept-01", "sealed approach", "approach"),
        ("concept-02", "laboratory gallery", "gallery"),
        ("concept-03", "archive aisle", "archive"),
        ("concept-04", "crystal brazier", "brazier"),
        # its own camera: a close shot across a bench, not the wide gallery again
        ("concept-05", "experiment table", "gallery",
         (-5.0, -2.5, 27.4), (-7.6, -3.0, 29.2)),
        ("concept-06", "lens room", "lens"),
        ("concept-07", "containment cell", "crossing",
         (13.5, -5.0, 68.5), (18.0, -5.2, 72.0)),
        ("concept-08", "energy crossing", "crossing"),
        ("concept-09", "research hall", "hall"),
        ("concept-10", "amethyst brass machinery materials", "hall",
         (-6.6, -7.85, 105.6), (-9.0, -8.25, 103.0)),
    ]
    it.landmark("the-sealed-door", "The Sealed Door", "approach", 2.6)
    it.landmark("the-gallery", "The Laboratory Gallery", "gallery")
    it.landmark("the-archive", "The Archive Aisle", "archive")
    it.landmark("the-brazier", "The Crystal Brazier", "brazier", 2.4)
    it.landmark("the-lens", "The Lens Room", "lens", 2.0)
    it.landmark("the-research-hall", "The Research Hall", "hall", 2.4)
    it.interactives = [
        {"id": "vault-door-wheel", "kind": "mechanism", "position": [0.0, 2.6, 7.6]},
        {"id": "experiment-table", "kind": "crafting", "position": [-7.6, -3.0, 29.2]},
        {"id": "archive-index", "kind": "lore", "position": [35.0, -3.0, 50.0]},
        {"id": "containment-cell", "kind": "mechanism", "position": [18.0, -5.4, 72.0]},
        {"id": "resonance-engine", "kind": "mechanism", "position": [0.0, -7.2, 116.0]},
    ]
    it.harvestables = [
        {"id": "vault-shard-01", "resource": "resonant-shard",
         "position": [-8.0, -6.2, 69.0]},
        {"id": "vault-shard-02", "resource": "resonant-shard",
         "position": [-6.0, -6.2, 74.0]},
    ]
    it.npc_markers = [
        {"id": "vault-warden", "name": "Vault Warden", "position": [0.0, -3.9, 24.0]},
        {"id": "resonance-adept", "name": "Resonance Adept", "position": [35.0, -3.9, 40.0]},
        {"id": "lens-keeper", "name": "Lens Keeper", "position": [41.0, -3.9, 74.0]},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.13, 0.11, 0.18], "energy": 0.42},
        "fog": {"enabled": True, "colour": [0.05, 0.05, 0.08],
                "begin": 16.0, "end": 54.0},
        "audio": [{"id": "resonance-hum", "space": "hall", "loop": True},
                  {"id": "arc-crackle", "space": "crossing", "loop": True}],
    }
    it.notes = [
        "Dressed slate and brass throughout, against the ochre dust of the "
        "region above: the Glasswardens built down away from the storm.",
        "The gallery walkways are scenery, not walk surfaces. They are reachable "
        "from nowhere, and marking them walkable would let the grounding ray "
        "stand an actor two metres above the bench floor.",
    ]
    return it


# --------------------------------------------------------------------------
# 2. The Geode Hollow
# --------------------------------------------------------------------------
def geode_hollow(seed: int = 20260902) -> Interior:
    """Inside a geode cave mouth: the crystal as it grows, undisturbed.

    The counterweight to the Vault. No dressed stone, no brass, no straight
    line: a throat down through rock into a chamber whose walls are the inside
    of a geode, with a still pool that doubles it.
    """
    it = Interior("amethyst_geode_hollow", "The Geode Hollow", "cave",
                  "amethyst-geode-cave-1", [318.0, 6.42, -102.0],
                  "geode-hollow-mouth")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("mouth", -7, -6, 7, 6, 0.0, 6.0, floor_mat=DUST, wall_mat=DARK_STONE,
             ceil_mat=DARK_STONE, ceiling="vault", vault_rise=2.6,
             doors=[("north", 0.0, 5.2, 3.6)])
    it.space("throat", -6, 18, 6, 30, -5.0, 6.4, floor_mat=CRYSTAL_GROUND,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=3.0, doors=[("south", 0.0, 5.2, 3.6), ("north", 0.0, 5.0, 3.4)])
    it.space("hollow", -22, 42, 22, 86, -9.0, 15.0, floor_mat=CRYSTAL_GROUND,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=7.5, doors=[("south", 0.0, 5.0, 3.4), ("east", 74.0, 4.2, 3.2)])
    it.space("mirror", 34, 62, 56, 84, -10.4, 9.0, floor_mat=DARK_STONE,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=4.2, doors=[("west", 74.0, 4.2, 3.2)])

    links = [
        ("descent", (0, 6), (0, 18), 5.2, 0.0, -5.0, 4.6, 14),
        ("gullet", (0, 30), (0, 42), 5.0, -5.0, -9.0, 4.6, 10),
        ("mirrorway", (22, 74), (34, 74), 4.2, -9.0, -10.4, 4.0, 4),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=CRYSTAL_GROUND, wall_mat=DARK_STONE,
                      ceil_mat=DARK_STONE, steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- mouth: daylight behind, crystal teeth around the opening ----------
    for index in range(9):
        angle = math.pi * (0.08 + 0.84 * index / 8.0)
        size = float(rng.uniform(0.7, 1.7))
        tooth = CC.shard(size * 2.0, size * 0.42, faces=int(rng.integers(5, 8)),
                         seed=seed + index, material=CRYSTAL)
        tooth.rotate_z(float(rng.uniform(-0.5, 0.5)) + math.pi * 0.5)
        tooth.rotate_y(angle)
        g.add(tooth.translate(math.cos(angle) * 6.2, 0.6 + math.sin(angle) * 3.4, -5.0))
    for index in range(5):
        g.add(P.boulder(radius=float(rng.uniform(0.5, 1.1)), seed=seed + 20 + index,
                        material=DARK_STONE)
              .translate(float(rng.uniform(-5.5, 5.5)), 0.0,
                         float(rng.uniform(-4.5, 3.0))))

    # -- throat: the walls begin to close in with crystal ------------------
    for index in range(14):
        side = -1 if index % 2 else 1
        z = 18.5 + (index // 2) * 1.7
        g.add(CC.vein_scatter(radius=1.5, count=int(rng.integers(4, 8)),
                              seed=seed + 40 + index, height=float(rng.uniform(0.6, 1.4)))
              .translate(side * float(rng.uniform(3.6, 5.4)), -5.0, z))

    # -- hollow: the geode itself ------------------------------------------
    hx, hz = it.centre("hollow")
    # the crystal lining, dense on the walls and thinning toward the middle
    for index in range(70):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        radial = float(rng.uniform(0.55, 1.0)) ** 0.5
        x = hx + math.cos(angle) * radial * 20.0
        z = hz + math.sin(angle) * radial * 21.0
        lift = float(rng.uniform(0.0, 1.0))
        size = float(rng.uniform(1.1, 3.6)) * (0.5 + lift * 0.9)
        shard = CC.shard(size * 2.2, size * 0.44, faces=int(rng.integers(5, 8)),
                         seed=seed + 100 + index, material=CRYSTAL)
        # shards on the upper wall point inward and down
        shard.rotate_z(math.pi * (0.20 + 0.55 * lift))
        shard.rotate_y(angle + math.pi)
        g.add(shard.translate(x, -9.0 + lift * 11.0, z))
    # the choir: seven great shards standing on the floor in a ring
    for index in range(7):
        angle = 2.0 * math.pi * index / 7.0 + 0.4
        g.add(CC.spire(height=float(rng.uniform(7.0, 11.5)),
                       radius=float(rng.uniform(0.9, 1.5)),
                       seed=seed + 200 + index, material=CRYSTAL,
                       rock_material=DARK_STONE)
              .translate(hx + math.cos(angle) * 11.0, -9.2,
                         hz + math.sin(angle) * 12.0))
    g.add(CC.cluster(count=11, radius=3.4, height=7.0, seed=seed + 210,
                     material=CRYSTAL).translate(hx, -9.0, hz))
    for index in range(9):
        g.add(P.boulder(radius=float(rng.uniform(0.6, 1.6)), seed=seed + 220 + index,
                        material=DARK_STONE)
              .translate(hx + float(rng.uniform(-17, 17)), -9.0,
                         hz + float(rng.uniform(-19, 19))))

    # -- mirror: the still pool that doubles the hollow ---------------------
    mx, mz = it.centre("mirror")
    g.add(M.box((18.0, 0.06, 18.0), center=(mx, -9.7, mz), uv_scale=0.25,
                material=WATER))
    for index in range(14):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        r = float(rng.uniform(9.0, 10.6))
        g.add(CC.shard(float(rng.uniform(1.4, 3.2)), float(rng.uniform(0.3, 0.6)),
                       faces=int(rng.integers(5, 8)), seed=seed + 300 + index,
                       material=CRYSTAL)
              .translate(mx + math.cos(angle) * r, -10.4, mz + math.sin(angle) * r))

    lamp_points = [
        (0.0, 3.4, -2.0),
        (0.0, -1.6, 12.0), (0.0, -1.6, 24.0),
        (0.0, -5.6, 36.0),
        (-14.0, -3.0, 52.0), (14.0, -3.0, 76.0), (0.0, -3.0, 64.0),
        (-14.0, -3.0, 76.0), (14.0, -3.0, 52.0),
        (45.0, -6.0, 73.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "mouth"
    it.subjects = [
        ("concept-01", "cave mouth from within", "mouth"),
        ("concept-02", "crystal-lined throat", "throat"),
        ("concept-03", "the descent", "descent"),
        ("concept-04", "the geode hollow", "hollow"),
        ("concept-05", "the crystal choir", "hollow"),
        ("concept-06", "the mirror pool", "mirror"),
    ]
    it.landmark("the-hollow", "The Geode Hollow", "hollow", 3.0)
    it.landmark("the-choir", "The Crystal Choir", "hollow", 1.8)
    it.landmark("the-mirror-pool", "The Mirror Pool", "mirror", 1.4)
    it.harvestables = [
        {"id": "geode-seam-%02d" % index, "resource": "amethyst-shard",
         "position": [round(float(rng.uniform(-16, 16)), 2), -9.0,
                      round(float(rng.uniform(46, 82)), 2)]}
        for index in range(8)
    ]
    it.npc_markers = [
        {"id": "hollow-crawler", "name": "Geode Crawler", "kind": "creature-zone",
         "position": [0.0, -9.0, 64.0], "radius": 22.0},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.16, 0.12, 0.24], "energy": 0.55},
        "fog": {"enabled": True, "colour": [0.09, 0.06, 0.13],
                "begin": 18.0, "end": 60.0},
        "audio": [{"id": "crystal-resonance", "space": "hollow", "loop": True},
                  {"id": "drip", "space": "mirror", "loop": True}],
    }
    it.notes = [
        "No dressed stone and no brass anywhere in this package. It is the one "
        "interior that is not built, only entered, and it earns its place by "
        "being unlike the other three.",
        "The crystal lining is placed on a radial falloff, so shards are dense "
        "against the walls and thin over the floor a player actually crosses.",
    ]
    return it


# --------------------------------------------------------------------------
# 3. The Shardworks
# --------------------------------------------------------------------------
def shardworks(seed: int = 20260903) -> Interior:
    """Under a resonant digging: the crystal being cut out and carried up.

    Timber, iron and spoil. Where the Vault studies the crystal and the Hollow
    grows it, this is the place people break it, weigh it and haul it - panel 7
    of the region board, continued underground.
    """
    it = Interior("amethyst_shardworks", "The Shardworks", "workings",
                  "resonant-crystal-cluster-0", [138.0, 2.09, -42.0],
                  "shardworks-headframe")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("headframe", -8, -7, 8, 7, 0.0, 7.5, floor_mat=DUST,
             wall_mat=RUBBLE, ceil_mat=TIMBER_DARK, ceiling="open",
             doors=[("north", 0.0, 4.6, 3.2)])
    it.space("sorting", -14, 20, 14, 40, -6.0, 5.6, floor_mat=DUST,
             wall_mat=RUBBLE, ceil_mat=TIMBER_DARK,
             doors=[("south", 0.0, 4.6, 3.2), ("east", 30.0, 4.2, 3.0),
                    ("west", 32.0, 4.2, 3.0)])
    it.space("cutting", 26, 24, 46, 42, -6.0, 5.2, floor_mat=DUST,
             wall_mat=RUBBLE, ceil_mat=TIMBER_DARK,
             doors=[("west", 30.0, 4.2, 3.0)])
    it.space("stope", -46, 24, -26, 46, -7.4, 8.5, floor_mat=CRYSTAL_GROUND,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=3.4, doors=[("east", 32.0, 4.2, 3.0), ("north", -36.0, 4.0, 3.0)])
    it.space("deep", -46, 58, -22, 82, -11.0, 7.0, floor_mat=CRYSTAL_GROUND,
             wall_mat=DARK_STONE, ceil_mat=DARK_STONE, ceiling="vault",
             vault_rise=3.0, doors=[("south", -36.0, 4.0, 3.0)])

    links = [
        ("shaft", (0, 7), (0, 20), 4.6, 0.0, -6.0, 4.4, 16),
        ("cuttingway", (14, 30), (26, 30), 4.2, -6.0, -6.0, 3.8, 0),
        ("stopeway", (-14, 32), (-26, 32), 4.2, -6.0, -7.4, 3.8, 4),
        ("winze", (-36, 46), (-36, 58), 4.0, -7.4, -11.0, 3.8, 10),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=DUST, wall_mat=RUBBLE, ceil_mat=TIMBER_DARK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- headframe: the winding gear, open to the storm above --------------
    for sx in (-1, 1):
        for sz in (-1, 1):
            leg = M.box((0.34, 7.4, 0.34), uv_scale=0.7, material=TIMBER)
            leg.rotate_z(-sx * 0.06)
            g.add(leg.translate(sx * 3.4, 3.7, sz * 3.0))
    g.add(M.box((7.6, 0.4, 6.6), center=(0.0, 7.6, 0.0), uv_scale=0.7,
                material=TIMBER))
    g.add(M.cylinder(1.5, 1.5, 0.36, 20, uv_scale=0.6, material=IRON)
          .rotate_x(math.pi * 0.5).translate(0.0, 7.0, 0.0))
    g.add(brass_ring(1.55, 0.09, material=IRON).rotate_x(math.pi * 0.5)
          .translate(0.0, 7.0, 0.0))
    for index in range(3):
        g.add(P.crate(size=float(rng.uniform(0.55, 0.8)), seed=seed + index)
              .translate(float(rng.uniform(-6, 6)), 0.0, float(rng.uniform(-5, 4))))

    # -- sorting floor: benches, scales, spoil -----------------------------
    sx0, sz0 = it.centre("sorting")
    for index in range(4):
        z = 23.0 + index * 4.2
        g.add(timber_prop(5.0, seed=seed + 10 + index, width=3.0)
              .translate(0.0, -6.0, z))
    for index in range(3):
        bench = P.workbench(length=2.6, seed=seed + 20 + index)
        for part in bench.parts:
            part.material = {"timber_warm": TIMBER, "dark_iron": IRON}.get(
                part.material, part.material)
        g.add(bench.translate(-9.0 + index * 9.0, -6.0, 34.0))
    # the scale pan, hanging from a prop
    g.add(M.cylinder(0.9, 0.78, 0.2, 14, uv_scale=0.7, material=BRASS)
          .translate(6.0, -4.6, 26.0))
    for index in range(3):
        angle = 2.0 * math.pi * index / 3.0
        g.add(M.cylinder(0.03, 0.03, 1.5, 5, uv_scale=0.7, material=IRON)
              .translate(6.0 + math.cos(angle) * 0.5, -4.5,
                         26.0 + math.sin(angle) * 0.5))
    for index in range(7):
        g.add(CC.vein_scatter(radius=1.2, count=int(rng.integers(3, 7)),
                              seed=seed + 30 + index, height=0.5)
              .translate(float(rng.uniform(-12, 12)), -6.0,
                         float(rng.uniform(22, 38))))

    # -- cutting floor: saw frames and finished blanks ---------------------
    cx, cz = it.centre("cutting")
    for index in range(3):
        x = cx - 6.0 + index * 6.0
        g.add(M.box((2.4, 0.9, 1.4), center=(x, -5.55, cz), uv_scale=0.7,
                    material=TIMBER_DARK))
        frame = M.box((0.14, 1.8, 0.14), uv_scale=0.7, material=IRON)
        g.add(frame.translate(x - 1.0, -5.1, cz))
        g.add(M.box((0.14, 1.8, 0.14), uv_scale=0.7, material=IRON)
              .translate(x + 1.0, -5.1, cz))
        blade = M.box((2.2, 0.06, 0.5), uv_scale=0.7, material=IRON)
        g.add(blade.translate(x, -4.3, cz))
        g.add(CC.shard(0.5, 0.22, faces=6, seed=seed + 50 + index, material=CRYSTAL)
              .translate(x, -5.1, cz))
    for index in range(5):
        g.add(P.crate(size=float(rng.uniform(0.5, 0.75)), seed=seed + 60 + index)
              .translate(cx + float(rng.uniform(-8, 8)), -6.0,
                         cz + float(rng.uniform(-7, 7))))

    # -- stope: the face they are working ----------------------------------
    tx, tz = it.centre("stope")
    for index in range(5):
        z = 26.0 + index * 4.4
        g.add(timber_prop(6.4, seed=seed + 70 + index, width=3.4)
              .translate(tx, -7.4, z))
    for index in range(22):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        size = float(rng.uniform(0.8, 2.6))
        shard = CC.shard(size * 2.0, size * 0.42, faces=int(rng.integers(5, 8)),
                         seed=seed + 80 + index, material=CRYSTAL)
        shard.rotate_z(float(rng.uniform(0.3, 1.2)))
        shard.rotate_y(angle)
        g.add(shard.translate(tx - 8.0 + float(rng.uniform(-1.5, 1.5)),
                              -7.4 + float(rng.uniform(0.0, 5.5)),
                              float(rng.uniform(26, 44))))
    cart = P.cart(seed=seed + 90)
    for part in cart.parts:
        part.material = {"timber_warm": TIMBER, "dark_iron": IRON}.get(
            part.material, part.material)
    g.add(cart.translate(tx + 5.0, -7.4, 34.0))

    # -- deep: where the workings stop, and something older starts ---------
    dx, dz = it.centre("deep")
    g.add(CC.cluster(count=9, radius=2.6, height=5.0, seed=seed + 100,
                     material=CRYSTAL).translate(dx, -11.0, dz))
    for index in range(3):
        g.add(timber_prop(5.4, seed=seed + 110 + index, width=3.0)
              .translate(dx, -11.0, 62.0 + index * 6.0))
    g.add(P.brazier(seed=seed + 120).translate(dx + 6.0, -11.0, dz - 6.0))
    for index in range(4):
        g.add(P.boulder(radius=float(rng.uniform(0.5, 1.2)), seed=seed + 130 + index,
                        material=DARK_STONE)
              .translate(dx + float(rng.uniform(-9, 9)), -11.0,
                         dz + float(rng.uniform(-9, 9))))

    lamp_points = [
        (-5.0, 4.0, -3.0), (5.0, 4.0, 3.0),
        (0.0, -1.8, 12.0),
        (-10.0, -2.4, 24.0), (10.0, -2.4, 36.0), (0.0, -2.4, 30.0),
        (20.0, -2.4, 30.0),
        (32.0, -2.4, 28.0), (42.0, -2.4, 38.0), (36.0, -2.4, 33.0),
        (-20.0, -2.6, 32.0),
        (-30.0, -3.4, 28.0), (-42.0, -3.4, 42.0), (-36.0, -3.4, 35.0),
        (-36.0, -5.0, 52.0),
        (-28.0, -7.0, 64.0), (-40.0, -7.0, 78.0), (-34.0, -7.0, 70.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "headframe"
    it.subjects = [
        ("concept-01", "headframe and winding gear", "headframe"),
        ("concept-02", "the shaft", "shaft"),
        ("concept-03", "sorting floor", "sorting"),
        ("concept-04", "the scale pan", "sorting"),
        ("concept-05", "cutting floor", "cutting"),
        ("concept-06", "the working stope", "stope"),
        ("concept-07", "the winze", "winze"),
        ("concept-08", "the deep", "deep"),
    ]
    it.landmark("the-headframe", "The Headframe", "headframe", 2.0)
    it.landmark("the-sorting-floor", "The Sorting Floor", "sorting")
    it.landmark("the-cutting-floor", "The Cutting Floor", "cutting")
    it.landmark("the-stope", "The Working Stope", "stope", 2.0)
    it.landmark("the-deep", "The Deep", "deep", 2.0)
    it.interactives = [
        {"id": "winding-gear", "kind": "mechanism", "position": [0.0, 0.4, 0.0]},
        {"id": "assay-scale", "kind": "crafting", "position": [6.0, -4.6, 26.0]},
        {"id": "cutting-frame", "kind": "crafting", "position": [36.0, -5.1, 33.0]},
    ]
    it.harvestables = [
        {"id": "stope-face-%02d" % index, "resource": "amethyst-shard",
         "position": [round(-44.0 + float(rng.uniform(0, 3)), 2),
                      round(-7.4 + float(rng.uniform(0, 3)), 2),
                      round(float(rng.uniform(26, 44)), 2)]}
        for index in range(6)
    ]
    it.npc_markers = [
        {"id": "shift-captain", "name": "Shift Captain", "position": [0.0, -5.9, 30.0]},
        {"id": "shard-cutter-deep", "name": "Shard Cutter", "position": [36.0, -5.9, 33.0]},
        {"id": "hauler", "name": "Hauler", "position": [-31.0, -7.3, 34.0]},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.16, 0.13, 0.12], "energy": 0.40},
        "fog": {"enabled": True, "colour": [0.09, 0.08, 0.07],
                "begin": 12.0, "end": 44.0},
        "audio": [{"id": "pick-work", "space": "stope", "loop": True},
                  {"id": "winding-gear", "space": "headframe", "loop": True}],
    }
    it.notes = [
        "The headframe is open to the sky, so the shaft reads as a hole in the "
        "barrens rather than as a door in a wall.",
        "Warm timber and iron against cold crystal is the whole point: this is "
        "the only interior of the four where people are working.",
    ]
    return it


# --------------------------------------------------------------------------
# 4. The Storm Barrow
# --------------------------------------------------------------------------
def storm_barrow(seed: int = 20260904) -> Interior:
    """Under a storm ruin: what was here before the Glasswardens.

    A barrow the storm still finds. Old, coarse masonry, a shaft open to the sky
    where lightning comes down onto a fused floor, and a sealed chamber past it
    that nobody living laid out.
    """
    it = Interior("amethyst_storm_barrow", "The Storm Barrow", "barrow",
                  "amethyst-storm-ruin-0", [216.0, 3.14, -168.0],
                  "storm-barrow-stair")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("dromos", -5, -6, 5, 8, 0.0, 4.4, floor_mat=PAVING, wall_mat=RUBBLE,
             ceil_mat=RUBBLE, ceiling="vault", vault_rise=1.8,
             doors=[("north", 0.0, 3.6, 2.8)])
    it.space("antechamber", -11, 20, 11, 36, -4.6, 5.0, floor_mat=PAVING,
             wall_mat=ASHLAR, ceil_mat=RUBBLE, ceiling="vault", vault_rise=2.6,
             doors=[("south", 0.0, 3.6, 2.8), ("north", 0.0, 4.0, 3.0)])
    # the strike well is open to the sky: the storm still comes down it
    it.space("strikewell", -13, 48, 13, 74, -6.0, 16.0, floor_mat=DARK_STONE,
             wall_mat=ASHLAR, ceil_mat=DARK_STONE, ceiling="open",
             doors=[("south", 0.0, 4.0, 3.0), ("north", 0.0, 3.6, 2.8)])
    it.space("cella", -16, 86, 16, 114, -8.4, 7.0, floor_mat=PAVING,
             wall_mat=ASHLAR, ceil_mat=ASHLAR, ceiling="vault", vault_rise=3.4,
             doors=[("south", 0.0, 3.6, 2.8)])

    links = [
        ("stair", (0, 8), (0, 20), 3.6, 0.0, -4.6, 3.4, 14),
        ("wellway", (0, 36), (0, 48), 4.0, -4.6, -6.0, 3.6, 5),
        ("cellaway", (0, 74), (0, 86), 3.6, -6.0, -8.4, 3.4, 8),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=PAVING, wall_mat=ASHLAR, ceil_mat=RUBBLE,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- dromos: the entrance passage, half fallen ------------------------
    g.add(S.ancient_arch(span=4.0, height=4.6, depth=1.3, seed=seed, roots=False,
                         ruined=True).translate(0.0, 0.0, -4.4))
    for index in range(4):
        frag = S.ruin_fragment(seed=seed + index, scale=0.9)
        for part in frag.parts if hasattr(frag, "parts") else [frag]:
            part.material = RUBBLE
        g.add(frag.translate(float(rng.uniform(-3.6, 3.6)), 0.0,
                             float(rng.uniform(-4.5, 6.0))))

    # -- antechamber: standing stones brought inside -----------------------
    ax, az = it.centre("antechamber")
    for index in range(6):
        angle = 2.0 * math.pi * index / 6.0
        stone = M.box((0.9, float(rng.uniform(2.4, 3.4)), 0.6), uv_scale=0.7,
                      material=DARK_STONE)
        stone.rotate_y(angle + float(rng.normal(0, 0.08)))
        g.add(stone.translate(ax + math.cos(angle) * 6.5,
                              -4.6 + float(rng.uniform(1.1, 1.6)),
                              az + math.sin(angle) * 5.0))
    g.add(M.box((3.0, 0.5, 2.0), center=(ax, -4.35, az), uv_scale=0.7,
                material=ASHLAR))
    g.add(CC.vein_scatter(radius=2.4, count=6, seed=seed + 20, height=0.7)
          .translate(ax, -4.6, az))

    # -- strikewell: open to the sky, fused floor, the storm's own room ----
    wx, wz = it.centre("strikewell")
    # the fused disc where the lightning lands, and the crystal grown from it
    g.add(M.cylinder(6.0, 6.0, 0.22, 32, uv_scale=0.4, material=DARK_STONE)
          .translate(wx, -5.9, wz))
    g.add(M.cylinder(3.4, 3.4, 0.12, 28, uv_scale=0.5, material=CRYSTAL_GROUND)
          .translate(wx, -5.72, wz))
    g.add(CC.cluster(count=9, radius=2.2, height=6.5, seed=seed + 30,
                     material=CRYSTAL).translate(wx, -5.7, wz))
    # fulgurite: branching fused rock climbing the walls
    for index in range(10):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        base = np.array([wx + math.cos(angle) * 9.0, -6.0,
                         wz + math.sin(angle) * 11.0])
        path = np.array([base,
                         base + [float(rng.uniform(-1.2, 1.2)), 3.0,
                                 float(rng.uniform(-1.2, 1.2))],
                         base + [float(rng.uniform(-2.4, 2.4)), 6.4,
                                 float(rng.uniform(-2.4, 2.4))]])
        g.add(M.tube(path, [0.34, 0.22, 0.10], segments=8, cap_start=True,
                     cap_end=True, material=CRYSTAL))
    for index in range(8):
        angle = 2.0 * math.pi * index / 8.0
        g.add(S.column(height=8.0, radius=0.5, material=ASHLAR)
              .translate(wx + math.cos(angle) * 10.5, -6.0,
                         wz + math.sin(angle) * 12.0))
    for sx in (-1, 1):
        pole = M.cylinder(0.13, 0.11, 5.0, 8, uv_scale=0.7, material=IRON)
        g.add(pole.translate(wx + sx * 7.0, -6.0, wz - 8.0))
        g.add(M.box((0.06, 2.6, 1.7), uv_scale=0.8, material=BANNER)
              .translate(wx + sx * 7.0, -3.2, wz - 7.2))

    # -- cella: the sealed chamber ----------------------------------------
    cx, cz = it.centre("cella")
    for ring, (half, lift) in enumerate(((10.0, 0.0), (7.6, 0.4), (5.4, 0.8))):
        g.add_walk(M.box((half * 2, 0.4, half * 1.5),
                         center=(cx, -8.4 + lift + 0.2, cz), uv_scale=0.45,
                         material=PAVING))
    g.add(M.box((4.4, 1.0, 2.4), center=(cx, -7.1, cz), uv_scale=0.6,
                material=DARK_STONE))
    g.add(M.box((4.0, 0.14, 2.0), center=(cx, -6.53, cz), uv_scale=0.6,
                material=CRYSTAL))
    for dx, dz in ((-3.0, -2.0), (3.0, -2.0), (-3.0, 2.0), (3.0, 2.0)):
        g.add(M.cylinder(0.10, 0.08, 2.4, 8, uv_scale=0.7, material=IRON)
              .translate(cx + dx, -7.6, cz + dz))
        g.add(CC.shard(0.5, 0.16, faces=6, seed=seed + 40 + int(dx + dz),
                       material=CRYSTAL).translate(cx + dx, -5.2, cz + dz))
    for index in range(10):
        angle = 2.0 * math.pi * index / 10.0
        g.add(S.column(height=7.0, radius=0.42, material=ASHLAR)
              .translate(cx + math.cos(angle) * 13.0, -8.4,
                         cz + math.sin(angle) * 11.0))
    for index in range(5):
        frag = S.ruin_fragment(seed=seed + 50 + index, scale=1.0)
        for part in frag.parts if hasattr(frag, "parts") else [frag]:
            part.material = RUBBLE
        g.add(frag.translate(cx + float(rng.uniform(-12, 12)), -8.4,
                             cz + float(rng.uniform(-11, 11))))

    lamp_points = [
        (0.0, 2.6, -2.0),
        (0.0, -2.0, 13.0),
        (-8.0, -1.6, 24.0), (8.0, -1.6, 32.0), (0.0, -1.6, 28.0),
        (0.0, -2.6, 42.0),
        (-10.0, -1.0, 54.0), (10.0, -1.0, 68.0),
        (0.0, -3.4, 80.0),
        (-12.0, -3.0, 92.0), (12.0, -3.0, 108.0), (0.0, -3.0, 100.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "dromos"
    it.subjects = [
        ("concept-01", "the ruined dromos", "dromos"),
        ("concept-02", "standing stones brought inside", "antechamber"),
        ("concept-03", "the strike well from below", "strikewell"),
        ("concept-04", "the fused floor", "strikewell"),
        ("concept-05", "fulgurite on the walls", "strikewell"),
        ("concept-06", "the sealed cella", "cella"),
        ("concept-07", "the crystal bier", "cella"),
    ]
    it.landmark("the-dromos", "The Dromos", "dromos", 1.4)
    it.landmark("the-antechamber", "The Stone Antechamber", "antechamber")
    it.landmark("the-strike-well", "The Strike Well", "strikewell", 2.6)
    it.landmark("the-cella", "The Sealed Cella", "cella", 2.0)
    it.interactives = [
        {"id": "storm-altar", "kind": "shrine", "position": [0.0, -4.1, 28.0]},
        {"id": "crystal-bier", "kind": "lore", "position": [0.0, -6.5, 100.0]},
    ]
    it.harvestables = [
        {"id": "fulgurite-%02d" % index, "resource": "fulgurite",
         "position": [round(float(rng.uniform(-11, 11)), 2), -6.0,
                      round(float(rng.uniform(50, 72)), 2)]}
        for index in range(4)
    ]
    it.npc_markers = [
        {"id": "barrow-shade", "name": "Barrow Shade", "kind": "creature-zone",
         "position": [0.0, -8.4, 100.0], "radius": 16.0},
    ]
    it.environment = {
        "sky": "storm",
        "ambient": {"colour": [0.14, 0.13, 0.18], "energy": 0.38},
        "fog": {"enabled": True, "colour": [0.07, 0.07, 0.09],
                "begin": 14.0, "end": 48.0},
        "audio": [{"id": "storm-distant", "space": "strikewell", "loop": True},
                  {"id": "wind-hollow", "space": "cella", "loop": True}],
    }
    it.notes = [
        "The strike well is the one space in these four interiors with no lid: "
        "it is open to the region's sky, and the storm is what is still using "
        "this room.",
        "Coarse rubble and unadorned ashlar only. Nothing here is Glasswarden "
        "work, and no brass appears until the Vault.",
    ]
    return it


ALL = {
    "resonant_vault": resonant_vault,
    "geode_hollow": geode_hollow,
    "shardworks": shardworks,
    "storm_barrow": storm_barrow,
}


# --------------------------------------------------------------------------
# The combined insides map
# --------------------------------------------------------------------------
# Eternal Lands puts every inside belonging to a region on one map, separated by
# unwalkable void, and sends the player to a different arrival point on that map
# depending on which door was used. Doing the same here means one GLB, one
# manifest and one collision grid instead of four, one server map key instead of
# four, and one load rather than a load per doorway.
#
# The blackspace falls out of the construction rather than being drawn: the
# collision grid is built only where a Walk_ surface exists, so the gutters
# between the four are already blocked, and nothing is rendered there either.
#
# Offsets are chosen from each interior's measured footprint so no two come
# within about forty metres of each other. That gap is not decoration - it is
# what stops a lamp in the Shardworks lighting the Barrow, and what keeps a
# stray camera in one from seeing into another.
LAYOUT = {
    #                     offset x, offset z, gutter neighbours
    "resonant_vault": (0.0, 0.0),
    "geode_hollow": (140.0, 0.0),
    "shardworks": (30.0, 190.0),
    "storm_barrow": (165.0, 190.0),
}

# Shift the whole assembly clear of the origin so the map sits in positive
# coordinates with a margin on every side, the way a server map is indexed.
LAYOUT_ORIGIN = (53.0, 39.0)


def combine(seed: int = 20260901) -> Interior:
    """Assemble the four interiors onto one map with blackspace between them."""
    combined = Interior("amethyst_barrens_insides", "Amethyst Barrens Insides",
                        "insides", "glasswarden-observatory",
                        [-78.0, 8.15, -204.0], "resonant-vault-stair")
    combined.arrivals = []
    combined.sections = []

    for key, build_fn in ALL.items():
        part = build_fn(seed)
        dx = LAYOUT[key][0] + LAYOUT_ORIGIN[0]
        dz = LAYOUT[key][1] + LAYOUT_ORIGIN[1]

        part.group.translate(dx, 0.0, dz)
        combined.group.add(part.group)

        def move(position):
            return [round(float(position[0]) + dx, 2), round(float(position[1]), 2),
                    round(float(position[2]) + dz, 2)]

        for space_key, space in part.spaces.items():
            combined.spaces[f"{key}.{space_key}"] = {
                "x0": space["x0"] + dx, "x1": space["x1"] + dx,
                "z0": space["z0"] + dz, "z1": space["z1"] + dz,
                "floor": space["floor"], "height": space["height"]}
        for run_key, run in part.passages.items():
            combined.passages[f"{key}.{run_key}"] = {
                "a": (run["a"][0] + dx, run["a"][1] + dz),
                "b": (run["b"][0] + dx, run["b"][1] + dz),
                "y0": run["y0"], "y1": run["y1"],
                "width": run["width"], "height": run["height"]}

        for entry in part.landmarks:
            item = dict(entry)
            item["position"] = move(entry["position"])
            item["space"] = f"{key}.{entry['space']}" if "space" in entry else None
            item["section"] = key
            combined.landmarks.append(item)
        for source, target in ((part.interactives, combined.interactives),
                               (part.harvestables, combined.harvestables),
                               (part.npc_markers, combined.npc_markers)):
            for entry in source:
                item = dict(entry)
                item["position"] = move(entry["position"])
                item["section"] = key
                target.append(item)
        combined.lamps.extend(move(p) for p in part.lamps)
        combined.open_to_sky.extend(f"{key}.{s}" for s in part.open_to_sky)
        for entry in part.subjects:
            ident, subject, space = entry[0], entry[1], entry[2]
            rest = tuple(entry[3:])
            moved = tuple(move(v) for v in rest) if rest else ()
            combined.subjects.append(
                (f"{key}-{ident}", f"{part.name}: {subject}", f"{key}.{space}") + moved)

        # the arrival: where a player using this section's surface door lands
        spawn_space = combined.spaces[f"{key}.{part.spawn_space}"]
        arrival = [round((spawn_space["x0"] + spawn_space["x1"]) * 0.5, 2),
                   round(spawn_space["floor"] + 0.05, 2),
                   round((spawn_space["z0"] + spawn_space["z1"]) * 0.5, 2)]
        combined.arrivals.append({
            "id": part.destination_spawn, "name": part.name, "section": key,
            "space": f"{key}.{part.spawn_space}", "position": arrival})
        combined.sections.append({
            "id": key, "name": part.name, "class": part.klass,
            "offset": [dx, 0.0, dz], "arrival": arrival,
            "spaces": [f"{key}.{s}" for s in part.spaces],
            "notes": part.notes})

    combined.spawn_space = f"resonant_vault.{ALL['resonant_vault'](seed).spawn_space}"

    # One map, one environment. The four sections carry their own audio, and the
    # Barrow's strike well stays declared open to the sky so the client can keep
    # a hole in the roof where the region's storm comes down.
    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.14, 0.12, 0.19], "energy": 0.44},
        "fog": {"enabled": True, "colour": [0.06, 0.06, 0.09],
                "begin": 15.0, "end": 52.0},
        "audio": [
            {"id": "resonance-hum", "space": "resonant_vault.hall", "loop": True},
            {"id": "arc-crackle", "space": "resonant_vault.crossing", "loop": True},
            {"id": "crystal-resonance", "space": "geode_hollow.hollow", "loop": True},
            {"id": "drip", "space": "geode_hollow.mirror", "loop": True},
            {"id": "pick-work", "space": "shardworks.stope", "loop": True},
            {"id": "winding-gear", "space": "shardworks.headframe", "loop": True},
            {"id": "storm-distant", "space": "storm_barrow.strikewell", "loop": True},
            {"id": "wind-hollow", "space": "storm_barrow.cella", "loop": True},
        ],
    }
    combined.notes = [
        "Four interiors on one map with blackspace between them, in the Eternal "
        "Lands convention: one GLB, one manifest, one collision grid, one server "
        "map key, and an arrival point per surface door.",
        "The blackspace is not drawn. The collision grid is built only where a "
        "Walk_ surface exists, so the gutters between sections are blocked by "
        "construction rather than by a mask that could drift out of step.",
        "Sections are spaced so no two come within about forty metres, which is "
        "what keeps one section's lamps and cameras out of the next.",
    ]
    return combined


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR


def sour_cut(seed: int = 20260905) -> Interior:
    """A geode split by the sour ground of thread C: the crystal grows wrong here."""
    return SR.cave("amethyst_sour_cut", "The Sour Cut", "amethyst-geode-cave-3",
                   [204.0, 11.2, -252.0], "sour-cut-mouth",
                   palette={"floor": DUST, "rock": DARK_STONE, "crystal": CRYSTAL,
                            "water": WATER, "bone": PALE_STONE},
                   seed=seed, crystal=True, den="Crystal Cave Spider")


def measure_house(seed: int = 20260906) -> Interior:
    """Where the eleven measures are kept: a resonance cell under a storm ruin."""
    return SR.shrine("amethyst_measure_house", "The Measure House", "amethyst-storm-ruin-2",
                     [162.0, 4.9, -72.0], "measure-house-door",
                     palette={"floor": VAULT_FLOOR, "wall": PALE_STONE, "ceil": DARK_STONE,
                              "accent": BRASS, "crystal": CRYSTAL, "metal": BRASS},
                     seed=seed, style="crystal")


def counting_house(seed: int = 20260907) -> Interior:
    """Bel Ammon's two columns: the only honest arithmetic in the Barrens."""
    return SR.cottage("amethyst_counting_house", "The Shard Counter's House",
                      "resonant-crystal-cluster-2", [258.0, 4.0, -90.0], "counting-house-door",
                      palette={"floor": TIMBER, "wall": PALE_STONE, "roof": TIMBER_DARK,
                               "timber": TIMBER_DARK, "stone": DARK_STONE, "cloth": BANNER,
                               "iron": BRASS},
                      seed=seed, trade="workshop")


ALL.update({"sour_cut": sour_cut, "measure_house": measure_house,
            "counting_house": counting_house})
# a column east of the four set pieces, well clear of them
LAYOUT.update({"sour_cut": (230.0, 6.0), "measure_house": (230.0, 90.0),
               "counting_house": (230.0, 140.0)})
