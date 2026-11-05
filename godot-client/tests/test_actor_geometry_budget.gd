extends SceneTree
## Actor geometry budget stage (actor LODs C11): tools/actor_geometry/
## budget_policy.gd on real race-refit helmets parsed as the runtime parses
## them, against their Human sources.
##
## Checks: the input is read strictly; the guard is LOD policy v1's pixel clamp
## at GUARD_METRES; level choice (capped = the largest level within the share
## that meets the guard, partial = the smallest level above it that does,
## kept otherwise); the chain below a capped base follows LOD policy v1; on the
## Votary Sun Headband (38,558 triangles, Human source 1,285) and an Orun helm
## the base becomes a verbatim simplifier level, smaller levels switch later,
## and the vertex buffers stay as parsed; a refit within its budget, no input,
## a rejected input, skinned and lining-masked surfaces leave the v1 plan
## byte-identical; two surfaces share the limit by their triangles; a soup
## with per-face UV tiles is never simplified and a line surface adds no
## triangles (review fixes); cooked and
## applied with the runtime applier, the generated mesh draws the capped base
## and the RenderingServer holds its levels; cooking twice is byte-identical.

const Format := preload("res://src/actors/actor_geometry_format.gd")
const ActorGeometry := preload("res://src/actors/actor_geometry.gd")
const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const LiningPolicy := preload("res://tools/actor_geometry/lining_policy.gd")
const BudgetPolicy := preload("res://tools/actor_geometry/budget_policy.gd")
const Cook := preload("res://tools/actor_geometry/cook.gd")
const GltfQuantization := preload("res://src/world/gltf_quantization.gd")

