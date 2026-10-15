"""Ssarathi Ruins' interiors, built from the same kit as the drowned city above.

Four spaces reached from named landmarks on the 576 m map:

    The Royal Archive       behind the Sun Vault          archive
    The Serpent Hatchery    under the Ritual Plaza        sanctum
    The Drowned Cistern     under the drowned quarter     utility
    The Root Undercroft     beneath the Strangled Arch    ruin

They share the region's material table, its `MeshGroup` walk-surface contract
and its modelling primitives, so a doorway, a stair tread and a column are the
same construction indoors as out.

WHERE THE PROGRAMME COMES FROM
------------------------------
**The Royal Archive's concept board does not decode.**
`interiors/ssarathi_royal_archive/references/00-concept-detail-board.png` is the
same truncated 786,444-byte file fifteen of the seventeen region boards carry,
but this one is worse than the region's was: zero rows decode, not the top row -
the IDAT stream is corrupt from its first byte. The copy under `dev/` is
byte-identical. There is no intact version anywhere in the tree.

So the Archive is built from the two authorities that do survive:

1. `concept.json` lists its ten subjects in words - water entrance, reading
   hall, scaled mosaic, water arch, archive shelves, royal statue, vault trap,
   flooded repository, central archive, and a material study of scale, stone and
   papyrus. Every one of them is a space or a fitting here.
2. The authored asset pack names the same pieces -
   `ssarathi_water_door`, `ssarathi_curved_wall`, `ssarathi_scaled_floor`,
   `ssarathi_water_arch`, `ssarathi_archive_shelf`, `ssarathi_royal_statue`,
   `ssarathi_vault_trap` - which corroborates the list and settles the naming.

That pack carries one more Ssarathi interior piece that is *not* among the ten:
`ssarathi_hatchery_pool`. A hatchery is therefore intended content for this
region, and it is the second section below.

Crownwater's `drowned_crown` had the same defect and was handled the same way.
The consequence is stated plainly in the package docs: there is no panel
comparison for the Archive, because there is no panel.

WHY THESE FOUR
--------------
Ssarathi is a city the water took, so its insides are about what the water
reached and what it did not. Each section takes a different answer, so no two
are the same room with different textures:

* **The Royal Archive** is what was saved. Dressed, ordered, lit, still dry in
  its heart - jade ashlar and gilt, curved walls, a scaled mosaic floor. The
  only section whose programme was given rather than invented.
* **The Serpent Hatchery** is what the place was *for*. No straight line in it:
  a coiled shaft down to tiered brooding pools cut as terraces, warm, organic,
  scale-tiled. The Archive's opposite in every axis.
* **The Drowned Cistern** is the water winning, and the counterweight to the
  Archive - undressed rubble and silt, columns standing in it, not one gram of
  gold anywhere. What the drowned quarter is standing on.
* **The Root Undercroft** is older than any of them and has no masonry order
  left: a chamber the strangler figs broke into and now hold up. The only
  section where the structure is wood rather than stone.

WHY THIS IS NOT IN `_toolkit/`
------------------------------
Amberwood's interiors live in `_toolkit/amberwood/interiors.py`, which makes the
shared toolkit carry one region's content. Ssarathi keeps its own beside its
region plan, exactly as Crownwater does: the toolkit's shell parts (`chamber`,
`passage`, `hanging_lamps`) are genuinely shared and imported unchanged; the
rooms are not.

THREE RULES THAT ARE LOAD-BEARING
---------------------------------
Inherited from the toolkit's notes and from Crownwater's, and all three
re-checked here:

* A walkable surface must be registered with `add_walk`. A floor added with
  `add` is scenery the player falls through.
* A descending passage's ceiling must follow its floor, or the passage stands
  proud of the room it opens into and leaks to the void.
* **Placement is single-layer.** The client puts an actor on the *first*
  surface a ray from y = 400 meets, so no spawn or portal may sit beneath a
  deck, and any gallery over a room a player arrives in must be annular. This
  is what put every placement in Crownwater's campanile 26 m up.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S
from amberwood import trees as TR
from amberwood.interiors import Interior, chamber, hanging_lamps, passage

import ssaratharch as A
import ssarathikit as SK

# -- materials, the region's own, indoors ----------------------------------
JADE = SK.JADE_ASHLAR
SCALE_TILE = SK.JADE_SCALE
GILT = SK.GILT
CARVED = SK.SERPENT_STONE
PAVING = SK.JADE_PAVING
MOSS = SK.MOSS_STONE
SILT = SK.SILT
WATER = SK.BASIN_WATER
VINE = SK.VINE
STONE = "ashlar"
RUBBLE = "rubble_stone"
ROCK = "cliff_rock"
IRON = "dark_iron"
TIMBER = "timber_grey"
TIMBER_WARM = "timber_warm"
BARK = SK.BARK
FOLIAGE = SK.FOLIAGE
AMBER = "amber_resin"
PLASTER = "lime_plaster"


# --------------------------------------------------------------- helpers
def _sheet(x0, z0, x1, z1, y, material=WATER):
    """A still water surface. Not a walk surface: you wade, you do not stand."""
    return M.box((abs(x1 - x0), 0.06, abs(z1 - z0)),
                 center=((x0 + x1) * 0.5, y, (z0 + z1) * 0.5),
                 uv_scale=0.25, material=material)


def _column_grid(x0, z0, x1, z1, spacing, height, floor_y, *, radius=0.42,
                 material=JADE, jitter=0.0, seed=0):
    """A regular forest of columns, merged into one mesh.

    Merged rather than added one at a time because a cistern is a hundred of
    them and each `add` is a separate part in the export.
    """
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    parts = []
    x = x0
    while x <= x1 + 1e-6:
        z = z0
        while z <= z1 + 1e-6:
            dx = float(rng.uniform(-jitter, jitter)) if jitter else 0.0
            dz = float(rng.uniform(-jitter, jitter)) if jitter else 0.0
            parts.append(S.column(height, radius=radius, material=material)
                         .translate(x + dx, floor_y, z + dz))
            z += spacing
        x += spacing
    return M.merge(parts, material)


def _stair_flight(x, z, axis, length, y0, y1, width, steps, material=PAVING):
    """A straight flight of treads, walkable, climbing along one axis."""
    out = S.MeshGroup()
    rise = (y1 - y0) / steps
    run = length / steps
    for i in range(steps):
        y = y0 + rise * (i + 1)
        offset = run * (i + 0.5)
        if axis == "x":
            out.add_walk(M.box((run, 0.30, width), center=(x + offset, y - 0.15, z),
                               uv_scale=0.5, material=material))
        else:
            out.add_walk(M.box((width, 0.30, run), center=(x, y - 0.15, z + offset),
                               uv_scale=0.5, material=material))
    return out


def _landing(x0, z0, x1, z1, y, material=PAVING):
    out = S.MeshGroup()
    out.add_walk(M.box((abs(x1 - x0), 0.30, abs(z1 - z0)),
                       center=((x0 + x1) * 0.5, y - 0.15, (z0 + z1) * 0.5),
                       uv_scale=0.5, material=material))
    return out


def _link(it, ident, a, b, width, y0, y1, height, steps, *,
          floor_mat=PAVING, wall_mat=JADE, ceil_mat=JADE, seed=0):
    """Add a passage and record it, the way the toolkit's examples do."""
    it.group.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                         floor_mat=floor_mat, wall_mat=wall_mat,
                         ceil_mat=ceil_mat, steps=steps, seed=seed))
    it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                        "z0": min(a[1], b[1]) - width * 0.5,
                        "x1": max(a[0], b[0]) + width * 0.5,
                        "z1": max(a[1], b[1]) + width * 0.5,
                        "floor": min(y0, y1), "height": height}
    it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                          "width": width, "height": height}


