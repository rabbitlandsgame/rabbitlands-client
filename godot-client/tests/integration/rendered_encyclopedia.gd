extends SceneTree
## Captures the encyclopedia's three panes on a written page, a recipe page and
## a category list, so the width the middle pane is left with can be looked at
## rather than argued about.
##
## Needs a display. Writes PNGs to ELORIA_ARTIFACT_DIR.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var output: String = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty():
		output = ProjectSettings.globalize_path("res://test-artifacts/encyclopedia")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	await process_frame
	var window: Control = main.get("reference_window") as Control
	var panel: PanelContainer = window.get_node("ReferenceWindow") as PanelContainer
	var view: EncyclopediaView = window.get("encyclopedia") as EncyclopediaView
	main.call("_input", _key(KEY_E))
	await process_frame
	_expect(panel.visible, "the window opens")

	var pages: Array[Array] = [["harvesting", "entry:gathering:harvesting"],
		["category", "cat:alchemy:0"], ["index", "index"]]
	var alchemy: Array[String] = view.entry_ids_in("alchemy")
	if not alchemy.is_empty():
		pages.append(["recipe", "entry:alchemy:%s" % alchemy[0]])
	for page: Array in pages:
		view.open_page_key(str(page[1]))
		for _i: int in range(4):
			await process_frame
		var content: Control = view.find_child("Content", true, false) as Control
		print("%s: panel %s, middle pane %.0f px wide" % [page[0], panel.size,
			content.size.x])
		_expect(content.size.x >= panel.size.x * 0.5,
			"%s leaves the middle pane at least half the window: %.0f of %.0f"
				% [page[0], content.size.x, panel.size.x])
		var image: Image = root.get_texture().get_image()
		var area := Rect2i(Vector2i(panel.global_position), Vector2i(panel.size))
		image.get_region(area.intersection(Rect2i(Vector2i.ZERO, image.get_size()))) \
			.save_png(output.path_join("encyclopedia-%s.png" % page[0]))

	print("rendered encyclopedia: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

static func _key(keycode: Key) -> InputEventKey:
	var event := InputEventKey.new()
	event.pressed = true
	event.physical_keycode = keycode
	event.keycode = keycode
	event.ctrl_pressed = true
	return event

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
