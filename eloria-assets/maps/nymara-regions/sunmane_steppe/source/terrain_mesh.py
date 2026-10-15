"""Convert the sculpted landform into chunked, class-split render geometry.

Chunking keeps frustum culling and per-chunk collision useful; splitting each
chunk by terrain class lets the four described ground types tint the shared
detail texture without splat seams or a second UV set.

Every chunk node is named with the `Terrain_` prefix the client's world loader
uses to build navigation-surface collision, so grounding covers the whole
landform including the shallow shelf - an actor can never raycast into empty
space and fall back to the manifest walking height.
"""
from __future__ import annotations

import numpy as np

from glb import Geometry
from terrain import CELL, CHUNKS, CLASS_TINT, Landform
from shapes import UV_SCALE


# Height range across one quad, in metres, beyond which the quad is facetted
# rather than smooth-shaded.
FLAT_SHADE_RELIEF = 2.2
# Above this relief across one quad the downward texture projection
# stretches enough to be visible, so the quad is textured on its face.
UV_PROJECT_RELIEF = 1.0


def _vertex_normals(height: np.ndarray) -> np.ndarray:
    """Smooth per-vertex normals from the heightfield's central differences."""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) / (2.0 * CELL)
    dz = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) / (2.0 * CELL)
    # Edges use one-sided differences so the border does not fold.
    dx[:, 0] = (height[:, 1] - height[:, 0]) / CELL
    dx[:, -1] = (height[:, -1] - height[:, -2]) / CELL
    dz[0, :] = (height[1, :] - height[0, :]) / CELL
    dz[-1, :] = (height[-1, :] - height[-2, :]) / CELL
    normals = np.stack([-dx, np.ones_like(height), -dz], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    return normals


def _coverage(quad_classes, quad_strength, corner_index, terrain_class):
    """Per-vertex alpha for one class over one quad.

    0.5 at the class edge, running to 1 inside the class and 0 outside it, so
    an alpha test at 0.5 cuts exactly on the edge. How fast it runs is the
    landform's own strength: at 1 - nothing knew where the edge was - the cut
    lands half way between two samples, which turns a corner staircase into a
    diagonal. Where a road wrote its own distance the cut lands on the real
    edge. White apart from the alpha: the material multiplies albedo by these,
    and tinting the ground is not the point.
    """
    colors = []
    for index in corner_index:
        inside = int(quad_classes[index]) == terrain_class
        strength = float(quad_strength[index])
        alpha = 0.5 + 0.5 * strength if inside else 0.5 - 0.5 * strength
        colors.append([1.0, 1.0, 1.0, alpha])
    return colors


def build_chunks(landform: Landform) -> list[dict]:
    """Return one entry per chunk: name, and per-class Geometry."""
    height = landform.height.astype("float64")
    strength = (landform.strength if landform.strength is not None
                else np.ones(landform.height.shape))
    normals = _vertex_normals(height)
    count = height.shape[0]
    span = (count - 1) // CHUNKS
    x_axis, z_axis = landform.x, landform.z
    scale = UV_SCALE["ground"]

    chunks = []
    for chunk_z in range(CHUNKS):
        for chunk_x in range(CHUNKS):
            x0, x1 = chunk_x * span, (chunk_x + 1) * span
            z0, z1 = chunk_z * span, (chunk_z + 1) * span
            by_class: dict[int, Geometry] = {}
            corner_classes = landform.classes[z0:z1 + 1, x0:x1 + 1]
            corner_strength = strength[z0:z1 + 1, x0:x1 + 1]
            for local_z in range(z1 - z0):
                for local_x in range(x1 - x0):
                    quad_classes = corner_classes[local_z:local_z + 2,
                                                  local_x:local_x + 2].ravel()
                    quad_strength = corner_strength[local_z:local_z + 2,
                                                    local_x:local_x + 2].ravel()
                    # Every class the quad touches takes it, not just the one
                    # holding most of its corners. Each copy carries a
                    # per-vertex coverage and is drawn with an alpha-tested
                    # material, so the pixels go to whichever class covers
                    # them and the boundary runs through the cell instead of
                    # around it. Majority ownership could only ever turn a
                    # road on a cell corner, which is what made a diagonal
                    # track read as a flight of 1.4 m steps.
                    gx, gz = x0 + local_x, z0 + local_z
                    # The corners in the order the quad is wound, so a
                    # coverage entry lines up with the vertex it belongs to.
                    corner_order = ((0, 0), (1, 0), (1, 1), (0, 1))
                    corner_index = [offset_z * 2 + offset_x
                                    for offset_z, offset_x in corner_order]
                    positions, vertex_normals, uvs = [], [], []
                    # Counter-clockwise seen from above, so the geometric normal
                    # points +Y. Clockwise here makes the terrain both invisible
                    # (back-face culled) and untouchable by the grounding ray,
                    # because ConcavePolygonShape3D ignores back faces.
                    for offset_z, offset_x in ((0, 0), (1, 0), (1, 1), (0, 1)):
                        world_x = float(x_axis[gx + offset_x])
                        world_z = float(z_axis[gz + offset_z])
                        positions.append([world_x, float(height[gz + offset_z,
                                                               gx + offset_x]), world_z])
                        vertex_normals.append(normals[gz + offset_z, gx + offset_x])
                        uvs.append([world_x / scale, world_z / scale])
                    # Split along the shorter diagonal to avoid sliver triangles
                    # on saddle quads.
                    diagonal_a = abs(positions[0][1] - positions[2][1])
                    diagonal_b = abs(positions[1][1] - positions[3][1])
                    indices = ([0, 1, 2, 0, 2, 3] if diagonal_a <= diagonal_b
                               else [0, 1, 3, 1, 2, 3])
                    # One decision, made from the quad's own normal rather than
                    # from a relief threshold. A threshold on how much a quad
                    # drops flips neighbouring quads between two treatments all
                    # along a hillside, and the alternation renders as a
                    # chequerboard of light and dark ground - the most visible
                    # procedural artifact this terrain had.
                    faces = []
                    for triangle in (indices[:3], indices[3:]):
                        corners = [np.asarray(positions[i]) for i in triangle]
                        face = np.cross(corners[1] - corners[0],
                                        corners[2] - corners[0])
                        length = float(np.linalg.norm(face))
                        faces.append(None if length < 1e-12 else face / length)
                    mean = np.zeros(3)
                    for face in faces:
                        if face is not None:
                            mean = mean + face
                    mean_length = float(np.linalg.norm(mean))
                    if mean_length < 1e-9:
                        continue
                    shared = mean / mean_length
                    # The weakest agreement between any corner's smoothed
                    # normal and either triangle's own face: one corner pulled
                    # across a break is enough to render a triangle inside-out.
                    agreement = 1.0
                    for triangle, face in zip((indices[:3], indices[3:]), faces):
                        if face is None:
                            continue
                        for corner in triangle:
                            agreement = min(agreement, float(np.dot(
                                np.asarray(vertex_normals[corner]), face)))
                    # Below roughly 63 degrees the downward projection is honest
                    # enough; past it one texel covers metres of rock face, so
                    # the quad is textured on whichever vertical plane faces it.
                    if abs(float(shared[1])) < 0.45:
                        side = abs(float(shared[0])) > abs(float(shared[2]))
                        quad_uvs = [[(point[2] if side else point[0]) / scale,
                                     -point[1] / scale] for point in positions]
                    else:
                        quad_uvs = uvs
                    for terrain_class in sorted({int(v) for v in quad_classes}):
                        geometry = by_class.setdefault(terrain_class, Geometry())
                        colors = _coverage(quad_classes, quad_strength,
                                           corner_index, terrain_class)
                        if agreement > 0.55:
                            # The smoothed normal still describes this face, so
                            # the quad keeps continuous shading with its
                            # neighbours.
                            geometry.add(positions, vertex_normals, quad_uvs,
                                         indices, colors)
                            continue
                        # A fold: the averaged normal has been dragged across
                        # the break and now opposes the face it belongs to,
                        # which renders the quad inside-out and lets the
                        # grounding ray through. Facet it - as one facet, so
                        # the two halves of the quad are not lit differently.
                        for triangle, face in zip((indices[:3], indices[3:]), faces):
                            if face is None:
                                continue
                            normal = (shared if float(np.dot(shared, face)) > 0.2
                                      else face)
                            geometry.add([positions[i] for i in triangle],
                                         [normal] * 3,
                                         [quad_uvs[i] for i in triangle],
                                         [0, 1, 2],
                                         [colors[i] for i in triangle])
                    continue
            chunks.append({
                "name": f"Terrain_Chunk_{chunk_x:02d}_{chunk_z:02d}",
                "geometry": {k: v for k, v in by_class.items() if v.triangle_count},
                "bounds": (float(x_axis[x0]), float(z_axis[z0]),
                           float(x_axis[x1]), float(z_axis[z1])),
            })
    return chunks


def water_surface(landform: Landform, level: float = 0.0) -> Geometry:
    """A single sea plane clipped to the cells the landform floods."""
    geometry = Geometry()
    height = landform.height
    x_axis, z_axis = landform.x, landform.z
    scale = UV_SCALE["ground"] * 2.0
    flooded = height < level - 0.05
    normal = [0.0, 1.0, 0.0]
    for gz in range(len(z_axis) - 1):
        run_start = None
        row = flooded[gz:gz + 2]
        for gx in range(len(x_axis) - 1):
            wet = bool(row[:, gx:gx + 2].any())
            if wet and run_start is None:
                run_start = gx
            if (not wet or gx == len(x_axis) - 2) and run_start is not None:
                run_end = gx + 1 if wet else gx
                x_start, x_end = float(x_axis[run_start]), float(x_axis[run_end])
                z_start, z_end = float(z_axis[gz]), float(z_axis[gz + 1])
                corners = [[x_start, level, z_start], [x_start, level, z_end],
                           [x_end, level, z_end], [x_end, level, z_start]]
                uvs = [[x_start / scale, z_start / scale], [x_start / scale, z_end / scale],
                       [x_end / scale, z_end / scale], [x_end / scale, z_start / scale]]
                geometry.add(corners, [normal] * 4, uvs, [0, 1, 2, 0, 2, 3])
                run_start = None
    return geometry


def pond_surfaces(landform: Landform, ponds) -> Geometry:
    """Inland waterhole surfaces, each level with its own bowl."""
    geometry = Geometry()
    scale = UV_SCALE["ground"]
    normal = [0.0, 1.0, 0.0]
    for px, pz, radius in ponds:
        # Fill level: a little above the bowl floor so a rim of wet ground shows.
        floor = landform.height_at(px, pz)
        level = floor + 1.9
        steps = 14
        for step_z in range(steps):
            for step_x in range(steps):
                x_start = px - radius + 2.0 * radius * step_x / steps
                x_end = px - radius + 2.0 * radius * (step_x + 1) / steps
                z_start = pz - radius + 2.0 * radius * step_z / steps
                z_end = pz - radius + 2.0 * radius * (step_z + 1) / steps
                centre_x, centre_z = (x_start + x_end) * 0.5, (z_start + z_end) * 0.5
                if np.hypot(centre_x - px, centre_z - pz) > radius:
                    continue
                if landform.height_at(centre_x, centre_z) > level - 0.05:
                    continue
                corners = [[x_start, level, z_start], [x_start, level, z_end],
                           [x_end, level, z_end], [x_end, level, z_start]]
                uvs = [[x_start / scale, z_start / scale], [x_start / scale, z_end / scale],
                       [x_end / scale, z_end / scale], [x_end / scale, z_start / scale]]
                geometry.add(corners, [normal] * 4, uvs, [0, 1, 2, 0, 2, 3])
    return geometry


def edge_apron(landform: Landform, overhang: float = 6.0) -> Geometry:
    """A skirt extending the landform past the world bounds.

    Without it a grounding raycast fired exactly on the boundary line can slip
    between the outermost triangles and miss, which would drop an actor to the
    manifest fallback height. The apron guarantees the walk surface strictly
    contains the declared bounds.
    """
    geometry = Geometry()
    height = landform.height
    x_axis, z_axis = landform.x, landform.z
    scale = UV_SCALE["ground"]
    count = len(x_axis)
    edges = (
        [(0, index) for index in range(count)],                      # -Z edge
        [(count - 1, index) for index in range(count)],              # +Z edge
        [(index, 0) for index in range(count)],                      # -X edge
        [(index, count - 1) for index in range(count)],              # +X edge
    )
    outward = ((0.0, -1.0), (0.0, 1.0), (-1.0, 0.0), (1.0, 0.0))
    for edge, (out_x, out_z) in zip(edges, outward):
        for step in range(len(edge) - 1):
            (z0, x0), (z1, x1) = edge[step], edge[step + 1]
            inner = [
                [float(x_axis[x0]), float(height[z0, x0]), float(z_axis[z0])],
                [float(x_axis[x1]), float(height[z1, x1]), float(z_axis[z1])],
            ]
            outer = [[point[0] + out_x * overhang, point[1] - 1.5,
                      point[2] + out_z * overhang] for point in inner]
            corners = [inner[0], inner[1], outer[1], outer[0]]
            # Counter-clockwise seen from above requires (edge x outward)_y > 0,
            # which holds on the -Z and +X edges and is reversed on the others.
            if (out_z - out_x) > 0:
                corners = [inner[1], inner[0], outer[0], outer[1]]
            uvs = [[point[0] / scale, point[2] / scale] for point in corners]
            normal = [0.0, 1.0, 0.0]
            geometry.add(corners, [normal] * 4, uvs, [0, 1, 2, 0, 2, 3])
    return geometry
