extends SceneTree
## The Serpent Deep's baked floor pool (serpent_deep_descent) in the complete
## client: Main loads the published package as it does for a player
## (environment, the descent's kit scenery, light markers, cutaway,
## SecretSections, the minimap and its section picture), the player standing
## at a floor's landing, with the stair and door portals as map objects read
## from the source the package was baked from (content/
## serpent_deep_descent.json: its tiles are the served tiles).
##
## For every chosen section it saves, under <out>/:
##   <section>-a-game.png   the default game view at the landing: the whole
##                          window, HUD and minimap (switched on)
##   <section>-a-view.png   the same frame, 3D viewport only
##   <section>-b-hall.png   the default view in the floor's largest room
##   <section>-c-top.png    a top-down orthographic view of the section
## <out>/report.json lists every capture with its tile, section, camera and
## the luminance of its frame (mean of the lit pixels, share of pixels below
## 0.06 and above 0.96), so a dark floor shows in numbers.
##
## Rendered only (needs a display; one GPU job at a time on the laptop):
##   godot --log-file <log> --path godot-client --script res://tests/integration/rendered_descent_pool.gd
## ELORIA_ARTIFACT_DIR picks <out> (default res://test-artifacts/descent-pool);
## ELORIA_DESCENT_SECTIONS=serpent_deep_f1v1,... picks the sections (default:
## a crypt floor, the sunken halls and the boss floor). Set
## ELORIA_NO_GEOMETRY_CACHE=1 to skip Main's first-start geometry preparation
## (the descent is outside the production cache scope and always loads raw).
## Exit status 0 when every capture was written.
const SOURCE := "res://../eloria-assets/maps/continent-v2/_continent_v2/content/serpent_deep_descent.json"
const PACKAGE_DIR := "res://../eloria-assets/maps/continent-v2/serpent_deep_descent/client/"
const INTERIOR := "serpent_deep_descent"
const DEFAULT_SECTIONS := ["serpent_deep_f1v1", "serpent_deep_f5v4", "serpent_deep_f6v1"]
const SIZE := Vector2i(1600, 900)
const PLAYER_ID := 1

var main: Control
var state: Node
var out := ""
var plan: Dictionary = {}
var grid: Dictionary = {}
var arrivals: Dictionary = {}
var captures: Array = []
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/descent-pool")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = SIZE
	plan = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
	grid = _served_grid(ProjectSettings.globalize_path(PACKAGE_DIR + "served-grid.escg.gz"))
	_expect(not grid.is_empty(), "the pool's served grid reads")
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(PACKAGE_DIR + "world.json"))
	for spawn: Dictionary in (manifest as Dictionary).get("spawnPoints", []):
		arrivals[str(spawn.section)] = Vector2i(int(spawn.serverTile[0]), int(spawn.serverTile[1]))
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
	var wanted := OS.get_environment("ELORIA_DESCENT_SECTIONS").split(",", false)
	var chosen: Array = wanted if not wanted.is_empty() else DEFAULT_SECTIONS
	var sections: Array = (plan.sections as Array).filter(func(s: Dictionary) -> bool: return chosen.has(str(s.id)))
	_expect(sections.size() == chosen.size(), "every chosen section is in the source")
	if sections.is_empty() or not await _enter(arrivals.get(str(sections[0].id), Vector2i.ZERO)):
		await _finish()
		return
	for section: Dictionary in sections:
		await _section(section)
	await _finish()

## One section: the default game view at its landing, the largest room, and a
## top-down view of the whole floor.
func _section(section: Dictionary) -> void:
	var id := str(section.id)
	var rig: Node3D = main.get("camera_rig")
	var block: Dictionary = (main.get("world_loader") as WorldLoader).manifest.data.get("camera", {})
	var landing: Vector2i = arrivals.get(id, Vector2i.ZERO)
	_expect(_open(landing), id + ": the landing is walkable on the served grid")
	await _place(landing)
	rig.set("yaw_degrees", 0.0)
	rig.set("pitch_degrees", float(block.get("pitchDegrees", -50.0)))
	rig.set("distance", float(block.get("distance", 12.0)))
	await _settle(90)
	_expect(str((main.get("secret_sections") as RefCounted).call("current_section")) == id,
		"the player's section is the shown section: " + id)
	await _capture("%s-a-game.png" % id, id, landing, true)
	await _capture("%s-a-view.png" % id, id, landing, false)
	var largest: Array = section.rooms[0]
	for room: Array in section.rooms:
		if float(room[2]) * float(room[3]) > float(largest[2]) * float(largest[3]):
			largest = room
	var hall := _open_near(Vector2(float(largest[0]), float(largest[1])))
	await _place(hall)
	rig.set("distance", float(block.get("distance", 12.0)) * 1.6)
	await _settle(60)
	await _capture("%s-b-hall.png" % id, id, hall, false)
	rig.set("distance", float(block.get("distance", 12.0)))
	await _top(section)

