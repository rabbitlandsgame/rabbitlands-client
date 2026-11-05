extends RefCounted
## Actor geometry lining stage (actor LODs C4, level L1): turns the offline
## lining visibility masks (eloria-assets/tools/lining_visibility.py) into
## masked base index buffers for the `Generated*` lining surfaces of one cooked
## actor glTF, plans LOD chains on the masked base and, where it pays and is
## provably invisible, compacts the masked surface's vertices by kept runs.
## Docs: godot-client/docs/actor-geometry-lods.md ("Lining stage").
##
## The cook (tools/actor_geometry/cook.gd, cook_file) runs it on each file's
## plan right after LOD policy v1 planned every surface:
##   plan = LiningPolicy.apply(parsed.state, plan, item.get("lining", {}))
## Without lining input the plan comes back unchanged, so every file without a
## mask cooks byte for byte as before.
##
## Input: one job file's `lining`, written by tools/actor_geometry_cache.py from
## a mask file it validated against the garment's bytes (schema, source
## SHA-256, margin, pose and direction counts, visible inside keep):
##   {schema: 1, mask_sha256, linings: [{mesh, primitive, triangles, keep,
##     check: [[triangle, x, y, z], ...]}]}
## `keep` is the mask's base64 little-endian bitset (bit i = glTF triangle i of
## that primitive); `check` holds the mask's check centroids in glTF mesh space.
##
## A lining is masked only when this parse binds to its mask: the mesh (by its
## unique name) and the surface (the glTF primitive) exist, the surface is a
## triangle list with the mask's triangle count, and every check centroid lies
## within CENTROID_TOLERANCE of the parsed triangle's centroid (the raw parse
## keeps glTF triangle order and only swaps the winding inside a triangle,
## which leaves the centroid). Anything else leaves that surface as LOD policy
## v1 planned it and is reported on its row (`lining.status` rejected).
##
## Per bound lining:
## - base: the kept triangles in parse order. Lossless: a mask keeps every
##   triangle a sampled pose and view can see, grown by a 2 cm surface margin.
## - LOD chains: LOD policy v1 on the masked base, merged with v1's chain of
##   the unmasked surface so that no depth draws more than either would
##   (merge_chains: the masked base's hole boundaries hold its own coarse
##   levels back); per-face-tile soups (the torso linings) get none, exactly
##   as unmasked.
## - Compaction (`compact_runs`): only when the kept triangles leave at least
##   COMPACT_MIN_SHARE and COMPACT_MIN_VERTICES of the surface's vertices
##   unused, the runs of used vertices (gaps of up to a few unused vertices
##   merged until at most COMPACT_MAX_RUNS runs remain; the runtime copies one
##   slice per run) still free that much, and every dropped vertex's position
##   is still present in the file's remaining vertex arrays (positions_kept).
##   The game reads raw lining vertex positions without the index buffer: the
##   cape's torso envelope and reaches (CapeDrape envelope, axis_reach over the
##   torso, shin_reach over body + torso + legs + boots, measured against the
##   wearer's bones), and mesh AABBs; all depend only on the set of positions,
##   so they stay exactly as they are. Base and levels then index the
##   compacted order. Without compaction the vertex buffers stay exactly as
##   parsed, so every reader of vertex positions reads what it reads today;
##   only hidden faces go (readers of the index buffer - the RL headwear
##   envelope, the mounted cape's body surface, the quiver strap fit - see the
##   kept faces only).
## A lining whose mask keeps every triangle keeps its v1 plan (`all_kept`), and
## so does one whose mask removes fewer than MASK_MIN_REMOVED_SHARE /
## MASK_MIN_REMOVED_TRIANGLES of its triangles (`below_gain`: a replacement base
## costs ~7 sidecar bytes per kept triangle and an index digest at first parse,
## and most torso masks remove 0-2 %). One whose mask keeps none stays unmasked
## (`all_hidden`: a sidecar cannot drop a surface; the authoring tools should
## drop such a lining instead).

const LodPolicy := preload("res://tools/actor_geometry/lod_policy.gd")
const Format := preload("res://src/actors/actor_geometry_format.gd")

