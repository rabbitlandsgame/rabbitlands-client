extends SceneTree
## Exercise the prepared registry fast path through real actor configuration,
## equipment creation, swaps and clearing, beside the mutable fallback path.

const Cache = preload("res://src/actors/equipment_registry_snapshot_cache.gd")
const KIT_A := {0: 114, 1: 106, 3: 133, 4: 219, 5: 208, 6: 248}
const KIT_B := {0: 164, 1: 111, 3: 138, 4: 221, 5: 211, 6: 252}

var _failures := 0
var _checks := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	Cache.clear()
	var equipment := _json("res://data/actors/equipment.json")
	var prepared := Cache.prepare(equipment)
	var fallback := equipment.duplicate(true)
	var models := _json("res://data/actors/models.json").get("models", {}) as Dictionary
	var animation := _json("res://data/animations/luminous.json")

	var shared_male := _make_actor(9101, models["luminous_male"], animation, prepared)
	var fallback_male := _make_actor(9102, models["luminous_male"], animation, fallback)
	var shared_female := _make_actor(9103, models["luminous_female"], animation, prepared)
	var fallback_female := _make_actor(9104, models["luminous_female"], animation, fallback)
	var actors := [shared_male, fallback_male, shared_female, fallback_female]
	if actors.any(func(actor: Variant) -> bool: return actor == null):
		_finish(actors)
		return

	_expect(is_same(shared_male._equipment_config, prepared)
		and is_same(shared_female._equipment_config, prepared),
		"two rigs acquire the same explicitly prepared catalogue")
	_expect(not is_same(fallback_male._equipment_config, fallback)
		and not is_same(fallback_female._equipment_config, fallback)
		and not is_same(fallback_male._equipment_config, fallback_female._equipment_config),
		"mutable callers retain independent actor copies")
	_expect(shared_male.fit_groups() == fallback_male.fit_groups()
		and shared_female.fit_groups() == fallback_female.fit_groups(),
		"prepared and fallback catalogues resolve identical fit variants")

	_apply_and_compare(shared_male, fallback_male, KIT_A, "male kit A")
	_apply_and_compare(shared_female, fallback_female, KIT_B, "female kit B")
	_apply_and_compare(shared_male, fallback_male, KIT_B, "male swap to kit B")
	_apply_and_compare(shared_female, fallback_female, KIT_A, "female swap to kit A")

	var male_nodes := _equipment_node_ids(shared_male)
	var female_nodes := _equipment_node_ids(shared_female)
	_expect(not male_nodes.is_empty() and not female_nodes.is_empty(),
		"both shared-registry actors build equipment nodes")
	for node_id: int in male_nodes:
		_expect(node_id not in female_nodes, "equipment nodes are never shared between actors")
	var male_mesh := _first_equipment_mesh(shared_male)
	var female_mesh := _first_equipment_mesh(shared_female)
	_expect(male_mesh != null and female_mesh != null, "both actors build equipment meshes")
	if male_mesh != null and female_mesh != null:
		var female_override := female_mesh.material_override
		male_mesh.material_override = StandardMaterial3D.new()
		_expect(female_mesh.material_override == female_override,
			"one actor's material override cannot cross into another actor")

	shared_male.apply_equipment_visuals({})
	_expect(_equipment_node_ids(shared_male).is_empty(), "clearing removes one actor's equipment")
	_expect(not _equipment_node_ids(shared_female).is_empty(),
		"clearing one actor leaves the other actor's equipment intact")

	# Mutation after prepare cannot affect shared actors. New actors configured
	# from the mutable caller see the changed catalogue through defensive copies.
	var original_models := equipment["models"] as Dictionary
	var original_entry := original_models["0:114"] as Dictionary
	var prepared_scene := str(prepared["models"]["0:114"]["scene"])
	original_entry["scene"] = "res://original-mutation-does-not-exist.glb"
	_expect(str(prepared["models"]["0:114"]["scene"]) == prepared_scene,
		"mutating the original dictionary after prepare cannot change the snapshot")
	var mutable_models := fallback["models"] as Dictionary
	var mutable_entry := mutable_models["0:114"] as Dictionary
	var original_scene := str(mutable_entry.get("scene", ""))
	mutable_entry["scene"] = "res://does-not-exist.glb"
	_expect(str(shared_female._equipment_config["models"]["0:114"]["scene"]) == original_scene,
		"caller mutation after prepare cannot change existing shared actors")
	_expect(str(fallback_male._equipment_config["models"]["0:114"]["scene"]) == original_scene,
		"caller mutation cannot change an existing fallback actor")
	var changed_copy := Cache.acquire(fallback)
	_expect(str(changed_copy["models"]["0:114"]["scene"]) == "res://does-not-exist.glb",
		"a later mutable acquire sees the caller's changed catalogue")

	_finish(actors)


