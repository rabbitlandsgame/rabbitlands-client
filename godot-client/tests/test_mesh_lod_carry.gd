extends SceneTree
## Actor LODs C6: every derivation that rebuilds an actor surface keeps the
## source's index LOD chains, with valid indices, and a source without chains
## still gives exactly the surface it gave before.
## Run with --headless --script res://tests/test_mesh_lod_carry.gd.
##
## Chains on the real meshes are made in-test: the race body's are Godot's own
## `ImporterMesh.generate_lods`; the cape has none from it (its surfaces are
## soups), so its chains are hand-made subsets of the base triangles. Each
## derivation runs twice on the same vertices, with and without chains; the
## vertex, attribute, skin and index buffers must match byte for byte.

const MESH_LODS := preload("res://src/actors/mesh_lods.gd")
const EMBLEMS := preload("res://src/actors/cape_emblems.gd")
const MOUNTED := preload("res://src/actors/cape_mounted_attachment.gd")
const APPROVED := preload("res://src/actors/cape_approved_data.gd")
const CAPE := "res://assets/actors/native/equipment/generic_cape.glb"
const TORSO := "res://assets/actors/native/equipment/variants/human_male/militia_torso_armor_03.glb"
const BODY := "res://assets/actors/native/races/luminous_male.glb"
const PROFILE := "wardrobe"
## Hand-made cape chains: every 2nd, then every 4th base triangle.
const CAPE_EDGES := [0.02, 0.08]

