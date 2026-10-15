extends SceneTree
## Focused LOD contract for runtime body coverage.
## Run with --headless --script res://tests/test_torso_body_cover_lods.gd.

const Policy := preload("res://src/actors/actor_render_quality.gd")
const RACE := "luminous_male"
const TORSO_VISUAL := 192
## A rebased female: its neck bridge carries the throat faces the throat rule
## keeps, under the Furtrim Coat's open front.
const BRIDGED_RACE := "greyhaven_female"
const OPEN_FRONT_TORSO := 189

var _checks := 0
var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_synthetic_lods()
	_check_protected_neck_outside_cover()
	_check_bridge_throat_rule()
	_check_u32_lod_indices()
	_check_cache_reset_and_rebuild()
	_check_imported_actor_lods_and_quality()
	_check_shipped_route_bridge()
	TorsoBodyCover.clear()
	GlbSceneCache.clear()
	print("torso body cover LODs: %s (%d checks)" % [
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


## The expected chains below are hand-authored. They deliberately do not call
## TorsoBodyCover.covers() or its filtering helpers, so a predicate regression
## cannot update both production and the oracle in lockstep.
func _check_synthetic_lods() -> void:
	var vertices := PackedVector3Array()
	var triangles: Array[PackedInt32Array] = []
	var centers: Array[Vector3] = [
		Vector3(-.20, 1.20, 0.0), # covered
		Vector3(0.0, 1.25, .20), # covered
		Vector3(.20, 1.30, -.20), # covered
		Vector3(0.0, .40, 0.0), # visible below the band
		Vector3(.90, 1.20, 0.0), # visible outside the band width
		Vector3(0.0, 1.80, 0.0), # visible above the band
		Vector3(-.90, 1.20, 0.0), # visible outside the band width
	]
	for center: Vector3 in centers:
		var first := vertices.size()
		vertices.append_array(PackedVector3Array([
			center + Vector3(-.03, -.02, 0.0),
			center + Vector3(.03, -.02, 0.0),
			center + Vector3(0.0, .04, 0.0),
		]))
		triangles.append(PackedInt32Array([first, first + 1, first + 2]))

	var base := _join_indices(triangles)
	var expected_base := _join_indices([
		triangles[3], triangles[4], triangles[5], triangles[6]])
	var expected_near := _join_indices([triangles[3], triangles[4]])
	var expected_far := triangles[5]
	var lods: Dictionary = {
		1.0: _join_indices([triangles[0], triangles[3], triangles[4]]),
		2.0: _join_indices([triangles[1], triangles[5]]),
		# Filtering leaves no indices, so this level must be omitted.
		3.0: _join_indices([triangles[0], triangles[1]]),
		# Filtering leaves the complete base chain, so this non-reducing level
		# must also be omitted rather than silently rejected by Godot.
		4.0: _join_indices([
			triangles[2], triangles[3], triangles[4], triangles[5], triangles[6]]),
	}
	var source := _mesh(vertices, base, lods)
	_expect(_lod_indices(source, 0).size() == 4,
		"the synthetic fixture starts with four imported-style LOD levels")
	var covered := TorsoBodyCover.cut(source, Transform3D.IDENTITY, 1.0)
	var actual_base: PackedInt32Array = covered.surface_get_arrays(0)[Mesh.ARRAY_INDEX]
	var actual_lods := _lod_indices(covered, 0)
	_expect(actual_base == expected_base,
		"the synthetic base chain removes only the three hand-authored covered faces")
	_expect(actual_lods.size() == 2 and actual_lods.has(1.0)
		and actual_lods.has(2.0) and not actual_lods.has(3.0)
		and not actual_lods.has(4.0),
		"empty and non-reducing filtered LOD levels are omitted")
	_expect(actual_lods.get(1.0, PackedInt32Array()) == expected_near,
		"the near LOD independently removes its covered face")
	_expect(actual_lods.get(2.0, PackedInt32Array()) == expected_far,
		"the far LOD independently removes its covered face")


## A protected bind activates the shaped-neck path, but that path must remain
## bounded by the active garment coverage. Low-head-weight face and LOD indices
## above the garment cannot be consumed merely because they are neck-width.
func _check_protected_neck_outside_cover() -> void:
	var vertices := PackedVector3Array()
	var triangles: Array[PackedInt32Array] = []
	for center: Vector3 in [
		Vector3(0.0, 1.50, 0.0), # covered collar face
		Vector3(.30, .40, 0.0), # uncovered control face
		Vector3(0.0, 1.80, 0.0), # neck-width but above the cover band
	]:
		var first := vertices.size()
		vertices.append_array(PackedVector3Array([
			center + Vector3(-.03, -.02, 0.0),
			center + Vector3(.03, -.02, 0.0),
			center + Vector3(0.0, .04, 0.0),
		]))
		triangles.append(PackedInt32Array([first, first + 1, first + 2]))
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	for vertex: int in range(vertices.size()):
		bones.append_array(PackedInt32Array([7, 0, 0, 0]))
		weights.append_array(PackedFloat32Array([.25, .75, 0.0, 0.0]))
	var expected := _join_indices([triangles[1], triangles[2]])
	var expected_lod := triangles[2]
	var source := _mesh(vertices, _join_indices(triangles), {
		1.0: _join_indices([triangles[0], triangles[2]]),
	}, bones, weights)
	var covered := TorsoBodyCover.cut(source, Transform3D.IDENTITY, 1.0, [],
		false, PackedInt32Array([7]))
	_expect(covered.surface_get_arrays(0)[Mesh.ARRAY_INDEX] == expected,
		"protected-bind coverage retains a neck-width face above the active band")
	_expect(_lod_indices(covered, 0).get(1.0, PackedInt32Array()) == expected_lod,
		"protected-bind LOD coverage retains a neck-width face above the active band")


## Under armour a "Shared neck bridge" face in front of the canonical neck_01
## (0, 1.452, -.051) -> Head (0, 1.568, .011) axis stays while every corner
## keeps more than a quarter of its Head/neck_01 weight. Behind the axis, on a
## surface that is not bridge, and on the wardrobe-only neckline the whole-face
## .5 test applies. No rebuilt bridge has a weak face behind the axis, so the
## real bodies cannot tell the axis split apart; these hand-weighted faces can.
func _check_bridge_throat_rule() -> void:
	var front := Vector3(0.0, 1.50, .05) # the axis is at depth -.025 at 1.50 m
	var behind := Vector3(0.0, 1.50, -.09)
	var bridge := _weighted_surface([[front, .30], [behind, .30], [front, .20],
		[behind, .80]])
	var body := _weighted_surface([[front, .30], [front, .80]])
	var source := ArrayMesh.new()
	for surface: Array in [bridge, body]:
		source.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, surface)
	for index: int in range(2):
		var material := StandardMaterial3D.new()
		material.resource_name = (TorsoBodyCover.BRIDGE_MATERIAL if index == 0
			else "Race body skin")
		source.surface_set_material(index, material)
	var armour := TorsoBodyCover.cut(source, Transform3D.IDENTITY, 1.0, [],
		false, PackedInt32Array([7]))
	_expect(armour.surface_get_arrays(0)[Mesh.ARRAY_INDEX]
		== PackedInt32Array([0, 1, 2, 9, 10, 11]),
		"under armour the bridge keeps its front .30 and behind .80 faces and "
		+ "drops its behind .30 and front .20 faces")
	_expect(armour.surface_get_arrays(1)[Mesh.ARRAY_INDEX]
		== PackedInt32Array([3, 4, 5]),
		"under armour a front .30 face off the bridge takes the whole-face test")
	var wardrobe := TorsoBodyCover.cut(source, Transform3D.IDENTITY, 1.0, [],
		false, PackedInt32Array([7]), true)
	_expect(wardrobe.surface_get_arrays(0)[Mesh.ARRAY_INDEX]
		== PackedInt32Array([9, 10, 11]),
		"the wardrobe-only neckline keeps no bridge face below .5 Head/neck_01")


## One surface of separate triangles, [centre, Head/neck_01 weight] each: every
## corner binds that weight to bind 7 (the protected one) and the rest to bind 0.
func _weighted_surface(faces: Array) -> Array:
	var vertices := PackedVector3Array()
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	for face: Array in faces:
		var center: Vector3 = face[0]
		vertices.append_array(PackedVector3Array([
			center + Vector3(-.03, -.02, 0.0),
			center + Vector3(.03, -.02, 0.0),
			center + Vector3(0.0, .04, 0.0),
		]))
		for corner: int in range(3):
			bones.append_array(PackedInt32Array([7, 0, 0, 0]))
			weights.append_array(PackedFloat32Array([face[1], 1.0 - face[1], 0.0, 0.0]))
	var indices := PackedInt32Array()
	for index: int in range(vertices.size()):
		indices.append(index)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	arrays[Mesh.ARRAY_BONES] = bones
	arrays[Mesh.ARRAY_WEIGHTS] = weights
	return arrays


## Godot stores generated LOD indices as u32 once a surface has more than
## 65,536 vertices. Keep one high index in a tiny two-triangle chain so the
## production decoder's wide-index branch is exercised without a huge draw.
func _check_u32_lod_indices() -> void:
	var vertices := PackedVector3Array()
	vertices.resize(65537)
	vertices[0] = Vector3(-.1, .2, 0.0)
	vertices[1] = Vector3(.1, .2, 0.0)
	vertices[65536] = Vector3(0.0, .3, 0.0)
	vertices[2] = Vector3(-.1, .4, 0.0)
	vertices[3] = Vector3(.1, .4, 0.0)
	vertices[4] = Vector3(0.0, .5, 0.0)
	var high_triangle := PackedInt32Array([0, 1, 65536])
	var source := _mesh(vertices,
		_join_indices([high_triangle, PackedInt32Array([2, 3, 4])]),
		{1.0: high_triangle})
	var raw: Dictionary = RenderingServer.mesh_get_surface(source.get_rid(), 0)
	var raw_lods: Array = raw.get("lods", []) as Array
	_expect(int(raw.get("vertex_count", 0)) == 65537 and not raw_lods.is_empty()
		and ((raw_lods[0] as Dictionary).get("index_data") as PackedByteArray).size() == 12,
		"the wide fixture is encoded as three u32 LOD indices")
	var covered := TorsoBodyCover.cut(source, Transform3D.IDENTITY, 1.0)
	_expect(_lod_indices(covered, 0).get(1.0, PackedInt32Array()) == high_triangle,
		"the u32 LOD decoder preserves an index above 65,535")


func _check_cache_reset_and_rebuild() -> void:
	TorsoBodyCover.clear()
	var source := _mesh(PackedVector3Array([
		Vector3(-.05, 1.20, 0.0), Vector3(.05, 1.20, 0.0),
		Vector3(0.0, 1.30, 0.0),
	]), PackedInt32Array([0, 1, 2]), {})
	var first := MeshInstance3D.new()
	first.mesh = source
	TorsoBodyCover.apply(first, true, Transform3D.IDENTITY, 1.0)
	var before_clear := first.mesh
	var shared := MeshInstance3D.new()
	shared.mesh = source
	TorsoBodyCover.apply(shared, true, Transform3D.IDENTITY, 1.0)
	_expect(is_same(shared.mesh, before_clear),
		"equivalent meshes share one torso-cover cache entry")

	TorsoBodyCover.clear()
	var rebuilt := MeshInstance3D.new()
	rebuilt.mesh = source
	TorsoBodyCover.apply(rebuilt, true, Transform3D.IDENTITY, 1.0)
	var after_clear := rebuilt.mesh
	var reshared := MeshInstance3D.new()
	reshared.mesh = source
	TorsoBodyCover.apply(reshared, true, Transform3D.IDENTITY, 1.0)
	_expect(not is_same(after_clear, before_clear)
		and is_same(reshared.mesh, after_clear),
		"session teardown releases and lazily rebuilds the shared torso-cover cache")
	first.free()
	shared.free()
	rebuilt.free()
	reshared.free()
	TorsoBodyCover.clear()


func _check_imported_actor_lods_and_quality() -> void:
	var models: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var config: Dictionary = models[RACE]
	var animations: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(config["animationMap"]))
	var first := _actor(6101, config, animations, equipment)
	if first == null:
		return
	var first_before := _coverable_meshes(first)
	var originals: Dictionary = {}
	var original_lods := 0
	for path: String in first_before:
		var mesh := first_before[path] as MeshInstance3D
		originals[path] = mesh.mesh
		original_lods += _mesh_lod_count(mesh.mesh)
	first.apply_equipment_visuals({5: TORSO_VISUAL})
	var first_after := _coverable_meshes(first)
	var covered_lods := 0
	var covered_count := 0
	var quality_mesh: MeshInstance3D = null
	var quality_path := ""
	for path: String in first_after:
		var mesh := first_after[path] as MeshInstance3D
		if not originals.has(path) or is_same(mesh.mesh, originals[path] as Mesh):
			continue
		covered_count += 1
		var count := _mesh_lod_count(mesh.mesh)
		covered_lods += count
		if quality_mesh == null and count > 0:
			quality_mesh = mesh
			quality_path = path
	_expect(covered_count > 0,
		"equipping a real fitted torso replaces imported body/wardrobe meshes")
	_expect(original_lods > 0 and covered_lods > 0,
		"real equipped body coverage retains imported LOD chains")
	if quality_mesh != null:
		var covered_resource := quality_mesh.mesh
		var lod_snapshot := _mesh_lod_snapshot(covered_resource)
		var high_bias := quality_mesh.lod_bias
		var high_shadow := quality_mesh.cast_shadow
		first.apply_render_quality(Policy.Quality.LOW)
		_expect(is_same(quality_mesh.mesh, covered_resource)
			and _mesh_lod_snapshot(quality_mesh.mesh) == lod_snapshot
			and is_equal_approx(quality_mesh.lod_bias,
				high_bias * Policy.lod_bias_scale(Policy.Quality.LOW))
			and quality_mesh.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
			"LOW changes render policy without replacing or rebuilding covered LODs")
		first.apply_render_quality(Policy.Quality.MEDIUM)
		_expect(is_same(quality_mesh.mesh, covered_resource)
			and _mesh_lod_snapshot(quality_mesh.mesh) == lod_snapshot
			and is_equal_approx(quality_mesh.lod_bias,
				high_bias * Policy.lod_bias_scale(Policy.Quality.MEDIUM))
			and quality_mesh.cast_shadow == high_shadow,
			"MEDIUM reuses the same covered LOD resource")
		first.apply_render_quality(Policy.Quality.HIGH)
		_expect(is_same(quality_mesh.mesh, covered_resource)
			and _mesh_lod_snapshot(quality_mesh.mesh) == lod_snapshot
			and is_equal_approx(quality_mesh.lod_bias, high_bias)
			and quality_mesh.cast_shadow == high_shadow,
			"HIGH restores authored policy on the same covered LOD resource")

	var second := _actor(6102, config, animations, equipment)
	if second != null:
		second.apply_equipment_visuals({5: TORSO_VISUAL})
		var second_after := _coverable_meshes(second)
		var second_quality := second_after.get(quality_path) as MeshInstance3D
		_expect(quality_mesh != null and second_quality != null
			and is_same(second_quality.mesh, quality_mesh.mesh),
			"equivalent actors share the quality-independent covered LOD cache entry")

	first.apply_equipment_visuals({})
	var restored := _coverable_meshes(first)
	for path: String in originals:
		var mesh := restored.get(path) as MeshInstance3D
		_expect(mesh != null and is_same(mesh.mesh, originals[path] as Mesh),
			"unequip restores the exact imported resource at " + path)
	if second != null:
		second.apply_equipment_visuals({})
		second.free()
	first.free()


