extends SceneTree
## Opt-in local MPFB study against the actual production actor and equipment
## path. The MPFB files stay outside the model registry and game package.

const ACTIONS: Array[StringName] = [&"idle", &"walk", &"run", &"attack_primary",
	&"attack_secondary", &"attack_flurry", &"combat_idle"]
const HAND_MODES: Array[Dictionary] = [{}, {0: 114, 1: 106}, {0: 163}]
const PHASE_COUNT := 17
const POSE_TOLERANCE := 0.000005
const REST_TOLERANCE := 0.000001
const BODY_TOLERANCE := 0.00002
const WEIGHT_TOLERANCE := 0.000001
const HEAD_NECK_FLOOR := 1.40
const HEAD_NECK_HALF_WIDTH := 0.13
const HIGH_META := &"rl_high_portrait"
const HIGH_USER_META := &"rl_high_portrait_user"
const MPFB_SHADER_PATH := "res://src/actors/mpfb_prototype_appearance.gdshader"
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
var checks := 0
var failures := 0
var bone_samples := 0
var phase_samples := 0
var models: Dictionary
var equipment: Dictionary
var animations: Dictionary
var records: Array[Dictionary] = []
var asset_hashes: Dictionary = {}
var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		# Bound console output while retaining the total failure count.
		if failures <= 20: push_error(label)

func read_json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func prototype_path(sex: String) -> String:
	return OS.get_environment("RL_MPFB_PROTOTYPE_ROOT").path_join(sex + "/luminous_" + sex + ".glb")

func model_config(sex: String, prototype: bool) -> Dictionary:
	var config: Dictionary = models["luminous_" + sex].duplicate(true)
	if prototype:
		config.scene = prototype_path(sex)
		config.geometryProfile = "mpfb"
		config.erase("faceAppearance")
		config.erase("skinPalette")
		var fit_path: String = str(config.scene).get_base_dir().path_join("fit.json")
		if FileAccess.file_exists(fit_path):
			var frame: Variant = read_json(fit_path).get("face_frame_head_local", {})
			if frame is Dictionary and not frame.is_empty(): config.mpfbFaceFrame = frame
	return config

func make_actor(sex: String, prototype: bool, look: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	actor.apply_render_quality(2, true)
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 9980 if sex == "male" else 9981,
		"actor_type": 1 if sex == "male" else 0, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "", "appearance": look, "equipment_visuals": {}},
		adapter, model_config(sex, prototype), animations, equipment)
	expect(errors.is_empty(), sex + " actual actor configures, prototype=" + str(prototype))
	actor.set_process(false)
	actor.set_physics_process(false)
	if actor.animation_player != null:
		actor.animation_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	return actor

func basis_error(a: Basis, b: Basis) -> float:
	return maxf(a.x.distance_to(b.x), maxf(a.y.distance_to(b.y), a.z.distance_to(b.z)))

func transform_error(a: Transform3D, b: Transform3D) -> float:
	return maxf(a.origin.distance_to(b.origin), basis_error(a.basis, b.basis))

func bind_bone(mesh: MeshInstance3D, rig: Skeleton3D, bind: int) -> int:
	var name := mesh.skin.get_bind_name(bind)
	return rig.find_bone(name) if name != &"" else mesh.skin.get_bind_bone(bind)

