extends SceneTree

const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const REGION := preload("res://src/dev/map_authoring_region/region_control.gd")
const PATH := preload("res://src/dev/map_authoring_region/path_control.gd")
const BRIDGE := preload("res://src/dev/map_authoring_region/bridge_control.gd")
const GROUND := preload("res://src/dev/map_authoring_region/ground_region_control.gd")
const SURFACE := preload(
	"res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd")
const PRESETS := preload(
	"res://src/dev/map_authoring_pilot/style/texture_presets.gd")

const HEIGHT_PATH := "res://tests/.continent-preview-heights.f32le"

var assertions := 0
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_write_heights()
	var region := _scene()
	root.add_child(region)
	await process_frame
	var terrain = region.get_node("Terrain")
	var road = region.get_node("Roads/Road")
	var river = region.get_node("Rivers/River")
	var bridge = region.get_node("Bridges/Bridge")
	terrain.refresh_preview()
	road.call("_refresh_preview")
	river.call("_refresh_preview")
	bridge.refresh_preview()
	_check(terrain.height_at_local(0.0, 0.0) <= 0.001,
		"river cut runs after crossing-road grading and keeps a wet channel bed")
	var outer_bank: float = terrain.height_at_local(4.0, 4.0)
	var feather_bank: float = terrain.height_at_local(4.0, 3.0)
	_check(outer_bank > 10.4 and feather_bank > 4.0,
		"river feather reaches unchanged high bank without an outer-edge trench " +
		"(outer %.3f, feather %.3f)" % [outer_bank, feather_bank])

	var deck := bridge.get_node("__BridgePreview/Deck") as MeshInstance3D
	var supports := bridge.get_node("__BridgePreview/Supports") as MeshInstance3D
	_check(deck.mesh != null and deck.mesh.get_surface_count() == 1,
		"bridge preview builds a visible deck")
	_check(supports.mesh != null and supports.mesh.get_surface_count() == 1,
		"bridge preview builds interior terrain supports")
	var deck_bounds := deck.mesh.get_aabb()
	_check(absf(deck_bounds.size.x - bridge.width) < 0.01 and
		deck_bounds.end.y > 2.7,
		"bridge deck uses its full width, crown arch, and uniform water clearance lift")
	_check(deck.owner == null and supports.owner == null,
		"generated bridge preview remains outside saved authoring ownership")

	_check_path_clearance(road, terrain, false)
	_check_path_clearance(river, terrain, true)
	_check_shape_terrain_control(region, terrain)
	var old_revision: int = terrain.preview_revision
	var old_path_signature: Array = road.call("_current_preview_signature")
	region.get_node("Terrain/Patches/Lift").position.y += 1.0
	terrain.refresh_preview()
	var new_path_signature: Array = road.call("_current_preview_signature")
	road.call("_refresh_preview")
	_check(terrain.preview_revision > old_revision and
		new_path_signature != old_path_signature,
		"terrain edits invalidate and re-drape the road preview")
	_check_path_clearance(road, terrain, false)
	var ground_preview := terrain.get_node(
		"__GroundRegionPreviews/GroundRegion_test-ground") as MeshInstance3D
	_check(ground_preview.mesh != null and ground_preview.material_override != null,
		"enabled ground-region surfaces render on resolved terrain")
	var terrain_preview := terrain.get_node("__TerrainPreview") as MeshInstance3D
	var terrain_arrays := terrain_preview.mesh.surface_get_arrays(0)
	_check_front_faces(terrain_arrays, "full terrain")
	var chunk_arrays: Array = terrain.call("_preview_arrays_for_cells",
		[Vector2i(0, 0), Vector2i(2, 2)], terrain_arrays[Mesh.ARRAY_VERTEX],
		terrain_arrays[Mesh.ARRAY_NORMAL], terrain_arrays[Mesh.ARRAY_TEX_UV])
	_check_front_faces(chunk_arrays, "chunk terrain")
	_check_front_faces(ground_preview.mesh.surface_get_arrays(0), "ground region")

	var old_width := deck.mesh.get_aabb().size.x
	bridge.width = 5.0
	bridge.deck_texture_rotation_degrees = 37.0
	bridge.refresh_preview()
	_check(deck.mesh.get_aabb().size.x > old_width + 0.9 and
		deck.material_override != null,
		"bridge width and local deck rotation rebuild only its generated preview")
	_check_curved_snapshot()
	_check_control_polygon_snapshot()

	region.queue_free()
	await process_frame
	DirAccess.remove_absolute(ProjectSettings.globalize_path(HEIGHT_PATH))
	print("continent bridge/path preview: %d assertions, %d failures" % [
		assertions, failures])
	quit(1 if failures else 0)


