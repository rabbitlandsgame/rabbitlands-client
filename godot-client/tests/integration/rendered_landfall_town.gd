extends SceneTree
## Landfall Town (landfall_town) in the complete client: Main loads the
## published package as it does for a player (environment, look, town
## scenery, light markers, cutaway, SecretSections, the map's camera block,
## occluder fade, minimap), with the town's people standing at their posts
## as NPC actors and the doors, stairs and lore objects as map objects, all
## read from the source the package was published from (content/
## landfall_town.json: its tiles are the served tiles).
##
## For every section it saves, under <out>/rooms/:
##   <section>-a-game.png   the default game view (yaw 0, the camera block's
##                          pitch and distance), the player at the open tile
##                          nearest the main room's centre: the whole window,
##                          HUD and minimap (switched on: it is off by
##                          default) with the shop dots included
##   <section>-a-view.png   the same frame, 3D viewport only
##   <section>-b<i>-<slug>.png  a closer view (distance CLOSE_DISTANCE) of
##                          each other room, the player at its centre
##   <section>-c-top.png    a top-down orthographic view of the section
## and under <out>/dots/ the Landfall town quarter on the live minimap and
## the Tab map (zoomed on the quarter), Landfall's picture as a region
## preview seen from inside the town, and the market's interior Tab map.
## <out>/report.json lists every capture with its tile, section, camera and
## the luminance of its 3D frame (mean of the lit pixels, share of pixels
## below 0.06 and above 0.96), so dark or blown-out rooms show in numbers.
##
## Rendered only (needs a display; one GPU job at a time on the laptop):
##   godot --log-file <log> --path godot-client --script res://tests/integration/rendered_landfall_town.gd
## ELORIA_ARTIFACT_DIR picks <out> (default res://test-artifacts/landfall-town).
## Main prepares the native map geometry cache on a first start (minutes, into
## user://); ELORIA_NO_GEOMETRY_CACHE=1 skips that and loads the packages raw,
## as the town always loads (it is outside the production cache scope).
## ELORIA_TOWN_SECTIONS=castle,market limits the sections; ELORIA_TOWN_DOTS=0
## skips the Landfall pass. Exit status 0 when every capture was written.
const SOURCE := "res://../eloria-assets/maps/continent-v2/_continent_v2/content/landfall_town.json"
const PACKAGE_DIR := "res://../eloria-assets/maps/continent-v2/landfall_town/client/"
const INTERIOR := "landfall_town"
const EXTERIOR := "landfall"
const SIZE := Vector2i(1600, 900)
const PLAYER_ID := 1
const NPC_BASE := 30000
const CLOSE_DISTANCE := 8.0
const FACINGS := ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
## Where the Landfall pass stands: the door clusters of the town quarter.
const QUARTER_VANTAGES := [
	["market", Vector2i(130, 252)], ["west-ward", Vector2i(95, 263)],
	["true-note", Vector2i(166, 261)], ["keep", Vector2i(219, 270)],
	["net-mender", Vector2i(233, 209)]]