var _checks := 0
var _failures := 0
var _timings := {}
var _notes := {}


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_read_and_decode()
	_check_sanitize()
	_check_remap()
	_check_metadata()
	var root := GlbSceneCache.instantiate(BODY) as Node3D
	_expect(root != null, "the Human body instantiates")
	if root != null:
		var skeleton := root.find_children("*", "Skeleton3D", true, false)[0] as Skeleton3D
		var body := root.find_child("body", true, false) as MeshInstance3D
		var bodies := _body_pair(body.mesh as ArrayMesh)
		_check_cape()
		_check_mounted(skeleton)
		_check_neck(bodies, body, skeleton)
		_check_beard(bodies, body, root, skeleton)
		root.free()
	NecklineSkin.clear()
	PortraitGroom.clear()
	GlbSceneCache.clear()
	var costs := []
	for key: String in _timings:
		costs.append("%s %.2f ms" % [key, float(_timings[key])])
	print("mesh LOD carry costs (debug editor build, headless, single runs): ", ", ".join(costs))
	print("mesh LOD carry notes: ", _notes)
	print("mesh LOD carry: %s (%d checks)" % [
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


# --- module -----------------------------------------------------------------

## A flat grid of `side` x `side` vertices, two triangles per cell.
func _grid_arrays(side: int) -> Array:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	for row: int in side:
		for column: int in side:
			vertices.append(Vector3(column * 0.01, row * 0.01, 0.0))
			normals.append(Vector3.BACK)
	var indices := PackedInt32Array()
	for row: int in side - 1:
		for column: int in side - 1:
			var a := row * side + column
			indices.append_array(PackedInt32Array([a, a + side, a + 1, a + 1, a + side, a + side + 1]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	return arrays


## Every `step`-th base triangle, as a chain level.
func _every(indices: PackedInt32Array, step: int) -> PackedInt32Array:
	var kept := PackedInt32Array()
	for triangle: int in range(0, indices.size(), 3 * step):
		kept.append_array(indices.slice(triangle, triangle + 3))
	return kept


func _check_read_and_decode() -> void:
	MESH_LODS.reset_counters()
	var arrays := _grid_arrays(21)
	var base: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var plain := ArrayMesh.new()
	plain.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_expect(MESH_LODS.read(plain, 0).is_empty(), "a surface without chains reads as none")
	_expect(MESH_LODS.read(plain, 3).is_empty() and MESH_LODS.read(null, 0).is_empty(),
		"a missing surface or mesh reads as none")
	# Odd triangle counts exercise the padded 16-bit word decode.
	var odd := _every(base, 3)
	if (odd.size() / 3) % 2 == 0:
		odd = odd.slice(0, odd.size() - 3)
	var lods := {0.01: _every(base, 2), 0.05: odd, 0.2: base.slice(0, 3)}
	var chained := ArrayMesh.new()
	chained.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods)
	var read := MESH_LODS.read(chained, 0)
	_expect(_same_lods(read, lods), "16-bit chains read back exactly (odd and single-triangle levels)")
	_expect(int(MESH_LODS.snapshot().server_reads) == 2,
		"a foreign mesh is read from the server")
	# 260 x 260 = 67,600 vertices: Godot switches the surface to 32-bit indices.
	var wide_arrays := _grid_arrays(260)
	var wide_base: PackedInt32Array = wide_arrays[Mesh.ARRAY_INDEX]
	var tail := wide_base.slice(wide_base.size() - 300)
	var wide_lods := {0.03: _every(wide_base, 2), 0.3: tail}
	var wide := ArrayMesh.new()
	wide.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, wide_arrays, [], wide_lods)
	var wide_read := MESH_LODS.read(wide, 0)
	_expect(_same_lods(wide_read, wide_lods), "32-bit chains read back exactly")
	_expect(_max_index(wide_read) > MESH_LODS.SHORT_INDEX_VERTICES,
		"the 32-bit fixture really addresses vertices past 65,536")
	var copy := MESH_LODS.read(chained, 0)
	var edges := copy.keys()
	(copy[edges[0]] as PackedInt32Array).fill(0)
	copy[edges[1]] = PackedInt32Array()
	_expect(_same_lods(MESH_LODS.read(chained, 0), lods), "callers get copies they may edit")
	# Decode cost of a body-sized chain (u16 words vs the per-index reader the
	# other carriers use).
	var body_sized := _grid_arrays(64)
	var big: PackedInt32Array = body_sized[Mesh.ARRAY_INDEX]
	var big_mesh := ArrayMesh.new()
	big_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, body_sized, [],
		{0.04: _every(big, 2), 0.14: _every(big, 5)})
	var began := Time.get_ticks_usec()
	for _repeat: int in 10:
		MESH_LODS.server_lods(big_mesh, 0)
	_timings["server_lods 7.9k-tri chain"] = (Time.get_ticks_usec() - began) / 10000.0
	began = Time.get_ticks_usec()
	for _repeat: int in 10:
		TorsoBodyCover._surface_lods(big_mesh, 0)
	_timings["TorsoBodyCover._surface_lods same chain"] = (Time.get_ticks_usec() - began) / 10000.0
	_expect(_same_lods(MESH_LODS.server_lods(big_mesh, 0), TorsoBodyCover._surface_lods(big_mesh, 0)),
		"the word decode equals the existing per-index reader")


func _check_sanitize() -> void:
	MESH_LODS.reset_counters()
	var arrays := _grid_arrays(11)
	var base: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var vertices := 121
	var half := _every(base, 2)
	var quarter := _every(base, 4)
	var valid := MESH_LODS.sanitize({0.08: quarter, 0.02: half}, vertices, base.size())
	_expect(valid.keys() == [0.02, 0.08] and valid[0.02] == half and valid[0.08] == quarter,
		"valid levels are kept, in ascending edge order")
	_expect(int(MESH_LODS.snapshot().rejected_levels) == 0, "valid levels are not counted as rejected")
	var out_of_range := half.duplicate()
	out_of_range[4] = vertices
	var negative := half.duplicate()
	negative[0] = -1
	var cases := {
		"empty level": {0.02: PackedInt32Array()},
		"partial triangle": {0.02: half.slice(0, half.size() - 1)},
		"not smaller than the base": {0.02: base},
		"index past the last vertex": {0.02: out_of_range},
		"negative index": {0.02: negative},
		"zero edge": {0.0: half},
		"negative edge": {-1.0: half},
		"NaN edge": {NAN: half},
		"infinite edge": {INF: half},
		"not a packed index array": {0.02: [0, 1, 2]},
		"string key": {"0.02": half},
	}
	for label: String in cases:
		MESH_LODS.reset_counters()
		var kept := MESH_LODS.sanitize(cases[label], vertices, base.size())
		_expect(kept.is_empty() and int(MESH_LODS.snapshot().rejected_levels) == 1,
			"sanitize drops one level: " + label)
	MESH_LODS.reset_counters()
	var growing := MESH_LODS.sanitize({0.02: quarter, 0.08: half}, vertices, base.size())
	_expect(growing.keys() == [0.02] and int(MESH_LODS.snapshot().rejected_levels) == 1,
		"a level no smaller than the one before it is dropped")
	MESH_LODS.reset_counters()
	_expect(MESH_LODS.sanitize({0.02: half}, vertices, base.size(), Mesh.PRIMITIVE_LINES).is_empty()
		and MESH_LODS.sanitize({0.02: half}, vertices, 0).is_empty()
		and MESH_LODS.sanitize({0.02: half}, 0, base.size()).is_empty(),
		"lines, unindexed and empty surfaces carry no chains")
	_expect(MESH_LODS.sanitize({}, vertices, base.size()).is_empty(), "no chains stay no chains")
	# What sanitize keeps, Godot keeps: nothing is dropped by the engine.
	var mesh := ArrayMesh.new()
	MESH_LODS.add_surface(mesh, Mesh.PRIMITIVE_TRIANGLES, arrays, [],
		{0.08: quarter, 0.02: half, 0.5: out_of_range, 0.9: PackedInt32Array()}, 0)
	_expect(_same_lods(MESH_LODS.server_lods(mesh, 0), {0.02: half, 0.08: quarter}),
		"the engine accepts every sanitized level and only those")


func _check_remap() -> void:
	var lods := {0.1: PackedInt32Array([0, 1, 2, 2, 1, 3, 3, 4, 5]), 0.4: PackedInt32Array([4, 5, 6])}
	var map := PackedInt32Array([10, 11, 12, 13, -1, 15])
	var mapped := MESH_LODS.remap(lods, map)
	_expect(mapped.keys() == [0.1] and mapped[0.1] == PackedInt32Array([10, 11, 12, 12, 11, 13]),
		"remap keeps whole triangles whose corners all map, renumbered, and drops emptied levels")


func _check_metadata() -> void:
	MESH_LODS.reset_counters()
	var arrays := _grid_arrays(11)
	var base: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var lods := {0.02: _every(base, 2), 0.08: _every(base, 4)}
	var mesh := ArrayMesh.new()
	MESH_LODS.add_surface(mesh, Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, 0)
	MESH_LODS.add_surface(mesh, Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods, 0)
	var reads: Dictionary = MESH_LODS.snapshot()
	_expect(MESH_LODS.read(mesh, 0).is_empty() and _same_lods(MESH_LODS.read(mesh, 1), lods),
		"a mesh built through add_surface answers per surface")
	var after: Dictionary = MESH_LODS.snapshot()
	_expect(int(after.server_reads) == int(reads.server_reads) and int(after.stored_reads) == int(reads.stored_reads) + 2,
		"... from its metadata, with no readback")
	_expect(_same_lods(MESH_LODS.server_lods(mesh, 1), lods), "the metadata matches the server")
	var duplicate := mesh.duplicate() as ArrayMesh
	MESH_LODS.reset_counters()
	_expect(_same_lods(MESH_LODS.read(duplicate, 1), MESH_LODS.server_lods(duplicate, 1))
		and int(MESH_LODS.snapshot().stored_reads) == 0,
		"copied metadata on another mesh is not trusted (bound to the RID)")
	# Metadata copied by reference onto another mesh (as mesh_rest_coordinates
	# and the RL head neck normals copy meta) must not let an add_surface on
	# the copy overwrite the source's record.
	var recorded := ArrayMesh.new()
	MESH_LODS.add_surface(recorded, Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods, 0)
	var sharing := ArrayMesh.new()
	sharing.set_meta(MESH_LODS.META, recorded.get_meta(MESH_LODS.META))
	MESH_LODS.add_surface(sharing, Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, 0)
	MESH_LODS.reset_counters()
	var kept_record := MESH_LODS.read(recorded, 0)
	var shared_counts: Dictionary = MESH_LODS.snapshot()
	_expect(_same_lods(kept_record, lods) and int(shared_counts.stored_reads) == 1
		and int(shared_counts.server_reads) == 0,
		"an add_surface on a mesh holding copied metadata leaves the source's record intact")
	_expect(MESH_LODS.read(sharing, 0).is_empty() and int(MESH_LODS.snapshot().server_reads) == 0,
		"... and the copy answers for its own surface from its own record")
	# A surface replaced outside add_surface no longer matches its record.
	var other := _grid_arrays(5)
	mesh.surface_remove(1)
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, other)
	MESH_LODS.reset_counters()
	_expect(MESH_LODS.read(mesh, 1).is_empty() and int(MESH_LODS.snapshot().server_reads) == 1,
		"a surface whose sizes changed is read from the server again")
	# Foreign meshes: one server read, then the memo, until the surface changes.
	MESH_LODS.clear()
	MESH_LODS.reset_counters()
	var foreign := ArrayMesh.new()
	foreign.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], lods)
	var first := MESH_LODS.read(foreign, 0)
	var second := MESH_LODS.read(foreign, 0)
	var counted: Dictionary = MESH_LODS.snapshot()
	_expect(_same_lods(first, lods) and _same_lods(second, lods)
		and int(counted.server_reads) == 1 and int(counted.memo_reads) == 1,
		"a foreign mesh is read back once, then remembered")
	(second.values()[0] as PackedInt32Array).fill(0)
	_expect(_same_lods(MESH_LODS.read(foreign, 0), lods), "the memo hands out copies")
	foreign.clear_surfaces()
	foreign.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, other)
	MESH_LODS.reset_counters()
	_expect(MESH_LODS.read(foreign, 0).is_empty() and int(MESH_LODS.snapshot().server_reads) == 1,
		"the memo forgets a surface whose sizes changed")
	var kept: Array[ArrayMesh] = []
	for index: int in MESH_LODS.MEMO_LIMIT + 8:
		var extra := ArrayMesh.new()
		extra.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, other)
		kept.append(extra)
		MESH_LODS.read(extra, 0)
	_expect(int(MESH_LODS.snapshot().remembered_meshes) == MESH_LODS.MEMO_LIMIT,
		"the memo stays bounded at %d meshes" % MESH_LODS.MEMO_LIMIT)
	MESH_LODS.clear()
	_expect(int(MESH_LODS.snapshot().remembered_meshes) == 0, "clear() forgets every mesh")


