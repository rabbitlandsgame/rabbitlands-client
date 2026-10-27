extends SceneTree
## Main's hooks for building interiors, headless, on the real app scene:
##
##   godot --headless --path godot-client --script res://tests/test_main_interior_hooks.gd
##
## - The live minimap frames a map's own span when its manifest states one
##   (`minimap.liveSpanMetres`, Landfall Town: a room reads at minimap size),
##   scaled by the player's zoom, and the player's zoom elsewhere.
## - WorldPark is told the arrival has settled only once the curtain is down
##   and the arrival is no longer pending (no preload competes with it), and a
##   new map change forgets it.
## - Exit labels are kept above the bottom HUD bar's top edge in the 3D view
##   (`_label_floor_y`); outside an interior no partition screens a name.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

static func _manifest(data: Dictionary) -> WorldManifest:
	var manifest := WorldManifest.new()
	manifest.data = data
	return manifest

func _run() -> void:
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	var camera: Camera3D = main.map_camera
	var zoom: float = main._minimap_zoom
	main._bind_minimap_span(_manifest({"minimap": {"liveSpanMetres": 40}}))
	_expect(is_equal_approx(camera.size, 40.0 * zoom / main.MINIMAP_ZOOM_DEFAULT),
		"a map stating liveSpanMetres frames that span at the player's zoom (%.1f m)" % camera.size)
	main._minimap_zoom = main.MINIMAP_ZOOM_DEFAULT * 2.0
	main._apply_minimap_zoom()
	_expect(is_equal_approx(camera.size, 80.0), "the scroll wheel still scales the stated span")
	main._minimap_zoom = zoom
	main._bind_minimap_span(_manifest({"asset": {"id": "landfall"}}))
	_expect(is_equal_approx(camera.size, zoom), "a map stating no span keeps the player's own zoom")
	main._bind_minimap_span(_manifest({"minimap": {"liveSpanMetres": "wide"}}))
	_expect(is_equal_approx(camera.size, zoom), "a span that is not a number is ignored")
	# The settled arrival WorldPark waits for.
	var state: Node = root.get_node("AppState")
	state.current_map = "landfall"
	main.loaded_server_map = "landfall"
	state.local_actor_id = 7
	state.actors = {7: {"id": 7, "x": 104, "y": 247, "map": "landfall"}}
	main._world_park_settled = ""
	main.arrival_curtain.begin("Entering Landfall")
	main._observe_world_park()
	_expect(main._world_park_settled == "", "nothing is settled while the arrival curtain is up")
	main.arrival_curtain.cancel()
	main._arrival = {"position": Vector3.ZERO, "started": 0, "ready": false}
	main._observe_world_park()
	_expect(main._world_park_settled == "", "nor while the arrival is still pending")
	main._arrival = {}
	main._observe_world_park()
	_expect(main._world_park_settled == "landfall", "once the arrival is down and loaded, the map is settled")
	main.loaded_server_map = "landfall_town"
	state.current_map = "landfall_town"
	_expect(main._world_park_settled != main.loaded_server_map, "another map is not settled by the last one")
	# Exit labels keep above the bottom HUD bar: its top edge in the 3D view's pixels.
	var bar: Control = main.get_node("%Quickbar")
	var view_height := float(main.main_viewport.size.y)
	main.game_view.show()
	bar.show()
	var floor_y: float = main._label_floor_y()
	var expected: float = main._viewport_position(bar.get_global_rect().position).y
	_expect(floor_y > 0.0 and floor_y < view_height and is_equal_approx(floor_y, minf(view_height, expected)),
		"the labels' floor is the quickbar's top edge in the 3D view (%.0f of %.0f px)" % [floor_y, view_height])
	bar.hide()
	_expect(is_equal_approx(main._label_floor_y(), view_height), "with the bar hidden it is the view's bottom")
	bar.show()
	_expect(main.interior_cutaway.has_method("screens") and not main.interior_cutaway.screens(Vector3.ZERO, Vector3.ONE),
		"names are screened only by an interior's standing partitions (none outside)")
	main.queue_free()
	for frame: int in 3:
		await process_frame
	print("Main interior hooks: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)
