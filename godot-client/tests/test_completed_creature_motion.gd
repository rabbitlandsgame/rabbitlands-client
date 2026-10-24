extends SceneTree

const CLIPS := ["Idle_A", "Fighting_Idle", "Hit_Chest", "Death_A", "Sword_Attack", "Walk", "Jog"]
var failures: Array[String] = []
func _init() -> void:
	_run.call_deferred()
func check(ok: bool, label: String) -> void:
	if not ok:
		failures.append(label)
		push_error(label)
func snapshot(sk: Skeleton3D) -> Array[Transform3D]:
	var poses: Array[Transform3D] = []
	for bone in sk.get_bone_count(): poses.append(sk.get_bone_pose(bone))
	return poses
func difference(sk: Skeleton3D, poses: Array[Transform3D]) -> float:
	var error := 0.0
	for bone in sk.get_bone_count():
		var actual := sk.get_bone_pose(bone)
		error = maxf(error, actual.origin.distance_to(poses[bone].origin))
		for axis in 3: error = maxf(error, actual.basis[axis].distance_to(poses[bone].basis[axis]))
	return error
func _run() -> void:
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/completed-creature-motion/index.json"))
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var selected := ""
	var report_path := "user://completed-creature-motion-playback.json"
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="): report_path = argument.trim_prefix("--report=")
		if argument.begins_with("--actor="): selected = argument.trim_prefix("--actor=")
	check(manifest.actors.size() == 47, "47 completed creature drafts")
	var actors: Dictionary = {}
	for name: String in manifest.actors:
		if not selected.is_empty() and selected != name: continue
		var witness: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/completed-creature-motion/" + name + ".json"))
		actors[name] = _audit_actor(name, witness, registry)
		check(actors[name].get("clips", []).size() == witness.clips.size(), name + " every native slot evaluated")
	check(not actors.is_empty(), "selected actors exist")
	var report := {"passed":failures.is_empty(),"failures":failures,"actors":actors,"engine":Engine.get_version_info(),"scope":"Completed creature draft baseline, installed registry/maps, independent off-grid surfaces, normals and bones, loops, one-shot holds, action switches and RESET; all available native slots."}
	FileAccess.open(report_path,FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	print("COMPLETED_CREATURE_GODOT ","PASS" if failures.is_empty() else "FAIL"," actors=",actors.size()," failures=",failures.size())
	quit(0 if failures.is_empty() else 1)

func _audit_actor(name: String, witness: Dictionary, registry: Dictionary) -> Dictionary:
	var actor_failure_start := failures.size()
	var actor_clips := PackedStringArray(witness.clips.keys())
	var config: Dictionary = registry.models[name]
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config.animationMap))
	var resolver := AnimationResolver.new(mapping)
	check(resolver.validate(PackedStringArray(actor_clips)).is_empty(), name + " complete action map")
	check(config.scene == config.animationLibrary, "scene and library use the same baseline model")
	for action in ["walk", "run", "attack_primary", "death"]:
		check(is_equal_approx(resolver.playback_speed_for_action(action),1.0), "review speed " + action)
	for action: String in ["walk", "run"]:
		check(resolver.stride_speed_for_action(action) >= 0.0, "existing stride metadata " + action)
		check(is_equal_approx(resolver.stride_speed_for_action(action, 2.0), (2.0 if bool(mapping.get("strideScalesWithActor",false)) else 1.0) * resolver.stride_speed_for_action(action)), "scaled stride " + action)
	check(resolver.clip_for_action(&"attack_primary") == StringName(witness.review_attack_clip), "attack mapping")
	check(resolver.clip_for_action(&"death") == &"Death_A", "death mapping")
	check(resolver.action_for_command(46) == &"attack_primary", "server attack command")
	check(resolver.action_for_command(3) == &"death", "server death command")
	var path: String = config.scene
	check(FileAccess.get_sha256(path) == witness.sha256, "bound candidate hash")
	check(ResourceLoader.load(path, "PackedScene") != null, "fresh imported runtime scene available")
	var policy := ConfigFile.new()
	check(policy.load(path + ".import") == OK, "tracked import policy")
	check(is_equal_approx(float(policy.get_value("params", "animation/fps", 30.0)), float(witness.get("bake_fps",3072))), "dense import cadence")
	var model := GlbSceneCache.instantiate(path)
	check(model != null, "actual in-project scene cache loading path")
	if model == null:
		return {"passed":false}
	root.add_child(model)
	var sk := model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	var source := model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	source.stop()
	source.active = false
	source.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var reference_model := GlbSceneCache.instantiate(path)
	root.add_child(reference_model)
	var reference_sk := reference_model.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
	source = reference_model.find_children("*", "AnimationPlayer", true, false)[0] as AnimationPlayer
	source.stop()
	source.deterministic = true
	source.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var skin_formats: Array = []
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var arrays: Array = mesh.mesh.surface_get_arrays(surface)
			var weights: Variant = arrays[Mesh.ARRAY_WEIGHTS]
			if weights == null or weights.size() == 0: continue
			var count: int = weights.size() / arrays[Mesh.ARRAY_VERTEX].size()
			skin_formats.append(count)
			check(count == mini(8,int(witness.get("skin_influence_count", 4))), "native skin influence count retained")
	var imported := NativeAnimationImporter.import_library(model, path, sk, {}, PackedStringArray(actor_clips), PackedStringArray(mapping.loopingClips))
	check(imported.errors.is_empty(), "actual native animation importer: " + str(imported.errors))
	var player: AnimationPlayer = imported.player
	check(player != null and player.has_animation("RESET"), "native RESET generated")
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.play("Idle_A", 0.0)
	player.advance(.2)
	var idle := snapshot(sk)
	check(is_equal_approx(player.get_animation("Sword_Attack").length, float(witness.durations.Sword_Attack)), name + " preserved attack duration")
	check(is_equal_approx(player.get_animation("Death_A").length, float(witness.durations.Death_A)), name + " preserved death duration")
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		for index in mesh.mesh.get_blend_shape_count(): mesh.set_blend_shape_value(index, .5)
	var surface_bindings := _surface_bindings(model, sk, witness)
	var actions: Array = []
	for clip: String in actor_clips:
		check(player.has_animation(clip), "clip discovered " + clip)
		var animation := player.get_animation(clip)
		check((animation.loop_mode == Animation.LOOP_LINEAR) == mapping.loopingClips.has(clip), "loop mapping " + clip)
		var witness_error := 0.0
		var morph_error := 0.0
		var import_error := 0.0
		var surface_error := 0.0
		var normal_error := 0.0
		var finite := true
		for entry: Dictionary in witness.clips[clip]:
			player.stop()
			source.stop()
			reference_sk.reset_bone_poses()
			source.play(clip, 0.0)
			source.seek(float(entry.time), true)
			var expected := snapshot(reference_sk)
			source.stop()
			player.play(clip, 0.0)
			player.seek(float(entry.time), true)
			for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
				if mesh.mesh.get_blend_shape_count() == 0: continue
				var values: Array = entry.morph_weights.values()[0]
				check(mesh.mesh.get_blend_shape_count() == values.size(), "all corrective targets retained")
				for shape_index in values.size(): morph_error = maxf(morph_error, absf(mesh.get_blend_shape_value(shape_index)-float(values[shape_index])))
			for probe_index: int in surface_bindings.size():
				var binding: Dictionary = surface_bindings[probe_index]
				var actual_surface := _surface_point(binding.group, binding.index)
				var value: Array = entry.surface[probe_index]
				var expected_surface := Vector3(float(value[0]),float(value[1]),float(value[2]))
				surface_error = maxf(surface_error, actual_surface.distance_to(expected_surface))
				var nn: Array = entry.surface_normals[probe_index]
				var expected_normal := Vector3(float(nn[0]),float(nn[1]),float(nn[2]))
				normal_error = maxf(normal_error,_surface_normal(binding.group,binding.index).distance_to(expected_normal))
			import_error = maxf(import_error, difference(sk, expected))
			for bone_name: String in entry.bones:
				var bone := sk.find_bone(bone_name)
				check(bone >= 0, "bone present " + bone_name)
				if bone < 0: continue
				var actual := sk.global_transform * sk.get_bone_global_pose(bone)
				finite = finite and actual.origin.is_finite() and actual.basis.is_finite()
				var matrix: Array = entry.bones[bone_name]
				for row in 3:
					witness_error = maxf(witness_error, absf(actual.origin[row] - float(matrix[row * 4 + 3])))
					for column in 3:
						witness_error = maxf(witness_error, absf(actual.basis[column][row] - float(matrix[row * 4 + column])))
		check(surface_error < .00025 * float(witness.get("height",1.0)), "independent imported surface " + clip + " " + str(surface_error))
		check(normal_error < .008, "independent surface normals " + clip + " " + str(normal_error))
		check(morph_error < .0002, "independent morph witness " + clip + " " + str(morph_error))
		check(finite, "finite native playback " + clip)
		check(import_error < .0001, "native/imported agreement " + clip + " " + str(import_error))
		check(witness_error < .0001, "independent off-grid GLB witness " + clip + " " + str(witness_error))
		var terminal_hold_error := 0.0
		if not mapping.loopingClips.has(clip):
			player.stop()
			player.play(clip, 0.0)
			player.seek(animation.length, true)
			var held := snapshot(sk)
			player.advance(.2)
			terminal_hold_error = difference(sk, held)
			check(not player.is_playing() and terminal_hold_error < .0001, "one-shot end hold " + clip)
		player.play(witness.review_attack_clip, 0.0)
		player.seek(.6, true)
		player.play(clip, 0.0)
		player.seek(animation.length * .393, true)
		var switched := snapshot(sk)
		player.play("RESET", 0.0)
		player.seek(0.0, true)
		player.play(clip, 0.0)
		player.seek(animation.length * .393, true)
		var switch_error := difference(sk, switched)
		check(switch_error < .0001, "posed attack switch restoration " + clip)
		player.play("Idle_A", 0.0)
		player.seek(.2, true)
		var idle_error := difference(sk, idle)
		check(idle_error < .0001, "idle restoration " + clip)
		actions.append({"clip":clip,"duration_seconds":animation.length,"finite":finite,
			"independent_surface_max_error":surface_error,"independent_surface_normal_max_error":normal_error,"native_import_max_error":import_error,"morph_error":morph_error,"independent_glb_world_max_error":witness_error,
			"attack_switch_error":switch_error,"idle_restore_error":idle_error})
		actions[-1]["terminal_hold_error"] = terminal_hold_error
	var report := {"passed":failures.size() == actor_failure_start,"failures":failures.slice(actor_failure_start),"candidate_sha256":witness.sha256,
		"engine":Engine.get_version_info(),"clips":actions,"skin_influences":skin_formats,"source_skin_slots":witness.skin_influence_count,"max_source_nonzero_influences":witness.max_nonzero_skin_influences,"requires_skin_packing":int(witness.max_nonzero_skin_influences)>8,
		"scope":"Installed draft baseline with actor-specific action map and every native clip; current client component integration."}
	report["preservation_note"] = "All available native clips checked against independent GLB bone, surface and normal witnesses. Original flight preservation and deliberate ground-surface repairs are qualified separately."
	model.free()
	reference_model.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	return report
