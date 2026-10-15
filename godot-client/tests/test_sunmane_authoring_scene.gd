extends SceneTree

const SCENE := preload("res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn")
const REGION_SCRIPT := preload("res://src/dev/map_authoring_region/region_control.gd")
const TERRAIN_SCRIPT := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const PATH_SCRIPT := preload("res://src/dev/map_authoring_region/path_control.gd")
const ASSET_SCRIPT := preload("res://src/dev/map_authoring_region/asset_control.gd")
const MARKER_SCRIPT := preload("res://src/dev/map_authoring_region/gameplay_marker.gd")

var assertions := 0
var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var region := SCENE.instantiate()
	root.add_child(region)
	await process_frame
	_check(region.get_script() == REGION_SCRIPT, "scene root uses the region authoring control")
	_check(region.region_id == "sunmane_steppe", "region identity survives load")
	_check(region.continent_translation == Vector3(1200.0, 0.0, 720.0),
		"continent translation is the explicit shared-world adapter")
	_check(region.server_origin == Vector2i(194, 292), "server tile origin stays distinct")
	_check(region.collision_origin_metres == Vector2(-194.0, 292.0),
		"collision origin stays distinct")
	_check(region.owned_route_ids.size() == 19, "all current Sunmane routes stay owned")
	_check(region.owned_plan_feature_ids == PackedStringArray(["southern_river"]),
		"river replacement persists independently of its path node")

	var terrain := region.get_node("Terrain")
	_check(terrain.get_script() == TERRAIN_SCRIPT, "terrain is an editable control")
	_check(terrain.grid_size == Vector2i(397, 397) and is_equal_approx(terrain.cell_metres, 2.0),
		"terrain uses the shared 2 metre grid")
	_check(terrain.base_heights().size() == 397 * 397,
		"terrain loads a complete editable base grid")

	var roads := _children_with_script(region.get_node("Roads"), PATH_SCRIPT)
	var rivers := _children_with_script(region.get_node("Rivers"), PATH_SCRIPT)
	_check(roads.size() >= 5 and rivers.size() <= 1, "required routes and optional river load")
	if not rivers.is_empty():
		var river = rivers[0]
		_check(river.path_id == "southern_river", "optional river keeps its replacement identity")
		_check(river.properties.has("channelDepth") and river.properties.has("valleyWidth"),
			"river grading parameters are explicit in the scene")
	var required_ids := PackedStringArray([
		"mirrorhold--sunmane_steppe-sunmane_steppe",
		"amethyst_barrens--sunmane_steppe-sunmane_steppe",
		"sunmane_steppe--verdant_stair-sunmane_steppe",
		"door-sunmane_steppe-cave-wind_caves",
		"door-sunmane_steppe-cave-crystal_hollow",
	])
	var loaded_required := {}
	for road in roads:
		_check(road.replaces_route_id == road.path_id or \
				(road.replaces_route_id.is_empty() and road.routing_role == "decorative"),
			"road replacement stays explicit or is a local decorative route: %s" % road.path_id)
		if required_ids.has(road.path_id):
			loaded_required[road.path_id] = true
	_check(loaded_required.size() == required_ids.size(), "all required seam and cave routes load")
	var east_ramp := region.get_node("Roads/east-gate-town-ramp")
	_check(east_ramp.get_script() == PATH_SCRIPT and east_ramp.routing_role == "decorative" and \
			east_ramp.replaces_route_id.is_empty(),
		"the East gate ramp stays an authored local connector")
	_check(east_ramp.curve.point_count == 4 and \
			east_ramp.curve.get_point_position(0).is_equal_approx(
				Vector3(4.5, 29.82, -17.5)) and \
			east_ramp.curve.get_point_position(1).is_equal_approx(
				Vector3(2.5, 28.91, -14.5)) and \
			east_ramp.curve.get_point_position(3).is_equal_approx(
				Vector3(8.5, 26.75, -16.5)),
		"the East gate ramp keeps its graded town and gate landings")
	var east_main_ramp := region.get_node("Roads/east-gate-main-ramp")
	_check(east_main_ramp.get_script() == PATH_SCRIPT and \
			east_main_ramp.routing_role == "decorative" and \
			east_main_ramp.replaces_route_id.is_empty() and \
			east_main_ramp.curve.point_count == 3,
		"the East outer ramp stays a local decorative connector")
	_check(east_main_ramp.curve.get_point_position(0).is_equal_approx(
			Vector3(14.5, 28.0384373665, -23.5)) and \
			east_main_ramp.curve.get_point_position(2).is_equal_approx(
				Vector3(15.5, 28.4254174232, -24.5)),
		"the East outer ramp keeps its certified gate and main landings")
	var hall_bridge := region.get_node("Bridges/SteppeHallAccess")
	_check(is_equal_approx(hall_bridge.width, 2.5) and \
			is_equal_approx(hall_bridge.arch, 0.15),
		"the steppe hall access keeps its actor-clear deck profile")
	_check(hall_bridge.get_node("Start").position.is_equal_approx(
			Vector3(-28.88, 27.0, -18.88)) and \
			hall_bridge.get_node("End").position.is_equal_approx(
				Vector3(-26.5, 28.254822, -16.5)),
		"the steppe hall access keeps its certified component landings")

	var assets := _children_with_script(region.get_node("AuthoredAssets"), ASSET_SCRIPT)
	var asset_ids := {}
	for asset in assets:
		asset_ids[asset.asset_id] = true
		_check(asset.content_root() != null, "asset prototype loads: %s" % asset.asset_id)
	_check(asset_ids.size() == assets.size(), "authored object identities are unique")

	var markers: Array = []
	for child in region.get_node("Gameplay").find_children("*", "", true, false):
		if child.get_script() == MARKER_SCRIPT:
			markers.append(child)
	_check(not markers.is_empty(), "gameplay records are editable markers")
	var followed := 0
	var runtime_points := 0
	var runtime_bindings := 0
	var existing_binding_offsets := 0
	var runtime_point_zero_offsets := 0
	var required_gameplay := {
		"server-arrival": false, "cave-wind_caves": false,
		"cave-crystal_hollow": false, "road-to-mirrorhold": false,
		"road-to-amethyst_barrens": false, "road-to-verdant_stair": false,
	}
	for marker in markers:
		if marker.kind == "runtime_point":
			runtime_points += 1
		runtime_bindings += marker.runtime_bindings.size()
		for binding in marker.runtime_bindings:
			var offset: Variant = binding.get("targetOffset")
			_check(offset is Array and offset.size() == 3 and
				is_zero_approx(float(offset[1])),
				"runtime binding has a horizontal target offset: %s" % binding.get("id", ""))
			if marker.kind == "runtime_point" and offset is Array and offset.size() == 3 and \
					Vector3(float(offset[0]), float(offset[1]), float(offset[2])).is_zero_approx():
				runtime_point_zero_offsets += 1
			elif marker.kind != "runtime_point":
				existing_binding_offsets += 1
		if required_gameplay.has(marker.record_id):
			required_gameplay[marker.record_id] = true
		if not marker.follow_asset_id.is_empty():
			followed += 1
			_check(asset_ids.has(marker.follow_asset_id),
				"gameplay follow target exists: %s" % marker.record_id)
	_check(not required_gameplay.values().has(false), "required spawn and portal identities load")
	_check(followed > 0, "object-bound gameplay markers keep local links")
	_check(markers.size() == 382 and runtime_points == 110,
		"all legacy markers and individually editable runtime points load")
	_check(runtime_bindings == 191,
		"every Sunmane server record has one explicit marker binding")
	_check(existing_binding_offsets == 81 and runtime_point_zero_offsets == 110,
		"existing aliases preserve 81 offsets while 110 RuntimePoints stay exact")

	if failures == 0:
		print("PASS: %d Sunmane authoring assertions" % assertions)
	else:
		push_error("FAIL: %d of %d Sunmane authoring assertions" % [failures, assertions])
	region.queue_free()
	quit(0 if failures == 0 else 1)


func _children_with_script(parent: Node, script: Script) -> Array:
	var result: Array = []
	for child in parent.get_children():
		if child.get_script() == script:
			result.append(child)
	return result


func _check(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		push_error("FAIL: " + message)
		failures += 1
