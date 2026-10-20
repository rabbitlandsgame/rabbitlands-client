extends SceneTree
## Guards the look pass's grass beds (layer L4).
##
## With ELORIA_LOOK=0 nothing is grown and no node is added. With it on,
## tufts grow on the grass and densest along a road's verge, never on the
## road itself, under a wall, on a steep bank, under water, on pale paving or
## where a second road deck covers the rim of the first; around paving they
## stop where its paint does, following a turned or round court's outline
## (not its bounds) and leaving the seam between two courts bare; placement is the
## same every time it is worked out, lives in the ground's frame (so moving
## the world moves the bed, not the tufts within it), stays inside its
## budget, draws in three MultiMeshes on the gameplay layer without shadows,
## and the tuft meshes are the tapered 5-9 blade tufts the shader expects.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	LookProfile.set_player_mode(LookProfile.Mode.FULL_PAINTED)
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var manifest := WorldManifest.new()
	manifest.data = {"continentGeography": {"geometryMode": "continent-chunks-v1"},
		"environment": {"sun": {"enabled": true}}}
	var interior := WorldManifest.new()
	interior.data = {"environment": {"sun": {"enabled": false}}}
	var parent := Node3D.new()
	parent.name = "WorldRoot"
	root.add_child(parent)
	var world := _world()
	parent.add_child(world)
	for i in 3:
		await physics_frame
	_check_streaming_fade()

	# --- Tuft meshes -------------------------------------------------------
	for variant: int in LookProfile.GRASS_TUFTS.size():
		var mesh := LookGrassBeds.tuft_mesh(variant)
		var blades := int(LookProfile.GRASS_TUFTS[variant].blades)
		var arrays := mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var colours: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		_expect(blades >= 4 and blades <= 9 and vertices.size() == blades * 5
			and indices.size() == blades * 9,
			"tuft %d has %d tapered two-segment blades" % [variant, blades])
		var root_shade := 1.0
		var tip_shade := 0.0
		var tip_width_zero := true
		for blade: int in blades:
			root_shade = minf(root_shade, colours[blade * 5].r)
			tip_shade = maxf(tip_shade, colours[blade * 5 + 4].r)
			tip_width_zero = tip_width_zero and uvs[blade * 5 + 4].y == 1.0 \
				and uvs[blade * 5].y == 0.0
		_expect(root_shade < tip_shade and tip_width_zero,
			"tuft %d's vertex colour darkens towards the root, UV.y runs root to tip" % variant)
		_expect(LookGrassBeds.tuft_mesh(variant) == mesh, "tuft %d is built once" % variant)

	# --- Classification helpers ----------------------------------------------
	_expect(int(LookGrassBeds.vertex_ground(Color(0.22, 0.44, 0.28)).x) == LookGrassBeds.Ground.GRASS,
		"an island's green vertex colour is grass")
	_expect(int(LookGrassBeds.vertex_ground(Color(0.82, 0.76, 0.58)).x) == LookGrassBeds.Ground.PATH,
		"its sand-gold trail is path")
	_expect(int(LookGrassBeds.vertex_ground(Color(0.38, 0.475, 0.34)).x) == LookGrassBeds.Ground.VERGE,
		"the blend between them is verge")
	_expect(int(LookGrassBeds.vertex_ground(Color(0.46, 0.57, 0.41)).x) == LookGrassBeds.Ground.PATH,
		"and the trail's painted margin is path, where tufts crowded the trail")
	var feathered := true
	for cell_hash: int in 64:
		var outer := LookGrassBeds.verge_strength(0.0, cell_hash)
		var middle := LookGrassBeds.verge_strength(0.13, cell_hash)
		var roadside := LookGrassBeds.verge_strength(0.23, cell_hash)
		feathered = feathered and outer < 0.5 and middle > outer and roadside <= 0.55
	_expect(feathered, "a verge bed feathers in from the deck's edge and thins towards the road")
	var mottle_mean := 0.0
	var mottle_in_range := true
	for step: int in 400:
		var spot := Vector2(float(step % 20) * 3.7 - 812.0, float(step / 20) * 3.1 + 1433.0)
		var noise := LookGrassBeds.paint_noise(spot / 16.0)
		mottle_in_range = mottle_in_range and noise >= 0.0 and noise <= 1.0
		mottle_mean += LookGrassBeds.ground_mottle(spot).g / 400.0
	_expect(mottle_in_range and absf(mottle_mean - 1.0) < 0.12
		and LookGrassBeds.ground_mottle(Vector2(5.0, 9.0)) == LookGrassBeds.ground_mottle(Vector2(5.0, 9.0)),
		"a tuft takes the ground paint's mottle: stable, centred on 1")
	_expect(int(LookGrassBeds.vertex_ground(Color(0.45, 0.44, 0.42)).x) == LookGrassBeds.Ground.NONE,
		"grey rock is neither")
	_expect(LookGrassBeds.open_green(Color8(66, 90, 42), true) > 0.99
		and LookGrassBeds.open_green(Color8(212, 190, 140), true) < 0.01
		and LookGrassBeds.open_green(Color8(100, 97, 90), true) < 0.01
		and LookGrassBeds.open_green(Color8(66, 90, 42).srgb_to_linear(), false) > 0.99,
		"open ground is as grassy as its colour is green: lawn green yes, sand and rock no")
	var road := LookProfile.TERRAIN_ROAD_COLOUR
	_expect(LookGrassBeds.road_weight(Color(road.r / 0.92, road.g / 0.92, road.b / 0.92), false) > 0.99
		and LookGrassBeds.road_weight(Color(0.1, 0.3, 0.05), false) < 0.01,
		"the terrain's worn road colour is road, its grass colour is not")
	var grass_texture := ImageTexture.new()
	grass_texture.resource_path = "res://tmp/ground-basecolor.png"
	var scree_texture := ImageTexture.new()
	scree_texture.resource_path = "res://tmp/alpine-scree-lichen-v001.png"
	var heather_texture := ImageTexture.new()
	heather_texture.resource_path = "res://tmp/moor-peat-heather-v001.png"
	_expect(LookGrassBeds.grassiness(grass_texture) == 1.0
		and LookGrassBeds.grassiness(scree_texture) == 0.0
		and absf(LookGrassBeds.grassiness(heather_texture) - 0.6) < 0.001
		and LookGrassBeds.grassiness(null) == LookProfile.GRASS_LAYER_DEFAULT,
		"biome layers are as grassy as their textures say")
	# A region file's own layer words are read before every map's.
	LookProfile.define_region("test_grass_region", {"id": "test_grass_region",
		"grass": {"layers": {"alpine-scree": 0.4, "tussock": 0.8}}})
	var tussock_texture := ImageTexture.new()
	tussock_texture.resource_path = "res://tmp/steppe-tussock-v001.png"
	_expect(is_equal_approx(LookGrassBeds.grassiness(scree_texture, "test_grass_region"), 0.4)
		and is_equal_approx(LookGrassBeds.grassiness(tussock_texture, "test_grass_region"), 0.8)
		and LookGrassBeds.grassiness(grass_texture, "test_grass_region") == 1.0
		and LookGrassBeds.grassiness(tussock_texture) == LookProfile.GRASS_LAYER_DEFAULT
		and LookProfile.grass_palette("test_grass_region").is_empty(),
		"a region's own layer words come first and only for it; words alone are no palette")
	# Palette slots: 0 is the default palette, a region with its own palette
	# takes the next slot once and keeps it.
	var slotted := LookGrassBeds.new()
	var reach_slot: int = slotted._slot("lantern_reach")
	var gates_slot: int = slotted._slot("four_gates")
	var reach_palette := LookProfile.grass_palette("lantern_reach")
	var roots_array: PackedVector3Array = slotted._material.get_shader_parameter(&"look_roots")
	var tips_array: PackedVector3Array = slotted._material.get_shader_parameter(&"look_tips")
	var reach_root: Color = reach_palette.get("root", Color.BLACK)
	var reach_trim := 1.7 if LookProfile.forward_plus() else 0.9
	_expect(reach_slot == 1 and gates_slot == 2 and slotted._slot("lantern_reach") == 1
		and slotted._slot("no_such_region") == 0 and slotted._slot("test_grass_region") == 0
		and roots_array.size() == LookProfile.GRASS_PALETTE_SLOTS
		and roots_array[1] == Vector3(reach_root.r, reach_root.g, reach_root.b)
		and reach_root.is_equal_approx(Color(0.05, 0.14, 0.05) * reach_trim)
		and tips_array[0] == Vector3(0.52, 0.6, 0.28),
		"regions with a palette take their own slot, with the renderer's value trim; others the default")
	slotted.free()
	LookProfile.reload_regions()
	var weights := LookGrassBeds.barycentric_xz(Vector3(0.25, 5.0, 0.25),
		Vector3.ZERO, Vector3(1, 0, 0), Vector3(0, 0, 1))
	_expect(weights.is_equal_approx(Vector3(0.5, 0.25, 0.25)), "barycentric weights across the ground")
	_expect(LookGrassBeds.value_noise(3.3, -7.1, 11) == LookGrassBeds.value_noise(3.3, -7.1, 11)
		and LookGrassBeds.value_noise(3.3, -7.1, 11) >= 0.0
		and LookGrassBeds.value_noise(3.3, -7.1, 11) <= 1.0, "the bed noise is deterministic")
	# Pale paving: the grass works out the paint's own wandering cut.
	var on_stones := true
	var under_paint := true
	var wander := Vector2(1.0, 0.0)
	for step: int in 400:
		var xz := Vector2(float(step % 20) * 2.3 - 604.0, float(step / 20) * 1.9 + 822.0)
		on_stones = on_stones and LookGrassBeds.paving_share(0.6, xz) == 0.0
		for coverage: float in [0.0, 0.04, 0.08, 0.12, 0.16, 0.2, 0.3]:
			if _paint_coverage(coverage, xz) > 0.0 and LookGrassBeds.paving_share(coverage, xz) > 0.0:
				under_paint = false
		var share := LookGrassBeds.paving_share(0.05, xz)
		wander = Vector2(minf(wander.x, share), maxf(wander.y, share))
	_expect(on_stones and under_paint,
		"paving leaves no grass where its paint draws stone, wherever the paint's cut wanders")
	_expect(wander.x < 0.1 and wander.y > 0.75,
		"along one coverage the grass's edge wanders with the paint's lobes (share %.2f to %.2f)"
			% [wander.x, wander.y])

	# --- Look off: nothing ---------------------------------------------------
	# The focus sits on the terrain frame's origin, (100, 0, -50) in the world.
	var focus := Vector3(100.0, 0.0, -50.0)
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	LookGrassBeds.tend(parent, world, manifest, {}, focus)
	_expect(parent.get_node_or_null(LookGrassBeds.NODE_NAME) == null,
		"with the look off no grass node is added")

	# --- Look on ---------------------------------------------------------------
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	LookGrassBeds.tend(parent, world, manifest, {}, focus)
	var beds := parent.get_node_or_null(LookGrassBeds.NODE_NAME) as LookGrassBeds
	_expect(beds != null, "with the look on the grass node is added")
	if beds == null:
		_finish(previous)
		return
	beds.settle()
	var positions := beds.tuft_positions()
	_expect(positions.size() > 500, "tufts grow on the grass (%d)" % positions.size())
	var counts := beds.tuft_counts()
	_expect(counts[0] + counts[1] + counts[2] == positions.size()
		and positions.size() <= LookProfile.GRASS_INSTANCE_BUDGET,
		"the MultiMeshes hold every placed tuft, within the budget")
	var distant := 0
	for position: Vector3 in positions:
		if Vector2(position.x, position.z).length() > 60.0:
			distant += 1
	var fade: Vector2 = beds._material.get_shader_parameter(&"look_fade_metres")
	_expect(distant > 500 and fade.x > 50.0 and fade.y >= 70.0,
		"a wide field keeps full grass past 50 m and draws tufts past 60 m (%d, fade %s)"
			% [distant, fade])
	var on_road := 0
	var verge := 0
	var open := 0
	var in_house := 0
	var on_bank := 0
	var in_pond := 0
	var on_paving := 0
	var on_overlap := 0
	for position: Vector3 in positions:
		# The frame is the terrain's own space, offset from the world by
		# (100, 0, -50); the road runs along x = 0 there.
		var x := position.x
		var z := position.z
		if absf(x) < 1.2 and z > -31.5 and z < 18.5:
			on_road += 1
		elif absf(x) >= 1.9 and absf(x) < 2.7 and z > -31.5 and z < 19.0:
			verge += 1
		elif absf(x) > 6.0 and absf(x) < 12.0 and z > -12.0 and z < 12.0:
			open += 1
		if x > 14.0 and x < 18.0 and z > -2.0 and z < 2.0:
			in_house += 1
		if x > -21.5 and x < -16.5 and z > -23.0 and z < -15.0:
			on_bank += 1
		if x > 8.0 and x < 12.0 and z > -24.0 and z < -20.0:
			in_pond += 1
		if x > -13.0 and x < -7.0 and z > 15.0 and z < 21.0:
			on_paving += 1
		if absf(x) < 1.2 and z >= 18.5 and z < 24.0:
			on_overlap += 1
	_expect(on_road == 0, "no tuft on the road (%d)" % on_road)
	_expect(verge > 0 and float(verge) / (0.8 * 2.0 * 51.0) > float(open) / (6.0 * 2.0 * 24.0),
		"the verge is denser than open grass (%d on the verge, %d in the open)" % [verge, open])
	_expect(in_house == 0, "no tuft under a wall (%d)" % in_house)
	_expect(on_bank == 0, "no tuft on a steep bank (%d)" % on_bank)
	_expect(in_pond == 0, "no tuft under water (%d)" % in_pond)
	_expect(on_paving == 0, "no tuft on pale paving (%d)" % on_paving)
	# The turned court, the round court and the two courts that meet.
	var on_paint := 0
	var turned_corners := 0
	var round_corners := 0
	var in_seam := 0
	for position: Vector3 in positions:
		if _paint_at(beds, beds.global_transform * position) > 0.0:
			on_paint += 1
		var spot := Vector2(position.x, position.z)
		if _inside_court(spot, TURNED_COURT) < -0.75 \
				and _bounds(TURNED_COURT).grow(0.5).has_point(spot):
			turned_corners += 1
		if _inside_court(spot, ROUND_COURT) < -0.75 and _bounds(ROUND_COURT).grow(0.5).has_point(spot):
			round_corners += 1
		if spot.x > 34.5 and spot.x < 37.5 and spot.y > -49.0 and spot.y < -41.0:
			in_seam += 1
	_expect(on_paint == 0, "no tuft where the paint draws a court's stones (%d)" % on_paint)
	_expect(turned_corners > 20 and round_corners > 10,
		"grass grows in a turned or round court's bounding-box corners, up to its outline (%d, %d)"
			% [turned_corners, round_corners])
	_expect(in_seam == 0, "no tuft along the seam where two paving courts meet (%d)" % in_seam)
	_expect(on_overlap == 0, "no tuft on a deck's rim where another deck is road (%d)" % on_overlap)
	var census := beds.get("_census") as Dictionary
	_expect(census.get("face_mismatch", 0) == 0, "every face index found its triangle")

	# Deterministic: forgetting and placing again grows the same tufts.
	var first := _sorted(positions)
	beds.update(null, manifest, {}, focus)
	_expect(beds.tuft_positions().is_empty() and not beds.visible,
		"a map without ground forgets the bed")
	beds.update(world, manifest, {}, focus)
	beds.settle()
	_expect(_sorted(beds.tuft_positions()) == first, "the same ground grows the same tufts")

	# The bed rides the frame: moving the world moves the node, not the tufts.
	world.position += Vector3(30.0, 2.0, -12.0)
	await physics_frame
	await physics_frame
	beds.update(world, manifest, {}, focus + Vector3(30.0, 2.0, -12.0))
	_expect(beds.global_position.is_equal_approx(Vector3(130.0, 2.0, -62.0))
		and _sorted(beds.tuft_positions()) == first, "a rebase moves the bed with its ground")

	var drawn := beds.get_child(0) as MultiMeshInstance3D
	_expect(beds.get_child_count() == 3 and drawn != null
		and drawn.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		and drawn.layers == LookProfile.GRASS_RENDER_LAYER
		and drawn.multimesh.use_colors and drawn.multimesh.use_custom_data
		and (drawn.material_override as ShaderMaterial).shader
			== preload("res://src/world/look/grass_beds.gdshader"),
		"three MultiMeshes, shadowless, on the gameplay layer, with colours and custom data")

	beds.update(world, interior, {}, Vector3.ZERO)
	_expect(not beds.visible and beds.tuft_positions().is_empty(), "an interior grows no grass")
	_finish(previous)

