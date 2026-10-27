"""Fresh self-contained Blender imports checked against original motion witnesses."""

import bpy, hashlib, json, pathlib, sys
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

job = json.loads(
    pathlib.Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8")
)
out = pathlib.Path(job["output"])
w = json.loads(pathlib.Path(job["witness"]).read_text(encoding="utf-8"))
results = {}
for label in ["baseline", "candidate"]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 240
    path = pathlib.Path(job["source"] if label == "baseline" else job["candidate"])
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = list(bpy.data.objects)
    actions = list(bpy.data.actions)
    clips = {
        cl: next(x for x in actions if x.name == cl or x.name.startswith(cl + "."))
        for cl in w["clips"]
    }
    for ob in objects:
        if ob.type == "MESH" and ob.data.shape_keys:
            for block in list(ob.data.shape_keys.key_blocks)[1:]:
                block.slider_min = -10.0
                block.slider_max = 10.0
        if ob.animation_data:
            ob.animation_data.action = None
            for track in ob.animation_data.nla_tracks:
                track.mute = True
    bone_names = list(next(iter(w["clips"].values()))[0]["bones"])
    arm = next(
        o
        for o in objects
        if o.type == "ARMATURE" and set(bone_names).issubset(o.pose.bones.keys())
    )

    def select(clip):
        action = clips[clip]
        for bone in arm.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        arm.animation_data_create()
        arm.animation_data.action = action
        arm.animation_data.action_slot = next(
            s for s in action.slots if s.target_id_type == "OBJECT"
        )
        for ob in objects:
            if ob.type != "MESH" or not ob.data.shape_keys:
                continue
            key = ob.data.shape_keys
            key.animation_data_create()
            key.animation_data.action = None
            for track in key.animation_data.nla_tracks:
                track.mute = True
            for block in list(key.key_blocks)[1:]:
                block.value = 0.0
            slots = [s for s in action.slots if s.target_id_type == "KEY"]
            if slots:
                key.animation_data.action = action
                key.animation_data.action_slot = slots[0]

    def pose(tm):
        frame = tm * 240
        scene.frame_set(int(frame), subframe=frame - int(frame))
        bpy.context.view_layer.update()
        return bpy.context.evaluated_depsgraph_get()

    def convert(v):
        return Vector((v[0], -v[2], v[1]))

    clip = next(iter(w["clips"]))
    entry = w["clips"][clip][0]
    select(clip)
    deps = pose(entry["time"])
    points = []
    for ob in objects:
        if ob.type == "MESH":
            ev = ob.evaluated_get(deps)
            for v in ev.data.vertices:
                points.append((ob, v.index, ev.matrix_world @ v.co))
    kd = KDTree(len(points))
    for i, (_, _, v) in enumerate(points):
        kd.insert(v, i)
    kd.balance()
    bindings = []
    for expected in entry["surface"]:
        pos, index, distance = kd.find(convert(expected))
        assert distance < 0.00015 * w["height"], (label, "binding", distance)
        bindings.append(points[index][:2])
    metrics = {}
    maxbone = 0.0
    maxsurface = 0.0
    for clip, entries in w["clips"].items():
        select(clip)
        bone_error = 0.0
        surface_error = 0.0
        for entry in entries:
            deps = pose(entry["time"])
            for (ob, vi), expected in zip(bindings, entry["surface"]):
                ev = ob.evaluated_get(deps)
                surface_error = max(
                    surface_error,
                    (
                        ev.matrix_world @ ev.data.vertices[vi].co - convert(expected)
                    ).length
                    / w["height"],
                )
            for name, values in entry["bones"].items():
                bone_error = max(
                    bone_error,
                    (
                        arm.matrix_world @ arm.pose.bones[name].head
                        - convert((values[3], values[7], values[11]))
                    ).length
                    / w["height"],
                )
        assert surface_error < 0.0002 and bone_error < 0.00015, (
            label,
            clip,
            surface_error,
            bone_error,
        )
        metrics[clip] = {
            "surface_error_over_height": surface_error,
            "bone_head_error_over_height": bone_error,
            "poses": len(entries),
        }
        maxbone = max(maxbone, bone_error)
        maxsurface = max(maxsurface, surface_error)
    results[label] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "passed": True,
        "surface_probes": len(bindings),
        "clips": metrics,
        "max_surface_error_over_height": maxsurface,
        "max_bone_head_error_over_height": maxbone,
        "scope": "Independent fresh Blender import geometry/motion witness check. Blender is not the authority for runtime morph normal shading.",
    }
    (out / "blender-validation.json").write_text(json.dumps(results, indent=2))
    print("BLENDER_PILOT_PASS", label, maxsurface, maxbone, flush=True)