# --- cape: fold, armour fit, emblem, mounted attachment ---------------------

func _check_cape() -> void:
	var pieces: Array = ReplicatedActor3D._equipment_pieces(CAPE)
	_expect(pieces.size() == 1, "the cape is one mesh")
	if pieces.is_empty():
		return
	var source := pieces[0]["mesh"] as ArrayMesh
	var bones: PackedStringArray = pieces[0]["bones"]
	var chains := _cape_chains(source)
	var chained := _copy_mesh(source, chains)
	var plain := _copy_mesh(source, [])
	_expect(_buffers_equal(chained, plain, "fixture"), "the chained and plain cape fixtures share every buffer")
	for surface: int in chained.get_surface_count():
		_expect(_same_lods(MESH_LODS.server_lods(chained, surface), chains[surface]),
			"cape fixture surface %d carries its hand-made chain" % surface)
	var grid := CapeDrape.envelope(ReplicatedActor3D._equipment_pieces(TORSO))
	_expect(not grid.is_empty(), "the militia torso has an envelope")
	MESH_LODS.clear()
	var source_reads := 0
	for case: String in ["relaxed", "fitted"]:
		var envelope := PackedFloat32Array() if case == "relaxed" else grid
		MESH_LODS.reset_counters()
		var began := Time.get_ticks_usec()
		var draped := CapeDrape.drape(chained, bones, envelope)
		_timings["drape %s, chains" % case] = (Time.get_ticks_usec() - began) / 1000.0
		var reads: Dictionary = MESH_LODS.snapshot()
		began = Time.get_ticks_usec()
		var draped_plain := CapeDrape.drape(plain, bones, envelope)
		_timings["drape %s, no chains" % case] = (Time.get_ticks_usec() - began) / 1000.0
		_expect(draped != chained and draped_plain != plain, "the %s drape builds a new mesh" % case)
		_check_carried(draped, chains, "%s drape" % case)
		_check_no_chains(draped_plain, "%s drape without chains" % case)
		_expect(_buffers_equal(draped, draped_plain, "%s drape" % case),
			"the %s drape's buffers are the same with and without chains" % case)
		# Only the imported source is read back, once; the fold's own result
		# answers the fit from its metadata, and the next drape of the same
		# cape from the memo.
		source_reads += int(reads.server_reads)
		_expect(int(reads.server_reads) + int(reads.memo_reads) == source.get_surface_count(),
			"the %s drape reads only the source's %d surfaces from the server or memo (got %d + %d)" % [
				case, source.get_surface_count(), int(reads.server_reads), int(reads.memo_reads)])
		MESH_LODS.reset_counters()
		var embroidered := EMBLEMS._projected_mesh(draped) as ArrayMesh
		_expect(int(MESH_LODS.snapshot().server_reads) == 0,
			"the emblem reads the draped cape's chains without a readback (%s)" % case)
		var embroidered_plain := EMBLEMS._projected_mesh(draped_plain) as ArrayMesh
		_check_carried(embroidered, chains, "%s emblem" % case)
		_check_no_chains(embroidered_plain, "%s emblem without chains" % case)
		_expect(_buffers_equal(embroidered, embroidered_plain, "%s emblem" % case),
			"the %s emblem's buffers are the same with and without chains" % case)
		for surface: int in embroidered.get_surface_count():
			var uv2: Variant = embroidered.surface_get_arrays(surface)[Mesh.ARRAY_TEX_UV2]
			_expect(uv2 is PackedVector2Array and (uv2 as PackedVector2Array).size()
				== embroidered.surface_get_array_len(surface),
				"%s emblem surface %d still gains its UV2" % [case, surface])
	_expect(source_reads == source.get_surface_count(),
		"two drapes of one cape read its surfaces back once (%d reads)" % source_reads)


