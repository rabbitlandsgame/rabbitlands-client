extends SceneTree
## Deterministic before/after parity probe for rebound Skin interning.
##
## The same probe is run with ELORIA_REBOUND_SKIN_POOL_PHASE=baseline before
## runtime integration and =candidate afterwards. It freezes only the cape
## cloth modifier in this fixture so the report isolates equipment, materials,
## skeleton binds, and a fixed non-rest animation pose. Production actor code is
## not changed by this fixture.

const KIT_A: Dictionary = {
	0: 114,
	1: 106,
	2: 0,
	3: 117,
	4: 171,
	5: 184,
	6: 192,
}
const KIT_B: Dictionary = {
	0: 164,
	1: 111,
	2: 1,
	3: 109,
	4: 172,
	5: 185,
	6: 193,
}
const RIGS := ["luminous_male", "luminous_female", "orun_male", "ssarathi_male"]
const POSE_TIME := 0.37

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var models := _json("res://data/actors/models.json").get("models", {}) as Dictionary
	var equipment := _json("res://data/actors/equipment.json")
	var report: Dictionary = {
		"schemaVersion": 1,
		"probe": "rebound_skin_pool_parity",
		"phase": OS.get_environment("ELORIA_REBOUND_SKIN_POOL_PHASE"),
		"clothFreeze": {
			"enabled": true,
			"scope": "fixture-only",
			"reason": "freeze CapeCloth so parity isolates equipment and skin output",
		},
		"pose": {"action": "idle", "time": POSE_TIME},
		"kits": {"A": KIT_A, "B": KIT_B,
			"stripped": _without(KIT_B, [2, 4, 6]),
			"bare": _without(KIT_B, [2, 4, 5, 6])},
		"actors": [],
	}
	if str(report["phase"]).is_empty():
		report["phase"] = "unspecified"

	for slug: String in RIGS:
		var model: Dictionary = models.get(slug, {}) as Dictionary
		if model.is_empty():
			_expect(false, slug + " exists in models.json")
			continue
		var animation := _json(str(model.get("animationMap", "")))
		var actor_index := (report["actors"] as Array).size()
		var primary := _make_actor(slug + "_primary", 5000 + actor_index * 2,
			model, animation, equipment, {"skin": 0, "eyes": 0, "hair": 0})
		var peer := _make_actor(slug + "_peer", 5001 + actor_index * 2,
			model, animation, equipment, {"skin": 3, "eyes": 4, "hair": 2})
		if primary == null or peer == null:
			_finish_actor(primary)
			_finish_actor(peer)
			continue

		await _apply_and_pose(primary, KIT_A)
		await _apply_and_pose(peer, KIT_A)
		var peer_before := _actor_snapshot(peer)
		var kit_a := _actor_snapshot(primary)

		await _apply_and_pose(primary, KIT_B)
		var kit_b := _actor_snapshot(primary)
		var stripped_kit := _without(KIT_B, [2, 4, 6])
		await _apply_and_pose(primary, stripped_kit)
		var stripped := _actor_snapshot(primary)
		var bare_kit := _without(KIT_B, [2, 4, 5, 6])
		await _apply_and_pose(primary, bare_kit)
		var bare := _actor_snapshot(primary)
		await _apply_and_pose(primary, KIT_B)
		var restored := _actor_snapshot(primary)
		var peer_after := _actor_snapshot(peer)

		var row: Dictionary = {
			"rig": slug,
			"kitA": kit_a,
			"kitB": kit_b,
			"stripped": stripped,
			"bare": bare,
			"restored": restored,
			"peerMaterialsStable": _material_digest(peer_before) ==
				_material_digest(peer_after),
			"restoredMatchesKitB": _parity_digest(restored) == _parity_digest(kit_b),
			"checks": {
				"kitAHasEquipment": _visuals_equal(kit_a, KIT_A),
				"kitBHasEquipment": _visuals_equal(kit_b, KIT_B),
				"strippedRemovesLegsBootsCape": _parts_absent(stripped, [2, 4, 6]),
				"strippedHasNoCapeMesh": _cape_count(stripped) == 0,
				"strippedKeepsTorso": _part_present(stripped, 5),
				"restoresCape": _cape_count(restored) > 0,
				"bareRemovesBodyCover": int(bare.get("bodyCoverMeshCount", 0)) == 0,
				"bareRemovesTorsoReplacement": int(bare.get(
					"torsoReplacementMeshCount", 0)) == 0,
				"restoresBodyCover": int(restored.get("bodyCoverMeshCount", 0)) > 0,
				"restoresTorsoReplacement": int(restored.get(
					"torsoReplacementMeshCount", 0)) > 0,
				"peerMaterialsStable": _material_digest(peer_before) ==
					_material_digest(peer_after),
				"restoredMatchesKitB": _parity_digest(restored) ==
					_parity_digest(kit_b),
			},
		}
		for value: Variant in (row["checks"] as Dictionary).values():
			_expect(bool(value), "%s parity contract" % slug)
		report["actors"].append(row)
		_finish_actor(primary)
		_finish_actor(peer)
		await process_frame

	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	var json := JSON.stringify(report)
	var output_path := OS.get_environment("ELORIA_REBOUND_SKIN_POOL_OUTPUT")
	if not output_path.is_empty():
		var output := FileAccess.open(output_path, FileAccess.WRITE)
		if output != null:
			output.store_string(json + "\n")
	print("REBOUND_SKIN_POOL_PARITY " + json)
	quit(1 if _failures else 0)


