extends SceneTree
## The play camera's far plane (wave 2 WD-C4, view_reach.gd): fitted to the
## orbit distance on LOW outdoors with the fog whole before the cut, the
## scene's own far plane and fog everywhere else, a campaign's far plane kept,
## and one ground sampler shared with the sun's shadow fit.

const ViewReach := preload("res://src/world/view_reach.gd")
const Fit := preload("res://src/world/sun_shadow_fit.gd")
const Warmup := preload("res://src/world/camera_shader_warmup.gd")
const LOW := LookProfile.Quality.LOW
const MEDIUM := LookProfile.Quality.MEDIUM
const HIGH := LookProfile.Quality.HIGH
const SCENE_FAR := 1800.0

var failures := 0
var _saved_variables := {}

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _run() -> void:
	for variable: String in [ViewReach.VARIABLE, "ELORIA_WORLD_DISTANCE",
			LookProfile.QUALITY_VARIABLE, LookProfile.ENABLE_VARIABLE, Fit.DISABLE_VARIABLE]:
		_saved_variables[variable] = OS.get_environment(variable)
		OS.unset_environment(variable)
	_check_policy()
	_check_fog_shapes()
	_check_modes()
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1280, 720)
	root.add_child(viewport)
	var stage := Node3D.new()
	viewport.add_child(stage)
	var ground := StaticBody3D.new()
	ground.collision_layer = 8
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(1200, 2, 1200)
	shape.shape = box
	shape.position.y = -1.0
	ground.add_child(shape)
	stage.add_child(ground)
	var world_environment := WorldEnvironment.new()
	stage.add_child(world_environment)
	var camera := Camera3D.new()
	camera.fov = 50.0
	camera.near = 1.0
	camera.far = SCENE_FAR
	stage.add_child(camera)
	camera.make_current()
	_frame(camera, -60.0, 26.0)
	await physics_frame
	await physics_frame
	_check_binder_marks(world_environment)
	await _check_far_and_fog(camera, world_environment)
	await _check_ownership(camera, world_environment)
	await _check_sampler(camera, stage)
	await _check_ground_fit(camera, world_environment)
	await _check_rig(viewport, world_environment)
	viewport.queue_free()
	await process_frame
	for variable: String in _saved_variables:
		if str(_saved_variables[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(_saved_variables[variable]))
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)
	print("view reach tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _check_policy() -> void:
	expect(ViewReach.bucket(26.0) == 32.0 and ViewReach.bucket(90.0) == 96.0
		and ViewReach.bucket(1.5) == 8.0 and ViewReach.bucket(32.0) == 32.0
		and ViewReach.bucket(0.0) == 0.0, "the orbit distance is rounded up to 8 m")
	expect(ViewReach.camera_far(26.0, LOW, SCENE_FAR) == 232.0
		and ViewReach.camera_far(90.0, LOW, SCENE_FAR) == 296.0
		and ViewReach.camera_far(1.5, LOW, SCENE_FAR) == 208.0,
		"LOW draws 200 m past the bucket: 232 m at 26 m, 296 m fully out, 208 m fully in")
	expect(ViewReach.camera_far(26.0, MEDIUM, SCENE_FAR) == SCENE_FAR
		and ViewReach.camera_far(90.0, HIGH, SCENE_FAR) == SCENE_FAR,
		"MEDIUM and HIGH keep the scene's far plane")
	expect(ViewReach.camera_far(26.0, LOW, 100.0) == 100.0,
		"never past the scene's own far plane")
	expect(ViewReach.ground_far(37.0, 232.0) == 64.0 and ViewReach.ground_far(400.0, 232.0) == 232.0
		and ViewReach.ground_far(1.0, 232.0) == ViewReach.GROUND_FAR_MIN,
		"the ground fit adds its margin in 8 m steps, within the far plane")

## Godot's depth fog at `distance` from the camera.
static func _fog_amount(shape: Dictionary, distance: float) -> float:
	return float(shape[&"fog_density"]) * pow(smoothstep(float(shape[&"fog_depth_begin"]),
		float(shape[&"fog_depth_end"]), distance), float(shape[&"fog_depth_curve"]))

func _check_fog_shapes() -> void:
	var exponential := {&"fog_mode": Environment.FOG_MODE_EXPONENTIAL, &"fog_depth_begin": 10.0,
		&"fog_depth_end": 100.0, &"fog_depth_curve": 1.0, &"fog_density": 0.0006}
	var fitted := ViewReach.fitted_fog(exponential, 232.0)
	expect(int(fitted[&"fog_mode"]) == Environment.FOG_MODE_DEPTH
		and is_equal_approx(float(fitted[&"fog_depth_begin"]), LookProfile.HAZE_BEGIN)
		and is_equal_approx(float(fitted[&"fog_depth_end"]), 222.0)
		and is_equal_approx(float(fitted[&"fog_depth_curve"]), LookProfile.HAZE_CURVE)
		and is_equal_approx(float(fitted[&"fog_density"]), 1.0),
		"a map's exponential fog becomes the haze's depth fog, whole 10 m before a 232 m cut")
	var haze := {&"fog_mode": Environment.FOG_MODE_DEPTH, &"fog_depth_begin": LookProfile.HAZE_BEGIN,
		&"fog_depth_end": LookProfile.HAZE_END, &"fog_depth_curve": LookProfile.HAZE_CURVE,
		&"fog_density": 0.75}
	fitted = ViewReach.fitted_fog(haze, 296.0)
	expect(is_equal_approx(float(fitted[&"fog_depth_begin"]), LookProfile.HAZE_BEGIN)
		and is_equal_approx(float(fitted[&"fog_depth_end"]), 286.0)
		and is_equal_approx(float(fitted[&"fog_depth_curve"]), LookProfile.HAZE_CURVE)
		and is_equal_approx(float(fitted[&"fog_density"]), 1.0),
		"the painted haze ends at the cut instead of 420 m, and is opaque there")
	var bank := {&"fog_mode": Environment.FOG_MODE_DEPTH, &"fog_depth_begin": 16.0,
		&"fog_depth_end": 200.0, &"fog_depth_curve": 1.0, &"fog_density": 0.95}
	fitted = ViewReach.fitted_fog(bank, 232.0)
	expect(is_equal_approx(float(fitted[&"fog_depth_begin"]), 16.0)
		and is_equal_approx(float(fitted[&"fog_depth_end"]), 200.0)
		and is_equal_approx(float(fitted[&"fog_density"]), 1.0),
		"a fog bank that already closes nearer keeps its shape, only made opaque")
	var narrow := {&"fog_mode": Environment.FOG_MODE_DEPTH, &"fog_depth_begin": 150.0,
		&"fog_depth_end": 600.0, &"fog_depth_curve": 1.4, &"fog_density": 0.3}
	fitted = ViewReach.fitted_fog(narrow, 208.0)
	expect(is_equal_approx(float(fitted[&"fog_depth_begin"]), 208.0 * ViewReach.FOG_BEGIN_SHARE)
		and float(fitted[&"fog_depth_begin"]) < float(fitted[&"fog_depth_end"]),
		"the fog begins no further out than 40 % of the far plane")
	var whole := true
	for base: Dictionary in [exponential, haze, bank, narrow]:
		for far: float in [208.0, 232.0, 264.0, 296.0]:
			var shape := ViewReach.fitted_fog(base, far)
			whole = whole and float(shape[&"fog_depth_end"]) <= far - ViewReach.FOG_CUT_METRES + 0.001 \
				and is_equal_approx(_fog_amount(shape, far), 1.0)
	expect(whole, "every fitted fog is whole at the far plane (every point of it lies at least that far)")
	var near_clear := is_zero_approx(_fog_amount(ViewReach.fitted_fog(exponential, 232.0), 45.0))
	expect(near_clear, "the default framing's ground (under 45 m) stays clear of it")

func _check_modes() -> void:
	expect(ViewReach.mode_from_environment() == "auto", "unset, the far plane is fitted")
	OS.set_environment(ViewReach.VARIABLE, "ground")
	expect(ViewReach.mode_from_environment() == "ground", "ELORIA_VIEW_REACH=ground adds the ground fit")
	OS.set_environment(ViewReach.VARIABLE, "off")
	expect(ViewReach.mode_from_environment() == "off", "ELORIA_VIEW_REACH=off turns it off")
	OS.unset_environment(ViewReach.VARIABLE)
	OS.set_environment("ELORIA_WORLD_DISTANCE", "off")
	expect(ViewReach.mode_from_environment() == "off", "and so does ELORIA_WORLD_DISTANCE=off")
	OS.unset_environment("ELORIA_WORLD_DISTANCE")

func _manifest(id: String, sun_enabled := true, fog := true) -> WorldManifest:
	var manifest := WorldManifest.new()
	var environment := {"sun": {"enabled": sun_enabled, "energy": 1.1},
		"sky": {"topColor": "3d7ec2", "horizonColor": "bcc9cd"}}
	if fog:
		environment["fog"] = {"enabled": true, "color": [0.7, 0.68, 0.58], "density": 0.0006}
	manifest.data = {"asset": {"id": id}, "environment": environment}
	return manifest

func _check_binder_marks(world_environment: WorldEnvironment) -> void:
	WorldEnvironmentBinder.apply(_manifest("boarsend"), world_environment, null)
	expect(ViewReach.horizon_fog(world_environment.environment),
		"an outdoor map with fog may have its far plane fitted")
	expect(world_environment.environment.duplicate(true).has_meta(ViewReach.OUTDOOR_META),
		"the mark survives the look switch's copy of develop's environment")
	WorldEnvironmentBinder.apply(_manifest("amberwood_amber_hall", false), world_environment, null)
	expect(not ViewReach.horizon_fog(world_environment.environment), "an interior may not")
	WorldEnvironmentBinder.apply(_manifest("sunmane_insides"), world_environment, null)
	expect(not ViewReach.horizon_fog(world_environment.environment),
		"nor an insides map whose void is meant dark (its region file keeps the sky unpainted)")
	WorldEnvironmentBinder.apply(_manifest("bellwatch", true, false), world_environment, null)
	expect(not ViewReach.horizon_fog(world_environment.environment),
		"nor an outdoor map without fog, in the appearances that keep the map's fog")

func _fog(environment: Environment) -> Dictionary:
	var values := {}
	for property: StringName in ViewReach.FOG_PROPERTIES:
		values[property] = environment.get(property)
	values[&"fog_light_color"] = environment.fog_light_color
	values[&"fog_sky_affect"] = environment.fog_sky_affect
	values[&"fog_aerial_perspective"] = environment.fog_aerial_perspective
	values[&"fog_enabled"] = environment.fog_enabled
	return values

func _check_far_and_fog(camera: Camera3D, world_environment: WorldEnvironment) -> void:
	WorldEnvironmentBinder.apply(_manifest("boarsend"), world_environment, null)
	var environment := world_environment.environment
	var bound := _fog(environment)
	var reach := ViewReach.new(camera)
	for level: int in [HIGH, MEDIUM]:
		for distance: float in [26.0, 90.0]:
			reach.fit(distance, level)
	expect(camera.far == SCENE_FAR and _fog(environment) == bound,
		"MEDIUM and HIGH leave the far plane and every fog value exactly as bound")
	reach.fit(26.0, LOW)
	expect(camera.far == 232.0 and reach.horizon_far() == 232.0,
		"LOW at 26 m draws to 232 m")
	expect(environment.fog_mode == Environment.FOG_MODE_DEPTH
		and is_equal_approx(environment.fog_depth_end, 222.0)
		and is_equal_approx(environment.fog_depth_begin, LookProfile.HAZE_BEGIN)
		and is_equal_approx(environment.fog_density, 1.0)
		and environment.fog_light_color == bound[&"fog_light_color"]
		and environment.fog_sky_affect == bound[&"fog_sky_affect"],
		"and its fog, in the map's own colour and sky share, is whole before the cut")
	reach.fit(90.0, LOW)
	expect(camera.far == 296.0 and is_equal_approx(environment.fog_depth_end, 286.0),
		"zoomed out, the far plane and the fog move out in the same frame")
	# Main's border blend writes the declared density ten times a second.
	environment.fog_density = 0.0009
	reach.fit(90.0, LOW)
	expect(is_equal_approx(environment.fog_density, 1.0),
		"a density another writer sets is fitted over before the draw")
	reach.fit(90.0, MEDIUM)
	var back := _fog(environment)
	expect(camera.far == SCENE_FAR and int(back[&"fog_mode"]) == Environment.FOG_MODE_EXPONENTIAL
		and is_equal_approx(float(back[&"fog_density"]), 0.0009)
		and is_equal_approx(float(back[&"fog_depth_begin"]), float(bound[&"fog_depth_begin"]))
		and is_equal_approx(float(back[&"fog_depth_end"]), float(bound[&"fog_depth_end"])),
		"MEDIUM gives back the scene's far plane and the fog as its writers left it")
	# Full painted: the sky's haze is rewritten every 100 ms over the fit.
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	var lighting := _manifest("boarsend")
	LookSky._haze(environment, lighting, Color(0.8, 0.75, 0.7))
	var haze := _fog(environment)
	reach.fit(26.0, LOW)
	LookSky._haze(environment, lighting, Color(0.8, 0.75, 0.7))
	reach.fit(26.0, LOW)
	expect(is_equal_approx(environment.fog_depth_end, 222.0)
		and is_equal_approx(environment.fog_depth_begin, LookProfile.HAZE_BEGIN)
		and is_equal_approx(environment.fog_depth_curve, LookProfile.HAZE_CURVE)
		and is_equal_approx(environment.fog_density, 1.0),
		"the painted haze rewritten over the fit is fitted again")
	reach.fit(26.0, HIGH)
	expect(_fog(environment) == haze and camera.far == SCENE_FAR,
		"and HIGH gives the haze back exactly")
	LookProfile.set_player_mode(LookProfile.MODE_DEFAULT)
	# A new map binds a new environment; the old one gets its fog back.
	reach.fit(26.0, LOW)
	var old := environment
	WorldEnvironmentBinder.apply(_manifest("brambleshaw"), world_environment, null)
	reach.fit(26.0, LOW)
	expect(_fog(old) == haze and is_equal_approx(world_environment.environment.fog_density, 1.0),
		"a newly bound environment is fitted and the one it replaced given back")
	WorldEnvironmentBinder.apply(_manifest("amberwood_amber_hall", false), world_environment, null)
	var indoor := _fog(world_environment.environment)
	reach.fit(26.0, LOW)
	expect(camera.far == SCENE_FAR and _fog(world_environment.environment) == indoor,
		"an interior on LOW keeps the scene's far plane and its fog")
	WorldEnvironmentBinder.apply(_manifest("boarsend"), world_environment, null)
	reach.fit(26.0, LOW)
	world_environment.environment.fog_enabled = false
	reach.fit(26.0, LOW)
	expect(camera.far == SCENE_FAR, "fog turned off (the mine's dark) gives the far plane back")
	world_environment.environment.fog_enabled = true
	reach.mode = "off"
	reach.fit(26.0, LOW)
	expect(camera.far == SCENE_FAR, "mode off leaves the scene's far plane")
	reach.mode = "auto"
	reach.fit(26.0, LOW)
	var steady := _fog(world_environment.environment)
	var started := Time.get_ticks_usec()
	for repeat: int in 1000:
		reach.fit(26.0, LOW)
	print("info: a LOW frame's fit with nothing to change: %.1f us"
		% ((Time.get_ticks_usec() - started) / 1000.0))
	expect(_fog(world_environment.environment) == steady and camera.far == 232.0,
		"frames with nothing to change leave the fit as it was")
	var fitted := world_environment.environment
	reach.release()
	var idle := ViewReach.new(camera)
	started = Time.get_ticks_usec()
	for repeat: int in 1000:
		idle.fit(26.0, HIGH)
	print("info: a HIGH frame's fit: %.1f us" % ((Time.get_ticks_usec() - started) / 1000.0))
	expect(camera.far == SCENE_FAR and fitted.fog_mode == Environment.FOG_MODE_EXPONENTIAL
		and is_equal_approx(fitted.fog_density, 0.0006),
		"releasing the fit gives the far plane and the fog back")
	var rays := ViewReach.ray_sets
	for distance: float in [26.0, 40.0, 90.0]:
		reach.fit(distance, LOW)
	expect(ViewReach.ray_sets == rays, "the default fit casts no rays (LOW's sun casts no shadows)")
	reach.release()

func _check_ownership(camera: Camera3D, world_environment: WorldEnvironment) -> void:
	WorldEnvironmentBinder.apply(_manifest("boarsend"), world_environment, null)
	var environment := world_environment.environment
	var reach := ViewReach.new(camera)
	reach.fit(26.0, LOW)
	# A campaign that saved the rig's far plane and poses with it stays fitted.
	var saved := camera.far
	camera.far = saved
	reach.fit(26.0, LOW)
	expect(camera.far == 232.0 and is_equal_approx(environment.fog_depth_end, 222.0),
		"a campaign posing with the saved far plane keeps the fitted one and its fog")
	camera.far = 4000.0
	reach.fit(26.0, LOW)
	reach.fit(90.0, LOW)
	expect(camera.far == 4000.0 and environment.fog_mode == Environment.FOG_MODE_EXPONENTIAL,
		"a far plane someone else sets is kept, with the scene's fog")
	camera.far = saved
	reach.fit(90.0, LOW)
	expect(camera.far == 296.0 and is_equal_approx(environment.fog_depth_end, 286.0),
		"given back, the rig fits it again")
	# A campaign saves the far plane as it begins, poses with it every frame
	# and puts it back as it ends; a zoom or a quality switch during the scene
	# changes the rig's own meanwhile. The saved one is still the rig's.
	reach.fit(26.0, LOW)
	var begun := camera.far
	reach.fit(40.0, LOW)
	camera.far = begun
	reach.fit(40.0, LOW)
	expect(begun == 232.0 and camera.far == 240.0
		and is_equal_approx(environment.fog_depth_end, 230.0),
		"a campaign posing with a far plane the rig wrote before a zoom stays fitted (%.0f)"
			% camera.far)
	# Its blend between two of the rig's far planes: kept, and fogged at its cut.
	camera.far = 236.0
	reach.fit(40.0, LOW)
	expect(camera.far == 236.0 and environment.fog_mode == Environment.FOG_MODE_DEPTH
		and is_equal_approx(environment.fog_depth_end, 226.0),
		"a blend between two of the rig's far planes is kept, with its cut fogged")
	camera.far = begun
	reach.fit(40.0, HIGH)
	camera.far = begun
	reach.fit(40.0, HIGH)
	expect(camera.far == SCENE_FAR and environment.fog_mode == Environment.FOG_MODE_EXPONENTIAL
		and is_equal_approx(environment.fog_density, 0.0006),
		"switched to HIGH during the scene, its saved LOW far plane never stays on HIGH (%.0f)"
			% camera.far)
	camera.far = SCENE_FAR
	reach.fit(40.0, LOW)
	camera.far = begun
	reach.release()
	expect(camera.far == SCENE_FAR and environment.fog_mode == Environment.FOG_MODE_EXPONENTIAL,
		"releasing gives the scene's far plane back over any far plane the rig wrote")
	camera.far = saved
	reach.fit(90.0, LOW)
	reach.release()
	camera.far = 4000.0
	reach.release()
	expect(camera.far == 4000.0, "releasing never overwrites someone else's far plane")
	camera.far = SCENE_FAR

func _check_sampler(camera: Camera3D, stage: Node3D) -> void:
	var size := camera.get_viewport().get_visible_rect().size
	expect(ViewReach.sample_points(size) == Fit.sample_points(size)
		and ViewReach.sample_points(size).size() == 28,
		"the shadow fit samples the frame with the shared 28 rays")
	_frame(camera, -60.0, 26.0)
	ViewReach.forget_shared()
	var fresh := ViewReach.visible_depths(camera, 232.0)
	var rays := ViewReach.ray_sets
	var shared := ViewReach.shared_depths(camera, 232.0)
	expect(shared == fresh and ViewReach.ray_sets == rays + 1,
		"a shared cast measures exactly what a fresh one does")
	var nearer := ViewReach.shared_depths(camera, 100.0)
	var direct := ViewReach.visible_depths(camera, 100.0)
	expect(ViewReach.ray_sets == rays + 2 and nearer.is_equal_approx(direct),
		"a nearer ceiling in the same frame and pose is served without casting (%s, %s)"
			% [nearer, direct])
	var short := ViewReach.shared_depths(camera, 30.0)
	expect(not is_finite(short.y) and not is_finite(ViewReach.visible_depths(camera, 30.0).y)
		and ViewReach.ray_sets == rays + 3,
		"and ground beyond that ceiling reads as unmet, as a cast to it would")
	ViewReach.shared_depths(camera, 400.0)
	expect(ViewReach.ray_sets == rays + 4, "a further ceiling casts again")
	_frame(camera, -60.0, 24.0)
	ViewReach.shared_depths(camera, 100.0)
	expect(ViewReach.ray_sets == rays + 5, "and so does another pose")
	# One frame, one cast: the shadow fit reads the far plane fit's rays.
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	stage.add_child(sun)
	var fit := Fit.new()
	sun.add_child(fit, false, Node.INTERNAL_MODE_BACK)
	camera.far = 232.0
	_frame(camera, -60.0, 26.0)
	ViewReach.shared_depths(camera, camera.far)
	rays = ViewReach.ray_sets
	fit._fit()
	expect(ViewReach.ray_sets == rays and sun.directional_shadow_max_distance < 60.0,
		"the shadow fit in the same frame casts nothing and still fits (%.0f m)"
			% sun.directional_shadow_max_distance)
	sun.free()
	camera.far = SCENE_FAR
	_frame(camera, -60.0, 26.0)

func _check_ground_fit(camera: Camera3D, world_environment: WorldEnvironment) -> void:
	WorldEnvironmentBinder.apply(_manifest("boarsend"), world_environment, null)
	var reach := ViewReach.new(camera)
	reach.mode = "ground"
	_frame(camera, -60.0, 26.0)
	reach.fit(26.0, LOW)
	var deepest := ViewReach.visible_depths(camera, 232.0).y
	expect(camera.far == 232.0 and reach.drawn_far() == ViewReach.ground_far(deepest, 232.0)
		and reach.drawn_far() < 100.0,
		"the ground fit draws to the visible ground (%.1f m deep) plus its margin: %.0f m, the node keeps 232 m"
			% [deepest, reach.drawn_far()])
	camera.position += Vector3(0.0, 0.3, 0.4)
	reach.fit(26.0, LOW)
	var held := reach.drawn_far()
	_frame(camera, -60.0, 60.0)
	reach.fit(60.0, LOW)
	expect(reach.drawn_far() > held and camera.far == 264.0,
		"zooming out grows it in the same frame (%.0f m)" % reach.drawn_far())
	_frame(camera, -15.0, 26.0)
	reach.fit(26.0, LOW)
	expect(reach.drawn_far() == 232.0 and reach.state().ground_far == 0.0,
		"a view up to the horizon draws to the far plane, under the fog")
	_frame(camera, -60.0, 26.0)
	reach.fit(26.0, LOW)
	var warm := Camera3D.new()
	camera.get_parent().add_child(warm)
	Warmup._drawing[-1] = weakref(warm)
	reach.fit(26.0, LOW)
	expect(reach.drawn_far() == 232.0, "a warm-up draws to the far plane, never the ground fit")
	Warmup._drawing.erase(-1)
	warm.free()
	reach.fit(26.0, LOW)
	expect(reach.drawn_far() < 100.0, "and the fit returns after it")
	reach.fit(26.0, HIGH)
	expect(reach.drawn_far() == SCENE_FAR and camera.far == SCENE_FAR,
		"HIGH draws to the scene's far plane")
	reach.release()

func _check_rig(viewport: SubViewport, world_environment: WorldEnvironment) -> void:
	WorldEnvironmentBinder.apply(_manifest("boarsend"), world_environment, null)
	var rig := IsometricCameraController.new()
	var camera := Camera3D.new()
	camera.name = "Camera"
	camera.fov = 50.0
	camera.far = SCENE_FAR
	rig.add_child(camera)
	camera.owner = rig
	camera.unique_name_in_owner = true
	viewport.add_child(rig)
	camera.make_current()
	LookProfile.set_player_quality(HIGH)
	rig._fit_view_reach()
	expect(camera.far == SCENE_FAR, "the rig at HIGH keeps the scene's far plane")
	LookProfile.set_player_quality(LOW)
	rig._fit_view_reach()
	expect(camera.far == 232.0 and rig.camera_diagnostics().view_reach.horizon_far == 232.0,
		"the rig reads the quality itself: LOW at its 26 m draws to 232 m")
	rig.handle_mouse_button(_wheel(MOUSE_BUTTON_WHEEL_DOWN))
	for step: int in 30:
		rig.handle_mouse_button(_wheel(MOUSE_BUTTON_WHEEL_DOWN))
	rig._fit_view_reach()
	expect(camera.far == 296.0, "zoomed fully out it draws to 296 m")
	var target := rig.focus + Vector3.UP * 1.2
	var view := {"transform": Transform3D(Basis.IDENTITY, target + Vector3(0, 20, 20)).looking_at(target, Vector3.UP),
		"target": target, "fov": 51.0, "near": 0.5, "far": 1900.0}
	expect(rig.adopt_world_view(view, rig.focus), "the rig adopts an authored view")
	rig._fit_view_reach()
	expect(camera.far == 1900.0, "and keeps the far plane that view names")
	camera.far = 296.0
	rig._fit_view_reach()
	expect(camera.far == 232.0, "given back the rig's own, it fits it to the adopted 29 m view")
	viewport.remove_child(rig)
	expect(camera.far == SCENE_FAR
		and world_environment.environment.fog_mode == Environment.FOG_MODE_EXPONENTIAL,
		"a rig leaving the tree gives the far plane and the fog back")
	rig.free()
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)

func _wheel(button: MouseButton) -> InputEventMouseButton:
	var event := InputEventMouseButton.new()
	event.button_index = button
	event.pressed = true
	return event

func _frame(camera: Camera3D, pitch_degrees: float, distance: float) -> void:
	var pitch := deg_to_rad(pitch_degrees)
	camera.look_at_from_position(Vector3(0.0, -sin(pitch), cos(pitch)) * distance,
		Vector3.UP * 1.2, Vector3.UP)
