extends SceneTree

## The Landfall boat network on the map window's continent view: the routes
## and docks, then the cursor on the Lakehead hub and on Suncoil, an isle only
## boats reach. Writes PNGs and report.json to ELORIA_ARTIFACT_DIR.
var _main: Control
var _output := ""

func _init() -> void:
	call_deferred("_run")

func _capture(name: String) -> void:
	for frame: int in range(5):
		await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(_output.path_join(name + ".png"))

func _hover(dock_id: String) -> String:
	var overlay: Control = _main.get("continent_map") as Control
	var boats: Control = _main.get("_boat_continent_overlay") as Control
	var docks: Array = ((_main.get("_v2_cartography") as Dictionary)["boatNetwork"] as Dictionary)["docks"]
	for index: int in range(docks.size()):
		if str((docks[index] as Dictionary).id) != dock_id:
			continue
		var motion := InputEventMouseMotion.new()
		motion.position = overlay.get_global_transform().affine_inverse() * (
			boats.get_global_transform() * (boats.call("dock_point", index) as Vector2))
		overlay.gui_input.emit(motion)
		overlay.call("_gui_input", motion)
		assert(int(boats.call("hovered_dock")) == index)
	return (_main.get("map_coordinates") as Label).text

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
	root.get_node("AppState").set("current_map", "landfall")
	_main.set("_current_map_display_name", "Landfall")
	_main.call("_toggle_full_map")
	_main.call("_show_continent_view")
	var boats: Control = _main.get("_boat_continent_overlay") as Control
	assert(int(boats.call("dock_count")) == 12 and int(boats.call("route_count")) == 12)
	await _capture("landfall-boat-routes")
	var hub := _hover("lakehead")
	await _capture("landfall-boat-routes-lakehead")
	var isle := _hover("suncoil")
	await _capture("landfall-boat-routes-suncoil")
	var report := {"docks": int(boats.call("dock_count")), "routes": int(boats.call("route_count")),
		"lakeheadHover": hub, "suncoilHover": isle, "resolution": [1440, 900]}
	var file := FileAccess.open(_output.path_join("report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	print("Landfall boat routes render PASS: ", report)
	_main.queue_free()
	await process_frame
	quit(0)
