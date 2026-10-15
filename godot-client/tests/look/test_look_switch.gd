extends SceneTree
## Guards the look's live switch (LookSwitch) on fixture worlds.
##
## A continent chunk and an island painted with the look on go back exactly to
## the loader's own materials when it is switched off: every surface override,
## every static batch's override and the island sea's parameters as they were
## before the paint, the source materials untouched. Switched on again they
## are painted as before. Switching many times in a row leaves nothing behind:
## no stand-in, no second grass bed, no shadow twin, no extra node. A faded
## occluder is put to rest before the materials it holds are swapped, and gets
## its shadow back even when the switch turned while it was faded. A root a
## worker painted under the switch's old answer is caught as stale and brought
## into line as it arrives. The sun loses the grade's warmth, and the shadows
## take the quality's cascades.

const ISLAND_SEA_SHADER := "res://src/world/lantern_water.gdshader"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var saved_variable := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var saved_quality := OS.get_environment(LookProfile.QUALITY_VARIABLE)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	var saved_look := LookProfile.player_look()
	var saved_level := LookProfile.player_quality()
	LookProfile.set_player_look(true)
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookProfile.define_region("switchtest", {"props": {"keep_words": ["jade"]}})
	LookProfile.define_region("switchisle", {"water": {"decode_albedo": {ISLAND_SEA_SHADER: 2.5}}})

	var continent := _manifest("switchtest__chunk_1_1", true)
	var island := _manifest("switchisle", false)
	var chunk := _continent_world("ImportedWorld_switchtest__chunk_1_1")
	var isle := _island_world()
	var baseline := {chunk: _state(chunk), isle: _state(isle)}
	var nodes := {chunk: _node_count(chunk), isle: _node_count(isle)}
	var sources := _source_properties(chunk)

	# On: painted as the loader and the bind paint.
	var first := LookSwitch.sync(chunk, continent) + LookSwitch.sync(isle, island, true)
	var painted := LookSwitch.look_surfaces(chunk) + LookSwitch.look_surfaces(isle)
	_expect(first > 0 and painted >= 10,
		"switched on, the chunk and the island are painted (%d changed, %d look surfaces)"
			% [first, painted])
	var batch := chunk.get_node("StaticBatch_0_kit-dark-fir-1") as MultiMeshInstance3D
	_expect(batch.material_override != null
		and batch.material_override.has_meta(LookProfile.SOURCE_META),
		"a static batch of crowns carries a painted override")
	var sea := chunk.get_node("Sea_switchtest_1_1") as MeshInstance3D
	_expect(sea.get_surface_override_material(0) != baseline[chunk]["Sea_switchtest_1_1"].surfaces[0]
		and sea.get_surface_override_material(0).has_meta(LookProfile.SOURCE_META)
			== LookProfile.forward_plus(),
		"the continent's sea is decoded in Forward+ (and only there)")
	var island_sea := (isle.get_node("Sea_switchisle") as MeshInstance3D).material_override \
		as ShaderMaterial
	_expect((island_sea.get_shader_parameter(&"look_decode_albedo") == true)
			== LookProfile.forward_plus(),
		"the island's sea is decoded in place in Forward+")
	_expect(_source_properties(chunk) == sources, "the source materials are never edited")

	# Off: exactly the loader's own again.
	LookProfile.set_player_look(false)
	LookSwitch.sync(chunk, continent)
	LookSwitch.sync(isle, island, true)
	_expect(_state(chunk) == baseline[chunk], "switched off, the chunk has its own materials back: %s"
		% _difference(_state(chunk), baseline[chunk]))
	_expect(_state(isle) == baseline[isle], "and so has the island, its sea's parameters too: %s"
		% _difference(_state(isle), baseline[isle]))
	_expect(LookSwitch.look_surfaces(chunk) == 0 and LookSwitch.look_surfaces(isle) == 0,
		"nothing of the look's is left drawing")
	_expect(_source_properties(chunk) == sources, "and the source materials are as they were")

	# Many switches: the same paint, then the same loader's materials.
	for turn: int in 7:
		LookProfile.set_player_look(turn % 2 == 0)
		LookSwitch.sync(chunk, continent)
		LookSwitch.sync(isle, island, true)
		LookSwitch.sync(chunk, continent)
	_expect(LookProfile.enabled()
		and LookSwitch.look_surfaces(chunk) + LookSwitch.look_surfaces(isle) == painted,
		"after an odd number of switches the look is on and painted as the first time")
	LookProfile.set_player_look(false)
	LookSwitch.sync(chunk, continent)
	LookSwitch.sync(isle, island, true)
	_expect(_state(chunk) == baseline[chunk] and _state(isle) == baseline[isle]
		and _node_count(chunk) == nodes[chunk] and _node_count(isle) == nodes[isle],
		"and back off, nothing is left behind and no node was added")

	await _check_fades(chunk, continent)
	await _check_grass(chunk, continent)
	_check_stale_arrival(continent)
	_check_sun()
	_check_shadows()

	chunk.queue_free()
	isle.queue_free()
	await process_frame
	LookProfile.reload_regions()
	if saved_variable.is_empty():
		OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	else:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, saved_variable)
	if saved_quality.is_empty():
		OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	else:
		OS.set_environment(LookProfile.QUALITY_VARIABLE, saved_quality)
	LookProfile.set_player_look(saved_look)
	LookProfile.set_player_quality(saved_level)
	print("look switch tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

## A faded occluder holds on to its resting (painted) materials and, with the
## look on, gives its shadow to a twin: release() puts it to rest before the
## switch, and a fade that began with the look on gives the shadow back even
## after the switch has turned.
func _check_fades(chunk: Node3D, continent: WorldManifest) -> void:
	LookProfile.set_player_look(true)
	LookSwitch.sync(chunk, continent)
	var crate := chunk.get_node("Crate_0001_timber") as MeshInstance3D
	var canopy := chunk.get_node("Tree_0001_pale_birch_Canopy") as MeshInstance3D
	var canopy_paint := canopy.get_surface_override_material(0)
	var fade := OccluderFade.new()
	fade.configure(null, chunk)
	fade.set_enabled(true)
	for occluder: OccluderFade.Occluder in fade._occluders:
		if occluder.node == crate or occluder.node == canopy:
			occluder.target = 1.0
			occluder.apply()
			fade._active.append(occluder)
	_expect(crate.get_child_count() == 1 and crate.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		and canopy.get_surface_override_material(0) != canopy_paint,
		"with the look on, a faded wall hands its shadow to a twin and a crown swaps to its dithered copy")
	# The player switches while both are faded.
	LookProfile.set_player_look(false)
	var released: Array[OccluderFade.Occluder] = fade._active.duplicate()
	for occluder: OccluderFade.Occluder in released:
		occluder.fade = 1.0
	fade.release()
	var ready := released.size() == 2
	for occluder: OccluderFade.Occluder in released:
		ready = ready and not occluder.applied and occluder.fade == 0.0 and occluder.target == 0.0
	_expect(ready and fade._active.is_empty(),
		"released, each occluder is at rest with no target, so the next probe fades it again from solid")
	_expect(crate.get_child_count() == 0
		and crate.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		and not crate.has_meta(LookFade.MODE_META) and not crate.has_meta(LookFade.SHADOW_META),
		"released after the switch turned, the wall gets its shadow back and its twin goes")
	_expect(canopy.get_surface_override_material(0) == canopy_paint,
		"and the crown is back on its resting paint, for the switch to replace")
	LookSwitch.sync(chunk, continent)
	_expect(LookSwitch.look_surfaces(chunk) == 0 and fade.is_active(),
		"the switch then takes the paint off, and the index is kept for the next probe")
	# The next probe, looking down through the crate at a player under it,
	# fades it again: as develop fades it, now the look is off.
	var camera := Camera3D.new()
	camera.position = Vector3(4, 60, 5)
	var player := Node3D.new()
	player.position = Vector3(4, 20, 5)
	root.add_child(camera)
	root.add_child(player)
	fade._probe(camera, player)
	var refaded := crate.get_surface_override_material(0) as BaseMaterial3D
	_expect(refaded != null and refaded.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA
		and crate.get_child_count() == 0,
		"and the next probe fades the crate again, blended as on develop")
	fade.reset()
	camera.queue_free()
	player.queue_free()
	await process_frame
	var twins := 0
	for node: Node in chunk.find_children(String(LookFade.SHADOW_TWIN_NAME), "", true, false):
		twins += 1
	_expect(twins == 0, "no shadow twin outlives the fade")

## The grass follows the switch and the quality by itself, one bed at most.
func _check_grass(chunk: Node3D, continent: WorldManifest) -> void:
	var parent := Node3D.new()
	parent.name = "GrassParent"
	root.add_child(parent)
	var counts: Array[int] = []
	LookProfile.set_player_look(true)
	LookGrassBeds.tend(parent, chunk, continent, {}, Vector3.ZERO)
	_expect(_beds(parent) == 1, "with the look on a grass bed is grown")
	var first := parent.get_node(LookGrassBeds.NODE_NAME)
	for turn: int in 9:
		LookProfile.set_player_look(turn % 2 == 1)
		LookGrassBeds.tend(parent, chunk, continent, {}, Vector3.ZERO)
		LookGrassBeds.tend(parent, chunk, continent, {}, Vector3.ZERO)
		counts.append(_beds(parent))
	_expect(counts == [0, 1, 0, 1, 0, 1, 0, 1, 0],
		"switched over and over, there is one bed while the look is on and none while it is off: %s"
			% str(counts))
	await process_frame
	_expect(not is_instance_valid(first), "a bed taken away is freed")
	LookProfile.set_player_look(true)
	LookGrassBeds.tend(parent, chunk, continent, {}, Vector3.ZERO)
	var high := parent.get_node(LookGrassBeds.NODE_NAME) as LookGrassBeds
	for level: int in [LookProfile.Quality.MEDIUM, LookProfile.Quality.LOW,
			LookProfile.Quality.MEDIUM]:
		LookProfile.set_player_quality(level)
		LookGrassBeds.tend(parent, chunk, continent, {}, Vector3.ZERO)
		var grows := bool(LookProfile.QUALITY_PRESETS[level].grass)
		_expect(_beds(parent) == (1 if grows else 0),
			"%s grows grass exactly when its preset says so" % LookProfile.quality_name(level))
	await process_frame
	_expect(not is_instance_valid(high), "the bed a quality without grass took away is freed")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookProfile.set_player_look(false)
	LookGrassBeds.tend(parent, chunk, continent, {}, Vector3.ZERO)
	_expect(_beds(parent) == 0, "and off again, none")
	parent.queue_free()
	await process_frame

## A chunk a worker painted with the look on, adopted after the player switched
## it off, is stale, and syncing it takes the paint off.
func _check_stale_arrival(continent: WorldManifest) -> void:
	LookProfile.set_player_look(true)
	var arriving := _continent_world("ImportedWorld_switchtest__chunk_1_2")
	root.remove_child(arriving)
	var before := _state(arriving)
	# As the loader finishes it on its worker.
	LookGround.paint_loaded(arriving, continent)
	LookFoliage.paint_loaded(arriving, continent)
	_expect(LookSwitch.look_surfaces(arriving) > 0 and not LookProfile.stale(arriving),
		"a chunk painted under the current answer is not stale")
	LookProfile.set_player_look(false)
	_expect(LookProfile.stale(arriving) and LookProfile.any_stale(),
		"the switch turns while it waits to be adopted: it is stale")
	var residents := {"switchtest": {"root": arriving, "manifest": continent}}
	root.add_child(arriving)
	var found := LookSwitch.worlds(null, null, residents)
	_expect(found.size() == 1 and found[0].root == arriving and not bool(found[0].bound),
		"it is among the loaded roots once resident, and not the bound map")
	for world: Dictionary in found:
		if LookProfile.stale(world.root as Node):
			LookSwitch.sync(world.root as Node, world.manifest as WorldManifest, bool(world.bound))
	_expect(not LookProfile.stale(arriving) and _state(arriving) == before,
		"synced as it arrives, it draws the loader's own materials")
	arriving.free()

## The grade's warmth comes off the sun; a sun it never touched is left alone.
func _check_sun() -> void:
	LookProfile.set_player_look(true)
	var sun := DirectionalLight3D.new()
	sun.light_color = Color(1.0, 0.9, 0.8)
	sun.light_energy = 1.3
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	var lighting := WorldManifest.new()
	lighting.data = {"asset": {"id": "switchtest"}, "environment": {"sun": {"enabled": true}}}
	LookGrade.apply(lighting, environment, sun)
	_expect(sun.light_color != Color(1.0, 0.9, 0.8), "the grade warms the sun")
	LookGrade.revert_key(sun)
	_expect(sun.light_color == Color(1.0, 0.9, 0.8) and is_equal_approx(sun.light_energy, 1.3)
		and not sun.has_meta(&"look_graded_light_color"),
		"switched off, the sun has the binders' colour and energy back")
	LookGrade.revert_key(sun)
	_expect(sun.light_color == Color(1.0, 0.9, 0.8), "and reverting twice changes nothing")
	sun.free()
	environment.free()

## The quality's cascades reach the sun.
func _check_shadows() -> void:
	var sun := DirectionalLight3D.new()
	var modes := {}
	for level: int in LookProfile.QUALITY_NAMES.size():
		LookProfile.set_player_quality(level)
		LookSwitch.apply_shadow_quality(sun)
		modes[level] = sun.directional_shadow_mode
	var expected := {1: DirectionalLight3D.SHADOW_ORTHOGONAL,
		2: DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS, 4: DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS}
	var ok := true
	for level: int in modes:
		ok = ok and modes[level] == expected[int(LookProfile.QUALITY_PRESETS[level].shadow_splits)]
	_expect(ok and modes[LookProfile.Quality.HIGH] == DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS,
		"each quality gives the sun its cascades, HIGH Godot's four: %s" % str(modes))
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	LookSwitch.apply_shadow_quality(sun)
	sun.free()

# --- Fixtures -------------------------------------------------------------------

func _manifest(id: String, on_continent: bool) -> WorldManifest:
	var manifest := WorldManifest.new()
	manifest.data = {"asset": {"id": id}, "environment": {"sun": {"enabled": true}}}
	if on_continent:
		manifest.data["continentGeography"] = {"geometryMode": "continent-chunks-v1"}
	return manifest

## A chunk as the loader leaves it: terrain, the biome blend and the sea on
## the loader's own surface overrides, a yard, a road deck, a river, crowns,
## a trunk, a crate, a jade statue (the region keeps jade's colour) and a
## static batch of firs.
func _continent_world(node_name: String) -> Node3D:
	var world := Node3D.new()
	world.name = node_name
	root.add_child(world)
	var terrain := StandardMaterial3D.new()
	terrain.vertex_color_use_as_albedo = true
	_mesh(world, "Terrain_switchtest_1_1", terrain)
	var biome := ShaderMaterial.new()
	biome.shader = load(LookGround.BIOME_SHADER_PATH) as Shader
	_mesh(world, "AuthoredGround_switchtestBase_1_1", null).set_surface_override_material(0, biome)
	var yard := StandardMaterial3D.new()
	yard.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	yard.cull_mode = BaseMaterial3D.CULL_DISABLED
	yard.albedo_color = Color("ffa85c")
	_mesh(world, "AuthoredGround_switchtest_ground-03_1_1", yard)
	var deck := yard.duplicate() as StandardMaterial3D
	deck.albedo_color = Color("997a4f")
	_mesh(world, "Walk_switchtest_highway_1_1", deck)
	var river := StandardMaterial3D.new()
	river.resource_name = "authored_switchtest_river_water"
	_mesh(world, "Water_switchtest_river_1_1", river)
	var sea := ShaderMaterial.new()
	sea.shader = load(LookGround.CONTINENT_WATER_PATH) as Shader
	_mesh(world, "Sea_switchtest_1_1", null).set_surface_override_material(0, sea)
	var leaves := StandardMaterial3D.new()
	leaves.resource_name = "foliage_amber"
	leaves.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	leaves.cull_mode = BaseMaterial3D.CULL_DISABLED
	_box(world, "Tree_0001_pale_birch_Canopy", leaves, Vector3(8, 6, 8), Vector3(-10, 30, 5))
	var bark := StandardMaterial3D.new()
	bark.resource_name = "bark_oak"
	_box(world, "Tree_0001_pale_birch_Wood", bark, Vector3(1, 8, 1), Vector3(-14, 30, 5))
	_box(world, "Crate_0001_timber", bark.duplicate(), Vector3(4, 3, 4), Vector3(4, 30, 5))
	var atlas := StandardMaterial3D.new()
	atlas.resource_name = "Material_0"
	atlas.cull_mode = BaseMaterial3D.CULL_DISABLED
	_box(world, "kit-crimson-maple-3", atlas, Vector3(9, 9, 9), Vector3(20, 18, 40))
	var jade := StandardMaterial3D.new()
	jade.resource_name = "jade_stone"
	_box(world, "Statue_0001", jade, Vector3(2, 3, 2), Vector3(30, 18, 30))
	var fir := atlas.duplicate() as StandardMaterial3D
	var fir_a := _box(world, "kit-dark-fir-1", fir, Vector3(5, 12, 5), Vector3(50, 20, 50))
	var fir_b := MeshInstance3D.new()
	fir_b.name = "kit-dark-fir-2"
	fir_b.mesh = fir_a.mesh
	world.add_child(fir_b)
	var batch := MultiMeshInstance3D.new()
	batch.name = "StaticBatch_0_kit-dark-fir-1"
	batch.multimesh = MultiMesh.new()
	batch.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	batch.multimesh.mesh = fir_a.mesh
	batch.multimesh.instance_count = 2
	world.add_child(batch)
	for index: int in 2:
		var member: MeshInstance3D = [fir_a, fir_b][index]
		member.visible = false
		member.set_meta(LookFoliage.BATCH_META, batch)
		member.set_meta(LookFoliage.BATCH_INDEX_META, index)
	return world

## An island as its scene script leaves it: vertex-coloured terrain, a pool,
## and a sea whose shader its scene script owns (and still animates) as the
## mesh's material override.
func _island_world() -> Node3D:
	var world := Node3D.new()
	world.name = "ImportedWorld_switchisle"
	root.add_child(world)
	var terrain := StandardMaterial3D.new()
	terrain.vertex_color_use_as_albedo = true
	_mesh(world, "Terrain_switchisle", terrain)
	var pool := StandardMaterial3D.new()
	pool.resource_name = "water_pool"
	_mesh(world, "Pool_0001", pool)
	var sea := ShaderMaterial.new()
	sea.shader = load(ISLAND_SEA_SHADER) as Shader
	_mesh(world, "Sea_switchisle", null).material_override = sea
	return world

func _mesh(parent: Node, node_name: String, material: Material) -> MeshInstance3D:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	for corner: Vector3 in [Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 0, 1)]:
		tool.set_color(Color(1, 1, 1, 0.5))
		tool.set_normal(Vector3.UP)
		tool.set_uv(Vector2(corner.x, corner.z))
		tool.add_vertex(corner)
	var mesh := tool.commit()
	if material != null:
		mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	parent.add_child(node)
	return node

