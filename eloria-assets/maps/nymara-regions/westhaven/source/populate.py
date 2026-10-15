"""Westhaven's placement passes.

Everything that stands on the terrain: the mole, the working waterfront, the
shipyard, the city, the two lighthouses, the upland, the planting and the props.
The terrain itself is `region.py`; this is what is built on it.

Written largest-to-smallest in the order the guide prescribes, and each pass is
independent of the ones after it, so the region can be built and validated at
any stage. That matters more than it sounds: the grounding contract was proved
on bare terrain, with every one of these returning early, before any of it was
written.

INSTANCING
----------
Kit pieces are built once into a small pool of variants and placed many times.
`RegionBuild.add_mesh` keys by name, so a name reused is a second node onto the
same mesh and costs no unique triangles. A city of three hundred houses drawn
from twelve variants is 12 meshes and 300 nodes, which is the difference
between a 20 MB package and one nobody can load.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as P
from amberwood import routecraft as RC
from amberwood import stonework as SW
from amberwood import terrain as TER
from amberwood import trees as TR

import havenarch as HA
import havenkit as HK
import region as REG

from region import Placement


def _ground(build, x: float, z: float) -> float:
    return float(build.terrain.height_at(x, z))


def _rand(seed: int, key: str) -> float:
    """Deterministic 0..1. `stable_hash`, never the builtin salted `hash`."""
    return N.stable_hash(f"{seed}:{key}") % 10007 / 10007.0


def _place(build, node: str, mesh_name: str, x: float, z: float,
           y: float | None = None, rotation: float = 0.0, scale: float = 1.0,
           collides: bool = True, kind: str = "prop",
           landmark: str | None = None) -> Placement:
    if y is None:
        y = _ground(build, x, z)
    return build.place(Placement(node=node, mesh=mesh_name,
                                 position=(float(x), float(y), float(z)),
                                 rotation_y=float(rotation), scale=float(scale),
                                 collides=collides, kind=kind,
                                 landmark=landmark))


def _landmark(build, ident: str, name: str, kind: str, node: str,
              x: float, z: float, y: float) -> None:
    build.landmarks.append({
        "id": ident, "name": name, "type": kind, "node": node,
        "position": [round(float(x), 2), round(float(y), 2), round(float(z), 2)],
        "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                       int(round(REG.SERVER_ORIGIN[1] - z))]})


# ------------------------------------------------------------------ water
def build_water(build, lod: str | None = None) -> None:
    """One water surface at sea level, clipped to where the terrain is below it.

    Cut far outside the authored terrain so that a camera on the crown terrace,
    52 m up and looking south, sees water running to a horizon rather than the
    edge of a slab.

    ONE body, not two. The first version had a separate, greener, more opaque
    harbour plane inside the mole, because the painting does show the sheltered
    water reading differently from the open sea. Two blended planes two
    centimetres apart z-fight, and the whole basin came back as a checkerboard.
    The distinction belongs to the water shader, not to the geometry: the
    manifest declares `environment.water.shallowColor` and `deepColor`, and the
    depth that drives them is already in the terrain - the basin is dredged to
    -7.5 m and the sea outside falls to -17.
    """
    t = build.terrain
    # 4.5 m cells over a 240 m reach. The plane is clipped per cell, so the
    # cell size is the shoreline's step size; but it is also a flat quad over
    # 1.1 km square, so halving the cell quadruples its triangles. At 3.5 m the
    # sea alone was 203,000 triangles - more than half the region's geometry,
    # for flat water - and the waterline is not visibly better.
    reach = REG.WATER_MARGIN
    # The far view keeps the same coastline geometry. Coarser per-cell
    # clipping discarded a real 39 m² sea strip at the Grey shared boundary;
    # texture/detail reduction must not turn water into a hole.
    cell = 4.5
    build.water_meshes["Water_Sea"] = TER.water_plane(
        t, REG.SEA_LEVEL,
        t.x0 - reach, t.z0 - reach,
        t.x0 + t.size_x + reach, t.z0 + t.size_z + reach,
        material=HK.HARBOUR, cell=cell, margin=0.12,
        outside_is_water=True)


# -------------------------------------------------------------------- surf
def populate_surf(build, seed: int = 0, lod: str | None = None) -> None:
    """Broken water along every shoreline, weighted by exposure.

    The single biggest gap between the build and the concept. Panels 2 and 8 are
    both substantially made of breaking water, and the southern half of the
    aerial is surf around two rock masses; the region had none of it and read
    as a millpond with land in it.

    Foam is placed where the terrain crosses the water line, as horizontal
    alpha-cut cards a few centimetres above the sea plane. Density is weighted
    by **exposure**: the outward-facing direction of a shore cell is downhill,
    so a cell whose downhill vector points south or west faces the open sea and
    gets heavy foam, and one facing into the harbour gets almost none. That is
    the difference between a decorative white ring and a coast that reads as
    having weather on one side of it.
    """
    t = build.terrain
    for v in range(4):
        card = M.quad([(-1.0, 0.0, -1.0), (1.0, 0.0, -1.0),
                       (1.0, 0.0, 1.0), (-1.0, 0.0, 1.0)],
                      uv_scale=1.0, material=HK.SURF)
        build.add_mesh(f"Surf_Card_{v}", card)

    gradient_z, gradient_x = np.gradient(t.height, t.cell)

    # The shore band is a ring of constant *width in metres*, not a band of
    # constant height. Westhaven's coast is steep - the ground crosses the water
    # line inside two cells almost everywhere - so a height band of +/- 1.5 m
    # caught 797 cells out of 101,761 and produced a dotted line of foam instead
    # of a shoreline. Blurring the land mask and taking the cells where it is
    # neither fully land nor fully water gives the ring the geometry actually
    # implies.
    land = (t.height > REG.SEA_LEVEL).astype(np.float64)
    soft = land
    for _ in range(6):
        padded = np.pad(soft, 1, mode="edge")
        soft = (padded[:-2, 1:-1] + padded[2:, 1:-1]
                + padded[1:-1, :-2] + padded[1:-1, 2:] + soft * 2.0) / 6.0
    band = (soft > 0.06) & (soft < 0.94) & (t.height < REG.SEA_LEVEL + 1.4)

    # Exposure: the outward-facing direction of a shore cell is downhill, which
    # is *minus* the gradient, and the open sea lies south (+Z) and west (-X).
    # Written with the gradient's own sign this comes out exactly negated - it
    # put the heavy foam inside the harbour and left the weather side bare.
    magnitude = np.hypot(gradient_x, gradient_z)
    safe = np.where(magnitude < 1e-6, 1.0, magnitude)
    outward_x = -gradient_x / safe
    outward_z = -gradient_z / safe
    exposure = np.clip(outward_z * 0.72 - outward_x * 0.58, 0.0, 1.0)

    step = 3.0 if lod is None else 6.0
    count = 0
    nx = int(t.size_x / step)
    nz = int(t.size_z / step)
    for iz in range(nz):
        for ix in range(nx):
            x = t.x0 + (ix + 0.5) * step
            z = t.z0 + (iz + 0.5) * step
            cx = int(np.clip((x - t.x0) / t.cell, 0, t.cols - 1))
            cz = int(np.clip((z - t.z0) / t.cell, 0, t.rows - 1))
            if not band[cz, cx]:
                continue
            key = f"s{ix}:{iz}"
            # Everywhere gets a little; the exposed side gets most of it. The
            # 0.22 floor is what keeps the sheltered harbour edge from reading
            # as unnaturally still against the rest.
            chance = 0.22 + 0.68 * float(exposure[cz, cx])
            if _rand(seed, key) > chance:
                continue
            jitter_x = (_rand(seed, key + "x") - 0.5) * step * 0.9
            jitter_z = (_rand(seed, key + "z") - 0.5) * step * 0.9
            scale = 1.9 + _rand(seed, key + "s") * 2.8 * (0.6 + float(exposure[cz, cx]))
            _place(build, f"Surf_{ix:03d}_{iz:03d}", f"Surf_Card_{count % 4}",
                   x + jitter_x, z + jitter_z,
                   y=REG.SEA_LEVEL + 0.06 + _rand(seed, key + "y") * 0.10,
                   rotation=_rand(seed, key + "r") * 6.2, scale=scale,
                   collides=False, kind="foliage")
            count += 1
    build.notes.append(f"surf cards placed: {count}")

    if lod == "far":
        return
    # Breakers: a raised card standing against the weather face of the two rock
    # masses and the mole, where the panels show water actually going up.
    build.add_mesh("Surf_Breaker", _breaker_card())
    breakers = 0
    for u, v in ((0.70, 6.60), (1.20, 7.05), (1.90, 7.30), (2.60, 7.20),
                 (3.10, 6.80), (0.55, 6.00),
                 (5.55, 6.90), (6.20, 7.30), (6.95, 7.35), (7.60, 7.00),
                 (7.80, 6.40),
                 (1.30, 5.06), (2.20, 5.14), (3.10, 5.18), (4.00, 5.20),
                 (4.60, 5.24)):
        x, z = REG._design_to_world(REG.cell(u, v))
        if float(t.height_at(x, z)) > REG.SEA_LEVEL + 2.5:
            continue
        _place(build, f"Surf_Breaker_{breakers:02d}", "Surf_Breaker", x, z,
               y=REG.SEA_LEVEL - 0.4, rotation=_rand(seed, f"bk{u}{v}") * 6.2,
               scale=1.4 + _rand(seed, f"bs{u}{v}") * 1.1,
               collides=False, kind="foliage")
        breakers += 1
    build.notes.append(f"surf breakers placed: {breakers}")


def _breaker_card() -> M.Mesh:
    """A curled sheet of water, for where the sea actually goes up a rock.

    Two rows of quads leaning back from a foot, so it reads as a wave face
    rather than as a billboard standing on edge. Cheap - twelve triangles.
    """
    parts = []
    for i in range(3):
        u0, u1 = i / 3.0, (i + 1) / 3.0
        y0, y1 = u0 * 3.4, u1 * 3.4
        z0 = -u0 * 1.5
        z1 = -u1 * 1.5
        half0 = 3.2 * (1.0 - u0 * 0.35)
        half1 = 3.2 * (1.0 - u1 * 0.35)
        parts.append(M.quad([(-half0, y0, z0), (half0, y0, z0),
                             (half1, y1, z1), (-half1, y1, z1)],
                            uv_scale=0.5, material=HK.SURF))
    return M.merge(parts, HK.SURF)


# ----------------------------------------------------------------- seawall
def populate_seawall(build, seed: int = 0) -> None:
    """The harbour mole and its bastion - detail-board panel 8.

    The mole is the piece that makes the harbour a harbour, and it is the one
    structure in the region whose deck is a long walk surface over open water.
    Per the runtime contract that deck owns its footprint on the server grid:
    the harbour beneath it is not separately walkable.
    """
    t = build.terrain
    deck_y = REG.LEVEL["mole"]
    floor_y = REG.LEVEL["harbour_floor"]

    points = REG.MOLE
    # Walk the polyline in fixed-length runs so each section is straight and
    # the joints fall on the bends. A single long box across a bend leaves a
    # wedge of harbour showing through the deck.
    total = 0.0
    lengths = [0.0]
    for i in range(len(points) - 1):
        total += float(np.linalg.norm(points[i + 1] - points[i]))
        lengths.append(total)
    run = 26.0
    count = max(int(round(total / run)), 3)
    build.add_mesh("Mole_Section", HA.mole_section(
        total / count + 1.2, deck_y, floor_y, deck_width=7.0, seed=seed))
    for i in range(count):
        s0 = total * i / count
        s1 = total * (i + 1) / count
        a = _polyline_point(points, lengths, s0)
        b = _polyline_point(points, lengths, s1)
        mid = (a + b) * 0.5
        _place(build, f"Mole_Run_{i:02d}", "Mole_Section",
               mid[0], mid[1], y=deck_y, rotation=_align(a, b),
               collides=False, kind="landmark")

    bastion_x, bastion_z = REG.ANCHORS["mole_bastion"]
    build.add_mesh("Mole_Bastion", HA.bastion(radius=8.0, height=7.0,
                                              deck_y=0.0, seed=seed + 11))
    node = _place(build, "Landmark_Mole_Bastion", "Mole_Bastion",
                  bastion_x, bastion_z, y=deck_y, collides=False,
                  kind="landmark").node
    # Recorded at the bastion platform, not at the mole deck it rises from:
    # the platform is the walk surface the grounding ray finds here, and a
    # landmark whose y is 3 m under its own floor reads as buried.
    _landmark(build, "mole-bastion", "The Gullstone Bastion", "fortification",
              node, bastion_x, bastion_z, deck_y + 3.15)

    # A light at the mole head, which is what marks the harbour mouth.
    head_x, head_z = REG.ANCHORS["mole_head"]
    build.add_mesh("Mole_Light", HA.lighthouse(height=11.0, base_radius=2.2,
                                               seed=seed + 17))
    node = _place(build, "Landmark_Mole_Light", "Mole_Light",
                  head_x, head_z, y=deck_y, collides=False, kind="landmark").node
    _landmark(build, "mole-light", "The Mole Light", "lighthouse",
              node, head_x, head_z, deck_y + 11.0)

    build.add_mesh("Bollard", HA.bollard(seed=seed))
    for i in range(14):
        s = total * (i + 0.5) / 14.0
        p = _polyline_point(points, lengths, s)
        offset = 2.4 * (1 if i % 2 else -1)
        _place(build, f"Prop_Mole_Bollard_{i:02d}", "Bollard",
               p[0] + offset, p[1], y=deck_y, collides=False, kind="prop")


def _align(a: np.ndarray, b: np.ndarray) -> float:
    """The rotation_y that points a piece built along +X from `a` toward `b`.

    Both `mesh.rotation_y` and the GLB writer's quaternion rotate (1, 0, 0) to
    (cos t, 0, -sin t), so aligning +X with the direction (dx, dz) needs
    t = atan2(-dz, dx). The obvious-looking `atan2(dx, dz) - pi/2` happens to be
    correct when dz is zero and is wrong by up to pi everywhere else, which is
    why the mole came out as a chain of planks lying across its own line
    instead of a breakwater running along it.
    """
    return math.atan2(-(b[1] - a[1]), b[0] - a[0])


def _polyline_point(points: np.ndarray, lengths: list[float],
                    s: float) -> np.ndarray:
    """Point at arc length `s` along a polyline."""
    for i in range(len(lengths) - 1):
        if s <= lengths[i + 1] or i == len(lengths) - 2:
            span = max(lengths[i + 1] - lengths[i], 1e-9)
            u = (s - lengths[i]) / span
            return points[i] + (points[i + 1] - points[i]) * u
    return points[-1]


# -------------------------------------------------------------- waterfront
def populate_waterfront(build, seed: int = 0) -> None:
    """Quay, warehouses, cranes, piers, moored ships and the fish market.

    Panels 3, 4, 5, 7 and 10 all live along this run. It is the busiest 400 m
    of the region and the one a player arrives in the middle of.
    """
    quay_y = REG.LEVEL["quay"]

    # -- the quay wall itself, along the whole harbour front ---------------
    build.add_mesh("Quay_Wall", HA.quay_wall(24.0, height=4.2, seed=seed))
    front = REG.QUAYSIDE
    total = 0.0
    lengths = [0.0]
    for i in range(len(front) - 1):
        total += float(np.linalg.norm(front[i + 1] - front[i]))
        lengths.append(total)
    sections = max(int(round(total / 24.0)), 4)
    for i in range(sections):
        a = _polyline_point(front, lengths, total * i / sections)
        b = _polyline_point(front, lengths, total * (i + 1) / sections)
        mid = (a + b) * 0.5
        # pushed out to the water side of the graded apron
        _place(build, f"Quay_Wall_{i:02d}", "Quay_Wall",
               mid[0], mid[1] + 9.0, y=quay_y, rotation=_align(a, b),
               collides=False, kind="landmark")

    build.add_mesh("Bollard", HA.bollard(seed=seed))
    for i in range(26):
        p = _polyline_point(front, lengths, total * (i + 0.5) / 26.0)
        _place(build, f"Prop_Quay_Bollard_{i:02d}", "Bollard",
               p[0], p[1] + 7.4, y=quay_y, collides=False, kind="prop")

    # -- warehouses: the gable-to-the-water range behind the quay ----------
    for v in range(4):
        build.add_mesh(f"Warehouse_{v}", HA.warehouse(
            width=7.4 + v * 0.7, depth=10.5 + v * 0.9, storeys=3 + (v % 2),
            seed=seed + 40 + v))
    from layout import WAREHOUSES
    for j,(ident,x,z,y) in enumerate(WAREHOUSES):
        variant=j%4
        node=_place(build,f'Landmark_Warehouse_{ident}',f'Warehouse_{variant}',x,z,y=y,
                    rotation=math.pi,kind='building').node
        _landmark(build,f'warehouse-{ident}','Harbour Warehouse','warehouse',node,x,z,y)

    # -- the arch the quay street runs through (panel 3) -------------------
    ax, az = REG.ANCHORS["quay_arch"]
    build.add_mesh("Street_Arch", HA.street_arch(span=5.4, height=4.6, depth=4.2,
                                                 storeys=2, seed=seed + 55))
    node = _place(build, "Landmark_Quay_Arch", "Street_Arch", ax, az,
                  rotation=math.pi * 0.5, collides=False, kind="landmark").node
    _landmark(build, "quay-arch", "The Quay Arch", "gate", node, ax, az,
              _ground(build, ax, az))

    # -- the fish market: an arcade with stalls under it (panel 7) ---------
    fx, fz = REG.ANCHORS["fish_market"]
    build.add_mesh("Market_Arcade", HA.arcade_range(bays=8, span=3.6, height=4.8,
                                                    depth=4.4, seed=seed + 61))
    # The arcade backs onto the warehouse row and opens south toward the quay,
    # with its stalls in front of it. Placed 6 m *south* of the anchor it stood
    # between the camera and its own stalls, and panel 7 came back as two blank
    # warehouse gables with a lane between them.
    node = _place(build, "Landmark_Fish_Market", "Market_Arcade",
                  fx, fz - 13.0, y=REG.LEVEL["lower_town"], rotation=math.pi,
                  collides=False, kind="landmark").node
    _landmark(build, "fish-market", "The Fish Market", "market", node,
              fx, fz, REG.LEVEL["lower_town"])
    for v in range(3):
        build.add_mesh(f"Fish_Stall_{v}", HA.fish_stall(seed=seed + 70 + v))
    for i in range(9):
        x = fx + (i % 5 - 2) * 3.4 + (_rand(seed, f"fs{i}") - 0.5) * 0.8
        z = fz + (i // 5) * 3.6 - 8.0
        _place(build, f"Prop_Fish_Stall_{i:02d}", f"Fish_Stall_{i % 3}",
               x, z, y=REG.LEVEL["lower_town"],
               rotation=(_rand(seed, f"fsr{i}") - 0.5) * 0.3,
               collides=False, kind="prop")

    # -- the piers, with a ship alongside one and a crane on the other -----
    pier_len = 29.0
    build.add_mesh("Pier", HA.pier(pier_len, width=5.4, deck_y=0.0,
                                   floor_y=REG.LEVEL["harbour_floor"] - quay_y,
                                   seed=seed + 81))
    build.add_mesh("Harbour_Crane", HA.harbour_crane(height=9.4, reach=6.8,
                                                     seed=seed + 85))
    build.add_mesh("Gantry", HA.gantry(width=5.6, height=6.4, seed=seed + 89))
    build.add_mesh("Ship_Large", HA.ship_hull(length=26.0, beam=6.8,
                                              seed=seed + 91, masts=2))
    build.add_mesh("Ship_Small", HA.ship_hull(length=17.0, beam=5.0,
                                              seed=seed + 93, masts=1))

    for name, anchor in (("A", "cargo_pier"), ("B", "crane_pier")):
        px, pz = REG.ANCHORS[anchor]
        node = _place(build, f"Landmark_Pier_{name}", "Pier",
                      px, pz - 2.0, y=quay_y, collides=False,
                      kind="landmark").node
        _landmark(build, f"pier-{name.lower()}",
                  "Cargo Pier" if name == "A" else "Crane Pier",
                  "pier", node, px, pz, quay_y)
    cx, cz = REG.ANCHORS["cargo_pier"]
    _place(build, "Landmark_Gantry", "Gantry", cx - 4.6, cz + 9.0, y=quay_y,
           rotation=math.pi * 0.5, collides=False, kind="landmark")
    _place(build, "Ship_At_Cargo_Pier", "Ship_Large",
           cx - 10.5, cz + 16.0, y=REG.SEA_LEVEL,
           rotation=math.pi * 0.5 + 0.04, collides=False, kind="landmark")
    kx, kz = REG.ANCHORS["crane_pier"]
    # On the pier's centreline, not beside it: the deck is 5.4 m wide, so a
    # 3.4 m offset put the crane over open water and 10.9 m above the harbour
    # floor the grounding ray found underneath it.
    node = _place(build, "Landmark_Harbour_Crane", "Harbour_Crane",
                  kx, kz + 12.0, y=quay_y, rotation=math.pi,
                  collides=False, kind="landmark").node
    _landmark(build, "harbour-crane", "The Great Crane", "crane", node,
              kx, kz + 12.0, quay_y)
    _place(build, "Ship_At_Crane_Pier", "Ship_Small",
           kx + 9.5, kz + 20.0, y=REG.SEA_LEVEL,
           rotation=math.pi * 0.5 - 0.06, collides=False, kind="landmark")

    # a few more hulls at anchor in the basin, which is what the aerial shows
    for i, (u, v, rot, big) in enumerate((
            (2.05, 4.95, 0.30, False), (3.05, 5.06, 1.10, True),
            (3.95, 5.14, 2.05, False), (4.55, 4.98, 0.62, True),
            (1.52, 4.86, 2.60, False))):
        x, z = REG._design_to_world(REG.cell(u, v))
        _place(build, f"Ship_Anchored_{i:02d}",
               "Ship_Large" if big else "Ship_Small",
               x, z, y=REG.SEA_LEVEL, rotation=rot, collides=False,
               kind="landmark")

    # -- small jetties along the front. The aerial has a dozen short landing
    #    stages between the two big piers; two piers alone left the waterfront
    #    reading as a wall with two fingers on it.
    build.add_mesh("Jetty", HA.jetty(length=9.0, width=2.2, deck_y=0.0,
                                     floor_y=REG.LEVEL["harbour_floor"] - quay_y,
                                     seed=seed + 95))
    jetties = 0
    for i in range(12):
        s0 = total * (i + 0.5) / 12.0
        p = _polyline_point(front, lengths, s0)
        if abs(p[0] - REG.ANCHORS["cargo_pier"][0]) < 22.0 or            abs(p[0] - REG.ANCHORS["crane_pier"][0]) < 22.0:
            continue                      # do not crowd the two working piers
        _place(build, f"Jetty_{i:02d}", "Jetty", p[0], p[1] + 8.5, y=quay_y,
               rotation=(_rand(seed, f"jy{i}") - 0.5) * 0.2,
               collides=False, kind="landmark")
        jetties += 1
    build.notes.append(f"jetties placed: {jetties}")

    # more hulls: the painting's harbour is busy, and nine was not busy
    for i, (u, v, rot, big) in enumerate((
            (1.05, 5.02, 1.70, False), (2.42, 4.90, 0.20, False),
            (3.48, 4.96, 2.35, True), (4.20, 5.08, 1.05, False),
            (5.02, 4.88, 0.48, False), (1.80, 5.16, 2.85, True),
            (2.95, 5.22, 0.90, False))):
        x, z = REG._design_to_world(REG.cell(u, v))
        _place(build, f"Ship_Moored_{i:02d}",
               "Ship_Large" if big else "Ship_Small",
               x, z, y=REG.SEA_LEVEL, rotation=rot, collides=False,
               kind="landmark")

    # -- the harbour gate over the west inlet (panel 1) --------------------
    gx, gz = REG.ANCHORS["harbour_gate"]
    build.add_mesh("Harbour_Gate", HA.gate_arch(span=12.0, height=17.5,
                                                depth=5.4, seed=seed + 101))
    node = _place(build, "Landmark_Harbour_Gate", "Harbour_Gate",
                  gx, gz + 6.0, y=REG.SEA_LEVEL, rotation=math.radians(28.0),
                  collides=False, kind="landmark").node
    # Recorded at its roadway, not at the water it spans: the roadway is a walk
    # surface, so the grounding ray finds the deck and a landmark logged at the
    # channel below reads as fourteen metres underground.
    _landmark(build, "harbour-gate", "The Harbour Gate", "gate", node,
              gx, gz + 6.0, REG.SEA_LEVEL + 17.75)

    # -- the custom house and the chandlery --------------------------------
    build.add_mesh("Custom_House", HA.town_house(width=9.0, depth=8.0,
                                                 storeys=2, seed=seed + 111,
                                                 jetty=False))
    hx, hz = REG.ANCHORS["custom_house"]
    node = _place(build, "Landmark_Custom_House", "Custom_House", hx, hz,
                  rotation=math.pi, kind="building").node
    _landmark(build, "custom-house", "The Custom House", "civic", node,
              hx, hz, _ground(build, hx, hz))


# ---------------------------------------------------------------- shipyard
def populate_shipyard(build, seed: int = 0) -> None:
    """The yard, the stocks and the hull on them - detail-board panel 6."""
    sx, sz = REG.ANCHORS["shipyard"]
    quay_y = REG.LEVEL["quay"]

    build.add_mesh("Ship_On_Stocks", HA.ship_on_stocks(length=21.0, beam=5.8,
                                                       seed=seed + 121))
    node = _place(build, "Landmark_Shipyard_Hull", "Ship_On_Stocks",
                  sx + 4.0, sz + 9.0, y=quay_y - 0.4,
                  rotation=math.radians(-14.0), collides=False,
                  kind="landmark").node
    _landmark(build, "shipyard", "The Westhaven Yard", "shipyard", node,
              sx, sz, quay_y)

    # the mould loft and the saw shed behind the stocks
    build.add_mesh("Yard_Shed", HA.warehouse(width=9.0, depth=13.0, storeys=1,
                                             seed=seed + 125, hoist=False))
    for i, (dx, dz, rot) in enumerate(((-11.0, -7.0, 0.10),
                                       (2.0, -11.0, -0.06))):
        _place(build, f"Landmark_Yard_Shed_{i}", "Yard_Shed",
               sx + dx, sz + dz, rotation=rot, kind="building")

    # timber stacked to season, which is most of what a yard looks like
    build.add_mesh("Timber_Stack", P.log_pile(length=4.4, rows=4, per_row=6,
                                              seed=seed + 129,
                                              material="timber_warm"))
    for i in range(9):
        x = sx - 16.0 + (i % 3) * 5.2 + (_rand(seed, f"ts{i}") - 0.5) * 1.2
        z = sz + 2.0 + (i // 3) * 4.4
        y = _ground(build, x, z)
        if y < REG.SEA_LEVEL + 0.6:
            continue
        _place(build, f"Prop_Timber_Stack_{i:02d}", "Timber_Stack", x, z, y=y,
               rotation=_rand(seed, f"tsr{i}") * 3.1, kind="prop")

    build.add_mesh("Ropewalk_Shed", HA.arcade_range(bays=10, span=3.2,
                                                    height=3.6, depth=3.4,
                                                    seed=seed + 133,
                                                    upper=False))
    rx, rz = REG.ANCHORS["ropewalk"]
    node = _place(build, "Landmark_Ropewalk", "Ropewalk_Shed", rx, rz,
                  rotation=math.pi, collides=False, kind="landmark").node
    _landmark(build, "ropewalk", "The Ropewalk", "workshop", node, rx, rz,
              _ground(build, rx, rz))


# -------------------------------------------------------------------- city
def populate_city(build, seed: int = 0) -> None:
    """The terraced city: houses, retaining walls, gates, arcades, cathedral,
    campanile and the brass dome of panel 9.
    """
    t = build.terrain

    import layout
    layout.populate_houses(build, seed)
    masks = REG.land_masks(t, seed)

    # -- retaining walls along the terrace risers --------------------------
    build.add_mesh("Retaining_Wall", SW.retaining_wall(10.0, 4.0, seed=seed + 301,
                                                       material="rubble_stone"))
    riser_v = (4.02, 3.36, 2.72, 2.04, 1.40)
    for band, v in enumerate(riser_v):
        z = REG.cell(0.0, v)[1] * REG.SCALE
        for i in range(14):
            u = 0.34 + (5.30 - 0.34) * (i + 0.5) / 14.0
            x = REG.cell(u, 0.0)[0] * REG.SCALE
            cx = int(np.clip((x - t.x0) / t.cell, 0, t.cols - 1))
            cz = int(np.clip((z - t.z0) / t.cell, 0, t.rows - 1))
            if not masks["city"][cz, cx] or t.tree_block[cz, cx]:
                continue
            y = float(t.height[cz, cx])
            _place(build, f"Retaining_{band}_{i:02d}", "Retaining_Wall",
                   x, z + 2.0, y=y - 3.4, collides=False, kind="landmark")

    # -- the city gate -----------------------------------------------------
    gx, gz = REG.ANCHORS["city_gate"]
    build.add_mesh("City_Gate", SW.monumental_gate(seed=seed + 311, span=7.4,
                                                   height=16.0,
                                                   stair_width=12.0,
                                                   stair_height=4.0))
    node = _place(build, "Landmark_City_Gate", "City_Gate", gx, gz,
                  rotation=math.pi, collides=False, kind="landmark").node
    _landmark(build, "city-gate", "The Sea Gate", "gate", node, gx, gz,
              _ground(build, gx, gz))

    # -- the great arcade of the middle city -------------------------------
    ax, az = REG.ANCHORS["arcade"]
    build.add_mesh("Great_Arcade", HA.arcade_range(bays=14, span=3.8, height=5.4,
                                                   depth=5.0, seed=seed + 321))
    node = _place(build, "Landmark_Great_Arcade", "Great_Arcade", ax, az,
                  y=REG.LEVEL["upper_town"], rotation=math.pi,
                  collides=False, kind="landmark").node
    _landmark(build, "great-arcade", "The Long Arcade", "civic", node,
              ax, az, REG.LEVEL["upper_town"])

    # -- the cathedral and the campanile -----------------------------------
    cx, cz = REG.ANCHORS["cathedral"]
    build.add_mesh("Cathedral", HA.cathedral(seed=seed + 331, length=36.0,
                                             width=17.0, height=15.5))
    node = _place(build, "Landmark_Cathedral", "Cathedral", cx, cz,
                  y=REG.LEVEL["citadel"], rotation=math.pi * 0.5,
                  collides=False, kind="landmark").node
    _landmark(build, "cathedral", "The Haven Church", "temple", node,
              cx, cz, REG.LEVEL["citadel"])

    mx, mz = REG.ANCHORS["campanile"]
    build.add_mesh("Campanile", HA.campanile(height=36.0, width=5.4,
                                             seed=seed + 341))
    node = _place(build, "Landmark_Campanile", "Campanile", mx, mz,
                  y=REG.LEVEL["citadel"], collides=False, kind="landmark").node
    _landmark(build, "campanile", "The Bell Tower", "tower", node, mx, mz,
              REG.LEVEL["citadel"])

    # -- the brass dome and its terrace (panel 9) --------------------------
    dx, dz = REG.ANCHORS["brass_dome"]
    build.add_mesh("Domed_Hall", HA.domed_hall(radius=7.2, drum_height=8.4,
                                               seed=seed + 351))
    node = _place(build, "Landmark_Domed_Hall", "Domed_Hall", dx, dz,
                  y=REG.LEVEL["crown"], collides=False, kind="landmark").node
    _landmark(build, "brass-dome", "The Astronomers' Hall", "civic", node,
              dx, dz, REG.LEVEL["crown"])

    # -- the high spire and the guild hall ---------------------------------
    hx, hz = REG.ANCHORS["high_spire"]
    build.add_mesh("High_Spire", A.watchtower(height=30.0, seed=seed + 361,
                                              radius=2.6))
    node = _place(build, "Landmark_High_Spire", "High_Spire", hx, hz,
                  y=REG.LEVEL["upper_town"], kind="landmark").node
    _landmark(build, "high-spire", "The Watch Spire", "tower", node, hx, hz,
              REG.LEVEL["upper_town"])

    gx, gz = REG.ANCHORS["guild_hall"]
    build.add_mesh("Guild_Hall", A.manor(seed=seed + 371, width=17.0, depth=12.0))
    node = _place(build, "Landmark_Guild_Hall", "Guild_Hall", gx, gz,
                  y=REG.LEVEL["lower_town"], rotation=math.pi,
                  kind="building").node
    _landmark(build, "guild-hall", "The Mariners' Guild", "civic", node,
              gx, gz, REG.LEVEL["lower_town"])

    # -- more vertical accents. The painting's skyline carries perhaps three
    #    times the towers this had, and from the water the city read as a bank
    #    of roofs with four things sticking out of it. These are small - a
    #    parish belfry and a merchant's lookout, not another cathedral - and
    #    they are placed on the terrace bands, so they step up with the city.
    for v in range(3):
        build.add_mesh(f"Lesser_Tower_{v}", HA.campanile(
            height=17.0 + v * 4.5, width=3.2 + v * 0.35, seed=seed + 390 + v))
    build.add_mesh("Lesser_Spire", A.watchtower(height=19.0, seed=seed + 396,
                                                radius=1.9))
    for i, (u, v, level, kind) in enumerate((
            (1.42, 3.86, "lower_town", 0), (4.02, 3.72, "lower_town", 1),
            (1.18, 3.04, "mid_town", 2), (4.46, 2.92, "mid_town", 0),
            (2.02, 2.28, "upper_town", 1), (4.10, 1.86, "citadel", 2),
            (2.72, 1.28, "crown", 0))):
        x, z = REG._design_to_world(REG.cell(u, v))
        cx = int(np.clip((x - t.x0) / t.cell, 0, t.cols - 1))
        cz = int(np.clip((z - t.z0) / t.cell, 0, t.rows - 1))
        if not masks["city"][cz, cx] or t.tree_block[cz, cx]:
            continue
        name = "Lesser_Spire" if i % 3 == 2 else f"Lesser_Tower_{kind}"
        _place(build, f"Landmark_Lesser_Tower_{i}", name, x, z,
               y=REG.LEVEL[level], kind="landmark")

    # -- street furniture: lamps along the ramp streets, cisterns in squares
    build.add_mesh("Lamp_Post", SW.lamp_post(height=2.8))
    build.add_mesh("Cistern_Head", HA.cistern_head(seed=seed + 381))
    for name in ("market_climb", "gate_climb", "arcade_walk", "crown_climb",
                 "quayside"):
        points = REG.ROADS[name]
        total = 0.0
        lengths = [0.0]
        for i in range(len(points) - 1):
            total += float(np.linalg.norm(points[i + 1] - points[i]))
            lengths.append(total)
        n = max(int(total / 17.0), 2)
        for i in range(n):
            p = _polyline_point(points, lengths, total * (i + 0.5) / n)
            side = 1 if i % 2 else -1
            x = p[0] + side * REG.ROAD_WIDTH[name] * REG.SCALE * 0.42
            z = p[1] + side * 0.6
            _place(build, f"Prop_Lamp_{name}_{i:02d}", "Lamp_Post", x, z,
                   y=float(build.terrain.mesh_height_at(x, z)),
                   collides=False, kind="prop")
    for name in ("lower_square", "mid_street", "crown_terrace"):
        x, z = REG.ANCHORS[name]
        _place(build, f"Prop_Cistern_{name}", "Cistern_Head", x + 4.0, z + 3.0,
               kind="prop")


# ------------------------------------------------------------- lighthouses
def populate_lighthouses(build, seed: int = 0) -> None:
    """The great lighthouse on Lamp Rock and the Gullstone watch - panel 2."""
    lx, lz = REG.ANCHORS["lighthouse"]
    ly = max(_ground(build, lx, lz), 12.0)
    build.add_mesh("Great_Lighthouse", HA.lighthouse(height=28.0,
                                                     base_radius=4.6,
                                                     seed=seed + 401))
    node = _place(build, "Landmark_Great_Lighthouse", "Great_Lighthouse",
                  lx, lz, y=ly, collides=False, kind="landmark").node
    _landmark(build, "great-lighthouse", "The Lamp Rock Light", "lighthouse",
              node, lx, lz, ly + 28.0)

    wx, wz = REG.ANCHORS["gullstone_watch"]
    build.add_mesh("Gullstone_Watch", A.watchtower(height=17.0, seed=seed + 411,
                                                   radius=2.4))
    node = _place(build, "Landmark_Gullstone_Watch", "Gullstone_Watch",
                  wx, wz, kind="landmark").node
    _landmark(build, "gullstone-watch", "The Gullstone Watch", "tower", node,
              wx, wz, _ground(build, wx, wz))

    # the sea arch on Gullstone's south shore, from the aerial
    ax, az = REG.ANCHORS["gullstone_arch"]
    build.add_mesh("Sea_Arch", SW.ancient_arch(span=9.0, height=11.5, depth=3.2,
                                               seed=seed + 421))
    node = _place(build, "Landmark_Sea_Arch", "Sea_Arch", ax, az,
                  rotation=math.radians(35.0), collides=False,
                  kind="landmark").node
    _landmark(build, "sea-arch", "The Gullstone Arch", "natural", node,
              ax, az, _ground(build, ax, az))

    # rock clutter on both masses, so they read as broken stone not smooth hills
    for v in range(3):
        build.add_mesh(f"Sea_Boulders_{v}", P.rock_cluster(
            radius=2.6 + v * 0.8, count=5 + v, seed=seed + 430 + v,
            material=HK.SEA_ROCK))
    masks = REG.land_masks(build.terrain, seed)
    t = build.terrain
    for name in ("gullstone", "lamp_rock"):
        mask = masks[name]
        rows, cols = np.nonzero(mask)
        for i in range(0, len(rows), max(len(rows) // 60, 1)):
            cz, cx = int(rows[i]), int(cols[i])
            x = float(t.xs[cx]); z = float(t.zs[cz])
            y = float(t.height[cz, cx])
            if y < REG.SEA_LEVEL + 0.5:
                continue
            if _rand(seed, f"rk{name}{i}") > 0.5:
                continue
            _place(build, f"Rock_{name}_{i:04d}",
                   f"Sea_Boulders_{i % 3}", x, z, y=y - 0.6,
                   rotation=_rand(seed, f"rkr{name}{i}") * 6.2,
                   collides=False, kind="rock")


# ------------------------------------------------------------------ upland
def populate_upland(build, seed: int = 0) -> None:
    """The open country north and east: chapel, farm, hill estate, fences."""
    build.add_mesh("Upland_Chapel", HA.cathedral(seed=seed + 501, length=13.0,
                                                 width=7.0, height=6.0))
    cx, cz = REG.ANCHORS["upland_chapel"]
    node = _place(build, "Landmark_Upland_Chapel", "Upland_Chapel", cx, cz,
                  rotation=math.pi * 0.5, collides=False, kind="landmark").node
    _landmark(build, "upland-chapel", "The Wayside Chapel", "temple", node,
              cx, cz, _ground(build, cx, cz))

    build.add_mesh("Farmstead", A.manor(seed=seed + 511, width=13.0, depth=9.0, storeys=1))
    fx, fz = REG.ANCHORS["upland_farm"]
    node = _place(build, "Landmark_Upland_Farm", "Farmstead", fx, fz,
                  rotation=0.4, kind="building").node
    _landmark(build, "upland-farm", "Gullscar Farm", "settlement", node,
              fx, fz, _ground(build, fx, fz))

    build.add_mesh("Hill_Estate", A.manor(seed=seed + 521, width=19.0, depth=13.0))
    hx, hz = REG.ANCHORS["hill_estate"]
    node = _place(build, "Landmark_Hill_Estate", "Hill_Estate", hx, hz,
                  rotation=math.pi * 1.15, kind="building").node
    _landmark(build, "hill-estate", "The Factor's House", "estate", node,
              hx, hz, _ground(build, hx, hz))

    build.add_mesh("East_Watch", A.watchtower(height=14.0, seed=seed + 531,
                                              radius=2.2))
    ex, ez = REG.ANCHORS["east_watch"]
    node = _place(build, "Landmark_East_Watch", "East_Watch", ex, ez,
                  kind="landmark").node
    _landmark(build, "east-watch", "The East Watch", "tower", node, ex, ez,
              _ground(build, ex, ez))

    # field walls along the upland roads, and a signpost at the crossroads
    build.add_mesh("Field_Fence", P.fence(length=5.0, height=1.05,
                                          seed=seed + 541, style="split"))
    build.add_mesh("Signpost", P.signpost(seed=seed + 545, arms=3))
    sx, sz = REG.ANCHORS["crossroads"]
    _place(build, "Prop_Signpost", "Signpost", sx - 6.0, sz + 5.0, kind="prop")
    for name in ("north_road", "east_road"):
        points = REG.ROADS[name]
        total = 0.0
        lengths = [0.0]
        for i in range(len(points) - 1):
            total += float(np.linalg.norm(points[i + 1] - points[i]))
            lengths.append(total)
        n = max(int(total / 11.0), 2)
        for i in range(n):
            s0 = total * (i + 0.2) / n
            a = _polyline_point(points, lengths, s0)
            b = _polyline_point(points, lengths, min(s0 + 5.0, total))
            angle = _align(a, b)
            # the road's normal, so the fences run alongside it, not across
            for side in (-1, 1):
                x = a[0] + side * 6.5 * math.sin(angle)
                z = a[1] + side * 6.5 * math.cos(angle)
                y = _ground(build, x, z)
                if y < REG.SEA_LEVEL + 1.5:
                    continue
                _place(build, f"Prop_Fence_{name}_{i:02d}_{side}", "Field_Fence",
                       x, z, y=y, rotation=angle, collides=False, kind="prop")


def populate_routes(build, seed=0):
    """Cart road furniture, tide crossings and the farm's working ground."""
    for ident, (stations, width) in REG.SHORE_CROSSINGS.items():
        x, y, z = stations[0]
        local = [(px - x, py - y, pz - z) for px, py, pz in stations]
        key = "Route_" + ident.replace("-", "_")
        build.add_mesh(key, RC.graded_causeway(local, width=width, foot=-10.0-y,
                                               stone=HK.SEA_ROCK, paving=HK.SETT))
        node = _place(build, "Landmark_" + key, key, x, z, y=y,
                      collides=False, kind="landmark").node
        _landmark(build, ident, "The Quay-Mole Ramp" if ident == "quay-mole-ramp" else "The Yard Bridge" if ident == "yard-bridge"
                  else "The Gullstone Footbridge" if ident == "gullstone-bridge"
                  else "The Lamp Causeway", "bridge", node, x, z, y)

    # The gateway frames the harbour skyline on the return from the fields.
    gate = HA.gate_arch(span=8.0, height=14.0, seed=seed + 610)
    # This lintel is scenery above a road, not a second road over the gate.
    gate.parts.extend(gate.walk_parts)
    gate.walk_parts.clear()
    build.add_mesh("Cart_Gate", gate)
    x, z = REG.ANCHORS["north_gate"]
    node = _place(build, "Landmark_Cart_Gate", "Cart_Gate", x, z, y=34.0,
                  rotation=0.54, collides=False, kind="landmark").node
    _landmark(build, "cart-gate", "The Upland Gate", "gate", node, x, z, 34.0)

    build.add_mesh("Farm_Grain", RC.crop_rows(seed=seed + 620))
    build.add_mesh("Farm_Herbs", RC.crop_rows(seed=seed + 621, material=HK.TURF,
                                            height_range=(0.26, 0.42)))
    build.add_mesh("Farm_Wall", M.box((18.0, 0.75, 0.5),
                                      center=(0, 0.375, 0), material=HK.SEA_ROCK))
    for i, (x, z, y) in enumerate(REG.FARM_FIELDS):
        # Each strip follows its own small terrace, with a clear opening
        # towards the lane and the water store above it.
        _place(build, f"Farm_Crops_{i}", "Farm_Grain" if i == 0 else "Farm_Herbs", x, z, y=y+0.10,
               collides=False, kind="foliage")
        for side in (-1, 1):
            _place(build, f"Farm_Wall_{i}_{side}", "Farm_Wall", x, z+side*6.5,
                   collides=False, kind="prop")
        node = _place(build, f"Farm_End_{i}", "Farm_Wall", x+9.5, z,
                      rotation=math.pi/2, collides=False, kind="prop").node
        _landmark(build, f"farm-field-{i}", "Gullscar Fields", "field",
                  node, x, z, y)
    x,z = REG.ANCHORS["upland_farm"]
    node = _place(build, "Farm_Water_Store", "Cistern_Head", x+12, z+1,
                  collides=True, kind="prop").node
    _landmark(build, "farm-water-store", "The Farm Cistern", "water",
              node,x+12,z+1,_ground(build,x+12,z+1))
    build.add_mesh("Road_Cart", P.cart(seed=seed+630))
    for i, (x,z) in enumerate(((116,-25),(170,-134))):
        _place(build, f"Road_Cart_{i}", "Road_Cart", x,z,rotation=0.4,kind="prop")
        _place(build, f"Road_Lamp_{i}", "Lamp_Post",x+3,z,collides=False,kind="prop")
    # A sign is beside the junction, not planted in its centre.
    build.notes.append("Surveyed cart loop, two tidal crossings, enclosed Gullscar fields.")

