"""Blender (MPFB) likeness lab: build an MPFB human from a JSON spec and render
orthographic clay views of the head for comparison with the reference art.

blender -b --python head_lab.py -- spec.json outdir [--save file.blend]
spec: {"macro": {...MPFB macro dict...}, "targets": {"nose/nose-scale-horiz-incr": 0.3, ...},
       "custom_targets": {"path/to/x.target": w}, "proxies": ["eyes/high-poly/high-poly.mhclo", ...]}
"""
import bpy, sys, json, os, math, mathutils
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.services.locationservice import LocationService

argv = sys.argv[sys.argv.index('--') + 1:]
spec = json.load(open(argv[0])); outdir = argv[1]
save = argv[argv.index('--save') + 1] if '--save' in argv else None
views = spec.get('views', ['front', 'side', 'tq'])
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

def sysdata(rel):
    return os.path.join(LocationService.get_mpfb_data('targets'), rel)

macro = TargetService.get_default_macro_info_dict()
for k, v in spec.get('macro', {}).items():
    if k == 'race': macro['race'].update(v)
    else: macro[k] = v
h = HumanService.create_human(macro_detail_dict=macro)
for name, w in spec.get('targets', {}).items():
    p = sysdata(name if name.endswith('.target.gz') else name + '.target.gz')
    TargetService.load_target(h, p, weight=w, name=os.path.basename(name).replace('.target.gz', ''))
for p, w in spec.get('custom_targets', {}).items():
    TargetService.load_target(h, p, weight=w, name=os.path.splitext(os.path.basename(p))[0])
user = LocationService.get_user_data()
for rel in spec.get('proxies', ['eyes/high-poly/high-poly.mhclo']):
    HumanService.add_mhclo_asset(os.path.join(user, rel), h, asset_type='Eyes' if rel.startswith('eyes') else 'Eyebrows' if rel.startswith('eyebrows') else 'Eyelashes' if rel.startswith('eyelash') else 'Clothes', material_type='MAKESKIN', set_up_rigging=False)

# head frame from evaluated mesh
for m in h.modifiers: m.show_viewport = False
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
eh = h.evaluated_get(dg); me = eh.to_mesh()
vg = {g.name: g.index for g in h.vertex_groups}
def centroid(group):
    gi = vg[group]; pts = [h.matrix_world @ v.co for v in me.vertices if any(g.group == gi for g in v.groups)]
    return sum(pts, mathutils.Vector()) / len(pts)
eyeL = centroid('helper-l-eye'); eyeR = centroid('helper-r-eye')
bodyi = vg['body']
mid = [h.matrix_world @ v.co for v in me.vertices if abs(v.co.x) < 1e-4 and any(g.group == bodyi for g in v.groups)]
face = [p for p in mid if p.y < eyeL.y + 0.02]
nose = min(face, key=lambda p: p.y)
chin_band = [p for p in face if nose.z - 0.13 < p.z < nose.z - 0.04 and p.y < nose.y + 0.035]
menton = min(chin_band, key=lambda p: p.z)
eye_mid = (eyeL + eyeR) / 2
top = max((h.matrix_world @ v.co).z for v in me.vertices)
eh.to_mesh_clear()
for m in h.modifiers: m.show_viewport = True
bpy.context.view_layer.update()
print('LAB eye_mid', tuple(round(c, 4) for c in eye_mid), 'top', round(top, 4), 'ipd', round((eyeL - eyeR).length, 4))
lm3 = {'eye_mid': eye_mid, 'eyeL': eyeL, 'eyeR': eyeR, 'nose': nose, 'menton': menton}

# clay material
mat = bpy.data.materials.new('clay')
for o in bpy.context.scene.objects:
    if o.type == 'MESH':
        o.data.materials.clear(); o.data.materials.append(mat)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.view_settings.view_transform = 'Standard'
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'SINGLE'
sc.display.shading.single_color = (0.78, 0.62, 0.52)
sc.display.shading.show_cavity = True
sc.display.shading.cavity_type = 'BOTH'
sc.render.resolution_x = spec.get('res', [640, 800])[0]; sc.render.resolution_y = spec.get('res', [640, 800])[1]
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.85, 0.84, 0.83)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = spec.get('ortho', 0.34)
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
center = mathutils.Vector((0, eye_mid.y + 0.07, eye_mid.z - 0.03))
frames = {}
W, H = sc.render.resolution_x, sc.render.resolution_y
for v in views:
    az, el = {'front': (0, 0), 'side': (90, 0), 'tq': (-38, 12), 'back': (180, 0), 'tql': (38, 12)}[v]
    a = math.radians(az); e = math.radians(el)
    # MPFB: the face looks toward -Y (Blender Z-up).
    d = mathutils.Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    co.location = center + d * 2.0
    co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    inv = co.matrix_world.inverted(); px = {}
    for k, p in lm3.items():
        c = inv @ p
        M = max(W, H); px[k] = [W / 2 + c.x / cam.ortho_scale * M, H / 2 - c.y / cam.ortho_scale * M]
    frames[v] = px
    sc.render.filepath = os.path.join(outdir, f'{v}.png')
    bpy.ops.render.render(write_still=True)
json.dump({'ipd': (eyeL - eyeR).length, 'top': top, 'views': frames}, open(os.path.join(outdir, 'frame.json'), 'w'), indent=1)
if save:
    bpy.ops.wm.save_as_mainfile(filepath=save)
