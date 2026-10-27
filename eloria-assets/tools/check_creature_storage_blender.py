"""Fresh self-contained Blender imports checked against original motion witnesses."""

import bpy, hashlib, json, pathlib, sys
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from video_motion.blender_vertex_identity import imported_bindings

job = json.loads(
    pathlib.Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8")
)
out = pathlib.Path(job["output"])
w = json.loads(pathlib.Path(job["witness"]).read_text(encoding="utf-8"))
results = {}
baseline_samples = {}
direct = {
    "maximum_position_error": 0.0,
    "maximum_bone_matrix_error": 0.0,
    "maximum_float32_budget": 0.0,
    "poses": 0,
    "neutral_default_checked": False,
}
for label in ["baseline", "candidate"]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 240
    path = pathlib.Path(job["source"] if label == "baseline" else job["candidate"])
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False)
    objects = list(bpy.data.objects)
    actions = list(bpy.data.actions)
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
    # Bone-parented static meshes must be matched in authored neutral rest,
    # rather than the first action Blender selected during GLB import.
    for ob in objects:
        if ob.type == "ARMATURE":
            for bone in ob.pose.bones:
                bone.matrix_basis = Matrix.Identity(4)
        if ob.type == "MESH" and ob.data.shape_keys:
            key = ob.data.shape_keys
            if key.animation_data:
                key.animation_data.action = None
                for track in key.animation_data.nla_tracks:
                    track.mute = True
    bpy.context.view_layer.update()
    all_bindings, default_weights, identity = imported_bindings(path, objects)
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

    def compare_direct(signature, deps):
        surface = np.array(
            [
                tuple(
                    ob.evaluated_get(deps).matrix_world
                    @ ob.evaluated_get(deps).data.vertices[vi].co
                )
                for ob, vi in bindings
            ]
        )
        bones = {
            bone.name: np.array(arm.matrix_world @ bone.matrix)
            for bone in arm.pose.bones
        }
        if label == "baseline":
            baseline_samples[signature] = (surface, bones)
            return
        old, old_bones = baseline_samples[signature]
        assert set(bones) == set(old_bones), "Direct Blender bone identities changed"
        position_error = float(np.linalg.norm(surface - old, axis=1).max())
        bone_error = max(
            float(np.abs(bones[name] - old_bones[name]).max()) for name in bones
        )
        magnitude = max(
            1.0,
            float(np.abs(old).max()),
            max(float(np.abs(matrix).max()) for matrix in old_bones.values()),
        )
        budget = 16 * float(np.spacing(np.float32(magnitude)))
        assert position_error <= budget and bone_error <= budget, (
            "Direct Blender pose differs",
            signature,
            position_error,
            bone_error,
            budget,
        )
        direct["maximum_position_error"] = max(
            direct["maximum_position_error"], position_error
        )
        direct["maximum_bone_matrix_error"] = max(
            direct["maximum_bone_matrix_error"], bone_error
        )
        direct["maximum_float32_budget"] = max(direct["maximum_float32_budget"], budget)
        direct["poses"] += 1
        if signature == "neutral_default":
            direct["neutral_default_checked"] = True

    for ob in objects:
        if ob.type == "MESH" and ob.data.shape_keys:
            key = ob.data.shape_keys
            for block, value in zip(
                list(key.key_blocks)[1:], default_weights[key.as_pointer()]
            ):
                block.value = value
    bpy.context.view_layer.update()
    compare_direct("neutral_default", bpy.context.evaluated_depsgraph_get())
    metrics = {}
    maxbone = 0.0
    maxsurface = 0.0
    for clip, entries in w["clips"].items():
        select(clip)
        bone_error = 0.0
        surface_error = 0.0
        for entry in entries:
            deps = pose(entry["time"])
            compare_direct((clip, float(entry["time"])), deps)
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
    if label == "candidate":
        direct.update(
            passed=True,
            source_sha256=results["baseline"]["sha256"],
            candidate_sha256=results["candidate"]["sha256"],
            scope="Direct source/candidate frozen-ID surfaces and every bone matrix at each original witness pose plus controlled neutral/default pose. Sixteen float32 ULPs at baseline coordinate/matrix magnitude; independent of inherited source/witness residual and separate from native/source appearance budgets.",
        )
        (out / "blender-direct-validation.json").write_text(
            json.dumps(direct, indent=2)
        )
    (out / "blender-validation.json").write_text(json.dumps(results, indent=2))
    print("BLENDER_PILOT_PASS", label, maxsurface, maxbone, flush=True)
