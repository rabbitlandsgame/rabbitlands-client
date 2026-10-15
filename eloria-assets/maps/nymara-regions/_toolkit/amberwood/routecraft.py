"""Road beds, tidal crossings and planted rows shared by region authors."""
from __future__ import annotations

import math
import numpy as np

from . import mesh as M
from . import terrain as TER
from .noise import Rng
from .stonework import MeshGroup


def grade_road(terrain, points, heights, width=7.0, shoulder=7.0,
               surface=TER.PATH, clearance=6.0):
    """A cart-width bed with surveyed levels at the actual polyline stations.

    The centre and the full bed are level across the road. Only its shoulders
    blend back into the hillside. Unlike a worn trail, a built ramp must meet
    its landing at the specified height, even when its segments differ in length.
    This edits the terrain itself, so no second surface lies on top of it.
    """
    points = np.asarray(points, dtype=float)
    heights = np.asarray(heights, dtype=float)
    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    if len(points) < 2 or len(heights) != len(points) or np.any(np.diff(lengths) <= 0):
        raise ValueError("road needs distinct stations with one height each")
    if width <= 0 or shoulder <= 0:
        raise ValueError("road width and shoulder must be positive")
    distance, along = TER._polyline_distance(terrain.gx, terrain.gz, points)
    target = np.interp(along, lengths / lengths[-1], heights)
    edge = np.clip((distance - width * 0.5) / shoulder, 0, 1)
    blend = 1 - edge * edge * (3 - 2 * edge)
    terrain.height = terrain.height * (1 - blend) + target * blend
    bed = distance <= width * 0.5 + 0.6
    terrain.surface = np.where(bed, surface, terrain.surface)
    terrain.tree_block |= distance < width * 0.5 + clearance
    terrain._write_strength(np.abs(distance - width * 0.5) / terrain.cell, bed)


def graded_causeway(stations, width=5.5, thickness=0.8, parapet=0.75,
                    foot=-9.0, stone="rubble_stone", paving="cobble_paving"):
    """Continuous mitred deck, open-ended parapets and piers down to the bed.

    Stations are (x, y, z) in placement-local metres. The walking top is a
    single skin. Slab sides end below it; parapets stand outside its edges.
    Neighbouring runs share edges only, including at bends.
    """
    points = np.asarray(stations, dtype=float)
    if len(points) < 2 or points.shape[1] != 3 or width <= 0 or thickness <= 0:
        raise ValueError("causeway needs at least two 3D stations and positive dimensions")
    runs = np.diff(points[:, [0, 2]], axis=0)
    lengths = np.linalg.norm(runs, axis=1)
    if np.any(lengths < 0.01):
        raise ValueError("causeway stations must be distinct in plan")
    tangents = runs / lengths[:, None]
    normals = np.c_[-tangents[:, 1], tangents[:, 0]]
    mitres = np.empty((len(points), 2))
    mitres[0], mitres[-1] = normals[0], normals[-1]
    for i in range(1, len(points) - 1):
        bisector = normals[i - 1] + normals[i]
        divisor = float(np.dot(bisector, normals[i]))
        if divisor < 0.5:
            raise ValueError("causeway bend is too sharp for a mitred deck")
        mitres[i] = bisector / divisor
    group = MeshGroup()

    def ribbon(offset, rise):
        out = points.copy()
        out[:, [0, 2]] += mitres * offset
        out[:, 1] += rise
        return out

    left, right = ribbon(-width / 2, 0), ribbon(width / 2, 0)
    lower_l, lower_r = ribbon(-width / 2, -thickness), ribbon(width / 2, -thickness)
    for i in range(len(points) - 1):
        j = i + 1
        group.add_walk(M.quad([right[i], right[j], left[j], left[i]],
                              uv_scale=0.7, material=paving))
        for quad in ([left[i], lower_l[i], lower_l[j], left[j]],
                     [right[j], lower_r[j], lower_r[i], right[i]],
                     [lower_l[i], lower_r[i], lower_r[j], lower_l[j]]):
            group.add(M.quad(list(reversed(quad)), uv_scale=0.7, material=stone))
        for sign in (-1, 1):
            inner = ribbon(sign * (width / 2 + 0.06), -0.1)
            outer = ribbon(sign * (width / 2 + 0.44), -0.1)
            inner_top, outer_top = inner.copy(), outer.copy()
            inner_top[:, 1] += parapet + 0.1
            outer_top[:, 1] += parapet + 0.1
            for quad in ([inner[i], inner[j], inner_top[j], inner_top[i]],
                         [outer[j], outer[i], outer_top[i], outer_top[j]],
                         [inner_top[i], inner_top[j], outer_top[j], outer_top[i]]):
                group.add(M.quad(quad if sign < 0 else list(reversed(quad)),
                                 uv_scale=0.9, material=stone))
        # Piers stop below the slab; their top cannot fight the walking plane.
        count = max(1, math.ceil(lengths[i] / 9))
        for k in range(count):
            p = points[i] + (points[j] - points[i]) * ((k + 0.5) / count)
            height = p[1] - thickness - 0.03 - foot
            if height <= 0:
                continue
            pier = M.box((1.4, height, width - 0.4),
                          center=(0, foot + height / 2, 0), material=stone)
            pier.rotate_y(math.atan2(-runs[i, 1], runs[i, 0]))
            group.add(pier.translate(p[0], 0, p[2]))
    return group


