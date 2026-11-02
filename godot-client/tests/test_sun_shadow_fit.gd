extends SceneTree
## The sun's shadow distance follows the ground the camera can see, never past
## what the scene set, and its cascade boundaries keep their place on screen.

const Fit := preload("res://src/world/sun_shadow_fit.gd")
const Warmup := preload("res://src/world/camera_shader_warmup.gd")
const AUTHORED := [0.1, 0.2, 0.5]
var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func _run() -> void:
	_check_ratios()
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1280, 720)
	root.add_child(viewport)
	var stage := Node3D.new()
	viewport.add_child(stage)
	var ground := StaticBody3D.new()
	ground.collision_layer = 8
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(600, 2, 600)
	shape.shape = box
	shape.position.y = -1.0
	ground.add_child(shape)
	stage.add_child(ground)
	var camera := Camera3D.new()
	camera.fov = 50.0
	camera.near = 1.0
	camera.far = 1800.0
	stage.add_child(camera)
	camera.make_current()
	_frame(camera, -60.0, 26.0)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	stage.add_child(sun)
	var environment := WorldEnvironment.new()
	stage.add_child(environment)
	var manifest := WorldManifest.new()
	manifest.data = {"environment": {"sun": {"shadows": true}}}
	WorldEnvironmentBinder.apply(manifest, environment, sun)
	WorldEnvironmentBinder.apply(manifest, environment, sun)
	var fit := sun.get_node_or_null(Fit.NODE_NAME)
	expect(fit != null and sun.get_child_count() == 0 and sun.get_child_count(true) == 1,
		"the binder gives the sun one internal shadow fit, however often it binds")
	await physics_frame
	await physics_frame

	fit._fit()
	var depths: Vector2 = fit.visible_depths(camera, 100.0)
	var fitted := sun.directional_shadow_max_distance
	expect(depths.y > 33.0 and depths.y < 41.0 and depths.x > 18.0 and depths.x < depths.y,
		"the default framing sees ground from %.1f to %.1f m deep" % [depths.x, depths.y])
	expect(fitted < 60.0 and fitted * sun.directional_shadow_fade_start
		>= depths.y * (1.0 + Fit.DEPTH_MARGIN) + Fit.DEPTH_MARGIN_METRES,
		"the distance comes in to %.0f m and fades only past the visible ground" % fitted)
	var boundary := func(ratio: float) -> float:
		return camera.near + ratio * (fitted - camera.near)
	expect(is_equal_approx(boundary.call(sun.directional_shadow_split_2), 1.0 + 0.1 * 99.0)
		and is_equal_approx(boundary.call(sun.directional_shadow_split_3), 1.0 + 0.2 * 99.0),
		"the 10 and 20 m boundaries stay where the scene's distance put them")
	expect(boundary.call(sun.directional_shadow_split_1) > camera.near
		and boundary.call(sun.directional_shadow_split_1) < 1.0 + 0.1 * 99.0,
		"the unreached 50 m boundary moves in front of the visible ground")
	expect(sun.directional_shadow_split_1 < sun.directional_shadow_split_2
		and sun.directional_shadow_split_2 < sun.directional_shadow_split_3,
		"the boundaries stay in order")
	expect(Fit.sample_points(Vector2(1280, 720)).size() == 28,
		"the frame is sampled by 28 rays, top edge to bottom edge")

	# Close in, a boundary moved in front of the ground follows the nearest
	# ground only once it changes by more than the hold: a small rise of the
	# camera leaves it, and the cascade behind it, where they were.
	_frame(camera, -60.0, 9.0)
	fit._fit()
	var held := _boundaries(sun, camera)
	camera.position += Vector3(1.2, 0.3, 0.0)
	fit._fit()
	var after := _boundaries(sun, camera)
	expect(held.size() == 3 and held[0] < 10.0 and held[1] < 10.0
		and is_equal_approx(after[0], held[0]) and is_equal_approx(after[1], held[1])
		and is_equal_approx(after[2], held[2]),
		"a small change in the nearest ground leaves the moved boundaries in place")
	_frame(camera, -60.0, 26.0)
	fit._fit()

	_frame(camera, -60.0, 60.0)
	fit._fit()
	expect(sun.directional_shadow_max_distance > fitted,
		"zooming out grows the distance in the same frame")
	_frame(camera, -15.0, 26.0)
	fit._fit()
	expect(_authored(sun, 100.0), "a view up to the horizon keeps the scene's own values")

	_frame(camera, -60.0, 26.0)
	fit._fit()
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	fit._fit()
	expect(sun.directional_shadow_max_distance < 60.0
		and is_equal_approx(camera.near + sun.directional_shadow_split_1
			* (sun.directional_shadow_max_distance - camera.near), 1.0 + 0.1 * 99.0),
		"LOW and MEDIUM's two cascades keep their 10 m boundary; the far one shrinks")
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS

	sun.directional_shadow_max_distance = 30.0
	fit._fit()
	expect(sun.directional_shadow_max_distance <= 30.0,
		"a distance something else sets is never exceeded")
	_frame(camera, -15.0, 26.0)
	fit._fit()
	expect(_authored(sun, 30.0), "and is what the fit gives back")
	sun.directional_shadow_max_distance = 100.0
	_frame(camera, -60.0, 26.0)
	fit._fit()

	var warm := Camera3D.new()
	stage.add_child(warm)
	Warmup._drawing[-1] = weakref(warm)
	fit._fit()
	expect(_authored(sun, 100.0), "a warm-up camera sees the scene's own shadow distance")
	Warmup._drawing.erase(-1)
	warm.free()
	fit._fit()
	expect(sun.directional_shadow_max_distance < 60.0, "and the fit returns after it")

	ground.collision_layer = 1
	await physics_frame
	_frame(camera, -60.0, 28.0)
	fit._fit()
	expect(_authored(sun, 100.0), "ground the fit cannot find keeps the scene's values")
	ground.collision_layer = 8
	await physics_frame
	_frame(camera, -60.0, 26.0)
	fit._fit()

	sun.shadow_enabled = false
	_frame(camera, -15.0, 26.0)
	fit._fit()
	expect(sun.directional_shadow_max_distance < 60.0, "a sun without shadows is left alone")
	sun.shadow_enabled = true
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_frame(camera, -60.0, 26.0)
	fit._fit()
	expect(_authored(sun, 100.0), "an orthogonal camera keeps the scene's values")
	camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	fit._fit()
	await _check_gorge(stage, ground, camera, sun, fit)
	await _measure_rays(stage, ground, camera, fit)
	fit.queue_free()
	await process_frame
	expect(_authored(sun, 100.0), "removing the fit gives the scene its values back")

	var previous := OS.get_environment(Fit.DISABLE_VARIABLE)
	OS.set_environment(Fit.DISABLE_VARIABLE, "0")
	var plain := DirectionalLight3D.new()
	stage.add_child(plain)
	WorldEnvironmentBinder.apply(manifest, environment, plain)
	expect(plain.get_child_count(true) == 0, "ELORIA_SHADOW_FIT=0 leaves the sun unfitted")
	OS.set_environment(Fit.DISABLE_VARIABLE, previous)
	viewport.queue_free()
	await process_frame
	print("sun shadow fit tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _frame(camera: Camera3D, pitch_degrees: float, distance: float) -> void:
	var pitch := deg_to_rad(pitch_degrees)
	camera.look_at_from_position(Vector3(0.0, -sin(pitch), cos(pitch)) * distance,
		Vector3.UP * 1.2, Vector3.UP)

func _boundaries(sun: DirectionalLight3D, camera: Camera3D) -> Array[float]:
	var result: Array[float] = []
	for ratio: float in [sun.directional_shadow_split_1, sun.directional_shadow_split_2,
			sun.directional_shadow_split_3]:
		result.append(camera.near + ratio * (sun.directional_shadow_max_distance - camera.near))
	return result

func _body(parent: Node3D, size: Vector3, centre: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = 8
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	shape.shape = box
	body.add_child(shape)
	body.position = centre
	parent.add_child(body)
	return body

## A gorge across the middle of the default view, its far side under the top
## edge: the far wall below the near rim is deeper than any ground the top
## edge meets, and its shadows must not fade.
func _check_gorge(stage: Node3D, ground: StaticBody3D, camera: Camera3D,
		sun: DirectionalLight3D, fit: Node) -> void:
	ground.collision_layer = 1
	var near_side := _body(stage, Vector3(600, 42, 303), Vector3(0, -21, 148.5))
	var far_side := _body(stage, Vector3(600, 42, 282), Vector3(0, -21, -159))
	var floor_body := _body(stage, Vector3(600, 2, 15), Vector3(0, -41, -10.5))
	await physics_frame
	await physics_frame
	_frame(camera, -60.0, 24.0)
	fit._fit()
	_frame(camera, -60.0, 26.0)
	fit._fit()
	var size := camera.get_viewport().get_visible_rect().size
	var space := camera.get_world_3d().direct_space_state
	var deepest := 0.0
	for step: int in 401:
		var depth: float = fit._depth(camera, space, Vector2(size.x * 0.5, size.y * step / 400.0), 1000.0)
		if is_finite(depth):
			deepest = maxf(deepest, depth)
	var top := 0.0
	for index: int in Fit.TOP_SAMPLES:
		top = maxf(top, fit._depth(camera, space,
			Vector2(size.x * index / float(Fit.TOP_SAMPLES - 1), 0.0), 1000.0))
	expect(top * (1.0 + Fit.DEPTH_MARGIN) + Fit.DEPTH_MARGIN_METRES < deepest,
		"the gorge's far wall (%.1f m) lies deeper than the top edge's ground (%.1f m) and its margin"
			% [deepest, top])
	expect(sun.directional_shadow_max_distance < 100.0
		and sun.directional_shadow_max_distance * sun.directional_shadow_fade_start >= deepest,
		"the fit (%.0f m) keeps unfaded shadows on all of it" % sun.directional_shadow_max_distance)
	for body: Node in [near_side, far_side, floor_body]:
		body.free()
	ground.collision_layer = 8
	await physics_frame
	await physics_frame
	_frame(camera, -60.0, 24.0)
	fit._fit()

## What one refit's rays cost against a walk-surface trimesh: informational.
func _measure_rays(stage: Node3D, ground: StaticBody3D, camera: Camera3D, fit: Node) -> void:
	ground.collision_layer = 1
	var plane := PlaneMesh.new()
	plane.size = Vector2(600, 600)
	plane.subdivide_width = 127
	plane.subdivide_depth = 127
	var body := StaticBody3D.new()
	body.collision_layer = 8
	var shape := CollisionShape3D.new()
	shape.shape = plane.create_trimesh_shape()
	body.add_child(shape)
	stage.add_child(body)
	await physics_frame
	await physics_frame
	_frame(camera, -60.0, 26.0)
	var started := Time.get_ticks_usec()
	var depths := Vector2.ZERO
	for repeat: int in 100:
		depths = fit.visible_depths(camera, 100.0)
	print("info: one refit's %d rays against a %d-triangle trimesh: %.0f us (deepest %.1f m)" % [
		Fit.sample_points(camera.get_viewport().get_visible_rect().size).size(),
		128 * 128 * 2, (Time.get_ticks_usec() - started) / 100.0, depths.y])
	body.free()
	ground.collision_layer = 8
	await physics_frame
	await physics_frame
	fit._fit()

func _authored(sun: DirectionalLight3D, distance: float) -> bool:
	return is_equal_approx(sun.directional_shadow_max_distance, distance) \
		and is_equal_approx(sun.directional_shadow_split_1, 0.1) \
		and is_equal_approx(sun.directional_shadow_split_2, 0.2) \
		and is_equal_approx(sun.directional_shadow_split_3, 0.5) \
		and is_equal_approx(sun.directional_shadow_fade_start, 0.8)

func _check_ratios() -> void:
	# HIGH at the default framing: 37 m deep, fitted to 46 m.
	var ratios := Fit.split_ratios(1.0, 100.0, 46.0, 21.0, 4, AUTHORED)
	var boundaries: Array[float] = []
	for ratio: float in ratios:
		boundaries.append(1.0 + ratio * 45.0)
	expect(boundaries[0] > 1.0 and boundaries[0] < 10.9 and is_equal_approx(boundaries[1], 10.9)
		and is_equal_approx(boundaries[2], 20.8),
		"HIGH keeps its 10.9 and 20.8 m boundaries and moves the 50.5 m one below them")
	ratios = Fit.split_ratios(1.0, 100.0, 46.0, 21.0, 2, AUTHORED)
	expect(is_equal_approx(1.0 + ratios[0] * 45.0, 10.9) and ratios[1] == 0.2 and ratios[2] == 0.5,
		"two cascades keep their boundary and leave the unused ratios alone")
	# Zoomed in: the ground from 6 to 9 m, fitted to 14 m.
	ratios = Fit.split_ratios(0.5, 100.0, 14.0, 6.0, 4, AUTHORED)
	var first := 0.5 + ratios[0] * 13.5
	var second := 0.5 + ratios[1] * 13.5
	var third := 0.5 + ratios[2] * 13.5
	expect(first < second and second < 6.0 * 0.8 + 0.001
		and is_equal_approx(third, 0.5 + 0.1 * 99.5),
		"close in, the moved boundaries split only the air before the visible ground")
	ratios = Fit.split_ratios(1.0, 100.0, 46.0, 21.0, 1, AUTHORED)
	expect(ratios[0] == 0.1 and ratios[1] == 0.2 and ratios[2] == 0.5,
		"one cascade has no boundaries to move")
	expect(Fit.held_nearest(0.0, 8.0) == 8.0 and Fit.held_nearest(8.0, 7.0) == 8.0
		and Fit.held_nearest(8.0, 9.9) == 8.0,
		"the nearest ground is held while it stays near the held value")
	expect(Fit.held_nearest(8.0, 6.0) == 6.0 and Fit.held_nearest(8.0, 10.5) == 10.5,
		"and taken anew once it leaves the hold")
	var safe := true
	for measured: float in [3.0, 6.3, 6.5, 7.9, 9.0, 10.0, 10.1, 30.0]:
		safe = safe and Fit.held_nearest(8.0, measured) * 0.8 <= measured
	expect(safe, "a held value never puts a moved boundary behind the ground in view")
