"""Amberwood's interiors, built from the same kit as the region above them.

Four spaces reached from named landmarks on the 576 m map:

    The Motherroot        under The Amberwood Mother    dungeon
    The Gate Undercroft   under The Amber Gate          annex
    The Amber Hall        inside The Amber Hall         settlement
    The Cinder Chapel     inside The Cinder Chapel      transition

They share the region's material table, its `MeshGroup` walk-surface contract and
its modelling primitives, so a doorway, a stair tread and a carved bracket are
the same construction indoors as out. Nothing here is scattered by a noise
function: every chamber is an authored extent and every prop is placed by hand.

Two rules are load-bearing and were learned the expensive way:

* A walkable surface must be registered with `add_walk`, because the client
  turns `navigation.surfaceNodePrefixes` into the layer its grounding ray tests.
  A floor added with `add` is scenery the player falls through.
* A descending passage's ceiling must follow its floor. A flat ceiling pinned to
  the high end leaves the passage taller than the room it descends into, and the
  volume then opens out above that room's wall - a leak straight to the void,
  invisible from inside the passage.
"""
from __future__ import annotations

import math

import numpy as np

from . import architecture as A, mesh as M, props as P, stonework as S, treecraft as TC

EARTH = "packed_earth"
PLASTER = "lime_plaster"
STONE = "ashlar"
RUBBLE = "rubble_stone"
ROCK = "cliff_rock"
PAVING = "cobble_paving"
TIMBER = "timber_warm"
TIMBER_DARK = "timber_dark"
TIMBER_GREY = "timber_grey"
CARVED = "carved_wood"
BARK = "bark_oak"
BARK_DARK = "bark_dark"
IRON = "dark_iron"
AMBER = "amber_resin"
AMBER_GLASS = "amber_glass"
WATER = "water_deep"
SCORCH = "scorched_ground"
SOOT = "lime_plaster"  # replaced per-interior; see cinder_chapel
SOOTED = "sooted_plaster"
CHAR = "charred_timber"
CLOTH = "woven_cloth"
LEAF = "leaf_path"

WALL_T = 0.55          # wall thickness, metres
EYE = 1.7


# ---------------------------------------------------------------- shell parts

def _wall_run(x0, z0, x1, z1, base, height, material, *, door=None, doors=(), thickness=WALL_T):
    """One wall, with its doorways cut as real jambs and lintels when asked.

    `door` is (centre_along_run, width, head_height) in metres from the start;
    `doors` is any number of them. A wall can carry several: a fork's hub has a
    way out to each branch on one side, and a gallery's three alcoves open off
    one wall.
    """
    out = S.MeshGroup()
    length = math.hypot(x1 - x0, z1 - z0)
    if length < 1e-6:
        return out
    ux, uz = (x1 - x0) / length, (z1 - z0) / length
    # rotation_y maps local +X to (cos t, 0, -sin t), so the run direction
    # (ux, uz) needs t = atan2(-uz, ux). Getting this backwards silently builds
    # every wall across its own room.
    angle = math.atan2(-uz, ux)

    def slab(t0, t1, y0, y1):
        if t1 - t0 < 1e-6 or y1 - y0 < 1e-6:
            return
        piece = M.box((t1 - t0, y1 - y0, thickness),
                      center=((t0 + t1) * 0.5 - length * 0.5, (y0 + y1) * 0.5, 0.0),
                      uv_scale=0.5, material=material)
        out.add(piece)

    openings = sorted(list(doors) + ([door] if door is not None else []))
    if not openings:
        slab(0.0, length, base, base + height)
    else:
        # Each doorway is a hole with sides and a soffit, not a gap: the
        # flanking slabs end on the jamb lines and the head slab's underside is
        # the soffit, and because `slab` builds closed boxes those three faces
        # already exist. Adding separate 20 mm reveal boxes straddling the same
        # planes - which this did - gave every doorway in every interior a pair
        # of same-facing surfaces 10 mm apart, and they z-fought.
        cursor = 0.0
        for centre, width, head in openings:
            left, right = max(0.0, centre - width * 0.5), min(length, centre + width * 0.5)
            slab(cursor, left, base, base + height)
            slab(left, right, base + head, base + height)
            cursor = max(cursor, right)
        slab(cursor, length, base, base + height)
    out.rotate_y(angle)
    out.translate((x0 + x1) * 0.5, 0.0, (z0 + z1) * 0.5)
    return out


def chamber(x0, z0, x1, z1, floor_y, height, *, floor_mat, wall_mat, ceil_mat,
            doors=(), ceiling="flat", vault_rise=2.2, seed=0):
    """An authored room: walk floor, four walls with doorways, and a lid.

    `doors` are (side, world coordinate along that wall, width, head). Absolute
    world coordinates rather than wall-relative offsets, because per-side sign
    bookkeeping is exactly where a doorway drifts out of line with its passage.
    """
    out = S.MeshGroup()
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    out.add_walk(M.box((x1 - x0 + WALL_T * 2, 0.4, z1 - z0 + WALL_T * 2),
                       center=((x0 + x1) * 0.5, floor_y - 0.2, (z0 + z1) * 0.5),
                       uv_scale=0.35, material=floor_mat))
    # Runs overlap by a wall thickness at each corner. Butting them exactly at
    # the corner leaves a thickness-square hole in all four, and from inside the
    # room you see daylight through it.
    o = WALL_T
    runs = {"north": ((x0 - o, z1), (x1 + o, z1)), "south": ((x1 + o, z0), (x0 - o, z0)),
            "east": ((x1, z1 + o), (x1, z0 - o)), "west": ((x0, z0 - o), (x0, z1 + o))}
    travel = {"north": lambda c: c - (x0 - o), "south": lambda c: (x1 + o) - c,
              "east": lambda c: (z1 + o) - c, "west": lambda c: c - (z0 - o)}
    for side, ((ax, az), (bx, bz)) in runs.items():
        # Every door named for the side is cut. Keeping only the last one - as
        # this did until 2026-09-06 - left a fork hub's second way and two of a
        # gallery's three alcoves behind solid wall, which nothing stopped a
        # player walking through until the walk grid learned to block walls.
        openings = [(travel[side](entry[1]), entry[2], entry[3] if len(entry) > 3 else 2.6)
                    for entry in doors if entry[0] == side]
        out.add(_wall_run(ax, az, bx, bz, floor_y, height, wall_mat, doors=openings))
    top = floor_y + height
    # The lid goes in the overhead bucket, never `add`: the isometric rig looks
    # down at these maps, so the client hides overhead nodes and the player sees
    # the room rather than its roof.
    if ceiling == "flat":
        out.add_overhead(M.box((x1 - x0 + WALL_T * 2, 0.35, z1 - z0 + WALL_T * 2),
                               center=((x0 + x1) * 0.5, top + 0.175, (z0 + z1) * 0.5),
                               uv_scale=0.35, material=ceil_mat))
    elif ceiling == "vault":
        out.add_overhead(_barrel_vault(x0, z0, x1, z1, top, vault_rise, ceil_mat))
    return out


def _barrel_vault(x0, z0, x1, z1, spring, rise, material, segments=16,
                  thickness=0.45):
    """Half-cylinder ceiling with real thickness, closed at both ends.

    A single-surface vault is a one-sided shell: from inside the room you look
    straight through its back faces at the sky. Built as an inner and an outer
    ring joined at the springing, it reads as construction and cannot leak.
    """
    cx = (x0 + x1) * 0.5
    inner = (x1 - x0) * 0.5
    outer = inner + thickness
    out = S.MeshGroup()

    def ring(radius, lift):
        return [(cx - math.cos(math.pi * i / segments) * radius,
                 spring + math.sin(math.pi * i / segments) * lift)
                for i in range(segments + 1)]

    inner_ring = ring(inner, rise)
    outer_ring = ring(outer, rise + thickness)
    for profile, flip in ((inner_ring, True), (outer_ring, False)):
        sections = [np.array([[x, y, z] for x, y in profile]) for z in (z0 - WALL_T,
                                                                       z1 + WALL_T)]
        shell = M.loft(sections, closed_rings=False, cap_ends=False,
                       uv_scale=0.4, material=material)
        out.add(shell.flip_winding() if flip else shell)
    # Close the ring ends and the springing edges so the volume is sealed.
    for z in (z0 - WALL_T, z1 + WALL_T):
        band = []
        for i in range(segments):
            a, b = inner_ring[i], inner_ring[i + 1]
            c, d = outer_ring[i + 1], outer_ring[i]
            band.append(M.quad([(a[0], a[1], z), (b[0], b[1], z),
                                (c[0], c[1], z), (d[0], d[1], z)],
                               uv_scale=0.5, material=material))
        piece = M.merge(band, material)
        out.add(piece if z > z0 else piece.flip_winding())
    for pair in ((inner_ring[0], outer_ring[0]), (inner_ring[-1], outer_ring[-1])):
        (ax, ay), (bx, by) = pair
        out.add(M.quad([(ax, ay, z0 - WALL_T), (bx, by, z0 - WALL_T),
                        (bx, by, z1 + WALL_T), (ax, ay, z1 + WALL_T)],
                       uv_scale=0.5, material=material))
    # Tympanum: the barrel is open at each end above the springing line, and the
    # room walls below only reach the springing. Without this half-lunette filled
    # in, every vaulted room shows a wedge of sky over its end walls.
    for z, flip in ((z0 - WALL_T, False), (z1 + WALL_T, True)):
        fan = []
        for i in range(segments):
            a, b = inner_ring[i], inner_ring[i + 1]
            fan.append(M.quad([(a[0], spring, z), (b[0], spring, z),
                               (b[0], b[1], z), (a[0], a[1], z)],
                              uv_scale=0.5, material=material))
        piece = M.merge(fan, material)
        out.add(piece.flip_winding() if flip else piece)
    return out


