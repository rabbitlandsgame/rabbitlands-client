extends SceneTree
## Verify authored units through the real actor, including unchanged sockets.

var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func make_actor(slug: String, equipment: Dictionary) -> ReplicatedActor3D:
	var model: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"][slug]
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 9011, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), model, animation, equipment)
	expect(errors.is_empty(), slug + " configures")
	actor.set_process(false)
	actor.set_physics_process(false)
	return actor

func sockets(actor: ReplicatedActor3D) -> Dictionary:
	var found := {}
	for nodes: Array in actor._equipment_nodes.values():
		for node: Node in nodes:
			if node is BoneAttachment3D:
				found[str(node.name)] = (node.get_child(0) as Node3D).transform
	return found

func has_textured_mesh(actor: ReplicatedActor3D) -> bool:
	for nodes: Array in actor._equipment_nodes.values():
		for node: Node in nodes:
			var meshes: Array[Node] = node.find_children("*", "MeshInstance3D", true, false)
			if node is MeshInstance3D:
				meshes.append(node)
			for mesh_node: MeshInstance3D in meshes:
				if mesh_node.mesh == null:
					continue
				for surface: int in range(mesh_node.mesh.get_surface_count()):
					var material := mesh_node.get_active_material(surface) as BaseMaterial3D
					if material != null and material.albedo_texture != null:
						var picture: Image = material.albedo_texture.get_image()
						if picture != null and not picture.is_empty():
							return true
	return false

func body_materials(actor: ReplicatedActor3D) -> Array:
	var found: Array = []
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.name.to_lower() not in ["body", "scalp", "wardrobe_shirt", "wardrobe_pants", "wardrobe_boots"] or mesh.mesh == null:
			continue
		for surface: int in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface) as StandardMaterial3D
			if material != null:
				found.append([mesh, surface, material.albedo_texture, material.albedo_color, material.grow, material.grow_amount])
	return found

func check_materials(snapshot: Array, restored: bool, label: String) -> void:
	for row: Array in snapshot:
		var material := (row[0] as MeshInstance3D).get_active_material(int(row[1])) as StandardMaterial3D
		expect(material != null, label + " material survives covering")
		if material == null:
			continue
		expect(material.albedo_texture == row[2], label + " retains each original skin and wardrobe atlas")
		if restored:
			expect(material.albedo_color == row[3] and material.grow == row[4] and is_equal_approx(material.grow_amount, float(row[5])), label + " restores each surface tint and normal grow")

func run() -> void:
	var path := "res://data/actors/equipment.json"
	if not OS.get_cmdline_user_args().is_empty():
		path = OS.get_cmdline_user_args()[0]
	var current: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var legacy: Dictionary = current.duplicate(true)
	var profile: Dictionary = current.get("fitProfiles", {}).get("legacy", {})
	expect(not profile.is_empty(), "legacy authored measurements are recorded")
	for key: String in profile:
		legacy[key] = profile[key]
	legacy.erase("fitProfiles")
	for model: Dictionary in legacy["models"].values():
		model.erase("fitProfile")
		model.erase("variants")
	for slug: String in current["bodyTemplates"]:
		var before := make_actor(slug, legacy)
		var after := make_actor(slug, current)
		var materials := body_materials(after)
		var template: String = current["bodyTemplates"][slug]
		var refitted: bool = slug in current.get("refittedBodies", [])
		if refitted:
			var ratios := after._girth_ratios(template, "canonical")
			expect(not ratios.is_empty(), slug + " fits clothing to replacement body")
			for bone: String in ratios:
				var expected := clampf(float(current["bodyGirth"][slug][bone]) / float(current["authoredBodyGirth"][template][bone]), 1.0, 2.0)
				expect(is_equal_approx(ratios[bone], expected), slug + " uses original garment measurement: " + bone)
			expect(after._ground_drops(template, "boots", "canonical").size() == 4, slug + " uses new foot anchors")
		else:
			expect(after._girth_ratios(template, "canonical").is_empty(), slug + " uses its shared body fit without girth scaling")
			expect(after._ground_drops(template, "boots", "canonical").is_empty(), slug + " uses its shared foot fit without sole translation")
		expect(not after._shares_authored_body(template, "legacy"), slug + " shared shape does not override legacy socket units")
		expect(absf(after.rig_fit_scale() - 1.0) < 0.00001, slug + " canonical scale is one")
		expect(absf(after.rig_fit_scale("legacy") - before.rig_fit_scale()) < 0.000001, slug + " legacy scale preserved")
		# Sword and battle gauntlet are hand sockets, not skinned finger gloves.
		for visual: int in [114, 184]:
			before.apply_equipment_visuals({0: visual})
			after.apply_equipment_visuals({0: visual})
			expect(has_textured_mesh(before) and has_textured_mesh(after), slug + " hand prop retains its original texture: " + str(visual))
			var old := sockets(before)
			var new := sockets(after)
			expect(old.size() > 0 and old.keys() == new.keys(), slug + " socket attaches")
			for key: String in old:
				expect((old[key] as Transform3D).is_equal_approx(new[key]), slug + " unchanged hand socket " + key)
		after.apply_equipment_visuals({3: 133, 4: 219, 5: 208, 6: 248})
		check_materials(materials, false, slug)
		var skins := 0
		for nodes: Array in after._equipment_nodes.values():
			for node: Node in nodes:
				if node is not MeshInstance3D:
					continue
				var skin := (node as MeshInstance3D).skin
				if skin == null:
					continue
				skins += 1
				expect(skin.get_bind_count() == 77, slug + " full ordered bind array")
				for bind: int in range(skin.get_bind_count()):
					var bone := after.get_skeleton().find_bone(skin.get_bind_name(bind))
					expect(bone >= 0, slug + " bind name exists")
					if bone < 0:
						continue
					var at_rest := after.get_skeleton().get_bone_global_rest(bone) * skin.get_bind_pose(bind)
					if refitted:
						expect(at_rest.is_finite() and at_rest.basis.determinant() > 0.0, slug + " fitted garment bind remains valid")
					else:
						expect(at_rest.is_equal_approx(Transform3D.IDENTITY), slug + " garment has no repeated rest compensation: " + str(skin.get_bind_name(bind)))
		expect(skins >= 7, slug + " canonical outfit loaded")
		after.apply_equipment_visuals({})
		check_materials(materials, true, slug)
		before.queue_free()
		after.queue_free()
		await process_frame
	NativeAnimationImporter.clear()
	print("EQUIPMENT_FIT_PROFILES checks=", checks, " failures=", failures)
	quit(1 if failures else 0)
