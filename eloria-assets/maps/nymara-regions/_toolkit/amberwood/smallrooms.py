"""Small interiors, for the places a region has more of than it has time for.

A region's four authored insides are its set pieces. Between them a living
region also has the ordinary rooms: a cave a hunter shelters in, a cottage
somebody still keeps, a shrine cut into a bank. These three generators build
one of each from the shared interior kit, sized and dressed by a handful of
parameters, so a region can add a section to its composed insides map with a
dozen lines and a palette rather than three hundred lines of authoring.

They follow the two rules every interior here follows: every standable
surface goes in through `add_walk` (the `chamber` and `passage` helpers do
that), and a room is a closed box - the client cuts the lid away, so the lid
has to be there to cut.

    cave(ident, name, anchor_landmark, anchor_position, destination_spawn,
         palette={"floor": "packed_earth", "rock": "cliff_rock", ...}, seed=...)
"""
from __future__ import annotations

import math

import numpy as np

from . import architecture as A, crystalcraft as CC, mesh as M, props as P
from . import stonework as S, trees as TREES
from .interiors import Interior, WALL_T, hanging_lamps, passage


def _palette(base: dict | None, **defaults) -> dict:
    out = dict(defaults)
    if base:
        out.update(base)
    return out


def _link(it: Interior, ident: str, a, b, width, y0, y1, height, *, floor, wall, ceil,
          steps: int, seed: int) -> None:
    it.group.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                         floor_mat=floor, wall_mat=wall, ceil_mat=ceil, steps=steps,
                         seed=seed))
    it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5, "z0": min(a[1], b[1]) - width * 0.5,
                        "x1": max(a[0], b[0]) + width * 0.5, "z1": max(a[1], b[1]) + width * 0.5,
                        "floor": min(y0, y1), "height": height}
    it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1, "width": width, "height": height}


