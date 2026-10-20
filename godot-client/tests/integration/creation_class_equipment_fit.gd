extends SceneTree
## Every creation class is race-independent, so its representative kit must
## survive the same live equipment path on all sixteen playable body rigs.

var failures := 0
var checks := 0


func _init() -> void:
	call_deferred("run")


func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)


func run() -> void:
	var models_document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))
	var models: Dictionary = models_document.get("models", {}) as Dictionary
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/equipment.json"))
	var equipment_models: Dictionary = equipment.get("models", {}) as Dictionary
	var suppressed_backing_models: Array[String] = []
	var wardrobe_only_models: Array[String] = []
	for model_key_value: Variant in equipment_models:
		var model_key := str(model_key_value)
		var equipment_model := equipment_models[model_key_value] as Dictionary
		if bool(equipment_model.get("wardrobeOnly", false)):
			wardrobe_only_models.append(model_key)
			expect((equipment_model.get("hides", []) as Array).is_empty(),
				model_key + " keeps the fitted native shirt visible")
			expect((equipment_model.get("wardrobeColor", []) as Array).size() == 3,
				model_key + " has a three-channel class colour")
			expect((equipment_model.get("wardrobeTrimColor", []) as Array).size() == 3,
				model_key + " has a three-channel class trim colour")
		if not equipment_model.has("suppressGeneratedBacking"):
			continue
		expect(equipment_model["suppressGeneratedBacking"] is bool and
			bool(equipment_model["suppressGeneratedBacking"]),
			model_key + " backing suppression is an explicit true boolean")
		suppressed_backing_models.append(model_key)
	suppressed_backing_models.sort()
	expect(suppressed_backing_models == ["4:179", "6:192"],
		"only the visually verified Warded leg and boot pieces suppress backing")
	wardrobe_only_models.sort()
	expect(wardrobe_only_models.is_empty(),
		"no torso stands in for the native wardrobe: the creation torsos are fitted meshes")
	var body_templates: Dictionary = equipment.get("bodyTemplates", {}) as Dictionary
	var slugs: Array = body_templates.keys()
	slugs.sort()
	expect(slugs.size() == 16, "class equipment sweep covers all sixteen player rigs")
	expect(CreationArchetypes.count() == 4, "four creation classes are fitted")
	expect(CreationArchetypes.loadout_at(0) == {0: 114, 1: 106, 2: 105, 3: 134, 4: 220, 5: 209, 6: 249},
		"Vanguard previews the whole militia set")
	expect(CreationArchetypes.loadout_at(1) == {0: 164, 3: 159, 4: 230, 5: 225, 6: 226, 8: 1},
		"Ranger previews hood, vest, breeches and fieldboots")
	expect(CreationArchetypes.loadout_at(2) == {0: 142, 3: 115, 4: 185, 5: 222, 6: 198},
		"Arcanist previews the whole Acolyte set")
	expect(CreationArchetypes.loadout_at(3) == {0: 163, 2: 100, 3: 122, 4: 176, 5: 189, 6: 205},
		"Warden previews the Antler Hood and the Furtrim set")
	for slug_value: Variant in slugs:
		var slug := str(slug_value)
		var model: Dictionary = models.get(slug, {}) as Dictionary
		expect(not model.is_empty(), slug + " model config exists")
		if model.is_empty():
			continue
		var animation_path := str(model.get("animationMap",
			"res://data/animations/luminous.json"))
		var animations: Dictionary = JSON.parse_string(
			FileAccess.get_file_as_string(animation_path))
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({
			"actor_id": 9100, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": "", "appearance": {},
			"equipment_visuals": {},
		}, CoordinateAdapter.new({"walkingHeight": 0.0}), model,
			animations, equipment)
		expect(errors.is_empty(), slug + " configures for class equipment")
		if not errors.is_empty():
			actor.queue_free()
			await process_frame
			continue
		actor.set_process(false)
		actor.set_physics_process(false)
		for class_index: int in range(CreationArchetypes.count()):
			var entry := CreationArchetypes.at(class_index)
			var label := "%s %s" % [slug, str(entry.get("label", "class"))]
			var loadout := CreationArchetypes.loadout_at(class_index)
			actor.apply_equipment_visuals(loadout)
			await process_frame
			var diagnostics := actor.equipment_diagnostics()
			expect((diagnostics.get("visuals", {}) as Dictionary) == loadout,
				label + " replaces the previous class without stale equipment")
			expect(int(diagnostics.get("fallback", -1)) == 0,
				label + " loads only shipped equipment models")
			for raw_part: Variant in loadout:
				var part := int(raw_part)
				var nodes: Array = actor._equipment_nodes.get(part, []) as Array
				expect(not nodes.is_empty(), "%s creates equipment part %d" % [label, part])
			_check_skin_contract(actor, label, loadout)
			_check_class_torso_mesh(actor, label, loadout)
			_check_fitted_backings(actor, label, loadout)
			_check_hand_socket(actor, label, str(entry.get("label", "class")))
		var mixed_backing_loadouts: Array[Dictionary] = [
			{5: 216},
			{4: 179},
			{6: 192},
			{4: 179, 6: 224},
			{4: 230, 6: 192},
			{4: 179, 5: 216, 6: 192},
		]
		for mixed_loadout: Dictionary in mixed_backing_loadouts:
			actor.apply_equipment_visuals(mixed_loadout)
			await process_frame
			_check_fitted_backings(actor, "%s mixed %s" % [slug, mixed_loadout],
				mixed_loadout)
		actor.apply_equipment_visuals({})
		await process_frame
		expect(actor._equipment_nodes.is_empty(),
			slug + " unequip removes every class equipment node")
		_check_native_body_restored(actor, slug)
		actor.queue_free()
		await process_frame
	NativeAnimationImporter.clear()
	print("CREATION_CLASS_EQUIPMENT_FIT checks=", checks,
		" failures=", failures, " rigs=", slugs.size())
	quit(1 if failures else 0)


