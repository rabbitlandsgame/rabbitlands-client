extends SceneTree
const Presets := preload("res://src/ui/inventory_presets.gd")
var failures := 0
var dispatches := {"store": 0, "get": 0, "drop": 0, "mix": 0, "lists": 0}

func _init() -> void: run.call_deferred()
func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	var app := root.get_node("AppState")
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://action-bar-test.cfg"
	root.add_child(main)
	for frame: int in 8: await process_frame
	var workspace: Control = main.inventory_workspace
	var bar: GridContainer = workspace.bulk_actions
	main.inventory_panel.show()
	app.set("inventory", {0: {"image_id": 1, "quantity": 3}})
	app.set("local_actor_id", 1)
	app.set("actors", {1: {"x": 10, "y": 11}})
	app.set("ground_bags", {})
	app.set("storage", {"open": false})
	for action: String in dispatches:
		bar.sources[action].pressed.connect(func() -> void: dispatches[action] += 1)
	bar.refresh_enabled()
	expect(bar.buttons.store.disabled and bar.buttons.get.disabled and not bar.buttons.drop.disabled,
		"storage and ground-bag actions need their real context; drop sees backpack stacks")
	bar._pressed("store")
	bar._pressed("get")
	expect(dispatches.store == 0 and dispatches.get == 0, "disabled shortcuts never dispatch")
	app.set("storage", {"open": true, "read_only": true})
	bar.refresh_enabled()
	bar._pressed("store")
	expect(bar.buttons.store.disabled and dispatches.store == 0, "read-only storage preview cannot enable or dispatch Store all")
	app.set("storage", {"open": true})
	app.set("ground_bags", {9: {"x": 10, "y": 11}})
	bar.refresh_enabled()
	bar._pressed("store")
	bar._pressed("get")
	bar._pressed("mix")
	bar._pressed("lists")
	expect(dispatches.store == 1 and dispatches.get == 1 and dispatches.mix == 1 and dispatches.lists == 1,
		"visible shortcuts reuse each original handler exactly once")
	bar._pressed("drop")
	expect(dispatches.drop == 0 and bar.confirmation.visible, "drop all asks for confirmation")
	bar.confirmation.hide()
	expect(dispatches.drop == 0, "cancel leaves every item untouched")
	bar._pressed("drop")
	bar.confirmation.confirmed.emit()
	bar.confirmation.hide()
	expect(dispatches.drop == 1, "confirmed drop uses the existing protection-aware handler once")
	bar._pressed("drop")
	workspace.open_editor()
	bar.confirmation.confirmed.emit()
	bar.confirmation.hide()
	expect(dispatches.drop == 1, "a confirmation cannot dispatch after editor mode begins")
	workspace.finish_edit(false)
	for preset: String in Presets.BUILT_INS:
		workspace.choose_preset(preset, true)
		for frame: int in 2: await process_frame
		expect(workspace.groups.actions.visible and bar.get_child_count() == 6,
			preset + " keeps the configurable action bar with all five shortcuts")
		var config: Dictionary = workspace.model.working
		config.parts.actions.enabled = false
		workspace.apply_layout()
		expect(not workspace.groups.actions.visible, preset + " can hide the action section")
		config.parts.actions.enabled = true
		config.parts.actions.show_drop = false
		config.parts.actions.columns = 2
		workspace.apply_layout()
		expect(not bar.buttons.drop.visible and bar.columns == 2, "per-action choice and columns apply")
		var normalised: Dictionary = Presets.normalise(config)
		expect(not normalised.parts.actions.show_drop and normalised.parts.actions.columns == 2,
			"action choices survive normalization")
	var model := Presets.new()
	model.working.parts.actions.show_drop = false
	model.working.parts.actions.columns = 2
	model.save_file("user://action-bar-model.cfg")
	var loaded := Presets.new()
	loaded.load_file("user://action-bar-model.cfg")
	expect(not loaded.working.parts.actions.show_drop and loaded.working.parts.actions.columns == 2,
		"action settings persist to the user's existing inventory preferences")
	main.queue_free()
	await process_frame
	print("inventory action bar failures=", failures)
	quit(failures)
