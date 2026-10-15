extends SceneTree
## Actual Camera3D projection, without a map, network session or GPU render.
const Walk := preload("res://tests/integration/rendered_landscape_walk.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(1440, 900)
	root.add_child(viewport)
	var rig := IsometricCameraController.new()
	var camera := Camera3D.new()
	camera.name = "Camera"
	camera.fov = 50.0
	rig.add_child(camera)
	camera.owner = rig
	camera.unique_name_in_owner = true
	viewport.add_child(rig)
	var focus := Vector3(-148.5, 3.159987, -281.5)
	rig.set_focus(focus)
	var stale := camera.global_transform
	var route := {"yaw": 90.0, "distance": 32.0, "start": [28, 401],
		"steps": [{"tile": [391, 5], "clickNeighbor": true, "expectRun": false}]}
	var original := route.duplicate(true)
	Walk._configure_route_camera(rig, route)
	_expect(camera.global_transform != stale, "route setup replaces the old camera pose synchronously")
	_expect(camera.global_position.distance_to(Vector3(-132.5, 30.8728, -281.5)) < .001,
		"first click uses the requested yaw and zoom before another frame")
	_expect(rig.focus == focus and route == original, "camera setup preserves focus, targets and click intent")
	# Exact emitted Grey road point, expressed in the resident Manymouth frame.
	var point := Vector3(-168.9, 6.635544, -281.1)
	var screen := camera.unproject_position(point)
	_expect(screen.y < 0 and absf(screen.y + 4.754376) < .05,
		"old32m framing reproduces the actual above-viewport failure")
	route.distance = 40.0
	Walk._configure_route_camera(rig, route)
	screen = camera.unproject_position(point)
	_expect(screen.y > 70.0 and screen.y < 71.0 and screen.x > 700 and screen.x < 730,
		"normal40m zoom gives the unchanged raised target a70px visible margin")
	_expect(not camera.is_position_behind(point), "visible target remains in front of the real camera")
	_expect(rig.focus == focus and route.steps == original.steps,
		"zoom repair changes no movement endpoint or run intent")
	var applied := camera.global_transform
	Walk._configure_route_camera(rig, route)
	_expect(camera.global_transform == applied, "reapplying an authored pose is deterministic")
	Walk._configure_route_camera(rig, {"yaw": 180.0, "distance": 26.0})
	_expect(camera.global_position.distance_to(focus + Vector3(0, 22.5166605, -13)) < .001,
		"a subsequent route also applies a different direction and zoom immediately")
	print("Landscape camera harness: ", "PASS" if failures == 0 else "FAIL")
	viewport.queue_free()
	await process_frame
	quit(failures)

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