const VERSION := 1
const INPUT_SCHEMA := 1
## Lining surfaces are the meshes the equipment generator names Generated*.
const LINING_PREFIX := "Generated"
## Check centroids must match the parse within this (metres, any axis).
const CENTROID_TOLERANCE := 1.0e-4
## A mask is applied only when it removes at least this share and this many
## of the lining's triangles (below it the surface keeps its v1 plan).
const MASK_MIN_REMOVED_SHARE := 0.05
const MASK_MIN_REMOVED_TRIANGLES := 64
## Compaction pays only when it frees this share and this many vertices.
const COMPACT_MIN_SHARE := 0.25
const COMPACT_MIN_VERTICES := 1024
## The runtime copies one slice per run per vertex array (ActorGeometry
## _gather): about 2.5 ms per 45k-vertex torso at ~400 runs on the dev laptop.
const COMPACT_MAX_RUNS := 400
## Gaps of unused vertices (counted in vertices) merged into a run, tried in
## order until the runs fit COMPACT_MAX_RUNS.
const COMPACT_GAPS: Array[int] = [0, 3, 6, 12, 24, 48, 96]
const LINING_KEYS: Array[String] = ["mesh", "primitive", "triangles", "keep", "check"]

static var _BASE64 := RegEx.create_from_string("^[A-Za-z0-9+/]*={0,2}$")


## The stage's parameters, for the cook report.
static func settings() -> Dictionary:
	return {"version": VERSION, "input_schema": INPUT_SCHEMA, "centroid_tolerance": CENTROID_TOLERANCE,
		"mask_min_removed_share": MASK_MIN_REMOVED_SHARE, "mask_min_removed_triangles": MASK_MIN_REMOVED_TRIANGLES,
		"compact_min_share": COMPACT_MIN_SHARE, "compact_min_vertices": COMPACT_MIN_VERTICES,
		"compact_max_runs": COMPACT_MAX_RUNS, "compact_gaps": COMPACT_GAPS.duplicate()}


## True for a mesh the lining stage may mask.
static func is_lining(mesh_name: String) -> bool:
	return mesh_name.begins_with(LINING_PREFIX)


