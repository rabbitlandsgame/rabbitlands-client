extends SceneTree
## A descent's fog of war and boss reward on the real Serpent Deep package
## (serpent_deep_descent) in the complete client: Main loads the package as for
## a player, the player stands at floor f1v1's landing, and the server's
## ELORIA_DESCENT_STATE (188) packets arrive through AppState._on_packet.
##
## The packets come from a JSON file (ELORIA_DESCENT_FOG_PACKETS, absolute
## path) written from the server's own generator and reveal rules:
##   {landing: [x, y], second: [x, y], first: <state>, secondState: <state>,
##    reward: <reward>}
## `first` reveals the landing room (and two cells of rock round it);
## `secondState` the walk on into the next room.
##
## Saves under <out>/ (ELORIA_ARTIFACT_DIR, default res://test-artifacts/descent-fog):
##   fog-a-game.png (with the minimap), fog-a-fullmap.png, fog-a-top.png   the landing revealed
##   fog-c-game.png, fog-c-fullmap.png, fog-c-top.png, fog-c-second-room.png  one more room revealed
##   fog-d-reward.png                                                       the boss reward's pick of three
## Rendered only (needs a display; one GPU job at a time on the laptop):
##   godot --log-file <log> --path godot-client --script res://tests/integration/rendered_descent_fog.gd
## Set ELORIA_NO_GEOMETRY_CACHE=1 (the descent always loads raw). Exit 0 when
## every check held and every capture was written.
const SOURCE := "res://../eloria-assets/maps/continent-v2/_continent_v2/content/serpent_deep_descent.json"
const INTERIOR := "serpent_deep_descent"
const SECTION := "serpent_deep_f1v1"
const SIZE := Vector2i(1600, 900)
const PLAYER_ID := 1
const DESCENT_STATE := 188

var main: Control
var state: Node
var out := ""
var packets: Dictionary = {}
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/descent-fog")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = SIZE
	var source := OS.get_environment("ELORIA_DESCENT_FOG_PACKETS")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(source)) if not source.is_empty() else null
	_expect(parsed is Dictionary, "the fog packets read from ELORIA_DESCENT_FOG_PACKETS")
	if parsed is not Dictionary:
		_finish()
		return
	packets = parsed
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	var ready_deadline := Time.get_ticks_msec() + 1800000
	while (main.get("map_registry") as Dictionary).is_empty() and Time.get_ticks_msec() < ready_deadline:
		await process_frame
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	if not (main.get("minimap_frame") as Control).visible:
		main.call("_toggle_minimap")
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	var landing := Vector2i(int(packets.landing[0]), int(packets.landing[1]))
	if not await _enter(landing):
		_finish()
		return
	# (a) the landing room revealed
	_packet(packets.first)
	await _settle(60)
	_expect(not (state.get("descent") as Dictionary).is_empty(), "AppState holds the descent state")
	var fog: Variant = main.get("_descent_fog_node")
	_expect(fog is MeshInstance3D and is_instance_valid(fog) and (fog as MeshInstance3D).visible,
		"the fog volume stands over the floor")
	await _views("a")
	# (c) one more room revealed: the same views, then from inside that room
	_packet(packets.secondState)
	await _settle(60)
	await _views("c")
	await _place(Vector2i(int(packets.second[0]), int(packets.second[1])))
	await _settle(60)
	await _capture("fog-c-second-room.png", true)
	# (d) the boss reward's pick of three
	_packet(packets.reward)
	await _settle(30)
	_expect(not (state.get("descent_reward") as Dictionary).is_empty(), "AppState holds the reward offer")
	await _capture("fog-d-reward.png", true)
	_finish()

func _packet(body: Dictionary) -> void:
	state.call("_on_packet", DESCENT_STATE, JSON.stringify(body).to_utf8_buffer())

## The game view (window, with the minimap), the full map and a top-down view.
func _views(prefix: String) -> void:
	var rig: Node3D = main.get("camera_rig")
	rig.set("yaw_degrees", 0.0)
	await _settle(20)
	await _capture("fog-%s-game.png" % prefix, true)
	main.call("_toggle_full_map")
	await _settle(30)
	await _capture("fog-%s-fullmap.png" % prefix, true)
	main.call("_toggle_full_map")
	await _settle(10)
	await _top("fog-%s-top.png" % prefix)

