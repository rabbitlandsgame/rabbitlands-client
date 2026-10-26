extends SceneTree
const Fixture := preload("res://tests/fixtures/mixing_window_fixture.gd")
const Presets := preload("res://src/ui/mixing_presets.gd")
var main: Control
var folder := "res://test-artifacts/mixing-designs/renders"
func _init() -> void: call_deferred("run")
func frames(count := 8) -> void:
	for frame: int in count: await process_frame
func capture(name: String) -> void:
	await frames()
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join(name))
	print("CAPTURE: ", name, " mixing=", main.manufacturing_panel.get_global_rect())
func run() -> void:
	create_timer(110).timeout.connect(func() -> void: quit(99))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	root.get_node("Network").block_for_hud_preview()
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://mixing-render.cfg"
	root.add_child(main)
	await frames(10)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	main.chat_hud.hide()
	main.system_chat_hud.hide()
	Fixture.populate(main)
	for resolution: Vector2i in [Vector2i(1280, 720), Vector2i(1672, 941)]:
		root.size = resolution
		await frames()
		for id: String in Presets.BUILT_INS:
			Fixture.populate(main)
			main.mixing_workspace.choose_preset(id, true)
			if id == "popover":
				main.get_node("/root/AppState").inventory.erase(2)
				main.get_node("/root/AppState").inventory_names.erase(2)
				main._sync_manufacturing()
			await capture("%s-%d.png" % [id, resolution.x])
		main.mixing_workspace.choose_preset("workbench", true)
		main.mixing_workspace.open_editor()
		await capture("editor-%d.png" % resolution.x)
		main.mixing_workspace.finish_edit(false)
	main.queue_free()
	await frames()
	quit()
