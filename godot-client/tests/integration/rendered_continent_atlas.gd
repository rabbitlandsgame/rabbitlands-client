extends SceneTree

## Full map-window proof without loading an unrelated 3D region.
var _main: Control
var _output := ""

func _init() -> void:
	call_deferred("_run")

func _capture(name: String) -> void:
	for frame: int in range(5):
		await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(_output.path_join(name + ".png"))

func _run() -> void:
	_output = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(_output)
	root.size = Vector2i(1440, 900)
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	(_main.get_node("LoginBackground") as Control).hide()
	(_main.get_node("LoginPanel") as Control).hide()
	(_main.get_node("GameView") as Control).show()
	root.get_node("AppState").set("current_map", "four_gates")
	var baseline: String = OS.get_environment("ELORIA_ATLAS_BASELINE")
	if not baseline.is_empty():
		var old: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(baseline))
		old.continent.texture = baseline.get_base_dir().path_join("before.webp")
		_main.set("cartography", old)
		_main.set("cartography_regions", old.regions)
		(_main.get("continent_map") as Control).free()
		_main.call("_configure_cartography")
	_main.call("_toggle_full_map")
	_main.call("_show_continent_view")
	await _capture("continent")
	var overlay: Control = _main.get("continent_map") as Control
	var regions: Array = _main.get("cartography_regions")
	var checked := 0
	for index: int in range(regions.size()):
		var label: Vector2 = overlay.call("region_label_position", index)
		assert(int(overlay.call("region_at", label)) == index)
		checked += 1
	var index: int = _main.call("_region_index_for_map", "sunmane_steppe")
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = overlay.call("region_label_position", index)
	overlay.call("_gui_input", click)
	assert((_main.get("region_preview") as TextureRect).visible)
	await _capture("sunmane-click-preview")
	var report := {"regionCentresClickable": checked, "previewOpened": true,
		"baselineLayout": not baseline.is_empty(), "resolution": [1440, 900]}
	var file := FileAccess.open(_output.path_join("report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	print("Continent atlas render PASS: ", checked, " regions and clicked preview")
	_main.queue_free()
	await process_frame
	quit(0)
