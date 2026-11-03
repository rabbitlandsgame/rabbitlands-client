extends RefCounted
## Actor geometry LOD policy v1 (actor LODs C2): which LOD index chains the
## package-time cook (tools/actor_geometry/cook.gd) attaches to one parsed
## actor surface, and at which edge lengths they switch. Docs:
## godot-client/docs/actor-geometry-lods.md ("Cook").
##
## Godot picks LOD level i of a surface while
##   edge_i * model_scale * lod_bias / (depth * lod_multiplier) <= threshold / width
## (threshold 1 px, width = the 3D viewport's width, lod_multiplier =
## 2 tan(hfov / 2), 1.658 at a 50 degree vertical FOV and 16:9). So an edge
## length is a distance in disguise: with lod_bias 1 at 1920 px, level i
## starts at depth edge_i * 1920 / 1.658. The policy chooses each edge as
##   max(band * 1.658 / (1920 * model_scale), error / MAX_ERROR_PX)
## - the band keeps the level away until the camera is that far (8 / 18 / 36 /
## 70 m for the levels near 50 / 25 / 12 / 5 % of the triangles, at lod_bias 1,
## i.e. High; Medium 0.65 and Low 0.35 switch at 0.65x / 0.35x those depths),
## and the error term holds the switch back until the level's geometric error
## (ImporterMesh.generate_lods' own figure, in mesh units) covers at most
## MAX_ERROR_PX pixels at lod_bias 1 (error_px = MAX_ERROR_PX / lod_bias in
## general, independent of the model's scale).
##
## Chains come from ImporterMesh.generate_lods(60, 25, []) on the exact parsed
## surface (vertex buffers are never touched). A triangle soup (one vertex per
## corner) whose corners at one position disagree on UV (per-face atlas tiles,
## the torso linings) gets no chain: simplifying it would smear tiles. A
## surface that gets no chain is simplified as a position-welded proxy whose
## corners are mapped back to an original vertex at that position, preferring
## the original UV island the whole triangle shares; a proxy level is kept only
## when the surface's welded corners agree on UV and skin (>= 95 %) or >= 95 %
## of the level's triangles stay on one UV island (no seam crossed). Everything here is CPU only
## and deterministic for one engine build.

const VERSION := 1
## Surfaces below this many triangles keep their base only.
const MIN_SURFACE_TRIANGLES := 64
const MERGE_ANGLE := 60.0
const SPLIT_ANGLE := 25.0
## Kept levels aim at these fractions of the base triangles, in order. A
## generated level counts for a target when within TARGET_TOLERANCE of it.
const TARGET_FRACTIONS: Array[float] = [0.5, 0.25, 0.12, 0.05]
const TARGET_TOLERANCE := 1.5
const MIN_LEVEL_TRIANGLES := 32
## Camera depth (metres, lod_bias 1) before which each target's level never
## draws. The first band keeps close-ups (creation preview, zoomed camera) at
## the full mesh.
const BAND_METRES: Array[float] = [8.0, 18.0, 36.0, 70.0]
const REFERENCE_WIDTH_PX := 1920.0
const REFERENCE_VFOV_DEGREES := 50.0
const REFERENCE_ASPECT := 16.0 / 9.0
const MAX_ERROR_PX := 3.0
## Share of corners that must keep their UV and skin when welded by position
## before a soup may be simplified, or a chainless surface may use a proxy.
const COHERENCE := 0.95
## Position weld quantum (metres): 0.01 mm.
const WELD_QUANTUM := 1.0e-5
const UV_EPSILON_SQUARED := 1.0e-10
const WEIGHT_EPSILON := 1.0e-5
const MIN_MODEL_SCALE := 0.001
const MAX_MODEL_SCALE := 1000.0


