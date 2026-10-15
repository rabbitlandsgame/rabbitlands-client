"""Whitehorn Range placement passes.

Largest to smallest, as the production guide orders it: primary landmarks,
then the crossings, then satellite locations, then roadside markers, then
vegetation, then props.

Everything is placed against the finished heightfield, never at an absolute Y,
so a change to the terrain moves the buildings with it rather than leaving
them buried or floating.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as P
from amberwood import stonework as SW
from amberwood import terrain as TER
from regionbuild import Placement, RegionBuild

import kit
import region as REG


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed & 0x7FFFFFFF)


def _ground(build: RegionBuild, x: float, z: float) -> float:
    return float(build.terrain.height_at(x, z))


def _facing(from_xz, to_xz) -> float:
    """Rotation about Y so a piece built facing -Z looks at `to_xz`.

    `mesh.rotation_y(theta)` maps the -Z front normal to (-sin, 0, -cos), as
    can be checked by rotating (0, 0, -1) through it: at 90 degrees the front
    points at -X. So aiming the front along (dx, dz) needs
    -sin = dx and -cos = dz, i.e. atan2(-dx, -dz).

    The sign on dx matters: atan2(dx, -dz) mirrors every piece about the Z
    axis, which pointed the mine portal, the ice cave and all three shrines
    away from the things they are supposed to face.
    """
    dx = to_xz[0] - from_xz[0]
    dz = to_xz[1] - from_xz[1]
    return math.atan2(-dx, -dz)


def _place(build: RegionBuild, node: str, mesh_key: str, mesh, x: float,
           z: float, *, rotation_y: float = 0.0, scale: float = 1.0,
           y_offset: float = 0.0, kind: str = "prop", collides: bool = False,
           walk_surface: bool = False, landmark: str | None = None,
           y: float | None = None) -> Placement:
    build.add_mesh(mesh_key, mesh)
    height = _ground(build, x, z) if y is None else y
    return build.place(Placement(
        node=node, mesh=mesh_key,
        position=(round(x, 3), round(height + y_offset, 3), round(z, 3)),
        rotation_y=rotation_y, scale=scale, collides=collides,
        walk_surface=walk_surface, kind=kind, landmark=landmark))


def _landmark(build: RegionBuild, ident: str, name: str, node: str,
              x: float, z: float, kind: str, y_offset: float = 0.0,
              y: float | None = None) -> None:
    """Record a landmark marker.

    `y` must be the height a player actually meets the landmark at, not the
    raw terrain height, wherever the landmark carries its own walk surface.
    A marker left on the ground under a bridge deck or a temple podium reads
    as "landmark below surface" in verify_runtime, because it is.
    """
    height = _ground(build, x, z) + y_offset if y is None else y + y_offset
    build.landmarks.append({
        "id": ident, "name": name, "node": node, "type": kind,
        "position": [round(x, 2), round(height, 2), round(z, 2)],
        "authority": "client-visual",
    })


# --------------------------------------------------------------------------
def populate(build: RegionBuild, seed: int = 20260828,
             lod: str | None = None) -> None:
    _primary_landmarks(build, seed)
    _crossings(build, seed + 101)
    _satellites(build, seed + 211)
    _roadside(build, seed + 307)
    _seracs(build, seed + 331)
    _vegetation(build, seed + 401, lod)
    _scatter(build, seed + 509, lod)
    _markers(build, seed + 601)


# -- 1. primary landmarks ---------------------------------------------------
def _primary_landmarks(build: RegionBuild, seed: int) -> None:
    t = build.terrain

    # The glacier temple, on its cut shelf, facing down the valley (south).
    tx, tz = REG.ANCHORS["temple"]
    temple = kit.glacier_temple(seed=seed, width=20.0, height=15.0)
    # kit pieces are built facing -Z. The temple is approached from the south,
    # so it has to be turned to face down the valley; at rotation 0 a player
    # coming up the road meets the mountain mass behind it, not the facade.
    _place(build, "Landmark_glacier_temple", "glacier_temple", temple, tx, tz,
           rotation_y=math.pi, kind="landmark", collides=True,
           landmark="whitehorn-glacier-temple")
    # the forecourt deck is the surface a player stands on here
    _landmark(build, "whitehorn-glacier-temple", "Glacier Temple",
              "Landmark_glacier_temple", tx, tz, "temple", y_offset=2.22)

    # The southern gate: the threshold the approach road passes through.
    gx, gz = REG.ANCHORS["south_gate"]
    gate = kit.gate_arch(seed=seed + 3, span=6.0, height=8.0)
    _place(build, "Landmark_south_gate", "whitehorn_gate", gate, gx, gz,
           rotation_y=0.0, kind="landmark", collides=True,
           landmark="whitehorn-south-gate")
    _landmark(build, "whitehorn-south-gate", "Whitehorn Gate",
              "Landmark_south_gate", gx, gz, "gate")

    # The mine, cut into the eastern massif, facing its yard.
    mx, mz = REG.ANCHORS["mine"]
    portal = kit.mine_portal(seed=seed + 5)
    _place(build, "Landmark_mine_portal", "whitehorn_mine", portal, mx, mz,
           rotation_y=_facing((mx, mz), REG.ANCHORS["mine_yard"]),
           kind="landmark", collides=True, landmark="whitehorn-mine")
    _landmark(build, "whitehorn-mine", "Whitehorn Mine",
              "Landmark_mine_portal", mx, mz, "mine")

    # The ice cave in the west.
    cx, cz = REG.ANCHORS["ice_cave"]
    cave = kit.ice_cave_mouth(seed=seed + 7, approach_drop=1.7)
    _place(build, "Landmark_ice_cave", "whitehorn_ice_cave", cave, cx, cz,
           rotation_y=_facing((cx, cz), REG.ANCHORS["lower_cairns"]),
           kind="landmark", collides=True, landmark="whitehorn-ice-cave")
    _landmark(build, "whitehorn-ice-cave", "Whitehorn Ice Cave",
              "Landmark_ice_cave", cx, cz, "cave")

    # The frozen cascades hanging off the glacier's shoulders.
    for index, (anchor, width, height) in enumerate((
            ("frozen_falls", 11.0, 20.0), ("upper_falls", 8.0, 15.0))):
        fx, fz = REG.ANCHORS[anchor]
        fx,fz,fy = getattr(t,"cascade_sites",{}).get(anchor,(fx,fz,float(t.height_at(fx,fz))))
        fall = kit.frozen_cascade(width=width, height=height,
                                  seed=seed + 11 + index, include_pool=False)
        node = f"Landmark_frozen_cascade_{index:02d}"
        # Same trap as the temple: the piece is built facing -Z, with its rock
        # backing behind it at positive local z. Placed unrotated on a valley
        # approached from the south, the backing ends up between the camera
        # and the ice, and the fall renders as a plain grey slab.
        _place(build, node, f"frozen_cascade_{index:02d}", fall, fx, fz,
               rotation_y=math.pi, kind="landmark", collides=True, y=fy,
               landmark=f"whitehorn-frozen-cascade-{index:02d}")
        _landmark(build, f"whitehorn-frozen-cascade-{index:02d}",
                  "Frozen Cascade", node, fx, fz, "natural", y=fy)



def _crossings(build: RegionBuild, seed: int) -> None:
    import layout
    layout.dress_crossings(build, seed)


# -- 3. satellite locations -------------------------------------------------
def _satellites(build: RegionBuild, seed: int) -> None:
    # The three shrines: gate, north and east.
    for index, (anchor, faces) in enumerate((
            ("gate_shrine", "south_gate"),
            ("north_shrine", "temple"),
            ("east_shrine", "mine_yard"))):
        sx, sz = REG.ANCHORS[anchor]
        shrine = kit.shrine_alcove(seed=seed + index * 7)
        node = f"Landmark_shrine_{index:02d}"
        _place(build, node, f"shrine_{index:02d}", shrine, sx, sz,
               rotation_y=_facing((sx, sz), REG.ANCHORS[faces]),
               kind="landmark", collides=True,
               landmark=f"whitehorn-shrine-{index:02d}")
        _landmark(build, f"whitehorn-shrine-{index:02d}", "Whitehorn Shrine",
                  node, sx, sz, "shrine")

    # Watch points and camps: light structures on the cut ground.
    rng = _rng(seed + 31)
    for index, anchor in enumerate(("west_watch", "overlook", "bridge_watch")):
        ax, az = REG.ANCHORS[anchor]
        tower = SW.MeshGroup()
        tower.add(M.box((2.6, 3.2, 2.6), center=(0.0, 1.6, 0.0), uv_scale=1.2,
                        material=kit.RUBBLE))
        tower.add(M.box((3.2, 0.3, 3.2), center=(0.0, 3.35, 0.0), uv_scale=1.1,
                        material=kit.STONE))
        tower.add(kit.cairn(1.1, seed=seed + index).transformed(
            M.translation(0.0, 3.5, 0.0)))
        node = f"Structure_watch_{index:02d}"
        _place(build, node, f"watch_{index:02d}", tower, ax, az,
               rotation_y=rng.random() * math.tau, kind="building",
               collides=True)

    for index, anchor in enumerate(("south_camp", "east_camp", "mine_yard")):
        ax, az = REG.ANCHORS[anchor]
        for j in range(3):
            angle = j * math.tau / 3.0 + rng.random()
            radius = 3.4 + rng.random() * 2.0
            x = ax + math.cos(angle) * radius
            z = az + math.sin(angle) * radius
            crate = P.crate(size=0.7, seed=seed + index * 10 + j,
                            material=kit.TIMBER)
            _place(build, f"Prop_camp_crate_{index:02d}_{j}",
                   f"camp_crate_{index:02d}_{j}", crate, x, z,
                   rotation_y=rng.random() * math.tau, kind="prop")
        brazier = P.brazier(seed=seed + index)
        _place(build, f"Prop_camp_brazier_{index:02d}",
               f"camp_brazier_{index:02d}", brazier, ax + 1.6, az + 1.2,
               kind="prop")


# -- 4. roadside markers ----------------------------------------------------
def _roadside(build: RegionBuild, seed: int) -> None:
    """Cairns along every route and dense on the ridges. Panels 1, 5 and 9."""
    rng = _rng(seed)
    t = build.terrain
    made = 0

    for route_name, points in REG.ROUTES.items():
        # walk the polyline at a fixed spacing and drop cairns alternating side
        spacing = 12.0 if route_name in ("approach_road", "temple_road") else 19.0
        total = 0.0
        segments = []
        for i in range(len(points) - 1):
            a, b = points[i], points[i + 1]
            length = float(np.hypot(*(b - a)))
            segments.append((a, b, length))
            total += length
        distance = spacing * 0.5
        side = 1.0
        while distance < total:
            travelled = 0.0
            for a, b, length in segments:
                if travelled + length >= distance:
                    f = (distance - travelled) / max(length, 1e-6)
                    px, pz = a + (b - a) * f
                    dx, dz = (b - a) / max(length, 1e-6)
                    # offset perpendicular to the road so cairns line it
                    offset = 3.6 + rng.random() * 1.4
                    x = px - dz * offset * side
                    z = pz + dx * offset * side
                    height = 1.0 + rng.random() * 1.1
                    node = f"Prop_cairn_{made:04d}"
                    _place(build, node, f"cairn_{made % 12:02d}",
                           kit.cairn(height, seed=seed + made),
                           x, z, rotation_y=rng.random() * math.tau,
                           kind="prop")
                    made += 1
                    break
                travelled += length
            side *= -1.0
            distance += spacing

    # the cairn fields: dense clusters on the west ridge and at the lower bend
    for anchor, count, spread in (("cairn_ridge", 44, 22.0),
                                  ("lower_cairns", 22, 13.0),
                                  ("west_watch", 16, 11.0)):
        ax, az = REG.ANCHORS[anchor]
        for i in range(count):
            angle = rng.random() * math.tau
            radius = spread * math.sqrt(rng.random())
            x = ax + math.cos(angle) * radius
            z = az + math.sin(angle) * radius
            height = 0.9 + rng.random() * 1.5
            _place(build, f"Prop_cairn_{made:04d}", f"cairn_{made % 12:02d}",
                   kit.cairn(height, seed=seed + made), x, z,
                   rotation_y=rng.random() * math.tau, kind="prop")
            made += 1
        _landmark(build, f"whitehorn-cairn-field-{anchor}", "Whitehorn Cairns",
                  f"Prop_cairn_{made - 1:04d}", ax, az, "cairn-field")

    # waystones at the shrines, the falls and the ridge
    stones = 0
    for anchor, count in (("cairn_ridge", 4), ("frozen_falls", 3),
                          ("temple_forecourt", 4), ("gate_shrine", 2),
                          ("ice_cave", 2), ("north_shrine", 2)):
        ax, az = REG.ANCHORS[anchor]
        for i in range(count):
            angle = rng.random() * math.tau
            radius = 6.0 + rng.random() * 7.0
            x = ax + math.cos(angle) * radius
            z = az + math.sin(angle) * radius
            node = f"Prop_waystone_{stones:03d}"
            _place(build, node, f"waystone_{stones % 8:02d}",
                   kit.waystone(2.0 + rng.random() * 0.7, seed=seed + 900 + stones),
                   x, z, rotation_y=rng.random() * math.tau, kind="prop",
                   collides=True)
            stones += 1

    build.notes.append(f"Roadside markers: {made} cairns, {stones} waystones.")


# -- 4b. seracs -------------------------------------------------------------
def _seracs(build: RegionBuild, seed: int) -> None:
    """Broken ice along the glacier trough.

    The aerial reads as ice mainly because of the blue blocks standing on it;
    a flat ICE surface class alone photographs as a pale road. These are
    placed along the authored glacier route rather than by surface lookup, so
    they follow the ice where it drops below the snow line at the snout.
    """
    rng = _rng(seed)
    t = build.terrain
    points = REG.GLACIER
    made = 0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        length = float(np.hypot(*(b - a)))
        steps = max(2, int(length / 9.0))
        for step in range(steps):
            f = (step + rng.random()) / steps
            px, pz = a + (b - a) * f
            for _ in range(int(rng.integers(1, 4))):
                offset = (rng.random() - 0.5) * REG.GLACIER_WIDTH * REG.SCALE * 0.9
                nx, nz = (b - a) / max(length, 1e-6)
                x = px - nz * offset
                z = pz + nx * offset
                variant = int(rng.integers(0, 6))
                block = M.icosphere(1.0 + rng.random() * 1.4, subdivisions=1,
                                    material=kit.ICE)
                block.transform(M.scaling(0.8 + rng.random() * 0.6,
                                          1.1 + rng.random() * 0.9,
                                          0.8 + rng.random() * 0.6))
                _place(build, f"Prop_serac_{made:04d}", f"serac_{variant}",
                       block, x, z, rotation_y=rng.random() * math.tau,
                       y_offset=-0.35, kind="rock")
                made += 1
    build.notes.append(f"Glacier: {made} seracs along the ice.")


# -- 5. vegetation ----------------------------------------------------------
def _vegetation(build: RegionBuild, seed: int, lod: str | None) -> None:
    """Conifers on the lower southern slopes only.

    The aerial puts trees below the snow line and nowhere near the glacier, so
    placement is gated on height, slope and surface class rather than
    scattered across the map.
    """
    rng = _rng(seed)
    t = build.terrain
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)

    spacing = 11.0 if lod == "far" else 6.6
    count = 0
    x = REG.PLAY_MIN_X
    while x < REG.PLAY_MAX_X:
        z = REG.PLAY_MIN_Z
        while z < REG.PLAY_MAX_Z:
            jx = x + (rng.random() - 0.5) * spacing * 0.9
            jz = z + (rng.random() - 0.5) * spacing * 0.9
            z += spacing
            cx = int(np.clip((jx - t.x0) / t.cell, 0, t.cols - 1))
            cz = int(np.clip((jz - t.z0) / t.cell, 0, t.rows - 1))
            if t.tree_block[cz, cx]:
                continue
            height = t.height[cz, cx]
            if height > REG.SNOW_LINE + 16.0 or height < REG.VALLEY_FLOOR - 2.0:
                continue
            if slope[cz, cx] > 0.85:
                continue
            if t.surface[cz, cx] not in (TER.TURF, TER.SNOW):
                continue
            density = N.fbm(jx * 0.010, jz * 0.010, seed=seed + 3)
            habitat=getattr(t,'alpine_density',None)
            chance=.62 if habitat is None else float(habitat[cz,cx])
            if density < 0.36 or rng.random() > chance:
                continue
            tier = rng.integers(0, 6)
            _place(build, f"Tree_pine_{count:04d}", f"pine_{int(tier)}",
                   kit.pine(5.5 + rng.random() * 4.0, seed=seed + int(tier)),
                   jx, jz, rotation_y=rng.random() * math.tau,
                   scale=0.85 + rng.random() * 0.4, kind="tree", collides=True)
            count += 1
        x += spacing
    build.notes.append(f"Vegetation: {count} conifers below the snow line.")


# -- 6. rock scatter --------------------------------------------------------
def _scatter(build: RegionBuild, seed: int, lod: str | None) -> None:
    rng = _rng(seed)
    t = build.terrain
    spacing = 22.0 if lod == "far" else 13.0
    count = 0
    x = REG.PLAY_MIN_X
    while x < REG.PLAY_MAX_X:
        z = REG.PLAY_MIN_Z
        while z < REG.PLAY_MAX_Z:
            jx = x + (rng.random() - 0.5) * spacing
            jz = z + (rng.random() - 0.5) * spacing
            z += spacing
            cx = int(np.clip((jx - t.x0) / t.cell, 0, t.cols - 1))
            cz = int(np.clip((jz - t.z0) / t.cell, 0, t.rows - 1))
            if t.tree_block[cz, cx] or rng.random() > 0.45:
                continue
            surface = t.surface[cz, cx]
            if surface in (TER.PAVING, TER.MARBLE, TER.PATH):
                continue
            variant = int(rng.integers(0, 5))
            piece = P.rock_cluster(radius=1.4 + rng.random() * 1.6,
                                   count=3 + int(rng.integers(0, 3)),
                                   seed=seed + variant, material=kit.ROCK)
            _place(build, f"Prop_rocks_{count:04d}", f"rocks_{variant}", piece,
                   jx, jz, rotation_y=rng.random() * math.tau,
                   scale=0.8 + rng.random() * 0.7, kind="rock")
            count += 1
        x += spacing
    build.notes.append(f"Scatter: {count} rock clusters.")


# -- 7. metadata markers ----------------------------------------------------
def _markers(build: RegionBuild, seed: int) -> None:
    """NPCs, creatures, harvestables and portals.

    All of these are metadata carrying "authority": "server". Nothing dynamic
    is baked into the static mesh; the server owns the actual gameplay.
    """
    rng = _rng(seed)

    for ident, name, anchor, role in (
            ("whitehorn-gatekeeper", "Gate Warden", "south_gate", "guard"),
            ("whitehorn-temple-keeper", "Temple Keeper", "temple_forecourt",
             "civilian"),
            ("whitehorn-pilgrim", "Pilgrim", "north_shrine", "civilian"),
            ("whitehorn-mine-foreman", "Mine Foreman", "mine_yard", "civilian"),
            ("whitehorn-guide", "Mountain Guide", "bridge_watch", "guide"),
            ("whitehorn-cave-watch", "Cave Watch", "ice_cave", "guard")):
        ax, az = REG.ANCHORS[anchor]
        build.npc_markers.append({
            "id": ident, "name": name, "role": role,
            "position": [round(ax, 2), round(_ground(build, ax, az), 2),
                         round(az, 2)],
            "authority": "server",
        })

    for index, (anchor, kind, count) in enumerate((
            ("mine_yard", "ore", 8), ("ice_cave", "ice", 6),
            ("cairn_ridge", "herb", 5), ("frozen_falls", "ice", 4),
            ("pine_shelf", "wood", 7))):
        ax, az = REG.ANCHORS[anchor]
        for i in range(count):
            angle = rng.random() * math.tau
            radius = 5.0 + rng.random() * 14.0
            x = ax + math.cos(angle) * radius
            z = az + math.sin(angle) * radius
            build.harvestables.append({
                "id": f"whitehorn-{kind}-{index:02d}-{i:02d}",
                "resource": kind,
                "position": [round(x, 2), round(_ground(build, x, z), 2),
                             round(z, 2)],
                "authority": "server",
            })

    # Portals. Positions are pinned to the server tiles the profile's
    # maps.txt already assigns to whitehorn_range, converted through the
    # region's own transform (server_x = x + 174, server_y = 174 - z), so the
    # client marker and the server transition sit on the same cell. The server
    # owns the actual transition; these are alignment metadata.
    def _from_tile(tile_x: int, tile_y: int) -> tuple[float, float]:
        return (tile_x - REG.SERVER_ORIGIN[0]) * REG.METRES_PER_TILE,                (REG.SERVER_ORIGIN[1] - tile_y) * REG.METRES_PER_TILE

    # The portals - the three crossings and the seven doors into the insides
    # map - are declared by build_whitehorn._add_portals(), from the same
    # CROSSINGS and door table the marches and the insides build read.

    for ident, name, anchor in (
            ("whitehorn-temple-brazier", "Temple Brazier", "temple_forecourt"),
            ("whitehorn-gate-shrine-offering", "Shrine Offering",
             "gate_shrine"),
            ("whitehorn-mine-winch", "Mine Winch", "mine_yard")):
        ax, az = REG.ANCHORS[anchor]
        build.interactives.append({
            "id": ident, "name": name, "type": "use",
            "position": [round(ax, 2), round(_ground(build, ax, az), 2),
                         round(az, 2)],
            "authority": "server",
        })
