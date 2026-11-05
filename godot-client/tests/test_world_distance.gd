extends SceneTree

## The runtime world distance pass (wave 2 WD-C3).
##
## WorldDistance.apply_loaded classes what a loaded continent territory, chunk
## or gauntlet draws: class-split static batches, pooled prototype placements
## and the package's own meshes join one SceneTree group per size class and
## extent step and take a visibility range measured from the camera's focus;
## small and flat pieces, ground patches, flat walk decks and (beside an
## opaque base) Terrain_ stop casting the sun's shadow, a batch's hidden
## members with it; every classed node takes the quality's LOD bias. The
## WorldDistance node re-applies the ranges with set_group when the camera
## bucket, the quality or a film changes it, and when a tree stamped with
## another state enters the scene.
##
## Checked here on hand-built worlds: the table and its helpers, classes,
## groups and ranges at 26/90 m LOW/HIGH, the focus guarantee (no member
## within reach of the focus is ever culled, batches included), ground never
## ranged, the shadow rules incl. hidden members, what is left alone
## (collision carriers, hidden, shadow-only, authored ranges, stream previews,
## water), idempotence, ELORIA_WORLD_DISTANCE=off, the map scope, the node's
## re-applies (zoom, quality, film, a stale chunk, a re-adopted park), the
## snapshot the camera probe reads, and the loader's cache snapshot packing
## the loader's own values.
##
## Run: Godot_v4.7.2-stable_win64.exe --headless --path . \
##         --script tests/test_world_distance.gd

