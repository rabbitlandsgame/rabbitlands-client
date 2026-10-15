extends SceneTree
## Rendered evidence for the weather and the fires the server places.
##
## Before and after, as the brief requires for particles and weather: the same
## map with a clear sky and nothing burning, then rain, then a storm with its
## lightning flash, then the fires the server placed on it.
##
## Run under a real display:
##   godot --rendering-method gl_compatibility --path . \
##     --script tests/integration/rendered_weather.gd

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifact_directory := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path(
			"res://test-artifacts/weather")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	var main: Control = (load("res://src/app/main.tscn") as PackedScene
		).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("LoginBackground") as TextureRect).hide()
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).show()

	var app_state: Node = root.get_node("AppState")
	app_state.set("authenticated", true)
	app_state.set("local_actor_id", 99)
	app_state.set("current_map", "four_gates")
	app_state.set("actors", {99: {
		"actor_id": 99, "x": 360, "y": 229, "rotation": 0, "actor_type": 1,
		"kind": 1, "name": "Ari", "health": 72, "max_health": 100,
		"alive": true, "sitting": false}})
	main.call("_load_server_map")
	main.call("_sync_world")
	for _settle: int in range(24):
		await process_frame

	var layer: Weather3D = main.get("weather_layer") as Weather3D
	_expect(layer != null, "the world carries a weather layer")
	if layer == null:
		_finish(main)
		return

	await _capture("weather-before.png")
	_expect(not layer.is_raining(),
		"nothing falls before the server says anything")

	app_state.call("_on_packet", 100, PackedByteArray([1, 35]))
	for _settle: int in range(16):
		await process_frame
	await _capture("weather-rain.png")
	var shower: int = layer.rain_particles()

	app_state.call("_on_packet", 100, PackedByteArray([2, 95]))
	for _settle: int in range(16):
		await process_frame
	await _capture("weather-storm.png")
	# The flash is captured separately, because it lights the whole scene and
	# would otherwise be the only thing the storm frame showed.
	app_state.call("_on_packet", 17, PackedByteArray([5]))
	await process_frame
	await _capture("weather-thunder.png")
	_expect(layer.rain_particles() > shower,
		"the storm draws more rain than the shower: %d then %d"
			% [shower, layer.rain_particles()])

	app_state.call("_on_packet", 100, PackedByteArray([0, 0]))
	for _settle: int in range(10):
		await process_frame
	# The three fire kinds the server can place, side by side.
	app_state.call("_on_packet", 61, PackedByteArray([0x00, 0x03, 0xe6, 0x01, 0]))
	app_state.call("_on_packet", 61, PackedByteArray([0x04, 0x03, 0xe6, 0x01, 1]))
	app_state.call("_on_packet", 61, PackedByteArray([0x08, 0x03, 0xe6, 0x01, 2]))
	for _settle: int in range(20):
		await process_frame
	await _capture("weather-fires.png")
	_expect(layer.fire_count() == 3, "all three fires are burning: %d"
		% layer.fire_count())

	app_state.call("_on_packet", 62, PackedByteArray([0x04, 0x03, 0xe6, 0x01]))
	for _settle: int in range(8):
		await process_frame
	_expect(layer.fire_count() == 2,
		"and one the server puts out goes out: %d" % layer.fire_count())

	_finish(main)

func _finish(main: Node) -> void:
	print("rendered weather: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	main.queue_free()
	await process_frame
	quit(_failures)

func _capture(file_name: String) -> void:
	for _settle: int in range(4):
		await process_frame
	RenderingServer.force_draw(false)
	var image_value: Variant = root.get_texture().get_image()
	if not image_value is Image:
		_expect(false, "%s: a rendered frame is available" % file_name)
		return
	var image: Image = image_value as Image
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		"%s: the frame has reference dimensions" % file_name)
	var sampled: Dictionary = {}
	for y: int in range(0, image.get_height(), 16):
		for x: int in range(0, image.get_width(), 16):
			sampled[image.get_pixel(x, y).to_html()] = true
	_expect(sampled.size() >= 24,
		"%s: the frame carries visual detail (%d colours)"
			% [file_name, sampled.size()])
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"%s: written" % file_name)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
