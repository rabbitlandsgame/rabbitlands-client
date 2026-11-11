extends SceneTree
## The descent status readout as a HUD editor part ("descent_status"): clear of
## every preset's parts by default (playtest 2026-11-11: it sat under the HUD),
## previewed and movable in the editor, shown only while a descent is open, and
## restored from saved settings.
const Presets := preload("res://src/ui/hud_presets.gd")
const PATH := "res://test-artifacts/descent-hud/settings.cfg"
var failures := 0
var main: Control

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func frames(count := 4) -> void:
	for index: int in count: await process_frame

func create_main() -> void:
	main = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = PATH
	root.add_child(main)
	await frames()
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	await frames()

func gesture(workspace: Control, origin: Vector2, destination: Vector2) -> void:
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = origin
	workspace.handle_input(click)
	var motion := InputEventMouseMotion.new()
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	motion.shift_pressed = true
	motion.position = destination
	workspace.handle_input(motion)
	click.pressed = false
	click.position = destination
	workspace.handle_input(click)
	await frames()

func open_descent(app: Node) -> void:
	app.set("authenticated", true)
	app.descent = {"open": true, "name": "The Serpent Deep", "difficulty": "Hard", "floor": 1, "floors": 6,
		"floor_name": "The Ossuary Stair", "time_left": 3000,
		"boss": "defeated"}
	app.descent_anchor_msec = Time.get_ticks_msec()
	app.state_changed.emit(&"descent")
	await frames()

func run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(PATH.get_base_dir()))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	var older := Presets.preset("heritage")
	older.parts.erase("descent_status")
	var migrated := Presets.normalise(older)
	expect(migrated.parts.descent_status.enabled and migrated.parts.descent_status.anchor == "top_center",
		"an existing HUD profile gains the descent readout at its default spot")
	await create_main()
	var app: Node = root.get_node("AppState")
	var workspace: Control = main.hud_workspace
	var hud: Control = main.extension_windows.descent_status_hud
	var panel: Control = hud.panel
	expect(workspace.parts.get("descent_status") == panel, "the readout is a HUD workspace part")
	expect(not panel.visible, "no descent, no readout")
	await open_descent(app)
	workspace.apply_layout()
	await frames()
	expect(panel.visible and hud.floor_line.text.begins_with("Floor 1 of 6"), "an open descent shows the readout")
	# Clear of every preset's visible parts at 1280 x 720, the long boss line included.
	for preset_id: String in Presets.BUILT_INS:
		workspace.choose_preset(preset_id, true)
		await frames(6)
		var mine: Rect2 = workspace._visual_rect("descent_status")
		expect(mine.size.x <= hud.MANAGED_WIDTH + 1 and main.game_view.get_global_rect().encloses(mine),
			"%s: the readout keeps its width and stays on screen (%s)" % [preset_id, mine])
		var covered: Array[String] = []
		for key: String in Presets.PARTS:
			if key in ["descent_status", "rare_drops"] or not workspace._root(key).is_visible_in_tree():
				continue
			if workspace._visual_rect(key).intersects(mine):
				covered.append(key)
		expect(covered.is_empty(), "%s: no HUD part covers the readout %s (%s)" % [preset_id, mine, ", ".join(covered)])
	workspace.choose_preset("heritage", true)
	await frames()
	workspace.open_editor()
	workspace.panel.position = Vector2(12, 300)
	await frames()
	var point: Vector2 = panel.get_global_rect().get_center()
	expect(workspace._pick(point).get("key") == "descent_status", "the readout can be selected in the editor")
	var before: Vector2 = panel.position
	await gesture(workspace, point, point + Vector2(-60, 40))
	expect(panel.position.distance_to(before + Vector2(-60, 40)) < 1, "the readout drags: %s -> %s" % [before, panel.position])
	workspace.undo_edit()
	expect(panel.position.distance_to(before) < 1, "the readout supports Undo")
	workspace.redo_edit()
	var moved: Vector2 = panel.position
	workspace.commit_and_close()
	await frames()
	hud._refresh()
	await frames()
	expect(panel.visible and panel.position.distance_to(moved) < 1, "the clock ticking keeps the edited position")
	app.descent = {"open": false}
	app.state_changed.emit(&"descent")
	await frames()
	expect(not panel.visible, "leaving the descent hides the readout")
	workspace.open_editor()
	await frames()
	expect(panel.visible and hud.heading.text.contains("Serpent Deep"), "the editor previews the readout with sample text")
	workspace.change_part("descent_status", "enabled", false)
	await frames()
	expect(not panel.visible, "a hidden part stays hidden in the editor")
	workspace.cancel_edit()
	await frames()
	main.queue_free()
	await frames()
	await create_main()
	app = root.get_node("AppState")
	await open_descent(app)
	main.hud_workspace.apply_layout()
	await frames()
	hud = main.extension_windows.descent_status_hud
	expect(hud.panel.position.distance_to(moved) < 1, "a fresh client restores the saved position")
	app.descent = {"open": false}
	app.state_changed.emit(&"descent")
	main.queue_free()
	await frames()
	print("Descent HUD layout: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)
