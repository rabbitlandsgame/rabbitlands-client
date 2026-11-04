extends SceneTree
## Actor geometry lining stage (actor LODs C4): tools/actor_geometry/
## lining_policy.gd on real garments parsed as the runtime parses them, with
## masks in the lining_visibility.py format built in-test.
##
## Checks: bitsets and the lining input are read strictly; a mask binds to the
## parse only by mesh name, surface, triangle count and check centroids; the
## masked base is the kept triangles in parse order; torso soups keep no
## chain and welded leg linings get chains on the masked base; masks that
## remove little, nothing or everything leave the v1 plan byte-identical, and
## so does no input; compaction pays only past its share and run limits, keeps
## the drawn corners, and is refused unless every dropped vertex's position
## survives in the file (the cape's envelope and leg/torso reaches read raw
## positions); the
## runtime applier takes the cooked sidecars, the RenderingServer holds their
## levels, and the cape envelope of a masked torso equals the plain one.
## RABBITLANDS_LINING_MASKS=<folder of <variant>/<stem>.lining.json> also
## binds every real mask in that folder to its garment.

const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const LiningPolicy := preload("res://tools/actor_geometry/lining_policy.gd")
const Cook := preload("res://tools/actor_geometry/cook.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")
const CapeDrapeScript := preload("res://src/actors/cape_drape.gd")

const VARIANTS := "res://assets/actors/native/equipment/variants/human_male/"
## Mossbound Coat: a 14,956-triangle per-face-tile lining soup.
const TORSO := VARIANTS + "amberwood_woodland_cuirass_02.glb"
## Mossbound Legguards: the welded GeneratedLegBacking[WithBoots] twins.
const LEGS := VARIANTS + "amberwood_woodland_legguards_02.glb"
const SWORD := "res://assets/actors/native/equipment/militia_arming_sword.glb"
const ROOT := "user://actor-geometry-lining-test"
const MASKS_ENVIRONMENT := "RABBITLANDS_LINING_MASKS"
const CHECK_TRIANGLES := 8