const VARIANTS := "res://assets/actors/native/equipment/variants/"
## Sun Headband (3:170): the Votary male refit is 30x its Human source.
const VOTARY_BAND := VARIANTS + "votary_male/sunmane_steppe_headgear_06.glb"
const HUMAN_BAND := VARIANTS + "human_male/sunmane_steppe_headgear_06.glb"
## Same item, Glasswarden refit: as many triangles as the Human source.
const GLASSWARDEN_BAND := VARIANTS + "glasswarden_male/sunmane_steppe_headgear_06.glb"
## Eloria helm 01 (3:125): the Orun male refit is 2.5x its Human source.
const ORUN_HELM := VARIANTS + "orun_male/legendary_eloria_helm_01.glb"
const HUMAN_HELM := VARIANTS + "human_male/legendary_eloria_helm_01.glb"
## A skinned garment (welded leg lining twins + shell).
const LEGS := VARIANTS + "human_male/amberwood_woodland_legguards_02.glb"
const ROOT := "user://actor-geometry-budget-test"

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
	print("section: settings and input")
	_check_settings_and_input()
	print("section: level choice")
	_check_choice()
	print("section: chain below")
	_check_chain_below()
	print("section: votary band")
	_check_capped(VOTARY_BAND, HUMAN_BAND)
	print("section: orun helm")
	_check_capped(ORUN_HELM, HUMAN_HELM)
	print("section: unchanged plans")
	_check_unchanged()
	print("section: shares")
	_check_shares()
	print("section: soups and lines")
	_check_soups_and_lines()
	print("section: cook and apply")
	_check_cook_and_apply()
	_remove_tree(ProjectSettings.globalize_path(ROOT))
	for variable: String in _saved_environment:
		if str(_saved_environment[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(_saved_environment[variable]))
	ActorGeometry.reset()
	print("actor geometry budget: %s (%d checks)" % ["PASS" if _failures == 0 else "FAIL (%d)" % _failures, _checks])
	quit(1 if _failures > 0 else 0)


# --- settings and input -----------------------------------------------------------

func _check_settings_and_input() -> void:
	_expect(BudgetPolicy.limit_for(1285) == 2570 and BudgetPolicy.limit_for(1) == 2, "the limit is 2x the Human source")
	# 3 px at 8 m on the 1920 px reference camera: 8 * 1.658 * 3 / 1920 m.
	var guard := BudgetPolicy.guard_error(1.0)
	_expect(absf(guard - 8.0 * LodPolicy.lod_multiplier() * 3.0 / 1920.0) < 1.0e-9 and absf(guard - 0.02072) < 1.0e-4,
		"the guard is LOD policy v1's 3 px clamp at 8 m (%.5f m)" % guard)
	# A level whose error equals the guard switches exactly at GUARD_METRES
	# under LOD policy v1's own error term.
	var edge := guard / LodPolicy.MAX_ERROR_PX
	_expect(absf(LodPolicy.switch_depth(edge) - BudgetPolicy.GUARD_METRES) < 1.0e-6,
		"an error at the guard switches at %.1f m in LOD policy v1" % LodPolicy.switch_depth(edge))
	_expect(absf(BudgetPolicy.guard_error(2.0) - guard * 0.5) < 1.0e-9, "the guard is in mesh units: half at model scale 2")

	var good := _input(1285)
	var read := BudgetPolicy.read_input(good)
	_expect(not read.has("error") and int(read.reference_triangles) == 1285 and str(read.reference) == HUMAN_BAND,
		"a well-formed input reads")
	_expect(not BudgetPolicy.read_input(_with(good, "reference_triangles", 1285.0)).has("error"),
		"whole JSON floats read as counts")
	var cases := {
		"not a dictionary": "budget",
		"key extra": _with(good, "extra", 1),
		"schema": _with(good, "schema", 2),
		"reference": _with(good, "reference", "res://assets/actors/native/rl_heads/head.glb"),
		"reference_sha256": _with(good, "reference_sha256", "ABC"),
		"reference_triangles": _with(good, "reference_triangles", 0),
	}
	for expected: String in cases:
		var problem := str(BudgetPolicy.read_input(cases[expected]).get("error", ""))
		_expect(problem == expected, "input refused: %s (got '%s')" % [expected, problem])
	_expect(str(BudgetPolicy.read_input(_with(good, "reference_triangles", 12.5)).get("error", "")) == "reference_triangles",
		"a fractional triangle count is refused")
	_expect(str(BudgetPolicy.read_input(_with(good, "reference", "res://data/actors/x.glb")).get("error", "")) == "reference",
		"a reference outside the actor scope is refused")


# --- level choice -----------------------------------------------------------------

func _check_choice() -> void:
	# Raw levels as LodPolicy.exact_chain returns them: by ascending error.
	var raw := _fake_raw([[2000, 0.001], [1000, 0.004], [500, 0.01], [250, 0.05], [20, 0.2]])
	var picked := BudgetPolicy.choose_level(raw, 4000, 1200, 0.02)
	_expect(int(picked.index) == 1 and str(picked.status) == "capped", "capped: the largest level within the share (1000 of 1200)")
	picked = BudgetPolicy.choose_level(raw, 4000, 600, 0.02)
	_expect(int(picked.index) == 2 and str(picked.status) == "capped", "capped: 500 within a share of 600")
	picked = BudgetPolicy.choose_level(raw, 4000, 300, 0.02)
	_expect(int(picked.index) == 2 and str(picked.status) == "partial",
		"partial: 250 misses the guard, so the smallest level above the share that meets it (500)")
	picked = BudgetPolicy.choose_level(raw, 4000, 300, 0.06)
	_expect(int(picked.index) == 3 and str(picked.status) == "capped", "a looser guard caps at 250")
	picked = BudgetPolicy.choose_level(raw, 4000, 10, 0.5)
	_expect(int(picked.index) == 3, "levels below MIN_LEVEL_TRIANGLES are never a base (20 skipped, 250 partial)")
	picked = BudgetPolicy.choose_level(raw, 2600, 300, 0.0005)
	_expect(int(picked.index) == -1 and str(picked.reason) == "guard", "kept (guard) when no level meets the clamp")
	picked = BudgetPolicy.choose_level(_fake_raw([[2400, 0.001]]), 2600, 300, 0.02)
	_expect(int(picked.index) == -1 and str(picked.reason) == "guard",
		"a partial base must remove MIN_REMOVED_SHARE (2400 of 2600 does not)")
	picked = BudgetPolicy.choose_level([], 2600, 300, 0.02)
	_expect(int(picked.index) == -1 and str(picked.reason) == "no_level", "kept (no_level) without simplifier levels")
	picked = BudgetPolicy.choose_level(_fake_raw([[3000, 0.001], [1500, 0.002]]), 2600, 1300, 0.02)
	_expect(int(picked.index) == 1 and str(picked.status) == "partial",
		"a level not smaller than the surface is never a base (3000 >= 2600 skipped; 1500 partial)")


func _check_chain_below() -> void:
	var raw := _fake_raw([[2000, 0.001], [1000, 0.004], [500, 0.01], [240, 0.05], [130, 0.06], [50, 0.2]])
	var chain := BudgetPolicy.chain_below(raw, 1, 1.0)
	var sizes: Array = (chain.levels as Array).map(func(level: Array) -> int: return int(level[0]))
	_expect(sizes == [500, 240, 130, 50], "below a 1000 base: levels near 50 / 25 / 12 / 5 %% (%s)" % [sizes])
	var sound := true
	var previous_edge := 0.0
	var previous_size := 1000
	for index: int in (chain.levels as Array).size():
		var level: Array = chain.levels[index]
		var expected_edge := LodPolicy.edge_for(int(level[3]), float(level[2]), 1.0)
		sound = sound and float(level[1]) == expected_edge and float(level[1]) > previous_edge and int(level[0]) < previous_size \
			and float((chain.lods[index] as Array)[0]) == expected_edge
		previous_edge = float(level[1])
		previous_size = int(level[0])
	_expect(sound, "edges are LOD policy v1's (band or 3 px error), strictly later and smaller")
	_expect(((chain.levels as Array)[1] as Array)[3] == 1 and LodPolicy.switch_depth(float(chain.levels[1][1])) >= 18.0,
		"the 25 %% level waits for the 18 m band at least")
	chain = BudgetPolicy.chain_below(raw, 5, 1.0)
	_expect((chain.lods as Array).is_empty(), "nothing below the smallest level")


# --- real refits -------------------------------------------------------------------

func _check_capped(path: String, reference: String) -> void:
	var name := path.get_file().get_basename() + " (" + path.get_base_dir().get_file() + ")"
	var reference_triangles := _triangles(_parse(reference))
	var limit := BudgetPolicy.limit_for(reference_triangles)
	var parsed := _parse(path)
	var arrays := _arrays(parsed.state, 0, 0)
	var triangles := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	_expect(triangles > limit, "%s: %d triangles, over 2x its Human source (%d)" % [name, triangles, reference_triangles])
	var plain := _plan(parsed, path)
	var plan := BudgetPolicy.apply(parsed.state, _plan(parsed, path), _input(reference_triangles, reference))
	_expect(Format.validate_sidecar(plan.sidecar).is_empty(), "%s: the capped sidecar validates" % name)
	var record: Dictionary = plan.sidecar.meshes[0].surfaces[0]
	var row: Dictionary = plan.meshes[0].surfaces[0]
	var budget: Dictionary = row.get("budget", {})
	var status := str(budget.get("status", ""))
	_expect(status in ["capped", "partial"], "%s: the stage caps it (%s %s)" % [name, status, budget.get("reason", "")])
	if not record.has("base"):
		return
	var base: PackedInt32Array = record.base
	var raw := LodPolicy.exact_chain(arrays, _flags(parsed.state, 0, 0))
	var digests := {}
	for level: Array in raw:
		digests[Format.index_digest(level[0])] = float(level[1])
	var error: Variant = digests.get(Format.index_digest(base))
	_expect(error != null and float(error) == float(budget.error), "%s: the base is a verbatim simplifier level (error %.4f)" % [name, float(budget.get("error", -1.0))])
	_expect(float(budget.error) <= BudgetPolicy.guard_error(1.0), "%s: its error meets the 3 px clamp at 8 m" % name)
	_expect(int(row.base_triangles) == base.size() / 3 and int(budget.base_triangles) == base.size() / 3,
		"%s: the row reports the drawn base (%d triangles)" % [name, base.size() / 3])
	if status == "capped":
		_expect(base.size() / 3 <= limit, "%s: capped within %d" % [name, limit])
		var larger_within := false
		for level: Array in raw:
			var size := (level[0] as PackedInt32Array).size() / 3
			larger_within = larger_within or (size <= limit and size > base.size() / 3 and float(level[1]) <= BudgetPolicy.guard_error(1.0))
		_expect(not larger_within, "%s: no larger level within the limit meets the guard" % name)
	else:
		var smaller_ok := false
		var within_misses := false
		for level: Array in raw:
			var size := (level[0] as PackedInt32Array).size() / 3
			smaller_ok = smaller_ok or (size < base.size() / 3 and size >= LodPolicy.MIN_LEVEL_TRIANGLES and float(level[1]) <= BudgetPolicy.guard_error(1.0))
			within_misses = within_misses or (size <= limit and size >= LodPolicy.MIN_LEVEL_TRIANGLES and float(level[1]) > BudgetPolicy.guard_error(1.0))
		_expect(not smaller_ok and base.size() / 3 > limit, "%s: partial = the smallest level that meets the guard (%d, above %d)" % [name, base.size() / 3, limit])
		_expect(within_misses, "%s: partial only because the levels within the limit miss the guard" % name)
	if path == VOTARY_BAND:
		# The plan's example (38,558 -> 2,408): that level's error (4.2 cm, 6 px
		# at 8 m) misses the guard, so the band keeps its 4,818 level.
		_expect(status == "partial" and base.size() / 3 == 4818,
			"%s: partial at 4,818, not the plan's unguarded 2,408 (%s %d)" % [name, status, base.size() / 3])
	# Indices in range of the untouched vertex buffer.
	_expect(Format.indices_within(base, (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()) and not record.has("compact_runs"),
		"%s: the base indexes the parsed vertex buffer, uncompacted" % name)
	var previous := base.size()
	var edge := 0.0
	var sound := true
	for level: Array in record.lods:
		sound = sound and (level[1] as PackedInt32Array).size() < previous and float(level[0]) > edge \
			and digests.has(Format.index_digest(level[1]))
		previous = (level[1] as PackedInt32Array).size()
		edge = float(level[0])
	_expect(sound, "%s: each level below is a smaller simplifier level and switches later (%s)" % [name, (row.levels as Array).map(func(l): return l[0])])
	_expect(int(plan.changed) == 1 and int(plan.levels) == (record.lods as Array).size(), "%s: changed and levels recounted" % name)
	# Never more at any depth than v1, and fewer close up.
	var v1_row: Dictionary = plain.meshes[0].surfaces[0]
	var never_more := true
	for depth: int in range(1, 400):
		never_more = never_more and _drawn(row.levels, base.size() / 3, depth) <= _drawn(v1_row.levels, triangles, depth)
	_expect(never_more, "%s: never draws more than the v1 chain at 1-400 m" % name)
	_expect(_drawn(row.levels, base.size() / 3, 3.0) <= maxi(limit, base.size() / 3) and _drawn(v1_row.levels, triangles, 3.0) == triangles,
		"%s: at 3 m it draws %d instead of %d" % [name, _drawn(row.levels, base.size() / 3, 3.0), triangles])
	print("measure: %s %d -> base %d (%s, error %.4f, guard %.4f, limit %d), levels %s at %s m; v1 %s at %s m" % [
		name, triangles, base.size() / 3, status, float(budget.error), BudgetPolicy.guard_error(1.0), limit,
		(row.levels as Array).map(func(l): return l[0]), (row.levels as Array).map(func(l): return snappedf(LodPolicy.switch_depth(float(l[1])), 0.1)),
		(v1_row.levels as Array).map(func(l): return l[0]), (v1_row.levels as Array).map(func(l): return snappedf(LodPolicy.switch_depth(float(l[1])), 0.1))])


func _check_unchanged() -> void:
	var parsed := _parse(VOTARY_BAND)
	var plain := Format.encode(_plan(parsed, VOTARY_BAND).sidecar)
	for case: Variant in [null, {}]:
		var plan := BudgetPolicy.apply(parsed.state, _plan(parsed, VOTARY_BAND), case)
		_expect(Format.encode(plan.sidecar) == plain and not (plan.meshes[0].surfaces[0] as Dictionary).has("budget"),
			"no budget input (%s): the v1 sidecar byte for byte" % [case])
	var rejected := BudgetPolicy.apply(parsed.state, _plan(parsed, VOTARY_BAND), _with(_input(1285), "schema", 7))
	_expect(Format.encode(rejected.sidecar) == plain and str(rejected.meshes[0].surfaces[0].budget.status) == "rejected",
		"a rejected input leaves the v1 sidecar and says why (%s)" % str(rejected.meshes[0].surfaces[0].budget.get("reason", "")))
	var roomy := BudgetPolicy.apply(parsed.state, _plan(parsed, VOTARY_BAND), _input(20000))
	_expect(Format.encode(roomy.sidecar) == plain and str(roomy.meshes[0].surfaces[0].budget.status) == "within",
		"a reference of 20,000 triangles: within budget, v1 sidecar")
	# A refit no larger than its Human source.
	var glass := _parse(GLASSWARDEN_BAND)
	var glass_plain := Format.encode(_plan(glass, GLASSWARDEN_BAND).sidecar)
	var reference := _triangles(_parse(HUMAN_BAND))
	var within := BudgetPolicy.apply(glass.state, _plan(glass, GLASSWARDEN_BAND), _input(reference))
	_expect(Format.encode(within.sidecar) == glass_plain and str(within.meshes[0].surfaces[0].budget.status) == "within"
		and int(within.meshes[0].surfaces[0].budget.limit) == 2 * reference,
		"the Glasswarden refit (%d triangles, limit %d) keeps its v1 sidecar" % [_triangles(glass), 2 * reference])
	# Skinned surfaces are not rigid socket meshes.
	var legs := _parse(LEGS)
	var legs_plain := Format.encode(_plan(legs, LEGS).sidecar)
	var skinned := BudgetPolicy.apply(legs.state, _plan(legs, LEGS), _input(100))
	var all_kept := true
	for mesh_row: Dictionary in skinned.meshes:
		for row: Dictionary in mesh_row.surfaces:
			var note: Dictionary = row.get("budget", {})
			all_kept = all_kept and str(note.get("status", "")) == "kept" and str(note.get("reason", "")) in ["skinned", "small"]
	_expect(Format.encode(skinned.sidecar) == legs_plain and all_kept, "skinned garment surfaces keep their v1 plan (kept: skinned)")
	# A base another stage set (the lining masks) is left alone.
	var masked_plan := _plan(parsed, VOTARY_BAND)
	var indices: PackedInt32Array = _arrays(parsed.state, 0, 0)[Mesh.ARRAY_INDEX]
	var half := indices.slice(0, (indices.size() / 6) * 3)
	masked_plan.sidecar.meshes[0].surfaces[0]["base"] = half
	masked_plan.sidecar.meshes[0].surfaces[0]["lods"] = []
	var before := Format.encode(masked_plan.sidecar)
	var masked := BudgetPolicy.apply(parsed.state, masked_plan, _input(1285))
	_expect(Format.encode(masked.sidecar) == before and str(masked.meshes[0].surfaces[0].budget.reason) == "masked",
		"a surface with a base from another stage is kept (masked)")


func _check_shares() -> void:
	# Two copies of the Sun Headband in one mesh: each gets half the limit
	# (a reference of 4,818 triangles: each copy's 4,818 level fits its share).
	var parsed := _parse(VOTARY_BAND)
	var source: ImporterMesh = _mesh(parsed.state, 0)
	var arrays := source.get_surface_arrays(0)
	var flags := source.get_surface_format(0)
	var doubled := ImporterMesh.new()
	doubled.set_name("Doubled")
	for copy: int in 2:
		doubled.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, source.get_surface_material(0), "copy%d" % copy, flags)
	var gltf_mesh := GLTFMesh.new()
	gltf_mesh.mesh = doubled
	var state := GLTFState.new()
	state.set_meshes([gltf_mesh])
	var plan := Cook.plan_state(state, VOTARY_BAND, "b".repeat(64), 1, 1.0)
	var reference := 4818
	plan = BudgetPolicy.apply(state, plan, _input(reference))
	var limit := BudgetPolicy.limit_for(reference)
	var drawn := 0
	var shares_ok := true
	for surface: int in 2:
		var note: Dictionary = plan.meshes[0].surfaces[surface].budget
		shares_ok = shares_ok and int(note.share) == limit / 2 and str(note.status) == "capped"
		drawn += int(note.base_triangles)
	_expect(shares_ok and drawn <= limit, "two equal surfaces share the limit (%d each, %d drawn of %d)" % [limit / 2, drawn, limit])
	_expect(Format.validate_sidecar(plan.sidecar).is_empty(), "the two-surface sidecar validates")


func _check_soups_and_lines() -> void:
	# A triangle soup whose corners disagree on UV (every 5th triangle on its
	# own atlas tile): LOD policy v1 gives it no chain, although the simplifier
	# offers levels that would meet the guard. The budget stage must not draw
	# one of them as the base either (review fix).
	var tiled := _soup(20, 5)
	var v1 := LodPolicy.plan_surface(tiled, 0, Mesh.PRIMITIVE_TRIANGLES, 1.0)
	var raw := LodPolicy.exact_chain(tiled, 0)
	_expect(str(v1.reason) == "per_face_tiles" and not raw.is_empty(),
		"precondition: a per-face-tile soup gets no v1 chain, though the simplifier offers %d levels" % raw.size())
	var capped := BudgetPolicy.plan_surface(tiled, 0, 100, 1.0)
	_expect(str(capped.status) == "kept" and str(capped.reason) == "per_face_tiles" and (capped.base as PackedInt32Array).is_empty(),
		"a per-face-tile soup is never given a simplified base (%s %s)" % [capped.status, capped.reason])
	var state := _state_with([[Mesh.PRIMITIVE_TRIANGLES, tiled]])
	var plain := Format.encode(Cook.plan_state(state, VOTARY_BAND, "c".repeat(64), 1, 1.0).sidecar)
	var plan := BudgetPolicy.apply(state, Cook.plan_state(state, VOTARY_BAND, "c".repeat(64), 1, 1.0), _input(50))
	var note: Dictionary = plan.meshes[0].surfaces[0].get("budget", {})
	_expect(Format.encode(plan.sidecar) == plain and str(note.get("status", "")) == "kept"
		and str(note.get("reason", "")) == "per_face_tiles", "the soup file keeps its v1 sidecar byte for byte (kept: per_face_tiles)")
	# A soup whose welded corners agree on UV is simplified by v1, so it is
	# budgeted like any rigid surface.
	var coherent := _soup(20, 0)
	_expect(str(LodPolicy.plan_surface(coherent, 0, Mesh.PRIMITIVE_TRIANGLES, 1.0).method) == "chain"
		and str(BudgetPolicy.plan_surface(coherent, 0, 100, 1.0).status) in ["capped", "partial"],
		"a soup with coherent UVs is still budgeted")
	# Line primitives draw no triangles: the Human source counts triangle-list
	# primitives only, so a line surface must not push a refit over its limit
	# (review fix). The band alone is exactly at 2x a 19,279-triangle source.
	var band := _parse(VOTARY_BAND)
	var band_arrays := _arrays(band.state, 0, 0)
	var lines: Array = []
	lines.resize(Mesh.ARRAY_MAX)
	lines[Mesh.ARRAY_VERTEX] = band_arrays[Mesh.ARRAY_VERTEX]
	var line_indices := PackedInt32Array()
	for index: int in 3000:
		line_indices.append(index)
	lines[Mesh.ARRAY_INDEX] = line_indices
	var mixed := _state_with([[Mesh.PRIMITIVE_TRIANGLES, band_arrays, _flags(band.state, 0, 0)], [Mesh.PRIMITIVE_LINES, lines]])
	var band_triangles := (band_arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	var mixed_plain := Format.encode(Cook.plan_state(mixed, VOTARY_BAND, "d".repeat(64), 1, 1.0).sidecar)
	var within := BudgetPolicy.apply(mixed, Cook.plan_state(mixed, VOTARY_BAND, "d".repeat(64), 1, 1.0),
		_input(band_triangles / 2))
	var band_note: Dictionary = within.meshes[0].surfaces[0].get("budget", {})
	_expect(BudgetPolicy.limit_for(band_triangles / 2) == band_triangles and Format.encode(within.sidecar) == mixed_plain
		and str(band_note.get("status", "")) == "within" and int(band_note.get("file_triangles", -1)) == band_triangles,
		"a line surface adds no triangles: the band at exactly 2x stays within (%s, file %s)" % [band_note.get("status", ""),
		band_note.get("file_triangles", "")])


func _check_cook_and_apply() -> void:
	var reference := _triangles(_parse(HUMAN_BAND))
	var cooked := _cook(VOTARY_BAND, _input(reference))
	var again := _cook(VOTARY_BAND, _input(reference))
	_expect(cooked.has("entry") and again.has("entry") and str(cooked.entry.sidecar_sha256) == str(again.entry.sidecar_sha256),
		"cooking twice gives the same sidecar bytes")
	if not cooked.has("entry"):
		return
	_write_catalog({VOTARY_BAND: cooked.entry})
	var parsed := _parse(VOTARY_BAND)
	var plain_arrays := _arrays(parsed.state, 0, 0)
	var applied := ActorGeometry.apply(parsed.state, ProjectSettings.globalize_path(VOTARY_BAND))
	_expect(str(applied.status) == "applied", "the runtime applier takes the capped sidecar (%s %s)" % [applied.status, applied.reason])
	var after := _arrays(parsed.state, 0, 0)
	var vertices_same := true
	for slot: int in Mesh.ARRAY_MAX:
		if slot != Mesh.ARRAY_INDEX:
			vertices_same = vertices_same and str(var_to_bytes(after[slot])) == str(var_to_bytes(plain_arrays[slot]))
	_expect(vertices_same, "every vertex array is byte-identical after the apply")
	_expect((after[Mesh.ARRAY_INDEX] as PackedInt32Array).size() == int(cooked.base) * 3,
		"the applied surface draws the capped base (%d triangles)" % int(cooked.base))
	var scene: Node = (parsed.document as GLTFDocument).generate_scene(parsed.state)
	var meshes := scene.find_children("*", "MeshInstance3D", true, false)
	var mesh: ArrayMesh = (meshes[0] as MeshInstance3D).mesh as ArrayMesh if not meshes.is_empty() else null
	_expect(mesh != null and mesh.surface_get_array_index_len(0) == int(cooked.base) * 3,
		"the generated scene's mesh draws %d indices" % (int(cooked.base) * 3))
	if mesh != null:
		var server_levels := (RenderingServer.mesh_get_surface(mesh.get_rid(), 0).get("lods", []) as Array).size()
		_expect(server_levels == int(cooked.levels) and server_levels > 0,
			"the RenderingServer holds the %d levels below the capped base (%d)" % [int(cooked.levels), server_levels])
	scene.free()
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ProjectSettings.globalize_path(ROOT).path_join(Format.CATALOG_FILE)))
	var verified := Cook.verify_file(VOTARY_BAND, ProjectSettings.globalize_path(ROOT), catalog, true)
	_expect(str(verified.status) == "applied" and int(verified.get("scene_mismatches", -1)) == 0,
		"cook.gd verify applies it with 0 level mismatches (%s)" % str(verified))
	# The Human source itself is never given budget input by the driver; the
	# file without a catalogue entry stays as parsed.
	var human := _parse(HUMAN_BAND)
	var plain_human := (_arrays(human.state, 0, 0)[Mesh.ARRAY_INDEX] as PackedInt32Array).size()
	var skipped := ActorGeometry.apply(human.state, ProjectSettings.globalize_path(HUMAN_BAND))
	_expect(str(skipped.status) == "rejected" and str(skipped.reason) == "not_listed"
		and (_arrays(human.state, 0, 0)[Mesh.ARRAY_INDEX] as PackedInt32Array).size() == plain_human,
		"an unlisted Human source stays as parsed")


