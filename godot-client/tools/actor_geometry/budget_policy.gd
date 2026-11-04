extends RefCounted
## Actor geometry budget stage (actor LODs C11): caps a race refit of a rigid
## socket mesh (the helmets equipment.json carries per race) at MAX_RATIO times
## the triangles of its Human source, at every distance, by giving its
## surfaces a simplified base index buffer. Docs:
## godot-client/docs/actor-geometry-lods.md ("Budget stage").
##
## The cook (tools/actor_geometry/cook.gd, cook_file) runs it on each file's
## plan after LOD policy v1 and the lining stage:
##   plan = BudgetPolicy.apply(parsed.state, plan, item.get("budget", {}))
## Without budget input the plan comes back unchanged, so every file that is
## not a race refit cooks byte for byte as before, and so does a refit within
## its budget.
##
## Input: one job file's `budget`, written by tools/actor_geometry_cache.py from
## data/actors/equipment.json (a socket model's `canonical_<race>_<sex>`
## variant; its Human source is the model's `canonical_human_<sex>` variant):
##   {schema: 1, reference: "res://...", reference_sha256, reference_triangles}
## `reference_triangles` counts the Human source's glTF triangles (the runtime
## parse keeps every one).
##
## When the file draws more than floor(MAX_RATIO * reference_triangles)
## triangles, every rigid triangle surface gets a share of that limit in
## proportion to its triangles, and its base becomes a level of
## ImporterMesh.generate_lods on the exact parsed surface (LOD policy v1's
## simplifier and arguments; vertex buffers untouched):
## - capped: the largest level within the surface's share whose error meets
##   LOD policy v1's MAX_ERROR_PX clamp from GUARD_METRES on (lod_bias 1, the
##   reference camera): the capped base draws even in close-ups, so it may be
##   no coarser than policy v1 lets a level draw at its first band.
## - partial: no level within the share meets that clamp; the base becomes the
##   smallest level that does (still well above the share), when it removes at
##   least MIN_REMOVED_SHARE of the surface.
## - kept (reason: guard, no_level, skinned, masked, small, not_triangles,
##   per_face_tiles): the surface keeps LOD policy v1's plan. A triangle soup
##   whose corners disagree on UV (per-face atlas tiles) is never simplified,
##   as in LOD policy v1: its levels would smear the tiles.
## The capped base keeps a chain of its own: LOD policy v1's level selection
## and edges on the simplifier's levels below it (targets 50 / 25 / 12 / 5 % of
## the capped base, bands 8 / 18 / 36 / 70 m, the MAX_ERROR_PX clamp on each
## level's error against the source).
## Surfaces with skin weights (not a rigid socket mesh) and surfaces the lining
## stage already gave a base keep their plan. Every surface row of the file
## reports `budget` ({status, ...}); a capped or partial row also carries
## `base_triangles` (what the driver's census prediction draws).

const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const Format := preload("res://src/actors/actor_geometry_format.gd")

const VERSION := 1
const INPUT_SCHEMA := 1
## A race refit draws at most this many times its Human source's triangles
## (owner decision 5 of the actor-LOD plan as proposed: 2x at every distance).
const MAX_RATIO := 2.0
## Depth (metres, lod_bias 1, reference camera and width) from which a capped
## base's error must meet LodPolicy.MAX_ERROR_PX: LOD policy v1's first band,
## where its first simplified level may start to draw at High.
const GUARD_METRES := 8.0
## A partial cap (no level within the share meets the clamp) must remove at
## least this share of the surface's triangles, or the surface keeps its plan.
const MIN_REMOVED_SHARE := 0.25
const INPUT_KEYS: Array[String] = ["schema", "reference", "reference_sha256", "reference_triangles"]
## Report statuses of a surface row's `budget`.
const STATUSES: Array[String] = ["within", "capped", "partial", "kept", "rejected"]