# -------------------------------------------------------------- vegetation
def populate_vegetation(build, seed: int = 0, lod: str | None = None) -> None:
    """Tree belts on the upland, thorn scrub on the headland, no forest.

    Westhaven is not a forest region. The painting has shelter belts along the
    upland field boundaries and pines on the north-west headland, and bare turf
    everywhere else - so the tree pass is a belt-follower, not a scatter.
    """
    t = build.terrain
    masks = REG.land_masks(t, seed)
    # `build_tree` returns (wood, foliage) as two meshes so the bark and the
    # alpha-cut canopy stay on their own materials; both are placed at the same
    # point. Two species: dark pine for the shelter belts and the headland,
    # dark holly for the scrubbier hedge lines along the field walls.
    tiers = ("low",) if lod == "far" else ("high", "mid", "low")
    species = ("dark_pine", "dark_pine", "dark_holly")
    for tier in tiers:
        for v in range(3):
            wood, leaves = TR.build_tree(species[v], seed=seed + 600 + v * 17,
                                         detail=tier)
            build.add_mesh(f"Tree_{tier}_{v}_Wood", wood)
            if leaves.triangle_count:
                build.add_mesh(f"Tree_{tier}_{v}_Canopy", leaves)

    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope_grid = np.hypot(gradient_x, gradient_z)

    # The belt field, precomputed over the whole terrain grid rather than
    # sampled per candidate. Calling `fbm` with scalars inside the placement
    # loop is both slow and noisy - the lattice hash overflows int64 on scalar
    # input and numpy warns about it on every one of ten thousand candidates -
    # and the array form is the one the rest of the toolkit uses.
    belt_field = N.fbm(t.gx * 0.004, t.gz * 0.030, octaves=3, seed=seed + 611)

    # belts follow the upland's own contour bands, which is where a farmer puts
    # a shelter belt: across the prevailing wind, along a field edge
    count = 0
    step = 7.0
    for iu in range(int(8.6 * 24.0 * REG.SCALE / step)):
        for iv in range(int(4.6 * 24.0 * REG.SCALE / step)):
            u = -0.3 + iu * step / (24.0 * REG.SCALE)
            v = -0.3 + iv * step / (24.0 * REG.SCALE)
            x, z = REG._design_to_world(REG.cell(u, v))
            key = f"t{iu}:{iv}"
            x += (_rand(seed, key + "x") - 0.5) * step * 0.8
            z += (_rand(seed, key + "z") - 0.5) * step * 0.8
            cx = int(np.clip((x - t.x0) / t.cell, 0, t.cols - 1))
            cz = int(np.clip((z - t.z0) / t.cell, 0, t.rows - 1))
            if not masks["mainland"][cz, cx] or masks["city"][cz, cx]:
                continue
            if t.tree_block[cz, cx]:
                continue
            y = float(t.height[cz, cx])
            if y < REG.SEA_LEVEL + 3.0 or slope_grid[cz, cx] > 1.15:
                continue
            # A belt field rather than uniform scatter: high-frequency noise in
            # one direction and low in the other gives lines of trees along the
            # contour instead of a uniform wood, which is what the painting has.
            if belt_field[cz, cx] < 0.60:
                continue
            if _rand(seed, key + "k") > 0.72:
                continue
            distance = math.hypot(x - REG.SPAWN[0], z - REG.SPAWN[1])
            tier = "low" if lod == "far" else (
                "high" if distance < 130.0 else "mid" if distance < 300.0 else "low")
            variant = int(_rand(seed, key + "v") * 3) % 3
            yaw = _rand(seed, key + "r") * 6.2
            scale = 0.8 + _rand(seed, key + "s") * 0.5
            _place(build, f"Tree_{iu:03d}_{iv:03d}_Wood",
                   f"Tree_{tier}_{variant}_Wood", x, z, y=y - 0.15,
                   rotation=yaw, scale=scale,
                   collides=(tier == "high"), kind="tree")
            canopy = f"Tree_{tier}_{variant}_Canopy"
            if canopy in build.meshes:
                _place(build, f"Tree_{iu:03d}_{iv:03d}_Canopy", canopy,
                       x, z, y=y - 0.15, rotation=yaw, scale=scale,
                       collides=False, kind="foliage")
            count += 1
    build.notes.append(f"trees placed: {count}")

    if lod == "far":
        return
    # ground dressing: thrift and thorn on the turf, weed along the tide line
    build.add_mesh("Scrub", P.undergrowth_patch(radius=1.2, count=5,
                                                seed=seed + 621))
    dressed = 0
    for iu in range(0, int(8.6 * 24.0 * REG.SCALE / 11.0)):
        for iv in range(0, int(7.8 * 24.0 * REG.SCALE / 11.0)):
            u = -0.3 + iu * 11.0 / (24.0 * REG.SCALE)
            v = -0.3 + iv * 11.0 / (24.0 * REG.SCALE)
            x, z = REG._design_to_world(REG.cell(u, v))
            cx = int(np.clip((x - t.x0) / t.cell, 0, t.cols - 1))
            cz = int(np.clip((z - t.z0) / t.cell, 0, t.rows - 1))
            y = float(t.height[cz, cx])
            if y < REG.SEA_LEVEL + 1.0 or t.tree_block[cz, cx]:
                continue
            if t.surface[cz, cx] in (TER.PAVING, TER.PATH):
                continue
            if _rand(seed, f"d{iu}:{iv}") > 0.30:
                continue
            _place(build, f"Scrub_{iu:03d}_{iv:03d}", "Scrub", x, z, y=y,
                   rotation=_rand(seed, f"dr{iu}:{iv}") * 6.2,
                   collides=False, kind="foliage")
            dressed += 1
    build.notes.append(f"ground dressing placed: {dressed}")