func _scene() -> Node3D:
	var region := REGION.new()
	region.name = "PreviewRegion"
	region.region_id = "preview-region"
	var terrain := TERRAIN.new()
	terrain.name = "Terrain"
	terrain.origin = Vector2(-6.0, -6.0)
	terrain.cell_metres = 2.0
	terrain.grid_size = Vector2i(7, 7)
	terrain.base_heights_path = HEIGHT_PATH
	terrain.base_surface = SURFACE.from_preset(PRESETS.GRASS)
	region.add_child(terrain)
	var patches := Node3D.new()
	patches.name = "Patches"
	terrain.add_child(patches)
	var patch_script := preload(
		"res://src/dev/map_authoring_region/terrain_patch.gd")
	var patch = patch_script.new()
	patch.name = "Lift"
	patch.patch_id = "lift"
	patch.operation = patch_script.Operation.ADD
	patch.size = Vector2(14.0, 14.0)
	patch.feather = 0.0
	patch.position = Vector3(0.0, 0.5, 0.0)
	patches.add_child(patch)
	var ground := Node3D.new()
	ground.name = "Ground"
	region.add_child(ground)
	var ground_regions := Node3D.new()
	ground_regions.name = "Regions"
	ground.add_child(ground_regions)
	var ground_region := GROUND.new()
	ground_region.name = "TestGround"
	ground_region.region_id = "test-ground"
	ground_region.enabled = true
	ground_region.position = Vector3(3.0, 0.0, 3.0)
	ground_region.size = Vector2(3.0, 3.0)
	ground_region.surface = SURFACE.from_preset(PRESETS.SOIL)
	ground_regions.add_child(ground_region)

	var roads := Node3D.new()
	roads.name = "Roads"
	region.add_child(roads)
	var road := _path("Road", "road", Vector3(-5.0, 2.0, -3.0),
		Vector3(5.0, 2.0, -3.0), 2.0)
	road.properties = {"terrainConform": false}
	roads.add_child(road)
	var crossing := _path("CrossingRoad", "road", Vector3(0.0, 2.0, -5.0),
		Vector3(0.0, 2.0, 5.0), 2.0)
	roads.add_child(crossing)
	var rivers := Node3D.new()
	rivers.name = "Rivers"
	region.add_child(rivers)
	var river := _path("River", "river", Vector3(-5.0, 1.5, 0.0),
		Vector3(5.0, 1.5, 0.0), 4.0)
	river.properties = {"channelDepth": 1.5, "terrainFeather": 2.0}
	rivers.add_child(river)

	var bridges := Node3D.new()
	bridges.name = "Bridges"
	region.add_child(bridges)
	var bridge := BRIDGE.new()
	bridge.name = "Bridge"
	bridge.bridge_id = "test-bridge"
	bridge.width = 4.0
	bridge.arch = 0.5
	bridge.water_clearance = 1.1
	bridge.deck_surface = SURFACE.from_preset(PRESETS.TIMBER)
	bridge.support_surface = SURFACE.from_preset(PRESETS.STONE)
	bridges.add_child(bridge)
	var start := Marker3D.new()
	start.name = "Start"
	start.position = Vector3(0.0, 2.0, -4.0)
	bridge.add_child(start)
	var end := Marker3D.new()
	end.name = "End"
	end.position = Vector3(0.0, 2.0, 4.0)
	bridge.add_child(end)
	return region