func _surface_point(group: Dictionary, index: int, rest: bool = false) -> Vector3:
	var mesh: MeshInstance3D = group.mesh
	var sk: Skeleton3D = group.skeleton
	var arrays: Array = group.arrays
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var point := vertices[index]
	if not rest:
		var shapes: Array = group.shapes
		for shape_index: int in shapes.size():
			var amount := mesh.get_blend_shape_value(shape_index)
			if absf(amount) < .000000001: continue
			var shape_vertices: PackedVector3Array = shapes[shape_index][Mesh.ARRAY_VERTEX]
			if group.relative:
				point += shape_vertices[index] * amount
			else:
				point += (shape_vertices[index] - vertices[index]) * amount
	if mesh.skin == null: return _static_surface_frame(mesh, sk, rest) * point
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var count: int = joints.size() / vertices.size()
	var result := Vector3.ZERO
	for slot: int in count:
		var at := index * count + slot
		var weight := weights[at]
		if weight <= 0.0: continue
		var bind := joints[at]
		var bone: int = group.bones[bind]
		var pose := sk.get_bone_global_rest(bone) if rest else sk.get_bone_global_pose(bone)
		result += (sk.global_transform * pose * mesh.skin.get_bind_pose(bind)) * point * weight
	return result

func _surface_bindings(model: Node3D, sk: Skeleton3D, witness: Dictionary) -> Array[Dictionary]:
	var groups: Array[Dictionary] = []
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		var resource := mesh.mesh as ArrayMesh
		if resource == null: continue
		var bones: Array[int] = []
		for bind: int in (mesh.skin.get_bind_count() if mesh.skin != null else 0):
			var bone := sk.find_bone(mesh.skin.get_bind_name(bind))
			if bone < 0: bone = mesh.skin.get_bind_bone(bind)
			check(bone >= 0, "surface bind resolves to skeleton")
			bones.append(bone)
		for surface: int in resource.get_surface_count():
			var arrays: Array = resource.surface_get_arrays(surface)
			var group := {"material_name":resource.surface_get_material(surface).resource_name if resource.surface_get_material(surface) != null else "","mesh":mesh,"skeleton":sk,"arrays":arrays,"shapes":resource.surface_get_blend_shape_arrays(surface),"relative":resource.blend_shape_mode == Mesh.BLEND_SHAPE_MODE_RELATIVE,"bones":bones}
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var points := PackedVector3Array()
			for index: int in vertices.size(): points.append(_surface_point(group, index, true))
			group.rest = points
			groups.append(group)
	var result: Array[Dictionary] = []
	for probe_index: int in witness.surface_rest.size():
		var expected_array: Array = witness.surface_rest[probe_index]
		var expected_nn: Array = witness.surface_rest_normals[probe_index]
		var expected_normal := Vector3(float(expected_nn[0]),float(expected_nn[1]),float(expected_nn[2]))
		var expected := Vector3(float(expected_array[0]),float(expected_array[1]),float(expected_array[2]))
		var best := INF
		var binding: Dictionary = {}
		for group: Dictionary in groups:
			var points: PackedVector3Array = group.rest
			for index: int in points.size():
				if witness.has("surface_material_names") and not str(witness.surface_material_names[probe_index]).is_empty() and str(group.material_name) != str(witness.surface_material_names[probe_index]): continue
				var position_error := expected.distance_squared_to(points[index])
				if position_error > pow(.0002 * float(witness.get("height",1.0)),2): continue
				var normal_distance := _surface_normal(group,index,true).distance_squared_to(expected_normal)
				var uv_distance := 0.0
				if witness.has("surface_uv"):
					var source_uv: Array = witness.surface_uv[probe_index]
					var uv: PackedVector2Array = group.arrays[Mesh.ARRAY_TEX_UV]
					uv_distance = uv[index].distance_squared_to(Vector2(float(source_uv[0]),float(source_uv[1])))
				var skin_error := 0.0
				if witness.has("surface_skin_influences"):
					var actual_skin: Dictionary = {}
					var jj: PackedInt32Array = group.arrays[Mesh.ARRAY_BONES]
					var ww: PackedFloat32Array = group.arrays[Mesh.ARRAY_WEIGHTS]
					var slots: int = jj.size() / points.size()
					for slot: int in slots:
						var at: int = index * slots + slot
						if ww[at] <= .00000001: continue
						var bone_name: String = sk.get_bone_name(group.bones[jj[at]])
						actual_skin[bone_name] = float(actual_skin.get(bone_name,0.0)) + ww[at]
					var expected_skin: Dictionary = witness.surface_skin_influences[probe_index]
					for bone_name: String in expected_skin: skin_error += absf(float(actual_skin.get(bone_name,0.0)) - float(expected_skin[bone_name]))
					for bone_name: String in actual_skin:
						if not expected_skin.has(bone_name): skin_error += float(actual_skin[bone_name])
				var morph_error := 0.0
				if witness.has("surface_source_morph_positions"):
					var signature: Array = witness.surface_source_morph_positions[probe_index]
					for shape_index: int in signature.size():
						var sv: PackedVector3Array = group.shapes[shape_index][Mesh.ARRAY_VERTEX]
						var delta: Vector3 = sv[index] if group.relative else sv[index] - group.arrays[Mesh.ARRAY_VERTEX][index]
						var source: Array = signature[shape_index]
						var expected_delta := Vector3(float(source[0]),float(source[1]),float(source[2]))
						morph_error = maxf(morph_error,delta.distance_to(expected_delta))
				var distance := position_error / pow(float(witness.get("height",1.0)),2) + uv_distance + .00001 * normal_distance + 10.0 * skin_error + morph_error / float(witness.get("height",1.0))
				if distance < best:
					best = distance
					binding = {"group":group,"index":index,"uv_error":sqrt(uv_distance),"rest_normal_error":sqrt(normal_distance),"skin_error":skin_error,"morph_error":morph_error}
		check(not binding.is_empty(), "independent source vertex identity exists")
		if binding.is_empty(): return result
		check(expected.distance_to(binding.group.rest[binding.index]) < .0002 * float(witness.get("height",1.0)), "independent surface rest position")
		check(float(binding.uv_error) < .001, "independent source UV identity")
		check(float(binding.rest_normal_error) < .01, "independent source rest-normal identity")
		check(float(binding.skin_error) < .0003, "independent source skin identity")
		check(float(binding.morph_error) < .0002 * float(witness.get("height",1.0)), "independent original morph identity")
		result.append(binding)
	return result

