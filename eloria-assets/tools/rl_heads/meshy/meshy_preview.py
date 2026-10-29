"""Workbench previews of a Meshy GLB: textured (flat) and clay rows, five yaws, framed on the head.

blender -b --factory-startup --python meshy_preview.py -- <model.glb> <out.png> [head_fraction=0.55]
glTF +Z (front) becomes Blender -Y on import, so yaw 0 looks at the face if Meshy faces +Z.
"""
import bpy, sys, math, mathutils, os

argv = sys.argv[sys.argv.index('--') + 1:]
glb, out = argv[0], argv[1]
head_frac = float(argv[2]) if len(argv) > 2 else 0.55
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
lo = mathutils.Vector((1e9, 1e9, 1e9)); hi = -lo
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        lo = mathutils.Vector(map(min, lo, w)); hi = mathutils.Vector(map(max, hi, w))
top = hi.z; bottom = hi.z - (hi.z - lo.z) * head_frac
centre = mathutils.Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, (top + bottom) / 2))
size = max(top - bottom, (hi.x - lo.x) * 0.7) * 1.08

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.render.resolution_x = sc.render.resolution_y = 512
sc.display.shading.light = 'STUDIO'
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.12, 0.12, 0.14)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = size

from PIL import Image  # noqa: E402  (bpy's python has Pillow here)
tiles = []
for mode in ('TEXTURE', 'SINGLE'):
    sc.display.shading.color_type = mode
    sc.display.shading.single_color = (0.72, 0.72, 0.72)
    sc.display.shading.light = 'FLAT' if mode == 'TEXTURE' else 'STUDIO'
    row = []
    for yaw in (0, 40, 90, 180, 270):
        a = math.radians(yaw)
        d = mathutils.Vector((math.sin(a), -math.cos(a), 0.0))
        cam.location = centre + d * 5.0
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        p = out[:-4] + f'_{mode.lower()}_{yaw}.png'
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        row.append(p)
    tiles.append(row)
W = 512
sheet = Image.new('RGB', (W * 5, W * 2))
for r, row in enumerate(tiles):
    for c, p in enumerate(row):
        sheet.paste(Image.open(p).convert('RGB'), (c * W, r * W))
        os.remove(p)
sheet.save(out)
print('saved', out)
