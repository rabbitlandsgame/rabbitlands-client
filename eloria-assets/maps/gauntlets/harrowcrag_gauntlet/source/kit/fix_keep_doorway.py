"""Open the Harrowcrag keep's doorway through its front wall (background Blender).

    blender --background --factory-startup --python fix_keep_doorway.py -- <in.glb> <out.glb>

Meshy drew the keep's round-arched doorway as a shallow painted recess, so
the undercroft inside (the run's vault: cache and waystone) had no way in.
This deletes the faces inside a passage box through the front wall, and the loose rubble
chunks lying on the floor inside the walls, in the
kit's own metres (it is placed at x0.732: a passage about 3.5 m wide and
4 m high). The ruin is open shells already, so the cut needs no capping.
"""
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[:2]
# glTF frame: x across the front, y up, +z out of the front face. Blender imports z-up with glTF z -> -y.
X0, X1 = -3.4, 1.6
Y0, Y1 = -0.5, 5.6
Z0, Z1 = 3.5, 16.5

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bm = bmesh.new()
bm.from_mesh(obj.data)
mw = obj.matrix_world
doomed = []
for face in bm.faces:
    c = mw @ face.calc_center_median()
    gx, gy, gz = c.x, c.z, -c.y                     # back to glTF axes
    if X0 <= gx <= X1 and Y0 <= gy <= Y1 and Z0 <= gz <= Z1:
        doomed.append(face)
bmesh.ops.delete(bm, geom=doomed, context="FACES")
# the undercroft floor: loose rubble chunks lying inside the walls go (the vault is walked through)
IX0, IX1, IZ0, IZ1, TOP = -10.5, 12.5, -9.5, 7.5, 3.5
bm.faces.ensure_lookup_table()
bm.faces.index_update()
seen, parts = set(), []
for face in bm.faces:
    if face.index in seen:
        continue
    part, stack = [], [face]
    seen.add(face.index)
    while stack:
        f = stack.pop()
        part.append(f)
        for e in f.edges:
            for g in e.link_faces:
                if g.index not in seen:
                    seen.add(g.index)
                    stack.append(g)
    parts.append(part)
loose_faces, loose = [], 0
for part in parts:
    pts = [mw @ v.co for f in part for v in f.verts]
    gx = [p.x for p in pts]; gy = [p.z for p in pts]; gz = [-p.y for p in pts]
    if min(gx) > IX0 and max(gx) < IX1 and min(gz) > IZ0 and max(gz) < IZ1 and max(gy) < TOP:
        loose_faces.extend(part)
        loose += 1
bmesh.ops.delete(bm, geom=loose_faces, context="FACES")
bm.to_mesh(obj.data)
bm.free()
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_yup=True,
                          export_apply=True, export_texcoords=True, export_normals=True,
                          export_materials="EXPORT", export_image_format="AUTO", export_animations=False,
                          export_cameras=False, export_lights=False)
print("DOORWAY_OK", len(doomed), "loose parts removed", loose)