func _box(parent: Node, node_name: String, material: Material, size: Vector3,
		at: Vector3) -> MeshInstance3D:
	var box := BoxMesh.new()
	box.size = size
	var tool := SurfaceTool.new()
	tool.create_from(box, 0)
	var mesh := tool.commit()
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.position = at
	parent.add_child(node)
	return node

## Every geometry's overrides under `world`, by node name: the surface
## overrides and the material override (the very objects), and the look's sea
## parameters on a shader override.
func _state(world: Node) -> Dictionary:
	var state := {}
	for node: Node in world.find_children("*", "GeometryInstance3D", true, false):
		var entry := {"surfaces": [], "override": (node as GeometryInstance3D).material_override,
			"cast_shadow": (node as GeometryInstance3D).cast_shadow}
		if node is MeshInstance3D:
			for surface: int in (node as MeshInstance3D).get_surface_override_material_count():
				entry.surfaces.append((node as MeshInstance3D).get_surface_override_material(surface))
		var shader := entry.override as ShaderMaterial
		if shader != null:
			entry["decode"] = shader.get_shader_parameter(&"look_decode_albedo")
			entry["sea_value"] = shader.get_shader_parameter(&"look_sea_value")
		state[String(node.name)] = entry
	return state

func _difference(now: Dictionary, then: Dictionary) -> String:
	var different: Array[String] = []
	for key: String in then:
		if now.get(key) != then[key]:
			different.append(key)
	for key: String in now:
		if not then.has(key):
			different.append("+" + key)
	return str(different)

func _node_count(world: Node) -> int:
	return world.find_children("*", "", true, false).size()

## What the chunk's source materials say, to prove the switch never edits one.
func _source_properties(world: Node) -> Array:
	var properties := []
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		var material := mesh.surface_get_material(0) if mesh != null else null
		if material is StandardMaterial3D:
			var standard := material as StandardMaterial3D
			properties.append([node.name, standard.albedo_color, standard.transparency,
				standard.cull_mode, standard.get_meta_list()])
	return properties

func _beds(parent: Node) -> int:
	var count := 0
	for child: Node in parent.get_children():
		if child is LookGrassBeds:
			count += 1
	return count

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
