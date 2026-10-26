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

	var creature := ReplicatedActor3D.new()
	creature.server_scale = 2.0
	creature._presentation_speed = 2.0
	for scales: bool in [false, true]:
		creature.resolver = AnimationResolver.new({"actions": {"walk": "Walk"}, "strideMetresPerSecond": {"walk": 1.0}, "strideScalesWithActor": scales})
		expect(is_equal_approx(creature._playback_speed_for(&"walk"), 1.0 if scales else 2.0), "creature stride scale remains profile-controlled")
	creature.free()
	for slug: String in ["luminous_male", "luminous_female", "orun_male"]:
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		# Sculpt/fit validation is independent of the optional High UV layer.
		actor.apply_render_quality(1, true)
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
		var original_normals: PackedVector3Array = source.surface_get_arrays(0)[Mesh.ARRAY_NORMAL]
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
		expect(actor._face_material != null and bool(actor._face_material.get_shader_parameter("natural_iris")) == human,
			slug + " natural eye pigment is scoped to Human bodies")

		if human:
			var original_speed := actor._presentation_speed
			for breadth: int in [0, 100]:
				actor.apply_appearance_variants({"build": breadth})
				var forward_scale := FIT.visual_scale({"build": breadth}).z
				for action: StringName in [&"walk", &"run"]:
					actor._presentation_speed = 1.6 if action == &"walk" else 4.8
					var expected_rate := actor._presentation_speed / (float(animations.strideMetresPerSecond[String(action)]) * forward_scale)
					expect(is_equal_approx(actor._playback_speed_for(action), expected_rate), slug + " " + str(action) + " follows real profile stride at build " + str(breadth))
			# A future Human profile can opt in to species scale too; breadth
			# must still enter exactly once rather than compounding in the resolver.
			actor.resolver.stride_scales_with_actor = true
			actor.server_scale = 2.0
			actor._presentation_speed = 1.6
			expect(is_equal_approx(actor._playback_speed_for(&"walk"), 1.6 / (float(animations.strideMetresPerSecond.walk) * 2.0 * 1.15)), slug + " body breadth scales stride once alongside optional species scale")
			actor.resolver.stride_scales_with_actor = false
			actor.server_scale = 1.0
			actor._presentation_speed = original_speed
			actor.apply_appearance_variants({})
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
				expect(source.surface_get_arrays(0)[Mesh.ARRAY_NORMAL] == original_normals, slug + " imported normal resource stays immutable")
				for surface: int in range(body.mesh.get_surface_count()):
					var arrays := body.mesh.surface_get_arrays(surface)
					var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
					var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
					for index: int in range(vertices.size()):
						if not vertices[index].is_finite() or not normals[index].is_finite():
							expect(false, slug + " finite sculpted vertices and normals")
							break

				if human and body.has_meta(FIT.SOURCE_META):
					var authored := body.get_meta(FIT.SOURCE_META) as Mesh
					var normal_frame := FIT.face_frame(native, rig)
					var to_head: Transform3D = normal_frame.to_head * FIT._to_root(rig, native).affine_inverse() * FIT._to_root(body, native)
					var untouched := true
					var maximum_pack_error := 0.0
					for surface: int in range(body.mesh.get_surface_count()):
						var before := authored.surface_get_arrays(surface)
						var after_arrays := body.mesh.surface_get_arrays(surface)
						var finish_control := after_arrays.duplicate(true)
						FIT._finish_face_normals(finish_control, to_head, normal_frame)
						var unique := {}
						for index: int in before[Mesh.ARRAY_INDEX]:
							unique[index] = true
						var order: Array = unique.keys()
						order.sort()
						if order.size() != after_arrays[Mesh.ARRAY_VERTEX].size():
							continue
						for index: int in range(order.size()):
							var original_index := int(order[index])
							var point: Vector3 = to_head * before[Mesh.ARRAY_VERTEX][original_index]
							if point.y < float(normal_frame.eye_y) - 0.17:
								if finish_control[Mesh.ARRAY_NORMAL][index] != after_arrays[Mesh.ARRAY_NORMAL][index]:
									untouched = false
								maximum_pack_error = maxf(maximum_pack_error, after_arrays[Mesh.ARRAY_NORMAL][index].distance_to(before[Mesh.ARRAY_NORMAL][original_index]))
					expect(untouched, slug + " normal finish leaves lower-body arrays exact")
					# ArrayMesh encodes normals octahedrally; an untouched normal can
					# round one quantization step when the custom mesh is published.
					expect(maximum_pack_error < 0.00015, slug + " lower-body normal publishing stays within encoding precision")
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
		# The bounded shared body cache can evict this neutral resource while
		# exercising all outfits. A rebuilt neutral mesh must still have exact
		# attribute data; resource identity alone is not a geometry regression.
		expect(body.mesh.get_surface_count() == source.get_surface_count(), slug + " reset restores neutral surface count")
		for surface: int in range(source.get_surface_count()):
			var neutral := source.surface_get_arrays(surface)
			var reset := body.mesh.surface_get_arrays(surface)
			for channel: int in range(Mesh.ARRAY_MAX):
				expect(neutral[channel] == reset[channel], slug + " reset restores exact neutral mesh channel " + str(channel))
		actor.free()
	FIT.clear()
	print("Character proportions: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)