var _checks := 0
var _failures := 0
var _saved_environment := {}


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	for variable: String in [ActorGeometry.MODE_ENVIRONMENT, ActorGeometry.ROOT_ENVIRONMENT]:
		_saved_environment[variable] = OS.get_environment(variable)
	_expect(GltfQuantization.ensure_registered(), "glTF extensions register on the main thread")
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	print("section: bits and input")
	_check_bits_and_input()
	print("section: compaction helpers")
	_check_compaction_helpers()
	print("section: binding")
	_check_binding()
	print("section: torso")
	_check_torso()
	print("section: legs")
	_check_legs()
	print("section: unchanged plans")
	_check_unchanged()
	print("section: compaction")
	_check_compaction()
	print("section: position guard")
	_check_position_guard()
	print("section: real masks")
	_check_real_masks()
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	for variable: String in _saved_environment:
		if str(_saved_environment[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(_saved_environment[variable]))
	ActorGeometry.reset()
	print("actor geometry lining: %s (%d checks)" % ["PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


# --- bits and input -------------------------------------------------------------

func _check_bits_and_input() -> void:
	for count: int in [1, 7, 8, 9, 23, 1000]:
		var flags := PackedByteArray()
		flags.resize(count)
		for index: int in count:
			flags[index] = int((index * 7) % 3 == 0)
		var text := LiningPolicy.encode_bits(flags)
		_expect(LiningPolicy.decode_bits(text, count) == flags, "a %d-bit mask round-trips through base64" % count)
	# Bit order: bit i of byte i / 8, least significant first (numpy
	# packbits(bitorder="little"), as lining_visibility.py writes it).
	_expect(LiningPolicy.decode_bits("BQ==", 8) == PackedByteArray([1, 0, 1, 0, 0, 0, 0, 0]),
		"0x05 keeps triangles 0 and 2 (little-endian bit order)")
	_expect(LiningPolicy.decode_bits("BQ==", 9).is_empty(), "a bitset of the wrong length is refused")
	_expect(LiningPolicy.decode_bits("/w==", 7).is_empty(), "a bit set past the triangle count is refused")
	_expect(LiningPolicy.decode_bits("B*==", 8).is_empty(), "text that is not base64 is refused")
	_expect(LiningPolicy.decode_bits(5, 8).is_empty(), "a bitset that is not text is refused")

	var good := _input([_entry("GeneratedLegBacking", 0, 4, "Dw==", [[0, 0.0, 0.0, 0.0]])])
	_expect(not LiningPolicy.read_input(good).has("error"), "a well-formed input reads")
	var cases := {
		"schema": _with(good, "schema", 2),
		"mask_sha256": _with(good, "mask_sha256", "abc"),
		"linings": _with(good, "linings", []),
		"lining mesh": _input([_entry("Mossbound Coat", 0, 4, "Dw==", [[0, 0.0, 0.0, 0.0]])]),
		"lining counts": _input([_entry("GeneratedLegBacking", -1, 4, "Dw==", [[0, 0.0, 0.0, 0.0]])]),
		"lining keep": _input([_entry("GeneratedLegBacking", 0, 4, "/w==", [[0, 0.0, 0.0, 0.0]])]),
		"lining check": _input([_entry("GeneratedLegBacking", 0, 4, "Dw==", [[4, 0.0, 0.0, 0.0]])]),
		"duplicate lining": _input([_entry("GeneratedLegBacking", 0, 4, "Dw==", [[0, 0.0, 0.0, 0.0]]),
			_entry("GeneratedLegBacking", 0, 4, "Dw==", [[0, 0.0, 0.0, 0.0]])]),
	}
	for expected: String in cases:
		var problem := str(LiningPolicy.read_input(cases[expected]).get("error", ""))
		_expect(problem.begins_with(expected), "input rejection '%s' (got '%s')" % [expected, problem])
	var missing := _input([_entry("GeneratedLegBacking", 0, 4, "Dw==", [[0, 0.0, 0.0, 0.0]])])
	(missing.linings[0] as Dictionary).erase("check")
	_expect(str(LiningPolicy.read_input(missing).get("error", "")) == "lining check", "an entry without check rows is refused")
	_expect(LiningPolicy.gltf_mesh_name("amberwood_woodland_cuirass_02_GeneratedArmorBacking", "amberwood_woodland_cuirass_02")
		== "GeneratedArmorBacking", "the parse's '<scene>_' mesh prefix is stripped")
	_expect(LiningPolicy.gltf_mesh_name("GeneratedArmorBacking", "") == "GeneratedArmorBacking", "an unprefixed name is kept")


# --- compaction helpers ---------------------------------------------------------

func _check_compaction_helpers() -> void:
	var used := PackedByteArray([0, 1, 1, 0, 1, 0, 0, 0, 1, 1])
	_expect(LiningPolicy.kept_runs(used, 0) == PackedInt32Array([1, 2, 4, 1, 8, 2]), "runs of used vertices")
	_expect(LiningPolicy.kept_runs(used, 1) == PackedInt32Array([1, 4, 8, 2]), "a one-vertex gap merges")
	_expect(LiningPolicy.kept_runs(used, 3) == PackedInt32Array([1, 9]), "a three-vertex gap merges")
	var remap := LiningPolicy.compacted_remap(10, PackedInt32Array([1, 2, 4, 1, 8, 2]))
	_expect(remap == PackedInt32Array([-1, 0, 1, -1, 2, -1, -1, -1, 3, 4]), "the compacted numbering")
	_expect(LiningPolicy.remap_indices(PackedInt32Array([9, 4, 1]), remap) == PackedInt32Array([4, 2, 0]),
		"indices follow the compacted numbering")
	_expect(LiningPolicy.masked_base(PackedInt32Array([0, 1, 2, 3, 4, 5, 6, 7, 8]), PackedByteArray([1, 0, 1]))
		== PackedInt32Array([0, 1, 2, 6, 7, 8]), "the masked base keeps the kept triangles in order")

	var own := _fake_chain([[1.0, 500], [2.0, 250], [5.0, 120], [9.0, 50]])
	var v1 := _fake_chain([[1.0, 600], [2.0, 300], [3.0, 150], [6.0, 70]])
	var merged := LiningPolicy.merge_chains(1000, own.lods, own.levels, v1.lods, v1.levels)
	_expect((merged.levels as Array).map(func(level: Array) -> int: return int(level[0])) == [500, 250, 150, 120, 70, 50]
		and int(merged.from_v1) == 2, "merged chains keep the fewest triangles at every edge (%s)" % [merged.levels])
	merged = LiningPolicy.merge_chains(400, own.lods, own.levels, v1.lods, v1.levels)
	_expect((merged.levels as Array).map(func(level: Array) -> int: return int(level[0])) == [250, 150, 120, 70, 50],
		"no merged level is as large as the masked base (%s)" % [merged.levels])

	var large := PackedByteArray()
	large.resize(8000)
	large.fill(1)
	for vertex: int in range(0, 3000):
		large[vertex] = 0
	var plan := LiningPolicy.compaction_plan(large)
	_expect(plan.has("runs") and int(plan.kept) == 5000 and (plan.runs as PackedInt32Array).size() == 2,
		"3,000 of 8,000 vertices unused in one block compacts to one run (%s)" % [plan.get("reason", "")])
	for vertex: int in range(0, 3000):
		large[vertex] = 1
	for vertex: int in range(0, 1000):
		large[vertex] = 0
	_expect(str(LiningPolicy.compaction_plan(large).get("reason", "")) == "share",
		"1,000 unused of 8,000 (12.5 %%, under the 1,024 floor) does not pay")
	var scattered := PackedByteArray()
	scattered.resize(8000)
	for vertex: int in 8000:
		scattered[vertex] = int(vertex % 4 != 0)
	_expect(str(LiningPolicy.compaction_plan(scattered).get("reason", "")) == "share",
		"every fourth vertex unused: merging gaps to fit the run limit leaves too few to drop")
	# The first half unused; the second half used but for 1,000 one-vertex
	# holes (1,000 runs): a gap of 3 merges them into one run.
	var sparse := PackedByteArray()
	sparse.resize(20000)
	for vertex: int in 20000:
		sparse[vertex] = int(vertex >= 10000 and vertex % 10 != 5)
	plan = LiningPolicy.compaction_plan(sparse)
	_expect(plan.has("runs") and (plan.runs as PackedInt32Array).size() / 2 <= LiningPolicy.COMPACT_MAX_RUNS
		and int(plan.gap) == 3 and int(plan.kept) == 10000 and int(plan.used) == 9000,
		"gaps merge until the runs fit %d (gap %d, %d runs)" % [LiningPolicy.COMPACT_MAX_RUNS,
		int(plan.get("gap", -1)), (plan.get("runs", PackedInt32Array()) as PackedInt32Array).size() / 2])


# --- binding ---------------------------------------------------------------------

func _check_binding() -> void:
	var parsed := _parse(TORSO)
	var mesh_index := _mesh_index(parsed.state, "GeneratedArmorBacking")
	_expect(mesh_index >= 0, "the torso parse holds GeneratedArmorBacking")
	if mesh_index < 0:
		return
	var arrays := _arrays(parsed.state, mesh_index, 0)
	var triangles := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	var keep := _keep_where(arrays, func(centre: Vector3) -> bool: return centre.y > 1.2)
	var entry := _mask_entry(arrays, "GeneratedArmorBacking", 0, keep)
	_expect(LiningPolicy.binding_problem(arrays, Mesh.PRIMITIVE_TRIANGLES, LiningPolicy.read_input(_input([entry])).linings[0]).is_empty(),
		"a mask built on the glTF triangle order binds to the parse")
	var cases := {"centroid": _moved(entry, 0.001), "triangles": _with(entry, "triangles", triangles - 1)}
	# Bits and check rows for the shorter count, so only the count is wrong.
	var shorter: Dictionary = cases.triangles
	shorter["keep"] = LiningPolicy.encode_bits(keep.slice(0, triangles - 1))
	shorter["check"] = (shorter.check as Array).filter(func(row: Array) -> bool: return int(row[0]) < triangles - 1)
	for expected: String in cases:
		var input := _input([cases[expected]])
		var plan := _plan(parsed, TORSO)
		plan = LiningPolicy.apply(parsed.state, plan, input)
		var row: Dictionary = plan.meshes[mesh_index].surfaces[0]
		_expect(row.get("lining", {}).get("status", "") == "rejected" and str(row.lining.reason) == expected,
			"a mask with a wrong %s is refused (%s)" % [expected, row.get("lining", {})])
		_expect(not (plan.sidecar.meshes[mesh_index].surfaces[0] as Dictionary).has("base"),
			"a refused mask leaves the surface as planned (%s)" % expected)
	var plan := LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), _input([_with(entry, "mesh", "GeneratedLegBacking")]))
	_expect(int(plan.changed) == int(_plan(parsed, TORSO).changed), "a mask for a mesh the file lacks changes nothing")
	plan = LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), _input([_with(entry, "primitive", 3)]))
	_expect(plan.meshes[mesh_index].surfaces[0].get("lining", {}).get("reason", "") == "surface",
		"a mask for a surface the mesh lacks is refused")
	plan = LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), {"schema": 9})
	_expect(str(plan.meshes[mesh_index].surfaces[0].get("lining", {}).get("reason", "")).begins_with("input: "),
		"a malformed input marks the lining rows and changes nothing")
	_expect(not (plan.sidecar.meshes[mesh_index].surfaces[0] as Dictionary).has("base"), "... and leaves the plan")