func _check_mounted(skeleton: Skeleton3D) -> void:
	_expect(APPROVED.compatible(skeleton), "the Human rig takes the approved cape")
	var pieces: Array = ReplicatedActor3D._equipment_pieces(CAPE)
	if pieces.is_empty() or not APPROVED.compatible(skeleton):
		return
	var approved := APPROVED.fit_mesh(PROFILE, pieces[0]["mesh"] as Mesh)
	_expect(approved != null, "the approved %s cape loads" % PROFILE)
	if approved == null:
		return
	var chains := _cape_chains(approved)
	var chained := _copy_mesh(approved, chains)
	var plain := _copy_mesh(approved, [])
	var relief := MOUNTED.recommended_relief(PROFILE)
	for mode: String in ["spine_neck", "rigid_neck"]:
		var began := Time.get_ticks_usec()
		var fitted := MOUNTED.build(PROFILE, chained, skeleton, mode, relief)
		_timings["mounted %s, chains" % mode] = (Time.get_ticks_usec() - began) / 1000.0
		var fitted_plain := MOUNTED.build(PROFILE, plain, skeleton, mode, relief)
		_expect(not fitted.is_empty() and not fitted_plain.is_empty(),
			"the %s mounted attachment builds with and without chains" % mode)
		if fitted.is_empty() or fitted_plain.is_empty():
			continue
		_check_carried(fitted.mesh as ArrayMesh, chains, "mounted %s" % mode)
		_check_no_chains(fitted_plain.mesh as ArrayMesh, "mounted %s without chains" % mode)
		_expect(_buffers_equal(fitted.mesh as ArrayMesh, fitted_plain.mesh as ArrayMesh, "mounted " + mode),
			"the %s attachment's buffers are the same with and without chains" % mode)
		_expect(is_equal_approx(float(fitted.reference_error_m), float(fitted_plain.reference_error_m)),
			"the %s attachment's reference error does not depend on chains" % mode)