func _make_actor(actor_name: String, actor_id: int, model: Dictionary,
		animation: Dictionary, equipment: Dictionary, appearance: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	actor.name = actor_name
	root.add_child(actor)
	var dto := {"actor_id": actor_id, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": actor_name, "appearance": appearance,
		"equipment_visuals": {}}
	var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight": 0.0}),
		model, animation, equipment)
	_expect(errors.is_empty(), "%s configures: %s" % [actor_name, errors])
	if not errors.is_empty():
		actor.free()
		return null
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor


func _apply_and_pose(actor: ReplicatedActor3D, visuals: Dictionary) -> void:
	actor.apply_equipment_visuals(visuals)
	await process_frame
	_freeze_fixture_cloth(actor)
	if actor.animation_player != null:
		# The probe owns a fixed pose. Manual callback mode prevents either the
		# frame between transitions or the await below from advancing it.
		actor.animation_player.callback_mode_process = \
			AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	actor.play_action(&"idle", true)
	if actor.animation_player != null:
		actor.animation_player.seek(POSE_TIME, true)
		actor.animation_player.pause()
		_expect(is_equal_approx(actor.animation_player.current_animation_position,
			POSE_TIME), "%s reaches fixed animation time" % actor.name)
	await process_frame


func _freeze_fixture_cloth(actor: ReplicatedActor3D) -> void:
	var skeleton := actor.get_skeleton()
	if skeleton == null:
		return
	var cloth := skeleton.get_node_or_null("CapeCloth") as SkeletonModifier3D
	if cloth != null:
		cloth.active = false


func _actor_snapshot(actor: ReplicatedActor3D) -> Dictionary:
	var meshes: Array = []
	var cape_meshes := 0
	var body_cover_meshes := 0
	var torso_replacement_meshes := 0
	for value: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := value as MeshInstance3D
		if mesh == null or mesh.mesh == null or _skip_mesh(actor, mesh):
			continue
		var path := str(actor.get_path_to(mesh))
		var row := _mesh_snapshot(actor, mesh, path)
		meshes.append(row)
		if _path_is_part(path, 2):
			cape_meshes += 1
		if mesh.has_meta("generated_body_cover"):
			body_cover_meshes += 1
		if mesh.has_meta("replaces_torso_body"):
			torso_replacement_meshes += 1
	meshes.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return str(a["path"]) < str(b["path"]))
	var skeleton := actor.get_skeleton()
	var cloth_active := false
	if skeleton != null:
		var cloth := skeleton.get_node_or_null("CapeCloth") as SkeletonModifier3D
		cloth_active = cloth != null and cloth.active
	var diagnostics := actor.equipment_diagnostics()
	return {
		"visuals": diagnostics.get("visuals", {}),
		"meshCount": meshes.size(),
		"meshDigest": _variant_sha(meshes),
		"meshes": meshes,
		"capeMeshCount": cape_meshes,
		"bodyCoverMeshCount": body_cover_meshes,
		"torsoReplacementMeshCount": torso_replacement_meshes,
		"capeClothActive": cloth_active,
		"animation": str(actor.animation_player.current_animation)
			if actor.animation_player != null else "",
		"animationPosition": actor.animation_player.current_animation_position
			if actor.animation_player != null else -1.0,
		"skeletonPoseDigest": _skeleton_pose_digest(skeleton),
	}