## The stage's parameters, for the cook report and tests.
static func settings() -> Dictionary:
	return {"version": VERSION, "input_schema": INPUT_SCHEMA, "max_ratio": MAX_RATIO,
		"guard_metres": GUARD_METRES, "min_removed_share": MIN_REMOVED_SHARE,
		"guard_error_at_scale_1": guard_error(1.0)}


## The largest error (mesh units) a capped base may carry on a model drawn at
## `model_scale`: LodPolicy.MAX_ERROR_PX pixels at GUARD_METRES, i.e. the error
## term of LodPolicy.edge_for switching no later than GUARD_METRES.
static func guard_error(model_scale := 1.0) -> float:
	var scale := clampf(model_scale, LodPolicy.MIN_MODEL_SCALE, LodPolicy.MAX_MODEL_SCALE)
	return GUARD_METRES * LodPolicy.lod_multiplier() * LodPolicy.MAX_ERROR_PX \
		/ (LodPolicy.REFERENCE_WIDTH_PX * scale)


## The triangle limit for a Human source of `reference_triangles`.
static func limit_for(reference_triangles: int) -> int:
	return floori(MAX_RATIO * float(reference_triangles))


## Applies the budget input to `plan` (cook.gd plan_state's result for the same
## `state`, after the lining stage): replaces the sidecar records and report
## rows of the capped surfaces and recounts `changed` and `levels`. Returns
## `plan` (changed in place).
static func apply(state: GLTFState, plan: Dictionary, budget: Variant) -> Dictionary:
	if budget == null or (budget is Dictionary and (budget as Dictionary).is_empty()):
		return plan
	var began := Time.get_ticks_usec()
	var input := read_input(budget)
	var meshes: Array = state.get_meshes()
	var records: Array = (plan.sidecar as Dictionary).meshes
	var rows: Array = plan.meshes
	if input.has("error"):
		_note_all(rows, {"status": "rejected", "reason": "input: " + str(input.error)})
		return plan
	var limit := limit_for(int(input.reference_triangles))
	var surfaces := _surfaces(meshes, records)
	var total := 0
	for surface: Dictionary in surfaces:
		total += int(surface.triangles)
	var common := {"reference": str(input.reference), "reference_triangles": int(input.reference_triangles),
		"limit": limit, "file_triangles": total}
	if total <= limit:
		_note_all(rows, dict_with(common, {"status": "within"}))
		plan["budget_usec"] = Time.get_ticks_usec() - began
		return plan
	for surface: Dictionary in surfaces:
		var mesh_index := int(surface.mesh)
		var surface_index := int(surface.surface)
		var row: Dictionary = rows[mesh_index].surfaces[surface_index]
		var share := floori(float(limit) * float(surface.triangles) / float(total))
		var summary := dict_with(common, {"triangles": int(surface.triangles), "share": share})
		if not str(surface.reason).is_empty():
			row["budget"] = dict_with(summary, {"status": "kept", "reason": str(surface.reason)})
			continue
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		var scale := float(rows[mesh_index].get("model_scale", 1.0))
		var capped := plan_surface(mesh.get_surface_arrays(surface_index), mesh.get_surface_format(surface_index),
			share, scale)
		if str(capped.status) == "kept":
			row["budget"] = dict_with(summary, {"status": "kept", "reason": str(capped.reason)})
			continue
		var record: Dictionary = records[mesh_index].surfaces[surface_index]
		record["base"] = capped.base
		record["lods"] = capped.lods
		var v1_levels := (row.get("levels", []) as Array).size()
		row["method"] = "chain"
		row.erase("reason")
		row.erase("generated")
		row["levels"] = capped.levels
		row["base_triangles"] = int(capped.base_triangles)
		row["budget"] = dict_with(summary, {"status": str(capped.status), "base_triangles": int(capped.base_triangles),
			"error": float(capped.error), "guard_error": float(capped.guard_error), "v1_levels": v1_levels})
	var changed := 0
	var levels := 0
	for mesh_record: Dictionary in records:
		for record: Dictionary in mesh_record.surfaces:
			if Format.changes_surface(record):
				changed += 1
				levels += (record.lods as Array).size()
	plan["changed"] = changed
	plan["levels"] = levels
	plan["budget_usec"] = Time.get_ticks_usec() - began
	return plan