# --- body derivations: neck skin and beard ----------------------------------

## The body with Godot's generated chains and without, built the same way.
func _body_pair(source: ArrayMesh) -> Dictionary:
	var chained := ImporterMesh.new()
	var plain := ImporterMesh.new()
	for importer: ImporterMesh in [chained, plain]:
		for surface: int in source.get_surface_count():
			importer.add_surface(source.surface_get_primitive_type(surface),
				source.surface_get_arrays(surface), source.surface_get_blend_shape_arrays(surface), {},
				source.surface_get_material(surface), source.surface_get_name(surface),
				source.surface_get_format(surface))
	chained.generate_lods(60, 25, [])
	var result := {"chained": chained.get_mesh(), "plain": plain.get_mesh()}
	var lods := MESH_LODS.server_lods(result.chained as ArrayMesh, 0)
	_expect(lods.size() >= 2, "Godot generates at least two levels for the Human body (%d)" % lods.size())
	_expect(_buffers_equal(result.chained as ArrayMesh, result.plain as ArrayMesh, "body fixture"),
		"the chained and plain body fixtures share every buffer")
	return result


func _check_neck(bodies: Dictionary, body: MeshInstance3D, skeleton: Skeleton3D) -> void:
	var chained_body := bodies.chained as ArrayMesh
	MESH_LODS.reset_counters()
	var began := Time.get_ticks_usec()
	var with_chains := NecklineSkin.build(chained_body, body.skin, skeleton)
	_timings["neck skin, chains"] = (Time.get_ticks_usec() - began) / 1000.0
	began = Time.get_ticks_usec()
	var without := NecklineSkin.build(bodies.plain as ArrayMesh, body.skin, skeleton)
	_timings["neck skin, no chains"] = (Time.get_ticks_usec() - began) / 1000.0
	_expect(not with_chains.is_empty() and not without.is_empty(), "the neck skin builds")
	if with_chains.is_empty() or without.is_empty():
		return
	var neck := with_chains.mesh as ArrayMesh
	var neck_plain := without.mesh as ArrayMesh
	_expect(with_chains.surfaces == without.surfaces, "chains do not change which body surfaces get a neck")
	_check_no_chains(neck_plain, "neck skin without chains")
	_expect(_buffers_equal(neck, neck_plain, "neck skin"), "the neck skin's buffers are the same with and without chains")
	var worst := 0.0
	for index: int in neck.get_surface_count():
		var parent := MESH_LODS.server_lods(chained_body, int(with_chains.surfaces[index]))
		var first := INF
		for edge: Variant in parent:
			first = minf(first, float(edge))
		var lods := MESH_LODS.server_lods(neck, index)
		var arrays := neck.surface_get_arrays(index)
		var base: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		_expect(lods.size() == 1 and lods.has(first),
			"neck surface %d has one level, at the body's first edge %.4f" % [index, first])
		if lods.size() != 1:
			continue
		var coarse: PackedInt32Array = lods.values()[0]
		_expect(coarse.size() * NecklineSkin.STEPS == base.size(), "the neck's coarse level is a quarter of its triangles")
		_expect(MESH_LODS.in_range(coarse, points.size()), "the neck's coarse indices are in range")
		var block := (NecklineSkin.STEPS + 1) * 2
		var rows_ok := true
		for corner: int in coarse:
			var row := (corner % block) / 2
			rows_ok = rows_ok and (row == 0 or row == NecklineSkin.STEPS)
		_expect(rows_ok, "the neck's coarse level uses only each strip's top and bottom rows")
		worst = maxf(worst, _strip_twist(points, base, coarse))
	_notes["neck coarse level rest deviation mm"] = snappedf(worst * 1000.0, 0.001)
	# The body's own first level moves its surface by centimetres (Godot's
	# error at 0.04 edge); the strip's twist is a millimetre.
	_expect(worst < 0.002, "the coarse neck level stays within 2 mm of the full strip at rest (%.3f mm)" % (worst * 1000.0))


