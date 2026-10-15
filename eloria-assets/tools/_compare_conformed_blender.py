"""In-Blender half of `compare_conformed_piece.py`.  Not run directly."""
import os
# Blender can reset the inherited Windows affinity during startup. Apply the
# requested common CPU mask again before importing or rendering task geometry.
if os.name == 'nt':
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    cores = min(8, max(1, int(os.environ.get('ELORIA_RENDER_CORES', '8'))))
    if not kernel.SetProcessAffinityMask(kernel.GetCurrentProcess(), (1 << cores) - 1):
        raise ctypes.WinError(ctypes.get_last_error())
import bpy
import math
import sys
import json
import struct
from pathlib import Path

from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT, YAW, POSE, WIDTH, DROP, LABELS = argv[:6]
WORN = argv[6] if len(argv) > 6 and argv[6] else ""
YAW = float(YAW)
POSE = POSE == "1"
WIDTH = int(WIDTH)
DROP = [d for d in DROP.split(",") if d]
LABELS = LABELS.split(",") if LABELS else []
WORN_POSE = argv[7]
WORN_REGION = argv[8]
ENSEMBLE = argv[9] == '1'
SAVE_BLEND = argv[10] == '1'
REGISTRY = argv[11]
MODELS = argv[12:]

#: Where the generated meshes hang their arms, measured off the phoenix
#: cuirass and steady to a degree across the set: 11 degrees out from
#: vertical, 9 forward.  In Blender space, glTF +z (forward) is -y and
#: glTF +y (up) is +z.
DOWN_ARM = Vector((0.138, -0.162, -0.977)).normalized()

COLUMN = 1.30           # world units between columns
HEIGHT = 1.0            # every piece normalised to this tall

TRACKED = []


def load(path):
    """Import a GLB and return exactly the objects it brought.

    ``read_factory_settings`` is deferred in background Blender: the startup
    file is really read when the first operator runs, which is this import, so
    a purge before it does nothing and the default icosphere lands in the
    scene afterwards -- doubling every bounding box measured here.  The
    importer leaves its own objects selected, and that selection is the only
    trustworthy answer to "what did this file add".
    """
    bpy.ops.import_scene.gltf(filepath=path)
    got = list(bpy.context.selected_objects)
    for stray in list(bpy.data.objects):
        if stray not in got and stray not in TRACKED:
            bpy.data.objects.remove(stray, do_unlink=True)
    split_body = any(o.name.split('.')[0] == 'body' for o in got)
    for obj in got:
        if obj.type == "ARMATURE":
            # An imported action otherwise leaves the wearer animated against
            # equipment at rest, invalidating the true-scale comparison.
            obj.animation_data_clear()
            for bone in obj.pose.bones:
                bone.matrix_basis = Matrix.Identity(4)
            obj.data.pose_position = "REST"
        if obj.type == "MESH" and (obj.name.split('.')[0] in
                ('wardrobe_head_band', 'wardrobe_head_cap') or
                (split_body and obj.name.split('.')[0] == 'char1')):
            obj.hide_render = True
    bpy.context.view_layer.update()
    TRACKED.extend(got)
    print("loaded %s -> %s" % (path.rsplit("\\")[-1].rsplit("/")[-1],
                               [o.name for o in got]))
    return got


def remember_corner_normals(mesh, bm):
    # BMesh topology edits discard imported custom normals unless explicitly
    # restored. Keep their original loop IDs as a corner-domain attribute.
    normals = [tuple(n.vector) for n in mesh.corner_normals]
    layer = bm.loops.layers.int.new('qa_original_loop')
    bm.faces.ensure_lookup_table()
    for face, polygon in zip(bm.faces, mesh.polygons):
        for loop, index in zip(face.loops, polygon.loop_indices):
            loop[layer] = index
    return normals


