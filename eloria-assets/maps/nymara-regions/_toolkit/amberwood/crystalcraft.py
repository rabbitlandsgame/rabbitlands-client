"""Crystal geometry: shards, clusters, geode mouths and floating shard fields.

Written for Amethyst Barrens but parameterised on material throughout, so any
region with crystal in it - Mirrorhold's blue crystal, Whitehorn's ice - can use
the same pieces without copying them.

A shard is a lofted faceted prism that tapers to a point, not a cone: crystal
reads as flat planes meeting at hard edges, and a smooth body of revolution
looks like a carrot however it is textured. `recompute_normals` is therefore
called with a small smoothing angle so the facets stay crisp.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .noise import Rng
from .stonework import MeshGroup, group

CRYSTAL = "amethyst_crystal"
ROCK = "amethyst_storm_rock"


def facet(piece: M.Mesh) -> M.Mesh:
    """Give every triangle its own vertices and its own flat normal.

    A lofted ring shares each vertex between the faces that meet at it, so
    `recompute_normals` can only average them and the result shades as a smooth
    body of revolution however small the smoothing angle. Crystal has to be flat
    shaded to read as crystal, and that means duplicating vertices.
    """
    if piece.triangle_count == 0:
        return piece
    tris = piece.indices.reshape(-1, 3)
    positions = piece.positions[tris].reshape(-1, 3)
    uvs = piece.uvs[tris].reshape(-1, 2)
    edge1 = positions[1::3] - positions[0::3]
    edge2 = positions[2::3] - positions[0::3]
    face = np.cross(edge1, edge2)
    lengths = np.linalg.norm(face, axis=1, keepdims=True)
    lengths[lengths < 1e-12] = 1.0
    face = face / lengths
    normals = np.repeat(face, 3, axis=0)
    piece.positions = positions
    piece.normals = normals
    piece.uvs = uvs
    piece.colors = None
    piece.indices = np.arange(len(positions), dtype=np.int64)
    return piece


def _ring(radius: float, y: float, faces: int, rng: Rng, wobble: float,
          phase: float) -> np.ndarray:
    """One cross-section of a shard, irregular but convex."""
    angles = np.linspace(0.0, 2.0 * math.pi, faces, endpoint=False) + phase
    radii = radius * (1.0 + rng.uniform(-wobble, wobble, faces))
    return np.stack([np.cos(angles) * radii,
                     np.full(faces, y),
                     np.sin(angles) * radii], axis=-1)


def shard(height: float = 3.0, radius: float = 0.5, faces: int = 6,
          seed: int = 0, material: str = CRYSTAL,
          tilt: float = 0.0, taper: float = 0.30) -> M.Mesh:
    """A single crystal, base at y = 0, point at y = height."""
    rng = Rng(seed)
    faces = max(4, int(faces))
    phase = float(rng.uniform(0.0, 2.0 * math.pi))
    wobble = 0.14

    # Quartz habit: a near-parallel prism for most of the length, then a short
    # pointed termination. A profile that tapers all the way from the base gives
    # a spike or a teardrop, which is what this looked like before - the flat
    # sides are most of what makes a crystal read as a crystal.
    profile = ((0.00, 0.98), (0.30, 1.00), (0.62, 0.98), (0.74, 0.95),
               (0.86, taper + 0.34), (0.95, taper), (1.00, 0.04))
    sections = [_ring(radius * r, height * t, faces, rng, wobble, phase)
                for t, r in profile]
    # a slight shear so the point is not directly above the centre
    lean_x = float(rng.uniform(-0.16, 0.16)) * height
    lean_z = float(rng.uniform(-0.16, 0.16)) * height
    for index, (t, _r) in enumerate(profile):
        sections[index][:, 0] += lean_x * t * t
        sections[index][:, 2] += lean_z * t * t

    piece = M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.5,
                   material=material)
    facet(piece)
    if tilt:
        piece.rotate_x(tilt * float(rng.uniform(0.6, 1.0)))
        piece.rotate_y(float(rng.uniform(0.0, 2.0 * math.pi)))
    return piece


def cluster(count: int = 6, radius: float = 1.6, height: float = 3.2,
            seed: int = 0, material: str = CRYSTAL,
            spread: float = 0.42) -> M.Mesh:
    """A group of shards growing out of one point, tallest in the middle."""
    rng = Rng(seed)
    parts = []
    for index in range(max(1, count)):
        # the first shard is the hero; the rest are smaller and lean outward
        scale = 1.0 if index == 0 else float(rng.uniform(0.32, 0.78))
        distance = 0.0 if index == 0 else float(rng.uniform(0.25, 1.0)) * radius
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        piece = shard(height * scale, radius * 0.34 * (0.6 + scale * 0.6),
                      faces=int(rng.integers(5, 8)), seed=seed + index * 17,
                      material=material)
        if index:
            piece.rotate_z(float(rng.uniform(-spread, spread)))
            piece.rotate_y(angle)
        piece.translate(math.cos(angle) * distance,
                        float(rng.uniform(-0.12, 0.06)) * height,
                        math.sin(angle) * distance)
        parts.append(piece)
    merged = M.merge(parts, material=material)
    return merged


def outcrop(seed: int = 0, radius: float = 2.6, height: float = 3.6,
            material: str = CRYSTAL, rock_material: str = ROCK) -> MeshGroup:
    """Crystal breaking out of a knuckle of rock - the roadside dressing."""
    rng = Rng(seed)
    out = MeshGroup()
    base = M.icosphere(radius * 0.55, subdivisions=1, material=rock_material)
    base.scale(1.0, 0.42, 1.0)
    base.jitter(radius * 0.13, seed=seed + 3)
    base.recompute_normals(52.0)
    out.add(base.translate(0.0, radius * 0.12, 0.0))
    out.add(cluster(count=int(rng.integers(3, 6)), radius=radius * 0.7,
                    height=height, seed=seed + 11, material=material)
            .translate(0.0, radius * 0.16, 0.0))
    return out


def spire(height: float = 14.0, radius: float = 2.2, seed: int = 0,
          material: str = CRYSTAL, rock_material: str = ROCK) -> MeshGroup:
    """A monumental shard with a rock plinth: the massif's individual peaks."""
    rng = Rng(seed)
    out = MeshGroup()
    plinth = M.icosphere(radius * 1.15, subdivisions=1, material=rock_material)
    plinth.scale(1.0, 0.38, 1.0)
    plinth.jitter(radius * 0.16, seed=seed + 5)
    plinth.recompute_normals(50.0)
    out.add(plinth.translate(0.0, radius * 0.10, 0.0))
    main = shard(height, radius, faces=int(rng.integers(6, 9)), seed=seed + 1,
                 material=material)
    out.add(main.translate(0.0, radius * 0.18, 0.0))
    for index in range(int(rng.integers(2, 5))):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        distance = float(rng.uniform(0.5, 1.3)) * radius
        minor = shard(height * float(rng.uniform(0.24, 0.52)),
                      radius * float(rng.uniform(0.30, 0.55)),
                      faces=int(rng.integers(5, 8)), seed=seed + 40 + index,
                      material=material)
        minor.rotate_z(float(rng.uniform(0.12, 0.38)))
        minor.rotate_y(angle)
        out.add(minor.translate(math.cos(angle) * distance, radius * 0.12,
                                math.sin(angle) * distance))
    return out