# ------------------------------------------------------------------- cave
def cave(ident: str, name: str, anchor_landmark: str, anchor_position, destination_spawn: str,
         *, palette: dict | None = None, seed: int = 0, depth: float = 6.0,
         crystal: bool = False, pool: bool = True, den: str = "") -> Interior:
    """A mouth, a throat down, and a chamber: the hollow behind a cliff face.

    `crystal` lines the chamber the way the Barrens' geodes are lined;
    `pool` puts still water at the low end; `den` names a creature the
    chamber is a lair of, and puts its bones and a creature zone there.
    """
    pal = _palette(palette, floor="packed_earth", rock="cliff_rock", water="water_deep",
                   crystal="amethyst_crystal", bone="pale_ashlar")
    it = Interior(ident, name, "cave", anchor_landmark, anchor_position, destination_spawn)
    rng = np.random.default_rng(seed)
    g = it.group
    rock = pal["rock"]

    it.space("mouth", -6, -6, 6, 6, 0.0, 5.4, floor_mat=pal["floor"], wall_mat=rock,
             ceil_mat=rock, ceiling="vault", vault_rise=2.2, doors=[("north", 0.0, 4.8, 3.4)])
    it.space("throat", -5, 16, 5, 26, -depth * 0.6, 5.6, floor_mat=pal["floor"], wall_mat=rock,
             ceil_mat=rock, ceiling="vault", vault_rise=2.6,
             doors=[("south", 0.0, 4.8, 3.4), ("north", 0.0, 4.6, 3.2)])
    it.space("chamber", -16, 36, 16, 66, -depth, 11.0, floor_mat=pal["floor"], wall_mat=rock,
             ceil_mat=rock, ceiling="vault", vault_rise=5.5, doors=[("south", 0.0, 4.6, 3.2)])
    _link(it, "descent", (0, 6), (0, 16), 4.8, 0.0, -depth * 0.6, 4.4,
          floor=pal["floor"], wall=rock, ceil=rock, steps=10, seed=seed + 1)
    _link(it, "gullet", (0, 26), (0, 36), 4.6, -depth * 0.6, -depth, 4.4,
          floor=pal["floor"], wall=rock, ceil=rock, steps=8, seed=seed + 2)

    # rockfall at the mouth and along the walls
    for index in range(6):
        g.add(P.boulder(radius=float(rng.uniform(0.5, 1.2)), seed=seed + index, material=rock)
              .translate(float(rng.uniform(-5.0, 5.0)), 0.0, float(rng.uniform(-4.5, 2.5))))
    cx, cz = it.centre("chamber")
    for index in range(14):
        angle = float(rng.uniform(0.0, math.tau))
        radial = float(rng.uniform(0.7, 1.0))
        g.add(P.boulder(radius=float(rng.uniform(0.6, 1.5)), seed=seed + 20 + index, material=rock)
              .translate(cx + math.cos(angle) * radial * 14.5, -depth,
                         cz + math.sin(angle) * radial * 13.5))
    if crystal:
        for index in range(28):
            angle = float(rng.uniform(0.0, math.tau))
            radial = float(rng.uniform(0.6, 1.0)) ** 0.5
            lift = float(rng.uniform(0.0, 1.0))
            shard = CC.shard(float(rng.uniform(1.2, 3.4)), float(rng.uniform(0.25, 0.5)),
                             faces=int(rng.integers(5, 8)), seed=seed + 40 + index,
                             material=pal["crystal"])
            shard.rotate_z(math.pi * (0.2 + 0.5 * lift))
            shard.rotate_y(angle + math.pi)
            g.add(shard.translate(cx + math.cos(angle) * radial * 14.0, -depth + lift * 7.0,
                                  cz + math.sin(angle) * radial * 13.0))
        g.add(CC.cluster(count=7, radius=2.2, height=4.4, seed=seed + 70,
                         material=pal["crystal"]).translate(cx, -depth, cz + 6.0))
    if pool:
        g.add(M.box((11.0, 0.06, 8.0), center=(cx - 3.0, -depth + 0.06, cz + 9.0), uv_scale=0.25,
                    material=pal["water"]))
    if den:
        for index in range(5):
            bone = M.cylinder(0.08, 0.06, float(rng.uniform(0.9, 1.8)), 6, uv_scale=1.0,
                              material=pal["bone"])
            bone.rotate_z(math.pi * 0.5).rotate_y(float(rng.uniform(0.0, math.tau)))
            g.add(bone.translate(cx + float(rng.uniform(-6, 6)), -depth + 0.08,
                                 cz - 6.0 + float(rng.uniform(-4, 4))))
        it.npc_markers.append({"id": f"{ident}-den", "name": den, "kind": "creature-zone",
                               "position": [round(cx, 2), round(-depth, 2), round(cz, 2)],
                               "radius": 12.0})
    lamps, placed = hanging_lamps([(0.0, 3.2, -2.0), (0.0, -depth * 0.6 + 3.4, 21.0),
                                   (-8.0, -depth + 4.2, cz), (8.0, -depth + 4.2, cz)], seed=seed)
    g.add(lamps)
    it.lamps = placed
    it.spawn_space = "mouth"
    it.subjects = [("concept-01", "cave mouth from within", "mouth"),
                   ("concept-02", "the descent", "descent"),
                   ("concept-03", "the chamber", "chamber")]
    it.landmark(f"{ident}-chamber", name, "chamber", 2.0)
    it.environment = {"sky": "none",
                      "ambient": {"colour": [0.12, 0.11, 0.13], "energy": 0.5},
                      "fog": {"enabled": True, "colour": [0.05, 0.05, 0.06], "begin": 16.0, "end": 52.0}}
    it.notes = ["Built from the shared small-room kit: mouth, throat and chamber, dressed "
                "for the region above it."]
    return it