## A dense field reaches the cap well before the normal fade band. A partial
## build and a walking focus must also stay inside the tiles actually drawn.
func _check_streaming_fade() -> void:
	var beds := LookGrassBeds.new()
	beds._focus = Vector3(4.0, 0.0, 4.0)
	var data: Array[PackedFloat32Array] = []
	var buffer := PackedFloat32Array()
	const DENSE_TUFTS := 800
	buffer.resize(DENSE_TUFTS * LookGrassBeds.FLOATS_PER_TUFT)
	data.append(buffer)
	data.append(PackedFloat32Array())
	data.append(PackedFloat32Array())
	var extent := ceili(LookProfile.GRASS_RADIUS / LookProfile.GRASS_TILE_METRES) + 1
	for x: int in range(-extent, extent + 1):
		for z: int in range(-extent, extent + 1):
			beds._tiles[Vector2i(x, z)] = {"data": data, "count": DENSE_TUFTS, "stale": false}
	beds._assemble(1000)
	beds._fade_radius = beds._coverage_radius
	beds._update_fade(1000, beds._focus)
	var drawn := beds._drawn_tiles()
	var nearest_missing := LookProfile.GRASS_RADIUS
	for key: Vector2i in beds._tiles:
		if not drawn.has(key):
			nearest_missing = minf(nearest_missing, LookGrassBeds._tile_distance(key, beds._focus))
	var fade: Vector2 = beds._material.get_shader_parameter(&"look_fade_metres")
	var counts := beds.tuft_counts()
	_expect(counts[0] + counts[1] + counts[2] <= LookProfile.GRASS_INSTANCE_BUDGET
		and nearest_missing < LookProfile.GRASS_RADIUS - LookProfile.GRASS_FADE_METRES,
		"a dense field reproduces a budget cut inside the normal fade band")
	_expect(fade.y < nearest_missing and fade.y > LookProfile.GRASS_FADE_METRES
		and is_equal_approx(fade.y - fade.x, LookProfile.GRASS_FADE_METRES),
		"the full fade band ends before the first budget-omitted tile")
	var coverage := beds._coverage_radius
	beds._update_fade(1100, beds._focus + Vector3(1.5, 0.0, 0.0))
	fade = beds._material.get_shader_parameter(&"look_fade_metres")
	_expect(is_equal_approx(fade.y, coverage - 1.5),
		"walking between uploads keeps the fade inside the uploaded coverage")
	var moved_focus := beds._focus + Vector3(2.5, 0.0, 0.0)
	for x: int in range(-extent, extent + 1):
		for z: int in range(-extent, extent + 1):
			var key := Vector2i(x, z)
			if not beds._tiles.has(key) and LookGrassBeds._tile_distance(key, moved_focus) \
					<= LookProfile.GRASS_RADIUS:
				beds._tiles[key] = {"data": data, "count": DENSE_TUFTS, "stale": false}
	beds._dirty = false
	beds._plan(moved_focus)
	_expect(beds._dirty and beds._queue.is_empty(),
		"walking refreshes budget selection even with all tiles resident")

	# One completed tile beside an unbuilt neighbour: fade before their seam.
	beds._tiles.clear()
	beds._queue.clear()
	beds._focus = Vector3(4.0, 0.0, 4.0)
	beds._tiles[Vector2i.ZERO] = {"data": data, "count": DENSE_TUFTS, "stale": false}
	beds._queue.append(Vector2i(1, 0))
	beds._assemble(1200)
	beds._fade_radius = beds._coverage_radius
	beds._update_fade(1200, beds._focus)
	fade = beds._material.get_shader_parameter(&"look_fade_metres")
	_expect(fade.x == 0.0 and fade.y > 0.0 and fade.y < 4.0,
		"a partial build fades out before the unbuilt neighbour's square edge")
	var partial_radius := fade.y
	beds._queue.clear()
	# Finish the rest of the planned area before publishing full coverage.
	var empty: Array[PackedFloat32Array] = [PackedFloat32Array(),
		PackedFloat32Array(), PackedFloat32Array()]
	for x: int in range(-extent, extent + 1):
		for z: int in range(-extent, extent + 1):
			var key := Vector2i(x, z)
			if not beds._tiles.has(key):
				beds._tiles[key] = {"data": empty, "count": 0, "stale": false}
	beds._assemble(1200)
	beds._update_fade(1300, beds._focus)
	fade = beds._material.get_shader_parameter(&"look_fade_metres")
	_expect(fade.y > partial_radius and fade.y < LookProfile.GRASS_RADIUS,
		"new coverage grows into view instead of appearing in a tile-sized step")
	beds._forget()
	_expect(beds._fade_radius == 0.0 and beds._coverage_radius == 0.0,
		"a map change resets the previous map's coverage and fade")
	beds.free()