## Furthest centroid of a fine strip triangle from the coarse level's surface.
func _strip_twist(points: PackedVector3Array, base: PackedInt32Array, coarse: PackedInt32Array) -> float:
	var worst := 0.0
	var block := (NecklineSkin.STEPS + 1) * 2
	for triangle: int in range(0, base.size(), 3):
		var strip := base[triangle] / block
		var centroid := (points[base[triangle]] + points[base[triangle + 1]] + points[base[triangle + 2]]) / 3.0
		var nearest := INF
		for coarse_triangle: int in range(strip * 6, strip * 6 + 6, 3):
			nearest = minf(nearest, _point_triangle(centroid, points[coarse[coarse_triangle]],
				points[coarse[coarse_triangle + 1]], points[coarse[coarse_triangle + 2]]))
		worst = maxf(worst, nearest)
	return worst


func _point_triangle(p: Vector3, a: Vector3, b: Vector3, c: Vector3) -> float:
	var normal := (b - a).cross(c - a)
	if normal.length_squared() > 1e-20:
		normal = normal.normalized()
		var projected := p - normal * normal.dot(p - a)
		var inside := true
		for edge: Array in [[a, b], [b, c], [c, a]]:
			var from: Vector3 = edge[0]
			var to: Vector3 = edge[1]
			if (to - from).cross(projected - from).dot(normal) < -1e-12:
				inside = false
		if inside:
			return p.distance_to(projected)
	var best := INF
	for edge: Array in [[a, b], [b, c], [c, a]]:
		best = minf(best, p.distance_to(Geometry3D.get_closest_point_to_segment(p, edge[0], edge[1])))
	return best


