"""Ancient stone landmarks: arches, gates, bridges, terraces, fountains, ruins.

Everything is built as solids with courses, mouldings and weathering, and the
overgrown pieces carry real root geometry rather than a moss decal.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .architecture import (AMBER, CARVED, IRON, RUBBLE, SHINGLE, STONE, TIMBER,
                           TIMBER_DARK, beam, railing, steps)
from .noise import Rng

MOSS_STONE = "rubble_stone"


def _weather(mesh: M.Mesh, amount: float, seed: int) -> M.Mesh:
    """Knock the machine-perfect edges off a stone solid."""
    mesh.jitter(amount, seed=seed)
    mesh.recompute_normals(58.0)
    return mesh


def column(height: float, radius: float = 0.45, flutes: int = 12,
           material: str = STONE, base: bool = True, capital: bool = True) -> M.Mesh:
    parts = []
    shaft = M.cylinder(radius * 1.04, radius * 0.88, height, flutes, uv_scale=0.8,
                       material=material,
                       radial_profile=lambda k, n: 1.0 - 0.055 * abs(math.sin(k / n * math.pi * n)))
    parts.append(shaft)
    if base:
        parts.append(M.lathe([[radius * 1.55, 0.0], [radius * 1.55, 0.14],
                              [radius * 1.30, 0.22], [radius * 1.38, 0.34],
                              [radius * 1.06, 0.46]], 12, uv_scale=0.9, material=material))
    if capital:
        cap = M.lathe([[radius * 0.88, 0.0], [radius * 1.05, 0.16], [radius * 1.34, 0.34],
                       [radius * 1.42, 0.46], [radius * 1.42, 0.58]], 12,
                      uv_scale=0.9, material=material)
        parts.append(cap.translate(0.0, height, 0.0))
        parts.append(M.box((radius * 3.0, 0.18, radius * 3.0),
                           center=(0.0, height + 0.66, 0.0), uv_scale=0.9,
                           material=material))
    return M.merge(parts, material)


def balustrade(length: float, height: float = 1.05, material: str = STONE) -> M.Mesh:
    """Stone balustrade with turned balusters, plinth and coping."""
    parts = [M.box((length, 0.22, 0.42), center=(0.0, 0.11, 0.0), uv_scale=1.0,
                   material=material),
             M.box((length, 0.20, 0.52), center=(0.0, height, 0.0), uv_scale=1.0,
                   material=material)]
    count = max(3, int(length / 0.42))
    for i in range(count):
        x = -length * 0.5 + length * (i + 0.5) / count
        baluster = M.lathe([[0.10, 0.0], [0.135, 0.20], [0.085, 0.44],
                            [0.12, height - 0.30], [0.09, height - 0.10]],
                           6, uv_scale=1.2, material=material)
        parts.append(baluster.translate(x, 0.22, 0.0))
    return M.merge(parts, material)


def ancient_arch(span: float = 4.6, height: float = 6.2, depth: float = 1.6,
                 seed: int = 0, roots: bool = True, ruined: bool = True) -> M.Mesh:
    """Free-standing arch, weathered and overgrown by roots.

    This is the close-up reference's root-swallowed forest arch: piers built of
    courses, a moulded archivolt, a broken cornice, and living roots that grip
    the stone and reach the ground.
    """
    rng = Rng(seed)
    parts = []
    pier = (span * 0.5 + 0.55, height * 0.55)
    for sign in (-1.0, 1.0):
        x = sign * (span * 0.5 + 0.55)
        courses = 9
        for i in range(courses):
            y = i * (pier[1] / courses)
            inset = 0.0 if i % 2 else 0.05
            block = M.box((1.10 - inset, pier[1] / courses - 0.02, depth + 0.30 - inset),
                          center=(x, y + pier[1] / (courses * 2.0), 0.0),
                          uv_scale=0.9, material=STONE)
            block.translate(float(rng.normal(0.0, 0.012)), 0.0, float(rng.normal(0.0, 0.012)))
            parts.append(block)
        parts.append(M.box((1.45, 0.22, depth + 0.60), center=(x, pier[1] + 0.11, 0.0),
                           uv_scale=0.9, material=STONE))
        parts.append(M.box((1.30, 0.16, depth + 0.44), center=(x, pier[1] + 0.30, 0.0),
                           uv_scale=0.9, material=STONE))

    ring = M.arch(span + 1.10, height - pier[1] - 0.3, 0.62, depth, 16, uv_scale=0.9,
                  material=STONE)
    ring.translate(0.0, pier[1] + 0.38, 0.0)
    parts.append(ring)
    inner = M.arch(span + 0.10, height - pier[1] - 0.55, 0.28, depth + 0.24, 16,
                   uv_scale=1.3, material=CARVED)
    inner.translate(0.0, pier[1] + 0.38, 0.0)
    parts.append(inner)

    # keystone
    parts.append(M.box((0.62, 0.86, depth + 0.34),
                       center=(0.0, pier[1] + (height - pier[1] - 0.3) + 0.30, 0.0),
                       uv_scale=1.0, material=CARVED))

    if ruined:
        # a broken entablature with a missing bite out of one side
        for i in range(7):
            x = -span * 0.5 - 0.4 + (span + 0.8) * i / 6
            if i in (4, 5):
                continue
            parts.append(M.box((0.86, 0.46, depth + 0.5),
                                center=(x, height + 0.55 + float(rng.uniform(-0.06, 0.06)), 0.0),
                                uv_scale=0.9, material=STONE))
        for i in range(3):
            parts.append(M.box((float(rng.uniform(0.5, 0.9)), float(rng.uniform(0.3, 0.5)),
                                float(rng.uniform(0.5, 0.9))),
                               center=(float(rng.uniform(-span, span)), 0.16,
                                       float(rng.uniform(-depth, depth))),
                               uv_scale=1.0, material=RUBBLE))

    body = _weather(M.merge(parts, STONE), 0.020, seed + 3)

    if roots:
        root_parts = []
        for i in range(7):
            sign = 1.0 if i % 2 else -1.0
            x = sign * (span * 0.5 + 0.55)
            start_y = float(rng.uniform(pier[1] * 0.55, pier[1] + 0.9))
            z = float(rng.uniform(-depth * 0.6, depth * 0.6))
            points = [np.array([x + sign * 0.55, start_y, z])]
            radius = [float(rng.uniform(0.10, 0.20))]
            steps_count = 6
            for k in range(1, steps_count):
                t = k / (steps_count - 1)
                points.append(np.array([
                    x + sign * (0.55 + 0.55 * t + 0.5 * math.sin(t * 3.1) * 0.3),
                    start_y * (1.0 - t) - 0.15 * t,
                    z + math.sin(t * 4.0 + i) * 0.55]))
                radius.append(radius[0] * (1.0 - 0.65 * t) + 0.03)
            root_parts.append(M.tube(np.array(points), radius, segments=6, cap_end=True,
                                     uv_scale=0.8, material="bark_dark"))
        # a root crossing the crown of the arch
        crown = np.array([[-span * 0.55, height + 0.2, -depth * 0.4],
                          [-span * 0.2, height + 0.75, 0.1],
                          [span * 0.25, height + 0.7, -0.15],
                          [span * 0.6, height + 0.05, depth * 0.35]])
        root_parts.append(M.tube(crown, [0.14, 0.19, 0.17, 0.09], segments=6,
                                 cap_start=True, cap_end=True, uv_scale=0.8,
                                 material="bark_dark"))
        roots_mesh = M.merge(root_parts, "bark_dark")
        roots_mesh.recompute_normals(70.0)
        return M.merge([body, roots_mesh], STONE) if False else _combine(body, roots_mesh)
    return body


def _combine(*meshes: M.Mesh) -> M.Mesh:
    """Keep meshes with different materials separate by returning a group list."""
    group = MeshGroup()
    for piece in meshes:
        group.add(piece)
    return group


class MeshGroup(M.Mesh):
    """A mesh-like container that keeps per-material parts separate.

    The GLB exporter walks `parts` so a single authored landmark can carry
    stone, timber, iron and foliage materials without merging them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[M.Mesh] = []
        self.walk_parts: list[M.Mesh] = []
        self.overhead_parts: list[M.Mesh] = []

    def add(self, piece: M.Mesh) -> "MeshGroup":
        if isinstance(piece, MeshGroup):
            for sub in piece.parts:
                self.parts.append(sub)
            for sub in piece.walk_parts:
                self.walk_parts.append(sub)
            for sub in piece.overhead_parts:
                self.overhead_parts.append(sub)
        elif piece is not None and piece.triangle_count:
            self.parts.append(piece)
        return self

    def add_overhead(self, piece: M.Mesh) -> "MeshGroup":
        """Register a lid: a ceiling, a vault or a roof over a walkable space.

        An interior is a closed box seen from a camera above it, so its lids are
        exported as their own nodes and named for the client's cutaway block,
        which hides them. Anything the player is meant to see from inside the
        room - a hanging lamp, a truss, a boss - is `add`, not this.
        """
        if isinstance(piece, MeshGroup):
            for sub in piece.parts + piece.overhead_parts:
                self.overhead_parts.append(sub)
            for sub in piece.walk_parts:
                self.walk_parts.append(sub)
        elif piece is not None and piece.triangle_count:
            self.overhead_parts.append(piece)
        return self

    def add_walk(self, piece: M.Mesh) -> "MeshGroup":
        """Register a surface a character may stand on.

        Only these parts are exported under the navigation prefix, so the
        client's downward grounding ray snaps to a bridge deck or a platform
        floor and never to the top of an arch or a roof.
        """
        if isinstance(piece, MeshGroup):
            for sub in piece.parts + piece.walk_parts + piece.overhead_parts:
                self.walk_parts.append(sub)
        elif piece is not None and piece.triangle_count:
            self.walk_parts.append(piece)
        return self

    # -- Mesh-compatible surface ------------------------------------------
    @property
    def all_parts(self) -> list[M.Mesh]:
        return self.parts + self.walk_parts + self.overhead_parts

    @property
    def triangle_count(self) -> int:  # type: ignore[override]
        return int(sum(p.triangle_count for p in self.all_parts))

    @property
    def vertex_count(self) -> int:  # type: ignore[override]
        return int(sum(p.vertex_count for p in self.all_parts))

    def bounds(self):
        if not self.all_parts:
            return np.zeros(3), np.zeros(3)
        lows = np.vstack([p.bounds()[0] for p in self.all_parts])
        highs = np.vstack([p.bounds()[1] for p in self.all_parts])
        return lows.min(axis=0), highs.max(axis=0)

    def copy(self) -> "MeshGroup":
        out = MeshGroup()
        out.parts = [p.copy() for p in self.parts]
        out.walk_parts = [p.copy() for p in self.walk_parts]
        out.overhead_parts = [p.copy() for p in self.overhead_parts]
        return out

    def transform(self, matrix) -> "MeshGroup":
        for p in self.all_parts:
            p.transform(matrix)
        return self

    def walk_bounds(self):
        if not self.walk_parts:
            return None
        lows = np.vstack([p.bounds()[0] for p in self.walk_parts])
        highs = np.vstack([p.bounds()[1] for p in self.walk_parts])
        return lows.min(axis=0), highs.max(axis=0)

    def transformed(self, matrix) -> "MeshGroup":
        return self.copy().transform(matrix)

    def translate(self, x, y, z) -> "MeshGroup":
        return self.transform(M.translation(x, y, z))

    def rotate_y(self, radians) -> "MeshGroup":
        return self.transform(M.rotation_y(radians))

    def scale(self, x, y=None, z=None) -> "MeshGroup":
        return self.transform(M.scaling(x, y, z))

    def by_material(self, walk: bool = False,
                    overhead: bool = False) -> dict[str, M.Mesh]:
        if overhead:
            source = self.overhead_parts
        else:
            source = self.walk_parts if walk else self.parts
        buckets: dict[str, list[M.Mesh]] = {}
        for p in source:
            buckets.setdefault(p.material, []).append(p)
        return {name: M.merge(items, name) for name, items in buckets.items()}


