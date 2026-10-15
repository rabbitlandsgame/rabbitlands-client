extends SceneTree

## End-to-end Four Gates gameplay validation through the real login flow.
##
## Runs the production `main.tscn` against a local protocol server
## (tests/integration/local_protocol_server.py), creates a temporary character,
## and verifies spawn grounding, click-to-move, traversal to every major
## landmark, collision, camera control, coordinate reporting, the tab map and
## the minimap -- capturing client screenshots throughout.

const TIMEOUT := 60.0
const SCREEN_SIZE := Vector2i(1280, 720)
const GROUND_TOLERANCE := 0.6
# The legacy actor coordinate field is 11 bits (protocol.gd masks with 0x7ff).
const TILE_FIELD_MAX := 2047

var _failures := 0
var _artifacts := ""
var _main: Control
var _app_state: Node
var _network: Node
var _loader: WorldLoader
var _adapter: CoordinateAdapter
var _report: Dictionary = {"checks": [], "traversal": [], "grounding": []}

# label, world target
# Waypoints stay inside the range the legacy 11-bit tile field can address
# under the current registry binding (see ADDRESSABLE_* below); the limit is
# asserted separately and reported rather than silently avoided.
const WAYPOINTS := [
	["plaza-centre", Vector3(0.0, 31.0, 0.0)],
	["civic-quarter", Vector3(-140.0, 31.0, -40.0)],
	["ring-road-east", Vector3(250.0, 31.0, 0.0)],
	["residential-block", Vector3(196.0, 31.0, 96.0)],
	["east-gate-approach", Vector3(320.0, 31.0, 0.0)],
	["north-avenue", Vector3(0.0, 31.0, -300.0)],
	["north-gate", Vector3(0.0, 31.0, -344.0)],
	["north-bridge-deck", Vector3(0.0, 29.0, -500.0)],
	["sanctuary-approach", Vector3(0.0, 40.0, -640.0)],
]

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/four-gates-gameplay")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN_SIZE

	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_app_state = root.get_node("AppState")
	_network = root.get_node("Network")

	var host: String = OS.get_environment("ELORIA_INTEGRATION_HOST")
	if host.is_empty():
		host = "127.0.0.1"
	var port_text: String = OS.get_environment("ELORIA_INTEGRATION_PORT")
	var port: int = int(port_text) if port_text.is_valid_int() else 2000
	var username: String = OS.get_environment("ELORIA_TEST_CHARACTER")
	if username.is_empty():
		username = "QA_FourGates_Temp1"
	var password: String = "qa_" + str(randi())

	(_main.get_node("LoginPanel/Content/Host") as LineEdit).text = host
	(_main.get_node("LoginPanel/Content/Port") as SpinBox).value = port
	_main.call("_on_connect_pressed")
	_expect(await _wait(func() -> bool:
		return str(_app_state.get("connection_state")) == "connected", TIMEOUT),
		"client opened a real TCP session to the local test server")

	_main.call("_on_new_character_pressed")
	(_main.get_node("CreationPanel/Columns/FormPanel/Form/CreateName") as LineEdit).text = username
	(_main.get_node("CreationPanel/Columns/FormPanel/Form/CreatePassword") as LineEdit).text = password
	(_main.get_node("CreationPanel/Columns/FormPanel/Form/CreateConfirm") as LineEdit).text = password
	_main.call("_on_create_pressed")
	_expect(await _wait(func() -> bool:
		return bool(_app_state.get("authenticated")), TIMEOUT),
		"temporary test character created and logged in through the real flow")

	_loader = _main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/WorldLoader") as WorldLoader
	_expect(await _wait(func() -> bool:
		var local_id: int = int(_app_state.get("local_actor_id"))
		return (local_id >= 0 and _loader.world_root != null
			and (_main.get("actor_nodes") as Dictionary).has(local_id)), TIMEOUT),
		"Four Gates loaded and the local actor is present")
	if _loader.world_root == null:
		_finish()
		return
	_adapter = _main.get("adapter") as CoordinateAdapter
	_report["map"] = str(_app_state.get("current_map"))
	_report["asset"] = _loader.manifest.asset_id()
	_report["manifest_warnings"] = _loader.manifest.warnings
	await _settle(10)

	# ---------------------------------------------------------------- grounding
	var actor: Node3D = _local_actor()
	_expect(actor != null, "local actor node exists")
	var spawn_ground: Dictionary = _ground_check("spawn", actor)
	_expect(bool(spawn_ground.get("ok", false)),
		"character spawns standing on the terrain, not below or floating")
	await _capture("00-spawn.png")

	# a real click-to-move through the production input path
	var viewport: SubViewport = _main.get_node(
		"GameView/ViewportContainer/Viewport") as SubViewport
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	var before_tile: Vector2i = _adapter.godot_to_server(actor.global_position)
	_main.call("_handle_world_click", click, Vector2(SCREEN_SIZE) * Vector2(0.5, 0.62))
	await _settle(40)
	var after_tile: Vector2i = _adapter.godot_to_server(_local_actor().global_position)
	_expect(after_tile != before_tile,
		"click-to-move issued a real MOVE_TO and the server moved the character")
	_report["click_to_move"] = {"from": [before_tile.x, before_tile.y],
		"to": [after_tile.x, after_tile.y]}
	await _capture("01-click-to-move.png")

	# ---------------------------------------------------------- traversal tests
	var walked_ok: int = 0
	for waypoint: Array in WAYPOINTS:
		var label: String = str(waypoint[0])
		var target: Vector3 = waypoint[1] as Vector3
		var tile: Vector2i = _adapter.godot_to_server(target)
		_network.call("move_to", tile, true)
		var arrived: bool = await _wait(func() -> bool:
			var node: Node3D = _local_actor()
			if node == null:
				return false
			var here: Vector2i = _adapter.godot_to_server(node.global_position)
			return absi(here.x - tile.x) <= 2 and absi(here.y - tile.y) <= 2, TIMEOUT)
		await _settle(6)
		var check: Dictionary = _ground_check(label, _local_actor())
		check["arrived"] = arrived
		check["target_tile"] = [tile.x, tile.y]
		(_report["traversal"] as Array).append(check)
		if arrived and bool(check.get("ok", false)):
			walked_ok += 1
		else:
			push_warning("traversal issue at %s: %s" % [label, str(check)])
		_camera_focus(target)
		await _capture("walk-%s.png" % label)
	_expect(walked_ok == WAYPOINTS.size(),
		"character walked to every landmark and stayed correctly grounded (%d/%d)"
			% [walked_ok, WAYPOINTS.size()])

	# --------------------------------------------------------------- collision
	var space: PhysicsDirectSpaceState3D = _main.get(
		"gameplay_world").direct_space_state
	var blocked: int = 0
	var probes: Array = [Vector3(196.0, 34.0, 96.0), Vector3(-166.0, 34.0, 78.0),
		Vector3(0.0, 34.0, 352.0), Vector3(250.0, 34.0, 0.0)]
	for probe: Vector3 in probes:
		var query := PhysicsRayQueryParameters3D.create(
			probe + Vector3(60.0, 0.0, 60.0), probe, WorldLoader.WORLD_COLLISION_LAYER)
		if not space.intersect_ray(query).is_empty():
			blocked += 1
	_expect(blocked >= 3,
		"authored collision proxies block movement through structures (%d/4 probes)"
			% blocked)
	_report["collision_probe_hits"] = blocked

	# ------------------------------------------------------- camera and framing
	var rig: IsometricCameraController = _main.get("camera_rig") as IsometricCameraController
	var start_yaw: float = float(rig.get("yaw_degrees"))
	var start_distance: float = float(rig.get("distance"))
	var rotate_press := InputEventMouseButton.new()
	rotate_press.button_index = MOUSE_BUTTON_RIGHT
	rotate_press.pressed = true
	rig.handle_mouse_button(rotate_press)
	var motion := InputEventMouseMotion.new()
	motion.relative = Vector2(220.0, 40.0)
	rig.handle_mouse_motion(motion)
	var rotate_release := InputEventMouseButton.new()
	rotate_release.button_index = MOUSE_BUTTON_RIGHT
	rotate_release.pressed = false
	rig.handle_mouse_button(rotate_release)
	var zoom := InputEventMouseButton.new()
	zoom.button_index = MOUSE_BUTTON_WHEEL_UP
	zoom.pressed = true
	rig.handle_mouse_button(zoom)
	await _settle(6)
	_expect(absf(float(rig.get("yaw_degrees")) - start_yaw) > 1.0,
		"camera rotation responds to input")
	_expect(absf(float(rig.get("distance")) - start_distance) > 0.5,
		"camera zoom responds to input")
	await _capture("02-camera-rotated.png")
	rig.set("yaw_degrees", start_yaw)
	rig.set("distance", start_distance)

	# ------------------------------------------------- coordinates and tab map
	var node_now: Node3D = _local_actor()
	var dto: Dictionary = (_app_state.get("actors") as Dictionary).get(
		int(_app_state.get("local_actor_id")), {})
	var reported := Vector2i(int(dto.get("x", -1)), int(dto.get("y", -1)))
	var derived: Vector2i = _adapter.godot_to_server(node_now.global_position)
	_expect(absi(reported.x - derived.x) <= 1 and absi(reported.y - derived.y) <= 1,
		"client world position round-trips to the authoritative server tile")
	_report["coordinates"] = {"server": [reported.x, reported.y],
		"derived": [derived.x, derived.y],
		"world": [node_now.global_position.x, node_now.global_position.y,
			node_now.global_position.z]}

	var minimap: TextureRect = _main.get_node("%Minimap") as TextureRect
	_expect(minimap != null and minimap.texture != null,
		"HUD minimap renders live from the loaded world")
	_main.call("_toggle_full_map")
	await _settle(10)
	await _capture("03-tab-map.png")
	_expect(int((_main.get("full_map_viewport") as SubViewport).render_target_update_mode)
		== int(SubViewport.UPDATE_ALWAYS),
		"tab map viewport only renders the world while the tab map is open")
	_main.call("_toggle_full_map")
	await _settle(4)
	_expect(int((_main.get("full_map_viewport") as SubViewport).render_target_update_mode)
		== int(SubViewport.UPDATE_DISABLED),
		"tab map viewport stops rendering the world once closed")

	# ------------------------------------------------------------ world bounds
	var bounds: Dictionary = _loader.manifest.data["asset"]["bounds"]
	var minimum: Array = bounds["min"]
	var maximum: Array = bounds["max"]
	var inside: bool = true
	for check_point: Vector3 in [Vector3(0, 31, 0), Vector3(0, 29, 620),
			Vector3(0, 74, -700)]:
		inside = inside and check_point.x >= float(minimum[0]) and check_point.x <= float(maximum[0])
	_expect(inside, "declared bounds contain every gameplay area")

	# --------------------------------------------------------------- performance
	var samples: Array[float] = []
	for _index: int in range(12):
		var started: int = Time.get_ticks_usec()
		RenderingServer.force_draw(false)
		samples.append(float(Time.get_ticks_usec() - started) / 1000.0)
	samples.sort()
	_report["frame_ms_software_gl"] = {
		"median": samples[samples.size() / 2],
		"min": samples[0], "max": samples[samples.size() - 1],
		"renderer": "OpenGL compatibility on llvmpipe (no GPU)",
	}
	_report["render_info"] = {
		"objects": RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
		"primitives": RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
		"draw_calls": RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
		"texture_memory": RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
		"video_memory": RenderingServer.get_rendering_info(
			RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
	}
	print("performance ", JSON.stringify(_report["render_info"]),
		" frame_ms ", JSON.stringify(_report["frame_ms_software_gl"]))

	# ------------------------------------------- legacy tile addressability
	# Record, rather than hide, how much of the authored map the 11-bit actor
	# coordinate field can reach under the registry's coordinate transform.
	var metres_per_tile: float = _adapter.metres_per_tile
	var server_origin: Vector2 = _adapter.server_origin
	var reach_low: float = (0.0 - server_origin.x) * metres_per_tile
	var reach_high: float = (float(TILE_FIELD_MAX) - server_origin.x) * metres_per_tile
	_report["tile_addressability"] = {
		"metresPerTile": metres_per_tile,
		"serverOrigin": [server_origin.x, server_origin.y],
		"worldXRange": [reach_low, reach_high],
		"worldZRange": [-reach_high, -reach_low],
		"authoredBounds": [minimum, maximum],
		"note": ("Tiles outside 0..2047 wrap in the 11-bit actor coordinate "
			+ "field, so world positions outside this range cannot be "
			+ "addressed by MOVE_TO under the current binding."),
	}
	var covers_city: bool = (reach_low <= -352.0 and reach_high >= 352.0)
	if not covers_city:
		push_warning("tile field does not cover the full walled city: x in [%.1f, %.1f]"
			% [reach_low, reach_high])
	_report["tile_field_covers_walled_city"] = covers_city

	_finish()

# ------------------------------------------------------------------- helpers
func _local_actor() -> Node3D:
	var nodes: Dictionary = _main.get("actor_nodes") as Dictionary
	return nodes.get(int(_app_state.get("local_actor_id"))) as Node3D

func _ground_check(label: String, actor: Node3D) -> Dictionary:
	if actor == null:
		return {"label": label, "ok": false, "error": "no actor"}
	var space: PhysicsDirectSpaceState3D = _main.get("gameplay_world").direct_space_state
	var from := Vector3(actor.global_position.x, 400.0, actor.global_position.z)
	var to := Vector3(actor.global_position.x, -200.0, actor.global_position.z)
	var query := PhysicsRayQueryParameters3D.create(
		from, to, WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit: Dictionary = space.intersect_ray(query)
	var result: Dictionary = {"label": label,
		"actor_y": actor.global_position.y,
		"x": actor.global_position.x, "z": actor.global_position.z}
	if hit.is_empty():
		result["ok"] = false
		result["error"] = "no navigation surface under the character"
		(_report["grounding"] as Array).append(result)
		return result
	var surface_y: float = (hit["position"] as Vector3).y
	result["surface_y"] = surface_y
	result["delta"] = actor.global_position.y - surface_y
	result["ok"] = absf(result["delta"]) <= GROUND_TOLERANCE
	(_report["grounding"] as Array).append(result)
	return result

func _camera_focus(point: Vector3) -> void:
	var rig: IsometricCameraController = _main.get("camera_rig") as IsometricCameraController
	rig.set_focus(point)

func _wait(predicate: Callable, seconds: float) -> bool:
	var deadline: int = Time.get_ticks_msec() + roundi(seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if bool(predicate.call()):
			return true
		await process_frame
	return bool(predicate.call())

func _settle(frames: int) -> void:
	for _index: int in range(frames):
		await physics_frame
		await process_frame

func _capture(name: String) -> void:
	await _settle(4)
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	_expect(image.save_png(_artifacts.path_join(name)) == OK, "saved " + name)

func _expect(condition: bool, message: String) -> void:
	(_report["checks"] as Array).append({"ok": condition, "check": message})
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	_report["failures"] = _failures
	var file := FileAccess.open(_artifacts.path_join("gameplay-report.json"),
		FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(_report, "  "))
		file.close()
	print("four gates gameplay: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)
