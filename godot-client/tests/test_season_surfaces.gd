extends SceneTree

const Surfaces = preload("res://src/world/season_surfaces.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": "amberwood__chunk_01_02"},
		"continentGeography": {}, "environment": {"sun": {"enabled": true}}}
	var warm := WorldManifest.new()
	warm.data = {"asset": {"id": "verdant_stair"}, "environment": {"sun": {"enabled": true}}}
	var inside := WorldManifest.new()
	inside.data = {"environment": {"sun": {"enabled": false}}}
	_expect(Surfaces.snow_cover(manifest) == 1.0 and Surfaces.snow_cover(warm) == 0.0
		and Surfaces.snow_cover(inside) == 0.0, "snow respects outdoor and warm climates")
	var green := StandardMaterial3D.new()
	green.resource_name = "leaf_atlas"
	green.albedo_color = Color(0.2, 0.5, 0.1)
	green.roughness = 0.72
	_expect(Surfaces.kind_of("kit-oak-tree", green) == Surfaces.Kind.LEAVES, "oak is deciduous")
	_expect(Surfaces.kind_of("kit-pine-tree", green) == Surfaces.Kind.EVERGREEN, "pine keeps its needles")
	_expect(Surfaces.kind_of("Tree_oak_Wood", green) == Surfaces.Kind.NONE, "bark is excluded")
	_expect(Surfaces.kind_of("kit-flower-shrub", green) == Surfaces.Kind.NONE, "flowers retain their colours")
	_expect(Surfaces.kind_of("Water_lake", green) == Surfaces.Kind.NONE, "water is excluded")
	var plane := PlaneMesh.new()
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, plane.get_mesh_arrays())
	mesh.surface_set_material(0, green)
	Surfaces.set_season({"index": 3})
	var autumn := Surfaces.material_for(green, Surfaces.Kind.LEAVES, mesh, 1.0)
	_expect(autumn != null, "original material gets a seasonal copy")
	if autumn == null:
		quit(1)
		return
	_expect(autumn.get_shader_parameter("rl_season") == 3.0, "autumn arrives from server state")
	_expect(autumn.get_shader_parameter("roughness_value") == green.roughness,
		"roughness remains authored beneath the season")
	_expect(green.albedo_color == Color(0.2, 0.5, 0.1) and green.next_pass == null,
		"original imported material is unchanged")
	_expect(Surfaces.material_for(green, Surfaces.Kind.LEAVES, mesh, 1.0) == autumn,
		"identical sources share one seasonal material")
	Surfaces.set_season({"index": 0})
	_expect(autumn.get_shader_parameter("rl_season") == 0.0, "existing trees update at the month boundary")
	Surfaces.set_season({})
	_expect(autumn.get_shader_parameter("rl_season") == -1.0, "missing season restores the source appearance")
	var scene := Node3D.new()
	root.add_child(scene)
	var tree := MeshInstance3D.new()
	tree.name = "kit-oak-tree"
	tree.mesh = mesh
	scene.add_child(tree)
	var batch := MultiMeshInstance3D.new()
	batch.multimesh = MultiMesh.new()
	batch.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	batch.multimesh.mesh = mesh
	batch.multimesh.instance_count = 1
	batch.multimesh.set_instance_transform(0, Transform3D.IDENTITY)
	scene.add_child(batch)
	tree.set_meta(LookFoliage.BATCH_META, batch)
	Surfaces.set_season({"index": 0})
	_expect(Surfaces.apply(scene, manifest) == 1, "streamed tree gets the current season")
	_expect(tree.get_active_material(0) == batch.material_override,
		"a batch and its lifted member share the seasonal surface")
	_expect(Surfaces.apply(scene, manifest) == 0, "an unchanged root is not rescanned")
	_expect(Surfaces.apply(scene, inside, true) == 0, "interior materials are untouched")
	for mode: int in [LookProfile.Mode.FULL_PAINTED, LookProfile.Mode.PAINTED_GROUND, LookProfile.Mode.ORIGINAL]:
		LookProfile.set_player_mode(mode)
		LookSwitch.sync(scene, manifest)
		Surfaces.apply(scene, manifest, true)
		await process_frame
		_expect(tree.get_active_material(0).has_meta(Surfaces.META),
			"changing appearance retains seasons in mode %d" % mode)
	var unbatched := MeshInstance3D.new()
	unbatched.name = "Terrain_amberwood"
	unbatched.mesh = mesh
	scene.add_child(unbatched)
	Surfaces.apply(scene, manifest, true)
	_expect(unbatched.get_active_material(0).has_meta(Surfaces.META), "unbatched terrain also receives snow")
	_expect(LookGrassBeds._material_facts(unbatched).tint == green.albedo_color,
		"grass placement still reads the underlying ground material")
	var faded := LookFade.dither_copy(tree.get_active_material(0), tree)
	_expect(faded != null and faded.get_shader_parameter("rl_season") == 0.0,
		"camera fade retains seasonal colour")
	if faded != null:
		LookFade.write(faded, 0.35, 1.0)
		_expect(faded.get_shader_parameter(LookFade.OPEN_PARAMETER) == 1.0, "the player can be revealed behind foliage")
	var occluder := OccluderFade.Occluder.new()
	occluder.node = tree
	occluder.apply()
	var active_fade := tree.get_active_material(0) as ShaderMaterial
	Surfaces.set_season({"index": 3})
	occluder.fade = 1.0
	occluder.write_alpha()
	_expect(active_fade != null and active_fade.get_shader_parameter("rl_season") == 3.0,
		"Original mode updates even a tree already faded at the month boundary")
	occluder.restore()
	Surfaces.set_season({"index": 0})
	# The biome blend is a shader, not a StandardMaterial3D.
	var biome := ShaderMaterial.new()
	biome.shader = load("res://src/world/biome_blend.gdshader") as Shader
	biome.set_shader_parameter("base_roughness", Vector4(0.6, 0.7, 0.8, 0.9))
	var snow := Surfaces.material_for(biome, Surfaces.Kind.GROUND, mesh, 1.0)
	_expect(snow != null and snow.get_shader_parameter("base_roughness") == Vector4(0.6, 0.7, 0.8, 0.9),
		"biome textures and layer settings survive seasonal wrapping")
	# Full painted's includes and faded variant must both remain usable.
	var painted := LookFoliage.painted_for(green, LookFoliage.Kind.KIT_TREE, mesh)
	var seasonal_paint := Surfaces.material_for(painted, Surfaces.Kind.LEAVES, mesh, 1.0)
	_expect(seasonal_paint != null and seasonal_paint.has_meta(LookFade.FADED_SHADER_META),
		"Full painted keeps its own foliage and camera fade")
	Surfaces.set_season({})
	await process_frame
	# Drop batch draw dependencies before disposing this artificial fixture.
	batch.material_override = null
	batch.multimesh = null
	await process_frame
	scene.queue_free()
	await process_frame
	print("season surface tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		push_error(description)
