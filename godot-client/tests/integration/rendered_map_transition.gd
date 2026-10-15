extends SceneTree

## Walks a temporary character through a real map transition: city -> interior
## -> city, driven by authoritative CHANGE_MAP frames, asserting the interior
## loads, the character is grounded inside it, and the return lands correctly.

const TIMEOUT := 90.0
const SCREEN := Vector2i(1280, 720)
const GROUND_TOLERANCE := 0.6
const INTERIOR := "four-gates-lantern-row"
const CITY := "four_gates"

var _failures := 0
var _artifacts := ""
var _main: Control
var _state: Node
var _network: Node
var _loader: WorldLoader
var _report: Dictionary = {"checks": [], "transitions": []}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/transition")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_state = root.get_node("AppState")
	_network = root.get_node("Network")

	var host: String = OS.get_environment("ELORIA_INTEGRATION_HOST")
	if host.is_empty():
		host = "127.0.0.1"
	var port_text: String = OS.get_environment("ELORIA_INTEGRATION_PORT")
	var port: int = int(port_text) if port_text.is_valid_int() else 2000
	var user: String = "QA_FourGates_Door1"
	var password: String = "qa_" + str(randi())

	(_main.get_node("LoginPanel/Content/Host") as LineEdit).text = host
	(_main.get_node("LoginPanel/Content/Port") as SpinBox).value = port
	_main.call("_on_connect_pressed")
	_expect(await _wait(func() -> bool:
		return str(_state.get("connection_state")) == "connected", TIMEOUT),
		"connected to the local test server")
	_main.call("_on_new_character_pressed")
	(_main.get_node("CreationPanel/Columns/FormPanel/Form/CreateName") as LineEdit).text = user
	(_main.get_node("CreationPanel/Columns/FormPanel/Form/CreatePassword") as LineEdit).text = password
	(_main.get_node("CreationPanel/Columns/FormPanel/Form/CreateConfirm") as LineEdit).text = password
	_main.call("_on_create_pressed")
	_expect(await _wait(func() -> bool:
		return bool(_state.get("authenticated")), TIMEOUT),
		"temporary character logged in")
	_loader = _main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/WorldLoader") as WorldLoader
	_expect(await _on_map(CITY), "started in the city")
	await _settle(8)
	await _capture("00-city-before.png")

	# the city manifest must actually describe the door we are about to use
	var interiors: Array = _loader.manifest.data.get("interiors", []) as Array
	_expect(interiors.size() >= 6,
		"city manifest lists its interiors (%d)" % interiors.size())
	var door: Dictionary = {}
	for entry_value: Variant in interiors:
		if entry_value is Dictionary and str((entry_value as Dictionary).get("map", "")) == INTERIOR:
			door = entry_value as Dictionary
	_expect(not door.is_empty(), "the target interior has a door on the street")
	if not door.is_empty():
		var node: Node = _loader.world_root.find_child(
			str(door.get("doorNode", "")), true, false)
		_expect(node != null, "the door node named by the manifest exists in the GLB")

	# --- city -> interior -------------------------------------------------
	_network.call("send_chat", "#goto %s 512,502" % INTERIOR)
	_expect(await _on_map(INTERIOR), "authoritative CHANGE_MAP moved us inside")
	await _settle(12)
	var inside: Dictionary = _ground("interior")
	_expect(bool(inside.get("ok", false)),
		"character is grounded on the interior floor, not the city terrain")
	_expect(_loader.manifest.asset_id() == "four-gates-lantern-row",
		"the interior package loaded, not a fallback")
	var lit: Array = _loader.get_tree().get_nodes_in_group(
		WorldEnvironmentBinder.MANIFEST_LIGHT_GROUP)
	var lamps: int = lit.size()
	_expect(lamps > 0, "interior manifest lights are lit (%d)" % lamps)
	await _capture("01-interior.png")

	# --- interior -> city -------------------------------------------------
	_network.call("send_chat", "#goto %s 384,266" % CITY)
	_expect(await _on_map(CITY), "the exit portal returned us to the city")
	await _settle(12)
	var back: Dictionary = _ground("returned")
	_expect(bool(back.get("ok", false)),
		"character is grounded again on the city terrain after returning")
	_expect(_loader.manifest.asset_id() == "four-gates",
		"the city package reloaded")
	await _capture("02-city-after.png")

	_report["failures"] = _failures
	var file := FileAccess.open(_artifacts.path_join("transition-report.json"),
		FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(_report, "  "))
		file.close()
	print("four gates map transition: ", "PASS" if _failures == 0 else "FAIL")
	quit(_failures)

func _on_map(name: String) -> bool:
	return await _wait(func() -> bool:
		return (str(_state.get("current_map")) == name
			and _loader.world_root != null
			and (_main.get("actor_nodes") as Dictionary).has(
				int(_state.get("local_actor_id")))), TIMEOUT)

func _ground(label: String) -> Dictionary:
	var nodes: Dictionary = _main.get("actor_nodes") as Dictionary
	var actor: Node3D = nodes.get(int(_state.get("local_actor_id"))) as Node3D
	var result: Dictionary = {"label": label, "map": str(_state.get("current_map"))}
	if actor == null:
		result["ok"] = false
		(_report["transitions"] as Array).append(result)
		return result
	var space: PhysicsDirectSpaceState3D = _main.get("gameplay_world").direct_space_state
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(actor.global_position.x, 400.0, actor.global_position.z),
		Vector3(actor.global_position.x, -200.0, actor.global_position.z),
		WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit: Dictionary = space.intersect_ray(query)
	result["actor_y"] = actor.global_position.y
	if hit.is_empty():
		result["ok"] = false
		result["error"] = "no navigation surface"
	else:
		result["surface_y"] = (hit["position"] as Vector3).y
		result["delta"] = actor.global_position.y - float(result["surface_y"])
		result["ok"] = absf(result["delta"]) <= GROUND_TOLERANCE
	(_report["transitions"] as Array).append(result)
	return result

func _wait(predicate: Callable, seconds: float) -> bool:
	var deadline: int = Time.get_ticks_msec() + roundi(seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if bool(predicate.call()):
			return true
		await process_frame
	return bool(predicate.call())

func _settle(frames: int) -> void:
	for _i: int in range(frames):
		await physics_frame
		await process_frame

func _capture(name: String) -> void:
	await _settle(4)
	RenderingServer.force_draw(false)
	_expect(root.get_texture().get_image().save_png(_artifacts.path_join(name)) == OK,
		"saved " + name)

func _expect(condition: bool, message: String) -> void:
	(_report["checks"] as Array).append({"ok": condition, "check": message})
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)
