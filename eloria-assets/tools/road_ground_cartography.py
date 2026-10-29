"""Offline-only road-field atlas for the maintained native map rasterizer.

No road geometry or images are written to runtime assets. A temporary linear
RGBA atlas resolves source affine UVs/style factors at field resolution, while
the retained ground triangles supply depth. Props, bridges and water still use
the ordinary native z-buffer. Normal/ORM texture omission matches cartography.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

VERSION = 1
DEPTH_BIAS_METRES = .0005


def dependencies(repository, manifest_path, config):
    """One strict metadata/runtime closure, including every field/image slot."""
    repository, manifest_path = Path(repository).resolve(), Path(manifest_path).resolve()
    tools = str(repository / "godot-client/tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from road_ground_dependencies import dependencies as declared
    result = declared(repository, manifest_path, config)
    if not config:
        return result
    metadata_path = (manifest_path.parent / config["metadata"]).resolve()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    field = metadata["field"]
    records = [(row["file"], row.get("file_sha256", row["sha256"]))
               for row in [*field["coverage_mips"], field["triangle_ids"], field["affine_coefficients"]]]
    for style in metadata["styles"]:
        records.extend((image["uri"], style["externalResources"][image["uri"]])
                       for image in style["material_document"].get("images", []))
    for uri, expected in records:
        path = (metadata_path.parent / uri).resolve()
        if result.get(path) != expected:
            raise ValueError(f"Undeclared/conflicting road-ground render dependency: {uri}")
    return result


def load(repository, manifest_path, config):
    deps = dependencies(repository, manifest_path, config)
    path = (Path(manifest_path).parent / config["metadata"]).resolve()
    metadata = json.loads(path.read_text(encoding="utf-8"))
    import numpy as np
    from PIL import Image
    import road_terrain_blend as producer
    ids, coefficients = producer.read_field(path.parent, metadata["field"])
    alpha = np.asarray(Image.open(path.parent / metadata["field"]["coverage_mips"][0]["file"]),
                       dtype=np.uint8)
    return metadata, ids, coefficients, alpha, path, deps


def _bilinear(texture, uv, repeat=(True, True)):
    import numpy as np
    h, w = texture.shape[:2]
    position = np.asarray(uv, float) * [w, h] - .5
    lower = np.floor(position).astype(np.int64)
    weight = position - lower
    x0 = lower[:, 0] % w if repeat[0] else np.clip(lower[:, 0], 0, w - 1)
    x1 = (lower[:, 0] + 1) % w if repeat[0] else np.clip(lower[:, 0] + 1, 0, w - 1)
    y0 = lower[:, 1] % h if repeat[1] else np.clip(lower[:, 1], 0, h - 1)
    y1 = (lower[:, 1] + 1) % h if repeat[1] else np.clip(lower[:, 1] + 1, 0, h - 1)
    a = texture[y0, x0] * (1 - weight[:, :1]) + texture[y0, x1] * weight[:, :1]
    b = texture[y1, x0] * (1 - weight[:, :1]) + texture[y1, x1] * weight[:, :1]
    return a * (1 - weight[:, 1:]) + b * weight[:, 1:]


def bake_atlas(rc, pool, metadata, ids, coefficients, alpha, path, chunk):
    """Resolve field-selected source albedo, using its analytic mip footprint."""
    import numpy as np
    from PIL import Image
    h, w = ids.shape
    if max(w, h) > 512:
        raise ValueError("Road field exceeds native atlas layer resolution")
    grid = metadata["field"]["grid"]
    ppm = float(grid["pixels_per_metre"])
    if ppm != 4:
        raise ValueError("Cartography expects production 4 px/m road fields")
    # Resolve directly at the native layer's texel centres. Prefiltering at
    # 4 px/m and then resizing/minifying again would erase road grain twice.
    # The field ID/coverage stays 4 px/m; its selected affine map can evaluate
    # source colour at any point without inventing another field resolution.
    yy, xx = np.indices((512, 512), dtype=np.float64)
    dx, dz = (xx + .5) * (w / ppm / 512), (yy + .5) * (h / ppm / 512)
    field_x = np.clip(np.floor(dx * ppm).astype(int), 0, w - 1)
    field_z = np.clip(np.floor(dz * ppm).astype(int), 0, h - 1)
    chosen = coefficients[ids[field_z, field_x] - 1]
    uv = np.stack((chosen[..., 0] + chosen[..., 2] * dx + chosen[..., 3] * dz,
                   chosen[..., 1] + chosen[..., 4] * dx + chosen[..., 5] * dz), axis=-1)
    styles = chosen[..., 6].astype(np.int32)
    if np.any(styles < 0) or np.any(styles >= len(metadata["styles"])):
        raise ValueError("Invalid road cartography style ID")
    factors = np.array([row["material_document"]["materials"][0].get("pbrMetallicRoughness", {}).get(
        "baseColorFactor", [1, 1, 1, 1]) for row in metadata["styles"]], float)
    common = np.maximum(factors.max(axis=0), 1e-12)
    result = np.empty((512, 512, 4), np.float64)
    result[:] = [0, 0, 0, 255]
    for row in metadata["styles"]:
        identity = int(row["id"])
        doc = row["material_document"]
        material = doc["materials"][0]
        pbr = material.get("pbrMetallicRoughness", {})
        if float(pbr.get("roughnessFactor", 1)) != 1 or float(pbr.get("metallicFactor", 1)) != 0:
            raise ValueError("Road atlas requires a deliberate adapter for differing roughness/metallic")
        slot = pbr["baseColorTexture"]
        if slot.get("texCoord", 0) != 0 or slot.get("extensions"):
            raise ValueError("Unsupported road cartography texture transform")
        key = pool.key(doc, b"", slot["index"], path, row["externalResources"], chunk)
        image = pool.images[key]
        wrap = rc.texture_wrap(doc, slot["index"])
        selected = styles == identity
        maps = chosen[selected]
        gx = np.stack((maps[:, 2], maps[:, 4]), axis=-1) * (w / ppm)
        gz = np.stack((maps[:, 3], maps[:, 5]), axis=-1) * (h / ppm)
        trace = (gx * gx + gz * gz).sum(axis=1)
        determinant = (gx[:, 0] * gz[:, 1] - gx[:, 1] * gz[:, 0]) ** 2
        footprint = np.sqrt((trace + np.sqrt(np.maximum(trace * trace - 4 * determinant, 0))) * .5)
        levels = np.clip(np.floor(np.log2(np.maximum(footprint, 1)) + .5), 0, 9).astype(np.int8)
        samples = np.empty((selected.sum(), 4), float)
        selected_uv = uv[selected]
        for level in np.unique(levels):
            at = levels == level
            texture = rc.mip_albedo(image, int(level), wrap)
            samples[at] = _bilinear(texture.astype(float), selected_uv[at], tuple(v == rc.REPEAT for v in wrap))
        result[selected] = samples * factors[identity] / common
    mask_uv = np.column_stack(((xx.ravel() + .5) / 512, (yy.ravel() + .5) / 512))
    raw_alpha = _bilinear(alpha[..., None].astype(float), mask_uv, (False, False)).reshape(512, 512)
    result[..., 3] *= raw_alpha / 255.
    pixels = np.clip(np.rint(result), 0, 255).astype(np.uint8)
    return np.ascontiguousarray(pixels), tuple(common)


def _triangle_key(triangle):
    return tuple(sorted(tuple(round(float(v), 5) for v in point[[0, 2]]) for point in triangle))


def highest_ground_triangles(ground, frame_name, target_names):
    """Keep ownership-clipped Base triangles and use highest matching patch Y.

    Published patches reuse the Base faces. A generic barycentric fallback
    handles clipped patch faces whose vertex ordering/edge partition differs.
    """
    import numpy as np
    base, others = [], {}
    extra = []
    for name, positions, normals, indices in ground:
        if name not in target_names:
            continue
        triangles = positions[np.asarray(indices).reshape(-1, 3)].astype(float)
        for triangle in triangles:
            key = _triangle_key(triangle)
            if name == frame_name:
                base.append(triangle)
            else:
                previous = others.get(key)
                if previous is None or triangle[:, 1].mean() > previous[:, 1].mean():
                    others[key] = triangle
    if not base:
        raise ValueError("Road field has no retained Base ground triangles")
    keys = {_triangle_key(t) for t in base}
    extra = [triangle for key, triangle in others.items() if key not in keys]
    result = []
    for triangle in base:
        high = others.get(_triangle_key(triangle))
        if high is not None:
            # Align vertices by XZ, never source index/triangle order.
            for point in triangle:
                distances = np.linalg.norm(high[:, [0, 2]] - point[[0, 2]], axis=1)
                point[1] = max(point[1], high[int(distances.argmin()), 1])
        result.append(triangle)
    if extra:
        # Source variants with different patch partitions are unusual. Apply
        # their exact plane only where a proxy vertex lies inside the patch.
        vertices = np.asarray(result).reshape(-1, 3)
        for triangle in extra:
            low, high = triangle[:, [0, 2]].min(axis=0), triangle[:, [0, 2]].max(axis=0)
            selected = np.all(vertices[:, [0, 2]] >= low - 1e-6, axis=1) & np.all(vertices[:, [0, 2]] <= high + 1e-6, axis=1)
            points = vertices[selected]
            if not len(points):
                continue
            matrix = np.column_stack((triangle[1, [0, 2]] - triangle[0, [0, 2]], triangle[2, [0, 2]] - triangle[0, [0, 2]]))
            if abs(np.linalg.det(matrix)) < 1e-12:
                continue
            uv = np.linalg.solve(matrix, (points[:, [0, 2]] - triangle[0, [0, 2]]).T).T
            inside = np.all(uv >= -1e-6, axis=1) & (uv.sum(axis=1) <= 1 + 1e-6)
            heights = triangle[0, 1] + uv @ (triangle[1:, 1] - triangle[0, 1])
            points[inside, 1] = np.maximum(points[inside, 1], heights[inside])
            vertices[selected] = points
        result = vertices.reshape(-1, 3, 3)
    return np.asarray(result)


def append(rc, pool, output, ground, repository, manifest_path, config, chunk):
    import numpy as np
    metadata, ids, coefficients, alpha, path, deps = load(repository, manifest_path, config)
    atlas, factor = bake_atlas(rc, pool, metadata, ids, coefficients, alpha, path, chunk)
    grid = metadata["field"]["grid"]
    origin = np.asarray(grid["origin_xz"], float)
    extent = np.asarray([grid["width"], grid["height"]], float) / grid["pixels_per_metre"]
    triangles = highest_ground_triangles(ground, metadata["source_frame_node"], {row["name"] for row in metadata["targets"]})
    low, high = triangles[:, :, [0, 2]].min(axis=1), triangles[:, :, [0, 2]].max(axis=1)
    keep = np.all(high >= origin, axis=1) & np.all(low <= origin + extent, axis=1)
    triangles = triangles[keep]
    active = []
    for triangle in triangles:
        lower = np.floor((triangle[:, [0, 2]].min(axis=0) - origin) * grid["pixels_per_metre"]).astype(int) - 1
        upper = np.ceil((triangle[:, [0, 2]].max(axis=0) - origin) * grid["pixels_per_metre"]).astype(int) + 1
        lower = np.maximum(lower, 0)
        upper = np.minimum(upper, [grid["width"], grid["height"]])
        if np.any(alpha[lower[1]:upper[1], lower[0]:upper[0]]):
            active.append(triangle)
    triangles = active
    # Clip to the field rectangle; world UVs remain in [0,1]. Alpha in the
    # texture, not coarse vertex colour, retains the 4 px/m road coverage.
    clipped = []
    for triangle in triangles:
        polygon = list(triangle)
        for axis, border, direction in [(0, origin[0], 1), (0, origin[0] + extent[0], -1),
                                         (2, origin[1], 1), (2, origin[1] + extent[1], -1)]:
            result = []
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                ia, ib = (a[axis] - border) * direction >= 0, (b[axis] - border) * direction >= 0
                if ia:
                    result.append(a)
                if ia != ib:
                    result.append(a + (b - a) * ((border - a[axis]) / (b[axis] - a[axis])))
            polygon = result
            if not polygon:
                break
        clipped.extend(np.array([polygon[0], polygon[i], polygon[i + 1]]) for i in range(1, len(polygon) - 1))
    if not clipped:
        raise ValueError("Road field does not intersect retained ground")
    triangles = np.asarray(clipped)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    normals[normals[:, 1] < 0] *= -1
    positions = triangles.reshape(-1, 3).astype(np.float32)
    positions[:, 1] += DEPTH_BIAS_METRES
    uv = ((positions[:, [0, 2]] - origin) / extent).astype(np.float32)
    name = "offline-road-field:" + hashlib.sha256(path.read_bytes()).hexdigest()
    pool.images[name] = atlas
    material = rc.R.RenderMaterial(name, factor, roughness=1., metallic=0., albedo=name,
                                   alpha_mode="MASK", alpha_cutoff=.5, double_sided=True)
    material.atlas_wrap = (rc.CLAMP_TO_EDGE, rc.CLAMP_TO_EDGE)
    rc.clamp_flags(material)
    material_index = len(output["materials"])
    output["materials"].append(material)
    output["parts"].append((positions, np.repeat(normals, 3, axis=0).astype(np.float32), uv,
                            np.arange(len(positions), dtype=np.int32), np.ones((len(positions), 4), np.float32), material_index))
    output["low"] = np.minimum(output["low"], positions.min(axis=0))
    output["high"] = np.maximum(output["high"], positions.max(axis=0))
    output["road_fields"] = {"version": VERSION, "triangles": len(triangles), "field_pixels": int(alpha.size),
                              "active_pixels": int(np.count_nonzero(alpha)), "dependency_files": len(deps)}