func _static_surface_frame(mesh: MeshInstance3D, sk: Skeleton3D, rest: bool) -> Transform3D:
	var local := mesh.transform
	var cursor := mesh.get_parent()
	while cursor != null and cursor != sk:
		if cursor is BoneAttachment3D:
			var bone := sk.find_bone(cursor.bone_name)
			if bone >= 0: return sk.global_transform * (sk.get_bone_global_rest(bone) if rest else sk.get_bone_global_pose(bone)) * local
		if cursor is Node3D: local = cursor.transform * local
		cursor = cursor.get_parent()
	return mesh.global_transform

func _surface_normal(group: Dictionary, index: int, rest: bool = false) -> Vector3:
	var mesh: MeshInstance3D = group.mesh
	var sk: Skeleton3D = group.skeleton
	var arrays: Array = group.arrays
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var point := normals[index]
	if not rest:
		var shapes: Array = group.shapes
		for shape_index: int in shapes.size():
			var amount := mesh.get_blend_shape_value(shape_index)
			if absf(amount) < .000000001: continue
			var shape_normals: Variant = shapes[shape_index][Mesh.ARRAY_NORMAL]
			if not shape_normals is PackedVector3Array or shape_normals.size() <= index: continue
			point += (shape_normals[index] if group.relative else shape_normals[index] - normals[index]) * amount
	if mesh.skin == null: return (_static_surface_frame(mesh,sk,rest).basis*point).normalized()
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var count: int = joints.size() / normals.size()
	var result := Vector3.ZERO
	for slot: int in count:
		var at := index * count + slot
		var weight := weights[at]
		if weight <= 0.0: continue
		var bind := joints[at]
		var bone: int = group.bones[bind]
		var pose := sk.get_bone_global_rest(bone) if rest else sk.get_bone_global_pose(bone)
		result += (sk.global_transform * pose * mesh.skin.get_bind_pose(bind)).basis * point * weight
	return result.normalized()
