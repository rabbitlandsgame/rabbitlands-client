extends SceneTree
## Focused geometry/cache regression for the wardrobe-only class shirt fit.

const WardrobeShirtFitImpl := preload("res://src/actors/wardrobe_shirt_fit.gd")

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
	WardrobeShirtFitImpl.clear()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/actors/models.json"))
	var models: Dictionary = (parsed as Dictionary)["models"]
	var races := 0
	for slug_value: Variant in models:
		var slug := str(slug_value)
		var config: Dictionary = models[slug]
		if not config.has("bodyTemplate"):
			continue
		verify_race(slug, config)
		races += 1
	expect(races == 16, "all sixteen race shirts use the fit")
	print("wardrobe shirt fit: %d races, %d checks, %d failures" % [
		races, checks, failures])
	WardrobeShirtFitImpl.clear()
	quit(1 if failures else 0)


func verify_race(slug: String, config: Dictionary) -> void:
	var packed := load(str(config["scene"])) as PackedScene
	expect(packed != null, slug + " scene loads")
	if packed == null:
		return
	var model := packed.instantiate() as Node3D
	root.add_child(model)
	var parts := find_parts(model)
	var skeleton := parts[0] as Skeleton3D
	var shirt := parts[1] as MeshInstance3D
	expect(skeleton != null and shirt != null, slug + " exposes shirt and skeleton")
	if skeleton == null or shirt == null:
		model.free()
		return
	var original := shirt.mesh
	WardrobeShirtFitImpl.apply(shirt, skeleton)
	var fitted := shirt.mesh
	expect(fitted != original, slug + " builds a fitted mesh")
	verify_surfaces(slug, original, fitted, shirt.skin, skeleton)
	# A second call is a no-op; restore/reapply resolves the same cached resource.
	WardrobeShirtFitImpl.apply(shirt, skeleton)
	expect(shirt.mesh == fitted, slug + " repeated apply keeps the fitted resource")
	WardrobeShirtFitImpl.restore(shirt)
	expect(shirt.mesh == original, slug + " restores the exact authored resource")
	WardrobeShirtFitImpl.apply(shirt, skeleton)
	expect(shirt.mesh == fitted, slug + " reuses the cached fitted resource")
	# A distinct Skin object with identical ordered binds must hit the same cache
	# entry. Imported instances are allowed to duplicate Skin resources.
	var twin := packed.instantiate() as Node3D
	root.add_child(twin)
	var twin_parts := find_parts(twin)
	var twin_skeleton := twin_parts[0] as Skeleton3D
	var twin_shirt := twin_parts[1] as MeshInstance3D
	twin_shirt.skin = twin_shirt.skin.duplicate() as Skin
	expect(twin_shirt.skin.get_instance_id() != shirt.skin.get_instance_id(),
		slug + " cache probe uses a distinct Skin resource")
	WardrobeShirtFitImpl.apply(twin_shirt, twin_skeleton)
	expect(twin_shirt.mesh == fitted,
		slug + " ordered bind content shares the fitted cache")
	twin.free()
	model.free()


func find_parts(model: Node3D) -> Array:
	var skeleton: Skeleton3D = null
	var shirt: MeshInstance3D = null
	for node: Node in model.find_children("*", "Skeleton3D", true, false):
		skeleton = node as Skeleton3D
		break
	for node: Node in model.find_children("*", "MeshInstance3D", true, false):
		if node.name.to_lower() == "wardrobe_shirt":
			shirt = node as MeshInstance3D
			break
	return [skeleton, shirt]


