extends SceneTree
## Projection/picking checks across the actual map catalogue, plus optional renders.

const MapView := preload("res://src/world/map_view.gd")
const Overlay := preload("res://src/ui/map_marker_overlay.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var viewport := SubViewport.new()
	root.add_child(viewport)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	viewport.add_child(camera)
	var overlay := Overlay.new()
	root.add_child(overlay)
	overlay.size = Vector2(1100.0, 700.0)
	var catalogue: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
		"res://data/maps/registry.json"))["maps"]
	var visited: Dictionary = {}
	var tested := 0
	for entry: Dictionary in catalogue.values():
		var path := str(entry.get("manifest", ""))
		if path.is_empty() or visited.has(path):
			continue
		visited[path] = true
		var manifest := WorldManifest.load_file(ProjectSettings.globalize_path(path))
		var bounds := MapView.bounds_for(manifest)
		_expect(bounds.size.x > 0.0 and bounds.size.z > 0.0, "map has framing bounds: " + path)
		if bounds.size.x <= 0.0 or bounds.size.z <= 0.0:
			continue
		if bool(manifest.data.get("secret", false)):
			for section: Dictionary in manifest.data.get("sections", []):
				var section_bounds := MapView.bounds_for(manifest, str(section["id"]))
				var declared: Dictionary = section["bounds"]
				_expect(is_equal_approx(section_bounds.position.x, float(declared["min"][0]))
					and is_equal_approx(section_bounds.end.z, float(declared["max"][1]))
					and section_bounds.size.x < bounds.size.x,
					"secret view contains only its current section: " + str(section["id"]))
		tested += 1
		MapView.configure(camera, viewport, bounds)
		await process_frame
		var adapter := manifest.coordinate_adapter()
		overlay.configure(camera, adapter, viewport.size)
		var low := camera.unproject_position(bounds.position)
		var high := camera.unproject_position(bounds.end)
		var span := (high - low).abs() / Vector2(viewport.size)
		_expect(span.x > 0.95 and span.y > 0.95 and span.x < 1.0 and span.y < 1.0,
			"playable area fills both texture dimensions: " + path)
		_expect(is_zero_approx(camera.rotation.y), "north remains -Z: " + path)
		for fraction: Vector2 in [Vector2(0.1, 0.1), Vector2(0.5, 0.5), Vector2(0.9, 0.9)]:
			var world := bounds.position + Vector3(bounds.size.x * fraction.x, 0.0,
				bounds.size.z * fraction.y)
			var tile := adapter.godot_to_server(world)
			world = adapter.tile_center(tile.x, tile.y)
			var pixel := camera.unproject_position(world)
			var origin := camera.project_ray_origin(pixel)
			var direction := camera.project_ray_normal(pixel)
			var picked := origin + direction * ((world.y - origin.y) / direction.y)
			_expect(adapter.godot_to_server(picked) == tile, "click round-trip: " + path)
		var mark := {"position": bounds.get_center(), "glyph": "P", "label": "Destination"}
		overlay.set_waypoints([mark])
		var point: Vector2 = overlay._texture_position(camera.unproject_position(mark.position))
		_expect(overlay.label_at(point) == "Destination", "hover uses matching projection: " + path)
		_expect(overlay.label_at(point + Vector2(40.0, 0.0)).is_empty(), "hover stays local")
		overlay.set_live_marks([{"position": mark.position, "type": &"self", "radius": 5.5}, mark])
		_expect(overlay._live_overlay._marks.size() == 1, "portal glyph is drawn only once")
		_expect(is_equal_approx(overlay._live_overlay.mark_radius({"radius": 5.5}), 5.5),
			"player dot stays the same size at every extent")
	print("Map catalogue: ", tested, " maps checked")
	overlay.queue_free()
	viewport.queue_free()
	await process_frame
	if "--capture" in OS.get_cmdline_user_args():
		await _capture_maps(catalogue)
	print("Map view: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _capture_maps(catalogue: Dictionary) -> void:
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	_expect(not output.is_empty(), "capture directory supplied")
	if output.is_empty():
		return
	root.get_node("AppState").set("game_minute", 180)
	root.size = Vector2i(1280, 800)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.get("login_panel").hide()
	main.get("game_view").show()
	for id: String in ["mirrorhold", "four_gates", "sunmane_steppe", "mirrorhold_interiors"]:
		var entry: Dictionary = catalogue[id]
		main.set("adapter", CoordinateAdapter.new(entry["coordinateTransform"]))
		var loader: WorldLoader = main.get("world_loader")
		loader.load_world(ProjectSettings.globalize_path(entry["manifest"]))
		var deadline := Time.get_ticks_msec() + 30000
		while loader.world_root == null and Time.get_ticks_msec() < deadline:
			await process_frame
		_expect(loader.world_root != null, "rendered map loaded: " + id)
		main.call("_show_current_map_view")
		main.get("full_map").show()
		var waypoints: Array[Dictionary] = []
		for portal: Dictionary in loader.manifest.data.get("portals", []):
			var p: Array = portal.get("position", [])
			if p.size() != 3:
				continue
			waypoints.append({"position": Vector3(p[0], p[1], p[2]), "glyph": "P",
				"colour": Color(0.2, 0.85, 1.0), "label": portal.get("destinationMap", "")})
		var map_overlay: Control = main.get("map_marker_overlay")
		map_overlay.set_waypoints(waypoints)
		var live_marks: Array[Dictionary] = [{"position": MapView.bounds_for(loader.manifest).get_center(),
			"type": &"self", "colour": Color.WHITE, "radius": 5.5}]
		map_overlay.set_live_marks(live_marks)
		main.get("full_map_viewport").render_target_update_mode = SubViewport.UPDATE_ALWAYS
		for frame: int in range(8):
			await process_frame
		RenderingServer.force_draw(false)
		var capture := root.get_texture().get_image()
		_expect(capture.save_png(output.path_join(id + ".png")) == OK, "saved " + id)
	main.queue_free()
	await process_frame

func _expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
