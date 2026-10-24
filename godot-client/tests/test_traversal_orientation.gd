extends SceneTree
## Exercise live imported bodies and saddle fitting on uphill/downhill/crosshill
## contacts, without adding a terrain sampler or altering authoritative motion.
var checks := 0
var failures := 0
var models: Dictionary
var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func make_actor(id: int) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var config: Dictionary = models.luminous_male
	var errors := actor.configure({"actor_id": id, "x": 0, "y": 0,
		"rotation": 0, "kind": 1, "name": "SlopeTest"}, adapter, config,
		JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)))
	expect(errors.is_empty(), "actual player loads: " + str(errors))
	actor.set_process(false)
	actor.set_physics_process(false)
	actor._physics_process(0.0)
	return actor

func finish_tilt(actor: ReplicatedActor3D) -> void:
	for frame: int in 60:
		actor._physics_process(1.0 / 60.0)

func run() -> void:
	models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var normal := Vector3(-0.4, 1.0, 0.3).normalized()
	var actor := make_actor(7001)
	var native := actor.get_node("NativeModel") as Node3D
	var rest := native.transform
	var authority := actor.global_transform
	actor.set_surface_height(actor.server_target.y, normal)
	actor._physics_process(1.0 / 60.0)
	var first_up := native.global_basis.orthonormalized().y
	expect(first_up.angle_to(Vector3.UP) > 0.0 and first_up.angle_to(Vector3.UP) < normal.angle_to(Vector3.UP) * 0.35,
		"a new slope eases in without snapping even at the same height")
	finish_tilt(actor)
	expect(absf(native.global_basis.orthonormalized().y.angle_to(Vector3.UP) - normal.angle_to(Vector3.UP) * 0.35) < 0.001,
		"on-foot players lean gently with the traversal surface")
	expect(actor.global_transform.is_equal_approx(authority), "surface lean leaves actor, collision and camera frame upright")
	expect(not actor.is_physics_processing(), "stationary slope alignment returns to idle physics")
	actor.set_surface_height(actor.server_target.y, normal)
	expect(not actor.is_physics_processing(), "an unchanged contact does not wake a settled actor")
	actor.set_server_scale(1.4)
	expect(absf(native.scale.x - actor._import_scale * 1.4) < 0.00001, "scale changes retain uniform import scale on slopes")
	actor.play_action(&"run")
	finish_tilt(actor)
	actor.play_action(&"idle")
	finish_tilt(actor)
	expect(absf(native.global_basis.orthonormalized().y.angle_to(Vector3.UP) - normal.angle_to(Vector3.UP) * 0.35) < 0.001,
		"walk/run facing corrections do not overwrite terrain lean")
	actor.set_server_scale(1.0)
	actor.set_surface_height(actor.server_target.y)
	finish_tilt(actor)
	expect(native.transform.is_equal_approx(rest), "returning to level ground restores the exact imported transform")

	for mount_id: String in preload("res://src/mounts/mount_profiles.gd").PATHS:
		actor.set_surface_height(actor.server_target.y, normal)
		finish_tilt(actor)
		actor.set_mount_state({"mode": "mounted", "mount_id": mount_id, "gait": "cruise", "step_us": 133333}, models)
		var visual = actor._mount_visual
		expect(is_instance_valid(visual), mount_id + " mounts on a slope")
		if not is_instance_valid(visual):
			continue
		visual.set_process(false)
		visual._step_visual(0.0)
		var rider_in_mount: Transform3D = visual.global_transform.affine_inverse() * native.global_transform
		actor.set_surface_height(actor.server_target.y, Vector3(0.2, 1, -0.4).normalized())
		actor._physics_process(1.0 / 60.0)
		expect((visual.global_transform.affine_inverse() * native.global_transform).is_equal_approx(rider_in_mount),
			"rider follows mount tilt even between gated skeleton samples")
		actor.set_surface_height(actor.server_target.y, normal)
		finish_tilt(actor)
		for yaw: float in [0.0, PI / 2.0, PI, -PI / 2.0]:
			actor._target_yaw = yaw
			actor._wake()
			finish_tilt(actor)
			visual._step_visual(0.0)
			expect(visual.global_basis.y.is_equal_approx(normal), mount_id + " matches uphill, downhill and crosshill normal")
			expect(actor.global_basis.y.is_equal_approx(Vector3.UP), "authoritative root remains upright when turning on slopes")
			for key: String in visual.pose.last_errors:
				expect(float(visual.pose.last_errors[key]) < 0.06, mount_id + " keeps rider contact on slopes: " + key)
		var before: Basis = visual.global_basis
		var rebase := Transform3D(Basis(Vector3.UP, 0.7), Vector3(12.0, 3.0, -2.0))
		actor.rebase_world(rebase)
		expect(visual.global_basis.is_equal_approx(rebase.basis * before), "map rebasing preserves world-relative slope alignment")
		actor.rebase_world(rebase.affine_inverse())
		actor.set_mount_state({}, models)
		expect(absf(native.global_basis.orthonormalized().y.angle_to(Vector3.UP) - normal.angle_to(Vector3.UP) * 0.35) < 0.001,
			"dismount immediately restores on-foot slope lean")
		actor.set_mount_state({"mode": "mounted", "mount_id": mount_id, "gait": "walk"}, models)
		actor._mount_visual.set_process(false)
		actor.set_surface_height(actor.server_target.y, Vector3(1, 0.001, 0))
		finish_tilt(actor)
		expect(actor._mount_visual.global_basis.y.angle_to(Vector3.UP) <= PI / 4.0 + 0.001,
			"steep facets cannot tip a mount beyond the safety angle")
		for invalid: Vector3 in [Vector3.ZERO, Vector3.DOWN, Vector3(NAN, 1, 0), Vector3(INF, 1, 0)]:
			actor.set_surface_height(actor.server_target.y, invalid)
			finish_tilt(actor)
			expect(actor._mount_visual.basis.is_equal_approx(Basis.IDENTITY), "invalid contacts recover to a finite upright mount")
		actor.set_mount_state({}, models)
		actor._target_yaw = 0.0
		finish_tilt(actor)

	actor.set_surface_height(actor.server_target.y, normal)
	finish_tilt(actor)
	var replacement := make_actor(7001)
	replacement.adopt_presentation_from(actor)
	expect(replacement._surface_up.is_equal_approx(normal), "deferred model replacement preserves the current surface orientation")
	finish_tilt(replacement)
	expect(not replacement.is_physics_processing(), "replacement on a slope settles normally")
	var route := PackedVector3Array([actor.global_position, actor.global_position + Vector3(2, 0.2, 0)])
	actor.begin_charge_leap(route, 0.5)
	actor._physics_process(0.2)
	expect(native.global_basis.orthonormalized().y.is_equal_approx(Vector3.UP), "ground lean eases out during an airborne charge")
	actor.end_charge_leap()
	finish_tilt(actor)
	expect(absf(native.global_basis.orthonormalized().y.angle_to(Vector3.UP) - normal.angle_to(Vector3.UP) * 0.35) < 0.001,
		"landing restores the sampled slope lean")
	await sampler_checks(actor)

	for fixture: ReplicatedActor3D in [actor, replacement]:
		fixture.process_mode = Node.PROCESS_MODE_DISABLED
	await physics_frame
	await process_frame
	actor.queue_free()
	replacement.queue_free()
	await process_frame
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("TRAVERSAL_ORIENTATION_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)

func sampler_checks(actor: ReplicatedActor3D) -> void:
	# Use Main's real cached ray path against a tilted traversal deck. Keeping
	# Main outside the tree avoids booting UI/network/streaming for this test.
	var main = load("res://src/app/main.gd").new()
	main.gameplay_world = root.get_world_3d()
	main.adapter = adapter
	main._local_placement_logged = true
	var floor := StaticBody3D.new()
	floor.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(10, 0.2, 10)
	shape.shape = box
	floor.add_child(shape)
	floor.rotation.z = 0.3
	root.add_child(floor)
	actor.server_target = Vector3.ZERO
	await physics_frame
	await physics_frame
	main._place_actor_on_surface(actor, true)
	expect(actor._surface_target_up.is_equal_approx(floor.global_basis.y), "existing placement ray supplies the traversal normal")
	var cached := actor._surface_target_up
	floor.rotation.z = -0.3
	await physics_frame
	await physics_frame
	main._place_actor_on_surface(actor)
	expect(actor._surface_target_up.is_equal_approx(cached), "unchanged actor tile reuses its cached ray contact")
	main._place_actor_on_surface(actor, true)
	expect(actor._surface_target_up.is_equal_approx(floor.global_basis.y), "forced terrain refresh updates normal as well as height")
	floor.collision_layer = ExteriorRegionStream.PREVIEW_SURFACE_LAYER
	floor.rotation.z = 0.2
	await physics_frame
	await physics_frame
	main._place_actor_on_surface(actor, true)
	expect(actor._surface_target_up.is_equal_approx(floor.global_basis.y), "preview terrain supplies its normal during a map seam crossing")
	var last_normal := actor._surface_target_up
	floor.free()
	await physics_frame
	await physics_frame
	main._place_actor_on_surface(actor, true)
	expect(actor._surface_target_up.is_equal_approx(last_normal), "a transient terrain miss preserves the last grounded orientation")
	if is_instance_valid(main.mount_status):
		main.mount_status.add_child(main.mount_status.status)
	# Main normally parents these presentation helpers in _ready. This sampler
	# fixture never enters the tree, so give its owned Nodes a cleanup parent.
	for property: Dictionary in main.get_property_list():
		var value: Variant = main.get(property.name)
		if value is Node and (value as Node).get_parent() == null:
			main.add_child(value as Node)
	main.free()