def crop_rows(length=16.0, width=10.0, seed=0, material="thatch_reed", height_range=(0.48, 0.85)):
    """Sparse planted grain rows; paths and harvest nodes remain region data."""
    rng = Rng(seed)
    parts = []
    for x in np.arange(-length / 2, length / 2, 0.8):
        for z in np.arange(-width / 2, width / 2, 1.3):
            h = float(rng.uniform(*height_range))
            px, pz = x + float(rng.uniform(-0.12, 0.12)), z + float(rng.uniform(-0.1, 0.1))
            for yaw in (0, math.pi / 2):
                blade = M.quad([(-0.12, 0.12, 0), (0, h, 0),
                                (0.12, h - 0.14, 0), (0.03, 0, 0)],
                               material=material)
                parts.append(blade.rotate_y(yaw).translate(px, 0, pz))
    return M.merge(parts, material)


def vault_entry(stone="pale_ashlar", roof="slate_roof", wood="carved_wood"):
    """A small covered entrance to a cellar, front on +Z, threshold at Z=2.

    The porch is open below: its region grades the actual ground. Separate
    wall sections frame a recessed door without a facade plane behind it.
    """
    from . import architecture as ARCH
    group = MeshGroup()
    for sign in (-1, 1):
        group.add(M.box((0.48, 3.4, 3.8),
                        center=(sign * 2.16, 1.7, 0), material=stone))
        group.add(M.box((1.18, 2.65, 0.44),
                        center=(sign * 1.35, 1.325, 1.7), material=stone))
    group.add(M.box((3.84, 3.4, 0.42), center=(0, 1.7, -1.69), material=stone))
    group.add(M.box((3.84, 0.75, 0.44), center=(0, 3.025, 1.7), material=stone))
    group.add(ARCH.door(1.48, 2.50, material=wood).translate(0, 0, 1.42))
    # Two pitched skins, no horizontal roof or coincident wall caps.
    for sign in (-1, 1):
        quad = [(-2.65, 3.46, sign * 2.15), (2.65, 3.46, sign * 2.15),
                (2.65, 4.4, 0), (-2.65, 4.4, 0)]
        group.add(M.quad(quad if sign > 0 else list(reversed(quad)),
                         uv_scale=0.8, material=roof))
    return group