def floating_field(count: int = 9, radius: float = 7.0, base_height: float = 6.0,
                   seed: int = 0, material: str = CRYSTAL,
                   hero_height: float = 6.5) -> MeshGroup:
    """Levitating shards: one large stone hanging low, smaller ones around it.

    Nothing here is a walk surface and nothing collides - a player walks under
    the field. The shards hang well clear of head height so the grounding ray,
    which takes the first hit from above, never resolves onto one: they are not
    on the navigation layer, but keeping them high also keeps the silhouette
    readable from the ground.
    """
    rng = Rng(seed)
    out = MeshGroup()
    hero = shard(hero_height, hero_height * 0.26, faces=8, seed=seed + 1,
                 material=material)
    # points down, the way the concept hangs its great stone
    hero.rotate_z(math.pi * 0.94)
    out.add(hero.translate(0.0, base_height + hero_height * 1.05, 0.0))
    for index in range(max(0, count - 1)):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        distance = float(rng.uniform(0.35, 1.0)) * radius
        size = hero_height * float(rng.uniform(0.12, 0.34))
        minor = shard(size, size * 0.30, faces=int(rng.integers(5, 8)),
                      seed=seed + 70 + index, material=material)
        minor.rotate_z(float(rng.uniform(0.0, math.pi)))
        minor.rotate_y(angle)
        lift = base_height + float(rng.uniform(0.3, 1.9)) * hero_height
        out.add(minor.translate(math.cos(angle) * distance, lift,
                                math.sin(angle) * distance))
    return out