## The policy's parameters, for the cook report and the cache digest.
static func settings() -> Dictionary:
	return {"version": VERSION, "min_surface_triangles": MIN_SURFACE_TRIANGLES,
		"merge_angle": MERGE_ANGLE, "split_angle": SPLIT_ANGLE,
		"target_fractions": TARGET_FRACTIONS.duplicate(), "target_tolerance": TARGET_TOLERANCE,
		"min_level_triangles": MIN_LEVEL_TRIANGLES, "band_metres": BAND_METRES.duplicate(),
		"reference_width_px": REFERENCE_WIDTH_PX, "reference_vfov_degrees": REFERENCE_VFOV_DEGREES,
		"reference_aspect": REFERENCE_ASPECT, "lod_multiplier": lod_multiplier(),
		"max_error_px": MAX_ERROR_PX, "coherence": COHERENCE, "weld_quantum": WELD_QUANTUM}


## 2 tan(hfov / 2) of the reference camera (Projection.get_lod_multiplier()).
static func lod_multiplier() -> float:
	return 2.0 * tan(deg_to_rad(REFERENCE_VFOV_DEGREES) * 0.5) * REFERENCE_ASPECT


## The camera depth (lod_bias 1, reference camera and width) at which a level
## of this edge length starts to draw on a model of this scale.
static func switch_depth(edge: float, model_scale := 1.0, lod_bias := 1.0) -> float:
	return edge * model_scale * lod_bias * REFERENCE_WIDTH_PX / lod_multiplier()


## The edge length for the level kept for TARGET_FRACTIONS[target] with this
## geometric error (mesh units), on a model drawn at `model_scale`.
static func edge_for(target: int, error: float, model_scale := 1.0) -> float:
	var scale := clampf(model_scale, MIN_MODEL_SCALE, MAX_MODEL_SCALE)
	var band := BAND_METRES[target] * lod_multiplier() / (REFERENCE_WIDTH_PX * scale)
	return maxf(band, maxf(error, 0.0) / MAX_ERROR_PX)


## The plan for one parsed surface. Returns {method, reason, triangles,
## coherence, lods: [[edge, PackedInt32Array]...], levels: [[triangles, edge,
## error, target]...], raw: [[triangles, error]...]}. `method` is chain
## (generate_lods on the surface), proxy (on its position-welded proxy) or
## none, with `reason`: not_triangles, no_indices, small, per_face_tiles (a
## soup with per-face UV tiles), seams (every proxy level crosses UV seams),
## no_levels or no_target (no level near a target fraction). `raw` lists
## what the simplifier produced ([triangles, error] or, for a proxy,
## [triangles, error, island share]).
static func plan_surface(arrays: Array, flags: int, primitive: int, model_scale := 1.0) -> Dictionary:
	var result := {"method": "none", "reason": "", "triangles": 0, "coherence": -1.0,
		"lods": [], "levels": [], "raw": []}
	if primitive != Mesh.PRIMITIVE_TRIANGLES:
		result.reason = "not_triangles"
		return result
	if arrays.size() != Mesh.ARRAY_MAX or not arrays[Mesh.ARRAY_VERTEX] is PackedVector3Array:
		result.reason = "no_indices"
		return result
	var indices: Variant = arrays[Mesh.ARRAY_INDEX]
	if not indices is PackedInt32Array or (indices as PackedInt32Array).is_empty():
		result.reason = "no_indices"
		return result
	var index_buffer: PackedInt32Array = indices
	var vertex_count := (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
	result.triangles = index_buffer.size() / 3
	if int(result.triangles) < MIN_SURFACE_TRIANGLES:
		result.reason = "small"
		return result
	var welded := {}
	if is_soup(index_buffer, vertex_count):
		welded = weld(arrays)
		result.coherence = welded.coherence
		if float(welded.coherence) < COHERENCE:
			result.reason = "per_face_tiles"
			return result
	var raw := exact_chain(arrays, flags)
	var method := "chain"
	if raw.is_empty():
		if welded.is_empty():
			welded = weld(arrays)
			result.coherence = welded.coherence
		method = "proxy"
		var safe: Array = []
		for level: Array in proxy_chain(arrays, welded):
			(result.raw as Array).append([(level[0] as PackedInt32Array).size() / 3, float(level[1]),
				snappedf(float(level[2]), 0.0001)])
			# A proxy level is kept when its corners keep their UVs: the
			# surface's welded corners agree, or the level's triangles stay on
			# one original UV island.
			if float(welded.coherence) >= COHERENCE or float(level[2]) >= COHERENCE:
				safe.append(level)
		if safe.is_empty():
			result.reason = "seams" if not (result.raw as Array).is_empty() else "no_levels"
			return result
		raw = safe
	else:
		for level: Array in raw:
			(result.raw as Array).append([(level[0] as PackedInt32Array).size() / 3, float(level[1])])
	var previous_edge := 0.0
	var previous_size := index_buffer.size()
	for chosen: Dictionary in select_levels(raw, int(result.triangles)):
		var level_indices: PackedInt32Array = raw[int(chosen.level)][0]
		var error := float(raw[int(chosen.level)][1])
		var edge := edge_for(int(chosen.target), error, model_scale)
		if not is_finite(edge) or edge <= previous_edge or level_indices.size() >= previous_size:
			continue
		(result.lods as Array).append([edge, level_indices])
		(result.levels as Array).append([level_indices.size() / 3, edge, error, int(chosen.target)])
		previous_edge = edge
		previous_size = level_indices.size()
	if (result.lods as Array).is_empty():
		result.reason = "no_target"
		return result
	result.method = method
	return result


## True when every vertex is one corner: as many vertices as indices (the
## parse drops unreferenced vertices, so each is referenced exactly once).
static func is_soup(indices: PackedInt32Array, vertex_count: int) -> bool:
	return vertex_count > 0 and indices.size() == vertex_count


## generate_lods on a one-surface copy of the parsed surface (no blend shapes:
## they do not take part). Returns [[PackedInt32Array, error], ...] by
## ascending error, as Godot orders them.
static func exact_chain(arrays: Array, flags: int) -> Array:
	var probe := ImporterMesh.new()
	probe.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays.duplicate(), [], {}, null, "", flags)
	probe.generate_lods(MERGE_ANGLE, SPLIT_ANGLE, [])
	return _levels_of(probe)