## An exported client has no resource path, so GlbSceneCache parses each loose
## actor GLB with GLTFDocument (_build_raw) instead of loading the imported
## scene. The throat rule finds a race's neck bridge by its material name, so
## that name must survive the raw parse: build a rebased female both ways and
## require both to keep every bridge face under an open-front collar (the
## throat faces with a corner below .5 included) and to cut the body alike.
func _check_shipped_route_bridge() -> void:
	GlbSceneCache.clear()
	TorsoBodyCover.clear()
	var models: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var equipment: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var config: Dictionary = models[BRIDGED_RACE]
	var animations: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(config["animationMap"]))
	var imported := _bridge_cut(_actor(6301, config, animations, equipment,
		BRIDGED_RACE))
	# install_prepared never replaces a cached scene: drop the imported one.
	GlbSceneCache.clear()
	TorsoBodyCover.clear()
	var scene_path := ProjectSettings.globalize_path(str(config["scene"]))
	var parsed := GlbSceneCache._build_raw(scene_path)
	_expect(parsed != null, "the loose %s GLB parses through GLTFDocument" % BRIDGED_RACE)
	if parsed == null:
		return
	GlbSceneCache.install_prepared({scene_path: parsed})
	var shipped := _bridge_cut(_actor(6302, config, animations, equipment,
		BRIDGED_RACE))
	GlbSceneCache.clear()
	TorsoBodyCover.clear()
	for route: String in ["imported", "shipped"]:
		var cut: Dictionary = imported if route == "imported" else shipped
		_expect(int(cut.get("bridges", 0)) == 2,
			"on the %s route the body carries two Shared neck bridge surfaces" % route)
		_expect(int(cut.get("bridge_faces", 0)) > 0
			and cut.get("bridge_kept") == cut.get("bridge_faces"),
			"on the %s route torso 5:%d keeps every bridge face: %s of %s" % [route,
				OPEN_FRONT_TORSO, cut.get("bridge_kept"), cut.get("bridge_faces")])
	_expect(shipped.get("layout") != imported.get("layout"),
		"the shipped-route actor carries the raw GLTFDocument parse, not the imported scene")
	_expect(shipped.get("faces") == imported.get("faces")
		and shipped.get("kept") == imported.get("kept"),
		"both routes cut the body alike: imported keeps %s of %s faces, shipped %s of %s" % [
			imported.get("kept"), imported.get("faces"), shipped.get("kept"),
			shipped.get("faces")])