def restore_corner_normals(mesh, normals):
    layer = mesh.attributes.get('qa_original_loop')
    if layer is None or layer.domain != 'CORNER':
        raise ValueError('Lost imported corner normal mapping')
    values = [normals[item.value] for item in layer.data]
    mesh.normals_split_custom_set(values)
    mesh.attributes.remove(layer)


def drop_materials(objs):
    """Delete the faces of any material the caller asked to hide."""
    if not DROP:
        return
    import bmesh
    import re

    # Blender suffixes a duplicate material name on import -- the second model
    # in the frame carries "... Liner.001" -- so matching the raw name drops
    # the layer from the first column only, and the comparison silently shows
    # one piece bare beside another still wearing its underlayer.
    def bare(name):
        return re.sub(r"\.\d{3}$", "", name)

    for obj in objs:
        if obj.type != "MESH":
            continue
        hide = {i for i, slot in enumerate(obj.material_slots)
                if slot.material and any(bare(slot.material.name).endswith(d)
                                         for d in DROP)}
        if not hide:
            continue
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        gone = [f for f in mesh.faces if f.material_index in hide]
        bmesh.ops.delete(mesh, geom=gone, context="FACES")
        mesh.to_mesh(obj.data)
        mesh.free()
        obj.data.update()


def bbox(objs):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    deps = bpy.context.evaluated_depsgraph_get()
    for obj in objs:
        if obj.type != "MESH":
            continue
        ev = obj.evaluated_get(deps)
        for vert in ev.data.vertices:
            world = ev.matrix_world @ vert.co
            for axis in range(3):
                lo[axis] = min(lo[axis], world[axis])
                hi[axis] = max(hi[axis], world[axis])
    return lo, hi


def pose_arms(objs):
    """Swing the upper arms down to the angle the generated mesh hangs at.

    The rotation is built in armature space and pushed through
    ``bone.matrix_local``, the only form that survives the glTF importer's
    Y-up-to-Z-up conversion sitting on the object matrix.
    """
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    if arm is None:
        return
    arm.data.pose_position = "POSE"
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    to_local = arm.matrix_world.inverted().to_3x3()
    for side, flip in (("l", 1.0), ("r", -1.0)):
        bone = arm.pose.bones.get("upperarm_%s" % side)
        if bone is None:
            continue
        rest = bone.bone.matrix_local
        head = rest.to_translation()
        have = (bone.bone.tail_local - bone.bone.head_local).normalized()
        want = (to_local @ Vector((DOWN_ARM.x * flip, DOWN_ARM.y,
                                   DOWN_ARM.z))).normalized()
        axis = have.cross(want)
        if axis.length < 1e-6:
            continue
        turn = Matrix.Rotation(
            math.acos(max(-1.0, min(1.0, have.dot(want)))), 4,
            axis.normalized())
        swing = Matrix.Translation(head) @ turn @ Matrix.Translation(-head)
        bone.matrix_basis = rest.inverted() @ swing @ rest
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()


def place(objs, x_at, index):
    lo, hi = bbox(objs)
    print("  bbox %s .. %s" % (tuple(round(v, 3) for v in lo),
                               tuple(round(v, 3) for v in hi)))
    scale = HEIGHT / max(hi[2] - lo[2], 1e-6)
    mid = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2,
                  (lo[2] + hi[2]) / 2))
    root = bpy.data.objects.new("column_%d" % index, None)
    bpy.context.collection.objects.link(root)
    TRACKED.append(root)
    for obj in objs:
        if obj.parent is None:
            obj.parent = root
    root.scale = (scale,) * 3
    root.location = (x_at - mid.x * scale, -mid.y * scale, -mid.z * scale)
    if YAW:
        bpy.context.view_layer.update()
        pivot = (Matrix.Translation((x_at, 0, 0))
                 @ Matrix.Rotation(math.radians(YAW), 4, "Z")
                 @ Matrix.Translation((-x_at, 0, 0)))
        root.matrix_world = pivot @ root.matrix_world
    bpy.context.view_layer.update()