def geode_mouth(radius: float = 5.0, depth: float = 7.0, seed: int = 0,
                material: str = CRYSTAL, rock_material: str = ROCK,
                segments: int = 18) -> MeshGroup:
    """A cave entrance in a rock face, lined with crystal.

    Built as a tapering tube driven into the hillside with its far end capped,
    so it reads as a real opening from outside and is not a hole a player can
    fall through. The interior is a separate map; this is the mouth only.
    """
    rng = Rng(seed)
    out = MeshGroup()

    # The surrounding rock, built as a collar of boulders around the opening
    # rather than one mass in front of it. A single ellipsoid centred on the
    # mouth simply closes it: the hole has to be left open by construction.
    for index in range(11):
        angle = math.pi * (0.06 + 0.88 * index / 10.0)
        boulder_r = radius * float(rng.uniform(0.34, 0.56))
        lump = M.icosphere(boulder_r, subdivisions=1, material=rock_material)
        lump.scale(1.0, float(rng.uniform(0.75, 1.15)), 1.0)
        lump.jitter(boulder_r * 0.22, seed=seed + 30 + index)
        lump.recompute_normals(46.0)
        # far enough out that a boulder's inner edge clears the opening: the
        # collar frames the mouth, it does not fill it
        reach = radius * 1.78
        out.add(lump.translate(math.cos(angle) * reach,
                               radius * 0.80 + math.sin(angle) * reach * 0.86,
                               float(rng.uniform(-0.3, 0.3)) * radius))
    # a lintel of rock over the top and a sill of scree at the foot
    sill = M.icosphere(radius * 1.25, subdivisions=1, material=rock_material)
    sill.scale(1.5, 0.30, 1.0)
    sill.jitter(radius * 0.16, seed=seed + 61)
    sill.recompute_normals(46.0)
    out.add(sill.translate(0.0, -radius * 0.06, radius * 0.34))

    # the throat: rings marching back and shrinking, capped at the far end
    sections = []
    steps = 7
    for index in range(steps):
        t = index / (steps - 1)
        r = radius * (1.0 - 0.72 * t)
        z = -depth * t
        angles = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
        wob = 1.0 + rng.uniform(-0.10, 0.10, segments)
        ring = np.stack([np.cos(angles) * r * wob,
                         np.sin(angles) * r * 0.82 * wob + r * 0.86,
                         np.full(segments, z)], axis=-1)
        sections.append(ring)
    throat = M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.4,
                    material=material)
    # seen from outside, so the inward-facing side is what must be lit
    throat.flip_winding()
    facet(throat)
    out.add(throat)

    # crystal teeth around the lip
    for index in range(int(rng.integers(7, 12))):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        size = radius * float(rng.uniform(0.16, 0.42))
        tooth = shard(size * 2.2, size * 0.42, faces=int(rng.integers(5, 8)),
                      seed=seed + 90 + index, material=material)
        tooth.rotate_z(float(rng.uniform(-0.5, 0.5)) + math.pi * 0.5)
        tooth.rotate_y(angle)
        out.add(tooth.translate(math.cos(angle) * radius * 0.95,
                                radius * 0.86 + math.sin(angle) * radius * 0.7,
                                radius * 0.1))
    return out


def vein_scatter(radius: float = 3.0, count: int = 7, seed: int = 0,
                 material: str = CRYSTAL, height: float = 0.9) -> M.Mesh:
    """Small shards pushing up through the ground: cheap ground dressing."""
    rng = Rng(seed)
    parts = []
    for index in range(max(1, count)):
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        distance = float(rng.uniform(0.0, 1.0)) ** 0.5 * radius
        size = height * float(rng.uniform(0.45, 1.25))
        piece = shard(size, size * float(rng.uniform(0.22, 0.40)),
                      faces=int(rng.integers(5, 7)), seed=seed + index * 13,
                      material=material)
        piece.rotate_z(float(rng.uniform(-0.42, 0.42)))
        piece.rotate_y(angle)
        parts.append(piece.translate(math.cos(angle) * distance,
                                     -size * 0.16,
                                     math.sin(angle) * distance))
    return M.merge(parts, material=material)