def annular_walk(outer_radius, inner_radius, thickness=0.16,
                 material="veined_marble", segments=40):
    """An upward-facing annular promenade, open around its central basin."""
    if not 0 < inner_radius < outer_radius or thickness <= 0:
        raise ValueError("promenade needs ordered positive radii and thickness")
    # The historical lathe indices face into the profile. The normals already
    # face out; only winding changes for a surface the grounding ray must hit.
    return M.lathe([[outer_radius, 0], [outer_radius, thickness],
                    [inner_radius, thickness]], segments, uv_scale=0.6,
                   material=material).flip_winding()


def stair_flight(width, height, length, steps, material="pale_ashlar"):
    """One solid flight with unique tread, riser and side faces, climbing +Z."""
    if min(width, height, length) <= 0 or steps < 1:
        raise ValueError("stair dimensions and step count must be positive")
    half = width / 2
    rise, run = height / steps, length / steps
    parts = []
    for i in range(steps):
        z, end, y, previous = i * run, (i + 1) * run, (i + 1) * rise, i * rise
        parts.append(M.quad([(-half, y, z), (-half, y, end),
                             (half, y, end), (half, y, z)], material=material))
        parts.append(M.quad([(-half, previous, z), (-half, y, z),
                             (half, y, z), (half, previous, z)], material=material))
        for sign in (-1, 1):
            face = [(sign * half, 0, z), (sign * half, 0, end),
                    (sign * half, y, end), (sign * half, y, z)]
            parts.append(M.quad(face if sign < 0 else list(reversed(face)), material=material))
    parts.append(M.quad([(-half, 0, length), (half, 0, length),
                         (half, height, length), (-half, height, length)], material=material))
    parts.append(M.quad([(-half, 0, 0), (half, 0, 0),
                         (half, 0, length), (-half, 0, length)], material=material))
    return M.merge(parts, material)


def crossing_endpoints(stations, inset=1.5):
    """Standing points inside a deck, clear of its half-open raster edges."""
    def inside(points):
        left = float(inset)
        for a, b in zip(points, points[1:]):
            a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
            length = float(np.linalg.norm((b - a)[[0, 2]]))
            if length >= left:
                return (a + (b - a) * left / length).tolist()
            left -= length
        return list(points[-1])
    return [inside(stations), inside(list(reversed(stations)))]


def clear_walk_corridors(build, corridors, clearances):
    """Cull encroaching dressing after placement, preserving seeded draws."""
    lines = [np.asarray(points, dtype=float)[:, [0, 2]] for points in corridors]
    kept = []
    for placement in build.placements:
        clearance = clearances.get(placement.kind)
        if clearance is None:
            kept.append(placement)
            continue
        x, _, z = placement.position
        blocked = any(float(TER._polyline_distance(
            np.asarray(x), np.asarray(z), line)[0]) < clearance for line in lines)
        if not blocked:
            kept.append(placement)
    removed = len(build.placements) - len(kept)
    build.placements[:] = kept
    build.notes.append(f"walk corridors: {removed} encroaching dressing placements removed")
    return removed


def incise_channel(terrain, points, width=7.0, shoulder=7.0, floor=-0.6):
    """Cut a downstream river bed without raising any surrounding ground.

    Dense stations follow the cumulative minimum of the natural bed. Surface
    classes are preserved for the region to paint after its water and roads.
    """
    points=np.asarray(points,dtype=float)
    lengths=np.linalg.norm(np.diff(points,axis=0),axis=1)
    distance=np.r_[0,np.cumsum(lengths)]
    stations=np.linspace(0,distance[-1],max(2,int(distance[-1]/2)+1))
    line=np.column_stack([np.interp(stations,distance,points[:,i]) for i in (0,1)])
    heights=np.maximum(floor,np.minimum.accumulate(terrain.height_at(line[:,0],line[:,1])))
    original=terrain.height.copy()
    classes=terrain.surface.copy()
    grade_road(terrain,line,heights,width=width,shoulder=shoulder,
               surface=int(classes.flat[0]),clearance=width/2)
    terrain.height=np.minimum(original,terrain.height)
    terrain.surface=classes
    return line,heights