def _annular_deck(cx, cz, outer, inner, y, *, segments=24, material=PAVING):
    """A gallery with a well down the middle.

    Placement is single-layer: a solid deck spanning a room's footprint grounds
    every actor in the room on the deck instead of the floor, including the
    arrival spawn. A ring leaves the middle clear, which is where these rooms
    want their light shaft or their stair anyway.
    """
    out = S.MeshGroup()
    for i in range(segments):
        a0 = 2.0 * math.pi * i / segments
        a1 = 2.0 * math.pi * (i + 1) / segments
        mid = (a0 + a1) * 0.5
        radius = (outer + inner) * 0.5
        width = outer - inner
        chord = 2.0 * outer * math.sin((a1 - a0) * 0.5) * 1.08
        plank = M.box((chord, 0.30, width),
                      center=(0.0, y - 0.15, 0.0), uv_scale=0.5,
                      material=material)
        plank.transform(M.rotation_y(-mid))
        plank.translate(cx + math.cos(mid) * radius, 0.0,
                        cz + math.sin(mid) * radius)
        out.add_walk(plank)
    return out


def _serpent_relief(length, height, seed=0, material=SCALE_TILE):
    """A coiled serpent laid along a wall, as a swept tube."""
    path, radii = [], []
    steps = 30
    for i in range(steps):
        t = i / (steps - 1.0)
        path.append((-length * 0.5 + length * t,
                     math.sin(t * math.pi * 3.0) * height * 0.32, 0.0))
        radii.append(height * (0.16 - 0.05 * t))
    return M.tube(np.asarray(path), radii, segments=8, material=material)


def _shelf_bay(length=4.0, height=3.2, seed=0):
    """`ssarathi_archive_shelf`: a bay of stone shelving with scroll cases."""
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    out = S.MeshGroup()
    out.add(M.box((length, height, 0.22), center=(0.0, height * 0.5, -0.32),
                  uv_scale=0.6, material=JADE))
    for i in range(4):
        y = 0.55 + i * (height - 0.9) / 3.0
        out.add(M.box((length, 0.14, 0.62), center=(0.0, y, 0.0),
                      uv_scale=0.7, material=JADE))
        for k in range(int(rng.integers(3, 8))):
            x = float(rng.uniform(-length * 0.44, length * 0.44))
            case = M.cylinder(0.09, 0.09, float(rng.uniform(0.34, 0.52)), 8,
                              uv_scale=0.9, material=CARVED)
            case.transform(M.rotation_z(math.pi * 0.5))
            case.translate(x, y + 0.16, float(rng.uniform(-0.12, 0.12)))
            out.add(case)
            if float(rng.uniform(0, 1)) < 0.3:
                out.add(M.box((0.10, 0.05, 0.24),
                              center=(x, y + 0.10, 0.24), uv_scale=1.0,
                              material=GILT))
    for sign in (-1.0, 1.0):
        out.add(M.box((0.20, height, 0.66),
                      center=(sign * length * 0.5, height * 0.5, 0.0),
                      uv_scale=0.6, material=JADE))
    return out