func _check_class_torso_mesh(actor: ReplicatedActor3D, label: String,
		loadout: Dictionary) -> void:
	var visual := int(loadout.get(ReplicatedActor3D.BODY_PART, -1))
	if visual < 0:
		return
	var model := actor._equipment_model_config(ReplicatedActor3D.BODY_PART, visual)
	expect(not bool(model.get("wardrobeOnly", false)),
		label + " wears a fitted torso mesh, not the native wardrobe")
	var skinned_torsos := 0
	for node_value: Variant in actor._equipment_nodes.get(ReplicatedActor3D.BODY_PART, []) as Array:
		var node := node_value as Node
		expect(not node.has_meta("wardrobe_only"),
			label + " adds no mesh-free wardrobe marker")
		if (node is MeshInstance3D and (node as MeshInstance3D).skin != null
				and (node as MeshInstance3D).visible):
			skinned_torsos += 1
	expect(skinned_torsos >= 1, label + " draws a visible skinned torso")


func _check_wardrobe_class_torso(actor: ReplicatedActor3D, label: String,
		loadout: Dictionary) -> void:
	var visual := int(loadout.get(ReplicatedActor3D.BODY_PART, -1))
	if visual < 0:
		return
	var model := actor._equipment_model_config(ReplicatedActor3D.BODY_PART, visual)
	expect(bool(model.get("wardrobeOnly", false)),
		label + " uses the actor's fitted native wardrobe torso")
	var torso_nodes := actor._equipment_nodes.get(ReplicatedActor3D.BODY_PART, []) as Array
	expect(torso_nodes.size() == 1 and (torso_nodes[0] as Node).has_meta("wardrobe_only"),
		label + " represents the torso with one mesh-free wardrobe marker")
	var torso_meshes := 0
	for node_value: Variant in torso_nodes:
		if node_value is MeshInstance3D:
			torso_meshes += 1
	expect(torso_meshes == 0,
		label + " adds no duplicate skinned torso mesh")
	var visible_shirts := 0
	var fitted_shirts := 0
	var masked_bodies := 0
	var native_model := actor.get_node_or_null("NativeModel") as Node3D
	for node_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node_value as MeshInstance3D
		if mesh_node.name.to_lower() in ["body", "char1", "mesh_node"] \
				and mesh_node.has_meta("uncovered_body_mesh") \
				and mesh_node.mesh != (mesh_node.get_meta("uncovered_body_mesh") as Mesh):
			masked_bodies += 1
		if ReplicatedActor3D.SHIRT_SURFACES.has(mesh_node.name.to_lower()) and mesh_node.visible:
			visible_shirts += 1
		if mesh_node.name.to_lower() == "wardrobe_shirt":
			expect(mesh_node.has_meta("wardrobe_shirt_fitted_mesh")
				and mesh_node.mesh == (mesh_node.get_meta(
					"wardrobe_shirt_fitted_mesh") as Mesh),
				label + " activates the cached shoulder fit")
			fitted_shirts += 1
	expect(masked_bodies > 0,
		label + " masks the body to the fitted wardrobe neckline")
	expect(visible_shirts > 0, label + " keeps a fitted native shirt visible")
	expect(fitted_shirts == 1, label + " fits exactly one native shirt")


