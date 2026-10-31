extends SceneTree
const Subdivide := preload("res://src/actors/rl_head/rl_headwear_trail_subdivision.gd")
var checks := 0
var failures := 0

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(message)

func source_arrays() -> Array:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, .12, 0), Vector3(.02, .12, 0), Vector3(.02, 0, 0), Vector3.ZERO])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK, Vector3.BACK])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO, Vector2(1, 0), Vector2.ONE, Vector2(0, 1)])
	arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color.RED, Color.RED, Color.BLUE, Color.BLUE])
	arrays[Mesh.ARRAY_TANGENT] = PackedFloat32Array([1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1])
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array([0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 0, 2, 3])
	return arrays

func _initialize() -> void:
	var original := source_arrays()
	var active := PackedFloat32Array([0, 0, 1, 1])
	var disabled: Dictionary = Subdivide.refine(original, Transform3D.IDENTITY, active, {})
	check(disabled.ok and not disabled.changed, "Absent configuration must keep the exact old path")
	for slot: int in original.size():
		check(disabled.arrays[slot] == original[slot], "Disabled subdivision changed source slot %d" % slot)
	var result: Dictionary = Subdivide.refine(original, Transform3D.IDENTITY, active,
		{"maxEdgeMm": 20, "maxAddedTriangles": 1000, "maxPasses": 10})
	check(result.ok and result.added_triangles > 0 and result.added_triangles <= 1000, "Bounded refinement must produce a useful cloth surface")
	if result.ok:
		var arrays: Array = result.arrays
		var p: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for slot: int in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_COLOR]:
			check(arrays[slot].slice(0, 4) == original[slot], "Original vertex attribute prefix changed")
		check(arrays[Mesh.ARRAY_BONES].slice(0, 16) == original[Mesh.ARRAY_BONES], "Original skin joints changed")
		check(arrays[Mesh.ARRAY_WEIGHTS].slice(0, 16) == original[Mesh.ARRAY_WEIGHTS], "Original skin weights changed")
		var area := 0.0
		var longest := 0.0
		for offset: int in range(0, indices.size(), 3):
			var a := p[indices[offset]]
			var b := p[indices[offset + 1]]
			var c := p[indices[offset + 2]]
			area += (b - a).cross(c - a).length() * .5
			longest = maxf(longest, maxf(a.distance_to(b), maxf(b.distance_to(c), c.distance_to(a))))
			check((b - a).cross(c - a).z < 0, "Child face winding changed")
		check(absf(area - .0024) < 1e-7, "Refinement changed the original cloth surface area")
		check(longest <= .020001, "Active cloth edges exceed the physical target")
		var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
		var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
		for vertex: int in p.size():
			check(uv[vertex].distance_to(Vector2(p[vertex].x / .02, 1.0 - p[vertex].y / .12)) < 1e-5, "UV interpolation changed painted cloth flow")
			var head_weight := 0.0
			var sum_weight := 0.0
			for at: int in 4:
				sum_weight += weights[vertex * 4 + at]
				if bones[vertex * 4 + at] == 0:
					head_weight += weights[vertex * 4 + at]
			check(absf(sum_weight - 1.0) < 1e-6, "New skin weights are not normalized")
			check(absf(head_weight - p[vertex].y / .12) < 1e-5, "New skin influences were pruned or averaged as joint indices")
	var limited: Dictionary = Subdivide.refine(original, Transform3D.IDENTITY, active,
		{"maxEdgeMm": 3, "maxAddedTriangles": 1, "maxPasses": 10})
	check(not limited.ok, "An inadequate triangle budget must fail closed")
	check(limited.arrays == original, "Failed preparation changed the original arrays")
	var rigid: Dictionary = Subdivide.refine(original, Transform3D.IDENTITY, PackedFloat32Array([0, 0, 0, 0]),
		{"maxEdgeMm": 3, "maxAddedTriangles": 1, "maxPasses": 10})
	check(rigid.ok and not rigid.changed and rigid.arrays == original, "Rigid crown must remain exact")
	var unindexed := original.duplicate()
	unindexed[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	unindexed[Mesh.ARRAY_INDEX] = null
	for slot: int in [Mesh.ARRAY_NORMAL, Mesh.ARRAY_TANGENT, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_COLOR, Mesh.ARRAY_BONES, Mesh.ARRAY_WEIGHTS]:
		unindexed[slot] = null
	var untouched: Dictionary = Subdivide.refine(unindexed, Transform3D.IDENTITY, PackedFloat32Array([0, 0, 0]),
		{"maxEdgeMm": 12, "maxAddedTriangles": 100, "maxPasses": 10})
	check(untouched.ok and untouched.arrays == unindexed, "Rigid unindexed geometry must retain its original index representation")
	var overloaded := source_arrays()
	overloaded[Mesh.ARRAY_BONES] = PackedInt32Array([0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 6, 7, 4, 5, 6, 7])
	overloaded[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([.25, .25, .25, .25, .25, .25, .25, .25, .25, .25, .25, .25, .25, .25, .25, .25])
	var too_many: Dictionary = Subdivide.refine(overloaded, Transform3D.IDENTITY, active,
		{"maxEdgeMm": 20, "maxAddedTriangles": 1000, "maxPasses": 10})
	check(not too_many.ok and too_many.arrays == overloaded, "Skin interpolation must fail rather than prune influences")
	test_uv_seam()
	print("HEADWEAR_TRAIL_SUBDIVISION_TESTS ", checks, " checks, ", failures, " failures")
	quit(0 if failures == 0 else 1)

func test_uv_seam() -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, .12, 0), Vector3(.02, .12, 0), Vector3(.02, 0, 0), Vector3(0, .12, 0), Vector3(.02, 0, 0), Vector3.ZERO])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2(0, 0), Vector2(.2, 0), Vector2(.2, 1), Vector2(.8, 0), Vector2(1, 1), Vector2(.8, 1)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 3, 4, 5])
	var result: Dictionary = Subdivide.refine(arrays, Transform3D.IDENTITY, PackedFloat32Array([1, 1, 1, 0, 0, 0]),
		{"maxEdgeMm": 20, "maxAddedTriangles": 1000, "maxPasses": 10})
	check(result.ok, "UV-split cloth must support conforming refinement")
	if not result.ok:
		return
	var p: PackedVector3Array = result.arrays[Mesh.ARRAY_VERTEX]
	var uv: PackedVector2Array = result.arrays[Mesh.ARRAY_TEX_UV]
	var indices: PackedInt32Array = result.arrays[Mesh.ARRAY_INDEX]
	var geometric := PackedInt32Array()
	var unique := {}
	for point: Vector3 in p:
		if not unique.has(point):
			unique[point] = unique.size()
		geometric.append(int(unique[point]))
	var edges := {}
	for offset: int in range(0, indices.size(), 3):
		for side: int in 3:
			var a := indices[offset + side]
			var b := indices[offset + (side + 1) % 3]
			var key := Vector2i(mini(geometric[a], geometric[b]), maxi(geometric[a], geometric[b]))
			edges[key] = int(edges.get(key, 0)) + 1
			if p[a].x > 1e-6 and p[a].x < .019999 and p[b].x > 1e-6 and p[b].x < .019999:
				check(int(edges[key]) <= 2, "UV seam generated a nonmanifold geometric edge")
	var seam_mid := Vector3(.01, .06, 0)
	var charts := []
	for vertex: int in p.size():
		if p[vertex].distance_to(seam_mid) < 1e-6:
			charts.append(uv[vertex].x)
	check(charts.size() == 2 and absf(float(charts[0]) - float(charts[1])) > .5, "Shared geometric split must retain both separate UV charts")
