extends RefCounted
## Optional preparation of sparse hanging cloth before the existing draper.
## Original vertex rows remain exact. UV seams receive separate midpoints;
## coincident geometric edges share split decisions, avoiding cracks.

const SUPPORTED := [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TANGENT,
	Mesh.ARRAY_COLOR, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2,
	Mesh.ARRAY_BONES, Mesh.ARRAY_WEIGHTS, Mesh.ARRAY_INDEX]

static func _failure(arrays: Array, reason: String) -> Dictionary:
	return {"ok": false, "arrays": arrays, "reason": reason}

static func _edge(a: int, b: int) -> Vector2i:
	return Vector2i(mini(a, b), maxi(a, b))

static func _append_triangle(out: PackedInt32Array, a: int, b: int, c: int) -> void:
	out.append(a)
	out.append(b)
	out.append(c)

static func refine(arrays: Array, placed: Transform3D,
		eligibility: PackedFloat32Array, config: Dictionary) -> Dictionary:
	if config.is_empty():
		return {"ok": true, "arrays": arrays, "added_triangles": 0, "changed": false}
	var edge_mm := float(config.get("maxEdgeMm", 12.0))
	var budget := int(config.get("maxAddedTriangles", 4096))
	var passes := int(config.get("maxPasses", 10))
	if not is_finite(edge_mm) or edge_mm < 3.0 or edge_mm > 50.0 \
			or budget < 1 or budget > 16384 or passes < 1 or passes > 12:
		return _failure(arrays, "Invalid bounded trail-subdivision configuration")
	var initial: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	if initial.is_empty() or eligibility.size() != initial.size():
		return _failure(arrays, "Trail eligibility must match the source vertices")
	for slot: int in arrays.size():
		if slot not in SUPPORTED and arrays[slot] != null and arrays[slot].size() > 0:
			return _failure(arrays, "Unsupported source attribute in slot %d" % slot)
	for slot: int in [Mesh.ARRAY_NORMAL, Mesh.ARRAY_COLOR, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2]:
		if arrays[slot] != null and arrays[slot].size() > 0 and arrays[slot].size() != initial.size():
			return _failure(arrays, "Source vertex attribute count differs in slot %d" % slot)
	if arrays[Mesh.ARRAY_TANGENT] != null and arrays[Mesh.ARRAY_TANGENT].size() > 0 \
			and arrays[Mesh.ARRAY_TANGENT].size() != initial.size() * 4:
		return _failure(arrays, "Source tangent count must have four values per vertex")
	var work := arrays.duplicate()
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] \
		if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array(range(initial.size()))
	if indices.size() % 3 != 0:
		return _failure(arrays, "Only indexed triangles may be subdivided")
	for index: int in indices:
		if index < 0 or index >= initial.size():
			return _failure(arrays, "Source triangle index is out of bounds")
	var original_triangles := indices.size() / 3
	var active := eligibility.duplicate()
	var total_midpoints := 0
	for iteration: int in passes + 1:
		var vertices: PackedVector3Array = work[Mesh.ARRAY_VERTEX]
		var shipped := PackedVector3Array()
		var geometric := PackedInt32Array()
		var by_position := {}
		for p: Vector3 in vertices:
			var point := placed * p
			if not point.is_finite():
				return _failure(arrays, "Non-finite source position")
			shipped.append(point)
			if not by_position.has(point):
				by_position[point] = by_position.size()
			geometric.append(int(by_position[point]))
		var marked := {}
		for offset: int in range(0, indices.size(), 3):
			var face := Vector3i(indices[offset], indices[offset + 1], indices[offset + 2])
			if maxf(active[face.x], maxf(active[face.y], active[face.z])) <= 0.0:
				continue
			for pair: Vector2i in [_edge(face.x, face.y), _edge(face.y, face.z), _edge(face.z, face.x)]:
				if shipped[pair.x].distance_to(shipped[pair.y]) > edge_mm * 0.001 + 1e-7:
					marked[_edge(geometric[pair.x], geometric[pair.y])] = true
		if marked.is_empty():
			if total_midpoints > 0:
				work[Mesh.ARRAY_INDEX] = indices
			return {"ok": true, "arrays": work if total_midpoints > 0 else arrays, "changed": total_midpoints > 0,
				"added_triangles": indices.size() / 3 - original_triangles,
				"new_vertices": vertices.size() - initial.size(), "passes": iteration,
				"original_vertex_rows": initial.size()}
		if iteration == passes:
			return _failure(arrays, "Trail edge target exceeded its bounded pass count")
		var midpoint_ids := {}
		var plans: Array[Vector2i] = []
		var masks := PackedInt32Array()
		var added := 0
		for offset: int in range(0, indices.size(), 3):
			var a := indices[offset]
			var b := indices[offset + 1]
			var c := indices[offset + 2]
			var mask := 0
			var edges: Array[Vector2i] = [_edge(a, b), _edge(b, c), _edge(c, a)]
			for side: int in 3:
				var pair := edges[side]
				if marked.has(_edge(geometric[pair.x], geometric[pair.y])):
					mask |= 1 << side
					added += 1
					if not midpoint_ids.has(pair):
						midpoint_ids[pair] = vertices.size() + plans.size()
						plans.append(pair)
			masks.append(mask)
		if indices.size() / 3 - original_triangles + added > budget:
			return _failure(arrays, "Trail refinement exceeded its added-triangle budget")
		var expanded := _expand_attributes(work, plans)
		if not expanded.ok:
			return _failure(arrays, str(expanded.reason))
		work = expanded.arrays
		var next_active := active.duplicate()
		for pair: Vector2i in plans:
			next_active.append((active[pair.x] + active[pair.y]) * 0.5)
		active = next_active
		var next := PackedInt32Array()
		for face_index: int in masks.size():
			var a := indices[face_index * 3]
			var b := indices[face_index * 3 + 1]
			var c := indices[face_index * 3 + 2]
			var ab := int(midpoint_ids.get(_edge(a, b), -1))
			var bc := int(midpoint_ids.get(_edge(b, c), -1))
			var ca := int(midpoint_ids.get(_edge(c, a), -1))
			match masks[face_index]:
				0: _append_triangle(next, a, b, c)
				1:
					_append_triangle(next, a, ab, c)
					_append_triangle(next, ab, b, c)
				2:
					_append_triangle(next, a, b, bc)
					_append_triangle(next, a, bc, c)
				4:
					_append_triangle(next, a, b, ca)
					_append_triangle(next, b, c, ca)
				3:
					_append_triangle(next, b, bc, ab)
					_append_triangle(next, a, ab, c)
					_append_triangle(next, ab, bc, c)
				6:
					_append_triangle(next, c, ca, bc)
					_append_triangle(next, a, b, bc)
					_append_triangle(next, a, bc, ca)
				5:
					_append_triangle(next, a, ab, ca)
					_append_triangle(next, ab, b, c)
					_append_triangle(next, ab, c, ca)
				7:
					_append_triangle(next, a, ab, ca)
					_append_triangle(next, ab, b, bc)
					_append_triangle(next, ca, bc, c)
					_append_triangle(next, ab, bc, ca)
		indices = next
		total_midpoints += plans.size()
	return _failure(arrays, "Unreachable trail-refinement state")

