"""Blender: shipped body with its head triangles hidden + RL head GLB, clay/normal renders."""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import bpy, sys, os, math, mathutils, json, bmesh
argv = sys.argv[sys.argv.index('--') + 1:]
sex, head_glb, outdir = argv[0], argv[1], argv[2]
mode = argv[3] if len(argv) > 3 else 'clay'
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
root = paths.REPO + '/godot-client/assets/actors/native/races/'
bpy.ops.import_scene.gltf(filepath=root + f'luminous_{sex}.glb')
body_objs = list(bpy.context.scene.objects)
# hidden triangles from the head glb extras
import struct
data = open(head_glb, 'rb').read(); jl = struct.unpack_from('<I', data, 12)[0]; gj = json.loads(data[20:20 + jl])
cut = gj['asset']['extras']['rlHead']['bodyCut']
hidden = set()
for s0, n in cut['hiddenBodyTriangles']:
    hidden.update(range(s0, s0 + n))
for o in body_objs:
    if o.type != 'MESH': continue
    nm = o.name.split('.')[0]
    if nm in cut['hideMeshes'] or nm.startswith('wardrobe_'):
        o.hide_render = True; continue
    if nm == 'body':
        # same rule as the runtime cut: a triangle goes when all corners lie above the neck plane
        tr = cut['travel']
        neck = mathutils.Vector((0, 1.4523, -0.0514)); headj = mathutils.Vector((0, 1.5685, 0.0114))
        dg = (headj - neck).normalized(); og = neck + tr * dg
        # glTF (x, y, z) -> Blender (x, -z, y)
        dB = mathutils.Vector((dg.x, -dg.z, dg.y)); oB = mathutils.Vector((og.x, -og.z, og.y))
        me = o.data; bm = bmesh.new(); bm.from_mesh(me)
        dele = [f for f in bm.faces if any((o.matrix_world @ v.co - oB).dot(dB) > 0 for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context='FACES'); bm.to_mesh(me); bm.free()
bpy.ops.import_scene.gltf(filepath=head_glb)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.view_settings.view_transform = 'Standard'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL' if mode == 'mat' else 'OBJECT'
sc.display.shading.show_cavity = False
for o in sc.objects:
    if o.type == 'MESH':
        o.color = (0.8, 0.62, 0.52, 1) if o.name.startswith('body') else (0.62, 0.72, 0.85, 1)
sc.render.resolution_x = 700; sc.render.resolution_y = 800
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.9, 0.9, 0.9)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = float(argv[4]) if len(argv) > 4 else 0.42
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
center = mathutils.Vector((0, 0.0, float(argv[5]) if len(argv) > 5 else 1.58))
for v, az, el in (('front', 0, 0), ('tq', 40, 10), ('side', 90, 0), ('back', 180, 0), ('under', 20, -35)):
    a = math.radians(az); e = math.radians(el); d = mathutils.Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    co.location = center + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(outdir, f'{v}.png'); bpy.ops.render.render(write_still=True)
