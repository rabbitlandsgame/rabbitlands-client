extends SceneTree
## The Serpent Deep's procedural floors (descent_layout_v1) in the complete
## client: Main loads the descent's frame package as it does for a player, and
## the server's layouts and states (ELORIA_DESCENT_STATE, 188) arrive through
## AppState._on_packet, so the floors are built by DescentFloors exactly as in
## a run - walk floor, rock faces, stair wells and flights, the themes' kit
## pieces, lamps, cutaway, sections, the minimap picture and the fog. The
## layouts are three floors of one server-generated run
## (tests/fixtures/descent_layouts.json, or ELORIA_DESCENT_LAYOUTS: an absolute
## path to a file of the same shape).
##
## For every floor it saves, under <out>/:
##   <section>-a-game.png    the default game view at the landing: the whole
##                           window, HUD and minimap (switched on)
##   <section>-a-view.png    the same frame, 3D viewport only
##   <section>-b-hall.png    the floor's largest room, pulled back
##   <section>-c-up.png      the way back up (its flight of steps), close
##   <section>-d-down.png    the way down (its well), close; not on the boss floor
##   <section>-e-top.png     a top-down orthographic view of the floor
## and, on the first floor, the fog with only the landing's room revealed:
##   <section>-f-fog-game.png, <section>-f-fog-fullmap.png
## <out>/report.json lists every capture with its tile, section, camera, build
## time and the luminance of its frame (mean of the lit pixels, share of pixels
## below 0.06 and above 0.96), so a dark floor shows in numbers.
##
## Rendered only (needs a display; one GPU job at a time on the laptop):
##   godot --log-file <log> --path godot-client --script res://tests/integration/rendered_descent_floors.gd
## ELORIA_ARTIFACT_DIR picks <out> (default res://test-artifacts/descent-floors).
## Set ELORIA_NO_GEOMETRY_CACHE=1 to skip Main's first-start geometry
## preparation. Exit status 0 when every check held and every capture was written.
const FIXTURE := "res://tests/fixtures/descent_layouts.json"
const INTERIOR := "serpent_deep_descent"
const SIZE := Vector2i(1600, 900)
const PLAYER_ID := 1
const DESCENT_STATE := 188
const DAIS := 59490
const EXIT := 59491

var main: Control
var state: Node
var out := ""
var captures: Array = []
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/descent-floors")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = SIZE
	var source := OS.get_environment("ELORIA_DESCENT_LAYOUTS")
	var text := FileAccess.get_file_as_string(source if not source.is_empty() else FIXTURE)
	var layouts: Array = (JSON.parse_string(text) as Dictionary).layouts
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	var ready_deadline := Time.get_ticks_msec() + 1800000
	while (main.get("map_registry") as Dictionary).is_empty() and Time.get_ticks_msec() < ready_deadline:
		await process_frame
	_expect(not (main.get("map_registry") as Dictionary).is_empty(), "Main has read its map registry")
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	if not (main.get("minimap_frame") as Control).visible:
		main.call("_toggle_minimap")
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	var first: Dictionary = layouts[0]
	if not await _enter(_tile(first._test.landing)):
		await _finish()
		return
	for layout: Dictionary in layouts:
		await _floor(layout, layout == first)
	await _finish()

func _tile(value: Variant) -> Vector2i:
	return Vector2i(int(value[0]), int(value[1]))

