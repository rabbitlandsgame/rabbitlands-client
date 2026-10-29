"""Textured preview renders of a hair / beard module on the RL head (Blender headless).

Run with the normal Python; it launches Blender (under the machine-wide GPU lock
when gpu_lock.sh is present) and then writes a contact sheet:

    python preview.py --sex female --asset ../../build/hair/mira_bun.glb \
        [--asset ../../build/beards/full_beard.glb] --name mira_bun \
        [--lod 0] [--color 0.45,0.12,0.04] [--ref ../../ref/mira_underclothes_front_head.png]

Writes build/hair/preview/<name>/{front,profile,back,tq,close}.png and
build/hair/preview/<name>/sheet.png (+ the reference crop if given).

Shading mirrors the runtime contract: texture luminance x tint, root darkening
from UV v, per-lock brightness from COLOR_0.R, ao from COLOR_0.B, alpha-tested
(clip) strand atlas on rl_hair_card / rl_beard, clump texture on rl_hair_clump.
"""
import os, sys, json, math, argparse, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
RL = paths.RL_ROOT
WT = paths.WORKTREE
VIEWS = ('front', 'profile', 'back', 'tq', 'close')
GAME_VIEWS = ('game_front', 'game_tq')      # 256 px wide: silhouette at gameplay distance

# Inside Blender only when launched as `blender ... --python preview.py -- ...`.
# (This machine also has bpy pip-installed in Python 3.13; importing it there must
# NOT render in-process, which would bypass the GPU lock and the contact sheet.)
IN_BLENDER = '--python' in sys.argv