## A bridged actor's body under torso OPEN_FRONT_TORSO: its bridge surface
## count, bridge faces before and after, all faces before and after, and a
## fingerprint of the uncovered mesh's vertices and face corners.
func _bridge_cut(actor: ReplicatedActor3D) -> Dictionary:
	if actor == null:
		return {}
	var meshes := _coverable_meshes(actor)
	var body: MeshInstance3D = null
	for path: String in meshes:
		if (meshes[path] as MeshInstance3D).name.to_lower() in ["body", "char1", "mesh_node"]:
			body = meshes[path] as MeshInstance3D
	_expect(body != null, "the %s actor exposes its body mesh" % BRIDGED_RACE)
	if body == null:
		actor.free()
		return {}
	var original := body.mesh
	actor.apply_equipment_visuals({5: OPEN_FRONT_TORSO})
	var covered := body.mesh
	var result := {"bridges": 0, "bridge_faces": 0, "bridge_kept": 0, "faces": 0,
		"kept": 0}
	var layout := HashingContext.new()
	layout.start(HashingContext.HASH_SHA256)
	for surface: int in range(original.get_surface_count()):
		var source: PackedInt32Array = original.surface_get_arrays(surface)[Mesh.ARRAY_INDEX]
		var left: PackedInt32Array = covered.surface_get_arrays(surface)[Mesh.ARRAY_INDEX]
		var left_faces := 0
		for index: int in range(0, left.size(), 3):
			if not (left[index] == left[index + 1] and left[index] == left[index + 2]):
				left_faces += 1
		result["faces"] += source.size() / 3
		result["kept"] += left_faces
		layout.update((original.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			as PackedVector3Array).to_byte_array())
		layout.update(source.to_byte_array())
		var material := original.surface_get_material(surface)
		if material != null and material.resource_name == TorsoBodyCover.BRIDGE_MATERIAL:
			result["bridges"] += 1
			result["bridge_faces"] += source.size() / 3
			result["bridge_kept"] += left_faces
	result["layout"] = layout.finish().hex_encode()
	actor.apply_equipment_visuals({})
	_expect(is_same(body.mesh, original), "unequip restores the exact %s body" % BRIDGED_RACE)
	actor.free()
	return result