## One floor: its layout and a state with every cell revealed arrive, then the
## captures.
func _floor(layout: Dictionary, fog: bool) -> void:
	var id := str(layout.section)
	var anchors: Dictionary = layout._test
	var landing := _tile(anchors.landing)
	var began := Time.get_ticks_msec()
	_packet(layout)
	var built_ms := Time.get_ticks_msec() - began
	var loader: WorldLoader = main.get("world_loader")
	var floors := loader.world_root.get_node_or_null("DescentFloors")
	_expect(floors != null and floors.has_node("Section_%s_floor" % id), "%s is built (%d ms)" % [id, built_ms])
	var objects := {}
	var stair_id := 59400
	for stair: Dictionary in layout.stairs:
		var tile := Vector2i(int(layout.origin[0]) + int(stair.x), int(layout.origin[1]) + int(stair.y))
		var label := "Up to floor %d" % (int(layout.floor) - 1) if str(stair.way) == "up" else "Down to floor %d" % (int(layout.floor) + 1)
		objects[stair_id] = _object(stair_id, tile, "Portal", label)
		stair_id += 1
	if anchors.has("dais"):
		objects[DAIS] = _object(DAIS, _tile(anchors.dais), "Descent Dais", "Claim your reward")
		objects[EXIT] = _object(EXIT, _tile(anchors.portal), "Descent Exit", "Return to the temple")
	state.set("map_objects", objects)
	main.call("_sync_map_objects")
	await _place(landing)
	_packet(_state(layout, true))
	var rig: Node3D = main.get("camera_rig")
	var block: Dictionary = loader.manifest.data.get("camera", {})
	rig.set("yaw_degrees", 0.0)
	rig.set("pitch_degrees", float(block.get("pitchDegrees", -50.0)))
	rig.set("distance", float(block.get("distance", 12.0)))
	await _settle(90)
	_expect(str((main.get("secret_sections") as RefCounted).call("current_section")) == id,
		"the player's section is the shown section: " + id)
	var actor: Node3D = (main.get("actor_nodes") as Dictionary).get(PLAYER_ID)
	_expect(is_instance_valid(actor) and absf(actor.global_position.y) < 0.1,
		"%s: the player stands on the built walk floor" % id)
	await _capture("%s-a-game.png" % id, id, landing, true, {"build_ms": built_ms})
	await _capture("%s-a-view.png" % id, id, landing, false)
	var hall := _tile(anchors.largest_room)
	await _place(hall)
	rig.set("distance", float(block.get("distance", 12.0)) * 1.6)
	await _settle(60)
	await _capture("%s-b-hall.png" % id, id, hall, false)
	rig.set("distance", float(block.get("distance", 12.0)))
	for stair: Dictionary in layout.stairs:
		# Two tiles back from the stair, looking at its wall.
		var facing := Vector2i(int(stair.facing[0]), int(stair.facing[1]))
		var tile := Vector2i(int(layout.origin[0]) + int(stair.x), int(layout.origin[1]) + int(stair.y)) - facing * 2
		await _place(tile)
		rig.set("yaw_degrees", _yaw_toward(facing))
		rig.set("distance", 9.0)
		await _settle(40)
		var name := "%s-c-up.png" % id if str(stair.way) == "up" else "%s-d-down.png" % id
		await _capture(name, id, tile, false)
	rig.set("yaw_degrees", 0.0)
	rig.set("distance", float(block.get("distance", 12.0)))
	await _top(id)
	if fog:
		await _place(landing)
		_packet(_state(layout, false))
		await _settle(40)
		_expect(not (main.get("_descent_fog_grid") as Dictionary).is_empty(), "%s: the fog is up" % id)
		await _capture("%s-f-fog-game.png" % id, id, landing, true)
		main.call("_toggle_full_map")
		await _settle(20)
		await _capture("%s-f-fog-fullmap.png" % id, id, landing, true)
		main.call("_toggle_full_map")
		await _settle(10)

## The camera yaw that looks along `facing` (server tiles: +y is south).
func _yaw_toward(facing: Vector2i) -> float:
	if facing == Vector2i(0, -1):
		return 0.0
	if facing == Vector2i(1, 0):
		return -90.0
	if facing == Vector2i(0, 1):
		return 180.0
	return 90.0

## A state for `layout`'s floor: every cell revealed, or only the landing's
## room (the cells within 6 of the landing that are open, and two of rock round).
func _state(layout: Dictionary, everything: bool) -> Dictionary:
	var width := int(layout.width)
	var height := int(layout.height)
	var bits := PackedByteArray()
	bits.resize((width * height + 7) / 8)
	var landing := _tile(layout._test.landing) - Vector2i(int(layout.origin[0]), int(layout.origin[1]))
	var centre := landing / 2
	for cy: int in range(height):
		for cx: int in range(width):
			if everything or (absi(cx - centre.x) <= 6 and absi(cy - centre.y) <= 6):
				var i := cy * width + cx
				bits[i >> 3] |= 1 << (i & 7)
	return {"version": 1, "kind": "state", "open": true, "run": str(layout.run), "dungeon": "serpent_deep",
		"name": "The Serpent Deep", "difficulty": "Hard", "floor": int(layout.floor), "floors": 6,
		"floor_name": "Floor %d" % int(layout.floor), "section": str(layout.section), "origin": layout.origin,
		"cell_tiles": int(layout.cell_tiles), "width": width, "height": height,
		"explored": Marshalls.raw_to_base64(bits), "time_left": 3000,
		"boss": "fighting" if int(layout.floor) == 6 else ""}

func _packet(body: Dictionary) -> void:
	state.call("_on_packet", DESCENT_STATE, JSON.stringify(body).to_utf8_buffer())