# ---------------------------------------------------------------- cottage
def cottage(ident: str, name: str, anchor_landmark: str, anchor_position, destination_spawn: str,
            *, palette: dict | None = None, seed: int = 0, trade: str = "hearth",
            loft: bool = True) -> Interior:
    """One room and a back room, with a hearth, a bed, and the tools of a trade.

    `trade` picks the dressing: "hearth" (a home), "workshop" (a bench and
    stores), "chandlery" (barrels, crates, rope), "still" (an alchemist's
    room). A cottage is the ordinary building a region has dozens of on its
    surface and, until now, none of inside.
    """
    pal = _palette(palette, floor="timber_warm", wall="lime_plaster", roof="timber_dark",
                   timber="timber_dark", stone="rubble_stone", cloth="woven_cloth",
                   iron="dark_iron")
    it = Interior(ident, name, "dwelling", anchor_landmark, anchor_position, destination_spawn)
    rng = np.random.default_rng(seed)
    g = it.group
    it.space("hall", -5, -4, 5, 6, 0.0, 3.4, floor_mat=pal["floor"], wall_mat=pal["wall"],
             ceil_mat=pal["roof"], ceiling="flat", doors=[("south", 0.0, 1.4, 2.2),
                                                         ("north", 2.0, 1.2, 2.1)])
    it.space("back", -3, 6.55, 5, 12, 0.0, 3.0, floor_mat=pal["floor"], wall_mat=pal["wall"],
             ceil_mat=pal["roof"], ceiling="flat", doors=[("south", 2.0, 1.2, 2.1)])
    # the hearth on the west wall, a chimney breast and a fire
    g.add(M.box((1.8, 3.2, 0.9), center=(-4.55, 1.6, 1.0), uv_scale=0.6, material=pal["stone"]))
    g.add(M.box((1.2, 1.1, 0.5), center=(-4.35, 0.55, 1.0), uv_scale=0.6, material="charred_timber")
          if False else M.box((1.2, 0.12, 0.7), center=(-4.2, 0.06, 1.0), uv_scale=0.6,
                              material=pal["stone"]))
    g.add(P.brazier(seed=seed).translate(-3.9, 0.0, 1.0))
    # a bed, a table and two stools, a chest
    g.add(M.box((1.0, 0.5, 2.0), center=(3.9, 0.25, 4.6), uv_scale=0.8, material=pal["timber"]))
    g.add(M.box((1.0, 0.18, 2.0), center=(3.9, 0.58, 4.6), uv_scale=0.8, material=pal["cloth"]))
    g.add(M.box((1.6, 0.08, 0.9), center=(0.6, 0.78, 0.6), uv_scale=0.8, material=pal["timber"]))
    for sx, sz in ((-0.1, 0.6), (1.3, 0.6)):
        g.add(M.box((0.08, 0.78, 0.08), center=(sx, 0.39, sz - 0.35), uv_scale=1.0, material=pal["timber"]))
        g.add(M.box((0.08, 0.78, 0.08), center=(sx, 0.39, sz + 0.35), uv_scale=1.0, material=pal["timber"]))
    for sz in (-0.4, 1.6):
        g.add(M.cylinder(0.22, 0.2, 0.45, 8, uv_scale=1.0, material=pal["timber"]).translate(0.6, 0.0, sz))
    g.add(P.crate(size=0.7, seed=seed + 1, material=pal["timber"]).translate(-3.6, 0.0, 4.9))
    if loft:
        # a half loft over the back of the hall, reached by a ladder: scenery
        g.add(M.box((9.4, 0.16, 3.4), center=(0.0, 2.3, 4.3), uv_scale=0.6, material=pal["timber"]))
        for index in range(7):
            g.add(M.box((0.9, 0.05, 0.06), center=(-4.2, 0.35 + index * 0.32, 2.5 + index * 0.02),
                        uv_scale=1.0, material=pal["timber"]))
    # the trade
    bx, bz = it.centre("back")
    if trade == "workshop":
        g.add(P.workbench(length=2.2, seed=seed + 2, tools=True).translate(bx, 0.0, bz + 1.4))
        g.add(P.log_pile(length=2.2, rows=2, per_row=4, seed=seed + 3).translate(bx - 2.4, 0.0, bz - 1.2))
        g.add(P.barrel(seed=seed + 4).translate(bx + 2.8, 0.0, bz - 1.4))
    elif trade == "chandlery":
        for index in range(4):
            g.add(P.barrel(seed=seed + 10 + index).translate(bx - 2.6 + index * 0.9, 0.0, bz + 1.6))
        g.add(P.crate(seed=seed + 15).translate(bx + 2.4, 0.0, bz - 1.2))
        g.add(P.crate(size=0.5, seed=seed + 16).translate(bx + 2.4, 0.57, bz - 1.2))
        g.add(P.sack(seed=seed + 17).translate(bx + 1.2, 0.0, bz - 1.4))
        g.add(P.sack(seed=seed + 18).translate(bx + 1.7, 0.0, bz - 0.8))
    elif trade == "still":
        g.add(P.amber_workstation(seed=seed + 20).translate(bx, 0.0, bz + 0.8))
        for index in range(3):
            g.add(M.box((0.34, 0.9, 0.34), center=(bx - 2.8 + index * 0.6, 0.45, bz - 1.6),
                        uv_scale=1.0, material="amber_glass"))
    else:
        g.add(P.basket(seed=seed + 30).translate(bx - 1.6, 0.0, bz + 1.4))
        g.add(P.sack(seed=seed + 31).translate(bx + 1.4, 0.0, bz + 1.5))
        g.add(P.firewood(radius=0.6, seed=seed + 32).translate(bx + 2.4, 0.0, bz - 1.4))
    lamps, placed = hanging_lamps([(0.0, 2.9, 1.0), (bx, 2.6, bz)], seed=seed)
    g.add(lamps)
    it.lamps = placed
    it.spawn_space = "hall"
    it.subjects = [("concept-01", "the hall and hearth", "hall"),
                   ("concept-02", f"the {trade}", "back")]
    it.landmark(f"{ident}-hearth", name, "hall", 1.4)
    it.environment = {"sky": "none",
                      "ambient": {"colour": [0.24, 0.19, 0.14], "energy": 0.6},
                      "fog": {"enabled": False}}
    it.notes = ["Built from the shared small-room kit: a hall with a hearth and a back room "
                f"for its trade ({trade})."]
    return it