# --- helpers -----------------------------------------------------------------------

func _parse(path: String) -> Dictionary:
	return Cook.parse(ProjectSettings.globalize_path(path))


func _plan(parsed: Dictionary, path: String) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	return Cook.plan_state(parsed.state, path, FileAccess.get_sha256(absolute), _length(absolute), 1.0)


## cook.gd cook_file with the lining and budget stages (the HOOKs C4 and C11
## ask for): parse, plan, lining stage (no masks), budget stage, validate,
## write the blob. Returns {entry, levels, base} or {reason}.
func _cook(path: String, budget: Dictionary) -> Dictionary:
	var parsed := _parse(path)
	var plan := LiningPolicy.apply(parsed.state, _plan(parsed, path), {})
	plan = BudgetPolicy.apply(parsed.state, plan, budget)
	var problem := Format.validate_sidecar(plan.sidecar)
	if not problem.is_empty():
		return {"reason": problem}
	var bytes := Format.encode(plan.sidecar)
	var entry := Format.catalog_entry(str(plan.sidecar.source.sha256), int(plan.sidecar.source.bytes), bytes)
	if not Cook.write_blob(ProjectSettings.globalize_path(ROOT), entry, bytes):
		return {"reason": "write"}
	return {"entry": entry, "levels": int(plan.levels),
		"base": int(plan.meshes[0].surfaces[0].get("base_triangles", plan.meshes[0].surfaces[0].triangles))}


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


