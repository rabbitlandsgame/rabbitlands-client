extends SceneTree
## Review evidence through the complete production actor/appearance/equipment path.
var output := ""
var stage: Node3D
var camera: Camera3D
var models: Dictionary
var equipment: Dictionary
var animations: Dictionary
var failures := 0
var records: Array = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)

func make_actor(slug: String, appearance: Dictionary, loadout: Dictionary = {}) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors := actor.configure({"actor_id": 9901, "x": 0, "y": 0, "rotation": 0,
		"kind": 1, "name": "", "appearance": appearance, "equipment_visuals": loadout},
		CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animations, equipment)
	expect(errors.is_empty(), slug + " complete actor configures " + str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.rotation.y = PI
	actor._advance_facing_offset(1.0)
	for node: Node in actor.get_children():
		if node is Node3D and node.name != "NativeModel":
			(node as Node3D).hide()
	freeze_idle(actor)
	return actor

func freeze_idle(actor: ReplicatedActor3D) -> void:
	actor.play_action(&"idle", true)
	actor.animation_player.seek(0.40, true)
	actor.animation_player.pause()
	actor.get_skeleton().force_update_all_bone_transforms()

func focus_of(actor: ReplicatedActor3D) -> Vector3:
	var skeleton := actor.get_skeleton()
	return skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, 0.055, 0.0)

func capture(name: String) -> void:
	for frame: int in range(6):
		await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(output.path_join(name + ".png")) == OK, "save " + name)
	records.append({"capture": name, "sha256": FileAccess.get_sha256(output.path_join(name + ".png"))})
	print("RENDER ", name)

func check_picking(actor: ReplicatedActor3D, label: String) -> void:
	await physics_frame
	await process_frame
	var collision := actor.get_node("SelectionCollision") as CollisionShape3D
	var shape := collision.shape as CapsuleShape3D
	expect(is_equal_approx(shape.radius, actor.SELECTION_RADIUS) and is_equal_approx(shape.height, 1.9), label + " fixed picking capsule")
	var target := actor.global_position + Vector3(0, 1.0, 0)
	var hit := stage.get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(target + Vector3(0, 0, 3), target, 2))
	expect(not hit.is_empty() and hit.collider == actor, label + " actual mouse ray picks actor")

