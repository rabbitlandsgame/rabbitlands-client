extends SceneTree
## Rendered check of the play camera's far plane (view_reach.gd, WD-C4) on a
## synthetic field: flat ground to 1.5 km with pillars every few tens of
## metres along the view and boxes buried under the ground in front of the
## camera, the binder's sky, sun and exponential fog (a continent map's), and
## the real orbit rig. Saved as `view-reach-<renderer>-<pass>.png` with
## `view-reach-<renderer>.json` beside them.
##
## What it checks, per renderer:
## - LOW at -15 degrees draws less than HIGH (the pillars past the 232 m cut),
##   and where the far plane cuts the ground the ground is already the fog's
##   own colour: the frame with the cut matches, below the cut, the same frame
##   drawn to 1800 m under the same fog, and its last ground rows match the
##   fully fogged ground beyond the cut in that frame (no hard edge in the
##   ground, only the fog meeting the sky);
## - the same for Full painted's haze;
## - ELORIA_VIEW_REACH=ground's narrowed draw (camera_set_perspective just
##   before the draw) takes effect: at -60 degrees the buried boxes are not
##   drawn, and the picture is unchanged;
## - HIGH after all of it draws the first HIGH frame again, pixel for pixel.
##
## Windowed, under the GPU lock, isolated APPDATA/LOCALAPPDATA:
##   ELORIA_ARTIFACT_DIR=<dir> Godot --log-file <log> --path godot-client
##     --rendering-method forward_plus|mobile|gl_compatibility
##     --resolution 640x360 --audio-driver Dummy
##     --script res://tests/integration/rendered_view_reach.gd

const ViewReach := preload("res://src/world/view_reach.gd")
const SETTLE_FRAMES := 6
## Channel difference (0-255) taken as the same colour.
const SAME_LEVELS := 6

var _failures := 0
var _artifacts := ""
var _method := ""
var _rig: IsometricCameraController
var _camera: Camera3D
var _world_environment: WorldEnvironment
var _report := {"passes": {}, "checks": []}

func _init() -> void:
	_run.call_deferred()

func _expect(ok: bool, message: String) -> bool:
	(_report.checks as Array).append({"ok": ok, "check": message})
	if ok:
		print("PASS: ", message)
	else:
		_failures += 1
		push_error("FAIL: " + message)
	return ok

func _run() -> void:
	_method = RenderingServer.get_current_rendering_method()
	_artifacts = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifacts.is_empty():
		_artifacts = ProjectSettings.globalize_path("res://test-artifacts/view-reach")
	DirAccess.make_dir_recursive_absolute(_artifacts)
	OS.unset_environment(ViewReach.VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_build()
	LookProfile.set_player_mode(LookProfile.Mode.PAINTED_GROUND)
	await _pose(-15.0, 26.0)
	var high := await _capture("high_m15", LookProfile.Quality.HIGH)
	var low := await _capture("low_m15", LookProfile.Quality.LOW)
	_expect(_camera.far == 232.0 and _rig.view_reach().horizon_far() == 232.0,
		"LOW at 26 m draws to 232 m (%.0f)" % _camera.far)
	_expect(int(low.objects) < int(high.objects) and int(low.primitives) <= int(high.primitives),
		"LOW at -15 degrees draws less than HIGH: %d/%d objects, %d/%d primitives"
			% [low.objects, high.objects, low.primitives, high.primitives])
	var uncut := await _capture_uncut("low_m15_uncut")
	_check_cut("Painted ground", low.image, uncut.image)

	await _pose(-60.0, 26.0)
	var steep := await _capture("low_m60", LookProfile.Quality.LOW)
	_rig.view_reach().mode = "ground"
	var narrowed := await _capture("low_m60_ground", LookProfile.Quality.LOW)
	var drawn := _rig.view_reach().drawn_far()
	_expect(drawn < 100.0 and _camera.far == 232.0,
		"the ground fit draws to %.0f m while the camera keeps 232 m" % drawn)
	_expect(int(narrowed.objects) < int(steep.objects),
		"and the boxes buried behind the visible ground are not drawn: %d -> %d objects"
			% [steep.objects, narrowed.objects])
	_expect(_max_difference(steep.image, narrowed.image) <= 2,
		"and the picture is unchanged (max difference %d)" % _max_difference(steep.image, narrowed.image))
	_rig.view_reach().mode = "auto"

	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	var manifest := _manifest()
	LookSky.install(manifest, _world_environment)
	LookSky.apply(manifest, _world_environment, 720.0)
	await _pose(-15.0, 26.0)
	var painted_high := await _capture("full_painted_high_m15", LookProfile.Quality.HIGH)
	var haze_end := _world_environment.environment.fog_depth_end
	var painted_low := await _capture("full_painted_low_m15", LookProfile.Quality.LOW)
	_expect(is_equal_approx(_world_environment.environment.fog_depth_end, 222.0)
		and is_equal_approx(haze_end, LookProfile.HAZE_END),
		"the painted haze ends at 222 m on LOW (%.0f m on HIGH)" % haze_end)
	_expect(int(painted_low.objects) < int(painted_high.objects),
		"Full painted LOW draws less than HIGH: %d/%d objects" % [painted_low.objects, painted_high.objects])
	var painted_uncut := await _capture_uncut("full_painted_low_m15_uncut")
	_check_cut("Full painted", painted_low.image, painted_uncut.image)
	LookProfile.set_player_mode(LookProfile.Mode.PAINTED_GROUND)
	_bind()
	await _pose(-15.0, 26.0)
	var again := await _capture("high_m15_again", LookProfile.Quality.HIGH)
	_expect(_camera.far == 1800.0 and _max_difference(high.image, again.image) == 0,
		"HIGH afterwards draws its first frame again, pixel for pixel (max difference %d)"
			% _max_difference(high.image, again.image))

	_report["renderer"] = _method
	_report["failures"] = _failures
	var file := FileAccess.open(_artifacts.path_join("view-reach-%s.json" % _method), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(_report, "  "))
	print("rendered view reach (%s): %s" % [_method, "PASS" if _failures == 0 else "FAIL (%d)" % _failures])
	quit(_failures)

func _manifest() -> WorldManifest:
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "boarsend"}, "environment": {
		"sky": {"topColor": [0.24, 0.45, 0.72], "horizonColor": [0.72, 0.76, 0.76],
			"groundBottomColor": [0.35, 0.3, 0.22], "groundHorizonColor": [0.62, 0.58, 0.48]},
		"sun": {"enabled": true, "energy": 1.2, "rotationDegrees": [-50, -30, 0]},
		"ambient": {"energy": 0.8, "color": [0.7, 0.72, 0.75]},
		"fog": {"enabled": true, "color": [0.7, 0.68, 0.58], "density": 0.0006}}}
	return manifest

