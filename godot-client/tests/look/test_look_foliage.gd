extends SceneTree
## Guards the look pass's painted crowns and dithered occluder fade (layer L3).
##
## With ELORIA_LOOK=0 the crowns keep the loader's materials and
## OccluderFade blends exactly as on develop. With it on, only crowns are
## painted (never trunks, ground or a merged scatter mesh), the source
## materials and meshes are never edited, painting twice is harmless, a
## crown's jitter seed does not move when the world is rebased, a batch and
## its hidden members draw the same crown, and OccluderFade opens a hole round
## the player in painted and standard materials, lets a faded crown's shadow go
## (as develop's blended copies do) but keeps a wall's on a twin, and puts
## everything back after.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var continent := WorldManifest.new()
	continent.data = {"continentGeography": {"geometryMode": "continent-chunks-v1"},
		"environment": {"sun": {"enabled": true}}}
	var island := WorldManifest.new()
	island.data = {"environment": {"sun": {"enabled": true}}}

	var leaves := StandardMaterial3D.new()
	leaves.resource_name = "foliage_amber"
	leaves.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	leaves.alpha_scissor_threshold = 0.4
	leaves.cull_mode = BaseMaterial3D.CULL_DISABLED
	var bark := StandardMaterial3D.new()
	bark.resource_name = "bark_oak"
	var atlas := StandardMaterial3D.new()
	atlas.resource_name = "Material_0"
	atlas.cull_mode = BaseMaterial3D.CULL_DISABLED
	atlas.roughness = 0.8
	var shrub_atlas := atlas.duplicate() as StandardMaterial3D
	var flower_atlas := atlas.duplicate() as StandardMaterial3D
	var litter_atlas := atlas.duplicate() as StandardMaterial3D
	var pine_colour := StandardMaterial3D.new()
	pine_colour.resource_name = "wind_pine"
	pine_colour.cull_mode = BaseMaterial3D.CULL_DISABLED
	pine_colour.vertex_color_use_as_albedo = true
	var ground := StandardMaterial3D.new()
	ground.resource_name = "foliage_amber"
	ground.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	ground.cull_mode = BaseMaterial3D.CULL_DISABLED
	var leaves_before := _properties(leaves)
	var atlas_before := _properties(atlas)

	var world := Node3D.new()
	world.name = "ImportedWorld_test__chunk_4_5"
	root.add_child(world)
	var canopy := _mesh(world, "Tree_0361_pale_birch_Canopy", leaves, Vector3(8, 6, 8), Vector3(-10, 30, 5))
	# A timber crate, faded as any StandardMaterial3D (wide enough to keep its
	# hole rather than vanish); a tree's own trunk is cut near the camera with
	# its crown.
	var wood := _mesh(world, "Crate_0361_timber", bark, Vector3(4, 3, 4), Vector3(-10, 30, 5))
	var trunk := _mesh(world, "Tree_0362_pale_birch_Wood", bark.duplicate(), Vector3(1, 8, 1),
		Vector3(-14, 30, 5))
	var maple := _mesh(world, "kit-crimson-maple-3", atlas, Vector3(9, 9, 9), Vector3(20, 18, 40))
	var maple_twin := MeshInstance3D.new()
	maple_twin.name = "kit-crimson-maple-4"
	maple_twin.mesh = maple.mesh
	maple_twin.position = Vector3(-35, 17, 90)
	world.add_child(maple_twin)
	var shrub := _mesh(world, "kit-autumn-shrub-2", shrub_atlas, Vector3(2, 2, 2), Vector3(3, 18, 3))
	var flower := _mesh(world, "kit-flower-shrub-1", flower_atlas, Vector3(1, 1, 1), Vector3(4, 18, 4))
	var litter := _mesh(world, "kit-fallen-leaves-1", litter_atlas, Vector3(4, 0.1, 4), Vector3(5, 18, 5))
	var pines := _mesh(world, "Scenery_WindPines_12", pine_colour, Vector3(74, 4, 65), Vector3.ZERO)
	var merged := _mesh(world, "Grove_Merged_1", leaves, Vector3(60, 4, 50), Vector3.ZERO)
	var patch := _mesh(world, "AuthoredGround_test_ground-31_test_4_5", ground, Vector3(4, 0.2, 4), Vector3.ZERO)
	# A static batch of two firs: the members are hidden and the MultiMesh
	# draws them.
	var fir_atlas := atlas.duplicate() as StandardMaterial3D
	var fir_a := _mesh(world, "kit-dark-fir-1", fir_atlas, Vector3(5, 12, 5), Vector3(50, 20, 50))
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

	# Off: nothing changes, and OccluderFade blends as on develop.
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	_expect(LookFoliage.paint_loaded(world, continent) == 0 and LookFoliage.paint(world) == 0,
		"with ELORIA_LOOK=0 nothing is painted")
	_expect(canopy.get_surface_override_material(0) == null
		and maple.get_surface_override_material(0) == null and batch.material_override == null,
		"with ELORIA_LOOK=0 the crowns keep the loader's materials")
	var off_fade := _fade_of(world, wood)
	off_fade.apply()
	var off_copy := wood.get_surface_override_material(0) as BaseMaterial3D
	_expect(off_copy != null and off_copy.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA
		and wood.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		and wood.get_child_count() == 0,
		"with ELORIA_LOOK=0 an occluder blends and keeps its own shadow, as on develop")
	off_fade.restore()
	_expect(wood.get_surface_override_material(0) == null, "and is put back after")
	_expect(_indexed(world) == _mesh_count(world),
		"with ELORIA_LOOK=0 the look keeps nothing out of the index: every mesh develop weighs is indexed")

	# On.
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_expect(LookFoliage.paint_loaded(world, island) == 0,
		"a map outside the continent is not painted")
	var painted_count := LookFoliage.paint_loaded(world, continent)
	var canopy_paint := canopy.get_surface_override_material(0) as ShaderMaterial
	var maple_paint := maple.get_surface_override_material(0) as ShaderMaterial
	_expect(canopy_paint != null and canopy_paint.shader == LookFoliage.SHADER_CUTOUT,
		"an authored canopy is painted with the alpha-cut shader")
	_expect(canopy_paint != null
		and is_equal_approx(float(canopy_paint.get_shader_parameter(&"alpha_scissor_threshold")), 0.4),
		"and keeps its cutout threshold")
	_expect(maple_paint != null and maple_paint.shader == LookFoliage.SHADER_OPAQUE,
		"a kit tree is painted with the opaque shader")
	_expect(wood.get_surface_override_material(0) == null,
		"a timber crate is not painted")
	var trunk_paint := trunk.get_surface_override_material(0) as ShaderMaterial
	_expect(trunk_paint != null and trunk_paint.shader == LookFoliage.SHADER_CHROMA
		and is_equal_approx(float(trunk_paint.get_shader_parameter(&"look_near_cut")),
			0.0)
		and is_equal_approx(float(trunk_paint.get_shader_parameter(&"look_chroma")), 1.0)
		and trunk_paint.get_meta(LookFade.FADED_SHADER_META) == LookFade.SHADER_STANDARD,
		"a tree trunk keeps its bark and is not cut by camera distance")
	_expect(litter.get_surface_override_material(0) == null,
		"fallen leaves on the ground are not a crown")
	_expect(pines.get_surface_override_material(0) == null
		and merged.get_surface_override_material(0) == null,
		"a merged scatter mesh and a vertex-coloured one are left alone")
	_expect(patch.get_surface_override_material(0) == null,
		"ground is never painted as a crown, whatever its material")
	_expect(canopy_paint.get_shader_parameter(&"look_near_fade") == Vector2.ZERO
		and maple_paint.get_shader_parameter(&"look_near_fade") == Vector2.ZERO,
		"nearby crowns stay visible when they do not obstruct the player")
	var maple_min: Vector3 = maple_paint.get_shader_parameter(&"look_crown_min")
	var canopy_min: Vector3 = canopy_paint.get_shader_parameter(&"look_crown_min")
	_expect(is_equal_approx(maple_min.y, 9.0 * LookProfile.CROWN_FLOOR)
		and is_equal_approx(canopy_min.y, 0.0),
		"a kit tree's crown starts at CROWN_FLOOR of its height, a canopy's at its foot")
	var shrub_paint := shrub.get_surface_override_material(0) as ShaderMaterial
	var flower_paint := flower.get_surface_override_material(0) as ShaderMaterial
	_expect(shrub_paint != null and is_equal_approx(
			(shrub_paint.get_shader_parameter(&"look_crown_min") as Vector3).y, 0.0)
		and float(shrub_paint.get_shader_parameter(&"look_tame")) == 1.0,
		"a shrub is crown from the ground up, and tamed")
	_expect(flower_paint != null and float(flower_paint.get_shader_parameter(&"look_tame")) == 0.0,
		"blossom keeps its hue")
	_expect(_properties(leaves) == leaves_before and _properties(atlas) == atlas_before
		and maple.mesh.surface_get_material(0) == atlas,
		"the source materials and meshes are never edited")
	_expect(canopy_paint.get_meta(LookFade.FADED_SHADER_META) == LookFoliage.SHADER_CUTOUT_FADED
		and maple_paint.get_meta(LookFade.FADED_SHADER_META) == LookFoliage.SHADER_OPAQUE_FADED,
		"every painted crown names its dithered variant")
	_expect(LookFoliage.paint(world) == 0 and canopy.get_surface_override_material(0) == canopy_paint,
		"painting a root twice changes nothing")
	_expect(painted_count == 8, "seven crown surfaces and a trunk are painted (got %d)" % painted_count)

	# Seeds: from the position in the region, not the world, and in variants.
	var seed_a := LookFoliage.seed_of(maple, world)
	world.position = Vector3(1200, -40, -800)
	world.rotation = Vector3(0, 0.7, 0)
	_expect(is_equal_approx(LookFoliage.seed_of(maple, world), seed_a),
		"a crown's seed does not move when the world is rebased")
	world.transform = Transform3D.IDENTITY
	var maple_seed := float(maple_paint.get_shader_parameter(&"look_seed"))
	_expect(is_equal_approx(maple_seed * LookProfile.CROWN_JITTER_VARIANTS,
			roundf(maple_seed * LookProfile.CROWN_JITTER_VARIANTS)),
		"a crown's seed is one of CROWN_JITTER_VARIANTS")
	var twin_paint := maple_twin.get_surface_override_material(0) as ShaderMaterial
	_expect(twin_paint != null and (twin_paint == maple_paint) == is_equal_approx(
			float(twin_paint.get_shader_parameter(&"look_seed")), maple_seed),
		"copies of a kit tree share a material exactly when they share a seed")

	# Batches: the MultiMesh and its hidden members draw the same crown.
	var batch_paint := batch.material_override as ShaderMaterial
	var member_paint := fir_b.get_surface_override_material(0) as ShaderMaterial
	_expect(batch_paint != null and member_paint != null
		and batch_paint.shader == LookFoliage.SHADER_OPAQUE,
		"a batch of crowns and its members are painted")
	var batch_seed := float(batch_paint.get_shader_parameter(&"look_seed"))
	_expect(is_equal_approx(float(member_paint.get_shader_parameter(&"look_seed")),
			fposmod(batch_seed + LookFoliage.INSTANCE_SEED_STEP, 1.0)),
		"a member's seed is the one the batch's shader gives its instance")

	# The dithered fade.
	var fade := _fade_of(world, canopy)
	fade.apply()
	var faded := canopy.get_surface_override_material(0) as ShaderMaterial
	_expect(faded != null and faded != canopy_paint
		and faded.shader == LookFoliage.SHADER_CUTOUT_FADED,
		"a faded painted crown swaps to a copy with the dithered shader")
	_expect(faded != null and faded.get_shader_parameter(&"look_crown_max")
			== canopy_paint.get_shader_parameter(&"look_crown_max"),
		"and the copy keeps the crown's paint")
	_expect(canopy.get_node_or_null(NodePath(String(LookFade.SHADOW_TWIN_NAME))) == null
		and canopy.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"while a crown fades it casts no shadow and has no twin, as on develop")
	_expect(faded != null and is_zero_approx(float(faded.get_shader_parameter(&"look_fade_open")))
		and is_equal_approx(float(faded.get_shader_parameter(&"look_fade_hole_metres")),
			LookProfile.FADE_HOLE_METRES),
		"a fresh faded copy starts whole, with the profile's hole")
	LookFade.focus = Vector3(1.0, 2.0, 3.0)
	fade.fade = 1.0
	fade.write_alpha()
	_expect(is_equal_approx(float(faded.get_shader_parameter(&"look_fade")),
			OccluderFade.FADED_ALPHA)
		and is_equal_approx(float(faded.get_shader_parameter(&"look_fade_open")), 1.0)
		and faded.get_shader_parameter(&"look_fade_focus") == Vector3(1.0, 2.0, 3.0),
		"the fade opens the hole at the focus")
	_expect(is_equal_approx(float(canopy_paint.get_shader_parameter(&"look_fade")), 1.0)
		and canopy_paint.get_shader_parameter(&"look_fade_open") == null,
		"the shared painted material is never faded")
	fade.restore()
	_expect(canopy.get_surface_override_material(0) == canopy_paint
		and canopy.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		and canopy.get_node_or_null(NodePath(String(LookFade.SHADOW_TWIN_NAME))) == null,
		"restoring puts the painted crown and its own shadow back and drops the twin")

	# A StandardMaterial3D dithers through look_faded_standard.
	bark.normal_enabled = true
	bark.normal_scale = 0.7
	bark.roughness = 0.6
	bark.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	var wood_fade := _fade_of(world, wood)
	wood_fade.apply()
	var standard := wood.get_surface_override_material(0) as ShaderMaterial
	_expect(standard != null and standard.shader == LookFade.SHADER_STANDARD,
		"a faded one-sided StandardMaterial3D dithers through look_faded_standard")
	var wood_shadow := wood.get_node_or_null(NodePath(String(LookFade.SHADOW_TWIN_NAME))) as MeshInstance3D
	_expect(wood_shadow != null
		and wood_shadow.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
		and wood_shadow.get_surface_override_material(0) == null
		and wood.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF,
		"while a wall or trunk fades a twin casts its resting shadow and it casts none")
	_expect(standard != null
		and is_equal_approx(float(standard.get_shader_parameter(&"normal_scale")), 0.7)
		and is_equal_approx(float(standard.get_shader_parameter(&"roughness_value")), 0.6)
		and standard.get_shader_parameter(&"roughness_channel") == Vector4(0, 1, 0, 0),
		"and carries the source's own properties")
	wood_fade.restore()
	_expect(wood.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		and wood.get_node_or_null(NodePath(String(LookFade.SHADOW_TWIN_NAME))) == null
		and not wood.has_meta(LookFade.SHADOW_META),
		"restoring gives the wall its own shadow back and drops the twin")
	var triplanar := StandardMaterial3D.new()
	triplanar.uv1_triplanar = true
	_expect(LookFade.dither_copy(triplanar) == null,
		"a material the stand-in cannot reproduce keeps develop's blend")
	var two_sided := StandardMaterial3D.new()
	two_sided.cull_mode = BaseMaterial3D.CULL_DISABLED
	two_sided.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	var two_sided_copy := LookFade.dither_copy(two_sided)
	_expect(two_sided_copy != null and two_sided_copy.shader == LookFade.SHADER_STANDARD_TWO_SIDED
		and int(two_sided_copy.get_shader_parameter(&"alpha_mode")) == 1,
		"a two-sided alpha-cut one keeps both")
	var foreign := ShaderMaterial.new()
	foreign.shader = Shader.new()
	_expect(LookFade.dither_copy(foreign) == null,
		"any other ShaderMaterial stays solid, as on develop")

	# The ground is never an occluder with the pass on.
	_expect(_indexed(world) == _mesh_count(world, true) and not _is_indexed(world, patch),
		"with the look on (the default) a ground patch is kept out of the fade index")

	# A kit prop named for a plant is not a crown; a single-sided crown keeps
	# its culling.
	_expect(LookFoliage.kind_of("kit-reed-raft-3", atlas) == LookFoliage.Kind.NONE
		and LookFoliage.kind_of("kit-reed-bed-3", atlas) == LookFoliage.Kind.KIT_SHRUB,
		"a reed raft is a boat, not a shrub")
	LookProfile.define_region("plain_test", {"id": "plain_test", "schema": 1,
		"foliage": {"plain_words": ["hedge"]}})
	_expect(LookFoliage.kind_of("kit-garden-hedge-1", atlas,
			LookFoliage.words_for("plain_test")) == LookFoliage.Kind.NONE
		and LookFoliage.kind_of("kit-garden-hedge-1", atlas) == LookFoliage.Kind.KIT_SHRUB
		and LookFoliage.kind_of("kit-reed-raft-3", atlas,
			LookFoliage.words_for("plain_test")) == LookFoliage.Kind.NONE,
		"a region's plain words keep its hedges out of the crowns, and every map's still apply")
	LookProfile.reload_regions()
	var one_sided := atlas.duplicate() as StandardMaterial3D
	one_sided.cull_mode = BaseMaterial3D.CULL_BACK
	var one_sided_paint := LookFoliage.painted_for(one_sided, LookFoliage.Kind.KIT_TREE,
		_mesh(world, "kit-steppe-tree-1", one_sided, Vector3(3, 5, 3), Vector3.ZERO).mesh)
	_expect(one_sided_paint != null and one_sided_paint.shader == LookFoliage.SHADER_OPAQUE_BACK
		and one_sided_paint.get_meta(LookFade.FADED_SHADER_META) == LookFoliage.SHADER_OPAQUE_BACK_FADED,
		"a single-sided crown is painted back-face culled, and fades so")

	# Occluders blend as on develop on an interior, and when a hole could not
	# open most of them; a crown and a cottage keep the hole.
	var roof := _mesh(world, "Roof_giant_dome", bark, Vector3(40, 8, 40), Vector3(0, 20, 0))
	var cottage := _mesh(world, "Roof_cottage", bark, Vector3(10, 4, 8), Vector3(0, 10, 0))
	LookFade.bind(island)
	_expect(not LookFade.keeps_hole(roof) and LookFade.keeps_hole(cottage)
		and LookFade.keeps_hole(canopy) and LookFade.dither_copy(bark, roof) == null,
		"outdoors a giant dome blends; a cottage's roof and a crown keep the hole")
	# How the rest fade: a roof beside the player keeps its hole and vanishes
	# once the player is under it; a pillar and a wall vanish; water blends.
	var focus_before := LookFade.focus
	LookFade.focus = Vector3(60, 1.5, -60)
	_expect(LookFade.mode_of(cottage) == LookFade.Mode.HOLE
		and LookFade.mode_of(canopy) == LookFade.Mode.HOLE,
		"a roof beside the player and a crown keep the hole")
	LookFade.focus = Vector3(1, 1.5, 1)
	_expect(LookFade.mode_of(cottage) == LookFade.Mode.VANISH
		and LookFade.mode_of(canopy) == LookFade.Mode.HOLE,
		"a roof over the player vanishes; a crown over the player keeps its hole")
	var pillar := _mesh(world, "Gate_pillar", bark, Vector3(1.5, 9, 1.5), Vector3(30, 0, 30))
	var wall := _mesh(world, "Wall_run", bark, Vector3(12, 5, 1), Vector3(-30, 0, -30))
	var pool := _mesh(world, "Water_BogPool_1", bark, Vector3(20, 0.1, 20), Vector3(-60, 0, 60))
	_expect(LookFade.mode_of(pillar) == LookFade.Mode.VANISH
		and LookFade.mode_of(wall) == LookFade.Mode.VANISH
		and LookFade.mode_of(pool) == LookFade.Mode.BLEND,
		"a pillar and a wall vanish; water blends as on develop")
	var vanished := LookFade.dither_copy(bark, pillar)
	_expect(vanished != null
		and float(vanished.get_shader_parameter(LookFade.WHOLE_PARAMETER)) == 1.0,
		"a vanishing copy dissolves the whole mesh")
	pool.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	_expect(LookFade.hold_shadow(pool) == null
		and pool.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		and not pool.has_meta(LookFade.SHADOW_META),
		"a blended occluder keeps develop's shadow: no twin, still casting")
	LookFade.release_shadow(pool, null)
	_expect(not pool.has_meta(LookFade.MODE_META), "releasing forgets the fade's mode")
	pillar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	_expect(LookFade.hold_shadow(pillar) == null
		and pillar.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		and pillar.get_node_or_null(NodePath(String(LookFade.SHADOW_TWIN_NAME))) == null,
		"a vanishing occluder casts no shadow and has no twin")
	LookFade.release_shadow(pillar, null)
	_expect(pillar.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_ON,
		"and casts again once it is back")
	# A landmark the bound region names (props.hole_words) keeps a hole where
	# it would vanish; the same mesh vanishes on a map whose file names none.
	LookProfile.define_region("hole_test", {"id": "hole_test", "schema": 1,
		"props": {"hole_words": ["kit-sw-palace-keep"]}})
	var landmark_map := WorldManifest.new()
	landmark_map.data = {"asset": {"id": "hole_test"}, "environment": {"sun": {"enabled": true}}}
	var keep_tower := _mesh(world, "kit-sw-palace-keep", bark, Vector3(10, 30, 10), Vector3(0, 0, 0))
	LookFade.bind(landmark_map)
	var kept_mode := LookFade.mode_of(keep_tower)
	var kept_preview := LookFade.keeps_named_hole("StreamView_3__kit-sw-palace-keep")
	# ...unless it fills the view: a camera right behind it still loses it.
	var close_camera := Camera3D.new()
	world.add_child(close_camera)
	close_camera.position = Vector3(0, 12, 9)
	close_camera.look_at(Vector3(0, 10, 0), Vector3.UP)
	var far_camera := Camera3D.new()
	world.add_child(far_camera)
	far_camera.position = Vector3(0, 60, 220)
	far_camera.look_at(Vector3(0, 10, 0), Vector3.UP)
	var filling_mode := LookFade.mode_of(keep_tower, close_camera)
	var far_mode := LookFade.mode_of(keep_tower, far_camera)
	close_camera.queue_free()
	far_camera.queue_free()
	LookFade.bind(island)
	_expect(kept_mode == LookFade.Mode.HOLE and kept_preview
		and LookFade.mode_of(keep_tower) == LookFade.Mode.VANISH
		and not LookFade.keeps_named_hole("kit-sw-palace-keep"),
		"a landmark its region names keeps a hole over the player; unnamed, it vanishes")
	_expect(filling_mode == LookFade.Mode.VANISH and far_mode == LookFade.Mode.HOLE,
		"a named landmark that fills the camera's view still vanishes; seen from afar it keeps its hole")
	LookFade.focus = focus_before

	# A region's signature materials keep their chroma (props.keep_words).
	LookProfile.define_region("chroma_test", {"id": "chroma_test", "schema": 1,
		"props": {"keep_words": ["crystal"]}})
	var crystal_material := StandardMaterial3D.new()
	crystal_material.resource_name = "amethyst_crystal"
	crystal_material.albedo_color = Color(0.6, 0.4, 0.8)
	var crystal := _mesh(world, "Prop_crystal_1", crystal_material, Vector3(1, 2, 1),
		Vector3(5, 0, 5))
	_expect(LookFoliage.keep_chroma(world, "no_such_map") == 0
		and crystal.get_surface_override_material(0) == null,
		"a region that names no signature materials keeps none")
	_expect(LookFoliage.keep_chroma(world, "chroma_test") == 1,
		"only the material named with a keep word is kept")
	var kept := crystal.get_surface_override_material(0) as ShaderMaterial
	var expected_chroma := LookProfile.KEEP_CHROMA_FORWARD if LookProfile.forward_plus() \
		else LookProfile.KEEP_CHROMA
	_expect(kept != null and kept.shader == LookFoliage.SHADER_CHROMA
		and is_equal_approx(float(kept.get_shader_parameter(&"look_chroma")), expected_chroma)
		and kept.get_shader_parameter(&"albedo_color") == Color(0.6, 0.4, 0.8)
		and kept.get_meta(LookFade.FADED_SHADER_META) == LookFade.SHADER_STANDARD
		and crystal_material.albedo_color == Color(0.6, 0.4, 0.8),
		"a kept material is drawn by the chroma stand-in and fades as a standard one")
	LookProfile.reload_regions()
	var interior := WorldManifest.new()
	interior.data = {"environment": {"sun": {"enabled": false}}}
	LookFade.bind(interior)
	_expect(not LookFade.keeps_hole(cottage)
		and LookFade.mode_of(canopy) == LookFade.Mode.VANISH,
		"on an interior everything blends, but a look stand-in, which has no blended copy, dissolves")
	var sunlit_inside := WorldManifest.new()
	sunlit_inside.data = {"asset": {"interiorClass": "gauntlet"},
		"environment": {"sun": {"enabled": true}}}
	LookFade.bind(sunlit_inside)
	_expect(LookFade.blend_only, "a sunlit interior (an interiorClass) blends too")
	LookFade.bind(island)

	world.queue_free()
	if previous.is_empty():
		OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	else:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	print("test_look_foliage: %s (%d failures)" % ["PASS" if failures == 0 else "FAIL", failures])
	quit(1 if failures > 0 else 0)

