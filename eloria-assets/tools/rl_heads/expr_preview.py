import bpy, sys, os, math, mathutils
argv = sys.argv[sys.argv.index('--') + 1:]
glb, outdir = argv[0], argv[1]; shapes = argv[2].split(','); os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.view_settings.view_transform = 'Standard'
sc.display.shading.light = 'STUDIO'; sc.display.shading.show_cavity = True; sc.display.shading.color_type = 'MATERIAL'
sc.render.resolution_x = 360; sc.render.resolution_y = 360
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.85, 0.85, 0.85)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = 0.17
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
lod = [o for o in sc.objects if o.type == 'MESH' and o.name.startswith('rl_head_lod0')][0]
for o in sc.objects:
    if o.type == 'MESH': o.hide_render = o is not lod
for m in lod.data.materials:
    nm = m.name.split('.')[0]
    m.diffuse_color = {'rl_skin': (0.8, 0.62, 0.52, 1), 'rl_eye': (0.95, 0.95, 0.95, 1), 'rl_mouth': (0.9, 0.85, 0.75, 1), 'rl_bodypatch': (0.8, 0.62, 0.52, 1)}.get(nm, (0.1, 0.08, 0.07, 0 if nm in ('rl_cornea', 'rl_brow') else 1))
    if nm in ('rl_cornea', 'rl_brow', 'rl_lash'): m.diffuse_color = (0.1, 0.08, 0.07, 0.0)
kb = lod.data.shape_keys.key_blocks
d = mathutils.Vector((-0.3, -1, 0.05)).normalized()
co.location = mathutils.Vector((0, 0, 1.6)) + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
for sh in ['none'] + shapes:
    for k in kb: k.value = 0.0
    for part in sh.split('+'):
        if part in kb: kb[part].value = 1.0
    sc.render.filepath = os.path.join(outdir, f'{sh}.png'); bpy.ops.render.render(write_still=True)
