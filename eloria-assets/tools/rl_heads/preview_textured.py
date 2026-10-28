"""Blender EEVEE preview: shipped body (head triangles cut, recoloured) + RL head with a composed look.

blender -b --factory-startup --python preview_textured.py -- <sex> <head.glb> <look.png> <eye.png> <outdir> <skinhex> <eyehex> [views] [hair.glb ...]
"""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import bpy, sys, os, math, mathutils, json, bmesh, struct

argv = sys.argv[sys.argv.index('--') + 1:]
sex, head_glb, look_png, eye_png, outdir, skin_hex, eye_hex = argv[:7]
views = argv[7].split(',') if len(argv) > 7 else ['front', 'tq', 'side']
extra_glbs = argv[8:]
os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
WT = paths.REPO


def hexc(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def s2l(c):
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


skin = s2l(hexc(skin_hex))
eyec = s2l(hexc(eye_hex))
bpy.ops.import_scene.gltf(filepath=f'{WT}/godot-client/assets/actors/native/races/luminous_{sex}.glb')
data = open(head_glb, 'rb').read()
jl = struct.unpack_from('<I', data, 12)[0]
gj = json.loads(data[20:20 + jl])
cut = gj['asset']['extras']['rlHead']['bodyCut']
ref = {'female': [0.8139, 0.6332, 0.5323], 'male': [0.8268, 0.6364, 0.5191]}[sex]
for o in list(bpy.context.scene.objects):
    if o.type != 'MESH':
        continue
    nm = o.name.split('.')[0]
    if nm in cut['hideMeshes'] or nm.startswith('wardrobe_head'):
        o.hide_render = True
        continue
    if nm == 'body':
        neck = mathutils.Vector((0, 1.4523, -0.0514)); hj = mathutils.Vector((0, 1.5685, 0.0114))
        dg = (hj - neck).normalized(); og = neck + cut['travel'] * dg
        dB = mathutils.Vector((dg.x, -dg.z, dg.y)); oB = mathutils.Vector((og.x, -og.z, og.y))
        bm = bmesh.new(); bm.from_mesh(o.data)
        dele = [f for f in bm.faces if any((o.matrix_world @ v.co - oB).dot(dB) > 0 for v in f.verts)]
        bmesh.ops.delete(bm, geom=dele, context='FACES'); bm.to_mesh(o.data); bm.free()
        for slot in o.material_slots:
            m = slot.material
            if not m or not m.use_nodes:
                continue
            nt = m.node_tree
            bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf is None or not bsdf.inputs['Base Color'].links:
                continue
            src = bsdf.inputs['Base Color'].links[0].from_socket
            mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            mix.inputs[7].default_value = (*[s / r for s, r in zip(skin, ref)], 1)
            nt.links.new(src, mix.inputs[6]); nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])
            bsdf.inputs['Roughness'].default_value = 0.7
bpy.ops.import_scene.gltf(filepath=head_glb)
for g in extra_glbs:
    bpy.ops.import_scene.gltf(filepath=g)
look = bpy.data.images.load(look_png)
eyei = bpy.data.images.load(eye_png)
lash = bpy.data.images.load(f'{WT}/.local/rl-heads/blender_profile/extensions/.user/user_default/mpfb/data/eyelashes/eyelashes02/eyelashes02.png')
for o in bpy.context.scene.objects:
    if o.type != 'MESH' or not o.name.startswith('rl_head'):
        continue
    for slot in o.material_slots:
        m = slot.material
        nm = m.name.split('.')[0]
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        for l in list(bsdf.inputs['Base Color'].links):
            nt.links.remove(l)
        if nm == 'rl_skin':
            t = nt.nodes.new('ShaderNodeTexImage'); t.image = look
            nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
            bsdf.inputs['Roughness'].default_value = 0.58
            bsdf.inputs['Subsurface Weight'].default_value = 0.03
            bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.35, 0.2)
            bsdf.inputs['Subsurface Scale'].default_value = 0.01
        elif nm == 'rl_eye':
            t = nt.nodes.new('ShaderNodeTexImage'); t.image = eyei
            mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
            mix.inputs[7].default_value = (*[min(c * 1.6, 1) for c in eyec], 1)
            nt.links.new(t.outputs['Alpha'], mix.inputs['Factor']); nt.links.new(t.outputs['Color'], mix.inputs[6])
            nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])
            bsdf.inputs['Roughness'].default_value = 0.15
        elif nm == 'rl_cornea':
            bsdf.inputs['Base Color'].default_value = (1, 1, 1, 1); bsdf.inputs['Alpha'].default_value = 0.0
            m.surface_render_method = 'BLENDED'
        elif nm == 'rl_lash':
            t = nt.nodes.new('ShaderNodeTexImage'); t.image = lash
            bsdf.inputs['Base Color'].default_value = (0.02, 0.015, 0.012, 1)
            nt.links.new(t.outputs['Alpha'], bsdf.inputs['Alpha']); m.surface_render_method = 'DITHERED'
        elif nm == 'rl_brow':
            bsdf.inputs['Alpha'].default_value = 0.0; m.surface_render_method = 'DITHERED'
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = 700; sc.render.resolution_y = 800
sc.eevee.taa_render_samples = 32
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.55, 0.55, 0.56, 1)
w.node_tree.nodes['Background'].inputs[1].default_value = 0.35


def light(name, energy, rot, size=2.0, col=(1, 1, 1)):
    L = bpy.data.lights.new(name, 'AREA'); L.energy = energy; L.size = size; L.color = col
    ob = bpy.data.objects.new(name, L); sc.collection.objects.link(ob)
    a, e = math.radians(rot[0]), math.radians(rot[1])
    d = mathutils.Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    ob.location = mathutils.Vector((0, 0, 1.62)) + d * 2.0
    ob.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()


light('key', 70, (-35, 30), 1.5, (1.0, 0.96, 0.9))
light('fill', 22, (50, 5), 2.5, (0.85, 0.9, 1.0))
light('rim', 45, (160, 25), 1.0)
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.ortho_scale = float(os.environ.get('RL_ORTHO', '0.36'))
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
center = mathutils.Vector((0, 0.0, float(os.environ.get('RL_CY', '1.60'))))
for v in views:
    az, el = {'front': (0, 0), 'tq': (-38, 8), 'side': (90, 0), 'back': (180, 0), 'sidel': (-90, 0), 'close': (-20, 4)}[v]
    a = math.radians(az); e = math.radians(el)
    d = mathutils.Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    co.location = center + d * 2.0; co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(outdir, f'{v}.png'); bpy.ops.render.render(write_still=True)