## Every surface of the parse with its drawn triangles and, when the stage may
## not touch it, why: [{mesh, surface, triangles, reason}] in plan order. A
## surface that is not a triangle list draws no triangles (the Human source's
## count, from the glTF JSON, holds triangle-list primitives only).
static func _surfaces(meshes: Array, records: Array) -> Array:
	var out: Array = []
	for mesh_index: int in mini(meshes.size(), records.size()):
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		if mesh == null:
			continue
		var mesh_records: Array = records[mesh_index].surfaces
		for surface: int in mini(mesh.get_surface_count(), mesh_records.size()):
			var record: Dictionary = mesh_records[surface]
			var triangles := int(record.index_count) / 3
			var reason := ""
			if record.has("base"):
				# Another stage (the lining masks) already chose this base.
				triangles = (record.base as PackedInt32Array).size() / 3
				reason = "masked"
			elif mesh.get_surface_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
				triangles = 0
				reason = "not_triangles"
			elif mesh.get_surface_arrays(surface)[Mesh.ARRAY_BONES] != null:
				reason = "skinned"
			elif triangles < LodPolicy.MIN_SURFACE_TRIANGLES:
				reason = "small"
			out.append({"mesh": mesh_index, "surface": surface, "triangles": triangles, "reason": reason})
	return out


## The capped plan for one rigid surface with `share` triangles of the file's
## limit. Returns {status (capped, partial or kept), reason, base,
## base_triangles, error, guard_error, lods, levels}; `lods`/`levels` as
## LodPolicy.plan_surface, below the capped base.
static func plan_surface(arrays: Array, flags: int, share: int, model_scale := 1.0) -> Dictionary:
	var result := {"status": "kept", "reason": "", "base": PackedInt32Array(), "base_triangles": 0,
		"error": 0.0, "guard_error": guard_error(model_scale), "lods": [], "levels": []}
	var indices: Variant = arrays[Mesh.ARRAY_INDEX] if arrays.size() == Mesh.ARRAY_MAX else null
	if not indices is PackedInt32Array or (indices as PackedInt32Array).is_empty():
		result.reason = "no_indices"
		return result
	var triangles := (indices as PackedInt32Array).size() / 3
	if triangles <= share:
		result.reason = "within"
		return result
	# LOD policy v1 gives a soup with per-face UV tiles no chain (simplifying
	# it smears the tiles); its simplifier levels are no base either.
	var vertices: Variant = arrays[Mesh.ARRAY_VERTEX]
	if vertices is PackedVector3Array and LodPolicy.is_soup(indices, (vertices as PackedVector3Array).size()) \
			and float(LodPolicy.weld(arrays).coherence) < LodPolicy.COHERENCE:
		result.reason = "per_face_tiles"
		return result
	var raw := LodPolicy.exact_chain(arrays, flags)
	var chosen := choose_level(raw, triangles, share, float(result.guard_error))
	if chosen.index < 0:
		result.reason = str(chosen.reason)
		return result
	var base: PackedInt32Array = raw[int(chosen.index)][0]
	result.status = str(chosen.status)
	result.base = base
	result.base_triangles = base.size() / 3
	result.error = float(raw[int(chosen.index)][1])
	var chain := chain_below(raw, int(chosen.index), model_scale)
	result.lods = chain.lods
	result.levels = chain.levels
	return result


