extends SceneTree
## Complete production Human bodies and every starter outfit share one
## source-preserving rest-space deformation, including quiver morph targets.
const FIT := preload("res://src/actors/character_proportions.gd")
var checks := 0
var failures := 0
var maximum_error := 0.0
var maximum_displacement := 0.0
var summaries: Array = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func rest_point(arrays: Array, index: int, binding: Dictionary) -> Vector3:
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
	var stride := bones.size() / vertices.size()
	var point := Vector3.ZERO
	for slot: int in range(stride):
		var at := index * stride + slot
		point += (binding.rests[bones[at]] as Transform3D) * vertices[index] * weights[at]
	return binding.to_rig * point

func validate_mesh(instance: MeshInstance3D, skeleton: Skeleton3D, native: Node3D, frame: Dictionary) -> Dictionary:
	var source := instance.get_meta(FIT.BODY_SOURCE_META) as Mesh
	var fitted := instance.mesh
	var binding := FIT.body_binding(instance.skin, skeleton, FIT._to_root(skeleton, native).affine_inverse() * FIT._to_root(instance, native))
	expect(fitted.get_surface_count() == source.get_surface_count(), str(instance.name) + " retains surfaces")
	expect(fitted.get_blend_shape_count() == source.get_blend_shape_count(), str(instance.name) + " retains morph count")
	var vertices_total := 0
	var triangles := 0
	for surface: int in range(source.get_surface_count()):
		var original := source.surface_get_arrays(surface)
		var original_bytes := var_to_bytes(original)
		var expected := original.duplicate(true)
		var shapes := source.surface_get_blend_shape_arrays(surface)
		FIT.compact(expected, shapes, FIT.LODS._surface_lods(source, surface))
		var actual := fitted.surface_get_arrays(surface)
		var points: PackedVector3Array = expected[Mesh.ARRAY_VERTEX]
		expect(actual[Mesh.ARRAY_VERTEX].size() == points.size(), str(instance.name) + " adds no vertices")
		expect(actual[Mesh.ARRAY_INDEX] == expected[Mesh.ARRAY_INDEX], str(instance.name) + " preserves topology")
		expect(actual[Mesh.ARRAY_BONES] == expected[Mesh.ARRAY_BONES], str(instance.name) + " preserves joint ownership")
		var weight_error := 0.0
		var attribute_ok := true
		var geometry_ok := true
		for index: int in range(points.size()):
			var before := rest_point(expected, index, binding)
			var after := rest_point(actual, index, binding)
			var wanted := FIT.body_point(before, frame)
			maximum_error = maxf(maximum_error, after.distance_to(wanted))
			maximum_displacement = maxf(maximum_displacement, after.distance_to(before))
			if after.distance_to(wanted) > 0.00002:
				geometry_ok = false
			if not (actual[Mesh.ARRAY_NORMAL][index] as Vector3).is_finite() or not after.is_finite():
				geometry_ok = false
			if actual[Mesh.ARRAY_TEX_UV] != null and expected[Mesh.ARRAY_TEX_UV] != null and (actual[Mesh.ARRAY_TEX_UV][index] as Vector2).distance_to(expected[Mesh.ARRAY_TEX_UV][index]) > 0.00001:
				attribute_ok = false
		for index: int in range(actual[Mesh.ARRAY_WEIGHTS].size()):
			weight_error = maxf(weight_error, absf(actual[Mesh.ARRAY_WEIGHTS][index] - expected[Mesh.ARRAY_WEIGHTS][index]))
		var fitted_shapes := fitted.surface_get_blend_shape_arrays(surface)
		for shape_index: int in range(shapes.size()):
			var expected_shape := expected.duplicate(true)
			var actual_shape := actual.duplicate(true)
			var from_shape: PackedVector3Array = shapes[shape_index][Mesh.ARRAY_VERTEX]
			var to_shape: PackedVector3Array = fitted_shapes[shape_index][Mesh.ARRAY_VERTEX]
			if fitted is ArrayMesh and (fitted as ArrayMesh).blend_shape_mode == Mesh.BLEND_SHAPE_MODE_RELATIVE:
				for index: int in range(from_shape.size()):
					from_shape[index] += expected[Mesh.ARRAY_VERTEX][index]
					to_shape[index] += actual[Mesh.ARRAY_VERTEX][index]
			expected_shape[Mesh.ARRAY_VERTEX] = from_shape
			actual_shape[Mesh.ARRAY_VERTEX] = to_shape
			var morph_ok := true
			for index: int in range(from_shape.size()):
				var before := rest_point(expected_shape, index, binding)
				var after := rest_point(actual_shape, index, binding)
				var error := after.distance_to(FIT.body_point(before, frame))
				maximum_error = maxf(maximum_error, error)
				if error > 0.00002 or not after.is_finite():
					morph_ok = false
			expect(morph_ok, str(instance.name) + " morph target follows the same rest-space field")
		expect(geometry_ok, str(instance.name) + " follows the shared wearer-rest field")
		expect(attribute_ok and weight_error < 0.0001, str(instance.name) + " retains UVs and normalized influences")
		expect(var_to_bytes(source.surface_get_arrays(surface)) == original_bytes, str(instance.name) + " authored mesh remains immutable")
		vertices_total += points.size()
		triangles += actual[Mesh.ARRAY_INDEX].size() / 3
	return {"mesh": str(instance.name), "vertices": vertices_total, "triangles": triangles, "morphs": fitted.get_blend_shape_count()}