func check_rest_and_bind(current: ReplicatedActor3D, prototype: ReplicatedActor3D, sex: String) -> void:
	var a := current.get_skeleton()
	var b := prototype.get_skeleton()
	expect(a != null and b != null, sex + " both imported skeletons exist")
	if a == null or b == null: return
	expect(a.get_bone_count() == 77 and b.get_bone_count() == 77, sex + " preserves all77 current joints")
	var maximum_rest := 0.0
	var maximum_global_rest := 0.0
	for index: int in a.get_bone_count():
		var name := a.get_bone_name(index)
		var other := b.find_bone(name)
		expect(other >= 0, sex + " retains bone " + str(name))
		if other < 0: continue
		var parent := a.get_bone_parent(index)
		var other_parent := b.get_bone_parent(other)
		expect((a.get_bone_name(parent) if parent >= 0 else &"") == (b.get_bone_name(other_parent) if other_parent >= 0 else &""), sex + " retains parent for " + str(name))
		maximum_rest = maxf(maximum_rest, transform_error(a.get_bone_rest(index), b.get_bone_rest(other)))
		maximum_global_rest = maxf(maximum_global_rest, transform_error(a.get_bone_global_rest(index), b.get_bone_global_rest(other)))
	expect(maximum_rest <= REST_TOLERANCE and maximum_global_rest <= REST_TOLERANCE, sex + " local/global rest matches including Head")
	var a_body := current._native_model.find_child("body", true, false) as MeshInstance3D
	var b_body := prototype._native_model.find_child("body", true, false) as MeshInstance3D
	expect(a_body != null and b_body != null and a_body.skin != null and b_body.skin != null, sex + " loaded body skins exist")
	if a_body == null or b_body == null or a_body.skin == null or b_body.skin == null: return
	expect(a_body.skin.get_bind_count() == b_body.skin.get_bind_count(), sex + " preserves all inverse bind entries")
	var a_binds: Dictionary = {}
	for bind: int in a_body.skin.get_bind_count():
		a_binds[a.get_bone_name(bind_bone(a_body, a, bind))] = a_body.skin.get_bind_pose(bind)
	var maximum_bind := 0.0
	for bind: int in b_body.skin.get_bind_count():
		var name := b.get_bone_name(bind_bone(b_body, b, bind))
		expect(a_binds.has(name), sex + " bind maps to the same named joint " + str(name))
		if a_binds.has(name): maximum_bind = maxf(maximum_bind, transform_error(a_binds[name], b_body.skin.get_bind_pose(bind)))
	expect(maximum_bind <= REST_TOLERANCE, sex + " loaded inverse bind matrices match including Head")
	records.append({"sex": sex, "kind": "rig_contract", "joint_count": a.get_bone_count(),
		"maximum_local_rest_delta": maximum_rest, "maximum_global_rest_delta": maximum_global_rest,
		"maximum_inverse_bind_delta": maximum_bind})

func check_materials(actor: ReplicatedActor3D, prototype: bool, label: String) -> void:
	if prototype:
		expect(not actor._native_model.has_meta(HIGH_USER_META), label + " never enters the old High portrait user cache")
	var prototype_materials := 0
	for node: Node in actor._native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null: continue
		if prototype: expect(not mesh.has_meta(HIGH_META), label + " has no old High portrait mesh metadata")
		for surface: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface)
			var is_mpfb := material is ShaderMaterial and (material as ShaderMaterial).shader != null \
				and (material as ShaderMaterial).shader.resource_path == MPFB_SHADER_PATH
			if is_mpfb: prototype_materials += 1
			if not prototype: expect(not is_mpfb, label + " cannot inherit an MPFB shader from cached resources")
			if prototype and str(mesh.name) in ["body", "eyes"] and surface == 0:
				var arrays := mesh.mesh.surface_get_arrays(surface)
				var uv2: Variant = arrays[Mesh.ARRAY_TEX_UV2]
				expect(uv2 == null or uv2.size() == 0, label + " authored MPFB head/eyes have no old portrait projection UVs")
				expect(is_mpfb, label + " authored MPFB surface uses its dedicated material")
	if prototype: expect(prototype_materials >= 2, label + " head and eyes have the prototype finish")

func vertex_weights(mesh: MeshInstance3D, rig: Skeleton3D, arrays: Array, index: int) -> Dictionary:
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var joints: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var width := joints.size() / vertices.size()
	var result: Dictionary = {}
	for slot: int in width:
		var value := weights[index * width + slot]
		if value <= 0.0: continue
		var name := rig.get_bone_name(bind_bone(mesh, rig, joints[index * width + slot]))
		result[name] = float(result.get(name, 0.0)) + value
	return result

func body_rows(actor: ReplicatedActor3D, surface: int, cutoff: float) -> Array[Dictionary]:
	var mesh := actor._native_model.find_child("body", true, false) as MeshInstance3D
	var result: Array[Dictionary] = []
	if mesh == null or mesh.mesh == null or surface >= mesh.mesh.get_surface_count(): return result
	var arrays := mesh.mesh.surface_get_arrays(surface)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var used: Dictionary = {}
	var to_model: Transform3D = actor._native_model.global_transform.affine_inverse() * mesh.global_transform
	for index: int in indices:
		if used.has(index): continue
		used[index] = true
		var point: Vector3 = to_model * vertices[index]
		# Exclude only the deliberately replaced head/neck. Arms above this
		# height still belong to the accepted canonical body and must match.
		if point.y > cutoff and absf(point.x) < HEAD_NECK_HALF_WIDTH: continue
		result.append({"point": point, "weights": vertex_weights(mesh, actor.get_skeleton(), arrays, index)})
	return result

