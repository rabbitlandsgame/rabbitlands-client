extends SceneTree
## Exercise the real map, console, HUD buttons and keyboard routing offline.
const Presets := preload("res://src/ui/hud_presets.gd")
const Stack := preload("res://src/ui/window_stack.gd")
const FOLDER := "res://test-artifacts/full-window-views"
class CaptureNetwork extends EloriaNetworkClient:
	func send_frame(_frame: PackedByteArray, _sensitive := false) -> Error: return OK
var checks := 0
var failures := 0
var main: Control
var map_clicks := 0
var console_scrolls := 0

func _init() -> void: call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func frames(count := 5) -> void:
	for index: int in count: await process_frame

func press(key: Key) -> void:
	var event := InputEventKey.new()
	event.keycode = key
	event.physical_keycode = key
	event.pressed = true
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await frames()

func click_at(point: Vector2, button := MOUSE_BUTTON_LEFT) -> void:
	var motion := InputEventMouseMotion.new()
	motion.position = point
	root.push_input(motion, true)
	var event := InputEventMouseButton.new()
	event.position = point
	event.button_index = button
	event.pressed = true
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await frames()

func bounds_match(view: Control) -> bool:
	return view.get_global_rect().is_equal_approx(main.game_view.get_global_rect())

func exposed_point(control: Control) -> Vector2:
	var rect := control.get_global_rect()
	for ratio: Vector2 in [Vector2(0.65, 0.4), Vector2(0.65, 0.25), Vector2(0.65, 0.6), Vector2(0.45, 0.3)]:
		var point := rect.position + rect.size * ratio
		var motion := InputEventMouseMotion.new()
		motion.position = point
		root.push_input(motion, true)
		await frames(1)
		if root.gui_get_hovered_control() == control: return point
	expect(false, "could not find an exposed point on " + str(control.name))
	return rect.get_center()

func close_map(button: Button, label: String) -> void:
	if button.is_visible_in_tree():
		await click_at(button.get_global_rect().get_center())
		expect(not main.full_map.visible, label + ": HUD map button remains clickable over the map")
	else:
		var inventory: Button = main.get_node("%InventoryButton")
		await click_at(inventory.get_global_rect().get_center())
		expect(main.inventory_panel.visible and main.inventory_panel.get_index() > main.full_map.get_index(),
			label + ": visible HUD inventory button works above the map")
		main.inventory_panel.hide()
		root.gui_release_focus()
		await press(KEY_TAB)
		expect(not main.full_map.visible and not button.visible, label + ": Tab closes the map without enabling a hidden HUD icon")

func geometry() -> Dictionary:
	var result := {}
	for key: String in Presets.PARTS:
		var part: Control = main.hud_workspace._root(key)
		result[key] = {"rect": part.get_global_rect(), "scale": part.scale}
	return result

