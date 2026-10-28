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
## - Exit labels are kept above the bottom HUD in the 3D view
##   (`_label_floor_y`): on Main's default (heritage) HUD layout in a
##   1600x900 window, as a new player sees it, a label over the middle of the
##   screen is floored by the resource strip above the quickbar (final review
##   2026-10-27, finding 2: the quickbar's top left the market's exit label
##   under the strip), a window standing clear of the bars (the system chat)
##   floors nothing, and a real exit label 5.5 m from a camera-side door is
##   lifted clear of the strip. Outside an interior no partition screens a
##   name.

const HudPresets := preload("res://src/ui/hud_presets.gd")
## The market's street door (Hanne's Provisions): its exit is the label the
## review found under the resource strip.
const DOOR := 59202

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("PASS: ", message)

## A control's rectangle in Main's 3D viewport pixels.
static func _view_rect(main: Control, control: Control) -> Rect2:
	var rect := control.get_global_rect()
	var top_left: Vector2 = main._viewport_position(rect.position)
	return Rect2(top_left, main._viewport_position(rect.end) - top_left)

## Exit labels keep above the bottom HUD: Main's default HUD layout (a fresh
## profile's, chosen again here as the factory default), in the 3D view's
## pixels.
func _test_label_floor(main: Control) -> void:
	main.game_view.show()
	var workspace: Control = main.hud_workspace
	for wait: int in 30:
		if workspace != null and workspace.ready_to_layout:
			break
		await process_frame
		workspace = main.hud_workspace
	_expect(workspace != null and workspace.ready_to_layout, "(fixture) Main's HUD workspace is configured")
	if workspace == null or not workspace.ready_to_layout:
		return
	workspace.choose_preset(HudPresets.DEFAULT_PRESET, true)
	for frame: int in 3:
		await process_frame
	var view_size := Vector2(main.main_viewport.size)
	var bar: Control = main.get_node("%Quickbar")
	var strip: Control = workspace.modern_resources
	var chat: Control = main.system_chat_hud
	var bar_rect := _view_rect(main, bar)
	var strip_rect := _view_rect(main, strip)
	var chat_rect := _view_rect(main, chat)
	_expect(str(workspace.model.active) == HudPresets.DEFAULT_PRESET and workspace.manages_layout()
		and bar.is_visible_in_tree() and strip.is_visible_in_tree() and not main.bottom_meters.is_visible_in_tree()
		and strip_rect.position.y < bar_rect.position.y - 1.0,
		"the default (%s) layout draws the meters in its resource strip above the quickbar (strip top %.0f, quickbar top %.0f of %.0f px)"
			% [HudPresets.DEFAULT_PRESET, strip_rect.position.y, bar_rect.position.y, view_size.y])
	# The market's exit label stood at the middle of the screen, over both.
	var middle := view_size.x * 0.5
	var floor_y: float = main._label_floor_y(middle - 60.0, middle + 60.0)
	_expect(is_equal_approx(floor_y, strip_rect.position.y) and floor_y < bar_rect.position.y,
		"a label over the middle of the screen keeps above the strip's top (%.0f px), not the quickbar's (%.0f)"
			% [floor_y, bar_rect.position.y])
	_expect(chat.is_visible_in_tree() and chat_rect.position.y > view_size.y * 0.5 and chat_rect.end.y < strip_rect.position.y
		and is_equal_approx(main._label_floor_y(chat_rect.position.x, chat_rect.end.x), strip_rect.position.y),
		"the system chat standing clear above the strip (%.0f-%.0f px) floors nothing: under it the strip does"
			% [chat_rect.position.y, chat_rect.end.y])
	_expect(main._label_floor_y() <= strip_rect.position.y + 0.5,
		"no floor is lower than the strip's for a label spanning the whole width (%.0f px)" % [main._label_floor_y()])
	bar.hide()
	_expect(is_equal_approx(main._label_floor_y(middle - 60.0, middle + 60.0), strip_rect.position.y),
		"with the quickbar hidden the strip still floors the label")
	strip.hide()
	_expect(is_equal_approx(main._label_floor_y(middle - 60.0, middle + 60.0), view_size.y),
		"with the strip hidden too the floor is the view's bottom")
	strip.show()
	bar.show()
	await _test_exit_lift(main, strip_rect.position.y)

## A real exit label seen through the town's camera (-50 degrees, 12 m, fov
## 50) in a view the size of Main's, the player 5.5 m from its camera-side
## door: under the strip as drawn, lifted clear of it by Main's floor.
func _test_exit_lift(main: Control, strip_top: float) -> void:
	var view := SubViewport.new()
	view.size = main.main_viewport.size
	view.own_world_3d = true
	view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(view)
	var camera := Camera3D.new()
	camera.fov = 50.0
	view.add_child(camera)
	camera.current = true
	var catalog := {"authoredObjects": {str(DOOR): {"entrance": true, "building": true, "exteriorTile": [10, 12],
		"label": "Hanne's Provisions", "exitLabel": "The avenue", "category": "general_store",
		"height": 3.0, "radius": 1.2, "exitOffset": [0.0, 0.0, 1.0]}}}
	var exit := MapObject3D.new()
	exit.configure({"object_id": DOOR, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE, "x": 40, "y": 40,
		"label": "Portal", "detail": "The avenue."}, CoordinateAdapter.new({}), catalog)
	view.add_child(exit)
	await process_frame
	var title := exit.get_node("EntranceLabel") as Label3D
	var player := exit.global_position + Vector3(0.0, 0.0, 1.0 - 5.5)
	exit.update_label_focus(player, false)
	var pitch := deg_to_rad(-50.0)
	camera.global_position = player + Vector3(0.0, -sin(pitch), cos(pitch)) * 12.0
	camera.look_at(player + Vector3.UP * 1.2, Vector3.UP)
	var per_unit := MapObject3D.screen_pixels_per_unit(camera)
	var bottom_of := func() -> float:
		return camera.unproject_position(title.global_position).y - title.offset.y * title.pixel_size * per_unit \
			+ MapObject3D.label_half_height(title) * per_unit
	var unlifted: float = bottom_of.call()
	var span := exit.label_span(camera)
	var lift := exit.keep_label_above(camera, main._label_floor_y(span.x, span.y))
	_expect(title.visible and exit.building_exit and unlifted > strip_top and lift > 0.0
		and float(bottom_of.call()) <= strip_top - MapObject3D.LABEL_HUD_MARGIN + 1.0,
		"an exit label 5.5 m from a camera-side door (to %.0f px as drawn, %.0f..%.0f px wide) is lifted %.0f px, clear of the strip (to %.0f px, strip top %.0f)"
			% [unlifted, span.x, span.y, lift, float(bottom_of.call()), strip_top])
	view.queue_free()
	await process_frame

static func _manifest(data: Dictionary) -> WorldManifest:
	var manifest := WorldManifest.new()
	manifest.data = data
	return manifest

func _run() -> void:
	# The window a new player's default HUD layout is laid out for (headless
	# otherwise starts at 64x64).
	root.size = Vector2i(1600, 900)
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
	await _test_label_floor(main)
	_expect(main.interior_cutaway.has_method("screens") and not main.interior_cutaway.screens(Vector3.ZERO, Vector3.ONE),
		"names are screened only by an interior's standing partitions (none outside)")
	main.queue_free()
	for frame: int in 3:
		await process_frame
	print("Main interior hooks: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)
