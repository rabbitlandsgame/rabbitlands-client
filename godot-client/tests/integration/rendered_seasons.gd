extends SceneTree
## Same native map, camera and noon for all four seasonal previews.
## Runs the production map loader, season palette, weather and lighting code.
## Weather examples are held deliberately; they are not a weather forecast.

const SeasonSky = preload("res://src/world/season_sky.gd")
const SeasonSurfaces = preload("res://src/world/season_surfaces.gd")
const TrailerCamera = preload("res://src/dev/trailer_camera/trailer_camera.gd")
const SIZE := Vector2i(1600, 900)
const NAMES := ["winter", "spring", "summer", "autumn"]
const EXAMPLES := [
	[2, 32, 68, 24, 16, 16, 0], # light_snow at 80%
	[1, 28, 68, 18, 24, 24, 0], # light_rain at 80%
	[0, 0, 0, 0, 0, 10, 0],    # clear
	[0, 0, 44, 68, 14, 4, 0],  # fog at 80%
]
var artifacts := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty():
		artifacts = ProjectSettings.globalize_path("res://test-artifacts/seasons-preview")
	DirAccess.make_dir_recursive_absolute(artifacts)
	root.size = SIZE
	var stage := TrailerCamera.new()
	stage.shot_path = OS.get_environment("RL_SEASONS_SHOT")
	root.add_child(stage)
	var deadline := Time.get_ticks_msec() + 180000
	while stage._state == "loading" and Time.get_ticks_msec() < deadline:
		await process_frame
	if stage._state == "loading" or stage._active.is_empty():
		push_error("season preview map did not finish loading")
		await ContinentChunkStream.drain_workers(self)
		quit(1)
		return
	stage.set_process(false)
	stage._state = "done"
	stage._minute = 180.0
	var appearance := OS.get_environment("RL_SEASONS_APPEARANCE")
	if not appearance.is_empty():
		LookProfile.set_player_mode(LookProfile.mode_named(appearance))
		for world: Dictionary in LookSwitch.worlds(stage._active.root, stage._active.manifest, stage._residents):
			LookSwitch.sync(world.root, world.manifest)
	var base: WorldManifest = stage._lighting
	for _frame: int in range(30):
		await process_frame
	for index: int in range(4):
		SeasonSurfaces.set_season({"index": index})
		for world: Dictionary in LookSwitch.worlds(stage._active.root, stage._active.manifest, stage._residents):
			var count := SeasonSurfaces.apply(world.root, world.manifest)
			if count > 0:
				print("season surfaces root=%s count=%d" % [world.root.name, count])
		# A fresh layer per example prevents the preceding season's particles
		# lingering through their natural lifetime in a comparison still.
		var weather := Weather3D.new()
		stage.add_child(weather)
		weather.follow(Vector3(-90.0, 123.0, -105.0))
		var seasonal: WorldManifest = SeasonSky.seasonal(base, {"index": index})
		weather.set_state([0, 0, 0, 0, 0, 10, 0], [0, 0, 0, 0, 0, 10, 0], 0.0, true, true)
		stage._lighting = seasonal
		_apply_light(stage)
		await _capture(NAMES[index] + "-clear.png", 0.5)
		weather.set_state(EXAMPLES[index], EXAMPLES[index], 0.0, true, true)
		stage._lighting = WeatherSky.weathered_look(seasonal, weather.look())
		_apply_light(stage)
		await _capture(NAMES[index] + "-weather.png", 4.0)
		weather.queue_free()
		await process_frame
	var receipt := {
		"map": "landfall", "game_minute": 180, "appearance": LookProfile.mode_name(LookProfile.mode()),
		"source": "native client renderer, prepared offline scenery preview",
		"camera": stage._camera.global_position, "weather_examples": EXAMPLES,
		"seasons": NAMES, "weather_is_held_for_comparison": true,
		"seasonal_ground_and_foliage": true,
	}
	var receipt_file := FileAccess.open(artifacts.path_join("capture.json"), FileAccess.WRITE)
	receipt_file.store_string(JSON.stringify(receipt, "\t"))
	stage.queue_free()
	await process_frame
	await ContinentChunkStream.drain_workers(self)
	print("season previews: PASS")
	quit(0)

func _apply_light(stage: Node3D) -> void:
	# Rebind density as well as colours, like main's weather lighting path.
	WorldEnvironmentBinder.apply(stage._lighting, stage._world_environment, stage._sun)
	LookSky.install(stage._lighting, stage._world_environment)
	stage._apply_hour()

func _capture(filename: String, seconds: float) -> void:
	var until := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < until:
		await process_frame
	await RenderingServer.frame_post_draw
	var picture := root.get_texture().get_image()
	if picture == null or picture.is_empty() or picture.get_width() != SIZE.x:
		push_error("no full rendered frame: " + filename)
		quit(1)
		return
	var error := picture.save_png(artifacts.path_join(filename))
	if error != OK:
		push_error("cannot save " + filename)
		quit(1)
	print("capture " + filename)