func _mesh_snapshot(actor: ReplicatedActor3D, mesh: MeshInstance3D,
		path: String) -> Dictionary:
	var surfaces: Array = []
	var materials: Array = []
	for surface: int in range(mesh.mesh.get_surface_count()):
		var arrays := mesh.mesh.surface_get_arrays(surface)
		var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array \
			if arrays.size() == Mesh.ARRAY_MAX else PackedVector3Array()
		surfaces.append({"surface": surface, "vertices": vertices.size(),
			"indices": (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size()
				if arrays.size() == Mesh.ARRAY_MAX and arrays[Mesh.ARRAY_INDEX] != null else 0,
			"digest": _variant_sha(arrays)})
		materials.append(_material_snapshot(mesh.get_active_material(surface)))
	var binds: Array = []
	if mesh.skin != null:
		for bind: int in range(mesh.skin.get_bind_count()):
			binds.append([mesh.skin.get_bind_name(bind), mesh.skin.get_bind_bone(bind),
				mesh.skin.get_bind_pose(bind)])
	var row := {
		"path": path,
		"visible": mesh.visible,
		"visibilityLayer": mesh.layers,
		"castShadow": mesh.cast_shadow,
		"nativeEquipment": mesh.has_meta("native_equipment"),
		"generatedBodyCover": mesh.has_meta("generated_body_cover"),
		"geometry": {"surfaceCount": surfaces.size(), "digest": _variant_sha(surfaces)},
		"skin": {"bindCount": binds.size(), "digest": _variant_sha(binds)},
		"materials": materials,
		"materialOverride": _material_snapshot(mesh.material_override),
		"posedVertices": _posed_vertex_snapshot(mesh, actor.get_skeleton()),
	}
	row["fingerprint"] = _variant_sha(row)
	return row


func _posed_vertex_snapshot(mesh: MeshInstance3D, skeleton: Skeleton3D) -> Dictionary:
	if skeleton == null or mesh.skin == null:
		return {"sampleCount": 0, "digest": _variant_sha([])}
	var samples: Array = []
	for surface: int in range(mesh.mesh.get_surface_count()):
		var arrays := mesh.mesh.surface_get_arrays(surface)
		if arrays.size() != Mesh.ARRAY_MAX or arrays[Mesh.ARRAY_VERTEX] == null:
			continue
		var vertices := arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
		var joints := arrays[Mesh.ARRAY_BONES] as PackedInt32Array
		var weights := arrays[Mesh.ARRAY_WEIGHTS] as PackedFloat32Array
		if joints.is_empty() or weights.is_empty() or vertices.is_empty():
			continue
		if joints.size() % vertices.size() != 0 or weights.size() % vertices.size() != 0:
			continue
		var influences := joints.size() / vertices.size()
		if (influences != 4 and influences != 8) \
				or weights.size() / vertices.size() != influences:
			continue
		var count: int = mini(vertices.size(), 16)
		for vertex_index: int in range(count):
			var posed := Vector3.ZERO
			var total := 0.0
			for slot: int in range(influences):
				var offset := vertex_index * influences + slot
				if offset >= joints.size() or offset >= weights.size():
					continue
				var weight := float(weights[offset])
				if weight <= 0.0:
					continue
				var bind_index := int(joints[offset])
				if bind_index < 0 or bind_index >= mesh.skin.get_bind_count():
					continue
				var bind_name := str(mesh.skin.get_bind_name(bind_index))
				var bone := skeleton.find_bone(bind_name) if not bind_name.is_empty() else -1
				if bone < 0:
					bone = mesh.skin.get_bind_bone(bind_index)
				if bone < 0:
					continue
				posed += (skeleton.get_bone_global_pose(bone) *
					mesh.skin.get_bind_pose(bind_index)) * vertices[vertex_index] * weight
				total += weight
			samples.append([surface, vertex_index, posed if total > 0.0 else vertices[vertex_index]])
	return {"sampleCount": samples.size(), "digest": _variant_sha(samples)}


func _skeleton_pose_digest(skeleton: Skeleton3D) -> String:
	if skeleton == null:
		return _variant_sha([])
	var poses: Array = []
	for bone: int in range(skeleton.get_bone_count()):
		poses.append([skeleton.get_bone_name(bone), skeleton.get_bone_global_pose(bone)])
	return _variant_sha(poses)


func _material_snapshot(material: Material) -> Variant:
	if material == null:
		return null
	var row: Dictionary = {"class": material.get_class(),
		"path": material.resource_path, "priority": material.render_priority}
	if material is BaseMaterial3D:
		var base := material as BaseMaterial3D
		row.merge({"albedoColor": base.albedo_color, "transparency": base.transparency,
			"shadingMode": base.shading_mode, "cullMode": base.cull_mode,
			"grow": base.grow, "growAmount": base.grow_amount})
	if material is ShaderMaterial:
		var shader := (material as ShaderMaterial).shader
		row["shaderPath"] = shader.resource_path if shader != null else ""
		var parameters: Array = []
		for name: String in ["skin_tint", "skin_color", "eye_tint", "hair_tint",
				"recolor_skin", "base_color", "base_texture", "region_texture",
				"mask_uv_scale", "mask_uv_offset"]:
			parameters.append([name, _material_value(
				(material as ShaderMaterial).get_shader_parameter(name))])
		row["shaderParameters"] = parameters
	return row


func _material_value(value: Variant) -> Variant:
	if value is Texture2D:
		return {"texturePath": (value as Texture2D).resource_path}
	return value


func _material_digest(snapshot: Dictionary) -> String:
	var rows: Array = snapshot.get("meshes", []) as Array
	var materials: Array = []
	for row_value: Variant in rows:
		var row := row_value as Dictionary
		materials.append([row.get("path", ""), row.get("materials", []),
			row.get("materialOverride", null)])
	return _variant_sha(materials)


func _parity_digest(snapshot: Dictionary) -> String:
	# Removing then restoring parts changes dictionary insertion order, which
	# is not equipment state. Canonicalize only those keys; mesh/pose digests
	# continue to compare exact serialized content.
	var visuals: Dictionary = snapshot.get("visuals", {})
	var parts := visuals.keys()
	parts.sort()
	var ordered_visuals: Array = []
	for part: Variant in parts:
		ordered_visuals.append([part, visuals[part]])
	return _variant_sha({"visuals": ordered_visuals,
		"meshDigest": snapshot.get("meshDigest", ""),
		"meshes": snapshot.get("meshes", []),
		"capeMeshCount": snapshot.get("capeMeshCount", 0),
		"bodyCoverMeshCount": snapshot.get("bodyCoverMeshCount", 0),
		"torsoReplacementMeshCount": snapshot.get("torsoReplacementMeshCount", 0),
		"animation": snapshot.get("animation", ""),
		"animationPosition": snapshot.get("animationPosition", -1.0),
		"posed": snapshot.get("skeletonPoseDigest", "")})


func _skip_mesh(actor: ReplicatedActor3D, mesh: MeshInstance3D) -> bool:
	var path := str(actor.get_path_to(mesh))
	return path.begins_with("SelectionRing") or path.contains("MapDot")


func _path_is_part(path: String, part: int) -> bool:
	return path.contains("EquipmentPart_%d_" % part) \
		or path.contains("EquipmentSkin_%d_Visual_" % part)


func _cape_count(snapshot: Dictionary) -> int:
	return int(snapshot.get("capeMeshCount", 0))


func _visuals_equal(snapshot: Dictionary, requested: Dictionary) -> bool:
	var visuals := snapshot.get("visuals", {}) as Dictionary
	if visuals.size() != requested.size():
		return false
	for raw_part: Variant in requested:
		var part := int(raw_part)
		if int(visuals.get(part, -1)) != int(requested[raw_part]):
			return false
	return true


func _parts_absent(snapshot: Dictionary, parts: Array) -> bool:
	var visuals := snapshot.get("visuals", {}) as Dictionary
	for part: int in parts:
		if visuals.has(part) or visuals.has(str(part)):
			return false
	return true


func _part_present(snapshot: Dictionary, part: int) -> bool:
	var visuals := snapshot.get("visuals", {}) as Dictionary
	return visuals.has(part) or visuals.has(str(part))


func _without(source: Dictionary, parts: Array) -> Dictionary:
	var copy := source.duplicate()
	for part: int in parts:
		copy.erase(part)
		copy.erase(str(part))
	return copy


func _json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary


func _finish_actor(actor: ReplicatedActor3D) -> void:
	if actor != null and is_instance_valid(actor):
		actor.queue_free()


func _variant_sha(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(value))
	return context.finish().hex_encode()


func _expect(value: bool, label: String) -> void:
	if value:
		return
	_failures += 1
	push_error("FAIL: " + label)
