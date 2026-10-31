class_name RLHeadNeckNormals
extends RefCounted
## Seven reviewed UV splits in the male neck patch carry hard normals. The
## adjoining face already averages their unique normals; keep that face exact
## and make the patch/body copies agree in the existing derived-mesh caches.
const POINTS: Array[Vector3] = [
	Vector3(-.020411404,1.468350887,.016450554),
	Vector3(-.020393837,1.502280712,.013905147),
	Vector3(-.019370040,1.489990115,.014231184),
	Vector3(-.020156836,1.502357960,.013762259),
	Vector3(.000427603,1.491602421,.016336361),
	Vector3(-.001402467,1.500108123,.017924225),
	Vector3(.014216422,1.501896739,.014615525),
]
const TOLERANCE := .0000002
# Decoded canonical patch POSITION+NORMAL streams, identical in all three
# LODs on the supported importer. An unfamiliar import is left unchanged.
const SOURCE_SIGNATURE := "1047e17e32410e82afbe8922c4f6fe353d8c739d7e65097c22c1023757c25f3d"
const BODY_SHA256 := "1cc5bd8cd2761e71f711dc33aabd500ea88cb918c0806223991cb5bd87bb2d75"

static func prepare_lods(lods: Array, body_path: String) -> void:
	# Commit all three derivatives and the body plan together, only after every
	# reviewed layout has passed. No partial head/body normal correction.
	if lods.size() != 3 or FileAccess.get_sha256(body_path) != BODY_SHA256:return
	var prepared: Array[Dictionary] = []
	var shared: Array = []
	for level: Array in lods:
		if level.size() != 1:return
		var piece: Dictionary = level[0]
		var source := piece.get("mesh") as ArrayMesh
		if source == null:return
		var targets := plan(source)
		if targets.is_empty() or (not shared.is_empty() and targets != shared):return
		var derived := patch(source,targets)
		if derived == source:return
		shared = targets
		prepared.append({"piece":piece,"mesh":derived})
	for item: Dictionary in prepared:
		item.piece["mesh"] = item.mesh
		item.piece["neck_normals"] = shared

static func plan(source: Mesh) -> Array[Dictionary]:
	if source is not ArrayMesh or source.blend_shape_mode != Mesh.BLEND_SHAPE_MODE_NORMALIZED \
			or source.get_blend_shape_count() != 75:return []
	var selected := -1
	for surface: int in source.get_surface_count():
		var material := source.surface_get_material(surface)
		if material != null and material.resource_name == "rl_bodypatch":
			if selected != -1:return []
			selected = surface
	if selected < 0:return []
	for surface: int in source.get_surface_count():
		if surface != selected:continue
		var arrays := source.surface_get_arrays(surface)
		if arrays[Mesh.ARRAY_VERTEX] is not PackedVector3Array \
				or arrays[Mesh.ARRAY_NORMAL] is not PackedVector3Array:return []
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		if points.size() != 115 or normals.size() != points.size():return []
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		context.update(points.to_byte_array())
		context.update(normals.to_byte_array())
		if context.finish().hex_encode() != SOURCE_SIGNATURE:return []
		var packed: Dictionary = (source.get("_surfaces") as Array)[surface]
		var format: int = packed.format
		var count := points.size()
		if not format & Mesh.ARRAY_FORMAT_NORMAL or not format & Mesh.ARRAY_FORMAT_TANGENT \
				or format & Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES:return []
		if RenderingServer.mesh_surface_get_format_normal_tangent_stride(format,count) != 8 \
				or (packed.vertex_data as PackedByteArray).size() != count * 20 \
				or (packed.blend_shapes as PackedByteArray).size() != 75 * count * 20:return []
		var shapes := source.surface_get_blend_shape_arrays(surface)
		if shapes.size() != 75:return []
		var result: Array[Dictionary] = []
		var affected := 0
		for position: Vector3 in POINTS:
			var rows: Array[int] = []
			var unique := {}
			for row: int in points.size():
				if points[row].distance_to(position) <= TOLERANCE:
					rows.append(row)
					unique[normals[row]] = true
			if rows.size() < 2 or unique.size() != 2:return []
			for shape: Array in shapes:
				if shape[Mesh.ARRAY_NORMAL] is not PackedVector3Array \
						or shape[Mesh.ARRAY_NORMAL].size() != count:return []
				for row: int in rows:
					if shape[Mesh.ARRAY_NORMAL][row] != normals[row]:return []
			var normal := Vector3.ZERO
			for value: Vector3 in unique:normal += value
			result.append({"position":points[rows[0]],"normal":normal.normalized(),"rows":rows})
			affected += rows.size()
		if affected != 15:return []
		return result
	return []

