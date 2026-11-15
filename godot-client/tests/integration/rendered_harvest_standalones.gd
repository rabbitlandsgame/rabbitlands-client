extends SceneTree
## The stand-alone harvest models (2026-11-15) in the complete client: Main
## loads each published Landfall map as it does for a player (look, chunks,
## harvest presentation), and the served harvest nodes round a vantage are
## listed as map objects exactly as the server sends them (object id, tile,
## resource label), so each node stands what a player sees: its package's
## variant and yaw when laid out, the label's own model otherwise.
##
## Writes under <out>:
##   lineup-close.png / lineup-game.png  the seven stand-alone models in a row
##       on open Landfall ground (synthetic, undescribed object ids, so each
##       stands at its seeded yaw and scale), close and at the game camera
##   model-<label>.png  each of the seven up close, the player in front of it
##   site-<map>-game.png / site-<map>-close.png  a real place dense in the
##       Bramble, Hearthroot, Kelp, Shell, Salt, Quartz or Clay nodes that
##       drew a bare ring before, at the default camera (pitch -60, 26 m) and
##       closer (pitch -50, 14 m); the 3D viewport only
##   report.json  every capture, the nodes listed, what each node stands
##       (model id) and how many still draw only the ring
##
## Rendered only (needs a display; one GPU job at a time on the laptop):
##   godot --log-file <log> --path godot-client --script res://tests/integration/rendered_harvest_standalones.gd
## ELORIA_ARTIFACT_DIR picks <out> (default res://test-artifacts/harvest-standalones);
## ELORIA_NO_GEOMETRY_CACHE=1 loads the packages raw. Exit 0 when every capture was written.
const SIZE := Vector2i(1600, 900)
const PLAYER_ID := 1
const LINEUP_BASE := 61001
const LINEUP := ["Bramble", "Hearthroot", "Kelp", "Shell", "Salt", "Quartz", "Clay"]
const STANDALONES := ["bramble_bush_a", "hearthroot_clump_a", "kelp_heap_a", "shell_heap_a", "salt_mound_a",
	"quartz_boulder_a", "clay_mound_a"]
## [map, vantage tile, radius in tiles of the nodes listed]
const SITES := [
	["landfall", Vector2i(254, 426), 30], ["saltsound", Vector2i(176, 531), 30],
	["ravenhead", Vector2i(332, 299), 30], ["ringholm", Vector2i(318, 617), 30],
	["stagheath", Vector2i(574, 103), 30]]

var main: Control
var state: Node
var out := ""
var grid: Dictionary = {}
var captures: Array = []
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/harvest-standalones")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = SIZE
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
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	var first := true
	for site: Array in SITES:
		var map_id := str(site[0])
		var vantage: Vector2i = site[1]
		var package := "res://../eloria-assets/maps/continent-v2/%s/client/" % map_id
		grid = _served_grid(ProjectSettings.globalize_path(package + "served-grid.escg.gz"))
		var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(package + "world.json"))
		var objects := {}
		for node: Dictionary in manifest.get("harvestables", []):
			var tile := Vector2i(int(node.serverTile[0]), int(node.serverTile[1]))
			if absi(tile.x - vantage.x) <= int(site[2]) and absi(tile.y - vantage.y) <= int(site[2]):
				objects[int(node.objectId)] = _harvest(int(node.objectId), tile, str(node.resource))
		var stand := _open_near(vantage, objects)
		var lineup_tiles: Array = []
		if first:
			# Seven undescribed nodes on open ground north of the vantage, 2 tiles apart.
			var anchor := _open_near(vantage + Vector2i(0, -12), objects)
			for index: int in LINEUP.size():
				var tile := _open_near(anchor + Vector2i(-6 + 2 * index, 0), objects)
				lineup_tiles.append(tile)
				objects[LINEUP_BASE + index] = _harvest(LINEUP_BASE + index, tile, LINEUP[index])
		if not await _enter(map_id, stand, objects):
			continue
		var rig: Node3D = main.get("camera_rig")
		if first:
			first = false
			var centre: Vector2i = lineup_tiles[3]
			await _place(centre + Vector2i(0, 2))
			await _wait_chunks()
			_check_lineup()
			rig.set("yaw_degrees", 0.0)
			rig.set("pitch_degrees", -35.0)
			rig.set("distance", 11.0)
			await _settle(60)
			await _capture("lineup-close.png", map_id, centre)
			rig.set("pitch_degrees", -60.0)
			rig.set("distance", 26.0)
			await _settle(45)
			await _capture("lineup-game.png", map_id, centre)
			# Each model up close, the player in front of it for scale (the camera looks along +y).
			rig.set("pitch_degrees", -35.0)
			rig.set("distance", 5.0)
			for index: int in LINEUP.size():
				var tile: Vector2i = lineup_tiles[index]
				await _place(tile + Vector2i(1, -3))
				await _settle(40)
				await _capture("model-%s.png" % str(LINEUP[index]).to_lower(), map_id, tile)
			await _place(stand)
			await _wait_chunks()
		rig.set("yaw_degrees", 0.0)
		rig.set("pitch_degrees", -60.0)
		rig.set("distance", 26.0)
		await _settle(60)
		await _capture("site-%s-game.png" % map_id, map_id, stand, _standing(objects))
		rig.set("pitch_degrees", -50.0)
		rig.set("distance", 14.0)
		await _settle(45)
		await _capture("site-%s-close.png" % map_id, map_id, stand)
	await _finish()