func run() -> void:
	output = OS.get_environment("RL_REAL_PREVIEW_OUTPUT")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/human-portraits")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(720, 720)
	stage = Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("1b242b")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("b8c3d0")
	environment.environment.ambient_light_energy = 0.62
	stage.add_child(environment)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-32, -28, 0)
	key.light_energy = 1.15
	key.light_color = Color("ffe9d1")
	stage.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, 145, 0)
	fill.light_energy = 0.45
	fill.light_color = Color("a1beca")
	stage.add_child(fill)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 0.55
	camera.current = true
	camera.cull_mask = 3
	stage.add_child(camera)
	models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	animations = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var presets: Array[Dictionary] = [
		{"id": "rowan", "slug": "luminous_male", "hair_style": 1, "hair_color": 1, "hair_detail": 1, "facial_hair": 0, "jaw": 62, "cheekbones": 68, "nose": 44},
		{"id": "mira", "slug": "luminous_female", "hair_style": 3, "hair_color": 14, "hair_detail": 2, "facial_hair": 0, "jaw": 35, "cheekbones": 70, "nose": 35},
		{"id": "tavi", "slug": "luminous_male", "hair_style": 1, "hair_color": 1, "hair_detail": 2, "facial_hair": 5, "jaw": 80, "cheekbones": 62, "nose": 66}]
	for preset: Dictionary in presets:
		var appearance := {"hair": AppearanceVariants.pack_hair(preset.hair_style, preset.hair_color), "skin": 2, "eyes": 2}
		appearance.merge(preset)
		records.append({"preset": preset.id, "appearance": appearance, "body_scene": models[preset.slug].scene, "body_sha256": FileAccess.get_sha256(models[preset.slug].scene)})
		var actor := make_actor(preset.slug, appearance)
		await process_frame
		await check_picking(actor, preset.id)
		var face := actor._native_model.find_child("body", true, false) as MeshInstance3D
		expect(face.material_override != null or face.get_surface_override_material(0) != null, preset.id + " production appearance shader active")
		for mode: String in ["before", "after"]:
			var look := appearance.duplicate()
			if mode == "before":
				look.merge({"jaw": 50, "cheekbones": 50, "nose": 50, "hair_detail": 0, "facial_hair": 0}, true)
			actor.apply_appearance_variants(look)
			freeze_idle(actor)
			var focus := focus_of(actor)
			for angle: String in ["front", "threequarter", "profile"]:
				camera.position = focus + {"front": Vector3(0, 0.055, 1.0), "threequarter": Vector3(0.40, 0.055, 1.0), "profile": Vector3(0.95, 0.055, 0.02)}[angle]
				camera.look_at(focus)
				await capture(preset.id + "-" + mode + "-" + angle)

			if mode == "after":
				var beard := actor._native_model.get_node_or_null("PortraitFacialHair") as MeshInstance3D
				if beard != null and beard.mesh != null:
					var vertices := 0
					var triangles := 0
					var maximum_weight_error := 0.0
					for surface: int in range(beard.mesh.get_surface_count()):
						var arrays := beard.mesh.surface_get_arrays(surface)
						var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
						var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
						var stride := weights.size() / positions.size()
						vertices += positions.size()
						triangles += arrays[Mesh.ARRAY_INDEX].size() / 3
						for index: int in range(positions.size()):
							var total := 0.0
							for influence: int in range(stride):
								total += weights[index * stride + influence]
							maximum_weight_error = maxf(maximum_weight_error, absf(total - 1.0))
					expect(maximum_weight_error < 0.0001, preset.id + " normalized beard skin")
					records.append({"beard": preset.id, "vertices": vertices, "triangles": triangles, "skin_binds": beard.skin.get_bind_count(), "maximum_skin_weight_error": maximum_weight_error})
		if preset.id == "tavi":
			actor.apply_equipment_visuals({3: 143})
			freeze_idle(actor)
			camera.position = focus_of(actor) + Vector3(0.40, 0.055, 1.0)
			camera.look_at(focus_of(actor))
			await capture("tavi-great-helm")
			records.append({"id": preset.id, "helmet": 143, "equipment": actor.equipment_diagnostics()})
		actor.free()
		await process_frame
	# Four complete actors retain their fixed authoritative footprints while the
	# entire existing equipment hierarchy follows the same scale as the body.
	root.size = Vector2i(1400, 1000)
	camera.size = 2.40
	var actors: Array[ReplicatedActor3D] = []
	for index: int in range(4):
		var slug := "luminous_male" if index < 2 else "luminous_female"
		var value := 0 if index % 2 == 0 else 100
		var appearance := {"height": value, "build": value, "hair": AppearanceVariants.pack_hair(1 if index < 2 else 3, 1 if index < 2 else 14), "hair_detail": 1 if index < 2 else 2, "skin": 2, "eyes": 2, "facial_hair": 5 if index == 1 else 0}
		var actor := make_actor(slug, appearance, CreationArchetypes.loadout_at(index))
		actor.position.x = (float(index) - 1.5) * 0.72
		actor.server_target = actor.position
		actors.append(actor)
		records.append({"id": slug + "-" + str(value), "equipment": actor.equipment_diagnostics(), "scale": actor._native_model.scale, "footprint": actor.footprint})
		await check_picking(actor, slug + str(value))
	for angle: String in ["front", "side"]:
		if angle == "side":
			for actor: ReplicatedActor3D in actors:
				actor.rotation.y = PI + PI / 2.0
		camera.size = 2.75 if angle == "side" else 2.40
		camera.position = Vector3(0.12 if angle == "side" else 0.0, 1.6, 5.0)
		camera.look_at(Vector3(0.12 if angle == "side" else 0.0, 1.0, 0))
		await capture("body-extremes-" + angle)
	for actor: ReplicatedActor3D in actors:
		actor.free()
	FileAccess.open(output.path_join("runtime-evidence.json"), FileAccess.WRITE).store_string(JSON.stringify({"failures": failures, "records": records, "sources": {"character_proportions": FileAccess.get_sha256("res://src/actors/character_proportions.gd"), "portrait_groom": FileAccess.get_sha256("res://src/actors/portrait_groom.gd"), "portrait_hair_shader": FileAccess.get_sha256("res://src/actors/portrait_hair.gdshader"), "portrait_beard_shader": FileAccess.get_sha256("res://src/actors/portrait_beard.gdshader")}}, "  "))
	print("Runtime portrait evidence: ", failures, " failures")
	quit(1 if failures else 0)