static func apply_body(arrays: Array, targets: Array) -> int:
	if targets.is_empty():return 0
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var changed := 0
	for target: Dictionary in targets:
		for row: int in points.size():
			if points[row].distance_to(target.position) <= TOLERANCE:
				normals[row] = target.normal
				changed += 1
	arrays[Mesh.ARRAY_NORMAL] = normals
	return changed

static func patch(source: ArrayMesh, targets: Array) -> ArrayMesh:
	if targets.is_empty() or targets != plan(source):return source
	var surfaces: Array = source.get("_surfaces")
	for surface: int in surfaces.size():
		var material := source.surface_get_material(surface)
		if material == null or material.resource_name != "rl_bodypatch":continue
		var arrays := source.surface_get_arrays(surface)
		apply_body(arrays, targets)
		# Let ArrayMesh encode the replacement normals. Only its four normal
		# bytes are copied below; all source positions/tangents/other payloads
		# stay packed exactly as imported, including the untouched face/eyes.
		var encoding := ArrayMesh.new()
		var minimal := []
		minimal.resize(Mesh.ARRAY_MAX)
		minimal[Mesh.ARRAY_VERTEX] = arrays[Mesh.ARRAY_VERTEX]
		minimal[Mesh.ARRAY_NORMAL] = arrays[Mesh.ARRAY_NORMAL]
		minimal[Mesh.ARRAY_INDEX] = arrays[Mesh.ARRAY_INDEX]
		encoding.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, minimal)
		var encoded: Dictionary = (encoding.get("_surfaces") as Array)[0]
		var packed: Dictionary = surfaces[surface].duplicate()
		var format: int = packed.format
		var count: int = packed.vertex_count
		var offset := RenderingServer.mesh_surface_get_format_offset(format,count,Mesh.ARRAY_NORMAL)
		var stride := RenderingServer.mesh_surface_get_format_normal_tangent_stride(format,count)
		var encoded_format: int = encoded.format
		var encoded_offset := RenderingServer.mesh_surface_get_format_offset(encoded_format,count,Mesh.ARRAY_NORMAL)
		var encoded_stride := RenderingServer.mesh_surface_get_format_normal_tangent_stride(encoded_format,count)
		var vertices: PackedByteArray = packed.vertex_data.duplicate()
		var blend: PackedByteArray = packed.blend_shapes.duplicate()
		var frames := source.get_blend_shape_count()
		for target: Dictionary in targets:
			for row: int in target.rows:
				for byte: int in 4:
					var value: int = (encoded.vertex_data as PackedByteArray)[encoded_offset + encoded_stride * row + byte]
					vertices[offset + stride * row + byte] = value
					for frame: int in frames:
						blend[frame * count * 20 + offset + stride * row + byte] = value
		packed.vertex_data = vertices
		packed.blend_shapes = blend
		surfaces[surface] = packed
	var result := ArrayMesh.new()
	result.resource_name = source.resource_name
	result.custom_aabb = source.custom_aabb
	result.shadow_mesh = source.shadow_mesh
	for shape: int in source.get_blend_shape_count():result.add_blend_shape(source.get_blend_shape_name(shape))
	result.blend_shape_mode = source.blend_shape_mode
	for key: StringName in source.get_meta_list():result.set_meta(key,source.get_meta(key))
	result.set("_surfaces",surfaces)
	return result