# --- torso (per-face-tile soup) --------------------------------------------------

func _check_torso() -> void:
	var parsed := _parse(TORSO)
	var mesh_index := _mesh_index(parsed.state, "GeneratedArmorBacking")
	if mesh_index < 0:
		return
	var arrays := _arrays(parsed.state, mesh_index, 0)
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	# The hem: the lowest 15 % of the lining's triangles.
	var hem := _quantile_y(arrays, 0.15)
	var keep := _keep_where(arrays, func(centre: Vector3) -> bool: return centre.y >= hem)
	var kept := LiningPolicy.count_kept(keep)
	_expect(kept < indices.size() / 3 and indices.size() / 3 - kept >= LiningPolicy.MASK_MIN_REMOVED_TRIANGLES,
		"the test mask removes %d of %d torso lining triangles" % [indices.size() / 3 - kept, indices.size() / 3])
	var input := _input([_mask_entry(arrays, "GeneratedArmorBacking", 0, keep)])
	var plan := LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), input)
	var record: Dictionary = plan.sidecar.meshes[mesh_index].surfaces[0]
	var row: Dictionary = plan.meshes[mesh_index].surfaces[0]
	_expect(str(row.get("lining", {}).get("status", "")) == "masked", "the torso lining is masked (%s)" % [row.get("lining")])
	_expect(record.has("base") and (record.base as PackedInt32Array).size() == kept * 3,
		"the base holds the %d kept triangles" % kept)
	var same := true
	var at := 0
	for triangle: int in keep.size():
		if keep[triangle] != 1:
			continue
		for corner: int in 3:
			same = same and positions[(record.base as PackedInt32Array)[at + corner]] == positions[indices[triangle * 3 + corner]]
		at += 3
	_expect(same, "the base draws the kept triangles' corners in parse order (winding included)")
	_expect((record.lods as Array).is_empty() and str(row.get("reason", "")) == "per_face_tiles",
		"a per-face-tile soup keeps no chain when masked (%s)" % row.get("reason", ""))
	_expect(not record.has("compact_runs") and str(row.lining.get("compaction", "")) == "share",
		"15 %% of a soup does not pay for compaction (%s)" % [row.lining])
	_expect(int(row.get("base_triangles", 0)) == kept, "the report row carries the masked base size")
	_expect(Format.validate_sidecar(plan.sidecar).is_empty(), "the masked torso sidecar validates (%s)" % Format.validate_sidecar(plan.sidecar))
	var shell := _mesh_index(parsed.state, "Mossbound Coat")
	var plain := _plan(parsed, TORSO)
	_expect(shell >= 0 and plan.sidecar.meshes[shell] == plain.sidecar.meshes[shell], "the shell keeps its v1 chain")

	# The runtime applier takes the sidecar; the vertex buffers stay exactly
	# as parsed, so the cape envelope (vertex positions) is the plain one.
	var cooked := _cook(TORSO, input)
	_expect(cooked.has("entry"), "the torso cooks with its mask (%s)" % cooked.get("reason", ""))
	if not cooked.has("entry"):
		return
	_write_catalog({TORSO: cooked.entry})
	var before := _parse(TORSO)
	var plain_envelope := CapeDrapeScript.envelope(_pieces(before))
	var after := _parse(TORSO)
	var applied := ActorGeometry.apply(after.state, ProjectSettings.globalize_path(TORSO))
	_expect(str(applied.status) == "applied", "the runtime applier applies the masked torso (%s %s)" % [applied.status, applied.reason])
	var lining_after := _arrays(after.state, mesh_index, 0)
	_expect(lining_after[Mesh.ARRAY_INDEX] == record.base, "the parse draws the masked base after apply")
	_expect(lining_after[Mesh.ARRAY_VERTEX] == positions and lining_after[Mesh.ARRAY_NORMAL] == arrays[Mesh.ARRAY_NORMAL]
		and lining_after[Mesh.ARRAY_TEX_UV] == arrays[Mesh.ARRAY_TEX_UV] and lining_after[Mesh.ARRAY_BONES] == arrays[Mesh.ARRAY_BONES]
		and lining_after[Mesh.ARRAY_WEIGHTS] == arrays[Mesh.ARRAY_WEIGHTS], "masking leaves every vertex array as parsed")
	var masked_envelope := CapeDrapeScript.envelope(_pieces(after))
	_expect(not plain_envelope.is_empty() and masked_envelope == plain_envelope,
		"CapeDrape.envelope of the masked torso equals the plain one (%d cells)" % plain_envelope.size())
	print("measure: masked torso apply %.2f ms (source_check file)" % (int(applied.usec) / 1000.0))