# =================================================================== blender side
def blender_main(a):
    import bpy, mathutils, bmesh, struct
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    body_path = paths.body_glb(a.sex)
    head_path = os.path.join(paths.HEADS, f'rl_head_{a.sex}.glb')

    def glb_json(p):
        data = open(p, 'rb').read(); jl = struct.unpack_from('<I', data, 12)[0]
        return json.loads(data[20:20 + jl])

    def imported(fn):
        before = set(bpy.data.objects)
        fn()
        return [o for o in bpy.data.objects if o not in before]

    # body with its head triangles removed (same plane rule as the runtime cut)
    cut = glb_json(head_path)['asset']['extras']['rlHead']['bodyCut']
    body_objs = imported(lambda: bpy.ops.import_scene.gltf(filepath=body_path)) if not a.no_body else []
    skin_rgb = tuple(float(x) for x in a.skin.split(','))
    for o in body_objs:
        if o.type != 'MESH':
            continue
        nm = o.name.split('.')[0]
        if nm in cut['hideMeshes'] or nm.startswith('wardrobe_'):
            o.hide_render = True; o.hide_viewport = True; continue
        if nm == 'body':
            neck = mathutils.Vector((0, 1.4523, -0.0514)); headj = mathutils.Vector((0, 1.5685, 0.0114))
            dg = (headj - neck).normalized(); og = neck + cut['travel'] * dg
            dB = mathutils.Vector((dg.x, -dg.z, dg.y)); oB = mathutils.Vector((og.x, -og.z, og.y))
            me = o.data; bm = bmesh.new(); bm.from_mesh(me)
            dele = [f for f in bm.faces if all((o.matrix_world @ v.co - oB).dot(dB) > 0 for v in f.verts)]
            # also drop everything far below the shoulders (faster renders)
            dele += [f for f in bm.faces if f not in dele and all((o.matrix_world @ v.co).z < 1.05 for v in f.verts)]
            bmesh.ops.delete(bm, geom=list(set(dele)), context='FACES'); bm.to_mesh(me); bm.free()
            o.data.materials.clear(); o.data.materials.append(skin_material(bpy, skin_rgb))
    head_objs = imported(lambda: bpy.ops.import_scene.gltf(filepath=head_path))
    for o in head_objs:
        if o.type != 'MESH':
            continue
        hn = o.name.split('.')[0]
        if '_lod' in hn and not hn.endswith('_lod0'):
            o.hide_render = True; o.hide_viewport = True; continue
        for i, slot in enumerate(o.material_slots):
            mn = slot.material.name if slot.material else ''
            if mn.startswith('rl_skin'):
                alb = os.path.join(paths.HEADS, 'tex', f'head_{a.sex}_albedo.png')
                slot.material = skin_tex_material(bpy, alb) if (os.path.exists(alb) and not a.flat_skin) else skin_material(bpy, skin_rgb)
            elif mn.startswith('rl_eye'):
                slot.material = flat_material(bpy, 'eye_prev', (0.75, 0.72, 0.68))
            elif mn.startswith('rl_cornea'):
                slot.material = flat_material(bpy, 'cornea_prev', (0.1, 0.12, 0.1))
                slot.material.surface_render_method = 'DITHERED'
            elif mn.startswith('rl_brow') or mn.startswith('rl_lash'):
                slot.material = flat_material(bpy, 'brow_prev', (0.12, 0.07, 0.04))
    tint = tuple(float(x) for x in a.color.split(','))
    tex = {'rl_hair_clump': os.path.join(paths.HAIR_TEX, 'hair_clump.png'),
           'rl_hair_card': os.path.join(paths.HAIR_TEX, 'hair_strands.png'),
           'rl_beard': os.path.join(paths.BEARD_TEX, 'beard.png')}
    btint = tuple(float(x) for x in a.beard_color.split(',')) if a.beard_color else tint
    for path in a.asset:
        objs = imported(lambda: bpy.ops.import_scene.gltf(filepath=path))
        for o in objs:
            if o.type != 'MESH':
                continue
            nm = o.name.split('.')[0]
            if '_lod' in nm and not nm.endswith(f'_lod{a.lod}'):
                o.hide_render = True; o.hide_viewport = True; continue
            # the runtime does not let hair cast shadows on the face / neck
            try:
                o.visible_shadow = False
            except Exception:
                pass
            for slot in o.material_slots:
                mn = slot.material.name.split('.')[0] if slot.material else ''
                if mn in tex:
                    slot.material = hair_material(bpy, mn, tex[mn], btint if mn == 'rl_beard' else tint, level=a.detail_level,
                                                  clip=(-1.0 if a.opaque else 0.5 if mn == 'rl_hair_clump' else 0.4))
    # ---------------- shape keys (head and hair share the id_* names; hl_* are hair only)
    if a.shapes:
        want = {}
        for tok in a.shapes.split(','):
            if tok in ('all_id_p', 'all_id_n'):
                want[tok] = 1.0
            elif '=' in tok:
                k, v = tok.split('='); want[k] = float(v)
            elif tok:
                want[tok] = 1.0
        for o in bpy.data.objects:
            sk = o.data.shape_keys if o.type == 'MESH' and o.data.shape_keys else None
            if sk is None:
                continue
            for kb in sk.key_blocks[1:]:
                nm = kb.name
                if nm in want:
                    kb.value = want[nm]
                elif nm.startswith('id_') and ('all_id_p' in want and nm.endswith('_p') or 'all_id_n' in want and nm.endswith('_n')):
                    kb.value = 1.0
    # ---------------- render setup
    if a.cpu:
        # CPU path tracing: no GPU use (no GPU lock needed on a shared machine)
        sc.render.engine = 'CYCLES'
        sc.cycles.device = 'CPU'
        sc.cycles.samples = 24
        sc.cycles.use_denoising = True
        sc.cycles.transparent_max_bounces = 32
        sc.cycles.max_bounces = 4
    else:
        for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
            try:
                sc.render.engine = eng; break
            except TypeError:
                continue
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x = a.size; sc.render.resolution_y = int(a.size * 1.12)
    sc.render.film_transparent = False
    try:
        sc.eevee.taa_render_samples = 32
        sc.eevee.use_shadows = True
    except Exception:
        pass
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs[0].default_value = (0.78, 0.78, 0.8, 1); bg.inputs[1].default_value = 0.5
    def sun(name, rot, energy, color=(1, 1, 1)):
        L = bpy.data.lights.new(name, 'SUN'); L.energy = energy; L.color = color; L.angle = math.radians(8)
        ob = bpy.data.objects.new(name, L); sc.collection.objects.link(ob)
        ob.rotation_euler = [math.radians(x) for x in rot]
    sun('key', (55, 0, -35), 2.4, (1.0, 0.96, 0.9))
    sun('fill', (70, 0, 60), 0.7, (0.85, 0.9, 1.0))
    sun('rim', (-60, 0, 170), 2.2, (1.0, 0.97, 0.92))
    cam = bpy.data.cameras.new('cam'); cam.lens = 85
    co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
    head_c = mathutils.Vector((0, -0.0, 1.635))
    os.makedirs(a.out, exist_ok=True)
    # angles match the concept sheets: side = her LEFT profile, isometric = her RIGHT-front
    # from slightly above (camera at -X); close-up from her left-front
    shots = {'front': (0, 2, 1.05, 0.0), 'profile': (90, 0, 1.05, 0.0), 'back': (180, 5, 1.05, 0.0),
             'tq': (-35, 14, 1.05, 0.0), 'close': (25, 4, 0.62, 0.02),
             # coverage views (only on request): back three-quarters from either side,
             # from above the crown and from below the nape
             'back_tq_l': (145, 10, 1.05, 0.0), 'back_tq_r': (-145, 10, 1.05, 0.0),
             'top_back': (180, 52, 1.05, 0.03), 'low_back': (180, -22, 1.05, 0.0)}
    want = [x for x in (a.views or '').split(',') if x]
    for v, (az, el, dist, dz) in shots.items():
        if (want and v not in want) or (not want and v not in VIEWS):
            continue
        az_r = math.radians(az); el_r = math.radians(el)
        # glTF +Z (face) == Blender -Y ; character's left (+X) stays +X
        d = mathutils.Vector((math.sin(az_r) * math.cos(el_r), -math.cos(az_r) * math.cos(el_r), math.sin(el_r)))
        tgt = head_c + mathutils.Vector((0, 0, dz))
        co.location = tgt + d * dist
        co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(a.out, f'{v}.png')
        bpy.ops.render.render(write_still=True)
    # gameplay-distance silhouette: same framing, 256 px wide
    sc.render.resolution_x = 256; sc.render.resolution_y = 288
    for v, (az, el) in (('game_front', (0, 2)), ('game_tq', (-35, 14))):
        if want and v not in want:
            continue
        az_r = math.radians(az); el_r = math.radians(el)
        d = mathutils.Vector((math.sin(az_r) * math.cos(el_r), -math.cos(az_r) * math.cos(el_r), math.sin(el_r)))
        co.location = head_c + d * 1.25
        co.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(a.out, f'{v}.png')
        bpy.ops.render.render(write_still=True)