func cell(point: Vector3) -> Vector3i:
	return Vector3i(floori(point.x / BODY_TOLERANCE), floori(point.y / BODY_TOLERANCE), floori(point.z / BODY_TOLERANCE))

func body_grid(rows: Array[Dictionary]) -> Dictionary:
	var grid: Dictionary = {}
	for row: Dictionary in rows:
		var key := cell(row.point)
		if not grid.has(key): grid[key] = []
		(grid[key] as Array).append(row)
	return grid

func compare_body_rows(rows: Array[Dictionary], grid: Dictionary) -> Dictionary:
	var maximum_position := 0.0
	var maximum_weight := 0.0
	var missing := 0
	for row: Dictionary in rows:
		var key := cell(row.point)
		var nearest: Dictionary = {}
		var distance := INF
		for dx: int in [-1, 0, 1]:
			for dy: int in [-1, 0, 1]:
				for dz: int in [-1, 0, 1]:
					for other: Dictionary in grid.get(key + Vector3i(dx, dy, dz), []):
						var delta: float = row.point.distance_to(other.point)
						if delta < distance:
							distance = delta
							nearest = other
		if nearest.is_empty() or distance > BODY_TOLERANCE:
			missing += 1
			continue
		maximum_position = maxf(maximum_position, distance)
		var names: Dictionary = row.weights.duplicate()
		names.merge(nearest.weights)
		for name: Variant in names:
			maximum_weight = maxf(maximum_weight, absf(float(row.weights.get(name, 0.0)) - float(nearest.weights.get(name, 0.0))))
	return {"compared_vertices": rows.size(), "unmatched_vertices": missing,
		"maximum_position_delta_m": maximum_position, "maximum_named_weight_delta": maximum_weight}

func check_body(current: ReplicatedActor3D, prototype: ReplicatedActor3D, sex: String) -> void:
	var cutoff := HEAD_NECK_FLOOR
	var a := body_rows(current, 0, cutoff)
	var b := body_rows(prototype, 1, cutoff)
	expect(a.size() > 100 and b.size() > 100, sex + " both engine bodies retain indexed torso/arm/hand/leg geometry")
	var forward := compare_body_rows(a, body_grid(b))
	var reverse := compare_body_rows(b, body_grid(a))
	expect(forward.unmatched_vertices == 0 and reverse.unmatched_vertices == 0, sex + " current and prototype body positions match outside the central head/neck in both directions")
	expect(maxf(forward.maximum_named_weight_delta, reverse.maximum_named_weight_delta) <= WEIGHT_TOLERANCE, sex + " canonical body skinning remains the same after runtime refinement")
	records.append({"sex": sex, "kind": "engine_body_geometry", "central_head_neck_exclusion": {"y_above_m": cutoff, "absolute_x_below_m": HEAD_NECK_HALF_WIDTH},
		"current_surface": 0, "prototype_surface": 1, "current_to_prototype": forward,
		"prototype_to_current": reverse, "comparison": "actual High actor meshes after body/face refinement, before equipment coverage"})

func check_equipment(current: ReplicatedActor3D, prototype: ReplicatedActor3D, gear: Dictionary, label: String) -> void:
	for actor: ReplicatedActor3D in [current, prototype]:
		var diagnostics := actor.equipment_diagnostics()
		expect(diagnostics.visuals == gear, label + " all selected equipment visuals are installed")
		expect(diagnostics.fallback == 0, label + " equipment uses real native assets")
		for part: int in [0, 1]:
			var nodes: Array = actor._equipment_nodes.get(part, [])
			expect(not nodes.is_empty() if gear.has(part) else nodes.is_empty(), label + " correct hand props exist and previous props are removed")
	var a := current.equipment_diagnostics()
	var b := prototype.equipment_diagnostics()
	expect(a.native == b.native and a.socket == b.socket and a.skinned == b.skinned, label + " preserves socket/skinned equipment counts")

