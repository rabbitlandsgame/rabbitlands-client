"""Repack an authored MPFB study skin for better head detail at fixed memory.

The original mesh/preset and CC0 source paint remain untouched. This tool moves
the nine existing body UV islands into one 1024-square atlas, giving the head
more texels without another material, texture or runtime shader operation.
Use the emitted NPZ and skin PNG together when running fit_canonical.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, map_coordinates


# Inner rectangles in pixel coordinates. Each has an eight-pixel gutter. The
# head's UV island is sideways in the source; rotate it into the wide top row.
LAYOUT = {
    'head': (8, 8, 1008, 531, True),
    'body': (8, 560, 400, 450, False),
    'hand_left': (432, 560, 200, 192, False),
    'hand_right': (656, 560, 200, 192, False),
    'foot_left': (432, 776, 128, 122, False),
    'foot_right': (584, 776, 128, 122, False),
    'mouth_inside': (736, 776, 128, 96, False),
    'eye_inside_left': (888, 560, 96, 126, False),
    'eye_inside_right': (888, 710, 96, 126, False),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def uv_islands(uv: np.ndarray) -> list[np.ndarray]:
    """Find connected triangle islands by their existing UV edges."""
    parent = list(range(len(uv)))
    edges = {}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    quantized = np.rint(uv * 1_000_000).astype(np.int64)
    for i, tri in enumerate(quantized):
        for corner in range(3):
            edge = tuple(sorted((tuple(tri[corner]), tuple(tri[(corner + 1) % 3]))))
            previous = edges.get(edge)
            if previous is None:
                edges[edge] = i
            else:
                union(i, previous)
    groups = {}
    for i in range(len(uv)):
        groups.setdefault(find(i), []).append(i)
    return [np.array(ids, dtype=np.int32) for ids in groups.values()]


def classify_islands(islands: list[np.ndarray], vertices: np.ndarray,
                     triangles: np.ndarray) -> dict[str, np.ndarray]:
    """Identify the stable MPFB2 hm08 islands without depending on file order."""
    out = {}
    counts = {7876: 'body', 6232: 'head', 796: 'mouth_inside'}
    paired = {3196: 'hand', 2144: 'foot', 586: 'eye_inside'}
    for ids in islands:
        count = len(ids)
        if count in counts:
            name = counts[count]
        elif count in paired:
            # Names follow the input object's X sides for deterministic packing;
            # the game rig's anatomical naming is deliberately not inferred here.
            x = vertices[np.unique(triangles[ids])][:, 0].mean()
            name = paired[count] + ('_left' if x < 0.0 else '_right')
        else:
            raise ValueError(f'Unexpected hm08 UV island with {count} triangles')
        if name in out:
            raise ValueError(f'Duplicate island classification: {name}')
        out[name] = ids
    if set(out) != set(LAYOUT):
        raise ValueError(f'Expected nine hm08 islands; got {sorted(out)}')
    return out


def destination_uv(source_uv, lower, upper, rectangle, size):
    x, y, width, height, rotate = rectangle
    local = (source_uv - lower) / (upper - lower)
    if rotate:
        # Source +V maps to image +X; source +U maps to image +Y.
        px, py = local[..., 1], local[..., 0]
    else:
        px, py = local[..., 0], 1.0 - local[..., 1]
    return np.stack(((x + px * width) / size,
                     1.0 - (y + py * height) / size), axis=-1)


def sample_rectangle(source: Image.Image, lower, upper, rectangle):
    """Sample source paint with the exact affine used by destination_uv."""
    _, _, width, height, rotate = rectangle
    sw, sh = source.size
    span = upper - lower
    if rotate:
        au, av = span[0] * sw / height, span[1] * sh / width
        coefficients = (0.0, au, lower[0] * sw,
                        -av, 0.0, (1.0 - lower[1]) * sh)
    else:
        au, av = span[0] * sw / width, span[1] * sh / height
        coefficients = (au, 0.0, lower[0] * sw,
                        0.0, av, (1.0 - upper[1]) * sh)
    return np.array(source.transform((width, height), Image.Transform.AFFINE,
                                    coefficients, Image.Resampling.BICUBIC))


def fill_island_gutter(pixels, new_uv, rectangle, size, gutter=8):
    """Extend the island's own edge colors into unused pixels and its gutter."""
    x, y, width, height, _ = rectangle
    mask_image = Image.new('1', (width, height))
    draw = ImageDraw.Draw(mask_image)
    local = np.stack((new_uv[..., 0] * size - x - 0.5,
                      (1.0 - new_uv[..., 1]) * size - y - 0.5), axis=-1)
    for tri in local:
        draw.polygon([tuple(p) for p in tri], fill=1)
    mask = np.array(mask_image, dtype=bool)
    if not mask.any():
        raise ValueError('Empty UV raster mask')
    # Discard any unrelated source island painted in an unused part of the
    # crop. Nearest owned texels give this island a safe, opaque mip gutter.
    valid = np.pad(mask, gutter)
    padded = np.pad(pixels, ((gutter, gutter), (gutter, gutter), (0, 0)), mode='edge')
    nearest = distance_transform_edt(~valid, return_distances=False, return_indices=True)
    padded[~valid] = padded[nearest[0, ~valid], nearest[1, ~valid]]
    return Image.fromarray(padded), int(mask.sum())