# --- legs (welded twins) ---------------------------------------------------------

func _check_legs() -> void:
	var parsed := _parse(LEGS)
	var entries: Array = []
	var expected := {}
	for name: String in ["GeneratedLegBacking", "GeneratedLegBackingWithBoots"]:
		var mesh_index := _mesh_index(parsed.state, name)
		_expect(mesh_index >= 0, "the legguards hold %s" % name)
		if mesh_index < 0:
			return
		var arrays := _arrays(parsed.state, mesh_index, 0)
		# Drop the inner thigh band (|x| < 0.06 m) - a third or so of the lining.
		var keep := _keep_where(arrays, func(centre: Vector3) -> bool: return absf(centre.x) >= 0.06)
		entries.append(_mask_entry(arrays, name, 0, keep))
		expected[mesh_index] = {"keep": keep, "arrays": arrays}
	var plain := _plan(parsed, LEGS)
	var plan := LiningPolicy.apply(parsed.state, _plan(parsed, LEGS), _input(entries))
	_expect(Format.validate_sidecar(plan.sidecar).is_empty(), "the masked legguards sidecar validates")
	for mesh_index: int in expected:
		var record: Dictionary = plan.sidecar.meshes[mesh_index].surfaces[0]
		var row: Dictionary = plan.meshes[mesh_index].surfaces[0]
		var base: PackedInt32Array = record.get("base", PackedInt32Array())
		var kept := LiningPolicy.count_kept(expected[mesh_index].keep)
		_expect(base.size() == kept * 3 and str(row.lining.status) == "masked", "%s: %d triangles kept" % [plan.meshes[mesh_index].name, kept])
		_expect(not (record.lods as Array).is_empty() and str(row.method) == "chain",
			"%s: a welded lining gets a chain on its masked base (%s)" % [plan.meshes[mesh_index].name, row.get("reason", "")])
		# A level is the masked base's own (drawing only its vertices) or one
		# of v1's levels of the unmasked lining, verbatim.
		var in_base := {}
		for index: int in base:
			in_base[index] = true
		var v1_levels := {}
		for level: Array in plain.sidecar.meshes[mesh_index].surfaces[0].lods:
			v1_levels[Format.index_digest(level[1])] = float(level[0])
		var previous := base.size()
		var sound := true
		var edge := 0.0
		for level: Array in record.lods:
			var level_indices: PackedInt32Array = level[1]
			sound = sound and level_indices.size() < previous and float(level[0]) > edge
			var own := true
			for index: int in level_indices:
				own = own and in_base.has(index)
			var from_v1: Variant = v1_levels.get(Format.index_digest(level_indices))
			sound = sound and (own or (from_v1 != null and float(from_v1) == float(level[0])))
			previous = level_indices.size()
			edge = float(level[0])
		_expect(sound, "%s: each level is smaller and switches later, and is the masked base's own or a v1 level with its v1 edge" % plan.meshes[mesh_index].name)
		_expect(int(row.levels[0][0]) <= int(ceil(kept * 0.5 * LodPolicy.TARGET_TOLERANCE)),
			"%s: the first level aims at half the masked base (%d of %d)" % [plan.meshes[mesh_index].name, int(row.levels[0][0]), kept])
		# Never more at any depth than the v1 chain or the masked base's own.
		var v1_row: Dictionary = plain.meshes[mesh_index].surfaces[0]
		var masked_arrays: Array = (expected[mesh_index].arrays as Array).duplicate()
		masked_arrays[Mesh.ARRAY_INDEX] = base
		var own := LodPolicy.plan_surface(masked_arrays, mesh_flags(parsed.state, mesh_index, 0), Mesh.PRIMITIVE_TRIANGLES, 1.0)
		var never_more := true
		var fewer_than_v1 := 0
		for depth: int in range(1, 400):
			var merged_drawn := _drawn(row.levels, kept, depth)
			var v1_drawn := _drawn(v1_row.levels, int(v1_row.triangles), depth)
			var own_drawn := _drawn(own.levels, kept, depth)
			never_more = never_more and merged_drawn <= mini(v1_drawn, own_drawn)
			fewer_than_v1 += int(merged_drawn < v1_drawn)
		_expect(never_more, "%s: the merged chain never draws more than v1 or the masked chain at 1-400 m" % plan.meshes[mesh_index].name)
		_expect(int(row.lining.get("v1_levels_kept", -1)) >= 0, "%s: the summary counts the v1 levels kept (%d)" % [
			plan.meshes[mesh_index].name, int(row.lining.get("v1_levels_kept", -1))])
		_expect(fewer_than_v1 > 0, "%s: masking draws fewer triangles than v1 at some depths" % plan.meshes[mesh_index].name)
		print("measure: %s v1 levels kept %d, own levels %s, merged %s, fewer than v1 at %d of 399 depths" % [
			plan.meshes[mesh_index].name, int(row.lining.get("v1_levels_kept", -1)), own.levels.map(func(l): return l[0]),
			(row.levels as Array).map(func(l): return l[0]), fewer_than_v1])
	# Cooked and applied, the RenderingServer holds every planned level.
	var cooked := _cook(LEGS, _input(entries))
	if not cooked.has("entry"):
		_expect(false, "the legguards cook with their masks")
		return
	_write_catalog({LEGS: cooked.entry})
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ProjectSettings.globalize_path(ROOT).path_join(Format.CATALOG_FILE)))
	var verified := Cook.verify_file(LEGS, ProjectSettings.globalize_path(ROOT), catalog, true)
	_expect(str(verified.status) == "applied" and int(verified.get("scene_mismatches", -1)) == 0
		and int(verified.get("scene_levels", 0)) == int(cooked.levels),
		"the RenderingServer holds the %d cooked levels of the masked legguards (%s, %d seen, %d mismatches)" % [
		int(cooked.levels), verified.status, int(verified.get("scene_levels", 0)), int(verified.get("scene_mismatches", -1))])