def equipment_config(model_path):
    registry_path = Path(REGISTRY) if REGISTRY else Path(WORN).parents[4] / 'data/actors/equipment.json'
    registry = json.loads(registry_path.read_text())
    name, race = Path(model_path).name, Path(WORN).stem
    for base in registry['models'].values():
        if Path(base.get('scene', '')).name != name:
            continue
        for variant in base.get('variants', {}).values():
            if variant.get('authoredFor') == race:
                return registry, dict(base, **variant)
        return registry, base
    report = Path(model_path).with_suffix('.fit.json')
    return registry, json.loads(report.read_text()).get('variant', {}) if report.exists() else {}


def helmet_socket(objects, rig_objects, model_path):
    registry, config = equipment_config(model_path)
    socket = config.get('socket', registry['sockets']['3'])
    arm = next(o for o in rig_objects if o.type == 'ARMATURE')
    head = arm.matrix_world @ arm.data.bones[socket['bone']].matrix_local.translation
    offset = socket.get('offset', [0, 0, 0])
    position = head + Vector((offset[0], -offset[2], offset[1]))
    for obj in objects:
        if obj.parent is None:
            obj.location += position


def is_tail(p):
    # Same canonical anatomical classifier as TorsoBodyCover. Convert Blender
    # world to the client's X-right/Y-up/Z-forward coordinates before calling.
    if p.y >= .9367 or (p.x <= .13 and p.z >= -.11):
        return False
    distance = float('inf')
    for sign in (-1., 1.):
        chain = [Vector((.089*sign,.9321,.0014)),Vector((.09109*sign,.52587,.01922)),
                 Vector((.089*sign,.09796,-.04823)),Vector((.089*sign,.0152,.1132)),Vector((.089*sign,.0152,.2632))]
        for a,b in zip(chain,chain[1:]):
            axis=b-a; t=max(0., min(1., (p-a).dot(axis)/axis.length_squared))
            distance=min(distance,(p-a-axis*t).length)
    return distance > .115


def model_meshes(path):
    raw = Path(path).read_bytes()
    return json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])['meshes']


def choose_boot_backing(objects):
    fitted_legs = any(o.name.split('.')[0] == 'GeneratedLegBacking' for o in objects)
    fitted_boots = any(o.name.split('.')[0] == 'GeneratedBootBacking' for o in objects)
    for obj in objects:
        name = obj.name.split('.')[0]
        if name in ('GeneratedBootBacking','GeneratedBootBackingWithLegs'):
            obj.hide_render = (name == 'GeneratedBootBackingWithLegs') != fitted_legs
        if name in ('GeneratedLegBacking','GeneratedLegBackingWithBoots'):
            obj.hide_render = (name == 'GeneratedLegBackingWithBoots') != fitted_boots


loaded = [load(path) for path in MODELS]
if ENSEMBLE:
    skeleton = next(group for group in loaded if any(o.type=='ARMATURE' for o in group))
    for model_path, group in zip(MODELS, loaded):
        if not any(o.type=='ARMATURE' for o in group):
            helmet_socket(group,skeleton,model_path)
        if POSE:
            pose_arms(group)
    loaded = [[o for group in loaded for o in group]]
for group in loaded:
    choose_boot_backing(group)
span = COLUMN * (len(loaded) - 1)
for index, objs in enumerate(loaded):
    drop_materials(objs)
    if POSE:
        pose_arms(objs)
    place(objs, index * COLUMN - span / 2.0, index)

camera_data = bpy.data.cameras.new("cam")
camera_data.type = "ORTHO"
camera_data.ortho_scale = COLUMN * len(loaded)
camera = bpy.data.objects.new("cam", camera_data)
bpy.context.collection.objects.link(camera)
camera.location = (0, -8, 0)
camera.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.camera = camera

