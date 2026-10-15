#!/usr/bin/env python3
"""Build the Four Gates production map package.

Outputs, into ``eloria-assets/maps/four-gates/``:

    world.glb        self-contained glTF 2.0 environment (embedded textures)
    world.json       schema-1 manifest consumed by the Godot ``WorldLoader``
    collision.bin    EWCG walk grid for the legacy/server collision contract
    minimap.webp     cartography derived from the final geometry

Run:  python3 eloria-assets/tools/four_gates/build_four_gates.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import interior_index as INDEX   # noqa: E402
import kits            # noqa: E402
import landmarks       # noqa: E402
import layout          # noqa: E402
import meshlib as M    # noqa: E402
import manifest as manifest_module               # noqa: E402
import terrain as T    # noqa: E402
from assembly import MaterialLibrary, SceneBuilder   # noqa: E402
from gltf_writer import GLB                          # noqa: E402
from meshlib import Geo                              # noqa: E402

TAU = math.pi * 2.0

ASSET_ID = "four-gates"
ASSET_NAME = "Four Gates"
ASSET_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# Preserved verbatim from the existing development server binding so the new
# geometry drops in without any protocol or server-profile change.
# Four Gates answers the server at one metre per tile, as every other
# Nymara map already did. Its 714.4 m island is 120 map tiles - 720 walk
# tiles - so a tile is a metre and the client needs no per-map
# conversion to talk to it. The origin is the island's centre.
COORDINATE_TRANSFORM = {
    "metresPerTile": 1.0,
    "serverOrigin": [360.0, 360.0],
    "origin": [0.0, 31.15, 0.0],
    "walkingHeight": 31.15,
    "invertServerY": True,
}

WALL_R = T.WALL_RADIUS
GATE_R = WALL_R
PLATEAU_Y = T.PLATEAU_Y
PLAZA_LIFT = 0.06           # paving carried clear of the plateau surface
BRIDGE_LIFT = 0.04          # bridge decks carried clear of the causeway
WATER_Y = T.WATER_Y
CAUSEWAY_Y = T.CAUSEWAY_Y

GATES = [
    # id,              node,               angle (rad),  outward yaw
    ("north", "Gate_North", -math.pi / 2),
    ("south", "Gate_South_Inner", math.pi / 2),
    ("east", "Gate_East", 0.0),
    ("west", "Gate_West", math.pi),
]
CARDINAL_NAMES = {0.0: "East", math.pi / 2: "South", math.pi: "West",
                  -math.pi / 2: "North"}


def _yaw_for(angle: float) -> float:
    """Rotate a +Z-facing kit so its passage runs radially outward."""
    return -angle + math.pi * 0.5


def interiors_kit_sign(p, slots: int) -> Geo:
    import interiors as interior_kit
    return interior_kit.sign_board(slots, p, width=1.9)


class WorldBuild:
    def __init__(self, out_dir: str, texture_size: int, hero_size: int,
                 cache_dir: Optional[str], lod: int = 1):
        self.out_dir = out_dir
        self.lod = lod
        self.glb = GLB("Eloria Four Gates production map builder")
        self.library = MaterialLibrary(self.glb, size=texture_size, hero=hero_size,
                                       cache_dir=cache_dir)
        self.scene = SceneBuilder(self.glb, self.library)
        self.p = self.library.palette
        self.mats = self.library.indices
        self.field = T.TerrainField()
        self.groups: Dict[str, List[int]] = {}
        self.collision_nodes: List[str] = []
        self.landmark_records: List[dict] = []
        self.animations: List[dict] = []
        self._collision_index = 0
        self._collision_extents: Dict[str, tuple] = {}
        self.collision_coverage = 0.0

    # ------------------------------------------------------------------ helpers
    def add(self, group: str, node: int) -> int:
        self.groups.setdefault(group, []).append(node)
        return node

    def ground(self, x: float, z: float) -> float:
        return float(self.field.height(np.array([float(x)]), np.array([float(z)]))[0])

    def plaza_surface(self, x: float, z: float) -> float:
        """Top of the plaza paving under a point, for standing dressing on it.

        Plaza dressing used to be hung off a flat PLATEAU_Y + 0.96, which is
        neither the apron nor the terrace nor the ground beyond the disc, so
        every bench, statue, planter and lamp floated 0.5 to 1.0 m in the air.
        """
        radius = math.hypot(x, z)
        if radius > layout.PLAZA_RADIUS:
            return self.ground(x, z)
        surface = PLATEAU_Y + PLAZA_LIFT
        if radius <= layout.PLAZA_RADIUS * landmarks.PLAZA_TERRACE_FRACTION:
            surface += landmarks.PLAZA_TERRACE_RISE
        return surface

    def collider(self, name: str, x: float, z: float, sx: float, sy: float,
                 sz: float, yaw: float = 0.0, y: Optional[float] = None) -> None:
        """Add an inset box proxy fully enclosed by its parent geometry."""
        base = self.ground(x, z) if y is None else y
        mesh = self.scene.mesh(
            f"ColliderBox_{sx:.1f}x{sy:.1f}x{sz:.1f}",
            lambda: M.box(sx, sy, sz, self.mats["stone_rubble"], 4.0, origin="corner"),
            )
        node_name = f"COLLISION_{name}"
        self.scene.instance(node_name, mesh, (x, base - 0.4, z), yaw)
        self.collision_nodes.append(node_name)
        self._collision_extents[node_name] = (sx * 0.5, sz * 0.5, yaw)
        self.add("Collision", self.glb.node_id(node_name))

    # ------------------------------------------------------------------ terrain
    def build_terrain(self) -> None:
        geo = T.build_terrain(self.field, self.mats)
        mesh = self.scene.mesh("Terrain_Surface_Mesh", geo)
        self.add("Terrain", self.scene.instance("Terrain_Surface", mesh))

        water = T.build_water(self.mats)
        water_mesh = self.scene.mesh("Water_Ring_Mesh", water)
        self.add("Water", self.scene.instance("Water_Ring_Surface", water_mesh))

        for index, (angle, cos_a, sin_a) in enumerate(T.waterfall_positions()):
            geo = T.build_waterfall(self.field, self.mats, angle)
            mesh = self.scene.mesh(f"Waterfall_Mesh_{index:02d}", geo)
            name = f"Waterfall_{index:02d}"
            self.add("Waterfalls", self.scene.instance(name, mesh))
            r = (T.PLATEAU_EDGE + T.CLIFF_FOOT) * 0.5
            self.add("Waterfalls", self.glb.add_node(
                f"FX_Waterfall_Mist_{index:02d}",
                translation=(cos_a * r, WATER_Y + 8.0, sin_a * r),
                extras={"effect": "waterfall-mist"}))

    # -------------------------------------------------------------------- roads
    def build_roads(self) -> None:
        # Carriageways cross one another, so each class gets its own datum: the
        # radials and diagonals run just under the plaza apron, which covers
        # their inner ends, and the ring roads pass just over them.  Authoring
        # every surface at one height left the plaza, the four avenues and the
        # rings exactly coplanar wherever they met, and they z-fought.
        lift = PLAZA_LIFT
        y = PLATEAU_Y + lift
        radial_y = y - 0.03
        ring_y = y + 0.03

        plaza = self.scene.mesh("Plaza_Disc_Mesh",
                                landmarks.plaza_disc(self.p, layout.PLAZA_RADIUS),
                                uv_locked=True)
        self.add("Plaza", self.scene.instance("Plaza_Disc", plaza, (0.0, y, 0.0)))

        for index, radius in enumerate(layout.RING_ROADS):
            band = M.ring_band(radius - layout.RING_HALF, radius + layout.RING_HALF,
                               192, lambda x, z: ring_y, self.mats["paving_road"], 1.0)
            mesh = self.scene.mesh(f"Road_Ring_Mesh_{index}", band)
            self.add("Roads", self.scene.instance(f"Road_Ring_{index}", mesh))

        # The avenues stop a little inside the plaza rim so the paving mandala
        # covers their ends without a gap; they never reach the centre, so the
        # four of them no longer overlap each other there either.
        for angle in layout.CARDINALS:
            name = CARDINAL_NAMES[angle if angle <= math.pi else angle - TAU]
            pts = [(math.cos(angle) * r, math.sin(angle) * r)
                   for r in np.linspace(layout.PLAZA_RADIUS - 4.0, WALL_R + 26.0, 40)]
            strip = M.quad_strip(pts, layout.AVENUE_HALF * 2.0, lambda x, z: radial_y,
                                 self.mats["paving_ceremonial"], 1.0)
            # map the inlay bands across the carriageway, repeating along it
            span = layout.AVENUE_HALF * 2.0
            axis = 0 if abs(math.cos(angle)) < 0.5 else 2
            across = strip.v[:, 0] if axis == 0 else strip.v[:, 2]
            along = strip.v[:, 2] if axis == 0 else strip.v[:, 0]
            strip.t = np.stack([across / span + 0.5, along / span],
                               axis=1).astype(np.float32)
            mesh = self.scene.mesh(f"Road_Radial_Mesh_{name}", strip, uv_locked=True)
            self.add("Roads", self.scene.instance(f"Road_Radial_{name}", mesh))

        for index, angle in enumerate(layout.DIAGONALS):
            pts = [(math.cos(angle) * r, math.sin(angle) * r)
                   for r in np.linspace(layout.PLAZA_RADIUS - 4.0, WALL_R - 8.0, 24)]
            strip = M.quad_strip(pts, layout.STREET_HALF * 2.0,
                                 lambda x, z: radial_y,
                                 self.mats["paving_road"], 1.0)
            mesh = self.scene.mesh(f"Road_Diagonal_Mesh_{index}", strip)
            self.add("Roads", self.scene.instance(f"Road_Diagonal_{index}", mesh))

        # Approach roads run from the gate to the near abutment and from the far
        # abutment up to the rim portal. The span between them is carried by the
        # bridge deck, so the carriageway never dives through the water ring.
        spans = {
            "inner": (WALL_R - 10.0, T.BRIDGE_NEAR + 2.0),
            "outer": (T.BRIDGE_FAR - 2.0, T.RIM_CREST + 24.0),
        }
        for angle in layout.CARDINALS:
            name = CARDINAL_NAMES[angle if angle <= math.pi else angle - TAU]
            for part, (r0, r1) in spans.items():
                if part == "outer" and name == "North":
                    r1 = T.SANCTUARY_SHELF_R - 54.0
                pts = [(math.cos(angle) * r, math.sin(angle) * r)
                       for r in np.linspace(r0, r1, 44)]
                strip = M.quad_strip(pts, 26.0,
                                     lambda x, z: self.ground(x, z) + 0.10,
                                     self.mats["paving_ceremonial"], 1.0)
                axis = 0 if abs(math.cos(angle)) < 0.5 else 2
                across = strip.v[:, 0] if axis == 0 else strip.v[:, 2]
                along = strip.v[:, 2] if axis == 0 else strip.v[:, 0]
                strip.t = np.stack([across / 26.0 + 0.5, along / 26.0],
                                   axis=1).astype(np.float32)
                mesh = self.scene.mesh(f"Road_Approach_Mesh_{name}_{part}", strip,
                                       uv_locked=True)
                self.add("Roads", self.scene.instance(
                    f"Road_Approach_{name}_{part}", mesh))

    # -------------------------------------------------------------------- walls
    def build_walls(self) -> None:
        segments = 48
        seg_len = TAU * WALL_R / segments
        wall_mesh = self.scene.mesh(
            "Wall_Segment_Mesh",
            lambda: kits.wall_segment(seg_len * 1.02, 17.0, 7.0, self.p))
        tower_mesh = self.scene.mesh(
            "Wall_Tower_Mesh", lambda: kits.wall_tower(6.6, 23.0, self.p))
        gate_angles = [g[2] for g in GATES]
        tower_every = 6
        for i in range(segments):
            angle = TAU * i / segments
            skip = any(layout.angle_gap(angle, ga) * WALL_R < 30.0 for ga in gate_angles)
            if skip:
                continue
            x, z = math.cos(angle) * WALL_R, math.sin(angle) * WALL_R
            name = f"Wall_Segment_{i:02d}"
            self.add("City_Walls", self.scene.instance(
                name, wall_mesh, (x, PLATEAU_Y - 1.0, z), _yaw_for(angle)))
            self.collider(f"Wall_{i:02d}", x, z, 7.4, 17.0, seg_len, _yaw_for(angle),
                          y=PLATEAU_Y - 1.0)
            if i % tower_every == 0:
                tx, tz = math.cos(angle) * WALL_R, math.sin(angle) * WALL_R
                tname = f"Wall_Tower_{i // tower_every:02d}"
                self.add("City_Walls", self.scene.instance(
                    tname, tower_mesh, (tx, PLATEAU_Y - 1.4, tz), _yaw_for(angle)))

    # -------------------------------------------------------------------- gates
    def build_gates(self) -> None:
        gate_mesh = self.scene.mesh("Gatehouse_Mesh", lambda: kits.gatehouse(self.p))
        gate_mesh_v1 = self.scene.mesh(
            "Gatehouse_Outer_Mesh",
            lambda: kits.gatehouse(self.p, width=40.0, depth=18.0, height=27.0,
                                   variant=1))
        portcullis_mesh = self.scene.mesh(
            "Portcullis_Mesh", lambda: kits.portcullis(self.p, 12.0, 16.6))

        placements = [(gid, node, angle, GATE_R, gate_mesh) for gid, node, angle in GATES]
        # the southern approach carries a second, outer gate on the causeway
        placements.append(("south-outer", "Gate_South_Outer", math.pi / 2, 596.0,
                           gate_mesh_v1))

        for gate_id, node_name, angle, radius, mesh in placements:
            x, z = math.cos(angle) * radius, math.sin(angle) * radius
            base = self.ground(x, z)
            yaw = _yaw_for(angle)
            self.add("Gates", self.scene.instance(node_name, mesh, (x, base, z), yaw))
            pc_name = f"{node_name}_Portcullis"
            self.add("Gates", self.scene.instance(
                pc_name, portcullis_mesh, (x, base + 0.2, z), yaw))
            # solid piers either side of the passage
            for side in (-1, 1):
                ox = -math.sin(angle) * side * 16.5
                oz = math.cos(angle) * side * 16.5
                self.collider(f"{node_name}_Pier_{'L' if side < 0 else 'R'}",
                              x + ox, z + oz, 16.0, 24.0, 19.0, yaw, y=base)
            self._animate_portcullis(pc_name, base)
            self.landmark_records.append({
                "id": gate_id, "name": node_name.replace("_", " "),
                "node": node_name, "type": "gate",
                "position": [round(x, 2), round(base, 2), round(z, 2)],
            })

    def _animate_portcullis(self, node_name: str, base: float) -> None:
        node = self.glb.node_id(node_name)
        x, y, z = self.glb.nodes[node].get("translation", [0.0, 0.0, 0.0])
        times = np.array([0.0, 2.5, 5.0], dtype=np.float32)
        values = np.array([[x, y, z], [x, y + 12.4, z], [x, y, z]], dtype=np.float32)
        self.animations.append({
            "name": f"{node_name}_OpenClose",
            "channels": [{"node": node, "path": "translation",
                          "times": times, "values": values}],
        })

    # ------------------------------------------------------------------ bridges
    def build_bridges(self) -> None:
        near, far = T.BRIDGE_NEAR, T.BRIDGE_FAR
        length = far - near
        centre_r = (near + far) * 0.5
        span = landmarks.bridge_span(self.p, length, CAUSEWAY_Y, WATER_Y,
                                     width=30.0, arches=4)
        deck_geo = M.box(30.0, 1.7, length, self.mats["paving_road"], 4.0,
                         origin="corner")
        span_mesh = self.scene.mesh("Bridge_Span_Mesh", span)
        self.bridge_standard_mesh = self.scene.mesh(
            "Bridge_Crystal_Standard_Mesh",
            lambda: kits.crystal_standard(self.p, 6.0))
        deck_mesh = self.scene.mesh("Bridge_Deck_Mesh", deck_geo)
        for gate_id, node_name, angle in GATES:
            name = CARDINAL_NAMES[angle if angle <= math.pi else angle - TAU]
            x, z = math.cos(angle) * centre_r, math.sin(angle) * centre_r
            yaw = _yaw_for(angle)
            self.add("Bridges", self.scene.instance(
                f"Bridge_{name}", span_mesh, (x, CAUSEWAY_Y, z), yaw))
            # Carried clear of the causeway the same way the carriageways are:
            # the deck runs out onto ground authored at exactly CAUSEWAY_Y, and
            # at that height its top and the causeway were one surface.
            self.add("Bridges", self.scene.instance(
                f"Deck_Bridge_{name}", deck_mesh,
                (x, CAUSEWAY_Y + BRIDGE_LIFT - 1.7, z), yaw))
            for side in (-1, 1):
                ox = -math.sin(angle) * side * 14.6
                oz = math.cos(angle) * side * 14.6
                self.collider(f"Bridge_{name}_Parapet_{'L' if side < 0 else 'R'}",
                              x + ox, z + oz, 1.6, 2.8, length, yaw, y=CAUSEWAY_Y)
            for step in range(6):
                t = (step + 0.5) / 6.0
                r = near + (far - near) * t
                for side in (-1, 1):
                    px = math.cos(angle) * r - math.sin(angle) * side * 13.4
                    pz = math.sin(angle) * r + math.cos(angle) * side * 13.4
                    self.add("Bridges", self.scene.instance(
                        f"Bridge_{name}_Standard_{step}_{'L' if side < 0 else 'R'}",
                        self.bridge_standard_mesh, (px, CAUSEWAY_Y + 1.5, pz)))

    # -------------------------------------------------------------------- plaza
    def build_plaza(self) -> None:
        monument = self.scene.mesh("Plaza_Monument_Mesh",
                                   lambda: landmarks.plaza_monument(self.p))
        crystal = self.scene.mesh("Plaza_Crystal_Mesh",
                                  lambda: landmarks.plaza_crystal(self.p))
        monument_y = self.plaza_surface(0.0, 0.0)
        self.add("Plaza", self.scene.instance("Plaza_Monument", monument,
                                              (0.0, monument_y, 0.0)))
        crystal_node = self.scene.instance("Plaza_Monument_Crystal", crystal,
                                           (0.0, monument_y + 60.0, 0.0))
        self.add("Plaza", crystal_node)
        self.collider("Plaza_Monument", 0.0, 0.0, 19.0, 14.0, 19.0,
                      y=monument_y)
        times = np.array([0.0, 1.6, 3.2], dtype=np.float32)
        values = np.array([[1, 1, 1], [1.14, 1.2, 1.14], [1, 1, 1]], dtype=np.float32)
        self.animations.append({
            "name": "Plaza_Monument_Crystal_Pulse",
            "channels": [{"node": crystal_node, "path": "scale",
                          "times": times, "values": values}]})

        fountain = self.scene.mesh("Fountain_Mesh", lambda: kits.fountain(self.p))
        statue = self.scene.mesh("Statue_Mesh",
                                 lambda: kits.hooded_statue(6.4, self.p))
        bench = self.scene.mesh("Bench_Mesh", lambda: kits.bench(self.p))
        planter = self.scene.mesh("Planter_Mesh", lambda: kits.planter(self.p))
        lamp = self.scene.mesh("Lamp_Mesh", lambda: kits.crystal_lamp(6.2, self.p))

        for i in range(4):
            a = math.pi / 4 + TAU * i / 4
            r = 52.0
            self.add("Plaza", self.scene.instance(
                f"Plaza_Fountain_{i}", fountain,
                (math.cos(a) * r, self.plaza_surface(math.cos(a) * r, math.sin(a) * r),
                 math.sin(a) * r)))
        for i in range(8):
            a = TAU * i / 8 + math.pi / 8
            r = 68.0
            self.add("Plaza", self.scene.instance(
                f"Plaza_Statue_{i}", statue,
                (math.cos(a) * r, self.plaza_surface(math.cos(a) * r, math.sin(a) * r),
                 math.sin(a) * r),
                _yaw_for(a)))
        for i in range(24):
            a = TAU * i / 24
            r = 40.0
            self.add("Plaza", self.scene.instance(
                f"Plaza_Bench_{i:02d}", bench,
                (math.cos(a) * r, self.plaza_surface(math.cos(a) * r, math.sin(a) * r),
                 math.sin(a) * r),
                _yaw_for(a)))
        for i in range(16):
            a = TAU * i / 16 + 0.2
            r = 76.0
            self.add("Plaza", self.scene.instance(
                f"Plaza_Planter_{i:02d}", planter,
                (math.cos(a) * r, self.plaza_surface(math.cos(a) * r, math.sin(a) * r),
                 math.sin(a) * r)))
        for i in range(16):
            a = TAU * i / 16 + 0.1
            r = layout.PLAZA_RADIUS - 3.0
            self.add("Plaza", self.scene.instance(
                f"Plaza_Lamp_{i:02d}", lamp,
                (math.cos(a) * r, self.plaza_surface(math.cos(a) * r, math.sin(a) * r),
                 math.sin(a) * r)))

        # arcaded porticos enclosing the plaza between the four avenues
        arcade_radius = layout.PLAZA_RADIUS + 20.0
        sweep = math.pi * 0.34
        arcade_mesh = self.scene.mesh(
            "Plaza_Arcade_Mesh",
            lambda: landmarks.plaza_arcade(self.p, arcade_radius, sweep, bays=9))
        for i, angle in enumerate(layout.DIAGONALS):
            # On the paving datum, not on the plateau itself: the portico's
            # stylobate is a flat annulus the size of the building's footprint,
            # and left at PLATEAU_Y it was coplanar with the ground under it.
            node = self.scene.instance(
                f"Plaza_Arcade_{i}", arcade_mesh,
                (0.0, PLATEAU_Y + PLAZA_LIFT, 0.0), angle * -1.0)
            self.add("Plaza", node)
            for k in (-1, 1):
                a = angle + k * sweep * 0.42
                cx = math.cos(a) * arcade_radius
                cz = math.sin(a) * arcade_radius
                self.collider(f"Plaza_Arcade_{i}_{'L' if k < 0 else 'R'}",
                              cx, cz, 9.0, 12.0, 22.0, _yaw_for(a),
                              y=PLATEAU_Y)

        # market awnings and dressing around the plaza rim
        awning_mesh = self.scene.mesh("Plaza_Awning_Mesh",
                                      lambda: kits.awning(7.0, 3.6, self.p))
        stall_mesh = self.scene.mesh("Plaza_Stall_Mesh",
                                     lambda: kits.market_stall(self.p, 1))
        for i in range(20):
            a = TAU * i / 20 + 0.15
            r = layout.PLAZA_RADIUS + 9.0
            if min(layout.angle_gap(a, c) for c in layout.CARDINALS) * r < 22.0:
                continue
            x, z = math.cos(a) * r, math.sin(a) * r
            self.add("Plaza", self.scene.instance(
                f"Plaza_Awning_{i:02d}", awning_mesh,
                (x, PLATEAU_Y + 4.6, z), _yaw_for(a) + math.pi))
            self.add("Plaza", self.scene.instance(
                f"Plaza_Stall_{i:02d}", stall_mesh,
                (x, PLATEAU_Y, z), _yaw_for(a)))

    # ---------------------------------------------------------------- districts
    def build_districts(self) -> None:
        p = self.p
        builders = {
            "civic_hall": lambda v: kits.civic_hall(p, 26.0, 18.0, v),
            "market_hall": lambda v: kits.market_hall(p, 20.0, 13.0),
            "townhouse_large": lambda v: kits.townhouse(
                p, 12.0, 14.0, 4, v,
                p.roof_verdigris if v % 2 == 0 else p.roof_slate),
            "townhouse": lambda v: kits.townhouse(
                p, 9.5, 11.0, 3, v,
                p.roof_verdigris if v % 3 else p.roof_slate),
            "townhouse_small": lambda v: kits.townhouse(
                p, 8.0, 9.0, 2, v,
                p.roof_slate if v % 2 else p.roof_tile),
            "farmhouse": lambda v: kits.farmhouse(p, 11.0, 8.0, v),
            "granary": lambda v: kits.granary(p),
            "warehouse": lambda v: kits.warehouse(p),
        }
        heights = {"civic_hall": 24.0, "market_hall": 11.0, "townhouse_large": 18.0,
                   "townhouse": 14.4, "townhouse_small": 10.0, "farmhouse": 8.0,
                   "granary": 8.0, "warehouse": 9.0}
        district_group = {"civic": "District_Civic", "residential": "District_Residential",
                          "agricultural": "District_Agricultural",
                          "service": "District_Service"}
        for place in layout.generate_buildings():
            variant = place.variant if place.kind != "granary" else 0
            key = f"{place.kind}_v{variant}"
            mesh = self.scene.mesh(key, lambda k=place.kind, v=variant: builders[k](v))
            district = layout.quadrant(place.angle)
            group = district_group[district]
            base = self.ground(place.x, place.z)
            node_name = f"{group}_{place.name}"
            self.add(group, self.scene.instance(
                node_name, mesh, (place.x, base, place.z), place.yaw))
            self.collider(f"B_{place.name}", place.x, place.z,
                          place.width - 0.12, heights[place.kind],
                          place.depth - 0.12, place.yaw, y=base)

    # --------------------------------------------------------------- sanctuary
    def build_sanctuary(self) -> None:
        z = -T.SANCTUARY_SHELF_R
        base = T.SANCTUARY_Y
        temple = self.scene.mesh("Sanctuary_Mesh", lambda: landmarks.sanctuary(self.p))
        # The temple carries its own paved terrace, so it stands on the same
        # paving datum the plaza uses rather than flat on the authored shelf,
        # which the shelf meets to within a couple of millimetres.
        self.add("Sanctuary", self.scene.instance(
            "Northern_Sanctuary", temple, (0.0, base + PLAZA_LIFT, z)))
        terrace = M.cylinder(52.0, 0.5, 32, self.mats["paving_plaza"], 6.0)
        terrace_mesh = self.scene.mesh("Sanctuary_Terrace_Mesh", terrace)
        self.add("Sanctuary", self.scene.instance(
            "Deck_Sanctuary_Terrace", terrace_mesh, (0.0, base - 0.4, z)))

        energy = self.scene.mesh("Sanctuary_Portal_Mesh",
                                 lambda: landmarks.sanctuary_portal_energy(self.p))
        portal_node = self.scene.instance("Sanctuary_Portal", energy,
                                          (0.0, base + 5.0, z - 0.2))
        self.add("Sanctuary", portal_node)

        beacon = self.scene.mesh("Beacon_Mesh", lambda: landmarks.beacon(self.p))
        flame = self.scene.mesh("Beacon_Flame_Mesh",
                                lambda: landmarks.beacon_flame(self.p))
        self.add("Sanctuary", self.scene.instance(
            "Sanctuary_Beacon", beacon, (0.0, base + 39.6, z - 14.0)))
        flame_node = self.scene.instance("Sanctuary_Beacon_Flame", flame,
                                         (0.0, base + 62.0, z - 14.0))
        self.add("Sanctuary", flame_node)
        times = np.array([0.0, 1.8, 3.6], dtype=np.float32)
        values = np.array([[1, 1, 1], [1.18, 1.34, 1.18], [1, 1, 1]], dtype=np.float32)
        self.animations.append({
            "name": "Sanctuary_Beacon_Pulse",
            "channels": [{"node": flame_node, "path": "scale",
                          "times": times, "values": values}]})
        self.collider("Sanctuary_Body", 0.0, z - 14.0, 44.0, 30.0, 28.0, y=base)

        # the ceremonial climb from the causeway up to the shelf, laid directly
        # on the authored ramp
        rise = base - CAUSEWAY_Y
        run = (T.SANCTUARY_SHELF_R - 10.0) - T.SANCTUARY_CLIMB_START
        stair = landmarks.ceremonial_stair(self.p, 26.0, rise, run, flights=5)
        stair_mesh = self.scene.mesh("Sanctuary_Stair_Mesh", stair)
        self.add("Sanctuary", self.scene.instance(
            "Stair_Sanctuary_Approach", stair_mesh,
            (0.0, CAUSEWAY_Y, -T.SANCTUARY_CLIMB_START)))

    # -------------------------------------------------------------- vegetation
    def build_vegetation(self) -> None:
        broadleaf = [self.scene.mesh(
            f"Tree_Broadleaf_{i}",
            lambda i=i: kits.broadleaf_tree(self.p, 8.0 + i * 0.9, 20 + i))
            for i in range(4)]
        pines = [self.scene.mesh(
            f"Tree_Pine_{i}", lambda i=i: kits.pine_tree(self.p, 12.0 + i * 2.0, 40 + i))
            for i in range(3)]
        hedge = self.scene.mesh("Hedge_Mesh", lambda: kits.hedge(self.p, 5.0))
        shrub = self.scene.mesh("Shrub_Mesh", lambda: kits.shrub(self.p))
        cypress = [self.scene.mesh(
            f"Tree_Cypress_{i}",
            lambda i=i: kits.cypress_tree(self.p, 11.0 + i * 1.8, 60 + i))
            for i in range(3)]
        rng = np.random.default_rng(5150)
        # formal cypress rows down each ceremonial avenue and along the causeways
        cypress_index = 0
        for angle in layout.CARDINALS:
            radii = list(np.arange(layout.PLAZA_RADIUS + 22.0, 348.0, 17.0))
            radii += list(np.arange(T.PLATEAU_EDGE + 8.0, T.BRIDGE_NEAR, 15.0))
            radii += list(np.arange(T.BRIDGE_FAR + 6.0, T.RIM_CREST, 15.0))
            for radius in radii:
                for side in (-1, 1):
                    offset = layout.AVENUE_HALF + 4.6
                    x = math.cos(angle) * radius - math.sin(angle) * offset * side
                    z = math.sin(angle) * radius + math.cos(angle) * offset * side
                    base = self.ground(x, z)
                    if base < WATER_Y + 2.0:
                        continue
                    self.add("Vegetation", self.scene.instance(
                        f"Tree_Cypress_{cypress_index:04d}",
                        cypress[cypress_index % 3], (x, base, z),
                        float(rng.uniform(0, TAU))))
                    cypress_index += 1
        for index, (x, z, height, kind) in enumerate(layout.tree_positions()):
            base = self.ground(x, z)
            if base < WATER_Y + 1.0:
                continue
            scale = height / (10.0 if kind == "broadleaf" else 14.0)
            mesh = (broadleaf[index % len(broadleaf)] if kind == "broadleaf"
                    else pines[index % len(pines)])
            self.add("Vegetation", self.scene.instance(
                f"Tree_{kind}_{index:04d}", mesh, (x, base, z),
                float(rng.uniform(0, TAU)), scale=(scale, scale, scale)))
        for i in range(90):
            angle = float(rng.uniform(0, TAU))
            radius = float(rng.uniform(layout.PLAZA_RADIUS + 6.0, 330.0))
            if not layout.clear_of_roads(radius, angle, margin=1.0):
                continue
            x, z = math.cos(angle) * radius, math.sin(angle) * radius
            self.add("Vegetation", self.scene.instance(
                f"Hedge_{i:03d}", hedge, (x, self.ground(x, z), z), -angle))
        for i in range(160):
            angle = float(rng.uniform(0, TAU))
            radius = float(rng.uniform(layout.PLAZA_RADIUS + 4.0, 344.0))
            x, z = math.cos(angle) * radius, math.sin(angle) * radius
            self.add("Vegetation", self.scene.instance(
                f"Shrub_{i:03d}", shrub, (x, self.ground(x, z), z)))

    # -------------------------------------------------------------------- props
    def build_props(self) -> None:
        p = self.p
        lamp = self.scene.mesh("Crystal_Standard_Mesh",
                               lambda: kits.crystal_standard(p, 7.4))
        stall = [self.scene.mesh(f"Market_Stall_{i}",
                                 lambda i=i: kits.market_stall(p, i)) for i in range(3)]
        crate = self.scene.mesh("Crate_Mesh", lambda: kits.crate(p))
        barrel = self.scene.mesh("Barrel_Mesh", lambda: kits.barrel(p))
        cart = self.scene.mesh("Cart_Mesh", lambda: kits.handcart(p))
        well = self.scene.mesh("Well_Mesh", lambda: kits.well(p))
        sign = self.scene.mesh("Sign_Mesh", lambda: kits.signboard(p))
        bollard = self.scene.mesh("Bollard_Mesh", lambda: kits.bollard(p))
        rail = self.scene.mesh("HitchRail_Mesh", lambda: kits.hitching_rail(p))
        fence = self.scene.mesh("Fence_Mesh", lambda: kits.fence_run(p, 8.0, 5))
        hay = self.scene.mesh("Hay_Mesh", lambda: kits.hay_stack(p))
        dock = self.scene.mesh("Dock_Mesh", lambda: kits.dock_platform(p))
        crane = self.scene.mesh("Crane_Mesh", lambda: kits.harbour_crane(p))
        boulder = [self.scene.mesh(f"Boulder_{i}",
                                   lambda i=i: kits.boulder(p, 1.6 + i * 0.9, 70 + i))
                   for i in range(3)]
        banner_pole = self.scene.mesh(
            "Banner_Pole_Mesh",
            lambda: Geo.concat([
                M.cylinder(0.28, 13.0, 8, self.mats["timber_dark"], 1.0),
                kits.banner(3.0, 8.0, p, pole=False).translate(0.0, 12.2, 0.0),
                kits.finial(2.0, 0.42, p).translate(0.0, 13.0, 0.0)]))

        rng = np.random.default_rng(8080)
        for index, (x, z, yaw) in enumerate(layout.avenue_lamp_positions()):
            self.add("Props", self.scene.instance(
                f"Street_Lamp_{index:03d}", lamp, (x, self.ground(x, z), z)))

        # market squares along the ring roads
        market_angles = [math.pi * 0.86, math.pi * 1.06, math.pi * 0.62,
                         math.pi * 1.34, math.pi * 0.18, math.pi * 1.72]
        stall_index = 0
        for m, angle in enumerate(market_angles):
            radius = layout.RING_ROADS[m % 2] + 24.0
            cx, cz = math.cos(angle) * radius, math.sin(angle) * radius
            for k in range(9):
                ox = float(rng.uniform(-16.0, 16.0))
                oz = float(rng.uniform(-13.0, 13.0))
                x, z = cx + ox, cz + oz
                self.add("Props", self.scene.instance(
                    f"Market_Stall_{stall_index:03d}", stall[k % 3],
                    (x, self.ground(x, z), z), float(rng.uniform(0, TAU))))
                stall_index += 1
            for k in range(7):
                x = cx + float(rng.uniform(-19.0, 19.0))
                z = cz + float(rng.uniform(-15.0, 15.0))
                mesh = crate if k % 2 == 0 else barrel
                self.add("Props", self.scene.instance(
                    f"Market_Goods_{m}_{k}", mesh, (x, self.ground(x, z), z),
                    float(rng.uniform(0, TAU))))
            self.add("Props", self.scene.instance(
                f"Market_Well_{m}", well, (cx, self.ground(cx, cz), cz)))
            self.add("Props", self.scene.instance(
                f"Market_Sign_{m}", sign, (cx + 12.0, self.ground(cx + 12.0, cz), cz),
                float(rng.uniform(0, TAU))))
            self.add("Props", self.scene.instance(
                f"Market_Cart_{m}", cart, (cx - 11.0, self.ground(cx - 11.0, cz), cz),
                float(rng.uniform(0, TAU))))

        # ceremonial banner poles down the four avenues
        pole_index = 0
        for angle in layout.CARDINALS:
            for radius in np.arange(layout.PLAZA_RADIUS + 30.0, 340.0, 46.0):
                for side in (-1, 1):
                    off = layout.AVENUE_HALF + 5.4
                    x = math.cos(angle) * radius - math.sin(angle) * off * side
                    z = math.sin(angle) * radius + math.cos(angle) * off * side
                    self.add("Props", self.scene.instance(
                        f"Avenue_Banner_{pole_index:03d}", banner_pole,
                        (x, self.ground(x, z), z), _yaw_for(angle)))
                    pole_index += 1

        # bollards lining the ceremonial south avenue
        for i, radius in enumerate(np.arange(layout.PLAZA_RADIUS + 8.0, 340.0, 9.0)):
            for side in (-1, 1):
                x = -math.sin(math.pi / 2) * (layout.AVENUE_HALF + 1.6) * side
                z = radius
                self.add("Props", self.scene.instance(
                    f"Avenue_Bollard_{i:03d}_{'L' if side < 0 else 'R'}", bollard,
                    (x, self.ground(x, z), z)))

        # agricultural dressing
        for index, (x, z, w, d, yaw) in enumerate(layout.farm_plots()):
            base = self.ground(x, z)
            # Keyed on the size it is, not on a rotating index: six cache slots
            # shared by forty plots of different sizes handed most of them the
            # first plot's plane, which then ran over its neighbours and fought
            # with them. Whole metres keep the cache small.
            w, d = float(round(w)), float(round(d))
            mesh = self.scene.mesh(f"Farm_Plot_Mesh_{w:.0f}x{d:.0f}",
                                   lambda w=w, d=d: M.plane(
                                       w, d, self.mats["terrain_crop"], 1.0, 0.05, 3),
                                   )
            self.add("Props", self.scene.instance(
                f"Farm_Plot_{index:02d}", mesh, (x, base + 0.08, z), yaw))
            self.add("Props", self.scene.instance(
                f"Farm_Fence_{index:02d}", fence,
                (x + w * 0.5 + 1.0, base, z), yaw))
            if index % 3 == 0:
                self.add("Props", self.scene.instance(
                    f"Farm_Hay_{index:02d}", hay,
                    (x - w * 0.4, base, z + d * 0.4)))
            if index % 4 == 1:
                self.add("Props", self.scene.instance(
                    f"Farm_Rail_{index:02d}", rail,
                    (x, base, z - d * 0.5 - 1.5), yaw))

        # service quarter docks on the northern shelf below the cliff
        for i in range(4):
            angle = -math.pi / 2 + (i - 1.5) * 0.16
            radius = T.CLIFF_FOOT + 14.0
            x, z = math.cos(angle) * radius, math.sin(angle) * radius
            self.add("Props", self.scene.instance(
                f"Service_Dock_{i}", dock, (x, WATER_Y - 0.4, z), _yaw_for(angle)))
            self.add("Props", self.scene.instance(
                f"Service_Crane_{i}", crane, (x, WATER_Y + 2.6, z), _yaw_for(angle)))

        # scattered rock detail on the cliffs and rim
        for i in range(150):
            angle = float(rng.uniform(0, TAU))
            radius = float(rng.uniform(T.PLATEAU_EDGE, T.CLIFF_FOOT + 40.0))
            x, z = math.cos(angle) * radius, math.sin(angle) * radius
            base = self.ground(x, z)
            self.add("Props", self.scene.instance(
                f"Cliff_Boulder_{i:03d}", boulder[i % 3], (x, base, z),
                float(rng.uniform(0, TAU))))

    # ------------------------------------------------------- interior doorways
    def build_interior_doors(self) -> None:
        """A shopfront, a trade sign and a door marker at each interior entry.

        The door marker is what the manifest portal references; the shopfront
        gives the entrance a silhouette on the street so a player can find it
        without reading the map.
        """
        p = self.p
        front = self.scene.mesh(
            "Shopfront_Mesh",
            lambda: kits.townhouse(p, 11.0, 12.0, 2, 2, p.roof_verdigris))
        porch = self.scene.mesh("Porch_Mesh", lambda: Geo.concat([
            M.box(4.6, 0.35, 2.4, self.mats["stone_trim"], 1.5, origin="corner"),
            M.box(0.5, 3.4, 0.5, self.mats["timber_dark"], 1.0, origin="corner")
             .translate(-1.9, 0.35, 0.9),
            M.box(0.5, 3.4, 0.5, self.mats["timber_dark"], 1.0, origin="corner")
             .translate(1.9, 0.35, 0.9),
            M.box(4.8, 0.4, 2.8, self.mats["roof_verdigris"], 1.6, origin="corner")
             .translate(0.0, 3.75, 0.5)]))
        lamp = self.scene.mesh("Shopfront_Lamp_Mesh",
                               lambda: kits.crystal_lamp(4.6, p))
        signs = {}
        for entry in INDEX.INTERIORS:
            slots = int(entry["signSlots"])
            key = f"Trade_Sign_{slots}"
            if key not in signs:
                signs[key] = self.scene.mesh(
                    key, lambda slots=slots: interiors_kit_sign(p, slots))
            x, _y, z = entry["door"]
            base = self.ground(x, z)
            yaw = float(entry["yaw"])
            ident = entry["id"]
            # the shopfront sits just behind the threshold
            bx = x - math.cos(yaw + math.pi * 0.5) * 7.4
            bz = z + math.sin(yaw + math.pi * 0.5) * 7.4
            self.add("Interiors", self.scene.instance(
                f"Shopfront_{ident}", front, (bx, self.ground(bx, bz), bz), yaw))
            self.collider(f"Shopfront_{ident}", bx, bz, 10.9, 10.0, 11.9, yaw,
                          y=self.ground(bx, bz))
            self.add("Interiors", self.scene.instance(
                f"Porch_{ident}", porch, (x, base, z), yaw))
            self.add("Interiors", self.scene.instance(
                f"Sign_{ident}", signs[key], (x, base + 3.6, z), yaw))
            for side in (-1, 1):
                lx = x - math.sin(yaw) * 2.6 * side
                lz = z + math.cos(yaw) * 2.6 * side
                self.add("Interiors", self.scene.instance(
                    f"Shopfront_Lamp_{ident}_{'L' if side < 0 else 'R'}", lamp,
                    (lx, self.ground(lx, lz), lz)))
            self.add("Markers", self.glb.add_node(
                f"Door_{ident}", translation=(x, base + 0.02, z),
                extras={"interior": ident, "quarter": entry["quarter"]}))

    # ------------------------------------------------------------------ markers
    def build_markers(self) -> None:
        markers = {
            "Spawn_Player_Plaza": (0.0, 55.0),
            "Spawn_Player_South_Gate": (0.0, 310.0),
            "POI_Sanctuary": (0.0, -T.SANCTUARY_SHELF_R + 8.0),
            "POI_Central_Plaza": (0.0, 0.0),
        }
        for name, (x, z) in markers.items():
            self.add("Markers", self.glb.add_node(
                name, translation=(x, self.ground(x, z) + 0.02, z)))
        for gate_id, node_name, angle in GATES:
            for label, radius in (("Approach", GATE_R + 34.0), ("Inner", GATE_R - 34.0)):
                x, z = math.cos(angle) * radius, math.sin(angle) * radius
                self.add("Markers", self.glb.add_node(
                    f"Marker_{node_name}_{label}",
                    translation=(x, self.ground(x, z) + 0.02, z)))

    # -------------------------------------------------------------------- build
    def run(self) -> dict:
        self.build_terrain()
        self.build_roads()
        self.build_walls()
        self.build_gates()
        self.build_bridges()
        self.build_plaza()
        self.build_districts()
        self.build_sanctuary()
        self.build_vegetation()
        self.build_props()
        self.build_interior_doors()
        self.build_markers()

        group_nodes = []
        for group in ["Terrain", "Water", "Waterfalls", "Roads", "Plaza", "City_Walls",
                      "Gates", "Bridges", "District_Civic", "District_Residential",
                      "District_Agricultural", "District_Service",
                      "Sanctuary", "Vegetation", "Props", "Interiors", "Markers",
                      "Collision"]:
            children = self.groups.get(group, [])
            if children:
                group_nodes.append(self.glb.add_node(group, children=children))
        root = self.glb.add_node("Four_Gates_Root", children=group_nodes)
        self.glb.scene_roots = [root]

        for animation in self.animations:
            self.glb.add_animation(animation["name"], animation["channels"])

        os.makedirs(self.out_dir, exist_ok=True)
        stats = self.glb.save(os.path.join(self.out_dir, "world.glb"))
        stats["instances"] = self.scene.stats["instances"]
        stats["visibleTriangles"] = self.scene.stats["visibleTriangles"]
        stats["textureMemoryBytes"] = self._texture_memory()
        stats["collisionProxies"] = len(self.collision_nodes)
        stats.pop("path", None)
        self.write_manifest(stats)
        self.write_collision_grid()
        return stats

    # ------------------------------------------------------------------ package
    def _texture_memory(self) -> int:
        """Uncompressed RGBA8 footprint of the exported maps, including mips."""
        from assembly import DEFAULT_RESOLUTION, MATERIAL_RESOLUTIONS
        total = 0
        for name, material in self.library.sets.items():
            side = min(MATERIAL_RESOLUTIONS.get(name, DEFAULT_RESOLUTION),
                       material.base.size[0])
            maps = 3 + (1 if material.emissive is not None else 0)
            total += int(side * side * 4 * maps * 4 / 3)
        return total

    def world_bounds(self) -> dict:
        edge = T.WORLD_EDGE + 18.0
        lo = self.field.height(np.array([0.0]), np.array([0.0]))
        sample_x, sample_z = np.meshgrid(np.linspace(-edge, edge, 96),
                                         np.linspace(-edge, edge, 96))
        heights = self.field.height(sample_x, sample_z)
        return {"min": [-round(edge, 1), round(float(heights.min()) - 6.0, 1),
                        -round(edge, 1)],
                "max": [round(edge, 1), round(float(heights.max()) + 78.0, 1),
                        round(edge, 1)]}

    def write_manifest(self, stats: dict) -> None:
        data = manifest_module.build(
            stats=stats, bounds=self.world_bounds(),
            landmark_records=self.landmark_records,
            collision_nodes=sorted(self.collision_nodes),
            coordinate_transform=COORDINATE_TRANSFORM,
            asset_id=ASSET_ID, asset_name=ASSET_NAME,
            asset_version=ASSET_VERSION, schema_version=SCHEMA_VERSION)
        path = os.path.join(self.out_dir, "world.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")

    def write_collision_grid(self) -> None:
        """EWCG walk grid on the map's own server grid.

        Version 2 of the format, and the same convention every other Eloria map
        package writes: half a metre per cell, cell (cx, cz) centred on server
        tile ((cx + 0.5) / 2, (cz + 0.5) / 2), byte 0 meaning blocked and
        anything else an elevation of `value * 0.2 - 2.2` metres.

        Version 1 of this file answered the coordinate system the map was first
        built in - 1536 cells of half a *2.15 metre* tile about an origin of
        384 - and kept answering it after the map moved to a metre a tile about
        an origin of 360. Read at face value it put the city about a third of a
        map from where the server thought it was, which is why the server-side
        reader carries an explicit remap for it. The layout now comes from
        COORDINATE_TRANSFORM, so it moves when the map does.
        """
        metres_per_tile = COORDINATE_TRANSFORM["metresPerTile"]
        origin_x, origin_z = COORDINATE_TRANSFORM["serverOrigin"]
        # The server's own grid, at two collision cells to the tile.
        tiles_wide = int(round(origin_x * 2))
        size = tiles_wide * 2
        cells = np.arange(size)
        tiles = (cells + 0.5) * 0.5
        xs = (tiles - origin_x) * metres_per_tile
        # invertServerY: server y runs north to south, so row 0 is the +Z edge.
        zs = (origin_z - tiles) * metres_per_tile
        gx, gz = np.meshgrid(xs, zs, indexing="xy")
        heights = self.field.height(gx, gz)
        radius = np.hypot(gx, gz)

        walkable = np.ones(heights.shape, dtype=bool)
        # water and anything below the shoreline is impassable
        walkable &= heights > (WATER_Y + 1.2)
        # steep ground: reject where the local gradient exceeds the agent slope
        grad_x = np.gradient(heights, axis=1)
        grad_z = np.gradient(heights, axis=0)
        # np.gradient is per cell; the cell is half a metre wide now, not the
        # 1.075 m the old grid used, so the divisor moves with it or every
        # slope reads twice as steep as it is.
        slope = np.hypot(grad_x, grad_z) / (0.5 * metres_per_tile)
        walkable &= slope < 0.70
        # the monument footprint
        walkable &= radius > 11.0
        # the curtain wall ring except at the gates
        angle = np.arctan2(gz, gx)
        gate_gap = np.zeros(angle.shape, dtype=bool)
        for _, _, gate_angle in GATES:
            delta = np.abs((angle - gate_angle + math.pi) % TAU - math.pi)
            gate_gap |= delta * np.maximum(radius, 1.0) < 13.0
        in_wall = (radius > WALL_R - 4.2) & (radius < WALL_R + 4.2)
        walkable &= ~(in_wall & ~gate_gap)
        # building footprints
        for name in self.collision_nodes:
            node = self.glb.nodes[self.glb.node_id(name)]
            if "translation" not in node:
                continue
        # (building blockers come from the proxy list below, vectorised)
        for cx, cz, half_x, half_z, yaw in self._collision_footprints():
            dx = gx - cx
            dz = gz - cz
            ca, sa = math.cos(-yaw), math.sin(-yaw)
            lx = dx * ca - dz * sa
            lz = dx * sa + dz * ca
            inside = (np.abs(lx) < half_x) & (np.abs(lz) < half_z)
            walkable &= ~inside

        # Metres at the ELM's own 0.2 m step. The plateau sits near 31 m, so
        # the byte runs past the 63 the ELM height field can hold; the server
        # rebases the map on its own lowest walkable tile when it folds this
        # onto its grid, which is where that loss belongs.
        encoded = np.clip(np.round((heights + 2.2) / 0.2), 1, 255)
        payload = np.where(walkable, encoded, 0).astype(np.uint8)
        header = struct.pack("<4sHHII", b"EWCG", 2, 0, size, size)
        with open(os.path.join(self.out_dir, "collision.bin"), "wb") as handle:
            handle.write(header)
            handle.write(payload.tobytes())
        self.collision_coverage = float((payload > 0).mean())

    def _collision_footprints(self):
        out = []
        for name in self.collision_nodes:
            node = self.glb.nodes[self.glb.node_id(name)]
            translation = node.get("translation", [0.0, 0.0, 0.0])
            extents = self._collision_extents.get(name)
            if extents is None:
                continue
            half_x, half_z, yaw = extents
            out.append((translation[0], translation[2], half_x, half_z, yaw))
        return out


def main() -> None:
    # The old WorldBuild class remains the native kit/reference implementation.
    # The package itself is now composed once through the shared region toolkit.
    # Keep the historical command usable without regenerating the720m layout.
    from pathlib import Path
    compact = Path(__file__).resolve().parents[2] / 'maps/four-gates/source/rebuild_landscape.py'
    os.execv(sys.executable, [sys.executable, str(compact), *sys.argv[1:]])
    parser = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.abspath(os.path.join(here, "..", "..", "maps", "four-gates"))
    parser.add_argument("--out", default=default_out)
    parser.add_argument("--texture-size", type=int, default=512)
    parser.add_argument("--hero-size", type=int, default=1024)
    parser.add_argument("--cache", default=os.environ.get("FOUR_GATES_TEXCACHE", ""))
    args = parser.parse_args()
    build = WorldBuild(args.out, args.texture_size, args.hero_size,
                       args.cache or None)
    stats = build.run()
    stats["collisionNodes"] = len(build.collision_nodes)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
