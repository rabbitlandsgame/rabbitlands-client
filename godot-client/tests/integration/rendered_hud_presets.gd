extends SceneTree
## Render production controls with representative offline state. No connection
## or player profile is required; output stays in ignored test artifacts.
const FOLDER := "res://test-artifacts/hud-presets/rendered-heritage-rail"
var main: Control
var app: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.get_node("Network").block_for_hud_preview()
	create_timer(600 if OS.get_cmdline_user_args().has("--hud-public-guide") else 120).timeout.connect(func() -> void: quit(99))
	root.size = Vector2i(1440, 900)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	var settings := FOLDER.path_join("render.cfg")
	var config := ConfigFile.new()
	config.save(settings)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = settings
	root.add_child(main)
	for frame: int in 6: await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	root.content_scale_factor = 1.0
	app = root.get_node("AppState")
	var preview_state: GDScript = load("res://prototypes/hud_preview_state.gd")
	preview_state.populate(main, app)
	main._load_server_map()
	main._sync_world()
	var deadline := Time.get_ticks_msec() + 45000
	while main.world_loader.world_root == null and Time.get_ticks_msec() < deadline: await process_frame
	while main.arrival_curtain.is_showing() and Time.get_ticks_msec() < deadline: await process_frame
	for frame: int in 60: await process_frame
	main._end_arrival()
	if main.world_loader.world_root == null or main._current_map_display_name != "Landfall":
		push_error("Landfall preview did not finish loading")
		quit(1)
		return
	print("LAND FALL PREVIEW: Landfall published arrival loaded")
	app.actors[100] = {"actor_id":100,"x":preview_state.SPAWN.x + 2,"y":preview_state.SPAWN.y,"rotation":0,"actor_type":1,"kind":1,"name":"Rowan","health":90,"max_health":150,"ether":40,"max_ether":60,"alive":true,"sitting":false,"map":preview_state.MAP_ID}
	app.selected_actor_id = 100
	if OS.get_cmdline_user_args().has("--hud-public-guide"):
		var guide := preload("res://tests/integration/hud_guide_capture.gd").new()
		root.add_child(guide)
		await guide.capture(main)
		guide.queue_free()
		await _shutdown()
		return
	if OS.get_cmdline_user_args().has("--minimal-reference-review"):
		var saved_reference := ConfigFile.new()
		if saved_reference.load("res://test-artifacts/hud-presets/user-minimal-reference-1752.cfg") == OK:
			main.hud_workspace.model.working = main.hud_workspace.Presets.normalise(saved_reference.get_value("hud_presets", "working"))
			main.hud_workspace.model.active = "minimal"
			main.hud_workspace.apply_layout()
			await _capture("minimal-saved-reference.png")
		main.hud_workspace.choose_preset("minimal", true)
		await _capture("minimal-updated-default.png")
		app.techniques = {"received_msec":Time.get_ticks_msec(), "techniques":[{
			"key":"heavy_blow", "name":"Heavy Blow", "known":true, "ready_in":10.0, "ap":5, "blocker":"Weapon unavailable"}]}
		main.spell_loadout.assign_technique(6, "heavy_blow")
		main.casting_bar.refresh()
		await _capture("minimal-unavailable-icons-opaque.png")
		main.hud_workspace.change_part("spells", "unavailable_icon_opacity", 0.35)
		await _capture("minimal-optional-icon-fading.png")
		await _shutdown()
		return
	if OS.get_cmdline_user_args().has("--heritage-gap-review"):
		main.hud_workspace.choose_preset("heritage", true)
		await _capture("heritage-continuous-rail.png")
		root.size = Vector2i(1280, 720)
		await _capture("heritage-continuous-rail-short.png")
		root.size = Vector2i(1920, 1080)
		await _capture("heritage-continuous-rail-tall.png")
		root.size = Vector2i(1440, 900)
		for key: String in ["rail_panel", "logo", "spells", "items", "skills", "research", "clock", "compass"]:
			main.hud_workspace.change_part(key, "background_color", Color("224f6380"))
		await _capture("heritage-continuous-rail-translucent.png")
		main.hud_workspace.choose_preset("heritage", true)
		main.hud_workspace.change_part("skills", "enabled", false)
		await _capture("heritage-continuous-rail-no-statistics.png")
		await _shutdown()
		return
	if OS.get_cmdline_user_args().has("--adventure-reference-review"):
		var saved_reference := ConfigFile.new()
		if saved_reference.load("res://test-artifacts/hud-presets/user-adventure-reference-1729.cfg") == OK:
			main.hud_workspace.model.working = main.hud_workspace.Presets.normalise(saved_reference.get_value("hud_presets", "working"))
			main.hud_workspace.model.active = "adventure"
			main.hud_workspace.apply_layout()
			await _capture("adventure-saved-reference.png")
		main.hud_workspace.choose_preset("adventure", true)
		await _capture("adventure-updated-default.png")
		main.hud_workspace.change_part("resources", "background_color", Color("224f6380"))
		for key: String in ["spells", "items"]: main.hud_workspace.change_part(key, "background_color", Color("224f6380"))
		await _capture("adventure-translucent-joins.png")
		main.hud_workspace.change_part("resources", "show_background", false)
		await _capture("adventure-open-shoulders.png")
		await _shutdown()
		return
	if OS.get_cmdline_user_args().has("--heritage-reference-review"):
		var saved_reference := ConfigFile.new()
		if saved_reference.load("res://test-artifacts/hud-presets/user-heritage-reference-1657.cfg") == OK:
			main.hud_workspace.model.working = main.hud_workspace.Presets.normalise(saved_reference.get_value("hud_presets", "working"))
			main.hud_workspace.model.active = "heritage"
			main.hud_workspace.apply_layout()
			await _capture("heritage-saved-reference.png")
		main.hud_workspace.choose_preset("heritage", true)
		await _capture("heritage-updated-default.png")
		main.hud_workspace.change_part("skills", "enabled", true)
		await _capture("heritage-updated-statistics.png")
		main.hud_workspace.change_part("skills", "enabled", false)
		await _capture("heritage-statistics-hidden.png")
		await _shutdown()
		return
	for id: String in ["current", "heritage", "classic", "modular", "minimal", "adventure"]:
		main.hud_workspace.choose_preset(id, true)
		await _capture(id + ".png")
	main.hud_workspace.choose_preset("classic", true)
	main.hud_workspace.change_part("minimap", "map_label_frame", true)
	await _capture("minimap-title-north-arrow.png")
	main.hud_workspace.change_part("minimap", "map_directions", "all")
	main.hud_workspace.change_part("minimap", "north_marker", "letter")
	main.hud_workspace.change_part("minimap", "direction_offset", 24)
	await _capture("minimap-title-four-directions.png")
	main.hud_workspace.choose_preset("classic", true)
	main.hud_workspace.change_part("party", "enabled", true)
	await _capture("classic-party.png")
	main.hud_workspace.change_part("minimap", "enabled", true)
	main.hud_workspace.change_part("minimap", "offset", Vector2(-12, 64))
	main.hud_workspace.change_part("minimap", "map_shape", "round")
	main.hud_workspace.change_part("minimap", "dimensions", Vector2(280, 240))
	await _capture("classic-round-map.png")
	main.hud_workspace.change_part("minimap", "frame_shape", "rectangle")
	await _capture("classic-round-map-square-frame.png")
	main.hud_workspace.change_part("minimap", "frame_shape", "circle")
	await _capture("classic-circle-frame.png")
	main.hud_workspace.open_editor()
	main.hud_workspace.panel.position = Vector2(530, 110)
	main.hud_workspace._detail_tabs.current_tab = 1
	main.hud_workspace._detail_group = "Look"
	main.hud_workspace.select_component("minimap")
	await _capture("editor-map-frame.png")
	main.hud_workspace.select_component("compass")
	await _capture("editor-compass-frame.png")
	main.hud_workspace.cancel_edit()
	main.hud_workspace.change_part("compass", "compass_corners", "transparent")
	await _capture("classic-compass-transparent.png")
	main.hud_workspace.change_part("compass", "compass_corners", "filled")
	for key: String in ["resources", "utilities", "spells", "items", "clock"]: main.hud_workspace.change_part(key, "hud_border_style", "ornate")
	await _capture("classic-ornate-joined-panels.png")
	main.hud_workspace.choose_preset("classic", true)
	main.hud_workspace.change_part("spells", "dimensions", Vector2(144, 80))
	main.hud_workspace.open_editor()
	main.hud_workspace.panel.position = Vector2(530, 110)
	main.hud_workspace._detail_tabs.current_tab = 0
	main.hud_workspace._detail_group = "Layout"
	main.hud_workspace.select_component("spells")
	for frame: int in 5: await process_frame
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = main.hud_workspace._resize_handles("spells").top.get_center()
	main.hud_workspace.handle_input(click)
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.position = Vector2(click.position.x, main.hud_workspace._selection_rect("resources").position.y + 5)
	main.hud_workspace.handle_input(motion)
	await _capture("editor-resize-alignment.png")
	click.pressed = false
	click.position = motion.position
	main.hud_workspace.handle_input(click)
	main.hud_workspace.cancel_edit()
	main.hud_workspace.choose_preset("classic", true)
	main.hud_workspace.open_editor()
	main.hud_workspace.panel.position = Vector2(530, 110)
	main.hud_workspace._detail_tabs.current_tab = 2
	main.hud_workspace._detail_group = "Options"
	main.hud_workspace.select_component("resources")
	await _capture("classic-editor-resources.png")
	main.hud_workspace.change_resource_color("mana", Color("e55f9c"))
	main.hud_workspace.move_resource("mana", -1)
	main.hud_workspace.change_part("clock", "clock_mode", "digital")
	await _capture("classic-custom-palette.png")
	main.hud_workspace.change_part("resources", "show_background", false)
	main.hud_workspace.change_part("resources", "show_border", false)
	main.hud_workspace.change_part("clock", "clock_mode", "dial")
	main.hud_workspace.change_part("clock", "show_background", false)
	main.hud_workspace.change_part("clock", "show_border", false)
	main.hud_workspace._detail_tabs.current_tab = 1
	main.hud_workspace._detail_group = "Look"
	main.hud_workspace.select_component("clock")
	await _capture("classic-editor-frames-off.png")
	main.hud_workspace.cancel_edit()
	var sample_members: Array = []
	for index: int in 12: sample_members.append(preview_state.member(index))
	preview_state.set_party(app, sample_members)
	for id: String in ["classic", "modular", "adventure", "minimal"]:
		main.hud_workspace.choose_preset(id, true)
		await _capture(id + "-party-12.png")
	preview_state.set_party(app, [preview_state.member(0), preview_state.member(1), preview_state.member(2)])
	main.hud_workspace.choose_preset("adventure", true)
	main.hud_workspace.change_part("spells", "slots", 12)
	main.hud_workspace.change_part("spells", "rows", 2)
	main.hud_workspace.change_part("items", "rows", 2)
	main.hud_workspace.change_part("items", "slots", 8)
	await _capture("adventure-two-rows.png")
	for index: int in 8: main.hud_workspace.change_arc(index, "enabled", true)
	for border: String in ["laurel", "runic", "crystal"]:
		main.hud_workspace.change_part("medallion", "border_design", border)
		await _capture("arcs-" + border + ".png")
	for side: String in ["left", "right", "top", "bottom"]:
		main.hud_workspace.choose_preset("adventure", true)
		for key: String in ["spells", "items"]: main.hud_workspace.dock_component(key, "none", "right")
		main.hud_workspace.change_part("resources", "dimensions", Vector2(360, 44))
		main.hud_workspace.change_part("resources", "show_background", true)
		main.hud_workspace.change_part("resources", "show_border", true)
		main.hud_workspace.change_part("resources", "background_color", Color("241e15ed"))
		main.hud_workspace.change_part("resources", "border_color", Color("aa8d50"))
		main.hud_workspace.change_part("resources", "edge_dock", "none")
		main.hud_workspace.change_part("resources", "anchor", "free")
		main.hud_workspace.change_part("resources", "position", Vector2(0.5, 0.45))
		main.hud_workspace.change_part("resources", "offset", Vector2.ZERO)
		main.hud_workspace.dock_component("medallion", "resources", side)
		await _capture("circle-to-meter-" + side + ".png")
	main.hud_workspace.choose_preset("adventure", true)
	main.hud_workspace.open_editor()
	main.hud_workspace.panel.position = Vector2(28, 180)
	main.hud_workspace.select_component("items")
	await _capture("editor.png")
	main.hud_workspace.select_component("utilities")
	await _capture("editor-icons.png")
	main.hud_workspace.select_component("medallion")
	main.hud_workspace._detail_tabs.current_tab = 2
	await _capture("editor-circle.png")
	main.hud_workspace.select_component("medallion", 0)
	await _capture("editor-curve.png")
	main.hud_workspace.cancel_edit()
	main.character_intro.cancel()
	main.hud_workspace.choose_preset("heritage", true)
	main.hud_workspace.open_editor()
	main.hud_workspace.panel.position = Vector2(530, 110)
	main.hud_workspace.select_component("rail_panel")
	await _capture("heritage-editor-blank-rail.png")
	main.hud_workspace.cancel_edit()
	# Reproduce the user's saved option-4 meter and docking settings without
	# depending on anyone's private preferences file.
	main.hud_workspace.choose_preset("adventure", true)
	var resource_config: Dictionary = main.hud_workspace.model.working.parts.resources
	resource_config.anchor = "free"
	resource_config.position = Vector2(0.224479, 0.956945)
	resource_config.frame_style = "panel"
	for field: String in ["show_labels", "show_values", "show_icons", "show_background", "show_border"]: resource_config[field] = true
	main.hud_workspace.apply_layout()
	await _capture("adventure-user-docking.png")
	for key: String in main.hud_workspace.Presets.RESOURCE_COLORS: main.hud_workspace.model.working.meters[key] = true
	main.hud_workspace.apply_layout()
	await _capture("adventure-all-six-resources.png")
	main.hud_workspace.change_part("resources", "dimensions", Vector2(280, 22))
	main.hud_workspace.change_frame_color("resources", "background_color", Color("172638ed"))
	main.hud_workspace.change_frame_color("resources", "border_color", Color("65d4eaff"))
	await _capture("adventure-narrow-six-colored-frame.png")
	await _shutdown()