func sample_pose(actor: ReplicatedActor3D, action: StringName, phase: float) -> void:
	actor.play_action(action, true)
	var player := actor.animation_player
	player.speed_scale = 1.0
	# Settle the actual action crossfade before selecting the measured time.
	player.advance(0.20)
	var clip := player.get_animation(player.assigned_animation)
	var time := clip.length * phase
	if clip.loop_mode == Animation.LOOP_NONE: time = minf(time, maxf(clip.length - 0.000001, 0.0))
	player.seek(time, true)
	player.advance(0.0)
	actor._advance_facing_offset(1.0)
	actor.get_skeleton().force_update_all_bone_transforms()

func compare_poses(current: ReplicatedActor3D, prototype: ReplicatedActor3D, row: Dictionary) -> void:
	var a := current.get_skeleton()
	var b := prototype.get_skeleton()
	var to_current: Transform3D = current.global_transform.affine_inverse() * a.global_transform
	var to_prototype: Transform3D = prototype.global_transform.affine_inverse() * b.global_transform
	for index: int in a.get_bone_count():
		var other := b.find_bone(a.get_bone_name(index))
		if other < 0: continue
		var a_pose := a.get_bone_global_pose(index)
		var b_pose := b.get_bone_global_pose(other)
		row.maximum_bone_pose_delta = maxf(row.maximum_bone_pose_delta, transform_error(a_pose, b_pose))
		row.maximum_actor_space_pose_delta = maxf(row.maximum_actor_space_pose_delta, transform_error(to_current * a_pose, to_prototype * b_pose))
		bone_samples += 1
	for part: int in [0, 1]:
		var a_nodes: Array = current._equipment_nodes.get(part, [])
		var b_nodes: Array = prototype._equipment_nodes.get(part, [])
		if a_nodes.size() != b_nodes.size(): continue
		for index: int in a_nodes.size():
			var a_node := a_nodes[index] as Node3D
			var b_node := b_nodes[index] as Node3D
			if a_node == null or b_node == null: continue
			row.maximum_hand_prop_transform_delta = maxf(row.maximum_hand_prop_transform_delta,
				transform_error(current.global_transform.affine_inverse() * a_node.global_transform,
					prototype.global_transform.affine_inverse() * b_node.global_transform))
	phase_samples += 1

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	Engine.max_fps = 0
	models = read_json("res://data/actors/models.json").models
	equipment = read_json("res://data/actors/equipment.json")
	animations = read_json("res://data/animations/luminous.json")
	for path: String in ["res://tests/test_mpfb_prototype_integration.gd",
		"res://data/actors/models.json", "res://data/actors/equipment.json", "res://data/animations/luminous.json",
		"res://src/actors/replicated_actor_3d.gd", "res://src/actors/native_animation_importer.gd",
		"res://src/actors/character_proportions.gd", "res://src/actors/human_portrait_presets.gd",
		"res://src/actors/human_locomotion_polish.gd", "res://src/actors/human_hand_pose.gd",
		"res://src/actors/human_attack_library.gd", "res://src/actors/mpfb_prototype_appearance.gd",
		"res://src/actors/mpfb_prototype_appearance.gdshader", "res://src/actors/high_portrait_appearance.gd",
		"res://src/actors/high_portrait_appearance.gdshader"]:
		asset_hashes[path] = FileAccess.get_sha256(path)
	for sex: String in ["female", "male"]:
		expect(FileAccess.file_exists(prototype_path(sex)), "explicit MPFB prototype exists for " + sex)
		if not FileAccess.file_exists(prototype_path(sex)):
			finish()
			return
		for path: String in [str(models["luminous_" + sex].scene), prototype_path(sex), prototype_path(sex).get_base_dir().path_join("fit.json")]:
			if FileAccess.file_exists(path): asset_hashes[path] = FileAccess.get_sha256(path)
		var library_path := str(models["luminous_" + sex].get("animationLibrary", ""))
		if FileAccess.file_exists(library_path): asset_hashes[library_path] = FileAccess.get_sha256(library_path)
	var registry_snapshot := var_to_bytes(models)
	for sex: String in ["female", "male"]:
		var look := PRESETS.appearance("Mira" if sex == "female" else "Rowan").merged({"shirt": 5, "pants": 2, "boots": 2})
		var current := make_actor(sex, false, look)
		var prototype := make_actor(sex, true, look)
		check_rest_and_bind(current, prototype, sex)
		check_materials(current, false, sex + " Current")
		check_materials(prototype, true, sex + " MPFB")
		check_body(current, prototype, sex)
		for height: int in [0, 50, 100]:
			for build: int in [0, 50, 100]:
				var shape := look.merged({"height": height, "build": build}, true)
				current.apply_appearance_variants(shape)
				prototype.apply_appearance_variants(shape)
				for kit: int in CreationArchetypes.count():
					for mode: int in HAND_MODES.size():
						var gear := CreationArchetypes.loadout_at(kit)
						gear.erase(0)
						gear.erase(1)
						gear.merge(HAND_MODES[mode], true)
						current.apply_equipment_visuals(gear)
						prototype.apply_equipment_visuals(gear)
						var label := "%s h%d b%d kit%d hand%d" % [sex, height, build, kit, mode]
						check_equipment(current, prototype, gear, label)
						var row := {"kind": "runtime_pose_equipment", "sex": sex, "height": height,
							"build": build, "kit": kit, "hand_mode": mode, "maximum_bone_pose_delta": 0.0,
							"maximum_actor_space_pose_delta": 0.0, "maximum_hand_prop_transform_delta": 0.0}
						for action: StringName in ACTIONS:
							expect(current.resolver.clip_for_action(action) == prototype.resolver.clip_for_action(action), label + " shares the accepted " + str(action) + " clip")
							for sample: int in PHASE_COUNT:
								var phase := float(sample) / float(PHASE_COUNT - 1)
								sample_pose(current, action, phase)
								sample_pose(prototype, action, phase)
								await process_frame
								compare_poses(current, prototype, row)
						expect(row.maximum_bone_pose_delta <= POSE_TOLERANCE, label + " all77 joint poses match at17 phases of every action")
						expect(row.maximum_actor_space_pose_delta <= POSE_TOLERANCE, label + " visual scale and actor-space joint placement match")
						expect(row.maximum_hand_prop_transform_delta <= POSE_TOLERANCE, label + " actual hand prop attachment transforms match")
						records.append(row)
		prototype.free()
		current.free()
		await process_frame
		# Switching models in the workshop creates a fresh actor from shared
		# resources. Check that MPFB never contaminates the Current cache.
		var restored := make_actor(sex, false, look)
		check_materials(restored, false, sex + " Current after MPFB release")
		restored.free()
		await process_frame
	expect(var_to_bytes(models) == registry_snapshot, "the production model registry remains exact")
	for path: String in asset_hashes:
		expect(FileAccess.get_sha256(path) == asset_hashes[path], "input remains unchanged during the integration proof: " + path.get_file())
	finish()