# --- unchanged plans ---------------------------------------------------------------

func _check_unchanged() -> void:
	var parsed := _parse(TORSO)
	var mesh_index := _mesh_index(parsed.state, "GeneratedArmorBacking")
	var arrays := _arrays(parsed.state, mesh_index, 0)
	var plain := Format.encode(_plan(parsed, TORSO).sidecar)
	_expect(Format.encode(LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), {}).sidecar) == plain,
		"no lining input leaves the v1 sidecar byte-identical")
	_expect(Format.encode(LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), null).sidecar) == plain,
		"a null lining input leaves it byte-identical")
	var triangles := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	var all := PackedByteArray()
	all.resize(triangles)
	all.fill(1)
	var cases := {"all_kept": all.duplicate()}
	var few := all.duplicate()
	for triangle: int in 40:
		few[triangle * 7] = 0
	cases["below_gain"] = few
	var none := all.duplicate()
	none.fill(0)
	cases["all_hidden"] = none
	for status: String in cases:
		var plan := LiningPolicy.apply(parsed.state, _plan(parsed, TORSO), _input([_mask_entry(arrays, "GeneratedArmorBacking", 0, cases[status])]))
		_expect(str(plan.meshes[mesh_index].surfaces[0].get("lining", {}).get("status", "")) == status
			and Format.encode(plan.sidecar) == plain, "a mask that is %s leaves the v1 sidecar byte-identical" % status)
	var sword := _parse(SWORD)
	var sword_plain := Format.encode(_plan(sword, SWORD).sidecar)
	var sword_plan := LiningPolicy.apply(sword.state, _plan(sword, SWORD),
		_input([_mask_entry(arrays, "GeneratedArmorBacking", 0, cases.all_kept)]))
	_expect(Format.encode(sword_plan.sidecar) == sword_plain, "a mask naming a lining the file lacks changes nothing")


# --- compaction --------------------------------------------------------------------