def passage(x0, z0, x1, z1, width, floor_a, floor_b, height, *,
            floor_mat, wall_mat, ceil_mat, steps=0, seed=0):
    """A connecting run whose ceiling descends with its floor.

    Overlaps both endpoints by a wall thickness so the join is sealed.
    """
    out = S.MeshGroup()
    horizontal = abs(x1 - x0) > abs(z1 - z0)
    half = width * 0.5
    length = math.hypot(x1 - x0, z1 - z0)
    if length < 1e-6:
        return out
    if steps:
        rise = (floor_b - floor_a) / steps
        run = length / steps
        for i in range(steps):
            t0 = i * run
            y = floor_a + rise * (i + 1)
            if horizontal:
                cx = min(x0, x1) + (t0 + run * 0.5) if x1 > x0 else max(x0, x1) - (t0 + run * 0.5)
                tread = M.box((run, 0.34, width), center=(cx, y - 0.17, z0),
                              uv_scale=0.4, material=floor_mat)
            else:
                cz = min(z0, z1) + (t0 + run * 0.5) if z1 > z0 else max(z0, z1) - (t0 + run * 0.5)
                tread = M.box((width, 0.34, run), center=(x0, y - 0.17, cz),
                              uv_scale=0.4, material=floor_mat)
            out.add_walk(tread)
    else:
        if horizontal:
            out.add_walk(M.box((length + WALL_T * 2, 0.35, width),
                               center=((x0 + x1) * 0.5, floor_a - 0.175, z0),
                               uv_scale=0.4, material=floor_mat))
        else:
            out.add_walk(M.box((width, 0.35, length + WALL_T * 2),
                               center=(x0, floor_a - 0.175, (z0 + z1) * 0.5),
                               uv_scale=0.4, material=floor_mat))

    # Side walls and lid follow the floor line, so the far end matches the room
    # it opens into instead of standing proud of that room's ceiling.
    lo = min(floor_a, floor_b)
    span = max(floor_a, floor_b) - lo
    slices = max(2, steps if steps else 2)
    for i in range(slices):
        t0, t1 = i / slices, (i + 1) / slices
        ya = floor_a + (floor_b - floor_a) * t0
        yb = floor_a + (floor_b - floor_a) * t1
        mid = (ya + yb) * 0.5
        if horizontal:
            xa = x0 + (x1 - x0) * t0
            xb = x0 + (x1 - x0) * t1
            seg = abs(xb - xa) + (WALL_T * 2 if i in (0, slices - 1) else 0.0)
            for side in (-1, 1):
                out.add(M.box((seg, height + span / slices + 0.6, WALL_T),
                              center=((xa + xb) * 0.5, mid + height * 0.5,
                                      z0 + side * (half + WALL_T * 0.5)),
                              uv_scale=0.5, material=wall_mat))
            out.add_overhead(M.box((seg, 0.3, width + WALL_T * 2),
                                   center=((xa + xb) * 0.5, mid + height + 0.15, z0),
                                   uv_scale=0.4, material=ceil_mat))
        else:
            za = z0 + (z1 - z0) * t0
            zb = z0 + (z1 - z0) * t1
            seg = abs(zb - za) + (WALL_T * 2 if i in (0, slices - 1) else 0.0)
            for side in (-1, 1):
                out.add(M.box((WALL_T, height + span / slices + 0.6, seg),
                              center=(x0 + side * (half + WALL_T * 0.5),
                                      mid + height * 0.5, (za + zb) * 0.5),
                              uv_scale=0.5, material=wall_mat))
            out.add_overhead(M.box((width + WALL_T * 2, 0.3, seg),
                                   center=(x0, mid + height + 0.15, (za + zb) * 0.5),
                                   uv_scale=0.4, material=ceil_mat))
    return out


def root_ribs(x0, z0, x1, z1, floor_a, floor_b, width, height, material=BARK_DARK,
              spacing=3.4, seed=0):
    """Roots arching over an earth-cut passage, springing from both walls."""
    out = S.MeshGroup()
    length = math.hypot(x1 - x0, z1 - z0)
    count = max(3, int(length / spacing))
    horizontal = abs(x1 - x0) > abs(z1 - z0)
    rng = np.random.default_rng(seed)
    for i in range(count):
        t = (i + 0.5) / count
        x = x0 + (x1 - x0) * t
        z = z0 + (z1 - z0) * t
        y = floor_a + (floor_b - floor_a) * t
        crown = y + height - 0.4 + float(rng.uniform(-0.15, 0.15))
        half = width * 0.5
        if horizontal:
            left = np.array([x, y + 0.15, z - half])
            right = np.array([x, y + 0.15, z + half])
        else:
            left = np.array([x - half, y + 0.15, z])
            right = np.array([x + half, y + 0.15, z])
        mid = np.array([x, crown, z])
        for end in (left, right):
            path = np.array([end, (end + mid) * 0.5 + np.array([0, -0.45, 0]), mid])
            out.add(M.tube(path, [0.26, 0.2, 0.15], segments=8, cap_start=True,
                           material=material))
    return out


def hanging_lamps(points, seed=0):
    """Iron hooks with amber vessels - the readable light source everywhere."""
    out = S.MeshGroup()
    placed = []
    for i, (x, y, z) in enumerate(points):
        lamp = P.hanging_lantern(seed=seed + i, drop=0.62)
        out.add(lamp.translate(x, y, z) if hasattr(lamp, "translate") else lamp)
        placed.append([round(x, 2), round(y - 0.62, 2), round(z, 2)])
    return out, placed


# ------------------------------------------------------------------ container

class Interior:
    """One authored interior: geometry plus everything its manifest needs."""

    def __init__(self, ident, name, klass, anchor_landmark, anchor_position,
                 destination_spawn):
        self.ident = ident
        self.name = name
        self.klass = klass
        self.anchor_landmark = anchor_landmark
        self.anchor_position = anchor_position
        self.destination_spawn = destination_spawn
        # The room a player arrives in. Not the first concept subject: that may be
        # a descending passage, and its bbox centre is halfway down the stair.
        self.spawn_space = None
        self.group = S.MeshGroup()
        self.spaces: dict[str, dict] = {}
        self.passages: dict[str, dict] = {}   # ident -> run endpoints, for cameras
        self.landmarks: list[dict] = []
        self.interactives: list[dict] = []
        self.harvestables: list[dict] = []
        self.npc_markers: list[dict] = []
        self.lamps: list[list[float]] = []
        self.open_to_sky: list[str] = []
        self.subjects: list[tuple[str, str, str]] = []
        self.notes: list[str] = []
        self.environment: dict = {}

    def space(self, key, x0, z0, x1, z1, floor_y, height, **kw):
        self.spaces[key] = {"x0": min(x0, x1), "z0": min(z0, z1), "x1": max(x0, x1),
                            "z1": max(z0, z1), "floor": floor_y, "height": height}
        if kw.get("ceiling") == "open":
            self.open_to_sky.append(key)
        self.group.add(chamber(x0, z0, x1, z1, floor_y, height, **kw))
        return self.spaces[key]

    def centre(self, key):
        s = self.spaces[key]
        return ((s["x0"] + s["x1"]) * 0.5, (s["z0"] + s["z1"]) * 0.5)

    def landmark(self, ident, name, space, y_offset=1.2):
        cx, cz = self.centre(space)
        self.landmarks.append({"id": ident, "name": name, "space": space,
                               "position": [round(cx, 2),
                                            round(self.spaces[space]["floor"] + y_offset, 2),
                                            round(cz, 2)]})


# ------------------------------------------------------- 1. The Motherroot