func _harvest(id: int, tile: Vector2i, label: String) -> Dictionary:
	return {"object_id": id, "kind": EloriaProtocol.MAP_OBJECT_HARVEST, "x": tile.x, "y": tile.y,
		"label": label, "detail": "Harvesting level 1"}

func _enter(map_id: String, tile: Vector2i, objects: Dictionary) -> bool:
	state.set("actors", {})
	state.set("local_actor_id", -1)
	state.set("map_objects", {})
	state.set("current_map", map_id)
	main.call("_load_server_map")
	var loader: WorldLoader = main.get("world_loader")
	var deadline := Time.get_ticks_msec() + 300000
	while Time.get_ticks_msec() < deadline and not (loader.world_root != null and loader.manifest != null
			and loader.manifest.asset_id() == map_id and str(main.get("loaded_server_map")) == map_id):
		await process_frame
	var loaded := loader.manifest != null and loader.manifest.asset_id() == map_id
	_expect(loaded, "%s loads through Main" % map_id)
	if not loaded:
		return false
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
	await _wait_chunks()
	await _settle(30)
	return true

## The seven lineup nodes stand their stand-alone models, with no idle ring.
func _check_lineup() -> void:
	var nodes: Dictionary = main.get("map_object_nodes")
	for index: int in LINEUP.size():
		var node: Node = nodes.get(LINEUP_BASE + index)
		var model_id := str(node.get("model_id")) if is_instance_valid(node) else ""
		_expect(model_id == STANDALONES[index], "%s stands %s: %s" % [LINEUP[index], STANDALONES[index], model_id])

## What every listed node stands: model ids by label, and the ring-only count.
func _standing(objects: Dictionary) -> Dictionary:
	var nodes: Dictionary = main.get("map_object_nodes")
	var by_label := {}
	var rings := 0
	for id: Variant in objects:
		var node: Node = nodes.get(id)
		if not is_instance_valid(node):
			continue
		var label := str((objects[id] as Dictionary).label)
		var model_id := str(node.get("model_id"))
		if model_id.is_empty():
			rings += 1
			model_id = "(ring)"
		var counts: Dictionary = by_label.get(label, {})
		counts[model_id] = int(counts.get(model_id, 0)) + 1
		by_label[label] = counts
	_expect(rings == 0, "no listed node draws only its ring (%d do)" % rings)
	return {"nodes": objects.size(), "ringOnly": rings, "standing": by_label}

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
	var deadline := Time.get_ticks_msec() + 90000
	while Time.get_ticks_msec() < deadline:
		var ready := stream._thread == null
		for entry: Dictionary in stream.selection(stream.focus, true):
			if float(entry.distance) <= stream.preload_distance and not stream.cells.has(str(entry.id)):
				ready = false
		if ready:
			break
		await process_frame
	await _settle(20)

func _capture(name: String, map_id: String, tile: Vector2i, extra := {}) -> void:
	await process_frame
	RenderingServer.force_draw(false)
	var image: Image = (main.get("main_viewport") as SubViewport).get_texture().get_image()
	var saved := image != null and image.save_png(out.path_join(name)) == OK
	_expect(saved, "saved " + name)
	if not saved:
		return
	var rig: Node3D = main.get("camera_rig")
	var row := {"file": name, "map": map_id, "tile": [tile.x, tile.y], "pixels": [image.get_width(), image.get_height()],
		"camera": {"yaw": rig.get("yaw_degrees"), "pitch": rig.get("pitch_degrees"), "distance": rig.get("distance")},
		"look": LookProfile.mode()}
	row.merge(extra)
	captures.append(row)
	print("HARVEST_CAPTURE ", JSON.stringify(row))

## The open served tile nearest `centre`, clear of the listed nodes' tiles.
func _open_near(centre: Vector2i, objects: Dictionary) -> Vector2i:
	var taken := {}
	for object: Dictionary in objects.values():
		taken[Vector2i(int(object.x), int(object.y))] = true
	var best := centre
	var best_distance := INF
	for dy: int in range(-6, 7):
		for dx: int in range(-6, 7):
			var tile := centre + Vector2i(dx, dy)
			if taken.has(tile) or not _open(tile):
				continue
			var distance := Vector2(tile).distance_to(Vector2(centre))
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

func _expect(ok: bool, message: String) -> void:
	print("HARVEST_RENDER ", "PASS " if ok else "FAIL ", message)
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
	print("Harvest stand-alone render: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures, ",
		captures.size(), " captures)")
	quit(0 if failures == 0 else 1)