static func _expand_attributes(arrays: Array, plans: Array[Vector2i]) -> Dictionary:
	var out := arrays.duplicate()
	for slot: int in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_COLOR,
			Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2]:
		var source: Variant = arrays[slot]
		if source == null or source.size() == 0:
			continue
		var values: Variant = source.duplicate()
		for pair: Vector2i in plans:
			var midpoint: Variant = (source[pair.x] + source[pair.y]) * 0.5
			if slot == Mesh.ARRAY_NORMAL:
				var normal: Vector3 = midpoint
				midpoint = normal.normalized() if normal.length_squared() > 1e-12 else source[pair.x]
			values.append(midpoint)
		out[slot] = values
	var tangents: Variant = arrays[Mesh.ARRAY_TANGENT]
	if tangents != null and tangents.size() > 0:
		var values: PackedFloat32Array = tangents.duplicate()
		for pair: Vector2i in plans:
			var a := pair.x * 4
			var b := pair.y * 4
			if tangents[a + 3] != tangents[b + 3]:
				return {"ok": false, "reason": "Tangent handedness must split at a UV seam"}
			var t := Vector3(tangents[a] + tangents[b], tangents[a + 1] + tangents[b + 1], tangents[a + 2] + tangents[b + 2]).normalized()
			values.append_array(PackedFloat32Array([t.x, t.y, t.z, tangents[a + 3]]))
		out[Mesh.ARRAY_TANGENT] = values
	var bones: Variant = arrays[Mesh.ARRAY_BONES]
	var weights: Variant = arrays[Mesh.ARRAY_WEIGHTS]
	if bones != null and bones.size() > 0:
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var stride: int = bones.size() / vertices.size()
		if stride not in [4, 8] or weights == null or weights.size() != bones.size():
			return {"ok": false, "reason": "Source skin influences must have matching4/8 slots"}
		var new_bones: PackedInt32Array = bones.duplicate()
		var new_weights: PackedFloat32Array = weights.duplicate()
		for pair: Vector2i in plans:
			var merged := {}
			for vertex: int in [pair.x, pair.y]:
				for at: int in stride:
					var weight := float(weights[vertex * stride + at]) * 0.5
					if weight > 0.0:
						var joint := int(bones[vertex * stride + at])
						merged[joint] = float(merged.get(joint, 0.0)) + weight
			if merged.size() > stride:
				return {"ok": false, "reason": "Midpoint would prune source skin influences"}
			var keys: Array = merged.keys()
			keys.sort()
			var total := 0.0
			for joint: int in keys:
				total += float(merged[joint])
			if total < 1e-8:
				return {"ok": false, "reason": "Source skin midpoint has zero weight"}
			for at: int in stride:
				new_bones.append(int(keys[at]) if at < keys.size() else 0)
				new_weights.append(float(merged[keys[at]]) / total if at < keys.size() else 0.0)
		out[Mesh.ARRAY_BONES] = new_bones
		out[Mesh.ARRAY_WEIGHTS] = new_weights
	return {"ok": true, "arrays": out}