func _actor(id: int, config: Dictionary, animations: Dictionary,
		equipment: Dictionary, race: String = RACE) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": id, "x": 0, "y": 0,
		"rotation": 0, "kind": 1, "name": race, "appearance": {},
		"equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
		config, animations, equipment)
	_expect(errors.is_empty(), "the real imported actor configures: " + str(errors))
	if not errors.is_empty():
		actor.free()
		return null
	return actor


func _coverable_meshes(actor: ReplicatedActor3D) -> Dictionary:
	var result: Dictionary = {}
	var native := actor.get_node_or_null("NativeModel") as Node3D
	if native == null:
		return result
	for node_value: Node in native.find_children("*", "MeshInstance3D", true, false):
		var mesh := node_value as MeshInstance3D
		var name := mesh.name.to_lower()
		if mesh.skin != null and (name in ["body", "char1", "mesh_node"]
				or name.begins_with("wardrobe_")):
			result[str(native.get_path_to(mesh))] = mesh
	return result


func _mesh(vertices: PackedVector3Array, indices: PackedInt32Array,
		lods: Dictionary, bones: PackedInt32Array = PackedInt32Array(),
		weights: PackedFloat32Array = PackedFloat32Array()) -> ArrayMesh:
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	if not bones.is_empty():
		arrays[Mesh.ARRAY_BONES] = bones
		arrays[Mesh.ARRAY_WEIGHTS] = weights
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods)
	return mesh