def rasterize_surface(uv, vertices, normals, size, candidate_triangles):
    """Rasterize only the brow-height skin band into its existing UV chart."""
    positions = np.full((size, size, 3), np.nan, dtype=np.float32)
    facing = np.zeros((size, size), dtype=np.float32)
    for i in candidate_triangles:
        triangle_uv = uv[i]
        xy = np.stack((triangle_uv[:, 0] * size - 0.5,
                       (1 - triangle_uv[:, 1]) * size - 0.5), axis=-1)
        x0, y0 = np.maximum(np.floor(xy.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(xy.max(0)).astype(int), size - 1)
        edge1, edge2 = xy[1] - xy[0], xy[2] - xy[0]
        det = edge1[0] * edge2[1] - edge1[1] * edge2[0]
        if abs(det) < 1e-8 or x1 < x0 or y1 < y0:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        dx, dy = xx - xy[0, 0], yy - xy[0, 1]
        b1 = (dx * edge2[1] - dy * edge2[0]) / det
        b2 = (edge1[0] * dy - edge1[1] * dx) / det
        b0 = 1 - b1 - b2
        inside = (b0 >= -1e-6) & (b1 >= -1e-6) & (b2 >= -1e-6)
        weights = np.stack((b0[inside], b1[inside], b2[inside]), axis=-1)
        positions[yy[inside], xx[inside]] = weights @ vertices[i]
        facing[yy[inside], xx[inside]] = (weights @ normals[i])[:, 1]
    return positions, facing


def project_brows(atlas, arrays, metadata, max_depth_mm=5.0, color_override=None):
    """Bake the fitted CC0 brow card pigment onto nearby front-facing skin.

    The source brow card supplies shape, UVs and alpha. A two-by-two subpixel
    projection preserves its feathered silhouette without extra game geometry
    or transparency. The Blender input uses negative Y as the front direction.
    """
    required = ('brow_vertices', 'brow_triangles', 'brow_uv')
    if not any(key in arrays for key in required):
        return atlas, {'applied': False, 'reason': 'No authored brow asset in input mesh'}
    if not all(key in arrays for key in required) or not metadata.get('brow_texture'):
        raise ValueError('Incomplete authored brow asset or missing brow texture metadata')
    source_path = Path(metadata['brow_texture'])
    source = Image.open(source_path).convert('RGBA')
    source_pixels = np.asarray(source, dtype=np.float32) / 255.0
    brow_vertices = arrays['brow_vertices'][arrays['brow_triangles']]
    brow_uv = arrays['brow_uv']
    lower = brow_vertices.reshape(-1, 3).min(0)
    upper = brow_vertices.reshape(-1, 3).max(0)
    triangles = arrays['body_triangles']
    skin_vertices = arrays['body_vertices'][triangles]
    skin_normals = arrays['body_normals'][triangles]
    padding = max_depth_mm / 1000.0
    # Front normal ownership prevents a projected brow from ever appearing on
    # the back of the head or the inside of the eye/lip islands.
    candidate = ((skin_vertices[:, :, 0].max(1) >= lower[0] - padding) &
                 (skin_vertices[:, :, 0].min(1) <= upper[0] + padding) &
                 (skin_vertices[:, :, 2].max(1) >= lower[2] - padding) &
                 (skin_vertices[:, :, 2].min(1) <= upper[2] + padding) &
                 (skin_vertices[:, :, 1].min(1) <= upper[1] + padding) &
                 (skin_normals[:, :, 1].min(1) < -0.1))
    size = atlas.width
    positions, facing = rasterize_surface(arrays['body_uv'], skin_vertices, skin_normals,
                                         size * 2, np.flatnonzero(candidate))
    valid = np.isfinite(positions[:, :, 0]) & (facing < -0.1)
    yy, xx = np.where(valid)
    points = positions[yy, xx]
    opacity = np.zeros(len(points), dtype=np.float32)
    pigments = np.zeros((len(points), 3), dtype=np.float32)
    depth = np.full(len(points), np.inf, dtype=np.float32)
    color_hex = color_override or metadata.get('profile', {}).get('palette_srgb', {}).get('brow')
    if not color_hex:
        color_hex = '#34251c' if metadata['sex'] == 'male' else '#6b3625'
    if len(color_hex.lstrip('#')) != 6:
        raise ValueError('Brow color must be a six-digit sRGB hex color')
    selected_color = np.array([int(color_hex.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    for triangle, triangle_uv in zip(brow_vertices, brow_uv):
        xz = triangle[:, [0, 2]]
        edge1, edge2 = xz[1] - xz[0], xz[2] - xz[0]
        det = edge1[0] * edge2[1] - edge1[1] * edge2[0]
        if abs(det) < 1e-12:
            continue
        dx, dz = points[:, 0] - xz[0, 0], points[:, 2] - xz[0, 1]
        b1 = (dx * edge2[1] - dz * edge2[0]) / det
        b2 = (edge1[0] * dz - edge1[1] * dx) / det
        b0 = 1 - b1 - b2
        inside = (b0 >= -1e-6) & (b1 >= -1e-6) & (b2 >= -1e-6)
        ids = np.flatnonzero(inside)
        if not len(ids):
            continue
        bary = np.stack((b0[ids], b1[ids], b2[ids]), axis=-1)
        surface_y = bary @ triangle[:, 1]
        gaps = abs(surface_y - points[ids, 1])
        owned = (gaps <= padding) & (gaps < depth[ids])
        ids, bary, gaps = ids[owned], bary[owned], gaps[owned]
        if not len(ids):
            continue
        uvs = bary @ triangle_uv
        source_x = uvs[:, 0] * source.width - 0.5
        source_y = (1 - uvs[:, 1]) * source.height - 0.5
        sample = np.stack([map_coordinates(source_pixels[:, :, channel], [source_y, source_x],
                                           order=1, mode='nearest') for channel in range(4)], axis=-1)
        # Retain the source hair pigment variation while the portrait palette
        # chooses its color. Alpha, shape and tapered hairs come from the asset.
        value = np.clip(0.65 + sample[:, :3].max(1) * 1.7, 0.65, 1.3)
        pigments[ids] = np.clip(selected_color[None] * value[:, None], 0, 1)
        opacity[ids] = sample[:, 3]
        depth[ids] = gaps
    alpha_high = np.zeros((size * 2, size * 2), dtype=np.float32)
    premultiplied_high = np.zeros((size * 2, size * 2, 3), dtype=np.float32)
    alpha_high[yy, xx] = opacity
    premultiplied_high[yy, xx] = pigments * opacity[:, None]
    alpha = alpha_high.reshape(size, 2, size, 2).mean(axis=(1, 3))
    pigment = premultiplied_high.reshape(size, 2, size, 2, 3).mean(axis=(1, 3))
    original = np.asarray(atlas, dtype=np.float32) / 255.0
    composited = np.rint(np.clip(original * (1 - alpha[:, :, None]) + pigment, 0, 1) * 255).astype(np.uint8)
    changed = np.any(composited != np.asarray(atlas), axis=-1)
    if not changed.any():
        raise ValueError('Brow projection produced no pigment; check fitted geometry and depth gap')
    cy, cx = np.where(changed)
    projected = np.isfinite(depth) & (opacity > 1 / 255)
    report = {'applied': True, 'source_texture': str(source_path), 'source_texture_sha256': sha256(source_path),
              'source_triangles': len(brow_vertices), 'color_srgb': color_hex,
              'max_depth_gap_mm': max_depth_mm, 'observed_depth_gap_mm_max': float(depth[projected].max() * 1000),
              'supersampling': 2, 'changed_texels': int(changed.sum()),
              'changed_bounds_pixels': [int(cx.min()), int(cy.min()), int(cx.max()) + 1, int(cy.max()) + 1],
              'coverage_max': float(alpha.max()), 'coverage_texels': int((alpha > 1 / 255).sum()),
              'unchanged_outside_brow_coverage': bool(np.array_equal(composited[alpha == 0], np.asarray(atlas)[alpha == 0]))}
    return Image.fromarray(composited), report


def bake(mesh_path: Path, metadata_path: Path, output: Path, size=1024,
         max_brow_depth_mm=5.0, brow_color=None):
    if size not in (1024, 2048):
        raise ValueError('Atlas size must be 1024 or 2048')
    output.mkdir(parents=True, exist_ok=True)
    meta = json.loads(metadata_path.read_text())
    sex = meta['sex']
    source_path = Path(meta['skin_texture'])
    source = Image.open(source_path).convert('RGB')
    with np.load(mesh_path) as data:
        arrays = {k: data[k].copy() for k in data.files}
    original_arrays = {k: data.copy() for k, data in arrays.items()}
    source_uv = arrays['body_uv']
    vertices, triangles = arrays['body_vertices'], arrays['body_triangles']
    islands = classify_islands(uv_islands(source_uv), vertices, triangles)
    target_uv = np.empty_like(source_uv)
    atlas = Image.new('RGB', (size, size), (128, 94, 74))
    layout_scale = size // 1024
    gutter = 8 * layout_scale
    occupied = np.zeros((size, size), dtype=bool)
    report = []
    for name, default_rectangle in LAYOUT.items():
        rectangle = tuple(n * layout_scale for n in default_rectangle[:4]) + (default_rectangle[4],)
        x, y, width, height, rotate = rectangle
        ids = islands[name]
        uvs = source_uv[ids]
        lower, upper = uvs.reshape(-1, 2).min(0), uvs.reshape(-1, 2).max(0)
        new_uv = destination_uv(uvs, lower, upper, rectangle, size)
        target_uv[ids] = new_uv
        pixels = sample_rectangle(source, lower, upper, rectangle)
        tile, covered = fill_island_gutter(pixels, new_uv, rectangle, size, gutter)
        bounds = (x - gutter, y - gutter, x + width + gutter, y + height + gutter)
        x0, y0, x1, y1 = bounds
        if x0 < 0 or y0 < 0 or x1 > size or y1 > size or occupied[y0:y1, x0:x1].any():
            raise ValueError(f'Out of bounds or overlapping atlas rectangle: {name}')
        occupied[y0:y1, x0:x1] = True
        atlas.paste(tile, (x0, y0))
        src_pixels = (upper - lower) * np.array(source.size)
        old_1024 = (upper - lower) * 1024
        ordered_src = src_pixels[::-1] if rotate else src_pixels
        ordered_old = old_1024[::-1] if rotate else old_1024
        report.append({'name': name, 'triangles': len(ids), 'source_uv_lower': lower.tolist(),
                       'source_uv_upper': upper.tolist(), 'rectangle_pixels': list(rectangle),
                       'source_bbox_pixels': src_pixels.tolist(),
                       'linear_detail_vs_original_1024': (np.array([width, height]) / ordered_old).tolist(),
                       'linear_detail_vs_source': (np.array([width, height]) / ordered_src).tolist(),
                       'covered_texels': covered})
    if not np.isfinite(target_uv).all() or target_uv.min() < 0 or target_uv.max() > 1:
        raise ValueError('Invalid packed UV coordinates')
    arrays['body_uv'] = target_uv
    atlas, brows_report = project_brows(atlas, arrays, meta, max_brow_depth_mm, brow_color)
    mesh_output = output / f'{sex}-atlas.npz'
    skin_output = output / f'{sex}-skin-{size}.png'
    np.savez_compressed(mesh_output, **arrays)
    atlas.save(skin_output, optimize=True)
    changed = [k for k in arrays if not np.array_equal(arrays[k], original_arrays[k])]
    if changed != ['body_uv']:
        raise ValueError(f'Unexpected authored mesh changes: {changed}')
    receipt = {'schema': 1, 'sex': sex, 'size': size,
               'source_tool_sha256': sha256(Path(__file__)),
               'description': 'CC0 source skin UV repack with optional fitted source eyebrow pigment projection',
               'input_mesh': str(mesh_path.resolve()), 'input_mesh_sha256': sha256(mesh_path),
               'input_metadata_sha256': sha256(metadata_path),
               'source_skin': str(source_path), 'source_skin_sha256': sha256(source_path),
               'source_skin_size': list(source.size), 'changed_arrays': changed,
               'source_skin_license': 'MakeHuman core system asset, CC0',
               'source_skin_license_reference': 'https://static.makehumancommunity.org/mpfb/faq/use_in_closed_source.html',
               'output_mesh': str(mesh_output.resolve()), 'output_mesh_sha256': sha256(mesh_output),
               'output_skin': str(skin_output.resolve()), 'output_skin_sha256': sha256(skin_output),
               'output_skin_bytes': skin_output.stat().st_size, 'islands': report,
               'eyebrows': brows_report,
               'materials_added': 0, 'triangles_added': 0, 'textures_added_vs_body_baseline': 0,
               'rgba8_mip_bytes_per_skin': sum(max(1, size >> i) ** 2 * 4 for i in range(size.bit_length())),
               'limits': 'Source geometry and official skin paint are preserved outside source eyebrow coverage. Brow color is baked for this concept study; it is not a runtime hair-dye mask.'}
    receipt_path = output / f'{sex}-atlas-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--size', type=int, default=1024, choices=(1024, 2048))
    parser.add_argument('--max-brow-depth-mm', type=float, default=5.0)
    parser.add_argument('--brow-color', help='Optional six-digit sRGB hex color for the source brow pigment')
    args = parser.parse_args()
    receipt = bake(args.mesh, args.metadata, args.output, args.size,
                   args.max_brow_depth_mm, args.brow_color)
    print(json.dumps({k: receipt[k] for k in ('sex', 'size', 'changed_arrays', 'output_mesh', 'output_skin', 'output_skin_bytes')}))


if __name__ == '__main__':
    main()