## The paint's coverage of pale paving at vertex alpha `coverage`, `xz` into
## its mesh space, as painted_ground_surface.gdshaderinc cuts it (without the
## texture's grain): kept apart from LookGrassBeds.paving_share on purpose.
func _paint_coverage(coverage: float, xz: Vector2) -> float:
	var lobe_at := xz / LookProfile.RIM_LOBE_METRES
	var lobe := 0.65 * LookGrassBeds.paint_noise(lobe_at + Vector2(41.3, 17.9)) \
		+ 0.35 * LookGrassBeds.paint_noise(lobe_at * 2.7 + Vector2(7.1, 29.3)) - 0.5
	var weight := coverage + (LookGrassBeds.paint_noise(xz / LookProfile.RIM_NOISE_METRES) - 0.5) \
		* 2.0 * LookProfile.PAVING_RIM.z + lobe * 2.0 * LookProfile.PAVING_RIM_LOBE.x
	return smoothstep(LookProfile.PAVING_RIM.x - LookProfile.PAVING_RIM.y,
		LookProfile.PAVING_RIM.x + LookProfile.PAVING_RIM.y, weight)

## The most the paint covers `point` (world) with any pale paving the bed knows.
func _paint_at(beds: LookGrassBeds, point: Vector3) -> float:
	var painted := 0.0
	for patch: Dictionary in beds.get("_patches") as Array:
		if not bool(patch.paving) or not (patch.rect as Rect2).has_point(Vector2(point.x, point.z)):
			continue
		var coverage: float = beds.call("_patch_coverage", patch, point)
		if coverage < 0.0:
			continue
		var local := (patch.inverse as Transform3D) * point
		painted = maxf(painted, _paint_coverage(coverage, Vector2(local.x, local.z)))
	return painted