## Straight down over the section, north up, 3D viewport only.
func _top(name: String) -> void:
	var loader: WorldLoader = main.get("world_loader")
	var bounds: Dictionary = {}
	for listed: Dictionary in loader.manifest.data.sections:
		if str(listed.id) == SECTION:
			bounds = listed.bounds
	var lo: Array = bounds.get("min", [0, 0])
	var hi: Array = bounds.get("max", [1, 1])
	var rig: Node3D = main.get("camera_rig")
	var rig_camera: Camera3D = rig.get("camera")
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = maxf(float(hi[1]) - float(lo[1]), (float(hi[0]) - float(lo[0])) * float(SIZE.y) / float(SIZE.x)) + 4.0
	camera.near = 0.5
	camera.far = 200.0
	camera.cull_mask = rig_camera.cull_mask
	rig.get_parent().add_child(camera)
	camera.global_transform = Transform3D(Basis.looking_at(Vector3.DOWN, Vector3.FORWARD),
		Vector3((float(lo[0]) + float(hi[0])) / 2.0, 40.0, (float(lo[1]) + float(hi[1])) / 2.0))
	camera.make_current()
	await _settle(20)
	await _capture(name, false)
	rig_camera.make_current()
	camera.queue_free()
	await process_frame

## Changes map as the server's CHANGE_MAP would and stands the player and the
## floor's door and stair portals on it.
func _enter(tile: Vector2i) -> bool:
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("map_objects", {})
	state.set("current_map", INTERIOR)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 180000
	while Time.get_ticks_msec() < deadline and not (loader.world_root != null and loader.manifest != null
			and loader.manifest.asset_id() == INTERIOR and str(main.get("loaded_server_map")) == INTERIOR):
		await process_frame
	var loaded := loader.manifest != null and loader.manifest.asset_id() == INTERIOR
	_expect(loaded, "%s loads through Main" % INTERIOR)
	if not loaded:
		return false
	var plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
	var objects := {}
	for section: Dictionary in plan.sections:
		for door: Dictionary in section.get("entrances", []):
			objects[int(door.object)] = _object(int(door.object), door.exit, "Portal", "Up to the temple.")
	for passage: Dictionary in plan.get("passages", []):
		var ends: Array = passage.ends
		for end_index: int in ends.size():
			var end: Dictionary = ends[end_index]
			objects[int(passage.object) + end_index] = _object(int(passage.object) + end_index, end.tile, "Portal",
				str(end.get("label", "")) + ".")
	var actors := {PLAYER_ID: {"actor_id": PLAYER_ID, "x": tile.x, "y": tile.y, "rotation": 0, "actor_type": 0,
		"kind": 1, "name": "Traveller", "health": 100, "max_health": 100, "alive": true, "appearance": {}}}
	state.set("map_objects", objects)
	state.set("local_actor_id", PLAYER_ID)
	state.set("actors", actors)
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	main.call("_sync_map_objects")
	deadline = Time.get_ticks_msec() + 120000
	var curtain: Object = main.get("arrival_curtain")
	while Time.get_ticks_msec() < deadline and ((main.get("actor_nodes") as Dictionary).size() < 1
			or bool(curtain.call("is_showing"))):
		main.call("_sync_world", state.call("take_changed_actors"))
		await process_frame
	_expect(not bool(curtain.call("is_showing")), "the arrival curtain lifts")
	await _settle(30)
	return true

func _object(id: int, tile: Variant, label: String, detail: String) -> Dictionary:
	return {"object_id": id, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x": int(tile[0]), "y": int(tile[1]), "label": label, "detail": detail}

func _place(tile: Vector2i) -> void:
	var record: Dictionary = (state.get("actors") as Dictionary)[PLAYER_ID]
	record.x = tile.x
	record.y = tile.y
	state.call("mark_all_actors_changed")
	main.call("_sync_world", state.call("take_changed_actors"))
	var target := (main.get("adapter") as CoordinateAdapter).tile_center(tile.x, tile.y)
	for frame: int in 400:
		await process_frame
		var node: Node3D = (main.get("actor_nodes") as Dictionary).get(PLAYER_ID)
		if is_instance_valid(node) and Vector2(node.global_position.x, node.global_position.z).distance_to(
				Vector2(target.x, target.z)) < 0.3:
			break

func _settle(frames: int) -> void:
	for frame: int in frames:
		await physics_frame
		await process_frame

func _capture(name: String, whole: bool) -> Image:
	await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image() if whole \
		else (main.get("main_viewport") as SubViewport).get_texture().get_image()
	var saved := image != null and image.save_png(out.path_join(name)) == OK
	_expect(saved, "saved " + name)
	print("DESCENT_FOG_CAPTURE ", name, " shown_section=",
		str((main.get("secret_sections") as RefCounted).call("current_section")))
	return image

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: " + message)
		return
	failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("rendered descent fog: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