# ================================================== 1. The Royal Archive
def royal_archive(seed: int = 20260910) -> Interior:
    """The Ssarathi Royal Archive, behind the Sun Vault at the temple.

    Follows the ten subjects `interiors/ssarathi_royal_archive/concept.json`
    names, in the order it names them, because its board does not decode and
    that written list is the only programme there is.

    The through-line is dryness. Everything else in this region is wet; the
    Archive was built to keep one thing out, and it is still mostly winning.
    The water entrance is knee-deep, the repository near the back has flooded,
    and the central archive at its heart is dry - so walking in is walking out
    of the water, which is the opposite of the Cistern below.
    """
    it = Interior("ssarathi_royal_archive", "The Royal Archive", "archive",
                  "sun-vault", [60.0, 13.0, -208.5], "archive-vault-door")
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    g = it.group
    flood = -1.20                      # the water line, flat throughout

    # 1. water entrance - `ssarathi_water_door`. Knee-deep, and the only
    #    daylight in the section.
    it.space("water_entrance", -7, -7, 7, 9, -1.9, 5.0, floor_mat=MOSS,
             wall_mat=JADE, ceil_mat=JADE, ceiling="vault", vault_rise=1.8,
             doors=[("south", 0.0, 3.6, 3.2), ("north", 0.0, 3.4, 3.0)])
    g.add(_sheet(-7, -7, 7, 9, flood))
    # the door itself: a sun disc set in the south wall, as the vault outside
    disc = A.sun_disc(1.9, seed=seed)
    disc.transform(M.rotation_x(math.pi * 0.5))
    disc.translate(0.0, 1.5, -6.7)
    g.add(disc)
    it.landmark("water-door", "The Water Door", "water_entrance", y_offset=1.5)

    # 2. reading hall - the first dry floor, raised out of the flood
    it.space("reading_hall", -13, 20, 13, 46, 0.35, 6.4, floor_mat=PAVING,
             wall_mat=JADE, ceil_mat=JADE, ceiling="vault", vault_rise=2.6,
             doors=[("south", 0.0, 3.4, 3.0), ("north", 0.0, 3.2, 3.0),
                    ("east", 33.0, 3.0, 2.8)])
    _link(it, "entrance_stair", (0, 9), (0, 20), 3.4, -1.9, 0.35, 3.4, 9,
          floor_mat=PAVING, seed=seed + 1)
    for z in np.arange(24.0, 43.0, 6.0):
        for sign in (-1.0, 1.0):
            table = P.table(seed=seed + int(z)) if hasattr(P, "table") else None
            if table is not None:
                g.add(table.translate(sign * 6.5, 0.35, float(z)))
    # 3. scaled mosaic - `ssarathi_scaled_floor`, laid into the reading hall
    g.add(M.box((16.0, 0.08, 16.0), center=(0.0, 0.42, 33.0), uv_scale=0.55,
                material=SCALE_TILE))
    g.add(M.lathe([[7.4, 0.0], [8.0, 0.0], [8.0, 0.10], [7.4, 0.10]], 40,
                  uv_scale=0.8, material=GILT).translate(0.0, 0.42, 33.0))
    it.landmark("scaled-mosaic", "The Scaled Mosaic", "reading_hall",
                y_offset=0.6)

    # 4. water arch - `ssarathi_water_arch`. A channel crosses the plan and an
    #    arch carries the way over it.
    it.space("arch_crossing", -9, 52, 9, 68, 0.35, 6.0, floor_mat=PAVING,
             wall_mat=JADE, ceil_mat=JADE,
             doors=[("south", 0.0, 3.2, 3.0), ("north", 0.0, 3.2, 3.0)])
    _link(it, "hall_to_arch", (0, 46), (0, 52), 3.2, 0.35, 0.35, 3.4, 0,
          floor_mat=PAVING, seed=seed + 2)
    # the channel, cut across the room, with the arch over it
    g.add(M.box((18.0, 2.6, 5.0), center=(0.0, -0.95, 60.0), uv_scale=0.4,
                material=SILT))
    g.add(_sheet(-9, 57.5, 9, 62.5, flood))
    bridge = A.arch_bridge(11.0, 4.4, rise=1.5, seed=seed + 3)
    bridge.transform(M.rotation_y(math.pi * 0.5))
    bridge.translate(0.0, 0.65, 60.0)
    g.add(bridge)
    it.landmark("water-arch", "The Water Arch", "arch_crossing", y_offset=2.0)

    # 5. archive shelves - `ssarathi_archive_shelf`, a long aisle of them
    it.space("shelf_aisle", 20, 24, 44, 60, 0.35, 5.6, floor_mat=PAVING,
             wall_mat=JADE, ceil_mat=JADE,
             doors=[("west", 33.0, 3.0, 2.8), ("north", 32.0, 3.0, 2.8)])
    _link(it, "hall_to_aisle", (13, 33), (20, 33), 3.0, 0.35, 0.35, 3.2, 0,
          floor_mat=PAVING, seed=seed + 4)
    for i, z in enumerate(np.arange(28.0, 57.0, 4.6)):
        for sign in (-1.0, 1.0):
            bay = _shelf_bay(4.0, 3.4, seed=seed + 10 + i)
            bay.rotate_y(math.pi * 0.5 if sign > 0 else -math.pi * 0.5)
            bay.translate(32.0 + sign * 8.0, 0.35, float(z))
            g.add(bay)
    it.landmark("archive-shelves", "The Long Aisle", "shelf_aisle", y_offset=1.6)

    # 6. royal statue - `ssarathi_royal_statue`, in its own apse
    it.space("statue_court", 22, 64, 42, 84, 0.35, 8.2, floor_mat=PAVING,
             wall_mat=JADE, ceil_mat=JADE, ceiling="vault", vault_rise=3.0,
             doors=[("south", 32.0, 3.0, 2.8), ("west", 74.0, 3.0, 2.8)])
    _link(it, "aisle_to_statue", (32, 60), (32, 64), 3.0, 0.35, 0.35, 3.2, 0,
          floor_mat=PAVING, seed=seed + 5)
    cx, cz = it.centre("statue_court")
    g.add(M.box((5.0, 1.1, 5.0), center=(cx, 0.90, cz), uv_scale=0.5,
                material=CARVED))
    king = S.statue(height=4.6, seed=seed + 6, plinth_height=0.0)
    king.translate(cx, 1.45, cz)
    g.add(king)
    crown = A.sun_disc(1.3, seed=seed + 7)
    crown.transform(M.rotation_x(math.pi * 0.5))
    crown.translate(cx, 6.4, cz + 0.3)
    g.add(crown)
    for sign in (-1.0, 1.0):
        col = A.serpent_column(5.6, seed=seed + 8)
        col.translate(cx + sign * 6.4, 0.35, cz)
        g.add(col)
    it.landmark("royal-statue", "The Serpent King", "statue_court", y_offset=3.0)

    # 7. vault trap - `ssarathi_vault_trap`. A narrow run with a dropped floor
    #    and the mechanism above it, between the statue court and the deep.
    it.space("trap_corridor", 2, 68, 20, 80, 0.35, 4.4, floor_mat=MOSS,
             wall_mat=JADE, ceil_mat=JADE,
             doors=[("east", 74.0, 3.0, 2.8), ("west", 74.0, 3.0, 2.8)])
    _link(it, "statue_to_trap", (20, 74), (22, 74), 3.0, 0.35, 0.35, 3.2, 0,
          floor_mat=MOSS, seed=seed + 9)
    for x in np.arange(5.0, 18.0, 3.2):
        g.add(M.box((2.4, 0.16, 8.0), center=(float(x), 0.30, 74.0),
                    uv_scale=0.7, material=IRON))
        for k in range(4):
            spike = M.cylinder(0.10, 0.0, 0.9, 6, uv_scale=0.9, material=IRON)
            spike.transform(M.rotation_x(math.pi))
            spike.translate(float(x), 4.3, 71.0 + k * 2.0)
            g.add(spike)
    it.landmark("vault-trap", "The Vault Trap", "trap_corridor", y_offset=1.4)
    it.interactives.append({
        "id": "ssarathi-archive-trap", "name": "Vault Trap Mechanism",
        "type": "mechanism", "position": [11.0, 1.4, 74.0],
        "authority": "server"})

    # 8. flooded repository - the water has got into this one
    it.space("flooded_repository", -24, 66, -4, 86, -1.9, 5.6, floor_mat=SILT,
             wall_mat=JADE, ceil_mat=JADE, ceiling="vault", vault_rise=2.2,
             doors=[("east", 74.0, 3.0, 2.8)])
    _link(it, "trap_to_repository", (2, 74), (-4, 74), 3.0, 0.35, -1.9, 3.4, 8,
          floor_mat=MOSS, seed=seed + 11)
    g.add(_sheet(-24, 66, -4, 86, flood))
    rx, rz = it.centre("flooded_repository")
    for i in range(9):
        bay = _shelf_bay(3.4, 2.8, seed=seed + 20 + i)
        bay.rotate_y(float(rng.uniform(0.0, math.pi)))
        bay.translate(rx + float(rng.uniform(-7.0, 7.0)), -1.9,
                      rz + float(rng.uniform(-8.0, 8.0)))
        g.add(bay)
    for i in range(6):
        g.add(A.rubble_heap(1.8, seed=seed + 40 + i)
              .translate(rx + float(rng.uniform(-8, 8)), -1.9,
                         rz + float(rng.uniform(-9, 9))))
    it.landmark("flooded-repository", "The Flooded Repository",
                "flooded_repository", y_offset=1.2)

    # 9. central archive - the heart, dry, and the deepest room in
    it.space("central_archive", -16, 96, 16, 128, 0.35, 9.0, floor_mat=PAVING,
             wall_mat=JADE, ceil_mat=JADE, ceiling="vault", vault_rise=3.6,
             doors=[("south", 0.0, 3.6, 3.2)])
    _link(it, "repository_to_central", (-14, 86), (0, 96), 3.4, -1.9, 0.35,
          3.6, 10, floor_mat=PAVING, seed=seed + 12)
    ax, az = it.centre("central_archive")
    # a ring gallery, annular so nothing grounds on it
    g.add(_annular_deck(ax, az, 13.0, 8.6, 4.6, segments=28, material=PAVING))
    g.add(_stair_flight(6.0, 100.0, "z", 12.0, 0.35, 4.6, 2.6, 12,
                        material=PAVING))
    for i in range(14):
        angle = 2.0 * math.pi * i / 14
        bay = _shelf_bay(3.6, 3.6, seed=seed + 60 + i)
        bay.rotate_y(-angle + math.pi * 0.5)
        bay.translate(ax + math.cos(angle) * 14.0, 0.35,
                      az + math.sin(angle) * 14.0)
        g.add(bay)
    # the reading table under the light shaft
    g.add(M.box((6.0, 0.20, 3.0), center=(ax, 1.05, az), uv_scale=0.6,
                material=CARVED))
    for sx in (-2.4, 2.4):
        for sz in (-1.1, 1.1):
            g.add(M.cylinder(0.14, 0.12, 0.95, 8, uv_scale=0.8, material=JADE)
                  .translate(ax + sx, 0.35, az + sz))
    it.landmark("central-archive", "The Central Archive", "central_archive",
                y_offset=1.8)
    it.interactives.append({
        "id": "ssarathi-archive-catalogue", "name": "The Great Catalogue",
        "type": "lectern", "position": [round(ax, 2), 1.5, round(az, 2)],
        "authority": "server"})

    # 10. material study - scale, stone and papyrus, staged on the gallery
    for i, (dx, dz, piece) in enumerate((
            (-4.0, -5.0, A.shell_boss(0.9)),
            (4.0, -5.0, A.sun_disc(1.0, seed=seed + 13)),
            (0.0, -6.4, A.stone_face(1.1, seed=seed + 14)))):
        g.add(piece.translate(ax + dx, 0.55 if i != 1 else 1.15, az + dz))
    g.add(M.box((3.0, 0.10, 1.6), center=(ax, 0.45, az - 5.6), uv_scale=0.7,
                material=SCALE_TILE))
    it.landmark("material-study", "The Study Table", "central_archive",
                y_offset=0.9)

    # serpent reliefs down the reading hall's long walls
    for sign in (-1.0, 1.0):
        relief = _serpent_relief(22.0, 2.4, seed=seed + 15)
        relief.transform(M.rotation_y(math.pi * 0.5))
        relief.translate(sign * 12.4, 3.4, 33.0)
        g.add(relief)

    lamps, placed = hanging_lamps(
        [(0.0, 3.2, 27.0), (0.0, 3.2, 39.0), (0.0, 3.0, 60.0),
         (32.0, 3.0, 34.0), (32.0, 3.0, 52.0),
         (float(cx), 4.4, float(cz)), (11.0, 2.8, 74.0),
         (float(rx), 2.4, float(rz)),
         (float(ax) - 7.0, 4.0, float(az)), (float(ax) + 7.0, 4.0, float(az)),
         (float(ax), 5.6, float(az) + 10.0)], seed=seed + 70)
    g.add(lamps)
    it.lamps = it.lamps + placed

    it.spawn_space = "water_entrance"
    it.subjects = [
        ("water entrance", "water_entrance", "knee-deep threshold, sun-disc door"),
        ("reading hall", "reading_hall", "first dry floor, vaulted"),
        ("scaled mosaic", "reading_hall", "scale-tiled floor with a gilt ring"),
        ("water arch", "arch_crossing", "arch over a cut channel"),
        ("archive shelves", "shelf_aisle", "twelve bays of stone shelving"),
        ("royal statue", "statue_court", "the Serpent King on his plinth"),
        ("vault trap", "trap_corridor", "dropped plates and a spike ceiling"),
        ("flooded repository", "flooded_repository", "shelving standing in water"),
        ("central archive", "central_archive", "domed heart, ring gallery"),
        ("scale stone papyrus materials", "central_archive",
         "shell, sun disc, carved face and a scale-tiled study table"),
    ]
    it.notes.append(
        "Built from concept.json's written subject list and the authored asset "
        "pack's names: its own concept board does not decode at all.")
    return it