# ------------------------------------------------------------------- props
def populate_props(build, seed: int = 0) -> None:
    """Dockside clutter - detail-board panel 10 and the working quay."""
    quay_y = REG.LEVEL["quay"]
    build.add_mesh("Barrel", P.barrel(seed=seed + 701))
    build.add_mesh("Crate", P.crate(size=0.72, seed=seed + 703,
                                    material="timber_grey"))
    build.add_mesh("Sack", P.sack(seed=seed + 705))
    build.add_mesh("Fishing_Gear", P.fishing_gear(seed=seed + 707))
    build.add_mesh("Cart", P.cart(seed=seed + 709))
    build.add_mesh("Rowing_Boat", P.rowing_boat(seed=seed + 711))
    build.add_mesh("Brazier", P.brazier(seed=seed + 713))
    build.add_mesh("Workbench", P.workbench(seed=seed + 715))
    build.add_mesh("Coiled_Rope", HA.coiled_rope(radius=0.62, turns=5,
                                                 seed=seed + 717))
    build.add_mesh("Chain_Run", HA.chain_run(length=2.2, links=11,
                                             seed=seed + 719))

    front = REG.QUAYSIDE
    total = 0.0
    lengths = [0.0]
    for i in range(len(front) - 1):
        total += float(np.linalg.norm(front[i + 1] - front[i]))
        lengths.append(total)

    pool = ("Barrel", "Crate", "Sack", "Fishing_Gear", "Cart", "Brazier",
            "Workbench")
    for i in range(96):
        s = total * (i + 0.5) / 96.0
        p = _polyline_point(front, lengths, s)
        x = p[0] + (_rand(seed, f"pq{i}x") - 0.5) * 14.0
        z = p[1] + 1.5 + (_rand(seed, f"pq{i}z")) * 7.0
        # The harbour service court is a clear gathering place.
        if 15 < x < 60 and -9 < z < 18:
            continue
        y = _ground(build, x, z)
        if abs(y - quay_y) > 1.4:
            continue
        # Keep the scatter out of the chandlery still-life. Panel 10 is a macro
        # of one deliberate arrangement, and a random workbench landing across
        # it is the difference between a composed shot and a junk pile.
        if math.hypot(x - REG.ANCHORS["chandlery"][0],
                      z - REG.ANCHORS["chandlery"][1]) < 7.0:
            continue
        name = pool[int(_rand(seed, f"pq{i}n") * len(pool)) % len(pool)]
        _place(build, f"Prop_Quay_{i:03d}", name, x, z, y=y,
               rotation=_rand(seed, f"pq{i}r") * 6.2, collides=False,
               kind="prop")

    # The chandlery still-life of panel 10: a tight composed cluster, not a
    # scatter. The panel is a copper-bound crate, coiled rope, chain and fish on
    # sailcloth; rope and chain are the two the region had no prop for at all,
    # which is why this shot was the weakest of the ten.
    cx, cz = REG.ANCHORS["chandlery"]
    for i, (dx, dz, name, rot) in enumerate((
            (0.0, 0.0, "Crate", 0.35), (0.9, 0.4, "Crate", 1.10),
            (-0.8, 0.5, "Barrel", 0.0), (0.3, -0.9, "Fishing_Gear", 2.2),
            (1.6, -0.3, "Sack", 0.8), (-1.5, -0.4, "Barrel", 0.0),
            (-0.1, 1.1, "Coiled_Rope", 0.6), (1.15, 1.25, "Coiled_Rope", 2.1),
            (0.75, -1.6, "Chain_Run", 0.25), (-1.0, -1.3, "Chain_Run", 1.35))):
        _place(build, f"Prop_Chandlery_{i:02d}", name, cx + dx, cz + dz,
               y=quay_y, rotation=rot, collides=False, kind="prop")

    # rowing boats drawn up on the beach and moored along the harbour edge
    for i, (u, v) in enumerate(((6.60, 4.96), (6.80, 4.98), (6.44, 5.00),
                                (1.30, 4.74), (2.60, 4.76), (4.10, 4.78))):
        x, z = REG._design_to_world(REG.cell(u, v))
        y = _ground(build, x, z)
        _place(build, f"Prop_Boat_{i:02d}", "Rowing_Boat", x, z,
               y=max(y, REG.SEA_LEVEL - 0.15),
               rotation=_rand(seed, f"bt{i}") * 6.2, collides=False,
               kind="prop")


