import bpy, sys
argv = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
r = bpy.ops.import_scene.gltf(filepath=argv[0])
print('IMPORT', r)
for o in bpy.context.scene.objects:
    print('OBJ', o.type, o.name, tuple(round(x, 3) for x in o.location), o.parent.name if o.parent else None,
          (len(o.data.vertices), len(o.data.polygons), [k.name for k in o.data.shape_keys.key_blocks][:6] if o.data.shape_keys else None) if o.type == 'MESH' else '')
    if o.type == 'MESH':
        import mathutils
        bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
        print('  bbox', [round(min(v[i] for v in bb), 3) for i in range(3)], [round(max(v[i] for v in bb), 3) for i in range(3)], 'mods', [m.type for m in o.modifiers])