func _make_actor(id: int, model: Dictionary, animation: Dictionary,
		equipment: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var dto := {"actor_id": id, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": {}, "equipment_visuals": {}}
	var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight": 0.0}),
		model, animation, equipment)
	_expect(errors.is_empty(), "actor %d configures: %s" % [id, errors])
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor


func _apply_and_compare(shared: ReplicatedActor3D, fallback: ReplicatedActor3D,
		visuals: Dictionary, label: String) -> void:
	shared.apply_equipment_visuals(visuals)
	fallback.apply_equipment_visuals(visuals)
	var shared_snapshot := _equipment_snapshot(shared)
	var fallback_snapshot := _equipment_snapshot(fallback)
	_expect(not shared_snapshot.is_empty(), label + " produces equipment geometry")
	_expect(shared_snapshot == fallback_snapshot,
		label + " matches defensive-copy node and mesh output")


func _equipment_snapshot(actor: ReplicatedActor3D) -> PackedStringArray:
	var rows := PackedStringArray()
	var parts: Array = actor._equipment_nodes.keys()
	parts.sort()
	for part: Variant in parts:
		var nodes := actor._equipment_nodes[part] as Array
		for index: int in range(nodes.size()):
			var node := nodes[index] as Node
			var node_transform := (node as Node3D).transform if node is Node3D \
				else Transform3D.IDENTITY
			rows.append("%s|%d|%s|%s|%s|%s" % [part, index, node.get_class(), node.name,
				_variant_sha(node_transform), node.visible if node is VisualInstance3D else true])
			var meshes: Array[MeshInstance3D] = []
			if node is MeshInstance3D:
				meshes.append(node as MeshInstance3D)
			for child: Node in node.find_children("*", "MeshInstance3D", true, false):
				meshes.append(child as MeshInstance3D)
			for mesh_node: MeshInstance3D in meshes:
				rows.append(_mesh_snapshot(str(part), mesh_node))
	rows.sort()
	return rows


func _mesh_snapshot(part: String, mesh_node: MeshInstance3D) -> String:
	var surfaces: Array = []
	var materials: Array = []
	if mesh_node.mesh != null:
		for surface: int in range(mesh_node.mesh.get_surface_count()):
			surfaces.append(mesh_node.mesh.surface_get_arrays(surface))
			var material := mesh_node.get_active_material(surface)
			materials.append(_material_snapshot(material))
	var binds: Array = []
	if mesh_node.skin != null:
		for bind: int in range(mesh_node.skin.get_bind_count()):
			binds.append([mesh_node.skin.get_bind_name(bind),
				mesh_node.skin.get_bind_bone(bind), mesh_node.skin.get_bind_pose(bind)])
	return "%s|mesh|%s|%s|%s|%s|%s|%s" % [part, mesh_node.name,
		mesh_node.visible, _variant_sha(mesh_node.transform), _variant_sha(surfaces),
		_variant_sha(binds), _variant_sha(materials)]


func _material_snapshot(material: Material) -> Variant:
	if material == null:
		return null
	var row := {"class": material.get_class(), "path": material.resource_path,
		"priority": material.render_priority}
	if material is BaseMaterial3D:
		var base := material as BaseMaterial3D
		row["albedoColor"] = base.albedo_color
		row["albedoTexture"] = (base.albedo_texture.resource_path
			if base.albedo_texture != null else "")
		row["transparency"] = base.transparency
		row["shadingMode"] = base.shading_mode
	return row


func _variant_sha(value: Variant) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(value))
	return context.finish().hex_encode()


func _equipment_node_ids(actor: ReplicatedActor3D) -> Array[int]:
	var ids: Array[int] = []
	for nodes: Array in actor._equipment_nodes.values():
		for node: Node in nodes:
			ids.append(node.get_instance_id())
	return ids


func _first_equipment_mesh(actor: ReplicatedActor3D) -> MeshInstance3D:
	for nodes: Array in actor._equipment_nodes.values():
		for node: Node in nodes:
			if node is MeshInstance3D:
				return node as MeshInstance3D
			var meshes := node.find_children("*", "MeshInstance3D", true, false)
			if not meshes.is_empty():
				return meshes[0] as MeshInstance3D
	return null


func _json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary


func _finish(actors: Array) -> void:
	for actor: Variant in actors:
		if actor is Node and is_instance_valid(actor):
			(actor as Node).queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	print("EQUIPMENT_REGISTRY_SHARED checks=", _checks, " failures=", _failures)
	quit(1 if _failures else 0)


func _expect(value: bool, label: String) -> void:
	_checks += 1
	if value:
		return
	_failures += 1
	push_error("FAIL: " + label)
