extends SceneTree

const Surface := preload("res://src/audio/footstep_surface.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	await _test_surfaces()
	_test_playback()
	await process_frame
	print("footstep tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _test_surfaces() -> void:
	var labels := {
		"terrain_grass": "grass", "forest_floor_ground": "grass",
		"ground_open_steppe": "grass", "packed_earth_ground": "dirt",
		"ground_caravan_road": "dirt", "cobble_paving_ground": "stone",
		"pale_ashlar_ground": "stone", "glacier_ice_ground": "stone",
		"sunmane_red_sandstone": "stone", "verdant_mossy_stone": "stone",
		"manymouth_bamboo": "wood", "manymouth_teak": "wood",
		"westhaven_sett_ground": "stone", "crownwater_mosaic": "stone",
		"verdant_jungle_floor_ground": "grass",
		"timber_warm": "wood", "ground_beach_sand": "sand",
		"snow_pack_ground": "snow", "unlabelled": "dirt",
	}
	for label: String in labels:
		_expect(Surface.from_name(label) == labels[label], "classify " + label)
	_expect(Surface.from_hit({}) == "dirt", "missing terrain has a gentle fallback")
	var world := Node3D.new()
	root.add_child(world)
	var loader := WorldLoader.new()
	world.add_child(loader)
	var mesh := ArrayMesh.new()
	var materials := ["meadow_grass_ground", "paving_road", "timber_grey",
		"terrain_sand", "snow_pack", "terrain_soil"]
	for index: int in materials.size():
		var arrays: Array = []
		arrays.resize(Mesh.ARRAY_MAX)
		var x := float(index * 3)
		var vertices := PackedVector3Array([
			Vector3(x, 0, -1), Vector3(x + 2, 0, 1), Vector3(x, 0, 1),
			Vector3(x, 0, -1), Vector3(x + 2, 0, -1), Vector3(x + 2, 0, 1)])
		arrays[Mesh.ARRAY_VERTEX] = vertices
		if index % 2 == 0:
			arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 3, 4, 5])
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var material := StandardMaterial3D.new()
		material.resource_name = materials[index]
		mesh.surface_set_material(index, material)
	var terrain := MeshInstance3D.new()
	terrain.name = "Terrain_Mixed"
	terrain.mesh = mesh
	world.add_child(terrain)
	loader._create_static_collision(terrain, WorldLoader.NAVIGATION_SURFACE_LAYER)
	await physics_frame
	await process_frame
	var space := world.get_world_3d().direct_space_state
	var surfaces := ["grass", "stone", "wood", "sand", "snow", "dirt"]
	for index: int in surfaces.size():
		_expect(Surface.at_position(space, Vector3(index * 3 + 1, 0, 0)) == surfaces[index],
			"ray resolves the actual material in a mesh with multiple surfaces: " + surfaces[index])
	_expect(Surface.at_position(space, Vector3(100, 0, 100)) == "dirt", "ray miss fallback")
	# Navigation proxies can sit just above the material-bearing mesh.
	var proxy := StaticBody3D.new()
	proxy.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	var shape := CollisionShape3D.new()
	shape.name = "Nav_plaza"
	shape.shape = BoxShape3D.new()
	(shape.shape as BoxShape3D).size = Vector3(2, 0.1, 2)
	proxy.add_child(shape)
	world.add_child(proxy)
	proxy.position = Vector3(1, 0.15, 0)
	await physics_frame
	await process_frame
	_expect(Surface.at_position(space, Vector3(1, 0, 0)) == "grass",
		"thin navigation proxy uses the rendered material just below it")
	proxy.position.y = 4.0
	await physics_frame
	await process_frame
	_expect(Surface.at_position(space, Vector3(1, 0, 0)) == "stone",
		"an elevated platform never borrows terrain far below it")
	world.queue_free()
	await process_frame

func _test_playback() -> void:
	var state := root.get_node("AppState")
	var director: Node = (load("res://src/audio/audio_director.gd") as GDScript).new()
	root.add_child(director)
	director.surface_at_tile = func(tile: Vector2i) -> String:
		return "wood" if tile.x < 10 else "sand"
	state.set("local_actor_id", 91)
	state.set("actors", {91: {"x": 2, "y": 4}})
	director._on_local_actor_moved()
	_expect(not director.is_playing(), "spawn is silent")
	_move(state, director, 3)
	var voice := _last_voice(director)
	_expect("footstep_wood_" in voice.stream.resource_path, "step uses the ground at its tile")
	_expect(voice.volume_db < linear_to_db(director.volume_linear) - 9.0,
		"footsteps sit at least 9 dB below ordinary effects")
	_expect(voice.pitch_scale >= 0.97 and voice.pitch_scale <= 1.03, "pitch variation stays subtle")
	var previous := voice.stream
	director.volume_linear = 0.5
	_expect(voice.volume_db < linear_to_db(0.5) - 9.0, "changing volume preserves the quiet footstep mix")
	director.stop_all()
	_move(state, director, 3)
	_expect(not director.is_playing(), "repeated actor snapshot stays silent")
	_move(state, director, 4)
	_expect(not director.is_playing(), "rapid run packets do not pile up impacts")
	director.set("_last_step_msec", -director.STEP_INTERVAL_MSEC)
	_move(state, director, 5)
	_expect(_last_voice(director).stream != previous, "consecutive steps do not repeat the same take")
	director.stop_all()
	director.set("_last_step_msec", -director.STEP_INTERVAL_MSEC)
	_move(state, director, 30)
	_expect(not director.is_playing(), "teleport is silent")
	_move(state, director, 31)
	_expect("footstep_sand_" in _last_voice(director).stream.resource_path, "surface changes with the next step")
	director.stop_all()
	state.emit_signal("state_changed", &"map")
	_move(state, director, 32)
	_expect(not director.is_playing(), "first tile after map change is silent")
	director.enabled = false
	_move(state, director, 33)
	_expect(not director.is_playing(), "disabled audio suppresses footsteps")
	director.enabled = true
	director.surface_at_tile = func(_tile: Vector2i) -> String: return "unknown"
	_move(state, director, 34)
	_expect(_last_voice(director).stream.resource_path.ends_with("/footstep.wav"), "unknown surface uses a soft fallback")
	# Cycle back to the footstep voice; pitch and per-sound gain must not leak.
	for index: int in director.VOICE_COUNT:
		director.play("ui_click")
	voice = _last_voice(director)
	_expect(is_equal_approx(voice.pitch_scale, 1.0)
		and is_equal_approx(voice.volume_db, linear_to_db(0.5)), "ordinary effects retain their pitch and volume")
	director.free()

func _move(state: Node, director: Node, x: int) -> void:
	state.set("actors", {91: {"x": x, "y": 4}})
	director._on_local_actor_moved()

func _last_voice(director: Node) -> AudioStreamPlayer:
	var voices: Array = director.get("_voices")
	return voices[(int(director.get("_next_voice")) + voices.size() - 1) % voices.size()]

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