## How far `spot` (the terrain frame) lies inside a court: negative outside.
static func _inside_court(spot: Vector2, court: Dictionary) -> float:
	var local := (spot - (court.centre as Vector2)).rotated(-float(court.angle))
	var half := float(court.half)
	if bool(court.round):
		return half - local.length()
	return minf(half - absf(local.x), half - absf(local.y))

static func _bounds(court: Dictionary) -> Rect2:
	var half := float(court.half)
	if bool(court.round):
		return Rect2(court.centre - Vector2.ONE * half, Vector2.ONE * half * 2.0)
	var corners := PackedVector2Array()
	for corner: Vector2 in [Vector2(-1, -1), Vector2(1, -1), Vector2(1, 1), Vector2(-1, 1)]:
		corners.append(court.centre + (corner * half).rotated(float(court.angle)))
	var bounds := Rect2(corners[0], Vector2.ZERO)
	for corner: Vector2 in corners:
		bounds = bounds.expand(corner)
	return bounds

func _sorted(positions: PackedVector3Array) -> PackedVector3Array:
	var copy := positions.duplicate()
	copy.sort()
	return copy

func _finish(previous: String) -> void:
	OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	print("test_look_grass: %d failure(s)" % failures)
	quit(1 if failures > 0 else 0)

## A continent field, 192 m square, in a terrain frame offset from its
## root: flat grass with a road deck down x = 0 (coverage 1 in the middle,
## 0 at 2.4 m out), a second deck overlapping its far end, a walled house, a
## steep bank, a pond, a pale paving patch, and pale paving courts as the
## continent exporter writes them: a turned square, a round one, and two
## squares that meet along one side.
func _world() -> Node3D:
	var world := Node3D.new()
	world.name = "ImportedWorld_test"
	var frame := Vector3(100.0, 0.0, -50.0)
	var grass := StandardMaterial3D.new()
	grass.resource_name = "continental_ground"
	_walk(world, "Terrain_test_0_0", _plane(-96.0, -96.0, 96.0, 96.0, 0.0, Color(0.2, 0.5, 0.1), 24),
		grass, frame)
	var deck := StandardMaterial3D.new()
	deck.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	deck.cull_mode = BaseMaterial3D.CULL_DISABLED
	_walk(world, "Walk_test_road", _strip(-2.4, 2.4, -32.0, 24.0, 0.06), deck, frame)
	# A second deck crossing the first one's far end, a little above it so the
	# rays always find it first: its rim lies over the first one's road.
	_walk(world, "Walk_test_crossing", _strip_x(-6.0, 6.0, 19.0, 25.0, 0.09), deck, frame)
	var house := StaticBody3D.new()
	house.collision_layer = LookGrassBeds.WORLD_LAYER
	var box := CollisionShape3D.new()
	box.shape = BoxShape3D.new()
	(box.shape as BoxShape3D).size = Vector3(6.0, 5.0, 6.0)
	house.position = frame + Vector3(16.0, 2.5, 0.0)
	house.add_child(box)
	world.add_child(house)
	# A steep bank (50 degrees), wholly above the ground so the rays find it:
	# turned about its own middle, (-19, 5, -19) in the frame.
	var bank := _walk(world, "Terrain_test_bank", _plane(-24.0, -24.0, -14.0, -14.0, 0.0,
		Color(0.2, 0.5, 0.1), 2), grass, frame)
	bank.rotation = Vector3(0.0, 0.0, deg_to_rad(50.0))
	bank.position = frame + Vector3(-19.0, 5.0, 0.0) - (bank.basis * Vector3(-19.0, 0.0, 0.0))
	var pond := MeshInstance3D.new()
	pond.name = "Water_test_pond"
	pond.mesh = _plane(7.0, -25.0, 13.0, -19.0, 0.4, Color.WHITE, 1)
	pond.position = frame
	world.add_child(pond)
	var paving := StandardMaterial3D.new()
	paving.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
	paving.albedo_color = Color("ccba9c")
	var plaza := MeshInstance3D.new()
	plaza.name = "AuthoredGround_test_plaza"
	plaza.mesh = _plane(-13.0, 15.0, -7.0, 21.0, 0.03, Color(1, 1, 1, 1), 2)
	plaza.material_override = null
	plaza.set_surface_override_material(0, paving)
	plaza.position = frame
	world.add_child(plaza)
	for court: Dictionary in [TURNED_COURT, ROUND_COURT, SEAM_COURT_WEST, SEAM_COURT_EAST]:
		var node := MeshInstance3D.new()
		node.name = "AuthoredGround_test_" + str(court.name)
		node.mesh = _court(court)
		node.set_surface_override_material(0, paving)
		node.position = frame
		world.add_child(node)
	return world