func _check_compaction() -> void:
	var parsed := _parse(TORSO)
	var mesh_index := _mesh_index(parsed.state, "GeneratedArmorBacking")
	var arrays := _arrays(parsed.state, mesh_index, 0)
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var vertex_count := positions.size()
	# Drop every triangle drawing a vertex in the first 40 % of the buffer: a
	# soup's vertices belong to one triangle each, so they go in few runs.
	var keep := PackedByteArray()
	keep.resize(indices.size() / 3)
	for triangle: int in keep.size():
		var lowest := mini(indices[triangle * 3], mini(indices[triangle * 3 + 1], indices[triangle * 3 + 2]))
		keep[triangle] = int(lowest >= int(vertex_count * 0.4))
	var flags := mesh_flags(parsed.state, mesh_index, 0)
	var lined := LiningPolicy.plan_surface(arrays, flags, Mesh.PRIMITIVE_TRIANGLES, 1.0, keep)
	_expect(lined.has("compact_runs"), "a soup with 40 %% of its vertices unused compacts (%s)" % [lined.summary])
	if not lined.has("compact_runs"):
		return
	var runs: PackedInt32Array = lined.compact_runs
	var kept_vertices := Format.compacted_vertex_count(runs, vertex_count)
	_expect(kept_vertices > 0 and kept_vertices <= int(vertex_count * 0.62) and runs.size() / 2 <= LiningPolicy.COMPACT_MAX_RUNS,
		"%d of %d vertices kept in %d runs" % [kept_vertices, vertex_count, runs.size() / 2])
	var gathered := PackedVector3Array()
	for index: int in range(0, runs.size(), 2):
		gathered.append_array(positions.slice(runs[index], runs[index] + runs[index + 1]))
	var base: PackedInt32Array = lined.base
	var same := Format.indices_within(base, kept_vertices)
	var at := 0
	for triangle: int in keep.size():
		if keep[triangle] != 1:
			continue
		for corner: int in 3:
			same = same and gathered[base[at + corner]] == positions[indices[triangle * 3 + corner]]
		at += 3
	_expect(same, "the compacted base draws exactly the kept corners")
	# Through the cook and the runtime applier.
	var plan := _plan(parsed, TORSO)
	var record: Dictionary = plan.sidecar.meshes[mesh_index].surfaces[0]
	record["base"] = lined.base
	record["compact_runs"] = lined.compact_runs
	record["lods"] = lined.lods
	_expect(Format.validate_sidecar(plan.sidecar).is_empty(), "the compacted sidecar validates (%s)" % Format.validate_sidecar(plan.sidecar))
	var bytes := Format.encode(plan.sidecar)
	var entry := Format.catalog_entry(str(plan.sidecar.source.sha256), int(plan.sidecar.source.bytes), bytes)
	_expect(Cook.write_blob(ProjectSettings.globalize_path(ROOT), entry, bytes), "the compacted blob is written")
	_write_catalog({TORSO: entry})
	var after := _parse(TORSO)
	var began := Time.get_ticks_usec()
	var applied := ActorGeometry.apply(after.state, ProjectSettings.globalize_path(TORSO))
	var elapsed := Time.get_ticks_usec() - began
	var compacted := _arrays(after.state, mesh_index, 0)
	_expect(str(applied.status) == "applied" and (compacted[Mesh.ARRAY_VERTEX] as PackedVector3Array) == gathered
		and compacted[Mesh.ARRAY_INDEX] == base, "the runtime applier compacts the lining by the runs (%s %s)" % [applied.status, applied.reason])
	print("measure: compacted torso apply %.2f ms with %d runs (source_check file)" % [elapsed / 1000.0, runs.size() / 2])
	# The guard: with the file's meshes, compaction is kept only when every
	# dropped vertex's position is still in the file (a soup repeats each
	# position at the corners of neighbouring faces).
	var guard := {"meshes": parsed.state.get_meshes(), "accepted": {}}
	var guarded := LiningPolicy.plan_surface(arrays, flags, Mesh.PRIMITIVE_TRIANGLES, 1.0, keep,
		guard, "%d|0" % mesh_index)
	var kept_positions := LiningPolicy.positions_kept(parsed.state.get_meshes(),
		{"%d|0" % mesh_index: {"runs": runs}})
	_expect(guarded.has("compact_runs") == kept_positions
		and (kept_positions or str(guarded.summary.get("compaction", "")) == "positions"),
		"the guard keeps compaction exactly when every dropped position survives (%s)" % kept_positions)


func mesh_flags(state: GLTFState, mesh_index: int, surface: int) -> int:
	return ((state.get_meshes()[mesh_index] as GLTFMesh).mesh as ImporterMesh).get_surface_format(surface)


# --- position guard (synthetic) -------------------------------------------------------