static func _levels_of(probe: ImporterMesh) -> Array:
	var levels: Array = []
	for level: int in probe.get_surface_lod_count(0):
		levels.append([probe.get_surface_lod_indices(0, level), probe.get_surface_lod_size(0, level)])
	return levels


## Picks, for each target fraction in order, the generated level nearest to
## it (by ratio, within TARGET_TOLERANCE), each later and smaller than the
## one before and at least MIN_LEVEL_TRIANGLES. `raw` is ordered by ascending
## error. Returns [{level, target, triangles}].
static func select_levels(raw: Array, base_triangles: int) -> Array:
	var chosen: Array = []
	var limit := base_triangles
	var after := -1
	var tolerance := log(TARGET_TOLERANCE)
	for target: int in TARGET_FRACTIONS.size():
		var best := -1
		var best_score := INF
		for level: int in range(after + 1, raw.size()):
			var triangles: int = (raw[level][0] as PackedInt32Array).size() / 3
			if triangles >= limit or triangles < MIN_LEVEL_TRIANGLES:
				continue
			var score := absf(log(float(triangles) / float(base_triangles) / TARGET_FRACTIONS[target]))
			if score < best_score:
				best = level
				best_score = score
		if best < 0 or best_score > tolerance:
			continue
		var kept: int = (raw[best][0] as PackedInt32Array).size() / 3
		chosen.append({"level": best, "target": target, "triangles": kept})
		limit = kept
		after = best
	return chosen