func finish() -> void:
	var output := OS.get_environment("RL_MPFB_INTEGRATION_REPORT")
	if output.is_empty(): output = "user://mpfb-prototype-integration.json"
	var report := {"checks": checks, "failures": failures, "joint_pose_samples": bone_samples,
		"phase_samples": phase_samples, "phases_per_action": PHASE_COUNT, "actions": ACTIONS,
		"height_values": [0, 50, 100], "build_values": [0, 50, 100], "class_kits": CreationArchetypes.count(),
		"hand_modes": HAND_MODES, "input_sha256": asset_hashes,
		"fixture_sha256": FileAccess.get_sha256("res://tests/test_mpfb_prototype_integration.gd"),
		"tolerances": {"pose_transform": POSE_TOLERANCE, "rest_and_inverse_bind": REST_TOLERANCE,
			"canonical_body_position_m": BODY_TOLERANCE, "named_skin_weight": WEIGHT_TOLERANCE},
		"one_shot_endpoint_policy": "last phase is one microsecond before clip end to prevent automatic recovery",
		"records": records, "visual_approval": false,
		"scope": "actual Godot actor, imported skeleton/skin and instantiated equipment; no server or native-binary execution"}
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		failures += 1
		push_error("Could not write MPFB integration report")
	else:
		file.store_string(JSON.stringify(report, "  "))
	print("MPFB_PROTOTYPE_INTEGRATION: %d checks, %d failures; %d joint poses at%d phases" % [checks, failures, bone_samples, phase_samples])
	quit(1 if failures else 0)
