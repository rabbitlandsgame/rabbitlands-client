"""The rooms a gauntlet is made of.

Every room is built in its own frame: it spans `x0..x1` across and `z0..z1`
along the road, the party comes in through a door on the south wall and
leaves through a door on the north wall (a fork leaves through two). The
composer in `build.py` chains them along +Z with a barred passage between
each pair, so a room never needs to know where it stands on the map.

A room reports what the server needs: the floor rectangle it fights in (its
`space`), a lattice of spawn tiles inside it, and any furniture it carries
(plaques, a bonus node, the cache, the waystones). The dressing is the
region's: the palette says what it is built of and `kit` says what grows in
it.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import crystalcraft as CC
from amberwood import interiors as I
from amberwood import junglecraft as JC
from amberwood import mesh as M
from amberwood import moorcraft as MOOR
from amberwood import props as P
from amberwood import stonework as S
from amberwood import trees as TREES
from amberwood.interiors import Interior
from amberwood.smallrooms import _link as _boxed_link
from secretrooms import _brazier, _node, _plaque

WAY_WIDTH = 3.6          # passage width
WAY_HEIGHT = 3.8
DOOR = (3.6, 3.0)        # width, head


def _link(it, ident, a, b, width, y0, y1, height, *, canyon=False, **kw):
    if not canyon:
        return _boxed_link(it, ident, a, b, width, y0, y1, height, **kw)
    from amberwood import canyoncraft as C
    it.group.add(C.cut_passage(a,b,width,y0,y1,max(height,4.8),
                               floor=kw["floor"],rock=kw["wall"],seed=kw["seed"]))
    it.spaces[ident] = {"x0":min(a[0],b[0])-width/2,"z0":min(a[1],b[1])-width/2,
                        "x1":max(a[0],b[0])+width/2,"z1":max(a[1],b[1])+width/2,
                        "floor":min(y0,y1),"height":height}
    it.passages[ident] = {"a":a,"b":b,"y0":y0,"y1":y1,"width":width,"height":height}


# ---------------------------------------------------------------- dressing
def dress(it: Interior, kit: str, pal: dict, x0, z0, x1, z1, floor_y, seed: int, count: int = 6):
    """Scatter the region's growth along the walls of a room, never in the
    middle where the fight is and never in the door lanes."""
    if kit in ("forest_haul", "ice_mine", "temple_procession", "barrow_visitation", "drowned_customs", "canyon_wash"):
        return  # themed layouts author useful bays instead of scattered growth
    rng = np.random.default_rng(seed)
    width, depth = x1 - x0, z1 - z0
    placed = 0
    tries = 0
    while placed < count and tries < count * 6:
        tries += 1
        side = rng.integers(0, 2)
        x = x0 + 1.4 if side == 0 else x1 - 1.4
        x += float(rng.uniform(-0.4, 0.4))
        z = z0 + 2.5 + float(rng.uniform(0.0, max(0.5, depth - 5.0)))
        if abs(x - (x0 + x1) * 0.5) < 2.4:
            continue
        k = seed * 7 + placed
        if kit == "forest":
            piece = (TREES.stump(radius=float(rng.uniform(0.5, 0.9)), height=float(rng.uniform(1.0, 2.2)), seed=k,
                                 material=pal.get("bark", "bark_dark")) if placed % 2 == 0
                     else P.mushroom_cluster(seed=k, count=5, material=pal["node"]))
        elif kit == "ice":
            piece = (CC.cluster(count=4, radius=0.9, height=float(rng.uniform(1.4, 2.6)), seed=k, material=pal["crystal"])
                     if placed % 2 == 0 else P.boulder(radius=float(rng.uniform(0.6, 1.1)), seed=k, material=pal["rock"]))
        elif kit == "jungle":
            piece = (JC.frond_cluster(radius=1.3, count=6, seed=k, material=pal["node"]) if placed % 3 != 2
                     else JC.shrine_post(height=2.4, seed=k))
        elif kit == "moor":
            piece = (MOOR.menhir(height=float(rng.uniform(1.6, 2.6)), seed=k, material=pal["stone"]) if placed % 2 == 0
                     else MOOR.candle_cluster(count=5, radius=0.5, seed=k))
        elif kit == "drowned":
            piece = (P.barrel(seed=k, material=pal["timber"]) if placed % 3 == 0
                     else P.crate(size=0.8, seed=k, material=pal["timber"]) if placed % 3 == 1
                     else M.cylinder(0.45, 0.45, 3.6, 10, uv_scale=1.0, material=pal["stone"]))
        elif kit == "canyon":
            piece = (P.boulder(radius=float(rng.uniform(0.6, 1.2)), seed=k, material=pal["rock"]) if placed % 2 == 0
                     else P.sack(seed=k))
        elif kit == "crystal":
            piece = (CC.cluster(count=5, radius=1.0, height=float(rng.uniform(1.6, 3.0)), seed=k, material=pal["crystal"])
                     if placed % 2 == 0 else CC.shard(height=float(rng.uniform(1.4, 2.4)), radius=0.35, seed=k,
                                                     material=pal["crystal"], tilt=0.2))
        else:   # reed
            piece = (M.box((0.9, 1.6, 0.9), center=(0.0, 0.8, 0.0), uv_scale=1.0, material="thatch_reed")
                     if placed % 2 == 0 else P.basket(seed=k))
        it.group.add(piece.translate(x, floor_y, z))
        placed += 1


def lattice(x0, z0, x1, z1, floor_y, *, pitch: float = 3.0, inset: float = 4.0, back: float = 3.0):
    """Spawn positions in ranks across the room, from `inset` metres past the
    entrance to `back` metres short of the exit."""
    out = []
    z = z0 + inset
    while z <= z1 - back:
        x = x0 + 2.4
        while x <= x1 - 2.4:
            out.append([round(x, 2), round(floor_y, 2), round(z, 2)])
            x += pitch
        z += pitch
    return out


def _doors(x_in, x_out, extra=()):
    doors = []
    if x_in is not None:
        doors.append(("south", x_in, DOOR[0], DOOR[1]))
    if x_out is not None:
        doors.append(("north", x_out, DOOR[0], DOOR[1]))
    doors.extend(extra)
    return doors


class Built:
    """What one room hands back to the composer."""

    def __init__(self, key: str, z_end: float, x_out, floor_out: float, spawns: list, bounds: tuple):
        self.key = key
        self.z_end = z_end
        self.x_out = x_out
        self.floor_out = floor_out
        self.spawns = spawns
        self.bounds = bounds      # x0, z0, x1, z1 of the fight floor


# ---------------------------------------------------------------- rooms
def staging(it: Interior, pal: dict, kit: str, z0: float, x_in: float, seed: int, *, lore=()) -> Built:
    w, d = 8.0, 14.0
    _room_(it, "staging", -w, z0, w, z0 + d, 0.0, 5.2, pal, doors=_doors(None, 0.0), ceiling="vault",
           vault_rise=2.2)
    _brazier(it, -w + 2.0, 0.0, z0 + 3.0, seed)
    _brazier(it, w - 2.0, 0.0, z0 + 3.0, seed + 1)
    for index, (title, text) in enumerate(lore):
        _plaque(it, f"plaque-staging-{index}", title, text, -w + 1.2 + index * 2.0, 0.0, z0 + d - 1.4,
                material=pal["timber"])
    # the waystone home stands by the entrance wall: the way out, any time
    it.group.add(MOOR.menhir(height=2.4, seed=seed + 3, material=pal["stone"]).translate(w - 2.2, 0.0, z0 + d - 3.0))
    it.interactives.append({"id": "exit-staging", "kind": "waystone", "target": "home",
                            "label": "Waystone", "text": "The waystone home. Using it counts you out of the run.",
                            "position": [round(w - 2.2, 2), 1.0, round(z0 + d - 3.0, 2)]})
    dress(it, kit, pal, -w, z0, w, z0 + d, 0.0, seed, count=4)
    return Built("staging", z0 + d, 0.0, 0.0, [], (-w, z0, w, z0 + d))


def hall(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
         pressure: float = 1.0) -> Built:
    w = 9.0 + 2.0 * pressure
    d = 20.0
    x_out = x_in + (3.0 if seed % 2 else -3.0)
    _room_(it, key, x_in - w, z0, x_in + w, z0 + d, floor, 5.6, pal, doors=_doors(x_in, x_out), ceiling="vault",
           vault_rise=2.6)
    for px in (() if kit == "canyon_wash" else (x_in - w * 0.5, x_in + w * 0.5)):
        for pz in (z0 + d * 0.33, z0 + d * 0.66):
            it.group.add(M.cylinder(0.5, 0.5, 5.6, 10, uv_scale=1.0, material=pal["stone"]).translate(px, floor, pz))
    dress(it, kit, pal, x_in - w, z0, x_in + w, z0 + d, floor, seed)
    it.lamps.append([round(x_in, 2), round(floor + 4.0, 2), round(z0 + d * 0.5, 2)])
    return Built(key, z0 + d, x_out, floor, lattice(x_in - w, z0, x_in + w, z0 + d, floor),
                 (x_in - w, z0, x_in + w, z0 + d))


def cavern(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
           pressure: float = 1.0) -> Built:
    w = 11.0 + 2.0 * pressure
    d = 24.0
    x_out = x_in + (4.0 if seed % 2 else -4.0)
    _room_(it, key, x_in - w, z0, x_in + w, z0 + d, floor, 8.0, pal, doors=_doors(x_in, x_out), ceiling="vault",
           vault_rise=3.8, walls=pal["rock"], ceil=pal["rock"])
    rng = np.random.default_rng(seed)
    for index in range(0 if kit in ("temple_procession", "barrow_visitation", "drowned_customs", "canyon_wash") else 7):
        angle = float(rng.uniform(0, math.tau))
        radial = float(rng.uniform(0.7, 0.92))
        it.group.add(P.boulder(radius=float(rng.uniform(0.6, 1.4)), seed=seed + index, material=pal["rock"])
                     .translate(x_in + math.cos(angle) * w * radial, floor, z0 + d * 0.5 + math.sin(angle) * d * 0.42))
    if kit in ("drowned", "reed", "jungle"):
        it.group.add(M.box((w * 0.9, 0.05, d * 0.35), center=(x_in + w * 0.4, floor + 0.04, z0 + d * 0.5),
                           uv_scale=0.25, material=pal["water"]))
    dress(it, kit, pal, x_in - w, z0, x_in + w, z0 + d, floor, seed, count=8)
    it.lamps.append([round(x_in, 2), round(floor + 5.0, 2), round(z0 + d * 0.5, 2)])
    return Built(key, z0 + d, x_out, floor, lattice(x_in - w, z0, x_in + w, z0 + d, floor, pitch=3.5),
                 (x_in - w, z0, x_in + w, z0 + d))


def bridge(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
           pressure: float = 1.0, *, deck: str = "stone") -> Built:
    """A narrow span: a deck two abreast over a pit of dark water, with lamp
    posts, between two small landings."""
    half = 2.2
    d = 34.0
    wide = 9.0
    landing = 3.0
    # landings at either end carry the doors
    _room_(it, f"{key}-in", x_in - 3.0, z0, x_in + 3.0, z0 + landing, floor, 4.4, pal,
           doors=_doors(x_in, x_in), walls=pal["stone"], ceil=pal["stone"])
    _room_(it, f"{key}-out", x_in - 3.0, z0 + d - landing, x_in + 3.0, z0 + d, floor, 4.4, pal,
           doors=_doors(x_in, x_in), walls=pal["stone"], ceil=pal["stone"])
    # the pit hall between them: its floor is water three metres down and is
    # not a walk surface; its end walls open for the deck
    _room_(it, key, x_in - wide, z0 + landing, x_in + wide, z0 + d - landing, floor - 3.0, 9.0, pal,
           doors=[("south", x_in, DOOR[0], 5.6), ("north", x_in, DOOR[0], 5.6)], ceiling="vault",
           vault_rise=3.0, walls=pal["rock"], ceil=pal["rock"], floor=pal["water"], walk=False)
    if deck == "rock_spine":
        from amberwood import canyoncraft as C
        it.group.add(C.ridge_spine(d - 2 * landing + .08, half * 2, 3, pal["rock"])
                     .translate(x_in, floor - 3, z0 + landing - .04))
    elif deck == "arcaded":
        from amberwood import civiccraft as C
        it.group.add(C.arcaded_causeway(d - 2 * landing + .08, floor, floor,
                                        width=half * 2, arches=3, foot=floor - 3.2,
                                        stone=pal["stone"], paving=pal["floor"], trim=pal["stone"])
                     .rotate_y(-math.pi / 2).translate(x_in, 0, z0 + d * .5))
    elif deck == "piles":
        from amberwood import barrowcraft as B
        it.group.add(B.pile_walkway(length=d - 2 * landing + .08, width=half * 2,
                                    deck_height=3.0, seed=seed, timber=pal["timber"])
                     .translate(x_in, floor - 3.0, z0 + d * .5))
    elif deck == "rope":
        from amberwood import mountaincraft as H
        span = H.suspension_bridge(length=d - 2 * landing, width=half * 2, sag=.55,
                                   seed=seed, deck_y=floor, stone=pal["stone"],
                                   timber=pal["timber"], posts=pal["timber"],
                                   rope=pal["cloth"], iron=pal["metal"])
        it.group.add(span.rotate_y(-math.pi / 2).translate(x_in, 0, z0 + d * .5))
    else:
        it.group.add_walk(M.box((half * 2, 0.6, d - 2 * landing + 0.6), center=(x_in, floor - 0.3, z0 + d * .5),
                                uv_scale=.5, material=pal["stone"]))
    for k in range(0 if deck in ("piles", "arcaded", "rock_spine") else 6):
        pz = z0 + 5.0 + k * (d - 10.0) / 5.0
        for sx in (-half, half):
            height = 2.8 if deck == "rope" else 1.1
            it.group.add(M.box((.24, height, .24), center=(x_in + sx, floor + height * .5, pz), uv_scale=1.0,
                               material=pal["metal"]))
        if deck == "rope":
            # Hang inward from an arm so the vessel and its light clear the
            # solid post, while keeping the middle of the deck unobstructed.
            it.group.add(M.box((.7, .08, .12), center=(x_in - half + .35, floor + 2.76, pz),
                               material=pal["metal"]))
            it.lamps.append([round(x_in - half + .7, 2), round(floor + 2.8, 2), round(pz, 2)])
        else:
            it.lamps.append([round(x_in - half, 2), round(floor + 1.6, 2), round(pz, 2)])
    spawns = [[round(x_in + sx, 2), round(floor, 2), round(z0 + 7.0 + k * 3.2, 2)]
              for k in range(7) for sx in (-1.1, 1.1)]
    return Built(key, z0 + d, x_in, floor, spawns, (x_in - half, z0 + landing, x_in + half, z0 + d - landing))


def stair(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
          pressure: float = 1.0) -> Built:
    """A climb of three metres to a landing where the fight is."""
    rise = 3.0
    run = 14.0
    _link(it, f"{key}-climb", (x_in, z0), (x_in, z0 + run), WAY_WIDTH, floor, floor + rise, WAY_HEIGHT,
          floor=pal["stone"], wall=pal["rock"], ceil=pal["rock"], steps=8, seed=seed, canyon=pal.get("open_canyon", False))
    top = floor + rise
    w = 9.0 + 2.0 * pressure
    d = 18.0
    x_out = x_in + (3.0 if seed % 2 else -3.0)
    _room_(it, key, x_in - w, z0 + run, x_in + w, z0 + run + d, top, 5.6, pal, doors=_doors(x_in, x_out),
           ceiling="vault", vault_rise=2.4)
    dress(it, kit, pal, x_in - w, z0 + run, x_in + w, z0 + run + d, top, seed)
    it.lamps.append([round(x_in, 2), round(top + 4.0, 2), round(z0 + run + d * 0.5, 2)])
    return Built(key, z0 + run + d, x_out, top, lattice(x_in - w, z0 + run, x_in + w, z0 + run + d, top),
                 (x_in - w, z0 + run, x_in + w, z0 + run + d))


def gallery(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
            pressure: float = 1.0, bonus: str = "") -> Built:
    """A long room with three alcoves on one side; the bonus stands in the
    middle one."""
    w = 5.5
    d = 32.0
    side = 1 if seed % 2 else -1
    alcove_x = x_in + side * (w + 3.0)
    doors = _doors(x_in, x_in)
    alcoves = []
    for k in range(3):
        az = z0 + 6.0 + k * 10.0
        doors.append(("east" if side > 0 else "west", az, 3.0, 2.8))
        alcoves.append(az)
    _room_(it, key, x_in - w, z0, x_in + w, z0 + d, floor, 5.4, pal, doors=doors, ceiling="vault", vault_rise=2.2)
    for k, az in enumerate(alcoves):
        akey = f"{key}-alcove-{k}"
        ax0, ax1 = (x_in + w, x_in + w + 6.0) if side > 0 else (x_in - w - 6.0, x_in - w)
        _room_(it, akey, ax0, az - 2.5, ax1, az + 2.5, floor, 4.0, pal,
               doors=[("west" if side > 0 else "east", az, 3.0, 2.8)], walls=pal["stone"], ceil=pal["stone"])
        cx = (ax0 + ax1) * 0.5
        if k == 1 and bonus.startswith("node:"):
            _node(it, f"{key}-bonus", bonus[5:], cx, floor, az, seed + 40, pal["node"])
        elif k == 1 and bonus == "cache":
            _brazier(it, cx, floor, az, seed + 41)
        elif kit not in ("barrow_visitation", "drowned_customs", "canyon_wash"):
            it.group.add(P.crate(size=0.7, seed=seed + k, material=pal["timber"]).translate(cx, floor, az))
    dress(it, kit, pal, x_in - w, z0, x_in + w, z0 + d, floor, seed, count=4)
    it.lamps.append([round(x_in, 2), round(floor + 4.0, 2), round(z0 + d * 0.5, 2)])
    return Built(key, z0 + d, x_in, floor, lattice(x_in - w, z0, x_in + w, z0 + d, floor, pitch=3.2),
                 (x_in - w, z0, x_in + w, z0 + d))


def fork(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
         pressure: float, branches, *, way: float = 12.0) -> tuple[Built, dict]:
    """A hub with two gates, two ways that both rejoin in a merge room.

    Returns the merge room as the leg's Built, and a dict describing the
    hub, the two branch rooms and their gate positions for the composer.
    """
    hub_w, hub_d = 15.0, 14.0
    span = 11.0                      # branch centres at x_in +- span
    _room_(it, f"{key}-hub", x_in - hub_w, z0, x_in + hub_w, z0 + hub_d, floor, 5.6, pal,
           doors=_doors(x_in, None, extra=[("north", x_in - span, DOOR[0], DOOR[1]),
                                           ("north", x_in + span, DOOR[0], DOOR[1])]),
           ceiling="vault", vault_rise=2.4)
    dress(it, kit, pal, x_in - hub_w, z0, x_in + hub_w, z0 + hub_d, floor, seed, count=4)
    it.lamps.append([round(x_in, 2), round(floor + 4.0, 2), round(z0 + hub_d * 0.5, 2)])
    hub_spawns = lattice(x_in - hub_w, z0, x_in + hub_w, z0 + hub_d, floor, pitch=3.5, inset=3.5, back=2.5)
    branch_d = 20.0
    branch_w = 8.0
    info = {"hub": {"key": f"{key}-hub", "bounds": (x_in - hub_w, z0, x_in + hub_w, z0 + hub_d),
                    "spawns": hub_spawns}, "branches": []}
    z_room = z0 + hub_d + way
    for (bid, bname, bkind), sign in zip(branches, (-1, 1)):
        bx = x_in + sign * span
        gate_z = z0 + hub_d + way * 0.5
        info["branches"].append({"id": bid, "name": bname, "kind": bkind, "x": bx,
                                 "gate": {"x": bx, "z0": z0 + hub_d, "z1": z_room},
                                 "key": f"{key}-{bid}"})
        _room_(it, f"{key}-{bid}", bx - branch_w, z_room, bx + branch_w, z_room + branch_d, floor, 6.0, pal,
               doors=_doors(bx, bx), ceiling="vault" if bkind == "cavern" else "flat", vault_rise=3.0,
               walls=pal["rock"] if bkind == "cavern" else None, ceil=pal["rock"] if bkind == "cavern" else None)
        if bkind == "cavern":
            rng = np.random.default_rng(seed + (1 if sign > 0 else 2))
            for index in range(0 if kit in ("temple_procession", "barrow_visitation", "drowned_customs", "canyon_wash") else 4):
                it.group.add(P.boulder(radius=float(rng.uniform(0.6, 1.2)), seed=seed + index + sign * 9,
                                       material=pal["rock"])
                             .translate(bx + sign * float(rng.uniform(2.0, branch_w - 1.5)), floor,
                                        z_room + float(rng.uniform(3.0, branch_d - 3.0))))
        else:
            for px in (() if kit == "canyon_wash" else (bx - branch_w * 0.5, bx + branch_w * 0.5)):
                it.group.add(M.cylinder(0.45, 0.45, 6.0, 10, uv_scale=1.0, material=pal["stone"])
                             .translate(px, floor, z_room + branch_d * 0.5))
        dress(it, kit, pal, bx - branch_w, z_room, bx + branch_w, z_room + branch_d, floor, seed + sign, count=4)
        it.lamps.append([round(bx, 2), round(floor + 4.0, 2), round(z_room + branch_d * 0.5, 2)])
        info["branches"][-1]["spawns"] = lattice(bx - branch_w, z_room, bx + branch_w, z_room + branch_d, floor)
        info["branches"][-1]["bounds"] = (bx - branch_w, z_room, bx + branch_w, z_room + branch_d)
    # the merge room, entered from both branches by plain passages
    z_merge = z_room + branch_d + way
    merge_w, merge_d = 15.0, 12.0
    x_out = x_in
    _room_(it, f"{key}-merge", x_in - merge_w, z_merge, x_in + merge_w, z_merge + merge_d, floor, 5.6, pal,
           doors=[("south", x_in - span, DOOR[0], DOOR[1]), ("south", x_in + span, DOOR[0], DOOR[1]),
                  ("north", x_out, DOOR[0], DOOR[1])], ceiling="vault", vault_rise=2.4)
    for branch in info["branches"]:
        bx = branch["x"]
        _link(it, f"{key}-{branch['id']}-out", (bx, z_room + branch_d), (bx, z_merge), WAY_WIDTH, floor, floor,
              WAY_HEIGHT, floor=pal["floor"], wall=pal["wall"], ceil=pal["ceil"], steps=0, seed=seed, canyon=pal.get("open_canyon", False))
    it.lamps.append([round(x_in, 2), round(floor + 4.0, 2), round(z_merge + merge_d * 0.5, 2)])
    info["merge"] = {"key": f"{key}-merge", "bounds": (x_in - merge_w, z_merge, x_in + merge_w, z_merge + merge_d)}
    built = Built(f"{key}-merge", z_merge + merge_d, x_out, floor, [], info["merge"]["bounds"])
    return built, info


def court(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int,
          pressure: float = 1.0, *, rear_step: bool = False) -> Built:
    """The boss room: wide, with a dais at the far end and braziers round it."""
    w, d = 16.0, 30.0
    x_out = x_in
    _room_(it, key, x_in - w, z0, x_in + w, z0 + d, floor, 9.0, pal, doors=_doors(x_in, x_out), ceiling="vault",
           vault_rise=4.2, walls=pal["rock"], ceil=pal["rock"])
    it.group.add_walk(M.box((12.0, 0.5, 8.0), center=(x_in, floor + 0.25, z0 + d - 7.0), uv_scale=0.8,
                            material=pal["stone"]))
    it.group.add_walk(M.box((6.0, 0.25, 2.0), center=(x_in, floor + 0.125, z0 + d - 12.0), uv_scale=0.8,
                            material=pal["stone"]))
    if rear_step:
        it.group.add_walk(M.box((6.0, .25, 2.0),
                                center=(x_in, floor + .125, z0 + d - 2.0),
                                uv_scale=.8, material=pal["stone"]))
    for k in range(6):
        angle = math.pi * (0.15 + 0.7 * k / 5.0)
        _brazier(it, x_in + math.cos(angle) * (w - 2.0), floor, z0 + d * 0.5 + math.sin(angle) * (d * 0.4), seed + k)
    dress(it, kit, pal, x_in - w, z0, x_in + w, z0 + d, floor, seed, count=8)
    boss = [round(x_in, 2), round(floor + 0.5, 2), round(z0 + d - 7.0, 2)]
    adds = []
    for k in range(8):
        angle = math.tau * k / 8.0
        adds.append([round(x_in + math.cos(angle) * 7.0, 2), round(floor, 2), round(z0 + d * 0.5 + math.sin(angle) * 6.0, 2)])
    built = Built(key, z0 + d, x_out, floor, adds, (x_in - w, z0, x_in + w, z0 + d))
    built.boss = boss
    return built


def vault(it: Interior, key: str, pal: dict, kit: str, z0: float, x_in: float, floor: float, seed: int) -> Built:
    w, d = 7.0, 12.0
    _room_(it, key, x_in - w, z0, x_in + w, z0 + d, floor, 5.0, pal, doors=_doors(x_in, None), ceiling="vault",
           vault_rise=2.0, walls=pal["stone"], ceil=pal["stone"])
    chest = S.MeshGroup()
    chest.add(P.crate(size=1.1, seed=seed, material=pal["timber"]))
    chest.add(M.box((1.2, 0.1, 0.8), center=(0.0, 1.05, 0.0), uv_scale=1.0, material=pal["metal"]))
    it.group.add(chest.translate(x_in, floor, z0 + d - 3.5))
    it.interactives.append({"id": "cache", "kind": "cache", "target": "run",
                            "label": "Reward cache", "text": "The run's cache. It opens once for each of you when the court is quiet.",
                            "position": [round(x_in, 2), round(floor + 0.6, 2), round(z0 + d - 3.5, 2)]})
    it.group.add(MOOR.menhir(height=2.4, seed=seed + 3, material=pal["stone"]).translate(x_in + w - 2.0, floor, z0 + 3.0))
    it.interactives.append({"id": "exit-vault", "kind": "waystone", "target": "home",
                            "label": "Waystone", "text": "The waystone home.",
                            "position": [round(x_in + w - 2.0, 2), round(floor + 1.0, 2), round(z0 + 3.0, 2)]})
    _brazier(it, x_in - w + 2.0, floor, z0 + 3.0, seed + 5)
    _plaque(it, "plaque-vault", "The court is quiet", "Whoever reads this walked the whole road. The cache is "
            "yours; the waystone is the way home.", x_in - w + 1.4, floor, z0 + d - 2.0, material=pal["timber"])
    return Built(key, z0 + d, None, floor, [], (x_in - w, z0, x_in + w, z0 + d))


# ---------------------------------------------------------------- gates
GATE_LABELS = {
    "portcullis": "A portcullis, down. It lifts when the way behind you is quiet.",
    "bars": "An iron bar gate. It opens when the way behind you is quiet.",
    "roots": "A knot of roots grown across the way. It parts when the way behind you is quiet.",
    "ice": "A wall of ice across the way. It cracks open when the way behind you is quiet.",
    "jade": "A jade door, sealed. It opens when the way behind you is quiet.",
    "slab": "A stone slab across the way. It slides when the way behind you is quiet.",
}


def barred_way(it: Interior, key: str, pal: dict, kind: str, a, b, floor_a: float, floor_b: float, seed: int):
    """A passage from `a` to `b` (along Z) cut by a gate at its middle: two
    walk halves, a sill nobody can stand on, jambs, a lintel and the bar.
    Returns (gate position, tile-before position, tile-beyond position)."""
    (x, za), (_, zb) = a, b
    mid = (za + zb) * 0.5
    # the cut is wider than two server tiles, so no sampling of the half-metre
    # grid can find a walkable path across it
    half = 1.4
    _link(it, f"{key}-way-a", (x, za), (x, mid - half), WAY_WIDTH, floor_a, floor_a, WAY_HEIGHT,
          floor=pal["floor"], wall=pal["wall"], ceil=pal["ceil"], steps=0, seed=seed, canyon=pal.get("open_canyon", False))
    _link(it, f"{key}-way-b", (x, mid + half), (x, zb), WAY_WIDTH, floor_a, floor_b, WAY_HEIGHT,
          floor=pal["floor"], wall=pal["wall"], ceil=pal["ceil"], steps=0, seed=seed, canyon=pal.get("open_canyon", False))
    w = WAY_WIDTH
    y = floor_a
    # the sill and the walls either side of it, so the cut is sealed but not walkable
    it.group.add(M.box((w + 0.6, 0.28, half * 2 + 0.2), center=(x, y + 0.14, mid), uv_scale=1.0, material=pal["stone"]))
    for sx in (-1, 1):
        it.group.add(M.box((0.5, WAY_HEIGHT + 0.4, half * 2 + 0.6), center=(x + sx * (w * 0.5 + 0.1), y + WAY_HEIGHT * 0.5, mid),
                           uv_scale=1.0, material=pal["stone"]))
    it.group.add(M.box((w + 0.8, 0.5, half * 2 + 0.6), center=(x, y + WAY_HEIGHT - 0.1, mid), uv_scale=1.0,
                       material=pal["stone"]))
    it.group.add(M.box((w + 0.6, WAY_HEIGHT - 0.5, 0.3), center=(x, y + (WAY_HEIGHT - 0.5) * 0.5, mid), uv_scale=1.0,
                       material=pal["stone"]))  # a slab behind the bars so nothing is seen through
    if kind in ("portcullis", "bars"):
        for k in range(7):
            bx = x - w * 0.45 + k * (w * 0.9 / 6.0)
            it.group.add(M.box((0.1, WAY_HEIGHT - 0.6, 0.1), center=(bx, y + (WAY_HEIGHT - 0.6) * 0.5 + 0.1, mid - 0.2),
                               uv_scale=1.0, material=pal["metal"]))
        for k in range(3):
            it.group.add(M.box((w * 0.92, 0.1, 0.1), center=(x, y + 0.8 + k * 1.1, mid - 0.2), uv_scale=1.0,
                               material=pal["metal"]))
    elif kind == "roots":
        it.group.add(TREES.stump(radius=0.5, height=WAY_HEIGHT - 0.4, seed=seed, material=pal.get("bark", "bark_dark"))
                     .translate(x - 0.9, y, mid - 0.25))
        it.group.add(TREES.stump(radius=0.45, height=WAY_HEIGHT - 0.6, seed=seed + 1, material=pal.get("bark", "bark_dark"))
                     .translate(x + 0.8, y, mid - 0.25))
        it.group.add(M.box((w * 0.9, 0.35, 0.3), center=(x, y + 1.6, mid - 0.25), uv_scale=1.0,
                           material=pal.get("bark", "bark_dark")))
    elif kind == "ice":
        it.group.add(CC.cluster(count=5, radius=1.1, height=WAY_HEIGHT - 0.5, seed=seed, material=pal["crystal"])
                     .translate(x, y, mid - 0.2))
    elif kind == "jade":
        it.group.add(M.box((w * 0.9, WAY_HEIGHT - 0.7, 0.24), center=(x, y + (WAY_HEIGHT - 0.7) * 0.5, mid - 0.2),
                           uv_scale=1.0, material=pal["crystal"]))
    else:  # slab
        it.group.add(M.box((w * 0.9, WAY_HEIGHT - 0.7, 0.4), center=(x, y + (WAY_HEIGHT - 0.7) * 0.5, mid - 0.2),
                           uv_scale=1.0, material=pal["rock"]))
    before = [round(x, 2), round(floor_a, 2), round(mid - half - 1.6, 2)]
    beyond = [round(x, 2), round(floor_a, 2), round(mid + half + 1.7, 2)]
    return [round(x, 2), round(floor_a + 1.2, 2), round(mid, 2)], before, beyond


def plain_way(it: Interior, key: str, pal: dict, a, b, floor_a: float, floor_b: float, seed: int, steps: int = 0):
    (x, za), (_, zb) = a, b
    _link(it, f"{key}-way", (x, za), (x, zb), WAY_WIDTH, floor_a, floor_b, WAY_HEIGHT,
          floor=pal["floor"], wall=pal["wall"], ceil=pal["ceil"], steps=steps, seed=seed, canyon=pal.get("open_canyon", False))


# ---------------------------------------------------------------- room
def _room_(it: Interior, key: str, x0, z0, x1, z1, floor_y, height, pal, *, doors=(), ceiling="flat",
           vault_rise=2.2, walls=None, ceil=None, floor=None, walk=True):
    floor = floor or pal.get("room_floors", {}).get(key)
    if pal.get("open_canyon"):
        from amberwood import canyoncraft as C, noise as N
        it.group.add(C.enclosure(x0,z0,x1,z1,floor_y,max(5.4,height),doors,
                                 floor or pal["floor"],pal["rock"],walk=walk,
                                 seed=pal["layout_seed"]+N.stable_hash(key)%10000))
        it.spaces[key] = {"x0":x0,"z0":z0,"x1":x1,"z1":z1,"floor":floor_y,"height":height}
        return

    if walk:
        it.space(key, x0, z0, x1, z1, floor_y, height,
                 floor_mat=floor or pal["floor"], wall_mat=walls or pal["wall"],
                 ceil_mat=ceil or pal["ceil"], doors=list(doors), ceiling=ceiling, vault_rise=vault_rise)
        if key in pal.get("flood_rooms", ()):
            # A real low weir retains each shallow flooded chamber. Two server
            # height steps carry the threshold, with no collision-only opening.
            for side, along, width, head in doors:
                vertical = side in ("east", "west")
                x = (x1 if side == "east" else x0) if vertical else along
                z = along if vertical else (z1 if side == "north" else z0)
                it.group.add_walk(M.box((.8 if vertical else width, .4, width if vertical else .8),
                                        center=(x, floor_y + .2, z), material=pal["stone"]))
        return
    # a pit room: walls and lid from the kit, and a floor that is not a walk surface
    group = I.chamber(x0, z0, x1, z1, floor_y, height, floor_mat=floor or pal["floor"],
                      wall_mat=walls or pal["wall"], ceil_mat=ceil or pal["ceil"], doors=list(doors),
                      ceiling=ceiling, vault_rise=vault_rise)
    for piece in group.parts + group.walk_parts:
        it.group.add(piece)
    for piece in group.overhead_parts:
        it.group.add_overhead(piece)
    it.spaces[key] = {"x0": min(x0, x1), "z0": min(z0, z1), "x1": max(x0, x1), "z1": max(z0, z1),
                      "floor": floor_y, "height": height}
