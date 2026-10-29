import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import bpy, sys, os, math, mathutils
argv = sys.argv[sys.argv.index('--') + 1:]; sex, outdir = argv[0], argv[1]
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
root = paths.REPO + '/godot-client/assets/actors/native/races/'
bpy.ops.import_scene.gltf(filepath=root + f'luminous_{sex}.glb')
for o in bpy.context.scene.objects:
    if o.type == 'MESH' and o.name.split('.')[0] not in ('body', 'scalp', 'eyes', 'eyebrows'): o.hide_render = True
sc = bpy.context.scene; sc.render.engine = 'BLENDER_EEVEE'; sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = 600; sc.render.resolution_y = 700
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.8, 0.8, 0.8)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = 0.32
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
L = bpy.data.lights.new('sun', 'SUN'); L.energy = 3.0; lo = bpy.data.objects.new('sun', L); sc.collection.objects.link(lo); lo.rotation_euler = (math.radians(50), 0, math.radians(-30))
center = mathutils.Vector((0, 0.0, 1.62))
for v, az in (('front', 0), ('tq', 35), ('side', 90)):
    a = math.radians(az); d = mathutils.Vector((math.sin(a), -math.cos(a), 0))
    co.location = center + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(outdir, f'{sex}_{v}.png'); bpy.ops.render.render(write_still=True)