func _input(reference_triangles: int, reference := HUMAN_BAND) -> Dictionary:
	return {"schema": BudgetPolicy.INPUT_SCHEMA, "reference": reference,
		"reference_sha256": FileAccess.get_sha256(ProjectSettings.globalize_path(reference)),
		"reference_triangles": reference_triangles}


func _with(value: Dictionary, key: String, replacement: Variant) -> Dictionary:
	var out := value.duplicate(true)
	out[key] = replacement
	return out


func _fake_raw(spec: Array) -> Array:
	var raw: Array = []
	for item: Array in spec:
		var indices := PackedInt32Array()
		indices.resize(int(item[0]) * 3)
		for at: int in indices.size():
			indices[at] = at % 7
		raw.append([indices, float(item[1])])
	return raw


## A wavy n x n grid (1 cm cells) as a triangle soup, one vertex per corner.
## With `every` > 0 every `every`-th triangle samples its own atlas tile (its
## corners disagree on UV with the neighbours at the same positions); the
## other triangles take one continuous UV.
func _soup(n: int, every: int) -> Array:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var triangle := 0
	for y: int in n:
		for x: int in n:
			var corners: Array[Vector2i] = [Vector2i(x, y), Vector2i(x + 1, y), Vector2i(x + 1, y + 1), Vector2i(x, y + 1)]
			for corner_set: Array in [[0, 2, 1], [0, 3, 2]]:
				var tile := every > 0 and triangle % every == 0
				for corner: int in corner_set:
					var cell := corners[corner]
					indices.append(vertices.size())
					vertices.append(Vector3(cell.x, 0.3 * sin(cell.x * 0.6) * cos(cell.y * 0.4), cell.y) * 0.01)
					normals.append(Vector3.UP)
					if tile:
						uvs.append(Vector2(float(triangle % 40) / 40.0, float(triangle / 40) / 40.0)
							+ Vector2(corner % 2, corner / 2) / 80.0)
					else:
						uvs.append(Vector2(cell) / float(n))
				triangle += 1
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	return arrays