## Applies the lining input to `plan` (cook.gd plan_state's result for the same
## `state`): changes the sidecar records and report rows of the bound linings
## and recounts `changed` and `levels`. Returns `plan` (changed in place).
static func apply(state: GLTFState, plan: Dictionary, lining: Variant) -> Dictionary:
	if lining == null or (lining is Dictionary and (lining as Dictionary).is_empty()):
		return plan
	var began := Time.get_ticks_usec()
	var input := read_input(lining)
	var meshes: Array = state.get_meshes()
	var records: Array = (plan.sidecar as Dictionary).meshes
	var rows: Array = plan.meshes
	var names := {}
	var glb_names: Array[String] = []
	for mesh_index: int in meshes.size():
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		var mesh_name := gltf_mesh_name(str(mesh.resource_name) if mesh != null else "", state.get_scene_name())
		glb_names.append(mesh_name)
		names[mesh_name] = -2 if names.has(mesh_name) else mesh_index
	if input.has("error"):
		for mesh_index: int in mini(rows.size(), glb_names.size()):
			if is_lining(glb_names[mesh_index]):
				for row: Dictionary in rows[mesh_index].surfaces:
					row["lining"] = {"status": "rejected", "reason": "input: " + str(input.error)}
		return plan
	var compaction_guard := {}
	for entry: Dictionary in input.linings:
		var mesh_index: int = names.get(str(entry.mesh), -1)
		if mesh_index < 0:
			# No such mesh, or two meshes share the name: nothing to bind.
			_note_unbound(rows, glb_names, str(entry.mesh), "mesh" if mesh_index == -1 else "mesh_ambiguous")
			continue
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		var surface := int(entry.primitive)
		if surface < 0 or surface >= mesh.get_surface_count() or surface >= (records[mesh_index].surfaces as Array).size():
			_note_unbound(rows, glb_names, str(entry.mesh), "surface")
			continue
		var row: Dictionary = rows[mesh_index].surfaces[surface]
		var arrays := mesh.get_surface_arrays(surface)
		var problem := binding_problem(arrays, mesh.get_surface_primitive_type(surface), entry)
		if not problem.is_empty():
			row["lining"] = {"status": "rejected", "reason": problem}
			continue
		var keep: PackedByteArray = entry.keep_flags
		var kept := count_kept(keep)
		var triangles := int(entry.triangles)
		if kept == triangles:
			row["lining"] = {"status": "all_kept", "triangles": triangles}
			continue
		if kept == 0:
			row["lining"] = {"status": "all_hidden", "triangles": triangles}
			continue
		if triangles - kept < maxi(MASK_MIN_REMOVED_TRIANGLES, ceili(MASK_MIN_REMOVED_SHARE * triangles)):
			# A replacement base costs ~7 sidecar bytes per kept triangle and
			# an index digest at first parse; a few removed faces do not pay.
			row["lining"] = {"status": "below_gain", "triangles": triangles, "removable_triangles": triangles - kept}
			continue
		if compaction_guard.is_empty():
			compaction_guard = {"meshes": meshes, "accepted": {}}
		var scale := float(rows[mesh_index].get("model_scale", 1.0))
		var record: Dictionary = records[mesh_index].surfaces[surface]
		var lined := plan_surface(arrays, mesh.get_surface_format(surface), mesh.get_surface_primitive_type(surface),
			scale, keep, compaction_guard, "%d|%d" % [mesh_index, surface], record.get("lods", []), row.get("levels", []))
		record["base"] = lined.base
		if lined.has("compact_runs"):
			record["compact_runs"] = lined.compact_runs
		else:
			record.erase("compact_runs")
		record["lods"] = lined.lods
		row["method"] = str(lined.method)
		row["levels"] = lined.levels
		row["base_triangles"] = kept
		if str(lined.reason).is_empty():
			row.erase("reason")
		else:
			row["reason"] = str(lined.reason)
		if float(lined.coherence) >= 0.0:
			row["coherence"] = snappedf(float(lined.coherence), 0.0001)
		row.erase("raw")
		row.erase("generated")
		if not (lined.raw as Array).is_empty() and str(lined.method) != "chain":
			row["generated"] = lined.raw
		row["lining"] = lined.summary
	var changed := 0
	var levels := 0
	for mesh_record: Dictionary in records:
		for record: Dictionary in mesh_record.surfaces:
			if Format.changes_surface(record):
				changed += 1
				levels += (record.lods as Array).size()
	plan["changed"] = changed
	plan["levels"] = levels
	plan["lining_usec"] = Time.get_ticks_usec() - began
	return plan


static func _note_unbound(rows: Array, glb_names: Array[String], mesh_name: String, reason: String) -> void:
	for mesh_index: int in mini(rows.size(), glb_names.size()):
		if glb_names[mesh_index] == mesh_name:
			for row: Dictionary in rows[mesh_index].surfaces:
				row["lining"] = {"status": "rejected", "reason": reason}


## The glTF mesh name behind a parsed ImporterMesh: GLTFDocument names it
## "<scene name>_<glTF mesh name>" (the scene name is the file's stem).
static func gltf_mesh_name(parsed_name: String, scene_name: String) -> String:
	if not scene_name.is_empty() and parsed_name.begins_with(scene_name + "_"):
		return parsed_name.substr(scene_name.length() + 1)
	return parsed_name