const TURNED_COURT := {"name": "turned", "centre": Vector2(-35.0, 35.0), "half": 6.0,
	"angle": 0.52, "round": false, "blend": 2.0}
const ROUND_COURT := {"name": "round", "centre": Vector2(35.0, 35.0), "half": 6.0,
	"angle": 0.0, "round": true, "blend": 2.0}
const SEAM_COURT_WEST := {"name": "seam_west", "centre": Vector2(30.0, -45.0), "half": 6.0,
	"angle": 0.0, "round": false, "blend": 2.0}
const SEAM_COURT_EAST := {"name": "seam_east", "centre": Vector2(42.0, -45.0), "half": 6.0,
	"angle": 0.0, "round": false, "blend": 2.0}

## A paving court as terrain_export.py writes a ground region: the terrain's
## 2 m lattice triangles under it, its coverage smoothstep(0, blend, the
## distance inside its shape) in each vertex's alpha, and no triangle whose
## every vertex has none.
func _court(court: Dictionary) -> ArrayMesh:
	var reach := float(court.half) * 1.5 + 2.0
	var low := ((court.centre as Vector2) - Vector2.ONE * reach).snapped(Vector2(2.0, 2.0))
	var cells := int(ceil(reach * 2.0 / 2.0)) + 1
	var alphas := PackedFloat32Array()
	for i: int in cells + 1:
		for j: int in cells + 1:
			var inside := _inside_court(low + Vector2(i, j) * 2.0, court)
			alphas.append(smoothstep(0.0, float(court.blend), inside) if inside > 0.0 else 0.0)
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	var indices := PackedInt32Array()
	var used := {}
	for i: int in cells:
		for j: int in cells:
			var a := i * (cells + 1) + j
			for triangle: Array in [[a, a + cells + 1, a + 1], [a + 1, a + cells + 1, a + cells + 2]]:
				if alphas[triangle[0]] <= 0.0 and alphas[triangle[1]] <= 0.0 and alphas[triangle[2]] <= 0.0:
					continue
				for corner: int in triangle:
					if not used.has(corner):
						used[corner] = vertices.size()
						var xz := low + Vector2(corner / (cells + 1), corner % (cells + 1)) * 2.0
						vertices.append(Vector3(xz.x, 0.03, xz.y))
						colours.append(Color(1, 1, 1, alphas[corner]))
					indices.append(int(used[corner]))
	return _mesh(vertices, colours, indices)