## Straight down over the floor's section, north up, 3D viewport only.
func _top(id: String) -> void:
	var loader: WorldLoader = main.get("world_loader")
	var bounds: Dictionary = {}
	for listed: Dictionary in loader.manifest.data.sections:
		if str(listed.id) == id:
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
	await _capture("%s-e-top.png" % id, id, Vector2i(-1, -1), false, {"orthographic_size": camera.size})
	rig_camera.make_current()
	camera.queue_free()
	await process_frame

## Changes map as the server's CHANGE_MAP would and stands the player on it.
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
	await _settle(10)
	var actors := {PLAYER_ID: _actor(PLAYER_ID, "Traveller", tile)}
	state.set("local_actor_id", PLAYER_ID)
	state.set("actors", actors)
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	deadline = Time.get_ticks_msec() + 120000
	var curtain: Object = main.get("arrival_curtain")
	while Time.get_ticks_msec() < deadline and ((main.get("actor_nodes") as Dictionary).size() < actors.size()
			or bool(curtain.call("is_showing"))):
		main.call("_sync_world", state.call("take_changed_actors"))
		await process_frame
	_expect((main.get("actor_nodes") as Dictionary).size() >= actors.size(), "the player stands")
	_expect(not bool(curtain.call("is_showing")), "the arrival curtain lifts")
	await _settle(30)
	return true

func _actor(id: int, name: String, tile: Vector2i) -> Dictionary:
	return {"actor_id": id, "x": tile.x, "y": tile.y, "rotation": 0, "actor_type": 0,
		"kind": 1, "name": name, "health": 100, "max_health": 100, "alive": true, "appearance": {}}

func _object(id: int, tile: Vector2i, label: String, detail: String) -> Dictionary:
	return {"object_id": id, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x": tile.x, "y": tile.y, "label": label, "detail": detail}

## Moves the player (a teleport past 8 m, a walk otherwise) and waits for it.
func _place(tile: Vector2i) -> void:
	var actors: Dictionary = state.get("actors")
	var record: Dictionary = actors[PLAYER_ID]
	record.x = tile.x
	record.y = tile.y
	state.call("mark_all_actors_changed")
	main.call("_sync_world", state.call("take_changed_actors"))
	var adapter: CoordinateAdapter = main.get("adapter")
	var target := adapter.tile_center(tile.x, tile.y)
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

## Saves the window (`whole`) or the 3D viewport and records the frame.
func _capture(name: String, section: String, tile: Vector2i, whole: bool, extra := {}) -> void:
	await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image() if whole \
		else (main.get("main_viewport") as SubViewport).get_texture().get_image()
	var path := out.path_join(name)
	var saved := image != null and image.save_png(path) == OK
	_expect(saved, "saved " + name)
	if not saved:
		return
	var rig: Node3D = main.get("camera_rig")
	var row := {"file": name, "section": section, "tile": [tile.x, tile.y],
		"pixels": [image.get_width(), image.get_height()],
		"shown_section": str((main.get("secret_sections") as RefCounted).call("current_section")),
		"camera": {"yaw": rig.get("yaw_degrees"), "pitch": rig.get("pitch_degrees"), "distance": rig.get("distance")},
		"look": LookProfile.mode(), "luminance": _luminance(image),
		"draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)}
	row.merge(extra)
	captures.append(row)
	print("DESCENT_CAPTURE ", JSON.stringify(row))

## Mean luminance of the pixels that are not blackspace, and the share of
## those that are near black or near white.
static func _luminance(image: Image) -> Dictionary:
	var lit := 0
	var total := 0.0
	var dark := 0
	var blown := 0
	for y: int in range(0, image.get_height(), 4):
		for x: int in range(0, image.get_width(), 4):
			var value := image.get_pixel(x, y).get_luminance()
			if value < 0.004:
				continue
			lit += 1
			total += value
			dark += 1 if value < 0.06 else 0
			blown += 1 if value > 0.96 else 0
	return {"lit_pixels": lit, "mean": snappedf(total / maxf(1.0, float(lit)), 0.001),
		"dark_share": snappedf(float(dark) / maxf(1.0, float(lit)), 0.001),
		"blown_share": snappedf(float(blown) / maxf(1.0, float(lit)), 0.001)}

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: " + message)
		return
	failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	var report := FileAccess.open(out.path_join("report.json"), FileAccess.WRITE)
	if report != null:
		report.store_string(JSON.stringify({"captures": captures, "failures": failures}, "  "))
		report.close()
	print("rendered descent floors: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
