extends SceneTree
## Rendered evidence for the Techniques tab of the Spells & Techniques window,
## the technique ring, and a technique on the quick spell bar.
##
## The payload is the server's own builder output for a sword-and-board
## fighter (tests/fixtures/techniques_state.json, written from
## TechniqueRuntime.technique_state_payload): six manuals read, Brace held,
## Shield Bash cooling down, 138 of 240 action points. The window is opened
## through the HUD the way a player opens it, and the frame is checked for real
## colour variation so a dummy or black frame cannot pass as evidence.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/techniques")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	root.size = SCREEN_SIZE
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var body := FileAccess.get_file_as_string("res://tests/fixtures/techniques_state.json")
	app_state.call("_on_packet", 212, body.to_utf8_buffer())
	main.call("_on_techniques_button_pressed")
	for _frame: int in range(8):
		await process_frame
	var window: Control = main.get("spells_window") as Control
	_expect(window != null and bool(window.call("is_open")) and str(window.get("current_tab")) == "techniques",
		"Ctrl+X opens Spells & Techniques on the Techniques tab")
	var loadout = main.get("spell_loadout")
	loadout.call("assign_technique", 2, "shield_bash")
	loadout.call("assign_technique", 3, "brace")
	var bottom := main.get("action_bottom_text") as Label
	_expect(bottom != null and "138" in bottom.text, "the Action meter shows the real pool: "
		+ (bottom.text if bottom != null else "missing"))
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		var image: Image = root.get_texture().get_image()
		_expect(image != null and image.get_size() == SCREEN_SIZE, "a full frame")
		if image != null:
			_expect(_varied(image), "the frame is rendered, not blank")
			_expect(image.save_png(_artifacts.path_join("techniques-window.png")) == OK, "saved")
		# The ring, held open over the same fighter.
		window.call("close")
		var ring: Control = main.get("technique_ring") as Control
		# Rings stay shut while a text box has focus; nobody is typing here.
		root.gui_release_focus()
		app_state.set("selected_actor_id", -1)
		ring.call("open_ring", true)
		_expect(bool(main.call("_can_open_technique_ring")), "an open ring may stay open")
		for _frame: int in range(6):
			await process_frame
		await RenderingServer.frame_post_draw
		var ring_image: Image = root.get_texture().get_image()
		_expect(ring.visible and ring_image != null and _varied(ring_image), "the ring renders")
		if ring_image != null:
			_expect(ring_image.save_png(_artifacts.path_join("technique-ring.png")) == OK, "ring saved")
		ring.call("dismiss")
		# Settings > Controls: the ring keys, keys.ini and the reset button.
		var settings: Control = main.get("settings_window") as Control
		settings.call("open_tab", "Controls")
		var rings_row: Control = settings.find_child("Bind_technique_ring", true, false) as Control
		if rings_row != null:
			var scroll := rings_row.get_parent()
			while scroll != null and not scroll is ScrollContainer:
				scroll = scroll.get_parent()
			if scroll is ScrollContainer:
				(scroll as ScrollContainer).ensure_control_visible.call_deferred(rings_row)
		for _frame: int in range(6):
			await process_frame
		await RenderingServer.frame_post_draw
		var keys_image: Image = root.get_texture().get_image()
		_expect(keys_image != null and _varied(keys_image), "the Controls page renders")
		if keys_image != null:
			_expect(keys_image.save_png(_artifacts.path_join("controls-keys.png")) == OK, "controls saved")
	print("rendered techniques window: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	main.queue_free()
	await process_frame
	quit(_failures)

func _varied(image: Image) -> bool:
	var first := image.get_pixel(0, 0)
	for y: int in range(0, image.get_height(), 37):
		for x: int in range(0, image.get_width(), 41):
			if not image.get_pixel(x, y).is_equal_approx(first):
				return true
	return false

func _expect(ok: bool, label: String) -> void:
	if not ok:
		_failures += 1
		push_error("FAIL: " + label)
