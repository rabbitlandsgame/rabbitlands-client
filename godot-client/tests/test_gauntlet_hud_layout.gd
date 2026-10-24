extends SceneTree
## Exercise the real HUD controls through editing, server updates and a restart.
const Presets := preload("res://src/ui/hud_presets.gd")
const PATH := "res://test-artifacts/gauntlet-hud/settings.cfg"
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

func run() -> void:
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(PATH.get_base_dir()))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	await create_main()
	var workspace: Control = main.hud_workspace
	var loot: Control = main.extension_windows.gauntlet_loot_window
	expect(not loot.reopen.visible and not loot.announcement.visible, "inactive loot HUD stays hidden during play")
	var older := Presets.preset("heritage")
	older.parts.erase("gauntlet_loot")
	older.parts.erase("rare_drops")
	var migrated := Presets.normalise(older)
	expect(migrated.parts.gauntlet_loot.enabled and migrated.parts.rare_drops.enabled,
		"existing HUD profiles gain both components without losing their layout")
	workspace.open_editor()
	workspace.panel.position = Vector2(12, 300)
	await frames()
	expect(loot.reopen.visible and loot.announcement.visible and loot._state.is_empty(),
		"editing previews both live controls without creating loot state")
	var sent: Array[String] = []
	loot.configure_sender(func(text: String) -> Error: sent.append(text); return OK)
	loot.reopen.pressed.emit()
	expect(sent.is_empty(), "the editor shortcut preview never sends a loot request")
	for key: String in ["gauntlet_loot", "rare_drops"]:
		workspace.change_part(key, "dimensions", Vector2(190, 42) if key == "gauntlet_loot" else Vector2(600, 42))
		workspace.change_part(key, "anchor", "free")
		workspace.change_part(key, "position", Vector2(0.45, 0.38) if key == "gauntlet_loot" else Vector2(0.4, 0.18))
		await frames()
		workspace.select_component(key)
		var control: Control = workspace.parts[key]
		var before: Vector2 = control.position
		var point: Vector2 = control.get_global_rect().get_center()
		expect(workspace._pick(point).get("key") == key, key + " can be selected on the HUD")
		await gesture(workspace, point, point + Vector2(36, 28))
		expect(control.position.distance_to(before + Vector2(36, 28)) < 1,
			key + " drags independently: %s -> %s" % [before, control.position])
		workspace.undo_edit()
		expect(control.position.distance_to(before) < 1, key + " supports Undo")
		workspace.redo_edit()
		expect(control.position.distance_to(before + Vector2(36, 28)) < 1, key + " supports Redo")
	var positions := {"gauntlet_loot": loot.reopen.position, "rare_drops": loot.announcement.position}
	workspace.commit_and_close()
	await frames()
	expect(not loot.reopen.visible and not loot.announcement.visible, "saving removes inactive previews")
	var snapshot := {"run_id": "hud-test", "revision": 1, "phase": "active", "total": 1,
		"open": false, "announcement": "Moonstone", "announcement_id": 1}
	loot.apply_snapshot(snapshot)
	await frames()
	expect(loot.reopen.visible and loot.announcement.visible and loot.announcement_text.text.contains("Moonstone"),
		"real loot and rare finds appear in the live HUD")
	loot._layout()
	await frames()
	expect(loot.reopen.position == positions.gauntlet_loot and loot.announcement.position == positions.rare_drops,
		"loot snapshots and ledger relayout preserve both edited positions")
	workspace.open_editor()
	workspace.change_part("rare_drops", "position", Vector2(0.1, 0.5))
	workspace.cancel_edit()
	await frames()
	expect(loot.announcement.position == positions.rare_drops and loot.announcement_text.text.contains("Moonstone"),
		"Cancel restores the position while retaining a real announcement")
	workspace.open_editor()
	workspace.change_part("gauntlet_loot", "enabled", false)
	workspace.change_part("rare_drops", "enabled", false)
	snapshot.revision = 2
	snapshot.announcement_id = 2
	loot.apply_snapshot(snapshot)
	await frames()
	expect(not loot.reopen.visible and not loot.announcement.visible, "incoming updates respect disabled HUD components")
	workspace.cancel_edit()
	loot.close()
	workspace.apply_layout()
	await frames()
	expect(loot.reopen.visible and not loot.announcement.visible, "applying a layout does not resurrect a dismissed announcement")
	snapshot.phase = "sent"
	snapshot.exited = true
	snapshot.exchange_total = 1
	loot.apply_snapshot(snapshot)
	await frames()
	expect(loot.reopen.visible, "the shortcut still reopens party exchange listings after a run exits")
	main.queue_free()
	await frames()
	root.get_node("AppState").gauntlet_loot.clear()
	await create_main()
	workspace = main.hud_workspace
	loot = main.extension_windows.gauntlet_loot_window
	expect(loot.reopen.position.distance_to(positions.gauntlet_loot) < 1 and loot.announcement.position.distance_to(positions.rare_drops) < 1,
		"a fresh client restores both positions from saved settings")
	workspace.open_editor()
	await frames()
	if OS.get_cmdline_user_args().has("--capture"):
		workspace.panel.position = Vector2(12, 300)
		await frames()
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(PATH.get_base_dir().path_join("editor.png"))
	workspace.cancel_edit()
	root.size = Vector2i(1024, 600)
	await frames()
	for key: String in positions:
		var rect: Rect2 = workspace._visual_rect(key)
		expect(main.game_view.get_global_rect().grow(1).encloses(rect), key + " stays reachable after a viewport resize")
	main.queue_free()
	await frames()
	print("Gauntlet HUD layout: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)
