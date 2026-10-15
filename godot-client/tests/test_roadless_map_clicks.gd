extends SceneTree

var failures := 0
var checks := 0
var main_scene: PackedScene
var main_script: Script
var probe_script: Script
var walk_harness: Script

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# Runtime loads match the established headless tests. Preloading a subclass
	# of main.gd from a --script entry point compiles it before autoload singleton
	# names have been registered.
	main_scene = load("res://src/app/main.tscn") as PackedScene
	main_script = load("res://src/app/main.gd") as Script
	probe_script = load("res://tests/fixtures/roadless_map_click_probe.gd") as Script
	walk_harness = load("res://tests/integration/rendered_landscape_walk.gd") as Script
	_check_fixture_validation()
	_check_letterboxed_projection()
	await _check_actual_map_handlers()
	print("Roadless map clicks: %d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)

func _check_fixture_validation() -> void:
	_expect(walk_harness.map_click_fixture_error({"tile": [1, 2]}).is_empty(),
		"a terrain click remains the default when mapClick is absent")
	_expect("full_map or minimap" in walk_harness.map_click_fixture_error({
		"tile": [1, 2], "clickNeighbor": true, "destination": "grey_moors",
		"mapClick": "atlas"}),
		"an unknown mapClick value is rejected visibly")
	_expect("clickNeighbor=true" in walk_harness.map_click_fixture_error({
		"tile": [1, 2], "destination": "grey_moors", "mapClick": "minimap"}),
		"a map click cannot silently become a same-map movement fixture")
	_expect(walk_harness.map_click_fixture_error({
		"tile": [1, 2], "clickNeighbor": true, "destination": "grey_moors",
		"mapClick": "full_map"}).is_empty(),
		"a complete full-map neighbour fixture is accepted")

func _check_letterboxed_projection() -> void:
	var texture_rect := TextureRect.new()
	texture_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	for fixture: Dictionary in [
			{"control": Vector2(400, 200), "viewport": Vector2i(100, 100),
				"pixel": Vector2(25, 75), "local": Vector2(150, 150)},
			{"control": Vector2(200, 400), "viewport": Vector2i(160, 90),
				"pixel": Vector2(120, 18), "local": Vector2(150, 166.25)}]:
		texture_rect.size = fixture.control
		var local_value: Variant = walk_harness.viewport_to_texture_position(
			fixture.pixel, texture_rect, fixture.viewport)
		_expect(local_value is Vector2 and (local_value as Vector2).distance_to(
			fixture.local) < 0.001,
			"non-square map projection accounts for centered letterboxing")
		if local_value is Vector2:
			var round_trip: Variant = main_script._texture_to_viewport_position(
				local_value as Vector2, texture_rect, fixture.viewport)
			_expect(round_trip is Vector2 and (round_trip as Vector2).distance_to(
				fixture.pixel) < 0.001,
				"fixture projection round-trips through the production click conversion")
	_expect(walk_harness.viewport_to_texture_position(
		Vector2(-1, 50), texture_rect, Vector2i(100, 100)) == null,
		"a viewport point outside the rendered frame is rejected")
	texture_rect.free()

func _check_actual_map_handlers() -> void:
	root.size = Vector2i(1100, 720)
	var main: Control = main_scene.instantiate() as Control
	main.set_script(probe_script)
	root.add_child(main)
	await process_frame
	main.set_process(false)
	(main.get("game_view") as Control).show()
	for panel_name: String in ["dialogue_panel", "trade_panel", "storage_panel",
			"manufacturing_panel"]:
		(main.get(panel_name) as Control).hide()
	var adapter := CoordinateAdapter.new({
		"metresPerTile": 1.0, "serverOrigin": [0.0, 0.0],
		"origin": [0.0, 31.15, 0.0], "walkingHeight": 31.15,
		"invertServerY": false})
	main.set("adapter", adapter)
	main.set("cartography", {"continent": {
		"originMetres": [0.0, 0.0], "metresPerPixel": 1.0}})
	main.set("cartography_regions", [
		{"serverMap": "four_gates", "globalTranslation": [0.0, 0.0, 0.0],
			"continentPolygon": [[0.0, 0.0], [50.0, 0.0], [50.0, 100.0], [0.0, 100.0]]},
		{"serverMap": "grey_moors", "globalTranslation": [0.0, 0.0, 0.0],
			"continentPolygon": [[50.0, 0.0], [100.0, 0.0], [100.0, 100.0], [50.0, 100.0]]}])
	main.set("_region_polygons", ([] as Array[PackedVector2Array]))
	var source_manifest := WorldManifest.new()
	source_manifest.data = {"coordinateTransform": {
		"serverOrigin": [0, 0], "serverCells": [128, 128]}}
	(main.get("world_loader") as WorldLoader).manifest = source_manifest
	root.get_node("AppState").set("current_map", "four_gates")
	var target := Vector2i(60, 40)
	var point := adapter.tile_center(target.x, target.y)
	_expect(bool(main.call("_tile_inside_current_map", target)),
		"the neighbour-owned regression target remains inside the source served rectangle")
	_expect(str(main.call("_map_owning_point", point)) == "grey_moors",
		"the cartography polygon assigns the border target to the neighbour")
	var full_map: Control = main.get("full_map") as Control
	if not full_map.visible:
		main.call("_on_map_button_pressed")
	await process_frame
	await _exercise_map_control(main, "full_map", main.get("map_image") as TextureRect,
		main.get("full_map_viewport") as SubViewport,
		main.get("full_map_camera") as Camera3D, point, target)
	if full_map.visible:
		main.call("_on_map_button_pressed")
	var minimap_frame: Control = main.get("minimap_frame") as Control
	if not minimap_frame.visible:
		main.call("_on_minimap_button_pressed")
	await process_frame
	await _exercise_map_control(main, "minimap", main.get("minimap") as TextureRect,
		main.get("map_viewport") as SubViewport,
		main.get("map_camera") as Camera3D, point, target)
	if minimap_frame.visible:
		main.call("_on_minimap_button_pressed")
	main.queue_free()
	await process_frame

func _exercise_map_control(main: Control, source: String, map_control: TextureRect,
		map_viewport: SubViewport, camera: Camera3D, point: Vector3,
		target: Vector2i) -> void:
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 120.0
	camera.global_position = Vector3(50.0, 220.0, 50.0)
	camera.rotation = Vector3(-PI * 0.5, 0.0, 0.0)
	await process_frame
	var viewport_position := camera.unproject_position(point)
	var local_value: Variant = walk_harness.viewport_to_texture_position(
		viewport_position, map_control, map_viewport.size)
	_expect(local_value is Vector2, "%s target projects into its displayed texture" % source)
	if not local_value is Vector2:
		return
	main.call("clear_map_click_dispatches")
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = local_value as Vector2
	map_control.gui_input.emit(click)
	var dispatches: Array = main.get("map_click_dispatches") as Array
	_expect(dispatches.size() == 1,
		"%s gui_input reaches the actual beyond-seam handler" % source)
	if dispatches.size() != 1:
		return
	var dispatch: Dictionary = dispatches[0] as Dictionary
	_expect(str(dispatch.get("source", "")) == source
		and str(dispatch.get("owner", "")) == "grey_moors",
		"%s handler dispatches to the neighbour polygon owner" % source)
	_expect(dispatch.get("tile") == target,
		"%s handler retains exact neighbour target %s" % [source, target])

func _expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		if failures <= 12:
			push_error("FAIL: " + label)
