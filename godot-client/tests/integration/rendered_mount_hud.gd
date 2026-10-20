extends SceneTree
## Native rendered review of the real selection window, HUD shortcut and
## banner popover. Synthetic state replaces the server for a repeatable view.
var main: Variant
var folder := ""
var failures := 0

func _init() -> void: call_deferred("run")

func settle(frames := 8) -> void:
	for frame: int in frames: await process_frame

func capture(filename: String) -> void:
	await settle()
	await RenderingServer.frame_post_draw
	var result := root.get_texture().get_image().save_png(folder.path_join(filename))
	if result != OK: failures += 1

func click(control: Control) -> void:
	var at := control.get_global_rect().get_center()
	var mouse := InputEventMouseButton.new()
	mouse.position = at
	mouse.global_position = at
	mouse.button_index = MOUSE_BUTTON_LEFT
	mouse.pressed = true
	Input.parse_input_event(mouse)
	await process_frame
	mouse = mouse.duplicate()
	mouse.pressed = false
	Input.parse_input_event(mouse)
	await settle(3)

func type_text(value: String) -> void:
	for letter: String in value:
		var key := InputEventKey.new()
		key.physical_keycode = letter.to_upper().unicode_at(0)
		key.keycode = key.physical_keycode
		key.unicode = letter.unicode_at(0)
		key.pressed = true
		Input.parse_input_event(key)
		await process_frame
		key = key.duplicate()
		key.pressed = false
		Input.parse_input_event(key)
		await process_frame

func run() -> void:
	root.size = Vector2i(1280,720)
	root.content_scale_size = Vector2i(1280,720)
	folder = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if folder.is_empty(): folder = ProjectSettings.globalize_path("res://test-artifacts/mount-hud")
	DirAccess.make_dir_recursive_absolute(folder)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await settle(2)
	main.set_process(false)
	main.login_panel.hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 42
	state.actor_mounts = {42: {"mode": "on_foot", "mount_id": "", "gait": "on_foot",
		"selected_mount_id": "moor_pony", "owned_mount_ids": ["moor_pony", "golden_plains_horse",
		"crystalback_tortoise", "rabbit", "jadefeather_raptor"], "blocked_reason": ""}}
	main.get_node("%OverheadPlayerName").text = "Traveller"
	main.actor_resource_overlay.position = Vector2(570,120)
	main.actor_resource_overlay.show()
	state.state_changed.emit(&"mount_states")
	await settle()
	await click(main.get_node("%MountsButton"))
	if not main.mounts_window.is_open():
		push_error("Actual HUD click did not open mount selection")
		failures += 1
	await capture("mount-library.png")
	await click(main.mounts_window.search)
	await type_text("raptor")
	if main.mounts_window.search.text != "raptor" or not main.mounts_window.cards.jadefeather_raptor.visible \
			or main.mounts_window.cards.moor_pony.visible:
		push_error("Typing in mount search must filter without triggering mount hotkeys")
		failures += 1
	main.mounts_window.search.clear()
	main.mounts_window.search.text_changed.emit("")
	await settle()
	await click(main.mounts_window.cards.golden_plains_horse)
	if main.mounts_window.candidate != "golden_plains_horse" or state.actor_mounts[42].selected_mount_id != "moor_pony":
		push_error("Clicking a card browses locally and waits for server confirmation")
		failures += 1
	main.mounts_window.close()
	main._sync_banner_context_menu()
	main._actor_hud_menu.open_at(Vector2(610,180), "Character")
	await capture("character-banner.png")
	var previous: bool = main._banner_option("health_numbers")
	await click(main._actor_hud_menu.character_boxes.health_numbers)
	if not main._actor_hud_menu.visible or main._banner_option("health_numbers") == previous:
		push_error("Actual checkbox click must update the banner and keep the panel open")
		failures += 1
	main._actor_hud_menu.tabs.current_tab = 1
	await capture("mount-banner.png")
	main._actor_hud_menu.close()
	root.size = Vector2i(800,720)
	root.content_scale_size = Vector2i(800,720)
	await settle()
	main.mounts_window.open()
	await capture("mount-library-small.png")
	main.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("MOUNT_HUD_RENDERED_REVIEW failures=",failures," folder=",folder)
	quit(1 if failures else 0)