## The lining input normalised ({mask_sha256, linings: [{mesh, primitive,
## triangles, keep_flags (one byte per triangle), check}]}, linings sorted by
## mesh and primitive) or {error}.
static func read_input(value: Variant) -> Dictionary:
	if not value is Dictionary:
		return {"error": "not a dictionary"}
	var input: Dictionary = value
	if not _whole(input.get("schema")) or int(input.schema) != INPUT_SCHEMA:
		return {"error": "schema"}
	if not Format.is_digest(input.get("mask_sha256")):
		return {"error": "mask_sha256"}
	if not input.get("linings") is Array or (input.linings as Array).is_empty():
		return {"error": "linings"}
	var linings: Array = []
	var seen := {}
	for item: Variant in input.linings:
		if not item is Dictionary:
			return {"error": "lining entry"}
		var entry: Dictionary = item
		for key: String in LINING_KEYS:
			if not entry.has(key):
				return {"error": "lining %s" % key}
		if not entry.mesh is String or not is_lining(str(entry.mesh)):
			return {"error": "lining mesh %s" % str(entry.mesh)}
		if not _whole(entry.primitive) or int(entry.primitive) < 0 \
				or not _whole(entry.triangles) or int(entry.triangles) <= 0:
			return {"error": "lining counts %s" % str(entry.mesh)}
		var key := "%s|%d" % [str(entry.mesh), int(entry.primitive)]
		if seen.has(key):
			return {"error": "duplicate lining %s" % key}
		seen[key] = true
		var flags := decode_bits(entry.keep, int(entry.triangles))
		if flags.is_empty():
			return {"error": "lining keep %s" % str(entry.mesh)}
		var check := _read_check(entry.check, int(entry.triangles))
		if check.is_empty():
			return {"error": "lining check %s" % str(entry.mesh)}
		linings.append({"mesh": str(entry.mesh), "primitive": int(entry.primitive),
			"triangles": int(entry.triangles), "keep_flags": flags, "check": check})
	linings.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return str(a.mesh) < str(b.mesh) or (str(a.mesh) == str(b.mesh) and int(a.primitive) < int(b.primitive)))
	return {"mask_sha256": str(input.mask_sha256), "linings": linings}


## One byte per triangle (1 = kept) from a base64 little-endian bitset, or an
## empty array when the text is not exactly `count` bits (no bit set past it).
static func decode_bits(value: Variant, count: int) -> PackedByteArray:
	if not value is String or count <= 0:
		return PackedByteArray()
	var text := str(value)
	# Checked first: Marshalls logs an engine error for malformed base64.
	if text.length() % 4 != 0 or text.length() != ((count + 7) / 8 + 2) / 3 * 4 \
			or not _BASE64.search(text) is RegExMatch:
		return PackedByteArray()
	var raw := Marshalls.base64_to_raw(text)
	if raw.size() != (count + 7) / 8:
		return PackedByteArray()
	var flags := PackedByteArray()
	flags.resize(count)
	for index: int in count:
		flags[index] = (raw[index >> 3] >> (index & 7)) & 1
	var tail := count & 7
	if tail != 0 and (raw[raw.size() - 1] >> tail) != 0:
		return PackedByteArray()
	return flags


## The base64 little-endian bitset of one byte per triangle (the mask tool's
## pack_bits), for tests and tools.
static func encode_bits(flags: PackedByteArray) -> String:
	var raw := PackedByteArray()
	raw.resize((flags.size() + 7) / 8)
	raw.fill(0)
	for index: int in flags.size():
		if flags[index] != 0:
			raw[index >> 3] |= 1 << (index & 7)
	return Marshalls.raw_to_base64(raw)


static func count_kept(flags: PackedByteArray) -> int:
	return flags.count(1)


static func _read_check(value: Variant, triangles: int) -> Array:
	if not value is Array or (value as Array).is_empty():
		return []
	var out: Array = []
	for row: Variant in value:
		if not row is Array or (row as Array).size() != 4 or not _whole(row[0]) \
				or int(row[0]) < 0 or int(row[0]) >= triangles:
			return []
		for axis: int in range(1, 4):
			if not (row[axis] is float or row[axis] is int) or not is_finite(float(row[axis])):
				return []
		out.append([int(row[0]), Vector3(float(row[1]), float(row[2]), float(row[3]))])
	return out


