extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1600, 900)
	root.content_scale_size = Vector2i(1600, 900)
	var background := ColorRect.new()
	background.color = Color("23332d")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 42
	state.actor_mounts[42] = {"mode": "on_foot", "selected_mount_id": "cheetah", "mount_id": "",
		"owned_mount_ids": preload("res://src/mounts/mount_profiles.gd").PATHS.keys(), "mount_coats":{}, "blocked_reason": "", "gait": "on_foot"}
	var window: Variant = (load("res://src/ui/mounts_window.gd") as Script).new()
	root.add_child(window)
	window.open()
	window._choose_coat(3)
	for frame: int in 8:
		await process_frame
	print("MOUNTS_WINDOW_LAYOUT ", window.panel.size, " minimum=", window.panel.get_combined_minimum_size(),
		" card=", window.cards["moor_pony"].size, " portrait=", window.portraits["moor_pony"].size)
	await RenderingServer.frame_post_draw
	var folder := ProjectSettings.globalize_path("res://test-artifacts/mount-selection")
	if not OS.get_environment("ELORIA_ARTIFACT_DIR").is_empty(): folder = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(folder)
	root.get_texture().get_image().save_png(folder.path_join("mounts-window.png"))
	print("MOUNTS_WINDOW_CAPTURE ", folder)
	window.free()
	state.authenticated = false
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit()