func _path(node_name: String, kind: String, start: Vector3, end: Vector3,
		path_width: float) -> Path3D:
	var path := PATH.new()
	path.name = node_name
	path.path_id = node_name.to_lower()
	path.kind = kind
	path.default_width = path_width
	path.curve = Curve3D.new()
	path.curve.add_point(start)
	path.curve.add_point(end)
	if kind == "road":
		path.surface = SURFACE.from_preset(PRESETS.WORN_EARTH, true)
	return path


func _check_path_clearance(path: Path3D, terrain: Node3D,
		expect_water_surface: bool) -> void:
	var preview := path.get_node("__PathPreview") as MeshInstance3D
	var arrays: Array = preview.mesh.surface_get_arrays(0)
	_check_front_faces(arrays, "river" if expect_water_surface else "road")
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var all_clear := not vertices.is_empty()
	var all_lit := normals.size() == vertices.size() and \
		tangents.size() == vertices.size() * 4
	var reaches_water := false
	var keeps_hydraulic_level := true
	for index in vertices.size():
		var local_vertex := vertices[index]
		var terrain_vertex: Vector3 = terrain.global_transform.affine_inverse() * \
			path.global_transform * local_vertex
		var floor_y: float = terrain.height_at_local(terrain_vertex.x, terrain_vertex.z)
		all_clear = all_clear and terrain_vertex.y >= floor_y + \
			(0.014 if expect_water_surface else 0.05)
		all_lit = all_lit and normals[index].length_squared() > 0.9 and \
			normals[index].y > 0.0 and \
			Vector3(tangents[index * 4], tangents[index * 4 + 1],
				tangents[index * 4 + 2]).length_squared() > 0.9 and \
			absf(tangents[index * 4 + 3]) > 0.9
		reaches_water = reaches_water or terrain_vertex.y >= 1.49
		if expect_water_surface:
			keeps_hydraulic_level = keeps_hydraulic_level and \
				absf(terrain_vertex.y - 1.5) < 0.001
	_check(all_clear and (not expect_water_surface or
		(reaches_water and keeps_hydraulic_level)),
		("river water renders over its cut channel" if expect_water_surface else
		"road ribbon follows exact resolved terrain triangles"))
	var expected_width := 4.0 if expect_water_surface else 2.0
	var maximum_u := 0.0
	for uv in uvs:
		maximum_u = maxf(maximum_u, uv.x)
	_check(all_lit and absf(maximum_u - expected_width) < 0.001,
		"path preview has upward normals and metre-scaled cross-path UVs")


func _check_front_faces(arrays: Array, label: String) -> void:
	var native := PlaneMesh.new().get_mesh_arrays()
	var nv: PackedVector3Array = native[Mesh.ARRAY_VERTEX]
	var ni: PackedInt32Array = native[Mesh.ARRAY_INDEX]
	var nn: PackedVector3Array = native[Mesh.ARRAY_NORMAL]
	var native_sign := (nv[ni[1]] - nv[ni[0]]).cross(
		nv[ni[2]] - nv[ni[0]]).dot(nn[ni[0]])
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var all_front := not indices.is_empty()
	var checked := 0
	for offset in range(0, indices.size(), 3):
		var a := indices[offset]
		var b := indices[offset + 1]
		var c := indices[offset + 2]
		var cross := (vertices[b] - vertices[a]).cross(vertices[c] - vertices[a])
		if cross.length_squared() < 0.00000001:
			continue
		var shading_normal := (normals[a] + normals[b] + normals[c]).normalized()
		all_front = all_front and shading_normal.y > 0.0 and \
			cross.dot(shading_normal) * native_sign > 0.0
		checked += 1
	_check(all_front and checked > 0,
		label + " front faces match native upward PlaneMesh with upward shading normals")