## "" when the parsed surface binds to the mask entry, else why not.
static func binding_problem(arrays: Array, primitive: int, entry: Dictionary) -> String:
	if primitive != Mesh.PRIMITIVE_TRIANGLES or arrays.size() != Mesh.ARRAY_MAX:
		return "primitive"
	var vertices: Variant = arrays[Mesh.ARRAY_VERTEX]
	var indices: Variant = arrays[Mesh.ARRAY_INDEX]
	if not vertices is PackedVector3Array or not indices is PackedInt32Array:
		return "arrays"
	var positions: PackedVector3Array = vertices
	var index_buffer: PackedInt32Array = indices
	if index_buffer.size() != int(entry.triangles) * 3:
		return "triangles"
	for row: Array in entry.check:
		var corner := int(row[0]) * 3
		var centre := (positions[index_buffer[corner]] + positions[index_buffer[corner + 1]]
			+ positions[index_buffer[corner + 2]]) / 3.0
		var difference := (centre - (row[1] as Vector3)).abs()
		if maxf(difference.x, maxf(difference.y, difference.z)) > CENTROID_TOLERANCE:
			return "centroid"
	return ""


## The masked base of one bound surface: the kept triangles' indices in order.
static func masked_base(indices: PackedInt32Array, keep: PackedByteArray) -> PackedInt32Array:
	var base := PackedInt32Array()
	base.resize(count_kept(keep) * 3)
	var at := 0
	for triangle: int in keep.size():
		if keep[triangle] == 1:
			base[at] = indices[triangle * 3]
			base[at + 1] = indices[triangle * 3 + 1]
			base[at + 2] = indices[triangle * 3 + 2]
			at += 3
	return base


## The plan for one bound lining surface. Returns {base, compact_runs?, lods,
## levels, method, reason, coherence, raw, summary}; `lods`/`levels` as
## LodPolicy.plan_surface, on the masked base (and in compacted numbering when
## compact_runs is present). `guard` ({meshes: the file's parsed meshes,
## accepted: compactions kept so far by "mesh|surface"}) and `key` (this
## surface's "mesh|surface") feed the compaction guard (positions_kept); an
## empty guard skips it (tests). `v1_lods`/`v1_levels` are LOD policy v1's
## chain for the unmasked surface (merge_chains).
static func plan_surface(arrays: Array, flags: int, primitive: int, model_scale: float, keep: PackedByteArray,
		guard := {}, key := "", v1_lods: Array = [], v1_levels: Array = []) -> Dictionary:
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var vertex_count := (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	var base := masked_base(indices, keep)
	var kept := base.size() / 3
	var result := {"base": base, "lods": [], "levels": [], "method": "none", "reason": "", "coherence": -1.0,
		"raw": []}
	var tiles := false
	if LodPolicy.is_soup(indices, vertex_count):
		var welded := LodPolicy.weld(arrays)
		result.coherence = float(welded.coherence)
		tiles = float(welded.coherence) < LodPolicy.COHERENCE
	if tiles:
		result.reason = "per_face_tiles"
	else:
		var masked := arrays.duplicate()
		masked[Mesh.ARRAY_INDEX] = base
		var chain := LodPolicy.plan_surface(masked, flags, primitive, model_scale)
		result.lods = chain.lods
		result.levels = chain.levels
		result.method = chain.method
		result.reason = chain.reason
		result.raw = chain.raw
		if float(result.coherence) < 0.0 and float(chain.coherence) >= 0.0:
			result.coherence = float(chain.coherence)
	var summary := {"status": "masked", "triangles": indices.size() / 3, "kept_triangles": kept,
		"removed_triangles": indices.size() / 3 - kept, "vertices": vertex_count}
	if not v1_lods.is_empty():
		var merged := merge_chains(kept, result.lods, result.levels, v1_lods, v1_levels)
		result.lods = merged.lods
		result.levels = merged.levels
		summary["v1_levels_kept"] = int(merged.from_v1)
		if str(result.method) == "none" and not (result.lods as Array).is_empty():
			result.method = "chain"
			result.reason = ""
	var used := used_vertices(vertex_count, base, result.lods)
	var compaction := compaction_plan(used)
	summary["used_vertices"] = int(compaction.used)
	if compaction.has("runs") and not guard.is_empty():
		# Judged together with the compactions already kept in this file: two
		# surfaces that share a position may not both drop it.
		var together: Dictionary = (guard.accepted as Dictionary).duplicate()
		together[key] = compaction
		if positions_kept(guard.meshes, together):
			(guard.accepted as Dictionary)[key] = compaction
		else:
			compaction.erase("runs")
			compaction["reason"] = "positions"
	if compaction.has("runs"):
		var remap := compacted_remap(vertex_count, compaction.runs)
		result.base = remap_indices(base, remap)
		var lods: Array = []
		for level: Array in result.lods:
			lods.append([level[0], remap_indices(level[1], remap)])
		result.lods = lods
		result["compact_runs"] = compaction.runs
		summary["compacted"] = {"kept_vertices": int(compaction.kept), "runs": (compaction.runs as PackedInt32Array).size() / 2,
			"gap": int(compaction.gap)}
	elif compaction.has("reason"):
		summary["compaction"] = str(compaction.reason)
	result.summary = summary
	return result


## The chain a masked surface keeps: its own levels (on the masked base) and
## LOD policy v1's levels of the unmasked surface, by ascending edge, keeping a
## level only when it draws fewer triangles than every level (and the base)
## before it. A masked base is full of hole boundaries the simplifier must
## keep, so its own coarse levels carry larger errors and switch later than
## v1's (a masked leg lining's 12 % level from 48-120 m instead of 36 m);
## with both chains Godot never draws more at any depth than either would,
## and every level kept still meets its own band and pixel-error clamp. Both
## index the parsed vertex buffer. Returns {lods, levels, from_v1}.
static func merge_chains(base_triangles: int, lods: Array, levels: Array, v1_lods: Array, v1_levels: Array) -> Dictionary:
	var candidates: Array = []
	for index: int in lods.size():
		candidates.append({"edge": float(lods[index][0]), "lod": lods[index], "level": levels[index] if index < levels.size() else [],
			"triangles": (lods[index][1] as PackedInt32Array).size() / 3, "v1": false})
	for index: int in v1_lods.size():
		candidates.append({"edge": float(v1_lods[index][0]), "lod": v1_lods[index],
			"level": v1_levels[index] if index < v1_levels.size() else [],
			"triangles": (v1_lods[index][1] as PackedInt32Array).size() / 3, "v1": true})
	candidates.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return float(a.edge) < float(b.edge) or (float(a.edge) == float(b.edge) and int(a.triangles) < int(b.triangles)))
	var out_lods: Array = []
	var out_levels: Array = []
	var from_v1 := 0
	var previous_edge := 0.0
	var previous_size := base_triangles
	for candidate: Dictionary in candidates:
		if float(candidate.edge) <= previous_edge or int(candidate.triangles) >= previous_size:
			continue
		out_lods.append(candidate.lod)
		out_levels.append(candidate.level)
		from_v1 += int(bool(candidate.v1))
		previous_edge = float(candidate.edge)
		previous_size = int(candidate.triangles)
	return {"lods": out_lods, "levels": out_levels, "from_v1": from_v1}


