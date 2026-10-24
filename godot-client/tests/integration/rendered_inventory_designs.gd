extends SceneTree
## Real inventory controls, offline sample state and isolated presentation settings.
const Presets := preload("res://src/ui/inventory_presets.gd")
var main: Control
var workspace: Control
var folder := ""

func _init() -> void: call_deferred("run")

func frames(count := 8) -> void:
	for index: int in count: await process_frame

func capture(filename: String) -> void:
	await frames()
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.save_png(folder.path_join(filename))
	print("CAPTURE: ", filename, " inventory=", main.inventory_panel.get_global_rect())

func run() -> void:
	create_timer(110).timeout.connect(func() -> void: quit(99))
	folder = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if folder.is_empty(): folder = ProjectSettings.globalize_path("res://test-artifacts/inventory-designs/renders")
	DirAccess.make_dir_recursive_absolute(folder)
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://inventory-render.cfg"
	root.add_child(main)
	await frames(10)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	main.chat_hud.hide()
	main.system_chat_hud.hide()
	workspace = main.inventory_workspace
	var app := root.get_node("AppState")
	app.set("stats", {"health": 120, "max_health": 150, "ether": 45, "max_ether": 60,
		"action_points": 28, "max_action_points": 30, "food": 42, "carried": 205, "capacity": 320})
	var contents := {}
	var names := {}
	var ids := [1, 3, 31, 35, 16, 12, 18, 21, 17, 22, 8, 4, 10, 23]
	var captions := ["Hearth Bread", "Health Potion", "Iron Bar", "Wood", "Herbs", "Thread", "Coal", "Lavender", "Grain", "White Flower", "Mortar", "Ether Potion", "Meat", "Golden Mushroom"]
	for index: int in ids.size():
		contents[index] = {"slot": index, "image_id": ids[index], "quantity": 24 if index == 0 else 1 + index * 3, "inventory_usable": index in [0, 1, 11]}
		names[index] = captions[index]
	for index: int in 8:
		contents[36 + index] = {"slot": 36 + index, "image_id": 40 + index, "quantity": 1, "inventory_usable": false}
	app.set("inventory", contents)
	app.set("inventory_names", names)
	main.selected_inventory_slot = 0
	main.inventory_panel.show()
	main._sync_stats()
	main._sync_inventory()
	for resolution: Vector2i in [Vector2i(1280, 720), Vector2i(1920, 1080)]:
		root.size = resolution
		await frames()
		for id: String in Presets.BUILT_INS:
			workspace.choose_preset(id, true)
			workspace.close_inspection()
			await capture("%s-%s-pack.png" % [id, resolution.x])
			workspace.request_inspection(0, true)
			workspace.present_detail({"open": true, "image_id": 1, "name": "Hearth Bread", "category": "Food", "quantity": 24,
				"description": "Baked before dawn at the Four Gates ovens.", "stats": "Restores 40 food. Weight 2.", "equipped": false}, true)
			await capture("%s-%s-inspect.png" % [id, resolution.x])
		workspace.choose_preset("unified", true)
		workspace.open_editor()
		await capture("editor-%s.png" % resolution.x)
		workspace.finish_edit(false)
	main.queue_free()
	await frames()
	quit()
