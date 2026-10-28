import bpy, sys, os, math, mathutils
argv = sys.argv[sys.argv.index('--') + 1:]
glb, outdir = argv[0], argv[1]; os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sc.view_settings.view_transform = 'Standard'
sc.display.shading.light = 'STUDIO'; sc.display.shading.show_cavity = True; sc.display.shading.color_type = 'SINGLE'
sc.render.resolution_x = 420; sc.render.resolution_y = 480
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.85, 0.85, 0.85)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = 0.3
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
meshes = [o for o in sc.objects if o.type == 'MESH']
for lod in range(3):
    for o in meshes: o.hide_render = not o.name.startswith(f'rl_head_lod{lod}')
    for v, az in (('f', 0), ('t', -40)):
        a = math.radians(az); d = mathutils.Vector((math.sin(a), -math.cos(a), 0.1))
        co.location = mathutils.Vector((0, 0, 1.6)) + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(outdir, f'lod{lod}_{v}.png'); bpy.ops.render.render(write_still=True)