## One byte per vertex: 1 when the base or a LOD level draws it.
static func used_vertices(vertex_count: int, base: PackedInt32Array, lods: Array) -> PackedByteArray:
	var used := PackedByteArray()
	used.resize(vertex_count)
	used.fill(0)
	for index: int in base:
		used[index] = 1
	for level: Array in lods:
		for index: int in (level[1] as PackedInt32Array):
			used[index] = 1
	return used


## Whether and how to compact a surface whose drawn vertices are `used`.
## Returns {used, runs?: PackedInt32Array ([start, length] pairs), kept, gap}
## or {used, reason} when compaction does not pay (share, runs).
static func compaction_plan(used: PackedByteArray) -> Dictionary:
	var vertex_count := used.size()
	var in_use := used.count(1)
	var floor_unused := maxi(COMPACT_MIN_VERTICES, ceili(COMPACT_MIN_SHARE * vertex_count))
	if vertex_count - in_use < floor_unused:
		return {"used": in_use, "reason": "share"}
	for gap: int in COMPACT_GAPS:
		var runs := kept_runs(used, gap)
		if runs.size() / 2 > COMPACT_MAX_RUNS:
			continue
		var kept := 0
		for index: int in range(1, runs.size(), 2):
			kept += runs[index]
		if vertex_count - kept < floor_unused:
			return {"used": in_use, "reason": "share"}
		return {"used": in_use, "runs": runs, "kept": kept, "gap": gap}
	return {"used": in_use, "reason": "runs"}


