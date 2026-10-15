extends SceneTree
## Proves the screenshot binding writes a real image.
##
## Headless has no framebuffer, so `test_localization.gd` can only prove the
## client says it failed. This runs under a real display and checks the file
## the client claims it wrote.

const SCREEN_SIZE := Vector2i(1280, 720)

var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = SCREEN_SIZE
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	for _settle: int in range(6):
		await process_frame

	var saved: String = str(main.call("_save_screenshot"))
	_expect(not saved.is_empty(), "the client reports a path")
	if not saved.is_empty():
		_expect(FileAccess.file_exists(saved),
			"the file is where the client said: " + saved)
		var written := Image.new()
		_expect(written.load(saved) == OK
			and written.get_size() == SCREEN_SIZE,
			"and it is a full %dx%d image" % [SCREEN_SIZE.x, SCREEN_SIZE.y])
		var artifacts: String = OS.get_environment("ELORIA_ARTIFACT_DIR")
		if not artifacts.is_empty():
			DirAccess.make_dir_recursive_absolute(artifacts)
			_expect(written.save_png(
				artifacts.path_join("screenshot-binding.png")) == OK,
				"the capture is kept as evidence")
		DirAccess.remove_absolute(saved)

	var lines: Array = (root.get_node("/root/AppState").get("chat_lines") as Array)
	_expect(not lines.is_empty() and str((lines[lines.size() - 1] as Dictionary
		).get("text", "")).contains("Screenshot saved"),
		"the player is told where it went")

	print("rendered screenshot: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	main.queue_free()
	await process_frame
	quit(_failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