var main: Control
var state: Node
var out := ""
var plan: Dictionary = {}
var grid: Dictionary = {}
var captures: Array = []
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/landfall-town")
	for folder: String in ["rooms", "dots"]:
		DirAccess.make_dir_recursive_absolute(out.path_join(folder))
	root.size = SIZE
	plan = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
	grid = _served_grid(ProjectSettings.globalize_path(PACKAGE_DIR + "served-grid.escg.gz"))
	_expect(not grid.is_empty(), "the town's served grid reads")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	state = root.get_node("AppState")
	# Main reads its registries and builds its exterior stream only after any
	# first-start world data preparation; ELORIA_NO_GEOMETRY_CACHE=1 skips it.
	var ready_deadline := Time.get_ticks_msec() + 1800000
	while (main.get("map_registry") as Dictionary).is_empty() and Time.get_ticks_msec() < ready_deadline:
		await process_frame
	_expect(not (main.get("map_registry") as Dictionary).is_empty(), "Main has read its map registry")
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	# The minimap is off by default; on here so its door and shop dots show.
	if not (main.get("minimap_frame") as Control).visible:
		main.call("_toggle_minimap")
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	var wanted := OS.get_environment("ELORIA_TOWN_SECTIONS").split(",", false)
	var sections: Array = (plan.sections as Array).filter(func(s: Dictionary) -> bool:
		return wanted.is_empty() or wanted.has(str(s.id)))
	var first: Dictionary = sections[0] if not sections.is_empty() else plan.sections[0]
	if not await _enter(INTERIOR, _open_near(Vector2(float(first.rooms[0][0]), float(first.rooms[0][1])))):
		await _finish()
		return
	for section: Dictionary in sections:
		await _section(section)
	if OS.get_environment("ELORIA_TOWN_DOTS") != "0":
		await _dots()
	await _finish()

## One section: the default game view on its main room, a closer view of each
## other room, and a top-down view of the whole section.
func _section(section: Dictionary) -> void:
	var id := str(section.id)
	var rooms: Array = section.rooms
	var names: Array = section.get("roomNames", [])
	var rig: Node3D = main.get("camera_rig")
	var block: Dictionary = (main.get("world_loader") as WorldLoader).manifest.data.get("camera", {})
	var main_tile := _open_near(Vector2(float(rooms[0][0]), float(rooms[0][1])))
	await _place(main_tile)
	rig.set("yaw_degrees", 0.0)
	rig.set("pitch_degrees", float(block.get("pitchDegrees", -50.0)))
	rig.set("distance", float(block.get("distance", 12.0)))
	await _settle(90)
	_expect(str((main.get("secret_sections") as RefCounted).call("current_section")) == id,
		"the player's section is the shown section: " + id)
	await _capture("rooms/%s-a-game.png" % id, id, 0, main_tile, true)
	await _capture("rooms/%s-a-view.png" % id, id, 0, main_tile, false)
	for index: int in range(1, rooms.size()):
		var tile := _open_near(Vector2(float(rooms[index][0]), float(rooms[index][1])))
		await _place(tile)
		rig.set("yaw_degrees", 0.0)
		rig.set("pitch_degrees", float(block.get("pitchDegrees", -50.0)))
		rig.set("distance", CLOSE_DISTANCE)
		await _settle(60)
		var slug := _slug(str(names[index]) if index < names.size() else "room")
		await _capture("rooms/%s-b%d-%s.png" % [id, index, slug], id, index, tile, false)
	await _place(main_tile)
	rig.set("distance", float(block.get("distance", 12.0)))
	await _settle(45)
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
	await _capture("rooms/%s-c-top.png" % str(section.id), str(section.id), -1, Vector2i(-1, -1), false,
		{"orthographic_size": camera.size})
	rig_camera.make_current()
	camera.queue_free()
	await process_frame

