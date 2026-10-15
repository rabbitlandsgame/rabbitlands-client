extends SceneTree
## Guards the look pass's painted ground (layer L2).
##
## With ELORIA_LOOK=0 the ground must be exactly what the loader built.
## With it on, only ground is painted, one painted material is shared by every
## mesh that used a source material, the source materials and meshes are never
## edited (a map cache is packed from them), and painting twice is harmless:
## a chunk can be finished by the loader and then seen again.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var continent := WorldManifest.new()
	continent.data = {"continentGeography": {"geometryMode": "continent-chunks-v1"},
		"environment": {"sun": {"enabled": true}}}
	var island := WorldManifest.new()
	island.data = {"environment": {"sun": {"enabled": true}}}
	var interior := WorldManifest.new()
	interior.data = {"environment": {"sun": {"enabled": false}}}

	var terrain_material := StandardMaterial3D.new()
	terrain_material.vertex_color_use_as_albedo = true
	var patch_material := StandardMaterial3D.new()
	patch_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	patch_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	patch_material.albedo_color = Color("ffa85c")
	var deck_material := StandardMaterial3D.new()
	deck_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	deck_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	deck_material.albedo_color = Color("997a4f")
	var threshold_material := deck_material.duplicate() as StandardMaterial3D
	threshold_material.albedo_color = Color(0, 0, 0, 0)
	var bridge_material := StandardMaterial3D.new()
	var water_material := StandardMaterial3D.new()
	var tree_material := StandardMaterial3D.new()
	var biome_material := ShaderMaterial.new()
	biome_material.shader = load(LookGround.BIOME_SHADER_PATH) as Shader
	biome_material.set_shader_parameter(&"mask_size", 66.0)
	biome_material.set_shader_parameter(&"base_tint_0", Color("b3eb80"))
	biome_material.set_shader_parameter(&"mask_metres_per_pixel", 1.5)

	var world := Node3D.new()
	world.name = "ImportedWorld_test"
	root.add_child(world)
	var terrain_a := _mesh(world, "Terrain_test_4_5", terrain_material)
	var terrain_b := _mesh(world, "Terrain_test_4_6", terrain_material)
	var biome := _mesh(world, "AuthoredGround_testBase_4_5", null)
	biome.set_surface_override_material(0, biome_material)
	var patch := _mesh(world, "AuthoredGround_test_ground-03_test_4_5", patch_material)
	var deck := _mesh(world, "Walk_test_highway-test-south_test_4_5", deck_material)
	var threshold := _mesh(world, "Walk__StreamThreshold_test--other", threshold_material)
	var bridge := _mesh(world, "Walk_ContinentalBridgeUnion_002_test", bridge_material, false)
	var water := _mesh(world, "Water_test_4_5", water_material)
	var tree := _mesh(world, "Tree_0361_pale_birch_Canopy", tree_material)
	var batched := _mesh(world, "Terrain_test_batched", terrain_material)
	batched.set_meta(LookGround.BATCH_META, NodePath("StaticBatch_0_Terrain"))
	var sources := {}
	for node: MeshInstance3D in [terrain_a, terrain_b, biome, patch, deck, threshold,
			bridge, water, tree, batched]:
		sources[node] = node.mesh.surface_get_material(0)
	var terrain_before := _properties(terrain_material)

	# Off: nothing changes.
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	_expect(LookGround.paint_loaded(world, continent) == 0
		and LookGround.paint_bound(world, island) == 0 and LookGround.paint(world) == 0,
		"with ELORIA_LOOK=0 every entry point paints nothing")
	_expect(terrain_a.get_surface_override_material(0) == null
		and biome.get_surface_override_material(0) == biome_material,
		"with ELORIA_LOOK=0 the ground keeps the loader's materials")

	# On: the entry points keep to their own maps.
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_expect(LookGround.paint_loaded(world, island) == 0,
		"the loader leaves a map outside the continent to the bind")
	_expect(LookGround.paint_bound(world, continent) == 0,
		"the bind leaves continent maps to the loader")
	_expect(LookGround.paint_bound(world, interior) == 0,
		"an interior is never painted")
	var painted := LookGround.paint_loaded(world, continent)
	_expect(painted == 5, "five ground surfaces are painted (got %d)" % painted)

	var terrain_paint := terrain_a.get_surface_override_material(0) as ShaderMaterial
	_expect(terrain_paint != null and terrain_paint.shader == LookGround.SHADER_OPAQUE,
		"the terrain is painted with the opaque culled shader")
	_expect(terrain_b.get_surface_override_material(0) == terrain_paint,
		"meshes that shared a source material share one painted material")
	_expect(terrain_paint != null
		and bool(terrain_paint.get_shader_parameter(&"use_vertex_albedo"))
		and float(terrain_paint.get_shader_parameter(&"look_road_detect")) == 1.0,
		"the terrain keeps its vertex colour and looks in it for worn roads")
	var patch_paint := patch.get_surface_override_material(0) as ShaderMaterial
	_expect(patch_paint != null and patch_paint.shader == LookGround.SHADER_OVERLAY
		and bool(patch_paint.get_shader_parameter(&"use_vertex_alpha"))
		and float(patch_paint.get_shader_parameter(&"look_yard")) == 1.0
		and patch_paint.get_shader_parameter(&"albedo_color") == Color("ffa85c"),
		"a patch keeps its tint, is feathered by vertex alpha and lifted as a yard")
	var deck_paint := deck.get_surface_override_material(0) as ShaderMaterial
	_expect(deck_paint != null
		and float(deck_paint.get_shader_parameter(&"look_path_force")) == 1.0,
		"a walk deck is painted as a path")
	var biome_paint := biome.get_surface_override_material(0) as ShaderMaterial
	_expect(biome_paint != null and biome_paint != biome_material
		and biome_paint.shader != biome_material.shader
		and biome_paint.shader.code.contains("look_paint(")
		and is_equal_approx(float(biome_paint.get_shader_parameter(&"mask_size")), 66.0)
		and biome_paint.get_shader_parameter(&"base_tint_0") == Color("b3eb80"),
		"the biome blend is painted through its own spliced copy, parameters intact")
	_expect(threshold.get_surface_override_material(0) == null
		and bridge.get_surface_override_material(0) == null
		and tree.get_surface_override_material(0) == null
		and batched.get_surface_override_material(0) == null,
		"thresholds, bridge timber, trees and batched meshes are left alone")
	# Inland water is not ground: in Forward+ it only takes its decoded tint.
	var water_paint := water.get_surface_override_material(0) as BaseMaterial3D
	if LookProfile.forward_plus():
		var tint := LookProfile.INLAND_WATER_TINT
		_expect(water_paint != null and water_paint != water_material
			and water_paint.albedo_color == Color(tint.r, tint.g, tint.b, 1.0)
			and water_material.albedo_color == Color.WHITE,
			"inland water takes a decoded copy in Forward+, its source untouched")
	else:
		_expect(water_paint == null, "inland water is left alone in the compatibility renderer")
	var untouched := true
	for node: MeshInstance3D in sources:
		untouched = untouched and node.mesh.surface_get_material(0) == sources[node]
	_expect(untouched and _properties(terrain_material) == terrain_before,
		"source materials and meshes are never edited, only overridden")

	var overrides: Array = []
	for node: MeshInstance3D in [terrain_a, terrain_b, biome, patch, deck]:
		overrides.append(node.get_surface_override_material(0))
	_expect(LookGround.paint(world) == 0, "painting a painted root again paints nothing")
	var same := true
	for index: int in overrides.size():
		var node: MeshInstance3D = [terrain_a, terrain_b, biome, patch, deck][index]
		same = same and node.get_surface_override_material(0) == overrides[index]
	_expect(same, "and leaves the painted materials in place")

	# Roads are edged and cut crisply; patches are glazes cut to their footprint.
	_expect(deck_paint != null and deck_paint.shader == LookGround.SHADER_DECK
		and float(deck_paint.get_shader_parameter(&"look_edge_band")) == LookProfile.EDGE_BAND
		and deck_paint.get_shader_parameter(&"look_rim") == LookProfile.DECK_RIM,
		"a walk deck is drawn with the deck shader, a crisp rim and an edging band")
	_expect(patch_paint != null
		and float(patch_paint.get_shader_parameter(&"look_edge_band")) == 0.0
		and patch_paint.get_shader_parameter(&"look_rim") == LookProfile.PATCH_RIM
		and is_equal_approx(float(patch_paint.get_shader_parameter(&"look_opacity")),
			LookProfile.PATCH_OPACITY),
		"a patch has no edging band, keeps its footprint and is a glaze")

	# A continent chunk is painted with its own region's trims, and the roads
	# of a root with pale paving learn where it lies.
	var chunk := Node3D.new()
	root.add_child(chunk)
	var paving_material := patch_material.duplicate() as StandardMaterial3D
	paving_material.albedo_color = Color("ccba9c")
	var chunk_deck_material := deck_material.duplicate() as StandardMaterial3D
	var chunk_soil_material := patch_material.duplicate() as StandardMaterial3D
	var paving := _mesh(chunk, "AuthoredGround_test_crystal_test_4_5", paving_material)
	var chunk_deck := _mesh(chunk, "Walk_test_avenue_test_4_5", chunk_deck_material)
	var chunk_soil := _mesh(chunk, "AuthoredGround_test_ground-03_test_4_5", chunk_soil_material)
	var amberwood := WorldManifest.new()
	amberwood.data = {"asset": {"id": "amberwood__chunk_4_5"},
		"continentGeography": {"geometryMode": "continent-chunks-v1"}}
	_expect(LookGround.region_of(amberwood) == "amberwood",
		"a chunk paints as its region")
	_expect(LookGround.paint_loaded(chunk, amberwood) == 3, "the chunk's ground is painted")
	var paving_paint := paving.get_surface_override_material(0) as ShaderMaterial
	_expect(LookGround.is_paving(paving_material) and not LookGround.is_paving(patch_material)
		and paving_paint.get_shader_parameter(&"look_rim") == LookProfile.PAVING_RIM
		and float(paving_paint.get_shader_parameter(&"look_opacity")) == 1.0
		and int(paving_paint.get_shader_parameter(&"look_paving_count")) == 0,
		"pale paving keeps its geometry, stays opaque and is not darkened as a road")
	var avenue_paint := chunk_deck.get_surface_override_material(0) as ShaderMaterial
	var box := paving.get_aabb()
	var rects: PackedVector4Array = avenue_paint.get_shader_parameter(&"look_paving_rects")
	_expect(int(avenue_paint.get_shader_parameter(&"look_paving_count")) == 1
		and rects.size() == LookProfile.PAVING_RECTS_MAX
		and rects[0] == Vector4(box.position.x, box.position.z, box.end.x, box.end.z)
		and int((chunk_soil.get_surface_override_material(0) as ShaderMaterial)
			.get_shader_parameter(&"look_paving_count")) == 1,
		"its road and its soil learn the paving's bounds")
	# The trims are the region files' (src/world/look/regions/<id>.json).
	var trims := LookProfile.region_section("amberwood", "ground")
	_expect(trims.has("path_luma") and trims.path_tint is Color,
		"Amberwood's ground trims are read from its region file, its tint as a colour")
	# The default is the renderer's: GROUND_FORWARD's in Forward+ (which a
	# headless run reports when the project names it), PATH_LUMA otherwise.
	var default_luma := float(LookProfile.GROUND_FORWARD.get("path_luma",
		LookProfile.PATH_LUMA)) if LookProfile.forward_plus() else LookProfile.PATH_LUMA
	_expect(is_equal_approx(float(avenue_paint.get_shader_parameter(&"look_path_luma")),
			float(trims.get("path_luma", -1.0)))
		and is_equal_approx(float(deck_paint.get_shader_parameter(&"look_path_luma")),
			default_luma),
		"a region's road value is its own trim; other regions keep the renderer's default")
	var reach_trims := LookProfile.region_section("lantern_reach", "ground")
	_expect(LookProfile.ground_value("lantern_reach", "verge_value_green", -1.0)
			== (reach_trims.get("verge_value_green_forward") if LookProfile.forward_plus()
				else reach_trims.get("verge_value_green"))
		and LookProfile.ground_value("no_such_region", "verge_value_green", -1.0)
			== (LookProfile.GROUND_FORWARD["verge_value_green"] if LookProfile.forward_plus() else -1.0),
		"a region's `_forward` trim wins in Forward+, and a region without one takes the renderer's default")

	# An island map is painted at bind, with its scene's vertex colour.
	var island_root := Node3D.new()
	root.add_child(island_root)
	var island_material := StandardMaterial3D.new()
	island_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	island_material.vertex_color_use_as_albedo = true
	var island_ground := _mesh(island_root, "Walk_Terrain_0", island_material)
	_expect(LookGround.paint_bound(island_root, island) == 1
		and (island_ground.get_surface_override_material(0) as ShaderMaterial).shader
			== LookGround.SHADER_TWO_SIDED,
		"an island's two-sided ground is painted at bind with the two-sided shader")

	# Paving and cobble are warm or neutral stone: not grass, granite or sand.
	var tinted := func(hex: String) -> StandardMaterial3D:
		var material := patch_material.duplicate() as StandardMaterial3D
		material.albedo_color = Color(hex)
		return material
	_expect(LookGround.is_paving(tinted.call("ccba9c")) and LookGround.is_paving(tinted.call("e6e0d1"))
		and LookGround.is_paving(tinted.call("d1c7ab")),
		"the Four Gates plaza and the civic courts are paving")
	_expect(not LookGround.is_paving(tinted.call("c7dbb8")) and LookGround.is_meadow(tinted.call("c7dbb8"))
		and LookGround.is_meadow(tinted.call("9cad66")) and LookGround.is_meadow(tinted.call("b3eb80"))
		and not LookGround.is_meadow(tinted.call("9ea169")) and not LookGround.is_meadow(tinted.call("ffa85c")),
		"green patches are meadows, whatever their value (Sunmane's grain and pasture, a Grass preset), not paving")
	_expect(LookGround.is_rock(tinted.call("b3b5bf")) and LookGround.is_rock(tinted.call("8a858f"))
		and not LookGround.is_rock(tinted.call("ccba9c")) and not LookGround.is_rock(tinted.call("fff5d1"))
		and not LookGround.is_rock(tinted.call("b8eba8")) and not LookGround.is_rock(tinted.call("666e59")),
		"granite and lilac scree are rock; paving, sand, meadow and dark heather are not")
	_expect(not LookGround.is_paving(tinted.call("b8eba8"))
		and not LookGround.is_paving(tinted.call("b3b5bf"))
		and not LookGround.is_paving(tinted.call("adc4db"))
		and not LookGround.is_paving(tinted.call("fff5d1")),
		"a pale moor-grass patch, granite, a cave's snow and beach sand are not paving")
	_expect(LookGround.is_cobble(tinted.call("ad9e82")) and not LookGround.is_cobble(tinted.call("b8eba8"))
		and not LookGround.is_cobble(tinted.call("fff5d1")),
		"worn cobble is still cobble; pale grass and sand are glazes")

	# A region whose decks are its ground (the tutorial courts) keeps their
	# own colour; a deck elsewhere is a road.
	LookProfile.define_region("deck_ground_test", {"id": "deck_ground_test", "schema": 1,
		"ground": {"deck_path": 0, "deck_road_colour": [1.0, 0.922, 0.792]}})
	var court_material := deck_material.duplicate() as StandardMaterial3D
	court_material.vertex_color_use_as_albedo = true
	var court := LookGround.painted_for(court_material, LookGround.Kind.DECK,
		(deck.mesh as Mesh), 0, "deck_ground_test") as ShaderMaterial
	_expect(court != null and float(court.get_shader_parameter(&"look_path_force")) == 0.0
		and float(court.get_shader_parameter(&"look_keep")) == 1.0
		and float(court.get_shader_parameter(&"look_edge_band")) == 0.0,
		"a deck its region calls ground keeps its own colour and no road edging")
	_expect(court != null and float(court.get_shader_parameter(&"look_road_detect")) == 1.0
		and court.get_shader_parameter(&"look_road_tolerance") == LookProfile.DECK_ROAD_TOLERANCE,
		"and finds its tracks by the vertex colour its region names")
	_expect(float(deck_paint.get_shader_parameter(&"look_path_force")) == 1.0
		and float(deck_paint.get_shader_parameter(&"look_keep")) == 0.0
		and float(deck_paint.get_shader_parameter(&"look_road_detect")) == 0.0,
		"any other deck is a road")
	LookProfile.reload_regions()

	# A region may name decorative inlays (`ground.keep_patches`, words in the
	# patch material's name) that keep their own colour instead of their tint
	# class: a blue ring inside paving is otherwise a yard worn into cobble.
	LookProfile.define_region("inlay_test", {"id": "inlay_test", "schema": 1,
		"ground": {"keep_patches": ["Rosette"]}})
	var inlay_material := patch_material.duplicate() as StandardMaterial3D
	inlay_material.albedo_color = Color(0.62, 0.68, 0.84)
	inlay_material.resource_name = "authored_inlay_test_plaza-rosette"
	var yard_material := inlay_material.duplicate() as StandardMaterial3D
	yard_material.resource_name = "authored_inlay_test_yard-3"
	var some_paving := PackedVector4Array([Vector4(-50, -50, 50, 50)])
	var inlay := LookGround.painted_for(inlay_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "inlay_test", some_paving) as ShaderMaterial
	var yard := LookGround.painted_for(yard_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "inlay_test", some_paving) as ShaderMaterial
	var elsewhere := LookGround.painted_for(inlay_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "no_such_region", some_paving) as ShaderMaterial
	_expect(LookGround.is_kept_patch(inlay_material, "inlay_test")
		and not LookGround.is_kept_patch(yard_material, "inlay_test")
		and not LookGround.is_kept_patch(inlay_material, "no_such_region"),
		"a patch is an inlay only where its region names it, by a word of its material's name")
	_expect(inlay != null and float(inlay.get_shader_parameter(&"look_keep")) == 1.0
		and float(inlay.get_shader_parameter(&"look_yard")) == 0.0
		and float(inlay.get_shader_parameter(&"look_opacity")) == 1.0
		and int(inlay.get_shader_parameter(&"look_paving_count")) == 0,
		"a named inlay is drawn solid in its own colour and never worn into the paving's cobble")
	_expect(yard != null and float(yard.get_shader_parameter(&"look_keep")) == 0.0
		and float(yard.get_shader_parameter(&"look_opacity")) == LookProfile.PATCH_OPACITY
		and int(yard.get_shader_parameter(&"look_paving_count")) == 1
		and elsewhere != null and float(elsewhere.get_shader_parameter(&"look_keep")) == 0.0,
		"an unnamed patch, or the same patch in another region, is still a yard glaze")
	LookProfile.define_region("meadow_tint_test", {"id": "meadow_tint_test", "schema": 1,
		"ground": {"meadow_value": 0.5, "meadow_tint": [0.8, 1.0, 0.6]}})
	var lawn_material := patch_material.duplicate() as StandardMaterial3D
	lawn_material.albedo_color = Color(0.7, 0.86, 0.58)
	var tinted_lawn := LookGround.painted_for(lawn_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "meadow_tint_test") as ShaderMaterial
	var plain_lawn := LookGround.painted_for(lawn_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "no_such_region") as ShaderMaterial
	_expect(tinted_lawn != null and (tinted_lawn.get_shader_parameter(&"look_keep_tint") as Vector3)
			.is_equal_approx(Vector3(0.4, 0.5, 0.3))
		and plain_lawn != null and (plain_lawn.get_shader_parameter(&"look_keep_tint") as Vector3)
			.is_equal_approx(Vector3.ONE * LookProfile.MEADOW_VALUE),
		"a meadow keeps its colour times its region's meadow value and tint; white elsewhere")
	LookProfile.define_region("paving_tint_test", {"id": "paving_tint_test", "schema": 1,
		"ground": {"paving_tint": [0.7, 0.6, 0.5]}})
	var own_paving := LookGround.painted_for(paving_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "paving_tint_test") as ShaderMaterial
	var shared_paving := LookGround.painted_for(paving_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "no_such_region") as ShaderMaterial
	var shared_tint := LookProfile.PAVING_SURFACE_TINT
	_expect(own_paving != null and (own_paving.get_shader_parameter(&"look_surface_tint") as Vector3)
			.is_equal_approx(Vector3(0.7, 0.6, 0.5))
		and shared_paving != null and (shared_paving.get_shader_parameter(&"look_surface_tint") as Vector3)
			.is_equal_approx(Vector3(shared_tint.r, shared_tint.g, shared_tint.b)),
		"pale paving takes its region's paving tint; the shared one elsewhere")
	LookProfile.define_region("verge_grain_test", {"id": "verge_grain_test", "schema": 1,
		"ground": {"verge_grain": 1.0, "verge_grain_steep": 0.3}})
	var grained := LookGround.painted_for(patch_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "verge_grain_test") as ShaderMaterial
	var default_grain := LookGround.painted_for(patch_material, LookGround.Kind.PATCH,
		(patch.mesh as Mesh), 0, "no_such_region") as ShaderMaterial
	_expect(grained != null and float(grained.get_shader_parameter(&"look_verge_grain")) == 1.0
		and default_grain != null
		and is_equal_approx(float(default_grain.get_shader_parameter(&"look_verge_grain")), LookProfile.VERGE_GRAIN)
		and is_equal_approx(float(grained.get_shader_parameter(&"look_verge_grain_steep")), 0.3)
		and float(default_grain.get_shader_parameter(&"look_verge_grain_steep")) == 1.0,
		"a region may keep all of its verge's texture grain; VERGE_GRAIN elsewhere")
	LookProfile.reload_regions()

	# The continent's sea is decoded in Forward+ as a copy, never in place.
	var sea_root := Node3D.new()
	root.add_child(sea_root)
	var sea := ShaderMaterial.new()
	sea.shader = load(LookGround.CONTINENT_WATER_PATH) as Shader
	var sea_mesh := _mesh(sea_root, "Water_test_1_2", null)
	sea_mesh.set_surface_override_material(0, sea)
	var decoded := LookGround.decode_continent_sea(sea_root)
	var decoded_sea := sea_mesh.get_surface_override_material(0) as ShaderMaterial
	if LookProfile.forward_plus():
		_expect(decoded == 1 and decoded_sea != sea
			and decoded_sea.get_shader_parameter(&"look_decode_albedo") == true
			and sea.get_shader_parameter(&"look_decode_albedo") != true,
			"the continent sea is decoded on a copy in Forward+")
		_expect(float(decoded_sea.get_shader_parameter(&"look_sea_value")) == LookProfile.CONTINENT_SEA_VALUE
			and (decoded_sea.get_shader_parameter(&"look_sea_tint") as Vector3).is_equal_approx(Vector3.ONE),
			"a region that names no sea of its own is decoded at the shared value")
		LookProfile.define_region("sea_test", {"id": "sea_test", "schema": 1,
			"water": {"sea_value": 9.0, "sea_chroma": 1.2, "sea_tint": [0.5, 1.0, 1.1]}})
		var own_sea_root := Node3D.new()
		root.add_child(own_sea_root)
		var own_sea_mesh := _mesh(own_sea_root, "Water_test_1_3", null)
		own_sea_mesh.set_surface_override_material(0, sea)
		LookGround.decode_continent_sea(own_sea_root, "sea_test")
		var own_sea := own_sea_mesh.get_surface_override_material(0) as ShaderMaterial
		_expect(own_sea != sea and float(own_sea.get_shader_parameter(&"look_sea_value")) == 9.0
			and float(own_sea.get_shader_parameter(&"look_sea_chroma")) == 1.2
			and (own_sea.get_shader_parameter(&"look_sea_tint") as Vector3)
				.is_equal_approx(Vector3(0.5, 1.0, 1.1)),
			"a region's own sea value, chroma and tint reach its decoded sea")
		LookProfile.reload_regions()
	else:
		_expect(decoded == 0 and decoded_sea == sea,
			"the continent sea is left alone in the compatibility renderer")

	OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	print("test_look_ground: %s (%d failures)" % [
		"PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

func _mesh(parent: Node, node_name: String, material: Material,
		coloured := true) -> MeshInstance3D:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	for corner: Vector3 in [Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 0, 1)]:
		if coloured:
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

func _properties(material: StandardMaterial3D) -> Array:
	return [material.albedo_color, material.vertex_color_use_as_albedo,
		material.transparency, material.cull_mode, material.roughness,
		material.get_meta_list()]

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
