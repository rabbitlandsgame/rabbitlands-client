extends SceneTree

const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")
const RELOAD_PATH := "res://src/dev/map_authoring_pilot/.visual-controls-reload.tscn"

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var pilot: Node = PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame

	var road := pilot.get_node("AuthoredControls/Road") as Path3D
	road.curve = road.curve.duplicate(true) as Curve3D
	var inserted_position := road.curve.get_point_position(0).lerp(
		road.curve.get_point_position(1), 0.5) + Vector3(1.25, 4.0, 0.75)
	road.curve.add_point(inserted_position, Vector3.ZERO, Vector3.ZERO, 1)
	pilot.call("_detect_authored_changes")
	_expect(road.curve.point_count == 5 and _mesh_has_vertices(
		pilot, "GeneratedPreview/Road/RoadSurface"),
		"inserting a native road point regenerates a visible road")
	var edited_road := road.curve.duplicate(true) as Curve3D

	while road.curve.point_count > 1:
		road.curve.remove_point(road.curve.point_count - 1)
	pilot.call("_detect_authored_changes")
	_expect(not _mesh_has_vertices(pilot, "GeneratedPreview/Road/RoadSurface"),
		"a one-point road safely produces no surface")
	road.curve.remove_point(0)
	pilot.call("_detect_authored_changes")
	_expect(not _mesh_has_vertices(pilot, "GeneratedPreview/Road/RoadSurface"),
		"an empty road safely produces no surface")
	road.curve = edited_road.duplicate(true) as Curve3D
	pilot.call("_detect_authored_changes")
	_expect(_mesh_has_vertices(pilot, "GeneratedPreview/Road/RoadSurface"),
		"restoring road points through the change detector restores its surface")

	var river := pilot.get_node("AuthoredControls/River") as Path3D
	var old_water_site := Vector2(0.0, 16.0)
	var new_water_site := Vector2(10.0, 16.0)
	_expect(int(pilot.call("_encoded_floor", old_water_site.x, old_water_site.y)) == 0,
		"the pristine river blocks the established water sample")
	var bent_river := Curve3D.new()
	bent_river.add_point(Vector3(0.0, 0.0, -24.0))
	bent_river.add_point(Vector3(0.0, 5.0, 0.0))
	bent_river.add_point(Vector3(10.0, -7.0, 12.0))
	bent_river.add_point(Vector3(10.0, 3.0, 24.0))
	river.curve = bent_river
	pilot.refresh_scope = "Road"
	pilot.refresh_selected()
	_expect(int(pilot.call("_encoded_floor", old_water_site.x, old_water_site.y)) > 0 and
		int(pilot.call("_encoded_floor", new_water_site.x, new_water_site.y)) == 0,
		"a manual partial refresh promotes a pending river edit and moves blocked cells")
	_expect(not _water_mesh_reaches(pilot, old_water_site, 2.5) and
		_water_mesh_reaches(pilot, new_water_site, 0.8),
		"the visible water mesh follows the same bent channel")
	_expect(_water_mesh_is_level(pilot, pilot.water_level),
		"river control-point Y is ignored and water stays at the root water level")

	var outside_river := Curve3D.new()
	outside_river.add_point(Vector3(40.0, 0.0, -20.0))
	outside_river.add_point(Vector3(40.0, 0.0, 20.0))
	river.curve = outside_river
	pilot.call("_detect_authored_changes")
	_expect(not _mesh_has_vertices(pilot, "GeneratedPreview/Water/River") and
		int(pilot.call("_encoded_floor", new_water_site.x, new_water_site.y)) > 0,
		"an out-of-map river creates neither water geometry nor in-map blocked cells")

	var one_point_river := Curve3D.new()
	one_point_river.add_point(Vector3(10.0, 9.0, 16.0))
	river.curve = one_point_river
	pilot.call("_detect_authored_changes")
	_expect(not _mesh_has_vertices(pilot, "GeneratedPreview/Water/River") and
		int(pilot.call("_encoded_floor", new_water_site.x, new_water_site.y)) > 0,
		"a one-point river removes both visible water and river collision")
	river.curve = Curve3D.new()
	pilot.call("_detect_authored_changes")
	_expect(not _mesh_has_vertices(pilot, "GeneratedPreview/Water/River"),
		"an empty river safely keeps the water preview empty")
	river.curve = bent_river.duplicate(true) as Curve3D
	pilot.call("_detect_authored_changes")

	var terrain_heights := pilot.get_node("AuthoredControls/TerrainHeights") as Node3D
	var handle := terrain_heights.get_child(0) as Marker3D
	var neutral_y := float(handle.get("neutral_y"))
	var first_site := Vector2(-12.0, 12.0)
	var moved_site := Vector2(-4.0, 12.0)
	var outside_site := Vector2(-7.0, 12.0)
	pilot.call("_refresh_authoring_caches")
	var first_baseline := float(pilot.call("_terrain_height", first_site.x, first_site.y))
	var moved_baseline := float(pilot.call("_terrain_height", moved_site.x, moved_site.y))
	var outside_baseline := float(pilot.call("_terrain_height", outside_site.x, outside_site.y))
	var first_encoded := int(pilot.call("_encoded_floor", first_site.x, first_site.y))
	handle.position = Vector3(first_site.x, neutral_y + 2.0, first_site.y)
	handle.set("influence_radius", 3.0)
	pilot.call("_detect_authored_changes")
	var raised_height := float(pilot.call("_terrain_height", first_site.x, first_site.y))
	var raised_encoded := int(pilot.call("_encoded_floor", first_site.x, first_site.y))
	_expect(is_equal_approx(raised_height, first_baseline + 2.0) and
		raised_encoded > first_encoded,
		"moving a terrain handle in Y raises sampled terrain and its encoded cell")
	_expect(is_equal_approx(float(pilot.call("_terrain_height", outside_site.x,
		outside_site.y)), outside_baseline),
		"terrain outside the handle radius remains unchanged")
	_expect(is_equal_approx(_terrain_mesh_height(pilot, first_site),
		float(pilot.call("_decoded_height", raised_encoded))),
		"the regenerated terrain mesh carries the encoded raised height")

	handle.set("influence_radius", 10.0)
	pilot.call("_detect_authored_changes")
	_expect(float(pilot.call("_terrain_height", outside_site.x, outside_site.y)) >
		outside_baseline + 0.7,
		"editing a terrain handle radius changes terrain inside the expanded area")
	handle.set("influence_radius", 3.0)
	handle.position = Vector3(moved_site.x, neutral_y + 2.0, moved_site.y)
	pilot.call("_detect_authored_changes")
	_expect(is_equal_approx(float(pilot.call("_terrain_height", first_site.x, first_site.y)),
		first_baseline) and is_equal_approx(float(pilot.call("_terrain_height", moved_site.x,
		moved_site.y)), moved_baseline + 2.0),
		"moving a terrain handle in X/Z transfers its local height influence")

	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(
		RELOAD_PATH.get_base_dir()))
	var packed := PackedScene.new()
	_expect(packed.pack(pilot) == OK, "the visual-control edits can be packed")
	var save_error := ResourceSaver.save(packed, RELOAD_PATH)
	_expect(save_error == OK, "the visual-control edits can be saved")
	if save_error != OK:
		_finish(pilot)
		return
	var reopened_resource := ResourceLoader.load(RELOAD_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened: Node = reopened_resource.instantiate()
	root.add_child(reopened)
	await process_frame
	await process_frame
	var reopened_road := reopened.get_node("AuthoredControls/Road") as Path3D
	var reopened_river := reopened.get_node("AuthoredControls/River") as Path3D
	var reopened_handle := reopened.get_node(
		"AuthoredControls/TerrainHeights/" + str(handle.name)) as Marker3D
	_expect(_curves_match(reopened_road.curve, edited_road),
		"the inserted road point count and shape survive save and reopen")
	_expect(_curves_match(reopened_river.curve, bent_river) and
		int(reopened.call("_encoded_floor", new_water_site.x, new_water_site.y)) == 0 and
		_water_mesh_reaches(reopened, new_water_site, 0.8),
		"the bent river shape, collision, and water survive save and reopen")
	_expect(reopened_handle.position == handle.position and
		is_equal_approx(float(reopened_handle.get("influence_radius")), 3.0) and
		is_equal_approx(float(reopened.call("_terrain_height", moved_site.x,
		moved_site.y)), moved_baseline + 2.0),
		"terrain-handle position, radius, and height effect survive save and reopen")

	var reopened_heights := reopened.get_node("AuthoredControls/TerrainHeights") as Node3D
	reopened_heights.remove_child(reopened_handle)
	reopened_handle.free()
	reopened.call("_detect_authored_changes")
	var reverted_height := float(reopened.call("_terrain_height", moved_site.x, moved_site.y))
	var reverted_encoded := int(reopened.call("_encoded_floor", moved_site.x, moved_site.y))
	_expect(is_equal_approx(reverted_height, moved_baseline) and
		reverted_encoded < int(reopened.call("_encode_height", moved_baseline + 2.0)) and
		is_equal_approx(_terrain_mesh_height(reopened, moved_site),
		float(reopened.call("_decoded_height", reverted_encoded))),
		"deleting a terrain handle reverts sampled, encoded, and generated terrain")

	reopened.queue_free()
	_finish(pilot)


func _mesh_has_vertices(pilot: Node, path: NodePath) -> bool:
	var mesh_instance := pilot.get_node_or_null(path) as MeshInstance3D
	if mesh_instance == null or mesh_instance.mesh == null:
		return false
	for surface_index in mesh_instance.mesh.get_surface_count():
		var arrays := mesh_instance.mesh.surface_get_arrays(surface_index)
		if arrays[Mesh.ARRAY_VERTEX].size() > 0:
			return true
	return false


func _water_mesh_reaches(pilot: Node, site: Vector2, tolerance: float) -> bool:
	var mesh_instance := pilot.get_node_or_null("GeneratedPreview/Water/River") as MeshInstance3D
	if mesh_instance == null or mesh_instance.mesh == null:
		return false
	for surface_index in mesh_instance.mesh.get_surface_count():
		var vertices: PackedVector3Array = mesh_instance.mesh.surface_get_arrays(
			surface_index)[Mesh.ARRAY_VERTEX]
		for vertex in vertices:
			if Vector2(vertex.x, vertex.z).distance_to(site) <= tolerance:
				return true
	return false


func _water_mesh_is_level(pilot: Node, expected_y: float) -> bool:
	var mesh_instance := pilot.get_node_or_null("GeneratedPreview/Water/River") as MeshInstance3D
	if mesh_instance == null or mesh_instance.mesh == null:
		return false
	var saw_vertex := false
	for surface_index in mesh_instance.mesh.get_surface_count():
		var vertices: PackedVector3Array = mesh_instance.mesh.surface_get_arrays(
			surface_index)[Mesh.ARRAY_VERTEX]
		for vertex in vertices:
			saw_vertex = true
			if not is_equal_approx(vertex.y, expected_y):
				return false
	return saw_vertex


func _terrain_mesh_height(pilot: Node, site: Vector2) -> float:
	var mesh_instance := pilot.get_node_or_null(
		"GeneratedPreview/Terrain/TerrainMesh") as MeshInstance3D
	if mesh_instance == null or mesh_instance.mesh == null:
		return -INF
	for surface_index in mesh_instance.mesh.get_surface_count():
		var vertices: PackedVector3Array = mesh_instance.mesh.surface_get_arrays(
			surface_index)[Mesh.ARRAY_VERTEX]
		for vertex in vertices:
			if is_equal_approx(vertex.x, site.x) and is_equal_approx(vertex.z, site.y):
				return vertex.y
	return -INF


func _curves_match(actual: Curve3D, expected: Curve3D) -> bool:
	if actual.point_count != expected.point_count or actual.closed != expected.closed:
		return false
	for index in actual.point_count:
		if actual.get_point_position(index) != expected.get_point_position(index) or \
				actual.get_point_in(index) != expected.get_point_in(index) or \
				actual.get_point_out(index) != expected.get_point_out(index):
			return false
	return true


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false


func _finish(pilot: Node) -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(RELOAD_PATH))
	print("map authoring pilot visual controls: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	pilot.queue_free()
	quit(_failures)