def group(*meshes: M.Mesh) -> MeshGroup:
    out = MeshGroup()
    for piece in meshes:
        out.add(piece)
    return out


def monumental_gate(seed: int = 0, span: float = 7.0, height: float = 15.0,
                    stair_width: float = 13.0, stair_height: float = 4.2,
                    continuous_walk: bool = False) -> MeshGroup:
    """The region's central landmark: a monumental arched ruin above a grand stair.

    Read from the aerial reference - a tall arched gate with flanking towers,
    a colonnaded front, a broad ceremonial stair, water channels beside the
    approach, and trees rooted in the ruined upper storey.
    """
    rng = Rng(seed)
    stone_parts: list[M.Mesh] = []
    carved_parts: list[M.Mesh] = []

    # podium the whole monument stands on
    podium_front = 3.5
    podium=M.box((stair_width + 6.0, stair_height, 13.0),
                 center=(0.0, stair_height * 0.5, -3.0), uv_scale=0.55, material=STONE)
    walks=[]
    if continuous_walk:
        triangles=podium.indices.reshape(-1,3)
        podium.indices=triangles[np.mean(podium.normals[triangles,1],axis=1)<0.9].reshape(-1)
        half=(stair_width+6)/2
        walks.append(M.quad([(-half,stair_height,-9.5),(-half,stair_height,3.5),
                             (half,stair_height,3.5),(half,stair_height,-9.5)],material=STONE))
    stone_parts.append(podium)
    # the ceremonial stair stands in front of the podium and lands on its top
    stair_run, stair_rise = 0.40, 0.19
    stair_steps = max(1, int(round(stair_height / stair_rise)))
    stair_length = stair_steps * stair_run
    if continuous_walk:
        from .routecraft import stair_flight
        stair=stair_flight(stair_width,stair_height,stair_length,stair_steps,STONE)
        walks.append(stair.rotate_y(math.pi).translate(0,0,podium_front+stair_length))
    else:
        stair = steps(stair_width, stair_height, stair_run, stair_rise, STONE)
        stair.rotate_y(math.pi)
        stone_parts.append(stair.translate(0.0, 0.0, podium_front + stair_length))
    for sign in (-1.0, 1.0):
        cheek_length = stair_length + 2.0
        cheek = M.box((1.5, stair_height + 0.7, cheek_length),
                      center=(sign * (stair_width * 0.5 + 0.75),
                              (stair_height + 0.7) * 0.5 - 0.5,
                              podium_front + cheek_length * 0.5 - 1.0),
                      uv_scale=0.7, material=STONE)
        stone_parts.append(cheek)
        stone_parts.append(balustrade(cheek_length - 1.0, 1.05, STONE)
                           .rotate_y(math.pi * 0.5)
                           .translate(sign * (stair_width * 0.5 + 0.75),
                                      stair_height + 0.2,
                                      podium_front + cheek_length * 0.5 - 1.4))
    for sign in (-1.0, 1.0):
        channel = water_channel(stair_length + 3.0, 1.1, 0.5, seed + 71)
        channel.rotate_y(math.pi * 0.5)
        channel.translate(sign * (stair_width * 0.5 + 2.6), stair_height * 0.55,
                          podium_front + stair_length * 0.5 + 1.0)
        for piece in channel.parts:
            (stone_parts if piece.material == STONE else carved_parts).append(piece)

    base_y = stair_height
    # flanking towers
    for sign in (-1.0, 1.0):
        x = sign * (span * 0.5 + 3.1)
        tower_height = height * 0.72
        for i in range(11):
            y = base_y + i * (tower_height / 11)
            inset = 0.06 * (i % 2)
            stone_parts.append(M.box((3.5 - inset, tower_height / 11 - 0.03, 4.2 - inset),
                                     center=(x, y + tower_height / 22, 0.0),
                                     uv_scale=0.6, material=STONE))
        stone_parts.append(M.box((4.1, 0.30, 4.8), center=(x, base_y + tower_height + 0.15, 0.0),
                                 uv_scale=0.7, material=STONE))
        # ruined crown: broken merlons, some missing
        for i in range(5):
            if i == 3 and sign > 0:
                continue
            stone_parts.append(M.box((0.62, float(rng.uniform(0.5, 1.15)), 0.62),
                                     center=(x - 1.4 + i * 0.7,
                                             base_y + tower_height + 0.7, 1.7),
                                     uv_scale=0.9, material=STONE))
        for level in range(3):
            y = base_y + 2.4 + level * 3.4
            opening = M.arch(1.05, 1.5, 0.22, 4.4, 10, uv_scale=1.1, material=CARVED)
            carved_parts.append(opening.translate(x, y + 1.2, 0.0))

    # the great arch
    pier_height = height * 0.46
    for sign in (-1.0, 1.0):
        x = sign * (span * 0.5 + 0.85)
        for i in range(12):
            y = base_y + i * (pier_height / 12)
            inset = 0.05 * (i % 2)
            stone_parts.append(M.box((1.70 - inset, pier_height / 12 - 0.03, 4.0 - inset),
                                     center=(x, y + pier_height / 24, 0.0),
                                     uv_scale=0.7, material=STONE))
        carved_parts.append(column(pier_height * 0.78, 0.42, 12, CARVED)
                            .translate(x + sign * 1.0, base_y, 1.9))
    ring = M.arch(span + 1.7, height - base_y - pier_height, 0.85, 4.0, 20,
                  uv_scale=0.7, material=STONE)
    stone_parts.append(ring.translate(0.0, base_y + pier_height, 0.0))
    archivolt = M.arch(span + 0.2, height - base_y - pier_height - 0.35, 0.34, 4.5, 20,
                       uv_scale=1.2, material=CARVED)
    carved_parts.append(archivolt.translate(0.0, base_y + pier_height, 0.0))
    stone_parts.append(M.box((0.9, 1.25, 4.6),
                             center=(0.0, base_y + height - base_y + 0.2, 0.0),
                             uv_scale=0.8, material=STONE))

    # entablature above the arch, partly collapsed
    for i in range(9):
        if i in (6, 7):
            continue
        stone_parts.append(M.box((1.5, 0.62, 4.8),
                                 center=(-6.0 + i * 1.5, height + 0.9, 0.0),
                                 uv_scale=0.7, material=STONE))
    for i in range(7):
        carved_parts.append(M.box((0.44, 0.44, 5.0),
                                  center=(-4.5 + i * 1.5, height + 1.45, 0.0),
                                  uv_scale=1.2, material=CARVED))

    stone = _weather(M.merge(stone_parts, STONE), 0.018, seed + 11)
    carved = _weather(M.merge(carved_parts, CARVED), 0.012, seed + 13)
    result=group(stone, carved)
    for part in walks: result.add_walk(part)
    return result