func _check_beard(bodies: Dictionary, body: MeshInstance3D, root: Node3D, skeleton: Skeleton3D) -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var config: Dictionary = models["luminous_male"]
	var original := body.mesh
	var parent := MESH_LODS.server_lods(bodies.chained as ArrayMesh, 0)
	var parent_sizes := {}
	for edge: Variant in parent:
		parent_sizes[float(edge)] = (parent[edge] as PackedInt32Array).size()
	for style: int in [2, 3, 4, 5]:
		var look := {"hair": 106, "skin": 2, "facial_hair": style}
		var meshes := {}
		for kind: String in ["chained", "plain"]:
			body.mesh = bodies[kind]
			var began := Time.get_ticks_usec()
			PortraitGroom.apply(root, skeleton, look, config)
			_timings["beard %d, %s" % [style, kind]] = (Time.get_ticks_usec() - began) / 1000.0
			var beard := root.get_node_or_null("PortraitFacialHair") as MeshInstance3D
			_expect(beard != null and beard.mesh != null, "beard style %d builds (%s)" % [style, kind])
			if beard != null:
				meshes[kind] = beard.mesh
		if meshes.size() != 2:
			continue
		var beard := meshes.chained as ArrayMesh
		_check_no_chains(meshes.plain as ArrayMesh, "beard %d without chains" % style)
		_expect(_buffers_equal(beard, meshes.plain as ArrayMesh, "beard %d" % style),
			"beard style %d's buffers are the same with and without chains" % style)
		var levels := 0
		for surface: int in beard.get_surface_count():
			var lods := MESH_LODS.server_lods(beard, surface)
			levels += lods.size()
			var vertices := beard.surface_get_array_len(surface)
			var previous := beard.surface_get_array_index_len(surface)
			var ordered := lods.keys()
			ordered.sort()
			for edge: Variant in ordered:
				var chain: PackedInt32Array = lods[edge]
				_expect(parent_sizes.has(float(edge)), "beard %d level %.4f is one of the face's levels" % [style, float(edge)])
				_expect(MESH_LODS.in_range(chain, vertices) and chain.size() % 3 == 0 and chain.size() < previous,
					"beard %d level %.4f is valid and smaller than the level before" % [style, float(edge)])
				_expect(chain.size() <= int(parent_sizes.get(float(edge), 0)),
					"beard %d level %.4f is cut from the face's level" % [style, float(edge)])
				previous = chain.size()
		_notes["beard %d levels" % style] = levels
		if style == 5:
			_expect(levels >= 1, "the full beard steps down with the face (%d levels)" % levels)
	body.mesh = original
	var old := root.get_node_or_null("PortraitFacialHair")
	if old != null:
		root.remove_child(old)
		old.free()


