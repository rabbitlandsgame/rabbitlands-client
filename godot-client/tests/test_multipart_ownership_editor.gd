extends SceneTree
## Two distant components exercise the editor's actual sculpt, mesh and capture paths.
const GEOMETRY := preload("res://addons/map_authoring_workspace/ownership_geometry.gd")
const SCULPT := preload("res://addons/map_authoring_workspace/terrain_sculpt_tool.gd")
const TERRAIN := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const REFERENCE := preload("res://addons/map_authoring_workspace/reference_preview.gd")
const TOPDOWN := preload("res://addons/map_authoring_usability/top_down_capture.gd")
const SCATTER := preload("res://addons/map_authoring_usability/scatter_tool.gd")
const AREA := preload("res://addons/map_authoring_usability/area_tool.gd")
const PATH := preload("res://addons/map_authoring_usability/path_draw_tool.gd")
const WALKABILITY := preload("res://addons/map_authoring_usability/walkability_overlay.gd")
const CATALOG := preload("res://addons/map_authoring_workspace/territory_catalog.gd")
const PLUGIN := preload("res://addons/map_authoring_usability/plugin.gd")
var failures := 0
func _initialize() -> void:
	call_deferred("_run")
func _run() -> void:
	var west := PackedVector2Array([Vector2(0,0), Vector2(20,0), Vector2(20,20), Vector2(0,20)])
	var east := PackedVector2Array([Vector2(40,0), Vector2(60,0), Vector2(60,20), Vector2(40,20)])
	var rings: Array[PackedVector2Array] = [west, east]
	_expect(GEOMETRY.contains(Vector2(10,10), rings) and GEOMETRY.contains(Vector2(50,10), rings), "both ownership components contain editable land")
	_expect(not GEOMETRY.contains(Vector2(30,10), rings), "gap stays outside ownership")
	_expect(GEOMETRY.bounds(rings) == Rect2(0,0,60,20), "full ownership bounds include both components")
	_expect(GEOMETRY.polygons([west, PackedVector2Array([Vector2.ZERO])]).is_empty(), "invalid component refuses partial ownership")
	var serial: Array = [[0.0,0.0],[20.0,0.0],[20.0,20.0],[0.0,20.0]]
	_expect(GEOMETRY.hash([west]) == JSON.stringify(serial).sha256_text(), "single polygon retains legacy SHA")
	var multi: Array = [serial, [[40.0,0.0],[60.0,0.0],[60.0,20.0],[40.0,20.0]]]
	_expect(GEOMETRY.hash(rings) == JSON.stringify(multi).sha256_text(), "multipart SHA matches canonical ordered float rings")
	var fields: Dictionary = SCULPT.boundary_fields(rings, Vector3.ZERO, Vector2(-10,-10), Vector2i(41,21), 2.0)
	_expect(fields.weights[10*41+10] == 1.0 and fields.weights[10*41+30] == 1.0, "sculpt permits interiors of both components")
	_expect(fields.locked[10*41+20] == 1 and fields.locked[10*41+5] == 1 and fields.locked[10*41+27] == 1, "sculpt protects gap and both component borders")
	_expect(is_equal_approx(fields.weights[10*41+8], 0.5), "sculpt fade uses component border distance")
	var owner := Node3D.new()
	var script := GDScript.new()
	script.source_code = "extends Node3D\nvar continent_translation := Vector3.ZERO\nvar region_id := 'multipart_fixture'\nvar owned_route_ids := PackedStringArray()\nvar owned_plan_feature_ids := PackedStringArray()\n"
	script.reload()
	owner.set_script(script)
	root.add_child(owner)
	var terrain := TERRAIN.new()
	terrain.name = "Terrain"
	terrain.preview_enabled = false
	terrain.origin = Vector2(-10,-10)
	terrain.cell_metres = 2.0
	terrain.grid_size = Vector2i(41,21)
	terrain.base_heights_path = "user://multipart-base.f32le"
	var heights := PackedFloat32Array()
	heights.resize(41*21)
	var file := FileAccess.open(terrain.base_heights_path, FileAccess.WRITE)
	file.store_buffer(heights.to_byte_array())
	file.close()
	terrain.preview_clip_polygons = rings
	owner.add_child(terrain)
	var mask: PackedByteArray = terrain.preview_clip_mask()
	var cells := 0
	for value in mask:
		cells += value
	_expect(cells == 200 and mask[10*40+20] == 0, "viewer draws exactly both components and excludes gap")
	var area_tool := AREA.new()
	_expect(area_tool.start(owner, "ground", {"surface":Resource.new(), "blend_width":0.0}, rings, {}), "ground tool accepts multipart ownership")
	_expect(area_tool.ground_error(Vector3(10,0,10), Vector2(4,4)).is_empty() and area_tool.ground_error(Vector3(50,0,10), Vector2(4,4)).is_empty(), "ground tool accepts stamps in both components")
	_expect(not area_tool.ground_error(Vector3(30,0,10), Vector2(4,4)).is_empty(), "ground tool rejects stamps in the gap")
	area_tool.cancel()
	var roads := Node3D.new()
	roads.name = "Roads"
	owner.add_child(roads)
	var path_tool := PATH.new()
	_expect(path_tool.start(owner, "road", rings), "path tool accepts multipart ownership")
	var path := Node.new()
	var path_script := GDScript.new()
	path_script.source_code = "extends Node\nvar replaces_route_id := ''\nvar replaces_plan_feature_id := ''\nvar path_id := 'local'\nvar properties := {}\n"
	path_script.reload()
	path.set_script(path_script)
	_expect(path_tool.ownership_reason(path, Vector3(10,0,10)).is_empty() and path_tool.ownership_reason(path, Vector3(50,0,10)).is_empty(), "path ends inside both components are editable")
	_expect(not path_tool.ownership_reason(path, Vector3(30,0,10)).is_empty() and not path_tool.ownership_reason(path, Vector3(42,0,10)).is_empty(), "path tool protects gap and second component seam")
	path_tool.cancel()
	path.free()
	var reference := REFERENCE.new()
	reference.configure(owner, {"ownership_polygon":west, "ownership_polygons":rings, "translation":Vector3.ZERO})
	owner.add_child(reference)
	_expect(TOPDOWN.ownership_polygons_local(owner) == rings, "capture reads all catalog ownership components")
	var framing: Dictionary = TOPDOWN.plan(owner, 1.0, rings)
	_expect(not framing.has("error") and framing.rect == Rect2(0,0,60,20) and framing.size == Vector2i(60,20), "capture frames complete ownership bounds")
	var image: Image = TOPDOWN.ownership_mask(framing, rings)
	_expect(image.get_pixel(10,10).a == 1.0 and image.get_pixel(50,10).a == 1.0 and image.get_pixel(30,10).a == 0.0, "capture includes both components with transparent gap")
	var source := MeshInstance3D.new()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0,0,0),Vector3(0,0,20),Vector3(60,0,0),Vector3(60,0,20)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,2,1,3])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	source.mesh = mesh
	owner.add_child(source)
	var clipped: ArrayMesh = REFERENCE.clipped_mesh(source, owner, rings, Vector3.ZERO)
	var area := 0.0
	var gap_free := true
	for surface in clipped.get_surface_count():
		var output: Array = clipped.surface_get_arrays(surface)
		var vertices: PackedVector3Array = output[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = output[Mesh.ARRAY_INDEX]
		for index in range(0, indices.size(), 3):
			var a := vertices[indices[index]]
			var b := vertices[indices[index+1]]
			var c := vertices[indices[index+2]]
			area += (b-a).cross(c-a).length() * 0.5
			var centre := (a+b+c)/3.0
			gap_free = gap_free and GEOMETRY.contains(Vector2(centre.x,centre.z), rings)
	_expect(is_equal_approx(area, 800.0) and gap_free, "reference clipping retains both 400m2 components without a bridge")
	var rng := RandomNumberGenerator.new()
	rng.seed = 147
	var points: PackedVector2Array = SCATTER.stamp_points(rng, Vector2(30,10), 30.0, 10.0, 1.0, PackedVector2Array(), rings)
	var left := 0
	var right := 0
	var contained := true
	for point in points:
		contained = contained and GEOMETRY.contains(point, rings)
		left += 1 if point.x < 20.0 else 0
		right += 1 if point.x > 40.0 else 0
	_expect(contained and left > 0 and right > 0, "scatter reaches both components and leaves gap empty")
	owner.queue_free()
	await process_frame
	print("multipart ownership editor: %d failures" % failures)
	quit(1 if failures else 0)
func _expect(condition: bool, message: String) -> void:
	print("PASS: " if condition else "FAIL: ", message)
	failures += 0 if condition else 1