def motherroot(seed: int = 20260828) -> Interior:
    """The root system under The Amberwood Mother.

    The settlement's oldest stone, swallowed by growth, and the amber seams that
    were mined out and abandoned. One descending route, nine authored spaces.
    """
    it = Interior("amberwood_motherroot", "The Motherroot", "dungeon",
                  "great-tree", [78.0, 56.18, -264.0], "motherroot-mouth")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("mouth", -9, -9, 9, 9, 0.0, 6.0, floor_mat=LEAF, wall_mat=BARK_DARK,
             ceil_mat=BARK_DARK, ceiling="open",
             doors=[("north", 0.0, 5.5, 3.2)])
    it.space("workings", -20, 30, 3, 48, -6.0, 5.6, floor_mat=EARTH, wall_mat=EARTH,
             ceil_mat=BARK_DARK, ceiling="vault", vault_rise=3.4,
             doors=[("south", 0.0, 5.5, 3.2), ("east", 39.0, 7.0, 3.4)])
    it.space("shrine", 20, 30, 38, 48, -8.5, 7.0, floor_mat=PAVING, wall_mat=STONE,
             ceil_mat=STONE, ceiling="vault", vault_rise=2.8,
             doors=[("west", 39.0, 7.0, 3.4), ("north", 29.0, 7.0, 3.4)])
    it.space("brood", 16, 66, 38, 86, -10.0, 6.0, floor_mat=EARTH, wall_mat=EARTH,
             ceil_mat=BARK_DARK, doors=[("south", 29.0, 7.0, 3.4),
                                        ("west", 76.0, 5.0, 3.4)])
    it.space("sump", -16, 66, 2, 88, -15.5, 5.5, floor_mat=RUBBLE, wall_mat=STONE,
             ceil_mat=ROCK, doors=[("east", 76.0, 5.0, 3.4), ("west", 77.0, 5.0, 3.6)])
    it.space("heartwood", -52, 62, -28, 92, -18.0, 12.0, floor_mat=BARK,
             wall_mat=BARK, ceil_mat=BARK, ceiling="vault", vault_rise=5.5,
             doors=[("east", 77.0, 5.0, 3.6)])

    links = [
        ("hollowway", (0, 9), (0, 30), 5.5, 0.0, -6.0, 4.0, 18, True),
        ("archway", (3, 39), (20, 39), 7.6, -6.0, -8.5, 5.0, 8, False),
        ("sapway", (29, 48), (29, 66), 7.0, -8.5, -10.0, 4.0, 5, False),
        ("descent", (16, 76), (2, 76), 5.0, -10.0, -15.5, 4.4, 16, True),
        ("deepway", (-16, 77), (-28, 77), 5.0, -15.5, -18.0, 4.6, 9, True),
    ]
    for ident, a, b, width, y0, y1, height, steps, ribs in links:
        mats = ((EARTH, EARTH, EARTH) if ribs or ident == "sapway"
                else (PAVING, STONE, STONE))
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=mats[0], wall_mat=mats[1], ceil_mat=mats[2],
                      steps=steps, seed=seed + len(ident)))
        if ribs:
            g.add(root_ribs(a[0], a[1], b[0], b[1], y0, y1, width, height,
                            seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        # A passage is a run, not a box: a camera placed from its bounding box
        # stands in a side wall. Keep the endpoints so views look along it.
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- mouth: buttress roots gripping the opening, leaf drift, daylight shaft
    for i in range(7):
        angle = 2 * math.pi * i / 7 + float(rng.uniform(-0.15, 0.15))
        bx, bz = math.cos(angle) * 7.4, math.sin(angle) * 7.4
        path = np.array([[bx * 1.25, 4.6, bz * 1.25], [bx, 1.9, bz],
                         [bx * 0.72, 0.15, bz * 0.72], [bx * 0.4, -0.3, bz * 0.4]])
        g.add(M.tube(path, [0.5, 0.42, 0.3, 0.2], segments=9, cap_start=True,
                     material=BARK_DARK))
    for i in range(4):
        g.add(P.leaf_drift(radius=1.9, seed=seed + i).translate(
            float(rng.uniform(-6, 6)), 0.02, float(rng.uniform(3.0, 7.5))))
    g.add(TC.root_stair(width=3.0, height=1.1, seed=seed).translate(0.0, 0.0, 7.4))

    # -- workings: the seam, timbering, spoil, and the tools left behind
    cx, cz = it.centre("workings")
    for i in range(12):
        z = 31.5 + i * 1.35
        y = -4.9 + 0.35 * math.sin(i * 0.9)
        g.add(M.tube(np.array([[2.4, y, z], [2.4, y + 0.3, z + 1.3]]),
                     [0.24, 0.18], segments=7, cap_start=True, cap_end=True,
                     material=AMBER))
    for z in (33.0, 37.5, 42.0, 46.0):
        g.add(A.post(1.9, z, -6.0, 2.8, width=0.26, material=TIMBER_GREY))
        g.add(A.post(-2.4, z, -6.0, 2.8, width=0.26, material=TIMBER_GREY))
        g.add(A.beam((1.9, -3.2, z), (-2.4, -3.2, z), 0.26, material=TIMBER_GREY))
    for x, z, r in ((-9.0, 34.0, 1.8), (-14.5, 41.0, 1.4), (-5.5, 44.5, 1.2)):
        g.add(P.rock_cluster(radius=r, count=6, seed=int(rng.integers(1 << 20)),
                             material=EARTH).translate(x, -6.0, z))
    for i, z in enumerate((32.4, 36.0, 40.6, 45.2)):
        g.add(P.basket(radius=0.34, height=0.44, seed=seed + i).translate(1.2, -6.0, z))
        g.add(P.amber_lump(radius=0.24, seed=seed + i).translate(1.2, -5.6, z))
    g.add(P.workbench(length=2.4, seed=seed, tools=True).translate(-12.0, -6.0, 37.0))
    g.add(P.cart(seed=seed).rotate_y(0.6).translate(-8.0, -6.0, 45.0))

    # -- archway: founder masonry split open by a root that outgrew it
    # Rotate before translating: rotate_y turns about the world origin, so a
    # rotate after a translate swings the piece across the map.
    g.add(S.ancient_arch(span=5.2, height=6.4, depth=1.4, seed=seed, roots=True,
                         ruined=True).rotate_y(math.pi / 2).translate(11.5, -7.3, 39.0))
    g.add(M.tube(np.array([[8.0, -1.6, 36.6], [11.0, -2.6, 38.0],
                           [13.8, -4.6, 39.8], [15.6, -7.1, 40.6]]),
                 [0.55, 0.46, 0.34, 0.22], segments=10, cap_start=True, cap_end=True,
                 material=BARK_DARK))
    for x, z, r in ((9.4, 40.6, 0.46), (12.6, 37.4, 0.38), (14.2, 40.8, 0.32)):
        g.add(P.boulder(radius=r, seed=int(rng.integers(1 << 20)),
                        material=STONE).translate(x, -8.2, z))

    # -- shrine: the focal chamber, columns, plinth, hung amber
    cx, cz = it.centre("shrine")
    for dx in (-6.0, 6.0):
        for dz in (-6.0, 6.0):
            g.add(S.column(height=7.0, radius=0.42, material=STONE)
                  .translate(cx + dx, -8.5, cz + dz))
    g.add(S.fountain(radius=2.2, seed=seed).translate(cx, -8.5, cz))
    for i in range(7):
        angle = 2 * math.pi * i / 7 + 0.35
        g.add(P.amber_lump(radius=0.2, seed=seed + i).translate(
            cx + math.cos(angle) * 3.3, -8.4, cz + math.sin(angle) * 3.3))
    g.add(P.brazier(seed=seed).translate(cx - 4.5, -8.5, cz - 3.0))
    g.add(P.brazier(seed=seed + 1).translate(cx + 4.5, -8.5, cz + 3.0))

    # -- sapway: a warm resin run crossed on stepping stones
    g.add(S.water_channel(length=17.0, width=2.2, depth=0.5, seed=seed)
          .rotate_y(math.pi / 2).translate(29.0, -10.0, 57.0))
    for i, z in enumerate((50.5, 53.5, 56.5, 59.5, 62.5)):
        g.add_walk(M.box((1.5, 0.42, 1.5), center=(29.0 + (1.6 if i % 2 else -1.6),
                                                   -9.8, z), material=STONE))

    # -- brood: roots from the ceiling, chewed pulp, egg cases
    cx, cz = it.centre("brood")
    for i in range(9):
        angle = 2 * math.pi * i / 9
        x, z = cx + math.cos(angle) * 7.5, cz + math.sin(angle) * 6.5
        inward = np.array([(cx - x) * 0.2, 0.0, (cz - z) * 0.2])
        path = np.array([[x, -4.2, z], [x, -6.4, z], [x, -8.6, z], [x, -10.2, z]]) + \
            np.array([[0, 0, 0], inward * 0.4, inward, inward * 1.5])
        g.add(M.tube(path, [0.34, 0.28, 0.22, 0.16], segments=10, cap_start=True,
                     material=BARK_DARK))
    for i in range(16):
        g.add(P.mushroom_cluster(seed=seed + i, count=4, material=AMBER).translate(
            float(rng.uniform(18.5, 35.5)), -10.0, float(rng.uniform(68.0, 84.0))))

    # -- sump: standing water and founder stone breaking the surface
    cx, cz = it.centre("sump")
    g.add(M.box((17.0, 0.06, 21.0), center=(cx, -14.7, cz), uv_scale=0.25,
                material=WATER))
    for x, z, h in ((-11.0, 70.0, 2.6), (-4.5, 74.0, 1.7), (-9.5, 82.0, 2.1),
                    (-2.0, 85.0, 1.3)):
        g.add(M.box((1.4, h, 1.4), center=(x, -15.5 + h * 0.5, z), material=STONE))
    g.add(M.tube(np.array([[-14.0, -15.0, 78.0], [-6.0, -14.9, 80.5]]), [0.5, 0.46],
                 segments=10, cap_start=True, cap_end=True, material=STONE))

    # -- heartwood: the objective. Ribs of living wood over sunken founder stone
    cx, cz = it.centre("heartwood")
    for i in range(9):
        t = i / 8.0
        z = 64.0 + t * 26.0
        for side in (-1, 1):
            x = cx + side * 10.4
            path = np.array([[x, -18.0, z], [x - side * 2.6, -13.0, z],
                             [cx - side * 0.8, -18.0 + 15.6, z]])
            g.add(M.tube(path, [0.62, 0.42, 0.24], segments=9, cap_start=True,
                         material=BARK))
    for ring, (r, h) in enumerate(((6.0, 0.0), (4.8, 0.36), (3.6, 0.72))):
        g.add_walk(M.box((r * 2, 0.36, r * 2), center=(cx, -18.0 + h + 0.18, cz),
                         uv_scale=0.4, material=STONE))
    g.add(S.statue(height=3.0, seed=seed, plinth_height=1.1).translate(cx, -16.92, cz))
    for i in range(14):
        t = i / 13.0
        z = 63.5 + t * 27.0
        for side in (-1, 1):
            g.add(M.tube(np.array([[cx + side * 11.0, -17.0, z],
                                   [cx + side * 11.0, -15.2 - 0.9 * math.sin(i), z]]),
                         [0.13, 0.09], segments=6, cap_start=True, cap_end=True,
                         material=AMBER))

    lamp_points = [
        (-6.8, 4.2, 4.5), (6.8, 4.2, -4.5), (0.0, 4.2, 7.2),
        (0.0, -1.3, 15.0), (0.0, -3.6, 23.0),
        (-17.5, -2.6, 33.0), (-17.5, -2.6, 45.0), (-3.0, -2.6, 39.0), (-10.0, -2.6, 31.5),
        (11.5, -5.4, 39.0),
        (22.5, -3.8, 32.0), (35.5, -3.8, 46.0), (29.0, -3.8, 33.0),
        (29.0, -7.4, 52.0), (29.0, -7.8, 62.0),
        (18.5, -5.8, 68.0), (35.5, -5.8, 84.0), (27.0, -5.8, 76.0),
        (9.0, -8.0, 76.0),
        (-13.5, -11.6, 69.0), (-0.5, -11.6, 85.0), (-7.0, -11.6, 77.0),
        (-22.0, -14.4, 77.0),
        (-49.0, -8.5, 65.0), (-31.0, -8.5, 89.0), (-40.0, -8.5, 77.0), (-40.0, -8.5, 68.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "mouth"
    it.subjects = [
        ("concept-01", "root cave entry", "mouth"),
        ("concept-02", "descending root gallery", "hollowway"),
        ("concept-03", "amber seam workings", "workings"),
        ("concept-04", "collapsed stone arch", "archway"),
        ("concept-05", "resin lantern shrine", "shrine"),
        ("concept-06", "sap flow channel", "sapway"),
        ("concept-07", "brood hollow", "brood"),
        ("concept-08", "flooded sump", "sump"),
        ("concept-09", "heartwood chamber", "heartwood"),
        ("concept-10", "root amber granite materials", "shrine"),
    ]
    it.landmark("the-mouth", "The Root Mouth", "mouth", 1.6)
    it.landmark("the-workings", "The Old Workings", "workings")
    it.landmark("the-shrine", "The Resin Shrine", "shrine")
    it.landmark("the-brood", "The Brood Hollow", "brood")
    it.landmark("the-sump", "The Sump", "sump")
    it.landmark("the-heartwood", "The Heartwood", "heartwood", 2.0)
    it.interactives = [
        {"id": "amber-seam", "kind": "harvest-node", "resource": "amber_resin",
         "position": [2.4, -4.6, 38.0]},
        {"id": "shrine-basin", "kind": "shrine", "position": [29.0, -7.4, 39.0]},
        {"id": "founder-marker", "kind": "lore", "position": [-40.0, -16.9, 77.0]},
    ]
    it.harvestables = [
        {"id": f"amber-{i:02d}", "resource": "amber_resin",
         "position": [round(1.2, 2), -6.0, round(z, 2)]}
        for i, z in enumerate((32.4, 36.0, 40.6, 45.2))
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.16, 0.13, 0.11], "energy": 0.35},
        "fog": {"enabled": True, "colour": [0.07, 0.05, 0.04], "begin": 12.0, "end": 48.0},
        "audio": [{"id": "drip", "space": "sump", "loop": True},
                  {"id": "creak", "space": "heartwood", "loop": True}],
    }
    it.notes = [
        "One descending route from the root mouth to the heartwood chamber; no branch "
        "is a dead end without a reason to be there.",
        "The sump's water plane is scenery, not a walk surface: navigation.blocked "
        "marks it so a grounding ray cannot resolve onto it.",
    ]
    return it


def timber_framing(x0, z0, x1, z1, floor_y, height, *, spacing=2.7,
                   material=TIMBER_DARK, sill=True, inset=None):
    """Exposed posts, sill, wall-plate and braces on the inside faces.

    Plaster infill between dark framing is what stops a warm interior collapsing
    into one uniform orange note, and it gives the eye a structural rhythm to
    read the room's length by. The framing is inset from the wall centre-line by
    half the wall thickness: laid on the line it sits entirely inside the wall
    and nothing shows.
    """
    out = S.MeshGroup()
    inset = WALL_T * 0.5 + 0.11 if inset is None else inset
    head = floor_y + height - 0.5
    ix0, ix1 = x0 + inset, x1 - inset
    iz0, iz1 = z0 + inset, z1 - inset
    for z, _side in ((iz0, 1), (iz1, -1)):
        n = max(2, int((ix1 - ix0) / spacing))
        if sill:
            out.add(A.beam((ix0, floor_y + 0.18, z), (ix1, floor_y + 0.18, z), 0.3,
                           material=material))
        out.add(A.beam((ix0, head, z), (ix1, head, z), 0.34, material=material))
        for i in range(n + 1):
            x = ix0 + (ix1 - ix0) * i / n
            out.add(A.post(x, z, floor_y, height - 0.5, width=0.26, material=material))
            if 0 < i < n:
                out.add(A.beam((x - 1.0, floor_y + 0.24, z), (x, floor_y + 1.7, z), 0.17,
                               material=material))
    for x in (ix0, ix1):
        n = max(2, int((iz1 - iz0) / spacing))
        if sill:
            out.add(A.beam((x, floor_y + 0.18, iz0), (x, floor_y + 0.18, iz1), 0.3,
                           material=material))
        out.add(A.beam((x, head, iz0), (x, head, iz1), 0.34, material=material))
        for i in range(n + 1):
            z = iz0 + (iz1 - iz0) * i / n
            out.add(A.post(x, z, floor_y, height - 0.5, width=0.26, material=material))
    return out


def trusses(x0, z0, x1, z1, top, count=5, material=TIMBER_DARK, rise=1.2):
    """Exposed carved roof trusses spanning X, with king post and struts."""
    out = S.MeshGroup()
    cx = (x0 + x1) * 0.5
    for i in range(count):
        z = z0 + 1.6 + i * ((z1 - z0 - 3.2) / max(1, count - 1))
        # Sprung from just under the wall plate, not from the ceiling line, so the
        # truss is a thing you stand under rather than a detail lost in the dark.
        spring = top - 1.15
        out.add(M.tube(np.array([[x0 + 0.4, spring, z], [cx, spring + rise, z],
                                 [x1 - 0.4, spring, z]]),
                       [0.3, 0.25, 0.3], segments=8, cap_start=True, cap_end=True,
                       material=material))
        out.add(A.beam((x0 + 0.4, spring - 0.1, z), (x1 - 0.4, spring - 0.1, z), 0.28,
                       material=material))
        out.add(A.post(cx, z, spring - 0.1, rise + 0.2, width=0.2, material=material))
        for side in (-1, 1):
            out.add(A.beam((cx + side * (x1 - x0) * 0.22, spring - 0.05, z),
                           (cx + side * 0.3, spring + rise * 0.72, z), 0.16,
                           material=material))
    return out


# --------------------------------------------------- 2. The Gate Undercroft

def gate_undercroft(seed: int = 20260829) -> Interior:
    """The founders' work beneath The Amber Gate.

    Square, dry and dressed - the counterweight to the Motherroot's organic
    descent, until Amberwood's growth finally reaches it.
    """
    it = Interior("amberwood_gate_undercroft", "The Gate Undercroft", "annex",
                  "great-arch", [174.0, 36.97, -102.0], "gate-undercroft-stair")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("landing", -7, -7, 7, 7, 0.0, 5.6, floor_mat=PAVING, wall_mat=STONE,
             ceil_mat=STONE, ceiling="open", doors=[("north", 0.0, 5.0, 3.2)])
    it.space("antechamber", -11, 22, 11, 38, -5.0, 5.4, floor_mat=PAVING,
             wall_mat=STONE, ceil_mat=STONE, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 5.0, 3.2), ("east", 30.0, 4.6, 3.0)])
    it.space("cistern", 24, 24, 40, 40, -6.4, 5.6, floor_mat=RUBBLE, wall_mat=STONE,
             ceil_mat=STONE, ceiling="vault", vault_rise=2.6,
             doors=[("west", 30.0, 4.6, 3.0), ("north", 32.0, 5.0, 3.2)])
    it.space("colonnade", 20, 52, 44, 74, -7.8, 6.6, floor_mat=RUBBLE,
             wall_mat=STONE, ceil_mat=STONE,
             doors=[("south", 32.0, 5.0, 3.2), ("west", 63.0, 4.8, 3.4)])
    it.space("crypt", -14, 54, 12, 78, -7.8, 7.4, floor_mat=PAVING, wall_mat=STONE,
             ceil_mat=STONE, ceiling="vault", vault_rise=3.4,
             doors=[("east", 63.0, 4.8, 3.4)])

    links = [
        ("stairhead", (0, 7), (0, 22), 5.0, 0.0, -5.0, 4.2, 18),
        ("breach", (11, 30), (24, 30), 4.6, -5.0, -6.4, 4.0, 5),
        ("cisternway", (32, 40), (32, 52), 5.0, -6.4, -7.8, 4.4, 5),
        ("cryptway", (20, 63), (12, 63), 4.8, -7.8, -7.8, 4.4, 0),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=PAVING, wall_mat=STONE, ceil_mat=STONE, steps=steps,
                      seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- landing: the ceremonial stair arriving from the surface
    g.add(S.ancient_arch(span=5.6, height=6.6, depth=1.5, seed=seed, roots=True,
                         ruined=False).translate(0.0, 0.0, -5.2))
    for dx in (-5.0, 5.0):
        g.add(S.column(height=5.6, radius=0.4, material=STONE).translate(dx, 0.0, 3.4))
    for i in range(3):
        g.add(P.leaf_drift(radius=1.7, seed=seed + i).translate(
            float(rng.uniform(-4, 4)), 0.02, float(rng.uniform(-4.5, 1.0))))

    # -- antechamber: carved keystone arch and the vault it springs from
    cx, cz = it.centre("antechamber")
    g.add(M.arch(span=6.4, rise=3.0, thickness=0.8, depth=1.6, material=STONE)
          .translate(cx, -5.0, cz + 3.0))
    for dz in (-4.6, 4.6):
        for dx in (-7.2, 7.2):
            g.add(S.column(height=5.4, radius=0.36, material=STONE)
                  .translate(cx + dx, -5.0, cz + dz))
    g.add(S.statue(height=2.4, seed=seed + 3).translate(cx - 7.2, -5.0, cz))

    # -- cistern: water management, and the votive niche in its west wall
    cx, cz = it.centre("cistern")
    g.add(M.box((9.6, 0.06, 9.6), center=(cx, -5.5, cz), uv_scale=0.3, material=WATER))
    for side in (-1, 1):
        g.add(M.box((0.6, 1.5, 10.6), center=(cx + side * 5.0, -5.8, cz),
                    material=STONE))
        g.add(M.box((10.6, 1.5, 0.6), center=(cx, -5.8, cz + side * 5.0),
                    material=STONE))
    niche_z = cz
    g.add(M.box((0.5, 1.9, 2.6), center=(24.35, -5.2, niche_z), material=IRON))
    for i in range(5):
        g.add(P.amber_lump(radius=0.16, seed=seed + i).translate(
            24.8, -5.4 + 0.0, niche_z - 1.0 + i * 0.5))
    g.add(P.brazier(seed=seed + 5).translate(cx + 3.4, -6.4, cz - 3.4))

    # -- breach: growth reaching the founders' stonework at last
    g.add(M.tube(np.array([[12.0, -2.2, 27.6], [15.5, -3.0, 29.0],
                           [19.0, -4.4, 30.6], [22.4, -6.2, 31.4]]),
                 [0.5, 0.42, 0.32, 0.2], segments=10, cap_start=True, cap_end=True,
                 material=BARK_DARK))
    for x, z, r in ((16.2, 30.8, 0.4), (18.8, 29.2, 0.32), (20.6, 31.2, 0.28)):
        g.add(P.boulder(radius=r, seed=int(rng.integers(1 << 20)),
                        material=STONE).translate(x, -5.8, z))

    # -- colonnade: half-drowned columns standing in silt
    cx, cz = it.centre("colonnade")
    for i in range(4):
        for side in (-1, 1):
            g.add(S.column(height=7.4, radius=0.5, material=STONE)
                  .translate(cx + side * 7.0, -8.6, 54.5 + i * 5.0))
    g.add(M.box((22.0, 0.06, 20.0), center=(cx, -7.1, cz), uv_scale=0.3, material=WATER))
    g.add(M.tube(np.array([[cx - 4.0, -7.4, cz + 2.0], [cx + 2.0, -7.3, cz + 4.5]]),
                 [0.5, 0.46], segments=10, cap_start=True, cap_end=True, material=STONE))
    g.add(P.boulder(radius=0.8, seed=seed + 9, material=STONE)
          .translate(cx + 3.2, -7.6, cz - 3.0))

    # -- crypt: the founders' marker, ringed in bronze-dark iron and moss
    cx, cz = it.centre("crypt")
    for ring, (r, h) in enumerate(((6.4, 0.0), (5.0, 0.38), (3.6, 0.76))):
        g.add_walk(M.box((r * 2, 0.38, r * 2), center=(cx, -7.8 + h + 0.19, cz),
                         uv_scale=0.4, material=STONE))
    g.add(M.box((4.0, 0.7, 2.2), center=(cx, -6.7, cz), uv_scale=0.6, material=STONE))
    g.add(M.box((3.6, 0.12, 1.9), center=(cx, -6.29, cz), uv_scale=0.6, material=IRON))
    for dx, dz in ((-2.6, -1.7), (2.6, -1.7), (-2.6, 1.7), (2.6, 1.7)):
        g.add(M.tube(np.array([[cx + dx, -7.0, cz + dz], [cx + dx, -4.9, cz + dz]]),
                     [0.08, 0.06], segments=8, cap_start=True, cap_end=True,
                     material=IRON))
        g.add(P.amber_lump(radius=0.2, seed=seed + int(dx + dz)).translate(
            cx + dx, -4.85, cz + dz))
    for dx in (-9.0, 9.0):
        for dz in (-8.0, 8.0):
            g.add(S.column(height=7.4, radius=0.42, material=STONE)
                  .translate(cx + dx, -7.8, cz + dz))

    lamp_points = [
        (-5.2, 3.8, -3.0), (5.2, 3.8, 3.0),
        (0.0, -1.2, 12.0), (0.0, -3.4, 19.0),
        (-8.0, -1.4, 25.0), (8.0, -1.4, 35.0), (0.0, -1.4, 30.0),
        (17.5, -2.6, 30.0),
        (26.5, -2.6, 26.5), (37.5, -2.6, 37.5), (32.0, -2.6, 30.0),
        (32.0, -4.6, 45.0),
        (23.0, -3.0, 55.0), (41.0, -3.0, 71.0), (32.0, -3.0, 63.0),
        (16.0, -4.6, 63.0),
        (-11.0, -2.6, 57.0), (9.0, -2.6, 75.0), (-1.0, -2.6, 66.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "landing"
    it.subjects = [
        ("concept-01", "stair descent", "stairhead"),
        ("concept-02", "vaulted antechamber", "antechamber"),
        ("concept-03", "carved keystone arch", "antechamber"),
        ("concept-04", "votive niche", "cistern"),
        ("concept-05", "cistern hall", "cistern"),
        ("concept-06", "root breach", "breach"),
        ("concept-07", "sunken colonnade", "colonnade"),
        ("concept-08", "silt pool", "colonnade"),
        ("concept-09", "founders vault", "crypt"),
        ("concept-10", "weathered granite moss iron materials", "crypt"),
    ]
    it.landmark("the-landing", "The Gate Stair", "landing", 1.6)
    it.landmark("the-antechamber", "The Antechamber", "antechamber")
    it.landmark("the-cistern", "The Cistern", "cistern")
    it.landmark("the-colonnade", "The Sunken Colonnade", "colonnade")
    it.landmark("the-crypt", "The Founders' Vault", "crypt")
    it.interactives = [
        {"id": "votive-niche", "kind": "shrine", "position": [24.8, -5.2, 32.0]},
        {"id": "founders-marker", "kind": "lore", "position": [-1.0, -6.3, 66.0]},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.15, 0.15, 0.16], "energy": 0.4},
        "fog": {"enabled": True, "colour": [0.06, 0.07, 0.07], "begin": 14.0, "end": 46.0},
        "audio": [{"id": "drip", "space": "cistern", "loop": True}],
    }
    it.notes = ["Dry dressed stone throughout, so the two standing-water rooms read "
                "as failure of the founders' drainage rather than as decoration."]
    return it


# ------------------------------------------------------- 3. The Amber Hall

def amber_hall(seed: int = 20260830) -> Interior:
    """Inside The Amber Hall: the amber-workers' guild at player scale.

    Raw resin graded, pressed, cut, polished and sold. Warm and occupied, and
    the tonal opposite of the two underground packages - pale plaster infill
    between dark framing, so the warmth has something cool to sit against.
    """
    it = Interior("amberwood_amber_hall", "The Amber Hall", "settlement",
                  "amber-hall", [66.0, 41.81, -150.0], "amber-hall-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("porch", -6, -7, 6, 4, 0.0, 4.2, floor_mat=PAVING, wall_mat=PLASTER,
             ceil_mat=TIMBER, ceiling="open", doors=[("north", 0.0, 4.2, 3.0)])
    it.space("sorting", -13, 14, 13, 36, 0.0, 6.6, floor_mat=TIMBER, wall_mat=PLASTER,
             ceil_mat=TIMBER_DARK, doors=[("south", 0.0, 4.2, 3.0),
                                          ("east", 26.0, 3.8, 3.0),
                                          ("north", 0.0, 5.0, 3.4)])
    it.space("press", 24, 18, 39, 34, 0.0, 5.8, floor_mat=PAVING, wall_mat=PLASTER,
             ceil_mat=TIMBER_DARK, doors=[("west", 26.0, 3.8, 3.0),
                                          ("north", 32.0, 3.6, 3.0)])
    it.space("common", -13, 40, 15, 60, 0.0, 6.2, floor_mat=TIMBER, wall_mat=PLASTER,
             ceil_mat=TIMBER_DARK, doors=[("south", 0.0, 5.0, 3.4)])
    it.space("loft", 24, 44, 39, 60, 3.6, 3.8, floor_mat=TIMBER, wall_mat=PLASTER,
             ceil_mat=TIMBER_DARK, doors=[("south", 32.0, 3.6, 3.0)])

    links = [("entryway", (0, 4), (0, 14), 4.2, 0.0, 0.0, 3.6, 0),
             ("pressway", (13, 26), (24, 26), 3.8, 0.0, 0.0, 3.6, 0),
             ("loftstair", (32, 34), (32, 44), 3.6, 0.0, 3.6, 3.8, 12)]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=TIMBER, wall_mat=PLASTER, ceil_mat=TIMBER_DARK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    for key in ("sorting", "common", "loft"):
        s = it.spaces[key]
        g.add(timber_framing(s["x0"], s["z0"], s["x1"], s["z1"], s["floor"], s["height"]))
    g.add(trusses(-13, 14, 13, 36, 6.6, count=6))
    g.add(trusses(-13, 40, 15, 60, 6.2, count=5))

    # -- porch: posts, bracket-carried canopy, boot scrapers, leaf drift
    for dx in (-4.4, 4.4):
        g.add(A.post(dx, 3.0, 0.0, 4.2, width=0.26, material=TIMBER_DARK))
        g.add(A.bracket(size=0.6).translate(dx, 3.4, 3.0))
    g.add(A.beam((-5.2, 4.1, 3.0), (5.2, 4.1, 3.0), 0.3, material=TIMBER_DARK))
    for x in (-2.4, 2.4):
        g.add(M.box((0.6, 0.16, 0.3), center=(x, 0.08, 1.6), material=IRON))
    for i in range(3):
        g.add(P.leaf_drift(radius=1.5, seed=seed + i).translate(
            float(rng.uniform(-4.5, 4.5)), 0.02, float(rng.uniform(-5.5, -2.0))))
    g.add(P.signpost(seed=seed, arms=1).translate(5.0, 0.0, -5.0))

    # -- sorting floor: grading benches down both sides, a long central table
    for i in range(5):
        z = 17.0 + i * 4.0
        for x in (-9.0, 9.0):
            g.add(P.workbench(length=2.6, seed=seed + i, tools=False).translate(x, 0.0, z))
            for k in range(3):
                g.add(P.basket(radius=0.28, height=0.34, seed=seed + k).translate(
                    x - 0.7 + k * 0.7, 0.92, z))
    g.add(P.workbench(length=7.0, seed=seed + 11, tools=True).translate(0.0, 0.0, 25.0))
    for i in range(7):
        g.add(P.amber_lump(radius=0.2, seed=seed + i).translate(
            -2.6 + i * 0.9, 0.94, 25.0))
    g.add(P.amber_workstation(seed=seed).translate(-9.0, 0.0, 32.5))
    g.add(P.amber_workstation(seed=seed + 1).translate(9.0, 0.0, 32.5))
    for i in range(4):
        g.add(P.crate(size=0.6, seed=seed + i).translate(
            float(rng.uniform(-11, 11)), 0.0, float(rng.uniform(15.5, 34.5))))

    # -- press room: the screw press, the hearth and its flue, polishing wheels
    cx, cz = it.centre("press")
    g.add(M.box((3.4, 0.7, 3.4), center=(cx, 0.35, cz), uv_scale=0.6, material=STONE))
    for dx, dz in ((-1.4, -1.4), (1.4, -1.4), (-1.4, 1.4), (1.4, 1.4)):
        g.add(A.post(cx + dx, cz + dz, 0.7, 3.0, width=0.2, material=TIMBER_DARK))
    g.add(M.box((3.2, 0.3, 3.2), center=(cx, 3.55, cz), uv_scale=0.6, material=TIMBER_DARK))
    g.add(M.cylinder(0.24, 0.24, 2.4, segments=12, material=IRON).translate(cx, 1.1, cz))
    g.add(M.box((2.0, 0.3, 2.0), center=(cx, 0.9, cz), uv_scale=0.6, material=AMBER))
    g.add(A.chimney(width=1.1, height=5.2).translate(37.4, 0.0, cz))
    g.add(M.box((1.9, 1.2, 3.0), center=(37.6, 0.6, cz), uv_scale=0.6, material=RUBBLE))
    g.add(P.brazier(seed=seed + 4).translate(37.0, 1.2, cz))
    g.add(P.workbench(length=3.0, seed=seed + 6, tools=True).translate(26.8, 0.0, 31.0))
    for dx in (-0.9, 0.0, 0.9):
        g.add(M.cylinder(0.34, 0.34, 0.18, segments=14, material=IRON)
              .translate(26.8 + dx, 0.98, 31.0))
    for i in range(5):
        g.add(P.barrel(seed=seed + i).translate(25.6, 0.0, 20.0 + i * 1.1))

    # -- common hall: hearth, seating, notice board, the master's display case
    cx, cz = it.centre("common")
    g.add(M.box((1.8, 1.3, 4.4), center=(-12.2, 0.65, cz), uv_scale=0.6, material=RUBBLE))
    g.add(A.chimney(width=1.2, height=6.0).translate(-12.4, 1.3, cz))
    g.add(P.brazier(seed=seed + 7).translate(-11.0, 0.0, cz))
    for dz in (-5.0, 0.0, 5.0):
        for dx in (-4.0, 4.0):
            g.add(P.workbench(length=2.4, seed=seed + int(dz), tools=False)
                  .rotate_y(math.pi / 2).translate(cx + dx, 0.0, cz + dz))
    g.add(M.box((3.0, 0.9, 1.4), center=(cx + 8.0, 0.45, cz + 6.0), uv_scale=0.6,
                material=TIMBER))
    for dx, dz in ((-1.4, -0.6), (1.4, -0.6), (-1.4, 0.6), (1.4, 0.6)):
        g.add(M.tube(np.array([[cx + 8.0 + dx, 0.9, cz + 6.0 + dz],
                               [cx + 8.0 + dx, 2.3, cz + 6.0 + dz]]), [0.05, 0.05],
                     segments=6, cap_start=True, cap_end=True, material=IRON))
    g.add(M.box((3.0, 0.12, 1.4), center=(cx + 8.0, 2.36, cz + 6.0), material=IRON))
    for i in range(5):
        g.add(P.amber_lump(radius=0.16, seed=seed + i).translate(
            cx + 6.9 + i * 0.55, 0.95, cz + 6.0))
    g.add(M.box((2.8, 1.4, 0.16), center=(cx - 6.0, 1.8, 40.4), uv_scale=0.7,
                material=TIMBER_GREY))
    g.add(P.banner(width=0.8, height=2.4, seed=seed).translate(cx + 6.0, 4.4, 40.5))

    # -- loft: barrels and crates over the press, with a rail at the stair head
    for i in range(4):
        for j in range(3):
            g.add(P.barrel(seed=seed + i * 3 + j).translate(
                26.6 + i * 3.0, 3.6, 47.0 + j * 4.0))
    for i in range(4):
        g.add(P.crate(size=0.64, seed=seed + i).translate(37.0, 3.6, 46.0 + i * 3.2))
    g.add(A.railing(length=6.0, height=1.0).translate(28.5, 3.6, 44.6))

    lamp_points = [(0.0, 3.4, -3.0), (0.0, 3.0, 9.0),
                   (-9.5, 5.4, 18.0), (9.5, 5.4, 18.0), (-9.5, 5.4, 32.0),
                   (9.5, 5.4, 32.0), (0.0, 5.4, 25.0),
                   (26.5, 4.6, 20.5), (37.0, 4.6, 31.5), (31.5, 4.6, 26.0),
                   (-9.5, 5.0, 44.0), (11.5, 5.0, 44.0), (-9.5, 5.0, 56.0),
                   (11.5, 5.0, 56.0), (1.0, 5.0, 50.0),
                   (26.5, 6.6, 47.0), (37.0, 6.6, 57.0)]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "porch"
    it.subjects = [
        ("concept-01", "hall entry porch", "porch"),
        ("concept-02", "sorting floor", "sorting"),
        ("concept-03", "resin press room", "press"),
        ("concept-04", "carved roof trusses", "sorting"),
        ("concept-05", "amber cutting benches", "sorting"),
        ("concept-06", "polishing alcove", "press"),
        ("concept-07", "master's display case", "common"),
        ("concept-08", "warm storage loft", "loft"),
        ("concept-09", "guild common hall", "common"),
        ("concept-10", "amber oak plaster iron materials", "common"),
    ]
    it.landmark("the-porch", "The Hall Porch", "porch", 1.6)
    it.landmark("the-sorting-floor", "The Sorting Floor", "sorting")
    it.landmark("the-press", "The Resin Press", "press")
    it.landmark("the-common-hall", "The Guild Hall", "common")
    it.landmark("the-loft", "The Warm Loft", "loft")
    it.interactives = [
        {"id": "cutting-bench", "kind": "crafting-station", "recipe": "amber_working",
         "position": [-9.0, 0.95, 32.5]},
        {"id": "resin-press", "kind": "crafting-station", "recipe": "resin_pressing",
         "position": [31.5, 0.9, 26.0]},
        {"id": "display-case", "kind": "merchant", "position": [9.0, 0.95, 56.0]},
        {"id": "notice-board", "kind": "quest-board", "position": [-5.0, 1.8, 40.4]},
    ]
    it.npc_markers = [
        {"id": "grader", "role": "artisan", "position": [0.0, 0.0, 25.0]},
        {"id": "presser", "role": "artisan", "position": [31.5, 0.0, 29.0]},
        {"id": "hall-master", "role": "merchant", "position": [9.0, 0.0, 54.5]},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.30, 0.25, 0.19], "energy": 0.62},
        "fog": {"enabled": True, "colour": [0.16, 0.12, 0.09], "begin": 24.0, "end": 74.0},
        "audio": [{"id": "workshop", "space": "sorting", "loop": True},
                  {"id": "hearth", "space": "common", "loop": True}],
    }
    it.notes = ["Pale plaster infill between dark framing: an interior built only "
                "from timber reads as one uniform orange, which the region brief "
                "explicitly warns against."]
    return it