func _walk(world: Node3D, node_name: String, mesh: ArrayMesh, material: Material,
		frame: Vector3) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.set_surface_override_material(0, material)
	node.position = frame
	world.add_child(node)
	var body := StaticBody3D.new()
	body.name = node_name + "_WalkSurfaceCollision"
	body.collision_layer = LookGrassBeds.WALK_LAYER
	var shape := CollisionShape3D.new()
	shape.shape = mesh.create_trimesh_shape()
	body.add_child(shape)
	node.add_child(body)
	return node

## A flat grid of `cells` x `cells` quads with one vertex colour. Every mesh
## here is wound to face up, as the exporters' walk surfaces are: the physics
## server's concave ray casts never report a back face.
func _plane(x0: float, z0: float, x1: float, z1: float, y: float, colour: Color,
		cells: int) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	var indices := PackedInt32Array()
	for i: int in cells + 1:
		for j: int in cells + 1:
			vertices.append(Vector3(lerpf(x0, x1, float(i) / cells), y, lerpf(z0, z1, float(j) / cells)))
			colours.append(colour)
	for i: int in cells:
		for j: int in cells:
			var a := i * (cells + 1) + j
			indices.append_array([a, a + cells + 1, a + 1, a + 1, a + cells + 1, a + cells + 2])
	return _mesh(vertices, colours, indices)