func _check_skin_contract(actor: ReplicatedActor3D, label: String,
		loadout: Dictionary) -> void:
	var skeleton := actor.get_skeleton()
	var skinned := 0
	for nodes_value: Variant in actor._equipment_nodes.values():
		for node_value: Variant in nodes_value as Array:
			var node := node_value as Node
			if node is not MeshInstance3D:
				continue
			var mesh_node := node as MeshInstance3D
			if mesh_node.skin == null:
				continue
			skinned += 1
			var skin := mesh_node.skin
			for bind: int in range(skin.get_bind_count()):
				expect(skeleton.find_bone(skin.get_bind_name(bind)) >= 0,
					label + " retains every named equipment bind")
	var expected_minimum := 4 if loadout.has(4) or loadout.has(6) else (
		1 if loadout.has(2) else 0)
	expect(skinned >= expected_minimum,
		label + " has every skinned garment required by its preview loadout")


func _check_fitted_backings(actor: ReplicatedActor3D, label: String,
		loadout: Dictionary) -> void:
	var suppressed_parts := 0
	var expected_suppressed_parts := 0
	var reviewed_suppressed_visuals := {
		4: 179,
		6: 192,
	}
	for part_value: Variant in reviewed_suppressed_visuals:
		var part := int(part_value)
		if int(loadout.get(part, -1)) == int(reviewed_suppressed_visuals[part_value]):
			expected_suppressed_parts += 1
	for part: int in [ReplicatedActor3D.BODY_PART, 4, 6]:
		if not loadout.has(part):
			continue
		var model := actor._equipment_model_config(part, int(loadout[part]))
		if not bool(model.get("suppressGeneratedBacking", false)):
			continue
		suppressed_parts += 1
		var suppressed_nodes := 0
		var cover_nodes := 0
		for piece_value: Variant in actor._equipment_nodes.get(part, []) as Array:
			var piece := piece_value as Node
			if piece.has_meta("generated_body_cover"):
				cover_nodes += 1
			if not piece.has_meta("suppress_generated_backing"):
				continue
			suppressed_nodes += 1
			expect(not (piece as MeshInstance3D).visible,
				"%s keeps suppressed generated backing hidden for part %d" % [label, part])
		expect(suppressed_nodes > 0,
			"%s carries suppression metadata onto generated part %d nodes" % [label, part])
		expect(cover_nodes > 0,
			"%s retains body-cover metadata while hiding part %d backing" % [label, part])
	if loadout.has(6):
		var visible_boot_backings := 0
		for piece_value: Variant in actor._equipment_nodes.get(6, []) as Array:
			var piece := piece_value as Node
			if piece.has_meta("boot_backing_with_legs") and (piece as MeshInstance3D).visible:
				visible_boot_backings += 1
		var boot_model := actor._equipment_model_config(6, int(loadout[6]))
		var ranger_paired_lower := (int(loadout.get(4, 0)) == 230
			and int(loadout.get(6, 0)) == 224)
		var expected_boot_backings := 0 if (ranger_paired_lower or bool(
			boot_model.get("suppressGeneratedBacking", false))) else 1
		expect(visible_boot_backings == expected_boot_backings,
			label + " draws no overlapping boot lining against its trousers")
	if loadout.has(4):
		var visible_leg_backings := 0
		for piece_value: Variant in actor._equipment_nodes.get(4, []) as Array:
			var piece := piece_value as Node
			if piece.has_meta("leg_backing_with_boots") and (piece as MeshInstance3D).visible:
				visible_leg_backings += 1
		var leg_model := actor._equipment_model_config(4, int(loadout[4]))
		var expected_leg_backings := 0 if bool(leg_model.get(
			"suppressGeneratedBacking", false)) else 1
		expect(visible_leg_backings == expected_leg_backings,
			label + " uses one trouser lining against its boots")
	expect(suppressed_parts == expected_suppressed_parts,
		label + " suppresses exactly the selected reviewed backing draws")
	if expected_suppressed_parts > 0:
		var covered_surfaces := 0
		var native_model := actor.get_node_or_null("NativeModel") as Node3D
		for mesh_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
			var mesh_node := mesh_value as MeshInstance3D
			if not mesh_node.has_meta("uncovered_body_mesh"):
				continue
			covered_surfaces += 1
			expect(mesh_node.mesh != (mesh_node.get_meta("uncovered_body_mesh") as Mesh),
				label + " still applies body cover behind hidden generated backing")
		expect(covered_surfaces > 0,
			label + " keeps at least one native body surface covered")