# ---------------------------------------------------------------- metadata
def populate_metadata(build, seed: int = 0) -> None:
    """Interactives and harvestables. Editor/visual only; the server spawns."""
    t = build.terrain

    interactive_plan = [
        ("westhaven-harbour-bell", "Harbour Bell", "bell", "main_quay", 3.0),
        ("westhaven-tide-board", "Tide Board", "notice", "custom_house", 4.0),
        ("westhaven-market-scales", "Market Scales", "workstation",
         "fish_market", 3.0),
        # On the quay behind the pier root, not on the pier: an interactive
        # inside the pier's footprint records the terrain height under the deck.
        ("westhaven-crane-winch", "Crane Winch", "workstation", "chandlery", 3.0),
        ("westhaven-yard-forge", "Yard Forge", "forge", "shipyard", 5.0),
        ("westhaven-ropewalk-wheel", "Ropewalk Wheel", "workstation",
         "ropewalk", 3.0),
        ("westhaven-guild-ledger", "Guild Ledger", "notice", "guild_hall", 3.0),
        ("westhaven-lamp-store", "Lamp Store", "container",
         "lighthouse_yard", 3.0),
        ("westhaven-cistern", "Street Cistern", "water", "lower_square", 4.0),
        ("westhaven-chapel-font", "Chapel Font", "shrine", "upland_chapel", 2.5),
    ]
    for ident, label, kind, anchor, radius in interactive_plan:
        centre = REG.ANCHORS[anchor]
        angle = _rand(seed, ident) * math.tau
        x = centre[0] + math.cos(angle) * radius
        z = centre[1] + math.sin(angle) * radius
        y = float(t.height_at(x, z))
        build.interactives.append({
            "id": ident, "name": label, "type": kind,
            "position": [round(x, 2), round(y, 2), round(z, 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "authority": "server"})

    harvest_plan = [
        ("westhaven-mussel-bed", "Mussel Bed", "shellfish", (6.70, 5.02), 5),
        ("westhaven-crab-pots", "Crab Pots", "shellfish", (5.90, 4.86), 4),
        ("westhaven-kelp-shallows", "Kelp Shallows", "plant", (7.20, 5.20), 6),
        ("westhaven-salt-pans", "Salt Pans", "mineral", (6.20, 4.72), 4),
        ("westhaven-thrift-turf", "Sea Thrift", "plant", (1.10, 1.70), 6),
        ("westhaven-gull-eggs", "Gull Eggs", "forage", (1.80, 6.20), 4),
        ("westhaven-driftwood", "Driftwood", "wood", (2.60, 6.90), 5),
        ("westhaven-limpet-rocks", "Limpet Rocks", "shellfish", (6.50, 6.90), 5),
    ]
    for ident, label, kind, (u, v), nodes in harvest_plan:
        centre = REG._design_to_world(REG.cell(u, v))
        for i in range(nodes):
            angle = _rand(seed, f"{ident}{i}a") * math.tau
            r = 4.0 + _rand(seed, f"{ident}{i}r") * 16.0
            x = centre[0] + math.cos(angle) * r
            z = centre[1] + math.sin(angle) * r
            y = float(t.height_at(x, z))
            build.harvestables.append({
                "id": f"{ident}-{i}", "name": label, "type": kind,
                "position": [round(x, 2), round(y, 2), round(z, 2)],
                "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                               int(round(REG.SERVER_ORIGIN[1] - z))],
                "authority": "server"})
