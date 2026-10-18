extends SceneTree
## Guards the streamed maps' lamps (NightLamps).
##
## The Landfall isles place about a hundred lantern posts, lamp buoys and two
## lighthouses, and none of them gave light. A streamed cell is read as it
## arrives and every lamp in it is found by its model's name; each gets a halo,
## and a small pool of real lights goes to the lamps nearest the camera's
## focus. All of it follows the server's clock.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# Names: the model's own, and the glTF import's unique-name suffix.
	_expect(NightLamps.kind_of("kit-lantern-post-1") == "kit-lantern-post-1"
		and NightLamps.kind_of("kit-lantern-post-12") == "kit-lantern-post-1"
		and NightLamps.kind_of("kit-sw-lighthouse-green") == "kit-sw-lighthouse-green",
		"a lamp is known by its model's name, with or without the import's number")
	_expect(NightLamps.kind_of("kit-vineyard-rows-1-light").is_empty()
		and NightLamps.kind_of("Authored_sw_isle_kit_lantern_post_1_001").is_empty()
		and NightLamps.kind_of("kit-lantern-post-1-wall").is_empty(),
		"a vineyard, a placement wrapper or another model is not a lamp")

	# The hour.
	_expect(is_zero_approx(NightLamps.strength_at(180.0, 0.0)),
		"no lamp burns at noon")
	_expect(is_equal_approx(NightLamps.strength_at(0.0, 0.0), 1.0),
		"every lamp burns at midnight")
	var dusk := NightLamps.strength_at(285.0, 0.0)
	_expect(dusk > 0.2 and dusk < 0.9, "at dusk they are coming up: %.2f" % dusk)
	_expect(is_equal_approx(NightLamps.strength_at(180.0, 1.0), NightLamps.STORM_LAMPS),
		"a full storm lights them a little at noon")

	# A streamed territory with one cell: two posts in the plaza, one out on
	# the edge of the lights' reach and a lighthouse far beyond it.
	var stream := ContinentChunkStream.new()
	root.add_child(stream)
	var cell := Node3D.new()
	cell.name = "cell_01_02"
	cell.position = Vector3(100.0, 0.0, 0.0)
	stream.add_child(cell)
	var near := _place(cell, "kit-lantern-post-1", Vector3(2.0, 10.0, 0.0), PI * 0.5)
	_place(cell, "kit-lantern-post-12", Vector3(6.0, 10.0, 4.0), 0.0)
	_place(cell, "kit-lantern-post-13", Vector3(55.0, 10.0, 0.0), 0.0)
	_place(cell, "kit-sw-lighthouse-red", Vector3(400.0, 10.0, 0.0), 0.0)
	_place(cell, "kit-vineyard-rows-1-light", Vector3(8.0, 10.0, 0.0), 0.0)
	stream.cells["01_02"] = {"root": cell}

	var lamps := NightLamps.new()
	root.add_child(lamps)
	lamps.watch(stream)
	_expect(lamps.lamp_count() == 4, "the cell's four lamps are found: %d" % lamps.lamp_count())
	var halos := cell.get_node_or_null("LampHalos") as MultiMeshInstance3D
	_expect(halos != null and halos.multimesh.instance_count == 4,
		"the cell draws its lamps' halos as one MultiMesh")
	# The headless renderer keeps no instance transforms, so the flame is read
	# where the halo and the light both take it from.
	var expected := near.global_transform * (NightLamps.LAMPS["kit-lantern-post-1"].anchor as Vector3)
	_expect(NightLamps.flame_of(near, "kit-lantern-post-1").is_equal_approx(expected)
		and expected.is_equal_approx(Vector3(102.0, 11.62, 0.565)),
		"a lamp's flame is its model's anchor, turned with its post: %s" % expected)

	var focus := Vector3(104.0, 10.0, 0.0)
	_tick(lamps, focus, 180.0)
	_expect(lamps.lit_count() == 0 and not halos.visible,
		"at noon no lamp has a light and no halo is drawn")
	_tick(lamps, focus, 0.0)
	_expect(lamps.lit_count() == 3 and halos.visible,
		"at midnight the three lamps in reach get a light, the far one only its halo: %d"
			% lamps.lit_count())
	var energies: Array[float] = []
	for light: Node in lamps.get_children():
		if light is OmniLight3D and (light as OmniLight3D).visible:
			energies.append((light as OmniLight3D).light_energy)
			_expect(not (light as OmniLight3D).shadow_enabled, "no lamp light casts a shadow")
	var nearest_light := lamps.get_node_or_null("LampLight0") as OmniLight3D
	_expect(nearest_light != null and nearest_light.global_position.is_equal_approx(expected),
		"the nearest lamp's light burns at its flame")
	_expect(energies.size() == 3 and energies[0] > energies[2],
		"the farthest light is faded towards the edge of its reach: %s" % [energies])

	# The budget is the graphics quality's.
	for index: int in 20:
		_place(cell, "kit-lantern-post-1%d" % (index + 4), Vector3(4.0 + index, 10.0, 2.0), 0.0)
	stream.cell_ready.emit("01_02", cell)
	_expect(lamps.lamp_count() == 24 and (cell.get_node_or_null("LampHalos") as MultiMeshInstance3D) != null,
		"a cell read again is counted once")
	var previous := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.set_environment(LookProfile.QUALITY_VARIABLE, "high")
	_tick(lamps, focus, 0.0)
	_expect(lamps.lit_count() == NightLamps.LIGHTS_BY_QUALITY[LookProfile.Quality.HIGH],
		"high quality lights %d lamps" % lamps.lit_count())
	OS.set_environment(LookProfile.QUALITY_VARIABLE, "low")
	_tick(lamps, focus, 0.0)
	_expect(lamps.lit_count() == NightLamps.LIGHTS_BY_QUALITY[LookProfile.Quality.LOW],
		"low quality lights %d lamps" % lamps.lit_count())
	if previous.is_empty():
		OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	else:
		OS.set_environment(LookProfile.QUALITY_VARIABLE, previous)

	# A map whose hour does not drive its light puts every lamp out.
	lamps.update(focus, 0.0, 0.0, false)
	lamps.set("_refresh_at", 0.0)
	lamps.update(focus, 0.0, 0.0, false)
	_expect(lamps.lit_count() == 0, "a map the hour does not drive keeps its lamps dark")

	# The cell streams out: its lamps go with it.
	stream.cell_retiring.emit("01_02", cell)
	await process_frame
	_tick(lamps, focus, 0.0)
	_expect(lamps.lamp_count() == 0 and lamps.lit_count() == 0
		and cell.get_node_or_null("LampHalos") == null,
		"a retired cell takes its lamps, halos and lights with it")

	# The territory is freed (the map was left): nothing is held on to.
	stream.cell_ready.emit("01_02", cell)
	_expect(lamps.lamp_count() == 24, "the cell back again brings its lamps back")
	stream.queue_free()
	await process_frame
	_tick(lamps, focus, 0.0)
	_expect(lamps.lamp_count() == 0 and lamps.lit_count() == 0,
		"a freed territory's lamps are let go")

	lamps.queue_free()
	await process_frame
	print("night lamps tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

## A placement as the chunk GLBs carry it: a wrapper holding the model.
func _place(cell: Node3D, model: String, at: Vector3, yaw: float) -> Node3D:
	var wrapper := Node3D.new()
	wrapper.name = "Authored_%s_%d" % [model.replace("-", "_"), cell.get_child_count()]
	wrapper.position = at
	wrapper.rotation.y = yaw
	cell.add_child(wrapper)
	var lamp := MeshInstance3D.new()
	lamp.name = model
	wrapper.add_child(lamp)
	return lamp

func _tick(lamps: NightLamps, focus: Vector3, minute: float) -> void:
	lamps.set("_refresh_at", 0.0)
	lamps.update(focus, minute, 0.0)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
