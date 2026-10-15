## Read the committed scene/resources and bake through the normal source exporter.
## No source save, plan override, runtime build, or preview mutation is persisted.
extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("Usage: --script tools/validate_migrated_terrain.gd -- REGION OUTPUT.json")
		quit(2)
		return
	var region_id: String = args[0]
	var directory := "res://world_authoring/regions/".path_join(region_id)
	var spec = JSON.parse_string(FileAccess.get_file_as_string(directory.path_join("region-authoring-spec.json")))
	if not spec is Dictionary or not spec.get("terrain", {}).has("migration"):
		push_error("Expected an explicitly migrated saved source spec")
		quit(2)
		return
	var packed = load(directory.path_join(region_id + ".tscn"))
	if not packed is PackedScene:
		push_error("Could not load saved region scene")
		quit(2)
		return
	var region = packed.instantiate()
	var terrain = region.get_node("Terrain")
	var expected: Dictionary = spec["terrain"]
	if (terrain.origin != Vector2(expected["origin"][0], expected["origin"][1]) or
			terrain.grid_size != Vector2i(expected["vertices"][0], expected["vertices"][1]) or
			terrain.cell_metres != expected["cellMetres"] or terrain.sculpt_layer != null):
		push_error("Loaded source grid disagrees with migrated spec")
		region.free()
		quit(2)
		return
	# Resolution/export uses saved modifiers normally; mesh previews are unnecessary.
	terrain.preview_enabled = false
	root.add_child(region)
	await process_frame
	if not terrain.refresh_preview():
		push_error("Source resource resolution failed: " + terrain.last_error)
		quit(2)
		return
	var base: PackedFloat32Array = terrain.base_heights()
	if base.size() != terrain.grid_size.x * terrain.grid_size.y:
		push_error("Loaded source resource dimensions mismatch")
		quit(2)
		return
	var document: Dictionary = region.export_snapshot(args[1])
	if document.is_empty():
		quit(2)
		return
	print("MIGRATED_SOURCE_OK ", region_id, " vertices=", base.size(),
		" origin=", terrain.origin, " grid=", terrain.grid_size,
		" resolved_sha256=", document.get("terrain", {}).get("resolvedHeights", {}).get("sha256", ""))
	region.queue_free()
	await process_frame
	quit(0)