## Straight down over the section's bounds, north up, 3D viewport only.
func _top(section: Dictionary) -> void:
	var loader: WorldLoader = main.get("world_loader")
	var bounds: Dictionary = {}
	for listed: Dictionary in loader.manifest.data.sections:
		if str(listed.id) == str(section.id):
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
	await _capture("%s-c-top.png" % str(section.id), str(section.id), Vector2i(-1, -1), false,
		{"orthographic_size": camera.size})
	rig_camera.make_current()
	camera.queue_free()
	await process_frame

## Changes map as the server's CHANGE_MAP would, then stands the player and
## the pool's doors and stair portals on it and waits for the curtain to lift.
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
	var actors := {PLAYER_ID: _actor(PLAYER_ID, "Traveller", tile)}
	var objects := {}
	for section: Dictionary in plan.sections:
		for door: Dictionary in section.get("entrances", []):
			objects[int(door.object)] = _object(int(door.object), door.exit, "Portal", "Up to the temple.")
	for passage: Dictionary in plan.get("passages", []):
		var ends: Array = passage.ends
		for end_index: int in ends.size():
			var end: Dictionary = ends[end_index]
			var object_id := int(passage.object) + end_index
			objects[object_id] = _object(object_id, end.tile, "Portal", str(end.get("label", "")) + ".")
	state.set("map_objects", objects)
	state.set("local_actor_id", PLAYER_ID)
	state.set("actors", actors)
	state.call("mark_all_actors_changed")
	main.call("_sync_world")
	main.call("_sync_map_objects")
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

func _object(id: int, tile: Variant, label: String, detail: String) -> Dictionary:
	return {"object_id": id, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x": int(tile[0]), "y": int(tile[1]), "label": label, "detail": detail}

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
		"scenery": _scenery_count(),
		"draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)}
	row.merge(extra)
	captures.append(row)
	print("DESCENT_CAPTURE ", JSON.stringify(row))

func _scenery_count() -> int:
	var loader: WorldLoader = main.get("world_loader")
	if loader.world_root == null or not loader.world_root.has_node("UndergroundScenery"):
		return -1
	return loader.world_root.get_node("UndergroundScenery").get_child_count()

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

## The open served tile nearest a room centre.
func _open_near(centre: Vector2) -> Vector2i:
	var best := Vector2i(floori(centre.x), floori(centre.y))
	var best_distance := INF
	for dy: int in range(-8, 9):
		for dx: int in range(-8, 9):
			var tile := Vector2i(floori(centre.x) + dx, floori(centre.y) + dy)
			if not _open(tile):
				continue
			var distance := Vector2(tile.x + 0.5, tile.y + 0.5).distance_to(centre)
			if distance < best_distance:
				best_distance = distance
				best = tile
	return best

func _open(tile: Vector2i) -> bool:
	if grid.is_empty() or tile.x < 0 or tile.y < 0 or tile.x >= int(grid.width) or tile.y >= int(grid.height):
		return false
	return int((grid.codes as PackedInt32Array)[tile.y * int(grid.width) + tile.x]) > 0

## ESCG-v2 (eloria/served_grid.py): a gzip of a 32-byte header and one
## little-endian u16 code per tile, row-delta filtered when filter is 1.
static func _served_grid(path: String) -> Dictionary:
	var blob := FileAccess.get_file_as_bytes(path)
	if blob.is_empty():
		return {}
	var data := blob.decompress_dynamic(-1, FileAccess.COMPRESSION_GZIP)
	if data.size() < 32 or data.slice(0, 4).get_string_from_ascii() != "ESCG":
		return {}
	var width := data.decode_u32(8)
	var height := data.decode_u32(12)
	var filtered := data[24] == 1
	var codes := PackedInt32Array()
	codes.resize(width * height)
	for row: int in height:
		var running := 0
		for column: int in width:
			var value := data.decode_u16(32 + 2 * (row * width + column))
			running = (running + value) & 0xffff if filtered else value
			codes[row * width + column] = running
	return {"width": width, "height": height, "codes": codes}

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
	print("rendered descent pool: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)
