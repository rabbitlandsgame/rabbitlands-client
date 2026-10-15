# Rebuild the human/cape review scene from files on disk (old bodies + old cape from develop ebdffd716,
# new bodies installed in the hm worktree, raw Meshy cape, animation library).
import bpy
from mathutils import Matrix

HM = "C:/rabbitlands/work-output/hm/godot-client/assets/actors/native"
OLD = SCR + "/old"
MESHY = "C:/rabbitlands/generate_models/human_bodies_2026-10/meshy_capes/cape_back.glb"
scn = bpy.context.scene

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)
for blk in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images, bpy.data.actions, bpy.data.cameras):
    for d in list(blk):
        if d.users == 0:
            blk.remove(d)


def import_into(path, cname, keep_actions=False):
    coll = bpy.data.collections.new(cname); scn.collection.children.link(coll)
    before = set(bpy.data.objects); acts = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    if not keep_actions:
        for a in list(bpy.data.actions):
            if a not in acts:
                bpy.data.actions.remove(a)
    return new


def body(path, cname, pre, x):
    new = import_into(path, cname)
    arm = next(o for o in new if o.type == 'ARMATURE')
    for o in list(new):
        if o.name.startswith('Icosphere'):
            bpy.data.objects.remove(o, do_unlink=True); continue
        o.name = pre + o.name.split('.')[0]
    arm.location = (x, 0, 0)
    arm.animation_data_clear()
    for o in bpy.data.collections[cname].objects:
        if o.name.endswith('wardrobe_head_band') or o.name.endswith('wardrobe_head_cap'):
            o.hide_set(True)
    return arm


import_into(HM + "/shared/Universal_Animation_Library.glb", 'lib', keep_actions=True)
m_old = body(OLD + "/luminous_male.glb", 'dev_male', 'M_', -0.55)
f_old = body(OLD + "/luminous_female.glb", 'dev_female', 'F_', 0.55)
m_new = body(HM + "/races/luminous_male.glb", 'new_male', 'NM_', -1.65)
f_new = body(HM + "/races/luminous_female.glb", 'new_female', 'NF_', 1.65)
bpy.context.view_layer.update()
exec(open(SCR + "/posekit.py").read())
for a in (m_old, f_old, m_new, f_new):
    pose_armature(a, style=False)

# raw Meshy cape: weld happens in the pipeline; keep it hidden
cb = import_into(MESHY, 'cape_back')
# old generic cape on its own canonical rig at x=1.2 (clearance reference)
oc = import_into(OLD + "/generic_cape.glb", 'old_cape')
for o in list(oc):
    if o.name.startswith('Icosphere'):
        bpy.data.objects.remove(o, do_unlink=True); continue
    if o.type == 'ARMATURE':
        o.name = 'OC_rig'; o.location = (1.2, 0, 0)
    elif o.type == 'MESH':
        o.name = 'OC_Cape'
bpy.data.collections.new('new_cape'); scn.collection.children.link(bpy.data.collections['new_cape'])

# the three tintable cape materials over the greyscale texture
grey = bpy.data.images.load(SCR + "/cape_grey.png", check_existing=True)
mats = []
for name, col in (('NC Cape Base', (0.52, 0.19, 0.17)), ('NC Cape Trim', (0.73, 0.35, 0.31)), ('NC Cape Detail', (0.31, 0.16, 0.15))):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = grey
    mix = nt.nodes.new('ShaderNodeMix'); mix.label = 'tint'; mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 1.0; mix.inputs[7].default_value = col + (1,)
    nt.links.new(tex.outputs['Color'], mix.inputs[6]); nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.9
    mats.append(m)
# a stub NC_cape so the pipeline inherits these materials
stub = bpy.data.meshes.new('NC_stub')
for m in mats:
    stub.materials.append(m)
nco = bpy.data.objects.new('NC_cape', stub); bpy.data.collections['new_cape'].objects.link(nco)

vl = bpy.context.view_layer.layer_collection.children
for name in ('lib', 'cape_back', 'old_cape'):
    vl[name].hide_viewport = True
for win in bpy.context.window_manager.windows:
    for area in win.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active; sp.shading.type = 'MATERIAL'; sp.overlay.show_bones = False
result = {"collections": [c.name for c in bpy.data.collections], "objects": len(bpy.data.objects)}
