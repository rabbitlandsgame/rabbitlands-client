extends SceneTree
## Offline rendered UI evidence; run with an isolated APPDATA/LOCALAPPDATA.

const MusicPlayer := preload("res://src/audio/music_program_player.gd")
const Jukebox := preload("res://src/audio/jukebox.gd")
const JukeboxWindow := preload("res://src/ui/jukebox_window.gd")

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.content_scale_size = Vector2i.ZERO
	root.size = Vector2i(1280, 800)
	root.position = Vector2i(20000, 20000)
	var background := ColorRect.new()
	background.color = Color("18251f")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/audio/catalog.json"))
	var player := MusicPlayer.new()
	root.add_child(player)
	player.configure(catalog.music)
	var box := Jukebox.new()
	box.storage_path = "user://jukebox-render.cfg"
	DirAccess.remove_absolute(ProjectSettings.globalize_path(box.storage_path))
	root.add_child(box)
	box.configure(catalog.music, player)
	box.create_playlist("Evening travels")
	box.edit_playlist("Evening travels", ["rising_moon", "home_town", "a_warm_fireplace", "the_bard_s_tale"])
	box.set_rules([
		{"enabled": true, "context": "invasion_boss", "mode": "game", "target": ""},
		{"enabled": true, "context": "night", "mode": "playlist", "target": "Evening travels"},
		{"enabled": false, "context": "inn", "mode": "song", "target": "the_bard_s_tale"}])
	box.request_game("@town_night")
	var window := JukeboxWindow.new()
	window.jukebox = box
	root.add_child(window)
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/jukebox")
	DirAccess.make_dir_recursive_absolute(output)
	for size: Vector2i in [Vector2i(1280, 800), Vector2i(800, 600)]:
		root.size = size
		window.open()
		window.search.release_focus()
		for tab: int in 3:
			window.tabs.current_tab = tab
			if tab == 2:
				window.call("_edit_rule", 1)
			for frame: int in 8:
				await process_frame
			await RenderingServer.frame_post_draw
			var path := output.path_join("jukebox-%dx%d-%d.png" % [size.x, size.y, tab])
			root.get_texture().get_image().save_png(path)
			print("JUKEBOX_RENDER ", path)
	window.hide()
	window.queue_free()
	box.queue_free()
	player.queue_free()
	await process_frame
	await create_timer(0.2).timeout
	quit()
