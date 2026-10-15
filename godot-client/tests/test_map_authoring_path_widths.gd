extends SceneTree

const WIDTH_PATH := preload("res://src/dev/map_authoring_pilot/width_path.gd")
const PILOT := preload("res://src/dev/map_authoring_pilot/map_authoring_pilot.tscn")
const RELOAD_PATH := "res://src/dev/map_authoring_pilot/.path-width-reload.tscn"

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var path := _make_width_path([Vector3.ZERO, Vector3(5.0, 0.0, 0.0),
		Vector3(10.0, 0.0, 0.0)], PackedFloat32Array([2.0, 4.0, 6.0]))
	root.add_child(path)
	await process_frame
	_expect(is_equal_approx(path.width_at_offset(0.0), 2.0) and
		is_equal_approx(path.width_at_offset(path.curve.get_baked_length()), 6.0) and
		is_equal_approx(path.width_at_offset(5.0), 4.0),
		"endpoint and middle widths follow baked distance")

	path.curve.add_point(Vector3(2.5, 0.0, 0.0), Vector3.ZERO, Vector3.ZERO, 1)
	_expect(path.point_widths == PackedFloat32Array([2.0, 0.0, 4.0, 6.0]) and
		is_equal_approx(path.width_at_offset(2.5), 3.0),
		"a middle insertion inherits the existing taper without using curve tilt")
	path.curve.remove_point(0)
	_expect(path.point_widths == PackedFloat32Array([0.0, 4.0, 6.0]),
		"deleting the first point keeps surviving point ownership")
	path.curve.add_point(Vector3.ZERO, Vector3.ZERO, Vector3.ZERO, 0)
	_expect(path.point_widths == PackedFloat32Array([2.0, 0.0, 4.0, 6.0]),
		"restoring a deleted first point restores its saved widths")

	path.curve.set_point_position(1, Vector3(2.75, 0.0, 0.0))
	path.curve.set_point_position(1, Vector3(2.5, 0.0, 0.0))
	_expect(path.point_widths == PackedFloat32Array([2.0, 0.0, 4.0, 6.0]),
		"moving a point away and back keeps width ownership by index")

	path.curve.remove_point(2)
	var last_position := path.curve.get_point_position(2)
	for index in 40:
		path.curve.set_point_position(2, last_position + Vector3(float(index + 1) * 0.01, 0.0, 0.0))
	path.curve.set_point_position(2, last_position)
	path.curve.add_point(Vector3(5.0, 0.0, 0.0), Vector3.ZERO, Vector3.ZERO, 2)
	_expect(path.point_widths == PackedFloat32Array([2.0, 0.0, 4.0, 6.0]),
		"topology undo restores widths after many same-count point moves")

	var holder := Node3D.new()
	holder.name = "WidthPaths"
	var saved_path := path.duplicate() as Path3D
	saved_path.name = "Original"
	var copied_path := path.duplicate() as Path3D
	copied_path.name = "Copy"
	holder.add_child(saved_path)
	holder.add_child(copied_path)
	saved_path.owner = holder
	copied_path.owner = holder
	root.add_child(holder)
	await process_frame
	var copied_widths: PackedFloat32Array = copied_path.point_widths.duplicate()
	copied_widths[0] = 8.0
	copied_path.point_widths = copied_widths
	copied_path.curve.set_point_position(0, Vector3(-1.0, 0.0, 0.0))
	_expect(saved_path.point_widths[0] == 2.0 and
		saved_path.curve.get_point_position(0) == Vector3.ZERO,
		"duplicated width controls own independent arrays and curves")
	var packed := PackedScene.new()
	_expect(packed.pack(holder) == OK and ResourceSaver.save(packed, RELOAD_PATH) == OK,
		"width overrides can be saved")
	var reopened_scene := ResourceLoader.load(RELOAD_PATH, "PackedScene",
		ResourceLoader.CACHE_MODE_IGNORE) as PackedScene
	var reopened := reopened_scene.instantiate()
	_expect(reopened.get_node("Original").point_widths[0] == 2.0 and
		reopened.get_node("Copy").point_widths[0] == 8.0,
		"independent width arrays survive save and reload")
	reopened.free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(RELOAD_PATH))

	var pilot := PILOT.instantiate()
	root.add_child(pilot)
	await process_frame
	await process_frame
	var road := pilot.get_node("AuthoredControls/Road") as Path3D
	road.curve = _straight_curve(Vector3(-10.0, 0.0, 15.0), Vector3(10.0, 0.0, 15.0))
	road.call("sync_curve_binding")
	road.point_widths = PackedFloat32Array([2.0, 6.0])
	var river := pilot.get_node("AuthoredControls/River") as Path3D
	river.curve = _straight_curve(Vector3(0.0, 0.0, -10.0), Vector3(0.0, 0.0, 10.0))
	river.call("sync_curve_binding")
	river.point_widths = PackedFloat32Array([2.0, 8.0])
	pilot.refresh_all()
	await process_frame
	var road_mesh := pilot.get_node("GeneratedPreview/Road/RoadSurface") as MeshInstance3D
	_expect(road_mesh.get_aabb().size.z > 5.9,
		"generated road geometry expands to the authored endpoint width")
	_expect(pilot.call("_encoded_floor", 3.25, 9.0) == 0 and
		pilot.call("_encoded_floor", 3.25, -9.0) > 0,
		"river taper drives the exported wet mask at narrow and wide ends")
	var river_mesh := pilot.get_node("GeneratedPreview/Water/River") as MeshInstance3D
	_expect(river_mesh != null and river_mesh.mesh.get_surface_count() == 1,
		"a tapered river builds one stable water surface")

	print("map authoring path widths: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	path.queue_free()
	holder.queue_free()
	pilot.queue_free()
	quit(_failures)


func _make_width_path(points: Array[Vector3], widths: PackedFloat32Array) -> Path3D:
	var path := Path3D.new()
	path.set_script(WIDTH_PATH)
	var authored_curve := Curve3D.new()
	for point in points:
		authored_curve.add_point(point)
	path.curve = authored_curve
	path.point_widths = widths
	return path


func _straight_curve(a: Vector3, b: Vector3) -> Curve3D:
	var result := Curve3D.new()
	result.add_point(a)
	result.add_point(b)
	return result


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