for direction, energy in (((-0.5, -1.0, 0.6), 4.0), ((0.9, -0.6, 0.2), 2.0),
                          ((0.0, 1.0, 0.3), 1.5)):
    data = bpy.data.lights.new("l", "SUN")
    data.energy = energy
    lamp = bpy.data.objects.new("l", data)
    bpy.context.collection.objects.link(lamp)
    lamp.rotation_euler = Vector(direction).to_track_quat("-Z", "Y").to_euler()

world = bpy.data.worlds.new("w")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (.07, .08, .09, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6

def render_worn(path):
    """Draw every skinned model on the race body, at true scale.

    A separate picture rather than another column, because the two answer
    different questions and cannot share a camera: the comparison above
    normalises each model to one height so shapes can be read against each
    other, and this one must not normalise anything at all -- whether a piece
    is the right SIZE for a character is most of what is being asked.
    """
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    TRACKED.clear()
    # Only the models that can be worn.  A raw generated mesh has no skeleton
    # and no place on a body; it belongs in the comparison above, not here.
    worn = []
    for model in MODELS:
        piece = load(model)
        if any(o.type == "ARMATURE" for o in piece) or ENSEMBLE or (WORN_REGION == 'head' and model == MODELS[0]):
            worn.append((model, piece))
        else:
            for obj in piece:
                bpy.data.objects.remove(obj, do_unlink=True)
            for obj in list(TRACKED):
                if obj not in bpy.data.objects.values():
                    TRACKED.remove(obj)
    if not worn:
        print("  nothing skinned to wear")
        return
    if ENSEMBLE:
        skeleton = next(group for _,group in worn if any(o.type=='ARMATURE' for o in group))
        for model_path,group in worn:
            if not any(o.type=='ARMATURE' for o in group):
                helmet_socket(group,skeleton,model_path)
            if WORN_POSE != 'rest':
                pose_arms(group)
        worn = [(MODELS[0],[o for _,group in worn for o in group])]
    span = COLUMN * (len(worn) - 1)
    for index, (_model, piece) in enumerate(worn):
        choose_boot_backing(piece)
        body = load(WORN)
        if any(mesh.get('extras',{}).get('coversHair',False)
               for model in (MODELS if ENSEMBLE else [_model]) for mesh in model_meshes(model)):
            for obj in body:
                if obj.name.split('.')[0].lower() in ('hair','scalp'):
                    obj.hide_render = True
        if WORN_REGION == 'head' and not ENSEMBLE:
            registry, config = equipment_config(_model)
            helmet_socket(piece, body, _model)
            hides = config.get('hides', registry['parts']['3'].get('hides', []))
            for obj in body:
                if obj.name.split('.')[0].lower() in [n.lower() for n in hides]:
                    obj.hide_render = True
        backings = [o for o in piece if o.name.split('.')[0] in
                    ('GeneratedArmorBacking', 'GeneratedLegBacking', 'GeneratedBootBacking')]
        if backings:
            # Match TorsoBodyCover's rest-space mask, only for new equipment
            # that actually supplies its replacement backing.
            import bmesh
            regions = []
            for model_path in (MODELS if ENSEMBLE else [_model]):
                for mesh in model_meshes(model_path):
                    region = mesh.get('extras', {}).get('bodyCover')
                    if region:
                        regions.append(region)
            for obj in body:
                name = obj.name.split('.')[0].lower()
                if obj.type != 'MESH' or not (name in ('body','char1','mesh_node') or name.startswith('wardrobe_')):
                    continue
                protect = {g.index for g in obj.vertex_groups if g.name in ('Head','neck_01')} if name in ('body','char1','mesh_node') else set()
                head_weight = [sum(g.weight for g in v.groups if g.group in protect) for v in obj.data.vertices]
                bm = bmesh.new()
                bm.from_mesh(obj.data)
                removed = []
                bm.verts.ensure_lookup_table()
                for face in bm.faces:
                    if sum(head_weight[v.index] for v in face.verts)/len(face.verts) > .5:
                        continue
                    c = sum((obj.matrix_world @ v.co for v in face.verts), Vector()) / len(face.verts)
                    if protect and c.z > 1.40 and abs(c.x) < .11:
                        continue
                    if Path(WORN).stem.startswith('ssarathi_') and is_tail(Vector((c.x,c.z,-c.y))):
                        continue
                    collar = (name == 'wardrobe_shirt' and 1.40 < c.z < 1.65 and abs(c.x) < .20
                              and any(lo < 1.30 < hi for lo,hi,width in regions))
                    if collar or any(lo < c.z < hi and abs(c.x) < width for lo,hi,width in regions):
                        removed.append(face)
                bmesh.ops.delete(bm, geom=removed, context='FACES')
                bm.to_mesh(obj.data)
                bm.free()
        if WORN_POSE != 'rest':
            for objects in (body, piece):
                pose_arms(objects)
                if WORN_POSE == 'bent':
                    for arm in (o for o in objects if o.type == 'ARMATURE'):
                        arm.data.pose_position = 'POSE'
                        limbs = ['calf_', 'lowerarm_'] if ENSEMBLE else [
                            'calf_' if WORN_REGION in ('legs', 'boots') else 'lowerarm_']
                        for limb in limbs:
                            for side in ('l', 'r'):
                                bone = arm.pose.bones.get(limb + side)
                                if bone:
                                    bone.matrix_basis = Matrix.Rotation(math.radians(70), 4, 'X')
            bpy.context.view_layer.update()
        drop_materials(piece)
        shift = index * COLUMN - span / 2.0
        for obj in body + piece:
            if obj.parent is None:
                obj.location = (obj.location.x + shift, obj.location.y,
                                obj.location.z)
    camera_data = bpy.data.cameras.new("cam")
    camera_data.type = "ORTHO"
    focus, width = {'torso': (1.28, COLUMN), 'legs': (.62, 1.25),
                    'boots': (.23, .72), 'head': (1.72, .72)}[WORN_REGION]
    if ENSEMBLE:
        focus,width = 1.10,2.55
    camera_data.ortho_scale = width * len(worn)
    camera = bpy.data.objects.new("cam", camera_data)
    bpy.context.collection.objects.link(camera)
    # Framed on the chest: the torso span is 1.02 to 1.54 in world metres.
    yaw = math.radians(YAW)
    camera.location = (8 * math.sin(yaw), -8 * math.cos(yaw), focus)
    camera.rotation_euler = (Vector((0, 0, focus)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = camera
    for direction, energy in (((-0.5, -1.0, 0.6), 4.0), ((0.9, -0.6, 0.2), 2.0),
                              ((0.0, 1.0, 0.3), 1.5)):
        data = bpy.data.lights.new("l", "SUN")
        data.energy = energy
        lamp = bpy.data.objects.new("l", data)
        bpy.context.collection.objects.link(lamp)
        lamp.rotation_euler = Vector(direction).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("w2")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (.07, .08, .09, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    scene = bpy.context.scene
    scene.render.resolution_x = WIDTH * len(worn)
    scene.render.resolution_y = int(WIDTH * 1.25)
    stem = OUT.rsplit(".", 1)
    scene.render.filepath = (stem[0] + "_worn." + stem[1]) if len(stem) == 2 \
        else OUT + "_worn.png"
    bpy.ops.render.render(write_still=True)
    if SAVE_BLEND:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(scene.render.filepath).with_suffix('.blend')), compress=True)
    print("  wrote %s" % scene.render.filepath)


scene = bpy.context.scene
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        continue
scene.render.resolution_x = WIDTH * len(loaded)
scene.render.resolution_y = int(WIDTH * 1.25)
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
if SAVE_BLEND:
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(OUT).with_suffix('.blend')), compress=True)
print("  rendered %d column(s)" % len(loaded))
if WORN:
    render_worn(WORN)