func _build() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var checker := Image.create(2, 2, false, Image.FORMAT_RGB8)
	checker.set_pixel(0, 0, Color(0.32, 0.46, 0.22))
	checker.set_pixel(1, 1, Color(0.32, 0.46, 0.22))
	checker.set_pixel(1, 0, Color(0.42, 0.38, 0.24))
	checker.set_pixel(0, 1, Color(0.42, 0.38, 0.24))
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_texture = ImageTexture.create_from_image(checker)
	ground_material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	ground_material.uv1_scale = Vector3(300, 300, 1)
	var plane := PlaneMesh.new()
	plane.size = Vector2(3000, 3000)
	plane.subdivide_width = 59
	plane.subdivide_depth = 59
	var ground := MeshInstance3D.new()
	ground.mesh = plane
	ground.material_override = ground_material
	stage.add_child(ground)
	var body := StaticBody3D.new()
	body.collision_layer = 8
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(3000, 2, 3000)
	shape.shape = box
	shape.position.y = -1.0
	body.add_child(shape)
	stage.add_child(body)
	var pillar_material := StandardMaterial3D.new()
	pillar_material.albedo_color = Color(0.85, 0.3, 0.2)
	var pillar := BoxMesh.new()
	pillar.size = Vector3(6, 30, 6)
	for metres: float in [60.0, 120.0, 180.0, 220.0, 250.0, 280.0, 320.0, 400.0, 600.0, 900.0]:
		for side: float in [-40.0, 0.0, 40.0]:
			var mesh := MeshInstance3D.new()
			mesh.mesh = pillar
			mesh.material_override = pillar_material
			mesh.position = Vector3(side, 15.0, -metres)
			stage.add_child(mesh)
	var buried := BoxMesh.new()
	buried.size = Vector3(10, 10, 10)
	for index: int in 8:
		var mesh := MeshInstance3D.new()
		mesh.mesh = buried
		mesh.material_override = pillar_material
		mesh.position = Vector3(-30.0 + index * 8.0, -70.0, -(70.0 + index * 15.0))
		stage.add_child(mesh)
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	stage.add_child(sun)
	_world_environment = WorldEnvironment.new()
	stage.add_child(_world_environment)
	_rig = IsometricCameraController.new()
	_camera = Camera3D.new()
	_camera.name = "Camera"
	_camera.fov = 50.0
	_camera.near = 1.0
	_camera.far = 1800.0
	_rig.add_child(_camera)
	_camera.owner = _rig
	_camera.unique_name_in_owner = true
	stage.add_child(_rig)
	_camera.make_current()
	_rig.set_focus(Vector3.ZERO)
	_bind()