## A box-shaped mesh of `size`, foot at its origin, placed at `at`.
func _mesh(parent: Node, node_name: String, material: Material, size: Vector3,
		at: Vector3) -> MeshInstance3D:
	var box := BoxMesh.new()
	box.size = size
	var tool := SurfaceTool.new()
	tool.create_from(box, 0)
	var arrays := tool.commit_to_arrays()
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	for index: int in vertices.size():
		vertices[index].y += size.y * 0.5
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.position = at
	parent.add_child(node)
	return node

## The OccluderFade record for one node, as its index builds it.
func _fade_of(world: Node3D, node: MeshInstance3D) -> OccluderFade.Occluder:
	var fade := OccluderFade.new()
	fade.configure(null, world)
	for occluder: OccluderFade.Occluder in fade._occluders:
		if occluder.node == node:
			return occluder
	var record := OccluderFade.Occluder.new()
	record.node = node
	return record

func _indexed(world: Node3D) -> int:
	var fade := OccluderFade.new()
	return fade.configure(null, world)

func _is_indexed(world: Node3D, node: MeshInstance3D) -> bool:
	var fade := OccluderFade.new()
	fade.configure(null, world)
	for occluder: OccluderFade.Occluder in fade._occluders:
		if occluder.node == node:
			return true
	return false

