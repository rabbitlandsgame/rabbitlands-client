class_name MeshRestCoordinates
extends RefCounted
## RD skinning runs before spatial vertex(), so VERTEX is already posed.
## An unused custom attribute carries source coordinates without changing any
## authored position, normal, UV, colour, skin, index or morph array. Callers
## retain ownership through their existing mesh caches and restore paths.

static func surface_flags(format: int) -> int:
	var flags := format & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS
	for shift: int in [Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT, Mesh.ARRAY_FORMAT_CUSTOM1_SHIFT,
			Mesh.ARRAY_FORMAT_CUSTOM2_SHIFT, Mesh.ARRAY_FORMAT_CUSTOM3_SHIFT]:
		flags |= format & (7 << shift)
	return flags

static func add(arrays: Array) -> void:
	assert(arrays[Mesh.ARRAY_CUSTOM0] == null or arrays[Mesh.ARRAY_CUSTOM0].is_empty(),
		"Rest coordinates require an unused CUSTOM0 channel")
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var values := PackedFloat32Array()
	values.resize(points.size() * 3)
	for vertex: int in points.size():
		for axis: int in 3:
			values[vertex * 3 + axis] = points[vertex][axis]
	arrays[Mesh.ARRAY_CUSTOM0] = values

static func with_rest(format: int) -> int:
	return surface_flags(format) | (Mesh.ARRAY_CUSTOM_RGB_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT)

static func for_material(source: Mesh, material_name: String) -> Mesh:
	assert(source is ArrayMesh, "Rest coordinates require a packed ArrayMesh")
	# ArrayMesh's serialized surfaces retain its already-packed vertex, skin,
	# index and morph buffers. Rebuilding every primitive from decoded arrays
	# would needlessly quantize face/eye normals and generated tangents again.
	var surfaces: Array = source.get("_surfaces")
	assert(surfaces.size() == source.get_surface_count())
	var result := ArrayMesh.new()
	result.resource_name = source.resource_name
	result.custom_aabb = (source as ArrayMesh).custom_aabb
	result.shadow_mesh = (source as ArrayMesh).shadow_mesh
	for shape: int in source.get_blend_shape_count():
		result.add_blend_shape(source.get_blend_shape_name(shape))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	for key: StringName in source.get_meta_list():
		result.set_meta(key, source.get_meta(key))
	for surface: int in surfaces.size():
		var material := source.surface_get_material(surface)
		if material == null or material.resource_name != material_name:
			continue
		var packed: Dictionary = surfaces[surface].duplicate()
		var format: int = packed["format"]
		assert((format & Mesh.ARRAY_FORMAT_CUSTOM0) == 0, "Rest coordinates require an unused CUSTOM0")
		var count: int = packed["vertex_count"]
		var next_format := format | Mesh.ARRAY_FORMAT_CUSTOM0 \
			| (Mesh.ARRAY_CUSTOM_RGB_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT)
		var stride := RenderingServer.mesh_surface_get_format_attribute_stride(format, count)
		var next_stride := RenderingServer.mesh_surface_get_format_attribute_stride(next_format, count)
		var original: PackedByteArray = packed.get("attribute_data", PackedByteArray())
		assert(original.size() == count * stride)
		var attributes := PackedByteArray()
		attributes.resize(count * next_stride)
		# Existing UV, colour and other custom channels keep their exact packed
		# bytes, even when CUSTOM0 is inserted before an existing CUSTOM1.
		var channels: Array[int] = []
		for channel: int in [Mesh.ARRAY_COLOR, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2,
				Mesh.ARRAY_CUSTOM1, Mesh.ARRAY_CUSTOM2, Mesh.ARRAY_CUSTOM3]:
			if format & (1 << channel): channels.append(channel)
		channels.sort_custom(func(a: int, b: int) -> bool:
			return RenderingServer.mesh_surface_get_format_offset(format, count, a) \
				< RenderingServer.mesh_surface_get_format_offset(format, count, b))
		for index: int in channels.size():
			var channel := channels[index]
			var offset := RenderingServer.mesh_surface_get_format_offset(format, count, channel)
			var end := RenderingServer.mesh_surface_get_format_offset(format, count, channels[index + 1]) \
				if index + 1 < channels.size() else stride
			var next_offset := RenderingServer.mesh_surface_get_format_offset(next_format, count, channel)
			for vertex: int in count:
				for byte: int in end - offset:
					attributes[vertex * next_stride + next_offset + byte] = original[vertex * stride + offset + byte]
		var points: PackedVector3Array = source.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
		var position_bytes := points.to_byte_array()
		var offset := RenderingServer.mesh_surface_get_format_offset(next_format, count, Mesh.ARRAY_CUSTOM0)
		for vertex: int in count:
			for byte: int in 12:
				attributes[vertex * next_stride + offset + byte] = position_bytes[vertex * 12 + byte]
		packed["format"] = next_format
		packed["attribute_data"] = attributes
		surfaces[surface] = packed
	result.set("_surfaces", surfaces)
	return result