# ------------------------------------------------------------------ shrine
def shrine(ident: str, name: str, anchor_landmark: str, anchor_position, destination_spawn: str,
           *, palette: dict | None = None, seed: int = 0, style: str = "stone",
           crypt: bool = False) -> Interior:
    """A cut sanctuary: a porch, a nave, and the thing it was cut for.

    `style` is who cut it - "stone" (Stoneborn benches and a carved slab),
    "lantern" (a Luminous register-shrine, lamps and a ledger stand),
    "water" (a Ssarathi basin), "crystal" (a Glasswarden resonance cell),
    "root" (a Mycelari grove chamber). `crypt` adds a lower vault of niches.
    """
    pal = _palette(palette, floor="cobble_paving", wall="ashlar", ceil="ashlar",
                   accent="carved_wood", crystal="amethyst_crystal", water="water_deep",
                   metal="dark_iron", cloth="woven_cloth", earth="packed_earth",
                   bark="bark_dark", amber="amber_resin")
    it = Interior(ident, name, "shrine", anchor_landmark, anchor_position, destination_spawn)
    rng = np.random.default_rng(seed)
    g = it.group
    it.space("porch", -4, -4, 4, 4, 0.0, 4.2, floor_mat=pal["floor"], wall_mat=pal["wall"],
             ceil_mat=pal["ceil"], ceiling="vault", vault_rise=1.8,
             doors=[("north", 0.0, 3.2, 2.8), ("south", 0.0, 2.6, 2.6)])
    it.space("nave", -8, 12, 8, 32, -1.2, 7.0, floor_mat=pal["floor"], wall_mat=pal["wall"],
             ceil_mat=pal["ceil"], ceiling="vault", vault_rise=3.2,
             doors=[("south", 0.0, 3.2, 2.8)] + ([("east", 24.0, 2.6, 2.4)] if crypt else []))
    _link(it, "aisle", (0, 4), (0, 12), 3.2, 0.0, -1.2, 3.6, floor=pal["floor"], wall=pal["wall"],
          ceil=pal["ceil"], steps=4, seed=seed + 1)
    nx, nz = it.centre("nave")
    # columns either side of the nave
    for index in range(4):
        z = 14.5 + index * 4.6
        for sx in (-1, 1):
            g.add(S.column(height=5.6, radius=0.36, material=pal["wall"]).translate(sx * 6.4, -1.2, z))
    # the sanctuary at the far end, by style
    if style == "lantern":
        g.add(M.box((3.2, 1.0, 1.2), center=(nx, -0.7, 29.0), uv_scale=0.8, material=pal["wall"]))
        g.add(M.box((1.2, 0.9, 0.8), center=(nx, 0.25, 29.0), uv_scale=0.8, material=pal["accent"]))
        for sx in (-2.4, 2.4):
            g.add(S.lamp_post(height=2.6, material=pal["metal"]).translate(nx + sx, -1.2, 27.5))
    elif style == "water":
        g.add(M.lathe([[2.6, 0.0], [2.6, 0.7], [2.2, 0.75], [2.2, 0.15], [0.0, 0.15]], 20,
                      material=pal["wall"]).translate(nx, -1.2, 26.0))
        g.add(M.cylinder(2.15, 2.15, 0.06, 20, uv_scale=0.3, material=pal["water"])
              .translate(nx, -0.55, 26.0))
        g.add(S.statue(height=2.6, seed=seed).translate(nx, -1.2, 30.2))
    elif style == "crystal":
        g.add(M.cylinder(2.4, 2.6, 0.5, 16, uv_scale=0.6, material=pal["wall"]).translate(nx, -1.2, 27.0))
        g.add(CC.cluster(count=8, radius=1.8, height=4.6, seed=seed + 5,
                         material=pal["crystal"]).translate(nx, -0.7, 27.0))
        for index in range(6):
            angle = math.tau * index / 6.0
            g.add(CC.shard(1.4, 0.24, faces=6, seed=seed + 10 + index, material=pal["crystal"])
                  .translate(nx + math.cos(angle) * 5.0, -1.2, 24.0 + math.sin(angle) * 5.0))
    elif style == "root":
        wood, _ = TREES.build_tree("great_oak", seed=seed + 7, detail="mid")
        g.add(wood.with_material(pal["bark"]).scale(0.42, 0.34, 0.42).translate(nx, -1.2, 27.0))
        for index in range(5):
            g.add(P.mushroom_cluster(seed=seed + 20 + index, count=5, material=pal["amber"])
                  .translate(nx + float(rng.uniform(-5, 5)), -1.2, 20.0 + float(rng.uniform(0, 10))))
    else:  # stone
        g.add(M.box((3.4, 0.9, 1.4), center=(nx, -0.75, 29.0), uv_scale=0.8, material=pal["wall"]))
        g.add(M.box((2.6, 2.4, 0.5), center=(nx, 0.9, 30.6), uv_scale=0.8, material=pal["accent"]))
        for sx in (-3.6, 3.6):
            g.add(M.box((0.6, 0.45, 8.0), center=(nx + sx, -0.98, 20.0), uv_scale=0.8, material=pal["wall"]))
    # votive braziers by the door
    for sx in (-2.2, 2.2):
        g.add(P.brazier(seed=seed + 40).translate(sx, -1.2, 13.5))
    lamp_points = [(0.0, 3.4, 0.0), (-5.0, 3.6, 16.0), (5.0, 3.6, 22.0), (0.0, 4.0, 29.0)]
    if crypt:
        it.space("crypt", 12, 20, 24, 30, -4.0, 4.0, floor_mat=pal["earth"], wall_mat=pal["wall"],
                 ceil_mat=pal["ceil"], ceiling="vault", vault_rise=1.6, doors=[("west", 24.0, 2.6, 2.4)])
        _link(it, "crypt-stair", (8, 24), (12, 24), 2.6, -1.2, -4.0, 3.2, floor=pal["floor"],
              wall=pal["wall"], ceil=pal["ceil"], steps=6, seed=seed + 2)
        cx, cz = it.centre("crypt")
        for index in range(6):
            side = -1 if index % 2 else 1
            g.add(M.box((0.9, 0.5, 2.0), center=(cx + side * 4.6, -3.75, cz - 3.5 + (index // 2) * 3.4),
                        uv_scale=0.8, material=pal["wall"]))
        lamp_points.append((cx, -0.8, cz))
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed
    it.spawn_space = "porch"
    it.subjects = [("concept-01", "the porch", "porch"), ("concept-02", "the nave", "nave"),
                   ("concept-03", "the sanctuary", "nave")]
    it.landmark(f"{ident}-sanctuary", name, "nave", 1.6)
    it.environment = {"sky": "none",
                      "ambient": {"colour": [0.16, 0.15, 0.17], "energy": 0.55},
                      "fog": {"enabled": True, "colour": [0.06, 0.06, 0.07], "begin": 20.0, "end": 60.0}}
    it.notes = [f"Built from the shared small-room kit: a cut sanctuary in the {style} manner"
                + (", with a crypt of niches below." if crypt else ".")]
    return it
