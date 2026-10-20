extends SceneTree
## Mode changes must preserve original subjects and survive streaming and
## preference migration, including Full painted -> Painted ground.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_expect(LookProfile.mode() == LookProfile.Mode.PAINTED_GROUND,
		"Painted ground is the fresh default")
	var config := ConfigFile.new()
	_expect(LookProfile.mode_from_settings(config) == LookProfile.Mode.PAINTED_GROUND,
		"missing preferences use Painted ground")
	config.set_value("graphics", "look", true)
	_expect(LookProfile.mode_from_settings(config) == LookProfile.Mode.PAINTED_GROUND,
		"old On migrates to Painted ground")
	config.set_value("graphics", "look", false)
	_expect(LookProfile.mode_from_settings(config) == LookProfile.Mode.ORIGINAL,
		"old Off preserves Original")
	for mode: int in LookProfile.MODE_NAMES.size():
		config.set_value("graphics", "appearance", LookProfile.mode_name(mode))
		_expect(LookProfile.mode_from_settings(config) == mode,
			"explicit mode round-trips: " + LookProfile.mode_name(mode))
	config.set_value("graphics", "appearance", "unrecognized")
	config.erase_section_key("graphics", "look")
	_expect(LookProfile.mode_from_settings(config) == LookProfile.MODE_DEFAULT,
		"invalid preferences recover the default")
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "ssarathi_ruins"},
		"continentGeography": {"geometryMode": "continent-chunks-v1"},
		"environment": {"sun": {"enabled": true}}}
	var world := Node3D.new()
	root.add_child(world)
	var terrain := _mesh(world, "Terrain_fixture", Color("4c7140"))
	var prop := _mesh(world, "Statue_fixture", Color("369369"))
	(prop.mesh.surface_get_material(0) as StandardMaterial3D).resource_name = "ssarathi_jade_scale"
	var creature := _mesh(world, "Creature_fixture", Color("bd6939"))
	var crown := _mesh(world, "Tree_0001_pale_birch_Canopy", Color("6b933c"))
	var water := _mesh(world, "Water_fixture", Color("2a87ad"))
	var originals := [prop.get_active_material(0), creature.get_active_material(0),
		crown.get_active_material(0), water.get_active_material(0)]
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	var sun := DirectionalLight3D.new()
	root.add_child(environment)
	root.add_child(sun)
	for mode: int in [LookProfile.Mode.FULL_PAINTED, LookProfile.Mode.PAINTED_GROUND,
			LookProfile.Mode.ORIGINAL, LookProfile.Mode.PAINTED_GROUND,
			LookProfile.Mode.FULL_PAINTED, LookProfile.Mode.PAINTED_GROUND]:
		LookProfile.set_player_mode(mode)
		LookSwitch.sync(world, manifest)
		_expect(not LookProfile.stale(world), "live switch stamps " + LookProfile.mode_name(mode))
		if mode == LookProfile.Mode.PAINTED_GROUND:
			_expect(terrain.get_active_material(0) is ShaderMaterial,
				"ground keeps the painted material")
			var subjects := [prop, creature, crown, water]
			for index: int in subjects.size():
				_expect(subjects[index].get_active_material(0) == originals[index],
					"ground mode restores original " + str(subjects[index].name))
			var before := [environment.environment.tonemap_mode,
				environment.environment.adjustment_enabled, sun.light_color, sun.light_energy]
			_expect(not LookGrade.apply(manifest, environment, sun) and before == [
				environment.environment.tonemap_mode, environment.environment.adjustment_enabled,
				sun.light_color, sun.light_energy], "ground mode leaves global light and grade untouched")
		elif mode == LookProfile.Mode.ORIGINAL:
			_expect(LookSwitch.look_surfaces(world) == 0, "Original restores all original materials")
		else:
			_expect(prop.get_active_material(0) != originals[0],
				"Full painted retains signature-prop treatment")
	# Both painted modes have enabled()==true; the generation must distinguish them.
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	_expect(LookProfile.stale(world), "a late chunk is stale across painted modes")
	LookSwitch.sync(world, manifest)
	LookProfile.set_player_mode(LookProfile.Mode.PAINTED_GROUND)
	_expect(LookProfile.stale(world), "a chunk arriving from Full painted is reconciled")
	LookSwitch.sync(world, manifest)
	_expect(prop.get_active_material(0) == originals[0], "reconciliation restores original props")
	for forced: String in ["0", "1", "painted_ground", "original", "full_painted"]:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, forced)
		_expect(LookProfile.look_forced(), "override supported: " + forced)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	world.free()
	environment.free()
	sun.free()
	print("appearance modes: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _mesh(parent: Node, node_name: String, colour: Color) -> MeshInstance3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = colour
	var mesh := MeshInstance3D.new()
	mesh.name = node_name
	var arrays := ArrayMesh.new()
	arrays.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, BoxMesh.new().get_mesh_arrays())
	mesh.mesh = arrays
	mesh.mesh.surface_set_material(0, material)
	parent.add_child(mesh)
	return mesh

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS " + message)