func _join_indices(parts: Array) -> PackedInt32Array:
	var result := PackedInt32Array()
	for part_value: Variant in parts:
		result.append_array(part_value as PackedInt32Array)
	return result


func _mesh_lod_count(mesh: Mesh) -> int:
	var count := 0
	for surface: int in range(mesh.get_surface_count()):
		count += _lod_indices(mesh, surface).size()
	return count


func _mesh_lod_snapshot(mesh: Mesh) -> Array:
	var result: Array = []
	for surface: int in range(mesh.get_surface_count()):
		result.append(_lod_indices(mesh, surface))
	return result


## Test-side decoder used only to inspect the public RenderingServer shape.
## Coverage expectations remain literal above and do not depend on production.
func _lod_indices(mesh: Mesh, surface: int) -> Dictionary:
	if mesh is not ArrayMesh:
		return {}
	var raw: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
	var rows_value: Variant = raw.get("lods", [])
	if rows_value is not Array:
		return {}
	var width := 2 if int(raw.get("vertex_count", 0)) <= 65536 else 4
	var result: Dictionary = {}
	for row_value: Variant in rows_value as Array:
		if row_value is not Dictionary:
			continue
		var row := row_value as Dictionary
		var bytes := row.get("index_data", PackedByteArray()) as PackedByteArray
		var indices := PackedInt32Array()
		indices.resize(bytes.size() / width)
		for index: int in range(indices.size()):
			indices[index] = (bytes.decode_u16(index * width) if width == 2
				else bytes.decode_u32(index * width))
		result[float(row.get("edge_length", 0.0))] = indices
	return result


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)
