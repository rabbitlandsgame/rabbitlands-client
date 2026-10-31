extends SceneTree

## Hearthcroft -> Reedfall used to leave world-root pictures in the departure
## frame and above the active picture, producing rectangular minimap strips.
var failures := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func select_map(main: Control, map_id: String) -> void:
	var manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/" + map_id + "/client/world.json")
	root.get_node("AppState").current_map = map_id
	main.adapter = manifest.coordinate_adapter()
	main.exterior_stream.active_map = map_id
	main.exterior_stream.active_root = main.world_root
	main.exterior_stream.active_manifest = manifest
	main._install_map_picture(manifest)

func run() -> void:
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.exterior_stream.set_process(false)
	root.get_node("Network").set_process(false)
	select_map(main, "hearthcroft")
	var before: Dictionary = main._neighbour_pictures["landfall"]
	var old_frame: Transform3D = before.transform
	expect(old_frame.is_equal_approx(main.world_root.global_transform * main.exterior_stream.region_transform("landfall")),
		"the unloaded region starts in the departure world's frame")
	var textures: Dictionary = main._tab_map_textures.duplicate()
	select_map(main, "reedfall")
	var after: Dictionary = main._neighbour_pictures["landfall"]
	var stale_draw := false
	for row: Dictionary in main.minimap_background.get("_pictures"):
		stale_draw = stale_draw or (row.texture == before.texture and row.transform.is_equal_approx(old_frame))
	expect(not stale_draw, "the departure frame stops drawing immediately at a map handoff")
	expect(after.transform.is_equal_approx(main.world_root.global_transform * main.exterior_stream.region_transform("landfall")),
		"the unloaded picture moves into Reedfall's coordinate frame")
	expect(not after.transform.is_equal_approx(old_frame), "a shared parent cannot preserve the departure transform")
	var region_index: int = main._region_index_for_map("landfall")
	var expected_height: float = main._map_picture_height - main.MAP_PICTURE_SINK_METRES * float(region_index + 1)
	expect(absf(float(after.height) - expected_height) < 0.001,
		"the rebuilt descriptor retains the new region's projection height")
	var plan: Array = main.minimap_background.get("_pictures")
	expect(not plan.is_empty() and plan.back().texture == main._map_picture.texture,
		"the current picture owns overlapping pixels after the handoff")
	var reused: bool = main._tab_map_textures.size() == textures.size()
	for map_id: String in textures:
		reused = reused and main._tab_map_textures[map_id] == textures[map_id]
	expect(reused, "the crossing reuses every decoded texture")
	await process_frame
	await process_frame
	expect(main.world_root.find_children("MapPicture", "MeshInstance3D", true, false).is_empty(),
		"a handoff leaves no obsolete picture geometry in either world")
	expect(main._neighbour_pictures.size() + 1 == textures.size(),
		"one active picture and one picture per other region remain after cleanup")
	select_map(main, "hearthcroft")
	var returned: Dictionary = main._neighbour_pictures["landfall"]
	expect(returned.transform.is_equal_approx(old_frame), "returning across the seam restores the original picture frame")
	main._remove_map_picture()
	expect(main._neighbour_pictures.is_empty() and main._map_picture.is_empty()
		and main.minimap_background.get("_pictures").is_empty()
		and main.full_map_background.get("_pictures").is_empty(),
		"removing the map picture also removes all neighboring pictures")
	print("map picture handoff: %d failures" % failures)
	textures.clear()
	main.queue_free()
	await process_frame
	quit(1 if failures > 0 else 0)