## A road deck across x (x0..x1) along z, with coverage 1 in its middle
## third and 0 at its edges, as the exporter writes it.
func _strip(x0: float, x1: float, z0: float, z1: float, y: float) -> ArrayMesh:
	var xs := [x0, lerpf(x0, x1, 0.25), lerpf(x0, x1, 0.75), x1]
	var alphas := [0.0, 1.0, 1.0, 0.0]
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	var indices := PackedInt32Array()
	var rows := 14
	for r: int in rows + 1:
		for c: int in 4:
			vertices.append(Vector3(xs[c], y, lerpf(z0, z1, float(r) / rows)))
			colours.append(Color(1, 1, 1, alphas[c]))
	for r: int in rows:
		for c: int in 3:
			var a := r * 4 + c
			indices.append_array([a, a + 1, a + 4, a + 1, a + 5, a + 4])
	return _mesh(vertices, colours, indices)

## The same, running across x with its coverage across z.
func _strip_x(x0: float, x1: float, z0: float, z1: float, y: float) -> ArrayMesh:
	var zs := [z0, lerpf(z0, z1, 0.25), lerpf(z0, z1, 0.75), z1]
	var alphas := [0.0, 1.0, 1.0, 0.0]
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	var indices := PackedInt32Array()
	var columns := 6
	for c: int in columns + 1:
		for r: int in 4:
			vertices.append(Vector3(lerpf(x0, x1, float(c) / columns), y, zs[r]))
			colours.append(Color(1, 1, 1, alphas[r]))
	for c: int in columns:
		for r: int in 3:
			var a := c * 4 + r
			indices.append_array([a, a + 4, a + 1, a + 1, a + 4, a + 5])
	return _mesh(vertices, colours, indices)

func _mesh(vertices: PackedVector3Array, colours: PackedColorArray,
		indices: PackedInt32Array) -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colours
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
