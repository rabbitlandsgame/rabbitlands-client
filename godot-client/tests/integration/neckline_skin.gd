extends "res://tests/integration/gear_fit_sweep.gd"
## Exercise the real torso attachment, appearance refresh and unequip paths.

func same_weights(a: Array, ai: int, b: Array, bi: int) -> bool:
	var aw: PackedFloat32Array = a[Mesh.ARRAY_WEIGHTS]
	var aj: PackedInt32Array = a[Mesh.ARRAY_BONES]
	var bw: PackedFloat32Array = b[Mesh.ARRAY_WEIGHTS]
	var bj: PackedInt32Array = b[Mesh.ARRAY_BONES]
	var astride: int = aj.size() / (a[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var bstride: int = bj.size() / (b[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var delta := {}
	for slot: int in range(astride):
		var joint := aj[ai * astride + slot]
		delta[joint] = float(delta.get(joint, 0.)) + aw[ai * astride + slot]
	for slot: int in range(bstride):
		var joint := bj[bi * bstride + slot]
		delta[joint] = float(delta.get(joint, 0.)) - bw[bi * bstride + slot]
	for value: float in delta.values():
		# Godot stores skin weights in 16-bit normalized integers. A second
		# ArrayMesh encoding can differ by one integer at the same seam.
		if absf(value) > 2. / 65535.:
			return false
	return true

func check_rim(lining: MeshInstance3D, original: Mesh, label: String) -> void:
	var surfaces: Array = lining.get_meta("neck_surfaces")
	var count := 0
	for index: int in range(lining.mesh.get_surface_count()):
		var source := original.surface_get_arrays(int(surfaces[index]))
		var a := lining.mesh.surface_get_arrays(index)
		var points: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
		var original_points: PackedVector3Array = source[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = a[Mesh.ARRAY_NORMAL]
		var original_normals: PackedVector3Array = source[Mesh.ARRAY_NORMAL]
		var uvs: PackedVector2Array = a[Mesh.ARRAY_TEX_UV]
		var original_uvs: PackedVector2Array = source[Mesh.ARRAY_TEX_UV]
		var lookup := {}
		for v: int in range(original_points.size()):
			var p := original_points[v]
			if NecklineSkin.is_neck_rim(p):
				var key := Vector3i(roundi(p.x * 100000), roundi(p.y * 100000), roundi(p.z * 100000))
				if not lookup.has(key):
					lookup[key] = []
				lookup[key].append(v)
		for first: int in range(0, points.size(), (NecklineSkin.STEPS + 1) * 2):
			for column: int in range(2):
				var v := first + column
				var p := points[v]
				var key := Vector3i(roundi(p.x * 100000), roundi(p.y * 100000), roundi(p.z * 100000))
				var matched := false
				for source_v: int in lookup.get(key, []):
					if p.distance_to(original_points[source_v]) < .000001 and uvs[v].distance_to(original_uvs[source_v]) < .0001 and normals[v].distance_to(original_normals[source_v]) < .0001 and same_weights(a, v, source, source_v):
						matched = true
						break
				expect(matched, label + " joins original positions, normals, UVs and skin weights")
				if source[Mesh.ARRAY_TANGENT] is PackedFloat32Array:
					var original_tangents: PackedFloat32Array = source[Mesh.ARRAY_TANGENT]
					if not original_tangents.is_empty():
						expect(a[Mesh.ARRAY_TANGENT] is PackedFloat32Array and (a[Mesh.ARRAY_TANGENT] as PackedFloat32Array).size() == points.size() * 4, label + " retains the skin's normal-map frame")
				count += 1
				var bottom := points[first + NecklineSkin.STEPS * 2 + column]
				expect(bottom.y <= 1.405 and bottom.y <= p.y, label + " reaches beneath the fitted collar")
	expect(count > 20, label + " continues the complete neck opening")

func run() -> void:
	stage = Node3D.new()
	root.add_child(stage)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var tested_sexes := {}
	for slug: String in models:
		if not models[slug].has("bodyTemplate"):
			continue
		var actor := make_actor(slug, models[slug], animations, equipment)
		var body := actor.get_node("NativeModel").find_child("body", true, false) as MeshInstance3D
		var original := body.mesh
		for class_index: int in range(CreationArchetypes.count()):
			var label := slug + " " + str(CreationArchetypes.at(class_index)["label"])
			actor.apply_equipment_visuals(CreationArchetypes.loadout_at(class_index))
			await process_frame
			var linings := []
			for node: Node in actor._equipment_nodes.get(5, []):
				if node.has_meta("neck_source"):
					linings.append(node)
			expect(linings.size() == 1, label + " has exactly one native neck continuation")
			if linings.size() != 1:
				continue
			var lining := linings[0] as MeshInstance3D
			expect(lining.skin == body.skin and lining.get_node(lining.skeleton) == actor.get_skeleton(), label + " shares the moving body skin")
			expect(lining.transform.is_equal_approx(actor.get_skeleton().global_transform.affine_inverse() * body.global_transform), label + " shares the body frame")
			expect(body.get_meta("uncovered_body_mesh") == original, label + " preserves imported head geometry")
			var sex := slug.get_slice("_", 1)
			if not tested_sexes.has(sex):
				check_rim(lining, original, label)
				tested_sexes[sex] = true
			for clip: String in ["Idle_Subtle", "Walk", "Fighting_Idle"]:
				actor.animation_player.play(clip)
				actor.animation_player.seek(.3, true)
				actor.animation_player.pause()
				expect(lining.skin == body.skin, label + " retains native skin in " + clip)
			actor.apply_appearance_variants({"skin": 2, "hair": 1, "eyes": 3})
			var surfaces: Array = lining.get_meta("neck_surfaces")
			for surface: int in range(surfaces.size()):
				expect(lining.get_active_material(surface) == body.get_active_material(int(surfaces[surface])), label + " follows the selected skin material")
		actor.apply_equipment_visuals({})
		await process_frame
		expect(body.mesh == original, slug + " restores the exact source body on unequip")
		var stale := 0
		for node: Node in actor.get_skeleton().get_children():
			if node.has_meta("neck_source"):
				stale += 1
		expect(stale == 0, slug + " removes the collar lining on unequip")
		actor.free()
		await process_frame
	NativeAnimationImporter.clear()
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	print("NECKLINE SKIN: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)
