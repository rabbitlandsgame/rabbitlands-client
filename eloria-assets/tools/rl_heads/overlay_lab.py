"""Overlay the shipped luminous head and an MPFB head (silhouettes, front/side)."""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import bpy, sys, json, os, math, mathutils, bmesh
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
argv = sys.argv[sys.argv.index('--') + 1:]
sex, outdir = argv[0], argv[1]
xf = json.loads(argv[2]) if len(argv) > 2 else {}
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
root = paths.REPO + '/godot-client/assets/actors/native/races/'
bpy.ops.import_scene.gltf(filepath=root + f'luminous_{sex}.glb')
game = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.split('.')[0] in ('body', 'scalp', 'eyes', 'eyebrows')]
for o in bpy.context.scene.objects:
    if o.type == 'MESH' and o not in game: o.hide_render = True
for o in bpy.context.scene.objects:
    if o.type == 'ARMATURE': o.hide_render = True
macro = TargetService.get_default_macro_info_dict()
macro.update({'gender': 0.0 if sex == 'female' else 1.0, 'age': 0.52, 'muscle': 0.6, 'weight': 0.45, 'proportions': 0.75})
macro['race'].update({'caucasian': 0.9, 'asian': 0.05, 'african': 0.05})
h = HumanService.create_human(macro_detail_dict=macro, feet_on_ground=True)
s = xf.get('scale', 1.0); eye = mathutils.Vector(xf.get('eye', [0, -0.1126, 1.5013])); tgt = mathutils.Vector(xf.get('target', [0, -0.056, 1.636])); t = tgt - s * eye
h.scale = (s, s, s); h.location = t
gm = bpy.data.materials.new('g'); gm.diffuse_color = (1, 0, 0, 1)
mm = bpy.data.materials.new('m'); mm.diffuse_color = (0, 0, 1, 1)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.view_settings.view_transform = 'Standard'
sc.display.shading.light = 'FLAT'; sc.display.shading.color_type = 'MATERIAL'
sc.render.resolution_x = 700; sc.render.resolution_y = 800
sc.world = bpy.data.worlds.new('w'); sc.world.color = (1, 1, 1)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = 0.36
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
center = mathutils.Vector((0, 0.0, 1.60))
def render(tag, objs, mat):
    for o in sc.objects:
        if o.type == 'MESH': o.hide_render = o not in objs
    for o in objs:
        o.data.materials.clear(); o.data.materials.append(mat)
    for v, az in (('front', 0), ('side', 90)):
        a = math.radians(az); d = mathutils.Vector((math.sin(a), -math.cos(a), 0))
        co.location = center + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(outdir, f'{tag}_{v}.png'); bpy.ops.render.render(write_still=True)
render('game', game, gm)
render('mpfb', [h], mm)
# stats for mpfb (evaluated, helpers masked)
dg = bpy.context.evaluated_depsgraph_get(); eh = h.evaluated_get(dg); me = eh.to_mesh()
P = [h.matrix_world @ v.co for v in me.vertices]
print('MPFB top', max(p.z for p in P), 'zmin', min(p.z for p in P))