## A GLTFState with one mesh of these surfaces: [[primitive, arrays, flags?], ...].
func _state_with(surfaces: Array) -> GLTFState:
	var mesh := ImporterMesh.new()
	mesh.set_name("Probe")
	for surface: Array in surfaces:
		mesh.add_surface(int(surface[0]), surface[1], [], {}, null, "", int(surface[2]) if surface.size() > 2 else 0)
	var gltf_mesh := GLTFMesh.new()
	gltf_mesh.mesh = mesh
	var state := GLTFState.new()
	state.set_meshes([gltf_mesh])
	return state


func _mesh(state: GLTFState, mesh_index: int) -> ImporterMesh:
	return (state.get_meshes()[mesh_index] as GLTFMesh).mesh


func _arrays(state: GLTFState, mesh_index: int, surface: int) -> Array:
	return _mesh(state, mesh_index).get_surface_arrays(surface)


func _flags(state: GLTFState, mesh_index: int, surface: int) -> int:
	return _mesh(state, mesh_index).get_surface_format(surface)


func _triangles(parsed: Dictionary) -> int:
	var total := 0
	for gltf_mesh: GLTFMesh in (parsed.state as GLTFState).get_meshes():
		for surface: int in gltf_mesh.mesh.get_surface_count():
			total += (gltf_mesh.mesh.get_surface_arrays(surface)[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
	return total


## Triangles Godot draws at this depth (lod_bias 1, reference camera, scale 1)
## for a surface of `base` triangles with these [triangles, edge, ...] levels.
func _drawn(levels: Array, base: int, depth: float) -> int:
	var drawn := base
	for level: Array in levels:
		if LodPolicy.switch_depth(float(level[1])) > depth:
			break
		drawn = int(level[0])
	return drawn


func _length(path: String) -> int:
	var file := FileAccess.open(path, FileAccess.READ)
	return file.get_length() if file != null else -1


func _remove_tree(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for file: String in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	for folder: String in DirAccess.get_directories_at(path):
		_remove_tree(path.path_join(folder))
	DirAccess.remove_absolute(path)


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		return
	_failures += 1
	push_error("FAIL: " + message)
	print("FAIL: " + message)