# ----------------------------------------------------- 4. The Cinder Chapel

def cinder_chapel(seed: int = 20260831) -> Interior:
    """Inside The Cinder Chapel, in the burnt country east of the forest.

    Deliberately the Amber Hall's construction language rendered in char - the
    same framing, the same plan logic, the same hearth - so the ruin reads as the
    living building after a fire rather than as a different kind of place.
    """
    it = Interior("amberwood_cinder_chapel", "The Cinder Chapel", "transition",
                  "ash-chapel", [312.0, 51.25, -222.0], "cinder-chapel-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("porch", -5, -6, 5, 4, 0.0, 4.0, floor_mat=SCORCH, wall_mat=SOOTED,
             ceil_mat=CHAR, ceiling="open", doors=[("north", 0.0, 3.8, 2.9)])
    it.space("nave", -13, 12, 11, 34, 0.0, 7.0, floor_mat=SCORCH, wall_mat=SOOTED,
             ceil_mat=CHAR, ceiling="open",
             doors=[("south", 0.0, 3.8, 2.9), ("east", 24.0, 3.4, 2.9),
                    ("north", -4.0, 3.6, 2.9)])
    it.space("vestry", -13, 38, -1, 52, 0.0, 4.6, floor_mat=SCORCH, wall_mat=SOOTED,
             ceil_mat=CHAR, doors=[("south", -4.0, 3.6, 2.9),
                                          ("north", -7.0, 3.4, 2.9)])
    it.space("store", 20, 16, 34, 32, -0.6, 4.8, floor_mat=SCORCH, wall_mat=SOOTED,
             ceil_mat=CHAR, doors=[("west", 24.0, 3.4, 2.9),
                                          ("north", 27.0, 3.4, 3.0)])
    it.space("crypt", 18, 40, 34, 56, -4.8, 4.4, floor_mat=RUBBLE, wall_mat=STONE,
             ceil_mat=STONE, doors=[("south", 27.0, 3.4, 3.0)])
    it.space("belfry", -13, 56, -1, 68, 3.4, 3.6, floor_mat=SCORCH, wall_mat=SOOTED,
             ceil_mat=CHAR, ceiling="open",
             doors=[("south", -7.0, 3.4, 2.9)])

    links = [("threshold", (0, 4), (0, 12), 3.8, 0.0, 0.0, 3.4, 0),
             ("aisle", (11, 24), (20, 24), 3.4, 0.0, -0.6, 3.4, 3),
             ("cryptstair", (27, 32), (27, 40), 3.4, -0.6, -4.8, 3.8, 13),
             ("belfrystair", (-7, 52), (-7, 56), 3.4, 0.0, 3.4, 3.6, 11)]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=SCORCH, wall_mat=SOOTED, ceil_mat=CHAR,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    for key in ("nave", "vestry", "store", "belfry"):
        s = it.spaces[key]
        g.add(timber_framing(s["x0"], s["z0"], s["x1"], s["z1"], s["floor"],
                             s["height"], material=CHAR, spacing=3.0))

    # -- porch: the door burned off its hinges, ash drift instead of leaf drift
    for dx in (-3.6, 3.6):
        g.add(A.post(dx, 3.0, 0.0, 4.0, width=0.24, material=CHAR))
    g.add(A.beam((-4.2, 3.9, 3.0), (4.2, 3.9, 3.0), 0.28, material=CHAR))
    g.add(M.box((1.8, 0.12, 2.2), center=(0.4, 0.06, 1.0), uv_scale=0.7,
                material=CHAR))
    g.add(M.box((0.2, 0.08, 2.2), center=(-0.4, 0.16, 1.0), material=IRON))
    # Ash banked against the threshold, not leaf drift: the same wedge shape the
    # living hall gets, in the colour the fire left behind.
    for i in range(5):
        x = -4.4 + i * 1.8
        peak = 0.2 + 0.1 * math.sin(i * 1.4)
        g.add(M.extrude([(x, -5.4), (x + 1.8, -5.4), (x + 1.8, -2.6), (x, -2.6)],
                        peak, material=SCORCH).translate(0.0, 0.0, 0.0))

    # -- nave: roof open to a grey sky, one truss failed and hanging
    cx, cz = it.centre("nave")
    for i, z in enumerate((15.0, 20.0, 25.0, 30.0)):
        if i == 2:
            g.add(M.tube(np.array([[-12.6, 6.6, z], [cx - 1.5, 7.4, z],
                                   [cx + 1.5, 1.8, z + 1.0]]), [0.24, 0.2, 0.15],
                         segments=7, cap_start=True, cap_end=True, material=CHAR))
            continue
        g.add(M.tube(np.array([[-12.6, 6.6, z], [cx, 8.3, z], [10.6, 6.6, z]]),
                     [0.24, 0.2, 0.24], segments=7, cap_start=True, cap_end=True,
                     material=CHAR))
        g.add(A.beam((-12.6, 6.5, z), (10.6, 6.5, z), 0.2, material=CHAR))
    for _ in range(16):
        x = float(rng.uniform(cx - 5.0, cx + 5.0))
        z = float(rng.uniform(22.0, 29.0))
        length = float(rng.uniform(0.9, 2.6))
        g.add(M.tube(np.array([[x, 0.12, z], [x + length, 0.2, z + length * 0.4]]),
                     [0.1, 0.08], segments=5, cap_start=True, cap_end=True,
                     material=CHAR))
    # Ash-choked altar where the chancel step used to be
    g.add(M.box((4.4, 0.4, 1.6), center=(cx, 0.2, 32.0), uv_scale=0.5, material=STONE))
    g.add(M.box((2.8, 0.9, 1.0), center=(cx, 0.65, 32.0), uv_scale=0.6, material=STONE))
    for i in range(9):
        angle = 2 * math.pi * i / 9
        g.add(P.amber_lump(radius=0.14, seed=seed + i).translate(
            cx + math.cos(angle) * 1.7, 0.12, 32.0 + math.sin(angle) * 0.9))
    for dz in (17.0, 21.0, 25.0):
        for dx in (-5.0, 5.0):
            g.add(M.box((2.6, 0.14, 0.5), center=(cx + dx, 0.42, dz), uv_scale=0.6,
                        material=CHAR))
            for side in (-1, 1):
                g.add(A.post(cx + dx + side * 1.1, dz, 0.0, 0.42, width=0.12,
                             material=CHAR))

    # -- vestry: cupboards, a chest left open, a lantern dropped on the floor
    g.add(M.box((1.0, 2.0, 4.0), center=(-12.2, 1.0, 45.0), uv_scale=0.6,
                material=CHAR))
    g.add(M.box((1.6, 0.6, 1.0), center=(-4.0, 0.3, 41.0), uv_scale=0.7, material=CHAR))
    g.add(M.box((1.6, 0.55, 0.14), center=(-4.0, 0.85, 40.6), uv_scale=0.7,
                material=CHAR))
    for i in range(3):
        g.add(P.crate(size=0.6, seed=seed + i).translate(-10.0 + i * 2.4, 0.0, 49.5))
    g.add(P.hanging_lantern(seed=seed, drop=0.0).translate(-6.5, 0.16, 44.0))

    # -- store: salvage stock, and the burned-through floor over the crypt
    cx, cz = it.centre("store")
    for i in range(3):
        g.add(P.log_pile(length=2.6, rows=2, per_row=4, seed=seed + i)
              .translate(32.0, -0.6, 19.0 + i * 4.0))
    for i in range(4):
        g.add(P.barrel(seed=seed + i).translate(21.8, -0.6, 18.5 + i * 1.2))
    g.add(M.box((4.6, 0.1, 3.4), center=(cx, -0.66, cz + 3.0), uv_scale=0.5,
                material=SCORCH))
    for i in range(6):
        x = cx - 2.1 + i * 0.85
        g.add(M.tube(np.array([[x, -0.6, cz + 1.4], [x + 0.3, -1.2, cz + 2.6]]),
                     [0.09, 0.07], segments=5, cap_start=True, cap_end=True,
                     material=CHAR))

    # -- crypt: black standing water under the collapse, founder stone above it
    cx, cz = it.centre("crypt")
    g.add(M.box((14.0, 0.06, 14.0), center=(cx, -4.2, cz), uv_scale=0.3, material=WATER))
    for x, z, h in ((22.0, 44.0, 1.6), (30.0, 46.5, 1.1), (24.5, 52.0, 1.35)):
        g.add(M.box((1.3, h, 1.3), center=(x, -4.8 + h * 0.5, z), material=STONE))
    for i in range(6):
        x = 21.0 + i * 2.2
        g.add(M.tube(np.array([[x, -4.2, 43.0], [x + 1.0, -3.9, 45.4]]), [0.1, 0.08],
                     segments=5, cap_start=True, cap_end=True, material=CHAR))
    g.add(S.statue(height=2.2, seed=seed + 2, plinth_height=0.9)
          .translate(cx, -4.8, cz + 4.5))

    # -- belfry: the vantage east, over the burnt country
    cx, cz = it.centre("belfry")
    g.add(A.railing(length=10.0, height=1.05, material=CHAR)
          .translate(cx - 5.0, 3.4, 66.6))
    g.add(M.box((2.0, 0.6, 1.2), center=(cx, 3.7, cz), uv_scale=0.6, material=CHAR))
    g.add(M.cylinder(0.6, 0.42, 0.9, segments=14, material=IRON).translate(cx, 5.6, cz))
    g.add(M.tube(np.array([[cx, 6.5, cz], [cx, 7.0, cz]]), [0.06, 0.06], segments=6,
                 cap_start=True, cap_end=True, material=IRON))

    lamp_points = [(0.0, 3.2, -3.0), (0.0, 2.8, 8.0),
                   (-10.0, 6.0, 16.0), (8.0, 6.0, 30.0), (-1.0, 6.0, 23.0),
                   (-10.5, 3.8, 41.0), (-3.0, 3.8, 49.0),
                   (22.0, 3.4, 18.5), (32.0, 3.4, 29.5),
                   (27.0, 0.4, 36.0),
                   (20.5, -1.6, 43.0), (32.0, -1.6, 53.0), (26.0, -1.6, 48.0),
                   (-10.5, 6.4, 59.0), (-3.0, 6.4, 65.0)]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "porch"
    it.subjects = [
        ("concept-01", "burned entry", "porch"),
        ("concept-02", "collapsed nave", "nave"),
        ("concept-03", "charred beam arch", "nave"),
        ("concept-04", "ash-choked altar", "nave"),
        ("concept-05", "abandoned vestry", "vestry"),
        ("concept-06", "floor collapse", "store"),
        ("concept-07", "smoke-stained store", "store"),
        ("concept-08", "crypt flood", "crypt"),
        ("concept-09", "bell loft", "belfry"),
        ("concept-10", "char ash iron soot materials", "nave"),
    ]
    it.landmark("the-porch", "The Burned Door", "porch", 1.6)
    it.landmark("the-nave", "The Open Nave", "nave", 1.6)
    it.landmark("the-vestry", "The Vestry", "vestry")
    it.landmark("the-store", "The Salvage Store", "store")
    it.landmark("the-crypt", "The Flooded Crypt", "crypt")
    it.landmark("the-belfry", "The Bell Loft", "belfry", 1.6)
    it.interactives = [
        {"id": "cold-altar", "kind": "lore", "position": [-1.0, 0.7, 32.0]},
        {"id": "vestry-chest", "kind": "container", "position": [-4.0, 0.6, 41.0]},
        {"id": "east-vantage", "kind": "vista", "position": [-7.0, 3.6, 66.0]},
    ]
    it.harvestables = [
        {"id": f"salvage-{i:02d}", "resource": "moor_peat",
         "position": [32.0, -0.6, round(19.0 + i * 4.0, 2)]} for i in range(3)
    ]
    it.environment = {
        "sky": "overcast",
        "ambient": {"colour": [0.17, 0.17, 0.18], "energy": 0.52},
        "fog": {"enabled": True, "colour": [0.13, 0.13, 0.13], "begin": 18.0, "end": 60.0},
        "audio": [{"id": "wind", "space": "nave", "loop": True},
                  {"id": "drip", "space": "crypt", "loop": True}],
    }
    it.notes = ["The nave and the belfry are open to the sky by design: the roof "
                "burned off. Both are declared in environment.openToSky so the "
                "enclosure check does not read them as leaks."]
    return it


ALL = {"motherroot": motherroot, "gate_undercroft": gate_undercroft,
       "amber_hall": amber_hall, "cinder_chapel": cinder_chapel}