## Which simplifier level (`raw`: [[indices, error], ...], LodPolicy.exact_chain)
## becomes the base of a surface of `triangles` with `share` allowed: {index,
## status: capped | partial, reason} (index -1 with reason no_level / guard
## when none may).
static func choose_level(raw: Array, triangles: int, share: int, max_error: float) -> Dictionary:
	var ceiling := floori((1.0 - MIN_REMOVED_SHARE) * float(triangles))
	var within := -1
	var within_size := -1
	var fallback := -1
	var fallback_size := triangles
	var candidates := 0
	for index: int in raw.size():
		var size: int = (raw[index][0] as PackedInt32Array).size() / 3
		if size < LodPolicy.MIN_LEVEL_TRIANGLES or size >= triangles:
			continue
		candidates += 1
		if float(raw[index][1]) > max_error:
			continue
		if size <= share:
			if size > within_size:
				within = index
				within_size = size
		elif size <= ceiling and size < fallback_size:
			fallback = index
			fallback_size = size
	if within >= 0:
		return {"index": within, "status": "capped", "reason": ""}
	if fallback >= 0:
		return {"index": fallback, "status": "partial", "reason": ""}
	return {"index": -1, "status": "kept", "reason": "no_level" if candidates == 0 else "guard"}


## LOD policy v1's chain below the capped base raw[base_index]: the
## simplifier's smaller levels, selected against the capped base's triangle
## count (targets 50 / 25 / 12 / 5 %) with LodPolicy.edge_for edges, strictly
## later and smaller. Returns {lods, levels}.
static func chain_below(raw: Array, base_index: int, model_scale := 1.0) -> Dictionary:
	var base: PackedInt32Array = raw[base_index][0]
	var rest: Array = []
	for index: int in raw.size():
		if index != base_index and (raw[index][0] as PackedInt32Array).size() < base.size():
			rest.append(raw[index])
	var lods: Array = []
	var levels: Array = []
	var previous_edge := 0.0
	var previous_size := base.size()
	for chosen: Dictionary in LodPolicy.select_levels(rest, base.size() / 3):
		var level_indices: PackedInt32Array = rest[int(chosen.level)][0]
		var error := float(rest[int(chosen.level)][1])
		var edge := LodPolicy.edge_for(int(chosen.target), error, model_scale)
		if not is_finite(edge) or edge <= previous_edge or level_indices.size() >= previous_size:
			continue
		lods.append([edge, level_indices])
		levels.append([level_indices.size() / 3, edge, error, int(chosen.target)])
		previous_edge = edge
		previous_size = level_indices.size()
	return {"lods": lods, "levels": levels}


## The budget input normalised ({reference, reference_sha256,
## reference_triangles}) or {error}.
static func read_input(value: Variant) -> Dictionary:
	if not value is Dictionary:
		return {"error": "not a dictionary"}
	var input: Dictionary = value
	for key: Variant in input.keys():
		if not str(key) in INPUT_KEYS:
			return {"error": "key %s" % str(key)}
	if not _whole(input.get("schema")) or int(input.schema) != INPUT_SCHEMA:
		return {"error": "schema"}
	if not input.get("reference") is String or not Format.in_scope(str(input.reference)):
		return {"error": "reference"}
	if not Format.is_digest(input.get("reference_sha256")):
		return {"error": "reference_sha256"}
	if not _whole(input.get("reference_triangles")) or int(input.reference_triangles) <= 0:
		return {"error": "reference_triangles"}
	return {"reference": str(input.reference), "reference_sha256": str(input.reference_sha256),
		"reference_triangles": int(input.reference_triangles)}


static func _note_all(rows: Array, note: Dictionary) -> void:
	for mesh_row: Dictionary in rows:
		for row: Dictionary in mesh_row.surfaces:
			row["budget"] = note.duplicate()


static func dict_with(base: Dictionary, extra: Dictionary) -> Dictionary:
	var out := base.duplicate()
	out.merge(extra, true)
	return out


## JSON numbers arrive as floats.
static func _whole(value: Variant) -> bool:
	return value is int or (value is float and is_finite(value) and float(value) == floorf(value))
