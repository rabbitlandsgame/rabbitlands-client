extends SceneTree
## Real Human actors, unchanged shared outfits and reversible face sculpting.
const FIT := preload("res://src/actors/character_proportions.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func equipment_resources(actor: ReplicatedActor3D) -> Dictionary:
	var result := {}
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.has_meta("native_equipment"):
			result[str(mesh.name)] = [mesh.mesh, mesh.skin, mesh.transform]
	return result

func run() -> void:
	expect(FIT.visual_scale({}).is_equal_approx(Vector3.ONE), "legacy appearance retains authored size")
	expect(FIT.visual_scale({"height": -500, "build": 900}).is_equal_approx(Vector3(1.15, 0.90, 1.15)), "out-of-range size is bounded")
	expect(FIT.visual_scale({"height": "bad", "build": NAN}).is_equal_approx(Vector3.ONE), "malformed size has neutral defaults")
	var frame := {"eye_y": 0.077, "eye_z": 0.05, "scale": 1.0}
	var middle := Vector3(0.0, -0.018, 0.05)
	var left := FIT.face_point(middle + Vector3.LEFT * 0.00001, frame, Vector3.ONE)
	var right := FIT.face_point(middle + Vector3.RIGHT * 0.00001, frame, Vector3.ONE)
	expect(left.distance_to(right) < 0.00003, "jaw field is continuous across centre seam")
	expect(FIT.face_point(Vector3(0, -0.1, 0.05), frame, Vector3.ONE) == Vector3(0, -0.1, 0.05), "neck seam remains exact")
	expect(FIT.face_point(Vector3(0, 0.1, 0.05), frame, Vector3.ONE) == Vector3(0, 0.1, 0.05), "eyelids and scalp remain exact")
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for slug: String in ["luminous_male", "luminous_female", "orun_male"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		var errors := actor.configure({"actor_id": 9800, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[slug], animations, equipment)
		expect(errors.is_empty(), slug + " configures: " + str(errors))
		if not errors.is_empty():
			actor.free()
			continue
		actor.set_process(false)
		actor.set_physics_process(false)
		var native := actor.get_node("NativeModel") as Node3D
		var body := native.find_child("body", true, false) as MeshInstance3D
		var source := body.mesh
		var original_vertices: PackedVector3Array = source.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var rig := actor.get_skeleton()
		var rest: Array[Transform3D] = []
		for bone: int in range(rig.get_bone_count()):
			rest.append(rig.get_bone_rest(bone))
		var collision := actor.get_node("SelectionCollision") as CollisionShape3D
		var shape := collision.shape as CapsuleShape3D
		var picking := Vector2(shape.radius, shape.height)
		var base_height := actor.head_height()
		var base_scale := native.scale
		var human := slug.begins_with("luminous_")
		for class_index: int in range(4 if human else 1):
			var loadout := CreationArchetypes.loadout_at(class_index)
			actor.apply_equipment_visuals(loadout)
			await process_frame
			var resources := equipment_resources(actor)
			for choice: int in [0, 100]:
				var appearance := {"height": choice, "build": 100 - choice,
					"jaw": choice, "cheekbones": 100 - choice, "nose": choice}
				actor.apply_appearance_variants(appearance)
				var expected := FIT.visual_scale(appearance) if human else Vector3.ONE
				expect(native.scale.is_equal_approx(expected * base_scale), "%s class %s uses bounded complete visual scale" % [slug, class_index])
				expect(actor.footprint == Vector2i.ONE and actor.position.is_equal_approx(actor.server_target), slug + " retains authoritative placement and footprint")
				expect(Vector2(shape.radius, shape.height) == picking, slug + " retains picking geometry")
				expect(is_equal_approx(actor.head_height(), base_height * expected.y), slug + " overhead height follows visible body")
				expect(actor.equipment_diagnostics().fallback == 0, slug + " uses shipped gear without fallback")
				var after := equipment_resources(actor)
				expect(after.keys() == resources.keys(), slug + " keeps the same equipped mesh nodes")
				for key: String in resources:
					expect(after[key] == resources[key], slug + " shares original equipment mesh, skin and local fit: " + key)
				for bone: int in range(rest.size()):
					expect(rig.get_bone_rest(bone) == rest[bone], slug + " authored bone rest remains exact")
				expect(source.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == original_vertices, slug + " imported body resource stays immutable")
				for surface: int in range(body.mesh.get_surface_count()):
					var arrays := body.mesh.surface_get_arrays(surface)
					var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
					var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
					for index: int in range(vertices.size()):
						if not vertices[index].is_finite() or not normals[index].is_finite():
							expect(false, slug + " finite sculpted vertices and normals")
							break
				if human:
					var fitted := body.mesh
					actor.position += Vector3(10000, 0, 20000)
					actor.apply_appearance_variants(appearance)
					expect(body.mesh == fitted, slug + " shares the same sculpt cache away from the world origin")
					actor.position = actor.server_target
				actor.play_action(&"walk", true)
				actor.animation_player.seek(0.3, true)
				actor.animation_player.pause()
				await process_frame
			actor.apply_appearance_variants({})
		actor.apply_equipment_visuals({})
		await process_frame
		expect(body.mesh == source, slug + " removing gear and resetting sliders restores exact original mesh")
		actor.free()
	FIT.clear()
	print("Character proportions: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