## Landfall's town quarter: the live minimap and Tab map with the door dots,
## then (from inside the town) Landfall as a region preview and the market's
## interior Tab map with its two shop dots.
func _dots() -> void:
	if not await _enter(EXTERIOR, QUARTER_VANTAGES[0][1]):
		return
	var rig: Node3D = main.get("camera_rig")
	for vantage: Array in QUARTER_VANTAGES:
		await _place(vantage[1])
		rig.set("yaw_degrees", 0.0)
		await _settle(120)
		await _wait_chunks()
		await _capture("dots/landfall-%s-game.png" % vantage[0], EXTERIOR, -1, vantage[1], true)
		if vantage[0] in ["market", "keep"]:
			main.call("_toggle_full_map")
			main.set("_full_map_zoom", 0.3)
			main.call("_apply_full_map_zoom")
			await _settle(30)
			await _capture("dots/landfall-%s-tab-map.png" % vantage[0], EXTERIOR, -1, vantage[1], true)
			main.set("_full_map_zoom", 1.0)
			main.call("_apply_full_map_zoom")
			await _settle(20)
			await _capture("dots/landfall-tab-map-whole.png", EXTERIOR, -1, vantage[1], true)
			main.call("_toggle_full_map")
			await _settle(10)
	# Back in through the market's door: Landfall's picture as a preview.
	var market: Dictionary = (plan.sections as Array).filter(func(s: Dictionary) -> bool:
		return str(s.id) == "market")[0]
	if not await _enter(INTERIOR, _open_near(Vector2(float(market.rooms[0][0]), float(market.rooms[0][1])))):
		return
	await _settle(60)
	main.call("_toggle_full_map")
	await _settle(30)
	await _capture("dots/town-market-tab-map.png", INTERIOR, 0, Vector2i(-1, -1), true)
	main.call("_preview_region", int(main.call("_region_index_for_map", EXTERIOR)))
	await _settle(30)
	await _capture("dots/landfall-region-preview.png", EXTERIOR, -1, Vector2i(-1, -1), true)
	main.call("_toggle_full_map")
	await _settle(10)

## Changes map as the server's CHANGE_MAP would, then stands the player and
## the map's people and objects on it and waits for the curtain to lift.
func _enter(map_id: String, tile: Vector2i) -> bool:
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("map_objects", {})
	state.set("current_map", map_id)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 180000
	while Time.get_ticks_msec() < deadline and not (loader.world_root != null and loader.manifest != null
			and loader.manifest.asset_id() == map_id and str(main.get("loaded_server_map")) == map_id):
		await process_frame
	var loaded := loader.manifest != null and loader.manifest.asset_id() == map_id
	_expect(loaded, "%s loads through Main" % map_id)
	if not loaded:
		return false
	var actors := {PLAYER_ID: _actor(PLAYER_ID, "Traveller", tile, 0, 1, 0)}
	var objects := {}
	if map_id == INTERIOR:
		var index := 0
		for section: Dictionary in plan.sections:
			for person: Dictionary in section.get("npcs", []):
				var id := NPC_BASE + index
				index += 1
				actors[id] = _actor(id, str(person.name), Vector2i(int(person.tile[0]), int(person.tile[1])),
					int(person.actorType), 2, FACINGS.find(str(person.get("facing", "S"))))
			for door: Dictionary in section.get("entrances", []):
				objects[int(door.object)] = _object(int(door.object), door.exit, "Portal", str(door.get("exitLabel", "")) + ".")
			for item: Dictionary in section.get("interactives", []):
				objects[int(item.object)] = _object(int(item.object), item.tile,
					str(item.role).replace("_", " ").capitalize(), str(item.get("text", "")))
		for passage: Dictionary in plan.get("passages", []):
			var ends: Array = passage.ends
			for end_index: int in ends.size():
				var end: Dictionary = ends[end_index]
				var object_id := int(passage.object) + end_index
				objects[object_id] = _object(object_id, end.tile, "Portal", str(end.get("label", "")) + ".")
	else:
		for section: Dictionary in plan.sections:
			for door: Dictionary in section.get("entrances", []):
				objects[int(door.object)] = _object(int(door.object), door.tile, "Portal",
					"%s. %s" % [str(door.get("label", "")), str(section.get("danger", ""))])
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
	_expect((main.get("actor_nodes") as Dictionary).size() >= actors.size(),
		"%s: the player and %d people stand" % [map_id, actors.size() - 1])
	_expect(not bool(curtain.call("is_showing")), map_id + ": the arrival curtain lifts")
	await _settle(30)
	return true

func _actor(id: int, name: String, tile: Vector2i, actor_type: int, kind: int, facing: int) -> Dictionary:
	var rotation := maxi(0, facing) * 8192
	if rotation >= 32768:
		rotation -= 65536
	return {"actor_id": id, "x": tile.x, "y": tile.y, "rotation": rotation, "actor_type": actor_type,
		"kind": kind, "name": name, "health": 100, "max_health": 100, "alive": true, "appearance": {}}

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