def high_bridge(length: float = 22.0, deck_height: float = 8.5, width: float = 4.6,
                arches: int = 3, seed: int = 0, pier_foot: float = -1.5) -> MeshGroup:
    """Multi-arch stone bridge over a rocky watercourse.

    The elevation is built as a solid wall whose underside follows the arch
    intrados, so the openings are real voids in real masonry rather than free
    floating rings, and the spandrels above each arch are continuous stone.
    """
    rng = Rng(seed)
    stone_parts: list[M.Mesh] = []
    carved_parts: list[M.Mesh] = []
    span = length / arches
    slices = 22

    for i in range(arches):
        centre = -length * 0.5 + span * (i + 0.5)
        is_main = (i == arches // 2)
        clear = span * (0.80 if is_main else 0.72)
        rise = (deck_height + abs(pier_foot)) * (0.55 if is_main else 0.46)
        springing = deck_height - rise - 0.55
        step = clear / slices
        for k in range(slices):
            local = -clear * 0.5 + step * (k + 0.5)
            ratio = min(abs(local) / (clear * 0.5), 1.0)
            intrados = springing + rise * math.sqrt(max(0.0, 1.0 - ratio * ratio))
            top = deck_height - 0.05
            if top - intrados < 0.05:
                continue
            stone_parts.append(M.box((step * 1.02, top - intrados, width),
                                     center=(centre + local, (top + intrados) * 0.5, 0.0),
                                     uv_scale=0.7, material=STONE))
            # archivolt ring standing proud on both faces
            thickness = 0.42
            for face in (-1.0, 1.0):
                carved_parts.append(M.box((step * 1.02, thickness, 0.34),
                                          center=(centre + local, intrados + thickness * 0.5,
                                                  face * (width * 0.5 + 0.16)),
                                          uv_scale=1.2, material=CARVED))
        # haunches: the solid stone between the springing and the pier faces
        for sign in (-1.0, 1.0):
            haunch = (span - clear) * 0.5
            if haunch > 0.05:
                stone_parts.append(M.box((haunch, deck_height - springing,
                                          width),
                                         center=(centre + sign * (clear + haunch) * 0.5,
                                                 (deck_height + springing) * 0.5, 0.0),
                                         uv_scale=0.7, material=STONE))
        stone_parts.append(M.box((span, max(springing - pier_foot, 0.1), width * 0.30),
                                 center=(centre, (springing + pier_foot) * 0.5, 0.0),
                                 uv_scale=0.7, material=STONE))

    for i in range(arches + 1):
        x = -length * 0.5 + span * i
        pier_width = 1.6 if 0 < i < arches else 2.6
        height = deck_height - pier_foot
        stone_parts.append(M.box((pier_width, height, width + 0.5),
                                 center=(x, pier_foot + height * 0.5, 0.0),
                                 uv_scale=0.6, material=STONE))
        if 0 < i < arches:
            for face in (-1.0, 1.0):
                cut = M.extrude([[-pier_width * 0.5, 0.0], [pier_width * 0.5, 0.0],
                                 [0.0, 1.7]], height * 0.72, cap=True, uv_scale=0.8,
                                material=STONE)
                cut.rotate_x(-math.pi * 0.5)
                if face < 0:
                    cut.rotate_y(math.pi)
                stone_parts.append(cut.translate(x, pier_foot, face * (width * 0.5 + 0.25)))

    stone_parts.append(M.box((length + 1.8, 0.48, width + 0.7),
                             center=(0.0, deck_height + 0.19, 0.0), uv_scale=0.8,
                             material=STONE))
    deck = M.box((length + 1.6, 0.20, width + 0.4),
                 center=(0.0, deck_height + 0.50, 0.0), uv_scale=1.4,
                 material="cobble_paving")
    for sign in (-1.0, 1.0):
        stone_parts.append(balustrade(length + 1.4, 1.05, STONE)
                           .translate(0.0, deck_height + 0.55, sign * (width * 0.5 + 0.12)))
    stone = _weather(M.merge(stone_parts, STONE), 0.012, seed + 5)
    carved = _weather(M.merge(carved_parts, CARVED), 0.008, seed + 6)
    lamps = []
    for sign in (-1.0, 1.0):
        for x in (-length * 0.34, length * 0.34):
            lamps.append(lamp_post(2.4).translate(x, deck_height + 0.6,
                                                  sign * (width * 0.5 + 0.05)))
    result = group(stone, carved, *lamps)
    result.add_walk(deck)
    return result


def lamp_post(height: float = 2.6, material: str = IRON) -> MeshGroup:
    """Wrought-iron post with an amber lantern - the region's night light."""
    parts = [M.cylinder(0.11, 0.075, height, 6, uv_scale=1.4, material=material),
             M.lathe([[0.22, 0.0], [0.22, 0.10], [0.13, 0.20], [0.10, 0.30]], 8,
                     uv_scale=1.4, material=material)]
    arm = M.tube(np.array([[0.0, height, 0.0], [0.0, height + 0.28, 0.10],
                           [0.0, height + 0.34, 0.34]]), [0.05, 0.045, 0.04],
                 segments=6, material=material)
    parts.append(arm)
    housing = M.lathe([[0.0, 0.0], [0.17, 0.05], [0.20, 0.30], [0.14, 0.44], [0.0, 0.50]],
                      6, uv_scale=1.4, material=material)
    parts.append(housing.translate(0.0, height + 0.02, 0.34))
    glow = M.icosphere(0.155, 1, material=AMBER)
    glow.translate(0.0, height + 0.24, 0.34)
    return group(M.merge(parts, material), glow)


def fountain(radius: float = 3.2, seed: int = 0) -> MeshGroup:
    """Tiered fountain with a carved basin, statue plinth and standing water."""
    stone_parts = [
        M.lathe([[radius, 0.0], [radius, 0.55], [radius - 0.32, 0.62],
                 [radius - 0.32, 0.20], [radius - 0.55, 0.16], [radius - 0.55, 0.0]],
                24, uv_scale=0.9, material=STONE),
        M.lathe([[0.0, 0.16], [radius - 0.5, 0.16], [radius - 0.5, 0.20], [0.0, 0.20]],
                24, uv_scale=0.9, material=STONE),
        M.lathe([[0.0, 0.20], [0.85, 0.24], [0.62, 0.85], [0.72, 1.05], [1.35, 1.20],
                 [1.30, 1.42], [0.28, 1.48], [0.28, 1.95], [0.0, 2.00]],
                18, uv_scale=1.0, material=CARVED),
    ]
    water = M.lathe([[0.0, 0.0], [radius - 0.36, 0.0]], 24, uv_scale=0.5,
                    material="water_pool")
    water.translate(0.0, 0.40, 0.0)
    return group(_weather(M.merge(stone_parts, STONE), 0.010, seed), water)


def statue(height: float = 2.8, seed: int = 0, plinth_height: float = 1.05) -> MeshGroup:
    """A weathered standing figure on a moulded plinth - readable, not detailed."""
    rng = Rng(seed)
    parts = [
        M.box((1.15, plinth_height * 0.16, 1.15),
              center=(0.0, plinth_height * 0.08, 0.0), uv_scale=1.0, material=STONE),
        M.box((0.92, plinth_height * 0.74, 0.92),
              center=(0.0, plinth_height * 0.53, 0.0), uv_scale=1.0, material=STONE),
        M.box((1.08, plinth_height * 0.12, 1.08),
              center=(0.0, plinth_height * 0.94, 0.0), uv_scale=1.0, material=STONE),
    ]
    y = plinth_height
    torso = M.lathe([[0.30, 0.0], [0.38, 0.15], [0.34, 0.55], [0.40, 1.02],
                     [0.30, 1.30], [0.22, 1.46]], 10, uv_scale=1.1, material=CARVED)
    parts.append(torso.translate(0.0, y + height * 0.28, 0.0))
    parts.append(M.cylinder(0.26, 0.22, height * 0.30, 8, uv_scale=1.1, material=CARVED)
                 .translate(-0.16, y, 0.0))
    parts.append(M.cylinder(0.26, 0.22, height * 0.30, 8, uv_scale=1.1, material=CARVED)
                 .translate(0.16, y, 0.0))
    head = M.icosphere(0.24, 1, material=CARVED)
    parts.append(head.translate(0.0, y + height * 0.28 + 1.60, 0.0))
    # a cloak reading as a mass behind the figure
    cloak = M.lathe([[0.0, 0.0], [0.52, 0.20], [0.48, 1.10], [0.30, 1.55], [0.0, 1.62]],
                    9, arc=math.pi * 1.25, uv_scale=1.0, material=CARVED)
    cloak.rotate_y(math.pi * 0.85)
    parts.append(cloak.translate(0.0, y + height * 0.24, 0.0))
    for sign in (-1.0, 1.0):
        arm = M.tube(np.array([[sign * 0.30, y + height * 0.28 + 1.30, 0.0],
                               [sign * 0.52, y + height * 0.28 + 0.95, 0.16],
                               [sign * 0.44, y + height * 0.28 + 0.60, 0.34]]),
                     [0.13, 0.11, 0.09], segments=6, cap_end=True, uv_scale=1.2,
                     material=CARVED)
        parts.append(arm)
    body = M.merge(parts, STONE)
    body.jitter(0.012, seed=seed + 7)
    body.recompute_normals(58.0)
    return group(body)


def retaining_wall(length: float, height: float, seed: int = 0,
                   material: str = RUBBLE, batter: float = 0.12,
                   coping: bool = True) -> M.Mesh:
    """Battered rubble retaining wall running along +X, with a coping course."""
    lower = np.array([[-length * 0.5, -0.55 - batter], [length * 0.5, -0.55 - batter],
                      [length * 0.5, 0.55 + batter], [-length * 0.5, 0.55 + batter]])
    upper = np.array([[-length * 0.5, -0.34], [length * 0.5, -0.34],
                      [length * 0.5, 0.34], [-length * 0.5, 0.34]])
    sections = [np.column_stack([lower[:, 0], np.full(4, -1.2), lower[:, 1]]),
                np.column_stack([upper[:, 0], np.full(4, height), upper[:, 1]])]
    body = M.loft(sections, closed_rings=True, uv_scale=0.55, material=material)
    parts = [body]
    if coping:
        parts.append(M.box((length, 0.20, 0.86), center=(0.0, height + 0.08, 0.0),
                           uv_scale=0.9, material="ashlar"))
    merged = M.merge(parts, material)
    merged.jitter(0.020, seed=seed)
    merged.recompute_normals(58.0)
    return merged


def forest_gate(width: float = 5.4, height: float = 6.0, seed: int = 0) -> MeshGroup:
    """A road gate of standing stones and a timber lintel, half taken by the forest."""
    rng = Rng(seed)
    stone_parts = []
    for sign in (-1.0, 1.0):
        x = sign * width * 0.5
        stones = 4
        y = 0.0
        for i in range(stones):
            h = height * 0.86 / stones * float(rng.uniform(0.85, 1.15))
            stone_parts.append(M.box((1.25 - i * 0.09, h, 1.15 - i * 0.07),
                                     center=(x + float(rng.normal(0, 0.05)), y + h * 0.5,
                                             float(rng.normal(0, 0.05))),
                                     uv_scale=0.9, material=RUBBLE))
            y += h
    lintel = beam((-width * 0.5 - 0.7, height * 0.86, 0.0),
                  (width * 0.5 + 0.7, height * 0.86, 0.0), 0.55, 0.62, TIMBER_DARK, 0.9)
    carved_top = M.box((width + 1.9, 0.32, 0.42),
                       center=(0.0, height * 0.86 + 0.52, 0.0), uv_scale=1.4,
                       material=CARVED)
    hangers = []
    for x in (-width * 0.28, width * 0.28):
        hangers.append(M.cylinder(0.035, 0.035, 0.55, 5, uv_scale=1.6, material=IRON)
                       .translate(x, height * 0.86 - 0.60, 0.0))
        bell = M.lathe([[0.0, 0.0], [0.16, 0.06], [0.19, 0.26], [0.12, 0.34], [0.0, 0.36]],
                       7, uv_scale=1.4, material=AMBER)
        hangers.append(bell.translate(x, height * 0.86 - 0.98, 0.0))
    stone = _weather(M.merge(stone_parts, RUBBLE), 0.022, seed + 3)
    return group(stone, M.merge([lintel], TIMBER_DARK), carved_top,
                 *[h for h in hangers])


def ruin_fragment(seed: int = 0, scale: float = 1.0) -> M.Mesh:
    """A tumbled wall stub or column drum group for scattering through the forest."""
    rng = Rng(seed)
    parts = []
    kind = int(rng.integers(0, 3))
    if kind == 0:
        courses = int(rng.integers(3, 7))
        for i in range(courses):
            width = float(rng.uniform(1.0, 2.2)) * (1.0 - i * 0.08)
            parts.append(M.box((width, 0.34, float(rng.uniform(0.6, 0.9))),
                               center=(float(rng.normal(0, 0.08)), 0.17 + i * 0.34,
                                       float(rng.normal(0, 0.08))),
                               uv_scale=0.9, material=STONE))
    elif kind == 1:
        for i in range(int(rng.integers(2, 5))):
            drum = M.cylinder(0.46, 0.44, 0.42, 10, uv_scale=0.9, material=STONE)
            drum.rotate_x(float(rng.uniform(-0.25, 0.25)))
            parts.append(drum.translate(float(rng.uniform(-1.4, 1.4)), 0.0,
                                        float(rng.uniform(-1.2, 1.2))))
    else:
        block = M.box((float(rng.uniform(1.2, 2.0)), float(rng.uniform(0.5, 0.9)),
                       float(rng.uniform(0.8, 1.4))), uv_scale=0.9, material=STONE)
        block.rotate_y(float(rng.uniform(0, 3.14))).rotate_z(float(rng.uniform(-0.2, 0.2)))
        parts.append(block.translate(0.0, 0.35, 0.0))
        for i in range(3):
            parts.append(M.box((0.4, 0.28, 0.34),
                               center=(float(rng.uniform(-1.6, 1.6)), 0.14,
                                       float(rng.uniform(-1.4, 1.4))),
                               uv_scale=1.0, material=RUBBLE))
    merged = M.merge(parts, STONE)
    merged.scale(scale)
    merged.jitter(0.022, seed=seed + 1)
    merged.recompute_normals(58.0)
    return merged


def water_channel(length: float, width: float = 1.4, depth: float = 0.55,
                  seed: int = 0) -> MeshGroup:
    """Dressed stone channel carrying water beside a stair or terrace."""
    stone_parts = []
    for sign in (-1.0, 1.0):
        stone_parts.append(M.box((length, depth + 0.30, 0.34),
                                 center=(0.0, (depth + 0.30) * 0.5 - depth,
                                         sign * (width * 0.5 + 0.17)),
                                 uv_scale=0.9, material=STONE))
    stone_parts.append(M.box((length, 0.22, width + 0.68),
                             center=(0.0, -depth - 0.11, 0.0), uv_scale=0.9,
                             material=STONE))
    water = M.box((length - 0.1, 0.05, width),
                  center=(0.0, -0.14, 0.0), uv_scale=0.8, material="water_stream")
    return group(_weather(M.merge(stone_parts, STONE), 0.010, seed), water)


def waterfall(width: float, height: float, seed: int = 0,
              material: str = "water_stream") -> M.Mesh:
    """A falling sheet of water with a curved lip and a widening plume."""
    rng = Rng(seed)
    sections = []
    rows = 9
    for i in range(rows):
        t = i / (rows - 1)
        y = -height * t
        spread = width * (0.5 + 0.55 * t ** 1.4)
        bulge = 0.55 * math.sin(t * math.pi) * (1.0 if t < 0.3 else 0.4)
        ring = []
        points = 9
        for k in range(points):
            u = k / (points - 1)
            x = -spread + 2.0 * spread * u
            z = bulge * math.sin(u * math.pi) + float(rng.normal(0.0, 0.05))
            ring.append([x, y, z])
        sections.append(np.array(ring))
    sheet = M.loft(sections, closed_rings=False, uv_scale=0.6, material=material)
    sheet.uvs = np.stack([sheet.positions[:, 0] * 0.22, sheet.positions[:, 1] * 0.16],
                         axis=-1)
    return sheet


def rotunda(radius: float = 3.0, height: float = 4.2, columns: int = 8,
            seed: int = 0) -> MeshGroup:
    """Open garden pavilion: stepped base, colonnade, entablature, domed roof."""
    stone_parts = [
        M.lathe([[radius + 1.05, 0.0], [radius + 1.05, 0.22], [radius + 0.70, 0.24],
                 [radius + 0.70, 0.46], [radius + 0.38, 0.48], [radius + 0.38, 0.62],
                 [0.0, 0.64]], 20, uv_scale=0.8, material=STONE),
    ]
    for i in range(columns):
        angle = math.pi * 2.0 * i / columns
        stone_parts.append(column(height, 0.30, 10, STONE)
                           .translate(math.cos(angle) * radius, 0.62,
                                      math.sin(angle) * radius))
    stone_parts.append(M.lathe(
        [[radius + 0.55, height + 1.22], [radius + 0.55, height + 1.46],
         [radius + 0.30, height + 1.52], [radius + 0.30, height + 1.70],
         [0.0, height + 1.74]], 20, uv_scale=0.8, material=STONE))
    dome = M.lathe([[radius + 0.30, height + 1.70], [radius * 0.92, height + 2.35],
                    [radius * 0.62, height + 2.90], [radius * 0.26, height + 3.22],
                    [0.0, height + 3.32]], 20, uv_scale=1.4, material=SHINGLE)
    finial = M.lathe([[0.0, 0.0], [0.14, 0.10], [0.09, 0.34], [0.16, 0.44],
                      [0.0, 0.62]], 8, uv_scale=1.6, material=IRON)
    return group(_weather(M.merge(stone_parts, STONE), 0.008, seed), dome,
                 finial.translate(0.0, height + 3.30, 0.0))
