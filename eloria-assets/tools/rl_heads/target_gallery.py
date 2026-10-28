"""Blender: render a labelled front/side gallery of individual MPFB targets on a base human."""
import bpy, sys, json, os, math, mathutils
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
argv = sys.argv[sys.argv.index('--') + 1:]
spec = json.load(open(argv[0])); outdir = argv[1]; os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
macro = TargetService.get_default_macro_info_dict()
for k, v in spec['macro'].items():
    if k == 'race': macro['race'].update(v)
    else: macro[k] = v
h = HumanService.create_human(macro_detail_dict=macro)
root = LocationService.get_mpfb_data('targets')
for name, w in spec.get('targets', {}).items():
    TargetService.load_target(h, os.path.join(root, name + '.target.gz'), weight=w, name='base_' + os.path.basename(name))
keys = []
for name in spec['gallery']:
    nm = 'g_' + os.path.basename(name)
    TargetService.load_target(h, os.path.join(root, name + '.target.gz'), weight=0.0, name=nm); keys.append((name, nm))
mat = bpy.data.materials.new('clay')
h.data.materials.clear(); h.data.materials.append(mat)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.view_settings.view_transform = 'Standard'
sc.display.shading.light = 'STUDIO'; sc.display.shading.show_cavity = True
sc.render.resolution_x = spec.get('res', [320, 380])[0]; sc.render.resolution_y = spec.get('res', [320, 380])[1]
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.85, 0.84, 0.83)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = spec.get('ortho', 0.2)
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
center = mathutils.Vector(spec.get('center', (0, -0.07, 1.48)))
def shoot(tag):
    for v, az in ((('f', 0), ('s', 90)) if spec.get('side', True) else (('f', 0),)):
        a = math.radians(az); d = mathutils.Vector((math.sin(a), -math.cos(a), 0))
        c = center + (mathutils.Vector((0, 0.03, 0)) if v == 's' else mathutils.Vector())
        co.location = c + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(outdir, f'{tag}_{v}.png'); bpy.ops.render.render(write_still=True)
kb = h.data.shape_keys.key_blocks
shoot('base')
for i, (name, nm) in enumerate(keys):
    kb[nm].value = spec.get('w', 1.0); shoot(f'{i:02d}'); kb[nm].value = 0.0
json.dump([n for n, _ in keys], open(os.path.join(outdir, 'names.json'), 'w'))