func _check_curved_snapshot() -> void:
	var path := PATH.new()
	path.curve = Curve3D.new()
	path.curve.add_point(Vector3(0.0, 0.0, 0.0), Vector3.ZERO,
		Vector3(3.0, 0.0, 5.0))
	path.curve.add_point(Vector3(10.0, 0.0, 0.0), Vector3(-3.0, 0.0, 5.0),
		Vector3(3.0, 0.0, -4.0))
	path.curve.add_point(Vector3(20.0, 0.0, 0.0), Vector3(-3.0, 0.0, -4.0))
	path.sync_curve_binding()
	path.point_widths = PackedFloat32Array([2.0, 6.0, 4.0])
	var records := path.snapshot_points()
	var keeps_curve := false
	var middle_anchor := false
	for record in records:
		var position := Vector3(float(record.position[0]), float(record.position[1]),
			float(record.position[2]))
		keeps_curve = keeps_curve or absf(position.z) > 0.5
		if position.distance_to(Vector3(10.0, 0.0, 0.0)) < 0.00001:
			middle_anchor = is_equal_approx(float(record.width), 6.0)
	_check(keeps_curve,
		"exact anchor retention keeps arbitrary user-authored Bezier curvature")
	_check(middle_anchor,
		"snapshot retains exact curve stations and their per-point widths")
	path.free()


func _check_control_polygon_snapshot() -> void:
	var path := PATH.new()
	path.curve = Curve3D.new()
	_check(path.snapshot_points().is_empty(),
		"control polygon has no records for an empty curve")
	path.curve.add_point(Vector3.ZERO)
	path.snapshot_mode = 1
	var singleton := path.snapshot_points()
	_check(singleton.size() == 1 and singleton[0].position == [0.0, 0.0, 0.0],
		"control polygon preserves a lone control")
	path.curve.add_point(Vector3(10.0, 0.0, 0.0))
	path.curve.add_point(Vector3(20.0, 0.0, 0.0))
	path.curve.add_point(Vector3(30.0, 0.0, 0.0))
	path.curve.add_point(Vector3(40.0, 0.0, 0.0))
	path.sync_curve_binding()
	path.point_widths = PackedFloat32Array([2.0, 4.0, 0.0, 6.0, 8.0])
	path.snapshot_spacing = 0.1
	var baseline := path.snapshot_points()
	_check(baseline.size() == 5 and baseline[2].position == [20.0, 0.0, 0.0]
		and is_equal_approx(float(baseline[2].width), 5.0),
		"control polygon keeps only authored stations and resolves inherited width")
	path.snapshot_mode = 0
	var baked := path.snapshot_points()
	path.snapshot_mode = 1
	_check(baked.size() > baseline.size() and path.snapshot_points() == baseline,
		"switching modes does not reuse baked stations or widths")
	var prior_signature: Array = path.call("_current_preview_signature")
	path.curve.set_point_position(2, Vector3(20.0, 0.0, 5.0))
	var moved := path.snapshot_points()
	var far_controls_stable := moved.size() == baseline.size()
	for index in [0, 1, 3, 4]:
		far_controls_stable = far_controls_stable and moved[index] == baseline[index]
	_check(far_controls_stable and moved[2].position == [20.0, 0.0, 5.0]
		and path.call("_current_preview_signature") != prior_signature,
		"an interior move preserves far stations and invalidates preview")
	path.curve.add_point(Vector3(25.0, 0.0, 3.0), Vector3.ZERO, Vector3.ZERO, 3)
	var inserted := path.snapshot_points()
	_check(inserted.size() == 6 and inserted[0] == baseline[0]
		and inserted[1] == baseline[1] and inserted[4] == baseline[3]
		and inserted[5] == baseline[4] and float(inserted[3].width) > 4.0
		and float(inserted[3].width) < 6.0,
		"inserting a control retains surviving widths and gives the new point a taper")
	path.curve.remove_point(3)
	_check(path.snapshot_points() == moved,
		"removing the inserted control restores the moved polygon")
	path.curve.set_point_position(2, Vector3(20.0, 0.0, 0.0))
	path.curve.set_point_out(1, Vector3(5.0, 0.0, 8.0))
	_check(path.snapshot_points() == baseline and
		(path.call("_get_configuration_warnings") as PackedStringArray).has(
			"Control polygon sampling uses straight segments; Bezier handles are ignored."),
		"control polygon ignores Bezier handles and reports them")
	path.curve.closed = true
	var closed := path.snapshot_points()
	_check(closed.size() == baseline.size() + 1 and closed[closed.size() - 1] == closed[0],
		"closed control polygon includes its return segment for preview and terrain")
	path.free()

	var duplicates := PATH.new()
	duplicates.curve = Curve3D.new()
	duplicates.curve.add_point(Vector3.ZERO)
	duplicates.curve.add_point(Vector3.ZERO)
	duplicates.sync_curve_binding()
	duplicates.point_widths = PackedFloat32Array([2.0, 4.0])
	duplicates.snapshot_mode = 1
	var coincident := duplicates.snapshot_points()
	_check(coincident.size() == 2 and coincident[0].position == coincident[1].position
		and is_equal_approx(float(coincident[0].width), 2.0)
		and is_equal_approx(float(coincident[1].width), 4.0),
		"coincident controls remain distinct with their own authored widths")
	duplicates.curve.add_point(Vector3.ZERO, Vector3.ZERO, Vector3.ZERO, 1)
	duplicates.point_widths = PackedFloat32Array([2.0, 0.0, 4.0])
	var zero_span := duplicates.snapshot_points()
	_check(zero_span.size() == 3 and is_equal_approx(float(zero_span[1].width), 2.0),
		"an inherited width in a zero-length span takes the preceding anchor")
	duplicates.free()