def flat_material(bpy, name, rgb):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*rgb, 1); p.inputs['Roughness'].default_value = 0.5
    return m


def skin_tex_material(bpy, path):
    """Head skin with the head build's painted albedo (brows/freckles are painted in)."""
    m = bpy.data.materials.get('skin_tex_prev')
    if m:
        return m
    m = bpy.data.materials.new('skin_tex_prev'); m.use_nodes = True
    N = m.node_tree.nodes; p = N.get('Principled BSDF')
    img = N.new('ShaderNodeTexImage'); img.image = bpy.data.images.load(path)
    m.node_tree.links.new(img.outputs['Color'], p.inputs['Base Color'])
    p.inputs['Roughness'].default_value = 0.55
    return m


def skin_material(bpy, rgb):
    m = bpy.data.materials.get('skin_prev')
    if m:
        return m
    m = bpy.data.materials.new('skin_prev'); m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*rgb, 1); p.inputs['Roughness'].default_value = 0.55
    try:
        p.inputs['Subsurface Weight'].default_value = 0.15
        p.inputs['Subsurface Radius'].default_value = (0.012, 0.005, 0.003)
    except KeyError:
        pass
    return m


def hair_material(bpy, name, tex_path, tint, clip=0.5, level=None):
    key = name + '_prev'
    m = bpy.data.materials.get(key)
    if m:
        return m
    m = bpy.data.materials.new(key); m.use_nodes = True
    m.surface_render_method = 'DITHERED'
    for attr, val in (('use_backface_culling', False), ('use_transparent_shadow', True)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    nt = m.node_tree; N = nt.nodes; Lk = nt.links
    p = N.get('Principled BSDF')
    img = N.new('ShaderNodeTexImage'); img.image = bpy.data.images.load(tex_path); img.extension = 'REPEAT'
    uv = N.new('ShaderNodeUVMap')
    Lk.new(uv.outputs['UV'], img.inputs['Vector'])
    sep = N.new('ShaderNodeSeparateXYZ'); Lk.new(uv.outputs['UV'], sep.inputs[0])
    # Blender flips v on import (v_blender = 1 - v_gltf): root darkening from gltf v
    inv = N.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
    Lk.new(sep.outputs['Y'], inv.inputs[1])
    ramp = N.new('ShaderNodeMapRange'); ramp.inputs['From Min'].default_value = 0.0
    ramp.inputs['From Max'].default_value = 0.3; ramp.inputs['To Min'].default_value = 0.62; ramp.inputs['To Max'].default_value = 1.0
    ramp.clamp = True
    Lk.new(inv.outputs[0], ramp.inputs['Value'])
    vc = N.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
    sepc = N.new('ShaderNodeSeparateColor'); Lk.new(vc.outputs['Color'], sepc.inputs[0])
    rr = N.new('ShaderNodeMapRange'); rr.inputs['To Min'].default_value = 0.85; rr.inputs['To Max'].default_value = 1.12
    Lk.new(sepc.outputs['Red'], rr.inputs['Value'])
    ao = N.new('ShaderNodeMapRange'); ao.inputs['To Min'].default_value = 0.68; ao.inputs['To Max'].default_value = 1.0
    Lk.new(sepc.outputs['Blue'], ao.inputs['Value'])
    m1 = N.new('ShaderNodeMath'); m1.operation = 'MULTIPLY'; Lk.new(ramp.outputs[0], m1.inputs[0]); Lk.new(rr.outputs[0], m1.inputs[1])
    m2 = N.new('ShaderNodeMath'); m2.operation = 'MULTIPLY'; Lk.new(m1.outputs[0], m2.inputs[0]); Lk.new(ao.outputs[0], m2.inputs[1])
    tintn = N.new('ShaderNodeRGB'); tintn.outputs[0].default_value = (*tint, 1)
    # per-lock streaks (COLOR_0.R): some locks a little lighter / redder
    streak = N.new('ShaderNodeRGB')
    streak.outputs[0].default_value = (min(1, tint[0] * 1.3), tint[1] * 1.12, tint[2] * 0.95, 1)
    sf = N.new('ShaderNodeMapRange'); sf.inputs['From Min'].default_value = 0.55; sf.inputs['From Max'].default_value = 1.0
    sf.inputs['To Min'].default_value = 0.0; sf.inputs['To Max'].default_value = 0.8; sf.clamp = True
    Lk.new(sepc.outputs['Red'], sf.inputs['Value'])
    tmix = N.new('ShaderNodeMix'); tmix.data_type = 'RGBA'
    Lk.new(sf.outputs[0], tmix.inputs['Factor']); Lk.new(tintn.outputs[0], tmix.inputs[6]); Lk.new(streak.outputs[0], tmix.inputs[7])
    mix1 = N.new('ShaderNodeMix'); mix1.data_type = 'RGBA'; mix1.blend_type = 'MULTIPLY'; mix1.inputs['Factor'].default_value = 1.0
    Lk.new(img.outputs['Color'], mix1.inputs[6]); Lk.new(tmix.outputs[2], mix1.inputs[7])
    # texture luminance is neutral grey ~0.5: scale up so the tint reads at its value
    gain = N.new('ShaderNodeMix'); gain.data_type = 'RGBA'; gain.blend_type = 'MULTIPLY'; gain.inputs['Factor'].default_value = 1.0
    Lk.new(mix1.outputs[2], gain.inputs[6])
    comb = N.new('ShaderNodeCombineColor')
    for ch in ('Red', 'Green', 'Blue'):
        Lk.new(m2.outputs[0], comb.inputs[ch])
    sc2 = N.new('ShaderNodeVectorMath'); sc2.operation = 'SCALE'; sc2.inputs['Scale'].default_value = 1.7
    Lk.new(comb.outputs[0], sc2.inputs[0])
    Lk.new(sc2.outputs[0], gain.inputs[7])
    Lk.new(gain.outputs[2], p.inputs['Base Color'])
    gt = N.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = clip
    Lk.new(img.outputs['Alpha'], gt.inputs[0])
    if level is None:
        Lk.new(gt.outputs[0], p.inputs['Alpha'])
    else:
        # runtime hair_detail rule: discard where COLOR_0.A < 1 - level
        keep = N.new('ShaderNodeMath'); keep.operation = 'GREATER_THAN'; keep.inputs[1].default_value = 1.0 - level - 1e-3
        Lk.new(vc.outputs['Alpha'], keep.inputs[0])
        both = N.new('ShaderNodeMath'); both.operation = 'MULTIPLY'
        Lk.new(gt.outputs[0], both.inputs[0]); Lk.new(keep.outputs[0], both.inputs[1])
        Lk.new(both.outputs[0], p.inputs['Alpha'])
    p.inputs['Roughness'].default_value = 0.42
    try:
        p.inputs['Specular IOR Level'].default_value = 0.35
        tg = N.new('ShaderNodeTangent'); tg.direction_type = 'UV_MAP'
        Lk.new(tg.outputs[0], p.inputs['Tangent'])
        p.inputs['Anisotropic'].default_value = 0.6
        p.inputs['Anisotropic Rotation'].default_value = 0.25
    except KeyError:
        pass
    return m


# =================================================================== python side
def contact_sheet(out_dir, name, refs):
    from PIL import Image, ImageDraw
    ims = [(v, Image.open(os.path.join(out_dir, f'{v}.png')).convert('RGB')) for v in VIEWS
           if os.path.exists(os.path.join(out_dir, f'{v}.png'))]
    for v in GAME_VIEWS:                       # shown as real pixels (nearest upscale)
        pth = os.path.join(out_dir, f'{v}.png')
        if os.path.exists(pth):
            im = Image.open(pth).convert('RGB')
            ims.append((v + ' (256px)', im.resize((im.width * 420 // im.height, 420), Image.NEAREST)))
    for r in refs or []:
        if os.path.exists(r):
            ims.append(('ref: ' + os.path.basename(r), Image.open(r).convert('RGB')))
    if not ims:
        return None
    h = 420
    tiles = []
    for lab, im in ims:
        im = im.resize((int(im.width * h / im.height), h))
        d = ImageDraw.Draw(im); d.rectangle([0, 0, 8 + 7 * len(lab), 16], fill=(255, 255, 255)); d.text((4, 2), lab, fill=(0, 0, 0))
        tiles.append(im)
    per_row = 4
    rows = [tiles[i:i + per_row] for i in range(0, len(tiles), per_row)]
    W = max(sum(t.width for t in r) for r in rows)
    sheet = Image.new('RGB', (W, h * len(rows)), (240, 240, 240))
    y = 0
    for r in rows:
        x = 0
        for t in r:
            sheet.paste(t, (x, y)); x += t.width
        y += h
    sheet = sheet.resize((W * 3 // 4, h * len(rows) * 3 // 4))
    path = os.path.join(out_dir, 'sheet.png')
    sheet.save(path, optimize=True)
    return path


def compare_sheet(out_dir, pairs, path=None, h=520):
    """Reference next to render at the matching angle: pairs = [(label, ref_png,
    ref_box or None, render_png, render_box or None), ...]; boxes are fractional
    (x0, y0, x1, y1) crops. Each pair is scaled to the same height."""
    from PIL import Image, ImageDraw
    tiles = []
    for lab, rp, rb, vp, vb in pairs:
        pair = []
        for p, box, tag in ((rp, rb, 'concept'), (vp, vb, 'render')):
            im = Image.open(p).convert('RGB')
            if box:
                w, hh = im.size
                im = im.crop((int(w * box[0]), int(hh * box[1]), int(w * box[2]), int(hh * box[3])))
            im = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
            d = ImageDraw.Draw(im); t = f'{lab}: {tag}'
            d.rectangle([0, 0, 7 * len(t) + 8, 16], fill=(255, 255, 255)); d.text((4, 2), t, fill=(0, 0, 0))
            pair.append(im)
        tiles.append(pair)
    W = max(sum(t.width for t in p) for p in tiles)
    cols = 2
    rows = [tiles[i:i + cols] for i in range(0, len(tiles), cols)]
    rw = [sum(t.width for p in r for t in p) + 12 * (len(r) - 1) for r in rows]
    sheet = Image.new('RGB', (max(rw), h * len(rows)), (235, 235, 235))
    for ri, r in enumerate(rows):
        x = 0
        for p in r:
            for t in p:
                sheet.paste(t, (x, ri * h)); x += t.width
            x += 12
    path = path or os.path.join(out_dir, 'compare.png')
    sheet.save(path, optimize=True)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sex', required=True)
    ap.add_argument('--asset', action='append', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--lod', type=int, default=0)
    ap.add_argument('--color', default='0.42,0.13,0.05')
    ap.add_argument('--beard-color', default='')
    ap.add_argument('--skin', default='0.6,0.4,0.31')
    ap.add_argument('--size', type=int, default=560)
    ap.add_argument('--out', default='')
    ap.add_argument('--ref', action='append', default=[])
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--no-body', action='store_true', help='head module only (no shipped body)')
    ap.add_argument('--opaque', action='store_true', help='debug: no alpha clip on hair materials')
    ap.add_argument('--flat-skin', action='store_true', help='plain skin colour instead of the head albedo')
    ap.add_argument('--detail-level', type=float, default=None,
                    help='hair_detail 0..1: apply the runtime discard rule (COLOR_0.A < 1 - level)')
    ap.add_argument('--views', default='', help='comma list of views to render (default: all)')
    ap.add_argument('--cpu', action='store_true', help='Cycles on the CPU (no GPU, no GPU lock)')
    ap.add_argument('--shapes', default='', help='shape keys on head + hair: name=w,... or all_id_p / all_id_n')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    a = ap.parse_args(argv)
    a.asset = [os.path.abspath(p) for p in a.asset]
    if not a.out:
        a.out = os.path.join(paths.HAIR_OUT, 'preview', a.name if a.lod == 0 else f'{a.name}_lod{a.lod}')
    a.out = os.path.abspath(a.out)
    if IN_BLENDER:
        blender_main(a)
        return
    cmd = [paths.blender(), '--factory-startup', '-b', '--python', os.path.abspath(__file__), '--'] + argv + ['--out', a.out]
    lock, sh = paths.gpu_lock(), paths.bash()
    if lock and sh and not a.cpu:
        cmd = [sh, lock] + cmd          # serialise GPU renders on a shared machine ($RL_GPU_LOCK)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout)
    errs = [ln for ln in (r.stdout + r.stderr).splitlines() if 'Error' in ln or 'Traceback' in ln]
    if r.returncode != 0 or errs:
        print('\n'.join((r.stdout + r.stderr).splitlines()[-40:]))
    sheet = contact_sheet(a.out, a.name, a.ref)
    print(json.dumps({'out': a.out, 'sheet': sheet, 'views': [os.path.join(a.out, v + '.png') for v in VIEWS]}, indent=1))


if __name__ == '__main__':
    main()