const Classes := preload("res://src/world/world_distance_classes.gd")
const WorldDistance := preload("res://src/world/world_distance.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const CONTINENT := {"continentGeography": {"geometryMode": "continent-chunks-v1"}}
const GAUNTLET := {"gauntlet": {"id": "test"}}
const ON := GeometryInstance3D.SHADOW_CASTING_SETTING_ON
const OFF := GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
const HIGH := LookProfile.Quality.HIGH
const LOW := LookProfile.Quality.LOW

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.unset_environment(HardwareTier.WORLD_DISTANCE_VARIABLE)
	WorldDistance.reset_state()
	_check_table()
	_check_ground_names()
	_check_state_before_publish()
	await _check_pass()
	await _check_objects()
	await _check_focus_guarantee()
	await _check_low_and_film()
	await _check_terrain_rule()
	await _check_idempotent()
	await _check_switch_and_scope()
	await _check_node()
	await _check_cache_snapshot()
	await _check_loader_paths()
	await _check_worker_build()
	WorldDistance.reset_state()
	print("world distance tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------

func _check_table() -> void:
	_expect(Classes.REACH_METRES == {"S": 30.0, "M": 70.0, "L": 160.0, "XL": 0.0}
		and Classes.TIER_REACH_SCALE == {"HIGH": 1.0, "MEDIUM": 0.8, "LOW": 0.6}
		and Classes.LOD_BIAS == {"HIGH": 1.0, "MEDIUM": 0.4, "LOW": 0.15},
		"the plan's reaches, tier scales and LOD biases")
	_expect(Classes.camera_bucket(26.0) == 32.0 and Classes.camera_bucket(24.0) == 24.0
		and Classes.camera_bucket(90.0) == 96.0 and Classes.camera_bucket(1.5) == 8.0
		and Classes.camera_bucket(0.0) == 8.0, "the orbit distance rounds up to 8 m steps")
	_expect(is_equal_approx(Classes.reach_metres("S", "LOW"), 18.0)
		and is_equal_approx(Classes.reach_metres("M", "medium"), 56.0)
		and Classes.reach_metres("XL", "HIGH") == 0.0, "reach x tier scale; XL has none")
	_expect(Classes.extent_step(0.0) == 0 and Classes.extent_step(0.5) == 1
		and Classes.extent_step(4.0) == 1 and Classes.extent_step(4.1) == 2
		and Classes.extent_step(128.0) == 32 and Classes.extent_step(129.0) == -1,
		"extents round up to 4 m steps; past 32 steps nothing is ranged")
	# 26 m HIGH: bucket 32. S, extent step 2: 32 + 30 + 8 + 4.
	_expect(is_equal_approx(Classes.range_end("S", 2, 32.0, "HIGH"), 74.0)
		and is_equal_approx(Classes.range_end("L", 0, 96.0, "HIGH"), 260.0)
		and is_equal_approx(Classes.range_end("S", 0, 32.0, "LOW"), 54.0)
		and is_equal_approx(Classes.range_end("M", 3, 96.0, "LOW"), 96.0 + 42.0 + 12.0 + 4.0)
		and Classes.range_end("XL", 0, 32.0, "HIGH") == 0.0
		and Classes.range_end("S", -1, 32.0, "HIGH") == 0.0,
		"range end = bucket + reach x scale + extent step + margin (26/90 m, LOW/HIGH)")
	_expect(Classes.is_flat(0.2, 3.0) and Classes.is_flat(0.11, 4.0) and Classes.is_flat(0.5, 4.0)
		and not Classes.is_flat(1.0, 3.0) and not Classes.is_flat(0.5, 1.0),
		"flat: under 0.35 m, or under 0.15 x the footprint's narrower width")
	# The footprint's narrower width, whatever the placement's heading.
	var turned := Basis(Vector3.UP, deg_to_rad(30.0))
	_expect(is_equal_approx(Classes.footprint_width(Vector3(8, 1, 0.2), Basis()), 0.2)
		and is_equal_approx(Classes.footprint_width(Vector3(8, 1, 0.2), turned), 0.2)
		and is_equal_approx(Classes.footprint_width(Vector3(8, 1, 0.2), Basis(Vector3.UP, PI / 4.0)), 0.2)
		and is_equal_approx(Classes.footprint_width(Vector3(4, 1, 6), turned.scaled(Vector3(2, 2, 2))), 8.0)
		and is_equal_approx(Classes.footprint_width(Vector3(3, 0.1, 3), Basis(Vector3.RIGHT, PI / 2.0)), 0.1),
		"footprint width: turned copies agree, scale counts, a slab stood on edge is narrow")
	# Pieces the shipped maps hold (WD-C3 review probe over Landfall and
	# Coilmere): a sea wall segment and a fence are long and low but not flat;
	# a causeway floor and a lotus pad are.
	var flat_of := func(size: Vector3, basis: Basis) -> bool:
		return Classes.is_flat((Transform3D(basis, Vector3.ZERO) * AABB(-size * 0.5, size)).size.y,
			Classes.footprint_width(size, basis))
	_expect(not flat_of.call(Vector3(11.56, 1.4, 1.38), Basis())
		and not flat_of.call(Vector3(11.56, 1.4, 1.38), Basis(Vector3.UP, PI / 4.0))
		and not flat_of.call(Vector3(8, 1, 0.2), Basis(Vector3.UP, 0.3))
		and not flat_of.call(Vector3(6.4, 1.06, 4.0), Basis(Vector3.UP, 1.85))
		and flat_of.call(Vector3(10.56, 0.11, 5.49), Basis(Vector3.UP, -2.04))
		and flat_of.call(Vector3(3.2, 0.35, 3.26), Basis(Vector3.UP, 2.8))
		and not flat_of.call(Vector3(3, 0.1, 3), Basis(Vector3.RIGHT, PI / 2.0)),
		"sea walls, fences and canopies keep their shadow at any heading; floors and pads are flat")
	# Wide enclosures (integrator fix, WD-C5 observation): a palisade ring, a
	# sheepfold and a Sunmane landmark ring are low against their footprint but
	# keep their walls' shadow; the palisade's 0.75 m floor and scree stay flat.
	_expect(not flat_of.call(Vector3(49.4, 4.86, 48.9), Basis())
		and not flat_of.call(Vector3(9.0, 1.2, 9.0), Basis(Vector3.UP, 0.7))
		and not flat_of.call(Vector3(18.2, 1.28, 20.2), Basis())
		and flat_of.call(Vector3(49.9, 0.75, 49.4), Basis())
		and flat_of.call(Vector3(5.2, 0.5, 3.9), Basis(Vector3.UP, 1.1))
		and Classes.is_flat(0.99, 10.0) and not Classes.is_flat(1.0, 10.0),
		"pieces 1 m tall or more are never flat; lower wide floors and scree still are")
	_expect(Classes.is_structure("AuthoredBridgeSupport_ravenhead__b25-11_01_ravenhead")
		and Classes.is_structure("AuthoredBridgeEdge_landfall__r29-gully-1-01_landfall")
		and Classes.is_structure("kit-sw-causeway-support-b22l-34") and Classes.is_structure("Deck_sw-causeway-arch-tier-floor")
		and Classes.is_structure("kit-rope-Bridge-1") and Classes.is_structure("Walk_ravenhead_trestle_pier_span")
		and not Classes.is_structure("kit-sea-wall-segment-1") and not Classes.is_structure("MarketStall_0__canvas_awning"),
		"bridge and pier structure by name")
	_expect(WorldDistance.BATCH_META == WorldLoader.BATCH_META
		and WorldDistance.BATCH_PATH_META == WorldLoader.BATCH_PATH_META
		and WorldDistance.WORLD_GROUP_PREFIX == WorldLoader.GROUP_NAME_PREFIX,
		"the batch link metas and the grouping prefix match the loader's")
	var state := WorldDistance.state_for(26.0, HIGH)
	_expect(state.bucket == 32.0 and state.quality_name == "HIGH" and not bool(state.detached)
		and state.key == "32_2_0", "a state names its bucket, quality and film flag")

func _check_ground_names() -> void:
	var G := Classes.Ground
	var cases := {"Terrain_landfall_12_11": G.TERRAIN, "Walk_Terrain_x": G.TERRAIN,
		"AuthoredGround_landfallBase_landfall_12_11": G.BASE, "AuthoredGround_landfallBase": G.BASE,
		"AuthoredGround_landfall_castle-town-lawn_landfall_12_11": G.PATCH,
		"AuthoredGround_boarsend_gs-rock-01-p01_boarsend": G.PATCH,
		"Walk_sw-trestle-pier-span-deck": G.DECK, "Water_boarsend_02_10": G.WATER,
		"Scenery_Water_pool": G.WATER, "kit-bracken-patch-1": G.NONE, "Under_006_062": G.NONE,
		"Deck_sw-causeway-arch-tier-floor": G.NONE, "AuthoredBridgeSupport_x": G.NONE}
	var wrong: Array = []
	for node_name: String in cases:
		if Classes.ground_kind(node_name) != cases[node_name]:
			wrong.append(node_name)
	_expect(wrong.is_empty(), "ground kinds by the exporter's names: %s" % [wrong])

# --------------------------------------------------------------------------
# The pass on one world
# --------------------------------------------------------------------------

## A continent chunk: 18 crates (S) and 18 halls (L) batched by the loader in
## class cells, and loose: a rock (S), two bushes (M), a flat slab (M), a tower
## (XL), terrain, an opaque base, a patch, a flat walk deck and a tall pier,
## water, a crate with collision, a hidden crate, a shadow-only crate, a crate
## with its own range and a crate inside a stream preview.
func _world(data: Dictionary, with_base := true) -> Dictionary:
	var world := Node3D.new()
	world.name = "ImportedWorld_wd"
	root.add_child(world)
	var crate := _mesh(Vector3(1, 1, 1))
	var hall := _mesh(Vector3(12, 4, 12))
	var nodes := {}
	for index: int in 20:
		_place(world, "Crate_%02d" % index, crate, Transform3D(Basis(), Vector3(index * 10.0, 0.0, 0.0)))
		_place(world, "Hall_%02d" % index, hall,
			Transform3D(Basis(Vector3.UP, index * 0.3), Vector3(index * 10.0, 2.0, 100.0)))
	nodes.rock = _place(world, "Rock_a", crate, Transform3D(Basis(), Vector3(-50, 0, -50)))
	var holder := Node3D.new()
	holder.name = "Authored_bush_WorldPlacement"
	holder.position = Vector3(-60, 0, -40)
	world.add_child(holder)
	nodes.bush = _place(holder, "kit-bush-1", _mesh(Vector3(3, 2, 3)), Transform3D.IDENTITY)
	nodes.big_bush = _place(world, "kit-bush-2", _mesh(Vector3(3, 2, 3)),
		Transform3D(Basis().scaled(Vector3(2, 2, 2)), Vector3(-80, 0, -40)))
	nodes.slab = _place(world, "Slab_floor", _mesh(Vector3(5, 0.1, 5)), Transform3D(Basis(), Vector3(-70, 0, 0)))
	nodes.tower = _place(world, "Landmark_tower", _mesh(Vector3(10, 30, 10)), Transform3D(Basis(), Vector3(-90, 0, 0)))
	nodes.terrain = _place(world, "Terrain_wd_00_00", _mesh(Vector3(100, 4, 100)), Transform3D.IDENTITY)
	if with_base:
		nodes.base = _place(world, "AuthoredGround_wdBase_wd_00_00", _mesh(Vector3(100, 4, 100)),
			Transform3D(Basis(), Vector3(0, 0.006, 0)))
	nodes.patch = _place(world, "AuthoredGround_wd_meadow-01_wd", _mesh(Vector3(20, 0.5, 20)), Transform3D.IDENTITY)
	nodes.deck = _place(world, "Walk_wd_jetty-deck", _mesh(Vector3(10, 0.2, 3)), Transform3D(Basis(), Vector3(0, 0, -30)))
	nodes.pier = _place(world, "Walk_wd_trestle_pier_span", _mesh(Vector3(8, 7, 10)), Transform3D(Basis(), Vector3(20, 0, -30)))
	nodes.water = _place(world, "Water_wd_00_00", _mesh(Vector3(100, 0.1, 100)), Transform3D.IDENTITY)
	nodes.collider = _place(world, "Crate_collider", crate, Transform3D(Basis(), Vector3(-20, 0, -20)))
	var body := StaticBody3D.new()
	body.name = "Crate_collider_Collision"
	nodes.collider.add_child(body)
	nodes.hidden = _place(world, "Crate_hidden", crate, Transform3D(Basis(), Vector3(-25, 0, -20)))
	nodes.hidden.visible = false
	nodes.shadow_only = _place(world, "Crate_shadow", crate, Transform3D(Basis(), Vector3(-30, 0, -20)))
	nodes.shadow_only.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
	nodes.authored = _place(world, "Crate_authored", crate, Transform3D(Basis(), Vector3(-35, 0, -20)))
	nodes.authored.visibility_range_end = 15.0
	var preview := Node3D.new()
	preview.name = "StreamPreview_next"
	world.add_child(preview)
	nodes.preview = _place(preview, "Crate_preview", crate, Transform3D(Basis(), Vector3(-40, 0, -20)))
	var loader := WorldLoader.new()
	loader.manifest = WorldManifest.new()
	loader.manifest.data = data.duplicate(true)
	loader.world_root = world
	await process_frame
	# The loader's own batching: the collider is not batchable (a child), the
	# rest of the crates and halls batch as WD-C2 builds them.
	loader.call("_batch_static_instances", world.find_children("*", "MeshInstance3D", true, false))
	return {"world": world, "loader": loader, "nodes": nodes}

func _check_pass() -> void:
	var built := await _world(CONTINENT)
	var world: Node3D = built.world
	var nodes: Dictionary = built.nodes
	var state := WorldDistance.state_for(26.0, HIGH)
	var result := WorldDistance.apply_root(world, state)
	var batches := _batches(world)
	var by_class := {}
	for batch: MultiMeshInstance3D in batches:
		var cls := str(batch.get_meta(Classes.CLASS_META, ""))
		by_class[cls] = int(by_class.get(cls, 0)) + 1
		var group := _wd_group(batch)
		_expect(not group.is_empty() and group.begins_with("rl_wd_%s_" % cls),
			"%s joins its class's group (%s)" % [batch.name, group])
		_expect(batch.visibility_range_end > 0.0 and is_equal_approx(batch.visibility_range_end_margin, 4.0)
			and batch.visibility_range_fade_mode == GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED,
			"%s is ranged with a 4 m margin and no fade" % batch.name)
		var expected := OFF if cls == "S" else ON
		_expect(batch.cast_shadow == expected, "%s: %s batches %s" % [batch.name, cls,
			"cast no shadow" if expected == OFF else "keep their shadow"])
		var members := _members(world, batch)
		_expect(not members.is_empty() and members.all(func(member: MeshInstance3D) -> bool:
			return member.cast_shadow == expected and not member.visible),
			"%s: its hidden members cast as the batch does" % batch.name)
		_expect(is_equal_approx(batch.lod_bias, 1.0), "HIGH bias 1.0")
	_expect(by_class == {"S": 6, "L": 3}, "the loader's class cells: %s" % [by_class])
	# One S batch: x 0-30 (four crates), box x -0.5..30.5 -> extent ~15.5 -> step 4.
	var first := world.get_node("StaticBatch_0_Crate_00") as MultiMeshInstance3D
	_expect(_wd_group(first) == "rl_wd_S_4" and is_equal_approx(first.visibility_range_end, 32.0 + 30.0 + 16.0 + 4.0),
		"a 31 m S cell reaches bucket + 30 + 16 + 4 m (%s, %.1f)" % [_wd_group(first), first.visibility_range_end])
	# Loose props.
	var rock := nodes.rock as MeshInstance3D
	_expect(_wd_group(rock) == "rl_wd_S_1" and rock.cast_shadow == OFF
		and is_equal_approx(rock.visibility_range_end, 32.0 + 30.0 + 4.0 + 4.0),
		"a loose S rock: ranged, no shadow (%s %.1f)" % [_wd_group(rock), rock.visibility_range_end])
	var bush := nodes.bush as MeshInstance3D
	_expect(_wd_group(bush).begins_with("rl_wd_M_") and bush.cast_shadow == ON,
		"a bush under a placement node: M, ranged, keeps its shadow (%s)" % _wd_group(bush))
	var big := nodes.big_bush as MeshInstance3D
	_expect(_wd_group(big).begins_with("rl_wd_L_"), "the placement's scale decides the class (%s)" % _wd_group(big))
	var slab := nodes.slab as MeshInstance3D
	_expect(_wd_group(slab).begins_with("rl_wd_M_") and slab.cast_shadow == OFF,
		"a flat 5 m slab (M) casts no shadow (%s)" % _wd_group(slab))
	var tower := nodes.tower as MeshInstance3D
	_expect(tower.is_in_group(WorldDistance.LOD_GROUP) and tower.visibility_range_end == 0.0
		and tower.cast_shadow == ON, "XL: the LOD group only, never culled, keeps its shadow")
	# Ground.
	for key: String in ["terrain", "base", "patch", "deck", "pier", "water"]:
		var ground := nodes[key] as MeshInstance3D
		_expect(_wd_group(ground).is_empty() and not ground.is_in_group(WorldDistance.LOD_GROUP)
			and ground.visibility_range_end == 0.0, "%s is never ranged" % key)
	_expect((nodes.terrain as MeshInstance3D).cast_shadow == OFF, "Terrain_ beside an opaque base casts no shadow")
	_expect((nodes.base as MeshInstance3D).cast_shadow == ON, "the base keeps the ground's shadow")
	_expect((nodes.patch as MeshInstance3D).cast_shadow == OFF, "a ground patch casts no shadow")
	_expect((nodes.deck as MeshInstance3D).cast_shadow == OFF, "a flat walk deck casts no shadow")
	_expect((nodes.pier as MeshInstance3D).cast_shadow == ON, "a tall pier span (Walk_) keeps its shadow")
	_expect((nodes.water as MeshInstance3D).cast_shadow == ON, "water is left alone")
	# Left alone.
	for key: String in ["collider", "hidden", "authored", "preview"]:
		var kept := nodes[key] as MeshInstance3D
		_expect(_wd_group(kept).is_empty() and kept.cast_shadow == ON and is_equal_approx(kept.lod_bias, 1.0),
			"%s is left alone" % key)
	_expect((nodes.authored as MeshInstance3D).visibility_range_end == 15.0, "an authored range is kept")
	_expect((nodes.shadow_only as MeshInstance3D).cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
		and _wd_group(nodes.shadow_only).is_empty(), "a shadow-only node is left alone")
	# Loose and ranged: crates 18-19 and halls 18-19 (past the 180 m cell), the
	# rock, both bushes and the slab.
	_expect(int(result.ranged) == 9 + 8 and int(result.lod_only) == 1,
		"counts: 9 batches and 8 loose props ranged, 1 XL (%s)" % [result])
	_expect(world.is_in_group(StringName(WorldDistance.STAMP_PREFIX + "32_2_0")),
		"the root carries the state it was applied under")
	_free(built)

## Before Main publishes a state, a load takes the quality in use at that
## moment, not one remembered from an earlier load.
func _check_state_before_publish() -> void:
	WorldDistance.reset_state()
	var before := LookProfile.player_quality()
	LookProfile.set_player_quality(LOW)
	var first := WorldDistance.current_state()
	LookProfile.set_player_quality(HIGH)
	var second := WorldDistance.current_state()
	LookProfile.set_player_quality(before)
	_expect(LookProfile.quality_forced() or (int(first.quality) == LOW and int(second.quality) == HIGH
		and float(second.bucket) == 32.0), "an unpublished state follows the quality in use (%s, %s)" % [first, second])
	WorldDistance.reset_state()

## Objects: a material-split cart is one prop (its parts share one class,
## range and shadow), a holder of far-apart meshes is not one object, the
## loader's WorldGroup_ nodes group nothing, bridge structure and lamps are
## never ranged, a dock's post beside its walk deck is never ranged, long low
## walls keep their shadow at any heading, and a batch of parts of objects (with
## the objects' unbatched parts) keeps its shadow and is never ranged.
func _check_objects() -> void:
	var world := Node3D.new()
	world.name = "ImportedWorld_objects"
	root.add_child(world)
	# A cart split by material, as the exporter writes one (Landfall's
	# Camp00_Cart): every part under the cart's node at the same placement.
	var cart := _holder(world, "Cart_0", Vector3(0, 0, 30))
	var turn := Transform3D(Basis(Vector3.UP, 0.7), Vector3.ZERO)
	var body := _place(cart, "Cart_0__timber", _mesh(Vector3(3, 1.5, 2)), turn)
	var wheels := _place(cart, "Cart_0__wheels", _mesh(Vector3(2.4, 1.0, 0.3), Vector3(0, -0.2, 0.8)), turn)
	var metal := _place(cart, "Cart_0__metal", _mesh(Vector3(0.5, 0.5, 0.5), Vector3(1, 0.5, 0)), turn)
	# A section node (a gauntlet's Dress_fort): props of its own placements.
	var section := _holder(world, "Dress_fort", Vector3(0, 0, 60))
	var near := _place(section, "Kit_crate_0_1", _mesh(Vector3(1, 1, 1)), Transform3D.IDENTITY)
	var far := _place(section, "Kit_crate_0_2", _mesh(Vector3(1, 1, 1)), Transform3D(Basis(), Vector3(3, 0, 0)))
	var section_hall := _place(section, "Kit_hall_0_3", _mesh(Vector3(12, 4, 12)), Transform3D(Basis(), Vector3(9, 0, 0)))
	# One placement drawing two pieces far apart in their own space (merged
	# props): not one object.
	var merged := _holder(world, "Props_0", Vector3(0, 0, 150))
	var merged_a := _place(merged, "Props_crates", _mesh(Vector3(1, 1, 1)), Transform3D.IDENTITY)
	var merged_b := _place(merged, "Props_barrels", _mesh(Vector3(1, 1, 1), Vector3(40, 0, 0)), Transform3D.IDENTITY)
	var group_node := _holder(world, "WorldGroup_1_0", Vector3(0, 0, 90))
	var grouped_crate := _place(group_node, "Crate_g", _mesh(Vector3(1, 1, 1)), Transform3D.IDENTITY)
	_place(group_node, "Hall_g", _mesh(Vector3(12, 4, 12)), Transform3D(Basis(), Vector3(7, 0, 0)))
	var support := _place(_holder(world, "AuthoredBridgeSupport_wd__b1-01_01_wd_WorldPlacement", Vector3(-40, 0, 0)),
		"AuthoredBridgeSupport_wd__b1-01_01_wd", _mesh(Vector3(0.55, 1.26, 0.55)), Transform3D.IDENTITY)
	var lamp := _place(_holder(world, "Authored_wd_kit_lantern_post_1_WorldPlacement", Vector3(-50, 0, 0)),
		"kit-lantern-post-12", _mesh(Vector3(0.8, 2.3, 0.4)), Transform3D.IDENTITY)
	var dock := _holder(world, "Dock_0", Vector3(-60, 0, 0))
	var dock_deck := _place(dock, "Walk_wd_dock-deck", _mesh(Vector3(6, 0.2, 3), Vector3(0, 1, 0)), Transform3D.IDENTITY)
	var dock_post := _place(dock, "Dock_0__post", _mesh(Vector3(0.4, 1.2, 0.4), Vector3(2, 0.4, 1)), Transform3D.IDENTITY)
	var wall := _place(world, "kit-sea-wall-segment-1", _mesh(Vector3(11.56, 1.4, 1.38)), Transform3D(Basis(), Vector3(-80, 0, 0)))
	var turned_wall := _place(world, "kit-sea-wall-segment-12", _mesh(Vector3(11.56, 1.4, 1.38)),
		Transform3D(Basis(Vector3.UP, 0.4), Vector3(-80, 0, 20)))
	# Four banners: each pole (one shared mesh) and its own gilt top. The loader
	# batches the poles; the gilt tops stay loose.
	var pole := _mesh(Vector3(0.2, 2.0, 0.2))
	var gilts: Array[MeshInstance3D] = []
	for index: int in 4:
		var banner := _holder(world, "Banner_%d" % index, Vector3(100 + index * 5.0, 0, 0))
		_place(banner, "Banner_%d__iron" % index, pole, Transform3D.IDENTITY)
		gilts.append(_place(banner, "Banner_%d__gilt" % index, _mesh(Vector3(0.3, 0.3, 0.3), Vector3(0, 1.1, 0)),
			Transform3D.IDENTITY))
	await process_frame
	var loader := WorldLoader.new()
	loader.manifest = WorldManifest.new()
	loader.manifest.data = CONTINENT.duplicate(true)
	loader.world_root = world
	loader.call("_batch_static_instances", world.find_children("*", "MeshInstance3D", true, false))
	WorldDistance.apply_root(world, WorldDistance.state_for(26.0, HIGH))
	var cart_group := _wd_group(body)
	_expect(cart_group.begins_with("rl_wd_M_") and _wd_group(wheels) == cart_group and _wd_group(metal) == cart_group
		and is_equal_approx(wheels.visibility_range_end, body.visibility_range_end)
		and is_equal_approx(metal.visibility_range_end, body.visibility_range_end),
		"a material-split cart is one M prop: its small parts share its range (%s %s %s)" % [
			cart_group, _wd_group(wheels), _wd_group(metal)])
	_expect(body.cast_shadow == ON and wheels.cast_shadow == ON and metal.cast_shadow == ON,
		"and its small parts keep their shadow with it")
	_expect(_wd_group(near) == "rl_wd_S_1" and _wd_group(far) == "rl_wd_S_1"
		and near.cast_shadow == OFF and far.cast_shadow == OFF and _wd_group(section_hall).begins_with("rl_wd_L_"),
		"a section node's props, each at its own placement, are classed one by one")
	_expect(_wd_group(merged_a) == "rl_wd_S_1" and _wd_group(merged_b) == "rl_wd_S_1",
		"pieces of one placement spread far apart are not one object (%s %s)" % [_wd_group(merged_a), _wd_group(merged_b)])
	_expect(_wd_group(grouped_crate) == "rl_wd_S_1", "the loader's WorldGroup_ nodes group nothing (%s)" % _wd_group(grouped_crate))
	_expect(support.is_in_group(WorldDistance.LOD_GROUP) and support.visibility_range_end == 0.0
		and support.cast_shadow == OFF, "a bridge support is never ranged (an S one still casts no shadow)")
	_expect(lamp.is_in_group(WorldDistance.LOD_GROUP) and lamp.visibility_range_end == 0.0,
		"a lamp NightLamps gives a halo is never ranged")
	_expect(dock_post.is_in_group(WorldDistance.LOD_GROUP) and dock_post.visibility_range_end == 0.0
		and dock_deck.cast_shadow == OFF and _wd_group(dock_deck).is_empty(),
		"a post beside its walk deck is never ranged; the flat deck casts no shadow")
	_expect(wall.cast_shadow == ON and turned_wall.cast_shadow == ON
		and _wd_group(wall).begins_with("rl_wd_L_") and _wd_group(turned_wall).begins_with("rl_wd_L_"),
		"a long low sea wall keeps its shadow, turned or not")
	var pole_batch: MultiMeshInstance3D = null
	for batch: MultiMeshInstance3D in _batches(world):
		if str(batch.name).contains("Banner_"):
			pole_batch = batch
	_expect(pole_batch != null and pole_batch.is_in_group(WorldDistance.LOD_GROUP)
		and pole_batch.visibility_range_end == 0.0 and pole_batch.cast_shadow == ON,
		"a batch of the banners' poles keeps its shadow and is never ranged")
	var gilts_kept := true
	for gilt: MeshInstance3D in gilts:
		gilts_kept = gilts_kept and gilt.is_in_group(WorldDistance.LOD_GROUP) \
			and gilt.visibility_range_end == 0.0 and gilt.cast_shadow == ON
	_expect(gilts_kept, "and so do the banners' unbatched gilt tops")
	loader.world_root = null
	loader.free()
	root.remove_child(world)
	world.free()

func _holder(parent: Node, node_name: String, at: Vector3) -> Node3D:
	var holder := Node3D.new()
	holder.name = node_name
	holder.position = at
	parent.add_child(holder)
	return holder

## For every ranged node and every point within the class reach of a focus,
## the camera at any orbit of that focus is inside end - margin of the node's
## box centre: nothing within reach is culled at any zoom, a batch whose
## centre is far from one of its members included.
func _check_focus_guarantee() -> void:
	var built := await _world(CONTINENT)
	var world: Node3D = built.world
	var worst := INF
	var checked := 0
	for level: int in [LOW, HIGH]:
		for distance: float in [1.5, 8.0, 26.0, 33.0, 90.0]:
			var state := WorldDistance.state_for(distance, level)
			WorldDistance.apply_root(world, state)
			for batch: MultiMeshInstance3D in _batches(world):
				var members := _members(world, batch)
				var union := AABB()
				for index: int in members.size():
					var box: AABB = members[index].transform * (members[index] as MeshInstance3D).mesh.get_aabb()
					union = box if index == 0 else union.merge(box)
				var reach := Classes.reach_metres(str(batch.get_meta(Classes.CLASS_META)), str(state.quality_name))
				for member: MeshInstance3D in members:
					# The focus on the member's nearest face, the camera straight away from the batch centre.
					var away := (member.transform.origin - union.get_center()).normalized()
					if not away.is_finite() or away.is_zero_approx():
						away = Vector3.RIGHT
					var focus := member.transform.origin + away * reach
					var camera := focus + away * distance
					var slack := batch.visibility_range_end - batch.visibility_range_end_margin \
						- camera.distance_to(union.get_center())
					worst = minf(worst, slack)
					checked += 1
	_expect(checked > 0 and worst >= 0.0,
		"no batch member within reach of the focus is ever culled (%d cases, worst slack %.2f m)" % [checked, worst])
	_free(built)

func _check_low_and_film() -> void:
	var built := await _world(GAUNTLET)
	var world: Node3D = built.world
	var rock := built.nodes.rock as MeshInstance3D
	WorldDistance.apply_root(world, WorldDistance.state_for(90.0, LOW))
	_expect(is_equal_approx(rock.visibility_range_end, 96.0 + 18.0 + 4.0 + 4.0) and is_equal_approx(rock.lod_bias, 0.15),
		"LOW at 90 m: S reaches 18 m past the 96 m bucket, bias 0.15 (%.1f)" % rock.visibility_range_end)
	WorldDistance.apply_root(world, WorldDistance.state_for(26.0, HIGH, true))
	var none_culled := true
	for node: Node in world.find_children("*", "GeometryInstance3D", true, false):
		if not _wd_group(node).is_empty():
			none_culled = none_culled and (node as GeometryInstance3D).visibility_range_end == 0.0
	_expect(none_culled and rock.cast_shadow == OFF, "a film (detached camera) culls nothing; shadows stay")
	_free(built)

func _check_terrain_rule() -> void:
	var bare := await _world(CONTINENT, false)
	WorldDistance.apply_root(bare.world, WorldDistance.state_for(26.0, HIGH))
	_expect((bare.nodes.terrain as MeshInstance3D).cast_shadow == ON, "without a base Terrain_ keeps its shadow")
	_free(bare)
	var glassy := await _world(CONTINENT)
	var base := glassy.nodes.base as MeshInstance3D
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	base.set_surface_override_material(0, material)
	WorldDistance.apply_root(glassy.world, WorldDistance.state_for(26.0, HIGH))
	_expect((glassy.nodes.terrain as MeshInstance3D).cast_shadow == ON,
		"beside a cut-out (not opaque) base Terrain_ keeps its shadow")
	_free(glassy)
	var shadowless := await _world(CONTINENT)
	(shadowless.nodes.base as MeshInstance3D).cast_shadow = OFF
	WorldDistance.apply_root(shadowless.world, WorldDistance.state_for(26.0, HIGH))
	_expect((shadowless.nodes.terrain as MeshInstance3D).cast_shadow == ON,
		"beside a base that casts no shadow Terrain_ keeps its own")
	_free(shadowless)

func _check_idempotent() -> void:
	var built := await _world(CONTINENT)
	var world: Node3D = built.world
	var state := WorldDistance.state_for(26.0, HIGH)
	var first := WorldDistance.apply_root(world, state)
	var before := _fingerprint(world)
	var second := WorldDistance.apply_root(world, state)
	_expect(_fingerprint(world) == before and int(first.ranged) == int(second.ranged)
		and int(second.shadows_off) == 0 and int(second.ground_shadows_off) == 0,
		"a second pass changes nothing (%s / %s)" % [first, second])
	WorldDistance.apply_root(world, WorldDistance.state_for(90.0, HIGH))
	var stamps := world.get_groups().filter(func(group: StringName) -> bool:
		return String(group).begins_with(WorldDistance.STAMP_PREFIX))
	_expect(stamps == [StringName(WorldDistance.STAMP_PREFIX + "96_2_0")], "a re-applied root carries one stamp: %s" % [stamps])
	_free(built)

func _check_switch_and_scope() -> void:
	var built := await _world(CONTINENT)
	var world: Node3D = built.world
	var before := _fingerprint(world)
	OS.set_environment(HardwareTier.WORLD_DISTANCE_VARIABLE, "off")
	_expect(WorldDistance.apply_loaded(world, (built.loader as WorldLoader).manifest).is_empty()
		and _fingerprint(world) == before and world.get_groups().is_empty(),
		"ELORIA_WORLD_DISTANCE=off: the pass changes nothing")
	var probe := WorldDistance.new()
	_expect(not probe.enabled, "and the node follows no camera")
	probe.free()
	OS.unset_environment(HardwareTier.WORLD_DISTANCE_VARIABLE)
	var interior := WorldManifest.new()
	interior.data = {"collision": {}}
	_expect(WorldDistance.apply_loaded(world, interior).is_empty() and _fingerprint(world) == before,
		"an interior or older whole map is left alone")
	_expect(not WorldDistance.apply_loaded(world, (built.loader as WorldLoader).manifest).is_empty(),
		"a continent chunk is classed")
	_free(built)

# --------------------------------------------------------------------------
# The node
# --------------------------------------------------------------------------

func _check_node() -> void:
	WorldDistance.reset_state()
	var distance := WorldDistance.new()
	root.add_child(distance)
	distance.enabled = true
	var built := await _world(CONTINENT)
	var world: Node3D = built.world
	var rock := built.nodes.rock as MeshInstance3D
	var tower := built.nodes.tower as MeshInstance3D
	# Loaded before Main published anything: the default 26 m state.
	WorldDistance.apply_loaded(world, (built.loader as WorldLoader).manifest)
	_expect(is_equal_approx(rock.visibility_range_end, 70.0), "a load before any update assumes the rig's 26 m")
	distance.update(26.0, HIGH)
	var applied := distance.applies
	distance.update(27.0, HIGH)
	distance.update(31.9, HIGH)
	_expect(distance.applies == applied, "inside one 8 m bucket nothing is re-applied")
	distance.update(90.0, HIGH)
	_expect(is_equal_approx(rock.visibility_range_end, 96.0 + 30.0 + 8.0) and distance.applies == applied + 1,
		"zooming out re-applies once: %.1f" % rock.visibility_range_end)
	_expect(world.is_in_group(StringName(WorldDistance.STAMP_PREFIX + "96_2_0")), "and restamps the roots in the scene")
	distance.update(90.0, LOW)
	_expect(is_equal_approx(rock.lod_bias, 0.15) and is_equal_approx(tower.lod_bias, 0.15)
		and is_equal_approx(rock.visibility_range_end, 96.0 + 18.0 + 8.0), "LOW: the bias and the reach follow")
	distance.set_quality(HIGH)
	_expect(is_equal_approx(rock.lod_bias, 1.0) and is_equal_approx(tower.lod_bias, 1.0), "set_quality follows too")
	distance.update(90.0, HIGH, true)
	_expect(rock.visibility_range_end == 0.0, "a film culls nothing")
	distance.update(90.0, HIGH)
	# A chunk prepared off the tree under an older state enters the scene.
	var chunk := await _world(CONTINENT)
	var chunk_world: Node3D = chunk.world
	root.remove_child(chunk_world)
	WorldDistance.apply_root(chunk_world, WorldDistance.state_for(26.0, HIGH))
	var chunk_rock := chunk.nodes.rock as MeshInstance3D
	var refreshes := distance.refreshes
	root.add_child(chunk_world)
	distance.update(90.0, HIGH)
	_expect(distance.refreshes == refreshes + 1 and is_equal_approx(chunk_rock.visibility_range_end, 134.0),
		"a stale chunk is caught as it enters: %.1f" % chunk_rock.visibility_range_end)
	distance.update(90.0, HIGH)
	_expect(distance.refreshes == refreshes + 1, "once")
	# A chunk applied under the current state costs nothing.
	var fresh := await _world(CONTINENT)
	root.remove_child(fresh.world)
	WorldDistance.apply_loaded(fresh.world, (fresh.loader as WorldLoader).manifest)
	root.add_child(fresh.world)
	distance.update(90.0, HIGH)
	_expect(distance.refreshes == refreshes + 1 and is_equal_approx((fresh.nodes.rock as MeshInstance3D).visibility_range_end, 134.0),
		"a chunk built under the current state needs no re-apply")
	# A parked world misses a zoom and is re-adopted.
	root.remove_child(world)
	distance.update(26.0, HIGH)
	_expect(is_equal_approx(rock.visibility_range_end, 134.0), "a parked world keeps its old ranges while out")
	root.add_child(world)
	distance.update(26.0, HIGH)
	_expect(is_equal_approx(rock.visibility_range_end, 70.0), "and follows once it is back")
	# The stream hook catches a cell in the frame it arrives.
	var stream := Node3D.new()
	stream.add_user_signal("cell_ready", [{"name": "identity", "type": TYPE_STRING}, {"name": "imported", "type": TYPE_OBJECT}])
	root.add_child(stream)
	distance.watch(stream)
	distance.watch(stream)
	_expect(stream.get_signal_connection_list("cell_ready").size() == 1, "watch connects a stream once")
	var cell := await _world(CONTINENT)
	root.remove_child(cell.world)
	WorldDistance.apply_root(cell.world, WorldDistance.state_for(90.0, HIGH))
	stream.add_child(cell.world)
	stream.emit_signal("cell_ready", "00_00", cell.world)
	_expect(is_equal_approx((cell.nodes.rock as MeshInstance3D).visibility_range_end, 70.0),
		"a stale cell is re-ranged on cell_ready")
	var snap := distance.snapshot()
	_expect(bool(snap.enabled) and snap.bucket_metres == 32.0 and snap.quality == "HIGH"
		and is_equal_approx(float(snap.range_end_metres.S), 66.0) and int(snap.nodes.S) > 0
		and int(snap.nodes.lod_only) >= 4 and int(snap.roots) >= 4 and int(snap.stale_roots) == 0
		and int(snap.applies) >= 6 and snap.has("max_apply_us"),
		"the snapshot the camera probe records: %s" % [snap])
	_free(cell)
	stream.queue_free()
	_free(fresh)
	_free(chunk)
	_free(built)
	distance.queue_free()
	WorldDistance.reset_state()

# --------------------------------------------------------------------------
# The loader
# --------------------------------------------------------------------------

## A raw load with a pending cache write: the pack sees the loader's own
## values, and the live tree gets the pass's back afterwards.
func _check_cache_snapshot() -> void:
	var built := await _world(CONTINENT)
	var world: Node3D = built.world
	var loader: WorldLoader = built.loader
	var rock := built.nodes.rock as MeshInstance3D
	var first := world.get_node("StaticBatch_0_Crate_00") as MultiMeshInstance3D
	loader.call("_snapshot_for_cache")
	loader.call("_apply_world_distance")
	_expect(int(loader.load_phases.get(&"worldDistanceRanged", 0)) == 17 and loader.load_phases.has(&"worldDistance"),
		"the load report counts the pass: %s" % [loader.load_phases])
	_expect(rock.cast_shadow == OFF and rock.visibility_range_end > 0.0 and first.cast_shadow == OFF,
		"the live tree is classed")
	var undo: Array = loader.call("_restore_pristine")
	var pristine := rock.cast_shadow == ON and rock.visibility_range_end == 0.0 \
		and rock.visibility_range_end_margin == 0.0 and first.cast_shadow == ON and first.visibility_range_end == 0.0
	for member: MeshInstance3D in _members(world, first):
		pristine = pristine and member.cast_shadow == ON
	_expect(pristine, "for the pack: the loader's own shadows and no ranges")
	for node: Node in world.find_children("*", "", true, false):
		node.owner = world
	var packed := PackedScene.new()
	_expect(packed.pack(world) == OK, "the classed world packs")
	loader.call("_undo_pristine", undo)
	_expect(rock.cast_shadow == OFF and rock.visibility_range_end > 0.0 and first.cast_shadow == OFF,
		"and the live tree is classed again")
	var restored := packed.instantiate() as Node3D
	var groups_left := 0
	for node: Node in restored.find_children("*", "", true, false):
		groups_left += node.get_groups().size()
	var restored_rock := restored.get_node("Rock_a") as MeshInstance3D
	_expect(groups_left == 0 and restored.get_groups().is_empty() and restored_rock.cast_shadow == ON
		and restored_rock.visibility_range_end == 0.0, "the packed entry is tier-neutral (no groups, no ranges)")
	restored.free()
	loader.call("_release_snapshot")
	_free(built)

## The three publish paths call the pass: a legacy cache hit, a geometry hit
## and a prepared hit run `_apply_world_distance` after linking batches.
func _check_loader_paths() -> void:
	var source := FileAccess.get_file_as_string("res://src/world/world_loader.gd")
	for anchor: String in ["func _materialize_geometry_world", "func _materialize_prepared_world",
			"func _load_from_cache", "func load_world"]:
		var start := source.find(anchor)
		var body := source.substr(start, source.find("\nfunc ", start + 1) - start)
		var call_at := body.find("_apply_world_distance()")
		var look_at := body.find("LookGround.paint_loaded")
		_expect(start >= 0 and call_at > 0 and look_at > call_at,
			"%s runs the pass before the look pass" % anchor)
	var raw := source.substr(source.find("func load_world"))
	_expect(raw.find("_snapshot_for_cache()") < raw.find("_apply_world_distance()"),
		"the raw path takes its cache snapshot first")

## A chunk built and classed on a worker (a private tree, as
## WorldLoader.prepare_detached builds one): its groups register when Main
## attaches it, and its stamp says which state it was built under.
func _check_worker_build() -> void:
	WorldDistance.reset_state()
	var thread := Thread.new()
	_expect(thread.start(_worker_chunk) == OK, "the worker starts")
	# Never block Main on a worker that may wait for the rendering server.
	while thread.is_alive():
		await process_frame
	var built: Node3D = thread.wait_to_finish()
	_expect(built != null and not built.is_inside_tree(), "the worker hands back a private tree")
	var before := get_node_count_in_group(WorldDistance.group_of("S", 1))
	root.add_child(built)
	var rock := built.get_node("Rock_a") as MeshInstance3D
	_expect(get_node_count_in_group(WorldDistance.group_of("S", 1)) == before + 1
		and rock.cast_shadow == OFF and is_equal_approx(rock.visibility_range_end, 70.0)
		and get_node_count_in_group(StringName(WorldDistance.STAMP_PREFIX + "32_2_0")) >= 1,
		"its groups and stamp register as it enters the scene")
	built.queue_free()
	await process_frame
	WorldDistance.reset_state()

func _worker_chunk() -> Node3D:
	var world := Node3D.new()
	world.name = "ImportedWorld_worker"
	_place(world, "Rock_a", _mesh(Vector3(1, 1, 1)), Transform3D(Basis(), Vector3(5, 0, 5)))
	var manifest := WorldManifest.new()
	manifest.data = CONTINENT.duplicate(true)
	WorldDistance.apply_loaded(world, manifest)
	return world

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

## A box mesh of `size` whose centre sits at `offset` in its own space (a part
## of a split object is drawn from the object's placement).
func _mesh(size: Vector3, offset := Vector3.ZERO) -> ArrayMesh:
	var box := BoxMesh.new()
	box.size = size
	var arrays := box.get_mesh_arrays()
	if offset != Vector3.ZERO:
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for index: int in vertices.size():
			vertices[index] += offset
		arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, StandardMaterial3D.new())
	return mesh

func _place(parent: Node, node_name: String, mesh: Mesh, placement: Transform3D) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.transform = placement
	parent.add_child(node)
	return node

func _batches(world: Node) -> Array[MultiMeshInstance3D]:
	var found: Array[MultiMeshInstance3D] = []
	for node: Node in world.find_children("StaticBatch_*", "MultiMeshInstance3D", true, false):
		found.append(node as MultiMeshInstance3D)
	return found

func _members(world: Node, batch: MultiMeshInstance3D) -> Array:
	var found: Array = []
	for node: Node in world.find_children("*", "MeshInstance3D", true, false):
		if node.has_meta(WorldLoader.BATCH_META) and node.get_meta(WorldLoader.BATCH_META) == batch:
			found.append(node)
	return found

func _wd_group(node: Node) -> String:
	for group: StringName in node.get_groups():
		var text := String(group)
		if text.begins_with(WorldDistance.GROUP_PREFIX) and not text.begins_with(WorldDistance.STAMP_PREFIX) \
				and group != WorldDistance.LOD_GROUP:
			return text
	return ""

## Every geometry node's distance properties and groups, by path.
func _fingerprint(world: Node) -> Dictionary:
	var rows := {}
	for node: Node in world.find_children("*", "GeometryInstance3D", true, false):
		var geometry := node as GeometryInstance3D
		var groups: Array = geometry.get_groups()
		groups.sort()
		rows[str(world.get_path_to(geometry))] = [geometry.cast_shadow, geometry.visibility_range_end,
			geometry.visibility_range_end_margin, geometry.lod_bias, groups]
	return rows

func _free(built: Dictionary) -> void:
	var loader := built.get("loader") as WorldLoader
	if loader != null:
		loader.world_root = null
		loader.free()
	var world := built.get("world") as Node
	if is_instance_valid(world):
		if world.get_parent() != null:
			world.get_parent().remove_child(world)
		world.free()

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