func _bind() -> void:
	WorldEnvironmentBinder.apply(_manifest(), _world_environment, root.find_child("Sun", true, false) as DirectionalLight3D)

## The rig faces -Z (yaw 0 puts the camera on +Z), at `pitch` and `distance`.
func _pose(pitch: float, distance: float) -> void:
	_rig.yaw_degrees = 0.0
	_rig.pitch_degrees = pitch
	_rig.distance = distance
	_rig._update_camera()
	await physics_frame
	await physics_frame

func _capture(name: String, quality: int) -> Dictionary:
	LookProfile.set_player_quality(quality)
	for frame: int in SETTLE_FRAMES:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.convert(Image.FORMAT_RGB8)
	image.save_png(_artifacts.path_join("view-reach-%s-%s.png" % [_method, name]))
	var environment := _world_environment.environment
	var entry := {"quality": LookProfile.quality_name(quality), "far": _camera.far,
		"drawn_far": _rig.view_reach().drawn_far(), "mode": _rig.view_reach().mode,
		"objects": root.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_OBJECTS_IN_FRAME),
		"primitives": root.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_PRIMITIVES_IN_FRAME),
		"draw_calls": root.get_render_info(Viewport.RENDER_INFO_TYPE_VISIBLE, Viewport.RENDER_INFO_DRAW_CALLS_IN_FRAME),
		"fog": {"mode": environment.fog_mode, "begin": environment.fog_depth_begin,
			"end": environment.fog_depth_end, "curve": environment.fog_depth_curve,
			"density": environment.fog_density}}
	(_report.passes as Dictionary)[name] = entry
	var result := entry.duplicate()
	result["image"] = image
	return result

## The LOW frame again, under the same fitted fog but drawn to 1800 m.
func _capture_uncut(name: String) -> Dictionary:
	var environment := _world_environment.environment
	var fitted := {}
	for property: StringName in ViewReach.FOG_PROPERTIES:
		fitted[property] = environment.get(property)
	_rig.view_reach().mode = "off"
	_rig._fit_view_reach()
	var base := {}
	for property: StringName in ViewReach.FOG_PROPERTIES:
		base[property] = environment.get(property)
		environment.set(property, fitted[property])
	var result := await _capture(name, LookProfile.Quality.LOW)
	_expect(_camera.far == 1800.0, "%s is drawn to the scene's 1800 m" % name)
	for property: StringName in ViewReach.FOG_PROPERTIES:
		environment.set(property, base[property])
	_rig.view_reach().mode = "auto"
	return result

## Where the frame with the cut first differs from the one drawn to 1800 m,
## column by column: below that row the two must match, and the cut frame's
## last ground rows must already be the fogged ground's colour.
func _check_cut(label: String, cut: Image, uncut: Image) -> void:
	var size := cut.get_size()
	var worst_below := 0
	var worst_edge := 0
	var rows: Array[int] = []
	for column: int in [size.x / 8, size.x / 4, size.x / 2, size.x * 3 / 4, size.x * 7 / 8]:
		var edge := -1
		for row: int in range(size.y - 1, -1, -1):
			if _difference(cut.get_pixel(column, row), uncut.get_pixel(column, row)) > SAME_LEVELS:
				edge = row
				break
		rows.append(edge)
		if edge < 2 or edge > size.y - 4:
			continue
		for row: int in range(edge + 3, size.y):
			worst_below = maxi(worst_below, _difference(cut.get_pixel(column, row), uncut.get_pixel(column, row)))
		worst_edge = maxi(worst_edge, _difference(cut.get_pixel(column, edge + 2), uncut.get_pixel(column, edge - 1)))
	(_report.passes as Dictionary)["%s cut rows" % label] = rows
	# A column without a row (-1) is one where the fogged ground beyond the
	# cut is the sky's own colour there: nothing to see at the cut at all.
	print("info: %s: rows where the cut frame's sky meets its fogged ground: %s (-1: no visible difference)"
		% [label, rows])
	_expect(worst_below <= 2, "%s: below the cut both frames match (max difference %d)" % [label, worst_below])
	_expect(worst_edge <= SAME_LEVELS,
		"%s: the ground at the cut is already the fog's colour (max difference %d from fogged ground beyond it)"
			% [label, worst_edge])

static func _difference(a: Color, b: Color) -> int:
	return roundi(maxf(maxf(absf(a.r - b.r), absf(a.g - b.g)), absf(a.b - b.b)) * 255.0)

static func _max_difference(a: Image, b: Image) -> int:
	var worst := 0
	var size := a.get_size()
	for y: int in range(0, size.y, 2):
		for x: int in range(0, size.x, 2):
			worst = maxi(worst, _difference(a.get_pixel(x, y), b.get_pixel(x, y)))
	return worst
