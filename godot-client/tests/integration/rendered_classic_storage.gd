extends SceneTree
## Real client screenshots for the classic, docked and favorite-set layouts.
const SETTINGS := "user://eloria_hud.cfg"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var had_settings: bool = FileAccess.file_exists(SETTINGS)
	var original: PackedByteArray = FileAccess.get_file_as_bytes(SETTINGS) if had_settings else PackedByteArray()
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	(main.get_node("LoginBackground") as Control).hide()
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).show()
	var state: Node = root.get_node("AppState")
	state.set("stats", {"carried": 183, "capacity": 840})
	state.set("inventory", {0: {"image_id": 16, "quantity": 14, "slot": 0},
		7: {"image_id": 0, "quantity": 33755, "slot": 7},
		30: {"image_id": 474, "quantity": 45, "slot": 30},
		31: {"image_id": 101, "quantity": 37, "slot": 31}})
	state.set("inventory_names", {0: "Sunleaf", 7: "Gold Coins", 30: "Potion of Minor Healing", 31: "Rosemary"})
	state.set("storage", {"open": true, "category_id": 3,
		"categories": [{"id": 1, "name": "Food"}, {"id": 2, "name": "Coins"},
			{"id": 3, "name": "Flowers"}, {"id": 4, "name": "Ores"},
			{"id": 5, "name": "Metals"}, {"id": 6, "name": "Minerals"},
			{"id": 7, "name": "Tools"}, {"id": 8, "name": "Weapons"}, {"id": 9, "name": "Armor"}],
		"items": {0: {"image_id": 16, "quantity": 347}, 1: {"image_id": 101, "quantity": 29},
			2: {"image_id": 21, "quantity": 84}, 3: {"image_id": 20, "quantity": 63}},
		"described": {0: {"name": "Sunleaf", "subtype": "Flower"},
			1: {"name": "Rosemary", "subtype": "Flower"},
			2: {"name": "Lavender", "subtype": "Flower"}, 3: {"name": "Mushroom", "subtype": "Fungus"}}})
	main.set("_item_lists", {"Foraging": [{"name": "Sunleaf", "image_id": 16, "quantity": 30, "category_id": 3},
		{"name": "Rosemary", "image_id": 101, "quantity": 50, "category_id": 3},
		{"name": "Potion of Minor Healing", "image_id": 474, "quantity": 10, "category_id": 6}],
		"Mining": [{"name": "Pickaxe", "image_id": 5, "quantity": 1, "category_id": 7}],
		"Potion making": [], "Combat supplies": []})
	var workspace: Node = main.get("classic_storage") as Node
	workspace.call("set_docked", false)
	(main.get("inventory_panel") as Control).scale = Vector2.ONE
	main.call("_sync_inventory")
	main.call("_sync_storage")
	workspace.call("activate_list", "Foraging")
	workspace.call("show_lists")
	await _capture("faithful-classic.png")
	workspace.call("set_docked", true)
	await _capture("docked-bank.png")
	workspace.call("activate_list", "Mining")
	await _capture("favorites-hot-swap.png")
	main.queue_free()
	await process_frame
	if had_settings:
		var file := FileAccess.open(SETTINGS, FileAccess.WRITE)
		file.store_buffer(original)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS))
	print("rendered classic storage: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _capture(file_name: String) -> void:
	for frame: int in range(6):
		await process_frame
	RenderingServer.force_draw(false)
	var image: Image = root.get_texture().get_image()
	if image == null or image.is_empty():
		failures += 1
		return
	var directory: String = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if directory.is_empty():
		directory = ProjectSettings.globalize_path("res://test-artifacts/classic-storage")
	DirAccess.make_dir_recursive_absolute(directory)
	if image.save_png(directory.path_join(file_name)) != OK:
		failures += 1