# ================================================ 2. The Serpent Hatchery
def serpent_hatchery(seed: int = 20260911) -> Interior:
    """The brooding pools under the Ritual Plaza.

    `ssarathi_hatchery_pool` is in the authored interior asset pack and is not
    among the Archive's ten subjects, so a hatchery is separate intended content
    for this region. This is that.

    Deliberately the Archive's opposite: no straight line, no dressed ashlar, no
    catalogue. A coiled shaft drops into a warm cavern where the pools are cut
    as concentric terraces, and everything is scale-tiled rather than coursed.
    """
    it = Interior("ssarathi_serpent_hatchery", "The Serpent Hatchery", "sanctum",
                  "ritual-plaza", [168.0, 2.25, -112.56], "hatchery-descent")
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    g = it.group

    # the coiled descent: a spiral of landings rather than a straight stair
    it.space("descent", -8, -8, 8, 8, -2.0, 5.0, floor_mat=SCALE_TILE,
             wall_mat=SCALE_TILE, ceil_mat=JADE, ceiling="vault",
             vault_rise=1.6, doors=[("north", 0.0, 3.2, 3.0)])
    turns, steps = 1.75, 26
    radius = 5.2
    for i in range(steps):
        t = i / (steps - 1.0)
        angle = t * turns * 2.0 * math.pi
        y = -0.2 - t * 7.4
        tread = M.box((2.6, 0.30, 2.2),
                      center=(0.0, y - 0.15, 0.0), uv_scale=0.6,
                      material=SCALE_TILE)
        tread.transform(M.rotation_y(-angle))
        tread.translate(math.cos(angle) * radius, 0.0, math.sin(angle) * radius)
        g.add_walk(tread)
    # the serpent the stair coils around
    path, radii = [], []
    for i in range(34):
        t = i / 33.0
        angle = t * turns * 2.0 * math.pi
        path.append((math.cos(angle) * 1.5, -0.4 - t * 7.4,
                     math.sin(angle) * 1.5))
        radii.append(0.62 - 0.18 * t)
    g.add(M.tube(np.asarray(path), radii, segments=9, material=SCALE_TILE))

    # the brood cavern: tiered pools cut as concentric terraces
    it.space("brood_cavern", -26, 22, 26, 74, -7.8, 11.0, floor_mat=MOSS,
             wall_mat=ROCK, ceil_mat=ROCK, ceiling="vault", vault_rise=4.2,
             doors=[("south", 0.0, 4.0, 3.4)])
    _link(it, "descent_run", (0, 8), (0, 22), 3.4, -7.8, -7.8, 3.6, 0,
          floor_mat=SCALE_TILE, wall_mat=ROCK, ceil_mat=ROCK, seed=seed + 1)
    bx, bz = it.centre("brood_cavern")
    # four terraces stepping down to the middle, each a walk ring
    for i, (outer, inner, y) in enumerate(((23.0, 18.0, -7.8),
                                           (18.0, 13.0, -8.5),
                                           (13.0, 8.0, -9.2),
                                           (8.0, 3.4, -9.9))):
        g.add(_annular_deck(bx, bz, outer, inner, y, segments=30,
                            material=SCALE_TILE))
        g.add(M.lathe([[inner, 0.0], [inner, 0.55], [inner - 0.35, 0.55],
                       [inner - 0.35, 0.0]], 34, uv_scale=0.7, material=JADE)
              .translate(bx, y - 0.30, bz))
        g.add(_sheet(bx - inner + 0.4, bz - inner + 0.4,
                     bx + inner - 0.4, bz + inner - 0.4, y - 0.55))
    # the hatchery pool itself at the bottom, and its eggs
    g.add(M.lathe([[0.0, 0.0], [3.4, 0.0], [3.4, 0.9], [3.0, 0.9]], 30,
                  uv_scale=0.6, material=CARVED).translate(bx, -11.0, bz))
    g.add(_sheet(bx - 3.0, bz - 3.0, bx + 3.0, bz + 3.0, -10.3))
    for i in range(14):
        angle = float(rng.uniform(0, math.tau))
        r = float(rng.uniform(0.4, 2.4))
        egg = M.icosphere(float(rng.uniform(0.22, 0.36)), 1, material=CARVED)
        egg.scale(1.0, 1.35, 1.0)
        egg.translate(bx + math.cos(angle) * r, -10.2, bz + math.sin(angle) * r)
        g.add(egg)
    it.landmark("hatchery-pool", "The Hatchery Pool", "brood_cavern",
                y_offset=2.0)
    it.interactives.append({
        "id": "ssarathi-hatchery-pool", "name": "The Hatchery Pool",
        "type": "font", "position": [round(bx, 2), -9.8, round(bz, 2)],
        "authority": "server"})

    # serpent columns around the rim, and reliefs on the rock
    for i in range(8):
        angle = 2.0 * math.pi * i / 8
        col = A.serpent_column(6.8, seed=seed + 10 + i)
        col.translate(bx + math.cos(angle) * 21.0, -7.8,
                      bz + math.sin(angle) * 21.0)
        g.add(col)

    # the warden's cell off the cavern - the one built thing down here
    it.space("warden_cell", 30, 40, 44, 56, -7.8, 4.6, floor_mat=PAVING,
             wall_mat=JADE, ceil_mat=JADE, doors=[("west", 48.0, 2.8, 2.6)])
    _link(it, "cell_run", (26, 48), (30, 48), 2.8, -7.8, -7.8, 3.0, 0,
          floor_mat=PAVING, seed=seed + 2)
    wx, wz = it.centre("warden_cell")
    g.add(M.box((3.0, 0.18, 1.4), center=(wx, -6.9, wz), uv_scale=0.7,
                material=CARVED))
    for i in range(3):
        g.add(P.crate(seed=seed + 20 + i).translate(wx - 3.0 + i * 1.3, -7.8,
                                                    wz + 4.0))
    it.landmark("hatchery-warden", "The Warden's Cell", "warden_cell",
                y_offset=1.2)

    lamps, placed = hanging_lamps(
        [(0.0, -1.0, 0.0), (0.0, -5.0, 4.0),
         (float(bx) - 14.0, -4.4, float(bz)), (float(bx) + 14.0, -4.4, float(bz)),
         (float(bx), -4.0, float(bz) - 14.0), (float(bx), -4.0, float(bz) + 14.0),
         (float(bx), -6.0, float(bz)),
         (float(wx), -5.4, float(wz))], seed=seed + 40)
    g.add(lamps)
    it.lamps = it.lamps + placed

    it.spawn_space = "descent"
    it.subjects = [
        ("coiled descent", "descent", "a spiral stair around a stone serpent"),
        ("brood cavern", "brood_cavern", "four terraces stepping down to water"),
        ("hatchery pool", "brood_cavern", "the pool and its clutch"),
        ("warden's cell", "warden_cell", "the one dressed room down here"),
    ]
    it.notes.append(
        "Authored from the asset pack's `ssarathi_hatchery_pool`, which is "
        "Ssarathi interior content outside the Archive's ten subjects. No "
        "concept art exists for it.")
    return it


