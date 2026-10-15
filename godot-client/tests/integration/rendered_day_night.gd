extends SceneTree
## Rendered evidence for the day/night cycle.
##
## The "before" frame is the map at the hour its package was authored for,
## which is what every map looked like at every hour: `NEW_MINUTE(5)` arrived
## and moved the clock face and nothing else. The rest are the same map and the
## same camera at four points on the server's own daylight curve.
##
## Every frame is checked for real colour variation, and the four are checked
## against each other so a run that changed nothing cannot pass as evidence.

const WORLD := "res://../eloria-assets/maps/four-gates/world.json"
const SCREEN_SIZE := Vector2i(1280, 720)
## Minute 0 is the server's darkest point and 180 its brightest.
const HOURS: Array[int] = [180, 90, 270, 0]
const NAMES: Array[String] = ["noon", "sunrise", "sunset", "midnight"]

var _artifacts := ""
var _failures := 0
var _luminance: Dictionary = {}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/phase3")
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

	var loader: WorldLoader = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/WorldLoader") as WorldLoader
	loader.load_world(ProjectSettings.globalize_path(WORLD))
	var deadline: int = Time.get_ticks_msec() + 180000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(loader.world_root != null, "the Four Gates package loaded"):
		await ContinentChunkStream.drain_workers(self)
		quit(_failures)
		return
	for _settle: int in range(30):
		await process_frame

	var camera: Camera3D = main.get_node(
		"GameView/ViewportContainer/Viewport/WorldRoot/CameraRig/Camera") as Camera3D
	_expect(DayNightBinder.drives(loader.manifest),
		"the package lets the hour drive its environment")

	# Before: the package's own environment, with no hour applied.
	WorldEnvironmentBinder.apply(loader.manifest,
		main.get_node(
			"GameView/ViewportContainer/Viewport/WorldRoot/Environment"),
		main.get_node("GameView/ViewportContainer/Viewport/WorldRoot/Sun"),
		null)
	await _aim(camera)
	await _capture("day-night-before.png",
		"the map at the hour its package was authored for, which is what every"
			+ " hour looked like")

	for index: int in range(HOURS.size()):
		app_state.call("_on_packet", 5, PackedByteArray([
			HOURS[index] & 0xff, (HOURS[index] >> 8) & 0xff]))
		main.call("_apply_day_night")
		await _aim(camera)
		await _capture("day-night-%s.png" % NAMES[index],
			"minute %d on the server's daylight curve" % HOURS[index])

	# The four hours must actually differ, and in the order the curve implies.
	var noon: float = float(_luminance.get("noon", 0.0))
	var midnight: float = float(_luminance.get("midnight", 0.0))
	var sunrise: float = float(_luminance.get("sunrise", 0.0))
	_expect(noon > midnight,
		"noon is brighter than midnight: %.4f vs %.4f" % [noon, midnight])
	_expect(noon > sunrise and sunrise > midnight,
		"sunrise sits between them: %.4f" % sunrise)

	app_state.set("authenticated", false)
	main.queue_free()
	await process_frame
	print("rendered day night: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	# Four Gates streams its framed chunks on a worker; quitting under a live
	# one crashes the process at exit (ContinentChunkStream.drain_workers).
	await ContinentChunkStream.drain_workers(self)
	quit(_failures)

func _aim(camera: Camera3D) -> void:
	camera.global_position = Vector3(60.0, 46.0, 120.0)
	camera.look_at(Vector3(0.0, 6.0, 0.0), Vector3.UP)
	for _settle: int in range(6):
		await process_frame

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
	var mean: float = _mean_luminance(image)
	_luminance[name.get_basename().replace("day-night-", "")] = mean
	print("capture ", name, ": ", description,
		"  mean_luminance=", "%.4f" % mean)

func _mean_luminance(image: Image) -> float:
	var total := 0.0
	var samples := 0
	# The lower two thirds only: the HUD's own panels do not move with the sun
	# and would flatten the difference this is measuring.
	for y: int in range(int(image.get_height() * 0.25), image.get_height(), 6):
		for x: int in range(0, image.get_width(), 6):
			total += image.get_pixel(x, y).get_luminance()
			samples += 1
	return total / maxf(1.0, float(samples))

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