func _check_shape_terrain_control(region: Node3D, terrain: Node3D) -> void:
	var roads := region.get_node("Roads")
	var baseline: PackedFloat32Array = terrain.effective_heights()
	var passive := _path("PassiveRoad", "road", Vector3(-5.0, 20.0, 5.0),
		Vector3(5.0, 20.0, 5.0), 2.0)
	roads.add_child(passive)
	var inspector_property := {}
	for property: Dictionary in passive.get_property_list():
		if property.name == &"shape_terrain":
			inspector_property = property
	passive.set("shape_terrain", false)
	terrain.refresh_preview()
	var disabled_heights: PackedFloat32Array = terrain.effective_heights()
	passive.position.x += 2.0
	terrain.refresh_preview()
	var moved_heights: PackedFloat32Array = terrain.effective_heights()
	roads.remove_child(passive)
	terrain.refresh_preview()
	var deleted_heights: PackedFloat32Array = terrain.effective_heights()
	_check(not inspector_property.is_empty() and
		(int(inspector_property.usage) & PROPERTY_USAGE_STORAGE) == 0 and
		passive.properties == {"terrainConform": false},
		"Shape terrain edits the existing path property without duplicate storage")
	_check(disabled_heights == baseline and moved_heights == baseline and
		deleted_heights == baseline,
		"a follow-existing road can move or be deleted without changing authored ground")
	passive.free()

	var shaping := _path("ShapingRoad", "road", Vector3(-5.0, 20.0, 5.0),
		Vector3(5.0, 20.0, 5.0), 2.0)
	roads.add_child(shaping)
	var defaults_to_shaping: bool = bool(shaping.get("shape_terrain")) and \
		not shaping.properties.has("terrainConform")
	terrain.refresh_preview()
	_check(defaults_to_shaping and terrain.effective_heights() != baseline,
		"new roads default to explicit curve-height terrain shaping")
	roads.remove_child(shaping)
	shaping.free()
	terrain.refresh_preview()


func _write_heights() -> void:
	var file := FileAccess.open(HEIGHT_PATH, FileAccess.WRITE)
	file.big_endian = false
	for z_index in 7:
		for x_index in 7:
			file.store_float(10.0 if z_index == 5 else
				float(x_index) * 0.2 + float(z_index) * 0.1)
	file.close()


func _check(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