func _check_native_body_restored(actor: ReplicatedActor3D, label: String) -> void:
	var native_model := actor.get_node_or_null("NativeModel") as Node3D
	var restored := 0
	for mesh_value: Node in native_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := mesh_value as MeshInstance3D
		if mesh_node.name.to_lower() == "wardrobe_shirt":
			expect(not mesh_node.has_meta("wardrobe_shirt_fitted_mesh")
				and (not mesh_node.has_meta("wardrobe_shirt_unfitted_mesh")
					or mesh_node.mesh == (mesh_node.get_meta(
						"wardrobe_shirt_unfitted_mesh") as Mesh)),
				label + " removes the class-only shoulder fit after unequip")
		if not mesh_node.has_meta("uncovered_body_mesh"):
			continue
		restored += 1
		expect(mesh_node.mesh == (mesh_node.get_meta("uncovered_body_mesh") as Mesh),
			label + " restores the exact native body mesh after unequip")
	expect(restored > 0, label + " exercised body-cover restoration")


func _check_hand_socket(actor: ReplicatedActor3D, label: String,
		class_label: String) -> void:
	var attachments := 0
	var skeleton := actor.get_skeleton()
	var hand := skeleton.find_bone("hand_r")
	var rest := skeleton.get_bone_global_rest(hand)
	var fit := actor.rig_fit_scale("legacy")
	var model := actor._equipment_model_config(0, int(actor._equipment_visuals.get(0, 0)))
	# Every class weapon is fought with in the same fist: the reviewed
	# arming-sword grip (cdd44dea5), which import_generated_weapons now closes
	# on every weapon. The quarterstaff's source origin sits below its wrapped
	# handle, so its fist closes 0.10 further up the staff -- the hold the
	# reviewed Warden placement measured.
	var fist_offset := Vector3(-0.0757, -0.05, 0.0)
	# The Ranger's longbow keeps the socket it was reviewed in (cdd44dea5):
	# its prop is hidden whenever the ranged presentation draws its bow.
	var socket_offsets := {
		"Vanguard": fist_offset,
		"Ranger": Vector3(-0.08, -0.04, -0.08),
		"Arcanist": fist_offset,
		"Warden": Vector3(-0.0757, -0.05, -0.1),
	}
	var fighting_holds := {"Warden": 0.10}
	var fist := rest.basis.inverse() * (fist_offset * fit)
	for piece_value: Variant in actor._equipment_nodes.get(0, []) as Array:
		var piece := piece_value as Node
		if piece is not BoneAttachment3D or piece.get_child_count() == 0:
			continue
		attachments += 1
		var attachment := piece as BoneAttachment3D
		var prop := piece.get_child(0) as Node3D
		var hand_world := skeleton.global_transform * skeleton.get_bone_global_pose(hand).origin
		# At rest the socket stays inside the fighting fist. Only the wrist
		# lowers the weapon; the shoulder and elbow retain the idle clip.
		var fighting: Transform3D = prop.get_meta(&"fighting_grip", prop.transform)
		# Where the registry's fighting grip closes on the piece: its origin,
		# or for the quarterstaff the hold that far up the staff from it.
		var hold := Vector3(0.0, float(fighting_holds.get(class_label, 0.0)) * fit, 0.0)
		var grip_point := attachment.global_transform * (fighting.origin + fighting.basis.orthonormalized() * hold)
		var grip_distance := grip_point.distance_to(hand_world)
		expect(grip_distance >= 0.025 and grip_distance <= 0.13,
			label + " places its weapon grip inside the palm reach (%.3f m)" % grip_distance)
		var socket := model.get("socket", {}) as Dictionary
		expect(actor._vector3(socket.get("offset", []), Vector3.INF).is_equal_approx(
				socket_offsets[class_label]),
			label + " uses its reviewed right-palm socket placement")
		var placed := rest.affine_inverse() * actor._socket_placement(socket, rest, fit, fit)
		expect(fighting.is_equal_approx(placed),
			label + " keeps the registry socket as its fighting grip")
		# The Ranger's visible bow is a separate animated left-hand visual, so
		# its hidden registry prop has no idle grip to stand in.
		if class_label == "Ranger":
			expect(not model.has("idleSocket") and not prop.has_meta(&"idle_grip"),
				label + " leaves its idle to the ranged presentation")
			continue
		expect(prop.has_meta(&"idle_grip"), label + " has an idle grip to stand in")
		expect(prop.transform.is_equal_approx(fighting),
			label + " holds its weapon inside the fist while standing")
		# The closed hand holds the piece: the point of it at the fist lies
		# on its own long axis and between its ends.
		var held := prop.transform.affine_inverse() * fist
		var bounds := _prop_bounds(prop)
		expect(Vector2(held.x, held.z).length() < 0.03 and held.y > bounds.position.y
				and held.y < bounds.end.y,
			label + " holds the weapon in the fist, on its haft or hilt")
		# The wrist lowers the staff ahead while keeping its entire mesh
		# above the floor. It no longer slides through an open idle hand.
		var lowest := _prop_lowest(prop) - actor.global_position.y
		expect(lowest > 0.0, label + " idles with its weapon clear of the floor")
		if class_label == "Warden":
			expect(lowest >= 0.075, label + " keeps the closed-fist staff above the floor")
			var shaft := prop.global_basis.y.normalized()
			expect(shaft.y < -0.25 and shaft.dot(-actor.global_basis.z.normalized()) > 0.5,
				label + " lowers the staff down and ahead from the fist")
	expect(attachments == 1, label + " has exactly one right-hand attachment")


## The local bounds of a held prop's meshes, in the prop's own frame.
func _prop_bounds(prop: Node3D) -> AABB:
	var bounds := AABB()
	var first := true
	for mesh_value: Node in prop.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := mesh_value as MeshInstance3D
		if mesh_node.mesh == null:
			continue
		var to_prop := prop.global_transform.affine_inverse() * mesh_node.global_transform
		var local := to_prop * mesh_node.mesh.get_aabb()
		bounds = local if first else bounds.merge(local)
		first = false
	return bounds


## The height of a held prop's lowest vertex, in world space.
func _prop_lowest(prop: Node3D) -> float:
	var lowest := INF
	for mesh_value: Node in prop.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := mesh_value as MeshInstance3D
		if mesh_node.mesh == null:
			continue
		for surface: int in mesh_node.mesh.get_surface_count():
			var vertices: PackedVector3Array = mesh_node.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for vertex: Vector3 in vertices:
				lowest = minf(lowest, (mesh_node.global_transform * vertex).y)
	return lowest