## Meshes OccluderFade would weigh at all: visible, narrower than its cap, and
## not ground by OccluderFade's own name test - nor, with `look_ground`, by
## the look's (LookFade.keeps_solid). Develop's 296afdc1a ("Keep authored
## ground patches from fading under the player") adds that name test as
## OccluderFade.GROUND_NAME_PREFIXES; before it, every ground patch was
## weighed. The constant is read from the script, not named, so this count
## is develop's on either side of that merge.
func _mesh_count(world: Node3D, look_ground := false) -> int:
	var fade_script: Script = load("res://src/world/occluder_fade.gd")
	var ground_prefixes: Array = fade_script.get_script_constant_map().get("GROUND_NAME_PREFIXES", [])
	var count := 0
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		var node_name := String(mesh_instance.name)
		if node_name == String(LookFade.SHADOW_TWIN_NAME):
			continue
		if ground_prefixes.any(func(prefix: Variant) -> bool: return node_name.begins_with(str(prefix))):
			continue
		if look_ground and LookFade.keeps_solid(node_name):
			continue
		var box := mesh_instance.get_aabb()
		if maxf(box.size.x, box.size.z) <= OccluderFade.MAX_EXTENT_METRES:
			count += 1
	return count

func _properties(material: StandardMaterial3D) -> Array:
	return [material.albedo_color, material.transparency, material.cull_mode,
		material.roughness, material.alpha_scissor_threshold, material.get_meta_list()]

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