func verify_surfaces(label: String, before: Mesh, after: Mesh, skin: Skin,
		skeleton: Skeleton3D) -> void:
	expect(after.get_surface_count() == before.get_surface_count(),
		label + " preserves surface count")
	var left_bind := bind_for(skin, skeleton, &"upperarm_l")
	var right_bind := bind_for(skin, skeleton, &"upperarm_r")
	var left_shoulder := skeleton.get_bone_global_rest(
		skeleton.find_bone(&"upperarm_l")).origin
	var right_shoulder := skeleton.get_bone_global_rest(
		skeleton.find_bone(&"upperarm_r")).origin
	var left_elbow := skeleton.get_bone_global_rest(
		skeleton.find_bone(&"lowerarm_l")).origin
	var right_elbow := skeleton.get_bone_global_rest(
		skeleton.find_bone(&"lowerarm_r")).origin
	var moved := 0
	var protected := 0
	var lod_levels := 0
	var maximum_fit_error := 0.0
	var maximum_preserved_error := 0.0
	var maximum_x_error := 0.0
	for surface: int in range(before.get_surface_count()):
		var old: Array = before.surface_get_arrays(surface)
		var new: Array = after.surface_get_arrays(surface)
		expect(before.surface_get_primitive_type(surface)
			== after.surface_get_primitive_type(surface),
			label + " preserves primitive type " + str(surface))
		expect(before.surface_get_material(surface) == after.surface_get_material(surface),
			label + " preserves material " + str(surface))
		for field: int in [Mesh.ARRAY_INDEX, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_BONES,
				Mesh.ARRAY_WEIGHTS, Mesh.ARRAY_COLOR]:
			expect(old[field] == new[field], label + " preserves array %d/%d" % [
				surface, field])
		var old_lods := surface_lods(before, surface)
		var new_lods := surface_lods(after, surface)
		expect(old_lods.keys() == new_lods.keys(),
			label + " preserves LOD distances " + str(surface))
		for distance: Variant in old_lods:
			expect(old_lods[distance] == new_lods[distance],
				label + " preserves LOD indices " + str(surface))
			lod_levels += 1
		var old_vertices: PackedVector3Array = old[Mesh.ARRAY_VERTEX]
		var new_vertices: PackedVector3Array = new[Mesh.ARRAY_VERTEX]
		var bones: PackedInt32Array = old[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = old[Mesh.ARRAY_WEIGHTS]
		var stride := bones.size() / maxi(old_vertices.size(), 1)
		for index: int in range(old_vertices.size()):
			var point := old_vertices[index]
			var left := 0.0
			var right := 0.0
			for slot: int in range(stride):
				var at := index * stride + slot
				if bones[at] == left_bind:
					left += weights[at]
				elif bones[at] == right_bind:
					right += weights[at]
			# Keep the sentinels written out here: changing the production masks
			# should make this test fail rather than changing its oracle with them.
			var preserve := absf(point.x) <= 0.10 or (point.y >= 1.38
				and absf(point.x) <= 0.20)
			var share := maxf(left, right)
			if preserve or share <= 0.0001:
				maximum_preserved_error = maxf(maximum_preserved_error,
					new_vertices[index].distance_to(point))
				protected += int(preserve)
				continue
			var shoulder := left_shoulder if left >= right else right_shoulder
			var elbow := left_elbow if left >= right else right_elbow
			var along := (point.x - shoulder.x) / (elbow.x - shoulder.x)
			var centre := shoulder.lerp(elbow, along)
			var scale := lerpf(1.0, 0.88, clampf(share, 0.0, 1.0))
			var expected := Vector3(point.x,
				centre.y + (point.y - centre.y) * scale,
				centre.z + (point.z - centre.z) * scale)
			maximum_fit_error = maxf(maximum_fit_error,
				new_vertices[index].distance_to(expected))
			maximum_x_error = maxf(maximum_x_error,
				absf(new_vertices[index].x - point.x))
			moved += int(new_vertices[index].distance_to(point) > 0.000001)
	expect(maximum_preserved_error < 0.000001,
		label + " preserves centre, collar and unweighted vertices")
	expect(maximum_fit_error < 0.00001,
		label + " contracts only the humerus radius")
	expect(maximum_x_error < 0.000001,
		label + " preserves shoulder span and sleeve length")
	expect(moved > 500, label + " contracts a substantive upper-arm region")
	expect(protected > 100, label + " retains collar and centre-front sentinels")
	expect(lod_levels > 0, label + " exercises generated mesh LODs")


func bind_for(skin: Skin, skeleton: Skeleton3D, wanted: StringName) -> int:
	for bind: int in range(skin.get_bind_count()):
		var name := skin.get_bind_name(bind)
		if name.is_empty():
			var bone := skin.get_bind_bone(bind)
			if bone >= 0 and bone < skeleton.get_bone_count():
				name = skeleton.get_bone_name(bone)
		if name == wanted:
			return bind
	return -1


func surface_lods(mesh: Mesh, surface: int) -> Dictionary:
	var raw: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
	var raw_lods: Variant = raw.get("lods", [])
	if raw_lods is not Array:
		return {}
	var width := 2 if int(raw.get("vertex_count", 0)) <= 65536 else 4
	var result: Dictionary = {}
	for lod_value: Variant in raw_lods as Array:
		if lod_value is not Dictionary:
			continue
		var lod := lod_value as Dictionary
		var distance := float(lod.get("edge_length", 0.0))
		var data: Variant = lod.get("index_data", PackedByteArray())
		if distance <= 0.0 or data is not PackedByteArray:
			continue
		var bytes := data as PackedByteArray
		if bytes.is_empty() or bytes.size() % width != 0:
			continue
		var indices := PackedInt32Array()
		indices.resize(bytes.size() / width)
		for index: int in range(indices.size()):
			var offset := index * width
			indices[index] = (bytes.decode_u16(offset) if width == 2
				else bytes.decode_u32(offset))
		result[distance] = indices
	return result