## [start, length] pairs covering every used vertex, merging runs separated by
## at most `gap` unused vertices.
static func kept_runs(used: PackedByteArray, gap: int) -> PackedInt32Array:
	var runs := PackedInt32Array()
	var start := -1
	var end := -1
	for vertex: int in used.size():
		if used[vertex] != 1:
			continue
		if start < 0:
			start = vertex
		elif vertex - end - 1 > gap:
			runs.append(start)
			runs.append(end - start + 1)
			start = vertex
		end = vertex
	if start >= 0:
		runs.append(start)
		runs.append(end - start + 1)
	return runs


## Old vertex -> compacted vertex (-1 when dropped).
static func compacted_remap(vertex_count: int, runs: PackedInt32Array) -> PackedInt32Array:
	var remap := PackedInt32Array()
	remap.resize(vertex_count)
	remap.fill(-1)
	var next := 0
	for index: int in range(0, runs.size(), 2):
		for vertex: int in range(runs[index], runs[index] + runs[index + 1]):
			remap[vertex] = next
			next += 1
	return remap


static func remap_indices(indices: PackedInt32Array, remap: PackedInt32Array) -> PackedInt32Array:
	var out := PackedInt32Array()
	out.resize(indices.size())
	for at: int in indices.size():
		out[at] = remap[indices[at]]
	return out


## True when every vertex the compactions in `compacted` ("mesh|surface" ->
## a compaction plan with `runs`) drop has its exact position still present in
## the parsed file's remaining vertex arrays (any mesh, any surface). Then
## every reader that measures the file by its vertex positions alone (the
## cape's CapeDrape.envelope / axis_reach / shin_reach, which take the
## outermost vertex per cell against the wearer's bones, and mesh AABBs) sees
## the same set of points. A position the comparison misses only refuses a
## compaction.
static func positions_kept(meshes: Array, compacted: Dictionary) -> bool:
	var remaining := {}
	var dropped: Array[PackedVector3Array] = []
	for mesh_index: int in meshes.size():
		var mesh: ImporterMesh = (meshes[mesh_index] as GLTFMesh).mesh
		if mesh == null:
			continue
		for surface: int in mesh.get_surface_count():
			var vertices: Variant = mesh.get_surface_arrays(surface)[Mesh.ARRAY_VERTEX]
			if not vertices is PackedVector3Array:
				continue
			var positions: PackedVector3Array = vertices
			var plan: Variant = compacted.get("%d|%d" % [mesh_index, surface])
			if not (plan is Dictionary and (plan as Dictionary).has("runs")):
				for point: Vector3 in positions:
					remaining[point] = true
				continue
			var runs: PackedInt32Array = plan.runs
			var at := 0
			for index: int in range(0, runs.size(), 2):
				if runs[index] > at:
					dropped.append(positions.slice(at, runs[index]))
				for point: Vector3 in positions.slice(runs[index], runs[index] + runs[index + 1]):
					remaining[point] = true
				at = runs[index] + runs[index + 1]
			if at < positions.size():
				dropped.append(positions.slice(at))
	for points: PackedVector3Array in dropped:
		for point: Vector3 in points:
			if not remaining.has(point):
				return false
	return true


## The lining input for one mask document (lining_visibility.py's
## <stem>.lining.json, parsed), for tools and tests that read masks directly.
## The cook driver builds the same input after validating the mask.
static func input_from_mask(mask: Dictionary, mask_sha256: String) -> Dictionary:
	var linings: Array = []
	for name: String in (mask.get("linings", {}) as Dictionary):
		var entry: Dictionary = mask.linings[name]
		linings.append({"mesh": str(entry.get("mesh", name)), "primitive": int(entry.get("primitive", 0)),
			"triangles": int(entry.get("triangles", 0)), "keep": str(entry.get("keep", "")),
			"check": entry.get("check", [])})
	return {"schema": INPUT_SCHEMA, "mask_sha256": mask_sha256, "linings": linings}


## JSON numbers arrive as floats.
static func _whole(value: Variant) -> bool:
	return value is int or (value is float and is_finite(value) and float(value) == floorf(value))