func _check_position_guard() -> void:
	# A shell ring at 0.20 m and a lining ring at 0.10 m (inside) or 0.24 m
	# (outside), 1.0-1.4 m up, behind the trunk (bearing 0 = -z). Even inside
	# the shell a dropped lining vertex can be what CapeDrape.shin_reach /
	# axis_reach / envelope measure in a cell the shell has no vertex in, so
	# both are refused while the positions exist nowhere else in the file.
	for outside: bool in [false, true]:
		var shell := _ring_mesh("Shell", 0.20, 2400, 0)
		var lining := _ring_mesh("GeneratedArmorBacking", 0.24 if outside else 0.10, 2400, 1)
		var meshes: Array = [shell, lining]
		var arrays := (lining.mesh as ImporterMesh).get_surface_arrays(0)
		var keep := PackedByteArray()
		keep.resize((arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3)
		for triangle: int in keep.size():
			keep[triangle] = int(triangle >= keep.size() / 2)
		var guard := {"meshes": meshes, "accepted": {}}
		var lined := LiningPolicy.plan_surface(arrays, (lining.mesh as ImporterMesh).get_surface_format(0),
			Mesh.PRIMITIVE_TRIANGLES, 1.0, keep, guard, "1|0")
		_expect(not lined.has("compact_runs") and str(lined.summary.get("compaction", "")) == "positions"
			and (guard.accepted as Dictionary).is_empty(),
			"dropping lining vertices found nowhere else (%s the shell) is refused (%s)" % [
			"outside" if outside else "inside", lined.summary])
	# Twin linings at the same positions (legs with and without boots): one
	# may drop what the other still holds, not both.
	var shell := _ring_mesh("Shell", 0.20, 2400, 0)
	var first := _ring_mesh("GeneratedLegBacking", 0.10, 2400, 1)
	var second := _ring_mesh("GeneratedLegBackingWithBoots", 0.10, 2400, 1)
	var twins: Array = [shell, first, second]
	var twin_guard := {"meshes": twins, "accepted": {}}
	var half := PackedByteArray()
	half.resize(2400)
	for triangle: int in 2400:
		half[triangle] = int(triangle >= 1200)
	var results: Array = []
	for mesh_index: int in [1, 2]:
		var mesh: ImporterMesh = (twins[mesh_index] as GLTFMesh).mesh
		results.append(LiningPolicy.plan_surface(mesh.get_surface_arrays(0), mesh.get_surface_format(0),
			Mesh.PRIMITIVE_TRIANGLES, 1.0, half, twin_guard, "%d|0" % mesh_index))
	_expect((results[0] as Dictionary).has("compact_runs") and not (results[1] as Dictionary).has("compact_runs")
		and str(results[1].summary.get("compaction", "")) == "positions",
		"the first twin compacts, the second keeps the last copies (%s / %s)" % [results[0].summary, results[1].summary])
	# The guard's promise, measured: the reaches the cape takes from these
	# pieces are those of the uncompacted file.
	var from := Vector3(0.0, 1.45, 0.0)
	var to := Vector3(0.0, 0.95, 0.0)
	var plain := _points_pieces(twins, {})
	var compacted := _points_pieces(twins, twin_guard.accepted)
	_expect(CapeDrapeScript.shin_reach(plain, from, to, 0.05) == CapeDrapeScript.shin_reach(compacted, from, to, 0.05)
		and CapeDrapeScript.axis_reach(plain, to, from, 0.05) == CapeDrapeScript.axis_reach(compacted, to, from, 0.05)
		and CapeDrapeScript.envelope(plain) == CapeDrapeScript.envelope(compacted),
		"an accepted compaction leaves CapeDrape shin_reach, axis_reach and envelope unchanged")


## Point pieces (what CapeDrape reads: vertex positions) of `meshes`, with the
## dropped vertices of the compactions in `compacted` left out.
func _points_pieces(meshes: Array, compacted: Dictionary) -> Array:
	var pieces: Array = []
	for mesh_index: int in meshes.size():
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		var points := ArrayMesh.new()
		for surface: int in mesh.get_surface_count():
			var positions: PackedVector3Array = mesh.get_surface_arrays(surface)[Mesh.ARRAY_VERTEX]
			var plan: Variant = compacted.get("%d|%d" % [mesh_index, surface])
			if plan is Dictionary and (plan as Dictionary).has("runs"):
				var kept := PackedVector3Array()
				var runs: PackedInt32Array = plan.runs
				for index: int in range(0, runs.size(), 2):
					kept.append_array(positions.slice(runs[index], runs[index] + runs[index + 1]))
				positions = kept
			var arrays: Array = []
			arrays.resize(Mesh.ARRAY_MAX)
			arrays[Mesh.ARRAY_VERTEX] = positions
			points.add_surface_from_arrays(Mesh.PRIMITIVE_POINTS, arrays)
		pieces.append({"mesh": points})
	return pieces


## A GLTFMesh holding one soup surface of `triangles` triangles on a ring of
## radius `radius` round the trunk line at y 1.0-1.4 m.
func _ring_mesh(name: String, radius: float, triangles: int, seed_offset: int) -> GLTFMesh:
	var positions := PackedVector3Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	for triangle: int in triangles:
		var angle := deg_to_rad(-80.0 + 160.0 * float(triangle) / float(triangles)) + seed_offset * 0.0001
		var y := 1.0 + 0.4 * fposmod(float(triangle) * 0.618, 1.0)
		for corner: int in 3:
			var at := angle + corner * 0.002
			positions.append(Vector3(sin(at) * radius, y + corner * 0.003, -cos(at) * radius))
			normals.append(Vector3(sin(at), 0.0, -cos(at)))
			indices.append(positions.size() - 1)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = positions
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ImporterMesh.new()
	mesh.resource_name = name
	mesh.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var gltf := GLTFMesh.new()
	gltf.mesh = mesh
	return gltf


# --- real masks (optional) --------------------------------------------------------------

func _check_real_masks() -> void:
	var folder := OS.get_environment(MASKS_ENVIRONMENT)
	if folder.is_empty():
		print("real masks: skipped (set %s)" % MASKS_ENVIRONMENT)
		return
	var bound := 0
	var masked := 0
	var removed := 0
	var total := 0
	for variant: String in DirAccess.get_directories_at(folder):
		for name: String in DirAccess.get_files_at(folder.path_join(variant)):
			if not name.ends_with(".lining.json"):
				continue
			var text := FileAccess.get_file_as_string(folder.path_join(variant).path_join(name))
			var mask: Dictionary = JSON.parse_string(text)
			var path := str(mask.source.path)
			var parsed := _parse(path)
			var plan := LiningPolicy.apply(parsed.state, _plan(parsed, path),
				LiningPolicy.input_from_mask(mask, Format.sha256_hex(text.to_utf8_buffer())))
			_expect(Format.validate_sidecar(plan.sidecar).is_empty(), "%s: the sidecar validates" % name)
			for mesh_row: Dictionary in plan.meshes:
				for row: Dictionary in mesh_row.surfaces:
					if not row.has("lining"):
						continue
					_expect(str(row.lining.status) != "rejected", "%s %s binds (%s)" % [name, mesh_row.name, row.lining])
					bound += 1
					total += int(row.triangles)
					if str(row.lining.status) == "masked":
						masked += 1
						removed += int(row.lining.removed_triangles)
	print("real masks: %d linings bound, %d masked, %d of %d triangles removed" % [bound, masked, removed, total])
	_expect(bound > 0, "the real mask folder held masks")


# --- helpers ---------------------------------------------------------------------------

func _parse(path: String) -> Dictionary:
	return Cook.parse(ProjectSettings.globalize_path(path))


func _plan(parsed: Dictionary, path: String) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	return Cook.plan_state(parsed.state, path, FileAccess.get_sha256(absolute), _length(absolute), 1.0)


## cook.gd cook_file with the lining stage (the HOOK this chunk asks for):
## parse, plan, lining stage, validate, write the blob. Returns {entry, levels}
## or {reason}.
func _cook(path: String, lining: Dictionary) -> Dictionary:
	var parsed := _parse(path)
	var plan := LiningPolicy.apply(parsed.state, _plan(parsed, path), lining)
	var problem := Format.validate_sidecar(plan.sidecar)
	if not problem.is_empty():
		return {"reason": problem}
	var bytes := Format.encode(plan.sidecar)
	var entry := Format.catalog_entry(str(plan.sidecar.source.sha256), int(plan.sidecar.source.bytes), bytes)
	if not Cook.write_blob(ProjectSettings.globalize_path(ROOT), entry, bytes):
		return {"reason": "write"}
	return {"entry": entry, "levels": int(plan.levels)}


func _write_catalog(entries: Dictionary) -> void:
	var root := ProjectSettings.globalize_path(ROOT)
	DirAccess.make_dir_recursive_absolute(root)
	var catalog := Format.new_catalog("file")
	catalog.entries = entries
	var file := FileAccess.open(root.path_join(Format.CATALOG_FILE), FileAccess.WRITE)
	file.store_string(JSON.stringify(catalog))
	file.close()
	OS.set_environment(ActorGeometry.MODE_ENVIRONMENT, "sidecar")
	OS.set_environment(ActorGeometry.ROOT_ENVIRONMENT, root)
	ActorGeometry.reset()


## The pieces CapeDrape.envelope reads in the game: every mesh the scene draws.
func _pieces(parsed: Dictionary) -> Array:
	var scene: Node = (parsed.document as GLTFDocument).generate_scene(parsed.state)
	var pieces: Array = []
	for node: Node in scene.find_children("*", "MeshInstance3D", true, false):
		pieces.append({"mesh": (node as MeshInstance3D).mesh})
	scene.free()
	return pieces


func _mesh_index(state: GLTFState, name: String) -> int:
	var meshes: Array = state.get_meshes()
	for index: int in meshes.size():
		var mesh: ImporterMesh = (meshes[index] as GLTFMesh).mesh
		if mesh != null and LiningPolicy.gltf_mesh_name(str(mesh.resource_name), state.get_scene_name()) == name:
			return index
	return -1


func _arrays(state: GLTFState, mesh_index: int, surface: int) -> Array:
	return ((state.get_meshes()[mesh_index] as GLTFMesh).mesh as ImporterMesh).get_surface_arrays(surface)


func _fake_chain(spec: Array) -> Dictionary:
	var lods: Array = []
	var levels: Array = []
	for item: Array in spec:
		var indices := PackedInt32Array()
		indices.resize(int(item[1]) * 3)
		lods.append([float(item[0]), indices])
		levels.append([int(item[1]), float(item[0]), 0.0, 0])
	return {"lods": lods, "levels": levels}


## Triangles Godot draws at this depth (lod_bias 1, reference camera, scale 1)
## for a surface of `base` triangles with these [triangles, edge, ...] levels.
func _drawn(levels: Array, base: int, depth: float) -> int:
	var drawn := base
	for level: Array in levels:
		if LodPolicy.switch_depth(float(level[1])) > depth:
			break
		drawn = int(level[0])
	return drawn


func _quantile_y(arrays: Array, fraction: float) -> float:
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var heights := PackedFloat32Array()
	for triangle: int in indices.size() / 3:
		heights.append((positions[indices[triangle * 3]].y + positions[indices[triangle * 3 + 1]].y
			+ positions[indices[triangle * 3 + 2]].y) / 3.0)
	heights.sort()
	return heights[int(heights.size() * fraction)]


func _keep_where(arrays: Array, rule: Callable) -> PackedByteArray:
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var keep := PackedByteArray()
	keep.resize(indices.size() / 3)
	for triangle: int in keep.size():
		var centre := (positions[indices[triangle * 3]] + positions[indices[triangle * 3 + 1]]
			+ positions[indices[triangle * 3 + 2]]) / 3.0
		keep[triangle] = int(bool(rule.call(centre)))
	return keep


## A lining entry as lining_visibility.py writes it: the keep bitset and the
## centroids of CHECK_TRIANGLES evenly spread triangles (rounded to 1e-6).
func _mask_entry(arrays: Array, mesh: String, primitive: int, keep: PackedByteArray) -> Dictionary:
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var count := indices.size() / 3
	var check: Array = []
	var picks := {}
	for step: int in mini(CHECK_TRIANGLES, count):
		picks[roundi(step * (count - 1) / float(maxi(CHECK_TRIANGLES - 1, 1)))] = true
	var ordered: Array = picks.keys()
	ordered.sort()
	for triangle: int in ordered:
		var centre := (positions[indices[triangle * 3]] + positions[indices[triangle * 3 + 1]]
			+ positions[indices[triangle * 3 + 2]]) / 3.0
		check.append([triangle, snappedf(centre.x, 1.0e-6), snappedf(centre.y, 1.0e-6), snappedf(centre.z, 1.0e-6)])
	return _entry(mesh, primitive, count, LiningPolicy.encode_bits(keep), check)


func _entry(mesh: String, primitive: int, triangles: int, keep: String, check: Array) -> Dictionary:
	return {"mesh": mesh, "primitive": primitive, "triangles": triangles, "keep": keep, "check": check}


func _input(linings: Array) -> Dictionary:
	return {"schema": LiningPolicy.INPUT_SCHEMA, "mask_sha256": "a".repeat(64), "linings": linings}


func _with(value: Dictionary, key: String, replacement: Variant) -> Dictionary:
	var copy := value.duplicate(true)
	copy[key] = replacement
	return copy


func _moved(entry: Dictionary, offset: float) -> Dictionary:
	var copy := entry.duplicate(true)
	var row: Array = copy.check[0]
	row[2] = float(row[2]) + offset
	return copy


func _length(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	return file.get_length() if file != null else 0


func _remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for file: String in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	for directory: String in DirAccess.get_directories_at(path):
		_remove_tree(path.path_join(directory))
	DirAccess.remove_absolute(path)


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)