func _wait_chunks() -> void:
	var stream := (main.get("world_loader") as WorldLoader).world_root as ContinentChunkStream
	if stream == null:
		return
	var deadline := Time.get_ticks_msec() + 60000
	while Time.get_ticks_msec() < deadline:
		var ready := stream._thread == null
		for entry: Dictionary in stream.selection(stream.focus, true):
			if float(entry.distance) <= stream.preload_distance and not stream.cells.has(str(entry.id)):
				ready = false
		if ready:
			break
		await process_frame
	await _settle(20)

## Saves the window (`whole`) or the 3D viewport and records the frame.
func _capture(name: String, section: String, room: int, tile: Vector2i, whole: bool, extra := {}) -> void:
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
	var loader: WorldLoader = main.get("world_loader")
	var row := {"file": name, "map": loader.manifest.asset_id(), "section": section, "room": room,
		"tile": [tile.x, tile.y], "pixels": [image.get_width(), image.get_height()],
		"shown_section": str((main.get("secret_sections") as RefCounted).call("current_section")),
		"camera": {"yaw": rig.get("yaw_degrees"), "pitch": rig.get("pitch_degrees"), "distance": rig.get("distance")},
		"look": LookProfile.mode(), "luminance": _luminance(image),
		"video_mem_bytes": Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		"draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)}
	row.merge(extra)
	captures.append(row)
	print("TOWN_CAPTURE ", JSON.stringify(row))

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

## The open served tile nearest a room centre (source tile units), avoiding
## the people's posts and the objects' tiles, so the player stands clear.
func _open_near(centre: Vector2) -> Vector2i:
	var taken_tiles := {}
	for section: Dictionary in plan.sections:
		for person: Dictionary in section.get("npcs", []):
			taken_tiles[Vector2i(int(person.tile[0]), int(person.tile[1]))] = true
		for item: Dictionary in section.get("interactives", []):
			taken_tiles[Vector2i(int(item.tile[0]), int(item.tile[1]))] = true
	var best := Vector2i(floori(centre.x), floori(centre.y))
	var best_distance := INF
	for dy: int in range(-6, 7):
		for dx: int in range(-6, 7):
			var tile := Vector2i(floori(centre.x) + dx, floori(centre.y) + dy)
			if taken_tiles.has(tile) or not _open(tile):
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

static func _slug(text: String) -> String:
	var slug := ""
	for character: String in text.to_lower():
		slug += character if character.is_valid_identifier() or character.is_valid_int() else "-"
	while slug.contains("--"):
		slug = slug.replace("--", "-")
	return slug.trim_prefix("-").trim_suffix("-")

func _expect(ok: bool, message: String) -> void:
	print("TOWN_RENDER ", "PASS " if ok else "FAIL ", message)
	if not ok:
		failures += 1

func _finish() -> void:
	var file := FileAccess.open(out.path_join("report.json"), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify({"captures": captures, "failures": failures,
			"look": LookProfile.mode(), "renderer": RenderingServer.get_current_rendering_method(),
			"engine": Engine.get_version_info()}, "  "))
		file.close()
	var stream: Object = main.get("exterior_stream") if is_instance_valid(main) else null
	if stream != null:
		main.call("_on_disconnect_pressed")
		stream.call("clear")
		while not bool(stream.call("is_idle")):
			await process_frame
	if is_instance_valid(main):
		for frame: int in 6:
			await process_frame
		main.queue_free()
	await ContinentChunkStream.drain_workers(self)
	for frame: int in 8:
		await process_frame
	GlbSceneCache.clear()
	print("Landfall Town render: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures, ",
		captures.size(), " captures)")
	quit(0 if failures == 0 else 1)
