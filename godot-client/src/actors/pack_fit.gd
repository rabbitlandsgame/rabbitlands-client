extends RefCounted
## Back equipment fits derive from immutable meshes so outfit swaps cannot drift.
const LOD_READER := preload("res://src/actors/wardrobe_shirt_fit.gd")
const CACHE_LIMIT := 48
static var _cache: Dictionary = {}


static func clear() -> void:
	_cache.clear()


static func fit_quiver(instance: MeshInstance3D, packs: Array, outfit: String) -> void:
	if instance.mesh == null or packs.is_empty():
		return
	var source := instance.mesh
	var key := "quiver|%d|%s" % [source.get_instance_id(), outfit]
	if not _cache.has(key):
		var left := INF
		var right := -INF
		for node: Node in packs:
			if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
				var bounds := (node as MeshInstance3D).mesh.get_aabb()
				left = minf(left, bounds.position.x)
				right = maxf(right, bounds.end.x)
		var rear := []
		for surface: int in source.get_surface_count():
			for point: Vector3 in source.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]:
				if point.z < -0.07:
					rear.append(point.x)
		var center := 0.0
		for value: float in rear:
			center += value / maxf(1.0, rear.size())
		var direction := -1.0 if center < 0.0 else 1.0
		var edge := left if direction < 0.0 else right
		var shift := edge + direction * 0.10 - center
		if _cache.size() >= CACHE_LIMIT:
			_cache.clear()
		_cache[key] = shifted(source, Vector3(shift, 0.0, 0.0))
	instance.mesh = _cache[key] as Mesh


static func shifted(source: Mesh, offset: Vector3) -> Mesh:
	var result := ArrayMesh.new()
	for shape: int in range(source.get_blend_shape_count()):
		result.add_blend_shape(source.get_blend_shape_name(shape))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	for surface: int in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var offsets := PackedVector3Array()
		offsets.resize(vertices.size())
		for vertex: int in vertices.size():
			var rear := 1.0 - smoothstep(-0.045, 0.04, vertices[vertex].z)
			offsets[vertex] = offset * rear
			vertices[vertex] += offsets[vertex]
		arrays[Mesh.ARRAY_VERTEX] = vertices
		var shapes := source.surface_get_blend_shape_arrays(surface)
		if result.blend_shape_mode == Mesh.BLEND_SHAPE_MODE_NORMALIZED:
			for shape_arrays: Array in shapes:
				var points: PackedVector3Array = shape_arrays[Mesh.ARRAY_VERTEX]
				for vertex: int in points.size():
					points[vertex] += offsets[vertex]
				shape_arrays[Mesh.ARRAY_VERTEX] = points
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays,
			shapes, LOD_READER._surface_lods(source, surface),
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result
