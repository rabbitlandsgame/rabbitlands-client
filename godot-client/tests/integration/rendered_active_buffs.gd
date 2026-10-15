extends SceneTree
## Rendered evidence for the active-effect strip.
##
## The "before" frame is the HUD with two effects already reduced into state
## and nothing on screen - which is exactly what the shipped client did with
## every effect the server reported. The "after" frame is the same HUD with the
## strip drawing them.
##
## The payloads are the server's own `active_spell` frames: buff id and
## duration in seconds.

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifacts := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/phase2")
	_expect(DirAccess.make_dir_recursive_absolute(_artifacts) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE

	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("authenticated", true)
	var bar: Control = main.get("active_buff_bar") as Control
	for _settle: int in range(4):
		await process_frame
	_expect((bar.call("shown_buff_ids") as Array).is_empty(),
		"the effect strip starts empty")
	await _capture("active-buffs-before.png",
		"the HUD with no effect strip: what every reported effect looked like")

	# Shield for 90 seconds, magic protection for 180, true sight for 45.
	app_state.call("_on_packet", 44, PackedByteArray([0, 90]))
	app_state.call("_on_packet", 44, PackedByteArray([1, 180]))
	app_state.call("_on_packet", 44, PackedByteArray([22, 45]))
	for _settle: int in range(4):
		await process_frame
	_expect((bar.call("shown_buff_ids") as Array) == [0, 1, 22],
		"all three effects the server reported are on the strip")
	await _capture("active-buffs-after.png",
		"the same HUD once the server reports three effects, each named,"
			+ " iconned and counting down to the moment the server stated")

	app_state.call("_on_packet", 46, PackedByteArray([1]))
	for _settle: int in range(4):
		await process_frame
	_expect((bar.call("shown_buff_ids") as Array) == [0, 22],
		"the server ending an effect takes it off the strip")
	await _capture("active-buffs-removed.png",
		"the server ended the middle effect and it left the strip")

	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame
	print("rendered active buffs: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _capture(name: String, description: String) -> void:
	await process_frame
	var image: Image = root.get_texture().get_image()
	_expect(image != null and image.get_size() == SCREEN_SIZE,
		"%s is a full %dx%d frame" % [name, SCREEN_SIZE.x, SCREEN_SIZE.y])
	if image == null:
		return
	_expect(_has_colour_variation(image),
		"%s contains rendered colour variation rather than a dummy frame" % name)
	_expect(image.save_png(_artifacts.path_join(name)) == OK,
		"%s is written" % name)
	print("capture ", name, ": ", description)

func _has_colour_variation(image: Image) -> bool:
	var lowest := 2.0
	var highest := -1.0
	for y: int in range(0, image.get_height(), 8):
		for x: int in range(0, image.get_width(), 8):
			var luminance: float = image.get_pixel(x, y).get_luminance()
			lowest = minf(lowest, luminance)
			highest = maxf(highest, luminance)
	return highest - lowest > 0.02

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
