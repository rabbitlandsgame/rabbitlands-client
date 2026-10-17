extends SceneTree
## Landfall's decorative paving is above its navigation surface. Verify the
## actual storage halo remains visible there and changes across rendered frames.
const PACKAGE := "res://../eloria-assets/maps/continent-v2/landfall/client/chunks/08_10/world.json"
const ARTIFACTS := "res://test-artifacts/storage-glow"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	root.get_node("Network").set_process(false)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(ARTIFACTS))
	var stage := Node3D.new()
	root.add_child(stage)
	var loader := WorldLoader.new()
	stage.add_child(loader)
	loader.load_world(ProjectSettings.globalize_path(PACKAGE))
	_expect(loader.world_root != null, "Landfall's storage plaza loads")
	if loader.world_root == null:
		quit(failures)
		return
	loader.set_process(false)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	stage.add_child(environment)
	var sun := DirectionalLight3D.new()
	stage.add_child(sun)
	WorldEnvironmentBinder.apply(loader.manifest, environment, sun)
	var camera := Camera3D.new()
	camera.fov = 50
	camera.near = 0.5
	camera.far = 1500
	camera.cull_mask = 3
	stage.add_child(camera)
	camera.current = true
	var chest := MapObject3D.new()
	stage.add_child(chest)
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world/objects.json"))
	chest.configure({"object_id": 22, "kind": EloriaProtocol.MAP_OBJECT_INTERACTIVE,
		"x": 130, "y": 229, "label": "Storage"}, loader.coordinate_adapter, catalog)
	for unused: int in range(8):
		await physics_frame
	var space := stage.get_world_3d().direct_space_state
	var ground: Variant = GroundDrape.surface_height(space, chest.position.x, chest.position.z)
	_expect(ground != null, "the chest has a navigation surface")
	if ground == null:
		quit(failures)
		return
	chest.set_surface_height(float(ground))
	chest.set_active(false)
	var target := chest.global_position + Vector3.UP * 0.5
	camera.look_at_from_position(target + Vector3(2.6, 4.8, 4.2), target)
	var glow := chest.get_node("StorageGlow") as MeshInstance3D
	var sparks := chest.get_node("StorageSparks") as GPUParticles3D
	sparks.hide()
	glow.hide()
	var baseline := await _capture()
	glow.show()
	var visible := await _capture()
	await create_timer(0.85).timeout
	var animated := await _capture()
	await create_timer(0.85).timeout
	var later := await _capture()
	# Stay on the paving around the chest, away from animated water and foliage.
	var centre := Vector2i(camera.unproject_position(chest.global_position))
	var area := Rect2i(centre - Vector2i(210, 140), Vector2i(420, 280))
	var halo_pixels := _changed_pixels(baseline, visible, area)
	var animated_pixels := maxi(_changed_pixels(visible, animated, area),
		_changed_pixels(visible, later, area))
	_expect(halo_pixels > 500, "the paving does not hide the halo (%d pixels)" % halo_pixels)
	_expect(animated_pixels > 200, "the visible halo animates (%d pixels)" % animated_pixels)
	# Follow the player towards and past storage at the normal and maximum
	# camera zooms. Transparent paving used to sort over the whole halo here.
	var close_camera := camera.transform
	var minimum_approach_pixels := 1000000
	for distance: float in [26.0, 90.0]:
		for offset: float in [-3.0, 0.0, 3.0]:
			var feet := chest.global_position + Vector3(0, 0, offset)
			camera.look_at_from_position(feet + Vector3(0, 0.866, 0.5) * distance,
				feet + Vector3.UP * 1.2)
			glow.hide()
			var without := await _capture()
			glow.show()
			var with_halo := await _capture()
			var pixels := _changed_pixels(without, with_halo, _halo_area(camera, chest))
			minimum_approach_pixels = mini(minimum_approach_pixels, pixels)
			_expect(pixels > (200 if distance < 90.0 else 40),
				"the halo stays visible at zoom %.0f, approach %.0f (%d pixels)" % [distance, offset, pixels])
	camera.transform = close_camera
	glow.hide()
	var no_particles := await _capture()
	sparks.show()
	var minimum_spark_pixels := 1000000
	var previous_particles: Image
	for sample: int in range(4):
		await create_timer(0.6).timeout
		var particles := await _capture()
		var pixels := _changed_pixels(no_particles, particles, area)
		minimum_spark_pixels = mini(minimum_spark_pixels, pixels)
		_expect(pixels > 100, "edge particles remain visible across a loop (%d pixels)" % pixels)
		if previous_particles != null:
			_expect(_changed_pixels(previous_particles, particles, area) > 100,
				"the edge particles keep moving")
		previous_particles = particles
	chest.set_particles_enabled(false)
	var disabled := await _capture()
	_expect(_changed_pixels(no_particles, disabled, area) < 20,
		"disabling particles immediately hides the motes")
	chest.set_particles_enabled(true)
	glow.show()
	await create_timer(0.4).timeout
	var combined := await _capture()
	combined.save_png(ARTIFACTS.path_join("storage-edge-particles.png"))
	var pick := chest.get_node("PickShape") as CollisionShape3D
	var ray := PhysicsRayQueryParameters3D.create(camera.global_position,
		chest.to_global(pick.position), MapObject3D.PICK_LAYER)
	_expect(MapObject3D.from_pick_collider(space.intersect_ray(ray).get("collider")) == chest,
		"the chest remains clickable")
	baseline.save_png(ARTIFACTS.path_join("storage-without-glow.png"))
	visible.save_png(ARTIFACTS.path_join("storage-glow-visible.png"))
	animated.save_png(ARTIFACTS.path_join("storage-glow-animated.png"))
	print("storage glow: visible_pixels=%d animated_pixels=%d approach_min=%d sparks_min=%d failures=%d" % [
		halo_pixels, animated_pixels, minimum_approach_pixels, minimum_spark_pixels, failures])
	stage.queue_free()
	await process_frame
	quit(failures)

func _capture() -> Image:
	for unused: int in range(8):
		await process_frame
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()

func _changed_pixels(first: Image, second: Image, area: Rect2i) -> int:
	var count := 0
	for y: int in range(area.position.y, area.end.y):
		for x: int in range(area.position.x, area.end.x):
			var delta := first.get_pixel(x, y) - second.get_pixel(x, y)
			if maxf(absf(delta.r), maxf(absf(delta.g), absf(delta.b))) > 0.015:
				count += 1
	return count

func _halo_area(camera: Camera3D, chest: Node3D) -> Rect2i:
	var centre := camera.unproject_position(chest.global_position)
	var edge := camera.unproject_position(chest.global_position + camera.global_basis.x * 1.6)
	var radius := ceili(centre.distance_to(edge)) + 8
	return Rect2i(Vector2i(centre) - Vector2i.ONE * radius,
		Vector2i.ONE * radius * 2).intersection(Rect2i(Vector2i.ZERO, root.size))

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
