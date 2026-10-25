class_name TerrainTargetPreview
extends RefCounted
## Surface-following spell footprint. Missing samples and cliff edges leave
## gaps instead of projecting a floating sheet across water or a drop.
const LIFT := 0.04

static func build(center: Vector3, width: float, sample: Callable,
		spacing := 0.5) -> ArrayMesh:
	var steps := maxi(1, ceili(width / maxf(spacing, 0.05)))
	var stride := width / steps
	var points: Array = []
	for z: int in steps + 1:
		for x: int in steps + 1:
			var point := center + Vector3(x * stride - width * 0.5, 0,
				z * stride - width * 0.5)
			var hit: Variant = sample.call(point)
			points.append(hit + Vector3.UP * LIFT if hit is Vector3 else null)
	var vertices := PackedVector3Array()
	for z: int in steps:
		for x: int in steps:
			var a := z * (steps + 1) + x
			for triangle: Array in [[a, a + steps + 1, a + 1],
					[a + 1, a + steps + 1, a + steps + 2]]:
				var p: Variant = points[triangle[0]]
				var q: Variant = points[triangle[1]]
				var t: Variant = points[triangle[2]]
				if not p is Vector3 or not q is Vector3 or not t is Vector3:
					continue
				# Sloped ground is continuous; a step/cliff is not. Do not fill
				# a vertical discontinuity with a diagonal floating triangle.
				if maxf(p.y, maxf(q.y, t.y)) - minf(p.y, minf(q.y, t.y)) > stride * 1.5:
					continue
				vertices.append(p - center)
				vertices.append(q - center)
				vertices.append(t - center)
	var mesh := ArrayMesh.new()
	if not vertices.is_empty():
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