# ================================================= 3. The Drowned Cistern
def drowned_cistern(seed: int = 20260912) -> Interior:
    """What the drowned quarter is standing on.

    The counterweight to the Archive: undressed rubble, silt underfoot, columns
    standing in water, and not one gram of gold in it. Where the Archive keeps
    the water out, this is the room the water simply owns.
    """
    it = Interior("ssarathi_drowned_cistern", "The Drowned Cistern", "utility",
                  "drowned-quarter", [-102.0, -0.70, -60.0], "cistern-shaft")
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    g = it.group
    water = -3.10

    it.space("shaft_room", -6, -6, 6, 6, -0.6, 4.6, floor_mat=MOSS,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="vault", vault_rise=1.4,
             doors=[("north", 0.0, 3.0, 2.8)])
    it.space("basin", -30, 18, 30, 66, -4.2, 8.0, floor_mat=SILT,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="vault", vault_rise=3.2,
             doors=[("south", 0.0, 3.6, 3.0), ("east", 42.0, 3.2, 2.8)])
    _link(it, "cistern_stair", (0, 6), (0, 18), 3.4, -0.6, -4.2, 3.4, 14,
          floor_mat=MOSS, wall_mat=RUBBLE, ceil_mat=RUBBLE, seed=seed + 1)

    g.add(_column_grid(-25.0, 22.0, 25.0, 62.0, 5.0, 8.0, -4.2,
                       radius=0.50, material=RUBBLE, jitter=0.22,
                       seed=seed + 10))
    g.add(_sheet(-30, 18, 30, 66, water))

    # a raised walk across it, so the room is crossable rather than only wadeable
    g.add_walk(M.box((3.6, 0.35, 46.0), center=(0.0, water + 0.18, 42.0),
                     uv_scale=0.5, material=MOSS))
    for z in np.arange(22.0, 63.0, 7.0):
        # translation @ rotation, not the other way round. `transform` applies
        # `m * p`, so `rotation_y @ translation` rotates the *translated* point
        # about the origin and throws the rail tens of metres off the basin -
        # which is exactly how this section first came out 118 m wide.
        g.add(S.balustrade(7.0, height=0.85, material=RUBBLE)
              .transformed(M.translation(0.0, water + 0.34, float(z))
                           @ M.rotation_y(math.pi * 0.5)))

    # drowned columns that have gone over, and silt drifts
    for i in range(9):
        col = S.column(float(rng.uniform(3.0, 6.5)), radius=0.48,
                       material=RUBBLE)
        col.transform(M.rotation_z(float(rng.uniform(0.9, 1.5))))
        col.translate(float(rng.uniform(-24, 24)), -4.0,
                      float(rng.uniform(22, 62)))
        g.add(col)
    for i in range(10):
        g.add(A.rubble_heap(2.2, seed=seed + 30 + i)
              .translate(float(rng.uniform(-26, 26)), -4.2,
                         float(rng.uniform(20, 64))))
    it.landmark("cistern-basin", "The Cistern Basin", "basin", y_offset=2.0)

    # the sluice room: where the quarter's water was supposed to go
    it.space("sluice", 34, 34, 48, 50, -4.2, 5.0, floor_mat=MOSS,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, doors=[("west", 42.0, 3.2, 2.8)])
    _link(it, "sluice_run", (30, 42), (34, 42), 3.2, -4.2, -4.2, 3.4, 0,
          floor_mat=MOSS, wall_mat=RUBBLE, ceil_mat=RUBBLE, seed=seed + 2)
    sx, sz = it.centre("sluice")
    g.add(M.lathe([[1.5, 0.0], [1.5, 0.20], [0.3, 0.20], [0.3, 0.0]], 22,
                  uv_scale=0.7, material=IRON).translate(sx, -1.7, sz))
    for i in range(8):
        angle = 2.0 * math.pi * i / 8
        # Build the spoke at the origin, rotate it, *then* move it. Creating it
        # at its world position and rotating afterwards spins that position
        # about the map origin - the eight spokes of this gear ended up on a
        # 58 m circle and made the section 118 m wide. The same construction is
        # in crownwater/source/interiors_crownwater.py's sluice room.
        spoke = M.box((0.20, 0.46, 1.4), center=(1.05, 0.0, 0.0),
                      uv_scale=0.8, material=IRON)
        spoke.transform(M.rotation_y(-angle))
        spoke.translate(sx, -1.7, sz)
        g.add(spoke)
    g.add(M.cylinder(0.13, 0.13, 2.6, 8, uv_scale=0.8, material=IRON)
          .translate(sx, -4.2, sz))
    it.landmark("cistern-sluice", "The Sluice Gear", "sluice", y_offset=1.4)
    it.interactives.append({
        "id": "ssarathi-cistern-sluice", "name": "Cistern Sluice Gear",
        "type": "mechanism", "position": [round(sx, 2), -2.4, round(sz, 2)],
        "authority": "server"})

    lamps, placed = hanging_lamps(
        [(0.0, 1.4, 0.0), (0.0, -1.4, 26.0), (0.0, -1.4, 42.0),
         (0.0, -1.4, 58.0), (float(sx), -1.8, float(sz))], seed=seed + 50)
    g.add(lamps)
    it.lamps = it.lamps + placed

    it.spawn_space = "shaft_room"
    it.subjects = [
        ("shaft room", "shaft_room", "the way down from the drowned quarter"),
        ("basin", "basin", "columns standing in silt water, a raised walk"),
        ("sluice", "sluice", "the iron gear that was meant to drain it"),
    ]
    return it