func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	for sex: String in ["male", "female"]:
		var slug := "luminous_" + sex
		var actor := ReplicatedActor3D.new()
		root.add_child(actor)
		actor.apply_render_quality(1, true)
		var errors := actor.configure({"actor_id": 9803, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "", "appearance": {}, "equipment_visuals": {}}, CoordinateAdapter.new(), models[slug], animations, equipment)
		expect(errors.is_empty(), slug + " loads for body refinement " + str(errors))
		if not errors.is_empty():
			actor.free()
			continue
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.apply_render_quality(1, true)
		var native := actor.get_node("NativeModel") as Node3D
		var skeleton := actor.get_skeleton()
		var frame := FIT.body_frame(skeleton, sex)
		for bone: int in range(skeleton.get_bone_count()):
			var point := skeleton.get_bone_global_rest(bone).origin
			expect(FIT.body_point(point, frame) == point, slug + " preserves joint anchor " + str(skeleton.get_bone_name(bone)))
		for point: Vector3 in [Vector3(0.04, 1.50, 0.05), Vector3(-0.05, 1.65, 0.04), Vector3(0.1, 0.1, 0.0)]:
			expect(FIT.body_point(point, frame) == point, slug + " head, neck and floor stay exact")
		var face_frame := FIT.face_frame(native, skeleton)
		var head := skeleton.get_bone_global_rest(skeleton.find_bone("Head"))
		var body := native.find_child("body", true, false) as MeshInstance3D
		var body_arrays := body.mesh.surface_get_arrays(0)
		var commute_error := 0.0
		for point: Vector3 in body_arrays[Mesh.ARRAY_VERTEX]:
			if point.y < 1.46:
				continue
			var face_first := head * FIT.face_point(head.affine_inverse() * point, face_frame, Vector3(0.6, 0.5, -0.3))
			var body_first := head * FIT.face_point(head.affine_inverse() * FIT.body_point(point, frame), face_frame, Vector3(0.6, 0.5, -0.3))
			commute_error = maxf(commute_error, FIT.body_point(face_first, frame).distance_to(body_first))
		expect(commute_error < 0.000001, slug + " body and facial sculpt commute on real head geometry")
		var outfits: Array[Dictionary] = [{}]
		for class_index: int in range(4):
			outfits.append(CreationArchetypes.loadout_at(class_index))
		var ranger_with_cape := CreationArchetypes.loadout_at(1).duplicate()
		ranger_with_cape[2] = 105
		outfits.append(ranger_with_cape)
		for outfit: Dictionary in outfits:
			actor.apply_equipment_visuals(outfit)
			actor.apply_render_quality(1, true)
			FIT.apply_body_refinement(native, skeleton, models[slug])
			var meshes := {}
			var altered := 0
			for node: Node in native.find_children("*", "MeshInstance3D", true, false):
				var instance := node as MeshInstance3D
				if instance.has_meta(FIT.BODY_RESULT_META):
					altered += 1
					summaries.append(validate_mesh(instance, skeleton, native, frame))
					for shape_index: int in range(instance.mesh.get_blend_shape_count()):
						if instance.mesh.get_blend_shape_name(shape_index) == &"Cape_Clearance":
							expect(is_equal_approx(instance.get_blend_shape_value(shape_index), 1.0 if outfit.has(2) else 0.0), slug + " quiver cape clearance survives refinement")
					meshes[instance] = instance.mesh
			expect(altered > 0, slug + " refines native body and worn surfaces")
			FIT.apply_body_refinement(native, skeleton, models[slug])
			for instance: MeshInstance3D in meshes:
				expect(instance.mesh == meshes[instance], slug + " repeated body fit is idempotent")
			for value: int in [0, 100]:
				actor.apply_appearance_variants({"height": value, "build": value})
				for action: StringName in [&"idle", &"walk", &"run"]:
					actor.play_action(action, true)
					actor.animation_player.seek(0.30, true)
					actor.animation_player.pause()
					skeleton.force_update_all_bone_transforms()
					expect(skeleton.get_bone_global_pose(skeleton.find_bone("hand_l")).is_finite(), slug + " finite pose after size/outfit transition")
			actor.apply_appearance_variants({})
			await process_frame
		actor.free()
	expect(maximum_error < 0.00002, "all skinned parts share the final wearer-rest field")
	expect(maximum_displacement < 0.012, "body refinement stays within twelve millimetres")
	print("Human body refinement: %d checks, %d failures; maximum fit error %.8f m; maximum displacement %.6f m" % [checks, failures, maximum_error, maximum_displacement])
	var output := OS.get_environment("RL_BODY_METRICS")
	if not output.is_empty():
		FileAccess.open(output, FileAccess.WRITE).store_string(JSON.stringify({"checks": checks, "failures": failures, "maximum_fit_error_m": maximum_error, "maximum_displacement_m": maximum_displacement, "cache": FIT.body_cache_metrics(), "meshes": summaries}, "  "))
	print("BODY_CACHE ", FIT.body_cache_metrics())
	quit(1 if failures else 0)
