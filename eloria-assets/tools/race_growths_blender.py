"""Blender half of race_growths.py prepare: decimate and unwrap the growths.

    blender --background --factory-startup --python race_growths_blender.py -- <in.npz> <out.npz>

<in.npz> holds, per side s in (left, right): s_P (welded float32 positions,
donor frame) and s_F (int32 triangles), plus target (int triangles per side).
Each side is collapse-decimated on its own to `target` triangles, the base
ring (the one open boundary loop) included. Both sides are then joined and
smart-UV-projected into one 0-1 square, so race_growths.py bakes one image.
<out.npz>: P (float32 vertices), F (int32 triangles), UV (float32 per
corner, shape (len(F), 3, 2)), side (int8 per triangle, 0 left / 1 right),
blender (version string). Never writes anywhere but <out.npz>.
"""
import math
from pathlib import Path
import sys

import bmesh
import bpy
import numpy as np

UV_ANGLE_LIMIT = math.radians(66.)
UV_ISLAND_MARGIN = .02
UV_PACK_MARGIN = .008
RING_PASSES = 2


def side_object(name, points, faces, target):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points.tolist(), [], faces.tolist())
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    for other in bpy.context.scene.objects:
        other.select_set(other is obj)
    # The base ring follows the ragged colour edge at source density and the
    # collapse keeps boundaries: thin it first (every other ring vertex
    # dissolved, RING_PASSES times), so the triangle budget goes to the cap.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    ring_before = sum(1 for v in bm.verts if v.is_boundary)
    for _ in range(RING_PASSES):
        ring = ordered_ring(bm)
        bmesh.ops.dissolve_verts(bm, verts=ring[1::2], use_face_split=False, use_boundary_tear=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3], quad_method='BEAUTY',
                              ngon_method='BEAUTY')
    ring_after = sum(1 for v in bm.verts if v.is_boundary)
    bm.to_mesh(obj.data)
    bm.free()
    modifier = obj.modifiers.new('GrowthReduction', 'DECIMATE')
    modifier.decimate_type = 'COLLAPSE'
    modifier.ratio = min(1., target/len(obj.data.polygons))
    modifier.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    print('GROWTH_SIDE', name, len(faces), '->', len(obj.data.polygons), 'ring', ring_before, '->', ring_after, flush=True)
    return obj


def ordered_ring(bm):
    """The longest open-boundary loop, in order."""
    boundary = {v for v in bm.verts if v.is_boundary}
    loops, seen = [], set()
    for start in sorted(boundary, key=lambda v: v.index):
        if start in seen:
            continue
        loop, v, prev = [], start, None
        while v not in seen:
            seen.add(v); loop.append(v)
            nxt = [e.other_vert(v) for e in v.link_edges if e.is_boundary and e.other_vert(v) is not prev
                   and e.other_vert(v) in boundary]
            if not nxt:
                break
            prev, v = v, nxt[0]
        loops.append(loop)
    return max(loops, key=len)


def main():
    source, target = (Path(a) for a in sys.argv[sys.argv.index('--')+1:][:2])
    data = np.load(source)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = [side_object(side, data[side+'_P'].astype(float), data[side+'_F'].astype(int), int(data['target']))
               for side in ('left', 'right')]
    counts = [len(o.data.polygons) for o in objects]
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=UV_ANGLE_LIMIT, island_margin=UV_ISLAND_MARGIN, area_weight=0.,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='ANY', scale=True,
                            merge_overlap=False, margin_method='SCALED', margin=UV_PACK_MARGIN,
                            shape_method='CONCAVE')
    bpy.ops.object.mode_set(mode='OBJECT')
    mesh = obj.data
    points = np.empty(len(mesh.vertices)*3, 'f4'); mesh.vertices.foreach_get('co', points)
    loops = np.empty(len(mesh.loops), 'i4'); mesh.loops.foreach_get('vertex_index', loops)
    totals = np.empty(len(mesh.polygons), 'i4'); mesh.polygons.foreach_get('loop_total', totals)
    if (totals != 3).any():
        raise ValueError('non-triangle face after decimation')
    uv = np.empty(len(mesh.loops)*2, 'f4'); mesh.uv_layers.active.data.foreach_get('uv', uv)
    # Joined order: the left object's faces first.
    side = np.repeat(np.arange(2, dtype='i1'), counts)
    np.savez(target, P=points.reshape(-1, 3), F=loops.reshape(-1, 3), UV=uv.reshape(-1, 3, 2), side=side,
             blender=np.array(bpy.app.version_string))
    print('GROWTH_BLENDER_OK', counts, str(target), flush=True)


main()