# ================================================= 4. The Root Undercroft
def root_undercroft(seed: int = 20260913) -> Interior:
    """The chamber the strangler figs broke into, beneath the Strangled Arch.

    Older than the Archive and with no masonry order left in it: the roots came
    through the vault and are now the only thing holding the ceiling up. The one
    section whose structure is wood rather than stone, and the only one where
    daylight reaches the floor.
    """
    it = Interior("ssarathi_root_undercroft", "The Root Undercroft", "ruin",
                  "root-arch", [234.0, 3.70, 66.0], "undercroft-mouth")
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    g = it.group

    it.space("mouth", -7, -6, 7, 6, -0.5, 4.8, floor_mat=MOSS,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="open",
             doors=[("north", 0.0, 3.4, 3.0)])
    it.space("undercroft", -22, 18, 22, 54, -3.4, 8.6, floor_mat=MOSS,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 3.6, 3.2), ("east", 36.0, 3.0, 2.8)])
    _link(it, "root_stair", (0, 6), (0, 18), 3.6, -0.5, -3.4, 3.6, 10,
          floor_mat=MOSS, wall_mat=RUBBLE, ceil_mat=RUBBLE, seed=seed + 1)

    ux, uz = it.centre("undercroft")
    # the roots: falling from the vault to the floor and spreading
    for i in range(16):
        top_x = ux + float(rng.uniform(-18, 18))
        top_z = uz + float(rng.uniform(-14, 14))
        spread = float(rng.uniform(2.0, 6.0)) * (1.0 if i % 2 else -1.0)
        path, radii = [], []
        steps = 16
        for k in range(steps):
            t = k / (steps - 1.0)
            path.append((top_x + spread * t * t,
                         5.0 * (1.0 - t) - 3.3,
                         top_z + math.sin(t * 3.2 + i) * 1.1))
            radii.append(float(rng.uniform(0.30, 0.62)) * (1.0 - 0.5 * t) + 0.08)
        g.add(M.tube(np.asarray(path), radii, segments=8, material=BARK))
    # collapsed vault ribs, and the rubble they came down as
    for i in range(7):
        g.add(A.rubble_heap(2.6, seed=seed + 20 + i)
              .translate(ux + float(rng.uniform(-18, 18)), -3.4,
                         uz + float(rng.uniform(-15, 15))))
    for i in range(5):
        frag = S.ruin_fragment(seed=seed + 30 + i, scale=float(rng.uniform(0.9, 1.8)))
        frag.transform(M.rotation_z(float(rng.uniform(-0.5, 0.5))))
        frag.translate(ux + float(rng.uniform(-16, 16)), -3.4,
                       uz + float(rng.uniform(-14, 14)))
        g.add(frag)
    # the light well the roots came through, open to the sky
    g.add(M.lathe([[4.6, 0.0], [4.6, 0.6], [4.0, 0.6], [4.0, 0.0]], 26,
                  uv_scale=0.6, material=RUBBLE).translate(ux, 4.8, uz))
    it.open_to_sky.append("undercroft")
    for i in range(5):
        card = A.vine_curtain(3.0, 6.0, seed=seed + 40 + i, sheets=2)
        card.translate(ux + float(rng.uniform(-5, 5)), 4.6,
                       uz + float(rng.uniform(-5, 5)))
        g.add(card)
    it.landmark("root-vault", "The Root Vault", "undercroft", y_offset=2.4)

    # the tomb niche off the side: what the undercroft was built for
    it.space("tomb_niche", 26, 30, 40, 44, -3.4, 4.4, floor_mat=MOSS,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, doors=[("west", 36.0, 2.8, 2.6)])
    _link(it, "niche_run", (22, 36), (26, 36), 2.8, -3.4, -3.4, 3.0, 0,
          floor_mat=MOSS, wall_mat=RUBBLE, ceil_mat=RUBBLE, seed=seed + 2)
    tx, tz = it.centre("tomb_niche")
    g.add(M.box((3.4, 1.0, 1.8), center=(tx, -2.9, tz), uv_scale=0.5,
                material=CARVED))
    g.add(A.stone_face(1.0, seed=seed + 50).translate(tx, -2.4, tz + 0.9))
    for sign in (-1.0, 1.0):
        g.add(M.box((0.3, 2.2, 0.3), center=(tx + sign * 2.2, -2.3, tz),
                    uv_scale=0.7, material=RUBBLE))
    it.landmark("root-tomb", "The Root Tomb", "tomb_niche", y_offset=1.2)

    lamps, placed = hanging_lamps(
        [(0.0, 1.6, 0.0), (float(ux) - 11.0, -0.4, float(uz)),
         (float(ux) + 11.0, -0.4, float(uz)),
         (float(ux), -0.4, float(uz) + 12.0),
         (float(tx), -1.4, float(tz))], seed=seed + 60)
    g.add(lamps)
    it.lamps = it.lamps + placed

    it.spawn_space = "mouth"
    it.subjects = [
        ("mouth", "mouth", "the broken way in under the arch"),
        ("undercroft", "undercroft", "roots holding a collapsed vault up"),
        ("tomb niche", "tomb_niche", "the sarcophagus it was built for"),
    ]
    return it


