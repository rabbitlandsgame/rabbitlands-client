extends SceneTree
## Player movement and neighbour residency must not steer the shared sun.

var failures := 0
var checks := 0
var stage: Node3D
var main: Control
var stream: ExteriorRegionStream
var sun: DirectionalLight3D
var environment: WorldEnvironment
var rig: IsometricCameraController
var registry: Dictionary

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	stage = Node3D.new()
	root.add_child(stage)
	sun = DirectionalLight3D.new()
	stage.add_child(sun)
	environment = WorldEnvironment.new()
	stage.add_child(environment)
	rig = IsometricCameraController.new()
	var camera := Camera3D.new()
	camera.name = "Camera"
	rig.add_child(camera)
	camera.owner = rig
	camera.unique_name_in_owner = true
	stage.add_child(rig)
	stream = ExteriorRegionStream.new()
	stage.add_child(stream)
	registry = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/registry.json")).maps
	stream.configure(registry)
	# Exercise the actual application lighting callbacks without opening a
	# session or loading terrain, actors and the rest of the UI.
	main = load("res://src/app/main.gd").new() as Control
	main.set("exterior_stream", stream)
	main.set("camera_rig", rig)
	main.set("world_sun", sun)
	main.set("world_environment", environment)
	var loader := WorldLoader.new()
	main.add_child(loader)
	main.set("world_loader", loader)
	for property: String in ["map_camera", "full_map_camera"]:
		var map_camera := Camera3D.new()
		main.add_child(map_camera)
		main.set(property, map_camera)
	var state := root.get_node("AppState")
	state.set("game_minute_interval_msec", 0)
	state.set("game_minute", 130)
	var regions := ["four_gates", "mirrorhold", "amberwood", "whitehorn_range"]
	var manifests: Dictionary = {}
	for region: String in regions:
		manifests[region] = WorldManifest.load_file(ProjectSettings.globalize_path(registry[region].manifest))
	_check_border("four_gates", "mirrorhold", manifests, loader)
	_check_border("amberwood", "whitehorn_range", manifests, loader)
	main.free()
	stage.queue_free()
	await process_frame
	print("border lighting tests: %d/%d passed" % [checks - failures, checks])
	quit(failures)

func _check_border(from: String, to: String, manifests: Dictionary, loader: WorldLoader) -> void:
	var near_manifest: WorldManifest = manifests[from]
	var far_manifest: WorldManifest = manifests[to]
	var near_original := near_manifest.data.duplicate(true)
	var far_original := far_manifest.data.duplicate(true)
	stream.active_map = from
	stream.active_manifest = near_manifest
	stream.residents = {to: {"manifest": far_manifest}}
	loader.manifest = near_manifest
	var join: Dictionary = {}
	for candidate: Dictionary in stream._candidates(Vector3.ZERO):
		if str(candidate.map) == to:
			join = candidate
			break
	_expect(not join.is_empty(), "%s has a surveyed connection to %s" % [from, to])
	if join.is_empty():
		return
	var frame: Dictionary = join.here.frame
	var anchor := ExteriorRegionStream._vector(frame.anchor)
	var normal := Vector3(float(frame.outward[0]), 0, float(frame.outward[1]))
	WorldEnvironmentBinder.apply(near_manifest, environment, sun)
	DayNightBinder.apply(near_manifest, environment, sun, 130.0)
	var original_basis := sun.global_basis
	var original_colour := sun.light_color
	# Walk out of and back into the entire transition band, including the
	# positions on the north bridge where the reported shadow swung around.
	for depth: float in [-90, -65, -37.5, -7.5, 0, -7.5, -37.5, -65, -90]:
		rig.set_focus(anchor + normal * depth)
		main.call("_update_border_lighting")
		main.call("_apply_day_night")
		_expect(sun.global_basis.is_equal_approx(original_basis),
			"%s sun stays fixed at border depth %.1f" % [from, depth])
		if depth == 0:
			_expect(not sun.light_color.is_equal_approx(original_colour),
				"%s still blends the region's light colour" % from)
		var lighting := stream.lighting_manifest(rig.focus)
		_expect(lighting.data.environment.sun.get("direction") == near_manifest.data.environment.sun.get("direction"),
			"%s lighting manifest keeps the authored heading at depth %.1f" % [from, depth])
	# Loading or evicting a neighbour while standing still also cannot turn it.
	rig.set_focus(anchor - normal * 10)
	stream.residents.clear()
	main.call("_update_border_lighting")
	stream.residents[to] = {"manifest": far_manifest}
	main.call("_update_border_lighting")
	_expect(sun.global_basis.is_equal_approx(original_basis), "%s neighbour residency does not turn the sun" % from)
	# A real rotated survey (Amberwood/Whitehorn) must preserve the light in
	# the viewer's frame when the application rebases camera and world.
	var before_view := rig.camera.global_basis.inverse() * sun.global_basis.z
	var rebase := ExteriorRegionStream.frame_transform(join.here.frame, join.there.frame).affine_inverse()
	main.call("_rebase_streamed_world", rebase)
	stream.active_map = to
	stream.active_manifest = far_manifest
	stream.residents = {from: {"manifest": near_manifest}}
	loader.manifest = far_manifest
	main.call("_update_border_lighting")
	main.call("_apply_day_night")
	_expect((rig.camera.global_basis.inverse() * sun.global_basis.z).is_equal_approx(before_view),
		"%s to %s crossing preserves the visible sun direction" % [from, to])
	main.call("_rebase_streamed_world", rebase.affine_inverse())
	stream.active_map = from
	stream.active_manifest = near_manifest
	stream.residents = {to: {"manifest": far_manifest}}
	loader.manifest = near_manifest
	main.call("_update_border_lighting")
	_expect(sun.global_basis.is_equal_approx(original_basis), "%s return crossing does not accumulate rotation" % from)
	var state := root.get_node("AppState")
	state.set("game_minute", 180)
	main.call("_update_border_lighting")
	_expect(not sun.global_basis.is_equal_approx(original_basis), "%s time of day still changes the sun angle" % from)
	state.set("game_minute", 130)
	main.call("_apply_day_night")
	_expect(sun.global_basis.is_equal_approx(original_basis), "%s restoring the hour restores the sun angle" % from)
	_expect(near_manifest.data == near_original and far_manifest.data == far_original,
		"border blending leaves both authored manifests untouched")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error("FAIL: " + message)
