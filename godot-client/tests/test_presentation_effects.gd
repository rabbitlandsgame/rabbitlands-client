extends SceneTree
## Guards the map-wide mist and gulls a package declares under
## `environment.presentation` (PresentationEffects).
##
## Nothing read the presentation block. The reader takes the map-wide form
## only: an entry that names zones (every Nymara one) names areas the manifest
## gives no geometry for, and is left alone rather than guessed at.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_expect(is_equal_approx(PresentationEffects._density({"enabled": true, "density": 0.4}), 0.4)
		and is_equal_approx(PresentationEffects._density({"enabled": true}), 1.0),
		"a map-wide entry is read at its density")
	_expect(is_zero_approx(PresentationEffects._density({"enabled": false, "density": 0.9}))
		and is_zero_approx(PresentationEffects._density({"enabled": true, "zones": ["coast"]}))
		and is_zero_approx(PresentationEffects._density(null)),
		"a disabled, zoned or missing entry draws nothing")
	_expect(is_zero_approx(PresentationEffects.mist_strength(180.0, 0.0))
		and is_equal_approx(PresentationEffects.mist_strength(0.0, 0.0), 1.0)
		and PresentationEffects.mist_strength(180.0, 1.0) > 0.5,
		"mist lies at night and in rain, not on a clear noon")
	_expect(is_equal_approx(PresentationEffects.gull_strength(180.0, 0.0), 1.0)
		and is_zero_approx(PresentationEffects.gull_strength(0.0, 0.0))
		and is_zero_approx(PresentationEffects.gull_strength(180.0, 1.0)),
		"gulls fly by day and keep off at night and in a storm")

	var effects := PresentationEffects.new()
	root.add_child(effects)
	var coast := WorldManifest.new()
	coast.data = {"environment": {"presentation": {
		"mist": {"enabled": true, "density": 0.5},
		"gulls": {"enabled": true, "density": 1.0}}}}
	effects.bind(coast)
	var mist := effects.get_node_or_null("Mist") as GPUParticles3D
	var gulls := effects.get_node_or_null("Gulls") as MultiMeshInstance3D
	_expect(mist != null and gulls != null and mist.emitting,
		"a coast that declares both gets a mist and a flock")
	var focus := Vector3(10.0, 30.0, -5.0)
	var haze := Color(0.3, 0.35, 0.45)
	effects.update(focus, 0.0, 0.0, haze, 0.1)
	_expect(mist.visible and mist.global_position.distance_to(focus) < 3.0,
		"at night the mist is drawn round the camera's focus")
	var drawn := (mist.draw_pass_1 as QuadMesh).material as StandardMaterial3D
	_expect(is_equal_approx(drawn.albedo_color.r, haze.r * PresentationEffects.MIST_SHADE)
		and drawn.albedo_color.a > 0.0,
		"in the haze's own colour")
	effects.update(focus, 0.0, 0.0, haze, 0.1, false)
	_expect(not mist.visible, "the particle switch takes the mist away")
	for frame: int in 40:
		effects.update(focus, 180.0, 0.0, haze, 0.25)
	_expect(not mist.visible and gulls.visible and gulls.multimesh.visible_instance_count > 0,
		"at noon the mist has gone and the gulls are out")
	# The headless renderer keeps no instance transforms; the flight is read
	# where the flock takes it from.
	var paths := effects.gull_paths()
	var ok := paths.size() == PresentationEffects.GULLS_MAX
	for path: Dictionary in paths:
		for time: float in [0.0, 7.5, 30.0]:
			var flight := PresentationEffects.gull_transform(path, time, focus)
			var bird := flight.origin
			ok = ok and bird.y > focus.y + PresentationEffects.GULL_HEIGHT.x - 1.5 \
				and Vector2(bird.x - focus.x, bird.z - focus.z).length() <= PresentationEffects.GULL_RADIUS.y + 0.01 \
				and (-flight.basis.z).dot(bird - focus) < 0.2 * (bird - focus).length()
	_expect(ok, "every gull wheels above and around the focus, flying along its circle")

	var zoned := WorldManifest.new()
	zoned.data = {"environment": {"presentation": {
		"mist": {"enabled": true, "zones": ["mill-pool"]},
		"gulls": {"enabled": true, "density": 0.8, "zones": ["harbour"]}}}}
	effects.bind(zoned)
	effects.update(focus, 0.0, 0.0, haze, 0.1)
	_expect(not mist.visible and not gulls.visible,
		"a map whose entries are zoned (Nymara's) gets nothing until zones have a reader")
	effects.bind(null)
	effects.update(focus, 0.0, 0.0, haze, 0.1)
	_expect(not mist.visible and not gulls.visible, "no manifest, no effects")

	effects.queue_free()
	await process_frame
	print("presentation effects tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