func capture(label: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(FOLDER.path_join(label + ".png"))

func check_world_overlays(shown: bool, label: String) -> void:
	# The frame update must not bring the player's banner back over a view.
	main._update_actor_resource_overlay()
	expect(main.actor_resource_overlay.is_visible_in_tree() == shown,
		label + ": player name, resources and mount banner follow world visibility")
	expect(main._world_text_overlay.is_visible_in_tree() == shown,
		label + ": NPC names, creature banners and world labels follow world visibility")
	expect(main._floating_feedback_layer.is_visible_in_tree() == shown,
		label + ": floating damage and experience follow world visibility")
	main._world_text_overlay._sync_camera()
	expect(main._world_text_overlay.text_viewport.render_target_update_mode ==
		(SubViewport.UPDATE_ALWAYS if shown else SubViewport.UPDATE_DISABLED),
		label + ": the world text pass only renders while visible")

func check_overlay_transitions() -> void:
	main.set_process(false)
	var state := root.get_node("AppState")
	var previous_id: int = state.local_actor_id
	state.local_actor_id = 9001
	var actor := Node3D.new()
	main.world_root.add_child(actor)
	actor.global_position = main.gameplay_camera.global_position \
		- main.gameplay_camera.global_basis.z * 8.0 - Vector3.UP * 2.8
	main.actor_nodes[state.local_actor_id] = actor
	var npc_name := Label3D.new()
	npc_name.text = "NPC name and quest marker"
	preload("res://src/ui/world_label_style.gd").apply(npc_name, 12, 0.01, 4)
	actor.add_child(npc_name)
	npc_name.position.y = 2.8
	var feedback := Label.new()
	feedback.text = "+12 Experience"
	feedback.position = main.game_view.size * 0.5 + Vector2(-50, 80)
	main._floating_feedback_layer.add_child(feedback)
	check_world_overlays(true, "gameplay")
	await frames()
	await capture("world-overlays-gameplay")
	main._toggle_full_map()
	check_world_overlays(false, "map opened")
	await frames()
	await capture("world-overlays-map")
	main._toggle_console()
	check_world_overlays(false, "map switched to console")
	await frames()
	await capture("world-overlays-console")
	main.console_panel.hide()
	check_world_overlays(true, "console closed directly")
	main._toggle_console()
	main._toggle_full_map()
	check_world_overlays(false, "console switched to map")
	main.full_map.hide()
	check_world_overlays(true, "map closed directly")
	# Either visible view must keep annotations hidden even if the other closes.
	main.full_map.show()
	main.console_panel.show()
	main.full_map.hide()
	check_world_overlays(false, "console remains open")
	main.console_panel.hide()
	check_world_overlays(true, "both views closed")
	main.actor_nodes.erase(state.local_actor_id)
	state.local_actor_id = previous_id
	actor.queue_free()
	feedback.queue_free()
	main.set_process(true)

func check_layout(label: String) -> void:
	var workspace: Control = main.hud_workspace
	await frames()
	var layout: Dictionary = workspace.model.working.duplicate(true)
	var before := geometry()
	var button: Button = main.get_node("%MapButton")
	root.gui_release_focus()
	await press(KEY_TAB)
	expect(main.full_map.visible and not main.console_panel.visible, label + ": Tab opens only the map")
	expect(bounds_match(main.full_map), label + ": map fills the complete game window")
	expect(main.full_map.get_index() > main.viewport_container.get_index()
		and main.full_map.get_index() < main.get_node("%Quickbar").get_index()
		and main.full_map.z_index <= main.get_node("%Quickbar").z_index,
		label + ": map draws and receives clicks below the HUD")
	var previous_map_clicks := map_clicks
	await click_at(await exposed_point(main.map_image))
	expect(map_clicks == previous_map_clicks + 1, label + ": exposed map surface still receives clicks")
	if label in ["heritage", "adventure"]: await capture(label + "-map")
	await press(KEY_T)
	expect(main.chat_hud.is_visible_in_tree() and main.chat_input.has_focus()
		and main.chat_hud.get_index() > main.full_map.get_index(), label + ": chat hotkey opens chat above the map")
	main._hide_chat_input()
	root.gui_release_focus()
	await close_map(button, label)
	expect(map_clicks == previous_map_clicks + 1, label + ": HUD click does not leak into the map")
	root.gui_release_focus()
	await press(KEY_QUOTELEFT)
	expect(main.console_panel.visible and not main.full_map.visible, label + ": console hotkey opens only the console")
	expect(bounds_match(main.console_panel), label + ": console fills the complete game window")
	expect(main.console_panel.get_index() > main.viewport_container.get_index()
		and main.console_panel.get_index() < main.get_node("%Quickbar").get_index()
		and main.console_panel.z_index <= main.get_node("%Quickbar").z_index,
		label + ": console remains below the HUD")
	var diagnostics: Button = main.get_node("%ConsoleDiagnostics")
	await click_at(diagnostics.get_global_rect().get_center())
	expect(main.diagnostics_output.visible and not main.console_output.visible, label + ": console protocol button is accessible beside the HUD")
	await click_at(diagnostics.get_global_rect().get_center())
	expect(main.console_output.visible, label + ": console history can be restored with its toolbar")
	var previous_scrolls := console_scrolls
	await click_at(await exposed_point(main.console_output), MOUSE_BUTTON_WHEEL_DOWN)
	expect(console_scrolls == previous_scrolls + 1, label + ": console history still receives scrolling")
	if label in ["heritage", "adventure"]: await capture(label + "-console")
	root.gui_release_focus()
	await press(KEY_T)
	expect(main.chat_hud.is_visible_in_tree() and main.chat_input.has_focus()
		and main.chat_hud.get_index() > main.console_panel.get_index(), label + ": chat hotkey works above the console")
	main._hide_chat_input()
	root.gui_release_focus()
	var close: Button = main.get_node("%ConsoleClose")
	await click_at(close.get_global_rect().get_center())
	expect(not main.console_panel.visible, label + ": console Close button stays accessible")
	root.gui_release_focus()
	await press(KEY_QUOTELEFT)
	if button.is_visible_in_tree():
		await click_at(button.get_global_rect().get_center())
		expect(main.full_map.visible and not main.console_panel.visible, label + ": HUD map button can switch from console to map")
	else:
		await press(KEY_TAB)
		expect(main.full_map.visible and not main.console_panel.visible, label + ": Tab switches from console to map")
	await close_map(button, label)
	expect(workspace.model.working == layout, label + ": opening and closing views preserves every HUD setting")
	var after := geometry()
	for key: String in before:
		if before[key] != after[key]:
			print("HUD geometry changed: ", label, " / ", key, ": ", before[key], " -> ", after[key])
	expect(geometry() == before, label + ": HUD positions and sizes stay unchanged")

func run() -> void:
	create_timer(150).timeout.connect(func() -> void: quit(99))
	var network := root.get_node("Network")
	network.set_script(CaptureNetwork)
	network.block_for_hud_preview()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	var path := FOLDER.path_join("settings.cfg")
	ConfigFile.new().save(path)
	root.size = Vector2i(1440, 900)
	main = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = path
	root.add_child(main)
	await frames(8)
	InputMap.load_from_project_settings()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	await check_overlay_transitions()
	main.map_image.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT: map_clicks += 1)
	main.console_output.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN: console_scrolls += 1)
	var workspace: Control = main.hud_workspace
	for id: String in Presets.BUILT_INS:
		workspace.choose_preset(id, true)
		await check_layout(id)
	workspace.choose_preset("heritage", true)
	var toolbar: Dictionary = workspace.model.working.parts.utilities
	toolbar.anchor = "free"
	toolbar.position = Vector2(0.2, 0.45)
	toolbar.offset = Vector2.ZERO
	toolbar.dock_target = "none"
	toolbar.edge_dock = "none"
	toolbar.extend_to_edge = false
	workspace.apply_layout()
	await frames()
	var custom: String = workspace.model.save_custom("Floating controls")
	workspace.choose_preset(custom)
	await check_layout("custom")
	var saved: Dictionary = workspace.model.custom[custom].duplicate(true)
	for dimensions: Vector2i in [Vector2i(800, 600), Vector2i(1920, 1080), Vector2i(1440, 900)]:
		root.size = dimensions
		await frames(8)
		expect(bounds_match(main.full_map) and bounds_match(main.console_panel), "both views follow window resize to %s" % dimensions)
		main._toggle_full_map()
		await frames()
		main._toggle_console()
		await frames()
		expect(bounds_match(main.console_panel), "visible console fills resized window %s" % dimensions)
		main._toggle_console()
	for scale: float in [0.75, 1.5, 1.0]:
		main._on_ui_scale_changed(scale)
		await frames(8)
		expect(bounds_match(main.full_map) and bounds_match(main.console_panel), "both views follow %d percent UI scale" % roundi(scale * 100))
	main._toggle_console()
	main.console_panel.move_to_front()
	await frames()
	expect(main.console_panel.get_index() < main.get_node("%Quickbar").get_index(), "view ordering recovers after an external raise")
	Stack.activate(main.console_panel)
	await frames()
	expect(main.console_panel.get_index() < main.chat_hud.get_index(), "activating a full-window view cannot cover chat")
	main.popup_panel.show()
	await frames()
	expect(main.popup_panel.get_index() > main.console_panel.get_index()
		and main.popup_panel.z_index > main.chat_hud.z_index, "confirmation windows retain priority")
	main.popup_panel.hide()
	main._toggle_console()
	expect(workspace.model.custom[custom] == saved, "window resize and UI scaling do not overwrite the saved custom design")
	main.queue_free()
	await frames()
	Input.set_custom_mouse_cursor(null, Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_IBEAM)
	(load("res://src/ui/hud_medallion.gd") as GDScript)._textures.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._cache.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._tinted.clear()
	(load("res://src/ui/technique_icons.gd") as GDScript)._cache.clear()
	print("FULL WINDOW VIEWS: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