func _shutdown() -> void:
	main.character_intro.cancel()
	main.exterior_stream.clear()
	while not main.exterior_stream.is_idle(): await process_frame
	await ContinentChunkStream.drain_workers(self)
	main.queue_free()
	for frame: int in 5: await process_frame
	Input.set_custom_mouse_cursor(null, Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_IBEAM)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	preload("res://src/ui/technique_icons.gd")._cache.clear()
	(load("res://src/ui/hud_medallion.gd") as GDScript)._textures.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._cache.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._tinted.clear()
	var actor_script: GDScript = load("res://src/actors/replicated_actor_3d.gd")
	actor_script._wardrobe_texture_cache.clear()
	actor_script._equipment_pieces_cache.clear()
	(load("res://src/world/look/look_ground.gd") as GDScript)._class_textures.clear()
	for frame: int in 2: await process_frame
	quit()

func _chat(channel: int, text: String) -> void:
	var payload := PackedByteArray([channel])
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _capture(filename: String) -> void:
	for frame: int in 15: await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(FOLDER.path_join(filename))
	for key: String in ["utilities", "resources", "spells", "items", "chat", "system_chat", "logo", "skills", "research", "clock", "compass", "status"]:
		print(filename, " ", key, " ", main.hud_workspace._root(key).get_global_rect())
	print("capture: ", filename)