## Welds the surface's vertices by position (WELD_QUANTUM). Returns {remap
## (vertex -> welded id), representatives (welded id -> first vertex),
## positions, coherence}: the share of corners whose UV, bones and weights
## equal those of their position's representative vertex.
static func weld(arrays: Array) -> Dictionary:
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var count := vertices.size()
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV] if arrays[Mesh.ARRAY_TEX_UV] is PackedVector2Array else PackedVector2Array()
	var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES] if arrays[Mesh.ARRAY_BONES] is PackedInt32Array else PackedInt32Array()
	var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS] if arrays[Mesh.ARRAY_WEIGHTS] is PackedFloat32Array else PackedFloat32Array()
	if uvs.size() != count:
		uvs = PackedVector2Array()
	var stride := bones.size() / count if count > 0 and bones.size() % count == 0 else 0
	if stride == 0 or weights.size() != bones.size():
		stride = 0
	var inverse := 1.0 / WELD_QUANTUM
	var ids := {}
	var remap := PackedInt32Array()
	remap.resize(count)
	var representatives := PackedInt32Array()
	var positions := PackedVector3Array()
	var agrees := PackedByteArray()
	agrees.resize(count)
	for vertex: int in count:
		var position := vertices[vertex]
		var key := Vector3i(roundi(position.x * inverse), roundi(position.y * inverse), roundi(position.z * inverse))
		var id: int = ids.get(key, -1)
		if id < 0:
			id = positions.size()
			ids[key] = id
			positions.append(position)
			representatives.append(vertex)
			agrees[vertex] = 1
		else:
			agrees[vertex] = int(_agree(vertex, representatives[id], uvs, bones, weights, stride))
		remap[vertex] = id
	var agreeing := 0
	for index: int in indices:
		agreeing += agrees[index]
	return {"remap": remap, "representatives": representatives, "positions": positions,
		"coherence": float(agreeing) / float(maxi(indices.size(), 1))}


static func _agree(vertex: int, other: int, uvs: PackedVector2Array, bones: PackedInt32Array,
		weights: PackedFloat32Array, stride: int) -> bool:
	if not uvs.is_empty() and uvs[vertex].distance_squared_to(uvs[other]) > UV_EPSILON_SQUARED:
		return false
	for offset: int in stride:
		var a := vertex * stride + offset
		var b := other * stride + offset
		if bones[a] != bones[b] or absf(weights[a] - weights[b]) > WEIGHT_EPSILON:
			return false
	return true


## Simplifies the position-welded proxy (positions, area-weighted normals, no
## UVs) and maps every proxy corner back to an original vertex at that
## position. Returns [[PackedInt32Array, error, island share], ...] by
## ascending error (see _map_level).
static func proxy_chain(arrays: Array, welded: Dictionary) -> Array:
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var remap: PackedInt32Array = welded.remap
	var positions: PackedVector3Array = welded.positions
	var proxy_indices := PackedInt32Array()
	for corner: int in range(0, indices.size(), 3):
		var a := remap[indices[corner]]
		var b := remap[indices[corner + 1]]
		var c := remap[indices[corner + 2]]
		if a != b and b != c and a != c:
			proxy_indices.append(a)
			proxy_indices.append(b)
			proxy_indices.append(c)
	if proxy_indices.size() < 3 * MIN_LEVEL_TRIANGLES:
		return []
	var normals := PackedVector3Array()
	normals.resize(positions.size())
	for corner: int in range(0, proxy_indices.size(), 3):
		var a := positions[proxy_indices[corner]]
		var face := (positions[proxy_indices[corner + 2]] - a).cross(positions[proxy_indices[corner + 1]] - a)
		for offset: int in 3:
			normals[proxy_indices[corner + offset]] += face
	for id: int in normals.size():
		normals[id] = normals[id].normalized() if normals[id].length_squared() > 0.0 else Vector3.UP
	var proxy_arrays: Array = []
	proxy_arrays.resize(Mesh.ARRAY_MAX)
	proxy_arrays[Mesh.ARRAY_VERTEX] = positions
	proxy_arrays[Mesh.ARRAY_NORMAL] = normals
	proxy_arrays[Mesh.ARRAY_INDEX] = proxy_indices
	var probe := ImporterMesh.new()
	probe.add_surface(Mesh.PRIMITIVE_TRIANGLES, proxy_arrays)
	probe.generate_lods(MERGE_ANGLE, SPLIT_ANGLE, [])
	var levels := _levels_of(probe)
	if levels.is_empty():
		return []
	var back := _back_map(indices, welded)
	var mapped: Array = []
	for level: Array in levels:
		var level_map := _map_level(level[0], welded.representatives, back)
		mapped.append([level_map.indices, float(level[1]), float(level_map.island_share)])
	return mapped