ALL = {
    "royal_archive": royal_archive,
    "serpent_hatchery": serpent_hatchery,
    "drowned_cistern": drowned_cistern,
    "root_undercroft": root_undercroft,
}


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR


def tenth_mouth(seed: int = 20260905) -> Interior:
    """The shrine of the channel that no longer exists: the tenth mouth."""
    return SR.shrine("ssarathi_tenth_mouth", "The Tenth Mouth Shrine", "lily-court",
                     [-48.0, 2.0, -118.1], "tenth-mouth-door",
                     palette={"floor": STONE, "wall": STONE, "ceil": STONE,
                              "accent": "verdant_carved_jade", "water": "water_deep",
                              "metal": IRON},
                     seed=seed, style="water")


def water_gate_undercut(seed: int = 20260906) -> Interior:
    """Under the south water gate, where the crocodiles lie up."""
    return SR.cave("ssarathi_water_gate_undercut", "The Water Gate Undercut",
                   "south-water-gate", [60.0, 2.1, 48.0], "water-gate-undercut-mouth",
                   palette={"floor": "packed_earth", "rock": ROCK, "water": "water_deep",
                            "bone": "pale_ashlar"},
                   seed=seed, den="Saltmarsh Crocodile", pool=True)


def lineage_house(seed: int = 20260907) -> Interior:
    """Lineage Reader Ssiran-Ta's house, by the Serpent Pair."""
    return SR.cottage("ssarathi_lineage_house", "The Lineage Reader's House", "serpent-gate",
                      [51.0, 1.9, -18.0], "lineage-house-door",
                      palette={"floor": TIMBER_WARM, "wall": PLASTER, "roof": TIMBER,
                               "timber": TIMBER, "stone": RUBBLE, "cloth": "woven_cloth",
                               "iron": IRON},
                      seed=seed, trade="workshop")


ALL.update({"tenth_mouth": tenth_mouth, "water_gate_undercut": water_gate_undercut,
            "lineage_house": lineage_house})