# --- helpers -----------------------------------------------------------------

func _cape_chains(source: ArrayMesh) -> Array:
	var chains := []
	for surface: int in source.get_surface_count():
		var base: PackedInt32Array = source.surface_get_arrays(surface)[Mesh.ARRAY_INDEX]
		chains.append({float(CAPE_EDGES[0]): _every(base, 2), float(CAPE_EDGES[1]): _every(base, 4)})
	return chains


## A copy of every surface, with `chains[surface]` (none when `chains` is empty).
func _copy_mesh(source: ArrayMesh, chains: Array) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	for surface: int in source.get_surface_count():
		mesh.add_surface_from_arrays(source.surface_get_primitive_type(surface),
			source.surface_get_arrays(surface), [], chains[surface] if not chains.is_empty() else {},
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		mesh.surface_set_material(surface, source.surface_get_material(surface))
		mesh.surface_set_name(surface, source.surface_get_name(surface))
	return mesh


func _check_carried(mesh: ArrayMesh, chains: Array, label: String) -> void:
	_expect(mesh != null and mesh.get_surface_count() == chains.size(), label + " keeps every surface")
	if mesh == null:
		return
	for surface: int in mini(mesh.get_surface_count(), chains.size()):
		var lods := MESH_LODS.server_lods(mesh, surface)
		_expect(lods.size() == (chains[surface] as Dictionary).size(),
			"%s surface %d keeps its %d levels (has %d)" % [label, surface, (chains[surface] as Dictionary).size(), lods.size()])
		_expect(_same_lods(lods, chains[surface]), "%s surface %d keeps the chains index for index" % [label, surface])
		var vertices := mesh.surface_get_array_len(surface)
		for edge: Variant in lods:
			_expect(MESH_LODS.in_range(lods[edge], vertices), "%s surface %d level %.3f is in range" % [label, surface, float(edge)])


func _check_no_chains(mesh: ArrayMesh, label: String) -> void:
	var none := mesh != null
	if mesh != null:
		for surface: int in mesh.get_surface_count():
			none = none and MESH_LODS.server_lods(mesh, surface).is_empty()
	_expect(none, label + " has no chains, as before")


func _buffers_equal(a: ArrayMesh, b: ArrayMesh, label: String) -> bool:
	if a == null or b == null or a.get_surface_count() != b.get_surface_count():
		print("  %s: surface counts differ" % label)
		return false
	for surface: int in a.get_surface_count():
		var left: Dictionary = RenderingServer.mesh_get_surface(a.get_rid(), surface)
		var right: Dictionary = RenderingServer.mesh_get_surface(b.get_rid(), surface)
		for key: String in ["format", "primitive", "vertex_count", "index_count", "vertex_data",
				"attribute_data", "skin_data", "index_data", "aabb", "bone_aabbs"]:
			if left.get(key) != right.get(key):
				print("  %s surface %d: %s differs" % [label, surface, key])
				return false
		if a.surface_get_material(surface) != b.surface_get_material(surface) \
				or a.surface_get_name(surface) != b.surface_get_name(surface):
			print("  %s surface %d: material or name differs" % [label, surface])
			return false
	return true


func _same_lods(a: Dictionary, b: Dictionary) -> bool:
	if a.size() != b.size():
		return false
	for key: Variant in b:
		var found := false
		for other: Variant in a:
			if is_equal_approx(float(other), float(key)):
				found = (a[other] as PackedInt32Array) == (b[key] as PackedInt32Array)
		if not found:
			return false
	return true


func _max_index(lods: Dictionary) -> int:
	var best := -1
	for chain: PackedInt32Array in lods.values():
		var sorted := chain.duplicate()
		sorted.sort()
		best = maxi(best, sorted[sorted.size() - 1])
	return best


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		return
	_failures += 1
	push_error("mesh LOD carry: " + message)
	print("  FAIL ", message)