## The original vertices behind each welded position and the island of every
## vertex: {islands: PackedInt32Array (vertex -> island), shared: {welded id ->
## PackedInt32Array of its vertices, representative first}} for positions
## held by several vertices. An island is a connected set of original
## triangles that share vertices (a UV chart of a welded mesh; one triangle of
## a soup).
static func _back_map(indices: PackedInt32Array, welded: Dictionary) -> Dictionary:
	var remap: PackedInt32Array = welded.remap
	var representatives: PackedInt32Array = welded.representatives
	var parents := PackedInt32Array()
	parents.resize(remap.size())
	for vertex: int in remap.size():
		parents[vertex] = vertex
	for corner: int in range(0, indices.size(), 3):
		var root := _find(parents, indices[corner])
		for offset: int in [1, 2]:
			var other := _find(parents, indices[corner + offset])
			if other != root:
				parents[maxi(other, root)] = mini(other, root)
				root = mini(other, root)
	var islands := PackedInt32Array()
	islands.resize(remap.size())
	for vertex: int in remap.size():
		islands[vertex] = _find(parents, vertex)
	var shared := {}
	for vertex: int in remap.size():
		var id := remap[vertex]
		if representatives[id] == vertex:
			continue
		var vertices: PackedInt32Array = shared.get(id, PackedInt32Array([representatives[id]]))
		vertices.append(vertex)
		shared[id] = vertices
	return {"islands": islands, "shared": shared}


static func _find(parents: PackedInt32Array, vertex: int) -> int:
	var root := vertex
	while parents[root] != root:
		root = parents[root]
	while parents[vertex] != root:
		var next := parents[vertex]
		parents[vertex] = root
		vertex = next
	return root


## Maps one proxy level's triangles to original vertices: a triangle whose
## three positions have vertices on one original island takes those vertices
## (no UV seam crossed); otherwise each corner takes its position's first
## vertex. Returns {indices, island_share}: the share of triangles drawn from
## one island.
static func _map_level(level: PackedInt32Array, representatives: PackedInt32Array, back: Dictionary) -> Dictionary:
	var islands: PackedInt32Array = back.islands
	var shared: Dictionary = back.shared
	var out := PackedInt32Array()
	out.resize(level.size())
	var on_island := 0
	for corner: int in range(0, level.size(), 3):
		var a := level[corner]
		var b := level[corner + 1]
		var c := level[corner + 2]
		out[corner] = representatives[a]
		out[corner + 1] = representatives[b]
		out[corner + 2] = representatives[c]
		if not (shared.has(a) or shared.has(b) or shared.has(c)):
			var island := islands[representatives[a]]
			on_island += int(islands[representatives[b]] == island and islands[representatives[c]] == island)
			continue
		var options_a: PackedInt32Array = shared.get(a, PackedInt32Array([representatives[a]]))
		var options_b: PackedInt32Array = shared.get(b, PackedInt32Array([representatives[b]]))
		var options_c: PackedInt32Array = shared.get(c, PackedInt32Array([representatives[c]]))
		for vertex_a: int in options_a:
			var island := islands[vertex_a]
			var vertex_b := _on_island(options_b, islands, island)
			if vertex_b < 0:
				continue
			var vertex_c := _on_island(options_c, islands, island)
			if vertex_c < 0:
				continue
			out[corner] = vertex_a
			out[corner + 1] = vertex_b
			out[corner + 2] = vertex_c
			on_island += 1
			break
	return {"indices": out, "island_share": float(on_island) / float(maxi(level.size() / 3, 1))}


static func _on_island(options: PackedInt32Array, islands: PackedInt32Array, island: int) -> int:
	for vertex: int in options:
		if islands[vertex] == island:
			return vertex
	return -1
