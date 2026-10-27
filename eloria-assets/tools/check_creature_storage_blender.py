"""Fresh self-contained Blender imports checked against original motion witnesses."""

import bpy, hashlib, json, pathlib, sys
from mathutils import Matrix, Vector

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from video_motion.blender_vertex_identity import imported_bindings

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
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False)
    objects = list(bpy.data.objects)
    actions = list(bpy.data.actions)
    all_bindings, default_weights, identity = imported_bindings(path, objects)
    slots_by_data = {}
    for data in list(objects) + [
        o.data.shape_keys for o in objects if o.type == "MESH" and o.data.shape_keys
    ]:
        ad = data.animation_data
        if ad is None:
            continue
        slots = {}
        if ad.action is not None and ad.action_slot is not None:
            slots[ad.action.as_pointer()] = ad.action_slot
        for track in ad.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    slots[strip.action.as_pointer()] = strip.action_slot
        slots_by_data[data.as_pointer()] = slots
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
        arm.animation_data.action_slot = slots_by_data[arm.as_pointer()][
            action.as_pointer()
        ]
        for ob in objects:
            if ob.type != "MESH" or not ob.data.shape_keys:
                continue
            key = ob.data.shape_keys
            key.animation_data_create()
            key.animation_data.action = None
            for track in key.animation_data.nla_tracks:
                track.mute = True
            for block, value in zip(
                list(key.key_blocks)[1:], default_weights[key.as_pointer()]
            ):
                block.value = value
            slot = slots_by_data.get(key.as_pointer(), {}).get(action.as_pointer())
            if slot is not None:
                key.animation_data.action = action
                key.animation_data.action_slot = slot

    def pose(tm):
        frame = tm * 240
        scene.frame_set(int(frame), subframe=frame - int(frame))
        bpy.context.view_layer.update()
        return bpy.context.evaluated_depsgraph_get()

    def convert(v):
        return Vector((v[0], -v[2], v[1]))

    original_ids = list(range(len(all_bindings)))
    if label == "candidate" and job.get("preparation"):
        preparation = json.loads(pathlib.Path(job["preparation"]).read_text())
        partition = preparation.get("partition")
        if partition and "all_candidate_original_vertex_ids" in partition:
            original_ids = partition["all_candidate_original_vertex_ids"]
    assert len(original_ids) == len(all_bindings) and len(set(original_ids)) == len(
        original_ids
    )
    by_original = {
        int(original): binding for original, binding in zip(original_ids, all_bindings)
    }
    bindings = [by_original[int(i)] for i in w["surface_vertex_ids"]]
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
        "vertex_identity": identity,
        "binding_method": "Full original GLB primitive vertex order, independently proved against basis/UV/skin/normals/all POSITION target data; frozen source IDs retained through partition mapping.",
        "clips": metrics,
        "max_surface_error_over_height": maxsurface,
        "max_bone_head_error_over_height": maxbone,
        "scope": "Independent fresh Blender import geometry/motion witness check. Blender is not the authority for runtime morph normal shading.",
    }
    (out / "blender-validation.json").write_text(json.dumps(results, indent=2))
    print("BLENDER_PILOT_PASS", label, maxsurface, maxbone, flush=True)
